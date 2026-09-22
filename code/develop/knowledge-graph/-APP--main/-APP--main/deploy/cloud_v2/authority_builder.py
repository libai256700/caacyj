#!/usr/bin/env python3
"""Build a clean revision-a-r9 SQLite authority in a candidate-only root."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.stderr.write("formal authority builder CLI bootstrap context is required\n")
    raise SystemExit(2)

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from .source_extract import EXTRACTOR_VERSION, extract_source, validate_ocr_runtime
from .source_scope import ApprovedSourceScope, CANDIDATE_ID, sha256_file


AUTHORITY_SCHEMA_VERSION = "cloud-rag-authority-v1"
CHUNKING_POLICY_VERSION = "cloud-v2-paragraph-1200-v1"
_SQLITE_HEADER_SIZE = 100
_SQLITE_CHANGE_COUNTER_OFFSET = 24
_SQLITE_PAGE_COUNT_OFFSET = 28
_SQLITE_SCHEMA_COOKIE_OFFSET = 40
_SQLITE_VERSION_VALID_FOR_OFFSET = 92
_SQLITE_LIBRARY_VERSION_OFFSET = 96
AUTHORITY_SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE document_sources (
    document_source_id TEXT PRIMARY KEY,
    doc_name TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL UNIQUE,
    source_sha256 TEXT NOT NULL,
    source_page_count INTEGER,
    authority TEXT NOT NULL,
    published_at TEXT,
    ocr_engine TEXT,
    ocr_version TEXT,
    ocr_backend TEXT,
    ocr_language TEXT,
    extractor_version TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_document_sources_sha ON document_sources(source_sha256);
CREATE INDEX idx_document_sources_run ON document_sources(import_run_id);
CREATE TABLE documents (
    doc_name TEXT PRIMARY KEY,
    doc_path TEXT NOT NULL UNIQUE,
    chunk_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    doc_name TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(doc_name) REFERENCES documents(doc_name),
    UNIQUE(doc_name, chunk_index)
);
CREATE INDEX idx_chunks_doc ON chunks(doc_name);
CREATE INDEX idx_chunks_doc_idx ON chunks(doc_name, chunk_index);
CREATE TABLE chunk_provenance (
    chunk_id TEXT PRIMARY KEY,
    document_source_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    pdf_page_start INTEGER NOT NULL,
    pdf_page_end INTEGER NOT NULL,
    printed_page_start INTEGER,
    printed_page_end INTEGER,
    chapter_id TEXT,
    chapter_title TEXT,
    section_id TEXT,
    section_title TEXT,
    content_type TEXT NOT NULL,
    confidence REAL,
    review_status TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    FOREIGN KEY(document_source_id) REFERENCES document_sources(document_source_id)
);
CREATE INDEX idx_chunk_provenance_scope ON chunk_provenance(source_sha256, import_run_id);
CREATE INDEX idx_chunk_provenance_section ON chunk_provenance(section_id, content_type);
"""


class AuthorityBuildError(RuntimeError):
    """The candidate authority failed a build or integrity gate."""


def _sqlite_library_version_number() -> int:
    version = sqlite3.sqlite_version_info
    if (
        not isinstance(version, tuple)
        or len(version) != 3
        or any(type(part) is not int or part < 0 for part in version)
    ):
        raise AuthorityBuildError("SQLite library version is malformed")
    major, minor, patch = version
    value = major * 1_000_000 + minor * 1_000 + patch
    if value <= 0 or value > 0xFFFFFFFF:
        raise AuthorityBuildError("SQLite library version is out of range")
    return value


def _normalize_serialized_database_header(
    payload: bytes,
    *,
    data_transaction_committed: bool,
) -> bytes:
    if type(payload) is not bytes or len(payload) < _SQLITE_HEADER_SIZE:
        raise AuthorityBuildError("serialized SQLite database is malformed")
    if type(data_transaction_committed) is not bool:
        raise AuthorityBuildError("serialized SQLite transaction state is malformed")
    if payload[:16] != b"SQLite format 3\x00":
        raise AuthorityBuildError("serialized SQLite header is malformed")

    encoded_page_size = int.from_bytes(payload[16:18], "big")
    page_size = 65_536 if encoded_page_size == 1 else encoded_page_size
    page_count = int.from_bytes(
        payload[_SQLITE_PAGE_COUNT_OFFSET : _SQLITE_PAGE_COUNT_OFFSET + 4],
        "big",
    )
    if (
        page_size < 512
        or page_size > 65_536
        or page_size & (page_size - 1)
        or page_count <= 0
        or page_count * page_size != len(payload)
    ):
        raise AuthorityBuildError("serialized SQLite page geometry is malformed")

    change_counter = int.from_bytes(
        payload[_SQLITE_CHANGE_COUNTER_OFFSET : _SQLITE_CHANGE_COUNTER_OFFSET + 4],
        "big",
    )
    version_valid_for = int.from_bytes(
        payload[
            _SQLITE_VERSION_VALID_FOR_OFFSET : _SQLITE_VERSION_VALID_FOR_OFFSET + 4
        ],
        "big",
    )
    library_version = int.from_bytes(
        payload[_SQLITE_LIBRARY_VERSION_OFFSET : _SQLITE_LIBRARY_VERSION_OFFSET + 4],
        "big",
    )
    if change_counter != 0 or version_valid_for != 0 or library_version != 0:
        raise AuthorityBuildError("serialized SQLite header state is unexpected")

    schema_cookie = int.from_bytes(
        payload[_SQLITE_SCHEMA_COOKIE_OFFSET : _SQLITE_SCHEMA_COOKIE_OFFSET + 4],
        "big",
    )
    # The post-VACUUM schema cookie accounts for schema writes and VACUUM. A
    # fresh disk file also records user_version and the optional data commit.
    disk_change_counter = schema_cookie + 1 + int(data_transaction_committed)
    if schema_cookie <= 0 or disk_change_counter > 0xFFFFFFFF:
        raise AuthorityBuildError("serialized SQLite schema state is malformed")

    normalized = bytearray(payload)
    normalized[
        _SQLITE_CHANGE_COUNTER_OFFSET : _SQLITE_CHANGE_COUNTER_OFFSET + 4
    ] = disk_change_counter.to_bytes(4, "big")
    normalized[
        _SQLITE_VERSION_VALID_FOR_OFFSET : _SQLITE_VERSION_VALID_FOR_OFFSET + 4
    ] = disk_change_counter.to_bytes(4, "big")
    normalized[
        _SQLITE_LIBRARY_VERSION_OFFSET : _SQLITE_LIBRARY_VERSION_OFFSET + 4
    ] = _sqlite_library_version_number().to_bytes(4, "big")
    return bytes(normalized)


