#!/usr/bin/env python3
"""Explicitly rotate a verified query trace into an anchored gzip archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any


DEPLOY_ROOT = Path(__file__).resolve().parent.parent
if str(DEPLOY_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPLOY_ROOT))

from rag_store.query_trace import (  # noqa: E402
    MAX_TRACE_BYTES,
    SecurePathHandle,
    TraceIntegrityError,
    canonical_absolute_path,
    encode_trace_chain,
    fsync_directory_fd,
    require_private_regular,
    secure_directory_fd,
    secure_parent_fd,
    trace_file_lock,
    verify_trace_bytes,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _open_nofollow(
    name: str,
    flags: int,
    mode: int = 0o600,
    *,
    dir_fd: int,
) -> int:
    return os.open(
        name,
        flags | getattr(os, "O_NOFOLLOW", 0),
        mode,
        dir_fd=dir_fd,
    )


def _file_identity(file_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _read_live(
    handle: SecurePathHandle,
) -> tuple[bytes, tuple[int, int, int, int, int]]:
    descriptor = _open_nofollow(
        handle.leaf,
        os.O_RDONLY,
        dir_fd=handle.parent_fd,
    )
    try:
        file_stat = os.fstat(descriptor)
        require_private_regular(file_stat, "trace log")
        _assert_live_identity(handle, _file_identity(file_stat))
        if file_stat.st_size > MAX_TRACE_BYTES:
            raise TraceIntegrityError(
                "trace log exceeds bounded verification size", "EFBIG"
            )
        chunks: list[bytes] = []
        remaining = file_stat.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != file_stat.st_size:
            raise TraceIntegrityError("trace log changed during rotation read")
        after_stat = os.fstat(descriptor)
        if _file_identity(after_stat) != _file_identity(file_stat):
            raise TraceIntegrityError("trace log changed during rotation read")
        _assert_live_identity(handle, _file_identity(after_stat))
        return data, _file_identity(after_stat)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise TraceIntegrityError("rotation write made no progress")
        offset += written


def _atomic_write(
    parent_fd: int,
    name: str,
    data: bytes,
    *,
    replace: bool,
    expected_identity: tuple[int, int, int, int, int] | None = None,
) -> None:
    temporary = f".{name}.{os.getpid()}.{time.time_ns()}.tmp"
    descriptor: int | None = None
    try:
        descriptor = _open_nofollow(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=parent_fd,
        )
        _write_all(descriptor, data)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if replace:
            if expected_identity is None:
                raise TraceIntegrityError("replacement requires an expected file identity")
            current_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            require_private_regular(current_stat, "trace log")
            if _file_identity(current_stat) != expected_identity:
                raise TraceIntegrityError("trace log changed before replacement")
            os.replace(
                temporary,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
        else:
            os.link(
                temporary,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            os.unlink(temporary, dir_fd=parent_fd)
        output_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        require_private_regular(output_stat, "rotation output")
        fsync_directory_fd(parent_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


def _without_integrity(record: dict[str, Any]) -> dict[str, Any]:
    value = dict(record)
    value.pop("integrity", None)
    return value


def _archive_candidates(archive_fd: int, prefix: str) -> list[str]:
    start = f"{prefix}."
    candidates = sorted(
        name
        for name in os.listdir(archive_fd)
        if name.startswith(start) and name.endswith(".jsonl.gz")
    )
    for name in candidates:
        require_private_regular(
            os.stat(name, dir_fd=archive_fd, follow_symlinks=False),
            "trace archive",
        )
    return candidates


def prune_archives(archive_fd: int, prefix: str, keep: int) -> list[str]:
    archives = _archive_candidates(archive_fd, prefix)
    removed: list[str] = []
    for old in archives[: max(0, len(archives) - keep)]:
        current_stat = os.stat(old, dir_fd=archive_fd, follow_symlinks=False)
        require_private_regular(current_stat, "trace archive")
        os.unlink(old, dir_fd=archive_fd)
        removed.append(old)
    if removed:
        fsync_directory_fd(archive_fd)
    return removed


def _assert_live_identity(
    handle: SecurePathHandle,
    expected_identity: tuple[int, int, int, int, int],
) -> None:
    try:
        current_stat = os.stat(
            handle.leaf,
            dir_fd=handle.parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError as exc:
        raise TraceIntegrityError("trace log disappeared during rotation") from exc
    require_private_regular(current_stat, "trace log")
    if _file_identity(current_stat) != expected_identity:
        raise TraceIntegrityError("trace log changed during rotation")


def rotate(
    trace_path: str | Path,
    archive_dir: str | Path,
    *,
    max_mb: float,
    keep_lines: int,
    keep_archives: int,
    dry_run: bool,
    prune_old_archives: bool = False,
) -> dict[str, Any]:
    """Rotate one explicitly selected trace after strict integrity verification."""

    if not math.isfinite(max_mb) or max_mb < 0:
        raise ValueError("max_mb must be a finite non-negative number")
    if keep_lines < 0:
        raise ValueError("keep_lines must be non-negative")
    if keep_archives < 1:
        raise ValueError("keep_archives must be at least one")

    live = canonical_absolute_path(trace_path, label="trace rotation target")
    archive_root = canonical_absolute_path(
        archive_dir,
        label="trace archive directory",
    )
    with secure_parent_fd(
        live,
        label="trace rotation target",
        create_parents=False,
    ) as initial_handle:
        try:
            live_stat = os.stat(
                initial_handle.leaf,
                dir_fd=initial_handle.parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return {"status": "missing", "trace": str(live)}
        require_private_regular(live_stat, "trace rotation target")

    with trace_file_lock(live, create_parent=False) as live_handle:
        data, live_identity = _read_live(live_handle)
        verified = verify_trace_bytes(data, require_chain=False)
        size_mb = len(data) / (1024 * 1024)
        if size_mb <= max_mb:
            return {
                "status": "below_threshold",
                "trace": str(live),
                "size_bytes": len(data),
            }

        if dry_run:
            return {
                "status": "dry_run",
                "trace": str(live),
                "size_bytes": len(data),
                "verified_lines": verified.line_count,
            }

        with secure_directory_fd(
            archive_root,
            label="trace archive directory",
            create=True,
        ) as (_archive_path, archive_fd):
            _archive_candidates(archive_fd, live.name)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            archive_name = (
                f"{live.name}.{stamp}_{time.time_ns() % 1_000_000_000:09d}.jsonl.gz"
            )
            archive_path = archive_root / archive_name
            compressed = gzip.compress(data, compresslevel=9, mtime=0)
            _atomic_write(archive_fd, archive_name, compressed, replace=False)

            retained = (
                [_without_integrity(record) for record in verified.records[-keep_lines:]]
                if keep_lines
                else []
            )
            last_record = verified.records[-1] if verified.records else {}
            last_integrity = last_record.get("integrity")
            anchor = {
                "event_type": "trace_rotation_anchor",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "archive_name": archive_name,
                "archive_content_sha256": _sha256(data),
                "archive_gzip_sha256": _sha256(compressed),
                "archive_size_bytes": len(data),
                "archive_gzip_size_bytes": len(compressed),
                "archived_line_count": verified.line_count,
                "archived_legacy_count": verified.legacy_count,
                "archived_last_sequence": verified.last_sequence,
                "archived_last_line_sha256": (
                    _sha256(verified.last_raw_line)
                    if verified.last_raw_line is not None
                    else None
                ),
                "archived_last_event_sha256": (
                    last_integrity.get("event_sha256")
                    if isinstance(last_integrity, dict)
                    else None
                ),
                "retained_record_count": len(retained),
            }
            replacement = encode_trace_chain([anchor, *retained])
            verify_trace_bytes(replacement)
            _assert_live_identity(live_handle, live_identity)
            _atomic_write(
                live_handle.parent_fd,
                live_handle.leaf,
                replacement,
                replace=True,
                expected_identity=live_identity,
            )

            removed = (
                prune_archives(archive_fd, live.name, keep_archives)
                if prune_old_archives
                else []
            )
        return {
            "status": "rotated",
            "trace": str(live),
            "old_size_bytes": len(data),
            "new_size_bytes": len(replacement),
            "archive": str(archive_path),
            "archive_content_sha256": anchor["archive_content_sha256"],
            "archive_gzip_sha256": anchor["archive_gzip_sha256"],
            "retained_record_count": len(retained),
            "archive_pruning_enabled": prune_old_archives,
            "removed_archives": removed,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, help="explicit trace JSONL path")
    parser.add_argument(
        "--archive-dir",
        required=True,
        help="explicit archive output directory",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=20.0,
        help="rotate only when the trace is larger than this many MiB",
    )
    parser.add_argument(
        "--keep-lines",
        type=int,
        default=300,
        help="records to retain and re-chain after the rotation anchor",
    )
    parser.add_argument(
        "--keep-archives",
        type=int,
        default=12,
        help="archives to retain only when --prune-archives is authorized",
    )
    parser.add_argument(
        "--prune-archives",
        action="store_true",
        help="explicitly authorize deletion of archives beyond --keep-archives",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = rotate(
            args.trace,
            args.archive_dir,
            max_mb=args.max_mb,
            keep_lines=args.keep_lines,
            keep_archives=args.keep_archives,
            dry_run=args.dry_run,
            prune_old_archives=args.prune_archives,
        )
    except (OSError, TraceIntegrityError, ValueError) as exc:
        print(f"trace rotation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
