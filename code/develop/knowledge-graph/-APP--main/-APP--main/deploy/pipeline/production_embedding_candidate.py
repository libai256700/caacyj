"""Build one sealed, candidate-only production embedding release.

The source sets are derived only from a hash-bound rag_chunks.db authority
manifest and a hash-bound scoped graph package. Callers cannot supply chunk or
entity coverage records. The CLI validates or builds one candidate and never
switches an active release.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from rag_store.embedding_adapter import (
    EmbeddingAdapter,
    EmbeddingError,
    EmbeddingIdentity,
    EmbeddingInput,
    EmbeddingLedgerEntry,
    EmbeddingPolicy,
)
from rag_store.local_vector_store import (
    CandidateBuildReceipt,
    LocalVectorContract,
    LocalVectorStoreAdapter,
    VectorRecord,
)
from rag_store.provider_http_transport import ProviderHTTPTransport
from rag_store.provider_meters import ProviderMeterError, resolve_meter
from rag_store.runtime_query_embedding import (
    QueryEmbeddingIdentity,
    QueryEmbeddingPolicy,
)
from rag_store.runtime_sqlite_reader import (
    ReadOnlyAuthorityReader,
    ReadOnlySQLiteError,
    SQLiteSemanticValidationError,
    inspect_authority_bm25_semantics,
    read_stable_regular_file,
)
from rag_store.scoped_graph_contract import (
    ScopedGraphContractError,
    ScopedGraphPackage,
    load_scoped_graph_package,
)
from rag_store.source_authority import FROZEN_R9_SOURCE_SCOPE

from .provider_bootstrap import (
    ProviderApprovalError,
    ProviderBootstrapError,
    ProviderRuntimeConfig,
    ProviderRuntimeConfigError,
    authorization_header,
    require_https_network_mode,
    resolve_secret,
    validate_production_approval,
)


CONFIG_SCHEMA_VERSION = "kg-production-embedding-candidate-config-v2"
AUTHORITY_SCHEMA_VERSION = "cloud-rag-authority-v1"
LOCAL_DATA_RELEASE_ID_SCHEMA_VERSION = "cloud-v2-local-data-release-id-v2"
BASE_PRODUCTION_VECTOR_BUILD_CONTRACT_SCHEMA_VERSION = (
    "cloud-v2-production-vector-build-contract-v1"
)
PRODUCTION_VECTOR_BUILD_CONTRACT_SCHEMA_VERSION = (
    "cloud-v2-production-vector-build-contract-v2"
)
PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256_ENV = (
    "KG_PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256"
)
BASE_SUITE_MANIFEST_SHA256_ENV = (
    "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
)
BASE_SUITE_MANIFEST_SCHEMA_VERSION = "cloud-v2-suite-manifest-v1"
BOOTSTRAP_CONTEXT_SCHEMA_VERSION = "kg-production-embedding-bootstrap-context-v1"
RUNTIME_LOCK_SHA256_ENV = "KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256"
BASE_SUITE_PENDING_CONTRACT_PATH = (
    "server-runtime/production-vector-build-contract.json"
)
LOCAL_VECTOR_SCHEMA_VERSION = "kg-local-vector-schema-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SAFE_AUTHORITY_RELEASE_ID = re.compile(
    r"^rag-authority:[A-Za-z0-9._-]+:[0-9a-f]{16}$"
)
_AUTHORITY_TABLES = frozenset(
    {"document_sources", "documents", "chunks", "chunk_provenance"}
)
_VECTOR_METADATA = {
    "chunk": ("authority_release_id", "content_type"),
    "entity": ("authority_release_id", "entity_type"),
}
_PRODUCTION_DATA_FILES = {
    "authority/authority-manifest.json": "authority-manifest",
    "authority/rag_chunks.db": "authority-sqlite",
    "derived/bm25-manifest.json": "bm25-manifest",
    "derived/bm25.sqlite3": "bm25-index",
    "derived/graph/graph-manifest.json": "graph-manifest",
    "derived/graph/scoped-graph.jsonl": "graph-data",
}
_REQUIRED_BUILDER_PATHS = (
    "deploy/cloud_v2/__init__.py",
    "deploy/cloud_v2/source_scope.py",
    "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
    "deploy/cloud_v2/stop_b_request.py",
    "deploy/pipeline/production_embedding_bootstrap.py",
    "deploy/pipeline/production_embedding_candidate.py",
    "deploy/pipeline/production_embedding_config.schema.json",
    "deploy/pipeline/production_embedding_runtime_lock.schema.json",
    "deploy/pipeline/provider_bootstrap.py",
    "deploy/pipeline/provider_runtime_config.schema.json",
    "deploy/rag_store/embedding_adapter.py",
    "deploy/rag_store/local_vector_store.py",
    "deploy/rag_store/provider_http_transport.py",
    "deploy/rag_store/provider_meters.py",
    "deploy/rag_store/provider_wire.py",
    "deploy/rag_store/runtime_query_embedding.py",
    "deploy/rag_store/runtime_sqlite_reader.py",
    "deploy/rag_store/scoped_graph_contract.py",
    "deploy/rag_store/server_answer_model.py",
    "deploy/rag_store/source_authority.py",
)
_BOOTSTRAP_CONTEXT_NONCE = object()
_FORBIDDEN_PATH_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
_BASE_SUITE_PHASE_STATE = {
    "stop_a": "approved",
    "stop_b": "pending",
    "stop_c": "pending",
    "stop_d": "pending",
    "real_provider_calls": 0,
    "commit_push_upload_deploy_authorized": False,
    "runtime_activation_authorized": False,
    "product_accepted": False,
}


@dataclass(frozen=True)
class _EmbeddingCandidateRecord:
    object_id: str
    text: str = field(repr=False)
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class _ActiveBootstrapContext:
    """In-process capability issued only after held-byte bootstrap validation."""

    identity: Mapping[str, str] = field(repr=False)
    verifier: Callable[[], Mapping[str, Any]] = field(repr=False)
    verifier_owner: object = field(repr=False)
    verifier_function: object = field(repr=False)
    action_closure: tuple[object, ...] = field(repr=False)
    loader: object = field(repr=False)
    held_source: object = field(repr=False)
    nonce: object = field(repr=False)


_ACTIVE_BOOTSTRAP_CONTEXT: _ActiveBootstrapContext | None = None


@dataclass(frozen=True)
class PurposeEmbeddingBinding:
    purpose: str
    identity_sha256: str
    policy_sha256: str


@dataclass(frozen=True)
class ProductionEmbeddingCandidateValidation:
    """Sanitized result of a complete no-network candidate preflight."""

    config_sha256: str
    provider_config_sha256: str
    production_vector_build_contract_sha256: str
    authority_release_id: str
    authority_manifest_sha256: str
    authority_database_sha256: str
    graph_release_id: str
    graph_manifest_sha256: str
    chunk_count: int
    entity_count: int
    candidate_release_dir: Path
    candidate_only: bool = True
    network_calls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority_database_sha256": self.authority_database_sha256,
            "authority_manifest_sha256": self.authority_manifest_sha256,
            "authority_release_id": self.authority_release_id,
            "candidate_only": self.candidate_only,
            "candidate_release_dir": str(self.candidate_release_dir),
            "chunk_count": self.chunk_count,
            "config_sha256": self.config_sha256,
            "entity_count": self.entity_count,
            "graph_manifest_sha256": self.graph_manifest_sha256,
            "graph_release_id": self.graph_release_id,
            "network_calls": self.network_calls,
            "provider_config_sha256": self.provider_config_sha256,
            "production_vector_build_contract_sha256": (
                self.production_vector_build_contract_sha256
            ),
        }


@dataclass(frozen=True)
class ProductionEmbeddingCandidateReceipt:
    """In-memory evidence for one complete candidate-only vector build."""

    local_vector: CandidateBuildReceipt
    purpose_bindings: tuple[PurposeEmbeddingBinding, ...]
    wire_contract_sha256: str
    provider_config_sha256: str
    provider_contract_sha256: str
    production_vector_build_contract_sha256: str
    config_sha256: str
    authority_release_id: str
    authority_manifest_sha256: str
    authority_database_sha256: str
    graph_release_id: str
    graph_manifest_sha256: str
    model: str
    model_version: str
    dimension: int
    normalization: str
    chunk_ledger: tuple[EmbeddingLedgerEntry, ...]
    entity_ledger: tuple[EmbeddingLedgerEntry, ...]
    candidate_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority_database_sha256": self.authority_database_sha256,
            "authority_manifest_sha256": self.authority_manifest_sha256,
            "authority_release_id": self.authority_release_id,
            "candidate_only": self.candidate_only,
            "chunk_ledger": _serialized_ledger(self.chunk_ledger),
            "chunk_count": self.local_vector.chunk_count,
            "config_sha256": self.config_sha256,
            "dimension": self.dimension,
            "entity_count": self.local_vector.entity_count,
            "entity_ledger": _serialized_ledger(self.entity_ledger),
            "graph_manifest_sha256": self.graph_manifest_sha256,
            "graph_release_id": self.graph_release_id,
            "local_vector_manifest_sha256": self.local_vector.manifest_sha256,
            "model": self.model,
            "model_version": self.model_version,
            "normalization": self.normalization,
            "provider_config_sha256": self.provider_config_sha256,
            "provider_contract_sha256": self.provider_contract_sha256,
            "production_vector_build_contract_sha256": (
                self.production_vector_build_contract_sha256
            ),
            "purpose_bindings": [
                {
                    "identity_sha256": item.identity_sha256,
                    "policy_sha256": item.policy_sha256,
                    "purpose": item.purpose,
                }
                for item in self.purpose_bindings
            ],
            "release_dir": str(self.local_vector.release_dir),
            "wire_contract_sha256": self.wire_contract_sha256,
        }


@dataclass(frozen=True)
class ProductionVectorContractMaterialization:
    """Sanitized identity for one suite-external configured contract."""

    contract_path: Path
    contract_sha256: str
    base_suite_manifest_sha256: str
    base_contract_sha256: str
    provider_config_sha256: str
    embedding_identity_sha256: str
    source_count: int
    candidate_only: bool = True
    network_calls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "base_contract_sha256": self.base_contract_sha256,
            "base_suite_manifest_sha256": self.base_suite_manifest_sha256,
            "candidate_only": self.candidate_only,
            "contract_path": str(self.contract_path),
            "contract_sha256": self.contract_sha256,
            "embedding_identity_sha256": self.embedding_identity_sha256,
            "network_calls": self.network_calls,
            "provider_config_sha256": self.provider_config_sha256,
            "source_count": self.source_count,
        }


class ProductionEmbeddingCandidateConfigError(RuntimeError):
    """Sanitized strict configuration failure."""

    def __init__(self, code: str) -> None:
        super().__init__("production embedding candidate config is invalid")
        self.code = code

    def __repr__(self) -> str:
        return f"ProductionEmbeddingCandidateConfigError(code={self.code!r})"


class ProductionEmbeddingCandidateError(RuntimeError):
    """Sanitized failure without provider text, payloads, or secrets."""

    def __init__(
        self,
        code: str,
        *,
        chunk_ledger: Sequence[EmbeddingLedgerEntry] = (),
        entity_ledger: Sequence[EmbeddingLedgerEntry] = (),
        emit_ledgers: bool = False,
    ) -> None:
        super().__init__("production embedding candidate build failed")
        self.code = code
        self.chunk_ledger = tuple(chunk_ledger)
        self.entity_ledger = tuple(entity_ledger)
        self.emit_ledgers = emit_ledgers

    def __repr__(self) -> str:
        return f"ProductionEmbeddingCandidateError(code={self.code!r})"

    def ledger_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "chunk_ledger": _serialized_ledger(self.chunk_ledger),
            "entity_ledger": _serialized_ledger(self.entity_ledger),
        }


def _serialized_ledger(
    entries: Sequence[EmbeddingLedgerEntry],
) -> list[dict[str, Any]]:
    """Return the complete provider-body-free accounting record."""

    return [
        {
            "accounted_cost_microunits": entry.accounted_cost_microunits,
            "attempt": entry.attempt,
            "batch_index": entry.batch_index,
            "cost_basis": entry.cost_basis,
            "latency_ms": entry.latency_ms,
            "purpose": entry.purpose,
            "request_sha256": entry.request_sha256,
            "response_sha256": entry.response_sha256,
            "status": entry.status,
        }
        for entry in entries
    ]


@dataclass(frozen=True)
class _BaseSuiteBinding:
    root: Path
    manifest_sha256: str
    suite_release_id: str
    component_set_sha256: str
    base_commit: str
    pending_contract_sha256: str
    builder: Mapping[str, Any] = field(repr=False)
    schemas: Mapping[str, Any] = field(repr=False)
    sealed_inputs: Mapping[str, Any] = field(repr=False)
    source_scope: Mapping[str, Any] = field(repr=False)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _required_text(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProductionEmbeddingCandidateConfigError("candidate_config_invalid")
    return value


def _required_sha256(value: Any) -> str:
    text = _required_text(value)
    if not _SHA256.fullmatch(text):
        raise ProductionEmbeddingCandidateConfigError("candidate_config_invalid")
    return text


def _strict_json_object(payload: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ProductionEmbeddingCandidateConfigError(
                    "candidate_config_invalid"
                )
            value[key] = item
        return value

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ProductionEmbeddingCandidateConfigError("candidate_config_invalid")
            ),
        )
    except ProductionEmbeddingCandidateConfigError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProductionEmbeddingCandidateConfigError(
            "candidate_config_invalid"
        ) from None
    if not isinstance(value, dict):
        raise ProductionEmbeddingCandidateConfigError("candidate_config_invalid")
    return value


def _exact_mapping(value: Any, expected_fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ProductionEmbeddingCandidateConfigError("candidate_config_invalid")
    return dict(value)


def _typed_equal(value: Any, expected: Any) -> bool:
    """Compare JSON-like values without Python's bool/int aliases."""

    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(
            _typed_equal(value[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(value) == len(expected) and all(
            _typed_equal(item, expected_item)
            for item, expected_item in zip(value, expected, strict=True)
        )
    return value == expected


def _validate_path_unicode(value: str) -> None:
    if unicodedata.normalize("NFC", value) != value or any(
        unicodedata.category(character) in _FORBIDDEN_PATH_UNICODE_CATEGORIES
        for character in value
    ):
        raise ProductionEmbeddingCandidateConfigError("candidate_input_unsafe")


def _reject_component_aliases(path: Path) -> None:
    parent = Path(path.anchor)
    try:
        for component in path.parts[1:]:
            entries = os.listdir(parent)
            folded = unicodedata.normalize("NFC", component).casefold()
            matches = [
                entry
                for entry in entries
                if unicodedata.normalize("NFC", entry).casefold() == folded
            ]
            if matches != [component]:
                raise ProductionEmbeddingCandidateConfigError(
                    "candidate_input_unsafe"
                )
            parent /= component
    except ProductionEmbeddingCandidateConfigError:
        raise
    except OSError:
        raise ProductionEmbeddingCandidateConfigError(
            "candidate_input_unavailable"
        ) from None


def _input_file(value: Any) -> Path:
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    raw = _required_text(value)
    _validate_path_unicode(raw)
    path = Path(raw)
    if (
        not path.is_absolute()
        or os.fspath(path) != raw
        or os.path.abspath(raw) != raw
    ):
        raise ProductionEmbeddingCandidateConfigError("candidate_config_invalid")
    try:
        resolved = path.resolve(strict=True)
        state = os.stat(path, follow_symlinks=False)
    except OSError:
        raise ProductionEmbeddingCandidateConfigError(
            "candidate_input_unavailable"
        ) from None
    _reject_component_aliases(path)
    if (
        resolved != path
        or not stat.S_ISREG(state.st_mode)
        or stat.S_ISLNK(state.st_mode)
        or state.st_nlink != 1
    ):
        raise ProductionEmbeddingCandidateConfigError("candidate_input_unsafe")
    return resolved


def _canonical_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    if (
        unicodedata.normalize("NFC", value) != value
        or any(
            unicodedata.category(character) in _FORBIDDEN_PATH_UNICODE_CATEGORIES
            for character in value
        )
        or "\\" in value
        or "//" in value
        or "\x00" in value
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    return value


def _record_set_sha256(value: Any) -> str:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _contract_object(payload: bytes) -> dict[str, Any]:
    try:
        value = _strict_json_object(payload)
    except ProductionEmbeddingCandidateConfigError:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        ) from None
    return value


def _contract_file(root: Path, relative: Any) -> Path:
    canonical = _canonical_relative(relative)
    try:
        return _input_file(root / canonical)
    except ProductionEmbeddingCandidateConfigError:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_file_unavailable"
        ) from None


def _stable_contract_payload(path: Path, error_code: str) -> tuple[bytes, str]:
    try:
        before = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise OSError("contract input is not a unique regular file")
        _path, payload, digest = read_stable_regular_file(path, "contract input")
        after = os.stat(path, follow_symlinks=False)
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or after.st_nlink != 1
        ):
            raise OSError("contract input changed")
    except ReadOnlySQLiteError:
        raise ProductionEmbeddingCandidateError(error_code) from None
    except OSError:
        raise ProductionEmbeddingCandidateError(error_code) from None
    return payload, digest


def _stable_contract_sha256(path: Path, error_code: str) -> str:
    _payload, digest = _stable_contract_payload(path, error_code)
    return digest


def _contract_records(value: Any, *, roles: bool) -> list[dict[str, str]]:
    expected_fields = {"path", "sha256", "role"} if roles else {"path", "sha256"}
    if not isinstance(value, list) or not value:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    records: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != expected_fields:
            raise ProductionEmbeddingCandidateError(
                "production_vector_build_contract_invalid"
            )
        path = _canonical_relative(raw.get("path"))
        digest = raw.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ProductionEmbeddingCandidateError(
                "production_vector_build_contract_invalid"
            )
        record = {"path": path, "sha256": digest}
        if roles:
            role = raw.get("role")
            if not isinstance(role, str) or not role or role != role.strip():
                raise ProductionEmbeddingCandidateError(
                    "production_vector_build_contract_invalid"
                )
            record["role"] = role
        records.append(record)
    paths = [record["path"] for record in records]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    return records


def _expected_contract_sha256(environment: Mapping[str, str]) -> str:
    value = environment.get(PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256_ENV)
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_hash_missing"
        )
    return value


