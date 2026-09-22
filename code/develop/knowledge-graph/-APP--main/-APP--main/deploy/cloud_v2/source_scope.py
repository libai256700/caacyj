#!/usr/bin/env python3
"""Validate the exact revision-a-r9 source-byte approval boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCOPE_SCHEMA_VERSION = "cloud-v2-source-scope-v1"
CANDIDATE_ID = "revision-a-r9"
EXPECTED_SOURCE_COUNT = 35
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "9e0f9018c9a72f2a99c19a7c6b2362cb49154233b770c8f7c41af0b48a3aa8fe"
)
EXPECTED_ALLOWLIST_SHA256 = (
    "a5efe7537d9ab9de1624bf40e5cb944f95c35fb0252c04927f73886c1bb5d64f"
)
EXPECTED_SOURCE_PATHS_SHA256 = (
    "81e9ca4f8aac3b25aaeeeb4481ca6b1147591dbfca6106dae1aa0eee7ba0b003"
)
EXPECTED_STOP_A_RECEIPT_SHA256 = (
    "4515475c1e89b85aea91eb912d238d0eb63776f82b75468ac4aecd8206c4ab6c"
)
EXPECTED_SOURCE_DLP_RECEIPT_SHA256 = (
    "ee460cfd8d35a6ace33d87c6f2f313e68e1ef6b5c5ceaa8b29fcb70950219123"
)
MAX_GOVERNANCE_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_APPROVED_SOURCE_BYTES = 128 * 1024 * 1024
_READ_BLOCK_BYTES = 1024 * 1024


class SourceScopeError(ValueError):
    """The requested input is outside or inconsistent with the approval."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, order=True)
class _NodeIdentity:
    device: int
    inode: int
    mode: int
    link_count: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True, order=True)
class _TreeNode:
    relative_path: str
    kind: str
    identity: _NodeIdentity


@dataclass
class _HeldScopeFile:
    relative_path: str
    descriptor: int
    identity: _NodeIdentity
    sha256: str
    max_bytes: int
    field: str
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        os.close(self.descriptor)


@dataclass
class _LoadedScopeState:
    source_root_identity: _NodeIdentity
    governance_root_identity: _NodeIdentity
    source_nodes: tuple[_TreeNode, ...]
    source_root_descriptor: int
    governance_root_descriptor: int
    source_files: tuple[_HeldScopeFile, ...]
    governance_files: tuple[_HeldScopeFile, ...]
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        first_error: BaseException | None = None
        for held in (*self.source_files, *self.governance_files):
            try:
                held.close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        for descriptor in (self.governance_root_descriptor, self.source_root_descriptor):
            try:
                os.close(descriptor)
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error


def _node_identity(value: os.stat_result) -> _NodeIdentity:
    return _NodeIdentity(
        device=value.st_dev,
        inode=value.st_ino,
        mode=value.st_mode,
        link_count=value.st_nlink,
        size=value.st_size,
        mtime_ns=value.st_mtime_ns,
        ctime_ns=value.st_ctime_ns,
    )


