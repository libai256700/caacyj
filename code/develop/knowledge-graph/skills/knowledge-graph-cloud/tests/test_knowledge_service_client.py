#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import knowledge_service_client as client_module  # noqa: E402
from app_answer import build_app_prompt  # noqa: E402
from knowledge_service_client import (  # noqa: E402
    ANSWER_CONTRACT,
    ANSWER_CONTRACT_HEADER,
    KnowledgeServiceClient,
    TransportRequest,
    TransportResponse,
)


ENDPOINT = "https://knowledge.example.invalid/api/ask"


def response(status: int, payload) -> TransportResponse:
    return TransportResponse(
        status=status,
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )


class RecordingTransport:
    def __init__(self, result: TransportResponse | BaseException):
        self.result = result
        self.requests: list[TransportRequest] = []

    def __call__(self, request: TransportRequest) -> TransportResponse:
        self.requests.append(request)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeHTTPResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body

    def read(self, limit: int) -> bytes:
        return self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeOpener:
    def __init__(self, result: FakeHTTPResponse):
        self.result = result
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        return self.result


class KnowledgeServiceClientTests(unittest.TestCase):
    def test_hit_sends_only_current_query_and_explicit_ordinary_contract(self):
        transport = RecordingTransport(
            response(
                200,
                {
                    "answer": "雷暴会带来强对流和突变风。",
                    "degraded": False,
                    "route": "rag",
                    "sources": [{"doc_name": "must-not-leak"}],
                    "stats": {"trace_id": "must-not-leak"},
                },
            )
        )
        client = KnowledgeServiceClient(
            ENDPOINT,
            timeout_s=2.5,
            headers={"Authorization": "secretref:runtime-auth-reference"},
            transport=transport,
        )

        answer = client.ask("雷暴飞行有什么风险？")

        self.assertEqual("雷暴会带来强对流和突变风。", answer)
        self.assertEqual(1, len(transport.requests))
        request = transport.requests[0]
        self.assertEqual("POST", request.method)
        self.assertEqual(ENDPOINT, request.url)
        self.assertEqual(2.5, request.timeout_s)
        self.assertEqual(
            {"user_query": "雷暴飞行有什么风险？"},
            json.loads(request.body.decode("utf-8")),
        )
        self.assertEqual(ANSWER_CONTRACT, request.headers[ANSWER_CONTRACT_HEADER])
        self.assertEqual("application/json", request.headers["Content-Type"])
        self.assertEqual("application/json", request.headers["Accept"])
        self.assertEqual(
            "secretref:runtime-auth-reference",
            request.headers["Authorization"],
        )

    def test_default_transport_is_mocked_https_post_with_redirects_disabled(self):
        opener = FakeOpener(
            FakeHTTPResponse(
                200,
                json.dumps(
                    {"answer": "飞控负责姿态与导航控制。", "degraded": False},
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
        )
        with mock.patch.object(
            client_module.urllib.request,
            "build_opener",
            return_value=opener,
        ) as build_opener:
            client = KnowledgeServiceClient(ENDPOINT, timeout_s=1.5)
            self.assertEqual("飞控负责姿态与导航控制。", client.ask("什么是飞控？"))

        redirect_handler = build_opener.call_args.args[0]
        self.assertIsInstance(redirect_handler, client_module._NoRedirectHandler)
        self.assertIsNone(
            redirect_handler.redirect_request(
                None,
                None,
                302,
                "redirect",
                {},
                "https://redirect.example.invalid/api/ask",
            )
        )
        self.assertEqual(1, len(opener.calls))
        request, timeout = opener.calls[0]
        self.assertEqual("POST", request.get_method())
        self.assertEqual(1.5, timeout)
        self.assertEqual(
            {"user_query": "什么是飞控？"},
            json.loads(request.data.decode("utf-8")),
        )
        headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(ANSWER_CONTRACT, headers[ANSWER_CONTRACT_HEADER.lower()])

    def test_raw_engineering_fields_cannot_enter_app_prompt(self):
        transport = RecordingTransport(
            response(
                200,
                {
                    "answer": "应与雷暴活动区保持安全距离。",
                    "degraded": False,
                    "route": "server_model",
                    "sources": [{"url": "https://metadata.example.invalid/not-public"}],
                    "trace_id": "trace-not-for-prompt",
                    "claim_evidence": {"private": True},
                    "provider": "provider-not-for-prompt",
                    "evaluation": "evaluation-not-for-prompt",
                },
            )
        )
        client = KnowledgeServiceClient(
            ENDPOINT,
            timeout_s=1,
            transport=transport,
        )

        answer = client.ask("雷暴天气怎么避让？")
        prompt = build_app_prompt(
            "雷暴天气怎么避让？",
            {"answer": answer} if answer is not None else None,
        )

        self.assertIn("应与雷暴活动区保持安全距离", prompt)
        for marker in (
            "metadata.example.invalid",
            "trace-not-for-prompt",
            "claim_evidence",
            "provider-not-for-prompt",
            "evaluation-not-for-prompt",
            '"route"',
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, prompt)

    def test_miss_returns_none_for_empty_or_explicit_non_hit_payloads(self):
        payloads = (
            {"answer": "", "degraded": False},
            {"answer": "unused", "degraded": False, "hit": False},
            {"answer": "unused", "degraded": False, "route": "miss"},
            {"answer": "unused", "degraded": False, "matched": False},
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                client = KnowledgeServiceClient(
                    ENDPOINT,
                    timeout_s=1,
                    transport=RecordingTransport(response(200, payload)),
                )
                self.assertIsNone(client.ask("普通库外问题"))

    def test_degraded_rejected_or_error_payload_returns_none(self):
        payloads = (
            {"answer": "unused", "degraded": True},
            {"answer": "unused", "degraded": False, "request_rejected": True},
            {"answer": "unused", "degraded": False, "error_type": "internal"},
            {"answer": "unused", "degraded": False, "error": 0},
            {"answer": "当前知识库问答服务不可用", "degraded": False},
            {"answer": "unused"},
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                client = KnowledgeServiceClient(
                    ENDPOINT,
                    timeout_s=1,
                    transport=RecordingTransport(response(200, payload)),
                )
                self.assertIsNone(client.ask("如何制定学习计划？"))

    def test_5xx_and_timeout_return_none_without_retry(self):
        cases = (
            RecordingTransport(
                response(
                    503,
                    {
                        "answer": "must-not-be-used",
                        "degraded": False,
                        "trace_id": "must-not-leak",
                    },
                )
            ),
            RecordingTransport(TimeoutError("private timeout detail")),
        )

        for transport in cases:
            with self.subTest(result=transport.result):
                client = KnowledgeServiceClient(
                    ENDPOINT,
                    timeout_s=1,
                    transport=transport,
                )
                self.assertIsNone(client.ask("如何提高学习效率？"))
                self.assertEqual(1, len(transport.requests))

    def test_invalid_or_oversized_response_returns_none(self):
        cases = (
            TransportResponse(status=200, body=b"not-json"),
            TransportResponse(status=200, body=b"[]"),
            TransportResponse(
                status=200,
                body=b'{"answer":"first","answer":"second","degraded":false}',
            ),
            TransportResponse(status=200, body=b"x" * 17),
        )

        for transport_response in cases:
            with self.subTest(body=transport_response.body[:20]):
                client = KnowledgeServiceClient(
                    ENDPOINT,
                    timeout_s=1,
                    max_response_bytes=16,
                    transport=RecordingTransport(transport_response),
                )
                self.assertIsNone(client.ask("什么是飞控？"))

    def test_injected_transport_works_with_process_network_blocked(self):
        transport = RecordingTransport(
            response(200, {"answer": "飞控负责姿态与导航控制。", "degraded": False})
        )
        client = KnowledgeServiceClient(
            ENDPOINT,
            timeout_s=1,
            transport=transport,
        )

        with (
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network forbidden"),
            ),
            mock.patch.object(
                socket,
                "socket",
                side_effect=AssertionError("network forbidden"),
            ),
        ):
            self.assertEqual("飞控负责姿态与导航控制。", client.ask("什么是飞控？"))

    def test_endpoint_and_reserved_headers_fail_closed(self):
        for endpoint in (
            "http://knowledge.example.invalid/api/ask",
            "https://username@knowledge.example.invalid/api/ask",
            "https://knowledge.example.invalid/ops/status",
            "https://knowledge.example.invalid/api/ask/",
            "https://knowledge.example.invalid/api/ask?debug=1",
            "https://knowledge.example.invalid/api/ask?",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    KnowledgeServiceClient(endpoint, timeout_s=1)

        for header in ("content-type", "Accept", ANSWER_CONTRACT_HEADER.lower()):
            with self.subTest(header=header):
                with self.assertRaises(ValueError):
                    KnowledgeServiceClient(
                        ENDPOINT,
                        timeout_s=1,
                        headers={header: "override"},
                    )

    def test_configuration_and_transport_contract_are_strict(self):
        with self.assertRaises(ValueError):
            KnowledgeServiceClient(ENDPOINT, timeout_s=0)
        with self.assertRaises(TypeError):
            KnowledgeServiceClient(ENDPOINT, timeout_s=True)
        with self.assertRaises(ValueError):
            KnowledgeServiceClient(ENDPOINT, timeout_s=math.inf)
        with self.assertRaises(ValueError):
            KnowledgeServiceClient(ENDPOINT, timeout_s=1).ask("  ")
        with self.assertRaises(TypeError):
            KnowledgeServiceClient(
                ENDPOINT,
                timeout_s=1,
                transport=lambda _request: (200, b"{}"),
            ).ask("问题")

    def test_transport_request_repr_hides_credentials_and_query(self):
        transport = RecordingTransport(
            response(200, {"answer": "answer", "degraded": False})
        )
        client = KnowledgeServiceClient(
            ENDPOINT,
            timeout_s=1,
            headers={"Authorization": "secretref:runtime-auth-reference"},
            transport=transport,
        )

        self.assertEqual("answer", client.ask("private user query"))
        rendered = repr(transport.requests[0])
        self.assertNotIn("secretref:runtime-auth-reference", rendered)
        self.assertNotIn("private user query", rendered)
        self.assertNotIn("answer", repr(transport.result))


if __name__ == "__main__":
    unittest.main()