@dataclass(frozen=True)
class _BuilderSourceState:
    device: int
    inode: int
    mode: int
    link_count: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass
class _HeldBuilderSource:
    path: Path
    parent_descriptor: int
    descriptor: int
    parent_state: _BuilderSourceState
    file_state: _BuilderSourceState
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


def _builder_source_state(value: os.stat_result) -> _BuilderSourceState:
    return _BuilderSourceState(
        device=value.st_dev,
        inode=value.st_ino,
        mode=value.st_mode,
        link_count=value.st_nlink,
        size=value.st_size,
        mtime_ns=value.st_mtime_ns,
        ctime_ns=value.st_ctime_ns,
    )


def _normalize_builder_source_path(raw_path: str | Path, field: str) -> Path:
    path = Path(raw_path)
    for alias, target in {
        Path("/var"): Path("/private/var"),
        Path("/tmp"): Path("/private/tmp"),
        Path("/etc"): Path("/private/etc"),
    }.items():
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
        raise AuthorityBuildError(f"{field} path is not canonical")
    return path


def _read_held_builder_source(
    descriptor: int,
    expected: _BuilderSourceState,
    *,
    field: str,
    max_bytes: int,
) -> bytes:
    before = _builder_source_state(os.fstat(descriptor))
    if before != expected or before.size < 0 or before.size > max_bytes:
        raise AuthorityBuildError(f"{field} is not stably bounded")
    chunks: list[bytes] = []
    offset = 0
    while offset < before.size:
        block = os.pread(descriptor, min(1024 * 1024, before.size - offset), offset)
        if not block:
            raise AuthorityBuildError(f"{field} became shorter")
        chunks.append(block)
        offset += len(block)
    payload = b"".join(chunks)
    if _builder_source_state(os.fstat(descriptor)) != expected or len(payload) != expected.size:
        raise AuthorityBuildError(f"{field} changed while reading")
    return payload


def _open_held_builder_source(
    raw_path: str | Path,
    field: str,
    *,
    max_bytes: int,
) -> _HeldBuilderSource:
    path = _normalize_builder_source_path(raw_path, field)
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
        parent_state = _builder_source_state(os.fstat(parent_descriptor))
        inspected = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        inspected_state = _builder_source_state(inspected)
        if (
            not stat.S_ISDIR(parent_state.mode)
            or not stat.S_ISREG(inspected_state.mode)
            or inspected_state.link_count != 1
            or inspected_state.inode == 0
        ):
            raise AuthorityBuildError(f"{field} must be one regular file")
        descriptor = os.open(path.name, file_flags, dir_fd=parent_descriptor)
        opened_state = _builder_source_state(os.fstat(descriptor))
        if opened_state != inspected_state:
            raise AuthorityBuildError(f"{field} changed while opening")
        payload = _read_held_builder_source(
            descriptor,
            opened_state,
            field=field,
            max_bytes=max_bytes,
        )
        if (
            _builder_source_state(
                os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
            )
            != opened_state
            or _builder_source_state(os.fstat(parent_descriptor)) != parent_state
        ):
            raise AuthorityBuildError(f"{field} changed while holding")
        return _HeldBuilderSource(
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


def _revalidate_held_builder_source(
    held: _HeldBuilderSource,
    *,
    field: str,
) -> None:
    if held.closed:
        raise AuthorityBuildError(f"{field} held descriptor is closed")
    try:
        parent_state = _builder_source_state(os.fstat(held.parent_descriptor))
        descriptor_state = _builder_source_state(os.fstat(held.descriptor))
        entry_state = _builder_source_state(
            os.stat(
                held.path.name,
                dir_fd=held.parent_descriptor,
                follow_symlinks=False,
            )
        )
    except OSError as exc:
        raise AuthorityBuildError(f"{field} binding changed") from exc
    if (
        parent_state != held.parent_state
        or descriptor_state != held.file_state
        or entry_state != held.file_state
        or _normalize_builder_source_path(held.path, field) != held.path
    ):
        raise AuthorityBuildError(f"{field} binding changed")
    payload = _read_held_builder_source(
        held.descriptor,
        held.file_state,
        field=field,
        max_bytes=4 * 1024 * 1024,
    )
    if payload != held.payload:
        raise AuthorityBuildError(f"{field} bytes changed")


def _require_formal_bootstrap_context() -> None:
    evidence = sys.modules.get("deploy.cloud_v2.offline_evidence")
    require = getattr(evidence, "_require_formal_bootstrap_context", None)
    if not callable(require):
        raise AuthorityBuildError(
            "formal authority builder CLI bootstrap context is required"
        )
    try:
        require()
    except Exception as exc:
        raise AuthorityBuildError(
            "formal authority builder CLI bootstrap context is required"
        ) from exc


def _require_isolated_python() -> None:
    if not (
        sys.flags.isolated == 1
        and sys.flags.no_site == 1
        and sys.flags.dont_write_bytecode == 1
    ):
        raise AuthorityBuildError(
            "formal authority builder requires Python -I -S -B"
        )


_FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)
_FORMAL_AUTHORITY_BUILDER_ACTION_COUNT = 14
_ACTION_SCOPE_READ_SOURCE_BYTES = 8
_ACTION_SCOPE_REVALIDATE = 9
_ACTION_SCOPE_IDENTITY = 10
_ACTION_SCOPE_CLOSE = 11
_ACTION_EXTRACT_SOURCE = 12
_ACTION_VALIDATE_OCR_RUNTIME = 13
_EXECUTED_AUTHORITY_BUILDER_SOURCE = _open_held_builder_source(
    Path(__file__),
    "authority builder source",
    max_bytes=4 * 1024 * 1024,
)
_FORMAL_AUTHORITY_BUILDER_SOURCE_SHA256: str | None = None
_FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_AUTHORITY_BUILDER_ACTION_CLOSURE: tuple[object, ...] | None = None