def _best_effort_close(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except BaseException:
        pass


def _require_descriptor_runtime() -> None:
    required_flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if (
        any(not hasattr(os, name) for name in required_flags)
        or not hasattr(os, "pread")
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
        or os.scandir not in os.supports_fd
    ):
        raise SourceScopeError("descriptor-relative source validation is unavailable")


def _open_directory_path(
    raw: str | Path,
    field: str,
) -> tuple[Path, int, _NodeIdentity]:
    try:
        path = Path(os.path.abspath(os.fspath(raw)))
    except (TypeError, ValueError, OSError) as exc:
        raise SourceScopeError(f"{field} path is invalid") from exc
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        current = os.open("/", flags)
    except OSError as exc:
        raise SourceScopeError(f"{field} root cannot be opened safely") from exc
    try:
        for component in path.parts[1:]:
            try:
                inspected = os.stat(
                    component,
                    dir_fd=current,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise SourceScopeError(f"{field} cannot be inspected") from exc
            if stat.S_ISLNK(inspected.st_mode):
                raise SourceScopeError(
                    f"{field} must be a real directory; path contains a symlink"
                )
            if not stat.S_ISDIR(inspected.st_mode):
                raise SourceScopeError(f"{field} must be a real directory")
            child: int | None = None
            try:
                child = os.open(component, flags, dir_fd=current)
                opened = os.fstat(child)
            except OSError as exc:
                if child is not None:
                    _best_effort_close(child)
                raise SourceScopeError(f"{field} cannot be opened safely") from exc
            except BaseException:
                if child is not None:
                    _best_effort_close(child)
                raise
            if _node_identity(inspected) != _node_identity(opened):
                _best_effort_close(child)
                raise SourceScopeError(f"{field} identity changed while opening")
            try:
                os.close(current)
            except BaseException:
                _best_effort_close(child)
                raise
            current = child
        opened_identity = _node_identity(os.fstat(current))
        if not stat.S_ISDIR(opened_identity.mode):
            raise SourceScopeError(f"{field} must be a real directory")
        return path, current, opened_identity
    except BaseException:
        _best_effort_close(current)
        raise


def _open_root_directory(
    raw: str | Path,
    field: str,
) -> tuple[Path, int, _NodeIdentity]:
    _require_descriptor_runtime()
    path, descriptor, opened_identity = _open_directory_path(raw, field)
    try:
        verified_path, verified_descriptor, verified_identity = _open_directory_path(
            path,
            field,
        )
        try:
            if verified_path != path or verified_identity != opened_identity:
                raise SourceScopeError(f"{field} identity changed while opening")
        finally:
            os.close(verified_descriptor)
        if _node_identity(os.fstat(descriptor)) != opened_identity:
            raise SourceScopeError(f"{field} identity changed while opening")
        return path, descriptor, opened_identity
    except BaseException:
        _best_effort_close(descriptor)
        raise


def _assert_root_binding(
    path: Path,
    descriptor: int,
    expected: _NodeIdentity,
    field: str,
) -> None:
    try:
        descriptor_state = os.fstat(descriptor)
    except OSError as exc:
        raise SourceScopeError(f"{field} cannot be revalidated") from exc
    if _node_identity(descriptor_state) != expected:
        raise SourceScopeError(f"{field} identity changed")
    reopened_path, reopened_descriptor, reopened_identity = _open_directory_path(path, field)
    try:
        if reopened_path != path or reopened_identity != expected:
            raise SourceScopeError(f"{field} identity changed")
    finally:
        os.close(reopened_descriptor)


def _canonical_node_relative(raw: str) -> str:
    if (
        not isinstance(raw, str)
        or not raw
        or raw.startswith("/")
        or "\\" in raw
        or "//" in raw
        or "\x00" in raw
    ):
        raise SourceScopeError("scope node path is not canonical")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise SourceScopeError("scope node path contains a dot or empty component")
    return path.as_posix()


def _open_regular_at(
    root_descriptor: int,
    raw_relative: str,
    *,
    field: str,
) -> tuple[int, _NodeIdentity]:
    relative = _canonical_node_relative(raw_relative)
    parts = PurePosixPath(relative).parts
    current = os.dup(root_descriptor)
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        for part in parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=current)
            except OSError as exc:
                raise SourceScopeError(
                    f"symlink or invalid parent is forbidden in {field} path: {parts[-1]}"
                ) from exc
            try:
                child_state = os.fstat(child)
            except OSError as exc:
                _best_effort_close(child)
                raise SourceScopeError(
                    f"{field} parent cannot be inspected safely: {parts[-1]}"
                ) from exc
            except BaseException:
                _best_effort_close(child)
                raise
            if not stat.S_ISDIR(child_state.st_mode):
                _best_effort_close(child)
                raise SourceScopeError(f"{field} parent is not a directory: {parts[-1]}")
            try:
                os.close(current)
            except BaseException:
                _best_effort_close(child)
                raise
            current = child
        file_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        except OSError as exc:
            try:
                state = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
            except OSError:
                state = None
            if state is not None and stat.S_ISLNK(state.st_mode):
                message = f"symlink is forbidden in {field} path: {parts[-1]}"
            else:
                message = f"{field} path cannot be opened safely: {parts[-1]}"
            raise SourceScopeError(message) from exc
        try:
            opened = os.fstat(descriptor)
        except OSError as exc:
            _best_effort_close(descriptor)
            raise SourceScopeError(
                f"{field} cannot be inspected safely: {parts[-1]}"
            ) from exc
        except BaseException:
            _best_effort_close(descriptor)
            raise
        if not stat.S_ISREG(opened.st_mode):
            _best_effort_close(descriptor)
            raise SourceScopeError(f"{field} is not a regular file: {parts[-1]}")
        if opened.st_nlink != 1:
            _best_effort_close(descriptor)
            raise SourceScopeError(f"hardlink is forbidden for {field}: {parts[-1]}")
        return descriptor, _node_identity(opened)
    finally:
        _best_effort_close(current)


def _read_descriptor_bytes(
    descriptor: int,
    *,
    max_bytes: int,
    field: str,
) -> tuple[bytes, _NodeIdentity]:
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise SourceScopeError(f"{field} exceeds its approved byte boundary")
        chunks: list[bytes] = []
        offset = 0
        while offset < before.st_size:
            block = os.pread(
                descriptor,
                min(_READ_BLOCK_BYTES, before.st_size - offset),
                offset,
            )
            if not block:
                raise SourceScopeError(f"{field} became shorter while reading")
            chunks.append(block)
            offset += len(block)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise SourceScopeError(f"{field} cannot be read safely") from exc
    if _node_identity(before) != _node_identity(after) or offset != after.st_size:
        raise SourceScopeError(f"{field} identity changed while reading")
    return b"".join(chunks), _node_identity(after)


def _read_held_scope_file(held: _HeldScopeFile) -> bytes:
    if held.closed:
        raise SourceScopeError(f"{held.field} held descriptor is closed")
    payload, identity = _read_descriptor_bytes(
        held.descriptor,
        max_bytes=held.max_bytes,
        field=held.field,
    )
    if identity != held.identity:
        raise SourceScopeError(f"{held.field} identity changed: {held.relative_path}")
    if hashlib.sha256(payload).hexdigest() != held.sha256:
        raise SourceScopeError(f"{held.field} bytes changed: {held.relative_path}")
    return payload


def _open_held_scope_file(
    root_descriptor: int,
    relative: str,
    *,
    expected_identity: _NodeIdentity | None,
    expected_sha256: str,
    max_bytes: int,
    field: str,
) -> tuple[_HeldScopeFile, bytes]:
    descriptor, identity = _open_regular_at(
        root_descriptor,
        relative,
        field=field,
    )
    held = _HeldScopeFile(
        relative_path=relative,
        descriptor=descriptor,
        identity=identity,
        sha256=expected_sha256,
        max_bytes=max_bytes,
        field=field,
    )
    try:
        if expected_identity is not None and identity != expected_identity:
            raise SourceScopeError(
                f"{field} identity changed: {PurePosixPath(relative).name}"
            )
        return held, _read_held_scope_file(held)
    except BaseException:
        held.close()
        raise


def _assert_held_scope_path(root_descriptor: int, held: _HeldScopeFile) -> None:
    if held.closed:
        raise SourceScopeError(f"{held.field} held descriptor is closed")
    descriptor: int | None = None
    try:
        descriptor, identity = _open_regular_at(
            root_descriptor,
            held.relative_path,
            field=held.field,
        )
        if identity != held.identity:
            raise SourceScopeError(
                f"{held.field} path identity changed: {held.relative_path}"
            )
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_regular_bytes_at(
    root_descriptor: int,
    relative: str,
    *,
    max_bytes: int,
    field: str,
    expected_identity: _NodeIdentity | None = None,
) -> tuple[bytes, _NodeIdentity]:
    descriptor, opened_identity = _open_regular_at(
        root_descriptor,
        relative,
        field=field,
    )
    try:
        if expected_identity is not None and opened_identity != expected_identity:
            raise SourceScopeError(f"{field} identity changed: {PurePosixPath(relative).name}")
        payload, read_identity = _read_descriptor_bytes(
            descriptor,
            max_bytes=max_bytes,
            field=field,
        )
        if read_identity != opened_identity:
            raise SourceScopeError(f"{field} identity changed: {PurePosixPath(relative).name}")
        return payload, read_identity
    finally:
        os.close(descriptor)


def _walk_tree_at(root_descriptor: int, *, field: str) -> tuple[_TreeNode, ...]:
    records: list[_TreeNode] = []

    def visit(directory_descriptor: int, prefix: PurePosixPath | None) -> None:
        before = _node_identity(os.fstat(directory_descriptor))
        try:
            with os.scandir(directory_descriptor) as entries:
                names = sorted(entry.name for entry in entries)
        except OSError as exc:
            raise SourceScopeError(f"{field} cannot be enumerated") from exc
        for name in names:
            relative = PurePosixPath(name) if prefix is None else prefix / name
            canonical = _canonical_node_relative(relative.as_posix())
            try:
                inspected = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
            except OSError as exc:
                raise SourceScopeError(f"{field} node cannot be inspected") from exc
            if stat.S_ISLNK(inspected.st_mode):
                raise SourceScopeError(f"{field} contains a symlink")
            if stat.S_ISDIR(inspected.st_mode):
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
                try:
                    child = os.open(name, flags, dir_fd=directory_descriptor)
                except OSError as exc:
                    raise SourceScopeError(f"{field} directory changed while opening") from exc
                try:
                    opened = _node_identity(os.fstat(child))
                    if opened != _node_identity(inspected):
                        raise SourceScopeError(f"{field} directory identity changed")
                    records.append(_TreeNode(canonical, "directory", opened))
                    visit(child, relative)
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(inspected.st_mode):
                raise SourceScopeError(f"{field} contains a nonregular node")
            descriptor, opened = _open_regular_at(
                directory_descriptor,
                name,
                field=field,
            )
            os.close(descriptor)
            if opened != _node_identity(inspected):
                raise SourceScopeError(f"{field} file identity changed")
            records.append(_TreeNode(canonical, "file", opened))
        after = _node_identity(os.fstat(directory_descriptor))
        if before != after:
            raise SourceScopeError(f"{field} changed while being enumerated")

    visit(root_descriptor, None)
    return tuple(sorted(records))


def canonical_relative_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw or raw.startswith("/"):
        raise SourceScopeError("source path must be a non-empty relative path")
    if "\\" in raw or "//" in raw or "\x00" in raw:
        raise SourceScopeError("source path is not canonical POSIX")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise SourceScopeError("source path contains a dot or empty component")
    if path.suffix.lower() not in {".docx", ".pdf"}:
        raise SourceScopeError("only approved DOCX and PDF sources are supported")
    return path.as_posix()


def _strict_json_bytes(payload: bytes, name: str) -> Any:
    def reject_duplicate(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SourceScopeError(f"duplicate JSON key in {name}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda value: (_ for _ in ()).throw(
                SourceScopeError(f"non-finite JSON value in {name}: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceScopeError(f"invalid JSON artifact: {name}") from exc


def _real_directory(raw: str | Path, field: str) -> Path:
    path, descriptor, _ = _open_root_directory(raw, field)
    try:
        return path
    finally:
        os.close(descriptor)


def _require_regular_unsymlinked(
    path: Path,
    root: Path,
    *,
    field: str = "source",
) -> Path:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise SourceScopeError(f"{field} escaped its approved root") from exc
    root_path, root_descriptor, root_identity = _open_root_directory(root, f"{field} root")
    try:
        descriptor, _ = _open_regular_at(root_descriptor, relative, field=field)
        os.close(descriptor)
        _assert_root_binding(root_path, root_descriptor, root_identity, f"{field} root")
        return root_path / relative
    finally:
        os.close(root_descriptor)


@dataclass(frozen=True)
class ApprovedSource:
    relative_path: str
    source_sha256: str
    byte_disposition: str


@dataclass(frozen=True)
class ApprovedSourceScope:
    source_root: Path
    governance_root: Path
    records: tuple[ApprovedSource, ...]
    source_manifest_sha256: str
    allowlist_sha256: str
    stop_a_receipt_sha256: str
    source_dlp_receipt_sha256: str
    approval_recorded_at: str
    _loaded_state: _LoadedScopeState | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, source_root: str | Path, governance_root: str | Path) -> "ApprovedSourceScope":
        source_root, source_descriptor, source_root_identity = _open_root_directory(
            source_root,
            "approved source root",
        )
        try:
            governance_root, governance_descriptor, governance_root_identity = (
                _open_root_directory(governance_root, "governance root")
            )
        except BaseException:
            _best_effort_close(source_descriptor)
            raise
        expected_hashes = {
            "SOURCE_MANIFEST.sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "CLOUD_SOURCE_ALLOWLIST.json": EXPECTED_ALLOWLIST_SHA256,
            "SOURCE_PATHS.json": EXPECTED_SOURCE_PATHS_SHA256,
            "STOP_A_REVISION_APPROVAL_RECEIPT.json": EXPECTED_STOP_A_RECEIPT_SHA256,
            "source_dlp_receipt.json": EXPECTED_SOURCE_DLP_RECEIPT_SHA256,
        }
        held_governance_files: list[_HeldScopeFile] = []
        held_source_files: list[_HeldScopeFile] = []
        keep_descriptors = False
        result: ApprovedSourceScope | None = None
        try:
            governance_payloads: dict[str, bytes] = {}
            for name, expected in expected_hashes.items():
                held, payload = _open_held_scope_file(
                    governance_descriptor,
                    name,
                    expected_identity=None,
                    expected_sha256=expected,
                    max_bytes=MAX_GOVERNANCE_ARTIFACT_BYTES,
                    field="governance artifact",
                )
                held_governance_files.append(held)
                if hashlib.sha256(payload).hexdigest() != expected:
                    raise SourceScopeError(f"governance artifact identity mismatch: {name}")
                governance_payloads[name] = payload

            manifest = cls._parse_manifest_bytes(
                governance_payloads["SOURCE_MANIFEST.sha256"]
            )
            allowlist = _strict_json_bytes(
                governance_payloads["CLOUD_SOURCE_ALLOWLIST.json"],
                "CLOUD_SOURCE_ALLOWLIST.json",
            )
            receipt = _strict_json_bytes(
                governance_payloads["STOP_A_REVISION_APPROVAL_RECEIPT.json"],
                "STOP_A_REVISION_APPROVAL_RECEIPT.json",
            )
            source_paths = _strict_json_bytes(
                governance_payloads["SOURCE_PATHS.json"],
                "SOURCE_PATHS.json",
            )
            cls._validate_governance(allowlist, receipt, source_paths, manifest)

            allowed_records = {
                canonical_relative_path(item["relative_path"]): item
                for item in allowlist["sources"]
            }
            source_nodes = _walk_tree_at(source_descriptor, field="source root")
            source_files = {
                node.relative_path: node.identity
                for node in source_nodes
                if node.kind == "file"
            }
            if set(source_files) != set(manifest):
                raise SourceScopeError("source root contains missing or unapproved paths")

            records: list[ApprovedSource] = []
            for relative, expected_sha in manifest.items():
                held, payload = _open_held_scope_file(
                    source_descriptor,
                    relative,
                    expected_identity=source_files[relative],
                    expected_sha256=expected_sha,
                    max_bytes=MAX_APPROVED_SOURCE_BYTES,
                    field="approved source",
                )
                held_source_files.append(held)
                actual_sha = hashlib.sha256(payload).hexdigest()
                if actual_sha != expected_sha:
                    raise SourceScopeError(f"approved source hash mismatch: {relative}")
                if held.identity != source_files[relative]:
                    raise SourceScopeError(f"approved source identity changed: {relative}")
                allowed = allowed_records[relative]
                if allowed.get("source_sha256") != expected_sha:
                    raise SourceScopeError(f"allowlist source hash mismatch: {relative}")
                disposition = str(allowed.get("byte_disposition") or "")
                if disposition not in {
                    "unchanged-from-original-stop-a",
                    "approved-redacted-copy",
                }:
                    raise SourceScopeError(f"unsupported byte disposition: {relative}")
                records.append(ApprovedSource(relative, actual_sha, disposition))

            if _walk_tree_at(source_descriptor, field="source root") != source_nodes:
                raise SourceScopeError("source tree identity changed during validation")
            for held in held_governance_files:
                _assert_held_scope_path(governance_descriptor, held)
                payload = _read_held_scope_file(held)
                if hashlib.sha256(payload).hexdigest() != held.sha256:
                    raise SourceScopeError(
                        f"governance artifact hash changed: {held.relative_path}"
                    )
            _assert_root_binding(
                source_root,
                source_descriptor,
                source_root_identity,
                "approved source root",
            )
            _assert_root_binding(
                governance_root,
                governance_descriptor,
                governance_root_identity,
                "governance root",
            )
            loaded_state = _LoadedScopeState(
                source_root_identity=source_root_identity,
                governance_root_identity=governance_root_identity,
                source_nodes=source_nodes,
                source_root_descriptor=source_descriptor,
                governance_root_descriptor=governance_descriptor,
                source_files=tuple(held_source_files),
                governance_files=tuple(held_governance_files),
            )
            result = cls(
                source_root=source_root,
                governance_root=governance_root,
                records=tuple(records),
                source_manifest_sha256=EXPECTED_SOURCE_MANIFEST_SHA256,
                allowlist_sha256=EXPECTED_ALLOWLIST_SHA256,
                stop_a_receipt_sha256=EXPECTED_STOP_A_RECEIPT_SHA256,
                source_dlp_receipt_sha256=EXPECTED_SOURCE_DLP_RECEIPT_SHA256,
                approval_recorded_at=str(receipt["recorded_at"]),
                _loaded_state=loaded_state,
            )
            keep_descriptors = True
        finally:
            if not keep_descriptors:
                for held in reversed(
                    (*held_source_files, *held_governance_files)
                ):
                    try:
                        held.close()
                    except BaseException:
                        pass
                for descriptor in (governance_descriptor, source_descriptor):
                    try:
                        os.close(descriptor)
                    except BaseException:
                        pass

        if result is None:
            raise SourceScopeError("approved source scope could not be retained")
        return result

    @staticmethod
    def _parse_manifest_bytes(payload: bytes) -> dict[str, str]:
        try:
            lines = payload.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise SourceScopeError("invalid source manifest encoding") from exc
        records: dict[str, str] = {}
        for line_number, line in enumerate(lines, 1):
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if not match:
                raise SourceScopeError(f"invalid source manifest line: {line_number}")
            digest, raw_relative = match.groups()
            relative = canonical_relative_path(raw_relative)
            if relative in records:
                raise SourceScopeError(f"duplicate source manifest path: {relative}")
            records[relative] = digest
        if len(records) != EXPECTED_SOURCE_COUNT:
            raise SourceScopeError("source manifest must contain exactly 35 records")
        return records

    @staticmethod
    def _validate_governance(
        allowlist: Any,
        receipt: Any,
        source_paths: Any,
        manifest: dict[str, str],
    ) -> None:
        if not isinstance(allowlist, dict) or not isinstance(receipt, dict):
            raise SourceScopeError("governance artifacts must be JSON objects")
        if type(source_paths) is not list:
            raise SourceScopeError("SOURCE_PATHS must be a JSON array")
        if allowlist.get("candidate_id") != CANDIDATE_ID:
            raise SourceScopeError("allowlist candidate identity mismatch")
        if allowlist.get("status") != "stop-a-revision-approved":
            raise SourceScopeError("source allowlist is not Stop A approved")
        if receipt.get("status") != "stop_a_revision_approved":
            raise SourceScopeError("Stop A approval receipt is not approved")
        scope = allowlist.get("scope") or {}
        if scope.get("source_count") != EXPECTED_SOURCE_COUNT:
            raise SourceScopeError("allowlist source count mismatch")
        if scope.get("unchanged_byte_identical_count") != 28:
            raise SourceScopeError("unchanged-byte count mismatch")
        if scope.get("approved_redacted_count") != 7:
            raise SourceScopeError("approved-redacted count mismatch")
        authority = allowlist.get("authority") or {}
        if not authority.get("usable_for_source_scoped_local_build"):
            raise SourceScopeError("source-scoped local build is not authorized")
        if authority.get("usable_for_embedding_or_vector_build"):
            raise SourceScopeError("old authority unexpectedly authorizes vector build")
        permissions = allowlist.get("authorization") or {}
        required_true = ("local_isolated_implementation", "local_dlp_testing", "fake_provider_testing")
        forbidden_true = (
            "real_provider_api_calls",
            "real_embedding_build",
            "real_vector_store_build",
            "commit",
            "push",
            "app_upload",
            "data_upload",
            "release",
            "deployment",
        )
        if not all(permissions.get(key) is True for key in required_true):
            raise SourceScopeError("required local authorization is absent")
        if any(permissions.get(key) is not False for key in forbidden_true):
            raise SourceScopeError("a forbidden external operation is not explicitly false")
        paths = [canonical_relative_path(value) for value in source_paths]
        if paths != list(manifest):
            raise SourceScopeError("SOURCE_PATHS order or membership differs from the manifest")
        sources = allowlist.get("sources")
        if not isinstance(sources, list) or len(sources) != EXPECTED_SOURCE_COUNT:
            raise SourceScopeError("allowlist source records are incomplete")
        allowlist_paths = [canonical_relative_path(item.get("relative_path")) for item in sources]
        if allowlist_paths != list(manifest):
            raise SourceScopeError("allowlist source order or membership differs from the manifest")
        bindings = receipt.get("bindings") or {}
        expected = {
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "cloud_source_allowlist_sha256": EXPECTED_ALLOWLIST_SHA256,
            "source_paths_sha256": EXPECTED_SOURCE_PATHS_SHA256,
            "source_dlp_receipt_sha256": EXPECTED_SOURCE_DLP_RECEIPT_SHA256,
        }
        if any(bindings.get(key) != value for key, value in expected.items()):
            raise SourceScopeError("Stop A receipt does not bind the approved source artifacts")

    def _validate_source_tree(
        self,
        source_descriptor: int,
        source_root: Path,
        source_root_identity: _NodeIdentity,
    ) -> tuple[_TreeNode, ...]:
        state = self._require_loaded_state()
        if (
            source_descriptor != state.source_root_descriptor
            or source_root != self.source_root
            or source_root_identity != state.source_root_identity
        ):
            raise SourceScopeError("approved source root held descriptor binding changed")
        expected_nodes = state.source_nodes
        current_nodes = _walk_tree_at(source_descriptor, field="source root")
        if current_nodes != expected_nodes:
            raise SourceScopeError("source tree identity changed")
        discovered = {
            node.relative_path for node in current_nodes if node.kind == "file"
        }
        if discovered != {record.relative_path for record in self.records}:
            raise SourceScopeError("source root contains missing or unapproved paths")
        _assert_root_binding(
            source_root,
            source_descriptor,
            source_root_identity,
            "approved source root",
        )
        return current_nodes

    def _require_loaded_state(self) -> _LoadedScopeState:
        state = self._loaded_state
        if state is None:
            raise SourceScopeError(
                "approved source scope must be created by ApprovedSourceScope.load"
            )
        if state.closed:
            raise SourceScopeError("approved source scope held descriptors are closed")
        return state

    def read_source_bytes(self, record: ApprovedSource) -> bytes:
        if record not in self.records:
            raise SourceScopeError("source record is outside the approved scope")
        state = self._require_loaded_state()
        source_nodes = self._validate_source_tree(
            state.source_root_descriptor,
            self.source_root,
            state.source_root_identity,
        )
        held_files = {held.relative_path: held for held in state.source_files}
        held = held_files.get(record.relative_path)
        if (
            held is None
            or held.sha256 != record.source_sha256
            or held.identity
            != next(
                node.identity
                for node in source_nodes
                if node.kind == "file" and node.relative_path == record.relative_path
            )
        ):
            raise SourceScopeError("approved source held descriptor binding changed")
        _assert_held_scope_path(state.source_root_descriptor, held)
        payload = _read_held_scope_file(held)
        if _walk_tree_at(state.source_root_descriptor, field="source root") != source_nodes:
            raise SourceScopeError("source tree identity changed while reading")
        _assert_root_binding(
            self.source_root,
            state.source_root_descriptor,
            state.source_root_identity,
            "approved source root",
        )
        return payload

    def revalidate(self) -> None:
        state = self._require_loaded_state()
        source_nodes = self._validate_source_tree(
            state.source_root_descriptor,
            self.source_root,
            state.source_root_identity,
        )
        identities = {
            node.relative_path: node.identity
            for node in source_nodes
            if node.kind == "file"
        }
        held_files = {held.relative_path: held for held in state.source_files}
        if set(held_files) != {record.relative_path for record in self.records}:
            raise SourceScopeError("approved source held descriptor closure changed")
        for record in self.records:
            held = held_files[record.relative_path]
            if (
                held.sha256 != record.source_sha256
                or held.identity != identities[record.relative_path]
            ):
                raise SourceScopeError("approved source held descriptor binding changed")
            _assert_held_scope_path(state.source_root_descriptor, held)
            payload = _read_held_scope_file(held)
            if hashlib.sha256(payload).hexdigest() != record.source_sha256:
                raise SourceScopeError(
                    f"approved source hash changed: {record.relative_path}"
                )
        if _walk_tree_at(state.source_root_descriptor, field="source root") != source_nodes:
            raise SourceScopeError("source tree identity changed during revalidation")
        _assert_root_binding(
            self.source_root,
            state.source_root_descriptor,
            state.source_root_identity,
            "approved source root",
        )
        for held in state.governance_files:
            _read_held_scope_file(held)
            _assert_held_scope_path(state.governance_root_descriptor, held)
        _assert_root_binding(
            self.governance_root,
            state.governance_root_descriptor,
            state.governance_root_identity,
            "governance root",
        )

    def close(self) -> None:
        state = self._loaded_state
        if state is None or state.closed:
            return
        state.close()

    def __enter__(self) -> "ApprovedSourceScope":
        self._require_loaded_state()
        return self

    def __exit__(
        self, exc_type: object, exc_value: object, traceback: object
    ) -> None:
        try:
            self.revalidate()
        finally:
            self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass

    def identity(self) -> dict[str, Any]:
        self._require_loaded_state()
        return {
            "schema_version": SCOPE_SCHEMA_VERSION,
            "candidate_id": CANDIDATE_ID,
            "source_count": len(self.records),
            "source_manifest_sha256": self.source_manifest_sha256,
            "allowlist_sha256": self.allowlist_sha256,
            "stop_a_receipt_sha256": self.stop_a_receipt_sha256,
            "source_dlp_receipt_sha256": self.source_dlp_receipt_sha256,
            "unchanged_source_count": sum(
                r.byte_disposition == "unchanged-from-original-stop-a" for r in self.records
            ),
            "approved_redacted_source_count": sum(
                r.byte_disposition == "approved-redacted-copy" for r in self.records
            ),
        }
