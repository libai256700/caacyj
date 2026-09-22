#!/usr/bin/env python3
"""Hash-chained query trace logging for /api/ask diagnostics."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import math
import os
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence


INTEGRITY_SCHEMA_VERSION = "kg-audit-chain-v1"
SHA256_ZERO = "0" * 64
MAX_TRACE_BYTES = 64 * 1024 * 1024
MAX_SAFE_SEQUENCE = 9_007_199_254_740_991
_INTEGRITY_REQUIRED_FIELDS = {
    "schema_version",
    "sequence",
    "previous_event_sha256",
    "event_sha256",
}
_INTEGRITY_LEGACY_FIELDS = {
    "legacy_prefix_sha256",
    "legacy_prefix_size_bytes",
}


class TraceIntegrityError(RuntimeError):
    """Raised when a trace cannot be safely verified or appended."""

    def __init__(self, message: str, code: str = "ETRACEINTEGRITY") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TraceChainState:
    records: tuple[dict[str, Any], ...]
    line_count: int
    chained_count: int
    legacy_count: int
    last_sequence: int
    last_raw_line: bytes | None
    legacy_prefix: bytes


@dataclass(frozen=True)
class SecurePathHandle:
    path: Path
    parent_fd: int
    leaf: str


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_constant(value: str) -> None:
    raise TraceIntegrityError(f"trace JSON contains non-finite number {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise TraceIntegrityError(f"trace JSON contains duplicate key {key!r}")
        value[key] = item
    return value


def _strict_json_loads(text: str, line_number: int | None = None) -> Any:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        _assert_finite_json(value)
        return value
    except TraceIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        label = f" line {line_number}" if line_number is not None else ""
        raise TraceIntegrityError(f"trace JSON{label} is invalid") from exc


def _assert_finite_json(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise TraceIntegrityError("trace JSON contains a non-finite number")
    if isinstance(value, list):
        for item in value:
            _assert_finite_json(item)
    elif isinstance(value, dict):
        for item in value.values():
            _assert_finite_json(item)


def canonical_trace_json(value: Any) -> str:
    """Return deterministic UTF-8 JSON while preserving the old default=str API."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise TraceIntegrityError("trace record is not canonical-JSON encodable") from exc


def _canonical_bytes(value: Any) -> bytes:
    try:
        return canonical_trace_json(value).encode("utf-8")
    except UnicodeError as exc:
        raise TraceIntegrityError("trace record contains invalid Unicode") from exc


def _canonical_line(value: Any) -> bytes:
    return _canonical_bytes(value) + b"\n"


def _split_jsonl(data: bytes) -> list[bytes]:
    if not isinstance(data, bytes):
        raise TraceIntegrityError("trace log must be bytes")
    if len(data) > MAX_TRACE_BYTES:
        raise TraceIntegrityError("trace log exceeds bounded verification size", "EFBIG")
    if data and not data.endswith(b"\n"):
        raise TraceIntegrityError("trace log has a partial line")
    lines = data.splitlines(keepends=True)
    if any(line == b"\n" for line in lines):
        raise TraceIntegrityError("trace log contains a blank line")
    return lines


def _parse_line(raw: bytes, line_number: int) -> dict[str, Any]:
    try:
        text = raw[:-1].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TraceIntegrityError(f"trace line {line_number} is not UTF-8") from exc
    value = _strict_json_loads(text, line_number)
    if not isinstance(value, dict):
        raise TraceIntegrityError(f"trace line {line_number} is not an object")
    return value


