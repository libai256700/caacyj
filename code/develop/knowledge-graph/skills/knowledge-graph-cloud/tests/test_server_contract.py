#!/usr/bin/env python3

from __future__ import annotations

import ast
import io
import json
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from deploy.cloud_v2.identity_policy import (
    VERIFIED_IDENTITY_ENVIRON_KEY,
    VerifiedIdentity,
)
from deploy.pipeline import server
from pipeline.cloud_runtime import CloudRuntimeDependencyError
from rag_store.runtime_query_embedding import QueryEmbeddingError


REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_PATH = REPO_ROOT / "deploy" / "pipeline" / "server.py"
RUNTIME_ALLOWLIST_PATH = REPO_ROOT / "deploy" / "cloud_v2" / "runtime-file-allowlist.json"
BUILDER_ALLOWLIST_PATH = REPO_ROOT / "deploy" / "cloud_v2" / "builder-file-allowlist.json"


class FakeAuthority:
    def __init__(self, rows):
        self.rows = {str(row["chunk_id"]): dict(row) for row in rows}

    def search_chunks(self, _terms, limit=20):
        return [dict(row) for row in list(self.rows.values())[:limit]]

    def require_chunks(self, chunk_ids):
        return [dict(self.rows[str(chunk_id)]) for chunk_id in chunk_ids]


class EmptyBm25:
    def search(self, _query, limit=20):
        del limit
        return []


class FakeRuntime:
    def __init__(self, rows, *, regulation_timeline=None, superseded_passages=()):
        self.authority_store = FakeAuthority(rows)
        self.bm25_index = EmptyBm25()
        self.regulation_timeline = regulation_timeline or {}
        self.superseded_passages = tuple(superseded_passages)
        self.coordinate_calls = 0
        self.close_calls = 0

    def embed_query(self, _text):
        raise CloudRuntimeDependencyError("fake embedding is intentionally unbound")

    def recall_scoped_graph(self, **_kwargs):
        return {
            "chunk_ids": [],
            "paths": [],
            "matched_entities": [],
            "evidence_bindings": [],
            "total": 0,
        }

    def augment_scoped_graph_from_chunks(self, graph, _chunk_ids):
        return dict(graph)

    def coordinate_answer(self, **_kwargs):
        self.coordinate_calls += 1
        raise AssertionError("deterministic authority paths must not call a model")

    def close(self):
        self.close_calls += 1


class FailedEmbeddingRuntime(FakeRuntime):
    def embed_query(self, _text):
        raise QueryEmbeddingError("transport_failed")


def post(client, question, *, headers=None, json_body=None):
    request_headers = {server.ANSWER_CONTRACT_HEADER: server.ANSWER_CONTRACT_VERSION}
    request_headers.update(headers or {})
    return client.post(
        server.PUBLIC_API_PATH,
        json=json_body if json_body is not None else {"user_query": question},
        headers=request_headers,
    )


def public_identity():
    return VerifiedIdentity(
        subject="synthetic-user",
        audience="public-app-agent",
        service_account="public-app-agent",
        token_kind="public-app-access",
        network_zone="public-app",
        authn_methods=("oidc",),
        roles=("app-user",),
    )


def create_test_app(runtime_loader):
    return server.create_app(
        runtime_loader,
        verified_identity_loader=lambda _environ: public_identity(),
    )


