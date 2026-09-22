#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import pickle
import socket
import ssl
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.embedding_adapter import EmbeddingIdentity
from rag_store.provider_http_transport import (
    ProviderHTTPTransport,
    ProviderTransportError,
)
from rag_store.provider_meters import (
    MAXIMUM_REQUEST_EXPOSURE_V1,
    UNICODE_CODEPOINTS_V1,
    UTF8_BYTES_V1,
    ProviderMeterError,
    meter_ids,
    resolve_meter,
)
from rag_store.provider_wire import (
    ProviderWire,
    ProviderWireError,
    compile_request,
    compile_response,
    resolve_json_pointer,
    validate_json_pointer,
)
from rag_store.server_answer_model import (
    ServerAnswerChannel,
    ServerAnswerModelAdapter,
    ServerAnswerRequest,
)


SECRET = "test-only-secret-72c46823"
ENDPOINT = "https://api.example.invalid:8443/exact/v1/answer"


def answer_identity() -> ServerAnswerChannel:
    return ServerAnswerChannel(
        channel_id="answer-a",
        provider="synthetic-provider",
        base_url=ENDPOINT,
        region="cn-test",
        model="synthetic-model",
        api_version="v1",
        timeout_seconds=1.0,
        max_input_units=100,
        max_output_units=100,
        max_cost_microunits=99,
    )


def answer_payload() -> dict:
    return {
        "schema_version": "kg-server-answer-request-v1",
        "request_id": "request-1",
        "question": "abc",
        "evidence": [{"evidence_id": "e-1", "text": "defg"}],
        "input_units": 7,
        "max_output_units": 100,
    }


def answer_template() -> dict:
    return {
        "model": {"$ref": "identity.model"},
        "messages": [
            {"role": "user", "content": {"$ref": "request.question"}},
        ],
        "evidence": {"$ref": "request.evidence"},
        "stream": False,
    }