def _expected_base_suite_manifest_sha256(environment: Mapping[str, str]) -> str:
    value = environment.get(BASE_SUITE_MANIFEST_SHA256_ENV)
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_suite_hash_missing"
        )
    return value


def _validate_contract_data_semantics(
    *,
    root: Path,
    config: "ProductionEmbeddingCandidateConfig",
    sealed_payloads: Mapping[str, bytes],
) -> None:
    authority_manifest = _manifest_object(
        sealed_payloads["authority/authority-manifest.json"]
    )
    authority_database = authority_manifest.get("database")
    if (
        not isinstance(authority_database, Mapping)
        or authority_database.get("path") != "rag_chunks.db"
    ):
        raise ProductionEmbeddingCandidateError("authority_schema_mismatch")
    raw_sources = authority_manifest.get("sources")
    if not isinstance(raw_sources, list) or any(
        not isinstance(source, Mapping)
        or not isinstance(source.get("relative_path"), str)
        or not isinstance(source.get("extracted_text_sha256"), str)
        or not _SHA256.fullmatch(source["extracted_text_sha256"])
        for source in raw_sources
    ):
        raise ProductionEmbeddingCandidateError("authority_schema_mismatch")
    expected_source_text_sha256 = {
        source["relative_path"]: source["extracted_text_sha256"]
        for source in raw_sources
    }
    if len(expected_source_text_sha256) != len(raw_sources):
        raise ProductionEmbeddingCandidateError("authority_schema_mismatch")
    authority_path = _authority_database_path(
        config.authority_manifest_path,
        authority_database,
    )
    bm25_manifest_path = _contract_file(root, "data/derived/bm25-manifest.json")
    bm25_database_path = _contract_file(root, "data/derived/bm25.sqlite3")
    bm25 = _contract_object(sealed_payloads["derived/bm25-manifest.json"])
    if set(bm25) != {
        "schema_version",
        "status",
        "authority_release_id",
        "authority_database_sha256",
        "source",
        "index",
        "indexed_chunk_count",
        "tokenizer",
        "minimum_effective_query_codepoints",
        "short_query_fallback",
        "sqlite_backfill_required",
    }:
        raise ProductionEmbeddingCandidateError("bm25_manifest_invalid")
    index = bm25.get("index")
    if (
        bm25.get("schema_version") != "cloud-v2-sqlite-fts5-trigram-v1"
        or bm25.get("status") not in {"candidate", "active"}
        or bm25.get("authority_release_id") != authority_manifest.get("release_id")
        or bm25.get("authority_database_sha256")
        != authority_database.get("sha256")
        or not isinstance(index, Mapping)
        or set(index) != {"path", "sha256"}
        or index.get("path") != "bm25.sqlite3"
        or index.get("sha256") != _sha256_file(bm25_database_path)
        or isinstance(bm25.get("indexed_chunk_count"), bool)
        or not isinstance(bm25.get("indexed_chunk_count"), int)
        or bm25.get("tokenizer") != "trigram"
        or bm25.get("minimum_effective_query_codepoints") != 3
        or bm25.get("short_query_fallback")
        != "authority-sqlite-substring-v1"
        or bm25.get("sqlite_backfill_required") is not True
    ):
        raise ProductionEmbeddingCandidateError("bm25_manifest_invalid")

    try:
        snapshot = inspect_authority_bm25_semantics(
            authority_path,
            bm25_database_path,
            expected_source_text_sha256=expected_source_text_sha256,
        )
        if (
            snapshot.authority_database_sha256 != authority_database.get("sha256")
            or snapshot.bm25_database_sha256 != index.get("sha256")
            or bm25.get("source") != snapshot.source
            or bm25.get("indexed_chunk_count") != snapshot.indexed_chunk_count
        ):
            raise ProductionEmbeddingCandidateError("bm25_authority_mismatch")
    except ProductionEmbeddingCandidateError:
        raise
    except SQLiteSemanticValidationError as exc:
        raise ProductionEmbeddingCandidateError(exc.code) from None
    except OSError:
        raise ProductionEmbeddingCandidateError("production_data_validation_failed") from None


def _output_contract() -> dict[str, Any]:
    return {
        "mode": "candidate-only",
        "chunk_and_entity_indexes_required": True,
        "production_vector_packaged": False,
        "fake_fixture_packaged": False,
        "active_write_authorized": False,
        "release_switch_authorized": False,
    }


def _approval_contract(*, authorized: bool) -> dict[str, Any]:
    return {
        "stop_b_production_provider_approved_required": True,
        "real_provider_calls_authorized": authorized,
        "production_build_authorized": authorized,
    }


def _expected_builder_command(command: str) -> list[str]:
    prefix = [
        "<absolute-python-executable>",
        "-I",
        "-S",
        "-B",
        "<exact-release-bootstrap-path>",
    ]
    if command == "capture-runtime":
        return [
            *prefix,
            "capture-runtime",
            "--output",
            "<absolute-runtime-lock-path>",
        ]
    suffix = [
        "--runtime-lock",
        "<absolute-runtime-lock-path>",
        command,
        "--config",
        "<absolute-config-path>",
    ]
    if command == "materialize":
        return [*prefix, *suffix, "--output", "<absolute-configured-contract-path>"]
    return [
        *prefix,
        *suffix,
        "--contract",
        "<absolute-configured-contract-path>",
    ]


def _executed_source_sha256() -> str:
    loader_digest = getattr(globals().get("__loader__"), "source_sha256", None)
    if isinstance(loader_digest, str) and _SHA256.fullmatch(loader_digest):
        return loader_digest
    return _sha256_file(Path(__file__).resolve())


def _validate_builder_and_schemas(
    root: Path,
    contract: Mapping[str, Any],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    builder = contract.get("builder")
    if not isinstance(builder, Mapping) or set(builder) != {
        "working_directory",
        "module",
        "bootstrap_path",
        "bootstrap_sha256",
        "source_path",
        "source_sha256",
        "runtime_capture_command",
        "runtime_verify_command",
        "materialize_command",
        "validate_command",
        "build_command",
        "file_allowlist_path",
        "file_allowlist_sha256",
        "file_set_sha256",
        "files",
    }:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    if (
        builder.get("working_directory") != "not-required-isolated-bootstrap"
        or builder.get("module") != "pipeline.production_embedding_candidate"
        or builder.get("bootstrap_path")
        != "code/deploy/pipeline/production_embedding_bootstrap.py"
        or builder.get("source_path")
        != "code/deploy/pipeline/production_embedding_candidate.py"
        or builder.get("runtime_capture_command")
        != _expected_builder_command("capture-runtime")
        or builder.get("runtime_verify_command")
        != [
            "<absolute-python-executable>",
            "-I",
            "-S",
            "-B",
            "<exact-release-bootstrap-path>",
            "--runtime-lock",
            "<absolute-runtime-lock-path>",
            "verify-runtime",
        ]
        or builder.get("materialize_command")
        != _expected_builder_command("materialize")
        or builder.get("validate_command") != _expected_builder_command("validate")
        or builder.get("build_command") != _expected_builder_command("build")
        or builder.get("file_allowlist_path") != "builder-file-allowlist.json"
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    builder_records = _contract_records(builder.get("files"), roles=False)
    builder_hashes = {record["path"]: record["sha256"] for record in builder_records}
    if (
        tuple(record["path"] for record in builder_records)
        != _REQUIRED_BUILDER_PATHS
        or builder.get("file_set_sha256") != _record_set_sha256(builder_records)
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    allowlist_path = _contract_file(root, builder.get("file_allowlist_path"))
    allowlist_payload, allowlist_sha256 = _stable_contract_payload(
        allowlist_path,
        "production_vector_build_contract_builder_mismatch",
    )
    if allowlist_sha256 != builder.get("file_allowlist_sha256"):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_builder_mismatch"
        )
    allowlist = _contract_object(allowlist_payload)
    if (
        set(allowlist) != {"schema_version", "files"}
        or allowlist.get("schema_version") != "cloud-v2-builder-file-allowlist-v1"
        or allowlist.get("files") != [record["path"] for record in builder_records]
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_builder_mismatch"
        )
    for record in builder_records:
        embedded = _contract_file(root, "code/" + record["path"])
        if _stable_contract_sha256(
            embedded,
            "production_vector_build_contract_builder_mismatch",
        ) != record["sha256"]:
            raise ProductionEmbeddingCandidateError(
                "production_vector_build_contract_builder_mismatch"
            )
    entrypoint_relative = "deploy/pipeline/production_embedding_candidate.py"
    bootstrap_relative = "deploy/pipeline/production_embedding_bootstrap.py"
    if (
        builder_hashes.get(entrypoint_relative) != builder.get("source_sha256")
        or _executed_source_sha256() != builder.get("source_sha256")
        or builder_hashes.get(bootstrap_relative) != builder.get("bootstrap_sha256")
        or _stable_contract_sha256(
            _contract_file(root, builder.get("source_path")),
            "production_vector_build_contract_builder_mismatch",
        )
        != builder.get("source_sha256")
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_builder_mismatch"
        )

    schema_paths = {
        "candidate_config_schema": "deploy/pipeline/production_embedding_config.schema.json",
        "provider_runtime_schema": "deploy/pipeline/provider_runtime_config.schema.json",
        "production_embedding_runtime_lock_schema": (
            "deploy/pipeline/production_embedding_runtime_lock.schema.json"
        ),
        "stop_b_request_schema": (
            "deploy/cloud_v2/stop-b-external-processing-request.schema.json"
        ),
    }
    schemas = contract.get("schemas")
    if not isinstance(schemas, Mapping) or set(schemas) != set(schema_paths):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    for name, relative in schema_paths.items():
        record = schemas[name]
        expected_path = "code/" + relative
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "sha256"}
            or record.get("path") != expected_path
            or record.get("sha256") != builder_hashes.get(relative)
            or _stable_contract_sha256(
                _contract_file(root, expected_path),
                "production_vector_build_contract_schema_mismatch",
            )
            != record.get("sha256")
        ):
            raise ProductionEmbeddingCandidateError(
                "production_vector_build_contract_schema_mismatch"
            )
    return builder_records, builder_hashes


