#!/usr/bin/env python3
"""Build and verify the sealed, zero-provider-call Stop B review handoff."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.stderr.write("formal Stop B handoff CLI bootstrap context is required\n")
    raise SystemExit(2)

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import types
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

from .artifact_builder import ArtifactBuildError, verify_app_package, verify_suite
from .authority_builder import canonical_json_bytes
from .dlp import (
    DLP_RULESET_VERSION,
    DLPError,
    DLPScanner,
    _open_held_payload,
    _positive_canary_receipt,
    _revalidate_held_payload,
    _ruleset_sha256,
    _scan_inventory,
    _scanner_contract,
    _tree_inventory,
    validate_phase1_dlp_receipt,
)
from .offline_evidence import (
    OfflineEvidenceError,
    TEST_COMPONENT_SET_SCHEMA_VERSION,
    TEST_RECEIPT_SCHEMA_VERSION,
    _require_formal_bootstrap_context,
    _require_isolated_python,
    run_formal_validation,
)
from .source_scope import ApprovedSourceScope, SourceScopeError
from .stop_b_request import (
    DERIVED_CANDIDATE_ROOT,
    PRODUCTION_DATA_FILES,
    PRODUCTION_DATA_FILE_SET_SHA256,
    REQUIRED_PHASE1_EVIDENCE_LABELS,
    StopBRequestError,
    load_stop_b_request,
)


HANDOFF_MANIFEST_SCHEMA_VERSION = "cloud-v2-stop-b-handoff-manifest-v1"
HANDOFF_RECEIPT_SCHEMA_VERSION = "cloud-v2-stop-b-handoff-receipt-v1"
FROZEN_FILE_MODE = 0o440
FORMAL_EVIDENCE_FILE_MODE = 0o400
FROZEN_DIRECTORY_MODE = 0o550
STAGING_FILE_MODE = 0o640
HANDOFF_DLP_SCHEMA_VERSION = "cloud-v2-stop-b-handoff-dlp-v1"
APP_VERIFICATION_EVIDENCE_SCHEMA_VERSION = (
    "cloud-v2-app-package-verification-evidence-v1"
)
CODE_VERIFICATION_EVIDENCE_SCHEMA_VERSION = "kg-cloud-package-verification-evidence-v1"
MATERIALS_NAME = "MATERIALS.sha256"
MANIFEST_NAME = "HANDOFF_MANIFEST.json"
REQUEST_NAME = "STOP_B_EXTERNAL_PROCESSING_REQUEST.json"
SUITE_RELATIVE = "knowledge-qa-suite-release"
EVIDENCE_RELATIVE = "phase1-evidence"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SYSTEM_PATH_ALIAS_TARGETS = {
    Path("/var"): Path("/private/var"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/etc"): Path("/private/etc"),
}
_SUPERSEDED_OFFLINE_EVIDENCE_SCHEMAS = {
    "cloud-v2-offline-test-component-set-v1",
    "cloud-v2-offline-test-component-set-v2",
    "cloud-v2-offline-test-component-set-v3",
    "cloud-v2-offline-test-component-set-v4",
    "cloud-v2-offline-test-component-set-v5",
    "cloud-v2-offline-test-component-set-v6",
    "cloud-v2-offline-test-component-set-v7",
    "cloud-v2-offline-test-receipt-v1",
    "cloud-v2-offline-test-receipt-v2",
    "cloud-v2-offline-test-receipt-v3",
    "cloud-v2-offline-test-receipt-v4",
    "cloud-v2-offline-test-receipt-v5",
    "cloud-v2-offline-test-receipt-v6",
    "cloud-v2-offline-test-receipt-v7",
}

_PHASE_STATE = {
    "stop_a": "approved",
    "stop_b": "pending",
    "stop_c": "pending",
    "stop_d": "pending",
    "real_provider_calls": 0,
    "commit_push_upload_deploy_authorized": False,
    "runtime_activation_authorized": False,
    "product_accepted": False,
}

_EVIDENCE_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (
        "app-package-receipt",
        "file",
        "phase1-evidence/app-package-receipt.json",
        "cloud-v2-app-package-receipt-v1",
    ),
    (
        "app-package-verification",
        "file",
        "phase1-evidence/app-package-verification.json",
        APP_VERIFICATION_EVIDENCE_SCHEMA_VERSION,
    ),
    (
        "code-manifest-verification",
        "file",
        "phase1-evidence/code-manifest-verification.json",
        CODE_VERIFICATION_EVIDENCE_SCHEMA_VERSION,
    ),
    (
        "disclosure-evidence",
        "file",
        "phase1-evidence/disclosure-evidence.json",
        "cloud-v2-offline-disclosure-evidence-v1",
    ),
    (
        "final-suite-dlp-receipt",
        "file",
        "phase1-evidence/final-suite-dlp-receipt.json",
        "cloud-v2-final-suite-dlp-receipt-v2",
    ),
    (
        "offline-test-component-set",
        "file",
        "phase1-evidence/offline-tests/offline-test-component-set.json",
        TEST_COMPONENT_SET_SCHEMA_VERSION,
    ),
    (
        "offline-test-logs",
        "directory_file_set",
        "phase1-evidence/offline-tests/logs",
        "cloud-v2-offline-test-log-file-set-v1",
    ),
    (
        "offline-test-receipt",
        "file",
        "phase1-evidence/offline-tests/offline-test-receipt.json",
        TEST_RECEIPT_SCHEMA_VERSION,
    ),
    (
        "phase1-dlp-receipt",
        "file",
        "phase1-evidence/phase1-dlp-receipt.json",
        "cloud-v2-dlp-receipt-v3",
    ),
    (
        "suite-build-receipt",
        "file",
        "phase1-evidence/suite-build-receipt.json",
        "cloud-v2-suite-build-receipt-v2",
    ),
    (
        "suite-verification",
        "file",
        "phase1-evidence/suite-verification.json",
        "cloud-v2-suite-verification-v2",
    ),
)

_FORMAL_OFFLINE_EVIDENCE_FILES = frozenset(
    {
        "phase1-evidence/disclosure-evidence.json",
        "phase1-evidence/offline-tests/offline-test-component-set.json",
        "phase1-evidence/offline-tests/offline-test-receipt.json",
        (
            "knowledge-qa-suite-release/server-runtime/evidence/"
            "disclosure-evidence.json"
        ),
        (
            "knowledge-qa-suite-release/server-runtime/evidence/"
            "offline-test-component-set.json"
        ),
        (
            "knowledge-qa-suite-release/server-runtime/evidence/"
            "offline-test-receipt.json"
        ),
    }
)
_FORMAL_OFFLINE_EVIDENCE_PREFIXES = (
    "phase1-evidence/offline-tests/logs/",
    "knowledge-qa-suite-release/server-runtime/evidence/logs/",
)


class HandoffError(RuntimeError):
    """A handoff input, binding, scan, or publication failed closed."""

    def __init__(self, message: str, *, code: str = "handoff-validation-error") -> None:
        super().__init__(message)
        self.code = code


_FORMAL_STOP_B_HANDOFF_SOURCE_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)
_EXECUTED_STOP_B_HANDOFF_SOURCE = _open_held_payload(
    Path(__file__),
    "Stop B handoff source",
    max_bytes=4 * 1024 * 1024,
)
_FORMAL_STOP_B_HANDOFF_SOURCE_SHA256: str | None = None
_FORMAL_STOP_B_HANDOFF_SOURCE_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_STOP_B_HANDOFF_ACTION_CLOSURE: tuple[object, ...] | None = None


def _stop_b_handoff_source_state_identity() -> dict[str, int]:
    state = _EXECUTED_STOP_B_HANDOFF_SOURCE.file_state
    return {
        "device": state.device,
        "inode": state.inode,
        "mode": state.mode,
        "nlink": state.link_count,
        "size": state.size,
        "mtime_ns": state.mtime_ns,
        "ctime_ns": state.ctime_ns,
    }


def _current_stop_b_handoff_action_closure() -> tuple[object, ...]:
    return (
        _parser,
        build_app_verification_evidence,
        build_code_manifest_verification_evidence,
        build_stop_b_handoff,
        verify_stop_b_handoff,
        _build_app_verification_evidence_impl,
        _build_code_manifest_verification_evidence_impl,
        _build_stop_b_handoff_impl,
        _verify_stop_b_handoff_impl,
    )


def _install_formal_stop_b_handoff_bootstrap_context(
    binding: Mapping[str, Any],
) -> None:
    global _FORMAL_STOP_B_HANDOFF_ACTION_CLOSURE
    global _FORMAL_STOP_B_HANDOFF_SOURCE_SHA256
    global _FORMAL_STOP_B_HANDOFF_SOURCE_STATE_IDENTITY

    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except OfflineEvidenceError as exc:
        raise HandoffError(
            "formal Stop B handoff CLI bootstrap context is required"
        ) from exc
    required = {*_FORMAL_STOP_B_HANDOFF_SOURCE_STATE_FIELDS, "sha256"}
    if (
        not isinstance(binding, Mapping)
        or set(binding) != required
        or not isinstance(binding.get("sha256"), str)
        or not SHA256_PATTERN.fullmatch(str(binding["sha256"]))
        or any(
            type(binding.get(field)) is not int or int(binding[field]) < 0
            for field in _FORMAL_STOP_B_HANDOFF_SOURCE_STATE_FIELDS
        )
        or binding["inode"] == 0
        or binding["nlink"] != 1
        or not stat.S_ISREG(binding["mode"])
    ):
        raise HandoffError(
            "formal Stop B handoff CLI source binding is malformed"
        )
    expected_state = {
        field: int(binding[field])
        for field in _FORMAL_STOP_B_HANDOFF_SOURCE_STATE_FIELDS
    }
    try:
        _revalidate_held_payload(_EXECUTED_STOP_B_HANDOFF_SOURCE)
    except DLPError as exc:
        raise HandoffError(
            "formal Stop B handoff CLI source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_STOP_B_HANDOFF_SOURCE.payload).hexdigest()
        != binding["sha256"]
        or _stop_b_handoff_source_state_identity() != expected_state
    ):
        raise HandoffError(
            "formal Stop B handoff CLI source differs from held bootstrap bytes"
        )
    _FORMAL_STOP_B_HANDOFF_SOURCE_SHA256 = str(binding["sha256"])
    _FORMAL_STOP_B_HANDOFF_SOURCE_STATE_IDENTITY = expected_state
    _FORMAL_STOP_B_HANDOFF_ACTION_CLOSURE = (
        _current_stop_b_handoff_action_closure()
    )


def _require_formal_stop_b_handoff_bootstrap_context() -> tuple[object, ...]:
    source_sha256 = _FORMAL_STOP_B_HANDOFF_SOURCE_SHA256
    source_state = _FORMAL_STOP_B_HANDOFF_SOURCE_STATE_IDENTITY
    actions = _FORMAL_STOP_B_HANDOFF_ACTION_CLOSURE
    if (
        not isinstance(source_sha256, str)
        or not SHA256_PATTERN.fullmatch(source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_FORMAL_STOP_B_HANDOFF_SOURCE_STATE_FIELDS)
        or any(
            type(source_state.get(field)) is not int or int(source_state[field]) < 0
            for field in _FORMAL_STOP_B_HANDOFF_SOURCE_STATE_FIELDS
        )
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
        or not isinstance(actions, tuple)
        or len(actions) != 9
    ):
        raise HandoffError(
            "formal Stop B handoff CLI bootstrap context is required"
        )
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
        _revalidate_held_payload(_EXECUTED_STOP_B_HANDOFF_SOURCE)
    except (OfflineEvidenceError, DLPError) as exc:
        raise HandoffError(
            "formal Stop B handoff CLI source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_STOP_B_HANDOFF_SOURCE.payload).hexdigest()
        != source_sha256
        or _stop_b_handoff_source_state_identity() != dict(source_state)
        or any(
            current is not expected
            for current, expected in zip(
                _current_stop_b_handoff_action_closure(),
                actions,
                strict=True,
            )
        )
    ):
        raise HandoffError(
            "formal Stop B handoff CLI source or action closure changed"
        )
    return actions


@dataclass(frozen=True)
class _HeldTreeFile:
    relative_path: str
    sha256: str
    state: os.stat_result
    descriptor: int
    sealed_mode: int
    directory_paths: tuple[str, ...] = ()
    # Directory identities are kept separately from regular-file identities.
    # A producer can otherwise move a populated child directory away, create a
    # replacement at the same path, and move the original file inodes back.
    # File-path checks alone would accept that replacement.
    directory_states: tuple[tuple[str, tuple[int, ...]], ...] = ()


def _is_formal_offline_evidence_path(relative_path: str) -> bool:
    relative = _canonical_relative(relative_path, "handoff file mode path")
    return relative in _FORMAL_OFFLINE_EVIDENCE_FILES or any(
        relative.startswith(prefix) and len(relative) > len(prefix)
        for prefix in _FORMAL_OFFLINE_EVIDENCE_PREFIXES
    )


def _staging_file_mode(relative_path: str) -> int:
    return (
        FORMAL_EVIDENCE_FILE_MODE
        if _is_formal_offline_evidence_path(relative_path)
        else STAGING_FILE_MODE
    )


def _sealed_file_mode(relative_path: str) -> int:
    return (
        FORMAL_EVIDENCE_FILE_MODE
        if _is_formal_offline_evidence_path(relative_path)
        else FROZEN_FILE_MODE
    )


@dataclass(frozen=True)
class _DetachedInode:
    """A pre-refresh inode retained as a mutation sentinel."""

    descriptor: int
    state: os.stat_result
    sha256: str
    label: str


def _safe_sha256_file(path: Path, label: str = "file") -> str:
    """Normalize filesystem hash failures to the handoff error contract."""

    try:
        return sha256_file(path)
    except (OSError, ValueError) as exc:
        raise HandoffError(f"{label} could not be hashed safely") from exc


def _has_control_character(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


_FORBIDDEN_PATH_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})


def _validate_path_unicode(value: str, label: str) -> None:
    """Require one stable, encodable spelling for a filesystem path."""

    if unicodedata.normalize("NFC", value) != value:
        raise HandoffError(f"{label} is not NFC-normalized")
    if any(
        unicodedata.category(character) in _FORBIDDEN_PATH_UNICODE_CATEGORIES
        for character in value
    ):
        raise HandoffError(f"{label} contains forbidden Unicode path characters")


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_relative(value: object, label: str = "path") -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise HandoffError(f"{label} must be a non-empty relative path")
    _validate_path_unicode(value, label)
    if (
        "\\" in value
        or "//" in value
        or _has_control_character(value)
    ):
        raise HandoffError(f"{label} is not canonical POSIX")
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise HandoffError(f"{label} contains a normalized component")
    return value


def _strict_json_bytes(payload: bytes, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise HandoffError(f"duplicate JSON key in {label}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                HandoffError(f"non-finite JSON value in {label}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError(f"invalid JSON in {label}") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"{label} must contain a JSON object")
    return value


def _strict_json(path: Path, *, canonical: bool = False) -> Mapping[str, Any]:
    payload = _read_regular_bytes(path, "JSON input")
    value = _strict_json_bytes(payload, path.name)
    if canonical and payload != canonical_json_bytes(value):
        raise HandoffError(f"{path.name} is not canonical JSON")
    return value


def _absolute_path(path: Path, label: str) -> Path:
    raw = os.fspath(path)
    if (
        not isinstance(raw, str)
        or not raw
        or "\\" in raw
        or _has_control_character(raw)
    ):
        raise HandoffError(f"{label} path is invalid")
    _validate_path_unicode(raw, label)
    if raw.startswith("//") or "//" in raw:
        raise HandoffError(f"{label} path is invalid")
    components = raw.split(os.sep)
    if any(part in {".", ".."} for part in components):
        raise HandoffError(f"{label} path contains a dot component")
    normalized = os.path.normpath(raw)
    if normalized.startswith("//"):
        raise HandoffError(f"{label} path is not canonical")
    absolute = Path(os.path.abspath(normalized))
    if sys.platform == "darwin":
        for alias, target in _SYSTEM_PATH_ALIAS_TARGETS.items():
            try:
                relative = absolute.relative_to(alias)
            except ValueError:
                continue
            return target / relative
    return absolute


def _reject_component_alias(parent_fd: int, component: str, label: str) -> None:
    """Reject a spelling that the filesystem resolves as a name alias.

    On case-insensitive or Unicode-normalizing volumes, ``openat`` can resolve
    a different directory entry than the spelling recorded in a manifest.  A
    sealed handoff must use the exact directory-entry spelling; accepting an
    alias would make overlap and identity checks depend on the host filesystem.
    """

    try:
        entries = os.listdir(parent_fd)
    except OSError as exc:
        raise HandoffError(f"{label} parent directory could not be inspected safely") from exc
    # Reject collisions in the *whole* parent directory, even when the
    # requested spelling itself exists.  On a case-sensitive volume both
    # ``A`` and ``a`` can coexist, but that tree is ambiguous when moved to a
    # case-insensitive or Unicode-normalizing volume.  Checking only a missing
    # requested name (the old behavior) let the second spelling pass.
    folded_entries: dict[str, list[str]] = {}
    for entry in entries:
        folded = unicodedata.normalize("NFC", entry).casefold()
        folded_entries.setdefault(folded, []).append(entry)
    if any(len(aliases) > 1 for aliases in folded_entries.values()):
        raise HandoffError(
            f"{label} parent contains a case or Unicode-normalization collision"
        )
    if component in entries:
        return
    folded = unicodedata.normalize("NFC", component).casefold()
    if folded in folded_entries:
        raise HandoffError(f"{label} uses a case or Unicode-normalization alias")


def _open_directory_fd(
    path: Path,
    label: str,
    *,
    create: bool = False,
    mode: int = 0o750,
) -> tuple[Path, int]:
    absolute = _absolute_path(path, label)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open("/", flags)
    try:
        for component in absolute.parts[1:]:
            _reject_component_alias(descriptor, component, label)
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise HandoffError(f"{label} does not exist") from None
                try:
                    os.mkdir(component, mode=mode, dir_fd=descriptor)
                except FileExistsError:
                    pass
                try:
                    child = os.open(component, flags, dir_fd=descriptor)
                except OSError as exc:
                    raise HandoffError(f"{label} could not be created safely") from exc
            except OSError as exc:
                raise HandoffError(f"{label} contains a symlink or non-directory component") from exc
            os.close(descriptor)
            descriptor = child
        state = os.fstat(descriptor)
        if not stat.S_ISDIR(state.st_mode):
            raise HandoffError(f"{label} must be a real directory")
        return absolute, descriptor
    except Exception:
        os.close(descriptor)
        raise


def _parent_fd(path: Path, label: str, *, create: bool = False) -> tuple[Path, str, int]:
    absolute = _absolute_path(path, label)
    if absolute == Path("/"):
        raise HandoffError(f"{label} must not be the filesystem root")
    parent, descriptor = _open_directory_fd(
        absolute.parent,
        f"{label} parent",
        create=create,
    )
    return parent / absolute.name, absolute.name, descriptor


def _open_relative_directory_fd(
    root_fd: int,
    relative: str,
    label: str,
    *,
    create: bool = False,
    mode: int = 0o750,
) -> int:
    """Open a directory below a held descriptor without resolving its path."""

    if relative in {"", "."}:
        try:
            return os.dup(root_fd)
        except OSError as exc:
            raise HandoffError(f"{label} could not be duplicated safely") from exc
    canonical = _canonical_relative(relative, label)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        descriptor = os.dup(root_fd)
    except OSError as exc:
        raise HandoffError(f"{label} could not be opened safely") from exc
    try:
        for component in PurePosixPath(canonical).parts:
            _reject_component_alias(descriptor, component, label)
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise HandoffError(f"{label} does not exist") from None
                try:
                    os.mkdir(component, mode=mode, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as exc:
                raise HandoffError(
                    f"{label} contains a symlink or non-directory component"
                ) from exc
            os.close(descriptor)
            descriptor = child
        state = os.fstat(descriptor)
        if not stat.S_ISDIR(state.st_mode):
            raise HandoffError(f"{label} must be a real directory")
        return descriptor
    except HandoffError:
        os.close(descriptor)
        raise
    except OSError as exc:
        os.close(descriptor)
        raise HandoffError(f"{label} could not be opened safely") from exc


def _open_relative_parent_fd(
    root_fd: int,
    relative_path: str,
    label: str,
    *,
    create: bool = False,
    mode: int = 0o750,
) -> tuple[str, int]:
    relative = _canonical_relative(relative_path, label)
    path = PurePosixPath(relative)
    parent = "" if path.parent == PurePosixPath(".") else path.parent.as_posix()
    parent_fd = _open_relative_directory_fd(
        root_fd,
        parent,
        f"{label} parent",
        create=create,
        mode=mode,
    )
    return path.name, parent_fd


def _mkdir_new_at(root_fd: int, relative_path: str, *, mode: int) -> None:
    name, parent_fd = _open_relative_parent_fd(
        root_fd,
        relative_path,
        "new handoff directory",
    )
    try:
        os.mkdir(name, mode=mode, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError as exc:
        raise HandoffError("handoff staging path unexpectedly exists") from exc
    except OSError as exc:
        raise HandoffError(
            "handoff staging directory could not be created safely"
        ) from exc
    finally:
        os.close(parent_fd)


def _write_new_at(
    root_fd: int,
    relative_path: str,
    payload: bytes,
    *,
    mode: int = 0o640,
) -> None:
    name, parent_fd = _open_relative_parent_fd(
        root_fd,
        relative_path,
        "handoff output",
        create=False,
    )
    descriptor: int | None = None
    created: os.stat_result | None = None
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_fd,
        )
        created = os.fstat(descriptor)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise HandoffError("handoff output write was incomplete")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        _unlink_if_same_inode(parent_fd, name, created)
        raise HandoffError("handoff output write failed safely") from exc
    except BaseException:
        _unlink_if_same_inode(parent_fd, name, created)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _copy_file_bound(
    source: Path,
    destination_root_fd: int,
    destination_root: Path,
    relative_path: str,
    *,
    mode: int = STAGING_FILE_MODE,
) -> str:
    relative = _canonical_relative(relative_path, "handoff destination")
    name, parent_fd = _open_relative_parent_fd(
        destination_root_fd,
        relative,
        "handoff destination",
        create=True,
    )
    try:
        return _copy_file(
            source,
            destination_root / Path(relative),
            _destination_parent_fd=parent_fd,
            _destination_name=name,
            mode=mode,
        )
    finally:
        os.close(parent_fd)


def _lstat(path: Path, label: str) -> os.stat_result:
    _absolute, name, parent_fd = _parent_fd(path, label)
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise HandoffError(f"{label} cannot be inspected") from exc
    finally:
        os.close(parent_fd)


def _require_regular(path: Path, label: str) -> os.stat_result:
    _absolute, name, parent_fd = _parent_fd(path, label)
    descriptor: int | None = None
    try:
        state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode):
            raise HandoffError(f"{label} must be a regular unsymlinked file")
        if state.st_nlink != 1:
            raise HandoffError(f"{label} must not be hard-linked")
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(descriptor)
        if _state_identity(opened) != _state_identity(state):
            raise HandoffError(f"{label} changed while it was opened")
        return state
    except OSError as exc:
        raise HandoffError(f"{label} could not be opened without following links") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _require_directory(path: Path, label: str) -> Path:
    absolute, descriptor = _open_directory_fd(path, label)
    os.close(descriptor)
    return absolute


def _state_identity(state: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        state.st_dev,
        state.st_ino,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
        state.st_nlink,
    )


def _require_frozen_mode(
    state: os.stat_result,
    *,
    expected: int,
    label: str,
) -> None:
    if stat.S_IMODE(state.st_mode) != expected:
        raise HandoffError(f"{label} does not have sealed read-only permissions")


def _published_node_identity(state: os.stat_result) -> tuple[int, int, int, int, int]:
    """Identity fields that remain stable when a node is renamed."""

    return (
        state.st_dev,
        state.st_ino,
        stat.S_IFMT(state.st_mode),
        state.st_size,
        state.st_nlink,
    )


def _rollback_node_identity(state: os.stat_result) -> tuple[int, int, int]:
    """Identity used when moving an unchanged inode back during rollback."""

    return (state.st_dev, state.st_ino, stat.S_IFMT(state.st_mode))


def _node_binding_identity(state: os.stat_result) -> tuple[object, ...]:
    """Return mutable metadata that should agree for one held inode and name.

    ``st_dev``/``st_ino`` alone can be reused after an unlink.  A held
    descriptor pins the original object, so comparing the complete observable
    stat tuple (plus platform generation/birth fields when available) against
    the name makes a reused inode classify as foreign instead of owned.
    """

    return (
        state.st_dev,
        state.st_ino,
        stat.S_IFMT(state.st_mode),
        stat.S_IMODE(state.st_mode),
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
        state.st_nlink,
        getattr(state, "st_birthtime_ns", None),
        getattr(state, "st_gen", None),
    )


def _sha256_open_file(
    descriptor: int,
    *,
    expected_state: os.stat_result | None = None,
    allow_unlinked: bool = False,
    label: str,
) -> str:
    """Hash a held regular-file descriptor without changing its offset."""

    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (not allow_unlinked and before.st_nlink != 1)
            or (allow_unlinked and before.st_nlink > 1)
            or (
                expected_state is not None
                and _state_identity(before) != _state_identity(expected_state)
            )
        ):
            raise HandoffError(f"{label} is not the expected unique regular file")
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            block = os.pread(
                descriptor,
                min(1024 * 1024, before.st_size - offset),
                offset,
            )
            if not block:
                raise HandoffError(f"{label} became shorter while hashing")
            digest.update(block)
            offset += len(block)
        after = os.fstat(descriptor)
        if _state_identity(after) != _state_identity(before):
            raise HandoffError(f"{label} changed while hashing")
        return digest.hexdigest()
    except OSError as exc:
        raise HandoffError(f"{label} could not be hashed safely") from exc


def _read_open_file_bytes(
    descriptor: int,
    *,
    expected_state: os.stat_result | None = None,
    label: str,
) -> bytes:
    """Read a held regular-file descriptor and reject concurrent mutation."""

    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (
                expected_state is not None
                and _state_identity(before) != _state_identity(expected_state)
            )
        ):
            raise HandoffError(f"{label} is not the expected unique regular file")
        chunks: list[bytes] = []
        offset = 0
        while offset < before.st_size:
            block = os.pread(
                descriptor,
                min(1024 * 1024, before.st_size - offset),
                offset,
            )
            if not block:
                raise HandoffError(f"{label} became shorter while reading")
            chunks.append(block)
            offset += len(block)
        after = os.fstat(descriptor)
        if _state_identity(after) != _state_identity(before):
            raise HandoffError(f"{label} changed while reading")
        return b"".join(chunks)
    except OSError as exc:
        raise HandoffError(f"{label} could not be read safely") from exc


def _verify_named_open_file(
    *,
    parent_fd: int,
    name: str,
    descriptor: int,
    expected_inode: os.stat_result,
    expected_sha256: str,
    label: str,
) -> None:
    """Bind a published name to its held inode and content in two stat phases."""

    try:
        before_fd = os.fstat(descriptor)
        before_name = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        _require_frozen_mode(
            before_fd,
            expected=FROZEN_FILE_MODE,
            label=label,
        )
        _require_frozen_mode(
            before_name,
            expected=FROZEN_FILE_MODE,
            label=label,
        )
        if (
            not stat.S_ISREG(before_fd.st_mode)
            or before_fd.st_nlink != 1
            or _state_identity(before_name) != _state_identity(before_fd)
            or _published_node_identity(before_fd)
            != _published_node_identity(expected_inode)
        ):
            raise HandoffError(f"{label} is not bound to its sealed inode")
        if (
            _sha256_open_file(
                descriptor,
                expected_state=before_fd,
                label=label,
            )
            != expected_sha256
        ):
            raise HandoffError(f"{label} differs from its sealed payload")
        after_fd = os.fstat(descriptor)
        after_name = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _state_identity(after_fd) != _state_identity(before_fd)
            or _state_identity(after_name) != _state_identity(before_fd)
        ):
            raise HandoffError(f"{label} changed during verification")
    except OSError as exc:
        raise HandoffError(f"{label} could not be verified safely") from exc


def _rebind_named_open_file(
    *,
    parent_fd: int,
    name: str,
    descriptor: int,
    expected_state: os.stat_result,
    label: str,
) -> None:
    try:
        descriptor_state = os.fstat(descriptor)
        path_state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        _require_frozen_mode(
            descriptor_state,
            expected=FROZEN_FILE_MODE,
            label=label,
        )
        _require_frozen_mode(
            path_state,
            expected=FROZEN_FILE_MODE,
            label=label,
        )
        if (
            _state_identity(descriptor_state) != _state_identity(expected_state)
            or _state_identity(path_state) != _state_identity(expected_state)
        ):
            raise HandoffError(f"{label} changed after content verification")
    except OSError as exc:
        raise HandoffError(f"{label} could not be rebound safely") from exc


def _directory_inode_identity(state: os.stat_result) -> tuple[int, int, int]:
    return (state.st_dev, state.st_ino, stat.S_IFMT(state.st_mode))


def _directory_snapshot_identity(state: os.stat_result) -> tuple[int, ...]:
    """Return directory identity fields stable across a root rename.

    ``st_ctime_ns`` is deliberately omitted: renaming the published root can
    update its ctime on some filesystems even though the directory object and
    all of its entries are unchanged.  Device/inode/type, size, link count and
    mode still detect replacement, entry-set changes, and permission drift.
    """

    return (
        state.st_dev,
        state.st_ino,
        stat.S_IFMT(state.st_mode),
        state.st_size,
        state.st_nlink,
        stat.S_IMODE(state.st_mode),
    )


def _verify_named_open_directory(
    *,
    path: Path,
    descriptor: int,
    expected_inode: os.stat_result,
    label: str,
) -> None:
    """Require an absolute directory path to remain bound to its held FD."""

    current_fd: int | None = None
    try:
        held_state = os.fstat(descriptor)
        _absolute, current_fd = _open_directory_fd(path, label)
        path_state = os.fstat(current_fd)
        if (
            not stat.S_ISDIR(held_state.st_mode)
            or not stat.S_ISDIR(path_state.st_mode)
            or _directory_inode_identity(held_state)
            != _directory_inode_identity(expected_inode)
            or _directory_inode_identity(path_state)
            != _directory_inode_identity(held_state)
        ):
            raise HandoffError(f"{label} path is not bound to its sealed inode")
    except OSError as exc:
        raise HandoffError(f"{label} path could not be verified safely") from exc
    finally:
        if current_fd is not None:
            os.close(current_fd)


def _unlink_if_same_inode(
    parent_fd: int,
    name: str,
    expected: os.stat_result | None,
) -> None:
    if expected is None:
        return
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) == (expected.st_dev, expected.st_ino):
            os.unlink(name, dir_fd=parent_fd)
    except OSError:
        pass


def _read_regular_bytes(path: Path, label: str) -> bytes:
    _absolute, name, parent_fd = _parent_fd(path, label)
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise HandoffError(f"{label} must be a unique regular file")
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        if _state_identity(os.fstat(descriptor)) != _state_identity(before):
            raise HandoffError(f"{label} changed while it was opened")
        chunks: list[bytes] = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _state_identity(after) != _state_identity(before):
            raise HandoffError(f"{label} changed while it was read")
        return b"".join(chunks)
    except OSError as exc:
        raise HandoffError(f"{label} could not be read safely") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _read_regular_bytes_at(root_fd: int, relative_path: str, label: str) -> bytes:
    """Read one regular file below a held directory descriptor."""

    name, parent_fd = _open_relative_parent_fd(root_fd, relative_path, label)
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise HandoffError(f"{label} must be a unique regular file")
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        if _state_identity(os.fstat(descriptor)) != _state_identity(before):
            raise HandoffError(f"{label} changed while it was opened")
        payload = _read_open_file_bytes(
            descriptor,
            expected_state=before,
            label=label,
        )
        after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _state_identity(after) != _state_identity(before):
            raise HandoffError(f"{label} changed while it was read")
        return payload
    except OSError as exc:
        raise HandoffError(f"{label} could not be read safely") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(_read_regular_bytes(path, "hashed file")).hexdigest()


def _walk_error(error: OSError) -> None:
    raise HandoffError("handoff tree could not be traversed completely") from error


def _copy_file(
    source: Path,
    destination: Path,
    *,
    _destination_parent_fd: int | None = None,
    _destination_name: str | None = None,
    mode: int = STAGING_FILE_MODE,
) -> str:
    if mode not in {FORMAL_EVIDENCE_FILE_MODE, STAGING_FILE_MODE}:
        raise HandoffError("handoff destination file mode is not allowlisted")
    _source_absolute, source_name, source_parent_fd = _parent_fd(
        source,
        "handoff source",
    )
    destination_bound = _destination_parent_fd is not None
    try:
        if destination_bound:
            if (
                not isinstance(_destination_name, str)
                or not _destination_name
                or "/" in _destination_name
                or _destination_name in {".", ".."}
            ):
                raise HandoffError("handoff destination name is not canonical")
            _validate_path_unicode(_destination_name, "handoff destination")
            destination_absolute = destination
            destination_name = _destination_name
            # The caller retains ownership of its bound directory descriptor.
            destination_parent_fd = os.dup(_destination_parent_fd)
        else:
            destination_absolute, destination_name, destination_parent_fd = _parent_fd(
                destination,
                "handoff destination",
                create=True,
            )
    except Exception:
        os.close(source_parent_fd)
        raise
    source_fd: int | None = None
    destination_fd: int | None = None
    destination_created: os.stat_result | None = None
    try:
        before = os.stat(source_name, dir_fd=source_parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise HandoffError("handoff source must be a unique regular file")
        source_fd = os.open(
            source_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=source_parent_fd,
        )
    except HandoffError:
        os.close(source_parent_fd)
        os.close(destination_parent_fd)
        raise
    except OSError as exc:
        os.close(source_parent_fd)
        os.close(destination_parent_fd)
        raise HandoffError("handoff source could not be opened safely") from exc
    digest = hashlib.sha256()
    try:
        opened = os.fstat(source_fd)
        if _state_identity(opened) != _state_identity(before) or not stat.S_ISREG(opened.st_mode):
            raise HandoffError("handoff source changed before copying")
        destination_fd = os.open(
            destination_name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=destination_parent_fd,
        )
        destination_created = os.fstat(destination_fd)
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            view = memoryview(block)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise HandoffError("handoff destination write was incomplete")
                view = view[written:]
        os.fchmod(destination_fd, mode)
        os.fsync(destination_fd)
        after_fd = os.fstat(source_fd)
        after_path = os.stat(
            source_name,
            dir_fd=source_parent_fd,
            follow_symlinks=False,
        )
        copied = os.fstat(destination_fd)
        if (
            _state_identity(after_fd) != _state_identity(before)
            or _state_identity(after_path) != _state_identity(before)
        ):
            raise HandoffError("handoff source changed while copying")
        if (
            not stat.S_ISREG(copied.st_mode)
            or copied.st_nlink != 1
            or copied.st_size != before.st_size
            or stat.S_IMODE(copied.st_mode) != mode
        ):
            raise HandoffError("handoff copy metadata differs from its source snapshot")
        copied_digest = _sha256_open_file(
            destination_fd,
            expected_state=copied,
            label="handoff copied file",
        )
    except OSError as exc:
        if destination_fd is not None:
            os.close(destination_fd)
            destination_fd = None
        _unlink_if_same_inode(
            destination_parent_fd,
            destination_name,
            destination_created,
        )
        raise HandoffError("handoff file copy failed safely") from exc
    except Exception:
        if destination_fd is not None:
            os.close(destination_fd)
            destination_fd = None
        _unlink_if_same_inode(
            destination_parent_fd,
            destination_name,
            destination_created,
        )
        raise
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
        if source_fd is not None:
            os.close(source_fd)
        os.close(source_parent_fd)
        os.close(destination_parent_fd)
    if copied_digest != digest.hexdigest():
        raise HandoffError("handoff copy differs from its source snapshot")
    return digest.hexdigest()


def _walk_regular(root: Path) -> list[Path]:
    absolute, root_fd = _open_directory_fd(root, "handoff tree")
    expected_root_state = os.fstat(root_fd)
    records: list[tuple[str, os.stat_result]] = []
    try:
        for current, directories, names, current_fd in os.fwalk(
            ".",
            topdown=True,
            follow_symlinks=False,
            dir_fd=root_fd,
        ):
            relative_parent = "" if current == "." else current.removeprefix("./")
            if relative_parent:
                _canonical_relative(relative_parent, "tree directory")
            current_state = os.fstat(current_fd)
            if stat.S_ISLNK(current_state.st_mode) or not stat.S_ISDIR(
                current_state.st_mode
            ):
                raise HandoffError("handoff tree contains a symlink or special directory")
            directories.sort()
            names.sort()
            for name in directories:
                _reject_component_alias(current_fd, name, "handoff tree directory")
                state = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
                if stat.S_ISLNK(state.st_mode) or not stat.S_ISDIR(state.st_mode):
                    raise HandoffError(
                        "handoff tree contains a symlink or special directory"
                    )
                relative = f"{relative_parent}/{name}" if relative_parent else name
                _canonical_relative(relative, "tree directory")
            for name in names:
                _reject_component_alias(current_fd, name, "handoff tree file")
                state = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
                if (
                    stat.S_ISLNK(state.st_mode)
                    or not stat.S_ISREG(state.st_mode)
                    or state.st_nlink != 1
                ):
                    raise HandoffError(
                        "handoff tree contains a symlink or special file"
                    )
                relative = f"{relative_parent}/{name}" if relative_parent else name
                _canonical_relative(relative, "tree file")
                records.append((relative, state))

        # Verify that the name used by the caller still denotes the directory
        # whose descriptor was traversed.  This catches a root rename/replace
        # between the initial open and the fwalk, including a replacement
        # symlink (which _open_directory_fd rejects).
        _verify_named_open_directory(
            path=absolute,
            descriptor=root_fd,
            expected_inode=expected_root_state,
            label="handoff tree",
        )
        records.sort(key=lambda item: item[0])
        return [absolute / Path(relative) for relative, _state in records]
    except (OSError, ValueError) as exc:
        raise HandoffError("handoff tree could not be traversed completely") from exc
    finally:
        os.close(root_fd)


def _source_tree_snapshot(root: Path) -> list[dict[str, object]]:
    root = _absolute_path(root, "handoff source tree")
    snapshot: list[dict[str, object]] = []
    for path in _walk_regular(root):
        state = _require_regular(path, "handoff source tree file")
        snapshot.append(
            {
                "path": path.relative_to(root).as_posix(),
                "state": _state_identity(state),
                "sha256": sha256_file(path),
            }
        )
    return snapshot


def _source_directory_paths(root: Path) -> tuple[str, ...]:
    """Return the complete source directory set, including empty branches.

    Directory entries are part of the sealed tree shape even though
    ``MATERIALS.sha256`` records regular files only.  In particular, the suite
    layout reserves empty authority/derived directories before their contents
    are populated; silently dropping those entries would make the copied tree
    differ from the source and would make a later directory-set check
    impossible.
    """

    # Use the same descriptor-relative walker as publication verification so a
    # source root cannot be swapped for an attacker-controlled tree between
    # directory enumeration steps.
    return _tree_directory_paths(root, require_frozen=False)


def _copy_tree(source: Path, destination: Path) -> None:
    source = _require_directory(source, "handoff source tree")
    source_directories = _source_directory_paths(source)
    destination_absolute, destination_name, destination_parent_fd = _parent_fd(
        destination,
        "handoff destination tree",
    )
    try:
        os.mkdir(destination_name, mode=0o750, dir_fd=destination_parent_fd)
    except FileExistsError as exc:
        raise HandoffError("handoff destination tree already exists") from exc
    except OSError as exc:
        raise HandoffError("handoff destination tree could not be created safely") from exc
    finally:
        os.close(destination_parent_fd)
    before = _source_tree_snapshot(source)
    # Preserve every source directory, including empty directories.  The
    # directory set is checked again after the copy below and at publication.
    for relative in source_directories:
        if not relative:
            continue
        _mkdir_new(destination_absolute / Path(relative), mode=0o750)
    for record in before:
        relative = Path(str(record["path"]))
        _copy_file(source / relative, destination_absolute / relative)
    after = _source_tree_snapshot(source)
    after_directories = _source_directory_paths(source)
    copied_directories = _source_directory_paths(destination_absolute)
    copied = [
        {
            "path": path.relative_to(destination_absolute).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in _walk_regular(destination_absolute)
    ]
    expected_copied = [
        {"path": str(record["path"]), "sha256": str(record["sha256"])}
        for record in before
    ]
    if (
        before != after
        or source_directories != after_directories
        or copied != expected_copied
        or copied_directories != source_directories
    ):
        raise HandoffError("handoff source tree changed while it was copied")


def _copy_tree_bound(
    source: Path,
    destination_root_fd: int,
    destination_root: Path,
    relative_root: str,
) -> None:
    """Copy a tree below a held destination descriptor.

    The ordinary path-based copier remains available for low-level callers;
    build publication uses this variant so replacement of the output parent
    cannot redirect staging writes to a different directory object.
    """

    source = _require_directory(source, "handoff source tree")
    source_directories = _source_directory_paths(source)
    relative_root = _canonical_relative(relative_root, "handoff destination tree")
    _mkdir_new_at(destination_root_fd, relative_root, mode=0o750)
    destination_absolute = destination_root / Path(relative_root)
    destination_fd = _open_relative_directory_fd(
        destination_root_fd,
        relative_root,
        "handoff destination tree",
    )
    try:
        destination_state = os.fstat(destination_fd)
        before = _source_tree_snapshot(source)
        for relative in source_directories:
            if relative:
                _mkdir_new_at(destination_fd, relative, mode=0o750)
        for record in before:
            relative = str(record["path"])
            destination_relative = f"{relative_root}/{relative}"
            _copy_file_bound(
                source / Path(relative),
                destination_fd,
                destination_absolute,
                relative,
                mode=_staging_file_mode(destination_relative),
            )
        after = _source_tree_snapshot(source)
        after_directories = _source_directory_paths(source)
        _verify_named_open_directory(
            path=destination_absolute,
            descriptor=destination_fd,
            expected_inode=destination_state,
            label="handoff destination tree",
        )
        copied = [
            {
                "path": path.relative_to(destination_absolute).as_posix(),
                "sha256": sha256_file(path),
            }
            for path in _walk_regular(destination_absolute)
        ]
        expected_copied = [
            {"path": str(record["path"]), "sha256": str(record["sha256"])}
            for record in before
        ]
        copied_directories = _source_directory_paths(destination_absolute)
        if (
            before != after
            or source_directories != after_directories
            or copied != expected_copied
            or copied_directories != source_directories
        ):
            raise HandoffError("handoff source tree changed while it was copied")
    finally:
        os.close(destination_fd)


def _mkdir_new(path: Path, *, mode: int) -> Path:
    absolute, name, parent_fd = _parent_fd(path, "new handoff directory")
    try:
        os.mkdir(name, mode=mode, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError as exc:
        raise HandoffError("handoff staging path unexpectedly exists") from exc
    except OSError as exc:
        raise HandoffError("handoff staging directory could not be created safely") from exc
    finally:
        os.close(parent_fd)
    return absolute


def _write_new(path: Path, payload: bytes, *, mode: int = 0o640) -> None:
    absolute, name, parent_fd = _parent_fd(
        path,
        "handoff output",
        create=True,
    )
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        os.close(parent_fd)
        raise HandoffError("handoff output could not be created exclusively") from exc
    created = os.fstat(descriptor)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise HandoffError("handoff output write was incomplete")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        _unlink_if_same_inode(parent_fd, name, created)
        raise HandoffError("handoff output write failed safely") from exc
    except Exception:
        _unlink_if_same_inode(parent_fd, name, created)
        raise
    finally:
        os.close(descriptor)
        os.close(parent_fd)


def _prospective(path: str | Path, label: str) -> Path:
    absolute, name, parent_fd = _parent_fd(Path(path), label)
    try:
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return absolute
        raise HandoffError(f"{label} already exists")
    finally:
        os.close(parent_fd)


def _parent_directory_state(path: Path, label: str) -> os.stat_result:
    """Capture the directory object that owns a prospective final name."""

    _absolute, _name, parent_fd = _parent_fd(path, label)
    try:
        state = os.fstat(parent_fd)
        if not stat.S_ISDIR(state.st_mode):
            raise HandoffError(f"{label} parent must be a real directory")
        return state
    finally:
        os.close(parent_fd)


def _open_prospective_parent(
    path: Path,
    label: str,
) -> tuple[Path, str, int, os.stat_result]:
    """Open and bind the parent of a prospective output before any writes."""

    absolute = _absolute_path(path, label)
    if absolute == Path("/"):
        raise HandoffError(f"{label} must not be the filesystem root")
    parent, parent_fd = _open_directory_fd(absolute.parent, f"{label} parent")
    try:
        try:
            os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise HandoffError(f"{label} already exists")
        state = os.fstat(parent_fd)
        if not stat.S_ISDIR(state.st_mode):
            raise HandoffError(f"{label} parent must be a real directory")
        return absolute, absolute.name, parent_fd, state
    except BaseException:
        os.close(parent_fd)
        raise


def _assert_parent_binding(
    path: Path,
    descriptor: int,
    expected_state: os.stat_result,
    label: str,
) -> None:
    """Check that a path still names the directory held for a build."""

    try:
        held = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(held.st_mode)
            or _directory_inode_identity(held)
            != _directory_inode_identity(expected_state)
        ):
            raise HandoffError(f"{label} parent identity changed")
        _verify_named_open_directory(
            path=path,
            descriptor=descriptor,
            expected_inode=expected_state,
            label=label,
        )
    except OSError as exc:
        raise HandoffError(f"{label} parent identity could not be checked") from exc


def _assert_bound_child_directory(
    parent_fd: int,
    name: str,
    descriptor: int,
    expected_state: os.stat_result,
    label: str,
) -> None:
    """Check a child directory name against its held descriptor."""

    try:
        held = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(held.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or _directory_inode_identity(held)
            != _directory_inode_identity(expected_state)
            or _directory_inode_identity(named)
            != _directory_inode_identity(held)
        ):
            raise HandoffError(f"{label} is not bound to its staging directory")
    except OSError as exc:
        raise HandoffError(f"{label} could not be bound safely") from exc


def _physical_path_for_overlap(path: Path) -> Path:
    """Resolve existing path components for boundary comparisons.

    ``Path`` comparisons are lexical and therefore miss aliases on volumes
    whose names are case-insensitive or Unicode-normalizing.  ``realpath``
    handles symlink/mount aliases; the component walk additionally recovers
    the spelling stored by a case-insensitive filesystem when the requested
    spelling is only an alias.  Ambiguous case-fold matches are left untouched
    so a genuinely case-sensitive volume is not treated as aliased.
    """

    try:
        resolved = Path(os.path.realpath(os.fspath(path)))
    except (OSError, ValueError):
        return path
    current = Path(resolved.anchor or os.sep)
    components = resolved.parts[1:] if resolved.is_absolute() else resolved.parts
    for component in components:
        if not current.is_dir():
            current /= component
            continue
        try:
            entries = list(os.scandir(current))
        except OSError:
            current /= component
            continue
        exact = [entry for entry in entries if entry.name == component]
        if exact:
            current /= exact[0].name
            continue
        folded = unicodedata.normalize("NFC", component).casefold()
        aliases = [
            entry.name
            for entry in entries
            if unicodedata.normalize("NFC", entry.name).casefold() == folded
        ]
        current /= aliases[0] if len(aliases) == 1 else component
    return current


def _existing_ancestors(path: Path) -> Iterable[Path]:
    current = path
    while True:
        try:
            os.lstat(current)
        except OSError:
            pass
        else:
            yield current
        if current == current.parent:
            break
        current = current.parent


def _samefile(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, OSError):
        return False


def _overlaps(left: Path, right: Path) -> bool:
    """Return whether two paths overlap lexically or on the actual volume."""

    candidates = ((left, right), (_physical_path_for_overlap(left), _physical_path_for_overlap(right)))
    for candidate_left, candidate_right in candidates:
        try:
            candidate_left.relative_to(candidate_right)
            return True
        except ValueError:
            pass
        try:
            candidate_right.relative_to(candidate_left)
            return True
        except ValueError:
            pass

    # ``left`` or ``right`` can be a prospective (not-yet-created) final
    # component.  Compare every existing ancestor only against the other exact
    # node; comparing arbitrary ancestor pairs would falsely report two
    # unrelated siblings as overlapping merely because they share ``/tmp``.
    for ancestor in _existing_ancestors(left):
        if _samefile(ancestor, right):
            return True
    for ancestor in _existing_ancestors(right):
        if _samefile(ancestor, left):
            return True
    return False


def _validate_output_boundaries(
    *,
    output_root: Path,
    receipt_path: Path,
    sources: Sequence[Path],
) -> None:
    if _overlaps(output_root, receipt_path):
        raise HandoffError("detached receipt must be outside the handoff output")
    for source in sources:
        absolute = _absolute_path(source, "handoff input")
        if _overlaps(output_root, absolute) or _overlaps(receipt_path, absolute):
            raise HandoffError("handoff outputs overlap an input root or file")


def _tree_records(root: Path, *, exclude: Iterable[str] = ()) -> list[dict[str, str]]:
    root = _absolute_path(root, "handoff tree")
    excluded = set(exclude)
    records: list[dict[str, str]] = []
    for path in _walk_regular(root):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        records.append({"path": relative, "sha256": sha256_file(path)})
    return records


def _directory_record_sha256(root: Path) -> str:
    root = _absolute_path(root, "handoff evidence directory")
    records = [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in _walk_regular(root)
    ]
    return _canonical_sha256(records)


def _evidence_records(root: Path) -> list[dict[str, str]]:
    records: list[dict[str, Any]] = []
    for label, kind, relative, schema_version in _EVIDENCE_SPECS:
        target = root / relative
        document = _strict_json(target) if kind == "file" else None
        if document is not None and document.get("schema_version") != schema_version:
            if (
                label in {"offline-test-component-set", "offline-test-receipt"}
                and document.get("schema_version")
                in _SUPERSEDED_OFFLINE_EVIDENCE_SCHEMAS
            ):
                raise HandoffError(
                    "superseded offline evidence is invalid and cannot be reused",
                    code="superseded-invalid-evidence",
                )
            raise HandoffError("handoff evidence schema differs from its typed record")
        digest = (
            sha256_file(target)
            if kind == "file"
            else _directory_record_sha256(target)
        )
        records.append(
            {
                "label": label,
                "kind": kind,
                "path": relative,
                "sha256": digest,
                "schema_version": schema_version,
                "status": "passed",
                "document_status": (
                    document.get("status") if document is not None else None
                ),
                "document_ok": document.get("ok") if document is not None else None,
            }
        )
    if tuple(record["label"] for record in records) != REQUIRED_PHASE1_EVIDENCE_LABELS:
        raise HandoffError("internal handoff evidence order differs from the request contract")
    return records  # type: ignore[return-value]


def _request_evidence_records(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    keys = ("label", "kind", "path", "sha256", "schema_version", "status")
    return [{key: str(record[key]) for key in keys} for record in records]


def _reject_superseded_offline_evidence(root: Path) -> None:
    """Classify known-invalid offline schemas before the current validator runs."""

    for label, kind, relative, _schema_version in _EVIDENCE_SPECS:
        if label not in {"offline-test-component-set", "offline-test-receipt"}:
            continue
        if kind != "file":
            raise HandoffError("offline evidence typed record is malformed")
        document = _strict_json(root / relative)
        if document.get("schema_version") in _SUPERSEDED_OFFLINE_EVIDENCE_SCHEMAS:
            raise HandoffError(
                "superseded offline evidence is invalid and cannot be reused",
                code="superseded-invalid-evidence",
            )


def _source_scope_value(scope: ApprovedSourceScope) -> dict[str, object]:
    redacted = sum(record.byte_disposition == "approved-redacted-copy" for record in scope.records)
    return {
        "schema_version": "cloud-v2-source-scope-v1",
        "candidate_id": "revision-a-r9",
        "source_count": len(scope.records),
        "unchanged_source_count": len(scope.records) - redacted,
        "approved_redacted_source_count": redacted,
        "source_manifest_sha256": scope.source_manifest_sha256,
        "allowlist_sha256": scope.allowlist_sha256,
        "stop_a_receipt_sha256": scope.stop_a_receipt_sha256,
        "source_dlp_receipt_sha256": scope.source_dlp_receipt_sha256,
    }


def _request_mode(path: Path) -> str:
    # The request is a sealed contract input, not an arbitrary JSON document.
    # Reject alternate whitespace/key-order encodings before its bytes are
    # copied into the handoff and bound by the manifest.
    value = _strict_json(path, canonical=True)
    readiness = value.get("approval_readiness")
    mode = readiness.get("mode") if isinstance(readiness, Mapping) else None
    if mode not in {"template", "approval_ready"}:
        raise HandoffError("Stop B request approval_readiness.mode is invalid")
    return str(mode)


def _require_schema(
    value: Mapping[str, Any],
    *,
    schema: str,
    label: str,
    status: str = "passed",
    ok: bool = True,
) -> None:
    if value.get("schema_version") != schema or value.get("status") != status or value.get("ok") is not ok:
        raise HandoffError(f"{label} did not satisfy its exact passing contract")


def _suite_identity(root: Path) -> dict[str, object]:
    suite_root = root / SUITE_RELATIVE
    suite_manifest_path = suite_root / "SUITE_MANIFEST.json"
    suite = _strict_json(suite_manifest_path)
    build_receipt = _strict_json(root / "phase1-evidence/suite-build-receipt.json")
    return {
        "path": SUITE_RELATIVE,
        "release_id": suite.get("suite_release_id"),
        "suite_manifest_sha256": sha256_file(suite_manifest_path),
        "sha256sums_sha256": sha256_file(suite_root / "SHA256SUMS"),
        "suite_file_count": len(_walk_regular(suite_root)),
        "suite_build_status": build_receipt.get("status"),
    }


def _manifest_value(
    *,
    root: Path,
    request: Mapping[str, Any],
    request_mode: str,
    scope: ApprovedSourceScope,
    evidence_records: list[dict[str, str]],
) -> dict[str, object]:
    # Regular-file hashes do not describe empty directories.  Bind the full
    # directory shape separately so a verifier cannot accept a tree with an
    # inserted empty branch merely because MATERIALS.sha256 is unchanged.
    directory_paths = _tree_directory_paths(root, require_frozen=False)
    return {
        "schema_version": HANDOFF_MANIFEST_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "request": {
            "path": REQUEST_NAME,
            "schema_version": request.get("schema_version"),
            "mode": request_mode,
            "sha256": sha256_file(root / REQUEST_NAME),
        },
        "suite": _suite_identity(root),
        "source_scope": _source_scope_value(scope),
        "phase_state": dict(_PHASE_STATE),
        "evidence_records": evidence_records,
        "materials": {
            "path": MATERIALS_NAME,
            "coverage": "all-regular-handoff-files-except-self",
            "record_order": "canonical-relative-posix-path",
        },
        "tree": {
            "directory_paths": list(directory_paths),
            "directory_paths_sha256": _canonical_sha256(list(directory_paths)),
        },
        "provider_contract": {
            "provider_neutral": True,
            "provider_calls_authorized": False,
            "real_provider_calls": 0,
        },
    }


def _detached_verification_evidence_output(
    output_path: str | Path,
    *,
    repo_root: Path,
    suite_root: Path,
    label: str,
) -> Path:
    output = _absolute_path(Path(output_path), label)
    if os.path.lexists(output):
        raise HandoffError(f"{label} already exists")
    if _overlaps(output, repo_root) or _overlaps(output, suite_root):
        raise HandoffError(f"{label} must be detached from the repository and suite")
    return output


def _expected_app_verification_evidence(
    *,
    repo_root: Path,
    zip_path: Path,
    app_receipt_path: Path,
) -> dict[str, Any]:
    zip_before = _require_regular(zip_path, "App package zip")
    receipt_before = _require_regular(app_receipt_path, "App package receipt")
    try:
        verification = verify_app_package(zip_path, repo_root=repo_root)
    except Exception as exc:
        raise HandoffError("App package verification could not be recomputed") from exc
    if set(verification) != {
        "schema_version",
        "status",
        "ok",
        "member_count",
        "member_set_sha256",
        "zip_sha256",
    }:
        raise HandoffError("App package verification result schema is not exact")
    _require_schema(
        verification,
        schema="cloud-v2-app-package-verification-v1",
        label="App package verification result",
    )
    if (
        type(verification.get("member_count")) is not int
        or verification["member_count"] < 1
        or not isinstance(verification.get("member_set_sha256"), str)
        or not SHA256_PATTERN.fullmatch(verification["member_set_sha256"])
        or not isinstance(verification.get("zip_sha256"), str)
        or not SHA256_PATTERN.fullmatch(verification["zip_sha256"])
    ):
        raise HandoffError("App package verification result values are malformed")

    receipt = _strict_json(app_receipt_path)
    if set(receipt) != {
        "schema_version",
        "status",
        "ok",
        "zip_sha256",
        "zip_size_bytes",
        "member_count",
        "member_set_sha256",
        "skill_roots",
        "server_or_ops_member_count",
    }:
        raise HandoffError("App package receipt schema is not exact")
    _require_schema(
        receipt,
        schema="cloud-v2-app-package-receipt-v1",
        label="App package receipt",
    )
    if (
        type(receipt.get("zip_size_bytes")) is not int
        or receipt["zip_size_bytes"] < 1
        or type(receipt.get("member_count")) is not int
        or receipt["member_count"] < 1
        or type(receipt.get("server_or_ops_member_count")) is not int
        or receipt["server_or_ops_member_count"] < 0
    ):
        raise HandoffError("App package receipt numeric values are malformed")
    if (
        receipt.get("zip_sha256") != verification["zip_sha256"]
        or receipt.get("zip_size_bytes") != zip_before.st_size
        or receipt.get("member_count") != verification["member_count"]
        or receipt.get("member_set_sha256") != verification["member_set_sha256"]
        or receipt.get("skill_roots") != ["knowledge-graph-cloud"]
        or receipt.get("server_or_ops_member_count") != 0
    ):
        raise HandoffError("App package receipt differs from the verified App zip")

    verifier_path = repo_root / "deploy/cloud_v2/artifact_builder.py"
    verifier_payload = _read_regular_bytes(verifier_path, "App package verifier")
    if (
        _state_identity(_require_regular(zip_path, "App package zip"))
        != _state_identity(zip_before)
        or _state_identity(_require_regular(app_receipt_path, "App package receipt"))
        != _state_identity(receipt_before)
    ):
        raise HandoffError("App verification inputs changed during recomputation")
    return {
        "schema_version": APP_VERIFICATION_EVIDENCE_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "verification": verification,
        "zip": {
            "path": f"{SUITE_RELATIVE}/app-upload/knowledge-graph-cloud-app-upload.zip",
            "sha256": verification["zip_sha256"],
        },
        "app_receipt": {
            "path": f"{EVIDENCE_RELATIVE}/app-package-receipt.json",
            "sha256": sha256_file(app_receipt_path),
        },
        "verifier": {
            "path": "deploy/cloud_v2/artifact_builder.py",
            "sha256": hashlib.sha256(verifier_payload).hexdigest(),
        },
    }


def _build_app_verification_evidence_impl(
    *,
    repo_root: str | Path,
    suite_root: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Create the exact detached App verification wrapper required by Stop B."""

    repo = _require_directory(Path(repo_root), "repository root")
    suite = _require_directory(Path(suite_root), "suite root")
    output = _detached_verification_evidence_output(
        output_path,
        repo_root=repo,
        suite_root=suite,
        label="App verification evidence output",
    )
    value = _expected_app_verification_evidence(
        repo_root=repo,
        zip_path=suite / "app-upload/knowledge-graph-cloud-app-upload.zip",
        app_receipt_path=suite / "server-runtime/evidence/app-package-receipt.json",
    )
    _write_new(output, canonical_json_bytes(value))
    if _strict_json(output, canonical=True) != value:
        raise HandoffError("App verification evidence changed after serialization")
    return {**value, "receipt_sha256": sha256_file(output)}


