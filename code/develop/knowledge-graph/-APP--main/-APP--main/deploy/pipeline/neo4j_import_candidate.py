#!/usr/bin/env python3
"""Import one sealed scoped graph into a Neo4j candidate release namespace."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.stderr.write("formal Neo4j candidate import bootstrap context is required\n")
    raise SystemExit(2)

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rag_store.neo4j_graph_importer import (
    ScopedNeo4jImportError,
    ScopedNeo4jImporter,
)
from rag_store.runtime_neo4j_reader import (
    Neo4jReadBinding,
    ReadOnlyNeo4jError,
    open_neo4j_driver,
)
from rag_store.runtime_sqlite_reader import ReadOnlyAuthorityReader, ReadOnlySQLiteError
from rag_store.scoped_graph_contract import (
    NEO4J_DRIVER_NAME,
    NEO4J_DRIVER_VERSION,
    ScopedGraphContractError,
    load_scoped_graph_package,
)


CONFIG_ENVIRONMENT_VARIABLE = "KG_NEO4J_IMPORT_CONFIG"
CONFIG_SCHEMA_VERSION = "kg-scoped-neo4j-import-config-v1"
_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class Neo4jImportConfigError(RuntimeError):
    """The explicit candidate import configuration is invalid."""


@dataclass(frozen=True)
class _HeldSourceState:
    device: int
    inode: int
    mode: int
    link_count: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass
class _HeldSource:
    path: Path
    parent_descriptor: int
    descriptor: int
    parent_state: _HeldSourceState
    file_state: _HeldSourceState
    payload: bytes
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for descriptor in (self.descriptor, self.parent_descriptor):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _held_source_state(value: os.stat_result) -> _HeldSourceState:
    return _HeldSourceState(
        device=value.st_dev,
        inode=value.st_ino,
        mode=value.st_mode,
        link_count=value.st_nlink,
        size=value.st_size,
        mtime_ns=value.st_mtime_ns,
        ctime_ns=value.st_ctime_ns,
    )


def _read_held_source(
    descriptor: int,
    expected: _HeldSourceState,
    *,
    max_bytes: int,
) -> bytes:
    before = _held_source_state(os.fstat(descriptor))
    if before != expected or before.size < 0 or before.size > max_bytes:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source is not stably bounded"
        )
    chunks: list[bytes] = []
    offset = 0
    while offset < before.size:
        block = os.pread(descriptor, min(1024 * 1024, before.size - offset), offset)
        if not block:
            raise Neo4jImportConfigError(
                "formal Neo4j candidate import source became shorter"
            )
        chunks.append(block)
        offset += len(block)
    payload = b"".join(chunks)
    if _held_source_state(os.fstat(descriptor)) != expected or len(payload) != expected.size:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source changed while reading"
        )
    return payload


def _open_held_payload(raw_path: str | Path, *, max_bytes: int) -> _HeldSource:
    path = Path(raw_path)
    system_aliases = {
        Path("/var"): Path("/private/var"),
        Path("/tmp"): Path("/private/tmp"),
        Path("/etc"): Path("/private/etc"),
    }
    for alias, target in system_aliases.items():
        try:
            suffix = path.relative_to(alias)
        except ValueError:
            continue
        path = target / suffix
        break
    if (
        not path.is_absolute()
        or Path(os.path.abspath(path)) != path
        or path.parent.is_symlink()
        or path.parent.resolve(strict=True) != path.parent
    ):
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source path is not canonical"
        )
    parent_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    parent_descriptor: int | None = None
    descriptor: int | None = None
    try:
        parent_descriptor = os.open(path.parent, parent_flags)
        parent_state = _held_source_state(os.fstat(parent_descriptor))
        inspected = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        inspected_state = _held_source_state(inspected)
        if (
            not stat.S_ISDIR(parent_state.mode)
            or not stat.S_ISREG(inspected_state.mode)
            or inspected_state.link_count != 1
            or inspected_state.inode == 0
        ):
            raise Neo4jImportConfigError(
                "formal Neo4j candidate import source must be one regular file"
            )
        descriptor = os.open(path.name, file_flags, dir_fd=parent_descriptor)
        opened_state = _held_source_state(os.fstat(descriptor))
        if opened_state != inspected_state:
            raise Neo4jImportConfigError(
                "formal Neo4j candidate import source changed while opening"
            )
        payload = _read_held_source(
            descriptor,
            opened_state,
            max_bytes=max_bytes,
        )
        if (
            _held_source_state(
                os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
            )
            != opened_state
            or _held_source_state(os.fstat(parent_descriptor)) != parent_state
        ):
            raise Neo4jImportConfigError(
                "formal Neo4j candidate import source changed while holding"
            )
        return _HeldSource(
            path=path,
            parent_descriptor=parent_descriptor,
            descriptor=descriptor,
            parent_state=parent_state,
            file_state=opened_state,
            payload=payload,
        )
    except BaseException:
        for opened in (descriptor, parent_descriptor):
            if opened is not None:
                try:
                    os.close(opened)
                except OSError:
                    pass
        raise


def _revalidate_held_payload(held: _HeldSource) -> None:
    if held.closed:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import held source is closed"
        )
    try:
        parent_state = _held_source_state(os.fstat(held.parent_descriptor))
        descriptor_state = _held_source_state(os.fstat(held.descriptor))
        entry_state = _held_source_state(
            os.stat(
                held.path.name,
                dir_fd=held.parent_descriptor,
                follow_symlinks=False,
            )
        )
    except OSError as exc:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source binding changed"
        ) from exc
    if (
        parent_state != held.parent_state
        or descriptor_state != held.file_state
        or entry_state != held.file_state
        or held.path.parent.is_symlink()
        or held.path.parent.resolve(strict=True) != held.path.parent
    ):
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source binding changed"
        )
    payload = _read_held_source(
        held.descriptor,
        held.file_state,
        max_bytes=4 * 1024 * 1024,
    )
    if payload != held.payload:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source bytes changed"
        )


def _require_formal_bootstrap_context() -> None:
    evidence = sys.modules.get("deploy.cloud_v2.offline_evidence")
    require = getattr(evidence, "_require_formal_bootstrap_context", None)
    if not callable(require):
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import bootstrap context is required"
        )
    try:
        require()
    except Exception as exc:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import bootstrap context is required"
        ) from exc


def _require_isolated_python() -> None:
    if not (
        sys.flags.isolated == 1
        and sys.flags.no_site == 1
        and sys.flags.dont_write_bytecode == 1
    ):
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import requires Python -I -S -B"
        )


_FORMAL_NEO4J_IMPORT_SOURCE_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)
_EXECUTED_NEO4J_IMPORT_SOURCE = _open_held_payload(
    Path(__file__),
    max_bytes=4 * 1024 * 1024,
)
_FORMAL_NEO4J_IMPORT_SOURCE_SHA256: str | None = None
_FORMAL_NEO4J_IMPORT_SOURCE_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_NEO4J_IMPORT_ACTION_CLOSURE: tuple[object, ...] | None = None


def _neo4j_import_source_state_identity() -> dict[str, int]:
    state = _EXECUTED_NEO4J_IMPORT_SOURCE.file_state
    return {
        "device": state.device,
        "inode": state.inode,
        "mode": state.mode,
        "nlink": state.link_count,
        "size": state.size,
        "mtime_ns": state.mtime_ns,
        "ctime_ns": state.ctime_ns,
    }


def _current_neo4j_import_action_closure() -> tuple[object, ...]:
    return (
        main,
        _main_impl,
        run_candidate_import,
        _run_candidate_import_impl,
        load_config_from_environment,
    )


def _install_formal_neo4j_import_bootstrap_context(
    binding: Mapping[str, Any],
) -> None:
    global _FORMAL_NEO4J_IMPORT_ACTION_CLOSURE
    global _FORMAL_NEO4J_IMPORT_SOURCE_SHA256
    global _FORMAL_NEO4J_IMPORT_SOURCE_STATE_IDENTITY

    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except Neo4jImportConfigError as exc:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import bootstrap context is required"
        ) from exc
    required = {*_FORMAL_NEO4J_IMPORT_SOURCE_STATE_FIELDS, "sha256"}
    if (
        not isinstance(binding, Mapping)
        or set(binding) != required
        or not isinstance(binding.get("sha256"), str)
        or hashlib.sha256(_EXECUTED_NEO4J_IMPORT_SOURCE.payload).hexdigest()
        != binding["sha256"]
        or any(
            type(binding.get(field)) is not int or int(binding[field]) < 0
            for field in _FORMAL_NEO4J_IMPORT_SOURCE_STATE_FIELDS
        )
        or binding["inode"] == 0
        or binding["nlink"] != 1
        or not stat.S_ISREG(binding["mode"])
    ):
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source binding is malformed"
        )
    expected_state = {
        field: int(binding[field])
        for field in _FORMAL_NEO4J_IMPORT_SOURCE_STATE_FIELDS
    }
    try:
        _revalidate_held_payload(_EXECUTED_NEO4J_IMPORT_SOURCE)
    except Neo4jImportConfigError as exc:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source binding changed"
        ) from exc
    if _neo4j_import_source_state_identity() != expected_state:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source differs from held bootstrap bytes"
        )
    _FORMAL_NEO4J_IMPORT_SOURCE_SHA256 = str(binding["sha256"])
    _FORMAL_NEO4J_IMPORT_SOURCE_STATE_IDENTITY = expected_state
    _FORMAL_NEO4J_IMPORT_ACTION_CLOSURE = _current_neo4j_import_action_closure()


def _require_formal_neo4j_import_bootstrap_context() -> tuple[object, ...]:
    source_sha256 = _FORMAL_NEO4J_IMPORT_SOURCE_SHA256
    source_state = _FORMAL_NEO4J_IMPORT_SOURCE_STATE_IDENTITY
    actions = _FORMAL_NEO4J_IMPORT_ACTION_CLOSURE
    if (
        not isinstance(source_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_FORMAL_NEO4J_IMPORT_SOURCE_STATE_FIELDS)
        or any(
            type(source_state.get(field)) is not int
            or int(source_state[field]) < 0
            for field in _FORMAL_NEO4J_IMPORT_SOURCE_STATE_FIELDS
        )
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
        or not isinstance(actions, tuple)
        or len(actions) != 5
    ):
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import bootstrap context is required"
        )
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
        _revalidate_held_payload(_EXECUTED_NEO4J_IMPORT_SOURCE)
    except Neo4jImportConfigError as exc:
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_NEO4J_IMPORT_SOURCE.payload).hexdigest()
        != source_sha256
        or _neo4j_import_source_state_identity() != dict(source_state)
        or any(
            current is not expected
            for current, expected in zip(
                _current_neo4j_import_action_closure(), actions, strict=True
            )
        )
    ):
        raise Neo4jImportConfigError(
            "formal Neo4j candidate import source or action closure changed"
        )
    return actions


@dataclass(frozen=True)
class Neo4jImportConfig:
    path: Path
    sha256: str
    graph_manifest_path: Path
    authority_database_path: Path
    receipt_output_path: Path
    driver: str
    driver_version: str
    uri_env: str
    username_env: str
    password_env: str
    database_env: str
    batch_size: int
    query_timeout_seconds: float

    @classmethod
    def load(cls, raw_path: str | Path) -> "Neo4jImportConfig":
        path = _input_file(raw_path, "Neo4j import config")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise Neo4jImportConfigError("Neo4j import config is unreadable") from exc
        root = _strict_object(payload, "Neo4j import config")
        expected = {
            "schema_version",
            "graph_manifest_path",
            "authority_database_path",
            "receipt_output_path",
            "driver",
            "driver_version",
            "uri_env",
            "username_env",
            "password_env",
            "database_env",
            "batch_size",
            "query_timeout_seconds",
        }
        if set(root) != expected or root["schema_version"] != CONFIG_SCHEMA_VERSION:
            raise Neo4jImportConfigError("Neo4j import config field set is invalid")
        driver = _required_text(root["driver"], "driver")
        driver_version = _required_text(root["driver_version"], "driver_version")
        if driver != NEO4J_DRIVER_NAME or driver_version != NEO4J_DRIVER_VERSION:
            raise Neo4jImportConfigError("Neo4j import driver contract mismatch")
        references = {}
        for field in ("uri_env", "username_env", "password_env", "database_env"):
            value = _required_text(root[field], field)
            if not _ENVIRONMENT_NAME.fullmatch(value):
                raise Neo4jImportConfigError(
                    f"{field} must be an exact environment variable name"
                )
            references[field] = value
        batch_size = root["batch_size"]
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= 5000
        ):
            raise Neo4jImportConfigError("batch_size is invalid")
        timeout = root["query_timeout_seconds"]
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
        ):
            raise Neo4jImportConfigError("query_timeout_seconds is invalid")
        try:
            timeout_value = float(timeout)
        except (OverflowError, ValueError) as exc:
            raise Neo4jImportConfigError(
                "query_timeout_seconds is invalid"
            ) from exc
        if not math.isfinite(timeout_value):
            raise Neo4jImportConfigError("query_timeout_seconds is invalid")
        graph_manifest_path = _input_file(
            root["graph_manifest_path"], "graph manifest"
        )
        authority_database_path = _input_file(
            root["authority_database_path"], "authority database"
        )
        receipt_output_path = _new_output_file(
            root["receipt_output_path"], "import receipt"
        )
        return cls(
            path=path,
            sha256=hashlib.sha256(payload).hexdigest(),
            graph_manifest_path=graph_manifest_path,
            authority_database_path=authority_database_path,
            receipt_output_path=receipt_output_path,
            driver=driver,
            driver_version=driver_version,
            batch_size=batch_size,
            query_timeout_seconds=timeout_value,
            **references,
        )


def _strict_object(payload: bytes, field: str) -> dict[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise Neo4jImportConfigError(f"{field} contains a duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                Neo4jImportConfigError(f"{field} contains a non-finite value")
            ),
        )
    except Neo4jImportConfigError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Neo4jImportConfigError(f"{field} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise Neo4jImportConfigError(f"{field} must contain an object")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise Neo4jImportConfigError(f"{field} must be exact non-empty text")
    return value


def _absolute_path(value: Any, field: str) -> Path:
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    text = _required_text(value, field)
    path = Path(text)
    if not path.is_absolute() or Path(os.path.abspath(path)) != path:
        raise Neo4jImportConfigError(f"{field} must be a canonical absolute path")
    return path


def _input_file(value: Any, field: str) -> Path:
    path = _absolute_path(value, field)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise Neo4jImportConfigError(f"{field} is unavailable") from exc
    if resolved != path or not resolved.is_file() or resolved.is_symlink():
        raise Neo4jImportConfigError(f"{field} must be a canonical regular file")
    return resolved


def _new_output_file(value: Any, field: str) -> Path:
    path = _absolute_path(value, field)
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise Neo4jImportConfigError(f"{field} parent is unavailable") from exc
    if parent != path.parent or not parent.is_dir() or parent.is_symlink() or path.exists():
        raise Neo4jImportConfigError(f"{field} must be a new file in a canonical directory")
    return path


def _write_receipt(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _run_candidate_import_impl(
    config: Neo4jImportConfig,
    *,
    environment: Mapping[str, str],
    driver_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(config, Neo4jImportConfig):
        raise TypeError("config must be a Neo4jImportConfig")
    authority = ReadOnlyAuthorityReader(config.authority_database_path)
    try:
        if authority.integrity_check() != "ok" or authority.foreign_key_violation_count():
            raise Neo4jImportConfigError("authority database integrity gate failed")
        authority_ids = authority.provenance_chunk_ids()
        authority_chunk_documents = authority.chunk_document_map()
        if not authority_chunk_documents:
            raise Neo4jImportConfigError("authority database has no chunk provenance")
        if set(authority_chunk_documents) != set(authority_ids):
            raise Neo4jImportConfigError("authority chunk provenance is inconsistent")
        package = load_scoped_graph_package(
            config.graph_manifest_path,
            authority_chunk_documents=authority_chunk_documents,
        )
        if authority.database_sha256 != package.authority_database_sha256:
            raise Neo4jImportConfigError("authority database hash does not match graph")
        authority.verify_unchanged()
    finally:
        authority.close()

    binding = Neo4jReadBinding(
        graph_release_id=package.graph_release_id,
        driver=config.driver,
        driver_version=config.driver_version,
        uri_env=config.uri_env,
        username_env=config.username_env,
        password_env=config.password_env,
        database_env=config.database_env,
        query_timeout_seconds=config.query_timeout_seconds,
        max_records=1000,
    )
    driver_kwargs = {"environment": environment}
    if driver_factory is not None:
        driver_kwargs["driver_factory"] = driver_factory
    driver, database = open_neo4j_driver(binding, **driver_kwargs)
    try:
        receipt = ScopedNeo4jImporter(
            driver=driver,
            database=database,
            batch_size=config.batch_size,
            query_timeout_seconds=config.query_timeout_seconds,
        ).import_candidate(package)
    finally:
        try:
            driver.close()
        except Exception as exc:
            raise ScopedNeo4jImportError("Neo4j candidate driver close failed") from exc
    complete = {
        **receipt,
        "config_sha256": config.sha256,
        "authority_database_sha256": package.authority_database_sha256,
        "network_policy": "deployment-configured-neo4j-only",
    }
    _write_receipt(config.receipt_output_path, complete)
    return complete


def run_candidate_import(
    config: Neo4jImportConfig,
    *,
    environment: Mapping[str, str],
    driver_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    actions = _require_formal_neo4j_import_bootstrap_context()
    return actions[3](
        config,
        environment=environment,
        driver_factory=driver_factory,
    )


def load_config_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Neo4jImportConfig:
    source = os.environ if environment is None else environment
    configured = source.get(CONFIG_ENVIRONMENT_VARIABLE, "")
    if not configured:
        raise Neo4jImportConfigError(
            f"{CONFIG_ENVIRONMENT_VARIABLE} must identify the explicit import config"
        )
    return Neo4jImportConfig.load(configured)


def _main_impl(
    *,
    _action_closure: tuple[object, ...] | None = None,
) -> int:
    actions = (
        (load_config_from_environment, _run_candidate_import_impl)
        if _action_closure is None
        else _action_closure
    )
    if (
        not isinstance(actions, tuple)
        or len(actions) != 2
        or any(not callable(action) for action in actions)
    ):
        raise Neo4jImportConfigError(
            "Neo4j candidate import CLI action closure is malformed"
        )
    load_config_action, import_action = actions
    try:
        config = load_config_action()
        receipt = import_action(config, environment=os.environ)
    except (
        Neo4jImportConfigError,
        ScopedGraphContractError,
        ScopedNeo4jImportError,
        ReadOnlyNeo4jError,
        ReadOnlySQLiteError,
        OSError,
        ValueError,
    ):
        print(
            json.dumps(
                {"ok": False, "error": "neo4j_candidate_import_failed"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "status": receipt["status"],
                "graph_release_id": receipt["graph_release_id"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def main() -> int:
    try:
        actions = _require_formal_neo4j_import_bootstrap_context()
    except Neo4jImportConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return actions[1](_action_closure=(actions[4], actions[3]))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CONFIG_ENVIRONMENT_VARIABLE",
    "CONFIG_SCHEMA_VERSION",
    "Neo4jImportConfig",
    "Neo4jImportConfigError",
    "load_config_from_environment",
    "run_candidate_import",
]