def _validate_sealed_inputs(
    root: Path,
    contract: Mapping[str, Any],
    config: "ProductionEmbeddingCandidateConfig",
) -> tuple[dict[str, str], dict[str, bytes]]:
    sealed = contract.get("sealed_inputs")
    if not isinstance(sealed, Mapping) or set(sealed) != {
        "file_set_sha256",
        "files",
        "authority_manifest_sha256",
        "authority_database_sha256",
        "bm25_manifest_sha256",
        "bm25_index_sha256",
        "graph_manifest_sha256",
        "graph_data_sha256",
    }:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    data_records = _contract_records(sealed.get("files"), roles=True)
    if (
        {record["path"]: record["role"] for record in data_records}
        != _PRODUCTION_DATA_FILES
        or sealed.get("file_set_sha256") != _record_set_sha256(data_records)
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_data_mismatch"
        )
    data_hashes = {record["path"]: record["sha256"] for record in data_records}
    named_hashes = {
        "authority_manifest_sha256": "authority/authority-manifest.json",
        "authority_database_sha256": "authority/rag_chunks.db",
        "bm25_manifest_sha256": "derived/bm25-manifest.json",
        "bm25_index_sha256": "derived/bm25.sqlite3",
        "graph_manifest_sha256": "derived/graph/graph-manifest.json",
        "graph_data_sha256": "derived/graph/scoped-graph.jsonl",
    }
    sealed_payloads: dict[str, bytes] = {}
    for field, relative in named_hashes.items():
        data_path = _contract_file(root, "data/" + relative)
        data_payload, actual_sha256 = _stable_contract_payload(
            data_path,
            "production_vector_build_contract_data_mismatch",
        )
        if (
            sealed.get(field) != data_hashes.get(relative)
            or actual_sha256 != data_hashes.get(relative)
        ):
            raise ProductionEmbeddingCandidateError(
                "production_vector_build_contract_data_mismatch"
            )
        if relative.endswith(".json"):
            sealed_payloads[relative] = data_payload
    if (
        _contract_file(root, "data/authority/authority-manifest.json")
        != config.authority_manifest_path
        or _contract_file(root, "data/derived/graph/graph-manifest.json")
        != config.graph_manifest_path
        or data_hashes["authority/authority-manifest.json"]
        != config.authority_manifest_sha256
        or data_hashes["derived/graph/graph-manifest.json"]
        != config.graph_manifest_sha256
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_data_mismatch"
        )
    _source_scope_binding(sealed_payloads["authority/authority-manifest.json"])
    _validate_contract_data_semantics(
        root=root,
        config=config,
        sealed_payloads=sealed_payloads,
    )
    return data_hashes, sealed_payloads


def _source_scope_binding(authority_manifest_payload: bytes) -> dict[str, Any]:
    manifest = _manifest_object(authority_manifest_payload)
    if not _matches_frozen_source_scope(manifest.get("source_scope")):
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    raw_sources = manifest.get("sources")
    if not isinstance(raw_sources, list) or len(raw_sources) != 35:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    records: list[dict[str, str]] = []
    for source in raw_sources:
        if not isinstance(source, Mapping):
            raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
        relative = _canonical_relative(source.get("relative_path"))
        digest = source.get("source_sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
        records.append({"relative_path": relative, "source_sha256": digest})
    paths = [record["relative_path"] for record in records]
    folded_paths = {
        unicodedata.normalize("NFC", relative).casefold() for relative in paths
    }
    if (
        paths != sorted(paths)
        or len(paths) != len(set(paths))
        or len(folded_paths) != len(paths)
    ):
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    return {
        "identity": dict(FROZEN_R9_SOURCE_SCOPE),
        "source_file_set_sha256": _record_set_sha256(records),
        "files": records,
    }


def _base_suite_contract_value(binding: _BaseSuiteBinding) -> dict[str, Any]:
    return {
        "manifest": {
            "path": "SUITE_MANIFEST.json",
            "sha256": binding.manifest_sha256,
        },
        "suite_release_id": binding.suite_release_id,
        "component_set_sha256": binding.component_set_sha256,
        "base_commit": binding.base_commit,
        "pending_contract": {
            "path": BASE_SUITE_PENDING_CONTRACT_PATH,
            "sha256": binding.pending_contract_sha256,
        },
    }


def _load_base_suite_binding(
    config: "ProductionEmbeddingCandidateConfig",
    expected_manifest_sha256: str,
) -> _BaseSuiteBinding:
    if config.base_suite_manifest_sha256 != expected_manifest_sha256:
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_suite_hash_mismatch"
        )
    manifest_payload, manifest_sha256 = _stable_contract_payload(
        config.base_suite_manifest_path,
        "production_vector_base_suite_unavailable",
    )
    if manifest_sha256 != expected_manifest_sha256:
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_suite_hash_mismatch"
        )
    manifest = _contract_object(manifest_payload)
    if set(manifest) != {
        "schema_version",
        "suite_release_id",
        "status",
        "created_at",
        "base_commit",
        "components",
        "component_set_sha256",
        "identities",
        "evidence",
        "phase_state",
    }:
        raise ProductionEmbeddingCandidateError("production_vector_base_suite_invalid")
    components = _contract_records(manifest.get("components"), roles=False)
    component_set_sha256 = _record_set_sha256(components)
    suite_release_id = manifest.get("suite_release_id")
    base_commit = manifest.get("base_commit")
    if (
        manifest.get("schema_version") != BASE_SUITE_MANIFEST_SCHEMA_VERSION
        or manifest.get("status") != "offline-provider-candidate"
        or manifest.get("component_set_sha256") != component_set_sha256
        or suite_release_id
        != "knowledge-qa-suite:r9-offline:" + component_set_sha256[:16]
        or not isinstance(base_commit, str)
        or not _GIT_SHA1.fullmatch(base_commit)
        or not _typed_equal(manifest.get("phase_state"), _BASE_SUITE_PHASE_STATE)
        or not isinstance(manifest.get("identities"), Mapping)
        or not isinstance(manifest.get("evidence"), Mapping)
    ):
        raise ProductionEmbeddingCandidateError("production_vector_base_suite_invalid")
    component_hashes = {
        record["path"]: record["sha256"] for record in components
    }
    if any(
        relative.endswith(".usearch")
        or relative.startswith("server-runtime/data/derived/local-vector/")
        or relative == "server-runtime/data/derived/fake-embedding-manifest.json"
        for relative in component_hashes
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_suite_contains_fake_vector"
        )
    if (
        component_hashes.get(BASE_SUITE_PENDING_CONTRACT_PATH)
        != config.base_contract_sha256
        or manifest["identities"].get("production_vector_build_contract_sha256")
        != config.base_contract_sha256
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_contract_mismatch"
        )
    pending_payload, pending_sha256 = _stable_contract_payload(
        config.base_contract_path,
        "production_vector_base_contract_unavailable",
    )
    if pending_sha256 != config.base_contract_sha256:
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_contract_mismatch"
        )
    pending = _contract_object(pending_payload)
    if set(pending) != {
        "schema_version",
        "status",
        "provider_neutral",
        "builder",
        "schemas",
        "sealed_inputs",
        "production_embedding_identity",
        "output_contract",
        "approval_contract",
    } or pending.get("schema_version") != BASE_PRODUCTION_VECTOR_BUILD_CONTRACT_SCHEMA_VERSION:
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_contract_invalid"
        )
    if (
        pending.get("status")
        != "unconfigured-pending-stop-b-production-provider-approval"
        or pending.get("provider_neutral") is not True
        or not _typed_equal(
            pending.get("production_embedding_identity"),
            {
                "provider": None,
                "endpoint": None,
                "region": None,
                "model": None,
                "model_version": None,
                "dimension": None,
                "normalization": None,
            },
        )
        or not _typed_equal(pending.get("output_contract"), _output_contract())
        or not _typed_equal(
            pending.get("approval_contract"), _approval_contract(authorized=False)
        )
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_contract_invalid"
        )
    runtime_root = config.base_contract_path.parent
    builder_records, _builder_hashes = _validate_builder_and_schemas(
        runtime_root, pending
    )
    data_hashes, sealed_payloads = _validate_sealed_inputs(
        runtime_root, pending, config
    )
    expected_components = {
        "server-runtime/builder-file-allowlist.json": pending["builder"][
            "file_allowlist_sha256"
        ],
        **{
            "server-runtime/code/" + record["path"]: record["sha256"]
            for record in builder_records
        },
        **{
            "server-runtime/data/" + relative: digest
            for relative, digest in data_hashes.items()
        },
    }
    if any(
        component_hashes.get(relative) != digest
        for relative, digest in expected_components.items()
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_suite_component_mismatch"
        )
    identities = manifest["identities"]
    expected_identities = {
        "authority_manifest_sha256": data_hashes[
            "authority/authority-manifest.json"
        ],
        "authority_database_sha256": data_hashes["authority/rag_chunks.db"],
        "bm25_manifest_sha256": data_hashes["derived/bm25-manifest.json"],
        "bm25_index_sha256": data_hashes["derived/bm25.sqlite3"],
        "graph_candidate_manifest_sha256": data_hashes[
            "derived/graph/graph-manifest.json"
        ],
        "graph_data_sha256": data_hashes[
            "derived/graph/scoped-graph.jsonl"
        ],
        "builder_file_allowlist_sha256": pending["builder"][
            "file_allowlist_sha256"
        ],
        "builder_code_file_set_sha256": pending["builder"]["file_set_sha256"],
        "production_vector_build_contract_sha256": pending_sha256,
    }
    if any(identities.get(key) != value for key, value in expected_identities.items()):
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_suite_identity_mismatch"
        )
    source_scope = _source_scope_binding(
        sealed_payloads["authority/authority-manifest.json"]
    )
    return _BaseSuiteBinding(
        root=config.base_suite_manifest_path.parent,
        manifest_sha256=manifest_sha256,
        suite_release_id=str(suite_release_id),
        component_set_sha256=component_set_sha256,
        base_commit=base_commit,
        pending_contract_sha256=pending_sha256,
        builder=copy.deepcopy(pending["builder"]),
        schemas=copy.deepcopy(pending["schemas"]),
        sealed_inputs=copy.deepcopy(pending["sealed_inputs"]),
        source_scope=source_scope,
    )


def _production_embedding_identity(identity: EmbeddingIdentity) -> dict[str, Any]:
    return {
        "provider": identity.provider,
        "endpoint": identity.base_url,
        "region": identity.region,
        "model": identity.model,
        "model_version": identity.model_version,
        "api_version": identity.api_version,
        "dimension": identity.dimension,
        "normalization": identity.normalization,
        "input_type": identity.input_type,
        "identity_sha256": identity.sha256,
    }


def _local_vector_build_contract(
    config: "ProductionEmbeddingCandidateConfig",
    identity: EmbeddingIdentity,
) -> dict[str, Any]:
    contract = config.vector_contract
    vector_identity = copy.deepcopy(contract.identity_manifest())
    vector_identity["normalization"] = identity.normalization
    return {
        "approved_data_parent": str(contract.approved_data_parent),
        "data_root": str(contract.data_root),
        "candidate_root": str(contract.data_root / "candidate"),
        "active_root": str(contract.data_root / "active"),
        "candidate_release_dir": str(contract.candidate_release_dir),
        "active_release_dir": str(contract.active_release_dir),
        "active_state_path": str(contract.active_state_path),
        "identity": vector_identity,
    }


