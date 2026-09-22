#!/usr/bin/env python3
"""Deterministic offline transports for pre-Stop-B tests and candidate builds."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from deploy.rag_store.embedding_adapter import (
    EMBEDDING_RESPONSE_SCHEMA_VERSION,
    EmbeddingIdentity,
)
from deploy.rag_store.server_answer_model import (
    RESPONSE_SCHEMA_VERSION,
    ServerAnswerChannel,
)


FAKE_PROVIDER_POLICY_VERSION = "cloud-v2-fake-provider-v1"
FAKE_EMBEDDING_MODEL = "sha256-fixture"
FAKE_EMBEDDING_ALGORITHM_VERSION = "whole-text-char-1-2gram-v2"
FAKE_EMBEDDING_DIMENSION = 32


def fake_embedding_identity() -> EmbeddingIdentity:
    """Return the identity of the current deterministic fake vector algorithm."""

    return EmbeddingIdentity(
        provider="fake-offline",
        base_url="https://fake.invalid/v1/embeddings",
        region="offline",
        model=FAKE_EMBEDDING_MODEL,
        model_version=FAKE_EMBEDDING_ALGORITHM_VERSION,
        api_version="v1",
        dimension=FAKE_EMBEDDING_DIMENSION,
        normalization="l2",
        input_type="document-or-query",
    )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _fake_vector(identity: EmbeddingIdentity, item: Mapping[str, Any]) -> list[float]:
    text = str(item["text"])
    features = [text]
    features.extend(text[index : index + 1] for index in range(len(text)))
    features.extend(text[index : index + 2] for index in range(max(0, len(text) - 1)))
    values = [0.0] * identity.dimension
    for feature in features:
        digest = hashlib.sha256(
            (identity.sha256 + "\x00" + feature).encode("utf-8")
        ).digest()
        index = int.from_bytes(digest[:4], "big") % identity.dimension
        sign = 1.0 if digest[4] & 1 else -1.0
        values[index] += sign
    if not any(value != 0.0 for value in values):
        values[0] = 1.0
    return values


@dataclass
class FakeEmbeddingTransport:
    """Return schema-valid vectors without resolving or opening a socket."""

    fail_on_call: int | None = None
    call_count: int = 0
    request_hashes: list[str] = field(default_factory=list)

    def __call__(
        self,
        identity: EmbeddingIdentity,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        del timeout_seconds
        self.call_count += 1
        self.request_hashes.append(_canonical_sha256(payload))
        if self.fail_on_call == self.call_count:
            raise RuntimeError("synthetic embedding failure")
        items = payload["items"]
        return {
            "schema_version": EMBEDDING_RESPONSE_SCHEMA_VERSION,
            "embedding_identity_sha256": identity.sha256,
            "vectors": [
                {"id": item["id"], "values": _fake_vector(identity, item)}
                for item in items
            ],
            "failed_ids": [],
            "usage": {
                "input_units": sum(int(item["input_units"]) for item in items),
                "cost_microunits": 0,
            },
        }


@dataclass
class FakeServerAnswerTransport:
    """Return a fixed sanitized answer or a controlled synthetic failure."""

    answer: str = "离线合成回答"
    behavior: str = "success"
    call_count: int = 0
    request_hashes: list[str] = field(default_factory=list)
    request_payloads: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def __call__(
        self,
        channel: ServerAnswerChannel,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        del timeout_seconds
        self.call_count += 1
        self.request_hashes.append(_canonical_sha256(payload))
        self.request_payloads.append(
            json.loads(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
        )
        if self.behavior == "timeout":
            raise TimeoutError("synthetic timeout")
        if self.behavior == "failure":
            raise RuntimeError("synthetic failure")
        answer = "" if self.behavior == "empty" else self.answer
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "channel_identity_sha256": channel.identity_sha256,
            "answer": answer,
            "usage": {
                "input_units": int(payload["input_units"]),
                "output_units": min(len(answer), channel.max_output_units),
                "cost_microunits": 0,
            },
        }