def _integrity_envelope(record: dict[str, Any]) -> dict[str, Any] | None:
    if "integrity" not in record:
        return None
    envelope = record["integrity"]
    if not isinstance(envelope, dict):
        raise TraceIntegrityError("trace integrity envelope is not an object")
    fields = set(envelope)
    allowed = _INTEGRITY_REQUIRED_FIELDS | _INTEGRITY_LEGACY_FIELDS
    if not _INTEGRITY_REQUIRED_FIELDS.issubset(fields) or not fields.issubset(allowed):
        raise TraceIntegrityError("trace integrity envelope has unexpected fields")
    legacy_fields = fields & _INTEGRITY_LEGACY_FIELDS
    if legacy_fields and legacy_fields != _INTEGRITY_LEGACY_FIELDS:
        raise TraceIntegrityError("trace legacy-prefix envelope is incomplete")
    return envelope


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def verify_trace_bytes(data: bytes, *, require_chain: bool = True) -> TraceChainState:
    """Strictly verify a complete JSONL byte stream and its hash chain."""

    lines = _split_jsonl(data)
    records: list[dict[str, Any]] = []
    legacy_lines: list[bytes] = []
    chain_started = False
    last_sequence = 0
    last_raw_line: bytes | None = None

    for index, raw in enumerate(lines, start=1):
        record = _parse_line(raw, index)
        envelope = _integrity_envelope(record)
        if envelope is None:
            if chain_started:
                raise TraceIntegrityError("legacy trace record appears after the chain started")
            legacy_lines.append(raw)
            records.append(record)
            last_raw_line = raw
            continue

        if envelope.get("schema_version") != INTEGRITY_SCHEMA_VERSION:
            raise TraceIntegrityError("trace integrity schema is unsupported")
        sequence = envelope.get("sequence")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not 1 <= sequence <= MAX_SAFE_SEQUENCE
        ):
            raise TraceIntegrityError("trace integrity sequence is invalid")
        previous_digest = envelope.get("previous_event_sha256")
        event_digest = envelope.get("event_sha256")
        if not _is_digest(previous_digest) or not _is_digest(event_digest):
            raise TraceIntegrityError("trace integrity digest is invalid")

        unsigned = dict(record)
        unsigned_integrity = dict(envelope)
        del unsigned_integrity["event_sha256"]
        unsigned["integrity"] = unsigned_integrity
        if _sha256(_canonical_bytes(unsigned)) != event_digest:
            raise TraceIntegrityError("trace event self hash is invalid")
        if raw != _canonical_line(record):
            raise TraceIntegrityError("trace chain line is not canonical JSONL")

        if not chain_started:
            if sequence != 1:
                raise TraceIntegrityError("trace chain must start at sequence 1")
            if legacy_lines:
                legacy_prefix = b"".join(legacy_lines)
                prefix_size = envelope.get("legacy_prefix_size_bytes")
                if (
                    isinstance(prefix_size, bool)
                    or not isinstance(prefix_size, int)
                    or previous_digest != _sha256(legacy_lines[-1])
                    or envelope.get("legacy_prefix_sha256") != _sha256(legacy_prefix)
                    or prefix_size != len(legacy_prefix)
                ):
                    raise TraceIntegrityError("trace legacy-prefix anchor is invalid")
            elif (
                previous_digest != SHA256_ZERO
                or _INTEGRITY_LEGACY_FIELDS & set(envelope)
            ):
                raise TraceIntegrityError("trace genesis anchor is invalid")
            chain_started = True
        elif (
            sequence != last_sequence + 1
            or last_raw_line is None
            or previous_digest != _sha256(last_raw_line)
            or _INTEGRITY_LEGACY_FIELDS & set(envelope)
        ):
            raise TraceIntegrityError("trace hash chain is discontinuous")

        last_sequence = sequence
        last_raw_line = raw
        records.append(record)

    if require_chain and lines and not chain_started:
        raise TraceIntegrityError("trace log contains no verifiable chain")

    return TraceChainState(
        records=tuple(records),
        line_count=len(lines),
        chained_count=last_sequence if chain_started else 0,
        legacy_count=len(legacy_lines),
        last_sequence=last_sequence,
        last_raw_line=last_raw_line,
        legacy_prefix=b"".join(legacy_lines),
    )


def _prepare_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict) or "integrity" in record:
        raise TraceIntegrityError("trace caller cannot supply an integrity envelope")
    prepared = _strict_json_loads(canonical_trace_json(record))
    if not isinstance(prepared, dict):
        raise TraceIntegrityError("trace record is not an object")
    return prepared


def _build_trace_line(
    record: dict[str, Any], state: TraceChainState
) -> tuple[bytes, dict[str, Any]]:
    prepared = _prepare_record(record)
    if state.last_sequence >= MAX_SAFE_SEQUENCE:
        raise TraceIntegrityError("trace integrity sequence is exhausted")
    has_chain = state.last_sequence > 0
    integrity: dict[str, Any] = {
        "schema_version": INTEGRITY_SCHEMA_VERSION,
        "sequence": state.last_sequence + 1 if has_chain else 1,
        "previous_event_sha256": (
            _sha256(state.last_raw_line) if state.last_raw_line is not None else SHA256_ZERO
        ),
    }
    if not has_chain and state.legacy_prefix:
        integrity["legacy_prefix_sha256"] = _sha256(state.legacy_prefix)
        integrity["legacy_prefix_size_bytes"] = len(state.legacy_prefix)
    unsigned = dict(prepared)
    unsigned["integrity"] = integrity
    integrity["event_sha256"] = _sha256(_canonical_bytes(unsigned))
    event = dict(prepared)
    event["integrity"] = integrity
    return _canonical_line(event), event