def _validate_local_vector_approval(
    *,
    config: "ProductionEmbeddingCandidateConfig",
    identity: EmbeddingIdentity,
    approved_production: Mapping[str, Any],
) -> None:
    configured = _local_vector_build_contract(config, identity)
    vector = configured["identity"]
    expected = {
        "engine": {
            "name": vector["engine"],
            "version": vector["engine_version"],
            "index_build_threads": vector["index_build_threads"],
        },
        "data_layout": {
            "data_root": configured["data_root"],
            "candidate_root": configured["candidate_root"],
            "active_root": configured["active_root"],
        },
        "indexes": copy.deepcopy(vector["index_names"]),
        "vector_identity": {
            "embedding_identity_sha256": vector["embedding_identity_sha256"],
            "dimension": vector["dimension"],
            "dtype": vector["dtype"],
            "normalization": vector["normalization"],
            "metric": vector["metric"],
            "engine_metric": vector["engine_metric"],
            "schema_version": vector["schema_version"],
            "authority_manifest_sha256": vector["authority_manifest_sha256"],
            "chunking_identity_sha256": vector["chunking_identity_sha256"],
            "metadata_allowlist": copy.deepcopy(vector["metadata_allowlist"]),
            "top_k_max": vector["top_k_max"],
            "max_vectors_per_index": vector["max_vectors_per_index"],
        },
        "runtime_read_only": True,
        "network_listener": False,
        "rebuild_from_real_embedding_required": True,
    }
    try:
        engine = approved_production["engine"]
        data_layout = approved_production["data_layout"]
        actual = {
            "engine": {
                "name": engine["name"],
                "version": engine["version"],
                "index_build_threads": engine["index_build_threads"],
            },
            "data_layout": {
                "data_root": data_layout["data_root"],
                "candidate_root": data_layout["candidate_root"],
                "active_root": data_layout["active_root"],
            },
            "indexes": approved_production["indexes"],
            "vector_identity": approved_production["vector_identity"],
            "runtime_read_only": approved_production["runtime_read_only"],
            "network_listener": approved_production["network_listener"],
            "rebuild_from_real_embedding_required": approved_production[
                "rebuild_from_real_embedding_required"
            ],
        }
    except (KeyError, TypeError):
        raise ProviderApprovalError("production_vector_approval_binding_invalid") from None
    if not _typed_equal(actual, expected):
        raise ProviderApprovalError("production_vector_approval_binding_mismatch")


def _provider_binding(
    config: "ProductionEmbeddingCandidateConfig",
) -> dict[str, Any]:
    provider = config.provider_config
    embedding = provider.embedding
    approval = provider.approval_binding
    if embedding is None or approval is None:
        raise ProviderRuntimeConfigError("provider_embedding_config_required")
    return {
        "provider_config_sha256": provider.sha256,
        "provider_contract_sha256": provider.contract_sha256,
        "stop_b_approval_receipt_sha256": approval.receipt_sha256,
        "embedding_policy_sha256": embedding.policy_sha256,
    }


def _configured_contract(
    binding: _BaseSuiteBinding,
    config: "ProductionEmbeddingCandidateConfig",
    identity: EmbeddingIdentity,
    approved_production: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PRODUCTION_VECTOR_BUILD_CONTRACT_SCHEMA_VERSION,
        "status": "configured-stop-b-production-provider-approved",
        "provider_neutral": True,
        "candidate_config_sha256": config.sha256,
        "base_suite": _base_suite_contract_value(binding),
        "source_scope": copy.deepcopy(binding.source_scope),
        "builder": copy.deepcopy(binding.builder),
        "schemas": copy.deepcopy(binding.schemas),
        "sealed_inputs": copy.deepcopy(binding.sealed_inputs),
        "provider_binding": _provider_binding(config),
        "production_embedding_identity": _production_embedding_identity(identity),
        "local_vector_contract": {
            "configured": _local_vector_build_contract(config, identity),
            "approved_production": copy.deepcopy(dict(approved_production)),
        },
        "output_contract": _output_contract(),
        "approval_contract": _approval_contract(authorized=True),
    }


def _load_anchored_production_vector_build_contract(
    *,
    contract_path: str | Path,
    expected_sha256: str,
    config: "ProductionEmbeddingCandidateConfig",
) -> tuple[Path, bytes, dict[str, Any]]:
    try:
        path = _input_file(contract_path)
    except (OSError, ProductionEmbeddingCandidateConfigError):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_unavailable"
        ) from None
    payload, actual_sha256 = _stable_contract_payload(
        path,
        "production_vector_build_contract_unavailable",
    )
    if actual_sha256 != expected_sha256:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_hash_mismatch"
        )
    contract = _contract_object(payload)
    if set(contract) != {
        "schema_version",
        "status",
        "provider_neutral",
        "candidate_config_sha256",
        "base_suite",
        "source_scope",
        "builder",
        "schemas",
        "sealed_inputs",
        "provider_binding",
        "production_embedding_identity",
        "local_vector_contract",
        "output_contract",
        "approval_contract",
    } or contract.get("schema_version") != PRODUCTION_VECTOR_BUILD_CONTRACT_SCHEMA_VERSION:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_invalid"
        )
    if (
        contract.get("status") != "configured-stop-b-production-provider-approved"
        or contract.get("provider_neutral") is not True
        or not _typed_equal(contract.get("output_contract"), _output_contract())
        or not _typed_equal(
            contract.get("approval_contract"), _approval_contract(authorized=True)
        )
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_unapproved"
        )
    try:
        path.relative_to(config.base_suite_manifest_path.parent)
    except ValueError:
        pass
    else:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_must_be_suite_external"
        )
    return path, payload, contract


def _validate_candidate_config_contract_binding(
    *,
    contract: Mapping[str, Any],
    config: "ProductionEmbeddingCandidateConfig",
    identity: EmbeddingIdentity,
) -> None:
    local_vector = contract.get("local_vector_contract")
    if (
        contract.get("candidate_config_sha256") != config.sha256
        or type(local_vector) is not dict
        or set(local_vector) != {"configured", "approved_production"}
        or not _typed_equal(
            contract.get("provider_binding"),
            _provider_binding(config),
        )
        or not _typed_equal(
            contract.get("production_embedding_identity"),
            _production_embedding_identity(identity),
        )
        or not _typed_equal(
            local_vector.get("configured"),
            _local_vector_build_contract(config, identity),
        )
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_config_mismatch"
        )


def _validate_approved_production_contract_binding(
    *,
    contract: Mapping[str, Any],
    approved_production: Mapping[str, Any],
) -> None:
    local_vector = contract.get("local_vector_contract")
    if (
        type(local_vector) is not dict
        or not _typed_equal(
            local_vector.get("approved_production"),
            dict(approved_production),
        )
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_approval_mismatch"
        )


def _validate_production_vector_build_contract(
    *,
    contract_path: str | Path,
    expected_sha256: str,
    expected_base_suite_manifest_sha256: str,
    config: "ProductionEmbeddingCandidateConfig",
    identity: EmbeddingIdentity,
    approved_production: Mapping[str, Any],
) -> str:
    path, payload, contract = _load_anchored_production_vector_build_contract(
        contract_path=contract_path,
        expected_sha256=expected_sha256,
        config=config,
    )
    _validate_candidate_config_contract_binding(
        contract=contract,
        config=config,
        identity=identity,
    )
    _validate_approved_production_contract_binding(
        contract=contract,
        approved_production=approved_production,
    )
    binding = _load_base_suite_binding(
        config, expected_base_suite_manifest_sha256
    )
    expected_contract = _configured_contract(
        binding,
        config,
        identity,
        approved_production,
    )
    if not _typed_equal(contract, expected_contract):
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_binding_mismatch"
        )
    final_payload, final_sha256 = _stable_contract_payload(
        path,
        "production_vector_build_contract_changed",
    )
    if final_sha256 != expected_sha256 or final_payload != payload:
        raise ProductionEmbeddingCandidateError(
            "production_vector_build_contract_changed"
        )
    if (
        _stable_contract_sha256(
            config.base_suite_manifest_path,
            "production_vector_base_suite_changed",
        )
        != binding.manifest_sha256
        or _stable_contract_sha256(
            config.base_contract_path,
            "production_vector_base_contract_changed",
        )
        != binding.pending_contract_sha256
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_base_suite_changed"
        )
    return expected_sha256

def local_data_release_id(
    authority_database_sha256: str,
    embedding_identity_sha256: str,
) -> str:
    """Return the deterministic release id for the frozen r9 vector layout."""

    if not _SHA256.fullmatch(str(authority_database_sha256)) or not _SHA256.fullmatch(
        str(embedding_identity_sha256)
    ):
        raise ValueError("release identities must be lowercase SHA-256 values")
    return "r9-" + _canonical_sha256(
        {
            "authority_database_sha256": authority_database_sha256,
            "embedding_identity_sha256": embedding_identity_sha256,
            "schema_version": LOCAL_DATA_RELEASE_ID_SCHEMA_VERSION,
        }
    )


@dataclass(frozen=True)
class ProductionEmbeddingCandidateConfig:
    path: Path
    sha256: str
    provider_config: ProviderRuntimeConfig
    base_suite_manifest_path: Path
    base_suite_manifest_sha256: str
    base_contract_path: Path
    base_contract_sha256: str
    authority_manifest_path: Path
    authority_manifest_sha256: str
    graph_manifest_path: Path
    graph_manifest_sha256: str
    vector_contract: LocalVectorContract

    @classmethod
    def load(cls, raw_path: str | Path) -> "ProductionEmbeddingCandidateConfig":
        path = _input_file(raw_path)
        try:
            payload = path.read_bytes()
        except OSError:
            raise ProductionEmbeddingCandidateConfigError(
                "candidate_config_unreadable"
            ) from None
        root = _strict_json_object(payload)
        if set(root) != {
            "schema_version",
            "provider_config",
            "base_suite",
            "authority",
            "graph",
            "local_vector",
        } or root["schema_version"] != CONFIG_SCHEMA_VERSION:
            raise ProductionEmbeddingCandidateConfigError("candidate_config_invalid")

        base_suite = _exact_mapping(
            root["base_suite"], {"manifest", "pending_contract"}
        )
        references: dict[str, tuple[Path, str]] = {}
        for key in ("provider_config", "authority", "graph"):
            reference = _exact_mapping(root[key], {"path", "sha256"})
            reference_path = _input_file(reference["path"])
            expected_hash = _required_sha256(reference["sha256"])
            try:
                actual_hash = _sha256_file(reference_path)
            except OSError:
                raise ProductionEmbeddingCandidateConfigError(
                    "candidate_input_unreadable"
                ) from None
            if actual_hash != expected_hash:
                raise ProductionEmbeddingCandidateConfigError(
                    "candidate_input_hash_mismatch"
                )
            references[key] = (reference_path, expected_hash)

        base_references: dict[str, tuple[Path, str]] = {}
        for key in ("manifest", "pending_contract"):
            reference = _exact_mapping(base_suite[key], {"path", "sha256"})
            reference_path = _input_file(reference["path"])
            expected_hash = _required_sha256(reference["sha256"])
            try:
                actual_hash = _sha256_file(reference_path)
            except OSError:
                raise ProductionEmbeddingCandidateConfigError(
                    "candidate_input_unreadable"
                ) from None
            if actual_hash != expected_hash:
                raise ProductionEmbeddingCandidateConfigError(
                    "candidate_input_hash_mismatch"
                )
            base_references[key] = (reference_path, expected_hash)

        base_manifest_path, base_manifest_sha256 = base_references["manifest"]
        base_contract_path, base_contract_sha256 = base_references["pending_contract"]
        base_root = base_manifest_path.parent
        if (
            base_manifest_path.name != "SUITE_MANIFEST.json"
            or base_contract_path
            != base_root / BASE_SUITE_PENDING_CONTRACT_PATH
            or references["authority"][0]
            != base_root / "server-runtime/data/authority/authority-manifest.json"
            or references["graph"][0]
            != base_root / "server-runtime/data/derived/graph/graph-manifest.json"
        ):
            raise ProductionEmbeddingCandidateConfigError(
                "base_suite_layout_mismatch"
            )

        provider_path, provider_sha256 = references["provider_config"]
        provider_config = ProviderRuntimeConfig.load(provider_path)
        if provider_config.sha256 != provider_sha256:
            raise ProductionEmbeddingCandidateConfigError(
                "provider_config_hash_mismatch"
            )

        local = _exact_mapping(
            root["local_vector"],
            {
                "approved_data_parent",
                "data_root",
                "data_release_id",
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
                "dtype",
            },
        )
        metadata = _exact_mapping(
            local["metadata_allowlist"], {"chunk", "entity"}
        )
        if metadata != {
            "chunk": list(_VECTOR_METADATA["chunk"]),
            "entity": list(_VECTOR_METADATA["entity"]),
        }:
            raise ProductionEmbeddingCandidateConfigError(
                "vector_metadata_contract_mismatch"
            )
        if local.get("schema_version") != LOCAL_VECTOR_SCHEMA_VERSION:
            raise ProductionEmbeddingCandidateConfigError("vector_contract_invalid")
        try:
            vector_contract = LocalVectorContract(
                approved_data_parent=Path(local["approved_data_parent"]),
                data_root=Path(local["data_root"]),
                data_release_id=local["data_release_id"],
                authority_manifest_sha256=local["authority_manifest_sha256"],
                chunking_identity_sha256=local["chunking_identity_sha256"],
                embedding_identity_sha256=local["embedding_identity_sha256"],
                dimension=local["dimension"],
                metric=local["metric"],
                schema_version=local["schema_version"],
                chunk_index_name=local["chunk_index_name"],
                entity_index_name=local["entity_index_name"],
                top_k_max=local["top_k_max"],
                max_vectors_per_index=local["max_vectors_per_index"],
                metadata_allowlist=metadata,
                engine=local["engine"],
                engine_version=local["engine_version"],
                dtype=local["dtype"],
            )
        except (TypeError, ValueError):
            raise ProductionEmbeddingCandidateConfigError(
                "vector_contract_invalid"
            ) from None

        authority_path, authority_sha256 = references["authority"]
        graph_path, graph_sha256 = references["graph"]
        if vector_contract.authority_manifest_sha256 != authority_sha256:
            raise ProductionEmbeddingCandidateConfigError(
                "authority_manifest_binding_mismatch"
            )
        embedding = provider_config.embedding
        if embedding is None or (
            vector_contract.embedding_identity_sha256 != embedding.identity_sha256
            or vector_contract.dimension != embedding.identity.get("dimension")
        ):
            raise ProductionEmbeddingCandidateConfigError(
                "embedding_vector_binding_mismatch"
            )
        return cls(
            path=path,
            sha256=hashlib.sha256(payload).hexdigest(),
            provider_config=provider_config,
            base_suite_manifest_path=base_manifest_path,
            base_suite_manifest_sha256=base_manifest_sha256,
            base_contract_path=base_contract_path,
            base_contract_sha256=base_contract_sha256,
            authority_manifest_path=authority_path,
            authority_manifest_sha256=authority_sha256,
            graph_manifest_path=graph_path,
            graph_manifest_sha256=graph_sha256,
            vector_contract=vector_contract,
        )