def answer_body(answer: str = "result") -> bytes:
    return json.dumps(
        {
            "choices": [{"message": {"content": answer}}],
            "usage": {
                "provider_diagnostic": "ignored",
                "input_units": 999999,
                "output_units": 999999,
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def answer_transport(**overrides) -> ProviderHTTPTransport:
    values = {
        "endpoint": ENDPOINT,
        "request_template": answer_template(),
        "response_kind": "server_answer",
        "response_mapping": {"answer_pointer": "/choices/0/message/content"},
        "input_meter_id": UNICODE_CODEPOINTS_V1,
        "output_meter_id": UNICODE_CODEPOINTS_V1,
        "cost_meter_id": MAXIMUM_REQUEST_EXPOSURE_V1,
        "secret_headers": {"Authorization": f"Bearer {SECRET}"},
        "executor": lambda **_request: (
            200,
            {"Content-Type": "application/json"},
            answer_body(),
        ),
    }
    values.update(overrides)
    return ProviderHTTPTransport(**values)


def embedding_identity() -> EmbeddingIdentity:
    return EmbeddingIdentity(
        provider="synthetic-provider",
        base_url="https://embedding.example.invalid/v1/embed",
        region="cn-test",
        model="synthetic-embedding",
        model_version="2026-01",
        api_version="v1",
        dimension=3,
        normalization="l2",
        input_type="document",
    )


def embedding_payload() -> dict:
    return {
        "schema_version": "kg-embedding-request-v1",
        "embedding_identity_sha256": embedding_identity().sha256,
        "purpose": "build",
        "input_type": "document",
        "items": [
            {"id": "a", "text": "one", "input_units": 3},
            {"id": "b", "text": "four", "input_units": 4},
        ],
    }


class FakeHTTPResponse:
    def __init__(self, status, headers, body):
        self.status = status
        self._headers = list(headers)
        self._body = body
        self._offset = 0
        self.read_sizes = []
        self.closed = False

    def getheaders(self):
        return list(self._headers)

    def read(self, amount):
        self.read_sizes.append(amount)
        chunk = self._body[self._offset : self._offset + amount]
        self._offset += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class FakeHTTPSConnection:
    def __init__(self, response):
        self.response = response
        self.request_call = None
        self.closed = False

    def request(self, method, target, *, body, headers, encode_chunked):
        self.request_call = {
            "method": method,
            "target": target,
            "body": body,
            "headers": headers,
            "encode_chunked": encode_chunked,
        }

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class ProviderWireTests(unittest.TestCase):
    def test_request_template_accepts_only_literals_and_closed_refs(self):
        rendered = compile_request(
            answer_template(),
            answer_identity(),
            answer_payload(),
        )
        self.assertEqual("synthetic-model", rendered["model"])
        self.assertEqual("abc", rendered["messages"][0]["content"])
        self.assertEqual(False, rendered["stream"])

        template = answer_template()
        wire = ProviderWire(template)
        template["model"] = "mutated"
        self.assertEqual(
            "synthetic-model",
            wire.render_request(answer_identity(), answer_payload())["model"],
        )
        self.assertNotIn("synthetic-model", repr(wire))

    def test_unknown_ref_extra_key_and_expression_are_rejected(self):
        bad_templates = (
            {"value": {"$ref": "request.not_allowed"}},
            {"value": {"$ref": "request.question", "fallback": "unsafe"}},
            {"value": "${request.question}"},
            {"value": "{{ request.question }}"},
            {"value": {"$ref": "identity.api_key"}},
        )
        for template in bad_templates:
            with self.subTest(template=template):
                with self.assertRaises(ProviderWireError):
                    ProviderWire(template)

    def test_runtime_ref_value_is_detached_and_must_be_json(self):
        payload = answer_payload()
        wire = ProviderWire({"evidence": {"$ref": "request.evidence"}})
        rendered = wire.render_request(answer_identity(), payload)
        payload["evidence"][0]["text"] = "mutated"
        self.assertEqual("defg", rendered["evidence"][0]["text"])

        payload["evidence"] = [object()]
        with self.assertRaises(ProviderWireError):
            wire.render_request(answer_identity(), payload)

    def test_response_mapping_uses_rfc6901_without_wildcards(self):
        document = {"a/b": {"~key": [10, 20]}}
        self.assertEqual(20, resolve_json_pointer(document, "/a~1b/~0key/1"))
        self.assertEqual(
            {"value": 20},
            compile_response({"value": "/a~1b/~0key/1"}, document),
        )
        for pointer in ("#/a", "/a/*/b", "/bad~2escape"):
            with self.subTest(pointer=pointer):
                with self.assertRaises(ProviderWireError):
                    validate_json_pointer(pointer)

        with self.assertRaises(ProviderWireError):
            resolve_json_pointer({"array": [1]}, "/array/-")

        with self.assertRaises(ProviderWireError):
            compile_response({"value": {"$ref": "request.question"}}, document)


class ProviderMeterTests(unittest.TestCase):
    def test_registry_is_closed_and_local(self):
        self.assertEqual(
            (
                UTF8_BYTES_V1,
                UNICODE_CODEPOINTS_V1,
                MAXIMUM_REQUEST_EXPOSURE_V1,
            ),
            meter_ids(),
        )
        self.assertEqual(7, resolve_meter(UNICODE_CODEPOINTS_V1)(answer_payload()))
        self.assertEqual(7, resolve_meter(UTF8_BYTES_V1)(answer_payload()))
        self.assertEqual(
            99,
            resolve_meter(MAXIMUM_REQUEST_EXPOSURE_V1)(answer_identity(), 1, 1),
        )
        for identifier in ("os.system", "pkg.module:callable", "unknown-v1"):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ProviderMeterError):
                    resolve_meter(identifier)

    def test_utf8_and_codepoint_meters_are_distinct(self):
        value = "\N{LATIN SMALL LETTER E WITH ACUTE}"
        self.assertEqual(2, resolve_meter(UTF8_BYTES_V1)(value))
        self.assertEqual(1, resolve_meter(UNICODE_CODEPOINTS_V1)(value))


class ProviderHTTPTransportTests(unittest.TestCase):
    def test_http_endpoint_credentials_query_and_fragment_are_rejected(self):
        endpoints = (
            "http://api.example.invalid/v1",
            "https://user:pass@api.example.invalid/v1",
            "https://api.example.invalid/v1?q=1",
            "https://api.example.invalid/v1#fragment",
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ProviderTransportError):
                    answer_transport(endpoint=endpoint)

    def test_answer_fake_receives_exact_json_and_secret_header_only(self):
        captured = {}

        def executor(**request):
            captured.update(request)
            return 200, {"Content-Type": "application/json"}, answer_body()

        transport = answer_transport(executor=executor)
        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network forbidden"),
        ):
            result = transport(answer_identity(), answer_payload(), 0.5)

        provider_request = json.loads(captured["body"])
        self.assertEqual("POST", captured["method"])
        self.assertEqual(ENDPOINT, captured["endpoint"])
        self.assertEqual("synthetic-model", provider_request["model"])
        self.assertEqual("abc", provider_request["messages"][0]["content"])
        self.assertNotIn(SECRET.encode("ascii"), captured["body"])
        self.assertEqual(f"Bearer {SECRET}", captured["headers"]["Authorization"])
        self.assertEqual("result", result["answer"])
        self.assertEqual(
            {"input_units": 7, "output_units": 6, "cost_microunits": 99},
            result["usage"],
        )
        self.assertNotIn("provider_diagnostic", repr(result))

    def test_answer_transport_matches_existing_adapter_and_local_meters(self):
        identity = answer_identity()
        transport = answer_transport()
        with mock.patch(
            "rag_store.server_answer_model._is_sealed_offline_fake_transport",
            return_value=True,
        ):
            adapter = ServerAnswerModelAdapter(
                identity,
                transport=transport,
                transport_mode="cooperative",
                input_unit_meter=resolve_meter(UNICODE_CODEPOINTS_V1),
                output_unit_meter=resolve_meter(UNICODE_CODEPOINTS_V1),
                cost_meter=resolve_meter(MAXIMUM_REQUEST_EXPOSURE_V1),
            )
        request = ServerAnswerRequest(
            request_id="request-1",
            question="abc",
            evidence=({"evidence_id": "e-1", "text": "defg"},),
            input_units=7,
        )
        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network forbidden"),
        ):
            result = adapter.invoke(request)
        self.assertEqual("result", result.answer)
        self.assertEqual(7, result.usage.input_units)
        self.assertEqual(6, result.usage.output_units)
        self.assertEqual(99, result.usage.cost_microunits)

    def test_sensitive_header_requires_the_secret_header_channel(self):
        with self.assertRaises(ProviderTransportError) as caught:
            answer_transport(
                secret_headers=None,
                headers={"X-API-Key": SECRET},
            )
        self.assertEqual("sensitive_header_must_be_secret", caught.exception.code)

    def test_secret_is_absent_from_repr_and_sanitized_exception(self):
        body_marker = "private-body-marker"

        def failing_executor(**_request):
            raise RuntimeError(f"{SECRET} {body_marker} provider diagnostic")

        transport = answer_transport(executor=failing_executor)
        self.assertNotIn(SECRET, repr(transport))
        self.assertNotIn(ENDPOINT, repr(transport))
        with self.assertRaises(ProviderTransportError) as caught:
            transport(answer_identity(), answer_payload(), 0.5)
        rendered = f"{caught.exception!s} {caught.exception!r}"
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn(body_marker, rendered)
        self.assertNotIn("provider diagnostic", rendered)

    def test_secret_is_rejected_in_request_body_or_provider_response(self):
        in_body = answer_template()
        in_body["accidental"] = SECRET
        with self.assertRaises(ProviderTransportError) as request_error:
            answer_transport(request_template=in_body)(
                answer_identity(),
                answer_payload(),
                0.5,
            )
        self.assertEqual("secret_in_request_body", request_error.exception.code)

        with self.assertRaises(ProviderTransportError) as response_error:
            answer_transport(
                executor=lambda **_request: (
                    200,
                    {"Content-Type": "application/json"},
                    answer_body(SECRET),
                )
            )(answer_identity(), answer_payload(), 0.5)
        self.assertEqual("secret_in_response", response_error.exception.code)

    def test_redirect_and_non_json_content_are_not_followed(self):
        cases = (
            (
                (
                    302,
                    {
                        "Content-Type": "application/json",
                        "Location": "https://other.invalid",
                    },
                    b"{}",
                ),
                "redirect_rejected",
            ),
            ((200, {"Content-Type": "text/plain"}, b"{}"), "invalid_content_type"),
        )
        for result, code in cases:
            with self.subTest(code=code):
                transport = answer_transport(executor=lambda **_request: result)
                with self.assertRaises(ProviderTransportError) as caught:
                    transport(answer_identity(), answer_payload(), 0.5)
                self.assertEqual(code, caught.exception.code)

    def test_request_and_response_limits_fail_closed(self):
        with self.assertRaises(ProviderTransportError) as request_error:
            answer_transport(max_request_bytes=8)(
                answer_identity(),
                answer_payload(),
                0.5,
            )
        self.assertEqual("request_too_large", request_error.exception.code)

        transport = answer_transport(
            max_response_bytes=8,
            executor=lambda **_request: (
                200,
                {"Content-Type": "application/json"},
                b"123456789",
            ),
        )
        with self.assertRaises(ProviderTransportError) as response_error:
            transport(answer_identity(), answer_payload(), 0.5)
        self.assertEqual("response_too_large", response_error.exception.code)

    def test_default_path_uses_verified_tls_exact_target_and_no_proxy(self):
        response = FakeHTTPResponse(
            200,
            [("Content-Type", "application/json")],
            answer_body(),
        )
        connection = FakeHTTPSConnection(response)
        captured = {}

        def factory(**kwargs):
            captured.update(kwargs)
            return connection

        transport = answer_transport(executor=None)
        with mock.patch.dict(
            os.environ,
            {"HTTPS_PROXY": "http://proxy.invalid:8080"},
        ), mock.patch(
            "rag_store.provider_http_transport.http.client.HTTPSConnection",
            side_effect=factory,
        ):
            result = transport(answer_identity(), answer_payload(), 0.5)

        context = captured["context"]
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertTrue(context.check_hostname)
        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual("api.example.invalid", captured["host"])
        self.assertEqual(8443, captured["port"])
        self.assertEqual("/exact/v1/answer", connection.request_call["target"])
        self.assertEqual("POST", connection.request_call["method"])
        self.assertFalse(connection.request_call["encode_chunked"])
        self.assertTrue(connection.closed)
        self.assertTrue(response.closed)
        self.assertEqual("result", result["answer"])

    def test_response_is_read_in_bounded_chunks(self):
        long_answer = "x" * 66_000
        response = FakeHTTPResponse(
            200,
            [("Content-Type", "application/json")],
            answer_body(long_answer),
        )
        connection = FakeHTTPSConnection(response)
        transport = answer_transport(
            executor=None,
            max_response_bytes=70_000,
            connection_factory=lambda **_kwargs: connection,
        )
        result = transport(answer_identity(), answer_payload(), 0.5)
        self.assertEqual(long_answer, result["answer"])
        self.assertGreaterEqual(len(response.read_sizes), 3)
        self.assertTrue(all(size <= 64 * 1024 for size in response.read_sizes))

    def test_endpoint_must_match_frozen_identity(self):
        wrong = answer_identity()
        object.__setattr__(wrong, "base_url", "https://other.invalid/v1")
        with self.assertRaises(ProviderTransportError) as caught:
            answer_transport()(wrong, answer_payload(), 0.5)
        self.assertEqual("identity_mismatch", caught.exception.code)

    def test_deadline_requires_a_strict_finite_number(self):
        class FloatCoercible:
            def __float__(self):
                return 0.5

        executor_calls = []
        transport = answer_transport(
            executor=lambda **request: executor_calls.append(request)
        )
        for deadline in (True, float("nan"), float("inf"), FloatCoercible()):
            with self.subTest(deadline=repr(deadline)):
                with self.assertRaises(ProviderTransportError) as caught:
                    transport(answer_identity(), answer_payload(), deadline)
                self.assertEqual("invalid_deadline", caught.exception.code)
        self.assertEqual([], executor_calls)

    def test_invalid_pointer_and_duplicate_json_are_sanitized(self):
        with self.assertRaises(ProviderWireError):
            answer_transport(response_mapping={"answer_pointer": "/choices/*"})

        duplicate = b'{"choices":[],"choices":[]}'
        transport = answer_transport(
            executor=lambda **_request: (
                200,
                {"Content-Type": "application/json"},
                duplicate,
            )
        )
        with self.assertRaises(ProviderTransportError) as caught:
            transport(answer_identity(), answer_payload(), 0.5)
        self.assertEqual("invalid_json_response", caught.exception.code)
        self.assertNotIn("choices", repr(caught.exception))

    def test_production_transport_is_pickleable_without_tls_context(self):
        transport = answer_transport(executor=None)
        restored = pickle.loads(pickle.dumps(transport))
        self.assertEqual("server_answer", restored.response_kind)
        self.assertNotIn(SECRET, repr(restored))

    def test_embedding_input_order_mapping_uses_local_usage(self):
        identity = embedding_identity()
        captured = {}

        def executor(**request):
            captured.update(request)
            response = {
                "data": [
                    {"embedding": [1.0, 0.0, 0.0]},
                    {"embedding": [0.0, 1.0, 0.0]},
                ],
                "usage": {"provider_claim": 999999},
            }
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps(response, separators=(",", ":")).encode("utf-8"),
            )

        transport = ProviderHTTPTransport(
            endpoint=identity.base_url,
            request_template={
                "model": {"$ref": "identity.model"},
                "inputs": {"$ref": "request.items"},
            },
            response_kind="embedding",
            response_mapping={
                "vectors_pointer": "/data",
                "values_pointer": "/embedding",
                "match_by": "input_order",
            },
            input_meter_id=UNICODE_CODEPOINTS_V1,
            cost_meter_id=MAXIMUM_REQUEST_EXPOSURE_V1,
            maximum_cost_microunits=17,
            secret_headers={"X-API-Key": SECRET},
            executor=executor,
        )
        result = transport(identity, embedding_payload(), 0.5)
        self.assertEqual(["a", "b"], [item["id"] for item in result["vectors"]])
        self.assertEqual({"input_units": 7, "cost_microunits": 17}, result["usage"])
        self.assertNotIn("provider_claim", repr(result))
        self.assertNotIn(SECRET.encode("ascii"), captured["body"])

    def test_embedding_response_id_mapping_restores_request_order(self):
        identity = embedding_identity()
        response = {
            "data": [
                {"object_id": "b", "vector": [0.0, 1.0, 0.0]},
                {"object_id": "a", "vector": [1.0, 0.0, 0.0]},
            ]
        }
        transport = ProviderHTTPTransport(
            endpoint=identity.base_url,
            request_template={"inputs": {"$ref": "request.items"}},
            response_kind="embedding",
            response_mapping={
                "vectors_pointer": "/data",
                "values_pointer": "/vector",
                "match_by": "response_id",
                "id_pointer": "/object_id",
            },
            input_meter_id=UNICODE_CODEPOINTS_V1,
            maximum_cost_microunits=0,
            executor=lambda **_request: (
                200,
                {"Content-Type": "application/json"},
                json.dumps(response, separators=(",", ":")).encode("utf-8"),
            ),
        )
        result = transport(identity, embedding_payload(), 0.5)
        self.assertEqual(["a", "b"], [item["id"] for item in result["vectors"]])
        self.assertEqual([1.0, 0.0, 0.0], result["vectors"][0]["values"])


if __name__ == "__main__":
    unittest.main()
