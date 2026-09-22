#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPT_DIR))

import eval_cloud_subset as EVAL
import cloud_gold as GOLD
from rag_store.query_trace import encode_trace_chain
from eval_cloud_subset import build_summary, evaluate_case, validate_ask_url

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cloud_gold import reviewed_gold


def response(doc_names, *, answer="reviewed answer", finalizer=True, degraded=False):
    return {
        "route": "rag",
        "degraded": degraded,
        "answer": answer,
        "sources": [{"doc_name": name} for name in doc_names],
        "stats": {
            "trace_id": "trace-1",
            "answer_model": {
                "recovery_status": "not_required",
                "unrecovered_model_failure": False,
            },
        },
        "claim_evidence": {
            "finalizer_invoked": finalizer,
            "outcome": "passed" if finalizer else "not_invoked",
            "unsupported_high_risk_claims": 0,
        },
    }


def gold_case_context():
    return {
        "answer_contract": {
            "scoring_policy_version": "cloud80-strict-segment-v1",
            "answer_mode": "exact_segment_set",
            "safe_refusal_policy": "forbidden",
            "required_claim_groups": [{
                "claim_id": "visibility",
                "description": "Visual line of sight is required",
                "expression_groups": [],
                "accepted_segments": ["运行时必须保持视距内"],
            }],
            "optional_segments": [],
            "forbidden_claims": [],
            "acceptable_synonyms": [{
                "canonical": "视距内",
                "variants": ["VLOS"],
            }],
            "safe_refusal_templates": ["当前证据不足，无法确认。"],
            "authority_sources": [{
                "source_name": "政策法规_测试规则.txt",
                "authority_kind": "regulation",
                "sha256": "a" * 64,
                "effective_at": "2026-08-03",
            }],
            "dynamic_oracle": None,
        }
    }


def authority_snapshot():
    return {
        "政策法规_测试规则.txt": {
            "sha256": "a" * 64,
            "effective_at": "2026-08-03",
        }
    }


