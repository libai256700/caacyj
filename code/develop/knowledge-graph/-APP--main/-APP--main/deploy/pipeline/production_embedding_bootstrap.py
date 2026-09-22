#!/usr/bin/env python3
"""Run the production vector candidate from one hash-bound exact release."""

from __future__ import annotations

import contextlib
import base64
import csv
import ctypes
import hashlib
import importlib
import importlib.abc
import importlib.util
import io
import json
import multiprocessing
import os
import re
import stat
import sys
import sysconfig
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


RUNTIME_LOCK_SCHEMA_VERSION = "kg-production-embedding-runtime-lock-v2"
RUNTIME_LOCK_SHA256_ENV = "KG_PRODUCTION_VECTOR_RUNTIME_LOCK_SHA256"
BASE_SUITE_MANIFEST_SHA256_ENV = "KG_PRODUCTION_VECTOR_BASE_SUITE_MANIFEST_SHA256"
_CHILD_RUNTIME_LOCK_PATH_ENV = "_KG_PRODUCTION_VECTOR_RUNTIME_LOCK_PATH"
_BOOTSTRAP_CONTEXT_SCHEMA_VERSION = "kg-production-embedding-bootstrap-context-v1"
_BOOTSTRAP_RELATIVE = "deploy/pipeline/production_embedding_bootstrap.py"
_CANDIDATE_RELATIVE = "deploy/pipeline/production_embedding_candidate.py"
_RUNTIME_LOCK_SCHEMA_RELATIVE = (
    "deploy/pipeline/production_embedding_runtime_lock.schema.json"
)
_PENDING_CONTRACT_RELATIVE = "server-runtime/production-vector-build-contract.json"
_BUILDER_ALLOWLIST_RELATIVE = "server-runtime/builder-file-allowlist.json"
_REQUIREMENTS_RELATIVE = "server-runtime/requirements.lock"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s=]+)$")
_RECORD_SHA256 = re.compile(r"^sha256=([A-Za-z0-9_-]{43})$")
_RECORD_SIZE = re.compile(r"^(0|[1-9][0-9]*)$")
_FORBIDDEN_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
_PROTECTED_MODULE_ROOTS = frozenset({"deploy", "pipeline", "rag_store"})
_MAX_JSON_BYTES = 64 * 1024 * 1024
_MAX_RUNTIME_FILE_BYTES = 512 * 1024 * 1024
_MAX_RUNTIME_TREE_BYTES = 4 * 1024 * 1024 * 1024
_MAX_RUNTIME_TREE_FILES = 200_000
_NATIVE_SUFFIXES = (".a", ".dll", ".dylib", ".pyd", ".so")
_SPAWN_PREFLIGHT_MAX_BYTES = 4096
_SPAWN_PREFLIGHT_TIMEOUT_SECONDS = 30.0


class ProductionEmbeddingBootstrapError(RuntimeError):
    """Sanitized exact-runtime bootstrap failure."""


@dataclass(frozen=True)
class _HeldSource:
    module: str
    path: Path
    payload: bytes
    sha256: str
    is_package: bool


@dataclass
class _BoundRelease:
    suite_root: Path
    server_runtime_root: Path
    code_root: Path
    code_root_fd: int
    code_root_identity: tuple[int, int, int]
    suite_manifest_sha256: str
    pending_contract_sha256: str
    builder_file_set_sha256: str
    sources: dict[str, _HeldSource]

    def close(self) -> None:
        try:
            os.close(self.code_root_fd)
        except OSError:
            pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _identity_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _record_set_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value) + b"\n").hexdigest()


def _strict_object(payload: bytes) -> dict[str, Any]:
    def pairs_hook(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ProductionEmbeddingBootstrapError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs_hook,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ProductionEmbeddingBootstrapError("non-finite JSON value")
            ),
        )
    except ProductionEmbeddingBootstrapError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProductionEmbeddingBootstrapError("invalid JSON") from None
    if type(value) is not dict:
        raise ProductionEmbeddingBootstrapError("JSON root is not an object")
    return value


def _typed_equal(value: Any, expected: Any) -> bool:
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


def _file_state(state: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        state.st_dev,
        state.st_ino,
        state.st_mode,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
    )


def _directory_state(state: os.stat_result) -> tuple[int, int, int]:
    return (state.st_dev, state.st_ino, state.st_mode)


def _stable_bytes(
    path: Path,
    *,
    maximum_bytes: int = _MAX_JSON_BYTES,
    require_unique: bool = True,
) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise ProductionEmbeddingBootstrapError("unsafe file path")
    try:
        resolved = path.resolve(strict=True)
        if resolved != path:
            raise ProductionEmbeddingBootstrapError("non-canonical file path")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except OSError:
        raise ProductionEmbeddingBootstrapError("file is unavailable") from None
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > maximum_bytes
            or (require_unique and before.st_nlink != 1)
        ):
            raise ProductionEmbeddingBootstrapError("unsafe file")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) > maximum_bytes
            or len(payload) != after.st_size
            or _file_state(before) != _file_state(after)
            or (require_unique and after.st_nlink != 1)
        ):
            raise ProductionEmbeddingBootstrapError("file changed while read")
        return payload
    finally:
        os.close(descriptor)