def build_app_verification_evidence(
    *,
    repo_root: str | Path,
    suite_root: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    actions = _require_formal_stop_b_handoff_bootstrap_context()
    return actions[5](
        repo_root=repo_root,
        suite_root=suite_root,
        output_path=output_path,
    )


def _validate_app_verification(root: Path, repo_root: Path) -> None:
    evidence = _strict_json(root / "phase1-evidence/app-package-verification.json")
    if set(evidence) != {
        "schema_version",
        "status",
        "ok",
        "verification",
        "zip",
        "app_receipt",
        "verifier",
    }:
        raise HandoffError("App package verification evidence schema is not exact")
    _require_schema(
        evidence,
        schema=APP_VERIFICATION_EVIDENCE_SCHEMA_VERSION,
        label="App package verification evidence",
    )
    zip_path = root / f"{SUITE_RELATIVE}/app-upload/knowledge-graph-cloud-app-upload.zip"
    receipt_path = root / f"{EVIDENCE_RELATIVE}/app-package-receipt.json"
    expected = _expected_app_verification_evidence(
        repo_root=repo_root,
        zip_path=zip_path,
        app_receipt_path=receipt_path,
    )
    if canonical_json_bytes(evidence) != canonical_json_bytes(expected):
        raise HandoffError("App verification evidence differs from recomputation")


def _parse_hash_manifest(path: Path) -> list[dict[str, str]]:
    try:
        lines = _read_regular_bytes(path, "code manifest").decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise HandoffError("code manifest is not UTF-8") from exc
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in lines:
        digest, separator, raw_path = line.partition("  ")
        relative = _canonical_relative(raw_path, "code manifest path")
        if not separator or not SHA256_PATTERN.fullmatch(digest) or relative in seen:
            raise HandoffError("code manifest contains a malformed or duplicate record")
        seen.add(relative)
        records.append({"path": relative, "sha256": digest})
    if not records or [record["path"] for record in records] != sorted(seen):
        raise HandoffError("code manifest must be non-empty and sorted")
    return records


def _load_package_verifier(repo_root: Path) -> tuple[types.ModuleType, Path, str]:
    path = repo_root / "skills/knowledge-graph-cloud/scripts/verify_package.py"
    payload = _read_regular_bytes(path, "package verifier")
    try:
        code = compile(payload, str(path), "exec")
    except (SyntaxError, ValueError) as exc:
        raise HandoffError("package verifier cannot be compiled") from exc
    module = types.ModuleType("_cloud_v2_live_package_verifier")
    module.__file__ = str(path)
    try:
        exec(code, module.__dict__)
    except Exception as exc:
        raise HandoffError("package verifier could not be loaded") from exc
    if not callable(getattr(module, "verify_package", None)) or not callable(
        getattr(module, "expected_delivery_files", None)
    ):
        raise HandoffError("package verifier public API is incomplete")
    return module, path, hashlib.sha256(payload).hexdigest()


def _expected_code_manifest_verification_evidence(
    repo_root: Path,
) -> dict[str, Any]:
    verifier_module, verifier_path, verifier_sha256 = _load_package_verifier(repo_root)
    code_path = repo_root / "CODE_MANIFEST.sha256"
    source_path = repo_root / "MANIFEST.sha256"
    code_before = _require_regular(code_path, "code manifest")
    source_before = _require_regular(source_path, "source manifest")
    try:
        live_errors = verifier_module.verify_package(repo_root)
        live_expected = verifier_module.expected_delivery_files(repo_root)
    except Exception as exc:
        raise HandoffError("live package verification could not be recomputed") from exc
    if live_errors != []:
        raise HandoffError("live package verifier rejected the current checkout")
    if not isinstance(live_expected, set) or not all(
        isinstance(item, str) for item in live_expected
    ):
        raise HandoffError("live package expected-delivery set is malformed")

    code_records = _parse_hash_manifest(code_path)
    source_records = _parse_hash_manifest(source_path)
    if {record["path"] for record in code_records} != live_expected:
        raise HandoffError("code manifest coverage differs from live expected delivery files")
    code_sha256 = sha256_file(code_path)
    source_sha256 = sha256_file(source_path)
    if (
        _state_identity(_require_regular(code_path, "code manifest"))
        != _state_identity(code_before)
        or _state_identity(_require_regular(source_path, "source manifest"))
        != _state_identity(source_before)
        or sha256_file(verifier_path) != verifier_sha256
    ):
        raise HandoffError("code verification inputs changed during recomputation")
    try:
        final_errors = verifier_module.verify_package(repo_root)
        final_expected = verifier_module.expected_delivery_files(repo_root)
    except Exception as exc:
        raise HandoffError("live package verification could not be repeated") from exc
    if (
        final_errors != []
        or final_expected != live_expected
        or _state_identity(_require_regular(code_path, "code manifest"))
        != _state_identity(code_before)
        or _state_identity(_require_regular(source_path, "source manifest"))
        != _state_identity(source_before)
        or sha256_file(verifier_path) != verifier_sha256
    ):
        raise HandoffError("code verification inputs changed during recomputation")

    return {
        "schema_version": CODE_VERIFICATION_EVIDENCE_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "errors": [],
        "expected_delivery_file_count": len(code_records),
        "code_manifest": {
            "path": "CODE_MANIFEST.sha256",
            "record_count": len(code_records),
            "sha256": code_sha256,
        },
        "source_manifest": {
            "path": "MANIFEST.sha256",
            "record_count": len(source_records),
            "sha256": source_sha256,
        },
        "verifier": {
            "path": "skills/knowledge-graph-cloud/scripts/verify_package.py",
            "sha256": verifier_sha256,
        },
    }


def _build_code_manifest_verification_evidence_impl(
    *,
    repo_root: str | Path,
    suite_root: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Create the exact detached code-manifest wrapper required by Stop B."""

    repo = _require_directory(Path(repo_root), "repository root")
    suite = _require_directory(Path(suite_root), "suite root")
    output = _detached_verification_evidence_output(
        output_path,
        repo_root=repo,
        suite_root=suite,
        label="code verification evidence output",
    )
    value = _expected_code_manifest_verification_evidence(repo)
    _write_new(output, canonical_json_bytes(value))
    if _strict_json(output, canonical=True) != value:
        raise HandoffError("code verification evidence changed after serialization")
    return {**value, "receipt_sha256": sha256_file(output)}


def build_code_manifest_verification_evidence(
    *,
    repo_root: str | Path,
    suite_root: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    actions = _require_formal_stop_b_handoff_bootstrap_context()
    return actions[6](
        repo_root=repo_root,
        suite_root=suite_root,
        output_path=output_path,
    )


def _validate_code_verification(root: Path, repo_root: Path, phase1: Mapping[str, Any]) -> None:
    evidence = _strict_json(root / "phase1-evidence/code-manifest-verification.json")
    if set(evidence) != {
        "schema_version",
        "status",
        "ok",
        "errors",
        "expected_delivery_file_count",
        "code_manifest",
        "source_manifest",
        "verifier",
    }:
        raise HandoffError("code manifest verification evidence schema is not exact")
    _require_schema(
        evidence,
        schema=CODE_VERIFICATION_EVIDENCE_SCHEMA_VERSION,
        label="code manifest verification evidence",
    )
    expected_value = _expected_code_manifest_verification_evidence(repo_root)
    if canonical_json_bytes(evidence) != canonical_json_bytes(expected_value):
        raise HandoffError("code verification evidence differs from recomputation")
    implementation = phase1.get("implementation_scope")
    files = implementation.get("files") if isinstance(implementation, Mapping) else None
    if not isinstance(files, list):
        raise HandoffError("Phase 1 DLP implementation scope is absent")
    implementation_map = {
        item.get("path"): item.get("sha256")
        for item in files
        if isinstance(item, Mapping)
    }
    for field in ("code_manifest", "source_manifest", "verifier"):
        binding = expected_value[field]
        relative = str(binding["path"])
        if implementation_map.get(relative) != binding.get("sha256"):
            raise HandoffError("code verification identity is absent from Phase 1 DLP scope")


def _phase1_layer_file_map(
    phase1: Mapping[str, Any], label: str
) -> dict[str, str]:
    layers = phase1.get("layers")
    layer = layers.get(label) if isinstance(layers, Mapping) else None
    files = layer.get("files") if isinstance(layer, Mapping) else None
    if not isinstance(files, list):
        raise HandoffError(f"Phase 1 DLP {label} file inventory is absent")
    result: dict[str, str] = {}
    for record in files:
        if not isinstance(record, Mapping) or set(record) != {"path", "sha256"}:
            raise HandoffError(f"Phase 1 DLP {label} file inventory is malformed")
        relative = _canonical_relative(
            record.get("path"), f"Phase 1 DLP {label} file"
        )
        digest = record.get("sha256")
        if (
            not isinstance(digest, str)
            or not SHA256_PATTERN.fullmatch(digest)
            or relative in result
        ):
            raise HandoffError(f"Phase 1 DLP {label} file identity is malformed")
        result[relative] = digest
    if list(result) != sorted(result):
        raise HandoffError(f"Phase 1 DLP {label} file inventory is not sorted")
    return result


def _validate_request_candidate_binding(
    request: Mapping[str, Any], phase1: Mapping[str, Any]
) -> None:
    local_vector_contract = request.get("local_vector_contract")
    candidate = (
        local_vector_contract.get("candidate")
        if isinstance(local_vector_contract, Mapping)
        else None
    )
    if not isinstance(candidate, Mapping):
        raise HandoffError("Stop B request candidate contract is absent")

    derived_root = _canonical_relative(
        candidate.get("derived_candidate_root"),
        "Stop B request derived candidate root",
    )
    data_release_id = candidate.get("data_release_id")
    if not isinstance(data_release_id, str) or not data_release_id:
        raise HandoffError("Stop B request candidate release identity is absent")
    candidate_data_root = _canonical_relative(
        candidate.get("candidate_data_root"),
        "Stop B request candidate data root",
    )
    candidate_relative = f"local-vector/candidate/{data_release_id}"
    if (
        derived_root != DERIVED_CANDIDATE_ROOT
        or candidate_data_root != f"{derived_root}/{candidate_relative}"
    ):
        raise HandoffError("Stop B request candidate path closure differs")

    authority_files = _phase1_layer_file_map(phase1, "authority")
    derived_files = _phase1_layer_file_map(phase1, "derived")
    local_vector_manifest = f"{candidate_relative}/local_vector_manifest.json"
    discovered_local_vector_manifests = sorted(
        relative
        for relative in derived_files
        if relative.startswith("local-vector/candidate/")
        and relative.endswith("/local_vector_manifest.json")
    )
    if discovered_local_vector_manifests != [local_vector_manifest]:
        raise HandoffError(
            "Phase 1 candidate local-vector path differs from the Stop B request"
        )

    production_data_files: list[dict[str, str]] = []
    for relative, _expected_digest in PRODUCTION_DATA_FILES:
        layer, layer_relative = relative.split("/", 1)
        layer_files = authority_files if layer == "authority" else derived_files
        digest = layer_files.get(layer_relative)
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise HandoffError(
                "Phase 1 production data identity is absent or malformed"
            )
        production_data_files.append({"path": relative, "sha256": digest})
    if (
        candidate.get("production_data_files") != production_data_files
        or candidate.get("production_data_file_set_sha256")
        != PRODUCTION_DATA_FILE_SET_SHA256
        or _canonical_sha256(production_data_files)
        != candidate.get("production_data_file_set_sha256")
    ):
        raise HandoffError(
            "Stop B request production data identity differs from the Phase 1 candidate"
        )

    role_closure = phase1.get("role_closure")
    derived_closure = (
        role_closure.get("derived") if isinstance(role_closure, Mapping) else None
    )
    if not isinstance(derived_closure, Mapping):
        raise HandoffError("Phase 1 candidate role closure is absent")
    actual = {
        "authority_manifest_sha256": authority_files.get("authority-manifest.json"),
        "derived_candidate_manifest_sha256": derived_files.get(
            "derived-candidate-manifest.json"
        ),
        "fake_embedding_manifest_sha256": derived_files.get(
            "fake-embedding-manifest.json"
        ),
        "candidate_manifest_sha256": derived_files.get(local_vector_manifest),
    }
    if (
        any(
            not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest)
            for digest in actual.values()
        )
        or role_closure.get("authority_manifest_sha256")
        != actual["authority_manifest_sha256"]
        or derived_closure.get("manifest_sha256")
        != actual["derived_candidate_manifest_sha256"]
        or any(candidate.get(field) != digest for field, digest in actual.items())
    ):
        raise HandoffError(
            "Stop B request candidate identity differs from the Phase 1 candidate"
        )


def _load_phase1_candidate_receipt(
    *,
    root: Path,
    repo_root: Path,
    scope: ApprovedSourceScope,
    authority_database_physical_mode: int,
) -> Mapping[str, Any]:
    receipt_path = root / "phase1-evidence/phase1-dlp-receipt.json"
    derived_root = root / f"{SUITE_RELATIVE}/server-runtime/data/derived"
    candidate_manifests = (
        derived_root / "derived-candidate-manifest.json",
        derived_root / "fake-embedding-manifest.json",
    )
    packaged = tuple(os.path.lexists(path) for path in candidate_manifests)
    if any(packaged):
        if not all(packaged):
            raise HandoffError("suite contains a partial offline candidate manifest set")
        return validate_phase1_dlp_receipt(
            receipt=receipt_path,
            scope=scope,
            authority_root=root / f"{SUITE_RELATIVE}/server-runtime/data/authority",
            derived_root=derived_root,
            code_root=repo_root,
            authority_database_physical_mode=authority_database_physical_mode,
        )

    receipt = _strict_json(receipt_path, canonical=True)
    if receipt.get("source_scope") != scope.identity():
        raise HandoffError(
            "production-only suite candidate DLP scope differs from the approved source scope"
        )
    return receipt


def _validate_fixed_cross_bindings(root: Path) -> None:
    suite = root / SUITE_RELATIVE
    pairs = (
        (
            root / "phase1-evidence/app-package-receipt.json",
            suite / "server-runtime/evidence/app-package-receipt.json",
        ),
        (
            root / "phase1-evidence/phase1-dlp-receipt.json",
            suite / "server-runtime/evidence/candidate-dlp-receipt.json",
        ),
        (
            root / "phase1-evidence/disclosure-evidence.json",
            suite / "server-runtime/evidence/disclosure-evidence.json",
        ),
        (
            root / "phase1-evidence/offline-tests/offline-test-component-set.json",
            suite / "server-runtime/evidence/offline-test-component-set.json",
        ),
        (
            root / "phase1-evidence/offline-tests/offline-test-receipt.json",
            suite / "server-runtime/evidence/offline-test-receipt.json",
        ),
    )
    for outside, inside in pairs:
        if _read_regular_bytes(outside, "handoff evidence") != _read_regular_bytes(
            inside,
            "suite embedded evidence",
        ):
            raise HandoffError("handoff evidence differs from the suite embedded copy")
    outside_logs = root / "phase1-evidence/offline-tests/logs"
    inside_logs = suite / "server-runtime/evidence/logs"
    if _tree_records(outside_logs) != _tree_records(inside_logs):
        raise HandoffError("handoff logs differ from the suite embedded logs")
    manifest = _strict_json(suite / "SUITE_MANIFEST.json")
    evidence = manifest.get("evidence")
    if not isinstance(evidence, Mapping):
        raise HandoffError("suite evidence bindings are absent")
    expected = {
        "app_package_receipt_sha256": sha256_file(root / "phase1-evidence/app-package-receipt.json"),
        "candidate_dlp_receipt_sha256": sha256_file(root / "phase1-evidence/phase1-dlp-receipt.json"),
        "disclosure_evidence_sha256": sha256_file(root / "phase1-evidence/disclosure-evidence.json"),
        "offline_test_component_set_sha256": sha256_file(root / "phase1-evidence/offline-tests/offline-test-component-set.json"),
        "offline_test_receipt_sha256": sha256_file(root / "phase1-evidence/offline-tests/offline-test-receipt.json"),
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        raise HandoffError("suite manifest evidence hashes differ from handoff evidence")
    log_records = [
        {
            "path": f"server-runtime/evidence/logs/{item['path']}",
            "sha256": item["sha256"],
        }
        for item in _tree_records(outside_logs)
    ]
    if evidence.get("offline_test_log_records") != log_records:
        raise HandoffError("suite manifest log bindings differ from handoff logs")


def _validate_suite_receipts(root: Path, recomputed: Mapping[str, Any]) -> None:
    suite = root / SUITE_RELATIVE
    build = _strict_json(root / "phase1-evidence/suite-build-receipt.json")
    _require_schema(
        build,
        schema="cloud-v2-suite-build-receipt-v2",
        label="suite build receipt",
        status="pending-final-dlp",
        ok=False,
    )
    if build.get("structural_verification_ok") is not True or build.get("final_dlp_verified") is not False or build.get("real_provider_calls") != 0:
        raise HandoffError("suite build receipt lost its exact pending-final-DLP boundary")
    if (
        build.get("suite_release_id") != recomputed.get("suite_release_id")
        or build.get("suite_manifest_sha256")
        != recomputed.get("suite_manifest_sha256")
        or build.get("sha256sums_sha256") != sha256_file(suite / "SHA256SUMS")
        or build.get("candidate_dlp_receipt_sha256")
        != sha256_file(root / "phase1-evidence/phase1-dlp-receipt.json")
    ):
        raise HandoffError("suite build receipt differs from the sealed suite")
    recorded = _strict_json(root / "phase1-evidence/suite-verification.json")
    if recorded != recomputed:
        raise HandoffError("suite verification evidence differs from recomputation")


def _finalize_source_scope(scope: ApprovedSourceScope) -> None:
    failure: Exception | None = None
    try:
        scope.revalidate()
    except Exception as exc:
        failure = exc
    try:
        scope.close()
    except Exception as exc:
        if failure is None:
            failure = exc
    if failure is not None:
        raise HandoffError(
            "approved source scope final revalidation failed"
        ) from failure


def _validate_core(
    *,
    root: Path,
    repo_root: Path,
    source_root: Path,
    governance_root: Path,
    authority_database_physical_mode: int,
) -> tuple[Mapping[str, Any], str, ApprovedSourceScope, list[dict[str, str]]]:
    request_path = root / REQUEST_NAME
    mode = _request_mode(request_path)
    _reject_superseded_offline_evidence(root)
    scope: ApprovedSourceScope | None = None
    try:
        request = load_stop_b_request(request_path, mode=mode)
        scope = ApprovedSourceScope.load(source_root, governance_root)
        phase1 = _load_phase1_candidate_receipt(
            root=root,
            repo_root=repo_root,
            scope=scope,
            authority_database_physical_mode=authority_database_physical_mode,
        )
        disclosure_result = run_formal_validation(
            repo_root=repo_root,
            validation="validate-disclosure",
            receipt_path=root / "phase1-evidence/disclosure-evidence.json",
        )
        test_result = run_formal_validation(
            repo_root=repo_root,
            validation="validate-tests",
            receipt_path=root / "phase1-evidence/offline-tests/offline-test-receipt.json",
            evidence_root=root / "phase1-evidence/offline-tests",
            component_set_path=root / "phase1-evidence/offline-tests/offline-test-component-set.json",
        )
        evidence_roots = {
            "disclosure-evidence": root / "phase1-evidence/disclosure-evidence.json",
            "offline-test-component-set": root / "phase1-evidence/offline-tests/offline-test-component-set.json",
            "offline-test-logs": root / "phase1-evidence/offline-tests/logs",
            "offline-test-receipt": root / "phase1-evidence/offline-tests/offline-test-receipt.json",
            "suite-build-receipt": root / "phase1-evidence/suite-build-receipt.json",
        }
        suite_result = verify_suite(
            root / SUITE_RELATIVE,
            root / "phase1-evidence/final-suite-dlp-receipt.json",
            evidence_roots,
            repo_root=repo_root,
        )
    except (ArtifactBuildError, DLPError, OfflineEvidenceError, SourceScopeError, StopBRequestError, OSError, ValueError, zipfile.BadZipFile) as exc:
        if scope is not None:
            _finalize_source_scope(scope)
        raise HandoffError("handoff semantic validation failed") from exc
    except Exception as exc:
        if scope is not None:
            _finalize_source_scope(scope)
        raise HandoffError("handoff semantic validation failed") from exc
    try:
        if disclosure_result.get("real_provider_calls") != 0 or test_result.get("real_provider_calls") != 0:
            raise HandoffError("handoff evidence reports a real provider call")
        _validate_fixed_cross_bindings(root)
        _validate_request_candidate_binding(request, phase1)
        _validate_app_verification(root, repo_root)
        _validate_code_verification(root, repo_root, phase1)
        _validate_suite_receipts(root, suite_result)
        records = _evidence_records(root)
        readiness = request.get("phase1_evidence")
        declared = readiness.get("receipts") if isinstance(readiness, Mapping) else None
        if mode == "template":
            if declared != []:
                raise HandoffError("template request must retain an empty evidence receipt list")
        elif declared != _request_evidence_records(records):
            raise HandoffError("approval-ready request receipts differ from actual handoff evidence")
        return request, mode, scope, records
    except Exception:
        _finalize_source_scope(scope)
        raise


def _materials_payload(records: Sequence[Mapping[str, str]]) -> bytes:
    return ("".join(f"{record['sha256']}  {record['path']}\n" for record in records)).encode("utf-8")


def _parse_materials_payload(payload: bytes) -> list[dict[str, str]]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise HandoffError("materials manifest is not UTF-8") from exc
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in lines:
        digest, separator, raw_path = line.partition("  ")
        if not separator or not SHA256_PATTERN.fullmatch(digest):
            raise HandoffError("materials manifest contains a malformed line")
        relative = _canonical_relative(raw_path, "materials path")
        if relative == MATERIALS_NAME:
            raise HandoffError("materials manifest must not self-reference")
        if relative in seen:
            raise HandoffError("materials manifest contains a duplicate path")
        seen.add(relative)
        records.append({"path": relative, "sha256": digest})
    if not records or [record["path"] for record in records] != sorted(seen):
        raise HandoffError("materials manifest must be non-empty and sorted")
    if payload != _materials_payload(records):
        raise HandoffError("materials manifest serialization is not canonical")
    return records


def _validate_fixed_layout(root: Path) -> None:
    root = _absolute_path(root, "handoff fixed layout")
    fixed_files = {
        REQUEST_NAME,
        MANIFEST_NAME,
        MATERIALS_NAME,
        "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
        "deploy/cloud_v2/stop-b-synthetic-probes.json",
        *(
            relative
            for _label, kind, relative, _schema in _EVIDENCE_SPECS
            if kind == "file"
        ),
    }
    suite_prefix = SUITE_RELATIVE + "/"
    log_prefix = "phase1-evidence/offline-tests/logs/"
    unexpected = [
        path.relative_to(root).as_posix()
        for path in _walk_regular(root)
        if (
            path.relative_to(root).as_posix() not in fixed_files
            and not path.relative_to(root).as_posix().startswith(suite_prefix)
            and not path.relative_to(root).as_posix().startswith(log_prefix)
        )
    ]
    if unexpected:
        raise HandoffError("handoff fixed layout contains an extra file")


def _parse_materials(root: Path) -> list[dict[str, str]]:
    _validate_fixed_layout(root)
    path = root / MATERIALS_NAME
    payload = _read_regular_bytes(path, "materials manifest")
    records = _parse_materials_payload(payload)
    discovered = _tree_records(root, exclude={MATERIALS_NAME})
    if records != discovered:
        raise HandoffError("materials manifest has missing, extra, or stale records")
    return records


def _handoff_dlp(root: Path) -> dict[str, object]:
    try:
        before = _tree_inventory(root, allow_empty_directories=True)
        scanner = DLPScanner()
        findings = _scan_inventory(
            scanner,
            root=root,
            inventory=before,
            object_prefix="stop-b-handoff",
        )
        after = _tree_inventory(root, allow_empty_directories=True)
        if before != after:
            raise HandoffError("handoff bytes changed during DLP scanning")
        positive_canary, canary_ok = _positive_canary_receipt()
        real = scanner.summary()
        scanner_contract = _scanner_contract()
    except (DLPError, OSError, ValueError) as exc:
        raise HandoffError("full handoff DLP scan failed") from exc
    ok = real.get("finding_count") == 0 and not findings and canary_ok
    return {
        "schema_version": HANDOFF_DLP_SCHEMA_VERSION,
        "status": "passed" if ok else "failed",
        "ok": ok,
        "ruleset_version": DLP_RULESET_VERSION,
        "ruleset_sha256": _ruleset_sha256(),
        "scanner_sha256": hashlib.sha256(
            canonical_json_bytes(scanner_contract)
        ).hexdigest(),
        "scanner_contract": scanner_contract,
        "inventory": before,
        "real_candidate": real,
        "findings": findings,
        "positive_canary": positive_canary,
    }


def _safe_tree_inventory(root: Path, label: str = "handoff tree inventory") -> dict[str, object]:
    """Normalize DLP inventory failures to the handoff's public error type."""

    try:
        return _tree_inventory(root, allow_empty_directories=True)
    except HandoffError:
        raise
    except (DLPError, OSError, ValueError) as exc:
        raise HandoffError(f"{label} could not be computed safely") from exc


def _receipt_value(
    *,
    root: Path,
    request_mode: str,
    evidence_records: list[dict[str, str]],
    dlp: Mapping[str, object],
    expected_inventory: Mapping[str, object],
    expected_materials_sha256: str,
    expected_manifest_sha256: str,
) -> dict[str, object]:
    materials = _parse_materials(root)
    current_inventory = _safe_tree_inventory(root)
    if (
        dlp.get("inventory") != expected_inventory
        or current_inventory != expected_inventory
    ):
        raise HandoffError("handoff DLP inventory differs from the sealed tree")
    manifest = _strict_json(root / MANIFEST_NAME, canonical=True)
    materials_sha256 = sha256_file(root / MATERIALS_NAME)
    manifest_sha256 = sha256_file(root / MANIFEST_NAME)
    if (
        materials_sha256 != expected_materials_sha256
        or manifest_sha256 != expected_manifest_sha256
    ):
        raise HandoffError("handoff manifest identities changed after semantic validation")
    suite = manifest.get("suite")
    request = manifest.get("request")
    tree = manifest.get("tree")
    if (
        not isinstance(suite, Mapping)
        or not isinstance(request, Mapping)
        or not isinstance(tree, Mapping)
    ):
        raise HandoffError("handoff manifest identities are malformed")
    directory_paths = _tree_directory_paths(root, require_frozen=False)
    declared_directory_paths = tree.get("directory_paths")
    declared_directory_hash = tree.get("directory_paths_sha256")
    if (
        not isinstance(declared_directory_paths, list)
        or any(not isinstance(item, str) for item in declared_directory_paths)
        or tuple(declared_directory_paths) != directory_paths
        or declared_directory_hash != _canonical_sha256(list(directory_paths))
    ):
        raise HandoffError("handoff directory identity differs from its manifest")
    return {
        "schema_version": HANDOFF_RECEIPT_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "handoff_manifest_sha256": manifest_sha256,
        "materials_sha256": materials_sha256,
        "material_file_count": len(materials),
        "material_records_sha256": _canonical_sha256(materials),
        "handoff_file_count": len(materials) + 1,
        "request": dict(request),
        "request_mode": request_mode,
        "suite": dict(suite),
        "tree": dict(tree),
        "source_scope": manifest.get("source_scope"),
        "evidence_records": evidence_records,
        "phase_state": dict(_PHASE_STATE),
        "dlp": dict(dlp),
        "real_provider_calls": 0,
        "provider_calls_authorized": False,
    }


def _rename_no_replace_at(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source_name)
    destination_bytes = os.fsencode(destination_name)
    ctypes.set_errno(0)
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        function = libc.renameatx_np
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(
            source_parent_fd,
            source_bytes,
            destination_parent_fd,
            destination_bytes,
            0x00000004,
        )
    elif hasattr(libc, "renameat2"):
        function = libc.renameat2
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(
            source_parent_fd,
            source_bytes,
            destination_parent_fd,
            destination_bytes,
            1,
        )
    else:
        raise HandoffError("atomic no-replace rename is unavailable on this platform")
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise HandoffError("handoff publication target appeared concurrently")
        raise HandoffError(f"atomic handoff publication failed with errno {error}")


def _rename_exchange_at(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    """Atomically exchange two existing names on the same filesystem.

    The exchange is used only to replace a staged inode with a freshly written
    inode.  A pre-existing writable descriptor therefore remains attached to
    the detached old inode and cannot mutate the bytes that will be published.
    """

    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source_name)
    destination_bytes = os.fsencode(destination_name)
    ctypes.set_errno(0)
    # RENAME_SWAP (Darwin) and RENAME_EXCHANGE (Linux) both use flag 0x2.
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        function = libc.renameatx_np
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(
            source_parent_fd,
            source_bytes,
            destination_parent_fd,
            destination_bytes,
            0x00000002,
        )
    elif hasattr(libc, "renameat2"):
        function = libc.renameat2
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(
            source_parent_fd,
            source_bytes,
            destination_parent_fd,
            destination_bytes,
            0x00000002,
        )
    else:
        raise HandoffError("atomic inode exchange is unavailable on this platform")
    if result != 0:
        error = ctypes.get_errno()
        raise HandoffError(f"atomic staged inode exchange failed with errno {error}")


def _copy_open_file_to_descriptor(
    source_fd: int,
    destination_fd: int,
    *,
    expected_state: os.stat_result,
    expected_sha256: str,
    label: str,
) -> None:
    """Copy and hash a held source FD while checking its state before/after."""

    try:
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or _state_identity(before) != _state_identity(expected_state)
        ):
            raise HandoffError(f"{label} changed before inode refresh")
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            block = os.pread(
                source_fd,
                min(1024 * 1024, before.st_size - offset),
                offset,
            )
            if not block:
                raise HandoffError(f"{label} became shorter during inode refresh")
            digest.update(block)
            view = memoryview(block)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise HandoffError(f"{label} refresh destination write was incomplete")
                view = view[written:]
            offset += len(block)
        after = os.fstat(source_fd)
        if _state_identity(after) != _state_identity(before):
            raise HandoffError(f"{label} changed while its inode was refreshed")
        if digest.hexdigest() != expected_sha256:
            raise HandoffError(f"{label} differs from its sealed payload")
    except OSError as exc:
        raise HandoffError(f"{label} could not be refreshed safely") from exc


def _refresh_regular_inode(
    path: Path,
    *,
    expected_sha256: str,
    label: str,
    expected_mode: int = FROZEN_FILE_MODE,
    detached_sentinels: list[_DetachedInode] | None = None,
    _bound_parent_fd: int | None = None,
    _bound_name: str | None = None,
) -> None:
    """Replace a staged regular file with a byte-identical fresh inode.

    This runs while staging parents are writable, before the permission freeze.
    Any descriptor opened before this function continues to reference the old
    inode after the exchange, which closes the otherwise unavoidable held-FD
    mutation path during publication and verification.
    """

    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise HandoffError(f"{label} expected hash is invalid")
    if expected_mode not in {FORMAL_EVIDENCE_FILE_MODE, FROZEN_FILE_MODE}:
        raise HandoffError(f"{label} expected mode is not allowlisted")
    if (_bound_parent_fd is None) != (_bound_name is None):
        raise HandoffError(f"{label} bound parent and name must be supplied together")
    if _bound_parent_fd is not None:
        if (
            not isinstance(_bound_name, str)
            or not _bound_name
            or "/" in _bound_name
            or _bound_name in {".", ".."}
        ):
            raise HandoffError(f"{label} name is not canonical")
        _validate_path_unicode(_bound_name, label)
        name = _bound_name
        try:
            parent_fd = os.dup(_bound_parent_fd)
        except OSError as exc:
            raise HandoffError(f"{label} parent could not be duplicated safely") from exc
    else:
        _absolute, name, parent_fd = _parent_fd(path, label)
    source_fd: int | None = None
    refresh_fd: int | None = None
    refresh_name = f".{name}.inode-refresh-{uuid.uuid4().hex}"
    refresh_state: os.stat_result | None = None
    source_state: os.stat_result | None = None
    try:
        if not stat.S_ISDIR(os.fstat(parent_fd).st_mode):
            raise HandoffError(f"{label} parent is not a directory")
        _reject_component_alias(parent_fd, name, label)
        source_state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(source_state.st_mode) or source_state.st_nlink != 1:
            raise HandoffError(f"{label} must be a unique regular file")
        source_fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        if _state_identity(os.fstat(source_fd)) != _state_identity(source_state):
            raise HandoffError(f"{label} changed while it was opened")
        refresh_fd = os.open(
            refresh_name,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        refresh_state = os.fstat(refresh_fd)
        _copy_open_file_to_descriptor(
            source_fd,
            refresh_fd,
            expected_state=source_state,
            expected_sha256=expected_sha256,
            label=label,
        )
        os.fchmod(refresh_fd, expected_mode)
        os.fsync(refresh_fd)
        refresh_state = os.fstat(refresh_fd)
        if (
            not stat.S_ISREG(refresh_state.st_mode)
            or refresh_state.st_nlink != 1
            or stat.S_IMODE(refresh_state.st_mode) != expected_mode
            or refresh_state.st_size != source_state.st_size
            or _sha256_open_file(
                refresh_fd,
                expected_state=refresh_state,
                label=f"{label} refreshed inode",
            )
            != expected_sha256
        ):
            raise HandoffError(f"{label} refreshed inode failed validation")
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _state_identity(current) != _state_identity(source_state):
            raise HandoffError(f"{label} changed before inode exchange")
        # Rehash the source immediately before the exchange.  If a pre-opened
        # descriptor changed the old inode after the copy, fail closed; if it
        # changes after this point, the fresh inode is already independent.
        if (
            _sha256_open_file(
                source_fd,
                expected_state=source_state,
                label=f"{label} source inode",
            )
            != expected_sha256
        ):
            raise HandoffError(f"{label} source changed before inode exchange")
        _rename_exchange_at(parent_fd, refresh_name, parent_fd, name)
        destination_state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(destination_state.st_mode)
            or destination_state.st_nlink != 1
            or stat.S_IMODE(destination_state.st_mode) != expected_mode
        ):
            raise HandoffError(f"{label} exchanged inode is not sealed")
        destination_fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            if (
                _state_identity(os.fstat(destination_fd))
                != _state_identity(destination_state)
                or _sha256_open_file(
                    destination_fd,
                    expected_state=destination_state,
                    label=f"{label} published inode",
                )
                != expected_sha256
            ):
                raise HandoffError(f"{label} exchanged inode differs from its payload")
            rebound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if _state_identity(rebound) != _state_identity(destination_state):
                raise HandoffError(f"{label} changed after inode exchange")
        finally:
            os.close(destination_fd)
        # The exchange leaves the old inode under refresh_name.  Remove only
        # that exact inode; a concurrent replacement is retained for diagnosis.
        old_state = os.stat(refresh_name, dir_fd=parent_fd, follow_symlinks=False)
        if _rollback_node_identity(old_state) == _rollback_node_identity(source_state):
            os.unlink(refresh_name, dir_fd=parent_fd)
        else:
            raise HandoffError(f"{label} old inode identity changed during exchange")
        if detached_sentinels is not None:
            # The old inode is now unlinked but remains observable through the
            # source FD.  Retain it as a mutation sentinel until publication
            # commits; this lets us fail closed if a producer keeps writing to
            # a descriptor it opened before the refresh.
            detached_state = os.fstat(source_fd)
            detached_sentinels.append(
                _DetachedInode(
                    descriptor=source_fd,
                    state=detached_state,
                    sha256=expected_sha256,
                    label=label,
                )
            )
            source_fd = None
        refresh_name = ""
    except OSError as exc:
        raise HandoffError(f"{label} inode refresh failed safely") from exc
    finally:
        if refresh_fd is not None:
            try:
                os.close(refresh_fd)
            except OSError:
                pass
        if source_fd is not None:
            try:
                os.close(source_fd)
            except OSError:
                pass
        if refresh_name:
            try:
                candidate = os.stat(refresh_name, dir_fd=parent_fd, follow_symlinks=False)
                if refresh_state is None or _rollback_node_identity(candidate) == _rollback_node_identity(refresh_state):
                    os.unlink(refresh_name, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


def _verify_detached_inodes(sentinels: Sequence[_DetachedInode]) -> None:
    """Reject writes made through descriptors detached during inode refresh."""

    for sentinel in sentinels:
        try:
            digest = _sha256_open_file(
                sentinel.descriptor,
                expected_state=sentinel.state,
                allow_unlinked=True,
                label=f"{sentinel.label} detached sentinel",
            )
        except HandoffError as exc:
            # The low-level helper quite correctly reports an identity/metadata
            # mismatch for a detached inode.  Keep the public failure useful by
            # translating that implementation detail into the sentinel contract.
            raise HandoffError(
                f"{sentinel.label} changed through a detached descriptor"
            ) from exc
        if digest != sentinel.sha256:
            raise HandoffError(f"{sentinel.label} changed through a detached descriptor")


def _refresh_staged_tree_inodes(
    root: Path,
    *,
    expected_materials_sha256: str,
    expected_manifest_sha256: str,
    detached_sentinels: list[_DetachedInode] | None = None,
    _bound_root_fd: int | None = None,
) -> None:
    """Detach all pre-existing writable file descriptors before freezing."""

    if _bound_root_fd is None:
        absolute, root_fd = _open_directory_fd(root, "handoff staging tree")
    else:
        absolute = _absolute_path(root, "handoff staging tree")
        try:
            root_fd = os.dup(_bound_root_fd)
        except OSError as exc:
            raise HandoffError("handoff staging tree could not be duplicated safely") from exc
    root_state = os.fstat(root_fd)
    if not stat.S_ISDIR(root_state.st_mode):
        os.close(root_fd)
        raise HandoffError("handoff staging tree must be a real directory")

    file_paths: tuple[str, ...] | None = None
    directory_records: tuple[tuple[str, tuple[int, ...]], ...] | None = None
    directory_handles: dict[str, tuple[int, int]] = {}
    thawed: list[tuple[int, int]] = []
    try:
        # Do not apply the public fixed-layout contract here: this helper is also
        # used by low-level publication tests with a deliberately small tree.
        # The complete file and directory sets are nevertheless bound to this
        # held root before any inode exchange can create a sibling entry.
        file_paths, directory_records = _tree_closed_set_from_fd(
            root_fd,
            require_frozen=False,
        )
        for relative, expected_identity in directory_records:
            descriptor = _open_relative_directory_fd(
                root_fd,
                relative,
                "staged handoff directory",
            )
            state = os.fstat(descriptor)
            if _directory_snapshot_identity(state) != expected_identity:
                os.close(descriptor)
                raise HandoffError("staged handoff directory changed while it was bound")
            directory_handles[relative] = (
                descriptor,
                stat.S_IMODE(state.st_mode),
            )

        materials_payload = _read_regular_bytes_at(
            root_fd,
            MATERIALS_NAME,
            "materials manifest",
        )
        if hashlib.sha256(materials_payload).hexdigest() != expected_materials_sha256:
            raise HandoffError("materials manifest changed before inode refresh")
        records = _parse_materials_payload(materials_payload)
        expected_paths = tuple(
            sorted((MATERIALS_NAME, *(record["path"] for record in records)))
        )
        if file_paths != expected_paths:
            raise HandoffError("materials manifest changed before inode refresh")
        targets: list[tuple[str, str]] = [
            (MATERIALS_NAME, expected_materials_sha256)
        ]
        targets.extend((record["path"], record["sha256"]) for record in records)
        manifest_hashes = [
            digest for path, digest in targets if path == MANIFEST_NAME
        ]
        if manifest_hashes != [expected_manifest_sha256]:
            raise HandoffError("handoff manifest hash differs before inode refresh")

        # A retry after a failed publication may have already frozen the
        # directories. Temporarily restore owner-write permission on the exact
        # held directory objects, then restore those modes in the finally block.
        for descriptor, mode in directory_handles.values():
            if not mode & stat.S_IWUSR:
                os.fchmod(descriptor, mode | stat.S_IWUSR)
                thawed.append((descriptor, mode))
        for relative, digest in targets:
            relative_path = PurePosixPath(relative)
            parent_relative = (
                ""
                if relative_path.parent == PurePosixPath(".")
                else relative_path.parent.as_posix()
            )
            parent_handle = directory_handles.get(parent_relative)
            if parent_handle is None:
                raise HandoffError("staged file parent is outside the bound tree")
            _refresh_regular_inode(
                root / Path(relative),
                expected_sha256=digest,
                label=f"staged file {relative}",
                expected_mode=_sealed_file_mode(relative),
                detached_sentinels=detached_sentinels,
                _bound_parent_fd=parent_handle[0],
                _bound_name=relative_path.name,
            )
    finally:
        restore_error: OSError | None = None
        for descriptor, mode in reversed(thawed):
            try:
                os.fchmod(descriptor, mode)
            except OSError as exc:
                if restore_error is None:
                    restore_error = exc
        for descriptor, _mode in directory_handles.values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if file_paths is not None and directory_records is not None:
                terminal_files, terminal_directories = _tree_closed_set_from_fd(
                    root_fd,
                    require_frozen=False,
                )
                if (
                    terminal_files != file_paths
                    or tuple(path for path, _state in terminal_directories)
                    != tuple(path for path, _state in directory_records)
                ):
                    raise HandoffError("staged handoff tree changed during inode refresh")
            _verify_named_open_directory(
                path=absolute,
                descriptor=root_fd,
                expected_inode=root_state,
                label="handoff staging tree after inode refresh",
            )
        finally:
            os.close(root_fd)
        if restore_error is not None:
            raise HandoffError(
                "staged handoff directory mode could not be restored"
            ) from restore_error


def _rename_no_replace(source: Path, destination: Path) -> None:
    _source_absolute, source_name, source_parent_fd = _parent_fd(
        source,
        "rename source",
    )
    _destination_absolute, destination_name, destination_parent_fd = _parent_fd(
        destination,
        "rename destination",
    )
    try:
        _rename_no_replace_at(
            source_parent_fd,
            source_name,
            destination_parent_fd,
            destination_name,
        )
    finally:
        os.close(source_parent_fd)
        os.close(destination_parent_fd)


def _fsync_tree_directories(
    root: Path,
    *,
    _bound_root_fd: int | None = None,
) -> None:
    if _bound_root_fd is None:
        absolute, root_fd = _open_directory_fd(root, "handoff staging tree")
    else:
        absolute = _absolute_path(root, "handoff staging tree")
        try:
            root_fd = os.dup(_bound_root_fd)
        except OSError as exc:
            raise HandoffError("handoff staging tree could not be duplicated safely") from exc
    root_state = os.fstat(root_fd)
    handles: list[tuple[str, int]] = []
    try:
        file_paths, directory_records = _tree_closed_set_from_fd(
            root_fd,
            require_frozen=True,
        )
        for relative, expected_identity in directory_records:
            descriptor = _open_relative_directory_fd(
                root_fd,
                relative,
                "handoff staging directory",
            )
            if _directory_snapshot_identity(os.fstat(descriptor)) != expected_identity:
                os.close(descriptor)
                raise HandoffError("handoff staging directory changed before fsync")
            handles.append((relative, descriptor))
        for _relative, descriptor in sorted(
            handles,
            key=lambda item: (-len(PurePosixPath(item[0]).parts), item[0]),
        ):
            os.fsync(descriptor)
        terminal_files, terminal_directories = _tree_closed_set_from_fd(
            root_fd,
            require_frozen=True,
        )
        if (
            terminal_files != file_paths
            or tuple(path for path, _state in terminal_directories)
            != tuple(path for path, _state in directory_records)
        ):
            raise HandoffError("handoff staging tree changed during directory fsync")
        _verify_named_open_directory(
            path=absolute,
            descriptor=root_fd,
            expected_inode=root_state,
            label="handoff staging tree after directory fsync",
        )
    except OSError as exc:
        raise HandoffError("handoff staging directories could not be synced safely") from exc
    finally:
        for _relative, descriptor in handles:
            try:
                os.close(descriptor)
            except OSError:
                pass
        os.close(root_fd)


def _freeze_tree_permissions(
    root: Path,
    *,
    _bound_root_fd: int | None = None,
) -> None:
    """Make the sealed staging copy read-only before publication starts."""

    if _bound_root_fd is None:
        absolute, root_fd = _open_directory_fd(root, "handoff staging tree")
    else:
        absolute = _absolute_path(root, "handoff staging tree")
        try:
            root_fd = os.dup(_bound_root_fd)
        except OSError as exc:
            raise HandoffError("handoff staging tree could not be duplicated safely") from exc
    root_state = os.fstat(root_fd)
    directory_handles: list[tuple[str, int]] = []
    try:
        file_paths, directory_records = _tree_closed_set_from_fd(
            root_fd,
            require_frozen=False,
        )
        for relative, expected_identity in directory_records:
            descriptor = _open_relative_directory_fd(
                root_fd,
                relative,
                "handoff staging directory",
            )
            if _directory_snapshot_identity(os.fstat(descriptor)) != expected_identity:
                os.close(descriptor)
                raise HandoffError("handoff staging directory changed before permission freeze")
            directory_handles.append((relative, descriptor))

        for relative in file_paths:
            name, parent_fd = _open_relative_parent_fd(
                root_fd,
                relative,
                "handoff staging file",
            )
            descriptor: int | None = None
            try:
                before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise HandoffError("handoff staging file is not a unique regular file")
                descriptor = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_fd,
                )
                if _state_identity(os.fstat(descriptor)) != _state_identity(before):
                    raise HandoffError("handoff staging file changed before permission freeze")
                expected_mode = _sealed_file_mode(relative)
                os.fchmod(descriptor, expected_mode)
                os.fsync(descriptor)
                after_fd = os.fstat(descriptor)
                after_name = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    _state_identity(after_fd) != _state_identity(after_name)
                    or stat.S_IMODE(after_fd.st_mode) != expected_mode
                ):
                    raise HandoffError("handoff staging file changed during permission freeze")
            except OSError as exc:
                raise HandoffError("handoff staging file could not be frozen") from exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                os.close(parent_fd)

        for _relative, descriptor in sorted(
            directory_handles,
            key=lambda item: (-len(PurePosixPath(item[0]).parts), item[0]),
        ):
            os.fchmod(descriptor, FROZEN_DIRECTORY_MODE)
            os.fsync(descriptor)
            _require_frozen_mode(
                os.fstat(descriptor),
                expected=FROZEN_DIRECTORY_MODE,
                label="handoff staging directory",
            )
        terminal_files, terminal_directories = _tree_closed_set_from_fd(
            root_fd,
            require_frozen=True,
        )
        if (
            terminal_files != file_paths
            or tuple(path for path, _state in terminal_directories)
            != tuple(path for path, _state in directory_records)
        ):
            raise HandoffError("handoff staging tree changed during permission freeze")
        _verify_named_open_directory(
            path=absolute,
            descriptor=root_fd,
            expected_inode=root_state,
            label="handoff staging tree after permission freeze",
        )
    except OSError as exc:
        raise HandoffError("handoff staging tree could not be frozen") from exc
    finally:
        for _relative, descriptor in directory_handles:
            try:
                os.close(descriptor)
            except OSError:
                pass
        os.close(root_fd)