def build_trace_line(record: dict[str, Any], state: TraceChainState) -> bytes:
    """Build one canonical chained line without mutating the supplied state."""

    return _build_trace_line(record, state)[0]


def _advance_state(
    state: TraceChainState, line: bytes, event: dict[str, Any]
) -> TraceChainState:
    return TraceChainState(
        records=state.records + (event,),
        line_count=state.line_count + 1,
        chained_count=state.last_sequence + 1,
        legacy_count=state.legacy_count,
        last_sequence=state.last_sequence + 1,
        last_raw_line=line,
        legacy_prefix=state.legacy_prefix,
    )


def encode_trace_chain(records: Sequence[dict[str, Any]]) -> bytes:
    """Encode records as a new genesis-rooted trace chain."""

    state = verify_trace_bytes(b"", require_chain=False)
    lines: list[bytes] = []
    for record in records:
        line, event = _build_trace_line(record, state)
        lines.append(line)
        state = _advance_state(state, line, event)
    data = b"".join(lines)
    verify_trace_bytes(data, require_chain=bool(records))
    return data


def _compact_state(state: TraceChainState) -> TraceChainState:
    return TraceChainState(
        records=(),
        line_count=state.line_count,
        chained_count=state.chained_count,
        legacy_count=state.legacy_count,
        last_sequence=state.last_sequence,
        last_raw_line=state.last_raw_line,
        legacy_prefix=state.legacy_prefix if state.last_sequence == 0 else b"",
    )