@dataclass(frozen=True)
class _TrustedCandidateInputs:
    authority_release_id: str
    authority_database_sha256: str
    graph_package: ScopedGraphPackage = field(repr=False)
    chunk_records: tuple[_EmbeddingCandidateRecord, ...] = field(repr=False)
    entity_records: tuple[_EmbeddingCandidateRecord, ...] = field(repr=False)


@dataclass(frozen=True)
class _PreparedCandidate:
    config: ProductionEmbeddingCandidateConfig
    identity: EmbeddingIdentity
    policy: EmbeddingPolicy
    bindings: tuple[PurposeEmbeddingBinding, ...]
    production_vector_build_contract_sha256: str
    trusted: _TrustedCandidateInputs = field(repr=False)
    chunk_inputs: tuple[EmbeddingInput, ...] = field(repr=False)
    chunks: tuple[_EmbeddingCandidateRecord, ...] = field(repr=False)
    entity_inputs: tuple[EmbeddingInput, ...] = field(repr=False)
    entities: tuple[_EmbeddingCandidateRecord, ...] = field(repr=False)
    vector_adapter: LocalVectorStoreAdapter = field(repr=False)
    input_meter: Callable[[str], int] = field(repr=False)


def _reload_bound_config(
    config: Any,
) -> ProductionEmbeddingCandidateConfig:
    if not isinstance(config, ProductionEmbeddingCandidateConfig):
        raise ProductionEmbeddingCandidateConfigError("candidate_config_required")
    try:
        _payload, current_sha256 = _stable_contract_payload(
            config.path,
            "candidate_config_hash_mismatch",
        )
    except ProductionEmbeddingCandidateError:
        raise ProductionEmbeddingCandidateConfigError(
            "candidate_config_hash_mismatch"
        ) from None
    if current_sha256 != config.sha256:
        raise ProductionEmbeddingCandidateConfigError(
            "candidate_config_hash_mismatch"
        )
    current = ProductionEmbeddingCandidateConfig.load(config.path)
    if current.sha256 != config.sha256:
        raise ProductionEmbeddingCandidateConfigError(
            "candidate_config_hash_mismatch"
        )
    return current


def _load_approved_local_vector_production(
    config: ProviderRuntimeConfig,
) -> dict[str, Any]:
    binding = config.approval_binding
    if binding is None:
        raise ProviderApprovalError("production_vector_approval_binding_invalid")
    try:
        from deploy.cloud_v2.stop_b_request import (
            StopBRequestError,
            validate_stop_b_request,
        )
    except ImportError:
        raise ProviderApprovalError(
            "production_vector_approval_binding_invalid"
        ) from None
    try:
        request_path = _input_file(binding.stop_b_request_path)
        payload, digest = _stable_contract_payload(
            request_path,
            "production_vector_approval_binding_invalid",
        )
        if digest != binding.stop_b_request_sha256:
            raise ProviderApprovalError("production_vector_approval_binding_invalid")
        request = _strict_json_object(payload)
        validated = validate_stop_b_request(request, mode="approval_ready")
        production = validated["local_vector_contract"]["production"]
    except ProviderApprovalError:
        raise
    except (
        KeyError,
        ProductionEmbeddingCandidateConfigError,
        ProductionEmbeddingCandidateError,
        StopBRequestError,
        TypeError,
    ):
        raise ProviderApprovalError(
            "production_vector_approval_binding_invalid"
        ) from None
    if type(production) is not dict:
        raise ProviderApprovalError("production_vector_approval_binding_invalid")
    return copy.deepcopy(production)


def _validate_approval(
    config: ProviderRuntimeConfig,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    try:
        approved_production = validate_production_approval(config, environment)
    except ProviderBootstrapError:
        raise
    except Exception:
        raise ProviderApprovalError("provider_approval_validation_failed") from None
    if approved_production is None:
        return _load_approved_local_vector_production(config)
    if type(approved_production) is not dict:
        raise ProviderApprovalError("production_vector_approval_binding_invalid")
    return copy.deepcopy(approved_production)


def _binding_contract(
    config: ProviderRuntimeConfig,
    vector_contract: LocalVectorContract,
) -> tuple[
    EmbeddingIdentity,
    EmbeddingPolicy,
    tuple[PurposeEmbeddingBinding, ...],
]:
    embedding = config.embedding
    if embedding is None:
        raise ProviderRuntimeConfigError("provider_embedding_config_required")
    try:
        build_identity = EmbeddingIdentity(**dict(embedding.identity))
        query_identity = QueryEmbeddingIdentity(**dict(embedding.identity))
        build_policy = EmbeddingPolicy(**dict(embedding.policy))
        query_policy = QueryEmbeddingPolicy(**dict(embedding.policy))
    except (TypeError, ValueError):
        raise ProviderRuntimeConfigError("provider_embedding_binding_invalid") from None
    if (
        build_identity.sha256 != query_identity.sha256
        or build_identity.sha256 != embedding.identity_sha256
        or build_policy.sha256 != query_policy.sha256
        or build_policy.sha256 != embedding.policy_sha256
    ):
        raise ProviderRuntimeConfigError("provider_embedding_binding_mismatch")
    if (
        vector_contract.embedding_identity_sha256 != build_identity.sha256
        or vector_contract.dimension != build_identity.dimension
    ):
        raise ProductionEmbeddingCandidateError("vector_contract_binding_mismatch")
    bindings = (
        PurposeEmbeddingBinding(
            purpose="build",
            identity_sha256=build_identity.sha256,
            policy_sha256=build_policy.sha256,
        ),
        PurposeEmbeddingBinding(
            purpose="query",
            identity_sha256=query_identity.sha256,
            policy_sha256=query_policy.sha256,
        ),
        PurposeEmbeddingBinding(
            purpose="entity",
            identity_sha256=build_identity.sha256,
            policy_sha256=build_policy.sha256,
        ),
    )
    return build_identity, build_policy, bindings


@dataclass(frozen=True)
class _HeldContractOutput:
    path: Path
    parent: Path
    name: str
    parent_fd: int
    parent_identity: tuple[int, int, int]


def _directory_identity(state: os.stat_result) -> tuple[int, int, int]:
    return (state.st_dev, state.st_ino, state.st_mode)


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _revalidate_contract_output_parent(target: _HeldContractOutput) -> None:
    try:
        held = os.fstat(target.parent_fd)
        current = os.stat(target.parent, follow_symlinks=False)
        resolved = target.parent.resolve(strict=True)
    except OSError:
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_parent_changed"
        ) from None
    if (
        not stat.S_ISDIR(held.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or resolved != target.parent
        or _directory_identity(held) != target.parent_identity
        or _directory_identity(current) != target.parent_identity
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_parent_changed"
        )


def _production_contract_output_path(
    raw_path: str | Path,
    *,
    base_suite_root: Path,
) -> _HeldContractOutput:
    raw = os.fspath(raw_path)
    try:
        raw = _required_text(raw)
        _validate_path_unicode(raw)
    except ProductionEmbeddingCandidateConfigError:
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_invalid"
        ) from None
    path = Path(raw)
    if (
        not path.is_absolute()
        or os.fspath(path) != raw
        or os.path.abspath(raw) != raw
        or path.name in {"", ".", ".."}
    ):
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_invalid"
        )
    parent = path.parent
    parent_fd: int | None = None
    try:
        resolved_parent = parent.resolve(strict=True)
        state = os.stat(parent, follow_symlinks=False)
        _reject_component_aliases(parent)
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        parent_fd = os.open(parent, flags)
        opened = os.fstat(parent_fd)
        current = os.stat(parent, follow_symlinks=False)
        entries = os.listdir(parent_fd)
    except (OSError, ProductionEmbeddingCandidateConfigError):
        if parent_fd is not None:
            _close_descriptor(parent_fd)
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_invalid"
        ) from None
    if (
        resolved_parent != parent
        or not stat.S_ISDIR(state.st_mode)
        or stat.S_ISLNK(state.st_mode)
        or _directory_identity(state) != _directory_identity(opened)
        or _directory_identity(state) != _directory_identity(current)
    ):
        _close_descriptor(parent_fd)
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_invalid"
        )
    folded = unicodedata.normalize("NFC", path.name).casefold()
    if any(
        unicodedata.normalize("NFC", entry).casefold() == folded
        for entry in entries
    ):
        _close_descriptor(parent_fd)
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_exists"
        )
    try:
        path.relative_to(base_suite_root)
    except ValueError:
        return _HeldContractOutput(
            path=path,
            parent=parent,
            name=path.name,
            parent_fd=parent_fd,
            parent_identity=_directory_identity(opened),
        )
    _close_descriptor(parent_fd)
    raise ProductionEmbeddingCandidateError(
        "production_vector_build_contract_must_be_suite_external"
    )


def _read_contract_from_parent(
    target: _HeldContractOutput,
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(target.name, flags, dir_fd=target.parent_fd)
        before = os.fstat(descriptor)
        entry = os.stat(
            target.name,
            dir_fd=target.parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (before.st_dev, before.st_ino) != (entry.st_dev, entry.st_ino)
        ):
            raise OSError("contract output is not a unique regular file")
        blocks: list[bytes] = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            blocks.append(block)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_nlink,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        ):
            raise OSError("contract output changed while being read")
        payload = b"".join(blocks)
        if len(payload) != after.st_size:
            raise OSError("contract output size changed")
        return payload, after
    finally:
        if descriptor is not None:
            _close_descriptor(descriptor)


def _cleanup_contract_output(target: _HeldContractOutput) -> None:
    try:
        os.unlink(target.name, dir_fd=target.parent_fd)
        os.fsync(target.parent_fd)
    except OSError:
        pass


def _write_new_contract(
    target: _HeldContractOutput,
    value: Mapping[str, Any],
) -> str:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(
            target.name,
            flags,
            0o640,
            dir_fd=target.parent_fd,
        )
        created = True
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise OSError("contract output is not a unique regular file")
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("contract output write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.fsync(target.parent_fd)
    except OSError:
        if created:
            _cleanup_contract_output(target)
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_write_failed"
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    digest = hashlib.sha256(payload).hexdigest()
    try:
        written_payload, written_state = _read_contract_from_parent(target)
        _revalidate_contract_output_parent(target)
    except (OSError, ProductionEmbeddingCandidateError):
        _cleanup_contract_output(target)
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_write_failed"
        ) from None
    if (
        written_payload != payload
        or hashlib.sha256(written_payload).hexdigest() != digest
        or written_state.st_nlink != 1
    ):
        _cleanup_contract_output(target)
        raise ProductionEmbeddingCandidateError(
            "production_vector_contract_output_write_failed"
        )
    return digest


def _materialize_production_vector_build_contract_impl(
    *,
    config: ProductionEmbeddingCandidateConfig,
    output_path: str | Path,
    _bootstrap_guard: Callable[[], None] | None = None,
) -> ProductionVectorContractMaterialization:
    """Create one deterministic configured contract outside the immutable suite."""

    source = os.environ
    expected_base_sha256 = _expected_base_suite_manifest_sha256(source)
    current = _reload_bound_config(config)
    require_https_network_mode(current.provider_config, source)
    identity, _policy, _bindings = _binding_contract(
        current.provider_config, current.vector_contract
    )
    approved_production = _validate_approval(
        current.provider_config,
        source,
    )
    _validate_local_vector_approval(
        config=current,
        identity=identity,
        approved_production=approved_production,
    )
    binding = _load_base_suite_binding(current, expected_base_sha256)
    trusted = _load_trusted_candidate_inputs(current)
    _validate_candidate_capacity(
        approved_production=approved_production,
        chunk_count=len(trusted.chunk_records),
        entity_count=len(trusted.entity_records),
        dimension=identity.dimension,
        dtype=current.vector_contract.dtype,
    )
    contract = _configured_contract(
        binding,
        current,
        identity,
        approved_production,
    )
    destination = _production_contract_output_path(
        output_path,
        base_suite_root=binding.root,
    )
    if _bootstrap_guard is not None:
        _bootstrap_guard()
    try:
        digest = _write_new_contract(destination, contract)
    finally:
        _close_descriptor(destination.parent_fd)
    return ProductionVectorContractMaterialization(
        contract_path=destination.path,
        contract_sha256=digest,
        base_suite_manifest_sha256=binding.manifest_sha256,
        base_contract_sha256=binding.pending_contract_sha256,
        provider_config_sha256=current.provider_config.sha256,
        embedding_identity_sha256=identity.sha256,
        source_count=len(binding.source_scope["files"]),
    )


