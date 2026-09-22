#!/usr/bin/env python3
"""USEarch-backed candidate builder and immutable active vector view.

This module wraps the mature ANN core from ``usearch==2.26.2``.  It does not
implement ANN algorithms, active switching, or deletion.  The only destructive
output is a reviewable exact-path deletion plan for a separate approved release
controller.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

try:
    import usearch
    from usearch.index import Index, search as usearch_search
except (ImportError, OSError) as exc:  # pragma: no cover - exercised in a subprocess
    # Keep contracts importable for offline validation, but never emulate ANN
    # behavior when the frozen binary dependency is unavailable.
    usearch = None  # type: ignore[assignment]
    Index = None  # type: ignore[assignment]
    usearch_search = None  # type: ignore[assignment]
    _USEARCH_IMPORT_ERROR: BaseException | None = exc
else:
    _USEARCH_IMPORT_ERROR = None


ENGINE_NAME = "usearch"
ENGINE_VERSION = "2.26.2"
INDEX_BUILD_THREADS = 1
MANIFEST_SCHEMA_VERSION = "kg-local-vector-manifest-v2"
MANIFEST_INTEGER_KEY_PREFIX = "u64:"
MANIFEST_INTEGER_KEY_HEX_LENGTH = 16
ACTIVE_STATE_SCHEMA_VERSION = "kg-local-vector-active-state-v1"
ACTIVE_STATE_FILE_NAME = "active-release.json"
INDEX_KINDS = ("chunk", "entity")
_METRICS = {
    "cosine": ("cos", "MetricKind.Cos"),
    "dot": ("ip", "MetricKind.IP"),
    "euclidean": ("l2sq", "MetricKind.L2sq"),
}
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_FIELD_NAMES = frozenset(
    {"text", "content", "body", "payload", "source_text", "raw_source"}
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _encode_manifest_integer_key(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**64:
        raise LocalVectorIntegrityError("integer key is outside uint64")
    return f"{MANIFEST_INTEGER_KEY_PREFIX}{value:0{MANIFEST_INTEGER_KEY_HEX_LENGTH}x}"


def _decode_manifest_integer_key(value: Any) -> int:
    if (
        not isinstance(value, str)
        or len(value) != len(MANIFEST_INTEGER_KEY_PREFIX) + MANIFEST_INTEGER_KEY_HEX_LENGTH
        or not value.startswith(MANIFEST_INTEGER_KEY_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[len(MANIFEST_INTEGER_KEY_PREFIX):])
    ):
        raise LocalVectorIntegrityError("integer key manifest encoding is invalid")
    return int(value[len(MANIFEST_INTEGER_KEY_PREFIX):], 16)


def _safe_component(value: str, field: str) -> str:
    value = _required_text(value, field)
    if not _SAFE_COMPONENT.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{field} must be one exact path component")
    return value


def _validate_json_metadata(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata numbers must be finite")
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise ValueError("metadata values must be scalar JSON values or string lists")


@dataclass(frozen=True)
class LocalVectorContract:
    approved_data_parent: Path
    data_root: Path
    data_release_id: str
    authority_manifest_sha256: str
    chunking_identity_sha256: str
    embedding_identity_sha256: str
    dimension: int
    metric: str
    schema_version: str
    chunk_index_name: str
    entity_index_name: str
    top_k_max: int
    max_vectors_per_index: int
    metadata_allowlist: Mapping[str, Sequence[str]]
    engine: str = ENGINE_NAME
    engine_version: str = ENGINE_VERSION
    dtype: str = "f32"

    def __post_init__(self) -> None:
        approved_parent = Path(self.approved_data_parent)
        if not approved_parent.is_absolute():
            raise ValueError("approved_data_parent must be absolute")
        approved_parent = approved_parent.resolve(strict=False)
        if len(approved_parent.parts) < 3 or not approved_parent.is_dir():
            raise ValueError("approved_data_parent must be an existing narrow directory")
        if approved_parent.is_symlink():
            raise ValueError("approved_data_parent cannot be a symlink")
        object.__setattr__(self, "approved_data_parent", approved_parent)
        data_root = Path(self.data_root)
        if not data_root.is_absolute():
            raise ValueError("data_root must be an absolute versioned path")
        data_root = data_root.resolve(strict=False)
        if len(data_root.parts) < 4:
            raise ValueError("data_root must be a canonical, narrowly scoped path")
        if data_root == approved_parent or approved_parent not in data_root.parents:
            raise ValueError("data_root must be below the approved data parent")
        object.__setattr__(self, "data_root", data_root)
        object.__setattr__(
            self,
            "data_release_id",
            _safe_component(self.data_release_id, "data_release_id"),
        )
        object.__setattr__(
            self,
            "chunk_index_name",
            _safe_component(self.chunk_index_name, "chunk_index_name"),
        )
        object.__setattr__(
            self,
            "entity_index_name",
            _safe_component(self.entity_index_name, "entity_index_name"),
        )
        if self.chunk_index_name == self.entity_index_name:
            raise ValueError("chunk and entity index names must be isolated")
        for field in (
            "authority_manifest_sha256",
            "chunking_identity_sha256",
            "embedding_identity_sha256",
        ):
            if not _SHA256.fullmatch(str(getattr(self, field))):
                raise ValueError(f"{field} must be a lowercase SHA-256")
        if self.engine != ENGINE_NAME or self.engine_version != ENGINE_VERSION:
            raise ValueError("local vector engine must be the reviewed USEarch 2.26.2 candidate")
        if self.dtype != "f32":
            raise ValueError("local vector dtype must be the frozen f32 candidate")
        if self.metric not in _METRICS:
            raise ValueError("metric must be cosine, dot, or euclidean")
        object.__setattr__(
            self,
            "schema_version",
            _required_text(self.schema_version, "schema_version"),
        )
        for value, field in (
            (self.dimension, "dimension"),
            (self.top_k_max, "top_k_max"),
            (self.max_vectors_per_index, "max_vectors_per_index"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field} must be a positive integer")
        if set(self.metadata_allowlist) != set(INDEX_KINDS):
            raise ValueError("metadata_allowlist must define chunk and entity")
        normalized_allowlist: dict[str, tuple[str, ...]] = {}
        for kind in INDEX_KINDS:
            fields = tuple(self.metadata_allowlist[kind])
            if len(fields) != len(set(fields)):
                raise ValueError("metadata allowlist fields must be unique")
            normalized_fields: list[str] = []
            for field in fields:
                normalized_field = _safe_component(
                    field, f"{kind} metadata field"
                )
                lowered = normalized_field.lower()
                if lowered in _CONTENT_FIELD_NAMES:
                    raise ValueError("authoritative text or payload fields cannot enter vector metadata")
                normalized_fields.append(normalized_field)
            if len(normalized_fields) != len(set(normalized_fields)):
                raise ValueError("normalized metadata allowlist fields must be unique")
            normalized_allowlist[kind] = tuple(normalized_fields)
        object.__setattr__(
            self,
            "metadata_allowlist",
            MappingProxyType(normalized_allowlist),
        )

    @property
    def candidate_release_dir(self) -> Path:
        return self.data_root / "candidate" / self.data_release_id

    @property
    def active_release_dir(self) -> Path:
        return self.data_root / "active" / self.data_release_id

    @property
    def active_state_path(self) -> Path:
        return self.data_root / "active" / ACTIVE_STATE_FILE_NAME

    def identity_manifest(self) -> dict[str, Any]:
        return {
            "authority_manifest_sha256": self.authority_manifest_sha256,
            "chunking_identity_sha256": self.chunking_identity_sha256,
            "data_release_id": self.data_release_id,
            "dimension": self.dimension,
            "dtype": self.dtype,
            "embedding_identity_sha256": self.embedding_identity_sha256,
            "engine": self.engine,
            "engine_metric": _METRICS[self.metric][0],
            "engine_version": self.engine_version,
            "index_names": {
                "chunk": self.chunk_index_name,
                "entity": self.entity_index_name,
            },
            "index_build_threads": INDEX_BUILD_THREADS,
            "max_vectors_per_index": self.max_vectors_per_index,
            "metadata_allowlist": {
                kind: list(self.metadata_allowlist[kind]) for kind in INDEX_KINDS
            },
            "metric": self.metric,
            "schema_version": self.schema_version,
            "top_k_max": self.top_k_max,
        }


@dataclass(frozen=True)
class VectorRecord:
    object_id: str
    vector: Sequence[float]
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class CandidateBuildReceipt:
    release_dir: Path
    manifest_sha256: str
    chunk_count: int
    entity_count: int


@dataclass(frozen=True)
class VectorSearchHit:
    object_id: str
    integer_key: int
    distance: float
    metadata: Mapping[str, Any]
    index_kind: str
    data_release_id: str


@dataclass(frozen=True)
class ExactDeleteEntry:
    path: Path
    object_type: str
    sha256: str | None


@dataclass(frozen=True)
class ExactReleaseDeletePlan:
    layout: str
    data_release_id: str
    release_dir: Path
    manifest_sha256: str
    active_state_sha256: str | None
    entries: tuple[ExactDeleteEntry, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "layout": self.layout,
            "data_release_id": self.data_release_id,
            "release_dir": str(self.release_dir),
            "manifest_sha256": self.manifest_sha256,
            "active_state_sha256": self.active_state_sha256,
            "entries": [
                {
                    "path": str(item.path),
                    "object_type": item.object_type,
                    "sha256": item.sha256,
                }
                for item in self.entries
            ],
            "execution_authorized": False,
        }


class LocalVectorError(RuntimeError):
    pass


class LocalVectorIntegrityError(LocalVectorError):
    pass


def _require_usearch(error_type: type[RuntimeError], operation: str) -> None:
    """Require the reviewed USEarch runtime at an actual vector boundary."""

    if usearch is None or Index is None or usearch_search is None:
        raise error_type(
            f"{operation} requires USEarch {ENGINE_VERSION}; "
            "the frozen vector dependency is unavailable"
        ) from _USEARCH_IMPORT_ERROR
    if str(getattr(usearch, "__version__", "")) != ENGINE_VERSION:
        raise error_type("USEarch runtime version does not match the frozen candidate")


class LocalVectorStoreAdapter:
    """Build complete candidate pairs and open exact active release views."""

    def __init__(self, contract: LocalVectorContract) -> None:
        _require_usearch(LocalVectorError, "local vector operations")
        self.contract = contract

    def build_candidate(
        self,
        *,
        chunk_records: Sequence[VectorRecord],
        entity_records: Sequence[VectorRecord],
        expected_ids: Mapping[str, Sequence[str]],
    ) -> CandidateBuildReceipt:
        if set(expected_ids) != set(INDEX_KINDS):
            raise ValueError("expected_ids must define chunk and entity")
        normalized = {
            "chunk": self._normalize_records(
                "chunk", chunk_records, expected_ids["chunk"]
            ),
            "entity": self._normalize_records(
                "entity", entity_records, expected_ids["entity"]
            ),
        }
        release_dir = self.contract.candidate_release_dir
        if release_dir.exists() or release_dir.is_symlink():
            raise LocalVectorError("candidate release directory already exists")

        candidate_root = self.contract.data_root / "candidate"
        self._ensure_builder_root(candidate_root)
        stage = candidate_root / (
            f".{self.contract.data_release_id}.building-{uuid.uuid4().hex}"
        )
        stage.mkdir(mode=0o750)
        try:
            indexes: dict[str, Any] = {}
            for kind in INDEX_KINDS:
                indexes[kind] = self._build_index(stage, kind, normalized[kind])
            manifest = {
                "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
                "identity": self.contract.identity_manifest(),
                "indexes": indexes,
            }
            manifest_bytes = _canonical_json(manifest) + b"\n"
            manifest_path = stage / "local_vector_manifest.json"
            manifest_path.write_bytes(manifest_bytes)
            self._fsync_file(manifest_path)
            os.replace(stage, release_dir)
            self._fsync_directory(candidate_root)
        except Exception:
            if stage.exists() and self._is_exact_child(stage, candidate_root):
                shutil.rmtree(stage)
            raise

        return CandidateBuildReceipt(
            release_dir=release_dir,
            manifest_sha256=_sha256_bytes(manifest_bytes),
            chunk_count=len(normalized["chunk"]),
            entity_count=len(normalized["entity"]),
        )

    def open_active(
        self, *, expected_manifest_sha256: str
    ) -> "LocalVectorReadView":
        release_dir = self.contract.active_release_dir
        self._assert_release_tree(release_dir, require_read_only=True)
        manifest_path = release_dir / "local_vector_manifest.json"
        if not _SHA256.fullmatch(str(expected_manifest_sha256)):
            raise ValueError("expected_manifest_sha256 must be a lowercase SHA-256")
        if _sha256_file(manifest_path) != expected_manifest_sha256:
            raise LocalVectorIntegrityError(
                "active manifest does not match the approved candidate"
            )
        manifest = self._load_manifest(manifest_path)
        self._validate_manifest(manifest, release_dir)
        return LocalVectorReadView(self.contract, release_dir, manifest)

    def plan_exact_release_delete(
        self,
        *,
        layout: str,
        data_release_id: str,
    ) -> ExactReleaseDeletePlan:
        if layout not in {"candidate", "active"}:
            raise ValueError("layout must be candidate or active")
        release_id = _safe_component(data_release_id, "data_release_id")
        active_state_sha256: str | None = None
        if layout == "active":
            current, active_state_sha256 = self._read_current_active_release()
            if current == release_id:
                raise LocalVectorError("cannot plan deletion of the current active release")
        release_dir = self.contract.data_root / layout / release_id
        self._assert_release_tree(release_dir, require_read_only=False)
        manifest_path = release_dir / "local_vector_manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise LocalVectorIntegrityError("release manifest is missing or unsafe")

        entries: list[ExactDeleteEntry] = []
        for root, directories, files in os.walk(release_dir, followlinks=False):
            root_path = Path(root)
            for name in sorted(directories):
                path = root_path / name
                if path.is_symlink():
                    raise LocalVectorIntegrityError("release tree contains a symlink")
                entries.append(ExactDeleteEntry(path, "directory", None))
            for name in sorted(files):
                path = root_path / name
                if path.is_symlink() or not path.is_file():
                    raise LocalVectorIntegrityError("release tree contains an unsafe file")
                entries.append(ExactDeleteEntry(path, "file", _sha256_file(path)))
        entries.sort(key=lambda item: str(item.path))
        return ExactReleaseDeletePlan(
            layout=layout,
            data_release_id=release_id,
            release_dir=release_dir,
            manifest_sha256=_sha256_file(manifest_path),
            active_state_sha256=active_state_sha256,
            entries=tuple(entries),
        )

    def _read_current_active_release(self) -> tuple[str, str]:
        state_path = self.contract.active_state_path
        if not state_path.is_file() or state_path.is_symlink():
            raise LocalVectorIntegrityError("active release state is missing or unsafe")
        if stat.S_IMODE(state_path.stat().st_mode) & 0o222:
            raise LocalVectorIntegrityError("active release state must be read-only")
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalVectorIntegrityError("active release state is unreadable") from exc
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version",
            "data_release_id",
            "manifest_sha256",
        }:
            raise LocalVectorIntegrityError("active release state fields do not match the schema")
        if value["schema_version"] != ACTIVE_STATE_SCHEMA_VERSION:
            raise LocalVectorIntegrityError("active release state schema mismatch")
        try:
            release_id = _safe_component(
                value["data_release_id"], "active data_release_id"
            )
        except (TypeError, ValueError) as exc:
            raise LocalVectorIntegrityError("active release id is invalid") from exc
        manifest_sha256 = value["manifest_sha256"]
        if not _SHA256.fullmatch(str(manifest_sha256)):
            raise LocalVectorIntegrityError("active manifest SHA-256 is invalid")
        release_dir = self.contract.data_root / "active" / release_id
        self._assert_release_tree(release_dir, require_read_only=True)
        manifest_path = release_dir / "local_vector_manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise LocalVectorIntegrityError("current active manifest is missing or unsafe")
        if _sha256_file(manifest_path) != manifest_sha256:
            raise LocalVectorIntegrityError("active release state is stale")
        return release_id, _sha256_file(state_path)

    def _normalize_records(
        self,
        kind: str,
        records: Sequence[VectorRecord],
        expected_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        if not isinstance(records, Sequence) or isinstance(
            records, (str, bytes, bytearray)
        ):
            raise ValueError(f"{kind}_records must be a sequence")
        if not isinstance(expected_ids, Sequence) or isinstance(
            expected_ids, (str, bytes, bytearray)
        ):
            raise ValueError(f"expected {kind} ids must be a sequence")
        expected = [_required_text(value, f"expected {kind} id") for value in expected_ids]
        if len(expected) != len(set(expected)):
            raise LocalVectorIntegrityError("expected ids contain duplicates")
        if len(records) > self.contract.max_vectors_per_index:
            raise LocalVectorIntegrityError("vector count exceeds the frozen capacity")

        allowlist = frozenset(self.contract.metadata_allowlist[kind])
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        seen_keys: dict[int, str] = {}
        for record in records:
            if not isinstance(record, VectorRecord):
                raise ValueError("records must contain VectorRecord values")
            object_id = _required_text(record.object_id, "object_id")
            if object_id in seen:
                raise LocalVectorIntegrityError("duplicate vector object id")
            seen.add(object_id)
            vector = self._vector(record.vector)
            if not isinstance(record.metadata, Mapping):
                raise ValueError("metadata must be an object")
            unknown = set(record.metadata) - allowlist
            if unknown:
                raise LocalVectorIntegrityError("metadata contains fields outside the allowlist")
            metadata = {
                str(key): _validate_json_metadata(value)
                for key, value in record.metadata.items()
            }
            integer_key = self._stable_integer_key(kind, object_id)
            collision = seen_keys.get(integer_key)
            if collision is not None and collision != object_id:
                raise LocalVectorIntegrityError("stable integer key collision")
            seen_keys[integer_key] = object_id
            normalized.append(
                {
                    "integer_key": integer_key,
                    "object_id": object_id,
                    "vector": vector,
                    "metadata": metadata,
                }
            )
        if set(seen) != set(expected):
            raise LocalVectorIntegrityError("missing or unknown vector object ids")
        normalized.sort(key=lambda item: item["object_id"])
        return normalized

    def _vector(self, values: Any) -> tuple[float, ...]:
        if not isinstance(values, Sequence) or isinstance(
            values, (str, bytes, bytearray)
        ):
            raise ValueError("vector must be a numeric sequence")
        if len(values) != self.contract.dimension:
            raise LocalVectorIntegrityError("vector dimension mismatch")
        parsed: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("vector values must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise LocalVectorIntegrityError("vector values must be finite")
            parsed.append(number)
        if not any(value != 0.0 for value in parsed):
            raise LocalVectorIntegrityError("zero vectors are not indexable")
        return tuple(parsed)

    def _stable_integer_key(self, kind: str, object_id: str) -> int:
        payload = {
            "data_release_id": self.contract.data_release_id,
            "embedding_identity_sha256": self.contract.embedding_identity_sha256,
            "index_kind": kind,
            "object_id": object_id,
        }
        return int.from_bytes(hashlib.sha256(_canonical_json(payload)).digest()[:8], "big")

    def _build_index(
        self, stage: Path, kind: str, records: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        _require_usearch(LocalVectorIntegrityError, "candidate index build")
        index_name = (
            self.contract.chunk_index_name
            if kind == "chunk"
            else self.contract.entity_index_name
        )
        index_dir = stage / index_name
        index_dir.mkdir(mode=0o750)
        index_path = index_dir / "index.usearch"
        index = Index(
            ndim=self.contract.dimension,
            metric=_METRICS[self.contract.metric][0],
            dtype=self.contract.dtype,
            multi=False,
        )
        if records:
            keys = np.asarray(
                [item["integer_key"] for item in records], dtype=np.uint64
            )
            vectors = np.asarray(
                [item["vector"] for item in records], dtype=np.float32
            )
            index.add(keys, vectors, threads=INDEX_BUILD_THREADS)
        index.save(index_path)
        self._fsync_file(index_path)
        restored = Index.restore(index_path, view=True)
        if restored is None or len(restored) != len(records):
            raise LocalVectorIntegrityError("persisted index count mismatch")
        actual_keys = {int(value) for value in restored.keys}
        expected_keys = {int(item["integer_key"]) for item in records}
        if actual_keys != expected_keys:
            raise LocalVectorIntegrityError("persisted index key set mismatch")
        self._validate_index_metadata(index_path, len(records))
        return {
            "file": f"{index_name}/index.usearch",
            "index_name": index_name,
            "index_sha256": _sha256_file(index_path),
            "object_count": len(records),
            "objects": [
                {
                    "integer_key": _encode_manifest_integer_key(int(item["integer_key"])),
                    "metadata": item["metadata"],
                    "object_id": item["object_id"],
                }
                for item in records
            ],
        }

    def _load_manifest(self, path: Path) -> Mapping[str, Any]:
        if not path.is_file() or path.is_symlink():
            raise LocalVectorIntegrityError("local vector manifest is missing or unsafe")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalVectorIntegrityError("local vector manifest is unreadable") from exc
        if not isinstance(value, Mapping):
            raise LocalVectorIntegrityError("local vector manifest must be an object")
        return value

    def _validate_manifest(self, manifest: Mapping[str, Any], release_dir: Path) -> None:
        if set(manifest) != {"manifest_schema_version", "identity", "indexes"}:
            raise LocalVectorIntegrityError("manifest fields do not match the frozen schema")
        if manifest["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION:
            raise LocalVectorIntegrityError("manifest schema mismatch")
        if manifest["identity"] != self.contract.identity_manifest():
            raise LocalVectorIntegrityError("local vector release identity mismatch")
        indexes = manifest["indexes"]
        if not isinstance(indexes, Mapping) or set(indexes) != set(INDEX_KINDS):
            raise LocalVectorIntegrityError("manifest must contain isolated chunk and entity indexes")
        for kind in INDEX_KINDS:
            entry = indexes[kind]
            if not isinstance(entry, Mapping) or set(entry) != {
                "file",
                "index_name",
                "index_sha256",
                "object_count",
                "objects",
            }:
                raise LocalVectorIntegrityError("index manifest fields do not match the frozen schema")
            expected_name = (
                self.contract.chunk_index_name
                if kind == "chunk"
                else self.contract.entity_index_name
            )
            if entry["index_name"] != expected_name or entry["file"] != (
                f"{expected_name}/index.usearch"
            ):
                raise LocalVectorIntegrityError("index path or name mismatch")
            index_path = release_dir / expected_name / "index.usearch"
            if not index_path.is_file() or index_path.is_symlink():
                raise LocalVectorIntegrityError("index file is missing or unsafe")
            if not _SHA256.fullmatch(str(entry["index_sha256"])) or (
                _sha256_file(index_path) != entry["index_sha256"]
            ):
                raise LocalVectorIntegrityError("index file hash mismatch")
            objects = entry["objects"]
            if not isinstance(objects, list) or entry["object_count"] != len(objects):
                raise LocalVectorIntegrityError("index object count mismatch")
            self._validate_object_manifest(kind, objects)
            self._validate_index_metadata(index_path, len(objects))

    def _validate_object_manifest(
        self, kind: str, objects: Sequence[Mapping[str, Any]]
    ) -> None:
        seen_ids: set[str] = set()
        seen_keys: set[int] = set()
        allowlist = frozenset(self.contract.metadata_allowlist[kind])
        for item in objects:
            if not isinstance(item, Mapping) or set(item) != {
                "integer_key",
                "metadata",
                "object_id",
            }:
                raise LocalVectorIntegrityError("object mapping fields do not match the frozen schema")
            object_id = _required_text(item["object_id"], "object_id")
            integer_key = _decode_manifest_integer_key(item["integer_key"])
            if integer_key != self._stable_integer_key(kind, object_id):
                raise LocalVectorIntegrityError("stable key or cross-release identity mismatch")
            if object_id in seen_ids or integer_key in seen_keys:
                raise LocalVectorIntegrityError("duplicate object mapping")
            seen_ids.add(object_id)
            seen_keys.add(integer_key)
            metadata = item["metadata"]
            if not isinstance(metadata, Mapping) or set(metadata) - allowlist:
                raise LocalVectorIntegrityError("metadata exceeds the frozen allowlist")
            for value in metadata.values():
                _validate_json_metadata(value)

    def _validate_index_metadata(self, index_path: Path, expected_count: int) -> None:
        _require_usearch(LocalVectorIntegrityError, "USEarch index validation")
        metadata = Index.metadata(index_path)
        if not metadata:
            raise LocalVectorIntegrityError("USEarch metadata is unavailable")
        if str(metadata.get("version")) != ENGINE_VERSION:
            raise LocalVectorIntegrityError("USEarch file version mismatch")
        if int(metadata.get("dimensions", -1)) != self.contract.dimension:
            raise LocalVectorIntegrityError("USEarch dimension mismatch")
        if int(metadata.get("count_present", -1)) != expected_count:
            raise LocalVectorIntegrityError("USEarch count mismatch")
        if int(metadata.get("count_deleted", -1)) != 0:
            raise LocalVectorIntegrityError("USEarch index contains deleted slots")
        if str(metadata.get("kind_metric")) != _METRICS[self.contract.metric][1]:
            raise LocalVectorIntegrityError("USEarch metric mismatch")
        if str(metadata.get("kind_scalar")) != "ScalarKind.F32":
            raise LocalVectorIntegrityError("USEarch dtype mismatch")

    def _ensure_builder_root(self, candidate_root: Path) -> None:
        data_root = self.contract.data_root
        if data_root.exists() and data_root.is_symlink():
            raise LocalVectorIntegrityError("data root cannot be a symlink")
        data_root.mkdir(parents=True, exist_ok=True)
        if candidate_root.exists() and candidate_root.is_symlink():
            raise LocalVectorIntegrityError("candidate root cannot be a symlink")
        candidate_root.mkdir(mode=0o750, exist_ok=True)

    def _assert_release_tree(self, release_dir: Path, *, require_read_only: bool) -> None:
        expected_parent = release_dir.parent
        if release_dir.parent.parent != self.contract.data_root:
            raise LocalVectorIntegrityError("release directory escaped the data root")
        if expected_parent.name not in {"candidate", "active"}:
            raise LocalVectorIntegrityError("release layout is invalid")
        if not release_dir.is_dir() or release_dir.is_symlink():
            raise LocalVectorIntegrityError("release directory is missing or unsafe")
        for root, directories, files in os.walk(release_dir, followlinks=False):
            root_path = Path(root)
            if root_path.is_symlink():
                raise LocalVectorIntegrityError("release tree contains a symlink")
            if require_read_only and stat.S_IMODE(root_path.stat().st_mode) & 0o222:
                raise LocalVectorIntegrityError("active release directory must be read-only")
            for name in directories + files:
                path = root_path / name
                if path.is_symlink():
                    raise LocalVectorIntegrityError("release tree contains a symlink")
                if require_read_only and stat.S_IMODE(path.stat().st_mode) & 0o222:
                    raise LocalVectorIntegrityError("active release files must be read-only")

    @staticmethod
    def _is_exact_child(path: Path, parent: Path) -> bool:
        return path.parent == parent and path.name.startswith(".")

    @staticmethod
    def _fsync_file(path: Path) -> None:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class LocalVectorReadView:
    """Query-only facade over memory-mapped active USEarch files."""

    def __init__(
        self,
        contract: LocalVectorContract,
        release_dir: Path,
        manifest: Mapping[str, Any],
    ) -> None:
        _require_usearch(LocalVectorIntegrityError, "active vector view")
        self.contract = contract
        self.release_dir = release_dir
        self._indexes: dict[str, Index] = {}
        self._objects: dict[str, dict[int, Mapping[str, Any]]] = {}
        self._closed = False
        try:
            for kind in INDEX_KINDS:
                entry = manifest["indexes"][kind]
                index_path = release_dir / str(entry["file"])
                index = Index.restore(index_path, view=True)
                if index is None:
                    raise LocalVectorIntegrityError(
                        "active USEarch index cannot be viewed"
                    )
                mapping = {
                    _decode_manifest_integer_key(item["integer_key"]): item for item in entry["objects"]
                }
                if {int(value) for value in index.keys} != set(mapping):
                    raise LocalVectorIntegrityError(
                        "active index contains unknown or missing keys"
                    )
                self._indexes[kind] = index
                self._objects[kind] = mapping
        except BaseException:
            self.close()
            raise

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        indexes = tuple(self._indexes.values())
        self._indexes.clear()
        self._objects.clear()
        for index in reversed(indexes):
            index.reset()

    def __enter__(self) -> "LocalVectorReadView":
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.close()

    def query_chunk(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> tuple[VectorSearchHit, ...]:
        return self.search(
            "chunk", vector, top_k=top_k, metadata_filter=metadata_filter
        )

    def query_entity(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> tuple[VectorSearchHit, ...]:
        return self.search(
            "entity", vector, top_k=top_k, metadata_filter=metadata_filter
        )

    def search(
        self,
        kind: str,
        vector: Sequence[float],
        *,
        top_k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> tuple[VectorSearchHit, ...]:
        if self._closed:
            raise LocalVectorIntegrityError("local vector read view is closed")
        if kind not in INDEX_KINDS:
            raise ValueError("index kind must be chunk or entity")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        if top_k > self.contract.top_k_max:
            raise LocalVectorIntegrityError("top_k exceeds the frozen limit")
        query = self._query_vector(vector)
        filters = self._metadata_filter(kind, metadata_filter)
        index = self._indexes[kind]
        if len(index) == 0:
            return ()
        search_keys: list[int] | None = None
        if filters:
            search_keys = [
                integer_key
                for integer_key, item in self._objects[kind].items()
                if not any(
                    item["metadata"].get(field) != value
                    for field, value in filters.items()
                )
            ]
            if not search_keys:
                return ()
            stored = index.get(np.asarray(search_keys, dtype=np.uint64), dtype="f32")
            if not isinstance(stored, tuple) or any(item is None for item in stored):
                raise LocalVectorIntegrityError("filtered keys cannot be read from USEarch")
            matches = usearch_search(
                np.vstack(stored).astype(np.float32, copy=False),
                query,
                count=min(top_k, len(search_keys)),
                metric=_METRICS[self.contract.metric][0],
                exact=True,
                dtype="f32",
            )
        else:
            matches = index.search(query, count=min(top_k, len(index)))
        hits: list[VectorSearchHit] = []
        for key, distance in zip(matches.keys, matches.distances):
            integer_key = (
                search_keys[int(key)] if search_keys is not None else int(key)
            )
            item = self._objects[kind].get(integer_key)
            if item is None:
                raise LocalVectorIntegrityError("USEarch returned an unknown key")
            object_id = str(item["object_id"])
            expected_key = self._stable_integer_key(kind, object_id)
            if expected_key != integer_key:
                raise LocalVectorIntegrityError("USEarch returned a cross-release key")
            metadata = item["metadata"]
            if any(metadata.get(field) != value for field, value in filters.items()):
                continue
            hits.append(
                VectorSearchHit(
                    object_id=object_id,
                    integer_key=integer_key,
                    distance=float(distance),
                    metadata=dict(metadata),
                    index_kind=kind,
                    data_release_id=self.contract.data_release_id,
                )
            )
            if len(hits) == top_k:
                break
        return tuple(hits)

    def _stable_integer_key(self, kind: str, object_id: str) -> int:
        payload = {
            "data_release_id": self.contract.data_release_id,
            "embedding_identity_sha256": self.contract.embedding_identity_sha256,
            "index_kind": kind,
            "object_id": object_id,
        }
        return int.from_bytes(
            hashlib.sha256(_canonical_json(payload)).digest()[:8], "big"
        )

    def _query_vector(self, values: Any) -> np.ndarray:
        if not isinstance(values, Sequence) or isinstance(
            values, (str, bytes, bytearray)
        ):
            raise ValueError("query vector must be a numeric sequence")
        if len(values) != self.contract.dimension:
            raise LocalVectorIntegrityError("query dimension mismatch")
        parsed: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("query vector values must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise LocalVectorIntegrityError("query vector values must be finite")
            parsed.append(number)
        if not any(value != 0.0 for value in parsed):
            raise LocalVectorIntegrityError("zero query vectors are not allowed")
        return np.asarray(parsed, dtype=np.float32)

    def _metadata_filter(
        self, kind: str, value: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("metadata_filter must be an object")
        if set(value) - set(self.contract.metadata_allowlist[kind]):
            raise LocalVectorIntegrityError("metadata filter exceeds the allowlist")
        return {str(key): _validate_json_metadata(item) for key, item in value.items()}
