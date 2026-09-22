#!/usr/bin/env python3

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_PATH = REPO_ROOT / "deploy" / "pipeline" / "server.py"
CONFIG_PATH = REPO_ROOT / "deploy" / "pipeline" / "config.example.json"


def load_server_function(name: str, namespace: dict):
    tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, str(SERVER_PATH), "exec"), namespace)
    return namespace[name]


class ServerContractTests(unittest.TestCase):
    def test_server_uses_one_policy_call_and_finalizes_before_rendering(self):
        source = SERVER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        policy_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_answer_model"
        ]

        self.assertEqual(1, len(policy_calls))
        self.assertNotIn("25+15+15", source)
        self.assertLess(
            source.index("finalization = finalize_claim_evidence"),
            source.index("answer = render_answer_citations", source.index("finalization = finalize_claim_evidence")),
        )
        self.assertIn('"claim_evidence": claim_evidence', source)

        unavailable_handlers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name)
            and node.type.id == "AnswerModelUnavailable"
        ]
        self.assertEqual(1, len(unavailable_handlers))
        fallback_calls = [
            node
            for node in ast.walk(unavailable_handlers[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "recover_authoritative_extractive_answer"
        ]
        self.assertEqual(1, len(fallback_calls))
        self.assertIsInstance(fallback_calls[0].args[0], ast.Name)
        self.assertEqual("q", fallback_calls[0].args[0].id)

    def test_recovery_telemetry_and_extractive_finalizer_contract(self):
        source = SERVER_PATH.read_text(encoding="utf-8")
        for status in (
            "model_fallback_succeeded",
            "extractive_fallback_succeeded",
            "unrecovered",
            "pipeline_error",
        ):
            self.assertIn(f'"{status}"', source)

        response_start = source.index("response = {")
        trace_start = source.index("query_trace.record({", response_start)
        trace_end = source.index("report_request_quality({", trace_start)
        telemetry_field = '"answer_model": answer_model_telemetry'
        self.assertIn(telemetry_field, source[response_start:trace_start])
        self.assertIn(telemetry_field, source[trace_start:trace_end])
        self.assertIn(
            '"authoritative_extractive"',
            source[source.index("_UNTRUSTED_FINALIZER_ORIGINS"):source.index("# ============ 安全配置")],
        )
        self.assertIn(
            "if answer_origin not in _UNTRUSTED_FINALIZER_ORIGINS:",
            source,
        )
        self.assertIn(
            "trusted_deterministic=answer_origin not in _UNTRUSTED_FINALIZER_ORIGINS",
            source,
        )
        self.assertIn(
            "return hydrate_sqlite_authority_sources(sources, fetched)",
            source,
        )
        self.assertIn(
            "elif extractive_fallback_used:\n"
            "            hydrated_finalizer_sources = list(",
            source,
        )
        finalizer_hydration_start = source.index(
            "try:\n                hydrated_finalizer_sources = hydrate_finalizer_sources("
        )
        finalizer_hydration_end = source.index(
            "if answer_origin not in _UNTRUSTED_FINALIZER_ORIGINS:",
            finalizer_hydration_start,
        )
        finalizer_hydration = source[
            finalizer_hydration_start:finalizer_hydration_end
        ]
        self.assertIn("except Exception as exc:", finalizer_hydration)
        self.assertIn("answer = FAIL_CLOSED_ANSWER", finalizer_hydration)
        self.assertIn('answer_origin = "unrecovered"', finalizer_hydration)
        self.assertIn(
            'answer_recovery_status = "pipeline_error"', finalizer_hydration
        )
        self.assertIn(
            "answer_recovery_status = recovery_status_after_finalizer(",
            source,
        )

        pipeline_start = source.index('if extractive_result["pipeline_error"]:')
        pipeline_end = source.index(
            'elif extractive_result["recovered"]:', pipeline_start
        )
        pipeline_branch = source[pipeline_start:pipeline_end]
        self.assertIn('answer_origin = "unrecovered"', pipeline_branch)
        self.assertIn('answer_recovery_status = "pipeline_error"', pipeline_branch)
        self.assertIn("degraded = True", pipeline_branch)

        recovered_start = source.index(
            'elif extractive_result["recovered"]:',
            source.index("except AnswerModelUnavailable as e:"),
        )
        recovered_end = source.index("else:", recovered_start)
        self.assertNotIn(
            "degraded = True",
            source[recovered_start:recovered_end],
        )

    def test_sqlite_hydration_error_returns_fail_closed_pipeline_result(self):
        fail_closed_answer = "safe refusal"

        def fail_hydration(_sources):
            raise OSError("sqlite unavailable")

        recover = load_server_function(
            "recover_authoritative_extractive_answer",
            {
                "hydrate_finalizer_sources": fail_hydration,
                "build_authoritative_extractive_fallback": lambda *_args: self.fail(
                    "extraction must not run after hydration failure"
                ),
                "FAIL_CLOSED_ANSWER": fail_closed_answer,
                "EXTRACTIVE_FALLBACK_POLICY_VERSION": "extractive-v1",
            },
        )

        result = recover("电池状态如何检查？", [{"chunk_id": "chunk:1"}])

        self.assertEqual(fail_closed_answer, result["answer"])
        self.assertEqual({"claims": []}, result["claim_map"])
        self.assertFalse(result["recovered"])
        self.assertEqual([], result["hydrated_sources"])
        self.assertTrue(result["pipeline_error"])
        self.assertEqual("OSError", result["error_type"])

    def test_recovery_helper_passes_original_question_and_hydrates_once(self):
        calls = []
        hydrated = [{"chunk_id": "chunk:1", "text": "SQLite text"}]

        def hydrate(sources):
            calls.append(("hydrate", sources))
            return hydrated

        def extract(question, sources):
            calls.append(("extract", question, sources))
            return {
                "answer": "answer",
                "claim_map": {"claims": []},
                "recovered": True,
                "used_chunk_ids": ["chunk:1"],
                "policy_version": "extractive-v2",
            }

        recover = load_server_function(
            "recover_authoritative_extractive_answer",
            {
                "hydrate_finalizer_sources": hydrate,
                "build_authoritative_extractive_fallback": extract,
                "FAIL_CLOSED_ANSWER": "safe refusal",
                "EXTRACTIVE_FALLBACK_POLICY_VERSION": "extractive-v2",
            },
        )

        raw_sources = [{"chunk_id": "chunk:1"}]
        result = recover("电池状态如何检查？", raw_sources)

        self.assertEqual(
            [
                ("hydrate", raw_sources),
                ("extract", "电池状态如何检查？", hydrated),
            ],
            calls,
        )
        self.assertIs(hydrated, result["hydrated_sources"])
        self.assertFalse(result["pipeline_error"])

    def test_unexpected_answer_pipeline_errors_use_untrusted_safe_refusal(self):
        source = SERVER_PATH.read_text(encoding="utf-8")
        handler_start = source.index(
            "except Exception as e:",
            source.index("except AnswerModelUnavailable as e:"),
        )
        handler_end = source.index("if hybrid_mode", handler_start)
        handler = source[handler_start:handler_end]

        self.assertIn("answer = FAIL_CLOSED_ANSWER", handler)
        self.assertIn('answer_claim_map = {"claims": []}', handler)
        self.assertIn('answer_origin = "unrecovered"', handler)
        self.assertIn('answer_recovery_status = "pipeline_error"', handler)
        self.assertNotIn("build_degraded_answer", source)
        self.assertNotIn('answer_origin = "deterministic_fallback"', source)

    def test_trace_paths_are_explicit_and_do_not_depend_on_symlinks(self):
        source = SERVER_PATH.read_text(encoding="utf-8")

        self.assertIn('"RAG_TRACE_PATH"', source)
        self.assertIn('"RAG_REMOTE_SHADOW_TRACE_PATH"', source)
        self.assertIn("must be a canonical absolute path", source)
        self.assertIn(
            "canonical_absolute_path(configured_path, label=environment_name)",
            source,
        )
        self.assertNotIn(
            'QueryTraceLogger(BASE_DIR / "eval" / "query_traces.jsonl")',
            source,
        )

    def test_runtime_config_contains_only_approved_answer_models(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

        self.assertEqual({"flash", "doubao_mini"}, set(config["models"]))
        self.assertEqual("deepseek-v4-flash", config["models"]["flash"]["name"])
        self.assertEqual(
            "doubao-seed-2-0-mini-260428",
            config["models"]["doubao_mini"]["name"],
        )


if __name__ == "__main__":
    unittest.main()