def _open_held_tree_file(
    root: Path,
    *,
    relative_path: str,
    expected_sha256: str,
) -> _HeldTreeFile:
    relative = _canonical_relative(relative_path, "sealed tree path")
    expected_mode = _sealed_file_mode(relative)
    _absolute, name, parent_fd = _parent_fd(
        root / Path(relative),
        "sealed tree file",
    )
    descriptor: int | None = None
    try:
        state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(state.st_mode) or state.st_nlink != 1:
            raise HandoffError("sealed tree file must be a unique regular file")
        _require_frozen_mode(
            state,
            expected=expected_mode,
            label="sealed tree file",
        )
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        if _state_identity(os.fstat(descriptor)) != _state_identity(state):
            raise HandoffError("sealed tree file changed while it was opened")
        if (
            _sha256_open_file(
                descriptor,
                expected_state=state,
                label=f"sealed tree file {relative}",
            )
            != expected_sha256
        ):
            raise HandoffError("sealed tree file differs from MATERIALS.sha256")
        return _HeldTreeFile(
            relative_path=relative,
            sha256=expected_sha256,
            state=state,
            descriptor=descriptor,
            sealed_mode=expected_mode,
        )
    except Exception as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise HandoffError("sealed tree file could not be opened safely") from exc
        raise
    finally:
        os.close(parent_fd)