def _file_identity(file_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def require_private_regular(file_stat: os.stat_result, label: str) -> None:
    if not stat.S_ISREG(file_stat.st_mode):
        raise TraceIntegrityError(f"{label} is not a regular file")
    if file_stat.st_uid != os.geteuid():
        raise TraceIntegrityError(f"{label} must be owned by the current euid")
    if file_stat.st_nlink != 1:
        raise TraceIntegrityError(f"{label} must have exactly one hard link")
    if stat.S_IMODE(file_stat.st_mode) & 0o077:
        raise TraceIntegrityError(f"{label} must not grant group or other permissions")


def _open_flags(*flags: int) -> int:
    value = 0
    for flag in flags:
        value |= flag
    value |= getattr(os, "O_NOFOLLOW", 0)
    return value


def canonical_absolute_path(path: str | Path, *, label: str) -> Path:
    """Preserve and validate the caller's lexical path before filesystem access."""

    raw_path = os.fspath(path)
    if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
        raise TraceIntegrityError(f"{label} must be a canonical absolute path")
    candidate = Path(raw_path)
    normalized = os.path.normpath(raw_path)
    if (
        not candidate.is_absolute()
        or raw_path != normalized
        or (raw_path != os.sep and raw_path.startswith(os.sep * 2))
    ):
        raise TraceIntegrityError(f"{label} must be a canonical absolute path")
    return candidate


def _directory_open_flags() -> int:
    return _open_flags(os.O_RDONLY, getattr(os, "O_DIRECTORY", 0))


def _require_private_directory(directory_stat: os.stat_result, label: str) -> None:
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise TraceIntegrityError(f"{label} is not a directory")
    if directory_stat.st_uid != os.geteuid():
        raise TraceIntegrityError(f"{label} must be owned by the current euid")
    if stat.S_IMODE(directory_stat.st_mode) & 0o077:
        raise TraceIntegrityError(f"{label} must be a private directory")


def _open_directory_chain(
    components: Sequence[str],
    *,
    label: str,
    create: bool,
) -> int:
    descriptor = os.open(os.sep, _directory_open_flags())
    try:
        for component in components:
            try:
                child = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise TraceIntegrityError(f"{label} component is unavailable") from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


@contextmanager
def secure_directory_fd(
    path: str | Path,
    *,
    label: str,
    create: bool = False,
) -> Iterator[tuple[Path, int]]:
    """Hold a private directory inode reached without following symlinks."""

    candidate = canonical_absolute_path(path, label=label)
    descriptor = _open_directory_chain(
        candidate.parts[1:],
        label=label,
        create=create,
    )
    try:
        _require_private_directory(os.fstat(descriptor), label)
        yield candidate, descriptor
    finally:
        os.close(descriptor)


@contextmanager
def secure_parent_fd(
    path: str | Path,
    *,
    label: str,
    create_parents: bool = False,
) -> Iterator[SecurePathHandle]:
    """Hold the parent inode so later leaf operations cannot be path-redirected."""

    candidate = canonical_absolute_path(path, label=label)
    if candidate == Path(os.sep):
        raise TraceIntegrityError(f"{label} must name a file below the root directory")
    descriptor = _open_directory_chain(
        candidate.parts[1:-1],
        label=label,
        create=create_parents,
    )
    try:
        _require_private_directory(os.fstat(descriptor), f"{label} parent")
        yield SecurePathHandle(candidate, descriptor, candidate.name)
    finally:
        os.close(descriptor)


def secure_path_components(
    path: str | Path,
    *,
    label: str,
    create_parents: bool = False,
    create_directory: bool = False,
    allow_missing_leaf: bool = False,
) -> Path:
    """Compatibility validator backed by held directory descriptors."""

    candidate = canonical_absolute_path(path, label=label)
    if create_directory:
        with secure_directory_fd(candidate, label=label, create=True):
            return candidate
    with secure_parent_fd(
        candidate,
        label=label,
        create_parents=create_parents,
    ) as handle:
        try:
            leaf_stat = os.stat(
                handle.leaf,
                dir_fd=handle.parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if allow_missing_leaf:
                return candidate
            raise
        if stat.S_ISLNK(leaf_stat.st_mode):
            raise TraceIntegrityError(f"{label} contains a symlink component")
    return candidate


def fsync_directory_fd(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF}:
            raise


def _named_file_stat(handle: SecurePathHandle, label: str) -> os.stat_result:
    try:
        file_stat = os.stat(
            handle.leaf,
            dir_fd=handle.parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise TraceIntegrityError(f"{label} path is unavailable") from exc
    require_private_regular(file_stat, label)
    return file_stat


def _require_named_identity(
    handle: SecurePathHandle,
    descriptor_stat: os.stat_result,
    label: str,
) -> None:
    named_stat = _named_file_stat(handle, label)
    if (named_stat.st_dev, named_stat.st_ino) != (
        descriptor_stat.st_dev,
        descriptor_stat.st_ino,
    ):
        raise TraceIntegrityError(f"{label} identity changed")


def _require_lock_identity(
    handle: SecurePathHandle,
    lock_name: str,
    descriptor_stat: os.stat_result,
) -> None:
    try:
        named_stat = os.stat(
            lock_name,
            dir_fd=handle.parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise TraceIntegrityError("trace lock path is unavailable") from exc
    require_private_regular(named_stat, "trace lock")
    if (named_stat.st_dev, named_stat.st_ino) != (
        descriptor_stat.st_dev,
        descriptor_stat.st_ino,
    ):
        raise TraceIntegrityError("trace lock identity changed")


def _open_lock_file(handle: SecurePathHandle, lock_name: str) -> int:
    for attempt in range(5):
        try:
            return os.open(
                lock_name,
                _open_flags(os.O_RDWR, os.O_CREAT),
                0o600,
                dir_fd=handle.parent_fd,
            )
        except FileNotFoundError:
            _require_private_directory(
                os.fstat(handle.parent_fd),
                "trace path parent",
            )
            if attempt == 4:
                raise
            time.sleep(0.001)
    raise AssertionError("unreachable")


@contextmanager
def trace_file_lock(
    path: str | Path,
    *,
    create_parent: bool = True,
) -> Iterator[SecurePathHandle]:
    """Take the cross-process lock shared by append and explicit rotation."""

    with secure_parent_fd(
        path,
        label="trace path",
        create_parents=create_parent,
    ) as handle:
        lock_name = f"{handle.leaf}.lock"
        descriptor = _open_lock_file(handle, lock_name)
        locked = False
        try:
            lock_stat = os.fstat(descriptor)
            require_private_regular(lock_stat, "trace lock")
            os.fchmod(descriptor, 0o600)
            lock_stat = os.fstat(descriptor)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
            _require_lock_identity(handle, lock_name, lock_stat)
            yield handle
        finally:
            try:
                if locked:
                    _require_lock_identity(handle, lock_name, lock_stat)
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _read_descriptor(descriptor: int, expected_size: int) -> bytes:
    if expected_size > MAX_TRACE_BYTES:
        raise TraceIntegrityError("trace log exceeds bounded verification size", "EFBIG")
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        chunk = os.read(descriptor, min(1024 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) != expected_size:
        raise TraceIntegrityError("trace log changed during verification")
    return data


def verify_trace_file(path: str | Path, *, require_chain: bool = True) -> TraceChainState:
    """Verify one on-disk trace while excluding concurrent append/rotation."""

    trace_path = canonical_absolute_path(path, label="trace path")
    with trace_file_lock(trace_path, create_parent=False) as handle:
        try:
            descriptor = os.open(
                handle.leaf,
                _open_flags(os.O_RDONLY),
                dir_fd=handle.parent_fd,
            )
        except FileNotFoundError:
            raise FileNotFoundError(trace_path) from None
        try:
            file_stat = os.fstat(descriptor)
            require_private_regular(file_stat, "trace log")
            _require_named_identity(handle, file_stat, "trace log")
            data = _read_descriptor(descriptor, file_stat.st_size)
            after_stat = os.fstat(descriptor)
            if _file_identity(after_stat) != _file_identity(file_stat):
                raise TraceIntegrityError("trace log changed during verification")
            _require_named_identity(handle, after_stat, "trace log")
        finally:
            os.close(descriptor)
    return verify_trace_bytes(data, require_chain=require_chain)


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise TraceIntegrityError("trace append made no progress")
        offset += written


class QueryTraceLogger:
    """Append-only, fail-closed JSONL logger for retrieval diagnostics."""

    def __init__(self, path: str | Path):
        self.path = canonical_absolute_path(path, label="trace path")
        self.enabled = os.environ.get("RAG_TRACE_ENABLED", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        self._lock = threading.RLock()
        self._verified_identity: tuple[int, int, int, int, int] | None = None
        self._verified_state: TraceChainState | None = None

    def record(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        item = dict(payload)
        item.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        if "query" in item and isinstance(item["query"], str):
            item["query"] = item["query"][:500]

        with self._lock, trace_file_lock(self.path) as handle:
            descriptor = os.open(
                handle.leaf,
                _open_flags(os.O_RDWR, os.O_APPEND, os.O_CREAT),
                0o600,
                dir_fd=handle.parent_fd,
            )
            try:
                file_stat = os.fstat(descriptor)
                require_private_regular(file_stat, "trace log")
                os.fchmod(descriptor, 0o600)
                file_stat = os.fstat(descriptor)
                _require_named_identity(handle, file_stat, "trace log")
                identity = _file_identity(file_stat)
                if (
                    self._verified_identity == identity
                    and self._verified_state is not None
                ):
                    state = self._verified_state
                else:
                    data = _read_descriptor(descriptor, file_stat.st_size)
                    state = _compact_state(
                        verify_trace_bytes(data, require_chain=False)
                    )

                line, event = _build_trace_line(item, state)
                if file_stat.st_size + len(line) > MAX_TRACE_BYTES:
                    raise TraceIntegrityError(
                        "trace append exceeds bounded verification size", "EFBIG"
                    )
                if _file_identity(os.fstat(descriptor)) != identity:
                    raise TraceIntegrityError("trace log changed before append")
                _require_named_identity(handle, file_stat, "trace log")
                try:
                    _write_all(descriptor, line)
                    os.fsync(descriptor)
                    appended_stat = os.fstat(descriptor)
                    if appended_stat.st_size != file_stat.st_size + len(line):
                        raise TraceIntegrityError(
                            "trace log size changed during append"
                        )
                    _require_named_identity(handle, appended_stat, "trace log")
                except Exception:
                    self._verified_identity = None
                    self._verified_state = None
                    raise
                state = _compact_state(_advance_state(state, line, event))
                file_stat = appended_stat
                self._verified_identity = _file_identity(file_stat)
                self._verified_state = state
            finally:
                os.close(descriptor)
            fsync_directory_fd(handle.parent_fd)


def source_name(source: dict[str, Any]) -> str:
    return str(
        source.get("doc_name")
        or source.get("doc")
        or source.get("source_doc")
        or source.get("file")
        or ""
    )