def _positive_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    return value


def _validate_candidate_capacity(
    *,
    approved_production: Mapping[str, Any],
    chunk_count: int,
    entity_count: int,
    dimension: int,
    dtype: str,
) -> None:
    """Bind approved vector capacity to the exact data selected for this build."""

    capacity = approved_production.get("capacity")
    required_fields = {
        "chunk_capacity",
        "entity_capacity",
        "memory_budget_bytes",
        "disk_budget_bytes",
    }
    if type(capacity) is not dict or set(capacity) != required_fields:
        raise ProductionEmbeddingCandidateError("production_vector_capacity_invalid")
    values: dict[str, int] = {}
    for field in sorted(required_fields):
        value = capacity.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ProductionEmbeddingCandidateError("production_vector_capacity_invalid")
        values[field] = value
    if (
        isinstance(chunk_count, bool)
        or not isinstance(chunk_count, int)
        or chunk_count <= 0
        or isinstance(entity_count, bool)
        or not isinstance(entity_count, int)
        or entity_count <= 0
        or isinstance(dimension, bool)
        or not isinstance(dimension, int)
        or dimension <= 0
        or dtype != "f32"
    ):
        raise ProductionEmbeddingCandidateError("production_vector_capacity_invalid")
    if (
        chunk_count > values["chunk_capacity"]
        or entity_count > values["entity_capacity"]
    ):
        raise ProductionEmbeddingCandidateError("production_vector_capacity_exceeded")

    # Both indexes persist f32 vectors. Their raw vector matrix is a strict lower
    # bound for build memory and disk; engine/metadata overhead can only add to it.
    minimum_vector_bytes = (chunk_count + entity_count) * dimension * 4
    if values["memory_budget_bytes"] < minimum_vector_bytes:
        raise ProductionEmbeddingCandidateError(
            "production_vector_memory_budget_exceeded"
        )
    if values["disk_budget_bytes"] < minimum_vector_bytes:
        raise ProductionEmbeddingCandidateError("production_vector_disk_budget_exceeded")

def _manifest_object(payload: bytes) -> dict[str, Any]:
    try:
        return _strict_json_object(payload)
    except ProductionEmbeddingCandidateConfigError:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid") from None


def _matches_frozen_source_scope(value: Any) -> bool:
    expected = dict(FROZEN_R9_SOURCE_SCOPE)
    return (
        type(value) is dict
        and set(value) == set(expected)
        and all(
            type(value[key]) is type(expected[key]) and value[key] == expected[key]
            for key in expected
        )
    )


def _authority_database_path(
    manifest_path: Path,
    database: Mapping[str, Any],
) -> Path:
    database_name = database.get("path")
    if (
        not isinstance(database_name, str)
        or not database_name
        or Path(database_name).name != database_name
        or Path(database_name).is_absolute()
    ):
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    candidate = manifest_path.parent / database_name
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise ProductionEmbeddingCandidateError(
            "authority_database_unavailable"
        ) from None
    if resolved != candidate or not resolved.is_file() or resolved.is_symlink():
        raise ProductionEmbeddingCandidateError("authority_database_unsafe")
    return resolved


def _load_trusted_candidate_inputs(
    config: ProductionEmbeddingCandidateConfig,
) -> _TrustedCandidateInputs:
    try:
        manifest_bytes = config.authority_manifest_path.read_bytes()
    except OSError:
        raise ProductionEmbeddingCandidateError(
            "authority_manifest_unreadable"
        ) from None
    if hashlib.sha256(manifest_bytes).hexdigest() != config.authority_manifest_sha256:
        raise ProductionEmbeddingCandidateError("authority_manifest_hash_mismatch")
    manifest = _manifest_object(manifest_bytes)
    if set(manifest) != {
        "schema_version",
        "release_id",
        "status",
        "authority",
        "source_scope",
        "database",
        "build",
        "counts",
        "sources",
    }:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    release_id = manifest.get("release_id")
    if (
        manifest.get("schema_version") != AUTHORITY_SCHEMA_VERSION
        or manifest.get("status") not in {"candidate", "active"}
        or manifest.get("authority")
        != {"owner": "rag_chunks.db", "join_key": "chunk_id"}
        or not _matches_frozen_source_scope(manifest.get("source_scope"))
        or not isinstance(release_id, str)
        or not _SAFE_AUTHORITY_RELEASE_ID.fullmatch(release_id)
    ):
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")

    database = manifest.get("database")
    if not isinstance(database, Mapping) or set(database) != {
        "path",
        "sha256",
        "mode",
        "sqlite_user_version",
        "integrity_check",
        "foreign_key_violation_count",
    }:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    database_sha256 = database.get("sha256")
    if (
        not isinstance(database_sha256, str)
        or not _SHA256.fullmatch(database_sha256)
        or database.get("mode") != "0600"
        or isinstance(database.get("sqlite_user_version"), bool)
        or not isinstance(database.get("sqlite_user_version"), int)
        or database.get("sqlite_user_version") != 1
        or database.get("integrity_check") != "ok"
        or isinstance(database.get("foreign_key_violation_count"), bool)
        or not isinstance(database.get("foreign_key_violation_count"), int)
        or database.get("foreign_key_violation_count") != 0
        or release_id.rsplit(":", 1)[-1] != database_sha256[:16]
    ):
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    database_path = _authority_database_path(config.authority_manifest_path, database)

    build = manifest.get("build")
    if not isinstance(build, Mapping) or set(build) != {
        "extractor_version",
        "chunking_policy",
        "import_run_id",
        "network_calls",
        "old_authority_reused",
        "ocr_runtime",
    }:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    extractor_version = build.get("extractor_version")
    chunking_policy = build.get("chunking_policy")
    if (
        not isinstance(extractor_version, str)
        or not extractor_version
        or extractor_version != extractor_version.strip()
        or not isinstance(chunking_policy, str)
        or not chunking_policy
        or chunking_policy != chunking_policy.strip()
        or not isinstance(build.get("import_run_id"), str)
        or not build.get("import_run_id")
        or isinstance(build.get("network_calls"), bool)
        or not isinstance(build.get("network_calls"), int)
        or build.get("network_calls") != 0
        or build.get("old_authority_reused") is not False
    ):
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    chunking_identity_sha256 = _canonical_sha256(
        {
            "chunking_policy": chunking_policy,
            "extractor_version": extractor_version,
        }
    )

    counts = manifest.get("counts")
    if not isinstance(counts, Mapping) or set(counts) != {
        "documents",
        "chunks",
        "provenance",
    }:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    expected_documents = _positive_count(counts.get("documents"))
    expected_chunks = _positive_count(counts.get("chunks"))
    if (
        expected_documents != FROZEN_R9_SOURCE_SCOPE["source_count"]
        or _positive_count(counts.get("provenance")) != expected_chunks
    ):
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")

    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != expected_documents:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
    source_names: set[str] = set()
    folded_source_names: set[str] = set()
    source_chunk_counts: dict[str, int] = {}
    source_text_sha256: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, Mapping) or set(source) != {
            "relative_path",
            "source_sha256",
            "extracted_text_sha256",
            "chunk_count",
            "page_count",
        }:
            raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
        relative_path = source.get("relative_path")
        try:
            canonical_relative_path = _canonical_relative(relative_path)
        except ProductionEmbeddingCandidateError:
            raise ProductionEmbeddingCandidateError(
                "authority_manifest_invalid"
            ) from None
        folded_relative_path = unicodedata.normalize(
            "NFC", canonical_relative_path
        ).casefold()
        if (
            relative_path != canonical_relative_path
            or relative_path in source_names
            or folded_relative_path in folded_source_names
            or not _SHA256.fullmatch(str(source.get("source_sha256") or ""))
            or not _SHA256.fullmatch(
                str(source.get("extracted_text_sha256") or "")
            )
        ):
            raise ProductionEmbeddingCandidateError("authority_manifest_invalid")
        source_names.add(relative_path)
        folded_source_names.add(folded_relative_path)
        source_text_sha256[relative_path] = str(source["extracted_text_sha256"])
        source_chunk_counts[relative_path] = _positive_count(
            source.get("chunk_count")
        )
        _positive_count(source.get("page_count"))
    if sum(source_chunk_counts.values()) != expected_chunks:
        raise ProductionEmbeddingCandidateError("authority_manifest_invalid")

    reader: ReadOnlyAuthorityReader | None = None
    try:
        reader = ReadOnlyAuthorityReader(database_path)
        if reader.database_sha256 != database_sha256:
            raise ProductionEmbeddingCandidateError(
                "authority_database_hash_mismatch"
            )
        if (
            reader.user_version() != database["sqlite_user_version"]
            or reader.integrity_check() != "ok"
            or reader.foreign_key_violation_count()
        ):
            raise ProductionEmbeddingCandidateError(
                "authority_database_integrity_failed"
            )
        if not _AUTHORITY_TABLES.issubset(reader.table_names()):
            raise ProductionEmbeddingCandidateError("authority_schema_incomplete")
        rows = reader.embedding_chunk_rows()
        reader.validate_provenance_bindings(source_text_sha256)
        provenance_ids = reader.provenance_chunk_ids()
        chunk_documents = reader.chunk_document_map()
        database_sources = reader.source_records()
        document_counts = reader.document_chunk_counts()
        reader.verify_unchanged()
    except ProductionEmbeddingCandidateError:
        raise
    except SQLiteSemanticValidationError as exc:
        raise ProductionEmbeddingCandidateError(exc.code) from None
    except ReadOnlySQLiteError:
        raise ProductionEmbeddingCandidateError(
            "authority_database_read_failed"
        ) from None
    finally:
        if reader is not None:
            try:
                reader.close()
            except ReadOnlySQLiteError:
                raise ProductionEmbeddingCandidateError(
                    "authority_database_read_failed"
                ) from None

    chunk_ids = [str(row.get("chunk_id") or "") for row in rows]
    row_chunk_documents = {
        str(row.get("chunk_id") or ""): str(row.get("doc_name") or "")
        for row in rows
    }
    row_document_names = {str(row.get("doc_name") or "") for row in rows}
    actual_chunk_counts: dict[str, int] = {}
    for doc_name in chunk_documents.values():
        actual_chunk_counts[doc_name] = actual_chunk_counts.get(doc_name, 0) + 1
    if (
        len(rows) != expected_chunks
        or len(chunk_ids) != len(set(chunk_ids))
        or set(chunk_ids) != set(provenance_ids)
        or len(chunk_documents) != len(rows)
        or chunk_documents != row_chunk_documents
        or len(database_sources) != expected_documents
        or len(document_counts) != expected_documents
        or set(document_counts) != source_names
        or {str(row.get("doc_name") or "") for row in database_sources}
        != source_names
        or row_document_names != source_names
        or document_counts != source_chunk_counts
        or actual_chunk_counts != source_chunk_counts
    ):
        raise ProductionEmbeddingCandidateError("authority_coverage_mismatch")

    per_document_indexes: dict[str, list[int]] = {}
    chunk_records: list[_EmbeddingCandidateRecord] = []
    for row in rows:
        chunk_id = str(row.get("chunk_id") or "")
        text = row.get("text")
        doc_name = str(row.get("doc_name") or "")
        chunk_index = row.get("chunk_index")
        content_type = row.get("content_type")
        if (
            not chunk_id
            or chunk_id != chunk_id.strip()
            or not isinstance(text, str)
            or not text.strip()
            or isinstance(chunk_index, bool)
            or not isinstance(chunk_index, int)
            or chunk_index < 0
            or not isinstance(content_type, str)
            or not content_type
            or content_type != content_type.strip()
        ):
            raise ProductionEmbeddingCandidateError("authority_coverage_mismatch")
        per_document_indexes.setdefault(doc_name, []).append(chunk_index)
        chunk_records.append(
            _EmbeddingCandidateRecord(
                object_id=chunk_id,
                text=text,
                metadata={
                    "authority_release_id": release_id,
                    "content_type": content_type,
                },
            )
        )
    if any(
        sorted(indexes) != list(range(len(indexes)))
        for indexes in per_document_indexes.values()
    ):
        raise ProductionEmbeddingCandidateError("authority_coverage_mismatch")

    try:
        graph_package = load_scoped_graph_package(
            config.graph_manifest_path,
            authority_chunk_documents=chunk_documents,
        )
    except ScopedGraphContractError:
        raise ProductionEmbeddingCandidateError("graph_package_invalid") from None
    try:
        source_hashes_unchanged = (
            _sha256_file(config.authority_manifest_path)
            == config.authority_manifest_sha256
            and _sha256_file(config.graph_manifest_path)
            == config.graph_manifest_sha256
            and _sha256_file(graph_package.graph_path)
            == graph_package.graph_sha256
        )
    except OSError:
        raise ProductionEmbeddingCandidateError("source_inputs_changed") from None
    if not source_hashes_unchanged:
        raise ProductionEmbeddingCandidateError("source_inputs_changed")
    if (
        graph_package.manifest_sha256 != config.graph_manifest_sha256
        or graph_package.authority_database_sha256 != database_sha256
        or graph_package.authority_release_id != release_id
        or set(graph_package.chunk_ids) != set(chunk_ids)
    ):
        raise ProductionEmbeddingCandidateError("graph_authority_binding_mismatch")

    entity_records = tuple(
        _EmbeddingCandidateRecord(
            object_id=str(entity["entity_id"]),
            text=str(entity["canonical_name"]),
            metadata={
                "authority_release_id": release_id,
                "entity_type": str(entity["entity_type"]),
            },
        )
        for entity in graph_package.entities
    )
    if not entity_records or len(entity_records) != len(set(graph_package.entity_ids)):
        raise ProductionEmbeddingCandidateError("graph_entity_coverage_mismatch")

    contract = config.vector_contract
    if (
        contract.authority_manifest_sha256 != config.authority_manifest_sha256
        or contract.chunking_identity_sha256 != chunking_identity_sha256
        or contract.data_release_id
        != local_data_release_id(
            database_sha256,
            contract.embedding_identity_sha256,
        )
        or dict(contract.metadata_allowlist) != _VECTOR_METADATA
        or max(len(chunk_records), len(entity_records))
        > contract.max_vectors_per_index
    ):
        raise ProductionEmbeddingCandidateError("vector_contract_source_mismatch")
    return _TrustedCandidateInputs(
        authority_release_id=release_id,
        authority_database_sha256=database_sha256,
        graph_package=graph_package,
        chunk_records=tuple(chunk_records),
        entity_records=entity_records,
    )


