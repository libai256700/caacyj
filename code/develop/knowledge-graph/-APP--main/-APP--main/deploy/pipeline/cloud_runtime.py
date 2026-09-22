#!/usr/bin/env python3
"""Read-only cloud runtime bindings for approved active RAG artifacts.

This module deliberately contains no provider transport implementation. Runtime
answer and embedding transports must be injected by a deployment bootstrap and
must match the identities frozen in the active runtime configuration.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import threading
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from rag_store.cloud_claim_evidence import build_claim_map_instruction
from rag_store.runtime_query_embedding import (
    QueryEmbeddingClient,
    QueryEmbeddingInput,
)
from rag_store.runtime_neo4j_reader import (
    Neo4jReadBinding,
    ReadOnlyNeo4jError,
    ReadOnlyScopedNeo4jReader,
    open_scoped_neo4j_reader,
)
from rag_store.runtime_sqlite_reader import (
    EXPECTED_AUTHORITY_SCHEMA_RECORDS,
    EXPECTED_BM25_SCHEMA_RECORDS,
    ReadOnlyAuthorityReader as ReadOnlyAuthorityStore,
    ReadOnlyFtsReader as ReadOnlyFtsIndex,
    ReadOnlySQLiteError,
    read_stable_regular_file,
)
from rag_store.runtime_vector_reader import (
    ReadOnlyVectorContract,
    ReadOnlyVectorError,
    ReadOnlyVectorReader,
)
from rag_store.server_answer_coordinator import (
    CoordinatorResult,
    ServerAnswerCoordinator,
    ServerAnswerUnavailable,
)
from rag_store.server_answer_model import ServerAnswerRequest
from rag_store.scoped_graph_contract import (
    NEO4J_DRIVER_NAME,
    NEO4J_DRIVER_VERSION,
    ScopedGraphContractError,
    ScopedGraphPackage,
    load_scoped_graph_package,
)
from rag_store.source_authority import (
    FROZEN_R9_SOURCE_SCOPE,
    SourceAuthorityError,
    authority_priority_rule,
    load_bound_regulation_governance,
)


CONFIG_ENVIRONMENT_VARIABLE = "KG_CLOUD_RUNTIME_CONFIG"
CONFIG_SHA256_ENVIRONMENT_VARIABLE = "KG_CLOUD_RUNTIME_CONFIG_SHA256"
CONFIG_SCHEMA_VERSION = "kg-cloud-runtime-config-v1"
ANSWER_TELEMETRY_SCHEMA_VERSION = "kg-answer-model-telemetry-v1"
EMBEDDING_MODE = "provider-neutral-external-api"
SCOPED_GRAPH_EVIDENCE_ORIGIN = "scoped_graph_manifest_entity"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
_MAX_CONFIG_BYTES = 1024 * 1024
_SERVER_ANSWER_STRATEGIES = frozenset(
    {"single", "sequential_fallback", "parallel_hedge"}
)
_WINNER_POLICIES = frozenset({"first_success", "ordered_success"})


class CloudRuntimeError(RuntimeError):
    """Base error for a fail-closed active runtime."""


class CloudRuntimeConfigError(CloudRuntimeError):
    """The explicit active runtime configuration is invalid."""


class CloudRuntimeIntegrityError(CloudRuntimeError):
    """An active artifact does not match its approved identity."""


class CloudRuntimeDependencyError(CloudRuntimeError):
    """An approved provider-neutral adapter has not been injected."""


AnswerCoordinationUnavailable = ServerAnswerUnavailable


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _merge_records(
    first: Sequence[Mapping[str, Any]],
    second: Sequence[Mapping[str, Any]],
    identity_field: str,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in [*first, *second]:
        if not isinstance(item, Mapping):
            continue
        identity = str(item.get(identity_field) or "")
        if identity and identity not in merged:
            merged[identity] = dict(item)
    return list(merged.values())


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _canonical_source_fingerprint(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    digest = hashlib.sha256()
    text_byte_count = 0
    text_codepoint_count = 0
    document_names: set[str] = set()
    for row in sorted(rows, key=lambda item: str(item["chunk_id"])):
        text = str(row["text"])
        document_names.add(str(row["doc_name"]))
        text_byte_count += len(text.encode("utf-8"))
        text_codepoint_count += len(text)
        canonical_row = json.dumps(
            [row["chunk_id"], row["doc_name"], row["chunk_index"], text],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest.update(canonical_row.encode("utf-8"))
        digest.update(b"\n")
    return {
        "chunk_count": len(rows),
        "document_count": len(document_names),
        "text_byte_count": text_byte_count,
        "text_codepoint_count": text_codepoint_count,
        "schema_version": "chunks-v1",
        "fingerprint_algorithm": "sha256-jsonl-chunk-content-v1",
        "fingerprint": digest.hexdigest(),
    }


def _required_text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise CloudRuntimeConfigError(f"{field} must be non-empty text")
    return value


def _required_sha256(value: Any, field: str) -> str:
    normalized = _required_text(value, field)
    if not _SHA256.fullmatch(normalized):
        raise CloudRuntimeConfigError(f"{field} must be a lowercase SHA-256")
    return normalized


def _required_environment_name(value: Any, field: str) -> str:
    normalized = _required_text(value, field)
    if not _ENVIRONMENT_NAME.fullmatch(normalized):
        raise CloudRuntimeConfigError(
            f"{field} must be an exact environment variable name"
        )
    return normalized


def _exact_mapping(
    value: Any,
    field: str,
    expected_fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise CloudRuntimeConfigError(f"{field} fields do not match the frozen schema")
    return dict(value)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CloudRuntimeConfigError(f"{field} must be a positive integer")
    return value


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CloudRuntimeConfigError(f"{field} must be a positive number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise CloudRuntimeConfigError(f"{field} must be a positive finite number")
    return normalized


def _relative_path(value: Any, field: str) -> str:
    normalized = _required_text(value, field)
    if normalized.startswith("/") or "\\" in normalized:
        raise CloudRuntimeConfigError(f"{field} must be a relative POSIX path")
    path = PurePosixPath(normalized)
    if (
        any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != normalized
    ):
        raise CloudRuntimeConfigError(f"{field} contains an unsafe component")
    if any(character in normalized for character in "*?[]{}"):
        raise CloudRuntimeConfigError(f"{field} cannot contain a glob")
    return path.as_posix()


def _canonical_directory(value: Any, field: str) -> Path:
    raw = Path(_required_text(value, field))
    if not raw.is_absolute():
        raise CloudRuntimeConfigError(f"{field} must be absolute")
    lexical = Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise CloudRuntimeConfigError(f"{field} does not exist") from exc
    if lexical != resolved or not resolved.is_dir() or resolved.is_symlink():
        raise CloudRuntimeConfigError(f"{field} must be a canonical real directory")
    if "active" not in resolved.parts:
        raise CloudRuntimeConfigError(f"{field} must identify an explicit active root")
    return resolved


def _active_file(active_root: Path, relative: str, field: str) -> Path:
    path = active_root.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CloudRuntimeIntegrityError(f"{field} is unavailable") from exc
    if active_root not in resolved.parents:
        raise CloudRuntimeIntegrityError(f"{field} escapes the active root")
    if resolved != path or not resolved.is_file() or resolved.is_symlink():
        raise CloudRuntimeIntegrityError(f"{field} must be a canonical regular file")
    if resolved.stat().st_mode & _WRITE_BITS:
        raise CloudRuntimeIntegrityError(f"{field} must be read-only")
    return resolved


def _stable_config_bytes(path: str | Path) -> tuple[Path, bytes]:
    raw = Path(path)
    if not raw.is_absolute():
        raise CloudRuntimeConfigError("runtime config path must be absolute")
    lexical = Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise CloudRuntimeConfigError("runtime config is unavailable") from exc
    if resolved != lexical or resolved.is_symlink():
        raise CloudRuntimeConfigError("runtime config path must be canonical")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(resolved, flags)
    except OSError as exc:
        raise CloudRuntimeConfigError("runtime config is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        named_before = os.stat(resolved, follow_symlinks=False)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(named_before.st_mode)
            or (before.st_dev, before.st_ino)
            != (named_before.st_dev, named_before.st_ino)
            or before.st_size <= 0
            or before.st_size > _MAX_CONFIG_BYTES
        ):
            raise CloudRuntimeConfigError("runtime config must be a regular file")
        blocks: list[bytes] = []
        remaining = _MAX_CONFIG_BYTES + 1
        while remaining > 0:
            block = os.read(descriptor, min(64 * 1024, remaining))
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        payload = b"".join(blocks)
        after = os.fstat(descriptor)
        named_after = os.stat(resolved, follow_symlinks=False)
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if (
            before_identity != after_identity
            or (after.st_dev, after.st_ino)
            != (named_after.st_dev, named_after.st_ino)
            or len(payload) != before.st_size
            or len(payload) > _MAX_CONFIG_BYTES
        ):
            raise CloudRuntimeConfigError("runtime config changed during read")
        return resolved, payload
    except OSError as exc:
        raise CloudRuntimeConfigError("runtime config changed during read") from exc
    finally:
        os.close(descriptor)


def _load_strict_config_json(payload: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise CloudRuntimeConfigError("runtime config contains a duplicate JSON key")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        raise CloudRuntimeConfigError("runtime config contains a non-finite JSON value")

    value = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise CloudRuntimeConfigError("runtime config must contain an object")
    return value


def _strict_pairs(
    pairs: Sequence[tuple[str, Any]], field: str
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CloudRuntimeIntegrityError(f"duplicate JSON key in {field}")
        value[key] = item
    return value


def _load_json_bytes(payload: bytes, field: str) -> dict[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise CloudRuntimeIntegrityError(f"duplicate JSON key in {field}")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        raise CloudRuntimeIntegrityError(f"non-finite JSON value in {field}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except CloudRuntimeIntegrityError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudRuntimeIntegrityError(f"{field} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise CloudRuntimeIntegrityError(f"{field} must contain an object")
    return value


def _read_bound_payload(path: Path, expected_sha256: str, field: str) -> bytes:
    try:
        _stable_path, payload, actual_sha256 = read_stable_regular_file(path, field)
    except ReadOnlySQLiteError as exc:
        raise CloudRuntimeIntegrityError(f"{field} stable read failed") from exc
    if actual_sha256 != expected_sha256:
        raise CloudRuntimeIntegrityError(f"{field} hash mismatch")
    return payload


def _load_bound_json(path: Path, expected_sha256: str, field: str) -> dict[str, Any]:
    payload = _read_bound_payload(path, expected_sha256, field)
    return _load_json_bytes(payload, field)


@dataclass(frozen=True)
class ArtifactBinding:
    manifest_path: str
    manifest_sha256: str
    data_path: str
    data_sha256: str


@dataclass(frozen=True)
class GraphBinding:
    manifest_path: str
    manifest_sha256: str
    release_id: str
    driver: str
    driver_version: str
    uri_env: str
    username_env: str
    password_env: str
    database_env: str
    query_timeout_seconds: float
    max_records: int

    @property
    def reader_binding(self) -> Neo4jReadBinding:
        return Neo4jReadBinding(
            graph_release_id=self.release_id,
            driver=self.driver,
            driver_version=self.driver_version,
            uri_env=self.uri_env,
            username_env=self.username_env,
            password_env=self.password_env,
            database_env=self.database_env,
            query_timeout_seconds=self.query_timeout_seconds,
            max_records=self.max_records,
        )


@dataclass(frozen=True)
class RegulationGovernanceBinding:
    timeline_path: str
    timeline_sha256: str
    superseded_path: str
    superseded_sha256: str


@dataclass(frozen=True)
class AnswerChannelBinding:
    channel_id: str
    identity_sha256: str


@dataclass(frozen=True)
class AnswerPolicyBinding:
    strategy: str
    winner_policy: str
    ordered_channels: tuple[AnswerChannelBinding, ...]
    total_budget_seconds: float
    total_cost_budget_microunits: int
    circuit_breaker_failure_threshold: int
    circuit_breaker_cooldown_seconds: float

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "strategy": self.strategy,
                "winner_policy": self.winner_policy,
                "ordered_channels": [
                    {
                        "channel_id": item.channel_id,
                        "identity_sha256": item.identity_sha256,
                    }
                    for item in self.ordered_channels
                ],
                "total_budget_seconds": self.total_budget_seconds,
                "total_cost_budget_microunits": self.total_cost_budget_microunits,
                "circuit_breaker_failure_threshold": self.circuit_breaker_failure_threshold,
                "circuit_breaker_cooldown_seconds": self.circuit_breaker_cooldown_seconds,
            }
        )


@dataclass(frozen=True)
class CloudRuntimeConfig:
    runtime_release_id: str
    active_root: Path
    provider_runtime_config_sha256: str
    authority: ArtifactBinding
    bm25: ArtifactBinding
    graph: GraphBinding
    regulation_governance: RegulationGovernanceBinding
    embedding_identity_sha256: str
    embedding_policy_sha256: str
    local_vector: Mapping[str, Any]
    server_answer: AnswerPolicyBinding

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        expected_sha256: str,
    ) -> "CloudRuntimeConfig":
        expected = _required_sha256(expected_sha256, "expected_config_sha256")
        try:
            _resolved_config, payload = _stable_config_bytes(path)
            if hashlib.sha256(payload).hexdigest() != expected:
                raise CloudRuntimeConfigError("runtime config hash mismatch")
            raw = _load_strict_config_json(payload)
        except CloudRuntimeConfigError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CloudRuntimeConfigError("runtime config is not valid JSON") from exc
        root = _exact_mapping(
            raw,
            "runtime config",
            {
                "schema_version",
                "runtime_release_id",
                "active_root",
                "provider_runtime",
                "authority",
                "bm25",
                "graph",
                "regulation_governance",
                "embedding",
                "local_vector",
                "server_answer",
            },
        )
        if root["schema_version"] != CONFIG_SCHEMA_VERSION:
            raise CloudRuntimeConfigError("runtime config schema version mismatch")
        active_root = _canonical_directory(root["active_root"], "active_root")
        provider_runtime_raw = _exact_mapping(
            root["provider_runtime"],
            "provider_runtime",
            {"config_sha256"},
        )

        def artifact(value: Any, field: str) -> ArtifactBinding:
            item = _exact_mapping(
                value,
                field,
                {"manifest_path", "manifest_sha256", "data_path", "data_sha256"},
            )
            return ArtifactBinding(
                manifest_path=_relative_path(item["manifest_path"], f"{field}.manifest_path"),
                manifest_sha256=_required_sha256(
                    item["manifest_sha256"], f"{field}.manifest_sha256"
                ),
                data_path=_relative_path(item["data_path"], f"{field}.data_path"),
                data_sha256=_required_sha256(
                    item["data_sha256"], f"{field}.data_sha256"
                ),
            )

        graph_raw = _exact_mapping(
            root["graph"],
            "graph",
            {
                "manifest_path",
                "manifest_sha256",
                "release_id",
                "driver",
                "driver_version",
                "uri_env",
                "username_env",
                "password_env",
                "database_env",
                "query_timeout_seconds",
                "max_records",
            },
        )
        regulation_raw = _exact_mapping(
            root["regulation_governance"],
            "regulation_governance",
            {
                "timeline_path",
                "timeline_sha256",
                "superseded_path",
                "superseded_sha256",
            },
        )
        embedding_raw = _exact_mapping(
            root["embedding"],
            "embedding",
            {"identity_sha256", "policy_sha256"},
        )
        local_vector = _parse_local_vector(root["local_vector"])
        server_answer = _parse_answer_policy(root["server_answer"])
        config = cls(
            runtime_release_id=_required_text(
                root["runtime_release_id"], "runtime_release_id"
            ),
            active_root=active_root,
            provider_runtime_config_sha256=_required_sha256(
                provider_runtime_raw["config_sha256"],
                "provider_runtime.config_sha256",
            ),
            authority=artifact(root["authority"], "authority"),
            bm25=artifact(root["bm25"], "bm25"),
            graph=GraphBinding(
                manifest_path=_relative_path(
                    graph_raw["manifest_path"], "graph.manifest_path"
                ),
                manifest_sha256=_required_sha256(
                    graph_raw["manifest_sha256"], "graph.manifest_sha256"
                ),
                release_id=_required_text(
                    graph_raw["release_id"], "graph.release_id"
                ),
                driver=_required_text(graph_raw["driver"], "graph.driver"),
                driver_version=_required_text(
                    graph_raw["driver_version"], "graph.driver_version"
                ),
                uri_env=_required_environment_name(
                    graph_raw["uri_env"], "graph.uri_env"
                ),
                username_env=_required_environment_name(
                    graph_raw["username_env"], "graph.username_env"
                ),
                password_env=_required_environment_name(
                    graph_raw["password_env"], "graph.password_env"
                ),
                database_env=_required_environment_name(
                    graph_raw["database_env"], "graph.database_env"
                ),
                query_timeout_seconds=_positive_number(
                    graph_raw["query_timeout_seconds"],
                    "graph.query_timeout_seconds",
                ),
                max_records=_positive_int(
                    graph_raw["max_records"], "graph.max_records"
                ),
            ),
            regulation_governance=RegulationGovernanceBinding(
                timeline_path=_relative_path(
                    regulation_raw["timeline_path"],
                    "regulation_governance.timeline_path",
                ),
                timeline_sha256=_required_sha256(
                    regulation_raw["timeline_sha256"],
                    "regulation_governance.timeline_sha256",
                ),
                superseded_path=_relative_path(
                    regulation_raw["superseded_path"],
                    "regulation_governance.superseded_path",
                ),
                superseded_sha256=_required_sha256(
                    regulation_raw["superseded_sha256"],
                    "regulation_governance.superseded_sha256",
                ),
            ),
            embedding_identity_sha256=_required_sha256(
                embedding_raw["identity_sha256"], "embedding.identity_sha256"
            ),
            embedding_policy_sha256=_required_sha256(
                embedding_raw["policy_sha256"], "embedding.policy_sha256"
            ),
            local_vector=MappingProxyType(local_vector),
            server_answer=server_answer,
        )
        if local_vector["authority_manifest_sha256"] != config.authority.manifest_sha256:
            raise CloudRuntimeConfigError("local vector authority binding mismatch")
        if local_vector["embedding_identity_sha256"] != config.embedding_identity_sha256:
            raise CloudRuntimeConfigError("local vector embedding binding mismatch")
        if (
            config.graph.driver != NEO4J_DRIVER_NAME
            or config.graph.driver_version != NEO4J_DRIVER_VERSION
            or config.graph.max_records > 1000
        ):
            raise CloudRuntimeConfigError("graph runtime contract mismatch")
        try:
            config.graph.reader_binding
        except ValueError as exc:
            raise CloudRuntimeConfigError("graph runtime binding is invalid") from exc
        return config


def _parse_local_vector(value: Any) -> dict[str, Any]:
    fields = {
        "data_root",
        "data_release_id",
        "manifest_sha256",
        "authority_manifest_sha256",
        "chunking_identity_sha256",
        "embedding_identity_sha256",
        "dimension",
        "metric",
        "schema_version",
        "chunk_index_name",
        "entity_index_name",
        "top_k_max",
        "max_vectors_per_index",
        "metadata_allowlist",
        "engine",
        "engine_version",
    }
    item = _exact_mapping(value, "local_vector", fields)
    allowlist_raw = _exact_mapping(
        item["metadata_allowlist"],
        "local_vector.metadata_allowlist",
        {"chunk", "entity"},
    )
    allowlist: dict[str, tuple[str, ...]] = {}
    for kind in ("chunk", "entity"):
        raw_fields = allowlist_raw[kind]
        if not isinstance(raw_fields, list) or any(
            not isinstance(field, str) or not field.strip() for field in raw_fields
        ):
            raise CloudRuntimeConfigError("local vector metadata allowlist is invalid")
        normalized = tuple(field.strip() for field in raw_fields)
        if len(normalized) != len(set(normalized)):
            raise CloudRuntimeConfigError("local vector metadata allowlist has duplicates")
        allowlist[kind] = normalized
    return {
        "data_root": _relative_path(item["data_root"], "local_vector.data_root"),
        "data_release_id": _required_text(
            item["data_release_id"], "local_vector.data_release_id"
        ),
        "manifest_sha256": _required_sha256(
            item["manifest_sha256"], "local_vector.manifest_sha256"
        ),
        "authority_manifest_sha256": _required_sha256(
            item["authority_manifest_sha256"],
            "local_vector.authority_manifest_sha256",
        ),
        "chunking_identity_sha256": _required_sha256(
            item["chunking_identity_sha256"],
            "local_vector.chunking_identity_sha256",
        ),
        "embedding_identity_sha256": _required_sha256(
            item["embedding_identity_sha256"],
            "local_vector.embedding_identity_sha256",
        ),
        "dimension": _positive_int(item["dimension"], "local_vector.dimension"),
        "metric": _required_text(item["metric"], "local_vector.metric"),
        "schema_version": _required_text(
            item["schema_version"], "local_vector.schema_version"
        ),
        "chunk_index_name": _required_text(
            item["chunk_index_name"], "local_vector.chunk_index_name"
        ),
        "entity_index_name": _required_text(
            item["entity_index_name"], "local_vector.entity_index_name"
        ),
        "top_k_max": _positive_int(
            item["top_k_max"], "local_vector.top_k_max"
        ),
        "max_vectors_per_index": _positive_int(
            item["max_vectors_per_index"],
            "local_vector.max_vectors_per_index",
        ),
        "metadata_allowlist": MappingProxyType(allowlist),
        "engine": _required_text(item["engine"], "local_vector.engine"),
        "engine_version": _required_text(
            item["engine_version"], "local_vector.engine_version"
        ),
    }


def _parse_answer_policy(value: Any) -> AnswerPolicyBinding:
    item = _exact_mapping(
        value,
        "server_answer",
        {
            "strategy",
            "winner_policy",
            "ordered_channels",
            "total_budget_seconds",
            "total_cost_budget_microunits",
            "circuit_breaker_failure_threshold",
            "circuit_breaker_cooldown_seconds",
        },
    )
    strategy = _required_text(item["strategy"], "server_answer.strategy")
    winner_policy = _required_text(
        item["winner_policy"], "server_answer.winner_policy"
    )
    if strategy not in _SERVER_ANSWER_STRATEGIES:
        raise CloudRuntimeConfigError("server answer strategy is unsupported")
    if winner_policy not in _WINNER_POLICIES:
        raise CloudRuntimeConfigError("server answer winner policy is unsupported")
    channels_raw = item["ordered_channels"]
    if not isinstance(channels_raw, list) or not channels_raw:
        raise CloudRuntimeConfigError("server answer requires at least one channel")
    channels: list[AnswerChannelBinding] = []
    for index, value in enumerate(channels_raw):
        channel = _exact_mapping(
            value,
            f"server_answer.ordered_channels[{index}]",
            {"channel_id", "identity_sha256"},
        )
        channels.append(
            AnswerChannelBinding(
                _required_text(channel["channel_id"], "server answer channel id"),
                _required_sha256(
                    channel["identity_sha256"], "server answer channel identity"
                ),
            )
        )
    ids = [channel.channel_id for channel in channels]
    if len(ids) != len(set(ids)):
        raise CloudRuntimeConfigError("server answer channel ids must be unique")
    if strategy == "single" and len(channels) != 1:
        raise CloudRuntimeConfigError("single strategy requires exactly one channel")
    if strategy != "parallel_hedge" and winner_policy != "ordered_success":
        raise CloudRuntimeConfigError(
            "non-parallel server answer strategies require ordered_success"
        )
    cost_budget = _positive_int(
        item["total_cost_budget_microunits"],
        "server_answer.total_cost_budget_microunits",
    )
    return AnswerPolicyBinding(
        strategy=strategy,
        winner_policy=winner_policy,
        ordered_channels=tuple(channels),
        total_budget_seconds=_positive_number(
            item["total_budget_seconds"], "server_answer.total_budget_seconds"
        ),
        total_cost_budget_microunits=cost_budget,
        circuit_breaker_failure_threshold=_positive_int(
            item["circuit_breaker_failure_threshold"],
            "server_answer.circuit_breaker_failure_threshold",
        ),
        circuit_breaker_cooldown_seconds=_positive_number(
            item["circuit_breaker_cooldown_seconds"],
            "server_answer.circuit_breaker_cooldown_seconds",
        ),
    )


class ReadOnlyLocalVectorIndex:
    """Dense/vector compatibility facade backed by an active local read view."""

    def __init__(self, read_view: Any, authority: ReadOnlyAuthorityStore):
        self.read_view = read_view
        self.authority = authority

    @staticmethod
    def _score(distance: float) -> float:
        return 1.0 / (1.0 + max(0.0, float(distance)))

    def search_by_embedding(
        self, embedding: Sequence[float], limit: int = 10
    ) -> list[dict[str, Any]]:
        hits = self.read_view.query_chunk(embedding, top_k=limit)
        ids = [hit.object_id for hit in hits]
        rows = self.authority.require_chunks(ids)
        hit_by_id = {hit.object_id: hit for hit in hits}
        return [
            {
                **row,
                "score": self._score(hit_by_id[str(row["chunk_id"])].distance),
                "type": "chunk",
                "source": "dense",
            }
            for row in rows
        ]


class CloudRuntimeResources:
    """Opened and cross-bound active artifacts plus injected provider adapters."""

    def __init__(
        self,
        config: CloudRuntimeConfig,
        authority_store: ReadOnlyAuthorityStore,
        bm25_index: ReadOnlyFtsIndex,
        vector_index: ReadOnlyLocalVectorIndex,
        vector_view: Any,
        graph_reader: ReadOnlyScopedNeo4jReader,
        graph_entities: Sequence[Mapping[str, Any]],
        regulation_governance: Mapping[str, Any],
        regulation_timeline: Mapping[str, Mapping[str, Any]],
        superseded_passages: Sequence[Mapping[str, Any]],
    ) -> None:
        self.config = config
        self.authority_store = authority_store
        self.bm25_index = bm25_index
        self.vector_index = vector_index
        self._vector_view = vector_view
        self._graph_reader = graph_reader
        self._graph_entities = MappingProxyType(
            {
                str(item["entity_id"]): MappingProxyType(
                    {
                        "canonical_name": str(item["canonical_name"]),
                        "entity_type": str(item["entity_type"]),
                        "evidence_chunk_ids": frozenset(
                            str(value) for value in item["evidence_chunk_ids"]
                        ),
                    }
                )
                for item in graph_entities
            }
        )
        self.regulation_governance = _deep_freeze(regulation_governance)
        self.regulation_timeline = _deep_freeze(regulation_timeline)
        self.superseded_passages = _deep_freeze(superseded_passages)
        self._embedding_adapter: QueryEmbeddingClient | None = None
        self._answer_coordinator: ServerAnswerCoordinator | None = None
        self._dependency_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def _require_open(self) -> None:
        with self._close_lock:
            if self._closed:
                raise CloudRuntimeDependencyError("cloud runtime is closed")

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            failures: list[BaseException] = []
            for close_resource in (
                self._graph_reader.close,
                self._vector_view.close,
                self.bm25_index.close,
                self.authority_store.close,
            ):
                try:
                    close_resource()
                except BaseException as exc:
                    failures.append(exc)
            if failures:
                raise CloudRuntimeError("cloud runtime resource close failed") from failures[0]

    def __enter__(self) -> "CloudRuntimeResources":
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.close()

    @classmethod
    def open(
        cls,
        config_path: str | Path,
        *,
        expected_config_sha256: str,
        environment: Mapping[str, str] | None = None,
        graph_driver_factory: Any | None = None,
    ) -> "CloudRuntimeResources":
        config = CloudRuntimeConfig.load(
            config_path,
            expected_sha256=expected_config_sha256,
        )
        runtime_environment = os.environ if environment is None else environment
        timeline_path = _active_file(
            config.active_root,
            config.regulation_governance.timeline_path,
            "regulation timeline",
        )
        superseded_path = _active_file(
            config.active_root,
            config.regulation_governance.superseded_path,
            "superseded passage registry",
        )
        timeline_payload = _read_bound_payload(
            timeline_path,
            config.regulation_governance.timeline_sha256,
            "regulation timeline",
        )
        superseded_payload = _read_bound_payload(
            superseded_path,
            config.regulation_governance.superseded_sha256,
            "superseded passage registry",
        )
        authority_manifest_path = _active_file(
            config.active_root,
            config.authority.manifest_path,
            "authority manifest",
        )
        authority_database_path = _active_file(
            config.active_root,
            config.authority.data_path,
            "authority database",
        )
        authority_manifest = _load_bound_json(
            authority_manifest_path,
            config.authority.manifest_sha256,
            "authority manifest",
        )
        _require_hash(
            authority_database_path,
            config.authority.data_sha256,
            "authority database",
        )
        _validate_authority_manifest(
            authority_manifest,
            authority_database_path,
            config.authority,
        )
        with ExitStack() as cleanup:
            authority_store = ReadOnlyAuthorityStore(authority_database_path)
            cleanup.callback(authority_store.close)
            if authority_store.database_sha256 != config.authority.data_sha256:
                raise CloudRuntimeIntegrityError(
                    "authority database descriptor hash mismatch"
                )
            authority_chunk_documents = _validate_authority_database(
                authority_store, authority_manifest
            )
            authority_ids = set(authority_chunk_documents)
            try:
                authority_rows = [
                    dict(row)
                    for row in authority_store.chunk_evidence_rows()
                ]
            except ReadOnlySQLiteError as exc:
                raise CloudRuntimeIntegrityError(
                    "authority SQLite fixed read failed"
                ) from exc
            try:
                (
                    regulation_governance,
                    regulation_timeline,
                    superseded_passages,
                ) = load_bound_regulation_governance(
                    authority_manifest,
                    authority_rows,
                    timeline_path=timeline_path,
                    superseded_path=superseded_path,
                    timeline_payload=timeline_payload,
                    superseded_payload=superseded_payload,
                )
            except SourceAuthorityError as exc:
                raise CloudRuntimeIntegrityError(
                    "regulation governance binding mismatch"
                ) from exc

            bm25_manifest_path = _active_file(
                config.active_root, config.bm25.manifest_path, "BM25 manifest"
            )
            bm25_database_path = _active_file(
                config.active_root, config.bm25.data_path, "BM25 database"
            )
            bm25_manifest = _load_bound_json(
                bm25_manifest_path,
                config.bm25.manifest_sha256,
                "BM25 manifest",
            )
            _require_hash(
                bm25_database_path, config.bm25.data_sha256, "BM25 database"
            )
            bm25_index = ReadOnlyFtsIndex(bm25_database_path, authority_store)
            cleanup.callback(bm25_index.close)
            if bm25_index.database_sha256 != config.bm25.data_sha256:
                raise CloudRuntimeIntegrityError(
                    "BM25 database descriptor hash mismatch"
                )
            _validate_bm25(
                bm25_manifest,
                bm25_database_path,
                config.bm25,
                authority_manifest,
                authority_ids,
                authority_store,
                bm25_index,
            )

            graph_manifest_path = _active_file(
                config.active_root, config.graph.manifest_path, "graph manifest"
            )
            graph_manifest = _load_bound_json(
                graph_manifest_path,
                config.graph.manifest_sha256,
                "graph manifest",
            )
            graph_package = _validate_graph(
                graph_manifest_path,
                graph_manifest,
                authority_manifest,
                authority_chunk_documents,
                config.graph,
            )
            try:
                graph_reader_kwargs = {
                    "authority_release_id": str(authority_manifest["release_id"]),
                    "package": graph_package,
                    "environment": runtime_environment,
                }
                if graph_driver_factory is not None:
                    graph_reader_kwargs["driver_factory"] = graph_driver_factory
                graph_reader = open_scoped_neo4j_reader(
                    config.graph.reader_binding,
                    **graph_reader_kwargs,
                )
            except (ReadOnlyNeo4jError, TypeError, ValueError) as exc:
                raise CloudRuntimeDependencyError(
                    "scoped Neo4j runtime binding failed"
                ) from exc
            cleanup.callback(graph_reader.close)

            local = config.local_vector
            contract = ReadOnlyVectorContract(
                approved_data_parent=config.active_root,
                data_root=config.active_root / str(local["data_root"]),
                data_release_id=str(local["data_release_id"]),
                authority_manifest_sha256=str(
                    local["authority_manifest_sha256"]
                ),
                chunking_identity_sha256=str(local["chunking_identity_sha256"]),
                embedding_identity_sha256=str(local["embedding_identity_sha256"]),
                dimension=int(local["dimension"]),
                metric=str(local["metric"]),
                schema_version=str(local["schema_version"]),
                chunk_index_name=str(local["chunk_index_name"]),
                entity_index_name=str(local["entity_index_name"]),
                top_k_max=int(local["top_k_max"]),
                max_vectors_per_index=int(local["max_vectors_per_index"]),
                metadata_allowlist=local["metadata_allowlist"],
                engine=str(local["engine"]),
                engine_version=str(local["engine_version"]),
            )
            vector_manifest_path = (
                contract.active_release_dir / "local_vector_manifest.json"
            )
            _active_file(
                config.active_root,
                vector_manifest_path.relative_to(config.active_root).as_posix(),
                "local vector manifest",
            )
            vector_manifest = _load_bound_json(
                vector_manifest_path,
                str(local["manifest_sha256"]),
                "local vector manifest",
            )
            _validate_vector_coverage(
                vector_manifest, authority_ids, set(graph_package.entity_ids)
            )
            try:
                vector_view = ReadOnlyVectorReader(contract).open_active(
                    expected_manifest_sha256=str(local["manifest_sha256"])
                )
            except (OSError, ValueError, ReadOnlyVectorError) as exc:
                raise CloudRuntimeIntegrityError(
                    "active local vector release failed read-only validation"
                ) from exc
            cleanup.callback(vector_view.close)
            vector_index = ReadOnlyLocalVectorIndex(vector_view, authority_store)
            try:
                authority_store.verify_unchanged()
            except ReadOnlySQLiteError as exc:
                raise CloudRuntimeIntegrityError(
                    "authority database changed during runtime open"
                ) from exc
            try:
                bm25_index.verify_unchanged()
            except ReadOnlySQLiteError as exc:
                raise CloudRuntimeIntegrityError(
                    "BM25 database changed during runtime open"
                ) from exc
            runtime = cls(
                config,
                authority_store,
                bm25_index,
                vector_index,
                vector_view,
                graph_reader,
                graph_package.entities,
                regulation_governance,
                regulation_timeline,
                superseded_passages,
            )
            cleanup.pop_all()
            return runtime

    @property
    def answer_policy_version(self) -> str:
        return "provider-neutral:" + self.config.server_answer.identity_sha256

    @property
    def embedding_mode(self) -> str:
        return EMBEDDING_MODE

    def bind_provider_adapters(
        self,
        *,
        embedding_adapter: QueryEmbeddingClient,
        answer_coordinator: ServerAnswerCoordinator,
    ) -> None:
        self._require_open()
        if not isinstance(embedding_adapter, QueryEmbeddingClient):
            raise TypeError("embedding_adapter must be a QueryEmbeddingClient")
        if not isinstance(answer_coordinator, ServerAnswerCoordinator):
            raise TypeError("answer_coordinator must be a ServerAnswerCoordinator")
        if embedding_adapter.identity.sha256 != self.config.embedding_identity_sha256:
            raise CloudRuntimeDependencyError("embedding adapter identity mismatch")
        if embedding_adapter.policy.sha256 != self.config.embedding_policy_sha256:
            raise CloudRuntimeDependencyError("embedding adapter policy mismatch")
        expected = self.config.server_answer
        actual_channels = tuple(
            (adapter.channel.channel_id, adapter.channel.identity_sha256)
            for adapter in answer_coordinator.adapters
        )
        configured_channels = tuple(
            (item.channel_id, item.identity_sha256) for item in expected.ordered_channels
        )
        actual_policy = answer_coordinator.policy
        if actual_channels != configured_channels or (
            actual_policy.strategy,
            actual_policy.winner_policy,
            float(actual_policy.total_budget_seconds),
            actual_policy.total_cost_budget_microunits,
            actual_policy.circuit_breaker_failure_threshold,
            float(actual_policy.circuit_breaker_cooldown_seconds),
        ) != (
            expected.strategy,
            expected.winner_policy,
            expected.total_budget_seconds,
            expected.total_cost_budget_microunits,
            expected.circuit_breaker_failure_threshold,
            expected.circuit_breaker_cooldown_seconds,
        ):
            raise CloudRuntimeDependencyError("answer coordinator policy mismatch")
        with self._dependency_lock:
            if self._embedding_adapter is not None or self._answer_coordinator is not None:
                raise CloudRuntimeDependencyError("provider adapters are already bound")
            self._embedding_adapter = embedding_adapter
            self._answer_coordinator = answer_coordinator

    def bind_query_embedding_adapter(
        self, embedding_adapter: QueryEmbeddingClient
    ) -> None:
        """Bind the frozen query embedding while server answers remain fail-closed."""

        self._require_open()
        if not isinstance(embedding_adapter, QueryEmbeddingClient):
            raise TypeError("embedding_adapter must be a QueryEmbeddingClient")
        if embedding_adapter.identity.sha256 != self.config.embedding_identity_sha256:
            raise CloudRuntimeDependencyError("embedding adapter identity mismatch")
        if embedding_adapter.policy.sha256 != self.config.embedding_policy_sha256:
            raise CloudRuntimeDependencyError("embedding adapter policy mismatch")
        with self._dependency_lock:
            if self._embedding_adapter is not None or self._answer_coordinator is not None:
                raise CloudRuntimeDependencyError("provider adapters are already bound")
            self._embedding_adapter = embedding_adapter

    def embed_query(self, text: str) -> list[float]:
        self._require_open()
        adapter = self._embedding_adapter
        if adapter is None:
            raise CloudRuntimeDependencyError("embedding adapter is not bound")
        normalized = _required_text(text, "embedding query")
        object_id = "query:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        input_units = adapter.measure_input_units(normalized)
        result = adapter.embed_query(
            QueryEmbeddingInput(object_id, normalized, input_units)
        )
        if result.identity_sha256 != self.config.embedding_identity_sha256:
            raise CloudRuntimeIntegrityError("query embedding identity drift")
        if result.object_id != object_id:
            raise CloudRuntimeIntegrityError("query embedding response coverage mismatch")
        return list(result.vector)

    def _sealed_graph_entity(
        self, entity: Mapping[str, Any]
    ) -> tuple[str, str, str, list[str]]:
        if not isinstance(entity, Mapping):
            raise CloudRuntimeIntegrityError("scoped Neo4j returned an invalid entity")
        entity_id = str(entity.get("entity_id") or "")
        canonical_name = str(entity.get("canonical_name") or "")
        entity_type = str(entity.get("entity_type") or "")
        evidence_raw = entity.get("evidence_chunk_ids")
        if not isinstance(evidence_raw, list):
            raise CloudRuntimeIntegrityError("scoped Neo4j returned invalid evidence")
        evidence_ids = [str(value) for value in evidence_raw]
        expected = self._graph_entities.get(entity_id)
        if (
            expected is None
            or canonical_name != expected["canonical_name"]
            or entity_type != expected["entity_type"]
            or frozenset(evidence_ids) != expected["evidence_chunk_ids"]
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            raise CloudRuntimeIntegrityError(
                "scoped Neo4j entity does not match the sealed graph"
            )
        return entity_id, canonical_name, entity_type, sorted(evidence_ids)

    def search_entity_evidence(
        self, embedding: Sequence[float], *, limit: int
    ) -> list[dict[str, Any]]:
        self._require_open()
        hits = self._vector_view.query_entity(embedding, top_k=limit)
        hit_ids = [hit.object_id for hit in hits]
        try:
            entities = self._graph_reader.entities_by_ids(hit_ids, limit=limit)
        except ReadOnlyNeo4jError as exc:
            raise CloudRuntimeDependencyError(
                "scoped Neo4j fixed read is unavailable"
            ) from exc
        entity_by_id = {str(item["entity_id"]): item for item in entities}
        if set(entity_by_id) != set(hit_ids):
            raise CloudRuntimeIntegrityError(
                "entity vector ids do not resolve through scoped Neo4j"
            )
        results: list[dict[str, Any]] = []
        for hit in hits:
            entity = entity_by_id[hit.object_id]
            entity_id, canonical_name, entity_type, evidence_ids = (
                self._sealed_graph_entity(entity)
            )
            if entity_id != hit.object_id:
                raise CloudRuntimeIntegrityError(
                    "entity vector id does not match the sealed graph"
                )
            evidence = self.authority_store.require_chunks(evidence_ids)
            results.append(
                {
                    "name": canonical_name,
                    "type": entity_type,
                    "description": "",
                    "source_doc": evidence[0]["doc_name"] if evidence else "",
                    "source_chunk_ids": evidence_ids,
                    "semantic_key": hit.object_id,
                    "entity_id": hit.object_id,
                    "review_status": "approved",
                    "conflict_status": "none",
                    "evidence_governance_status": "sqlite-bound",
                    "score": ReadOnlyLocalVectorIndex._score(hit.distance),
                }
            )
        return results

    def recall_scoped_graph(
        self,
        *,
        query: str,
        entities: Sequence[Mapping[str, Any]],
        keywords: Sequence[str],
        limit: int = 20,
    ) -> dict[str, Any]:
        """Recall only sealed scoped-graph entities and SQLite-bound evidence."""
        self._require_open()
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("scoped graph limit must be between 1 and 100")
        query_text = str(query or "").strip().casefold()
        terms = [
            str(item.get("name") or "").strip().casefold()
            for item in entities
            if isinstance(item, Mapping) and str(item.get("name") or "").strip()
        ]
        terms.extend(str(item).strip().casefold() for item in keywords if str(item).strip())
        if query_text:
            terms.insert(0, query_text)
        ordered_terms = list(dict.fromkeys(item for item in terms if item))
        try:
            selected = self._graph_reader.entities_by_terms(
                ordered_terms, limit=limit
            )
        except ReadOnlyNeo4jError as exc:
            raise CloudRuntimeDependencyError(
                "scoped Neo4j fixed read is unavailable"
            ) from exc
        expected_ids = [
            entity_id
            for entity_id, item in sorted(
                self._graph_entities.items(),
                key=lambda pair: (
                    -len(str(pair[1]["canonical_name"])),
                    str(pair[1]["canonical_name"]),
                    pair[0],
                ),
            )
            if any(
                str(item["canonical_name"]).lower() == term
                or term in str(item["canonical_name"]).lower()
                or str(item["canonical_name"]).lower() in term
                for term in ordered_terms
            )
        ][:limit]
        if [str(item["entity_id"]) for item in selected] != expected_ids:
            raise CloudRuntimeIntegrityError(
                "scoped Neo4j term lookup does not match the sealed graph"
            )
        return self._scoped_graph_result(selected)

    def augment_scoped_graph_from_chunks(
        self,
        graph_result: Mapping[str, Any],
        chunk_ids: Sequence[str],
    ) -> dict[str, Any]:
        """Bind retrieved chunks back to the sealed graph without a live graph query."""
        self._require_open()
        approved_ids = list(dict.fromkeys(str(item) for item in chunk_ids if str(item)))
        self.authority_store.require_chunks(approved_ids)
        approved = set(approved_ids)
        try:
            selected = self._graph_reader.entities_by_chunk_ids(
                approved_ids,
                limit=min(100, self.config.graph.max_records),
            )
        except ReadOnlyNeo4jError as exc:
            raise CloudRuntimeDependencyError(
                "scoped Neo4j fixed read is unavailable"
            ) from exc
        selected_limit = min(100, self.config.graph.max_records)
        expected_ids = [
            entity_id
            for entity_id, item in sorted(self._graph_entities.items())
            if approved.intersection(item["evidence_chunk_ids"])
        ][:selected_limit]
        if [str(item["entity_id"]) for item in selected] != expected_ids:
            raise CloudRuntimeIntegrityError(
                "scoped Neo4j chunk lookup does not match the sealed graph"
            )
        if any(
            not approved.intersection(
                str(value) for value in item["evidence_chunk_ids"]
            )
            for item in selected
        ):
            raise CloudRuntimeIntegrityError(
                "scoped Neo4j chunk lookup returned an unrelated entity"
            )
        supplemental = self._scoped_graph_result(selected)
        merged = {
            "chunk_ids": list(
                dict.fromkeys(
                    [
                        *[str(item) for item in graph_result.get("chunk_ids", []) if str(item)],
                        *supplemental["chunk_ids"],
                    ]
                )
            ),
            "paths": _merge_records(
                graph_result.get("paths", []), supplemental["paths"], "path_id"
            ),
            "matched_entities": _merge_records(
                graph_result.get("matched_entities", []),
                supplemental["matched_entities"],
                "entity_id",
            ),
            "evidence_bindings": _merge_records(
                graph_result.get("evidence_bindings", []),
                supplemental["evidence_bindings"],
                "binding_id",
            ),
        }
        merged["total"] = len(merged["chunk_ids"])
        return merged

    def exact_scoped_graph_bindings(
        self,
        bindings: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        self._require_open()
        selected = [
            dict(item)
            for item in bindings
            if isinstance(item, Mapping)
            and SCOPED_GRAPH_EVIDENCE_ORIGIN
            in [str(value) for value in item.get("evidence_origins", [])]
            and str(item.get("chunk_id") or "")
        ]
        self.authority_store.require_chunks(
            [str(item["chunk_id"]) for item in selected]
        )
        return selected

    def prompt_scoped_graph_evidence(
        self, graph_result: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        self._require_open()
        bindings = self.exact_scoped_graph_bindings(
            graph_result.get("evidence_bindings", [])
        )
        bound_ids = {str(item["chunk_id"]) for item in bindings}
        paths = [
            dict(item)
            for item in graph_result.get("paths", [])
            if isinstance(item, Mapping)
            and bound_ids.intersection(
                str(value) for value in item.get("evidence_chunk_ids", [])
            )
        ]
        matched_entities = [
            dict(item)
            for item in graph_result.get("matched_entities", [])
            if isinstance(item, Mapping)
            and bound_ids.intersection(
                str(value) for value in item.get("source_chunk_ids", [])
            )
        ]
        return paths, matched_entities

    def _scoped_graph_result(
        self, selected: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        chunk_ids: list[str] = []
        paths: list[dict[str, Any]] = []
        matched_entities: list[dict[str, Any]] = []
        bindings: list[dict[str, Any]] = []
        for entity in selected:
            entity_id, name, entity_type, evidence_ids = self._sealed_graph_entity(entity)
            self.authority_store.require_chunks(evidence_ids)
            chunk_ids.extend(evidence_ids)
            matched_entities.append(
                {
                    "entity_id": entity_id,
                    "name": name,
                    "type": entity_type,
                    "source_chunk_ids": evidence_ids,
                    "matched_chunk_ids": evidence_ids,
                    "match_mode": "exact_scoped_graph",
                    "match_origin": "scoped_graph_manifest",
                    "review_status": "approved",
                    "conflict_status": "none",
                    "evidence_governance_status": "sqlite-bound",
                }
            )
            for chunk_id in evidence_ids:
                path_id = hashlib.sha256(
                    (entity_id + "\x00" + chunk_id).encode("utf-8")
                ).hexdigest()
                paths.append(
                    {
                        "path_id": path_id,
                        "path": f"{chunk_id} -[MENTIONS]-> {name}",
                        "relation": "MENTIONS",
                        "domain": entity_type,
                        "confidence": 1.0,
                        "relation_reason": "sealed scoped graph",
                        "evidence_chunk_ids": [chunk_id],
                        "source_chunk_ids": [chunk_id],
                        "nodes": [chunk_id, entity_id],
                    }
                )
                bindings.append(
                    {
                        "binding_id": path_id,
                        "chunk_id": chunk_id,
                        "entity_id": entity_id,
                        "evidence_origins": [SCOPED_GRAPH_EVIDENCE_ORIGIN],
                    }
                )
        unique_chunk_ids = list(dict.fromkeys(chunk_ids))
        return {
            "chunk_ids": unique_chunk_ids,
            "paths": paths,
            "matched_entities": matched_entities,
            "evidence_bindings": bindings,
            "total": len(unique_chunk_ids),
        }

    def coordinate_answer(
        self,
        *,
        request_id: str,
        question: str,
        sources: Sequence[Mapping[str, Any]],
    ) -> CoordinatorResult:
        self._require_open()
        coordinator = self._answer_coordinator
        if coordinator is None:
            raise CloudRuntimeDependencyError("server answer coordinator is not bound")
        eligible_sources = [
            source
            for source in sources
            if not str(source.get("doc_name") or "").replace("_", "/", 1).startswith(
                ("理论题库/", "实操题库/", "题库/")
            )
        ]
        source_ids = [
            str(source.get("chunk_id") or "") for source in eligible_sources
        ]
        source_ids = [item for item in source_ids if item]
        rows = self.authority_store.require_chunks(source_ids)
        row_by_id = {str(row["chunk_id"]): row for row in rows}
        maximum_input = min(
            adapter.channel.max_input_units for adapter in coordinator.adapters
        )
        evidence: list[dict[str, str]] = []
        seen: set[str] = set()
        for position, source in enumerate(eligible_sources, start=1):
            chunk_id = str(source.get("chunk_id") or "")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            row = row_by_id[chunk_id]
            text = str(row["text"])
            alias = f"S{source.get('seq') or position}"
            evidence.append({"evidence_id": alias, "text": text})
        if not evidence:
            raise CloudRuntimeDependencyError(
                "selected SQLite evidence exceeds the approved model input budget"
            )
        request_question = ""
        input_units = 0
        while evidence:
            instruction_sources = [
                {"seq": item["evidence_id"].removeprefix("S")}
                for item in evidence
            ]
            evidence_prompt = "\n\nSelected evidence:\n" + "\n\n".join(
                f'[{item["evidence_id"]}] {item["text"]}' for item in evidence
            )
            request_question = (
                "User question (answer in Chinese):\n"
                + question
                + "\n\nUse only the selected evidence supplied with this request. "
                "Do not add model knowledge, public information, unsupported numbers, "
                "or internal source aliases to the user-visible answer. "
                "If evidence is insufficient, state that limitation without inventing facts. "
                "Question-bank material is reserved for the deterministic exact-question "
                "path and must not be used by this coordinator."
                + authority_priority_rule()
                + build_claim_map_instruction(instruction_sources)
                + evidence_prompt
            )
            input_units = len(request_question) + sum(
                len(item["text"]) for item in evidence
            )
            if input_units <= maximum_input:
                break
            evidence.pop()
        if not evidence:
            raise CloudRuntimeDependencyError(
                "selected SQLite evidence exceeds the approved model input budget"
            )
        return coordinator.coordinate(
            ServerAnswerRequest(
                request_id=request_id,
                question=request_question,
                evidence=tuple(evidence),
                input_units=input_units,
            )
        )

    def answer_telemetry(
        self,
        *,
        outcome: CoordinatorResult | ServerAnswerUnavailable | None,
        selected_channel_id: str | None,
        latency_ms: int,
        recovery_status: str,
        extractive_fallback_used: bool,
        extractive_fallback_recovered: bool,
        extractive_policy_version: str,
        answer_method: str,
        answer_status: str,
    ) -> dict[str, Any]:
        ledger = tuple(getattr(outcome, "ledger", ()) or ())
        attempts = [
            {
                "channel_id": entry.channel_id,
                "channel_identity_sha256": entry.channel_identity_sha256,
                "status": entry.status,
                "timeout_ms": entry.timeout_ms,
                "latency_ms": entry.latency_ms,
                "request_sha256": entry.request_sha256,
                "response_sha256": entry.response_sha256,
                "accounted_cost_microunits": entry.accounted_cost_microunits,
                "cost_basis": entry.cost_basis,
                "disclosed": entry.disclosed,
            }
            for entry in ledger
        ]
        first_id = self.config.server_answer.ordered_channels[0].channel_id
        first = next((item for item in attempts if item["channel_id"] == first_id), None)
        fallback_attempts = [
            item for item in attempts if item["channel_id"] != first_id
        ]
        primary_status = _telemetry_status(first)
        fallback_succeeded = bool(
            selected_channel_id and selected_channel_id != first_id
        )
        fallback_attempted = any(item["disclosed"] for item in fallback_attempts)
        fallback_status = (
            "succeeded"
            if fallback_succeeded
            else "failed"
            if fallback_attempted
            else "not_attempted"
        )
        skipped = list(getattr(outcome, "skipped_channel_ids", ()) or ())
        coordinator_payload = {
            "schema_version": getattr(outcome, "schema_version", None),
            "strategy": self.config.server_answer.strategy,
            "winner_policy": self.config.server_answer.winner_policy,
            "winner_channel_id": selected_channel_id,
            "ledger": attempts,
            "skipped_channel_ids": skipped,
        }
        return {
            "schema_version": ANSWER_TELEMETRY_SCHEMA_VERSION,
            "policy_version": self.answer_policy_version,
            "selected_model": selected_channel_id,
            "selected_channel_id": selected_channel_id,
            "attempts": attempts,
            "latency_ms": max(0, int(latency_ms)),
            "primary_status": primary_status,
            "primary_failed": first is not None and primary_status != "succeeded",
            "primary_timed_out": primary_status == "timed_out",
            "model_fallback_status": fallback_status,
            "model_fallback_attempted": fallback_attempted,
            "model_fallback_succeeded": fallback_succeeded,
            "extractive_fallback_policy_version": extractive_policy_version,
            "extractive_fallback_used": bool(extractive_fallback_used),
            "extractive_fallback_recovered": bool(extractive_fallback_recovered),
            "fallback_recovered_answer": (
                recovery_status
                in {"model_fallback_succeeded", "extractive_fallback_succeeded"}
                and answer_status == "recovered"
            ),
            "unrecovered_model_failure": recovery_status
            in {"unrecovered", "pipeline_error"},
            "answer_method": answer_method,
            "answer_status": answer_status,
            "recovery_status": recovery_status,
            "coordinator": coordinator_payload,
        }


def _telemetry_status(item: Mapping[str, Any] | None) -> str:
    if item is None:
        return "not_attempted"
    status = str(item.get("status") or "")
    if status == "succeeded":
        return "succeeded"
    if "timed_out" in status or "deadline" in status:
        return "timed_out"
    return "failed"


def _require_hash(path: Path, expected: str, field: str) -> None:
    if _sha256_file(path) != expected:
        raise CloudRuntimeIntegrityError(f"{field} hash mismatch")


def _validate_authority_manifest(
    manifest: Mapping[str, Any],
    database_path: Path,
    binding: ArtifactBinding,
) -> None:
    database = manifest.get("database")
    counts = manifest.get("counts")
    build = manifest.get("build")
    sources = manifest.get("sources")
    authority = manifest.get("authority")
    expected_root_fields = {
        "authority",
        "build",
        "counts",
        "database",
        "release_id",
        "schema_version",
        "source_scope",
        "sources",
        "status",
    }
    if (
        set(manifest) != expected_root_fields
        or
        manifest.get("schema_version") != "cloud-rag-authority-v1"
        or manifest.get("status") not in {"candidate", "active"}
        or manifest.get("source_scope") != dict(FROZEN_R9_SOURCE_SCOPE)
        or authority != {"owner": "rag_chunks.db", "join_key": "chunk_id"}
        or not isinstance(database, Mapping)
        or set(database)
        != {
            "path",
            "sha256",
            "mode",
            "sqlite_user_version",
            "integrity_check",
            "foreign_key_violation_count",
        }
        or not isinstance(counts, Mapping)
        or set(counts) != {"documents", "chunks", "provenance"}
        or counts.get("documents") != FROZEN_R9_SOURCE_SCOPE["source_count"]
        or isinstance(counts.get("chunks"), bool)
        or not isinstance(counts.get("chunks"), int)
        or counts.get("chunks", 0) <= 0
        or counts.get("chunks") != counts.get("provenance")
        or not isinstance(build, Mapping)
        or set(build)
        != {
            "extractor_version",
            "chunking_policy",
            "import_run_id",
            "network_calls",
            "old_authority_reused",
            "ocr_runtime",
        }
        or build.get("chunking_policy") != "cloud-v2-paragraph-1200-v1"
        or build.get("extractor_version") != "cloud-v2-source-extractor-v1"
        or isinstance(build.get("network_calls"), bool)
        or not isinstance(build.get("network_calls"), int)
        or build.get("network_calls") != 0
        or build.get("old_authority_reused") is not False
        or database.get("path") != database_path.name
        or database.get("sha256") != binding.data_sha256
        or database.get("mode") != "0600"
        or isinstance(database.get("sqlite_user_version"), bool)
        or not isinstance(database.get("sqlite_user_version"), int)
        or database.get("sqlite_user_version") != 1
        or database.get("integrity_check") != "ok"
        or isinstance(database.get("foreign_key_violation_count"), bool)
        or not isinstance(database.get("foreign_key_violation_count"), int)
        or database.get("foreign_key_violation_count") != 0
        or not isinstance(sources, list)
        or len(sources) != FROZEN_R9_SOURCE_SCOPE["source_count"]
        or manifest.get("release_id")
        != f"rag-authority:revision-a-r9:{binding.data_sha256[:16]}"
    ):
        raise CloudRuntimeIntegrityError("authority manifest binding mismatch")
    expected_source_fields = {
        "relative_path",
        "source_sha256",
        "extracted_text_sha256",
        "page_count",
        "chunk_count",
    }
    paths: list[str] = []
    source_chunk_count = 0
    for item in sources:
        if not isinstance(item, Mapping) or set(item) != expected_source_fields:
            raise CloudRuntimeIntegrityError("authority source record shape mismatch")
        relative_path = str(item.get("relative_path") or "")
        if (
            not relative_path
            or relative_path.startswith("/")
            or "\\" in relative_path
            or any(part in {"", ".", ".."} for part in PurePosixPath(relative_path).parts)
            or not _SHA256.fullmatch(str(item.get("source_sha256") or ""))
            or not _SHA256.fullmatch(str(item.get("extracted_text_sha256") or ""))
            or isinstance(item.get("page_count"), bool)
            or not isinstance(item.get("page_count"), int)
            or item.get("page_count", 0) <= 0
            or isinstance(item.get("chunk_count"), bool)
            or not isinstance(item.get("chunk_count"), int)
            or item.get("chunk_count", 0) <= 0
        ):
            raise CloudRuntimeIntegrityError("authority source record is invalid")
        paths.append(relative_path)
        source_chunk_count += int(item["chunk_count"])
    if len(paths) != len(set(paths)) or source_chunk_count != counts["chunks"]:
        raise CloudRuntimeIntegrityError("authority source coverage mismatch")


def _validate_authority_database(
    store: ReadOnlyAuthorityStore, manifest: Mapping[str, Any]
) -> dict[str, str]:
    try:
        if store.user_version() != (manifest.get("database") or {}).get(
            "sqlite_user_version"
        ):
            raise CloudRuntimeIntegrityError("authority SQLite user version mismatch")
        if store.integrity_check() != "ok":
            raise CloudRuntimeIntegrityError("authority SQLite integrity check failed")
        if store.foreign_key_violation_count() != 0:
            raise CloudRuntimeIntegrityError("authority SQLite foreign-key check failed")
        if store.schema_records() != EXPECTED_AUTHORITY_SCHEMA_RECORDS:
            raise CloudRuntimeIntegrityError("authority SQLite schema mismatch")
        chunk_rows = store.all_chunks()
        chunk_documents = store.chunk_document_map()
        provenance_ids = set(store.provenance_chunk_ids())
        source_rows = store.source_records()
        document_rows = store.document_chunk_counts()
    except ReadOnlySQLiteError as exc:
        raise CloudRuntimeIntegrityError("authority SQLite fixed read failed") from exc
    ids = {str(row["chunk_id"]) for row in chunk_rows}
    row_chunk_documents = {
        str(row["chunk_id"]): str(row["doc_name"]) for row in chunk_rows
    }
    expected_count = (manifest.get("counts") or {}).get("chunks")
    if (
        not ids
        or len(ids) != len(chunk_rows)
        or any(
            not re.fullmatch(r"chunk:[0-9a-f]{40}", str(row["chunk_id"]))
            for row in chunk_rows
        )
        or ids != provenance_ids
        or len(chunk_documents) != len(chunk_rows)
        or chunk_documents != row_chunk_documents
        or expected_count != len(ids)
    ):
        raise CloudRuntimeIntegrityError("authority SQLite coverage mismatch")

    manifest_sources = {
        str(item["relative_path"]): item for item in manifest.get("sources", [])
    }
    if (
        len(source_rows) != FROZEN_R9_SOURCE_SCOPE["source_count"]
        or len(document_rows) != FROZEN_R9_SOURCE_SCOPE["source_count"]
        or set(document_rows) != set(manifest_sources)
    ):
        raise CloudRuntimeIntegrityError("authority document coverage mismatch")
    dispositions = {
        "unchanged-from-original-stop-a": 0,
        "approved-redacted-copy": 0,
    }
    actual_document_counts: dict[str, int] = {}
    for doc_name in chunk_documents.values():
        actual_document_counts[doc_name] = (
            actual_document_counts.get(doc_name, 0) + 1
        )
    build = manifest["build"]
    for row in source_rows:
        doc_name = str(row["doc_name"])
        declared = manifest_sources.get(doc_name)
        try:
            metadata = json.loads(
                str(row["metadata_json"]),
                object_pairs_hook=lambda pairs: _strict_pairs(
                    pairs, "authority document metadata"
                ),
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    CloudRuntimeIntegrityError(
                        "authority document metadata contains a non-finite value"
                    )
                ),
            )
        except CloudRuntimeIntegrityError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CloudRuntimeIntegrityError(
                "authority document metadata is invalid"
            ) from exc
        if (
            declared is None
            or not isinstance(metadata, Mapping)
            or set(metadata)
            != {"byte_disposition", "chunking_policy", "source_relative_path_sha256"}
            or str(row["source_path"]).startswith("kb://knowledge_base/") is False
            or str(row["source_sha256"]) != declared["source_sha256"]
            or isinstance(row["source_page_count"], bool)
            or not isinstance(row["source_page_count"], int)
            or row["source_page_count"] != declared["page_count"]
            or str(row["authority"]) != "rag_chunks.db"
            or not (
                str(row["extractor_version"]) == str(build["extractor_version"])
                or str(row["extractor_version"]).startswith(
                    str(build["extractor_version"]) + ":"
                )
            )
            or str(row["import_run_id"]) != build["import_run_id"]
            or metadata.get("chunking_policy") != build["chunking_policy"]
            or metadata.get("source_relative_path_sha256")
            != hashlib.sha256(doc_name.encode("utf-8")).hexdigest()
            or document_rows[doc_name] != declared["chunk_count"]
            or actual_document_counts.get(doc_name) != declared["chunk_count"]
        ):
            raise CloudRuntimeIntegrityError("authority document identity mismatch")
        disposition = str(metadata.get("byte_disposition") or "")
        if disposition not in dispositions:
            raise CloudRuntimeIntegrityError("authority byte disposition is invalid")
        dispositions[disposition] += 1
    if dispositions != {
        "unchanged-from-original-stop-a": 28,
        "approved-redacted-copy": 7,
    }:
        raise CloudRuntimeIntegrityError("authority 28/7 disposition mismatch")
    return chunk_documents


def _validate_bm25(
    manifest: Mapping[str, Any],
    database_path: Path,
    binding: ArtifactBinding,
    authority_manifest: Mapping[str, Any],
    authority_ids: set[str],
    authority_store: ReadOnlyAuthorityStore,
    index_reader: ReadOnlyFtsIndex,
) -> None:
    index = manifest.get("index")
    source = manifest.get("source")
    root_fields = {
        "authority_database_sha256",
        "authority_release_id",
        "index",
        "indexed_chunk_count",
        "minimum_effective_query_codepoints",
        "schema_version",
        "short_query_fallback",
        "source",
        "sqlite_backfill_required",
        "status",
        "tokenizer",
    }
    source_fields = {
        "chunk_count",
        "document_count",
        "fingerprint",
        "fingerprint_algorithm",
        "schema_version",
        "text_byte_count",
        "text_codepoint_count",
    }
    integer_fields = (
        manifest.get("indexed_chunk_count"),
        manifest.get("minimum_effective_query_codepoints"),
        source.get("chunk_count") if isinstance(source, Mapping) else None,
        source.get("document_count") if isinstance(source, Mapping) else None,
        source.get("text_byte_count") if isinstance(source, Mapping) else None,
        source.get("text_codepoint_count") if isinstance(source, Mapping) else None,
    )
    if (
        set(manifest) != root_fields
        or not isinstance(index, Mapping)
        or set(index) != {"path", "sha256"}
        or not isinstance(source, Mapping)
        or set(source) != source_fields
        or any(isinstance(value, bool) or not isinstance(value, int) for value in integer_fields)
        or manifest.get("schema_version") != "cloud-v2-sqlite-fts5-trigram-v1"
        or manifest.get("status") not in {"candidate", "active"}
        or manifest.get("authority_release_id") != authority_manifest.get("release_id")
        or manifest.get("authority_database_sha256")
        != (authority_manifest.get("database") or {}).get("sha256")
        or index.get("path") != database_path.name
        or index.get("sha256") != binding.data_sha256
        or manifest.get("indexed_chunk_count") != len(authority_ids)
        or manifest.get("sqlite_backfill_required") is not True
        or manifest.get("tokenizer") != "trigram"
        or manifest.get("minimum_effective_query_codepoints") != 3
        or manifest.get("short_query_fallback")
        != "authority-sqlite-substring-v1"
    ):
        raise CloudRuntimeIntegrityError("BM25 manifest binding mismatch")
    try:
        if (
            index_reader.integrity_check() != "ok"
            or index_reader.user_version() != 0
            or index_reader.foreign_key_violation_count() != 0
            or index_reader.schema_records() != EXPECTED_BM25_SCHEMA_RECORDS
        ):
            raise CloudRuntimeIntegrityError("BM25 SQLite schema mismatch")
        authority_rows = authority_store.all_chunks()
    except ReadOnlySQLiteError as exc:
        raise CloudRuntimeIntegrityError("authority SQLite fixed read failed") from exc
    expected_source = _canonical_source_fingerprint(authority_rows)
    if manifest.get("source") != expected_source:
        raise CloudRuntimeIntegrityError("BM25 source fingerprint mismatch")
    authority_by_id = {
        str(row["chunk_id"]): (str(row["text"]), str(row["doc_name"]))
        for row in authority_rows
    }
    try:
        bm25_rows = index_reader.all_rows()
    except ReadOnlySQLiteError as exc:
        raise CloudRuntimeIntegrityError("BM25 SQLite fixed read failed") from exc
    bm25_by_id = {
        str(row["chunk_id"]): (str(row["text"]), str(row["doc_name"]))
        for row in bm25_rows
    }
    if (
        len(bm25_rows) != len(authority_rows)
        or set(bm25_by_id) != authority_ids
        or bm25_by_id != authority_by_id
    ):
        raise CloudRuntimeIntegrityError(
            "BM25 rows do not exactly mirror SQLite authority"
        )


def _validate_graph(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    authority_manifest: Mapping[str, Any],
    authority_chunk_documents: Mapping[str, str],
    binding: GraphBinding,
) -> ScopedGraphPackage:
    graph = manifest.get("graph")
    if (
        manifest.get("schema_version") != "cloud-scoped-graph-v1"
        or manifest.get("status") not in {"candidate", "active"}
        or manifest.get("release_id") != binding.release_id
        or manifest.get("authority_release_id") != authority_manifest.get("release_id")
        or manifest.get("authority_database_sha256")
        != (authority_manifest.get("database") or {}).get("sha256")
        or not isinstance(graph, Mapping)
    ):
        raise CloudRuntimeIntegrityError("scoped graph manifest binding mismatch")
    graph_name = graph.get("path")
    if not isinstance(graph_name, str) or Path(graph_name).name != graph_name:
        raise CloudRuntimeIntegrityError("scoped graph data path is invalid")
    graph_path = manifest_path.parent / graph_name
    if (
        graph_path.resolve(strict=True) != graph_path
        or not graph_path.is_file()
        or graph_path.is_symlink()
        or graph_path.stat().st_mode & _WRITE_BITS
        or _sha256_file(graph_path) != graph.get("sha256")
    ):
        raise CloudRuntimeIntegrityError("scoped graph data binding mismatch")
    try:
        package = load_scoped_graph_package(
            manifest_path,
            authority_chunk_documents=authority_chunk_documents,
        )
    except ScopedGraphContractError as exc:
        raise CloudRuntimeIntegrityError(
            "scoped graph portable package is invalid"
        ) from exc
    if (
        package.manifest_sha256 != binding.manifest_sha256
        or package.graph_release_id != binding.release_id
    ):
        raise CloudRuntimeIntegrityError("scoped graph configured identity mismatch")
    return package


def _validate_vector_coverage(
    manifest: Mapping[str, Any], authority_ids: set[str], entity_ids: set[str]
) -> None:
    indexes = manifest.get("indexes")
    if not isinstance(indexes, Mapping):
        raise CloudRuntimeIntegrityError("local vector manifest is incomplete")
    actual: dict[str, set[str]] = {}
    for kind in ("chunk", "entity"):
        entry = indexes.get(kind)
        objects = entry.get("objects") if isinstance(entry, Mapping) else None
        if not isinstance(objects, list):
            raise CloudRuntimeIntegrityError("local vector object map is incomplete")
        ids = [str(item.get("object_id") or "") for item in objects if isinstance(item, Mapping)]
        if len(ids) != len(objects) or not all(ids) or len(ids) != len(set(ids)):
            raise CloudRuntimeIntegrityError("local vector object ids are invalid")
        actual[kind] = set(ids)
    if actual["chunk"] != authority_ids or actual["entity"] != entity_ids:
        raise CloudRuntimeIntegrityError(
            "local vector ids do not exactly cover authority and scoped graph"
        )


def recovery_status_after_finalizer(
    recovery_status: str, finalizer_outcome: str
) -> str:
    if finalizer_outcome == "blocked" and recovery_status in {
        "model_fallback_succeeded",
        "extractive_fallback_succeeded",
    }:
        return "unrecovered"
    return recovery_status


def load_cloud_runtime_from_environment() -> CloudRuntimeResources:
    configured = os.environ.get(CONFIG_ENVIRONMENT_VARIABLE, "").strip()
    if not configured:
        raise CloudRuntimeConfigError(
            f"{CONFIG_ENVIRONMENT_VARIABLE} must identify the explicit active runtime config"
        )
    expected_sha256 = os.environ.get(
        CONFIG_SHA256_ENVIRONMENT_VARIABLE,
        "",
    ).strip()
    if not expected_sha256:
        raise CloudRuntimeConfigError(
            f"{CONFIG_SHA256_ENVIRONMENT_VARIABLE} must identify the approved runtime config hash"
        )
    return CloudRuntimeResources.open(
        configured,
        expected_config_sha256=expected_sha256,
    )


__all__ = [
    "ANSWER_TELEMETRY_SCHEMA_VERSION",
    "AnswerCoordinationUnavailable",
    "CloudRuntimeConfig",
    "CloudRuntimeConfigError",
    "CloudRuntimeDependencyError",
    "CloudRuntimeIntegrityError",
    "CloudRuntimeResources",
    "CONFIG_ENVIRONMENT_VARIABLE",
    "CONFIG_SHA256_ENVIRONMENT_VARIABLE",
    "CONFIG_SCHEMA_VERSION",
    "ReadOnlyAuthorityStore",
    "ReadOnlyFtsIndex",
    "ReadOnlyLocalVectorIndex",
    "load_cloud_runtime_from_environment",
    "recovery_status_after_finalizer",
]
