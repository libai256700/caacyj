#!/usr/bin/env python3
"""Hash-bound production runtime for the private ops-admin-agent surface."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import weakref
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .identity_policy import VerifiedIdentity, VerifiedMaintenanceConfirmation
from .maintenance_jobs import (
    BUILTIN_BACKEND_REGISTRY_ID,
    BuiltinCandidateBackendRegistry,
    CandidateJobRunner,
    CandidateWorkspaceBinding,
    MaintenanceJobError,
)
from .ops_service import OpsHandler


CONFIG_ENVIRONMENT_VARIABLE = "KG_OPS_RUNTIME_CONFIG"
CONFIG_SHA256_ENVIRONMENT_VARIABLE = "KG_OPS_RUNTIME_CONFIG_SHA256"
CONFIG_SCHEMA_VERSION = "cloud-v2-ops-runtime-config-v1"
QUALITY_SUMMARY_SCHEMA_VERSION = "cloud-v2-sanitized-quality-summary-v1"
PRODUCTION_MODE = "production"
QUALITY_WINDOWS = ("1h", "24h", "7d", "30d")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
_JSON_FILES = frozenset(
    {
        "suite_manifest",
        "data_release_manifest",
        "runtime_manifest",
        "authority_manifest",
        "bm25_manifest",
        "local_vector_manifest",
        "graph_manifest",
        "quality_summary",
    }
)
_FILE_NAMES = frozenset(
    {
        *_JSON_FILES,
        "authority_database",
        "bm25_index",
        "local_vector_chunk_index",
        "local_vector_entity_index",
        "graph_data",
    }
)


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mode,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
    )


class OpsRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OpsRuntimeConfigError(OpsRuntimeError):
    pass


class OpsRuntimeIntegrityError(OpsRuntimeError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _strict_json(raw: bytes, *, field: str) -> dict[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise OpsRuntimeIntegrityError(f"{field}_duplicate_json_key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                OpsRuntimeIntegrityError(f"{field}_non_finite_json")
            ),
        )
    except OpsRuntimeIntegrityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpsRuntimeIntegrityError(f"{field}_invalid_json") from exc
    if not isinstance(value, dict):
        raise OpsRuntimeIntegrityError(f"{field}_must_be_object")
    return value


def _exact_mapping(value: Any, field: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OpsRuntimeConfigError(f"{field}_shape_mismatch")
    return dict(value)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise OpsRuntimeIntegrityError(f"{field}_must_be_object")
    return value


def _text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise OpsRuntimeConfigError(f"{field}_must_be_text")
    return value


def _identifier(value: Any, field: str) -> str:
    normalized = _text(value, field)
    if _IDENTIFIER.fullmatch(normalized) is None:
        raise OpsRuntimeConfigError(f"{field}_invalid")
    return normalized


def _sha256(value: Any, field: str) -> str:
    normalized = _text(value, field)
    if _SHA256.fullmatch(normalized) is None:
        raise OpsRuntimeConfigError(f"{field}_invalid")
    return normalized


def _manifest_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise OpsRuntimeIntegrityError(f"{field}_invalid")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpsRuntimeIntegrityError(f"{field}_invalid")
    return value


def _positive_int(value: Any, field: str, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > maximum
    ):
        raise OpsRuntimeConfigError(f"{field}_invalid")
    return value


def _relative_path(value: Any, field: str) -> str:
    normalized = _text(value, field)
    if normalized.startswith("/") or "\\" in normalized or "//" in normalized:
        raise OpsRuntimeConfigError(f"{field}_unsafe")
    path = PurePosixPath(normalized)
    if (
        any(part in {"", ".", ".."} for part in path.parts)
        or any(character in normalized for character in "*?[]{}")
        or any(part.lower() in {"candidate", "candidates"} for part in path.parts)
        or path.as_posix() != normalized
    ):
        raise OpsRuntimeConfigError(f"{field}_unsafe")
    return path.as_posix()


def _canonical_config_file(path: str | Path) -> Path:
    raw = Path(path)
    if not raw.is_absolute():
        raise OpsRuntimeConfigError("config_path_must_be_absolute")
    lexical = Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
        path_stat = raw.lstat()
    except OSError as exc:
        raise OpsRuntimeConfigError("config_unavailable") from exc
    if (
        resolved != lexical
        or not stat.S_ISREG(path_stat.st_mode)
        or stat.S_ISLNK(path_stat.st_mode)
        or path_stat.st_uid != os.geteuid()
        or stat.S_IMODE(path_stat.st_mode) & 0o022
        or path_stat.st_nlink != 1
    ):
        raise OpsRuntimeConfigError("config_permissions_or_path_invalid")
    return resolved


def _canonical_directory(
    value: Any,
    field: str,
    *,
    exact_mode: int | None = None,
    read_only: bool = False,
) -> Path:
    raw = Path(_text(value, field))
    if not raw.is_absolute() or len(raw.parts) < 3:
        raise OpsRuntimeConfigError(f"{field}_must_be_narrow_absolute_path")
    lexical = Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
        path_stat = raw.lstat()
    except OSError as exc:
        raise OpsRuntimeConfigError(f"{field}_unavailable") from exc
    mode = stat.S_IMODE(path_stat.st_mode)
    if (
        resolved != lexical
        or stat.S_ISLNK(path_stat.st_mode)
        or not stat.S_ISDIR(path_stat.st_mode)
        or path_stat.st_uid != os.geteuid()
        or (exact_mode is not None and mode != exact_mode)
        or (read_only and mode & _WRITE_BITS)
    ):
        raise OpsRuntimeConfigError(f"{field}_permissions_or_path_invalid")
    return resolved


def _read_config(path: Path, expected_sha256: str) -> tuple[bytes, os.stat_result]:
    try:
        named_before = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise OpsRuntimeConfigError("config_unavailable") from exc
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise OpsRuntimeConfigError("config_unavailable") from exc
    try:
        before = os.fstat(descriptor)
        named_open = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(named_open.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & 0o022
            or before.st_nlink != 1
            or _file_identity(named_before) != _file_identity(before)
            or _file_identity(before) != _file_identity(named_open)
        ):
            raise OpsRuntimeConfigError("config_permissions_or_path_invalid")
        chunks: list[bytes] = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(descriptor)
        named_after = os.stat(path, follow_symlinks=False)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if (
        _file_identity(before) != _file_identity(after)
        or _file_identity(after) != _file_identity(named_after)
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise OpsRuntimeConfigError("config_hash_or_identity_mismatch")
    return raw, after


@dataclass(frozen=True)
class FileBinding:
    path: str
    sha256: str


@dataclass(frozen=True)
class BoundArtifact:
    path: Path
    sha256: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    uid: int
    gid: int
    mode: int
    nlink: int
    json_value: Mapping[str, Any] | None = None
    raw_bytes: bytes | None = None


@dataclass(frozen=True)
class OpsRuntimeConfig:
    config_path: Path
    config_sha256: str
    active_root: Path
    suite_release_id: str
    data_release_id: str
    runtime_code_file_set_sha256: str
    local_vector_release_id: str
    graph_release_id: str
    operator_companion_sha256: str
    files: Mapping[str, FileBinding]
    candidate_workspace: Path
    confirmation_ledger: Path
    listen_host: str
    listen_port: int
    listen_threads: int
    allowed_hosts: tuple[str, ...]

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        expected_sha256: str,
    ) -> "OpsRuntimeConfig":
        expected = _sha256(expected_sha256, "config_sha256")
        config_path = _canonical_config_file(path)
        raw, _config_stat = _read_config(config_path, expected)
        try:
            value = _strict_json(raw, field="config")
        except OpsRuntimeIntegrityError as exc:
            raise OpsRuntimeConfigError(exc.code) from exc
        root = _exact_mapping(
            value,
            "config",
            {
                "schema_version",
                "mode",
                "active_root",
                "identities",
                "files",
                "candidate_workspace",
                "confirmation_ledger",
                "listen",
            },
        )
        if root["schema_version"] != CONFIG_SCHEMA_VERSION:
            raise OpsRuntimeConfigError("config_schema_version_mismatch")
        if root["mode"] != PRODUCTION_MODE:
            raise OpsRuntimeConfigError("production_mode_required")

        active_root = _canonical_directory(
            root["active_root"],
            "active_root",
            read_only=True,
        )
        lowered_active_parts = {part.lower() for part in active_root.parts}
        if "active" not in lowered_active_parts or lowered_active_parts & {
            "candidate",
            "candidates",
        }:
            raise OpsRuntimeConfigError("active_root_identity_invalid")

        identities = _exact_mapping(
            root["identities"],
            "identities",
            {
                "suite_release_id",
                "data_release_id",
                "runtime_code_file_set_sha256",
                "local_vector_release_id",
                "graph_release_id",
                "operator_companion_sha256",
            },
        )
        raw_files = _exact_mapping(root["files"], "files", set(_FILE_NAMES))
        files: dict[str, FileBinding] = {}
        for name in sorted(_FILE_NAMES):
            item = _exact_mapping(raw_files[name], f"files_{name}", {"path", "sha256"})
            files[name] = FileBinding(
                path=_relative_path(item["path"], f"files_{name}_path"),
                sha256=_sha256(item["sha256"], f"files_{name}_sha256"),
            )
        paths = [item.path for item in files.values()]
        if len(paths) != len(set(paths)):
            raise OpsRuntimeConfigError("file_paths_must_be_unique")

        candidate_raw = _exact_mapping(
            root["candidate_workspace"],
            "candidate_workspace",
            {"path", "mode"},
        )
        if candidate_raw["mode"] != "0700":
            raise OpsRuntimeConfigError("candidate_workspace_mode_mismatch")
        candidate_workspace = _canonical_directory(
            candidate_raw["path"],
            "candidate_workspace",
            exact_mode=0o700,
        )
        lowered_candidate_parts = {part.lower() for part in candidate_workspace.parts}
        if not lowered_candidate_parts & {"candidate", "candidates"} or "active" in lowered_candidate_parts:
            raise OpsRuntimeConfigError("candidate_workspace_identity_invalid")

        ledger_raw = _exact_mapping(
            root["confirmation_ledger"],
            "confirmation_ledger",
            {"path", "mode"},
        )
        if ledger_raw["mode"] != "0700":
            raise OpsRuntimeConfigError("confirmation_ledger_mode_mismatch")
        confirmation_ledger = _canonical_directory(
            ledger_raw["path"],
            "confirmation_ledger",
            exact_mode=0o700,
        )
        if (
            active_root == candidate_workspace
            or active_root in candidate_workspace.parents
            or candidate_workspace in active_root.parents
            or confirmation_ledger == active_root
            or confirmation_ledger == candidate_workspace
            or active_root in confirmation_ledger.parents
            or candidate_workspace in confirmation_ledger.parents
            or confirmation_ledger in active_root.parents
            or confirmation_ledger in candidate_workspace.parents
        ):
            raise OpsRuntimeConfigError("runtime_directory_boundaries_overlap")

        listen = _exact_mapping(
            root["listen"],
            "listen",
            {"host", "port", "threads", "allowed_hosts"},
        )
        host = _text(listen["host"], "listen_host")
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise OpsRuntimeConfigError("listen_host_must_be_loopback")
        port = _positive_int(listen["port"], "listen_port", maximum=65535)
        threads = _positive_int(listen["threads"], "listen_threads", maximum=64)
        raw_allowed_hosts = listen["allowed_hosts"]
        if (
            not isinstance(raw_allowed_hosts, list)
            or not raw_allowed_hosts
            or any(not isinstance(item, str) or not item for item in raw_allowed_hosts)
        ):
            raise OpsRuntimeConfigError("allowed_hosts_invalid")
        allowed_hosts = tuple(item.lower() for item in raw_allowed_hosts)
        permitted_hosts = {
            "127.0.0.1",
            f"127.0.0.1:{port}",
            "[::1]",
            f"[::1]:{port}",
            "localhost",
            f"localhost:{port}",
        }
        if (
            allowed_hosts != tuple(sorted(set(allowed_hosts)))
            or not set(allowed_hosts).issubset(permitted_hosts)
        ):
            raise OpsRuntimeConfigError("allowed_hosts_invalid")

        return cls(
            config_path=config_path,
            config_sha256=expected,
            active_root=active_root,
            suite_release_id=_identifier(
                identities["suite_release_id"], "suite_release_id"
            ),
            data_release_id=_identifier(
                identities["data_release_id"], "data_release_id"
            ),
            runtime_code_file_set_sha256=_sha256(
                identities["runtime_code_file_set_sha256"],
                "runtime_code_file_set_sha256",
            ),
            local_vector_release_id=_identifier(
                identities["local_vector_release_id"], "local_vector_release_id"
            ),
            graph_release_id=_identifier(
                identities["graph_release_id"], "graph_release_id"
            ),
            operator_companion_sha256=_sha256(
                identities["operator_companion_sha256"],
                "operator_companion_sha256",
            ),
            files=MappingProxyType(files),
            candidate_workspace=candidate_workspace,
            confirmation_ledger=confirmation_ledger,
            listen_host=host,
            listen_port=port,
            listen_threads=threads,
            allowed_hosts=allowed_hosts,
        )


def _bind_artifact(
    active_root: Path,
    binding: FileBinding,
    *,
    field: str,
    load_json: bool,
    load_bytes: bool = False,
) -> BoundArtifact:
    path = active_root.joinpath(*PurePosixPath(binding.path).parts)
    _verify_read_only_ancestors(active_root, path, field=field)
    try:
        resolved = path.resolve(strict=True)
        path_stat = path.lstat()
    except OSError as exc:
        raise OpsRuntimeIntegrityError(f"{field}_unavailable") from exc
    if (
        resolved != path
        or active_root not in path.parents
        or stat.S_ISLNK(path_stat.st_mode)
        or not stat.S_ISREG(path_stat.st_mode)
        or path_stat.st_uid != os.geteuid()
        or stat.S_IMODE(path_stat.st_mode) & _WRITE_BITS
        or path_stat.st_nlink != 1
    ):
        raise OpsRuntimeIntegrityError(f"{field}_path_or_permissions_invalid")

    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise OpsRuntimeIntegrityError(f"{field}_unavailable") from exc
    digest = hashlib.sha256()
    chunks: list[bytes] | None = [] if load_json or load_bytes else None
    try:
        before = os.fstat(descriptor)
        named_open = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(named_open.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & _WRITE_BITS
            or before.st_nlink != 1
            or _file_identity(path_stat) != _file_identity(before)
            or _file_identity(before) != _file_identity(named_open)
        ):
            raise OpsRuntimeIntegrityError(
                f"{field}_path_or_permissions_invalid"
            )
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            if chunks is not None:
                chunks.append(block)
        after = os.fstat(descriptor)
        named_after = os.stat(path, follow_symlinks=False)
    finally:
        os.close(descriptor)
    if (
        _file_identity(before) != _file_identity(after)
        or _file_identity(after) != _file_identity(named_after)
        or digest.hexdigest() != binding.sha256
    ):
        raise OpsRuntimeIntegrityError(f"{field}_hash_or_identity_mismatch")
    raw_bytes = b"".join(chunks) if chunks is not None else None
    json_value = None
    if load_json and raw_bytes is not None:
        json_value = MappingProxyType(
            _strict_json(raw_bytes, field=field)
        )
    return BoundArtifact(
        path=path,
        sha256=binding.sha256,
        device=after.st_dev,
        inode=after.st_ino,
        size=after.st_size,
        mtime_ns=after.st_mtime_ns,
        ctime_ns=after.st_ctime_ns,
        uid=after.st_uid,
        gid=after.st_gid,
        mode=after.st_mode,
        nlink=after.st_nlink,
        json_value=json_value,
        raw_bytes=raw_bytes if load_bytes else None,
    )


def _verify_bound_artifact(artifact: BoundArtifact, *, field: str) -> None:
    try:
        path_stat = artifact.path.lstat()
    except OSError as exc:
        raise OpsRuntimeIntegrityError(f"{field}_unavailable") from exc
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or stat.S_ISLNK(path_stat.st_mode)
        or path_stat.st_uid != os.geteuid()
        or stat.S_IMODE(path_stat.st_mode) & _WRITE_BITS
        or path_stat.st_nlink != 1
        or _file_identity(path_stat)
        != (
            artifact.device,
            artifact.inode,
            artifact.size,
            artifact.mode,
            artifact.mtime_ns,
            artifact.ctime_ns,
            artifact.uid,
            artifact.gid,
            artifact.nlink,
        )
    ):
        raise OpsRuntimeIntegrityError(f"{field}_identity_changed")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(artifact.path, flags)
    except OSError as exc:
        raise OpsRuntimeIntegrityError(f"{field}_unavailable") from exc
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        named_open = os.stat(artifact.path, follow_symlinks=False)
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
        named_after = os.stat(artifact.path, follow_symlinks=False)
    finally:
        os.close(descriptor)
    expected_identity = (
        artifact.device,
        artifact.inode,
        artifact.size,
        artifact.mode,
        artifact.mtime_ns,
        artifact.ctime_ns,
        artifact.uid,
        artifact.gid,
        artifact.nlink,
    )
    if (
        _file_identity(path_stat) != expected_identity
        or _file_identity(named_open) != expected_identity
        or _file_identity(before) != expected_identity
        or _file_identity(after) != expected_identity
        or _file_identity(named_after) != expected_identity
        or digest.hexdigest() != artifact.sha256
    ):
        raise OpsRuntimeIntegrityError(f"{field}_hash_or_identity_mismatch")


def _verify_read_only_ancestors(
    active_root: Path,
    artifact_path: Path,
    *,
    field: str,
) -> None:
    current = artifact_path.parent
    while True:
        try:
            current_stat = current.lstat()
        except OSError as exc:
            raise OpsRuntimeIntegrityError(f"{field}_ancestor_unavailable") from exc
        if (
            stat.S_ISLNK(current_stat.st_mode)
            or not stat.S_ISDIR(current_stat.st_mode)
            or current_stat.st_uid != os.geteuid()
            or stat.S_IMODE(current_stat.st_mode) & _WRITE_BITS
        ):
            raise OpsRuntimeIntegrityError(
                f"{field}_ancestor_permissions_or_path_invalid"
            )
        if current == active_root:
            return
        if active_root not in current.parents:
            raise OpsRuntimeIntegrityError(f"{field}_outside_active_root")
        current = current.parent


def _manifest(artifacts: Mapping[str, BoundArtifact], name: str) -> Mapping[str, Any]:
    value = artifacts[name].json_value
    if value is None:
        raise OpsRuntimeIntegrityError(f"{name}_not_loaded")
    return value


def _require_equal(actual: Any, expected: Any, code: str) -> None:
    if type(actual) is not type(expected) or actual != expected:
        raise OpsRuntimeIntegrityError(code)


def _manifest_identity(
    config: OpsRuntimeConfig,
    artifacts: Mapping[str, BoundArtifact],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    suite = _manifest(artifacts, "suite_manifest")
    data = _manifest(artifacts, "data_release_manifest")
    runtime = _manifest(artifacts, "runtime_manifest")
    authority = _manifest(artifacts, "authority_manifest")
    bm25 = _manifest(artifacts, "bm25_manifest")
    vector = _manifest(artifacts, "local_vector_manifest")
    graph = _manifest(artifacts, "graph_manifest")

    _require_equal(suite.get("schema_version"), "cloud-v2-suite-manifest-v1", "suite_schema_mismatch")
    _require_equal(suite.get("status"), "active", "suite_not_active")
    _require_equal(suite.get("suite_release_id"), config.suite_release_id, "suite_release_identity_mismatch")
    phase_state = _mapping(suite.get("phase_state"), "suite_phase_state")
    _require_equal(phase_state.get("runtime_activation_authorized"), True, "suite_activation_not_authorized")
    suite_ids = _mapping(suite.get("identities"), "suite_identities")
    suite_expected = {
        "data_release_manifest_sha256": artifacts["data_release_manifest"].sha256,
        "runtime_code_manifest_sha256": artifacts["runtime_manifest"].sha256,
        "authority_manifest_sha256": artifacts["authority_manifest"].sha256,
        "authority_database_sha256": artifacts["authority_database"].sha256,
        "bm25_manifest_sha256": artifacts["bm25_manifest"].sha256,
        "bm25_index_sha256": artifacts["bm25_index"].sha256,
        "local_vector_manifest_sha256": artifacts["local_vector_manifest"].sha256,
        "graph_manifest_sha256": artifacts["graph_manifest"].sha256,
        "graph_data_sha256": artifacts["graph_data"].sha256,
        "operator_manifest_sha256": config.operator_companion_sha256,
    }
    for field, expected in suite_expected.items():
        _require_equal(suite_ids.get(field), expected, f"suite_{field}_mismatch")
    for field in (
        "app_host_contract_sha256",
        "server_model_set_sha256",
        "embedding_manifest_sha256",
    ):
        _manifest_sha256(suite_ids.get(field), f"suite_{field}")

    _require_equal(data.get("schema_version"), "cloud-v2-data-release-manifest-v1", "data_schema_mismatch")
    _require_equal(data.get("status"), "active", "data_release_not_active")
    _require_equal(data.get("release_id"), config.data_release_id, "data_release_identity_mismatch")
    _require_equal(data.get("active_switch_authorized"), True, "data_release_activation_not_authorized")
    _require_equal(
        data.get("real_embedding_rebuild_required_after_stop_b"),
        False,
        "production_vector_not_ready",
    )
    data_authority = _mapping(data.get("authority"), "data_authority")
    for field, expected in {
        "manifest_sha256": artifacts["authority_manifest"].sha256,
        "database_sha256": artifacts["authority_database"].sha256,
    }.items():
        _require_equal(data_authority.get(field), expected, f"data_authority_{field}_mismatch")
    for field, expected in {
        "manifest_path": config.files["authority_manifest"].path,
        "database_path": config.files["authority_database"].path,
    }.items():
        _require_equal(data_authority.get(field), expected, f"data_authority_{field}_mismatch")
    data_derived = _mapping(data.get("derived"), "data_derived")
    for field, expected in {
        "bm25_manifest_sha256": artifacts["bm25_manifest"].sha256,
        "bm25_index_sha256": artifacts["bm25_index"].sha256,
        "local_vector_manifest_sha256": artifacts["local_vector_manifest"].sha256,
        "graph_manifest_sha256": artifacts["graph_manifest"].sha256,
        "graph_data_sha256": artifacts["graph_data"].sha256,
    }.items():
        _require_equal(data_derived.get(field), expected, f"data_derived_{field}_mismatch")
    for field, expected in {
        "bm25_manifest_path": config.files["bm25_manifest"].path,
        "bm25_index_path": config.files["bm25_index"].path,
        "local_vector_manifest_path": config.files["local_vector_manifest"].path,
        "graph_manifest_path": config.files["graph_manifest"].path,
        "graph_data_path": config.files["graph_data"].path,
    }.items():
        _require_equal(data_derived.get(field), expected, f"data_derived_{field}_mismatch")

    _require_equal(runtime.get("schema_version"), "cloud-v2-runtime-code-manifest-v1", "runtime_schema_mismatch")
    _require_equal(runtime.get("status"), "active", "runtime_not_active")
    _require_equal(
        runtime.get("file_set_sha256"),
        config.runtime_code_file_set_sha256,
        "runtime_code_identity_mismatch",
    )
    image_digest = runtime.get("image_digest")
    if not isinstance(image_digest, str) or not image_digest.startswith("sha256:") or not _SHA256.fullmatch(image_digest[7:]):
        raise OpsRuntimeIntegrityError("runtime_image_identity_invalid")

    _require_equal(authority.get("schema_version"), "cloud-rag-authority-v1", "authority_schema_mismatch")
    _require_equal(authority.get("status"), "active", "authority_not_active")
    _require_equal(authority.get("release_id"), config.data_release_id, "authority_release_identity_mismatch")
    authority_owner = _mapping(authority.get("authority"), "authority_owner")
    _require_equal(authority_owner.get("owner"), "rag_chunks.db", "authority_owner_mismatch")
    _require_equal(authority_owner.get("join_key"), "chunk_id", "authority_join_key_mismatch")
    authority_database = _mapping(authority.get("database"), "authority_database")
    _require_equal(authority_database.get("sha256"), artifacts["authority_database"].sha256, "authority_database_hash_mismatch")
    _require_equal(authority_database.get("integrity_check"), "ok", "authority_integrity_not_ok")
    _require_equal(authority_database.get("foreign_key_violation_count"), 0, "authority_foreign_key_violation")
    authority_database_path = (
        PurePosixPath(config.files["authority_manifest"].path).parent
        / _relative_path(authority_database.get("path"), "authority_database_path")
    ).as_posix()
    _require_equal(
        config.files["authority_database"].path,
        authority_database_path,
        "authority_database_path_mismatch",
    )
    counts = _mapping(authority.get("counts"), "authority_counts")
    chunk_count = _non_negative_int(counts.get("chunks"), "authority_chunk_count")
    document_count = _non_negative_int(counts.get("documents"), "authority_document_count")
    _require_equal(counts.get("provenance"), chunk_count, "authority_provenance_count_mismatch")

    _require_equal(
        bm25.get("schema_version"),
        "cloud-v2-sqlite-fts5-trigram-v1",
        "bm25_schema_mismatch",
    )
    _require_equal(bm25.get("status"), "active", "bm25_not_active")
    _require_equal(bm25.get("authority_release_id"), config.data_release_id, "bm25_authority_release_mismatch")
    _require_equal(bm25.get("authority_database_sha256"), artifacts["authority_database"].sha256, "bm25_authority_hash_mismatch")
    _require_equal(bm25.get("indexed_chunk_count"), chunk_count, "bm25_count_mismatch")
    bm25_index = _mapping(bm25.get("index"), "bm25_index")
    _require_equal(bm25_index.get("sha256"), artifacts["bm25_index"].sha256, "bm25_index_hash_mismatch")
    bm25_index_path = (
        PurePosixPath(config.files["bm25_manifest"].path).parent
        / _relative_path(bm25_index.get("path"), "bm25_index_path")
    ).as_posix()
    _require_equal(
        config.files["bm25_index"].path,
        bm25_index_path,
        "bm25_index_path_mismatch",
    )

    _require_equal(vector.get("manifest_schema_version"), "kg-local-vector-manifest-v2", "local_vector_schema_mismatch")
    vector_identity = _mapping(vector.get("identity"), "local_vector_identity")
    _require_equal(vector_identity.get("data_release_id"), config.local_vector_release_id, "local_vector_release_identity_mismatch")
    _require_equal(vector_identity.get("authority_manifest_sha256"), artifacts["authority_manifest"].sha256, "local_vector_authority_mismatch")
    vector_indexes = _mapping(vector.get("indexes"), "local_vector_indexes")
    if set(vector_indexes) != {"chunk", "entity"}:
        raise OpsRuntimeIntegrityError("local_vector_index_set_mismatch")
    vector_counts: dict[str, int] = {}
    for kind, file_name in (
        ("chunk", "local_vector_chunk_index"),
        ("entity", "local_vector_entity_index"),
    ):
        index = _mapping(vector_indexes[kind], f"local_vector_{kind}_index")
        _require_equal(index.get("index_sha256"), artifacts[file_name].sha256, f"local_vector_{kind}_hash_mismatch")
        expected_path = (
            PurePosixPath(config.files["local_vector_manifest"].path).parent
            / _relative_path(index.get("file"), f"local_vector_{kind}_file")
        ).as_posix()
        _require_equal(config.files[file_name].path, expected_path, f"local_vector_{kind}_path_mismatch")
        vector_counts[kind] = _non_negative_int(index.get("object_count"), f"local_vector_{kind}_count")
    _require_equal(vector_counts["chunk"], chunk_count, "local_vector_chunk_count_mismatch")

    _require_equal(graph.get("schema_version"), "cloud-scoped-graph-v1", "graph_schema_mismatch")
    _require_equal(graph.get("status"), "active", "graph_not_active")
    _require_equal(graph.get("release_id"), config.graph_release_id, "graph_release_identity_mismatch")
    _require_equal(graph.get("authority_release_id"), config.data_release_id, "graph_authority_release_mismatch")
    _require_equal(graph.get("authority_database_sha256"), artifacts["authority_database"].sha256, "graph_authority_hash_mismatch")
    graph_file = _mapping(graph.get("graph"), "graph_file")
    _require_equal(graph_file.get("sha256"), artifacts["graph_data"].sha256, "graph_data_hash_mismatch")
    graph_data_path = (
        PurePosixPath(config.files["graph_manifest"].path).parent
        / _relative_path(graph_file.get("path"), "graph_data_path")
    ).as_posix()
    _require_equal(
        config.files["graph_data"].path,
        graph_data_path,
        "graph_data_path_mismatch",
    )
    graph_binding = _mapping(graph.get("binding"), "graph_binding")
    _require_equal(
        graph_binding.get("authoritative_text_stored_in_graph"),
        False,
        "graph_authoritative_text_forbidden",
    )
    _require_equal(
        graph_binding.get("unresolved_sqlite_chunk_id_count"),
        0,
        "graph_unresolved_sqlite_chunk_ids",
    )
    graph_counts = _mapping(graph.get("counts"), "graph_counts")
    _require_equal(graph_counts.get("chunk_nodes"), chunk_count, "graph_chunk_count_mismatch")
    _require_equal(graph_counts.get("document_nodes"), document_count, "graph_document_count_mismatch")
    entity_count = _non_negative_int(graph_counts.get("entity_nodes"), "graph_entity_count")
    _non_negative_int(graph_counts.get("edges"), "graph_relation_count")
    _require_equal(vector_counts["entity"], entity_count, "local_vector_entity_count_mismatch")

    return (
        {
            "authority_release_id": config.data_release_id,
            "authority_sha256": artifacts["authority_database"].sha256,
            "document_count": document_count,
            "chunk_count": chunk_count,
            "status_code": "active_verified",
            "diagnostic_codes": [],
        },
        {
            "code_image_digest": image_digest,
            "data_release_id": config.data_release_id,
            "authority_sha256": artifacts["authority_database"].sha256,
            "app_host_contract_sha256": suite_ids.get("app_host_contract_sha256"),
            "server_model_set_sha256": suite_ids.get("server_model_set_sha256"),
            "embedding_manifest_sha256": suite_ids.get("embedding_manifest_sha256"),
            "local_vector_manifest_sha256": artifacts["local_vector_manifest"].sha256,
            "graph_manifest_sha256": artifacts["graph_manifest"].sha256,
            "operator_companion_identity": config.operator_companion_sha256,
            "status_code": "active_verified",
            "diagnostic_codes": [],
        },
        {
            "authority_chunk_count": chunk_count,
            "bm25_entry_count": _non_negative_int(bm25.get("indexed_chunk_count"), "bm25_entry_count"),
            "chunk_vector_count": vector_counts["chunk"],
            "entity_vector_count": vector_counts["entity"],
            "graph_entity_count": entity_count,
        },
    )


def _audit_authority_sqlite(raw: bytes) -> tuple[int, int]:
    try:
        connection = sqlite3.connect(":memory:")
        try:
            connection.deserialize(raw)
            connection.execute("PRAGMA query_only = ON")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()
            document_count = connection.execute(
                "SELECT COUNT(DISTINCT doc_name) FROM chunks"
            ).fetchone()
        finally:
            connection.close()
    except (AttributeError, sqlite3.Error) as exc:
        raise OpsRuntimeIntegrityError("authority_sqlite_read_failed") from exc
    if integrity != ("ok",) or chunk_count is None or document_count is None:
        raise OpsRuntimeIntegrityError("authority_sqlite_integrity_failed")
    return int(chunk_count[0]), int(document_count[0])


def _verify_active_root_descriptor(
    path: Path,
    descriptor: int,
    expected_identity: tuple[int, ...],
) -> None:
    try:
        named_before = os.stat(path, follow_symlinks=False)
        opened = os.fstat(descriptor)
        named_after = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise OpsRuntimeIntegrityError("active_root_unavailable") from exc
    if (
        not stat.S_ISDIR(named_before.st_mode)
        or stat.S_ISLNK(named_before.st_mode)
        or named_before.st_uid != os.geteuid()
        or stat.S_IMODE(named_before.st_mode) & _WRITE_BITS
        or not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) & _WRITE_BITS
        or _file_identity(named_before) != expected_identity
        or _file_identity(opened) != expected_identity
        or _file_identity(named_after) != expected_identity
    ):
        raise OpsRuntimeIntegrityError("active_root_identity_changed")


def _open_active_root_descriptor(
    path: Path,
    expected_identity: tuple[int, ...],
) -> int:
    flags = (
        os.O_RDONLY
        | os.O_CLOEXEC
        | os.O_NOFOLLOW
        | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise OpsRuntimeIntegrityError("active_root_unavailable") from exc
    try:
        _verify_active_root_descriptor(path, descriptor, expected_identity)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _bound_disk_utilization_percent(
    path: Path,
    descriptor: int,
    expected_identity: tuple[int, ...],
) -> float:
    _verify_active_root_descriptor(path, descriptor, expected_identity)
    try:
        disk = os.fstatvfs(descriptor)
    except OSError as exc:
        raise OpsRuntimeIntegrityError("capacity_disk_read_failed") from exc
    _verify_active_root_descriptor(path, descriptor, expected_identity)
    block_size = disk.f_frsize or disk.f_bsize
    total = disk.f_blocks * block_size
    used = (disk.f_blocks - disk.f_bfree) * block_size
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or total <= 0
        or isinstance(used, bool)
        or not isinstance(used, int)
        or used < 0
        or used > total
    ):
        raise OpsRuntimeIntegrityError("capacity_disk_read_failed")
    return round((used / total) * 100.0, 6)


def _quality_windows(
    config: OpsRuntimeConfig,
    artifacts: Mapping[str, BoundArtifact],
) -> Mapping[str, Mapping[str, Any]]:
    summary = _manifest(artifacts, "quality_summary")
    if set(summary) != {
        "schema_version",
        "status",
        "suite_release_id",
        "data_release_id",
        "windows",
    }:
        raise OpsRuntimeIntegrityError("quality_summary_shape_mismatch")
    _require_equal(summary.get("schema_version"), QUALITY_SUMMARY_SCHEMA_VERSION, "quality_summary_schema_mismatch")
    _require_equal(summary.get("status"), "active", "quality_summary_not_active")
    _require_equal(summary.get("suite_release_id"), config.suite_release_id, "quality_suite_identity_mismatch")
    _require_equal(summary.get("data_release_id"), config.data_release_id, "quality_data_identity_mismatch")
    windows = _mapping(summary.get("windows"), "quality_windows")
    if set(windows) != set(QUALITY_WINDOWS):
        raise OpsRuntimeIntegrityError("quality_window_set_mismatch")
    normalized: dict[str, Mapping[str, Any]] = {}
    metric_fields = {
        "request_count",
        "route_counts",
        "degraded_count",
        "evidence_bound_count",
        "false_verified_count",
    }
    for window in QUALITY_WINDOWS:
        metrics = _mapping(windows[window], f"quality_{window}")
        if set(metrics) != metric_fields:
            raise OpsRuntimeIntegrityError("quality_metric_shape_mismatch")
        request_count = _non_negative_int(metrics["request_count"], "quality_request_count")
        degraded_count = _non_negative_int(metrics["degraded_count"], "quality_degraded_count")
        evidence_bound_count = _non_negative_int(metrics["evidence_bound_count"], "quality_evidence_bound_count")
        false_verified_count = _non_negative_int(metrics["false_verified_count"], "quality_false_verified_count")
        if any(value > request_count for value in (degraded_count, evidence_bound_count, false_verified_count)):
            raise OpsRuntimeIntegrityError("quality_count_exceeds_request_count")
        route_counts = _mapping(metrics["route_counts"], "quality_route_counts")
        normalized_routes: dict[str, int] = {}
        for route, count in route_counts.items():
            if _IDENTIFIER.fullmatch(route) is None:
                raise OpsRuntimeIntegrityError("quality_route_invalid")
            normalized_routes[route] = _non_negative_int(count, "quality_route_count")
        if sum(normalized_routes.values()) != request_count:
            raise OpsRuntimeIntegrityError("quality_route_count_mismatch")
        normalized[window] = MappingProxyType(
            {
                "window": window,
                "request_count": request_count,
                "route_counts": MappingProxyType(dict(sorted(normalized_routes.items()))),
                "degraded_count": degraded_count,
                "degraded_rate": degraded_count / request_count if request_count else 0.0,
                "evidence_bound_rate": evidence_bound_count / request_count if request_count else 0.0,
                "false_verified_count": false_verified_count,
                "status_code": "active_verified",
                "diagnostic_codes": (),
            }
        )
    return MappingProxyType(normalized)


def _exact_request_body(body: Mapping[str, Any], fields: set[str]) -> dict[str, Any]:
    if not isinstance(body, Mapping) or set(body) != fields:
        raise OpsRuntimeError("ops_request_shape_mismatch")
    return dict(body)


class ProductionOpsRuntime:
    def __init__(
        self,
        *,
        config: OpsRuntimeConfig,
        artifacts: Mapping[str, BoundArtifact],
        authority_response: Mapping[str, Any],
        release_response: Mapping[str, Any],
        capacity_response: Mapping[str, Any],
        quality_windows: Mapping[str, Mapping[str, Any]],
        runner: CandidateJobRunner,
        workspace: CandidateWorkspaceBinding,
        active_identity_sha256: str,
        active_root_descriptor: int,
        active_root_identity: tuple[int, ...],
    ) -> None:
        self.config = config
        self.artifacts = MappingProxyType(dict(artifacts))
        self.authority_response = MappingProxyType(dict(authority_response))
        self.release_response = MappingProxyType(dict(release_response))
        self.capacity_response = MappingProxyType(dict(capacity_response))
        self.quality_windows = quality_windows
        self.runner = runner
        self.workspace = workspace
        self.active_identity_sha256 = active_identity_sha256
        self._active_root_descriptor = active_root_descriptor
        self._active_root_identity = active_root_identity
        self._descriptor_finalizer = weakref.finalize(
            self, os.close, active_root_descriptor
        )

    @classmethod
    def open(
        cls,
        config_path: str | Path,
        *,
        expected_config_sha256: str,
    ) -> "ProductionOpsRuntime":
        config = OpsRuntimeConfig.load(
            config_path,
            expected_sha256=expected_config_sha256,
        )
        try:
            active_root_stat = config.active_root.lstat()
        except OSError as exc:
            raise OpsRuntimeIntegrityError("active_root_unavailable") from exc
        artifacts = {
            name: _bind_artifact(
                config.active_root,
                binding,
                field=name,
                load_json=name in _JSON_FILES,
                load_bytes=name == "authority_database",
            )
            for name, binding in config.files.items()
        }
        authority, release, capacity = _manifest_identity(config, artifacts)
        authority_bytes = artifacts["authority_database"].raw_bytes
        if authority_bytes is None:
            raise OpsRuntimeIntegrityError("authority_sqlite_bytes_unavailable")
        sqlite_chunks, sqlite_documents = _audit_authority_sqlite(
            authority_bytes
        )
        artifacts["authority_database"] = replace(
            artifacts["authority_database"], raw_bytes=None
        )
        del authority_bytes
        if (
            sqlite_chunks != authority["chunk_count"]
            or sqlite_documents != authority["document_count"]
        ):
            raise OpsRuntimeIntegrityError("authority_sqlite_count_mismatch")
        quality = _quality_windows(config, artifacts)
        for name, artifact in artifacts.items():
            _verify_bound_artifact(artifact, field=name)

        active_identity_sha256 = _canonical_sha256(
            {
                "config_sha256": config.config_sha256,
                "suite_release_id": config.suite_release_id,
                "data_release_id": config.data_release_id,
                "runtime_code_file_set_sha256": config.runtime_code_file_set_sha256,
                "local_vector_release_id": config.local_vector_release_id,
                "graph_release_id": config.graph_release_id,
                "operator_companion_sha256": config.operator_companion_sha256,
                "files": {
                    name: artifact.sha256 for name, artifact in sorted(artifacts.items())
                },
            }
        )
        try:
            workspace = CandidateWorkspaceBinding(config.candidate_workspace)
            backends = BuiltinCandidateBackendRegistry(
                active_identity_sha256=active_identity_sha256
            )
            runner = CandidateJobRunner(
                backends.handlers(),
                confirmation_ledger_root=config.confirmation_ledger,
            )
        except MaintenanceJobError as exc:
            raise OpsRuntimeConfigError(exc.code) from exc
        active_root_identity = _file_identity(active_root_stat)
        active_root_descriptor = _open_active_root_descriptor(
            config.active_root,
            active_root_identity,
        )
        try:
            capacity = {
                **capacity,
                "disk_utilization_percent": _bound_disk_utilization_percent(
                    config.active_root,
                    active_root_descriptor,
                    active_root_identity,
                ),
                "status_code": "active_verified",
                "diagnostic_codes": [],
            }
            return cls(
                config=config,
                artifacts=artifacts,
                authority_response=authority,
                release_response=release,
                capacity_response=capacity,
                quality_windows=quality,
                runner=runner,
                workspace=workspace,
                active_identity_sha256=active_identity_sha256,
                active_root_descriptor=active_root_descriptor,
                active_root_identity=active_root_identity,
            )
        except BaseException:
            os.close(active_root_descriptor)
            raise

    def verify_active_bindings(self) -> None:
        _verify_active_root_descriptor(
            self.config.active_root,
            self._active_root_descriptor,
            self._active_root_identity,
        )
        for name, artifact in self.artifacts.items():
            _verify_read_only_ancestors(
                self.config.active_root,
                artifact.path,
                field=name,
            )
            _verify_bound_artifact(artifact, field=name)

    def capacity_snapshot(self) -> dict[str, Any]:
        self.verify_active_bindings()
        return {
            **self.capacity_response,
            "disk_utilization_percent": _bound_disk_utilization_percent(
                self.config.active_root,
                self._active_root_descriptor,
                self._active_root_identity,
            ),
            "status_code": "active_verified",
            "diagnostic_codes": [],
        }

    def close(self) -> None:
        self._descriptor_finalizer()

    def read_handlers(self) -> dict[str, OpsHandler]:
        def authority(
            _identity: VerifiedIdentity,
            body: Mapping[str, Any],
            _confirmation: VerifiedMaintenanceConfirmation | None,
        ) -> dict[str, Any]:
            _exact_request_body(body, set())
            self.verify_active_bindings()
            return dict(self.authority_response)

        def release(
            _identity: VerifiedIdentity,
            body: Mapping[str, Any],
            _confirmation: VerifiedMaintenanceConfirmation | None,
        ) -> dict[str, Any]:
            _exact_request_body(body, set())
            self.verify_active_bindings()
            return dict(self.release_response)

        def quality(
            _identity: VerifiedIdentity,
            body: Mapping[str, Any],
            _confirmation: VerifiedMaintenanceConfirmation | None,
        ) -> dict[str, Any]:
            value = _exact_request_body(body, {"window"})
            window = value["window"]
            if not isinstance(window, str) or window not in self.quality_windows:
                raise OpsRuntimeError("quality_window_invalid")
            self.verify_active_bindings()
            result = dict(self.quality_windows[window])
            result["route_counts"] = dict(result["route_counts"])
            result["diagnostic_codes"] = list(result["diagnostic_codes"])
            return result

        def capacity(
            _identity: VerifiedIdentity,
            body: Mapping[str, Any],
            _confirmation: VerifiedMaintenanceConfirmation | None,
        ) -> dict[str, Any]:
            _exact_request_body(body, set())
            return self.capacity_snapshot()

        return {
            "/ops/audit/authority": authority,
            "/ops/audit/release": release,
            "/ops/dashboard/quality": quality,
            "/ops/dashboard/capacity": capacity,
        }


def load_production_ops_runtime_from_environment(
    environ: Mapping[str, str] | None = None,
) -> ProductionOpsRuntime:
    source = os.environ if environ is None else environ
    config_path = source.get(CONFIG_ENVIRONMENT_VARIABLE)
    config_sha256 = source.get(CONFIG_SHA256_ENVIRONMENT_VARIABLE)
    if not config_path or not config_sha256:
        raise OpsRuntimeConfigError("ops_runtime_config_binding_required")
    return ProductionOpsRuntime.open(
        config_path,
        expected_config_sha256=config_sha256,
    )


def ops_startup_error_payload(error: BaseException) -> dict[str, Any]:
    code = error.code if isinstance(error, OpsRuntimeError) else "unknown_preflight_error"
    return {
        "schema_version": "cloud-v2-ops-startup-error-v1",
        "error": "ops_runtime_preflight_failed",
        "detail_code": code,
        "production_ready": False,
    }


__all__ = [
    "BUILTIN_BACKEND_REGISTRY_ID",
    "CONFIG_ENVIRONMENT_VARIABLE",
    "CONFIG_SCHEMA_VERSION",
    "CONFIG_SHA256_ENVIRONMENT_VARIABLE",
    "OpsRuntimeConfig",
    "OpsRuntimeConfigError",
    "OpsRuntimeError",
    "OpsRuntimeIntegrityError",
    "PRODUCTION_MODE",
    "ProductionOpsRuntime",
    "load_production_ops_runtime_from_environment",
    "ops_startup_error_payload",
]