class ServerContractTests(unittest.TestCase):
    def test_production_factory_preflights_runtime_before_returning_app(self):
        runtime = FakeRuntime([])
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            return runtime

        app = server.create_production_app(loader)
        self.assertEqual(1, calls)
        self.assertIsNotNone(app)
        app.extensions["cloud_runtime_close"]()
        self.assertEqual(1, runtime.close_calls)

    def test_cli_provider_preflight_failure_is_sanitized_exit_78(self):
        stderr = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "KG_PUBLIC_BIND_HOST": "127.0.0.1",
                    "KG_PUBLIC_BIND_PORT": "5001",
                },
                clear=False,
            ),
            mock.patch.object(
                server,
                "create_production_app",
                side_effect=server.ProviderBootstrapError(
                    "provider_approval_missing"
                ),
            ),
            redirect_stderr(stderr),
        ):
            exit_code = server.main()

        self.assertEqual(server.EX_CONFIG, exit_code)
        payload = json.loads(stderr.getvalue())
        self.assertEqual("provider_approval_missing", payload["error"])
        self.assertFalse(payload["provider_runtime_ready"])

    def test_wsgi_unknown_preflight_failure_exits_without_error_detail(self):
        stderr = io.StringIO()
        with (
            mock.patch.object(
                server,
                "create_production_app",
                side_effect=OSError("private path and secret detail"),
            ),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as caught,
        ):
            server.create_wsgi_app()

        self.assertEqual(server.EX_CONFIG, caught.exception.code)
        payload = json.loads(stderr.getvalue())
        self.assertEqual("runtime_preflight_failed", payload["error"])
        self.assertNotIn("private path", stderr.getvalue())

    def test_configured_regulation_order_precedes_retrieval_score(self):
        timeline = {
            "政策法规/高位法.docx": {
                "authority_rank": 700,
                "effective_date": "2024-01-01",
                "status": "current",
            },
            "政策法规/低位新规.docx": {
                "authority_rank": 400,
                "effective_date": "2026-01-01",
                "status": "current",
            },
        }
        ranked = server._merge_sources(
            [
                {
                    "chunk_id": "chunk:textbook",
                    "doc_name": "无人机理论书籍/高分教材.pdf",
                    "text": "textbook",
                    "score": 999.0,
                },
                {
                    "chunk_id": "chunk:lower-regulation",
                    "doc_name": "政策法规/低位新规.docx",
                    "text": "lower regulation",
                    "score": 100.0,
                },
                {
                    "chunk_id": "chunk:higher-regulation",
                    "doc_name": "政策法规/高位法.docx",
                    "text": "higher regulation",
                    "score": 0.01,
                },
            ],
            regulation_timeline=timeline,
        )

        self.assertEqual(
            [
                "chunk:higher-regulation",
                "chunk:lower-regulation",
                "chunk:textbook",
            ],
            [item["chunk_id"] for item in ranked],
        )

    def test_answer_path_uses_configured_supersession_registry(self):
        legacy = {
            "chunk_id": "chunk:configured-legacy",
            "doc_name": "无人机理论书籍/旧版教材.pdf",
            "text": "旧版驾驶员等级说明。",
        }
        runtime = FakeRuntime(
            [legacy],
            superseded_passages=(
                {
                    "id": "configured-supersession",
                    "doc_name": legacy["doc_name"],
                    "chunk_ids": [legacy["chunk_id"]],
                    "topic": "legacy pilot grades",
                    "topic_markers": ["驾驶员", "等级"],
                    "keep_when_exact_question_match": False,
                    "superseded_by": ["政策法规/CCAR-92部.docx"],
                    "reason": "later rule",
                },
            ),
        )

        response = post(
            create_test_app(lambda: runtime).test_client(),
            "驾驶员等级现在如何规定？",
        )
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("degraded", payload["route"])
        self.assertIn("superseded_evidence_excluded", payload["degraded_reasons"])
        self.assertEqual(0, runtime.coordinate_calls)

    def test_public_route_requires_trusted_identity_and_ignores_identity_headers(self):
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            return FakeRuntime([])

        app = server.create_app(loader)
        client = app.test_client()
        missing = post(client, "无身份请求")
        spoofed = post(
            client,
            "header 冒充请求",
            headers={
                "X-KG-Verified-Audience": "public-app-agent",
                "X-KG-Verified-Role": "app-user",
            },
        )
        trusted = client.post(
            server.PUBLIC_API_PATH,
            json={"user_query": "可信身份请求"},
            headers={
                server.ANSWER_CONTRACT_HEADER: server.ANSWER_CONTRACT_VERSION
            },
            environ_overrides={VERIFIED_IDENTITY_ENVIRON_KEY: public_identity()},
        )

        self.assertEqual(403, missing.status_code)
        self.assertEqual(403, spoofed.status_code)
        self.assertEqual("access_denied", spoofed.get_json()["error"])
        self.assertEqual(200, trusted.status_code)
        self.assertEqual(1, calls)

    def test_runtime_allowlist_closes_server_and_builder_without_fake_provider(self):
        allowlist = json.loads(RUNTIME_ALLOWLIST_PATH.read_text(encoding="utf-8"))
        files = allowlist["files"]
        builder = json.loads(BUILDER_ALLOWLIST_PATH.read_text(encoding="utf-8"))["files"]
        self.assertIn("deploy/cloud_v2/identity_policy.py", files)
        self.assertIn("deploy/rag_store/runtime_query_embedding.py", files)
        self.assertIn("deploy/rag_store/runtime_sqlite_reader.py", files)
        self.assertIn("deploy/rag_store/runtime_vector_reader.py", files)
        self.assertIn("deploy/pipeline/public_identity_middleware.py", files)
        self.assertIn("deploy/pipeline/public_identity_config.schema.json", files)
        self.assertIn("deploy/pipeline/production_embedding_candidate.py", builder)
        self.assertIn("deploy/pipeline/production_embedding_config.schema.json", builder)
        self.assertIn("deploy/rag_store/embedding_adapter.py", builder)
        self.assertIn("deploy/rag_store/local_vector_store.py", builder)
        self.assertTrue(set(builder).issubset(files))
        self.assertNotIn("deploy/rag_store/knowledge_governance.py", files)
        self.assertNotIn("deploy/rag_store/sqlite_store.py", files)
        self.assertNotIn("deploy/cloud_v2/fake_providers.py", files)

    def test_runtime_reader_closure_has_no_builder_or_mutation_entrypoint(self):
        module_paths = (
            REPO_ROOT / "deploy/rag_store/runtime_query_embedding.py",
            REPO_ROOT / "deploy/rag_store/runtime_sqlite_reader.py",
            REPO_ROOT / "deploy/rag_store/runtime_vector_reader.py",
        )
        forbidden_names = {
            "build",
            "embed",
            "embed_build",
            "embed_entity",
            "execute_sql",
            "rebuild",
            "upsert",
            "delete",
            "write",
        }
        for path in module_paths:
            with self.subTest(path=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                public_functions = {
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not node.name.startswith("_")
                }
                self.assertTrue(public_functions.isdisjoint(forbidden_names))

        query_tree = ast.parse(module_paths[0].read_text(encoding="utf-8"))
        query_operations = {
            node.name
            for node in ast.walk(query_tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("embed")
        }
        self.assertEqual({"embed_query"}, query_operations)

    def test_app_shutdown_hook_closes_cached_runtime_once(self):
        runtime = FakeRuntime([])
        app = create_test_app(lambda: runtime)
        with app.test_client() as client:
            post(client, "无证据问题")

        app.extensions["cloud_runtime_close"]()
        app.extensions["cloud_runtime_close"]()

        self.assertEqual(1, runtime.close_calls)

    def test_runtime_source_has_one_public_route_and_no_legacy_runtime_surface(self):
        source = SERVER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        routes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"route", "get", "post", "put", "delete", "patch"}
                for decorator in node.decorator_list
            )
        ]
        coordinator_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "coordinate_answer"
        ]

        self.assertEqual(["ask"], [node.name for node in routes])
        self.assertEqual(1, len(coordinator_calls))
        self.assertIn("use_llm=False", source)
        for forbidden in (
            "QueryTraceLogger",
            "query_trace.record",
            "KGRecall",
            "model_secrets",
            "deepseek",
            "doubao",
            "ollama",
            "serper",
            "baidu",
            "@app.get",
            "@app.delete",
        ):
            self.assertNotIn(forbidden.lower(), source.lower())
        self.assertLess(
            source.index("build_exact_question_answer("),
            source.index("runtime.coordinate_answer("),
        )
        self.assertLess(
            source.index("build_authoritative_extractive_fallback("),
            source.index("runtime.coordinate_answer("),
        )

    def test_import_is_lazy_and_public_surface_requires_post_json_and_contract(self):
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            return FakeRuntime([])

        app = create_test_app(loader)
        client = app.test_client()
        self.assertEqual(0, calls)
        self.assertEqual(404, client.get("/ops/status").status_code)
        self.assertEqual(405, client.get(server.PUBLIC_API_PATH).status_code)
        self.assertEqual(412, client.post(server.PUBLIC_API_PATH, json={"user_query": "x"}).status_code)
        response = client.post(
            server.PUBLIC_API_PATH,
            data="not json",
            headers={server.ANSWER_CONTRACT_HEADER: server.ANSWER_CONTRACT_VERSION},
        )
        self.assertEqual(415, response.status_code)
        self.assertEqual(0, calls)

    def test_request_body_uses_bounded_strict_json(self):
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            return FakeRuntime([])

        app = create_test_app(loader)
        client = app.test_client()
        headers = {
            server.ANSWER_CONTRACT_HEADER: server.ANSWER_CONTRACT_VERSION,
            "Content-Type": "application/json",
        }
        invalid_bodies = (
            b'{"user_query":"first","user_query":"second"}',
            b'{"user_query":"question","risk_level":NaN}',
            b'{"user_query":"\xff"}',
        )

        for body in invalid_bodies:
            with self.subTest(body=body):
                response = client.post(
                    server.PUBLIC_API_PATH,
                    data=body,
                    headers=headers,
                )
                self.assertEqual(400, response.status_code)
                self.assertEqual("invalid_json", response.get_json()["error"])

        oversized = b'{"user_query":"' + (
            b"x" * server.MAX_REQUEST_BODY_BYTES
        ) + b'"}'
        response = client.post(
            server.PUBLIC_API_PATH,
            data=oversized,
            headers=headers,
        )
        self.assertEqual(413, response.status_code)
        self.assertEqual("request_body_too_large", response.get_json()["error"])
        self.assertEqual(0, calls)

    def test_r9_chunk_id_exact_question_bypasses_all_server_models(self):
        runtime = FakeRuntime(
            [
                {
                    "chunk_id": "chunk:exact-r9",
                    "doc_name": "理论题库/旋翼无人机.docx",
                    "chunk_index": 0,
                    "text": (
                        "1.六轴飞行器安装有\n"
                        "A.6个顺时针旋转螺旋桨\n"
                        "B.3个顺时针和3个逆时针旋转螺旋桨\n"
                        "参考答案：B"
                    ),
                }
            ]
        )
        response = post(
            create_test_app(lambda: runtime).test_client(),
            "六轴飞行器安装有",
        )
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("question_bank_exact", payload["route"])
        self.assertIn("正确答案", payload["answer"])
        self.assertFalse(payload["degraded"])
        self.assertTrue(payload["knowledge_available"])
        self.assertEqual(0, payload["stats"]["model_invocation_count"])
        self.assertEqual(0, runtime.coordinate_calls)
        self.assertEqual(["chunk:exact-r9"], [item["chunk_id"] for item in payload["sources"]])

    def test_exact_question_honors_supersession_keep_policy(self):
        question_source = {
            "chunk_id": "chunk:kept-exact-question",
            "doc_name": "理论题库/旋翼无人机.docx",
            "text": (
                "9.民用无人驾驶航空器系统驾驶员合格证由哪个部门颁发\n"
                "A.行业协会\n"
                "B.民航主管部门\n"
                "参考答案：A"
            ),
        }
        runtime = FakeRuntime(
            [question_source],
            superseded_passages=(
                {
                    "id": "legacy-exact-question-policy",
                    "doc_name": question_source["doc_name"],
                    "chunk_ids": [question_source["chunk_id"]],
                    "topic": "legacy pilot certificate issuer",
                    "topic_markers": ["驾驶员", "合格证", "行业协会"],
                    "keep_when_exact_question_match": True,
                    "superseded_by": ["政策法规/CCAR-92部.docx"],
                    "reason": "later rule",
                },
            ),
        )
        response = post(
            create_test_app(lambda: runtime).test_client(),
            "民用无人驾驶航空器系统驾驶员合格证由哪个部门颁发",
        )
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("question_bank_exact", payload["route"])
        self.assertIn("正确答案", payload["answer"])
        self.assertEqual(
            [question_source["chunk_id"]],
            [item["chunk_id"] for item in payload["sources"]],
        )
        self.assertNotIn("superseded_evidence_excluded", payload["degraded_reasons"])
        self.assertEqual(0, runtime.coordinate_calls)

    def test_current_regulation_precedes_frozen_r9_kept_exact_question(self):
        question_source = {
            "chunk_id": "chunk:ec89f9598178036a0d31b43d4db694864fdceafc",
            "doc_name": "理论题库/无人机飞行手册、法律法规及其他.docx",
            "text": (
                "9.民用无人驾驶航空器系统驾驶员合格证由哪个部门颁发\n"
                "A.民航主管部门\n"
                "B.中国航空器拥有者及驾驶员协会\n"
                "C.地区管理局\n"
                "参考答案：B"
            ),
        }
        regulation_source = {
            "chunk_id": "chunk:e3192adcc59104fc878183203fda846f0c698188",
            "doc_name": "政策法规/CCAR-92部.docx",
            "text": (
                "现行规定：民用无人驾驶航空器系统驾驶员合格证由"
                "民航主管部门颁发。"
            ),
        }
        runtime = FakeRuntime(
            [regulation_source, question_source],
            superseded_passages=(
                {
                    "id": "r9-question-bank-ac61-pilot-grades",
                    "doc_name": question_source["doc_name"],
                    "chunk_ids": [question_source["chunk_id"]],
                    "topic": "legacy question-bank pilot certificate issuer",
                    "topic_markers": ["驾驶员", "合格证", "行业协会"],
                    "keep_when_exact_question_match": True,
                    "superseded_by": [regulation_source["doc_name"]],
                    "reason": "legacy_exam_item_not_current_operational_authority",
                },
            ),
        )
        response = post(
            create_test_app(lambda: runtime).test_client(),
            "民用无人驾驶航空器系统驾驶员合格证由哪个部门颁发",
        )
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("authoritative_extractive", payload["route"])
        self.assertIn("民航主管部门颁发", payload["answer"])
        self.assertEqual(
            [regulation_source["chunk_id"]],
            [item["chunk_id"] for item in payload["sources"]],
        )
        self.assertEqual(0, payload["stats"]["model_invocation_count"])
        self.assertEqual(0, runtime.coordinate_calls)

    def test_current_regulation_precedes_conflicting_exact_question_bank(self):
        runtime = FakeRuntime(
            [
                {
                    "chunk_id": "chunk:current-regulation",
                    "doc_name": "政策法规/现行规定.docx",
                    "text": (
                        "现行规定：六轴飞行器安装有三组顺时针旋转螺旋桨和"
                        "三组逆时针旋转螺旋桨。"
                    ),
                },
                {
                    "chunk_id": "chunk:conflicting-question-bank",
                    "doc_name": "理论题库/旋翼无人机.docx",
                    "text": (
                        "1.六轴飞行器安装有\n"
                        "A.6个顺时针旋转螺旋桨\n"
                        "B.3个顺时针和3个逆时针旋转螺旋桨\n"
                        "参考答案：A"
                    ),
                },
            ]
        )
        response = post(
            create_test_app(lambda: runtime).test_client(),
            "六轴飞行器安装有",
        )
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("authoritative_extractive", payload["route"])
        self.assertIn("现行规定", payload["answer"])
        self.assertEqual(
            ["chunk:current-regulation"],
            [item["chunk_id"] for item in payload["sources"]],
        )
        self.assertEqual(0, payload["stats"]["model_invocation_count"])
        self.assertEqual(0, runtime.coordinate_calls)

    def test_non_exact_question_bank_never_reaches_server_model(self):
        runtime = FakeRuntime(
            [
                {
                    "chunk_id": "chunk:distractor-r9",
                    "doc_name": "理论题库/安全.docx",
                    "text": (
                        "A. 飞行前必须关闭设备。\n"
                        "B. 飞行前必须检查设备。\n"
                        "参考答案：B"
                    ),
                }
            ]
        )
        app = create_test_app(lambda: runtime)

        with app.test_client() as client:
            response = post(client, "飞行前需要关闭设备吗？")

        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertEqual("degraded", payload["route"])
        self.assertEqual(0, payload["stats"]["model_invocation_count"])
        self.assertEqual(0, runtime.coordinate_calls)

    def test_authoritative_extractive_answer_bypasses_all_server_models(self):
        runtime = FakeRuntime(
            [
                {
                    "chunk_id": "chunk:textbook-r9",
                    "doc_name": "无人机理论书籍/示例教材.pdf",
                    "chunk_index": 0,
                    "text": "飞控负责姿态与导航控制。",
                }
            ]
        )
        response = post(
            create_test_app(lambda: runtime).test_client(),
            "飞控负责什么？",
        )
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("authoritative_extractive", payload["route"])
        self.assertIn("飞控负责姿态与导航控制", payload["answer"])
        self.assertFalse(payload["degraded"])
        self.assertEqual(0, payload["stats"]["model_invocation_count"])
        self.assertEqual(0, runtime.coordinate_calls)

    def test_embedding_failure_preserves_available_authority_path(self):
        runtime = FailedEmbeddingRuntime(
            [
                {
                    "chunk_id": "chunk:textbook-embedding-failure",
                    "doc_name": "无人机理论书籍/飞控示例.pdf",
                    "text": "飞控负责姿态与导航控制。",
                }
            ]
        )

        response = post(
            create_test_app(lambda: runtime).test_client(),
            "飞控负责什么？",
        )
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("authoritative_extractive", payload["route"])
        self.assertIn("embedding_query_unavailable", payload["degraded_reasons"])
        self.assertEqual(0, payload["stats"]["model_invocation_count"])
        self.assertEqual(0, runtime.coordinate_calls)

    def test_miss_and_runtime_failure_return_nonempty_degraded_contracts(self):
        miss = post(
            create_test_app(lambda: FakeRuntime([])).test_client(),
            "普通库外问题",
        )
        miss_payload = miss.get_json()
        self.assertEqual(200, miss.status_code)
        self.assertEqual("miss", miss_payload["route"])
        self.assertTrue(miss_payload["degraded"])
        self.assertTrue(miss_payload["answer"])
        self.assertFalse(miss_payload["knowledge_available"])

        def failed_loader():
            raise OSError("private runtime path and error detail")

        failed = post(
            create_test_app(failed_loader).test_client(),
            "飞控是什么？",
        )
        failed_payload = failed.get_json()
        self.assertEqual(503, failed.status_code)
        self.assertTrue(failed_payload["answer"])
        self.assertNotIn("private runtime", str(failed_payload))


if __name__ == "__main__":
    unittest.main()