def _metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProductionEmbeddingCandidateError("candidate_input_invalid")
        return value
    if type(value) is list and all(isinstance(item, str) for item in value):
        return list(value)
    raise ProductionEmbeddingCandidateError("candidate_input_invalid")


def _candidate_inputs(
    kind: str,
    records: Sequence[_EmbeddingCandidateRecord],
    *,
    contract: LocalVectorContract,
    meter: Callable[[str], int],
    maximum_input_units: int,
) -> tuple[
    tuple[EmbeddingInput, ...],
    tuple[_EmbeddingCandidateRecord, ...],
]:
    if not records or len(records) > contract.max_vectors_per_index:
        raise ProductionEmbeddingCandidateError("candidate_input_invalid")
    allowed_metadata = frozenset(contract.metadata_allowlist[kind])
    inputs: list[EmbeddingInput] = []
    normalized: list[_EmbeddingCandidateRecord] = []
    seen: set[str] = set()
    for record in records:
        if (
            not isinstance(record, _EmbeddingCandidateRecord)
            or not isinstance(record.object_id, str)
            or not record.object_id
            or record.object_id != record.object_id.strip()
            or record.object_id in seen
            or not isinstance(record.text, str)
            or not record.text.strip()
        ):
            raise ProductionEmbeddingCandidateError("candidate_input_invalid")
        seen.add(record.object_id)
        if not isinstance(record.metadata, Mapping):
            raise ProductionEmbeddingCandidateError("candidate_input_invalid")
        if set(record.metadata) != allowed_metadata:
            raise ProductionEmbeddingCandidateError("candidate_input_invalid")
        metadata = {
            key: _metadata_value(value) for key, value in record.metadata.items()
        }
        try:
            input_units = meter(record.text)
        except Exception:
            raise ProductionEmbeddingCandidateError("input_meter_failure") from None
        if (
            isinstance(input_units, bool)
            or not isinstance(input_units, int)
            or input_units <= 0
            or input_units > maximum_input_units
        ):
            raise ProductionEmbeddingCandidateError("candidate_input_invalid")
        inputs.append(EmbeddingInput(record.object_id, record.text, input_units))
        normalized.append(
            _EmbeddingCandidateRecord(record.object_id, record.text, metadata)
        )
    return tuple(inputs), tuple(normalized)


def _embedding_transport(
    config: ProviderRuntimeConfig,
    identity: EmbeddingIdentity,
    policy: EmbeddingPolicy,
) -> ProviderHTTPTransport:
    embedding = config.embedding
    if embedding is None:
        raise ProviderRuntimeConfigError("provider_embedding_config_required")
    secret = resolve_secret(embedding.secret_ref, os.environ)
    header_name, header_value = authorization_header(embedding.auth, secret)
    response_mapping: dict[str, Any] = {
        "vectors_pointer": embedding.wire.vectors_pointer,
        "values_pointer": embedding.wire.values_pointer,
        "match_by": embedding.wire.match_by,
    }
    if embedding.wire.id_pointer is not None:
        response_mapping["id_pointer"] = embedding.wire.id_pointer
    try:
        return ProviderHTTPTransport(
            endpoint=identity.base_url,
            request_template=embedding.wire.body_template,
            response_kind="embedding",
            response_mapping=response_mapping,
            input_meter_id=embedding.meters.input_meter_id,
            output_meter_id=embedding.meters.output_meter_id,
            cost_meter_id=embedding.meters.cost_meter_id,
            maximum_cost_microunits=policy.max_cost_microunits_per_request,
            secret_headers={header_name: header_value},
            max_request_bytes=policy.max_request_bytes,
            max_response_bytes=policy.max_response_bytes,
        )
    except Exception:
        raise ProductionEmbeddingCandidateError(
            "embedding_transport_invalid"
        ) from None


def _prepare_candidate(
    *,
    config: ProductionEmbeddingCandidateConfig,
    production_vector_build_contract_path: str | Path,
) -> _PreparedCandidate:
    environment = os.environ
    expected_contract_sha256 = _expected_contract_sha256(environment)
    expected_base_suite_manifest_sha256 = (
        _expected_base_suite_manifest_sha256(environment)
    )
    if not isinstance(config, ProductionEmbeddingCandidateConfig):
        raise ProductionEmbeddingCandidateConfigError("candidate_config_required")
    initial_identity, _initial_policy, _initial_bindings = _binding_contract(
        config.provider_config,
        config.vector_contract,
    )
    _path, _payload, anchored_contract = (
        _load_anchored_production_vector_build_contract(
            contract_path=production_vector_build_contract_path,
            expected_sha256=expected_contract_sha256,
            config=config,
        )
    )
    _validate_candidate_config_contract_binding(
        contract=anchored_contract,
        config=config,
        identity=initial_identity,
    )
    current = _reload_bound_config(config)
    provider = current.provider_config
    require_https_network_mode(provider, environment)
    identity, policy, bindings = _binding_contract(
        provider, current.vector_contract
    )
    approved_production = _validate_approval(
        provider,
        environment,
    )
    _validate_local_vector_approval(
        config=current,
        identity=identity,
        approved_production=approved_production,
    )
    _validate_approved_production_contract_binding(
        contract=anchored_contract,
        approved_production=approved_production,
    )
    production_vector_build_contract_sha256 = (
        _validate_production_vector_build_contract(
            contract_path=production_vector_build_contract_path,
            expected_sha256=expected_contract_sha256,
            expected_base_suite_manifest_sha256=(
                expected_base_suite_manifest_sha256
            ),
            config=current,
            identity=identity,
            approved_production=approved_production,
        )
    )
    trusted = _load_trusted_candidate_inputs(current)
    _validate_candidate_capacity(
        approved_production=approved_production,
        chunk_count=len(trusted.chunk_records),
        entity_count=len(trusted.entity_records),
        dimension=identity.dimension,
        dtype=current.vector_contract.dtype,
    )
    contract = current.vector_contract
    if (
        contract.candidate_release_dir.exists()
        or contract.candidate_release_dir.is_symlink()
    ):
        raise ProductionEmbeddingCandidateError("candidate_already_exists")
    try:
        vector_adapter = LocalVectorStoreAdapter(contract)
    except Exception:
        raise ProductionEmbeddingCandidateError("vector_engine_unavailable") from None
    embedding = provider.embedding
    if embedding is None:
        raise ProviderRuntimeConfigError("provider_embedding_config_required")
    try:
        input_meter = resolve_meter(embedding.meters.input_meter_id)
    except ProviderMeterError:
        raise ProductionEmbeddingCandidateError("input_meter_failure") from None
    chunk_inputs, chunks = _candidate_inputs(
        "chunk",
        trusted.chunk_records,
        contract=contract,
        meter=input_meter,
        maximum_input_units=policy.max_input_units,
    )
    entity_inputs, entities = _candidate_inputs(
        "entity",
        trusted.entity_records,
        contract=contract,
        meter=input_meter,
        maximum_input_units=policy.max_input_units,
    )
    _embedding_transport(
        provider,
        identity,
        policy,
    )
    return _PreparedCandidate(
        config=current,
        identity=identity,
        policy=policy,
        bindings=bindings,
        production_vector_build_contract_sha256=(
            production_vector_build_contract_sha256
        ),
        trusted=trusted,
        chunk_inputs=chunk_inputs,
        chunks=chunks,
        entity_inputs=entity_inputs,
        entities=entities,
        vector_adapter=vector_adapter,
        input_meter=input_meter,
    )


def _validation(
    prepared: _PreparedCandidate,
) -> ProductionEmbeddingCandidateValidation:
    config = prepared.config
    trusted = prepared.trusted
    return ProductionEmbeddingCandidateValidation(
        config_sha256=config.sha256,
        provider_config_sha256=config.provider_config.sha256,
        production_vector_build_contract_sha256=(
            prepared.production_vector_build_contract_sha256
        ),
        authority_release_id=trusted.authority_release_id,
        authority_manifest_sha256=config.authority_manifest_sha256,
        authority_database_sha256=trusted.authority_database_sha256,
        graph_release_id=trusted.graph_package.graph_release_id,
        graph_manifest_sha256=config.graph_manifest_sha256,
        chunk_count=len(prepared.chunks),
        entity_count=len(prepared.entities),
        candidate_release_dir=config.vector_contract.candidate_release_dir,
    )


def _validate_production_embedding_candidate_impl(
    *,
    config: ProductionEmbeddingCandidateConfig,
    production_vector_build_contract_path: str | Path,
) -> ProductionEmbeddingCandidateValidation:
    """Validate all bindings and dependencies without provider calls."""

    prepared = _prepare_candidate(
        config=config,
        production_vector_build_contract_path=production_vector_build_contract_path,
    )
    return _validation(prepared)


def _build_production_embedding_candidate_impl(
    *,
    config: ProductionEmbeddingCandidateConfig,
    production_vector_build_contract_path: str | Path,
    _bootstrap_guard: Callable[[], None] | None = None,
) -> ProductionEmbeddingCandidateReceipt:
    """Embed the sealed complete source sets and write one candidate pair."""

    prepared = _prepare_candidate(
        config=config,
        production_vector_build_contract_path=production_vector_build_contract_path,
    )
    provider = prepared.config.provider_config
    embedding = provider.embedding
    if embedding is None:
        raise ProviderRuntimeConfigError("provider_embedding_config_required")
    if _bootstrap_guard is not None:
        _bootstrap_guard()
    transport = _embedding_transport(
        provider,
        prepared.identity,
        prepared.policy,
    )
    adapter = EmbeddingAdapter(
        prepared.identity,
        policy=prepared.policy,
        transport=transport,
        transport_mode="external_process",
        input_unit_meter=prepared.input_meter,
    )
    if _bootstrap_guard is not None:
        _bootstrap_guard()
    try:
        chunk_result = adapter.embed_build(prepared.chunk_inputs)
    except EmbeddingError as exc:
        raise ProductionEmbeddingCandidateError(
            "chunk_embedding_failed",
            chunk_ledger=exc.ledger,
            emit_ledgers=True,
        ) from None
    if _bootstrap_guard is not None:
        _bootstrap_guard()
    try:
        entity_result = adapter.embed_entity(prepared.entity_inputs)
    except EmbeddingError as exc:
        raise ProductionEmbeddingCandidateError(
            "entity_embedding_failed",
            chunk_ledger=chunk_result.ledger,
            entity_ledger=exc.ledger,
            emit_ledgers=True,
        ) from None
    if (
        chunk_result.identity_sha256 != prepared.identity.sha256
        or entity_result.identity_sha256 != prepared.identity.sha256
    ):
        raise ProductionEmbeddingCandidateError(
            "embedding_identity_mismatch",
            chunk_ledger=chunk_result.ledger,
            entity_ledger=entity_result.ledger,
            emit_ledgers=True,
        )
    chunk_vectors = chunk_result.by_id()
    entity_vectors = entity_result.by_id()
    chunk_ids = tuple(record.object_id for record in prepared.chunks)
    entity_ids = tuple(record.object_id for record in prepared.entities)
    if set(chunk_vectors) != set(chunk_ids) or set(entity_vectors) != set(entity_ids):
        raise ProductionEmbeddingCandidateError(
            "embedding_coverage_mismatch",
            chunk_ledger=chunk_result.ledger,
            entity_ledger=entity_result.ledger,
            emit_ledgers=True,
        )

    if _bootstrap_guard is not None:
        _bootstrap_guard()
    try:
        local_receipt = prepared.vector_adapter.build_candidate(
            chunk_records=tuple(
                VectorRecord(
                    object_id=record.object_id,
                    vector=chunk_vectors[record.object_id],
                    metadata=record.metadata,
                )
                for record in prepared.chunks
            ),
            entity_records=tuple(
                VectorRecord(
                    object_id=record.object_id,
                    vector=entity_vectors[record.object_id],
                    metadata=record.metadata,
                )
                for record in prepared.entities
            ),
            expected_ids={"chunk": chunk_ids, "entity": entity_ids},
        )
    except Exception:
        raise ProductionEmbeddingCandidateError(
            "candidate_write_failed",
            chunk_ledger=chunk_result.ledger,
            entity_ledger=entity_result.ledger,
            emit_ledgers=True,
        ) from None
    contract = prepared.config.vector_contract
    if local_receipt.release_dir != contract.candidate_release_dir:
        raise ProductionEmbeddingCandidateError(
            "candidate_layout_mismatch",
            chunk_ledger=chunk_result.ledger,
            entity_ledger=entity_result.ledger,
            emit_ledgers=True,
        )
    trusted = prepared.trusted
    return ProductionEmbeddingCandidateReceipt(
        local_vector=local_receipt,
        purpose_bindings=prepared.bindings,
        wire_contract_sha256=embedding.wire.wire_contract_sha256,
        provider_config_sha256=provider.sha256,
        provider_contract_sha256=provider.contract_sha256,
        production_vector_build_contract_sha256=(
            prepared.production_vector_build_contract_sha256
        ),
        config_sha256=prepared.config.sha256,
        authority_release_id=trusted.authority_release_id,
        authority_manifest_sha256=prepared.config.authority_manifest_sha256,
        authority_database_sha256=trusted.authority_database_sha256,
        graph_release_id=trusted.graph_package.graph_release_id,
        graph_manifest_sha256=prepared.config.graph_manifest_sha256,
        model=prepared.identity.model,
        model_version=prepared.identity.model_version,
        dimension=prepared.identity.dimension,
        normalization=prepared.identity.normalization,
        chunk_ledger=chunk_result.ledger,
        entity_ledger=entity_result.ledger,
    )