def _authority_builder_source_state_identity() -> dict[str, int]:
    state = _EXECUTED_AUTHORITY_BUILDER_SOURCE.file_state
    return {
        "device": state.device,
        "inode": state.inode,
        "mode": state.mode,
        "nlink": state.link_count,
        "size": state.size,
        "mtime_ns": state.mtime_ns,
        "ctime_ns": state.ctime_ns,
    }


def _current_authority_builder_action_closure() -> tuple[object, ...]:
    return (
        main,
        _main_impl,
        build_authority,
        _build_authority_impl,
        _parser,
        ApprovedSourceScope.__dict__["load"].__func__,
        write_json,
        _write_json_impl,
        ApprovedSourceScope.__dict__["read_source_bytes"],
        ApprovedSourceScope.__dict__["revalidate"],
        ApprovedSourceScope.__dict__["identity"],
        ApprovedSourceScope.__dict__["close"],
        extract_source,
        validate_ocr_runtime,
    )


def _install_formal_authority_builder_bootstrap_context(
    binding: Mapping[str, Any],
) -> None:
    global _FORMAL_AUTHORITY_BUILDER_ACTION_CLOSURE
    global _FORMAL_AUTHORITY_BUILDER_SOURCE_SHA256
    global _FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_IDENTITY

    _require_formal_bootstrap_context()
    _require_isolated_python()
    required = {*_FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_FIELDS, "sha256"}
    if (
        not isinstance(binding, Mapping)
        or set(binding) != required
        or not isinstance(binding.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", str(binding["sha256"]))
        or any(
            type(binding.get(field)) is not int or int(binding[field]) < 0
            for field in _FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_FIELDS
        )
        or binding["inode"] == 0
        or binding["nlink"] != 1
        or not stat.S_ISREG(binding["mode"])
    ):
        raise AuthorityBuildError(
            "formal authority builder CLI source binding is malformed"
        )
    expected_state = {
        field: int(binding[field])
        for field in _FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_FIELDS
    }
    _revalidate_held_builder_source(
        _EXECUTED_AUTHORITY_BUILDER_SOURCE,
        field="authority builder source",
    )
    if (
        hashlib.sha256(_EXECUTED_AUTHORITY_BUILDER_SOURCE.payload).hexdigest()
        != binding["sha256"]
        or _authority_builder_source_state_identity() != expected_state
    ):
        raise AuthorityBuildError(
            "formal authority builder CLI source differs from held bootstrap bytes"
        )
    _FORMAL_AUTHORITY_BUILDER_SOURCE_SHA256 = str(binding["sha256"])
    _FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_IDENTITY = expected_state
    actions = _current_authority_builder_action_closure()
    if (
        len(actions) != _FORMAL_AUTHORITY_BUILDER_ACTION_COUNT
        or any(not callable(action) for action in actions)
    ):
        raise AuthorityBuildError(
            "formal authority builder CLI action closure is malformed"
        )
    _FORMAL_AUTHORITY_BUILDER_ACTION_CLOSURE = actions


def _require_formal_authority_builder_bootstrap_context() -> tuple[object, ...]:
    source_sha256 = _FORMAL_AUTHORITY_BUILDER_SOURCE_SHA256
    source_state = _FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_IDENTITY
    actions = _FORMAL_AUTHORITY_BUILDER_ACTION_CLOSURE
    if (
        not isinstance(source_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_FIELDS)
        or any(
            type(source_state.get(field)) is not int or int(source_state[field]) < 0
            for field in _FORMAL_AUTHORITY_BUILDER_SOURCE_STATE_FIELDS
        )
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
        or not isinstance(actions, tuple)
        or len(actions) != _FORMAL_AUTHORITY_BUILDER_ACTION_COUNT
        or any(not callable(action) for action in actions)
    ):
        raise AuthorityBuildError(
            "formal authority builder CLI bootstrap context is required"
        )
    _require_formal_bootstrap_context()
    _require_isolated_python()
    _revalidate_held_builder_source(
        _EXECUTED_AUTHORITY_BUILDER_SOURCE,
        field="authority builder source",
    )
    if (
        hashlib.sha256(_EXECUTED_AUTHORITY_BUILDER_SOURCE.payload).hexdigest()
        != source_sha256
        or _authority_builder_source_state_identity() != dict(source_state)
        or any(
            current is not expected
            for current, expected in zip(
                _current_authority_builder_action_closure(),
                actions,
                strict=True,
            )
        )
    ):
        raise AuthorityBuildError(
            "formal authority builder CLI source or action closure changed"
        )
    return actions


_DATABASE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _write_json_impl(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value))


def write_json(path: Path, value: object) -> None:
    actions = _require_formal_authority_builder_bootstrap_context()
    actions[7](path, value)


