#!/usr/bin/env python3
"""Loopback-only Ollama Embedding transport for local vector builds.

This module is intentionally separate from the production HTTPS provider
bootstrap. It talks only to a local Ollama daemon and returns the repository's
normal embedding response contract, so build/query/entity vectors share one
real model identity and dimension.
"""

from __future__ import annotations

import http.client
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from .embedding_adapter import (
    EMBEDDING_RESPONSE_SCHEMA_VERSION,
    EmbeddingAdapter,
    EmbeddingIdentity,
    EmbeddingPolicy,
)
from .runtime_query_embedding import (
    QueryEmbeddingClient,
    QueryEmbeddingIdentity,
    QueryEmbeddingPolicy,
)


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "bge-m3:latest"
DEFAULT_OLLAMA_DIMENSION = 1024
OLLAMA_PROVIDER = "ollama-local"
OLLAMA_API_VERSION = "api-embed-v1"
OLLAMA_INPUT_TYPE = "document-or-query"
OLLAMA_MAX_MODEL_REGISTRY_RESPONSE_BYTES = 2 * 1024 * 1024
OLLAMA_MAX_EMBEDDING_RESPONSE_BYTES = 16 * 1024 * 1024


class OllamaEmbeddingError(RuntimeError):
    """Sanitized local Ollama failure."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _positive_response_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Ollama response limit must be a positive integer")
    return value


def _read_bounded_json(
    response: Any,
    *,
    max_response_bytes: int,
    too_large_code: str,
    invalid_code: str,
) -> Any:
    limit = _positive_response_limit(max_response_bytes)
    payload = response.read(limit + 1)
    if not isinstance(payload, bytes):
        raise OllamaEmbeddingError(invalid_code)
    if len(payload) > limit:
        raise OllamaEmbeddingError(too_large_code)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OllamaEmbeddingError(invalid_code) from None


def _loopback_endpoint(value: str, *, path: str) -> tuple[str, int, str]:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != path
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError("Ollama endpoint must be a loopback HTTP endpoint")
    try:
        port = parsed.port or 11434
    except ValueError:
        raise ValueError("Ollama endpoint port is invalid") from None
    if not 1 <= port <= 65535:
        raise ValueError("Ollama endpoint port is invalid")
    host = parsed.hostname
    if host == "localhost":
        host = "127.0.0.1"
    return host, port, path


def _finite_vector(value: Any, dimension: int) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise OllamaEmbeddingError("invalid_embedding_response")
    if len(value) != dimension:
        raise OllamaEmbeddingError("embedding_dimension_mismatch")
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise OllamaEmbeddingError("invalid_embedding_response")
        number = float(item)
        if not math.isfinite(number):
            raise OllamaEmbeddingError("invalid_embedding_response")
        vector.append(number)
    if not any(number != 0.0 for number in vector):
        raise OllamaEmbeddingError("zero_embedding")
    return vector


@dataclass(frozen=True)
class OllamaModelInfo:
    model: str
    digest: str
    dimension: int


def ollama_embedding_identities(
    info: OllamaModelInfo,
    *,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> tuple[EmbeddingIdentity, QueryEmbeddingIdentity]:
    """Create hash-identical build and query identities for one local model."""

    values = {
        "provider": OLLAMA_PROVIDER,
        "base_url": base_url.rstrip("/") + "/api/embed",
        "region": "local-loopback",
        "model": info.model,
        "model_version": info.digest,
        "api_version": OLLAMA_API_VERSION,
        "dimension": info.dimension,
        "normalization": "l2",
        "input_type": OLLAMA_INPUT_TYPE,
    }
    build_identity = EmbeddingIdentity(**values)
    query_identity = QueryEmbeddingIdentity(**values)
    if build_identity.sha256 != query_identity.sha256:
        raise OllamaEmbeddingError("ollama_identity_contract_mismatch")
    return build_identity, query_identity


def ollama_embedding_clients(
    info: OllamaModelInfo,
    *,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    batch_size: int = 32,
    max_input_units: int = 8192,
    timeout_seconds: float = 120.0,
) -> tuple[EmbeddingAdapter, QueryEmbeddingClient]:
    """Create build/entity and query clients with one exact vector identity."""

    build_identity, query_identity = ollama_embedding_identities(
        info, base_url=base_url
    )
    policy_values = {
        "batch_size": batch_size,
        "max_input_units": max_input_units,
        "timeout_seconds": timeout_seconds,
        "max_retries": 0,
        "max_requests_per_operation": 10000,
        "max_cost_microunits_per_request": 0,
        "total_cost_budget_microunits": 0,
    }
    transport = OllamaEmbeddingTransport(base_url=base_url)
    return (
        EmbeddingAdapter(
            build_identity,
            policy=EmbeddingPolicy(**policy_values),
            transport=transport,
            transport_mode="external_process",
            input_unit_meter=len,
        ),
        QueryEmbeddingClient(
            query_identity,
            policy=QueryEmbeddingPolicy(**policy_values),
            transport=transport,
            transport_mode="external_process",
            input_unit_meter=len,
        ),
    )


def inspect_ollama_model(
    *, base_url: str = DEFAULT_OLLAMA_BASE_URL, model: str = DEFAULT_OLLAMA_MODEL,
    timeout_seconds: float = 5.0,
    max_response_bytes: int = OLLAMA_MAX_MODEL_REGISTRY_RESPONSE_BYTES,
) -> OllamaModelInfo:
    """Read `/api/tags` and return the exact locally registered model identity."""

    if not isinstance(model, str) or not model.strip() or len(model) > 256:
        raise ValueError("Ollama model must be non-empty")
    host, port, _ = _loopback_endpoint(base_url.rstrip("/") + "/api/tags", path="/api/tags")
    connection = http.client.HTTPConnection(host, port, timeout=timeout_seconds)
    try:
        connection.request("GET", "/api/tags", headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise OllamaEmbeddingError("ollama_model_registry_unavailable")
        payload = _read_bounded_json(
            response,
            max_response_bytes=max_response_bytes,
            too_large_code="ollama_model_registry_response_too_large",
            invalid_code="ollama_model_registry_unavailable",
        )
    except OllamaEmbeddingError:
        raise
    except Exception:
        raise OllamaEmbeddingError("ollama_model_registry_unavailable") from None
    finally:
        connection.close()
    models = payload.get("models") if isinstance(payload, Mapping) else None
    if not isinstance(models, list):
        raise OllamaEmbeddingError("invalid_ollama_model_registry")
    for item in models:
        if not isinstance(item, Mapping) or item.get("name") != model:
            continue
        details = item.get("details")
        dimension = details.get("embedding_length") if isinstance(details, Mapping) else None
        if not isinstance(dimension, int) or dimension <= 0:
            raise OllamaEmbeddingError("ollama_model_dimension_unavailable")
        if model == DEFAULT_OLLAMA_MODEL and dimension != DEFAULT_OLLAMA_DIMENSION:
            raise OllamaEmbeddingError("ollama_default_model_dimension_mismatch")
        digest = item.get("digest")
        if not isinstance(digest, str) or not digest:
            raise OllamaEmbeddingError("ollama_model_digest_unavailable")
        return OllamaModelInfo(model=model, digest=digest, dimension=dimension)
    raise OllamaEmbeddingError("ollama_model_not_registered")


@dataclass(frozen=True)
class OllamaEmbeddingTransport:
    """Map repository batches to Ollama `/api/embed` and back."""

    base_url: str = DEFAULT_OLLAMA_BASE_URL
    truncate: bool = False
    max_response_bytes: int = OLLAMA_MAX_EMBEDDING_RESPONSE_BYTES

    def __post_init__(self) -> None:
        _loopback_endpoint(self.base_url.rstrip("/") + "/api/embed", path="/api/embed")
        _positive_response_limit(self.max_response_bytes)

    def __call__(
        self, identity: Any, payload: Mapping[str, Any], deadline: float
    ) -> Mapping[str, Any]:
        if getattr(deadline, "cancelled", False):
            raise TimeoutError("Ollama request cancelled")
        items = payload.get("items") if isinstance(payload, Mapping) else None
        if not isinstance(items, list) or not items:
            raise OllamaEmbeddingError("invalid_embedding_request")
        texts = [item.get("text") for item in items if isinstance(item, Mapping)]
        if len(texts) != len(items) or any(not isinstance(text, str) or not text for text in texts):
            raise OllamaEmbeddingError("invalid_embedding_request")
        model = str(getattr(identity, "model", ""))
        if not model:
            raise OllamaEmbeddingError("invalid_embedding_identity")
        body = _canonical_json({"model": model, "input": texts, "truncate": self.truncate})
        host, port, _ = _loopback_endpoint(self.base_url.rstrip("/") + "/api/embed", path="/api/embed")
        connection = http.client.HTTPConnection(host, port, timeout=max(0.05, float(deadline)))
        try:
            connection.request(
                "POST", "/api/embed", body=body,
                headers={"Accept": "application/json", "Content-Type": "application/json", "Content-Length": str(len(body))},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise OllamaEmbeddingError("ollama_embedding_failed")
            provider = _read_bounded_json(
                response,
                max_response_bytes=self.max_response_bytes,
                too_large_code="ollama_embedding_response_too_large",
                invalid_code="ollama_embedding_failed",
            )
        except OllamaEmbeddingError:
            raise
        except TimeoutError:
            raise
        except Exception:
            raise OllamaEmbeddingError("ollama_embedding_failed") from None
        finally:
            connection.close()
        if getattr(deadline, "cancelled", False):
            raise TimeoutError("Ollama request cancelled")
        if not isinstance(provider, Mapping) or provider.get("model") not in {None, model}:
            raise OllamaEmbeddingError("invalid_embedding_response")
        vectors = provider.get("embeddings")
        dimension = int(getattr(identity, "dimension", 0))
        if not isinstance(vectors, list) or len(vectors) != len(items):
            raise OllamaEmbeddingError("invalid_embedding_response")
        parsed = [_finite_vector(vector, dimension) for vector in vectors]
        return {
            "schema_version": EMBEDDING_RESPONSE_SCHEMA_VERSION,
            "embedding_identity_sha256": identity.sha256,
            "vectors": [
                {"id": str(item["id"]), "values": vector}
                for item, vector in zip(items, parsed, strict=True)
            ],
            "failed_ids": [],
            "usage": {
                "input_units": sum(int(item["input_units"]) for item in items),
                "cost_microunits": 0,
            },
        }


def ollama_environment() -> tuple[str, str]:
    """Resolve local-only defaults without reading provider secrets."""

    base_url = os.environ.get("KG_OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = os.environ.get("KG_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    _loopback_endpoint(base_url + "/api/embed", path="/api/embed")
    if not model.strip():
        raise ValueError("KG_OLLAMA_MODEL must be non-empty")
    return base_url, model


__all__ = [
    "DEFAULT_OLLAMA_BASE_URL",
    "DEFAULT_OLLAMA_DIMENSION",
    "DEFAULT_OLLAMA_MODEL",
    "OLLAMA_API_VERSION",
    "OLLAMA_INPUT_TYPE",
    "OLLAMA_MAX_EMBEDDING_RESPONSE_BYTES",
    "OLLAMA_MAX_MODEL_REGISTRY_RESPONSE_BYTES",
    "OLLAMA_PROVIDER",
    "OllamaEmbeddingError",
    "OllamaEmbeddingTransport",
    "OllamaModelInfo",
    "inspect_ollama_model",
    "ollama_embedding_clients",
    "ollama_embedding_identities",
    "ollama_environment",
]
