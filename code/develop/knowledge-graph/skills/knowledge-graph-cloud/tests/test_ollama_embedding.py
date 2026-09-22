from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.embedding_adapter import EmbeddingAdapter, EmbeddingIdentity, EmbeddingInput, EmbeddingPolicy
from rag_store.ollama_embedding import (
    OllamaEmbeddingError,
    OllamaEmbeddingTransport,
    OllamaModelInfo,
    inspect_ollama_model,
    ollama_embedding_identities,
)
from rag_store.runtime_query_embedding import QueryEmbeddingIdentity


def _identity() -> EmbeddingIdentity:
    return EmbeddingIdentity(
        provider="ollama-local",
        base_url="http://127.0.0.1:11434/api/embed",
        region="local-loopback",
        model="bge-m3:latest",
        model_version="sha256:test",
        api_version="api-embed-v1",
        dimension=3,
        normalization="l2",
        input_type="document-or-query",
    )


class OllamaEmbeddingTests(unittest.TestCase):
    def test_transport_maps_ollama_embeddings_to_repository_contract(self) -> None:
        identity = _identity()
        response = mock.Mock(status=200)
        response.read.return_value = json.dumps({
            "model": identity.model,
            "embeddings": [[1.0, 2.0, 3.0]],
        }).encode()
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch("rag_store.ollama_embedding.http.client.HTTPConnection", return_value=connection):
            payload = OllamaEmbeddingTransport()(identity, {
                "items": [{"id": "q", "text": "查询", "input_units": 2}]
            }, 5.0)
        self.assertEqual(["q"], [item["id"] for item in payload["vectors"]])
        self.assertEqual(3, len(payload["vectors"][0]["values"]))
        self.assertEqual(2, payload["usage"]["input_units"])
        body = json.loads(connection.request.call_args.kwargs["body"])
        self.assertEqual(["查询"], body["input"])
        self.assertEqual(identity.model, body["model"])

    def test_transport_rejects_non_loopback_endpoint(self) -> None:
        for endpoint in (
            "http://example.invalid",
            "http://127.0.0.1.example.invalid/api/embed",
            "http://user@127.0.0.1:11434/api/embed",
            "http://127.0.0.1:11434/api/embed?redirect=1",
            "http://127.0.0.1:11434/not-embed",
            "https://127.0.0.1:11434/api/embed",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                OllamaEmbeddingTransport(endpoint)

    def test_transport_rejects_oversized_raw_response(self) -> None:
        response = mock.Mock(status=200)
        response.read.return_value = b"x" * 65
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch(
            "rag_store.ollama_embedding.http.client.HTTPConnection",
            return_value=connection,
        ), self.assertRaisesRegex(
            OllamaEmbeddingError, "ollama_embedding_response_too_large"
        ):
            OllamaEmbeddingTransport(max_response_bytes=64)(
                _identity(),
                {"items": [{"id": "q", "text": "query", "input_units": 5}]},
                5.0,
            )
        response.read.assert_called_once_with(65)

    def test_identity_http_exception_is_exactly_scoped_to_local_ollama(self) -> None:
        values = dict(_identity().manifest())
        for identity_type in (EmbeddingIdentity, QueryEmbeddingIdentity):
            identity_type(**values)
            with self.assertRaises(ValueError):
                identity_type(**{**values, "provider": "other-provider"})
            with self.assertRaises(ValueError):
                identity_type(
                    **{**values, "base_url": "http://example.invalid/api/embed"}
                )
            with self.assertRaises(ValueError):
                identity_type(
                    **{**values, "base_url": "http://127.0.0.1:11434/api/tags"}
                )

    def test_registry_probe_binds_registered_dimension_and_digest(self) -> None:
        response = mock.Mock(status=200)
        response.read.return_value = json.dumps({"models": [{
            "name": "bge-m3:latest",
            "digest": "sha256:abc",
            "details": {"embedding_length": 1024},
        }]}).encode()
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch("rag_store.ollama_embedding.http.client.HTTPConnection", return_value=connection):
            info = inspect_ollama_model()
        self.assertEqual(1024, info.dimension)
        self.assertEqual("sha256:abc", info.digest)

    def test_registry_probe_rejects_oversized_raw_response(self) -> None:
        response = mock.Mock(status=200)
        response.read.return_value = b"x" * 65
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch(
            "rag_store.ollama_embedding.http.client.HTTPConnection",
            return_value=connection,
        ), self.assertRaisesRegex(
            OllamaEmbeddingError, "ollama_model_registry_response_too_large"
        ):
            inspect_ollama_model(max_response_bytes=64)
        response.read.assert_called_once_with(65)

    def test_real_adapter_uses_external_process_mode(self) -> None:
        adapter = EmbeddingAdapter(
            _identity(),
            policy=EmbeddingPolicy(8, 100, 1.0, 0, 2, 0, 0),
            transport=OllamaEmbeddingTransport(),
            transport_mode="external_process",
            input_unit_meter=len,
        )
        self.assertEqual("external_process", adapter.transport_mode)

    def test_build_and_query_identities_are_hash_identical(self) -> None:
        build, query = ollama_embedding_identities(
            OllamaModelInfo("bge-m3:latest", "digest", 1024)
        )
        self.assertEqual(build.sha256, query.sha256)
        self.assertEqual(1024, build.dimension)


if __name__ == "__main__":
    unittest.main()