def _validated_exact_release_identity(
    value: Any,
) -> tuple[dict[str, str], object, object]:
    fields = {
        "schema_version",
        "bootstrap_sha256",
        "candidate_sha256",
        "runtime_lock_sha256",
        "builder_file_set_sha256",
        "exact_import_root_sha256",
    }
    loader = globals().get("__loader__")
    held_source = getattr(loader, "source", None)
    payload = getattr(held_source, "payload", None)
    expected_root_sha256 = hashlib.sha256(
        str(Path(__file__).resolve().parents[2]).encode("utf-8")
    ).hexdigest()
    if (
        type(value) is not dict
        or set(value) != fields
        or value.get("schema_version") != BOOTSTRAP_CONTEXT_SCHEMA_VERSION
        or any(
            type(value.get(field)) is not str
            or not _SHA256.fullmatch(value[field])
            for field in fields - {"schema_version"}
        )
        or type(loader).__name__ != "_HeldSourceLoader"
        or type(loader).__module__ != "__main__"
        or getattr(loader, "source_sha256", None) != value.get("candidate_sha256")
        or getattr(held_source, "module", None) != __name__
        or getattr(held_source, "sha256", None) != value.get("candidate_sha256")
        or type(payload) is not bytes
        or hashlib.sha256(payload).hexdigest() != value.get("candidate_sha256")
        or value.get("runtime_lock_sha256")
        != os.environ.get(RUNTIME_LOCK_SHA256_ENV)
        or value.get("exact_import_root_sha256") != expected_root_sha256
    ):
        raise ProductionEmbeddingCandidateError("exact_release_bootstrap_required")
    return dict(value), loader, held_source


def _current_exact_release_action_closure() -> tuple[object, ...]:
    return (
        _current_exact_release_action_closure,
        _require_exact_release_bootstrap_context,
        _parser,
        _run_cli,
        _run_cli_impl,
        materialize_production_vector_build_contract,
        validate_production_embedding_candidate,
        build_production_embedding_candidate,
        _materialize_production_vector_build_contract_impl,
        _validate_production_embedding_candidate_impl,
        _build_production_embedding_candidate_impl,
    )


def _require_exact_release_bootstrap_context(
    action: str,
    *,
    expected_context: _ActiveBootstrapContext | None = None,
) -> _ActiveBootstrapContext:
    active = _ACTIVE_BOOTSTRAP_CONTEXT
    if (
        action not in {"cli", "materialize", "validate", "build"}
        or type(active) is not _ActiveBootstrapContext
        or active.nonce is not _BOOTSTRAP_CONTEXT_NONCE
        or (expected_context is not None and active is not expected_context)
        or globals().get("__loader__") is not active.loader
        or getattr(active.loader, "source", None) is not active.held_source
        or getattr(active.verifier, "__self__", None) is not active.verifier_owner
        or getattr(active.verifier, "__func__", None) is not active.verifier_function
        or getattr(
            type(active.verifier_owner),
            "revalidate_candidate",
            None,
        )
        is not active.verifier_function
        or len(active.action_closure) != 11
    ):
        raise ProductionEmbeddingCandidateError("exact_release_bootstrap_required")
    if any(
        current is not expected
        for current, expected in zip(
            _current_exact_release_action_closure(),
            active.action_closure,
            strict=True,
        )
    ):
        raise ProductionEmbeddingCandidateError(
            "exact_release_bootstrap_source_or_action_changed"
        )
    try:
        observed = active.verifier()
        identity, loader, held_source = _validated_exact_release_identity(observed)
    except ProductionEmbeddingCandidateError:
        raise
    except Exception:
        raise ProductionEmbeddingCandidateError(
            "exact_release_bootstrap_source_or_action_changed"
        ) from None
    if (
        identity != dict(active.identity)
        or loader is not active.loader
        or held_source is not active.held_source
    ):
        raise ProductionEmbeddingCandidateError(
            "exact_release_bootstrap_source_or_action_changed"
        )
    return active


def materialize_production_vector_build_contract(
    *,
    config: ProductionEmbeddingCandidateConfig,
    output_path: str | Path,
) -> ProductionVectorContractMaterialization:
    """Create one configured contract only under the held-byte bootstrap."""

    active = _require_exact_release_bootstrap_context("materialize")
    guard = lambda: _require_exact_release_bootstrap_context(
        "materialize", expected_context=active
    )
    result = _materialize_production_vector_build_contract_impl(
        config=config,
        output_path=output_path,
        _bootstrap_guard=guard,
    )
    guard()
    return result


def validate_production_embedding_candidate(
    *,
    config: ProductionEmbeddingCandidateConfig,
    production_vector_build_contract_path: str | Path,
) -> ProductionEmbeddingCandidateValidation:
    """Validate a candidate only under the held-byte bootstrap."""

    active = _require_exact_release_bootstrap_context("validate")
    result = _validate_production_embedding_candidate_impl(
        config=config,
        production_vector_build_contract_path=production_vector_build_contract_path,
    )
    _require_exact_release_bootstrap_context("validate", expected_context=active)
    return result


def build_production_embedding_candidate(
    *,
    config: ProductionEmbeddingCandidateConfig,
    production_vector_build_contract_path: str | Path,
) -> ProductionEmbeddingCandidateReceipt:
    """Build a candidate only under the held-byte bootstrap."""

    active = _require_exact_release_bootstrap_context("build")
    guard = lambda: _require_exact_release_bootstrap_context(
        "build", expected_context=active
    )
    result = _build_production_embedding_candidate_impl(
        config=config,
        production_vector_build_contract_path=production_vector_build_contract_path,
        _bootstrap_guard=guard,
    )
    guard()
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    materialize = subparsers.add_parser("materialize")
    materialize.add_argument("--config", required=True)
    materialize.add_argument("--output", required=True)
    for command in ("validate", "build"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", required=True)
        subparser.add_argument("--contract", required=True)
    return parser


def _run_cli_impl(
    argv: Sequence[str] | None = None,
    *,
    _action_closure: tuple[object, ...] | None = None,
    _bootstrap_guard: Callable[[], None] | None = None,
) -> int:
    actions = (
        (
            _parser,
            _materialize_production_vector_build_contract_impl,
            _validate_production_embedding_candidate_impl,
            _build_production_embedding_candidate_impl,
        )
        if _action_closure is None
        else _action_closure
    )
    if len(actions) != 4 or any(not callable(action) for action in actions):
        raise ProductionEmbeddingCandidateError("candidate_cli_action_closure_invalid")
    parser_action, materialize_action, validate_action, build_action = actions
    args = parser_action().parse_args(argv)
    try:
        config = ProductionEmbeddingCandidateConfig.load(args.config)
        if args.command == "materialize":
            result = materialize_action(
                config=config,
                output_path=args.output,
            ).as_dict()
            result.update({"command": "materialize", "ok": True})
        elif args.command == "validate":
            result = validate_action(
                config=config,
                production_vector_build_contract_path=args.contract,
            ).as_dict()
            result.update({"command": "validate", "ok": True})
        else:
            result = build_action(
                config=config,
                production_vector_build_contract_path=args.contract,
            ).as_dict()
            result.update({"command": "build", "ok": True})
    except (
        ProductionEmbeddingCandidateConfigError,
        ProductionEmbeddingCandidateError,
        ProviderBootstrapError,
        ProviderRuntimeConfigError,
        ReadOnlySQLiteError,
        ScopedGraphContractError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        failure = {
            "command": getattr(args, "command", "unknown"),
            "error": "production_embedding_candidate_failed",
            "ok": False,
        }
        if (
            isinstance(exc, ProductionEmbeddingCandidateError)
            and exc.emit_ledgers
        ):
            failure.update(exc.ledger_dict())
        if _bootstrap_guard is not None:
            _bootstrap_guard()
        print(
            json.dumps(
                failure,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    if _bootstrap_guard is not None:
        _bootstrap_guard()
    print(
        json.dumps(
            result,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def _activate_exact_release_bootstrap_context(
    context: object,
) -> _ActiveBootstrapContext:
    if (
        _ACTIVE_BOOTSTRAP_CONTEXT is not None
        or type(context).__name__ != "_ProductionEmbeddingBootstrapContext"
        or type(context).__module__ != "__main__"
    ):
        raise ProductionEmbeddingCandidateError("exact_release_bootstrap_required")
    try:
        verifier = getattr(context, "revalidate_candidate")
    except Exception:
        raise ProductionEmbeddingCandidateError(
            "exact_release_bootstrap_required"
        ) from None
    verifier_function = getattr(verifier, "__func__", None)
    if (
        not callable(verifier)
        or getattr(verifier, "__self__", None) is not context
        or verifier_function is None
        or getattr(type(context), "revalidate_candidate", None)
        is not verifier_function
    ):
        raise ProductionEmbeddingCandidateError("exact_release_bootstrap_required")
    try:
        identity, loader, held_source = _validated_exact_release_identity(verifier())
    except ProductionEmbeddingCandidateError:
        raise
    except Exception:
        raise ProductionEmbeddingCandidateError(
            "exact_release_bootstrap_required"
        ) from None
    return _ActiveBootstrapContext(
        identity=identity,
        verifier=verifier,
        verifier_owner=context,
        verifier_function=verifier_function,
        action_closure=_current_exact_release_action_closure(),
        loader=loader,
        held_source=held_source,
        nonce=_BOOTSTRAP_CONTEXT_NONCE,
    )


def _run_cli(argv: Sequence[str] | None = None) -> int:
    active = _require_exact_release_bootstrap_context("cli")
    actions = active.action_closure
    return _run_cli_impl(
        argv,
        _action_closure=(actions[2], actions[5], actions[6], actions[7]),
        _bootstrap_guard=lambda: _require_exact_release_bootstrap_context(
            "cli", expected_context=active
        ),
    )


def _run_from_exact_release_bootstrap(
    argv: Sequence[str],
    context: object,
) -> int:
    global _ACTIVE_BOOTSTRAP_CONTEXT
    active = _activate_exact_release_bootstrap_context(context)
    _ACTIVE_BOOTSTRAP_CONTEXT = active
    try:
        return _run_cli(argv)
    finally:
        _ACTIVE_BOOTSTRAP_CONTEXT = None


def main(argv: Sequence[str] | None = None) -> int:
    command = "unknown"
    if argv:
        command = str(argv[0])
    elif len(sys.argv) > 1:
        command = str(sys.argv[1])
    print(
        json.dumps(
            {
                "command": command,
                "error": "exact_release_bootstrap_required",
                "ok": False,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 1


__all__ = [
    "BASE_PRODUCTION_VECTOR_BUILD_CONTRACT_SCHEMA_VERSION",
    "BASE_SUITE_MANIFEST_SHA256_ENV",
    "CONFIG_SCHEMA_VERSION",
    "PRODUCTION_VECTOR_BUILD_CONTRACT_SCHEMA_VERSION",
    "PRODUCTION_VECTOR_BUILD_CONTRACT_SHA256_ENV",
    "ProductionEmbeddingCandidateConfig",
    "ProductionEmbeddingCandidateConfigError",
    "ProductionEmbeddingCandidateError",
    "ProductionEmbeddingCandidateReceipt",
    "ProductionEmbeddingCandidateValidation",
    "ProductionVectorContractMaterialization",
    "PurposeEmbeddingBinding",
    "build_production_embedding_candidate",
    "local_data_release_id",
    "main",
    "materialize_production_vector_build_contract",
    "validate_production_embedding_candidate",
]


if __name__ == "__main__":
    raise SystemExit(main())