def _held_tree_path_state(root: Path, relative_path: str) -> os.stat_result:
    relative = _canonical_relative(relative_path, "sealed tree path")
    _absolute, name, parent_fd = _parent_fd(
        root / Path(relative),
        "sealed tree file",
    )
    try:
        state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(state.st_mode) or state.st_nlink != 1:
            raise HandoffError("sealed tree path is not a unique regular file")
        _require_frozen_mode(
            state,
            expected=_sealed_file_mode(relative),
            label="sealed tree path",
        )
        return state
    except OSError as exc:
        raise HandoffError("sealed tree path could not be inspected safely") from exc
    finally:
        os.close(parent_fd)


def _tree_closed_set_from_fd(
    root_fd: int,
    *,
    require_frozen: bool = True,
) -> tuple[tuple[str, ...], tuple[tuple[str, tuple[int, ...]], ...]]:
    """Inspect the complete regular-file and directory sets from a held root FD.

    The two sets are collected in one descriptor-relative walk so a terminal
    publication probe can reject an extra file, symlink, or directory branch
    instead of checking only the files that were present in its original
    snapshot.
    """

    file_paths: list[str] = []
    directory_records: dict[str, tuple[int, ...]] = {}
    try:
        for current, child_directories, names, current_fd in os.fwalk(
            ".",
            topdown=True,
            follow_symlinks=False,
            dir_fd=root_fd,
        ):
            relative_parent = "" if current == "." else current.removeprefix("./")
            if relative_parent:
                _canonical_relative(relative_parent, "sealed handoff directory")
            current_state = os.fstat(current_fd)
            if not stat.S_ISDIR(current_state.st_mode):
                raise HandoffError("sealed handoff tree contains a special directory")
            if require_frozen:
                _require_frozen_mode(
                    current_state,
                    expected=FROZEN_DIRECTORY_MODE,
                    label="sealed handoff directory",
                )
            if relative_parent in directory_records:
                raise HandoffError("sealed handoff tree contains a duplicate directory")
            directory_records[relative_parent] = _directory_snapshot_identity(current_state)

            # fwalk may return a node in either list while a producer changes
            # the tree.  Inspect every entry explicitly before accepting it.
            child_directories.sort()
            names.sort()
            for child_name in child_directories:
                _reject_component_alias(current_fd, child_name, "sealed handoff directory")
                child_state = os.stat(
                    child_name,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
                if stat.S_ISLNK(child_state.st_mode) or not stat.S_ISDIR(
                    child_state.st_mode
                ):
                    raise HandoffError("sealed handoff tree contains a special directory")
                if require_frozen:
                    _require_frozen_mode(
                        child_state,
                        expected=FROZEN_DIRECTORY_MODE,
                        label="sealed handoff directory",
                    )
                relative = (
                    f"{relative_parent}/{child_name}"
                    if relative_parent
                    else child_name
                )
                _canonical_relative(relative, "sealed handoff directory")
            for name in names:
                _reject_component_alias(current_fd, name, "sealed handoff file")
                state = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
                if (
                    stat.S_ISLNK(state.st_mode)
                    or not stat.S_ISREG(state.st_mode)
                    or state.st_nlink != 1
                ):
                    raise HandoffError("sealed handoff tree contains a symlink or special file")
                relative = f"{relative_parent}/{name}" if relative_parent else name
                relative = _canonical_relative(relative, "sealed handoff file")
                if require_frozen:
                    _require_frozen_mode(
                        state,
                        expected=_sealed_file_mode(relative),
                        label="sealed handoff file",
                    )
                file_paths.append(relative)
        return tuple(sorted(file_paths)), tuple(sorted(directory_records.items()))
    except HandoffError:
        raise
    except (OSError, ValueError) as exc:
        raise HandoffError("sealed handoff tree closed set could not be inspected safely") from exc


def _tree_regular_paths_from_fd(
    root_fd: int,
    *,
    require_frozen: bool = True,
) -> tuple[str, ...]:
    """Return the complete regular-file set relative to a held root FD."""

    files, _directories = _tree_closed_set_from_fd(
        root_fd,
        require_frozen=require_frozen,
    )
    return files


def _tree_directory_state_records_from_fd(
    root_fd: int,
    *,
    require_frozen: bool = True,
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Inspect a complete directory tree relative to a held root FD.

    Walking from a descriptor avoids resolving a path alias between entries and
    also gives rollback a way to inspect a directory after its formal name has
    been renamed.  The returned identities intentionally omit ctime; see
    :func:`_directory_snapshot_identity`.
    """

    _files, directories = _tree_closed_set_from_fd(
        root_fd,
        require_frozen=require_frozen,
    )
    return directories


def _tree_directory_state_records(
    root: Path,
    *,
    require_frozen: bool = True,
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    absolute, root_fd = _open_directory_fd(root, "sealed handoff tree")
    expected_root_state = os.fstat(root_fd)
    try:
        records = _tree_directory_state_records_from_fd(
            root_fd,
            require_frozen=require_frozen,
        )
        _verify_named_open_directory(
            path=absolute,
            descriptor=root_fd,
            expected_inode=expected_root_state,
            label="sealed handoff tree",
        )
        return records
    finally:
        os.close(root_fd)


def _sealed_closed_set(
    root: Path,
    *,
    expected_root_state: os.stat_result,
    label: str = "sealed handoff tree",
) -> tuple[tuple[str, ...], tuple[tuple[str, tuple[int, ...]], ...]]:
    """Collect a sealed tree's file and directory sets while holding its root FD."""

    _absolute, root_fd = _open_directory_fd(root, label)
    try:
        current_root_state = os.fstat(root_fd)
        if (
            _published_node_identity(current_root_state)
            != _published_node_identity(expected_root_state)
            or stat.S_IMODE(current_root_state.st_mode) != FROZEN_DIRECTORY_MODE
        ):
            raise HandoffError(f"{label} changed at closed-set barrier")
        return _tree_closed_set_from_fd(root_fd, require_frozen=True)
    finally:
        os.close(root_fd)


def _tree_directory_paths(
    root: Path,
    *,
    require_frozen: bool = True,
) -> tuple[str, ...]:
    """Return the complete canonical directory set, including the root.

    Manifest construction runs before the staging tree is permission-frozen,
    while publication/verification runs after the freeze.  The caller chooses
    which mode is appropriate; both paths use the same descriptor-relative
    traversal and reject symlink/special directories.
    """

    return tuple(
        path
        for path, _identity in _tree_directory_state_records(
            root,
            require_frozen=require_frozen,
        )
    )


def _rebind_held_tree_snapshot(
    *,
    root: Path,
    expected_root_state: os.stat_result,
    snapshot: Sequence[_HeldTreeFile],
) -> None:
    root = _absolute_path(root, "sealed handoff tree")
    _absolute, root_fd = _open_directory_fd(root, "sealed handoff tree")
    try:
        root_state = os.fstat(root_fd)
        _require_frozen_mode(
            root_state,
            expected=FROZEN_DIRECTORY_MODE,
            label="sealed handoff tree",
        )
        if _published_node_identity(root_state) != _published_node_identity(
            expected_root_state
        ):
            raise HandoffError("sealed handoff tree identity changed")
    finally:
        os.close(root_fd)

    expected_directory_paths = snapshot[0].directory_paths if snapshot else ("",)
    expected_directory_states = snapshot[0].directory_states if snapshot else ()
    discovered_directory_states = _tree_directory_state_records(root)
    discovered_directories = tuple(
        path for path, _identity in discovered_directory_states
    )
    if discovered_directories != expected_directory_paths:
        raise HandoffError("sealed handoff tree directory set changed")
    if expected_directory_states and discovered_directory_states != expected_directory_states:
        raise HandoffError("sealed handoff tree directory identity changed")
    expected_paths = [item.relative_path for item in snapshot]
    discovered = [
        path.relative_to(root).as_posix()
        for path in _walk_regular(root)
    ]
    if discovered != expected_paths:
        raise HandoffError("sealed handoff tree path set changed")
    for item in snapshot:
        descriptor_state = os.fstat(item.descriptor)
        path_state = _held_tree_path_state(root, item.relative_path)
        if (
            _state_identity(descriptor_state) != _state_identity(item.state)
            or _state_identity(path_state) != _state_identity(item.state)
        ):
            raise HandoffError("sealed handoff tree file identity changed")


def _verify_held_tree_snapshot(
    *,
    root: Path,
    expected_root_state: os.stat_result,
    snapshot: Sequence[_HeldTreeFile],
) -> None:
    """Rehash held files, then restat the complete path set as one checkpoint."""

    _rebind_held_tree_snapshot(
        root=root,
        expected_root_state=expected_root_state,
        snapshot=snapshot,
    )
    for item in snapshot:
        if (
            _sha256_open_file(
                item.descriptor,
                expected_state=item.state,
                label=f"sealed tree file {item.relative_path}",
            )
            != item.sha256
        ):
            raise HandoffError("sealed handoff tree file content changed")
    # This barrier catches a mutation after an earlier file was hashed.
    try:
        _rebind_held_tree_snapshot(
            root=root,
            expected_root_state=expected_root_state,
            snapshot=snapshot,
        )
    except HandoffError as exc:
        raise HandoffError("sealed handoff tree changed during verification") from exc


def _open_held_tree_snapshot(
    *,
    root: Path,
    expected_root_state: os.stat_result,
    expected_materials_sha256: str,
    expected_manifest_sha256: str,
) -> list[_HeldTreeFile]:
    if not SHA256_PATTERN.fullmatch(expected_materials_sha256):
        raise HandoffError("expected materials manifest hash is invalid")
    if not SHA256_PATTERN.fullmatch(expected_manifest_sha256):
        raise HandoffError("expected handoff manifest hash is invalid")

    snapshot: list[_HeldTreeFile] = []
    try:
        materials = _open_held_tree_file(
            root,
            relative_path=MATERIALS_NAME,
            expected_sha256=expected_materials_sha256,
        )
        snapshot.append(materials)
        payload = _read_open_file_bytes(
            materials.descriptor,
            expected_state=materials.state,
            label="sealed materials manifest",
        )
        records = _parse_materials_payload(payload)
        record_map = {record["path"]: record["sha256"] for record in records}
        if record_map.get(MANIFEST_NAME) != expected_manifest_sha256:
            raise HandoffError("HANDOFF_MANIFEST.json identity differs from the sealed receipt")
        for record in records:
            snapshot.append(
                _open_held_tree_file(
                    root,
                    relative_path=record["path"],
                    expected_sha256=record["sha256"],
                )
            )
        directory_states = _tree_directory_state_records(root)
        directory_paths = tuple(path for path, _identity in directory_states)
        snapshot = [
            replace(
                item,
                directory_paths=directory_paths,
                directory_states=directory_states,
            )
            for item in snapshot
        ]
        snapshot.sort(key=lambda item: item.relative_path)
        _verify_held_tree_snapshot(
            root=root,
            expected_root_state=expected_root_state,
            snapshot=snapshot,
        )
        return snapshot
    except Exception:
        for item in snapshot:
            try:
                os.close(item.descriptor)
            except OSError:
                pass
        raise


def _sha256_open_file_final(
    descriptor: int,
    *,
    expected_state: os.stat_result,
    expected_mode: int = FROZEN_FILE_MODE,
    label: str,
) -> str:
    """Hash a held file for the final barrier without calling probe helpers."""

    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or _state_identity(before) != _state_identity(expected_state)
            or stat.S_IMODE(before.st_mode) != expected_mode
        ):
            raise HandoffError(f"{label} is not the sealed regular file")
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            block = os.pread(
                descriptor,
                min(1024 * 1024, before.st_size - offset),
                offset,
            )
            if not block:
                raise HandoffError(f"{label} became shorter while hashing")
            digest.update(block)
            offset += len(block)
        after = os.fstat(descriptor)
        if _state_identity(after) != _state_identity(before):
            raise HandoffError(f"{label} changed while hashing")
        return digest.hexdigest()
    except OSError as exc:
        raise HandoffError(f"{label} could not be hashed safely") from exc


def _final_snapshot_probe(
    *,
    root: Path,
    expected_root_state: os.stat_result,
    snapshot: Sequence[_HeldTreeFile],
    receipt_parent_fd: int,
    receipt_name: str,
    receipt_fd: int,
    receipt_state: os.stat_result,
    expected_receipt_sha256: str,
) -> None:
    """Perform bounded, self-contained cross-object consistency checks.

    The terminal pass deliberately rechecks the complete tree *after* the
    receipt pass.  This catches a mutation of an earlier tree entry or a
    directory set change that occurs while the preceding pass is in flight.
    Inode refresh before publication removes pre-open writable descriptors from
    the published names; this probe remains a bounded concurrent-writer check,
    not a claim of kernel-level immutability against a privileged writer.
    """

    expected_paths = tuple(item.relative_path for item in snapshot)
    expected_directories = snapshot[0].directory_paths if snapshot else ("",)
    expected_directory_states = snapshot[0].directory_states if snapshot else ()
    for _attempt in range(2):
        current_paths, current_directory_states = _sealed_closed_set(
            root,
            expected_root_state=expected_root_state,
        )
        if current_paths != expected_paths:
            raise HandoffError("sealed handoff tree file set changed at final barrier")
        if tuple(path for path, _identity in current_directory_states) != expected_directories:
            raise HandoffError("sealed handoff tree directory set changed at final barrier")
        if expected_directory_states and current_directory_states != expected_directory_states:
            raise HandoffError("sealed handoff tree directory identity changed at final barrier")
        for item in snapshot:
            descriptor_state = os.fstat(item.descriptor)
            path_state = _held_tree_path_state(root, item.relative_path)
            if (
                _state_identity(descriptor_state) != _state_identity(item.state)
                or _state_identity(path_state) != _state_identity(item.state)
                or stat.S_IMODE(descriptor_state.st_mode) != item.sealed_mode
                or stat.S_IMODE(path_state.st_mode) != item.sealed_mode
            ):
                raise HandoffError("sealed handoff tree file changed at final barrier")
            if (
                _sha256_open_file_final(
                    item.descriptor,
                    expected_state=item.state,
                    expected_mode=item.sealed_mode,
                    label=f"sealed handoff tree file {item.relative_path}",
                )
                != item.sha256
            ):
                raise HandoffError("sealed handoff tree file differs at final barrier")

        receipt_fd_state = os.fstat(receipt_fd)
        receipt_path_state = os.stat(
            receipt_name,
            dir_fd=receipt_parent_fd,
            follow_symlinks=False,
        )
        if (
            _state_identity(receipt_fd_state) != _state_identity(receipt_state)
            or _state_identity(receipt_path_state) != _state_identity(receipt_state)
            or stat.S_IMODE(receipt_fd_state.st_mode) != FROZEN_FILE_MODE
            or stat.S_IMODE(receipt_path_state.st_mode) != FROZEN_FILE_MODE
        ):
            raise HandoffError("detached receipt changed at final barrier")
        if (
            _sha256_open_file_final(
                receipt_fd,
                expected_state=receipt_state,
                label="detached handoff receipt",
            )
            != expected_receipt_sha256
        ):
            raise HandoffError("detached receipt differs at final barrier")
        receipt_fd_after = os.fstat(receipt_fd)
        receipt_path_after = os.stat(
            receipt_name,
            dir_fd=receipt_parent_fd,
            follow_symlinks=False,
        )
        if (
            _state_identity(receipt_fd_after) != _state_identity(receipt_fd_state)
            or _state_identity(receipt_path_after) != _state_identity(receipt_fd_state)
        ):
            raise HandoffError("detached receipt changed during final barrier")

    # Terminal tree pass: the prior loop ends with a receipt check, so a
    # callback that changes an earlier file or adds an empty directory during
    # that receipt check must be observed before the commit decision.
    terminal_paths, terminal_directory_states = _sealed_closed_set(
        root,
        expected_root_state=expected_root_state,
    )
    if terminal_paths != expected_paths:
        raise HandoffError("sealed handoff tree file set changed at terminal barrier")
    for item in snapshot:
        descriptor_state = os.fstat(item.descriptor)
        path_state = _held_tree_path_state(root, item.relative_path)
        if (
            _state_identity(descriptor_state) != _state_identity(item.state)
            or _state_identity(path_state) != _state_identity(item.state)
            or stat.S_IMODE(descriptor_state.st_mode) != item.sealed_mode
            or stat.S_IMODE(path_state.st_mode) != item.sealed_mode
            or _sha256_open_file_final(
                item.descriptor,
                expected_state=item.state,
                expected_mode=item.sealed_mode,
                label=f"sealed handoff tree file {item.relative_path}",
            )
            != item.sha256
        ):
            raise HandoffError("sealed handoff tree differs at terminal barrier")
    # Recheck the directory set after the final file hash as well; otherwise an
    # empty-directory insertion at the end of the scan could go unnoticed.
    if tuple(path for path, _identity in terminal_directory_states) != expected_directories:
        raise HandoffError("sealed handoff tree directory set changed at terminal barrier")
    if expected_directory_states and terminal_directory_states != expected_directory_states:
        raise HandoffError("sealed handoff tree directory identity changed at terminal barrier")
    receipt_fd_state = os.fstat(receipt_fd)
    receipt_path_state = os.stat(
        receipt_name,
        dir_fd=receipt_parent_fd,
        follow_symlinks=False,
    )
    if (
        _state_identity(receipt_fd_state) != _state_identity(receipt_state)
        or _state_identity(receipt_path_state) != _state_identity(receipt_state)
        or stat.S_IMODE(receipt_fd_state.st_mode) != FROZEN_FILE_MODE
        or stat.S_IMODE(receipt_path_state.st_mode) != FROZEN_FILE_MODE
        or _sha256_open_file_final(
            receipt_fd,
            expected_state=receipt_state,
            label="detached handoff receipt",
        )
        != expected_receipt_sha256
    ):
        raise HandoffError("detached receipt differs at terminal barrier")


def _final_cross_object_barrier(
    *,
    root: Path,
    expected_root_state: os.stat_result,
    snapshot: Sequence[_HeldTreeFile],
    receipt_parent_fd: int,
    receipt_name: str,
    receipt_fd: int,
    receipt_state: os.stat_result,
    expected_receipt_sha256: str,
    label_prefix: str,
) -> None:
    """Recheck both published objects after all preceding identity checks.

    Two alternating passes close the cross-object window where a callback or a
    concurrent writer changes one object while the other object is being
    checked.  The final inode rebinds retain the held descriptors as the
    authoritative snapshot for the commit decision.
    """

    _verify_held_tree_snapshot(
        root=root,
        expected_root_state=expected_root_state,
        snapshot=snapshot,
    )
    _verify_named_open_file(
        parent_fd=receipt_parent_fd,
        name=receipt_name,
        descriptor=receipt_fd,
        expected_inode=receipt_state,
        expected_sha256=expected_receipt_sha256,
        label=f"{label_prefix} receipt content barrier",
    )
    _verify_held_tree_snapshot(
        root=root,
        expected_root_state=expected_root_state,
        snapshot=snapshot,
    )
    _verify_named_open_file(
        parent_fd=receipt_parent_fd,
        name=receipt_name,
        descriptor=receipt_fd,
        expected_inode=receipt_state,
        expected_sha256=expected_receipt_sha256,
        label=f"{label_prefix} receipt final content barrier",
    )
    _rebind_held_tree_snapshot(
        root=root,
        expected_root_state=expected_root_state,
        snapshot=snapshot,
    )
    _rebind_named_open_file(
        parent_fd=receipt_parent_fd,
        name=receipt_name,
        descriptor=receipt_fd,
        expected_state=receipt_state,
        label=f"{label_prefix} receipt final inode barrier",
    )
    _final_snapshot_probe(
        root=root,
        expected_root_state=expected_root_state,
        snapshot=snapshot,
        receipt_parent_fd=receipt_parent_fd,
        receipt_name=receipt_name,
        receipt_fd=receipt_fd,
        receipt_state=receipt_state,
        expected_receipt_sha256=expected_receipt_sha256,
    )


def _verify_tree_rollback_state(
    *,
    parent_fd: int,
    name: str,
    root_fd: int,
    expected_root_state: os.stat_result,
    snapshot: Sequence[_HeldTreeFile],
    label: str,
) -> None:
    """Prove that a tree is still the exact sealed object before moving it.

    Rollback is itself a publication operation.  Checking only the directory
    inode is insufficient because a same-size in-place write keeps that inode
    intact.  Rebind the held descriptors, verify every byte and mode, and
    compare both the regular-file and complete-directory sets before and after
    the rename.
    """

    try:
        named_root = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        held_root = os.fstat(root_fd)
        if (
            _published_node_identity(named_root)
            != _published_node_identity(expected_root_state)
            or _published_node_identity(held_root)
            != _published_node_identity(expected_root_state)
            or stat.S_IMODE(named_root.st_mode) != FROZEN_DIRECTORY_MODE
            or stat.S_IMODE(held_root.st_mode) != FROZEN_DIRECTORY_MODE
        ):
            raise HandoffError(f"{label} root changed before rollback")

        directory_states: dict[str, tuple[int, ...]] = {}
        path_states: dict[str, os.stat_result] = {}
        for current, child_directories, files, current_fd in os.fwalk(
            ".",
            topdown=True,
            follow_symlinks=False,
            dir_fd=root_fd,
        ):
            relative_parent = "" if current == "." else current.removeprefix("./")
            current_state = os.fstat(current_fd)
            if not stat.S_ISDIR(current_state.st_mode):
                raise HandoffError(f"{label} contains an unsealed directory")
            if stat.S_IMODE(current_state.st_mode) != FROZEN_DIRECTORY_MODE:
                raise HandoffError(f"{label} contains an unsealed directory")
            if relative_parent in directory_states:
                raise HandoffError(f"{label} contains a duplicate directory")
            directory_states[relative_parent] = _directory_snapshot_identity(current_state)
            child_directories.sort()
            files.sort()
            for child_name in child_directories:
                child_state = os.stat(
                    child_name,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
                if (
                    stat.S_ISLNK(child_state.st_mode)
                    or not stat.S_ISDIR(child_state.st_mode)
                    or stat.S_IMODE(child_state.st_mode) != FROZEN_DIRECTORY_MODE
                ):
                    raise HandoffError(f"{label} contains a special or unsealed directory")
                relative = (
                    f"{relative_parent}/{child_name}"
                    if relative_parent
                    else child_name
                )
                _canonical_relative(relative, f"{label} directory")
            for file_name in files:
                file_state = os.stat(
                    file_name,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
                relative = (
                    f"{relative_parent}/{file_name}"
                    if relative_parent
                    else file_name
                )
                relative = _canonical_relative(relative, f"{label} file")
                if (
                    stat.S_ISLNK(file_state.st_mode)
                    or not stat.S_ISREG(file_state.st_mode)
                    or file_state.st_nlink != 1
                    or stat.S_IMODE(file_state.st_mode)
                    != _sealed_file_mode(relative)
                ):
                    raise HandoffError(f"{label} contains a special or unsealed file")
                if relative in path_states:
                    raise HandoffError(f"{label} contains a duplicate file path")
                path_states[relative] = file_state

        expected_directories = snapshot[0].directory_paths if snapshot else ("",)
        discovered_directories = tuple(sorted(directory_states))
        if discovered_directories != expected_directories:
            raise HandoffError(f"{label} directory set changed before rollback")
        expected_directory_states = snapshot[0].directory_states if snapshot else ()
        discovered_directory_states = tuple(sorted(directory_states.items()))
        if expected_directory_states and discovered_directory_states != expected_directory_states:
            raise HandoffError(f"{label} directory identity changed before rollback")
        expected_paths = [item.relative_path for item in snapshot]
        if sorted(path_states) != expected_paths:
            raise HandoffError(f"{label} file set changed before rollback")
        for item in snapshot:
            held_state = os.fstat(item.descriptor)
            path_state = path_states[item.relative_path]
            if (
                _state_identity(held_state) != _state_identity(item.state)
                or _state_identity(path_state) != _state_identity(item.state)
                or stat.S_IMODE(held_state.st_mode) != item.sealed_mode
                or _sha256_open_file_final(
                    item.descriptor,
                    expected_state=item.state,
                    expected_mode=item.sealed_mode,
                    label=f"{label} file {item.relative_path}",
                )
                != item.sha256
            ):
                raise HandoffError(f"{label} content changed before rollback")
    except HandoffError:
        raise
    except (OSError, ValueError) as exc:
        raise HandoffError(f"{label} could not be validated before rollback") from exc


def _verify_tree_after_rollback(
    *,
    parent_fd: int,
    name: str,
    root_fd: int,
    expected_root_state: os.stat_result,
    snapshot: Sequence[_HeldTreeFile],
    label: str,
) -> None:
    """Validate the restored tree after a rollback rename."""

    _verify_tree_rollback_state(
        parent_fd=parent_fd,
        name=name,
        root_fd=root_fd,
        expected_root_state=expected_root_state,
        snapshot=snapshot,
        label=label,
    )


def _named_node_status(
    *,
    parent_fd: int,
    name: str,
    expected_state: os.stat_result,
    expected_descriptor: int | None = None,
) -> str:
    """Classify a publication target without ever claiming a foreign inode.

    When the caller still holds the source descriptor, the name must agree with
    that descriptor's full stat identity.  This closes the inode-number reuse
    case where a deleted inode number is quickly assigned to a competing node.
    """

    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        raise HandoffError("handoff publication target could not be inspected") from exc
    if expected_descriptor is not None:
        try:
            held = os.fstat(expected_descriptor)
        except OSError as exc:
            raise HandoffError("handoff publication source could not be inspected") from exc
        if (
            _rollback_node_identity(current) == _rollback_node_identity(expected_state)
            and _rollback_node_identity(held) == _rollback_node_identity(expected_state)
            and _node_binding_identity(current) == _node_binding_identity(held)
        ):
            return "expected"
        return "foreign"
    if _rollback_node_identity(current) == _rollback_node_identity(expected_state):
        return "expected"
    return "foreign"


def _reconcile_publication_target(
    *,
    destination_parent_fd: int,
    destination_name: str,
    source_parent_fd: int,
    source_name: str,
    expected_state: os.stat_result,
    collision_error: bool,
    expected_descriptor: int | None = None,
) -> str:
    """Reconcile a target after a possibly-partial no-replace rename.

    A foreign target that coexists with the still-present source is a normal
    pre-publication collision and must never be treated as an object owned by
    this publisher.  A foreign target with no source is ambiguous: the kernel
    may have completed the rename and a concurrent actor may then have
    replaced it, so the caller must fail closed and report incomplete rollback.
    """

    destination = _named_node_status(
        parent_fd=destination_parent_fd,
        name=destination_name,
        expected_state=expected_state,
        expected_descriptor=expected_descriptor,
    )
    if destination == "expected":
        return "expected"
    source = _named_node_status(
        parent_fd=source_parent_fd,
        name=source_name,
        expected_state=expected_state,
        expected_descriptor=expected_descriptor,
    )
    if destination == "foreign" and source == "expected" and collision_error:
        return "preexisting-foreign"
    if destination == "absent" and source == "expected":
        return "not-published"
    return "ambiguous"


def _verify_tree_rollback_ownership(
    *,
    parent_fd: int,
    name: str,
    root_fd: int,
    expected_root_state: os.stat_result,
    label: str,
) -> None:
    """Prove ownership of a tree before rollback without trusting its contents.

    This guard intentionally checks only the root directory identity.  If a
    file, mode, or child directory was changed after publication, a strict
    content check must report that fact, but it must not prevent us from moving
    the exact owned object out of the formal publication name for quarantine
    and investigation.
    """

    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        held = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(named.st_mode)
            or not stat.S_ISDIR(held.st_mode)
            or _rollback_node_identity(named)
            != _rollback_node_identity(expected_root_state)
            or _rollback_node_identity(held)
            != _rollback_node_identity(expected_root_state)
            or _node_binding_identity(named) != _node_binding_identity(held)
        ):
            raise HandoffError(f"{label} root is not owned by this publication")
    except HandoffError:
        raise
    except OSError as exc:
        raise HandoffError(f"{label} root could not be checked for rollback ownership") from exc


def _verify_file_rollback_ownership(
    *,
    parent_fd: int,
    name: str,
    descriptor: int,
    expected_state: os.stat_result,
    label: str,
) -> None:
    """Prove ownership of a published file while allowing tainted contents."""

    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        held = os.fstat(descriptor)
        if (
            not stat.S_ISREG(named.st_mode)
            or not stat.S_ISREG(held.st_mode)
            or named.st_nlink != 1
            or held.st_nlink != 1
            or _rollback_node_identity(named) != _rollback_node_identity(expected_state)
            or _rollback_node_identity(held) != _rollback_node_identity(expected_state)
            or _node_binding_identity(named) != _node_binding_identity(held)
        ):
            raise HandoffError(f"{label} file is not owned by this publication")
    except HandoffError:
        raise
    except OSError as exc:
        raise HandoffError(f"{label} file could not be checked for rollback ownership") from exc


def _quarantine_named_node(
    *,
    parent_fd: int,
    source_name: str,
    expected_state: os.stat_result,
    expected_descriptor: int | None = None,
) -> str:
    """Remove an owned but untrusted node from its formal publication name."""

    quarantine_name = f".{source_name}.quarantine-{uuid.uuid4().hex}"
    current = os.stat(source_name, dir_fd=parent_fd, follow_symlinks=False)
    if _rollback_node_identity(current) != _rollback_node_identity(expected_state):
        raise HandoffError("untrusted publication node no longer has the owned inode")
    if expected_descriptor is not None:
        try:
            held = os.fstat(expected_descriptor)
        except OSError as exc:
            raise HandoffError("untrusted publication node source could not be inspected") from exc
        if _node_binding_identity(current) != _node_binding_identity(held):
            raise HandoffError("untrusted publication node no longer matches its held inode")
    _rename_no_replace_at(
        parent_fd,
        source_name,
        parent_fd,
        quarantine_name,
    )
    quarantined = os.stat(
        quarantine_name,
        dir_fd=parent_fd,
        follow_symlinks=False,
    )
    if _rollback_node_identity(quarantined) != _rollback_node_identity(expected_state):
        raise HandoffError("quarantined publication node identity changed")
    try:
        os.stat(source_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise HandoffError("formal publication name remained after quarantine")
    os.fsync(parent_fd)
    return quarantine_name


def _publish(
    *,
    staging: Path,
    output_root: Path,
    receipt_temp: Path,
    receipt_path: Path,
    expected_receipt_sha256: str,
    expected_materials_sha256: str,
    expected_manifest_sha256: str,
    expected_staging_root_state: os.stat_result | None = None,
    expected_output_parent_state: os.stat_result | None = None,
    expected_receipt_parent_state: os.stat_result | None = None,
    _bound_output_parent_fd: int | None = None,
    _bound_receipt_parent_fd: int | None = None,
    _terminal_semantic_validator: Callable[[], None] | None = None,
) -> None:
    if staging.parent != output_root.parent or receipt_temp.parent != receipt_path.parent:
        raise HandoffError("handoff publication paths are not sibling pairs")
    if not SHA256_PATTERN.fullmatch(expected_receipt_sha256):
        raise HandoffError("expected detached receipt hash is invalid")
    if (_bound_output_parent_fd is None) != (_bound_receipt_parent_fd is None):
        raise HandoffError("both publication parent descriptors must be supplied together")

    output_parent_fd: int | None = None
    receipt_parent_fd: int | None = None
    staging_fd: int | None = None
    detached_sentinels: list[_DetachedInode] = []
    try:
        if _bound_output_parent_fd is None:
            _output_parent, output_parent_fd = _open_directory_fd(
                output_root.parent,
                "handoff output parent",
            )
            _receipt_parent, receipt_parent_fd = _open_directory_fd(
                receipt_path.parent,
                "handoff receipt parent",
            )
        else:
            output_parent_fd = os.dup(_bound_output_parent_fd)
            receipt_parent_fd = os.dup(_bound_receipt_parent_fd)
        output_parent_state = os.fstat(output_parent_fd)
        receipt_parent_state = os.fstat(receipt_parent_fd)
        if (
            not stat.S_ISDIR(output_parent_state.st_mode)
            or not stat.S_ISDIR(receipt_parent_state.st_mode)
        ):
            raise HandoffError("handoff publication parent is not a directory")
        if expected_output_parent_state is None:
            expected_output_parent_state = output_parent_state
        if expected_receipt_parent_state is None:
            expected_receipt_parent_state = receipt_parent_state
        if (
            _directory_inode_identity(output_parent_state)
            != _directory_inode_identity(expected_output_parent_state)
            or _directory_inode_identity(receipt_parent_state)
            != _directory_inode_identity(expected_receipt_parent_state)
        ):
            raise HandoffError("handoff publication parent directory changed before sealing")
        _verify_named_open_directory(
            path=output_root.parent,
            descriptor=output_parent_fd,
            expected_inode=output_parent_state,
            label="handoff output parent before sealing",
        )
        _verify_named_open_directory(
            path=receipt_path.parent,
            descriptor=receipt_parent_fd,
            expected_inode=receipt_parent_state,
            label="handoff receipt parent before sealing",
        )

        _reject_component_alias(output_parent_fd, staging.name, "handoff staging tree")
        staging_fd = os.open(
            staging.name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=output_parent_fd,
        )
        initial_staging_state = os.fstat(staging_fd)
        staged_by_name = os.stat(
            staging.name,
            dir_fd=output_parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(initial_staging_state.st_mode)
            or _state_identity(staged_by_name) != _state_identity(initial_staging_state)
        ):
            raise HandoffError("handoff staging directory changed before sealing")
        if expected_staging_root_state is None:
            expected_staging_root_state = initial_staging_state
        if (
            not stat.S_ISDIR(expected_staging_root_state.st_mode)
            or _directory_inode_identity(initial_staging_state)
            != _directory_inode_identity(expected_staging_root_state)
        ):
            raise HandoffError("handoff staging directory changed before sealing")

        # Refresh every staged file to a fresh inode before permission freeze.
        # This detaches any writable descriptors that may have been opened by
        # a producer while the evidence tree was being assembled.
        _refresh_staged_tree_inodes(
            staging,
            expected_materials_sha256=expected_materials_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            detached_sentinels=detached_sentinels,
            _bound_root_fd=staging_fd,
        )
        _refresh_regular_inode(
            receipt_temp,
            expected_sha256=expected_receipt_sha256,
            label="detached receipt staging file",
            detached_sentinels=detached_sentinels,
            _bound_parent_fd=receipt_parent_fd,
            _bound_name=receipt_temp.name,
        )
        _freeze_tree_permissions(
            staging,
            _bound_root_fd=staging_fd,
        )
        _fsync_tree_directories(
            staging,
            _bound_root_fd=staging_fd,
        )
        staging_state = os.fstat(staging_fd)
        staged_by_name = os.stat(
            staging.name,
            dir_fd=output_parent_fd,
            follow_symlinks=False,
        )
        if (
            _state_identity(staged_by_name) != _state_identity(staging_state)
            or _directory_inode_identity(staging_state)
            != _directory_inode_identity(expected_staging_root_state)
        ):
            raise HandoffError("handoff staging directory changed before publication")
        _verify_named_open_directory(
            path=output_root.parent,
            descriptor=output_parent_fd,
            expected_inode=output_parent_state,
            label="handoff output parent after sealing",
        )
        _verify_named_open_directory(
            path=receipt_path.parent,
            descriptor=receipt_parent_fd,
            expected_inode=receipt_parent_state,
            label="handoff receipt parent after sealing",
        )
    except BaseException as exc:
        for sentinel in detached_sentinels:
            try:
                os.close(sentinel.descriptor)
            except OSError:
                pass
        for descriptor in (staging_fd, output_parent_fd, receipt_parent_fd):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except OSError:
                pass
        if isinstance(exc, (OSError, ValueError)):
            raise HandoffError("handoff staging tree could not be sealed safely") from exc
        raise

    receipt_fd: int | None = None
    output_published = False
    receipt_published = False
    output_rename_attempted = False
    receipt_rename_attempted = False
    committed = False
    receipt_state: os.stat_result | None = None
    tree_snapshot: list[_HeldTreeFile] = []
    try:
        os.fsync(staging_fd)
        staged_by_name = os.stat(
            staging.name,
            dir_fd=output_parent_fd,
            follow_symlinks=False,
        )
        if (
            _state_identity(staged_by_name) != _state_identity(staging_state)
            or _directory_inode_identity(staging_state)
            != _directory_inode_identity(expected_staging_root_state)
        ):
            raise HandoffError("handoff staging directory changed before publication")
        tree_snapshot = _open_held_tree_snapshot(
            root=staging,
            expected_root_state=staging_state,
            expected_materials_sha256=expected_materials_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        receipt_fd = os.open(
            receipt_temp.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=receipt_parent_fd,
        )
        receipt_state = os.fstat(receipt_fd)
        if not stat.S_ISREG(receipt_state.st_mode) or receipt_state.st_nlink != 1:
            raise HandoffError("detached receipt staging file is not a unique regular file")
        os.fchmod(receipt_fd, FROZEN_FILE_MODE)
        os.fsync(receipt_fd)
        receipt_state = os.fstat(receipt_fd)
        receipt_by_name = os.stat(
            receipt_temp.name,
            dir_fd=receipt_parent_fd,
            follow_symlinks=False,
        )
        if (
            _state_identity(receipt_by_name) != _state_identity(receipt_state)
        ):
            raise HandoffError("detached receipt staging file is not a unique regular file")
        if (
            _sha256_open_file(
                receipt_fd,
                expected_state=receipt_state,
                label="detached receipt staging file",
            )
            != expected_receipt_sha256
        ):
            raise HandoffError("detached receipt staging hash differs from its sealed payload")
        if _terminal_semantic_validator is not None:
            _terminal_semantic_validator()
        staged_by_name = os.stat(
            staging.name,
            dir_fd=output_parent_fd,
            follow_symlinks=False,
        )
        if _state_identity(staged_by_name) != _state_identity(staging_state):
            raise HandoffError("handoff staging directory changed before publication")
        _verify_held_tree_snapshot(
            root=staging,
            expected_root_state=staging_state,
            snapshot=tree_snapshot,
        )
        _verify_named_open_directory(
            path=output_root.parent,
            descriptor=output_parent_fd,
            expected_inode=output_parent_state,
            label="handoff output parent",
        )
        _verify_named_open_directory(
            path=receipt_path.parent,
            descriptor=receipt_parent_fd,
            expected_inode=receipt_parent_state,
            label="handoff receipt parent",
        )
        _verify_detached_inodes(detached_sentinels)
        output_rename_attempted = True
        _rename_no_replace_at(
            output_parent_fd,
            staging.name,
            output_parent_fd,
            output_root.name,
        )
        output_published = True
        published_output_state = os.stat(
            output_root.name,
            dir_fd=output_parent_fd,
            follow_symlinks=False,
        )
        if _published_node_identity(published_output_state) != _published_node_identity(
            staging_state
        ):
            raise HandoffError("published handoff directory identity differs from staging")
        _verify_held_tree_snapshot(
            root=output_root,
            expected_root_state=staging_state,
            snapshot=tree_snapshot,
        )
        receipt_by_name = os.stat(
            receipt_temp.name,
            dir_fd=receipt_parent_fd,
            follow_symlinks=False,
        )
        if _state_identity(receipt_by_name) != _state_identity(receipt_state):
            raise HandoffError("detached receipt changed before publication")
        if (
            _sha256_open_file(
                receipt_fd,
                label="detached receipt staging file",
            )
            != expected_receipt_sha256
        ):
            raise HandoffError("detached receipt changed before publication")
        receipt_by_name = os.stat(
            receipt_temp.name,
            dir_fd=receipt_parent_fd,
            follow_symlinks=False,
        )
        if _state_identity(receipt_by_name) != _state_identity(receipt_state):
            raise HandoffError("detached receipt changed before publication")
        _verify_named_open_directory(
            path=output_root.parent,
            descriptor=output_parent_fd,
            expected_inode=output_parent_state,
            label="handoff output parent",
        )
        _verify_named_open_directory(
            path=receipt_path.parent,
            descriptor=receipt_parent_fd,
            expected_inode=receipt_parent_state,
            label="handoff receipt parent",
        )
        receipt_rename_attempted = True
        _rename_no_replace_at(
            receipt_parent_fd,
            receipt_temp.name,
            receipt_parent_fd,
            receipt_path.name,
        )
        receipt_published = True
        published_receipt_state = os.stat(
            receipt_path.name,
            dir_fd=receipt_parent_fd,
            follow_symlinks=False,
        )
        published_output_state = os.stat(
            output_root.name,
            dir_fd=output_parent_fd,
            follow_symlinks=False,
        )
        if (
            _published_node_identity(published_receipt_state)
            != _published_node_identity(receipt_state)
            or _published_node_identity(published_output_state)
            != _published_node_identity(staging_state)
        ):
            raise HandoffError("published handoff identities differ from staged inputs")
        _verify_named_open_file(
            parent_fd=receipt_parent_fd,
            name=receipt_path.name,
            descriptor=receipt_fd,
            expected_inode=receipt_state,
            expected_sha256=expected_receipt_sha256,
            label="published detached receipt",
        )
        os.fsync(output_parent_fd)
        os.fsync(receipt_parent_fd)
        _verify_held_tree_snapshot(
            root=output_root,
            expected_root_state=staging_state,
            snapshot=tree_snapshot,
        )
        _verify_named_open_file(
            parent_fd=receipt_parent_fd,
            name=receipt_path.name,
            descriptor=receipt_fd,
            expected_inode=receipt_state,
            expected_sha256=expected_receipt_sha256,
            label="published detached receipt before durable commit",
        )
        receipt_commit_state = os.fstat(receipt_fd)
        _verify_named_open_directory(
            path=output_root.parent,
            descriptor=output_parent_fd,
            expected_inode=output_parent_state,
            label="handoff output parent before durable commit",
        )
        _verify_named_open_directory(
            path=receipt_path.parent,
            descriptor=receipt_parent_fd,
            expected_inode=receipt_parent_state,
            label="handoff receipt parent before durable commit",
        )
        _rebind_held_tree_snapshot(
            root=output_root,
            expected_root_state=staging_state,
            snapshot=tree_snapshot,
        )
        _rebind_named_open_file(
            parent_fd=receipt_parent_fd,
            name=receipt_path.name,
            descriptor=receipt_fd,
            expected_state=receipt_commit_state,
            label="published detached receipt commit barrier",
        )
        _verify_named_open_directory(
            path=output_root.parent,
            descriptor=output_parent_fd,
            expected_inode=output_parent_state,
            label="handoff output parent commit barrier",
        )
        _verify_named_open_directory(
            path=receipt_path.parent,
            descriptor=receipt_parent_fd,
            expected_inode=receipt_parent_state,
            label="handoff receipt parent commit barrier",
        )
        # Close cross-object race windows opened while checking the two parent
        # path identities: each sealed object must still bind to its held FD.
        _final_cross_object_barrier(
            root=output_root,
            expected_root_state=staging_state,
            snapshot=tree_snapshot,
            receipt_parent_fd=receipt_parent_fd,
            receipt_name=receipt_path.name,
            receipt_fd=receipt_fd,
            receipt_state=receipt_commit_state,
            expected_receipt_sha256=expected_receipt_sha256,
            label_prefix="published detached",
        )
        # Keep one terminal pass immediately before the commit flag.  The
        # cross-object barrier performs alternating checks, but a producer can
        # still write through an already-open descriptor while the last receipt
        # check is returning.  A second self-contained pass catches that
        # bounded window before success is reported.
        _final_snapshot_probe(
            root=output_root,
            expected_root_state=staging_state,
            snapshot=tree_snapshot,
            receipt_parent_fd=receipt_parent_fd,
            receipt_name=receipt_path.name,
            receipt_fd=receipt_fd,
            receipt_state=receipt_commit_state,
            expected_receipt_sha256=expected_receipt_sha256,
        )
        _verify_detached_inodes(detached_sentinels)
        committed = True
    except BaseException as publication_error:
        rollback_errors: list[BaseException] = []

        # A wrapper around rename may raise after the kernel has completed the
        # operation.  Reconcile the booleans with both formal names *and* the
        # still-held source names before deciding what can be rolled back.  A
        # foreign target alongside an untouched source is a pre-publication
        # collision; it is not an object owned by this publisher.
        collision_error = "appeared concurrently" in str(publication_error)
        if staging_state is not None and staging_fd is not None:
            try:
                output_status = _reconcile_publication_target(
                    destination_parent_fd=output_parent_fd,
                    destination_name=output_root.name,
                    source_parent_fd=output_parent_fd,
                    source_name=staging.name,
                    expected_state=staging_state,
                    collision_error=collision_error and output_rename_attempted,
                    expected_descriptor=staging_fd,
                )
                if output_status == "expected":
                    output_published = True
                elif output_status == "ambiguous":
                    rollback_errors.append(
                        HandoffError("published handoff changed before rollback")
                    )
            except BaseException as exc:
                rollback_errors.append(exc)
        if receipt_state is not None and receipt_fd is not None:
            try:
                receipt_status = _reconcile_publication_target(
                    destination_parent_fd=receipt_parent_fd,
                    destination_name=receipt_path.name,
                    source_parent_fd=receipt_parent_fd,
                    source_name=receipt_temp.name,
                    expected_state=receipt_state,
                    collision_error=collision_error and receipt_rename_attempted,
                    expected_descriptor=receipt_fd,
                )
                if receipt_status == "expected":
                    receipt_published = True
                elif receipt_status == "ambiguous":
                    rollback_errors.append(
                        HandoffError("published receipt changed before rollback")
                    )
            except BaseException as exc:
                rollback_errors.append(exc)

        if receipt_published and receipt_state is not None and receipt_fd is not None:
            try:
                # Ownership is checked separately from integrity.  A receipt
                # whose bytes or mode were changed must be moved out of the
                # formal name, but must remain available as an investigation
                # object rather than being silently repaired or discarded.
                _verify_file_rollback_ownership(
                    parent_fd=receipt_parent_fd,
                    name=receipt_path.name,
                    descriptor=receipt_fd,
                    expected_state=receipt_state,
                    label="published receipt before rollback",
                )
                try:
                    _rename_no_replace_at(
                        receipt_parent_fd,
                        receipt_path.name,
                        receipt_parent_fd,
                        receipt_temp.name,
                    )
                except BaseException:
                    # Reconcile a wrapper that raised after the kernel rename.
                    if not (
                        _named_node_status(
                            parent_fd=receipt_parent_fd,
                            name=receipt_path.name,
                            expected_state=receipt_state,
                            expected_descriptor=receipt_fd,
                        )
                        == "absent"
                        and _named_node_status(
                            parent_fd=receipt_parent_fd,
                            name=receipt_temp.name,
                            expected_state=receipt_state,
                            expected_descriptor=receipt_fd,
                        )
                        == "expected"
                    ):
                        raise
                _verify_file_rollback_ownership(
                    parent_fd=receipt_parent_fd,
                    name=receipt_temp.name,
                    descriptor=receipt_fd,
                    expected_state=receipt_state,
                    label="rolled-back receipt ownership",
                )
                if _named_node_status(
                    parent_fd=receipt_parent_fd,
                    name=receipt_path.name,
                    expected_state=receipt_state,
                    expected_descriptor=receipt_fd,
                ) != "absent":
                    raise HandoffError("published receipt remained after rollback")
                receipt_published = False
                # Do not re-run the strict content verifier here.  A failure
                # may have been caused by a byte/mode/child-shape mutation; the
                # owned inode has still been moved out of the formal name and
                # must remain available at ``receipt_temp`` as an explicitly
                # untrusted investigation object.
            except BaseException as exc:
                rollback_errors.append(exc)

        if output_published and staging_state is not None and staging_fd is not None:
            try:
                _verify_tree_rollback_ownership(
                    parent_fd=output_parent_fd,
                    name=output_root.name,
                    root_fd=staging_fd,
                    expected_root_state=staging_state,
                    label="published handoff",
                )
                try:
                    _rename_no_replace_at(
                        output_parent_fd,
                        output_root.name,
                        output_parent_fd,
                        staging.name,
                    )
                except BaseException:
                    # As above, accept only a proven post-syscall rename; never
                    # overwrite a competing staging name.
                    if not (
                        _named_node_status(
                            parent_fd=output_parent_fd,
                            name=output_root.name,
                            expected_state=staging_state,
                            expected_descriptor=staging_fd,
                        )
                        == "absent"
                        and _named_node_status(
                            parent_fd=output_parent_fd,
                            name=staging.name,
                            expected_state=staging_state,
                            expected_descriptor=staging_fd,
                        )
                        == "expected"
                    ):
                        raise
                _verify_tree_rollback_ownership(
                    parent_fd=output_parent_fd,
                    name=staging.name,
                    root_fd=staging_fd,
                    expected_root_state=staging_state,
                    label="rolled-back handoff ownership",
                )
                if _named_node_status(
                    parent_fd=output_parent_fd,
                    name=output_root.name,
                    expected_state=staging_state,
                    expected_descriptor=staging_fd,
                ) != "absent":
                    raise HandoffError("published handoff remained after rollback")
                output_published = False
                # As with the receipt, the restored staging tree is an
                # investigation object after any detected mutation.  Ownership
                # and formal-name absence are the rollback gate; rehashing it
                # would turn a successful quarantine into a false incomplete
                # rollback and could also require a path that was concurrently
                # moved away while the held parent descriptor remains valid.
            except BaseException as exc:
                rollback_errors.append(exc)

        try:
            _verify_detached_inodes(detached_sentinels)
        except BaseException as exc:
            # A detached sentinel is deliberately outside the published names.
            # Its mutation explains why publication failed, but it cannot make
            # an otherwise proven ownership rollback incomplete.  Preserve the
            # detail on the original failure without treating the sentinel as a
            # formal output that must be restored.
            try:
                publication_error.add_note(str(exc))
            except AttributeError:
                pass
        try:
            os.fsync(output_parent_fd)
            os.fsync(receipt_parent_fd)
        except OSError as exc:
            rollback_errors.append(exc)
        if rollback_errors:
            first_error = rollback_errors[0]
            raise HandoffError(
                "handoff publication failed and rollback was incomplete"
            ) from first_error
        raise HandoffError(
            "handoff publication failed; formal outputs were rolled back"
        ) from publication_error
    finally:
        close_errors: list[OSError] = []
        descriptors = [item.descriptor for item in tree_snapshot]
        descriptors.extend(item.descriptor for item in detached_sentinels)
        descriptors.extend((receipt_fd, staging_fd, output_parent_fd, receipt_parent_fd))
        for descriptor in descriptors:
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except OSError as exc:
                close_errors.append(exc)
        if close_errors and committed:
            # The files and both parent directories are already durable. A late
            # descriptor-close error must not turn a successful publication into
            # a false failure with formal outputs left behind.
            pass
        elif close_errors and sys.exc_info()[0] is None:
            raise HandoffError("handoff publication descriptors could not be closed")


def _build_stop_b_handoff_impl(
    *,
    repo_root: str | Path,
    source_root: str | Path,
    governance_root: str | Path,
    request_path: str | Path,
    suite_root: str | Path,
    final_dlp_receipt: str | Path,
    app_verification: str | Path,
    code_verification: str | Path,
    disclosure: str | Path,
    offline_test_root: str | Path,
    offline_test_component_set: str | Path,
    offline_test_receipt: str | Path,
    suite_build_receipt: str | Path,
    suite_verification: str | Path,
    output_root: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    """Build a fixed-layout handoff in sibling staging and publish it once."""

    repo = _require_directory(Path(repo_root), "repository root")
    source = _require_directory(Path(source_root), "approved source root")
    governance = _require_directory(Path(governance_root), "governance root")
    suite = _require_directory(Path(suite_root), "suite root")
    offline = _require_directory(Path(offline_test_root), "offline test root")
    raw_source_files = [
        Path(request_path),
        Path(final_dlp_receipt),
        Path(app_verification),
        Path(code_verification),
        Path(disclosure),
        Path(offline_test_component_set),
        Path(offline_test_receipt),
        Path(suite_build_receipt),
        Path(suite_verification),
    ]
    source_files: list[Path] = []
    for path in raw_source_files:
        _require_regular(path, "handoff input")
        source_files.append(_absolute_path(path, "handoff input"))
    output, output_name, output_parent_fd, expected_output_parent_state = (
        _open_prospective_parent(output_root, "handoff output root")
    )
    receipt_parent_fd: int | None = None
    staging_fd: int | None = None
    try:
        receipt, receipt_name, receipt_parent_fd, expected_receipt_parent_state = (
            _open_prospective_parent(receipt_path, "detached handoff receipt")
        )
        _validate_output_boundaries(
            output_root=output,
            receipt_path=receipt,
            sources=[repo, source, governance, suite, offline, *source_files],
        )
        # Keep both parent descriptors open while the candidate is assembled.
        # Every staging and detached-receipt write below is relative to one of
        # these descriptors, so a path replacement cannot redirect bytes to a
        # newly-created parent at the original spelling.
        _assert_parent_binding(
            output.parent,
            output_parent_fd,
            expected_output_parent_state,
            "handoff output",
        )
        _assert_parent_binding(
            receipt.parent,
            receipt_parent_fd,
            expected_receipt_parent_state,
            "detached handoff receipt",
        )
        for parent_fd, name, label in (
            (output_parent_fd, output_name, "handoff output root"),
            (receipt_parent_fd, receipt_name, "detached handoff receipt"),
        ):
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise HandoffError(f"{label} already exists")

        staging_name = f".{output.name}.staging-{uuid.uuid4().hex}"
        receipt_temp_name = f".{receipt.name}.staging-{uuid.uuid4().hex}"
        staging = output.parent / staging_name
        receipt_temp = receipt.parent / receipt_temp_name
        _mkdir_new_at(output_parent_fd, staging_name, mode=0o700)
        staging_fd = _open_relative_directory_fd(
            output_parent_fd,
            staging_name,
            "handoff staging tree",
        )
        staging_state = os.fstat(staging_fd)
        _assert_bound_child_directory(
            output_parent_fd,
            staging_name,
            staging_fd,
            staging_state,
            "handoff staging tree",
        )

        _copy_file_bound(source_files[0], staging_fd, staging, REQUEST_NAME)
        _copy_file_bound(
            repo / "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
            staging_fd,
            staging,
            "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
        )
        _copy_file_bound(
            repo / "deploy/cloud_v2/stop-b-synthetic-probes.json",
            staging_fd,
            staging,
            "deploy/cloud_v2/stop-b-synthetic-probes.json",
        )
        _copy_tree_bound(suite, staging_fd, staging, SUITE_RELATIVE)
        embedded = suite / "server-runtime/evidence"
        copy_map = (
            (embedded / "app-package-receipt.json", "phase1-evidence/app-package-receipt.json"),
            (source_files[2], "phase1-evidence/app-package-verification.json"),
            (source_files[3], "phase1-evidence/code-manifest-verification.json"),
            (source_files[4], "phase1-evidence/disclosure-evidence.json"),
            (source_files[1], "phase1-evidence/final-suite-dlp-receipt.json"),
            (embedded / "candidate-dlp-receipt.json", "phase1-evidence/phase1-dlp-receipt.json"),
            (source_files[7], "phase1-evidence/suite-build-receipt.json"),
            (source_files[8], "phase1-evidence/suite-verification.json"),
            (source_files[5], "phase1-evidence/offline-tests/offline-test-component-set.json"),
            (source_files[6], "phase1-evidence/offline-tests/offline-test-receipt.json"),
        )
        for copy_source, relative_destination in copy_map:
            _copy_file_bound(
                copy_source,
                staging_fd,
                staging,
                relative_destination,
                mode=_staging_file_mode(relative_destination),
            )
        _copy_tree_bound(
            offline / "logs",
            staging_fd,
            staging,
            "phase1-evidence/offline-tests/logs",
        )
        _assert_bound_child_directory(
            output_parent_fd,
            staging_name,
            staging_fd,
            staging_state,
            "handoff staging tree",
        )
        _verify_named_open_directory(
            path=staging,
            descriptor=staging_fd,
            expected_inode=staging_state,
            label="handoff staging tree",
        )

        request, mode, scope, records = _validate_core(
            root=staging,
            repo_root=repo,
            source_root=source,
            governance_root=governance,
            authority_database_physical_mode=0o640,
        )
        try:
            manifest = _manifest_value(
                root=staging,
                request=request,
                request_mode=mode,
                scope=scope,
                evidence_records=records,
            )
        finally:
            _finalize_source_scope(scope)
        _write_new_at(staging_fd, MANIFEST_NAME, canonical_json_bytes(manifest))
        material_records = _tree_records(staging)
        _write_new_at(staging_fd, MATERIALS_NAME, _materials_payload(material_records))
        _parse_materials(staging)
        if _strict_json(staging / MANIFEST_NAME, canonical=True) != manifest:
            raise HandoffError("handoff manifest changed after serialization")
        final_request, final_mode, final_scope, final_records = _validate_core(
            root=staging,
            repo_root=repo,
            source_root=source,
            governance_root=governance,
            authority_database_physical_mode=0o640,
        )
        try:
            final_manifest = _manifest_value(
                root=staging,
                request=final_request,
                request_mode=final_mode,
                scope=final_scope,
                evidence_records=final_records,
            )
        finally:
            _finalize_source_scope(final_scope)
        if final_manifest != manifest:
            raise HandoffError(
                "handoff semantic evidence changed before the final seal"
            )
        # The final semantic pass is read-only. Re-parse MATERIALS afterwards so
        # any concurrent byte change during that pass is still caught before the
        # expected hashes are frozen for publication.
        _parse_materials(staging)
        sealed_materials_sha256 = sha256_file(staging / MATERIALS_NAME)
        sealed_manifest_sha256 = sha256_file(staging / MANIFEST_NAME)
        sealed_inventory = _safe_tree_inventory(staging)
        dlp = _handoff_dlp(staging)
        if dlp.get("ok") is not True:
            raise HandoffError("full handoff DLP did not pass")
        result = _receipt_value(
            root=staging,
            request_mode=mode,
            evidence_records=records,
            dlp=dlp,
            expected_inventory=sealed_inventory,
            expected_materials_sha256=sealed_materials_sha256,
            expected_manifest_sha256=sealed_manifest_sha256,
        )
        receipt_payload = canonical_json_bytes(result)
        receipt_sha256 = hashlib.sha256(receipt_payload).hexdigest()
        published_result = {**result, "receipt_sha256": receipt_sha256}
        _write_new_at(receipt_parent_fd, receipt_temp_name, receipt_payload)

        def terminal_semantic_validator() -> None:
            verified = _verify_stop_b_handoff_impl(
                handoff_root=staging,
                receipt_path=receipt_temp,
                source_root=source,
                governance_root=governance,
                repo_root=repo,
            )
            if verified.get("receipt_sha256") != receipt_sha256:
                raise HandoffError(
                    "terminal handoff verification returned a different receipt identity"
                )

        _assert_parent_binding(
            receipt.parent,
            receipt_parent_fd,
            expected_receipt_parent_state,
            "detached handoff receipt",
        )
        expected_staging_root_state = os.fstat(staging_fd)
        _publish(
            staging=staging,
            output_root=output,
            receipt_temp=receipt_temp,
            receipt_path=receipt,
            expected_receipt_sha256=receipt_sha256,
            expected_materials_sha256=sealed_materials_sha256,
            expected_manifest_sha256=sealed_manifest_sha256,
            expected_staging_root_state=expected_staging_root_state,
            expected_output_parent_state=expected_output_parent_state,
            expected_receipt_parent_state=expected_receipt_parent_state,
            _bound_output_parent_fd=output_parent_fd,
            _bound_receipt_parent_fd=receipt_parent_fd,
            _terminal_semantic_validator=terminal_semantic_validator,
        )
        return published_result
    finally:
        if staging_fd is not None:
            os.close(staging_fd)
        if receipt_parent_fd is not None:
            os.close(receipt_parent_fd)
        os.close(output_parent_fd)


def build_stop_b_handoff(
    *,
    repo_root: str | Path,
    source_root: str | Path,
    governance_root: str | Path,
    request_path: str | Path,
    suite_root: str | Path,
    final_dlp_receipt: str | Path,
    app_verification: str | Path,
    code_verification: str | Path,
    disclosure: str | Path,
    offline_test_root: str | Path,
    offline_test_component_set: str | Path,
    offline_test_receipt: str | Path,
    suite_build_receipt: str | Path,
    suite_verification: str | Path,
    output_root: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    actions = _require_formal_stop_b_handoff_bootstrap_context()
    return actions[7](
        repo_root=repo_root,
        source_root=source_root,
        governance_root=governance_root,
        request_path=request_path,
        suite_root=suite_root,
        final_dlp_receipt=final_dlp_receipt,
        app_verification=app_verification,
        code_verification=code_verification,
        disclosure=disclosure,
        offline_test_root=offline_test_root,
        offline_test_component_set=offline_test_component_set,
        offline_test_receipt=offline_test_receipt,
        suite_build_receipt=suite_build_receipt,
        suite_verification=suite_verification,
        output_root=output_root,
        receipt_path=receipt_path,
    )


def _verify_stop_b_handoff_impl(
    *,
    handoff_root: str | Path,
    receipt_path: str | Path,
    source_root: str | Path,
    governance_root: str | Path,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute all material, semantic, DLP, and detached-receipt bindings."""

    root = _require_directory(Path(handoff_root), "handoff root")
    receipt_file = _absolute_path(Path(receipt_path), "detached handoff receipt")
    if _overlaps(root, receipt_file):
        raise HandoffError("handoff receipt must remain detached")
    receipt_parent_fd: int | None = None
    receipt_fd: int | None = None
    root_fd: int | None = None
    tree_snapshot: list[_HeldTreeFile] = []
    try:
        _receipt_absolute, receipt_name, receipt_parent_fd = _parent_fd(
            receipt_file,
            "detached handoff receipt",
        )
        receipt_parent_state = os.fstat(receipt_parent_fd)
        receipt_state = os.stat(
            receipt_name,
            dir_fd=receipt_parent_fd,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(receipt_state.st_mode) or receipt_state.st_nlink != 1:
            raise HandoffError("detached handoff receipt must be a unique regular file")
        _require_frozen_mode(
            receipt_state,
            expected=FROZEN_FILE_MODE,
            label="detached handoff receipt",
        )
        receipt_fd = os.open(
            receipt_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=receipt_parent_fd,
        )
        if _state_identity(os.fstat(receipt_fd)) != _state_identity(receipt_state):
            raise HandoffError("detached handoff receipt changed while it was opened")
        receipt_payload = _read_open_file_bytes(
            receipt_fd,
            expected_state=receipt_state,
            label="detached handoff receipt",
        )
        receipt_sha256 = hashlib.sha256(receipt_payload).hexdigest()
        actual_receipt = _strict_json_bytes(
            receipt_payload,
            "detached handoff receipt",
        )
        if receipt_payload != canonical_json_bytes(actual_receipt):
            raise HandoffError("detached handoff receipt is not canonical JSON")
        expected_materials_sha256 = actual_receipt.get("materials_sha256")
        expected_manifest_sha256 = actual_receipt.get("handoff_manifest_sha256")
        if not isinstance(expected_materials_sha256, str) or not isinstance(
            expected_manifest_sha256,
            str,
        ):
            raise HandoffError("detached handoff receipt lacks sealed tree identities")

        _root_absolute, root_fd = _open_directory_fd(root, "handoff root")
        root_state = os.fstat(root_fd)
        tree_snapshot = _open_held_tree_snapshot(
            root=root,
            expected_root_state=root_state,
            expected_materials_sha256=expected_materials_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        repo = (
            _require_directory(
                _absolute_path(Path(__file__), "handoff module").parents[2],
                "repository root",
            )
            if repo_root is None
            else _require_directory(Path(repo_root), "repository root")
        )
        source = _require_directory(Path(source_root), "approved source root")
        governance = _require_directory(Path(governance_root), "governance root")
        material_records = _parse_materials(root)
        request, mode, scope, records = _validate_core(
            root=root,
            repo_root=repo,
            source_root=source,
            governance_root=governance,
            authority_database_physical_mode=FROZEN_FILE_MODE,
        )
        try:
            expected_manifest = _manifest_value(
                root=root,
                request=request,
                request_mode=mode,
                scope=scope,
                evidence_records=records,
            )
        finally:
            _finalize_source_scope(scope)
        if _strict_json(root / MANIFEST_NAME, canonical=True) != expected_manifest:
            raise HandoffError("handoff manifest differs from current material bindings")
        _verify_held_tree_snapshot(
            root=root,
            expected_root_state=root_state,
            snapshot=tree_snapshot,
        )
        sealed_inventory = _safe_tree_inventory(root)
        _verify_held_tree_snapshot(
            root=root,
            expected_root_state=root_state,
            snapshot=tree_snapshot,
        )
        dlp = _handoff_dlp(root)
        if dlp.get("ok") is not True:
            raise HandoffError("full handoff DLP did not pass")
        expected_receipt = _receipt_value(
            root=root,
            request_mode=mode,
            evidence_records=records,
            dlp=dlp,
            expected_inventory=sealed_inventory,
            expected_materials_sha256=expected_materials_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        if actual_receipt != expected_receipt:
            raise HandoffError("detached handoff receipt is stale or mismatched")
        if expected_receipt["material_file_count"] != len(material_records):
            raise HandoffError("detached receipt material count is inconsistent")
        _verify_held_tree_snapshot(
            root=root,
            expected_root_state=root_state,
            snapshot=tree_snapshot,
        )
        _verify_named_open_file(
            parent_fd=receipt_parent_fd,
            name=receipt_name,
            descriptor=receipt_fd,
            expected_inode=receipt_state,
            expected_sha256=receipt_sha256,
            label="detached handoff receipt after verification",
        )
        receipt_commit_state = os.fstat(receipt_fd)
        _verify_named_open_directory(
            path=receipt_file.parent,
            descriptor=receipt_parent_fd,
            expected_inode=receipt_parent_state,
            label="detached handoff receipt parent after verification",
        )
        _final_cross_object_barrier(
            root=root,
            expected_root_state=root_state,
            snapshot=tree_snapshot,
            receipt_parent_fd=receipt_parent_fd,
            receipt_name=receipt_name,
            receipt_fd=receipt_fd,
            receipt_state=receipt_commit_state,
            expected_receipt_sha256=receipt_sha256,
            label_prefix="detached handoff",
        )
        return {**expected_receipt, "receipt_sha256": receipt_sha256}
    except OSError as exc:
        raise HandoffError("detached handoff verification failed safely") from exc
    finally:
        descriptors = [item.descriptor for item in tree_snapshot]
        descriptors.extend((receipt_fd, root_fd, receipt_parent_fd))
        for descriptor in descriptors:
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except OSError:
                pass


def verify_stop_b_handoff(
    *,
    handoff_root: str | Path,
    receipt_path: str | Path,
    source_root: str | Path,
    governance_root: str | Path,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    actions = _require_formal_stop_b_handoff_bootstrap_context()
    return actions[8](
        handoff_root=handoff_root,
        receipt_path=receipt_path,
        source_root=source_root,
        governance_root=governance_root,
        repo_root=repo_root,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    produce_app = commands.add_parser(
        "produce-app-verification",
        help="produce the detached Stop B App verification evidence wrapper",
    )
    produce_app.add_argument("--repo-root", required=True)
    produce_app.add_argument("--suite-root", required=True)
    produce_app.add_argument("--output-path", required=True)
    produce_code = commands.add_parser(
        "produce-code-verification",
        help="produce the detached Stop B code verification evidence wrapper",
    )
    produce_code.add_argument("--repo-root", required=True)
    produce_code.add_argument("--suite-root", required=True)
    produce_code.add_argument("--output-path", required=True)
    build = commands.add_parser("build", help="build and seal a Stop B handoff")
    for option in (
        "repo-root",
        "source-root",
        "governance-root",
        "request-path",
        "suite-root",
        "final-dlp-receipt",
        "app-verification",
        "code-verification",
        "disclosure",
        "offline-test-root",
        "offline-test-component-set",
        "offline-test-receipt",
        "suite-build-receipt",
        "suite-verification",
        "output-root",
        "receipt-path",
    ):
        build.add_argument(f"--{option}", required=True)
    verify = commands.add_parser("verify", help="verify an existing Stop B handoff")
    verify.add_argument("--handoff-root", required=True)
    verify.add_argument("--receipt-path", required=True)
    verify.add_argument("--source-root", required=True)
    verify.add_argument("--governance-root", required=True)
    verify.add_argument("--repo-root")
    return parser


def _run_cli(
    argv: list[str] | None = None,
    *,
    _action_closure: tuple[object, ...] | None = None,
) -> int:
    actions = (
        _current_stop_b_handoff_action_closure()[:5]
        if _action_closure is None
        else _action_closure
    )
    if not isinstance(actions, tuple) or len(actions) != 5 or any(
        not callable(action) for action in actions
    ):
        raise HandoffError("Stop B handoff CLI action closure is malformed")
    (
        parser_action,
        app_verification_action,
        code_verification_action,
        build_action,
        verify_action,
    ) = actions
    args = parser_action().parse_args(argv)
    try:
        if args.command == "produce-app-verification":
            result = app_verification_action(
                repo_root=args.repo_root,
                suite_root=args.suite_root,
                output_path=args.output_path,
            )
        elif args.command == "produce-code-verification":
            result = code_verification_action(
                repo_root=args.repo_root,
                suite_root=args.suite_root,
                output_path=args.output_path,
            )
        elif args.command == "build":
            result = build_action(
                repo_root=args.repo_root,
                source_root=args.source_root,
                governance_root=args.governance_root,
                request_path=args.request_path,
                suite_root=args.suite_root,
                final_dlp_receipt=args.final_dlp_receipt,
                app_verification=args.app_verification,
                code_verification=args.code_verification,
                disclosure=args.disclosure,
                offline_test_root=args.offline_test_root,
                offline_test_component_set=args.offline_test_component_set,
                offline_test_receipt=args.offline_test_receipt,
                suite_build_receipt=args.suite_build_receipt,
                suite_verification=args.suite_verification,
                output_root=args.output_root,
                receipt_path=args.receipt_path,
            )
        else:
            result = verify_action(
                handoff_root=args.handoff_root,
                receipt_path=args.receipt_path,
                source_root=args.source_root,
                governance_root=args.governance_root,
                repo_root=args.repo_root,
            )
    except HandoffError as exc:
        status = exc.code if exc.code == "superseded-invalid-evidence" else "failed"
        print(
            json.dumps(
                {
                    "schema_version": "cloud-v2-stop-b-handoff-error-v1",
                    "status": status,
                    "ok": False,
                    "error_code": exc.code,
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        actions = _require_formal_stop_b_handoff_bootstrap_context()
    except HandoffError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    return _run_cli(argv, _action_closure=actions[:5])


if __name__ == "__main__":
    raise SystemExit(main())