_SYSTEM_PATH_ALIAS_TARGETS = {
    Path("/var"): Path("/private/var"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/etc"): Path("/private/etc"),
}


@dataclass
class _HeldCandidateRoot:
    path: Path
    parent_descriptor: int
    descriptor: int
    parent_identity: tuple[int, int]
    root_identity: tuple[int, int]
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


@dataclass
class _HeldCandidateOutput:
    staging_name: str
    final_name: str
    descriptor: int
    initial_state: _BuilderSourceState
    current_name: str
    sealed_state: _BuilderSourceState | None = None
    sealed_size: int | None = None
    sealed_sha256: str | None = None
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            os.close(self.descriptor)
        except OSError:
            pass


def _inode_identity(value: os.stat_result | _BuilderSourceState) -> tuple[int, int]:
    if isinstance(value, _BuilderSourceState):
        return value.device, value.inode
    return value.st_dev, value.st_ino


def _candidate_path(raw_path: str | Path) -> Path:
    try:
        path = Path(os.path.abspath(Path(raw_path)))
    except (OSError, TypeError, ValueError) as exc:
        raise AuthorityBuildError("candidate root path is invalid") from exc
    for alias, target in _SYSTEM_PATH_ALIAS_TARGETS.items():
        try:
            relative = path.relative_to(alias)
        except ValueError:
            continue
        path = target / relative
        break
    if (
        not path.is_absolute()
        or path == Path("/")
        or not any(part in {"candidate", "candidates"} for part in path.parts)
    ):
        raise AuthorityBuildError(
            "builder output must be inside an explicit candidate root"
        )
    return path


def _open_directory_path(path: Path, field: str, *, create: bool) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        current = os.open("/", flags)
    except OSError as exc:
        raise AuthorityBuildError(f"{field} cannot be opened safely") from exc
    try:
        for component in path.parts[1:]:
            try:
                inspected = os.stat(
                    component,
                    dir_fd=current,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                if not create:
                    raise AuthorityBuildError(f"{field} changed or disappeared")
                try:
                    os.mkdir(component, 0o700, dir_fd=current)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise AuthorityBuildError(
                        f"{field} cannot be created safely"
                    ) from exc
                try:
                    inspected = os.stat(
                        component,
                        dir_fd=current,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise AuthorityBuildError(
                        f"{field} cannot be inspected safely"
                    ) from exc
            if stat.S_ISLNK(inspected.st_mode) or not stat.S_ISDIR(
                inspected.st_mode
            ):
                raise AuthorityBuildError(
                    f"{field} must contain only real directories"
                )
            child: int | None = None
            try:
                child = os.open(component, flags, dir_fd=current)
                opened = os.fstat(child)
            except OSError as exc:
                if child is not None:
                    try:
                        os.close(child)
                    except OSError:
                        pass
                raise AuthorityBuildError(
                    f"{field} cannot be opened safely"
                ) from exc
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _inode_identity(opened) != _inode_identity(inspected)
            ):
                os.close(child)
                raise AuthorityBuildError(f"{field} changed while opening")
            previous = current
            current = child
            os.close(previous)
        return current
    except BaseException:
        try:
            os.close(current)
        except OSError:
            pass
        raise


def _candidate_root(raw_path: str | Path) -> _HeldCandidateRoot:
    path = _candidate_path(raw_path)
    parent_descriptor = _open_directory_path(
        path.parent,
        "candidate root parent",
        create=True,
    )
    descriptor: int | None = None
    held: _HeldCandidateRoot | None = None
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        try:
            inspected = os.stat(
                path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            try:
                os.mkdir(path.name, 0o700, dir_fd=parent_descriptor)
            except FileExistsError:
                pass
            except OSError as exc:
                raise AuthorityBuildError(
                    "candidate root cannot be created safely"
                ) from exc
            try:
                inspected = os.stat(
                    path.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise AuthorityBuildError(
                    "candidate root cannot be inspected safely"
                ) from exc
        if stat.S_ISLNK(inspected.st_mode) or not stat.S_ISDIR(
            inspected.st_mode
        ):
            raise AuthorityBuildError("candidate root must be a real directory")
        try:
            descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
            opened_before_chmod = os.fstat(descriptor)
            os.fchmod(descriptor, 0o700)
            opened = os.fstat(descriptor)
            entry = os.stat(
                path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise AuthorityBuildError(
                "candidate root cannot be opened safely"
            ) from exc
        if (
            not stat.S_ISDIR(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o700
            or _inode_identity(inspected) != _inode_identity(opened_before_chmod)
            or _inode_identity(opened) != _inode_identity(opened_before_chmod)
            or _inode_identity(entry) != _inode_identity(opened)
        ):
            raise AuthorityBuildError("candidate root changed while opening")
        held = _HeldCandidateRoot(
            path=path,
            parent_descriptor=parent_descriptor,
            descriptor=descriptor,
            parent_identity=_inode_identity(os.fstat(parent_descriptor)),
            root_identity=_inode_identity(opened),
        )
        descriptor = None
        _revalidate_candidate_root(held)
        return held
    except BaseException:
        if held is not None:
            held.close()
        else:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            try:
                os.close(parent_descriptor)
            except OSError:
                pass
        raise


def _revalidate_candidate_root(root: _HeldCandidateRoot) -> None:
    if root.closed:
        raise AuthorityBuildError("candidate root descriptor is closed")
    reopened: int | None = None
    reopened_state: os.stat_result | None = None
    try:
        held_parent = os.fstat(root.parent_descriptor)
        held_root = os.fstat(root.descriptor)
        entry = os.stat(
            root.path.name,
            dir_fd=root.parent_descriptor,
            follow_symlinks=False,
        )
        reopened = _open_directory_path(
            root.path,
            "candidate root",
            create=False,
        )
        reopened_state = os.fstat(reopened)
    except AuthorityBuildError:
        raise
    except OSError as exc:
        raise AuthorityBuildError("candidate root binding changed") from exc
    finally:
        if reopened is not None:
            try:
                os.close(reopened)
            except OSError:
                pass
    if (
        reopened_state is None
        or not stat.S_ISDIR(held_root.st_mode)
        or stat.S_IMODE(held_root.st_mode) != 0o700
        or root.parent_identity != _inode_identity(held_parent)
        or root.root_identity != _inode_identity(held_root)
        or root.root_identity != _inode_identity(entry)
        or root.root_identity != _inode_identity(reopened_state)
    ):
        raise AuthorityBuildError("candidate root binding changed")


def _ensure_candidate_outputs_absent(
    root: _HeldCandidateRoot,
    names: Sequence[str],
) -> None:
    _revalidate_candidate_root(root)
    try:
        entries = os.listdir(root.descriptor)
    except OSError as exc:
        raise AuthorityBuildError(
            "candidate authority output cannot be inspected safely"
        ) from exc
    if any(name.startswith(".") and ".cleanup-" in name for name in entries):
        raise AuthorityBuildError("candidate root contains cleanup residue")
    for name in names:
        try:
            os.stat(name, dir_fd=root.descriptor, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise AuthorityBuildError(
                "candidate authority output cannot be inspected safely"
            ) from exc
        raise AuthorityBuildError("candidate authority output already exists")


def _discard_candidate_output_if_owned(
    root: _HeldCandidateRoot,
    output: _HeldCandidateOutput,
) -> None:
    _discard_candidate_entry_if_owned(
        root,
        descriptor=output.descriptor,
        current_name=output.current_name,
    )


def _discard_candidate_entry_if_owned(
    root: _HeldCandidateRoot,
    *,
    descriptor: int,
    current_name: str,
) -> None:
    try:
        opened = os.fstat(descriptor)
        entry = os.stat(
            current_name,
            dir_fd=root.descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return
    if _inode_identity(entry) != _inode_identity(opened):
        return

    quarantine_name: str | None = None
    for index in range(32):
        candidate = f".{current_name}.cleanup-{index:02d}"
        try:
            _atomic_noreplace_rename(
                current_name,
                candidate,
                directory_descriptor=root.descriptor,
            )
        except FileExistsError:
            continue
        except (AuthorityBuildError, OSError):
            return
        quarantine_name = candidate
        try:
            os.fsync(root.descriptor)
        except OSError:
            return
        break
    if quarantine_name is None:
        return

    quarantine_descriptor: int | None = None
    try:
        quarantine_descriptor = os.open(
            quarantine_name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root.descriptor,
        )
        quarantined = os.fstat(quarantine_descriptor)
        held = os.fstat(descriptor)
        if (
            not stat.S_ISREG(quarantined.st_mode)
            or quarantined.st_ino == 0
            or _inode_identity(quarantined) != _inode_identity(held)
        ):
            return
    except OSError:
        return
    finally:
        if quarantine_descriptor is not None:
            try:
                os.close(quarantine_descriptor)
            except OSError:
                pass


def _discard_reserved_candidate_entry_if_owned(
    root: _HeldCandidateRoot,
    *,
    descriptor: int,
    staging_name: str,
) -> None:
    _discard_candidate_entry_if_owned(
        root,
        descriptor=descriptor,
        current_name=staging_name,
    )
    try:
        os.fsync(root.descriptor)
    except OSError:
        pass


def _reserve_candidate_output(
    root: _HeldCandidateRoot,
    *,
    staging_name: str,
    final_name: str,
    field: str,
) -> _HeldCandidateOutput:
    for name in (staging_name, final_name):
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise AuthorityBuildError(f"{field} name is invalid")
    _revalidate_candidate_root(root)
    try:
        os.stat(
            final_name,
            dir_fd=root.descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise AuthorityBuildError(
            f"{field} publication target cannot be inspected"
        ) from exc
    else:
        raise AuthorityBuildError(f"{field} publication target already exists")

    descriptor: int | None = None
    output: _HeldCandidateOutput | None = None
    try:
        descriptor = os.open(
            staging_name,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=root.descriptor,
        )
        os.fchmod(descriptor, 0o600)
        opened = os.fstat(descriptor)
        entry = os.stat(
            staging_name,
            dir_fd=root.descriptor,
            follow_symlinks=False,
        )
        opened_state = _builder_source_state(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_ino == 0
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened_state != _builder_source_state(entry)
        ):
            raise AuthorityBuildError(
                f"{field} reservation is not one private regular file"
            )
        output = _HeldCandidateOutput(
            staging_name=staging_name,
            final_name=final_name,
            descriptor=descriptor,
            initial_state=opened_state,
            current_name=staging_name,
        )
        descriptor = None
        return output
    except FileExistsError as exc:
        raise AuthorityBuildError(
            f"{field} could not be created exclusively"
        ) from exc
    except AuthorityBuildError:
        raise
    except OSError as exc:
        raise AuthorityBuildError(
            f"{field} could not be created exclusively"
        ) from exc
    finally:
        if descriptor is not None:
            _discard_reserved_candidate_entry_if_owned(
                root,
                descriptor=descriptor,
                staging_name=staging_name,
            )
            try:
                os.close(descriptor)
            except OSError:
                pass


def _candidate_output_state(
    root: _HeldCandidateRoot,
    output: _HeldCandidateOutput,
    *,
    field: str,
) -> _BuilderSourceState:
    _revalidate_candidate_root(root)
    try:
        opened = os.fstat(output.descriptor)
        entry = os.stat(
            output.current_name,
            dir_fd=root.descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise AuthorityBuildError(f"{field} binding changed") from exc
    opened_state = _builder_source_state(opened)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or opened.st_ino == 0
        or stat.S_IMODE(opened.st_mode) != 0o600
        or opened_state != _builder_source_state(entry)
    ):
        raise AuthorityBuildError(f"{field} binding changed")
    return opened_state


def _write_and_seal_candidate_output(
    root: _HeldCandidateRoot,
    output: _HeldCandidateOutput,
    payload: bytes,
    *,
    field: str,
) -> str:
    if (
        not isinstance(payload, bytes)
        or output.sealed_state is not None
        or output.sealed_size is not None
        or output.sealed_sha256 is not None
    ):
        raise AuthorityBuildError(f"{field} sealing state is invalid")
    before = _candidate_output_state(root, output, field=field)
    if before != output.initial_state or before.size != 0:
        raise AuthorityBuildError(f"{field} reservation changed before writing")
    try:
        offset = 0
        while offset < len(payload):
            written = os.pwrite(output.descriptor, payload[offset:], offset)
            if written <= 0:
                raise AuthorityBuildError(f"{field} could not be written completely")
            offset += written
        os.fsync(output.descriptor)
        os.fchmod(output.descriptor, 0o600)
        os.fsync(output.descriptor)
    except AuthorityBuildError:
        raise
    except OSError as exc:
        raise AuthorityBuildError(f"{field} could not be written safely") from exc
    after = _candidate_output_state(root, output, field=field)
    if (
        _inode_identity(after) != _inode_identity(before)
        or after.size != len(payload)
    ):
        raise AuthorityBuildError(f"{field} changed while writing")
    written_payload = _read_held_builder_source(
        output.descriptor,
        after,
        field=field,
        max_bytes=len(payload),
    )
    if written_payload != payload:
        raise AuthorityBuildError(f"{field} bytes differ after writing")
    output.sealed_state = after
    output.sealed_size = len(payload)
    output.sealed_sha256 = hashlib.sha256(written_payload).hexdigest()
    _revalidate_candidate_output(root, output, field=field)
    return output.sealed_sha256


def _revalidate_candidate_output(
    root: _HeldCandidateRoot,
    output: _HeldCandidateOutput,
    *,
    field: str,
) -> None:
    if (
        output.closed
        or output.sealed_state is None
        or output.sealed_size is None
        or output.sealed_sha256 is None
    ):
        raise AuthorityBuildError(f"{field} is not sealed")
    state = _candidate_output_state(root, output, field=field)
    if state != output.sealed_state or state.size != output.sealed_size:
        raise AuthorityBuildError(f"{field} state changed")
    payload = _read_held_builder_source(
        output.descriptor,
        state,
        field=field,
        max_bytes=output.sealed_size,
    )
    if hashlib.sha256(payload).hexdigest() != output.sealed_sha256:
        raise AuthorityBuildError(f"{field} bytes changed")


def _atomic_noreplace_rename(
    source_name: str,
    destination_name: str,
    *,
    directory_descriptor: int,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        try:
            rename = libc.renameatx_np
        except AttributeError as exc:
            raise AuthorityBuildError(
                "atomic no-replace publication is unavailable"
            ) from exc
        flag = 0x00000004
    elif sys.platform.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as exc:
            raise AuthorityBuildError(
                "atomic no-replace publication is unavailable"
            ) from exc
        flag = 0x00000001
    else:
        raise AuthorityBuildError(
            "atomic no-replace publication is unsupported"
        )
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    result = rename(
        directory_descriptor,
        source,
        directory_descriptor,
        destination,
        flag,
    )
    if result == 0:
        return
    error_code = ctypes.get_errno()
    if error_code == errno.EEXIST:
        raise FileExistsError(
            error_code,
            os.strerror(error_code),
            destination_name,
        )
    raise OSError(error_code, os.strerror(error_code), destination_name)


def _publish_candidate_output(
    root: _HeldCandidateRoot,
    output: _HeldCandidateOutput,
    *,
    field: str,
) -> None:
    _revalidate_candidate_output(root, output, field=field)
    try:
        _atomic_noreplace_rename(
            output.staging_name,
            output.final_name,
            directory_descriptor=root.descriptor,
        )
    except FileExistsError as exc:
        raise AuthorityBuildError(
            f"{field} publication target already exists"
        ) from exc
    except AuthorityBuildError:
        raise
    except OSError as exc:
        raise AuthorityBuildError(f"{field} could not be published safely") from exc
    output.current_name = output.final_name
    published_state = _candidate_output_state(root, output, field=field)
    if (
        output.sealed_state is None
        or _inode_identity(published_state)
        != _inode_identity(output.sealed_state)
        or published_state.size != output.sealed_size
    ):
        raise AuthorityBuildError(f"{field} changed during publication")
    output.sealed_state = published_state
    _revalidate_candidate_output(root, output, field=field)
    try:
        os.fsync(root.descriptor)
    except OSError as exc:
        raise AuthorityBuildError(
            f"{field} directory durability could not be established"
        ) from exc
    _revalidate_candidate_output(root, output, field=field)


def _safe_database_name(value: object) -> str:
    if not isinstance(value, str) or not _DATABASE_NAME.fullmatch(value):
        raise AuthorityBuildError("database_name must be one safe file name")
    if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise AuthorityBuildError("database_name must be one safe file name")
    return value


def _stable_id(prefix: str, *parts: str, length: int = 40) -> str:
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest[:length]}"


def _content_type(relative_path: str) -> str:
    if relative_path.startswith("政策法规/"):
        return "regulation"
    if relative_path.startswith("理论题库/"):
        return "question_bank"
    if relative_path.startswith("地面站考题考试条件/"):
        return "exam_condition"
    return "textbook"


def _build_authority_impl(
    scope: ApprovedSourceScope,
    candidate_root: str | Path,
    *,
    database_name: str = "rag_chunks.db",
    ocr_tessdata_dir: str | Path | None = None,
    ocr_workers: int = 4,
) -> dict[str, object]:
    if _FORMAL_AUTHORITY_BUILDER_ACTION_CLOSURE is None:
        scope_read_source_bytes_action = (
            lambda current_scope, record: current_scope.read_source_bytes(record)
        )
        scope_revalidate_action = lambda current_scope: current_scope.revalidate()
        scope_identity_action = lambda current_scope: current_scope.identity()
        extract_source_action = extract_source
        validate_ocr_runtime_action = validate_ocr_runtime
    else:
        formal_actions = _require_formal_authority_builder_bootstrap_context()
        scope_read_source_bytes_action = formal_actions[
            _ACTION_SCOPE_READ_SOURCE_BYTES
        ]
        scope_revalidate_action = formal_actions[_ACTION_SCOPE_REVALIDATE]
        scope_identity_action = formal_actions[_ACTION_SCOPE_IDENTITY]
        extract_source_action = formal_actions[_ACTION_EXTRACT_SOURCE]
        validate_ocr_runtime_action = formal_actions[
            _ACTION_VALIDATE_OCR_RUNTIME
        ]
    if type(ocr_workers) is not int or not 1 <= ocr_workers <= 4:
        raise AuthorityBuildError("ocr_workers must be an integer from 1 through 4")
    database_name = _safe_database_name(database_name)
    root = _candidate_root(candidate_root)
    database_output: _HeldCandidateOutput | None = None
    manifest_output: _HeldCandidateOutput | None = None
    connection: sqlite3.Connection | None = None
    try:
        _ensure_candidate_outputs_absent(
            root,
            (
                database_name,
                database_name + ".building",
                "authority-manifest.json",
                "authority-manifest.json.building",
            ),
        )
        scope_revalidate_action(scope)
        _revalidate_candidate_root(root)

        import_run_id = (
            f"cloud-v2:{CANDIDATE_ID}:{scope.source_manifest_sha256[:16]}"
        )
        recorded_at = scope.approval_recorded_at
        counts = {"documents": 0, "chunks": 0, "provenance": 0}
        extracted_records: list[dict[str, object]] = []
        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA page_size=4096")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(AUTHORITY_SCHEMA_SQL)
        connection.execute("PRAGMA user_version=1")
        for record in scope.records:
            source_payload = scope_read_source_bytes_action(scope, record)
            extracted = extract_source_action(
                source_payload,
                record.relative_path,
                ocr_tessdata_dir=ocr_tessdata_dir,
                ocr_workers=ocr_workers,
            )
            if not extracted.units:
                raise AuthorityBuildError(f"source produced zero chunks: {record.relative_path}")
            doc_name = record.relative_path
            doc_uri = "kb://knowledge_base/" + quote(record.relative_path, safe="/")
            document_source_id = _stable_id("docsrc", record.relative_path, record.source_sha256)
            metadata = {
                "byte_disposition": record.byte_disposition,
                "chunking_policy": CHUNKING_POLICY_VERSION,
                "source_relative_path_sha256": hashlib.sha256(
                    record.relative_path.encode("utf-8")
                ).hexdigest(),
            }
            connection.execute(
                """INSERT INTO document_sources (
                       document_source_id, doc_name, source_path, source_sha256,
                       source_page_count, authority, extractor_version, import_run_id,
                       metadata_json, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    document_source_id,
                    doc_name,
                    doc_uri,
                    record.source_sha256,
                    extracted.page_count,
                    "rag_chunks.db",
                    extracted.extractor,
                    import_run_id,
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    recorded_at,
                    recorded_at,
                ),
            )
            connection.execute(
                "INSERT INTO documents (doc_name, doc_path, chunk_count, updated_at) VALUES (?, ?, ?, ?)",
                (doc_name, doc_uri, len(extracted.units), recorded_at),
            )
            for index, unit in enumerate(extracted.units):
                chunk_id = _stable_id(
                    "chunk",
                    record.source_sha256,
                    str(index),
                    unit.text,
                )
                connection.execute(
                    "INSERT INTO chunks (chunk_id, text, doc_name, chunk_index, created_at) VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, unit.text, doc_name, index, recorded_at),
                )
                evidence = {
                    "extractor": extracted.extractor,
                    "source_text_sha256": extracted.text_sha256,
                    "unit_ordinal": unit.ordinal,
                }
                connection.execute(
                    """INSERT INTO chunk_provenance (
                           chunk_id, document_source_id, source_sha256, import_run_id,
                           pdf_page_start, pdf_page_end, section_title, content_type,
                           confidence, review_status, evidence_json, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk_id,
                        document_source_id,
                        record.source_sha256,
                        import_run_id,
                        unit.page_start,
                        unit.page_end,
                        unit.section_title,
                        _content_type(record.relative_path),
                        1.0,
                        "approved-source-extracted",
                        json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        recorded_at,
                    ),
                )
            counts["documents"] += 1
            counts["chunks"] += len(extracted.units)
            counts["provenance"] += len(extracted.units)
            extracted_records.append(
                {
                    "relative_path": record.relative_path,
                    "source_sha256": record.source_sha256,
                    "extracted_text_sha256": extracted.text_sha256,
                    "chunk_count": len(extracted.units),
                    "page_count": extracted.page_count,
                }
            )
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_keys:
            raise AuthorityBuildError("SQLite integrity or foreign-key gate failed")
        database_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("document_sources", "documents", "chunks", "chunk_provenance")
        }
        if database_counts != {
            "document_sources": counts["documents"],
            "documents": counts["documents"],
            "chunks": counts["chunks"],
            "chunk_provenance": counts["provenance"],
        }:
            raise AuthorityBuildError("SQLite row-count gate failed")
        connection.execute("VACUUM")
        serializer = getattr(connection, "serialize", None)
        if not callable(serializer):
            raise AuthorityBuildError(
                "SQLite runtime does not support sealed serialization"
            )
        database_payload = _normalize_serialized_database_header(
            serializer(),
            data_transaction_committed=counts["documents"] > 0,
        )
        connection.close()
        connection = None

        verification = sqlite3.connect(":memory:")
        try:
            deserializer = getattr(verification, "deserialize", None)
            if not callable(deserializer):
                raise AuthorityBuildError(
                    "SQLite runtime does not support sealed deserialization"
                )
            deserializer(database_payload)
            if (
                verification.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or verification.execute("PRAGMA foreign_key_check").fetchall()
                or verification.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                raise AuthorityBuildError(
                    "serialized SQLite integrity gate failed"
                )
        finally:
            verification.close()

        database_output = _reserve_candidate_output(
            root,
            staging_name=database_name + ".building",
            final_name=database_name,
            field="candidate authority database",
        )
        database_sha256 = _write_and_seal_candidate_output(
            root,
            database_output,
            database_payload,
            field="candidate authority database",
        )
        scope_revalidate_action(scope)
        _revalidate_candidate_output(
            root,
            database_output,
            field="candidate authority database",
        )
        _publish_candidate_output(
            root,
            database_output,
            field="candidate authority database",
        )
        scope_revalidate_action(scope)
        _revalidate_candidate_output(
            root,
            database_output,
            field="candidate authority database",
        )
    except BaseException:
        try:
            if connection is not None:
                connection.close()
        except BaseException:
            pass
        if database_output is not None:
            _discard_candidate_output_if_owned(root, database_output)
            database_output.close()
        root.close()
        raise

    try:
        release_id = f"rag-authority:{CANDIDATE_ID}:{database_sha256[:16]}"
        ocr_identity = (
            validate_ocr_runtime_action(ocr_tessdata_dir)
            if ocr_tessdata_dir
            else None
        )
        manifest: dict[str, object] = {
            "schema_version": AUTHORITY_SCHEMA_VERSION,
            "release_id": release_id,
            "status": "candidate",
            "authority": {"owner": "rag_chunks.db", "join_key": "chunk_id"},
            "source_scope": scope_identity_action(scope),
            "database": {
                "path": database_name,
                "sha256": database_sha256,
                "mode": "0600",
                "sqlite_user_version": 1,
                "integrity_check": "ok",
                "foreign_key_violation_count": 0,
            },
            "build": {
                "extractor_version": EXTRACTOR_VERSION,
                "chunking_policy": CHUNKING_POLICY_VERSION,
                "import_run_id": import_run_id,
                "network_calls": 0,
                "old_authority_reused": False,
                "ocr_runtime": ocr_identity,
            },
            "counts": counts,
            "sources": extracted_records,
        }
        manifest_payload = canonical_json_bytes(manifest)
        manifest_output = _reserve_candidate_output(
            root,
            staging_name="authority-manifest.json.building",
            final_name="authority-manifest.json",
            field="candidate authority manifest",
        )
        manifest_sha256 = _write_and_seal_candidate_output(
            root,
            manifest_output,
            manifest_payload,
            field="candidate authority manifest",
        )
        scope_revalidate_action(scope)
        _revalidate_candidate_output(
            root,
            database_output,
            field="candidate authority database",
        )
        _revalidate_candidate_output(
            root,
            manifest_output,
            field="candidate authority manifest",
        )
        _publish_candidate_output(
            root,
            manifest_output,
            field="candidate authority manifest",
        )
        scope_revalidate_action(scope)
        _revalidate_candidate_output(
            root,
            database_output,
            field="candidate authority database",
        )
        _revalidate_candidate_output(
            root,
            manifest_output,
            field="candidate authority manifest",
        )
        _revalidate_candidate_root(root)
        manifest["manifest_sha256"] = manifest_sha256
        manifest_output.close()
        database_output.close()
        root.close()
        return manifest
    except BaseException:
        if manifest_output is not None:
            _discard_candidate_output_if_owned(root, manifest_output)
            manifest_output.close()
        _discard_candidate_output_if_owned(root, database_output)
        database_output.close()
        root.close()
        raise


def build_authority(
    scope: ApprovedSourceScope,
    candidate_root: str | Path,
    *,
    database_name: str = "rag_chunks.db",
    ocr_tessdata_dir: str | Path | None = None,
    ocr_workers: int = 4,
) -> dict[str, object]:
    actions = _require_formal_authority_builder_bootstrap_context()
    return actions[3](
        scope,
        candidate_root,
        database_name=database_name,
        ocr_tessdata_dir=ocr_tessdata_dir,
        ocr_workers=ocr_workers,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--governance-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--ocr-tessdata-dir")
    parser.add_argument("--ocr-workers", type=int, default=4)
    return parser


def _main_impl(
    argv: Sequence[str] | None = None,
    *,
    _action_closure: tuple[object, ...] | None = None,
) -> int:
    actions = (
        (
            _parser,
            ApprovedSourceScope.__dict__["load"].__func__,
            _build_authority_impl,
        )
        if _action_closure is None
        else _action_closure
    )
    if (
        not isinstance(actions, tuple)
        or len(actions) != 3
        or any(not callable(action) for action in actions)
    ):
        raise AuthorityBuildError("authority builder CLI action closure is malformed")
    parser_action, scope_load_action, build_action = actions
    if _FORMAL_AUTHORITY_BUILDER_ACTION_CLOSURE is None:
        scope_revalidate_action = lambda current_scope: current_scope.revalidate()
        scope_close_action = lambda current_scope: current_scope.close()
    else:
        formal_actions = _require_formal_authority_builder_bootstrap_context()
        expected_cli_actions = (
            formal_actions[4],
            formal_actions[5],
            formal_actions[3],
        )
        if any(
            current is not expected
            for current, expected in zip(
                actions,
                expected_cli_actions,
                strict=True,
            )
        ):
            raise AuthorityBuildError(
                "authority builder CLI action closure changed"
            )
        scope_revalidate_action = formal_actions[_ACTION_SCOPE_REVALIDATE]
        scope_close_action = formal_actions[_ACTION_SCOPE_CLOSE]
    args = parser_action().parse_args(argv)
    scope = scope_load_action(
        ApprovedSourceScope,
        args.source_root,
        args.governance_root,
    )
    try:
        result = build_action(
            scope,
            args.candidate_root,
            ocr_tessdata_dir=args.ocr_tessdata_dir,
            ocr_workers=args.ocr_workers,
        )
    finally:
        try:
            scope_revalidate_action(scope)
        finally:
            scope_close_action(scope)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        actions = _require_formal_authority_builder_bootstrap_context()
    except AuthorityBuildError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return actions[1](
        argv,
        _action_closure=(actions[4], actions[5], actions[3]),
    )


if __name__ == "__main__":
    raise SystemExit(main())