def _file_identity(path: Path, *, require_unique: bool = False) -> dict[str, Any]:
    payload = _stable_bytes(
        path,
        maximum_bytes=_MAX_RUNTIME_FILE_BYTES,
        require_unique=require_unique,
    )
    state = path.stat(follow_symlinks=False)
    return {
        "path": str(path),
        "device": state.st_dev,
        "inode": state.st_ino,
        "mode": state.st_mode,
        "nlink": state.st_nlink,
        "size": state.st_size,
        "mtime_ns": state.st_mtime_ns,
        "ctime_ns": state.st_ctime_ns,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _canonical_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise ProductionEmbeddingBootstrapError("invalid relative path")
    if (
        unicodedata.normalize("NFC", value) != value
        or any(
            unicodedata.category(character) in _FORBIDDEN_UNICODE_CATEGORIES
            for character in value
        )
        or "\\" in value
        or "//" in value
        or "\x00" in value
    ):
        raise ProductionEmbeddingBootstrapError("invalid relative path")
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise ProductionEmbeddingBootstrapError("invalid relative path")
    return value


def _bootstrap_layout() -> tuple[Path, Path, Path, Path]:
    raw = Path(__file__)
    if not raw.is_absolute() or raw.is_symlink():
        raise ProductionEmbeddingBootstrapError("bootstrap path is unsafe")
    try:
        bootstrap = raw.resolve(strict=True)
    except OSError:
        raise ProductionEmbeddingBootstrapError("bootstrap path is unavailable") from None
    if bootstrap != raw or bootstrap.as_posix().endswith("/__pycache__"):
        raise ProductionEmbeddingBootstrapError("bootstrap path is not exact")
    try:
        code_root = bootstrap.parents[2]
        server_runtime = code_root.parent
        suite_root = server_runtime.parent
    except IndexError:
        raise ProductionEmbeddingBootstrapError("bootstrap layout is invalid") from None
    if bootstrap != code_root / _BOOTSTRAP_RELATIVE:
        raise ProductionEmbeddingBootstrapError("bootstrap layout is invalid")
    return bootstrap, code_root, server_runtime, suite_root


def _require_isolated_flags() -> None:
    checks = (
        sys.flags.isolated == 1,
        sys.flags.ignore_environment == 1,
        sys.flags.no_site == 1,
        sys.flags.no_user_site == 1,
        sys.flags.dont_write_bytecode == 1,
    )
    if not all(checks):
        raise ProductionEmbeddingBootstrapError("python isolation flags are required")


def _required_hash_environment(name: str) -> str:
    value = os.environ.get(name)
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ProductionEmbeddingBootstrapError("required external hash anchor is missing")
    return value


def _open_code_root(code_root: Path) -> tuple[int, tuple[int, int, int]]:
    if code_root.is_symlink() or code_root.resolve(strict=True) != code_root:
        raise ProductionEmbeddingBootstrapError("import root is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(code_root, flags)
        state = os.fstat(descriptor)
    except OSError:
        raise ProductionEmbeddingBootstrapError("import root is unavailable") from None
    if not stat.S_ISDIR(state.st_mode):
        os.close(descriptor)
        raise ProductionEmbeddingBootstrapError("import root is unsafe")
    return descriptor, _directory_state(state)


def _held_relative_bytes(root_fd: int, relative: str) -> bytes:
    parts = PurePosixPath(_canonical_relative(relative)).parts
    directory_fd = os.dup(root_fd)
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        for component in parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        file_flags |= getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(parts[-1], file_flags, dir_fd=directory_fd)
        try:
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ProductionEmbeddingBootstrapError("builder file is unsafe")
            chunks: list[bytes] = []
            remaining = _MAX_JSON_BYTES + 1
            while remaining:
                chunk = os.read(file_fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(file_fd)
            if (
                len(payload) > _MAX_JSON_BYTES
                or len(payload) != after.st_size
                or _file_state(before) != _file_state(after)
                or after.st_nlink != 1
            ):
                raise ProductionEmbeddingBootstrapError("builder file changed")
            return payload
        finally:
            os.close(file_fd)
    except OSError:
        raise ProductionEmbeddingBootstrapError("builder file is unavailable") from None
    finally:
        os.close(directory_fd)


def _module_name(relative: str) -> tuple[str, bool] | None:
    if not relative.endswith(".py"):
        return None
    parts = list(PurePosixPath(relative).parts)
    if parts[:2] == ["deploy", "pipeline"]:
        module_parts = ["pipeline", *parts[2:]]
    elif parts[:2] == ["deploy", "rag_store"]:
        module_parts = ["rag_store", *parts[2:]]
    elif parts[0] == "deploy":
        module_parts = parts
    else:
        raise ProductionEmbeddingBootstrapError("builder Python path is outside import roots")
    is_package = module_parts[-1] == "__init__.py"
    if is_package:
        module_parts = module_parts[:-1]
    else:
        module_parts[-1] = module_parts[-1][:-3]
    if not module_parts:
        raise ProductionEmbeddingBootstrapError("builder module name is invalid")
    return ".".join(module_parts), is_package


def _load_bound_release() -> _BoundRelease:
    bootstrap, code_root, server_runtime, suite_root = _bootstrap_layout()
    manifest_path = suite_root / "SUITE_MANIFEST.json"
    manifest_payload = _stable_bytes(manifest_path)
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    if manifest_sha256 != _required_hash_environment(BASE_SUITE_MANIFEST_SHA256_ENV):
        raise ProductionEmbeddingBootstrapError("base suite manifest hash mismatch")
    manifest = _strict_object(manifest_payload)
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise ProductionEmbeddingBootstrapError("base suite components are invalid")
    component_hashes: dict[str, str] = {}
    for record in components:
        if not isinstance(record, Mapping) or set(record) != {"path", "sha256"}:
            raise ProductionEmbeddingBootstrapError("base suite components are invalid")
        relative = _canonical_relative(record.get("path"))
        digest = record.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ProductionEmbeddingBootstrapError("base suite components are invalid")
        if relative in component_hashes:
            raise ProductionEmbeddingBootstrapError("duplicate base suite component")
        component_hashes[relative] = digest

    pending_path = suite_root / _PENDING_CONTRACT_RELATIVE
    pending_payload = _stable_bytes(pending_path)
    pending_sha256 = hashlib.sha256(pending_payload).hexdigest()
    if component_hashes.get(_PENDING_CONTRACT_RELATIVE) != pending_sha256:
        raise ProductionEmbeddingBootstrapError("pending contract is not suite-bound")
    pending = _strict_object(pending_payload)
    builder = pending.get("builder")
    if not isinstance(builder, Mapping):
        raise ProductionEmbeddingBootstrapError("builder contract is invalid")
    records = builder.get("files")
    if not isinstance(records, list) or not records:
        raise ProductionEmbeddingBootstrapError("builder closure is invalid")
    normalized: list[dict[str, str]] = []
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {"path", "sha256"}:
            raise ProductionEmbeddingBootstrapError("builder closure is invalid")
        relative = _canonical_relative(record.get("path"))
        digest = record.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ProductionEmbeddingBootstrapError("builder closure is invalid")
        normalized.append({"path": relative, "sha256": digest})
    paths = [record["path"] for record in normalized]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ProductionEmbeddingBootstrapError("builder closure is not canonical")
    if builder.get("file_set_sha256") != _record_set_sha256(normalized):
        raise ProductionEmbeddingBootstrapError("builder closure hash mismatch")
    required = {
        _BOOTSTRAP_RELATIVE,
        _CANDIDATE_RELATIVE,
        _RUNTIME_LOCK_SCHEMA_RELATIVE,
    }
    if not required.issubset(paths):
        raise ProductionEmbeddingBootstrapError("builder closure lacks bootstrap files")

    allowlist_path = suite_root / _BUILDER_ALLOWLIST_RELATIVE
    allowlist_payload = _stable_bytes(allowlist_path)
    allowlist_sha256 = hashlib.sha256(allowlist_payload).hexdigest()
    if (
        builder.get("file_allowlist_path") != "builder-file-allowlist.json"
        or builder.get("file_allowlist_sha256") != allowlist_sha256
        or component_hashes.get(_BUILDER_ALLOWLIST_RELATIVE) != allowlist_sha256
    ):
        raise ProductionEmbeddingBootstrapError("builder allowlist hash mismatch")
    allowlist = _strict_object(allowlist_payload)
    if allowlist.get("files") != paths:
        raise ProductionEmbeddingBootstrapError("builder allowlist differs from closure")

    requirements_path = suite_root / _REQUIREMENTS_RELATIVE
    requirements_sha256 = hashlib.sha256(_stable_bytes(requirements_path)).hexdigest()
    if component_hashes.get(_REQUIREMENTS_RELATIVE) != requirements_sha256:
        raise ProductionEmbeddingBootstrapError("requirements lock is not suite-bound")

    code_root_fd, code_root_identity = _open_code_root(code_root)
    sources: dict[str, _HeldSource] = {}
    try:
        for record in normalized:
            payload = _held_relative_bytes(code_root_fd, record["path"])
            digest = hashlib.sha256(payload).hexdigest()
            suite_relative = "server-runtime/code/" + record["path"]
            if digest != record["sha256"] or component_hashes.get(suite_relative) != digest:
                raise ProductionEmbeddingBootstrapError("builder source hash mismatch")
            module_binding = _module_name(record["path"])
            if module_binding is None:
                continue
            module, is_package = module_binding
            if module in sources:
                raise ProductionEmbeddingBootstrapError("duplicate builder module")
            sources[module] = _HeldSource(
                module=module,
                path=code_root / record["path"],
                payload=payload,
                sha256=digest,
                is_package=is_package,
            )
        if sources["pipeline.production_embedding_bootstrap"].path != bootstrap:
            raise ProductionEmbeddingBootstrapError("bootstrap source path mismatch")
        identities = manifest.get("identities")
        if (
            not isinstance(identities, Mapping)
            or identities.get("production_vector_build_contract_sha256")
            != pending_sha256
            or identities.get("builder_file_allowlist_sha256") != allowlist_sha256
            or identities.get("builder_code_file_set_sha256")
            != builder.get("file_set_sha256")
        ):
            raise ProductionEmbeddingBootstrapError("suite builder identity mismatch")
        return _BoundRelease(
            suite_root=suite_root,
            server_runtime_root=server_runtime,
            code_root=code_root,
            code_root_fd=code_root_fd,
            code_root_identity=code_root_identity,
            suite_manifest_sha256=manifest_sha256,
            pending_contract_sha256=pending_sha256,
            builder_file_set_sha256=str(builder["file_set_sha256"]),
            sources=sources,
        )
    except BaseException:
        os.close(code_root_fd)
        raise


def _revalidate_release(release: _BoundRelease) -> None:
    try:
        held = os.fstat(release.code_root_fd)
        current = os.stat(release.code_root, follow_symlinks=False)
    except OSError:
        raise ProductionEmbeddingBootstrapError("exact import root changed") from None
    if (
        _directory_state(held) != release.code_root_identity
        or _directory_state(current) != release.code_root_identity
        or release.code_root.resolve(strict=True) != release.code_root
    ):
        raise ProductionEmbeddingBootstrapError("exact import root changed")
    for source in release.sources.values():
        payload = _stable_bytes(source.path)
        if hashlib.sha256(payload).hexdigest() != source.sha256:
            raise ProductionEmbeddingBootstrapError("builder source changed")


def _overlaps_import_root(path: Path, import_roots: Sequence[Path]) -> bool:
    for import_root in import_roots:
        try:
            path.relative_to(import_root)
            return True
        except ValueError:
            pass
        try:
            import_root.relative_to(path)
            return True
        except ValueError:
            pass
    return False


def _tree_records(
    root: Path,
    *,
    import_roots: Sequence[Path] = (),
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    total_bytes = 0
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        names.sort()
        files.sort()
        directory_path = Path(directory)
        for name in [*names, *files]:
            path = directory_path / name
            relative = path.relative_to(root).as_posix()
            state_before = path.lstat()
            if stat.S_ISLNK(state_before.st_mode):
                target = os.readlink(path)
                state_after = path.lstat()
                if _file_state(state_before) != _file_state(state_after):
                    raise ProductionEmbeddingBootstrapError("runtime symlink changed")
                record: dict[str, Any] = {
                    "path": relative,
                    "kind": "symlink",
                    "target": target,
                    "mode": state_after.st_mode,
                    "mtime_ns": state_after.st_mtime_ns,
                    "ctime_ns": state_after.st_ctime_ns,
                }
                resolved = path.resolve(strict=True)
                if resolved.is_dir() and _overlaps_import_root(path, import_roots):
                    raise ProductionEmbeddingBootstrapError(
                        "import-reachable runtime directory symlink is unsafe"
                    )
                if resolved.is_file():
                    payload = _stable_bytes(
                        resolved,
                        maximum_bytes=_MAX_RUNTIME_FILE_BYTES,
                        require_unique=False,
                    )
                    record.update(
                        {
                            "resolved_path": str(resolved),
                            "resolved_sha256": hashlib.sha256(payload).hexdigest(),
                            "resolved_size": len(payload),
                        }
                    )
                records.append(record)
                if len(records) > _MAX_RUNTIME_TREE_FILES:
                    raise ProductionEmbeddingBootstrapError(
                        "runtime tree has too many files"
                    )
                continue
            if stat.S_ISDIR(state_before.st_mode):
                continue
            if not stat.S_ISREG(state_before.st_mode):
                raise ProductionEmbeddingBootstrapError("runtime tree has special file")
            payload = _stable_bytes(
                path,
                maximum_bytes=_MAX_RUNTIME_FILE_BYTES,
                require_unique=False,
            )
            total_bytes += len(payload)
            if total_bytes > _MAX_RUNTIME_TREE_BYTES:
                raise ProductionEmbeddingBootstrapError("runtime tree is too large")
            records.append(
                {
                    "path": relative,
                    "kind": "file",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "mode": state_before.st_mode,
                    "nlink": state_before.st_nlink,
                    "mtime_ns": state_before.st_mtime_ns,
                    "ctime_ns": state_before.st_ctime_ns,
                }
            )
            if len(records) > _MAX_RUNTIME_TREE_FILES:
                raise ProductionEmbeddingBootstrapError("runtime tree has too many files")
    records.sort(key=lambda item: item["path"])
    return records


def _tree_identity(
    root: Path,
    *,
    import_roots: Sequence[Path] = (),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if root.is_symlink() or root.resolve(strict=True) != root or not root.is_dir():
        raise ProductionEmbeddingBootstrapError("runtime root is unsafe")
    records = _tree_records(root, import_roots=import_roots)
    state = root.stat(follow_symlinks=False)
    identity = {
        "path": str(root),
        "device": state.st_dev,
        "inode": state.st_ino,
        "mode": state.st_mode,
        "file_count": len(records),
        "file_set_sha256": _identity_sha256(records),
    }
    return identity, records


def _canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _record_target(
    library_root: Path,
    value: Any,
    installation_root: Path,
) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or unicodedata.normalize("NFC", value) != value
        or any(
            unicodedata.category(character) in _FORBIDDEN_UNICODE_CATEGORIES
            for character in value
        )
    ):
        raise ProductionEmbeddingBootstrapError("distribution RECORD path is invalid")
    relative = PurePosixPath(value)
    parts = relative.parts
    saw_named_component = False
    if relative.is_absolute() or relative.as_posix() != value or not parts:
        raise ProductionEmbeddingBootstrapError("distribution RECORD path is invalid")
    for part in parts:
        if part in {"", "."}:
            raise ProductionEmbeddingBootstrapError("distribution RECORD path is invalid")
        if part == "..":
            if saw_named_component:
                raise ProductionEmbeddingBootstrapError(
                    "distribution RECORD path is not canonical"
                )
        else:
            saw_named_component = True
    if not saw_named_component:
        raise ProductionEmbeddingBootstrapError("distribution RECORD path is invalid")
    target = Path(os.path.abspath(library_root.joinpath(*parts)))
    if target == installation_root or not target.is_relative_to(installation_root):
        raise ProductionEmbeddingBootstrapError(
            "distribution RECORD path escapes the installation root"
        )
    try:
        if target.is_symlink() or target.resolve(strict=True) != target:
            raise ProductionEmbeddingBootstrapError(
                "distribution RECORD path is unsafe"
            )
    except OSError:
        raise ProductionEmbeddingBootstrapError(
            "distribution RECORD file is unavailable"
        ) from None
    return target


def _record_digest(value: str) -> bytes:
    match = _RECORD_SHA256.fullmatch(value)
    if match is None:
        raise ProductionEmbeddingBootstrapError("distribution RECORD hash is invalid")
    try:
        digest = base64.b64decode(
            match.group(1) + "=",
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError):
        raise ProductionEmbeddingBootstrapError(
            "distribution RECORD hash is invalid"
        ) from None
    if len(digest) != hashlib.sha256().digest_size:
        raise ProductionEmbeddingBootstrapError("distribution RECORD hash is invalid")
    return digest


def _requirements_identity(
    server_runtime: Path,
    library_roots: Sequence[Path],
    installation_root: Path,
) -> dict[str, Any]:
    path = server_runtime / "requirements.lock"
    payload = _stable_bytes(path)
    expected: dict[str, str] = {}
    for raw_line in payload.decode("ascii").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _REQUIREMENT.fullmatch(line)
        if match is None:
            raise ProductionEmbeddingBootstrapError("requirements lock is invalid")
        name = _canonical_distribution_name(match.group(1))
        if name in expected:
            raise ProductionEmbeddingBootstrapError("requirements lock has duplicates")
        expected[name] = match.group(2)
    if not expected:
        raise ProductionEmbeddingBootstrapError("requirements lock is empty")

    if (
        installation_root.is_symlink()
        or installation_root.resolve(strict=True) != installation_root
        or not installation_root.is_dir()
    ):
        raise ProductionEmbeddingBootstrapError("installation root is unsafe")
    roots = tuple(sorted(set(library_roots), key=str))
    if not roots:
        raise ProductionEmbeddingBootstrapError("runtime library roots are unavailable")
    for root in roots:
        if (
            root.is_symlink()
            or root.resolve(strict=True) != root
            or not root.is_dir()
            or not root.is_relative_to(installation_root)
        ):
            raise ProductionEmbeddingBootstrapError("runtime library root is unsafe")

    observed: dict[str, dict[str, Any]] = {}
    owned_paths: dict[Path, str] = {}
    owned_identities: dict[tuple[int, int], tuple[Path, str]] = {}
    owned_records: list[dict[str, Any]] = []
    total_owned_bytes = 0
    for root in roots:
        metadata_paths: list[Path] = []
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if not child.name.endswith(".dist-info"):
                continue
            if child.is_symlink() or not child.is_dir():
                raise ProductionEmbeddingBootstrapError(
                    "distribution metadata directory is unsafe"
                )
            metadata_paths.append(child / "METADATA")
        for metadata_path in metadata_paths:
            metadata = _stable_bytes(metadata_path, maximum_bytes=16 * 1024 * 1024)
            name = None
            version = None
            try:
                metadata_lines = metadata.decode("utf-8").splitlines()
            except UnicodeDecodeError:
                raise ProductionEmbeddingBootstrapError(
                    "distribution metadata is invalid"
                ) from None
            for raw_line in metadata_lines:
                if raw_line.startswith("Name: ") and name is None:
                    name = _canonical_distribution_name(raw_line[6:].strip())
                elif raw_line.startswith("Version: ") and version is None:
                    version = raw_line[9:].strip()
                if name is not None and version is not None:
                    break
            if name is None or version is None or name in observed:
                raise ProductionEmbeddingBootstrapError("distribution metadata is invalid")
            record_path = metadata_path.parent / "RECORD"
            record_payload = _stable_bytes(record_path, maximum_bytes=64 * 1024 * 1024)
            try:
                rows = list(
                    csv.reader(
                        io.StringIO(record_payload.decode("utf-8"), newline=""),
                        strict=True,
                    )
                )
            except (UnicodeDecodeError, csv.Error):
                raise ProductionEmbeddingBootstrapError("distribution RECORD is invalid") from None
            if not rows or len(rows) > _MAX_RUNTIME_TREE_FILES:
                raise ProductionEmbeddingBootstrapError("distribution RECORD is invalid")
            distribution_records: list[dict[str, Any]] = []
            distribution_targets: set[Path] = set()
            for row in rows:
                if len(row) != 3:
                    raise ProductionEmbeddingBootstrapError(
                        "distribution RECORD row is invalid"
                    )
                raw_target, hash_field, size_field = row
                target = _record_target(root, raw_target, installation_root)
                if target in distribution_targets or target in owned_paths:
                    raise ProductionEmbeddingBootstrapError(
                        "distribution RECORD ownership is duplicated"
                    )
                file_payload = _stable_bytes(
                    target,
                    maximum_bytes=_MAX_RUNTIME_FILE_BYTES,
                    require_unique=False,
                )
                if target == record_path:
                    if hash_field or size_field:
                        raise ProductionEmbeddingBootstrapError(
                            "distribution RECORD self-entry is invalid"
                        )
                else:
                    if not _RECORD_SIZE.fullmatch(size_field):
                        raise ProductionEmbeddingBootstrapError(
                            "distribution RECORD size is invalid"
                        )
                    if int(size_field) != len(file_payload):
                        raise ProductionEmbeddingBootstrapError(
                            "distribution RECORD size drifted"
                        )
                    if _record_digest(hash_field) != hashlib.sha256(file_payload).digest():
                        raise ProductionEmbeddingBootstrapError(
                            "distribution RECORD hash drifted"
                        )
                state = target.stat(follow_symlinks=False)
                file_identity = (state.st_dev, state.st_ino)
                if file_identity in owned_identities:
                    raise ProductionEmbeddingBootstrapError(
                        "distribution RECORD ownership is duplicated"
                    )
                record = {
                    "path": str(target),
                    "sha256": hashlib.sha256(file_payload).hexdigest(),
                    "size": len(file_payload),
                }
                distribution_targets.add(target)
                owned_paths[target] = name
                owned_identities[file_identity] = (target, name)
                distribution_records.append(record)
                owned_records.append({"owner": name, **record})
                total_owned_bytes += len(file_payload)
                if (
                    len(owned_records) > _MAX_RUNTIME_TREE_FILES
                    or total_owned_bytes > _MAX_RUNTIME_TREE_BYTES
                ):
                    raise ProductionEmbeddingBootstrapError(
                        "distribution RECORD closure is too large"
                    )
            if metadata_path not in distribution_targets or record_path not in distribution_targets:
                raise ProductionEmbeddingBootstrapError(
                    "distribution RECORD lacks required metadata ownership"
                )
            distribution_records.sort(key=lambda item: item["path"])
            observed[name] = {
                "name": name,
                "version": version,
                "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
                "record_sha256": hashlib.sha256(record_payload).hexdigest(),
                "record_count": len(rows),
                "owned_file_count": len(distribution_records),
                "owned_file_set_sha256": _identity_sha256(distribution_records),
            }
    if set(observed) != set(expected) or any(
        observed[name]["version"] != version for name, version in expected.items()
    ):
        raise ProductionEmbeddingBootstrapError("installed distributions differ from lock")

    site_packages: list[dict[str, Any]] = []
    for root in roots:
        records = _tree_records(root, import_roots=(root,))
        present_paths: set[Path] = set()
        owned_directories = {root}
        closure: list[dict[str, Any]] = []
        for record in records:
            target = root / record["path"]
            owner = owned_paths.get(target)
            if record.get("kind") != "file" or owner is None:
                raise ProductionEmbeddingBootstrapError(
                    "site-packages contains an unowned runtime file"
                )
            present_paths.add(target)
            parent = target.parent
            while parent != root:
                owned_directories.add(parent)
                parent = parent.parent
            closure.append({"owner": owner, **record})
        for target in owned_paths:
            if target.is_relative_to(root) and target not in present_paths:
                raise ProductionEmbeddingBootstrapError(
                    "distribution RECORD ownership is incomplete"
                )
        for directory, names, _files in os.walk(root, topdown=True, followlinks=False):
            directory_path = Path(directory)
            for name in names:
                child = directory_path / name
                if child.is_symlink() or child not in owned_directories:
                    raise ProductionEmbeddingBootstrapError(
                        "site-packages contains an unowned runtime directory"
                    )
        closure.sort(key=lambda item: item["path"])
        site_packages.append(
            {
                "path": str(root),
                "file_count": len(closure),
                "file_set_sha256": _identity_sha256(closure),
            }
        )
    owned_records.sort(key=lambda item: item["path"])
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "distributions": [observed[name] for name in sorted(observed)],
        "owned_file_count": len(owned_records),
        "owned_file_set_sha256": _identity_sha256(owned_records),
        "site_packages": site_packages,
    }


def _process_executable() -> Path:
    if sys.platform == "darwin":
        try:
            library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            function = library.proc_pidpath
            function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
            function.restype = ctypes.c_int
            buffer = ctypes.create_string_buffer(4096)
            length = function(os.getpid(), buffer, len(buffer))
        except (AttributeError, OSError):
            raise ProductionEmbeddingBootstrapError("process executable unavailable") from None
        if length <= 0:
            raise ProductionEmbeddingBootstrapError("process executable unavailable")
        path = Path(os.fsdecode(buffer.raw[:length]))
    elif Path("/proc/self/exe").exists():
        path = Path(os.path.realpath("/proc/self/exe"))
    else:
        path = Path(sys.executable)
    return path.resolve(strict=True)


def _validated_sys_path(value: Any, field: str) -> list[str]:
    if type(value) is not list or any(
        not isinstance(item, str)
        or not item
        or not Path(item).is_absolute()
        or os.path.abspath(item) != item
        for item in value
    ):
        raise ProductionEmbeddingBootstrapError(f"{field} is invalid")
    if len(value) != len(set(value)):
        raise ProductionEmbeddingBootstrapError(f"{field} has duplicates")
    return list(value)


def _expected_worker_sys_path(
    bootstrap_sys_path: Any,
    library_paths: Mapping[str, Any],
) -> list[str]:
    result = _validated_sys_path(bootstrap_sys_path, "bootstrap sys.path")
    for key in ("purelib", "platlib"):
        value = library_paths.get(key)
        if (
            not isinstance(value, str)
            or not value
            or not Path(value).is_absolute()
            or os.path.abspath(value) != value
        ):
            raise ProductionEmbeddingBootstrapError("runtime library path is invalid")
        if value not in result:
            result.append(value)
    return result


def _runtime_quick_identity(release: _BoundRelease) -> dict[str, Any]:
    executable = Path(sys.executable)
    base_executable = Path(sys._base_executable)
    if (
        not executable.is_absolute()
        or executable.is_symlink()
        or not base_executable.is_absolute()
    ):
        raise ProductionEmbeddingBootstrapError("python executable is unsafe")
    executable = executable.resolve(strict=True)
    base_executable = base_executable.resolve(strict=True)
    process_executable = _process_executable()
    paths: dict[str, str] = {}
    for name in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = sysconfig.get_path(name)
        if not value:
            raise ProductionEmbeddingBootstrapError("python library path unavailable")
        paths[name] = str(Path(value).resolve(strict=True))
    bootstrap_sys_path = _validated_sys_path(list(sys.path), "bootstrap sys.path")
    return {
        "implementation": sys.implementation.name,
        "version": ".".join(str(item) for item in sys.version_info[:3]),
        "version_sha256": hashlib.sha256(sys.version.encode("utf-8")).hexdigest(),
        "cache_tag": sys.implementation.cache_tag,
        "soabi": str(sysconfig.get_config_var("SOABI") or ""),
        "flags": {
            "isolated": sys.flags.isolated,
            "ignore_environment": sys.flags.ignore_environment,
            "no_site": sys.flags.no_site,
            "no_user_site": sys.flags.no_user_site,
            "dont_write_bytecode": sys.flags.dont_write_bytecode,
        },
        "bootstrap_sys_path": bootstrap_sys_path,
        "worker_sys_path": _expected_worker_sys_path(bootstrap_sys_path, paths),
        "executable": _file_identity(executable),
        "base_executable": _file_identity(base_executable),
        "process_executable": _file_identity(process_executable),
        "library_paths": paths,
        "exact_import_root": {
            "path": str(release.code_root),
            "device": release.code_root_identity[0],
            "inode": release.code_root_identity[1],
            "mode": release.code_root_identity[2],
        },
    }


def _runtime_identity(release: _BoundRelease) -> dict[str, Any]:
    quick = _runtime_quick_identity(release)
    prefix = Path(sys.prefix).resolve(strict=True)
    base_prefix = Path(sys.base_prefix).resolve(strict=True)
    library_roots = tuple(
        sorted(
            {
                Path(path)
                for path in quick["library_paths"].values()
                if Path(path).name in {"site-packages", "dist-packages"}
            },
            key=str,
        )
    )
    runtime_prefixes = (prefix, base_prefix)
    if any(
        not any(
            library_root == runtime_prefix
            or library_root.is_relative_to(runtime_prefix)
            for runtime_prefix in runtime_prefixes
        )
        for library_root in library_roots
    ):
        raise ProductionEmbeddingBootstrapError(
            "runtime library root is outside locked prefixes"
        )
    prefix_identity, prefix_records = _tree_identity(
        prefix,
        import_roots=library_roots,
    )
    if base_prefix == prefix:
        base_identity = prefix_identity
        base_records = prefix_records
    else:
        base_identity, base_records = _tree_identity(
            base_prefix,
            import_roots=library_roots,
        )
    dependencies = _requirements_identity(
        release.server_runtime_root,
        library_roots,
        prefix,
    )
    native_records = [
        {"root": root_name, **record}
        for root_name, records in (
            ("prefix", prefix_records),
            ("base_prefix", base_records),
        )
        for record in records
        if record["path"].lower().endswith(_NATIVE_SUFFIXES)
    ]
    return {
        "quick": quick,
        "runtime_roots": {
            "prefix": prefix_identity,
            "base_prefix": base_identity,
        },
        "dependencies": dependencies,
        "native_closure": {
            "file_count": len(native_records),
            "file_set_sha256": _identity_sha256(native_records),
        },
        "release_binding": {
            "suite_manifest_sha256": release.suite_manifest_sha256,
            "pending_contract_sha256": release.pending_contract_sha256,
            "builder_file_set_sha256": release.builder_file_set_sha256,
        },
    }


def _write_new_external(path: Path, payload: bytes, suite_root: Path) -> str:
    if not path.is_absolute() or os.path.abspath(path) != str(path) or path.is_symlink():
        raise ProductionEmbeddingBootstrapError("runtime lock output path is invalid")
    try:
        path.relative_to(suite_root)
    except ValueError:
        pass
    else:
        raise ProductionEmbeddingBootstrapError("runtime lock must be suite-external")
    parent = path.parent
    if parent.is_symlink() or parent.resolve(strict=True) != parent:
        raise ProductionEmbeddingBootstrapError("runtime lock parent is unsafe")
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(parent, directory_flags)
    try:
        parent_identity = _directory_state(os.fstat(parent_fd))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path.name, flags, 0o640, dir_fd=parent_fd)
        created = True
        try:
            view = memoryview(payload)
            while view:
                count = os.write(descriptor, view)
                if count <= 0:
                    raise OSError("write made no progress")
                view = view[count:]
            os.fsync(descriptor)
        except BaseException:
            os.close(descriptor)
            if created:
                os.unlink(path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            raise
        else:
            os.close(descriptor)
        os.fsync(parent_fd)
        if (
            _directory_state(os.fstat(parent_fd)) != parent_identity
            or _directory_state(os.stat(parent, follow_symlinks=False)) != parent_identity
        ):
            os.unlink(path.name, dir_fd=parent_fd)
            os.fsync(parent_fd)
            raise ProductionEmbeddingBootstrapError("runtime lock parent changed")
        written = _stable_bytes(path)
        if written != payload:
            os.unlink(path.name, dir_fd=parent_fd)
            os.fsync(parent_fd)
            raise ProductionEmbeddingBootstrapError("runtime lock write mismatch")
    except OSError:
        raise ProductionEmbeddingBootstrapError("runtime lock write failed") from None
    finally:
        os.close(parent_fd)
    return hashlib.sha256(payload).hexdigest()


def _capture_runtime(output: str) -> dict[str, Any]:
    release = _load_bound_release()
    try:
        identity = _runtime_identity(release)
        lock = {
            "schema_version": RUNTIME_LOCK_SCHEMA_VERSION,
            "identity": identity,
            "identity_sha256": _identity_sha256(identity),
        }
        payload = _canonical_bytes(lock) + b"\n"
        output_path = Path(output)
        digest = _write_new_external(output_path, payload, release.suite_root)
        _revalidate_release(release)
        return {
            "command": "capture-runtime",
            "ok": True,
            "runtime_lock_sha256": digest,
            "runtime_identity_sha256": lock["identity_sha256"],
        }
    finally:
        release.close()


def _read_runtime_lock(
    path: Path,
    release: _BoundRelease,
) -> tuple[dict[str, Any], str]:
    if not path.is_absolute() or os.path.abspath(path) != str(path) or path.is_symlink():
        raise ProductionEmbeddingBootstrapError("runtime lock path is invalid")
    try:
        path.relative_to(release.suite_root)
    except ValueError:
        pass
    else:
        raise ProductionEmbeddingBootstrapError("runtime lock must be suite-external")
    payload = _stable_bytes(path)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != _required_hash_environment(RUNTIME_LOCK_SHA256_ENV):
        raise ProductionEmbeddingBootstrapError("runtime lock hash mismatch")
    lock = _strict_object(payload)
    if set(lock) != {"schema_version", "identity", "identity_sha256"}:
        raise ProductionEmbeddingBootstrapError("runtime lock shape is invalid")
    if lock.get("schema_version") != RUNTIME_LOCK_SCHEMA_VERSION:
        raise ProductionEmbeddingBootstrapError("runtime lock schema mismatch")
    identity = lock.get("identity")
    if type(identity) is not dict or lock.get("identity_sha256") != _identity_sha256(identity):
        raise ProductionEmbeddingBootstrapError("runtime lock identity is invalid")
    return lock, digest


def _load_runtime_lock(
    path: Path,
    release: _BoundRelease,
) -> tuple[dict[str, Any], str]:
    lock, digest = _read_runtime_lock(path, release)
    identity = lock["identity"]
    if not _typed_equal(_runtime_identity(release), identity):
        raise ProductionEmbeddingBootstrapError("runtime identity drifted")
    binding = identity.get("release_binding")
    if not _typed_equal(
        binding,
        {
            "suite_manifest_sha256": release.suite_manifest_sha256,
            "pending_contract_sha256": release.pending_contract_sha256,
            "builder_file_set_sha256": release.builder_file_set_sha256,
        },
    ):
        raise ProductionEmbeddingBootstrapError("runtime release binding drifted")
    return lock, digest


class _HeldSourceLoader(importlib.abc.Loader):
    def __init__(self, source: _HeldSource) -> None:
        self.source = source
        self.source_sha256 = source.sha256

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        expected_package = (
            self.source.module
            if self.source.is_package
            else self.source.module.rpartition(".")[0]
        )
        spec = getattr(module, "__spec__", None)
        if (
            spec is None
            or spec.loader is not self
            or spec.origin != str(self.source.path)
        ):
            raise ImportError("held module spec metadata is invalid")
        module.__file__ = str(self.source.path)
        module.__loader__ = self
        module.__package__ = expected_package
        if self.source.is_package:
            spec.submodule_search_locations = []
            module.__path__ = []
        code = compile(
            self.source.payload,
            str(self.source.path),
            "exec",
            dont_inherit=True,
        )
        exec(code, module.__dict__)


class _SyntheticPackageLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        module.__path__ = []


class _HeldSourceFinder(importlib.abc.MetaPathFinder):
    def __init__(self, sources: Mapping[str, _HeldSource]) -> None:
        self.sources = dict(sources)

    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"deploy", "pipeline", "rag_store"}:
            return importlib.util.spec_from_loader(
                fullname,
                _SyntheticPackageLoader(),
                origin="held-byte-exact-release-package",
                is_package=True,
            )
        source = self.sources.get(fullname)
        if source is not None:
            spec = importlib.util.spec_from_loader(
                fullname,
                _HeldSourceLoader(source),
                origin=str(source.path),
                is_package=source.is_package,
            )
            if spec is None:
                raise ImportError("held module spec is unavailable")
            spec.has_location = True
            if source.is_package:
                spec.submodule_search_locations = []
            return spec
        root = fullname.split(".", 1)[0]
        if root in _PROTECTED_MODULE_ROOTS:
            raise ImportError("module is outside the hash-bound exact-release closure")
        return None


def _install_bound_imports(release: _BoundRelease, identity: Mapping[str, Any]) -> None:
    if any(
        name == root or name.startswith(root + ".")
        for name in sys.modules
        for root in _PROTECTED_MODULE_ROOTS
    ):
        raise ProductionEmbeddingBootstrapError("protected module was imported too early")
    quick = identity.get("quick")
    if not isinstance(quick, Mapping):
        raise ProductionEmbeddingBootstrapError("runtime quick identity is invalid")
    paths = quick.get("library_paths")
    if not isinstance(paths, Mapping):
        raise ProductionEmbeddingBootstrapError("runtime library paths are invalid")
    bootstrap_sys_path = _validated_sys_path(
        quick.get("bootstrap_sys_path"),
        "bootstrap sys.path",
    )
    worker_sys_path = _validated_sys_path(
        quick.get("worker_sys_path"),
        "worker sys.path",
    )
    if (
        list(sys.path) != bootstrap_sys_path
        or _expected_worker_sys_path(bootstrap_sys_path, paths) != worker_sys_path
    ):
        raise ProductionEmbeddingBootstrapError("bootstrap sys.path drifted")
    for key in ("purelib", "platlib"):
        value = paths.get(key)
        if not isinstance(value, str):
            raise ProductionEmbeddingBootstrapError("runtime library path is invalid")
        if value not in sys.path:
            sys.path.append(value)
    if list(sys.path) != worker_sys_path:
        raise ProductionEmbeddingBootstrapError("worker sys.path drifted")
    sys.meta_path.insert(0, _HeldSourceFinder(release.sources))


def _runtime_spawn_preflight_child(connection: Any) -> None:
    try:
        payload = {
            "held_import_finder": any(
                isinstance(finder, _HeldSourceFinder) for finder in sys.meta_path
            ),
            "runtime_lock_sha256": os.environ.get(RUNTIME_LOCK_SHA256_ENV),
            "worker_sys_path_sha256": _identity_sha256(list(sys.path)),
        }
        connection.send_bytes(_canonical_bytes(payload))
    finally:
        connection.close()


def _verify_multiprocessing_spawn(
    lock: Mapping[str, Any],
    runtime_lock_sha256: str,
) -> dict[str, Any]:
    identity = lock.get("identity")
    quick = identity.get("quick") if isinstance(identity, Mapping) else None
    if not isinstance(quick, Mapping):
        raise ProductionEmbeddingBootstrapError("runtime quick identity is invalid")
    worker_sys_path = _validated_sys_path(
        quick.get("worker_sys_path"),
        "worker sys.path",
    )
    expected = {
        "held_import_finder": True,
        "runtime_lock_sha256": runtime_lock_sha256,
        "worker_sys_path_sha256": _identity_sha256(worker_sys_path),
    }
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_runtime_spawn_preflight_child,
        args=(send_connection,),
        name="kg-production-runtime-spawn-preflight",
        daemon=True,
    )
    started = False
    try:
        try:
            process.start()
            started = True
        except BaseException:
            raise ProductionEmbeddingBootstrapError(
                "multiprocessing spawn preflight failed"
            ) from None
        finally:
            send_connection.close()
        if not receive_connection.poll(_SPAWN_PREFLIGHT_TIMEOUT_SECONDS):
            raise ProductionEmbeddingBootstrapError(
                "multiprocessing spawn preflight failed"
            )
        try:
            payload = receive_connection.recv_bytes(
                maxlength=_SPAWN_PREFLIGHT_MAX_BYTES
            )
        except (EOFError, OSError):
            raise ProductionEmbeddingBootstrapError(
                "multiprocessing spawn preflight failed"
            ) from None
        process.join(1.0)
        if process.is_alive() or process.exitcode != 0:
            raise ProductionEmbeddingBootstrapError(
                "multiprocessing spawn preflight failed"
            )
        observed = _strict_object(payload)
        if not _typed_equal(observed, expected):
            raise ProductionEmbeddingBootstrapError(
                "multiprocessing spawn preflight drifted"
            )
        return {"start_method": "spawn", **observed}
    finally:
        receive_connection.close()
        try:
            send_connection.close()
        except OSError:
            pass
        if started and process.is_alive():
            process.terminate()
            process.join(1.0)
            if process.is_alive():
                process.kill()
                process.join(1.0)


def _bootstrap_context(release: _BoundRelease, runtime_lock_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": _BOOTSTRAP_CONTEXT_SCHEMA_VERSION,
        "bootstrap_sha256": release.sources[
            "pipeline.production_embedding_bootstrap"
        ].sha256,
        "candidate_sha256": release.sources[
            "pipeline.production_embedding_candidate"
        ].sha256,
        "runtime_lock_sha256": runtime_lock_sha256,
        "builder_file_set_sha256": release.builder_file_set_sha256,
        "exact_import_root_sha256": hashlib.sha256(
            str(release.code_root).encode("utf-8")
        ).hexdigest(),
    }


class _ProductionEmbeddingBootstrapContext:
    """Capability bound to one open exact-release descriptor closure."""

    def __init__(
        self,
        release: _BoundRelease,
        runtime_lock_sha256: str,
        candidate: Any,
    ) -> None:
        self._release = release
        self._runtime_lock_sha256 = runtime_lock_sha256
        self._candidate = candidate
        self._closed = False
        self._action_closure = (
            _revalidate_release,
            _bootstrap_context,
            _run_bound,
            type(self).revalidate_candidate,
        )

    def revalidate_candidate(self) -> dict[str, Any]:
        if self._closed or self._action_closure != (
            _revalidate_release,
            _bootstrap_context,
            _run_bound,
            type(self).revalidate_candidate,
        ):
            raise ProductionEmbeddingBootstrapError(
                "candidate bootstrap action closure changed"
            )
        _revalidate_release(self._release)
        source = self._release.sources["pipeline.production_embedding_candidate"]
        loader = getattr(self._candidate, "__loader__", None)
        if (
            sys.modules.get("pipeline.production_embedding_candidate")
            is not self._candidate
            or not isinstance(loader, _HeldSourceLoader)
            or loader.source is not source
            or loader.source_sha256 != source.sha256
        ):
            raise ProductionEmbeddingBootstrapError(
                "candidate held-source binding changed"
            )
        return _bootstrap_context(self._release, self._runtime_lock_sha256)

    def close(self) -> None:
        self._closed = True


def _run_bound(runtime_lock_path: str, candidate_args: Sequence[str]) -> int:
    release = _load_bound_release()
    try:
        lock, runtime_lock_sha256 = _load_runtime_lock(Path(runtime_lock_path), release)
        _install_bound_imports(release, lock["identity"])
        candidate = importlib.import_module("pipeline.production_embedding_candidate")
        previous = os.environ.get(_CHILD_RUNTIME_LOCK_PATH_ENV)
        os.environ[_CHILD_RUNTIME_LOCK_PATH_ENV] = runtime_lock_path
        try:
            if candidate_args == ("verify-runtime",) or list(candidate_args) == [
                "verify-runtime"
            ]:
                spawn_preflight = _verify_multiprocessing_spawn(
                    lock,
                    runtime_lock_sha256,
                )
                _revalidate_release(release)
                print(
                    json.dumps(
                        {
                            "command": "verify-runtime",
                            "multiprocessing_spawn_preflight": spawn_preflight,
                            "ok": True,
                            **_bootstrap_context(release, runtime_lock_sha256),
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                return 0
            if not candidate_args or candidate_args[0] not in {
                "materialize",
                "validate",
                "build",
            }:
                raise ProductionEmbeddingBootstrapError("candidate command is invalid")
            buffered = io.StringIO()
            candidate_context = _ProductionEmbeddingBootstrapContext(
                release, runtime_lock_sha256, candidate
            )
            try:
                with contextlib.redirect_stdout(buffered):
                    result = candidate._run_from_exact_release_bootstrap(
                        list(candidate_args),
                        candidate_context,
                    )
            finally:
                candidate_context.close()
        finally:
            if previous is None:
                os.environ.pop(_CHILD_RUNTIME_LOCK_PATH_ENV, None)
            else:
                os.environ[_CHILD_RUNTIME_LOCK_PATH_ENV] = previous
        _revalidate_release(release)
        output = buffered.getvalue()
        if output:
            sys.stdout.write(output)
        return int(result)
    finally:
        release.close()


def _install_multiprocessing_child() -> None:
    _require_isolated_flags()
    runtime_lock_path = os.environ.get(_CHILD_RUNTIME_LOCK_PATH_ENV)
    if not runtime_lock_path:
        raise ProductionEmbeddingBootstrapError("child runtime lock path is missing")
    release = _load_bound_release()
    try:
        lock, _digest = _read_runtime_lock(Path(runtime_lock_path), release)
        identity = lock.get("identity")
        quick = identity.get("quick") if isinstance(identity, Mapping) else None
        if not isinstance(quick, Mapping):
            raise ProductionEmbeddingBootstrapError("runtime quick identity is invalid")
        bootstrap_sys_path = _validated_sys_path(
            quick.get("bootstrap_sys_path"),
            "bootstrap sys.path",
        )
        worker_sys_path = _validated_sys_path(
            quick.get("worker_sys_path"),
            "worker sys.path",
        )
        library_paths = quick.get("library_paths")
        if (
            not isinstance(library_paths, Mapping)
            or _expected_worker_sys_path(bootstrap_sys_path, library_paths)
            != worker_sys_path
            or list(sys.path) != worker_sys_path
        ):
            raise ProductionEmbeddingBootstrapError("worker sys.path drifted")
        sys.path[:] = bootstrap_sys_path
        lock, _digest = _load_runtime_lock(Path(runtime_lock_path), release)
        _install_bound_imports(release, lock["identity"])
        _revalidate_release(release)
    finally:
        release.close()


def _parse(argv: Sequence[str]) -> tuple[str, str, list[str]]:
    values = list(argv)
    if len(values) == 3 and values[0] == "capture-runtime" and values[1] == "--output":
        return "capture-runtime", values[2], []
    if len(values) >= 3 and values[0] == "--runtime-lock":
        return "run", values[1], values[2:]
    raise ProductionEmbeddingBootstrapError("bootstrap command is invalid")


def main(argv: Sequence[str] | None = None) -> int:
    command = "unknown"
    try:
        _require_isolated_flags()
        command, path, candidate_args = _parse(sys.argv[1:] if argv is None else argv)
        if command == "capture-runtime":
            result = _capture_runtime(path)
            print(
                json.dumps(
                    result,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        return _run_bound(path, candidate_args)
    except (
        OSError,
        TypeError,
        ValueError,
        ProductionEmbeddingBootstrapError,
    ):
        print(
            json.dumps(
                {
                    "command": command,
                    "error": "production_embedding_bootstrap_failed",
                    "ok": False,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__mp_main__":
    try:
        _install_multiprocessing_child()
    except BaseException:
        os._exit(78)
elif __name__ == "__main__":
    raise SystemExit(main())
