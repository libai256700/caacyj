#!/usr/bin/env python3
"""Immutable USEarch reader for a sealed active cloud runtime release.

Candidate construction and release lifecycle operations intentionally live in
``local_vector_store.py`` and are not dependencies of this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import mmap
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from .runtime_sqlite_reader import ReadOnlySQLiteError, read_stable_regular_file

try:
    import usearch
    from usearch.index import Index, search as usearch_search
except (ImportError, OSError) as exc:  # pragma: no cover - exercised in a subprocess
    # Runtime contracts remain inspectable offline; opening/querying an index
    # must still fail closed when the reviewed binary is absent.
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


class ReadOnlyVectorError(RuntimeError):
    """A sealed vector release cannot be opened or queried safely."""



def _decode_manifest_integer_key(value: Any) -> int:
    if (
        not isinstance(value, str)
        or len(value) != len(MANIFEST_INTEGER_KEY_PREFIX) + MANIFEST_INTEGER_KEY_HEX_LENGTH
        or not value.startswith(MANIFEST_INTEGER_KEY_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[len(MANIFEST_INTEGER_KEY_PREFIX):])
    ):
        raise ReadOnlyVectorError("vector integer key encoding is invalid")
    return int(value[len(MANIFEST_INTEGER_KEY_PREFIX):], 16)


class _StableIndexFile:
    """Hold one immutable index inode and its read-only mapping for a view."""

    def __init__(self, path: Path, expected_sha256: str) -> None:
        self.path = path
        self.expected_sha256 = expected_sha256
        self._descriptor = -1
        self._mapping: mmap.mmap | None = None
        self._opened_identity: tuple[int, int, int, int, int] | None = None
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        try:
            resolved = path.resolve(strict=True)
            if resolved != path or path.is_symlink():
                raise ReadOnlyVectorError(
                    "vector index must be a canonical regular file"
                )
            self._descriptor = os.open(path, flags)
            opened = os.fstat(self._descriptor)
            named = os.stat(path, follow_symlinks=False)
            if (
                not stat.S_ISREG(opened.st_mode)
                or not stat.S_ISREG(named.st_mode)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
                or opened.st_size <= 0
                or stat.S_IMODE(opened.st_mode) & 0o222
            ):
                raise ReadOnlyVectorError(
                    "vector index changed while it was opened"
                )
            self._opened_identity = self._identity(opened)
            self._mapping = mmap.mmap(
                self._descriptor,
                0,
                access=mmap.ACCESS_READ,
            )
            if hashlib.sha256(self._mapping).hexdigest() != expected_sha256:
                raise ReadOnlyVectorError("vector index hash mismatch")
            self.verify_unchanged()
        except ReadOnlyVectorError:
            try:
                self.close()
            except ReadOnlyVectorError:
                pass
            raise
        except (OSError, ValueError) as exc:
            try:
                self.close()
            except ReadOnlyVectorError:
                pass
            raise ReadOnlyVectorError("vector index could not be opened stably") from exc

    @staticmethod
    def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    @property
    def buffer(self) -> mmap.mmap:
        if self._mapping is None:
            raise ReadOnlyVectorError("vector index descriptor is closed")
        return self._mapping

    def verify_unchanged(self, *, full_hash: bool = False) -> None:
        if (
            self._descriptor < 0
            or self._mapping is None
            or self._opened_identity is None
        ):
            raise ReadOnlyVectorError("vector index descriptor is closed")
        try:
            descriptor_stat = os.fstat(self._descriptor)
            named_stat = os.stat(self.path, follow_symlinks=False)
        except OSError as exc:
            raise ReadOnlyVectorError("vector index path binding changed") from exc
        if (
            self._identity(descriptor_stat) != self._opened_identity
            or self._identity(named_stat) != self._opened_identity
            or not stat.S_ISREG(named_stat.st_mode)
            or stat.S_IMODE(named_stat.st_mode) & 0o222
            or len(self._mapping) != descriptor_stat.st_size
        ):
            raise ReadOnlyVectorError("vector index path binding changed")
        if full_hash and hashlib.sha256(self._mapping).hexdigest() != self.expected_sha256:
            raise ReadOnlyVectorError("vector index bytes changed during read")

    def close(self) -> None:
        mapping = self._mapping
        descriptor = self._descriptor
        self._mapping = None
        self._descriptor = -1
        failure: BaseException | None = None
        if mapping is not None:
            try:
                mapping.close()
            except (BufferError, OSError) as exc:
                failure = exc
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise ReadOnlyVectorError("vector index close failed") from failure


def _require_usearch(operation: str) -> None:
    """Require the exact reviewed USEarch runtime for vector operations."""

    if usearch is None or Index is None or usearch_search is None:
        raise ReadOnlyVectorError(
            f"{operation} requires USEarch {ENGINE_VERSION}; "
            "the frozen vector dependency is unavailable"
        ) from _USEARCH_IMPORT_ERROR
    if str(getattr(usearch, "__version__", "")) != ENGINE_VERSION:
        raise ReadOnlyVectorError(
            "USEarch runtime version does not match the frozen release"
        )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _safe_component(value: Any, field: str) -> str:
    normalized = _required_text(value, field)
    if not _SAFE_COMPONENT.fullmatch(normalized) or normalized in {".", ".."}:
        raise ValueError(f"{field} must be one exact path component")
    return normalized


def _metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata numbers must be finite")
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise ValueError("metadata values must be scalar JSON values or string lists")


def _strict_json_payload(payload: bytes) -> Mapping[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ReadOnlyVectorError("vector manifest contains a duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ReadOnlyVectorError("vector manifest contains a non-finite value")
            ),
        )
    except ReadOnlyVectorError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadOnlyVectorError("vector manifest is unreadable") from exc
    if not isinstance(value, Mapping):
        raise ReadOnlyVectorError("vector manifest must contain an object")
    return value


@dataclass(frozen=True)
class ReadOnlyVectorContract:
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
        approved_parent_input = Path(self.approved_data_parent)
        if not approved_parent_input.is_absolute():
            raise ValueError("approved_data_parent must be absolute")
        approved_parent = approved_parent_input.resolve(strict=True)
        if (
            approved_parent != approved_parent_input
            or len(approved_parent.parts) < 3
            or not approved_parent.is_dir()
        ):
            raise ValueError("approved_data_parent must be an existing narrow directory")
        object.__setattr__(self, "approved_data_parent", approved_parent)

        data_root_input = Path(self.data_root)
        if not data_root_input.is_absolute():
            raise ValueError("data_root must be absolute")
        data_root = data_root_input.resolve(strict=True)
        if (
            data_root != data_root_input
            or len(data_root.parts) < 4
            or data_root == approved_parent
            or approved_parent not in data_root.parents
            or not data_root.is_dir()
        ):
            raise ValueError("data_root must be a real path below the approved parent")
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
            raise ValueError("runtime vector engine identity mismatch")
        if self.dtype != "f32" or self.metric not in _METRICS:
            raise ValueError("runtime vector dtype or metric mismatch")
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
        normalized: dict[str, tuple[str, ...]] = {}
        for kind in INDEX_KINDS:
            fields = tuple(self.metadata_allowlist[kind])
            if len(fields) != len(set(fields)):
                raise ValueError("metadata allowlist fields must be unique")
            values: list[str] = []
            for field in fields:
                name = _safe_component(field, f"{kind} metadata field")
                if name.lower() in _CONTENT_FIELD_NAMES:
                    raise ValueError("authoritative content is forbidden in vector metadata")
                values.append(name)
            normalized[kind] = tuple(values)
        object.__setattr__(self, "metadata_allowlist", MappingProxyType(normalized))

    @property
    def active_release_dir(self) -> Path:
        return self.data_root / "active" / self.data_release_id

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
class ReadOnlyVectorHit:
    object_id: str
    integer_key: int
    distance: float
    metadata: Mapping[str, Any]
    index_kind: str
    data_release_id: str


class ReadOnlyVectorReader:
    """Validate and open exactly one configured active vector release."""

    def __init__(self, contract: ReadOnlyVectorContract) -> None:
        _require_usearch("read-only vector operations")
        self.contract = contract

    def open_active(self, *, expected_manifest_sha256: str) -> "ReadOnlyVectorView":
        if not _SHA256.fullmatch(str(expected_manifest_sha256)):
            raise ValueError("expected_manifest_sha256 must be a lowercase SHA-256")
        try:
            release_dir = self.contract.active_release_dir
            self._assert_immutable_tree(release_dir)
            manifest_path = release_dir / "local_vector_manifest.json"
            try:
                _path, manifest_payload, manifest_sha256 = read_stable_regular_file(
                    manifest_path,
                    "active vector manifest",
                )
            except ReadOnlySQLiteError as exc:
                raise ReadOnlyVectorError(
                    "active vector manifest could not be read stably"
                ) from exc
            if manifest_sha256 != expected_manifest_sha256:
                raise ReadOnlyVectorError("active vector manifest identity mismatch")
            manifest = _strict_json_payload(manifest_payload)
            index_files = self._validate_manifest(manifest, release_dir)
            try:
                return ReadOnlyVectorView(
                    self.contract,
                    release_dir,
                    manifest,
                    index_files,
                )
            except BaseException:
                for index_file in index_files.values():
                    index_file.close()
                raise
        except ReadOnlyVectorError:
            raise
        except Exception as exc:
            raise ReadOnlyVectorError("active vector release could not be opened") from exc

    def _assert_immutable_tree(self, release_dir: Path) -> None:
        if (
            release_dir.parent.name != "active"
            or release_dir.parent.parent != self.contract.data_root
            or not release_dir.is_dir()
            or release_dir.is_symlink()
        ):
            raise ReadOnlyVectorError("active vector release layout is invalid")
        for root, directories, files in os.walk(release_dir, followlinks=False):
            root_path = Path(root)
            if root_path.is_symlink() or stat.S_IMODE(root_path.stat().st_mode) & 0o222:
                raise ReadOnlyVectorError("active vector tree must be immutable")
            for name in directories + files:
                path = root_path / name
                if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o222:
                    raise ReadOnlyVectorError("active vector tree contains an unsafe entry")

    def _validate_manifest(
        self, manifest: Mapping[str, Any], release_dir: Path
    ) -> dict[str, _StableIndexFile]:
        if set(manifest) != {"manifest_schema_version", "identity", "indexes"}:
            raise ReadOnlyVectorError("vector manifest fields do not match the schema")
        if (
            manifest["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION
            or manifest["identity"] != self.contract.identity_manifest()
        ):
            raise ReadOnlyVectorError("vector release identity mismatch")
        indexes = manifest["indexes"]
        if not isinstance(indexes, Mapping) or set(indexes) != set(INDEX_KINDS):
            raise ReadOnlyVectorError("vector indexes are not exactly isolated")
        opened: dict[str, _StableIndexFile] = {}
        try:
            for kind in INDEX_KINDS:
                entry = indexes[kind]
                if not isinstance(entry, Mapping) or set(entry) != {
                    "file",
                    "index_name",
                    "index_sha256",
                    "object_count",
                    "objects",
                }:
                    raise ReadOnlyVectorError("vector index record shape mismatch")
                expected_name = (
                    self.contract.chunk_index_name
                    if kind == "chunk"
                    else self.contract.entity_index_name
                )
                if (
                    entry["index_name"] != expected_name
                    or entry["file"] != f"{expected_name}/index.usearch"
                ):
                    raise ReadOnlyVectorError("vector index path mismatch")
                expected_sha256 = str(entry["index_sha256"])
                if not _SHA256.fullmatch(expected_sha256):
                    raise ReadOnlyVectorError("vector index hash mismatch")
                index_path = release_dir / expected_name / "index.usearch"
                index_file = _StableIndexFile(index_path, expected_sha256)
                opened[kind] = index_file
                objects = entry["objects"]
                if not isinstance(objects, list) or entry["object_count"] != len(objects):
                    raise ReadOnlyVectorError("vector object count mismatch")
                self._validate_objects(kind, objects)
                self._validate_index_file(index_file, len(objects))
            return opened
        except BaseException:
            for index_file in opened.values():
                index_file.close()
            raise

    def _validate_objects(
        self, kind: str, objects: Sequence[Mapping[str, Any]]
    ) -> None:
        seen_ids: set[str] = set()
        seen_keys: set[int] = set()
        allowed_metadata = frozenset(self.contract.metadata_allowlist[kind])
        for item in objects:
            if not isinstance(item, Mapping) or set(item) != {
                "integer_key",
                "metadata",
                "object_id",
            }:
                raise ReadOnlyVectorError("vector object shape mismatch")
            object_id = _required_text(item["object_id"], "object_id")
            integer_key = _decode_manifest_integer_key(item["integer_key"])
            if integer_key != self._stable_integer_key(kind, object_id):
                raise ReadOnlyVectorError("vector stable key identity mismatch")
            if object_id in seen_ids or integer_key in seen_keys:
                raise ReadOnlyVectorError("duplicate vector object mapping")
            seen_ids.add(object_id)
            seen_keys.add(integer_key)
            metadata = item["metadata"]
            if not isinstance(metadata, Mapping) or set(metadata) - allowed_metadata:
                raise ReadOnlyVectorError("vector metadata exceeds its allowlist")
            for value in metadata.values():
                _metadata_value(value)

    def _validate_index_file(
        self, index_file: _StableIndexFile, expected_count: int
    ) -> None:
        _require_usearch("USEarch index validation")
        metadata = Index.metadata(index_file.buffer)
        if (
            not metadata
            or str(metadata.get("version")) != ENGINE_VERSION
            or int(metadata.get("dimensions", -1)) != self.contract.dimension
            or int(metadata.get("count_present", -1)) != expected_count
            or int(metadata.get("count_deleted", -1)) != 0
            or str(metadata.get("kind_metric")) != _METRICS[self.contract.metric][1]
            or str(metadata.get("kind_scalar")) != "ScalarKind.F32"
        ):
            raise ReadOnlyVectorError("USEarch file metadata mismatch")
        index_file.verify_unchanged(full_hash=True)

    def _stable_integer_key(self, kind: str, object_id: str) -> int:
        payload = {
            "data_release_id": self.contract.data_release_id,
            "embedding_identity_sha256": self.contract.embedding_identity_sha256,
            "index_kind": kind,
            "object_id": object_id,
        }
        return int.from_bytes(hashlib.sha256(_canonical_json(payload)).digest()[:8], "big")


class ReadOnlyVectorView:
    """Query-only memory-mapped view of validated chunk and entity indexes."""

    def __init__(
        self,
        contract: ReadOnlyVectorContract,
        release_dir: Path,
        manifest: Mapping[str, Any],
        index_files: Mapping[str, _StableIndexFile],
    ) -> None:
        _require_usearch("active vector view")
        self.contract = contract
        self.release_dir = release_dir
        self._indexes: dict[str, Index] = {}
        self._objects: dict[str, dict[int, Mapping[str, Any]]] = {}
        self._index_files = dict(index_files)
        self._closed = False
        try:
            for kind in INDEX_KINDS:
                entry = manifest["indexes"][kind]
                index_file = self._index_files[kind]
                index = Index.restore(index_file.buffer, view=True)
                if index is None:
                    raise ReadOnlyVectorError("active USEarch index cannot be viewed")
                mapping = {
                    _decode_manifest_integer_key(item["integer_key"]): item for item in entry["objects"]
                }
                if {int(value) for value in index.keys} != set(mapping):
                    raise ReadOnlyVectorError("vector index key coverage mismatch")
                self._indexes[kind] = index
                self._objects[kind] = mapping
                index_file.verify_unchanged(full_hash=True)
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
        index_files = tuple(self._index_files.values())
        self._indexes.clear()
        self._objects.clear()
        self._index_files.clear()
        failure: BaseException | None = None
        for index in reversed(indexes):
            try:
                index.reset()
            except BaseException as exc:
                if failure is None:
                    failure = exc
        for index_file in reversed(index_files):
            try:
                index_file.close()
            except ReadOnlyVectorError as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise ReadOnlyVectorError("vector read view close failed") from failure

    def __enter__(self) -> "ReadOnlyVectorView":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    def query_chunk(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> tuple[ReadOnlyVectorHit, ...]:
        return self.search("chunk", vector, top_k=top_k, metadata_filter=metadata_filter)

    def query_entity(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> tuple[ReadOnlyVectorHit, ...]:
        return self.search("entity", vector, top_k=top_k, metadata_filter=metadata_filter)

    def search(
        self,
        kind: str,
        vector: Sequence[float],
        *,
        top_k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> tuple[ReadOnlyVectorHit, ...]:
        if self._closed:
            raise ReadOnlyVectorError("vector read view is closed")
        if kind not in INDEX_KINDS:
            raise ValueError("index kind must be chunk or entity")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        if top_k > self.contract.top_k_max:
            raise ReadOnlyVectorError("top_k exceeds the frozen limit")
        index_file = self._index_files[kind]
        index_file.verify_unchanged()
        query = self._query_vector(vector)
        filters = self._metadata_filter(kind, metadata_filter)
        index = self._indexes[kind]
        if len(index) == 0:
            index_file.verify_unchanged()
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
                index_file.verify_unchanged()
                return ()
            try:
                stored = index.get(np.asarray(search_keys, dtype=np.uint64), dtype="f32")
            except Exception as exc:
                raise ReadOnlyVectorError("active vector query failed") from exc
            if not isinstance(stored, tuple) or any(item is None for item in stored):
                raise ReadOnlyVectorError("filtered vector keys cannot be read")
            try:
                matches = usearch_search(
                    np.vstack(stored).astype(np.float32, copy=False),
                    query,
                    count=min(top_k, len(search_keys)),
                    metric=_METRICS[self.contract.metric][0],
                    exact=True,
                    dtype="f32",
                )
            except Exception as exc:
                raise ReadOnlyVectorError("active vector query failed") from exc
        else:
            try:
                matches = index.search(query, count=min(top_k, len(index)))
            except Exception as exc:
                raise ReadOnlyVectorError("active vector query failed") from exc
        hits: list[ReadOnlyVectorHit] = []
        for key, distance in zip(matches.keys, matches.distances):
            integer_key = search_keys[int(key)] if search_keys is not None else int(key)
            item = self._objects[kind].get(integer_key)
            if item is None:
                raise ReadOnlyVectorError("USEarch returned an unknown key")
            object_id = str(item["object_id"])
            if self._stable_integer_key(kind, object_id) != integer_key:
                raise ReadOnlyVectorError("USEarch returned a cross-release key")
            metadata = item["metadata"]
            if any(metadata.get(field) != value for field, value in filters.items()):
                continue
            hits.append(
                ReadOnlyVectorHit(
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
        index_file.verify_unchanged()
        return tuple(hits)

    def _stable_integer_key(self, kind: str, object_id: str) -> int:
        payload = {
            "data_release_id": self.contract.data_release_id,
            "embedding_identity_sha256": self.contract.embedding_identity_sha256,
            "index_kind": kind,
            "object_id": object_id,
        }
        return int.from_bytes(hashlib.sha256(_canonical_json(payload)).digest()[:8], "big")

    def _query_vector(self, values: Any) -> np.ndarray:
        if not isinstance(values, Sequence) or isinstance(
            values, (str, bytes, bytearray)
        ):
            raise ValueError("query vector must be a numeric sequence")
        if len(values) != self.contract.dimension:
            raise ReadOnlyVectorError("query dimension mismatch")
        parsed: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("query vector values must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise ReadOnlyVectorError("query vector values must be finite")
            parsed.append(number)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            query = np.asarray(parsed, dtype=np.float32)
        if not bool(np.isfinite(query).all()):
            raise ReadOnlyVectorError(
                "query vector values must remain finite after float32 conversion"
            )
        converted_norm = float(
            np.linalg.norm(query.astype(np.float64, copy=False))
        )
        if not math.isfinite(converted_norm) or converted_norm <= 0.0:
            raise ReadOnlyVectorError(
                "query vector must remain non-zero after float32 conversion"
            )
        return query

    def _metadata_filter(
        self, kind: str, value: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("metadata_filter must be an object")
        if set(value) - set(self.contract.metadata_allowlist[kind]):
            raise ReadOnlyVectorError("metadata filter exceeds the allowlist")
        return {str(key): _metadata_value(item) for key, item in value.items()}


__all__ = [
    "ReadOnlyVectorContract",
    "ReadOnlyVectorError",
    "ReadOnlyVectorHit",
    "ReadOnlyVectorReader",
    "ReadOnlyVectorView",
]