class CloudSubsetEvaluatorTests(unittest.TestCase):
    def test_ask_url_rejects_embedded_credentials_and_wrong_paths(self):
        self.assertEqual(
            "http://127.0.0.1:5001/api/ask",
            validate_ask_url("http://127.0.0.1:5001/api/ask"),
        )
        for invalid in (
            "https://user:password@example.test/api/ask",
            "https://example.test/api/health",
            "file:///tmp/api/ask",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_ask_url(invalid)

    def test_cross_document_representative_requires_every_expected_document(self):
        case = {
            "id": "sys_04",
            "category": "system",
            "expected_docs": [
                "理论题库_系统组成及介绍.txt",
                "无人机理论书籍_2023_无人机系统结构与设计_机械工业出版社_李宏达.txt",
            ],
        }

        result = evaluate_case(
            case,
            200,
            response(["理论题库_系统组成及介绍"]),
            elapsed_s=1.2,
        )

        self.assertFalse(result["passed"])
        self.assertIn("expected_documents_not_fully_covered", result["reasons"])

    def test_summary_enforces_finalizer_and_latency_gates(self):
        results = [
            {
                "id": "reg_01",
                "category": "regulation",
                "passed": True,
                "reasons": [],
                "elapsed_s": 7.5,
                "degraded": False,
                "finalizer_invoked": False,
                "unsupported_high_risk_claims": 0,
            }
        ]

        summary = build_summary(results, {"regulation": 1})

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["gates"]["finalizer_coverage_100"])
        self.assertFalse(summary["gates"]["p95_latency_lte_7s"])

    def test_wrong_answer_and_improper_refusal_cannot_pass_on_sources(self):
        case = {
            "id": "reg_01",
            "category": "regulation",
            "expected_docs": ["政策法规_测试规则.txt"],
        }
        wrong = evaluate_case(
            case,
            200,
            response(["政策法规_测试规则.txt"], answer="已找到相关文档。"),
            elapsed_s=1.0,
            gold_case_context=gold_case_context(),
            gold_activated=True,
            authority_snapshot=authority_snapshot(),
        )
        self.assertTrue(wrong["retrieval_backed"])
        self.assertTrue(wrong["claim_supported"])
        self.assertFalse(wrong["gold_correct"])
        self.assertFalse(wrong["passed"])
        self.assertIn("required_claim_missing:visibility", wrong["reasons"])

        refused = evaluate_case(
            case,
            200,
            response(
                ["政策法规_测试规则.txt"],
                answer="当前证据不足，无法确认。",
            ),
            elapsed_s=1.0,
            gold_case_context=gold_case_context(),
            gold_activated=True,
            authority_snapshot=authority_snapshot(),
        )
        self.assertTrue(refused["safe_refusal"])
        self.assertFalse(refused["passed"])
        self.assertIn("unexpected_safe_refusal", refused["reasons"])

    def test_malformed_response_types_fail_closed_without_crashing(self):
        case = {
            "id": "reg_01",
            "category": "regulation",
            "expected_docs": ["政策法规_测试规则.txt"],
        }
        payload = response(
            ["政策法规_测试规则.txt"],
            answer={"text": "运行时必须保持视距内"},
        )
        payload["claim_evidence"]["unsupported_high_risk_claims"] = "0"
        result = evaluate_case(
            case,
            200,
            payload,
            elapsed_s=1.0,
            gold_case_context=gold_case_context(),
            gold_activated=True,
            authority_snapshot=authority_snapshot(),
        )
        self.assertFalse(result["passed"])
        self.assertIn("answer_invalid_type", result["reasons"])
        self.assertIn(
            "unsupported_high_risk_claims_invalid_type",
            result["reasons"],
        )

    def test_pipeline_error_cannot_claim_zero_unrecovered_failures(self):
        case = {
            "id": "reg_01",
            "category": "regulation",
            "expected_docs": ["政策法规_测试规则.txt"],
        }
        payload = response(["政策法规_测试规则.txt"])
        payload["stats"]["answer_model"].update({
            "recovery_status": "pipeline_error",
            "unrecovered_model_failure": False,
        })

        result = evaluate_case(case, 200, payload, elapsed_s=1.0)

        self.assertFalse(result["passed"])
        self.assertIn("unrecovered_model_failure_inconsistent", result["reasons"])

    def test_http_parser_rejects_duplicate_keys_and_bounds_raw_bytes(self):
        duplicate = b'{"answer":"first","answer":"second"}'
        reply = mock.MagicMock()
        reply.status = 200
        reply.read.return_value = duplicate
        reply.__enter__.return_value = reply
        with mock.patch.object(EVAL.urllib.request, "urlopen", return_value=reply):
            status, payload, _elapsed, raw = EVAL._post_question(
                "http://127.0.0.1:5001/api/ask", "question", 1.0
            )
        self.assertEqual(200, status)
        self.assertEqual(duplicate, raw)
        self.assertIn("_invalid_json", payload)

        oversized = b"{" + b" " * EVAL.MAX_RESPONSE_BYTES
        reply = mock.MagicMock()
        reply.status = 200
        reply.read.return_value = oversized
        reply.__enter__.return_value = reply
        with mock.patch.object(EVAL.urllib.request, "urlopen", return_value=reply):
            _status, payload, _elapsed, raw = EVAL._post_question(
                "http://127.0.0.1:5001/api/ask", "question", 1.0
            )
        self.assertEqual(EVAL.MAX_RESPONSE_BYTES, len(raw))
        self.assertEqual("response_too_large", payload["error"])

    def test_formal_summary_requires_gold_and_trace_binding(self):
        result = {
            "id": "reg_01",
            "category": "regulation",
            "passed": True,
            "reasons": [],
            "elapsed_s": 1.0,
            "degraded": False,
            "finalizer_invoked": True,
            "unsupported_high_risk_claims": 0,
            "answer_model_present": True,
            "unrecovered_model_failure": False,
            "gold_correctness_evaluated": True,
            "gold_correct": True,
            "gold_reason_codes": [],
        }
        missing_trace = build_summary(
            [result],
            {"regulation": 1},
            gold_activated=True,
        )
        self.assertFalse(missing_trace["quality_gate_passed"])
        self.assertFalse(missing_trace["gates"]["trace_binding_verified"])

        passed = build_summary(
            [result],
            {"regulation": 1},
            gold_activated=True,
            trace_binding={"verified": True},
        )
        self.assertTrue(passed["quality_gate_passed"])
        self.assertTrue(passed["passed"])

        unrecovered = dict(result)
        unrecovered["unrecovered_model_failure"] = True
        failed = build_summary(
            [unrecovered],
            {"regulation": 1},
            gold_activated=True,
            trace_binding={"verified": True},
        )
        self.assertFalse(failed["quality_gate_passed"])
        self.assertFalse(failed["gates"]["unrecovered_model_failure_zero"])

    def test_report_only_never_reuses_passed_or_activated_labels(self):
        case = {
            "id": "reg_01",
            "category": "regulation",
            "expected_docs": ["政策法规_测试规则.txt"],
        }
        result = evaluate_case(
            case,
            200,
            response(["政策法规_测试规则.txt"]),
            elapsed_s=1.0,
            report_only=True,
        )
        self.assertNotIn("passed", result)
        self.assertFalse(result["quality_gate_evaluated"])
        self.assertIsNone(result["quality_gate_passed"])
        self.assertIsNone(result["gold_correct"])

        summary = build_summary(
            [result],
            {"regulation": 1},
            report_only=True,
        )
        self.assertNotIn("passed", summary)
        self.assertNotIn("gates", summary)
        self.assertFalse(summary["quality_gate_evaluated"])
        self.assertIsNone(summary["quality_gate_passed"])

    def test_live_formal_mode_is_forbidden_before_http(self):
        with TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "formal"
            with (
                mock.patch.object(EVAL, "_post_question") as post,
            ):
                with self.assertRaisesRegex(SystemExit, "live HTTP formal evaluation is forbidden"):
                    EVAL.main([
                        "--formal-offline",
                        "--url", "http://127.0.0.1:5001/api/ask",
                        "--output-dir", str(output),
                        "--gold-approval-decision", "decision.json",
                        "--gold-approval-signature", "decision.sig",
                        "--gold-approval-public-key", "approval.pub",
                        "--gold-expected-fingerprint", "SHA256:test",
                        "--authority-snapshot", "authority.json",
                        "--trace-log", "trace.jsonl",
                    ])
            post.assert_not_called()
            self.assertFalse(output.exists())

    def test_report_only_writes_observations_and_returns_distinct_exit(self):
        with TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "report"
            fixture = json.loads(
                (REPO_ROOT / "eval" / "online_subset_20260803.json").read_text(
                    encoding="utf-8"
                )
            )
            case = next(item for item in fixture["questions"] if item["id"] == "reg_01")
            with mock.patch.object(
                EVAL,
                "_post_question",
                return_value=(
                    200,
                    response([case["expected_docs"][0]], answer="report observation"),
                    1.0,
                    json.dumps(
                        response(
                            [case["expected_docs"][0]],
                            answer="report observation",
                        ),
                        ensure_ascii=False,
                    ).encode("utf-8"),
                ),
            ):
                exit_code = EVAL.main([
                    "--url", "http://127.0.0.1:5001/api/ask",
                    "--output-dir", str(output),
                    "--report-only",
                    "--ids", "reg_01",
                ])
            self.assertEqual(EVAL.REPORT_ONLY_EXIT_CODE, exit_code)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            results = json.loads((output / "results.json").read_text(encoding="utf-8"))
            self.assertEqual("report_only", summary["mode"])
            self.assertFalse(summary["quality_gate_evaluated"])
            self.assertIsNone(summary["quality_gate_passed"])
            self.assertNotIn("passed", summary)
            self.assertNotIn("gates", summary)
            self.assertFalse(summary["gold_contract"]["activation_evaluated"])
            self.assertNotIn("activated", summary["gold_contract"])
            self.assertNotIn("passed", results[0])

    def test_signed_attestation_full_80_offline_gate_and_raw_tamper(self):
        ssh_keygen = shutil.which("ssh-keygen")
        if not ssh_keygen:
            self.skipTest("ssh-keygen unavailable")
        with TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            fixture = json.loads(
                (REPO_ROOT / "eval" / "online_subset_20260803.json").read_text(
                    encoding="utf-8"
                )
            )
            questions = fixture["questions"]
            by_question = {item["question"]: item for item in questions}
            reviewed = reviewed_gold()
            gold_path = root / "reviewed-gold.json"
            gold_path.write_text(
                json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            gold_context = GOLD.load_gold_standard(
                gold_path,
                REPO_ROOT / "eval" / "cloud80_gold_standard_v1.schema.json",
                REPO_ROOT / "eval" / "online_subset_20260803.json",
            )
            gold_key = root / "gold-signing-key"
            subprocess.run(
                [
                    ssh_keygen,
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(gold_key),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            gold_public_key = Path(f"{gold_key}.pub")
            _public, gold_fingerprint = GOLD.public_key_identity(
                gold_public_key.read_bytes()
            )
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            gold_decision = {
                **gold_context["activation_basis"],
                "approved_by": "approver@example.test",
                "reviewer_type": "human",
                "approved_at": now,
                "public_key_fingerprint": gold_fingerprint,
            }
            gold_decision_path = root / "gold-decision.json"
            gold_decision_path.write_bytes(GOLD.canonical_json_bytes(gold_decision))
            subprocess.run(
                [
                    ssh_keygen, "-Y", "sign", "-f", str(gold_key), "-n",
                    GOLD.SIGNATURE_NAMESPACE, str(gold_decision_path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            gold_signature = Path(f"{gold_decision_path}.sig")
            attestation_key = root / "attestation-signing-key"
            subprocess.run(
                [
                    ssh_keygen,
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(attestation_key),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            attestation_public_key = Path(f"{attestation_key}.pub")
            _public, attestation_fingerprint = GOLD.public_key_identity(
                attestation_public_key.read_bytes()
            )
            self.assertNotEqual(gold_fingerprint, attestation_fingerprint)

            authorities: dict[str, dict[str, str]] = {}
            for case in reviewed["cases"]:
                for source in case["answer_contract"]["authority_sources"]:
                    authorities[source["source_name"]] = {
                        "source_name": source["source_name"],
                        "sha256": source["sha256"],
                        "effective_at": source["effective_at"],
                    }
            authority_path = root / "authority.json"
            authority_path.write_text(
                json.dumps({
                    "schema_version": GOLD.AUTHORITY_SNAPSHOT_SCHEMA_VERSION,
                    "sources": list(authorities.values()),
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            trace_records = []

            def fake_post(_url, question, _timeout):
                case = by_question[question]
                docs = (
                    case["expected_docs"]
                    if case["id"] in EVAL.FULL_COVERAGE_IDS
                    else [case["expected_docs"][0]]
                )
                trace_id = f"trace-{len(trace_records):03d}"
                payload = response(docs, answer=f"gold fact {case['id']}")
                payload["stats"].update({
                    "trace_id": trace_id,
                    "model": "deepseek-chat",
                    "answer_model": {
                        "selected": "deepseek-chat",
                        "attempts": 1,
                        "recovery_status": "not_required",
                        "unrecovered_model_failure": False,
                    },
                })
                trace_records.append({
                    "trace_id": trace_id,
                    "route": "rag",
                    "query": question,
                    "source_count": len(docs),
                    "top_sources": docs,
                    "claim_evidence": payload["claim_evidence"],
                    "model": "deepseek-chat",
                    "answer_model": payload["stats"]["answer_model"],
                })
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                return 200, payload, 1.0, raw

            collection_dir = root / "collection"
            with (
                mock.patch.object(EVAL, "_post_question", side_effect=fake_post),
                mock.patch("builtins.print"),
            ):
                collect_exit = EVAL.main([
                    "--report-only",
                    "--url", "http://127.0.0.1:5001/api/ask",
                    "--output-dir", str(collection_dir),
                ])
            self.assertEqual(EVAL.REPORT_ONLY_EXIT_CODE, collect_exit)
            self.assertEqual(GOLD.QUESTION_COUNT, len(trace_records))

            original_manifest = GOLD.strict_json_object(
                (collection_dir / "collection.json").read_bytes(),
                "test collection manifest",
            )
            collection_variants = {
                "79": original_manifest["cases"][:-1],
                "81": [*original_manifest["cases"], original_manifest["cases"][-1]],
                "order": [
                    original_manifest["cases"][1],
                    original_manifest["cases"][0],
                    *original_manifest["cases"][2:],
                ],
            }
            for label, cases in collection_variants.items():
                with self.subTest(collection_variant=label):
                    variant_dir = root / f"collection-{label}"
                    shutil.copytree(collection_dir, variant_dir)
                    variant_manifest = {**original_manifest, "cases": cases}
                    manifest_path = variant_dir / "collection.json"
                    manifest_path.write_bytes(GOLD.canonical_json_bytes(variant_manifest))
                    manifest_path.chmod(0o600)
                    expected_error = (
                        "exactly 80 cases" if label in {"79", "81"}
                        else "collection case"
                    )
                    with self.assertRaisesRegex(
                        GOLD.GoldContractError,
                        expected_error,
                    ):
                        EVAL._load_full_collection(variant_dir, fixture)

            attested_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            trace_path = root / "trace.jsonl"
            trace_path.write_bytes(encode_trace_chain(trace_records))
            trace_path.chmod(0o600)

            common = [
                "--gold", str(gold_path),
                "--gold-schema", str(REPO_ROOT / "eval" / "cloud80_gold_standard_v1.schema.json"),
                "--gold-approval-decision", str(gold_decision_path),
                "--gold-approval-signature", str(gold_signature),
                "--gold-approval-public-key", str(gold_public_key),
                "--gold-expected-fingerprint", gold_fingerprint,
                "--authority-snapshot", str(authority_path),
                "--trace-log", str(trace_path),
                "--collection-dir", str(collection_dir),
            ]
            model_bad_records = [dict(item) for item in trace_records]
            model_bad_records[0]["model"] = "unexpected-model"
            model_bad_trace = root / "model-bad-trace.jsonl"
            model_bad_trace.write_bytes(encode_trace_chain(model_bad_records))
            model_bad_trace.chmod(0o600)
            model_bad_common = list(common)
            model_bad_common[model_bad_common.index("--trace-log") + 1] = str(
                model_bad_trace
            )
            with self.assertRaisesRegex(SystemExit, "trace model telemetry mismatch"):
                EVAL.main([
                    "--prepare-attestation",
                    "--output-dir", str(root / "model-bad-prepare"),
                    "--attested-by", "attester@example.test",
                    "--attested-at", attested_at,
                    "--attestation-public-key", str(attestation_public_key),
                    "--attestation-expected-fingerprint", attestation_fingerprint,
                    *model_bad_common,
                ])

            interleaved_records = list(trace_records)
            interleaved_records.insert(1, {
                **trace_records[0],
                "trace_id": "unrelated-trace",
                "query": "unrelated query",
            })
            interleaved_trace = root / "interleaved-trace.jsonl"
            interleaved_trace.write_bytes(encode_trace_chain(interleaved_records))
            interleaved_trace.chmod(0o600)
            interleaved_common = list(common)
            interleaved_common[interleaved_common.index("--trace-log") + 1] = str(
                interleaved_trace
            )
            with self.assertRaisesRegex(SystemExit, "must be contiguous"):
                EVAL.main([
                    "--prepare-attestation",
                    "--output-dir", str(root / "interleaved-prepare"),
                    "--attested-by", "attester@example.test",
                    "--attested-at", attested_at,
                    "--attestation-public-key", str(attestation_public_key),
                    "--attestation-expected-fingerprint", attestation_fingerprint,
                    *interleaved_common,
                ])

            with self.assertRaisesRegex(SystemExit, "differ from the Gold approver"):
                EVAL.main([
                    "--prepare-attestation",
                    "--output-dir", str(root / "same-human-prepare"),
                    "--attested-by", "APPROVER@example.test",
                    "--attested-at", attested_at,
                    "--attestation-public-key", str(attestation_public_key),
                    "--attestation-expected-fingerprint", attestation_fingerprint,
                    *common,
                ])
            with self.assertRaisesRegex(
                SystemExit,
                "differ from the Gold approval public key",
            ):
                EVAL.main([
                    "--prepare-attestation",
                    "--output-dir", str(root / "same-key-prepare"),
                    "--attested-by", "attester@example.test",
                    "--attested-at", attested_at,
                    "--attestation-public-key", str(gold_public_key),
                    "--attestation-expected-fingerprint", gold_fingerprint,
                    *common,
                ])

            prepare_dir = root / "prepare"
            with mock.patch("builtins.print"):
                prepare_exit = EVAL.main([
                    "--prepare-attestation",
                    "--output-dir", str(prepare_dir),
                    "--attested-by", "attester@example.test",
                    "--attested-at", attested_at,
                    "--attestation-public-key", str(attestation_public_key),
                    "--attestation-expected-fingerprint", attestation_fingerprint,
                    *common,
                ])
            self.assertEqual(EVAL.PREPARE_ATTESTATION_EXIT_CODE, prepare_exit)
            preparation = json.loads(
                (prepare_dir / "preparation.json").read_text(encoding="utf-8")
            )
            self.assertFalse(preparation["quality_gate_evaluated"])
            self.assertIsNone(preparation["quality_gate_passed"])
            attestation_decision = prepare_dir / "attestation-decision.json"
            attestation_payload = GOLD.strict_json_object(
                attestation_decision.read_bytes(),
                "prepared attestation decision",
            )
            self.assertEqual(
                GOLD.sha256_bytes(gold_decision_path.read_bytes()),
                attestation_payload["gold_approval_decision_sha256"],
            )
            self.assertEqual(
                GOLD.sha256_bytes(gold_signature.read_bytes()),
                attestation_payload["gold_approval_signature_sha256"],
            )
            self.assertEqual(
                GOLD.sha256_bytes(gold_public_key.read_bytes()),
                attestation_payload["gold_approval_public_key_sha256"],
            )
            self.assertEqual(
                gold_fingerprint,
                attestation_payload["gold_approval_public_key_fingerprint"],
            )
            self.assertEqual(
                "approver@example.test",
                attestation_payload["gold_approval_approved_by"],
            )
            self.assertEqual(now, attestation_payload["gold_approval_approved_at"])
            subprocess.run(
                [
                    ssh_keygen, "-Y", "sign", "-f", str(attestation_key), "-n",
                    GOLD.ATTESTATION_SIGNATURE_NAMESPACE,
                    str(attestation_decision),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            attestation_signature = Path(f"{attestation_decision}.sig")
            formal_dir = root / "formal"
            with (
                mock.patch.object(EVAL, "_post_question") as post,
                mock.patch("builtins.print"),
            ):
                formal_exit = EVAL.main([
                    "--formal-offline",
                    "--output-dir", str(formal_dir),
                    "--attestation-decision", str(attestation_decision),
                    "--attestation-signature", str(attestation_signature),
                    "--attestation-public-key", str(attestation_public_key),
                    "--attestation-expected-fingerprint", attestation_fingerprint,
                    *common,
                ])
            post.assert_not_called()
            self.assertEqual(0, formal_exit)
            formal_summary = json.loads(
                (formal_dir / "summary.json").read_text(encoding="utf-8")
            )
            self.assertTrue(formal_summary["quality_gate_passed"])
            self.assertTrue(formal_summary["attestation_validation"]["verified"])

            first_raw = collection_dir / "raw" / f"{questions[0]['id']}.json"
            first_raw.write_bytes(first_raw.read_bytes() + b" ")
            tampered_output = root / "tampered-formal"
            with (
                mock.patch.object(EVAL, "_post_question") as tampered_post,
                self.assertRaisesRegex(SystemExit, "raw response hash mismatch"),
            ):
                EVAL.main([
                    "--formal-offline",
                    "--output-dir", str(tampered_output),
                    "--attestation-decision", str(attestation_decision),
                    "--attestation-signature", str(attestation_signature),
                    "--attestation-public-key", str(attestation_public_key),
                    "--attestation-expected-fingerprint", attestation_fingerprint,
                    *common,
                ])
            tampered_post.assert_not_called()
            self.assertFalse(tampered_output.exists())


if __name__ == "__main__":
    unittest.main()
