#!/usr/bin/env python3
"""Hash-only DLP gates for approved sources and cloud-v2 candidate artifacts."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.stderr.write("formal DLP CLI bootstrap context is required\n")
    raise SystemExit(2)

import argparse
import contextlib
import ctypes
import errno
import fcntl
import hashlib
import io
import json
import os
import re
import resource
import secrets
import shutil
import sqlite3
import stat
import struct
import subprocess
import tarfile
import tempfile
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Iterator, Mapping
from urllib.parse import quote

from .authority_builder import (
    AUTHORITY_SCHEMA_SQL,
    CHUNKING_POLICY_VERSION,
    canonical_json_bytes,
)
from .graph_builder import ENTITY_LEXICON
from .offline_evidence import (
    NETWORK_SANDBOX_PATH,
    OfflineEvidenceError,
    _external_tool_macho_closure,
    _require_formal_bootstrap_context,
    _require_isolated_python,
    run_formal_validation,
)
from .source_scope import ApprovedSource, ApprovedSourceScope, sha256_file


DLP_SCHEMA_VERSION = "cloud-v2-dlp-receipt-v3"
DLP_RULESET_VERSION = "cloud-v2-dlp-rules-v3"
FINAL_SUITE_DLP_SCHEMA_VERSION = "cloud-v2-final-suite-dlp-receipt-v2"
INVENTORY_SCHEMA_VERSION = "cloud-v2-dlp-inventory-v1"
IMPLEMENTATION_SCOPE_SCHEMA_VERSION = "cloud-v2-phase1-implementation-scope-v2"
ROLE_CLOSURE_SCHEMA_VERSION = "cloud-v2-role-semantic-closure-v1"
FINAL_EVIDENCE_CLOSURE_SCHEMA_VERSION = "cloud-v2-final-evidence-closure-v1"
AUTHORITY_DATABASE_PHYSICAL_MODES = frozenset({0o440, 0o600, 0o640})
PHASE1_DLP_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "ruleset_version",
        "ruleset_sha256",
        "scanner_sha256",
        "status",
        "ok",
        "source_scope",
        "upstream_source_ocr_dlp",
        "role_closure",
        "layers",
        "implementation_scope",
        "real_candidate",
        "positive_canary",
        "scanner_contract",
    }
)
FINAL_EVIDENCE_TARGET_KINDS: Mapping[str, str] = {
    "disclosure-evidence": "file",
    "offline-test-component-set": "file",
    "offline-test-logs": "directory",
    "offline-test-receipt": "file",
    "suite-build-receipt": "file",
}
OFFLINE_DISCLOSURE_SCHEMA_VERSION = "cloud-v2-offline-disclosure-evidence-v1"
SUITE_BUILD_RECEIPT_SCHEMA_VERSION = "cloud-v2-suite-build-receipt-v2"
MAX_CONTAINER_MEMBER_BYTES = 128 * 1024 * 1024
MAX_CONTAINER_DIRECTORY_BYTES = 128 * 1024 * 1024
MAX_CONTAINER_HEADER_BYTES = 16 * 1024 * 1024
MAX_SCANNED_OBJECTS = 200_000
MAX_SCANNED_BYTES = 2 * 1024 * 1024 * 1024
MAX_CONTAINER_NESTING_DEPTH = 32
MAX_PDF_TOOL_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_PDF_RUNTIME_IMAGE_COUNT = 256
MAX_PDF_RUNTIME_BYTES = 512 * 1024 * 1024
MAX_PDF_CPU_SECONDS = 300
MAX_PDF_TOOL_WALL_SECONDS = 300
_STABLE_CAPTURE_FD_RESERVE = 32
_PDF_TOOL_INVOCATION_FD_RESERVE = 32
_POPPLER_CORE_LIBRARY_PATTERN = re.compile(
    r"^libpoppler(?:\.\d+)*\.dylib$"
)
RUNTIME_FILE_ALLOWLIST = "deploy/cloud_v2/runtime-file-allowlist.json"
BUILDER_FILE_ALLOWLIST = "deploy/cloud_v2/builder-file-allowlist.json"
REQUIRED_RUNTIME_FILES = (
    "deploy/cloud_v2/__init__.py",
    "deploy/cloud_v2/identity_policy.py",
    "deploy/cloud_v2/source_scope.py",
    "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
    "deploy/cloud_v2/stop_b_request.py",
    "deploy/pipeline/cloud_runtime.py",
    "deploy/pipeline/cloud_runtime_config.schema.json",
    "deploy/pipeline/neo4j_import_candidate.py",
    "deploy/pipeline/neo4j_import_config.schema.json",
    "deploy/pipeline/production_embedding_bootstrap.py",
    "deploy/pipeline/production_embedding_candidate.py",
    "deploy/pipeline/production_embedding_config.schema.json",
    "deploy/pipeline/production_embedding_runtime_lock.schema.json",
    "deploy/pipeline/provider_bootstrap.py",
    "deploy/pipeline/provider_runtime_config.schema.json",
    "deploy/pipeline/public_identity_config.schema.json",
    "deploy/pipeline/public_identity_middleware.py",
    "deploy/pipeline/server.py",
    "deploy/pipeline/wsgi.py",
    "deploy/rag_store/authoritative_extractive_fallback.py",
    "deploy/rag_store/cloud_claim_evidence.py",
    "deploy/rag_store/embedding_adapter.py",
    "deploy/rag_store/local_vector_store.py",
    "deploy/rag_store/neo4j_graph_importer.py",
    "deploy/rag_store/provider_http_transport.py",
    "deploy/rag_store/provider_meters.py",
    "deploy/rag_store/provider_wire.py",
    "deploy/rag_store/query_rewrite.py",
    "deploy/rag_store/question_bank_match.py",
    "deploy/rag_store/regulation_timeline.json",
    "deploy/rag_store/request_envelope.py",
    "deploy/rag_store/route_policy.py",
    "deploy/rag_store/runtime_neo4j_reader.py",
    "deploy/rag_store/runtime_query_embedding.py",
    "deploy/rag_store/runtime_sqlite_reader.py",
    "deploy/rag_store/runtime_vector_reader.py",
    "deploy/rag_store/scoped_graph_contract.py",
    "deploy/rag_store/server_answer_coordinator.py",
    "deploy/rag_store/server_answer_model.py",
    "deploy/rag_store/source_authority.py",
    "deploy/rag_store/superseded_passages.json",
)
REQUIRED_BUILDER_FILES = (
    "deploy/cloud_v2/__init__.py",
    "deploy/cloud_v2/source_scope.py",
    "deploy/cloud_v2/stop-b-external-processing-request.schema.json",
    "deploy/cloud_v2/stop_b_request.py",
    "deploy/pipeline/production_embedding_bootstrap.py",
    "deploy/pipeline/production_embedding_candidate.py",
    "deploy/pipeline/production_embedding_config.schema.json",
    "deploy/pipeline/production_embedding_runtime_lock.schema.json",
    "deploy/pipeline/provider_bootstrap.py",
    "deploy/pipeline/provider_runtime_config.schema.json",
    "deploy/rag_store/embedding_adapter.py",
    "deploy/rag_store/local_vector_store.py",
    "deploy/rag_store/provider_http_transport.py",
    "deploy/rag_store/provider_meters.py",
    "deploy/rag_store/provider_wire.py",
    "deploy/rag_store/runtime_query_embedding.py",
    "deploy/rag_store/runtime_sqlite_reader.py",
    "deploy/rag_store/scoped_graph_contract.py",
    "deploy/rag_store/server_answer_model.py",
    "deploy/rag_store/source_authority.py",
)
GOVERNANCE_TOP_LEVEL_FILES = (
    "CLOUD_SOURCE_ALLOWLIST.json",
    "REDACTION_POLICY.json",
    "SOURCE_MANIFEST.sha256",
    "SOURCE_PATHS.json",
    "STOP_A_REVISION_APPROVAL_RECEIPT.json",
    "app_package_candidate_receipt.json",
    "source_dlp_receipt.json",
    "source_integrity_receipt.json",
    "source_redaction_receipt.json",
    "visual_qa_receipt.json",
)
GOVERNANCE_REVIEW_EVIDENCE_ROOT = "visual-qa"
PHASE1_TOP_LEVEL_FILES = (
    ".gitattributes",
    "APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md",
    "CLOUD_MIGRATION_DECISIONS.json",
    "CODE_MANIFEST.sha256",
    "DEPLOY.md",
    "KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md",
    "MANIFEST.sha256",
    "README.md",
    "STOP_B_EXTERNAL_PROCESSING_REQUEST.json",
    "USAGE.md",
)
PHASE1_TREE_ROOTS = (
    "deploy/cloud_v2",
    "operator-companion",
    "skills/knowledge-graph-cloud",
)
FORBIDDEN_IMPLEMENTATION_DIRECTORY_NAMES = frozenset({"__pycache__"})
IGNORED_IMPLEMENTATION_FILE_NAMES = frozenset({".DS_Store"})
FORBIDDEN_IMPLEMENTATION_FILE_SUFFIXES = frozenset({".pyc"})
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".ndjson",
    ".log",
    ".out",
    ".xml",
    ".rels",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".py",
    ".js",
    ".mjs",
    ".html",
    ".css",
    ".sha256",
    ".lock",
}
IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "email",
        re.compile(r"(?i)(?<![\w.+-])[A-Z0-9._%+-]{1,64}@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])"),
    ),
    ("cn_mobile", re.compile(r"(?<![A-Za-z0-9])1[3-9]\d{9}(?![A-Za-z0-9])")),
    (
        "cn_landline",
        re.compile(r"(?<![A-Za-z0-9])0\d{2,3}[- ]?\d{7,8}(?![A-Za-z0-9])"),
    ),
    (
        "host_absolute_path",
        re.compile(
            r"(?:/"
            + "Users/"
            + r"|(?i:[A-Z]:\\"
            + "Users"
            + r"\\)|/home/[A-Za-z0-9._-]+/|\."
            + "openclaw"
            + r"(?:/|\\))"
        ),
    ),
    (
        "feishu_lark_identifier",
        re.compile(
            r"(?i)(?:"
            r"(?<![A-Za-z0-9_])(?:ou|oc|on|cli)_[A-Za-z0-9]{8,}(?![A-Za-z0-9_])|"
            r"(?:tenant|user|app)_access_token\s*[=:]\s*['\"]?"
            r"(?!secretref:|fake-|redacted\b|<|\$\{|\{\{)[A-Za-z0-9._-]{8,}"
            r")"
        ),
    ),
    (
        "credential_token",
        re.compile(
            r"(?i)(?:"
            r"(?<![A-Za-z0-9])(?:sk|ak)-[A-Za-z0-9_-]{16,}(?![A-Za-z0-9])|"
            r"(?<![A-Za-z0-9])AKIA[A-Z0-9]{16}(?![A-Za-z0-9])|"
            r"(?<![A-Za-z0-9])(?:ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{16,}(?![A-Za-z0-9])|"
            r"\bBearer\s+(?!fake-|redacted\b|<|\$\{|\{\{)[A-Za-z0-9._~-]{16,}"
            r")"
        ),
    ),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "literal_secret",
        re.compile(
            r"(?i)['\"]?(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|authorization)['\"]?"
            r"\s*[=:]\s*(?:"
            r"['\"](?!secretref:|fake-|redacted\b|<|\$\{|\{\{)[^'\"\r\n]{8,}['\"]|"
            r"(?!secretref:|fake-|redacted\b|<|\$\{|\{\{)[^\s,'\";#()\[\]{}]{8,}"
            r"(?=\s|[,;'\"#]|$)"
            r")"
        ),
    ),
    (
        "internal_domain",
        re.compile(r"(?i)\b(?:[A-Za-z0-9-]+\.)+(?:internal|corp|lan|local)\b"),
    ),
    (
        "ipv4_address",
        re.compile(
            r"(?<![A-Za-z0-9])(?:"
            r"10(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}|"
            r"172\.(?:1[6-9]|2\d|3[01])(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){2}|"
            r"192\.168(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){2}|"
            r"169\.254(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){2}"
            r")(?![A-Za-z0-9])"
        ),
    ),
    (
        "ipv6_address",
        re.compile(
            r"(?i)(?<![A-F0-9:])(?:f[cd][0-9a-f]{2}|fe[89ab][0-9a-f])"
            r"(?::[0-9a-f]{0,4}){2,7}(?![A-F0-9:/])"
        ),
    ),
    (
        "cn_id_number",
        re.compile(
            r"(?<![A-Za-z0-9])[1-8]\d{5}(?:19|20)\d{2}"
            r"(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]"
            r"(?![A-Za-z0-9])"
        ),
    ),
)

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
UPSTREAM_SOURCE_DLP_SCHEMA_VERSION = "cloud-dlp-receipt-v3"
UPSTREAM_SOURCE_DLP_BINDINGS: Mapping[str, Any] = {
    "ocr": {
        "engine": "tesseract",
        "executable_sha256": "6855d30ee1e9e97de11a58624973d2c7eb115a050df64fc3ba88b4077e153997",
        "language_data_sha256": {
            "chi_sim": "a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730",
            "eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
        },
        "languages": "chi_sim+eng",
        "timeout_seconds": 120.0,
    },
    "pdf_page_renderer": {
        "dpi": 300,
        "engine": "poppler-pdftoppm",
        "executable_sha256": "504dd5b6efe73d7d23bc04c90d2cfd75962b8893df95de6db7f45ab54bf47fc1",
        "timeout_seconds": 120.0,
    },
}


class DLPError(RuntimeError):
    """A scan target is unsafe, incomplete, or contains a prohibited value."""


class ReceiptPublicationState(str, Enum):
    COMMITTED = "COMMITTED"
    COMMITTED_DURABILITY_UNKNOWN = "COMMITTED_DURABILITY_UNKNOWN"
    COMMITTED_MAINTENANCE_REQUIRED = "COMMITTED_MAINTENANCE_REQUIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class ReceiptPublicationOutcome:
    state: ReceiptPublicationState
    receipt_sha256: str
    final_identity_verified: bool | None
    directory_fsync_ok: bool | None
    maintenance_required: bool
    maintenance_error_types: tuple[str, ...] = ()
    safe_to_retry: bool = False


class DLPReceiptPublicationError(DLPError):
    """A receipt may already be committed and must not be retried blindly."""

    def __init__(self, message: str, outcome: ReceiptPublicationOutcome) -> None:
        super().__init__(message)
        self.outcome = outcome


def _publication_error_message(state: ReceiptPublicationState) -> str:
    if state is ReceiptPublicationState.COMMITTED:
        return "DLP receipt committed; inspect the existing receipt before any retry"
    if state is ReceiptPublicationState.COMMITTED_MAINTENANCE_REQUIRED:
        return "DLP receipt committed but post-commit maintenance is required"
    if state is ReceiptPublicationState.COMMITTED_DURABILITY_UNKNOWN:
        return "DLP receipt committed but directory durability is unknown"
    return "DLP receipt publication requires explicit reconciliation"


@dataclass(frozen=True, order=True)
class Finding:
    object_id: str
    rule_id: str
    value_sha256: str


@dataclass(frozen=True, order=True)
class _NodeState:
    device: int
    inode: int
    mode: int
    link_count: int
    size: int
    mtime_ns: int
    ctime_ns: int


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
        return
    except BaseException as first_error:
        try:
            os.fstat(descriptor)
        except OSError:
            raise first_error
        try:
            os.close(descriptor)
        except BaseException as retry_error:
            try:
                first_error.add_note(
                    f"descriptor close retry failed: {type(retry_error).__name__}"
                )
            except (AttributeError, TypeError):
                pass
        raise first_error


_CLEANUP_ERROR_TYPES_ATTRIBUTE = "_dlp_cleanup_error_types"


def _attached_cleanup_error_types(error: BaseException) -> tuple[str, ...]:
    value = getattr(error, _CLEANUP_ERROR_TYPES_ATTRIBUTE, ())
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        return ()
    return value


def _attach_cleanup_failures(
    target: BaseException,
    failures: Iterable[BaseException],
) -> None:
    names = list(_attached_cleanup_error_types(target))
    for failure in failures:
        names.append(type(failure).__name__)
        names.extend(_attached_cleanup_error_types(failure))
    try:
        setattr(
            target,
            _CLEANUP_ERROR_TYPES_ATTRIBUTE,
            tuple(dict.fromkeys(names)),
        )
    except (AttributeError, TypeError):
        pass


def _drain_cleanup(actions: Iterable[Callable[[], None]]) -> BaseException | None:
    first_error: BaseException | None = None
    for action in actions:
        try:
            action()
        except BaseException as exc:
            if first_error is None:
                first_error = exc
            else:
                _attach_cleanup_failures(first_error, (exc,))
                try:
                    first_error.add_note(
                        f"additional cleanup failure: {type(exc).__name__}"
                    )
                except (AttributeError, TypeError):
                    pass
    return first_error


def _finish_cleanup(error: BaseException | None) -> None:
    if error is None:
        return
    active = sys.exception()
    if active is not None:
        _attach_cleanup_failures(active, (error,))
        try:
            active.add_note(f"cleanup failure: {type(error).__name__}")
        except (AttributeError, TypeError):
            pass
        return
    raise error


def _revalidate_then_close(
    revalidate: Callable[[], None],
    close: Callable[[], None],
    *,
    body_failed: bool,
) -> None:
    errors: list[BaseException] = []
    maintenance_errors: list[BaseException] = []
    for index, action in enumerate((revalidate, close)):
        try:
            action()
        except BaseException as exc:
            errors.append(exc)
            if index == 1:
                maintenance_errors.append(exc)
    if not errors:
        return
    active = sys.exception()
    if body_failed and active is not None:
        _attach_cleanup_failures(active, maintenance_errors)
        for error in errors:
            try:
                active.add_note(f"cleanup failure: {type(error).__name__}")
            except (AttributeError, TypeError):
                pass
        return
    first = errors[0]
    for error in errors[1:]:
        _attach_cleanup_failures(first, (error,))
        try:
            first.add_note(f"additional cleanup failure: {type(error).__name__}")
        except (AttributeError, TypeError):
            pass
    raise first


@dataclass
class _StableCaptureBudget:
    object_count: int = 0
    byte_count: int = 0

    def reserve_node(self, kind: str, state: _NodeState) -> None:
        if kind not in {"directory", "file"}:
            raise DLPError("DLP stable-capture node kind is invalid")
        next_object_count = self.object_count + 1
        next_byte_count = self.byte_count + (state.size if kind == "file" else 0)
        if next_object_count > MAX_SCANNED_OBJECTS:
            raise DLPError("DLP stable-capture object-count limit exceeded")
        if next_byte_count > MAX_SCANNED_BYTES:
            raise DLPError("DLP stable-capture byte limit exceeded")
        self.object_count = next_object_count
        self.byte_count = next_byte_count

    def require_file_descriptors(self, file_count: int) -> None:
        try:
            soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        except (OSError, ValueError) as exc:
            raise DLPError("DLP stable-capture file-descriptor limit is unavailable") from exc
        if soft_limit != resource.RLIM_INFINITY:
            open_count = _open_file_descriptor_count()
            required = open_count + (2 * file_count) + _STABLE_CAPTURE_FD_RESERVE
            if required > soft_limit:
                raise DLPError("DLP stable-capture file-descriptor limit exceeded")


@dataclass
class _HeldPayload:
    path: Path
    field: str
    parent_fd: int
    descriptor: int
    parent_state: _NodeState
    file_state: _NodeState
    payload: bytes
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        error = _drain_cleanup(
            (
                lambda: _close_descriptor(self.descriptor),
                lambda: _close_descriptor(self.parent_fd),
            )
        )
        if error is not None:
            raise error


@dataclass
class _HeldTree:
    path: Path
    field: str
    descriptor: int
    root_state: _NodeState
    entries: tuple["_TreeEntry", ...]
    files: dict[str, _HeldPayload]
    closed: bool = False

    def revalidate(self) -> None:
        if self.closed:
            raise DLPError(f"{self.field} held descriptor is closed")
        for relative in sorted(self.files):
            _revalidate_held_payload(self.files[relative])
        if _walk_held_tree(
            self.descriptor,
            allow_empty_directories=True,
        ) != self.entries:
            raise DLPError(f"{self.field} identity changed during DLP operation")
        _revalidate_held_directory(
            self.path,
            self.descriptor,
            self.root_state,
            self.field,
        )

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        actions: list[Callable[[], None]] = [
            self.files[relative].close
            for relative in sorted(self.files, reverse=True)
        ]
        actions.append(lambda: _close_descriptor(self.descriptor))
        error = _drain_cleanup(actions)
        if error is not None:
            raise error


@dataclass
class _PDFToolSet:
    tools: dict[str, _HeldPayload]
    execution_tools: dict[str, _HeldPayload]
    source_libraries: dict[str, _HeldPayload]
    execution_libraries: dict[str, _HeldPayload]
    native_closures: dict[str, object]
    library_aliases: dict[str, str]
    library_alias_states: dict[str, _NodeState]
    runtime_data: _HeldTree
    runtime_data_identity: dict[str, object]
    execution_root: tempfile.TemporaryDirectory[str]
    bundle_root: Path
    library_root: Path
    scratch_root: Path
    sandbox_executable: _HeldPayload
    environment_executable: _HeldPayload
    closed: bool = False

    def revalidate(self) -> None:
        if self.closed:
            raise DLPError("PDF DLP tool binding is closed")
        self.runtime_data.revalidate()
        for name in sorted(self.tools):
            _revalidate_held_payload(self.tools[name])
            execution = self.execution_tools.get(name)
            if execution is None:
                raise DLPError("PDF DLP execution snapshot is incomplete")
            _revalidate_held_payload(execution)
            if execution.payload != self.tools[name].payload:
                raise DLPError("PDF DLP execution snapshot differs from held bytes")
            try:
                current_closure = _external_tool_macho_closure(
                    self.tools[name].path,
                    tool_name=name,
                )
            except OfflineEvidenceError as exc:
                raise DLPError("PDF DLP native closure cannot be revalidated") from exc
            expected_closure = self.native_closures.get(name)
            if current_closure != expected_closure:
                raise DLPError("PDF DLP native closure identity changed")
        for path, held in sorted(self.source_libraries.items()):
            _revalidate_held_payload(held)
            digest = hashlib.sha256(held.payload).hexdigest()
            execution = self.execution_libraries.get(digest)
            if execution is None or execution.payload != held.payload:
                raise DLPError("PDF DLP private library closure is incomplete")
            _revalidate_held_payload(execution)
        for alias, digest in sorted(self.library_aliases.items()):
            alias_path = self.library_root / alias
            expected_target = f"../objects/{digest}.dylib"
            try:
                state = os.lstat(alias_path)
                target = os.readlink(alias_path)
            except OSError as exc:
                raise DLPError("PDF DLP private library alias is unavailable") from exc
            if (
                not stat.S_ISLNK(state.st_mode)
                or _node_state(state) != self.library_alias_states.get(alias)
                or target != expected_target
            ):
                raise DLPError("PDF DLP private library alias identity changed")
            try:
                if alias_path.resolve(strict=True) != self.execution_libraries[digest].path:
                    raise DLPError("PDF DLP private library alias target changed")
            except (OSError, KeyError) as exc:
                raise DLPError("PDF DLP private library alias target changed") from exc
        _revalidate_held_payload(self.sandbox_executable)
        _revalidate_held_payload(self.environment_executable)

    def command_path(self, name: str) -> str:
        try:
            held = self.execution_tools[name]
        except KeyError as exc:
            raise DLPError(f"unbound PDF DLP tool: {name}") from exc
        return str(held.path)

    def environment(self) -> dict[str, str]:
        return {"LC_ALL": "C", "LANG": "C"}

    def receipt(self) -> dict[str, dict[str, object]]:
        self.revalidate()
        return {
            name: {
                "path": str(held.path),
                "sha256": hashlib.sha256(held.payload).hexdigest(),
                "device": held.file_state.device,
                "inode": held.file_state.inode,
                "mode": stat.S_IMODE(held.file_state.mode),
                "execution_snapshot_sha256": hashlib.sha256(
                    self.execution_tools[name].payload
                ).hexdigest(),
                "execution_snapshot_mode": stat.S_IMODE(
                    self.execution_tools[name].file_state.mode
                ),
                "execution_snapshot_private": True,
                "native_closure_identity": self.native_closures[name].identity,
                "private_library_count": len(self.execution_libraries),
                "private_library_set_sha256": _canonical_identity_sha256(
                    {
                        digest: hashlib.sha256(library.payload).hexdigest()
                        for digest, library in sorted(self.execution_libraries.items())
                    }
                ),
                "private_library_alias_count": len(self.library_aliases),
                "private_library_alias_set_sha256": _canonical_identity_sha256(
                    self.library_aliases
                ),
                "poppler_runtime_data": self.runtime_data_identity,
                "sandbox_executable_sha256": hashlib.sha256(
                    self.sandbox_executable.payload
                ).hexdigest(),
                "environment_executable_sha256": hashlib.sha256(
                    self.environment_executable.payload
                ).hexdigest(),
                "sandbox_profile_template_sha256": hashlib.sha256(
                    _PDF_SANDBOX_PROFILE_TEMPLATE.encode("utf-8")
                ).hexdigest(),
            }
            for name, held in sorted(self.tools.items())
        }

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        actions: list[Callable[[], None]] = [
            self.execution_tools[name].close
            for name in sorted(self.execution_tools, reverse=True)
        ]
        actions.extend(
            self.execution_libraries[digest].close
            for digest in sorted(self.execution_libraries, reverse=True)
        )
        actions.append(self.execution_root.cleanup)
        actions.extend(
            self.source_libraries[path].close
            for path in sorted(self.source_libraries, reverse=True)
        )
        actions.extend(
            self.tools[name].close for name in sorted(self.tools, reverse=True)
        )
        actions.append(self.runtime_data.close)
        actions.extend(
            (self.sandbox_executable.close, self.environment_executable.close)
        )
        error = _drain_cleanup(actions)
        if error is not None:
            raise error


@dataclass
class _WrittenJSON:
    held: _HeldPayload
    digest: str
    final_path: Path
    baseline_names: frozenset[str]
    staging_name: str
    published: bool = False
    removed: bool = False
    commit_attempted: bool = False
    commit_succeeded: bool = False
    reconciliation_required: bool = False
    publication_outcome: ReceiptPublicationOutcome | None = None

    def revalidate(self) -> None:
        _revalidate_held_payload(self.held)
        expected_name = self.final_path.name if self.published else self.staging_name
        expected_names = set(self.baseline_names) | {expected_name}
        try:
            current_names = set(os.listdir(self.held.parent_fd))
        except OSError as exc:
            raise DLPError("DLP receipt parent cannot be revalidated") from exc
        if current_names != expected_names or self.held.path.name != expected_name:
            raise DLPError("DLP receipt parent membership changed")

    def publish(self) -> ReceiptPublicationOutcome:
        if (
            self.published
            or self.removed
            or self.commit_attempted
            or self.commit_succeeded
            or self.reconciliation_required
        ):
            raise DLPError("DLP receipt staging state is invalid")
        self.revalidate()
        self.commit_attempted = True
        try:
            _atomic_noreplace_rename(
                self.staging_name,
                self.final_path.name,
                directory_fd=self.held.parent_fd,
            )
        except BaseException as exc:
            state = self._publication_state()
            if state == "committed":
                self._latch_committed()
                return self._finish_committed_publication()
            if state == "precommit":
                try:
                    committed = self._remove_staging_after_failed_commit(exc)
                except BaseException as cleanup_exc:
                    self._require_reconciliation(
                        final_identity_verified=False,
                        directory_fsync_ok=None,
                        cause=cleanup_exc,
                    )
                if committed:
                    return self._finish_committed_publication()
                raise
            self._require_reconciliation(
                final_identity_verified=None,
                directory_fsync_ok=None,
                cause=exc,
            )
        self._latch_committed()
        return self._finish_committed_publication()

    def _latch_committed(self) -> None:
        self.commit_succeeded = True
        self.publication_outcome = ReceiptPublicationOutcome(
            state=ReceiptPublicationState.COMMITTED_DURABILITY_UNKNOWN,
            receipt_sha256=self.digest,
            final_identity_verified=None,
            directory_fsync_ok=None,
            maintenance_required=False,
        )

    def _require_reconciliation(
        self,
        *,
        final_identity_verified: bool | None,
        directory_fsync_ok: bool | None,
        cause: BaseException,
    ) -> None:
        self.reconciliation_required = True
        outcome = ReceiptPublicationOutcome(
            state=ReceiptPublicationState.RECONCILIATION_REQUIRED,
            receipt_sha256=self.digest,
            final_identity_verified=final_identity_verified,
            directory_fsync_ok=directory_fsync_ok,
            maintenance_required=False,
        )
        self.publication_outcome = outcome
        raise DLPReceiptPublicationError(
            "DLP receipt publication requires explicit reconciliation",
            outcome,
        ) from cause

    def _finish_committed_publication(self) -> ReceiptPublicationOutcome:
        fsync_error: BaseException | None = None
        try:
            os.fsync(self.held.parent_fd)
        except BaseException as exc:
            fsync_error = exc
        state = self._publication_state()
        if state != "committed":
            self._require_reconciliation(
                final_identity_verified=False,
                directory_fsync_ok=fsync_error is None,
                cause=fsync_error or DLPError("committed receipt identity is ambiguous"),
            )
        try:
            descriptor_state = _node_state(os.fstat(self.held.descriptor))
            parent_state = _node_state(os.fstat(self.held.parent_fd))
        except BaseException as exc:
            self._require_reconciliation(
                final_identity_verified=None,
                directory_fsync_ok=fsync_error is None,
                cause=exc,
            )
        self.published = True
        self.reconciliation_required = False
        self.held.path = self.final_path
        self.held.file_state = descriptor_state
        self.held.parent_state = parent_state
        if fsync_error is not None:
            outcome = ReceiptPublicationOutcome(
                state=ReceiptPublicationState.COMMITTED_DURABILITY_UNKNOWN,
                receipt_sha256=self.digest,
                final_identity_verified=True,
                directory_fsync_ok=False,
                maintenance_required=False,
            )
            self.publication_outcome = outcome
            return outcome
        outcome = ReceiptPublicationOutcome(
            state=ReceiptPublicationState.COMMITTED,
            receipt_sha256=self.digest,
            final_identity_verified=True,
            directory_fsync_ok=True,
            maintenance_required=False,
        )
        self.publication_outcome = outcome
        return outcome

    def _publication_state(self) -> str:
        try:
            descriptor_state = _node_state(os.fstat(self.held.descriptor))
            held_parent_state = _node_state(os.fstat(self.held.parent_fd))
            payload, payload_state = _read_open_payload(
                self.held.descriptor,
                field="staged DLP receipt",
                max_bytes=max(len(self.held.payload), 1),
            )
            reopened_path, reopened_parent, reopened_state = _open_directory_path(
                self.final_path.parent,
                "DLP receipt parent",
            )
            try:
                if (
                    reopened_path != self.final_path.parent
                    or reopened_state != held_parent_state
                ):
                    return "ambiguous"
            finally:
                _close_descriptor(reopened_parent)
        except BaseException:
            return "ambiguous"
        if payload_state != descriptor_state or payload != self.held.payload:
            return "ambiguous"

        def optional_state(name: str) -> _NodeState | None:
            try:
                return _node_state(
                    os.stat(
                        name,
                        dir_fd=self.held.parent_fd,
                        follow_symlinks=False,
                    )
                )
            except FileNotFoundError:
                return None
            except OSError:
                raise

        try:
            staging_state = optional_state(self.staging_name)
            final_state = optional_state(self.final_path.name)
        except OSError:
            return "ambiguous"
        if (
            staging_state is not None
            and final_state is None
            and staging_state == descriptor_state
            and descriptor_state.link_count == 1
        ):
            return "precommit"
        if (
            staging_state is None
            and final_state is not None
            and final_state == descriptor_state
            and descriptor_state.link_count == 1
        ):
            return "committed"
        return "ambiguous"

    def _remove_staging_after_failed_commit(self, cause: BaseException) -> bool:
        try:
            entry = _node_state(
                os.stat(
                    self.staging_name,
                    dir_fd=self.held.parent_fd,
                    follow_symlinks=False,
                )
            )
            descriptor_state = _node_state(os.fstat(self.held.descriptor))
            if entry != descriptor_state:
                raise DLPError("DLP receipt staging identity changed before cleanup")
            os.unlink(self.staging_name, dir_fd=self.held.parent_fd)
            os.fsync(self.held.parent_fd)
        except FileNotFoundError as missing_exc:
            state = self._publication_state()
            if state == "committed":
                self._latch_committed()
                return True
            raise DLPError(
                "DLP receipt namespace changed during failed-publication cleanup"
            ) from missing_exc
        except BaseException as cleanup_exc:
            try:
                cleanup_exc.add_note(f"publication failure: {type(cause).__name__}")
            except (AttributeError, TypeError):
                pass
            raise DLPError("DLP receipt publication cleanup failed") from cleanup_exc
        self.removed = True
        return False

    def remove_if_unchanged(self) -> None:
        if (
            self.removed
            or self.published
            or self.commit_attempted
            or self.commit_succeeded
            or self.reconciliation_required
        ):
            return
        try:
            entry = _node_state(
                os.stat(
                    self.staging_name,
                    dir_fd=self.held.parent_fd,
                    follow_symlinks=False,
                )
            )
        except FileNotFoundError:
            self.removed = True
            return
        except OSError as exc:
            raise DLPError("new DLP receipt could not be inspected for cleanup") from exc
        if entry != self.held.file_state:
            raise DLPError("new DLP receipt identity changed before cleanup")
        try:
            os.unlink(self.staging_name, dir_fd=self.held.parent_fd)
            os.fsync(self.held.parent_fd)
        except OSError as exc:
            raise DLPError("new DLP receipt could not be removed after failure") from exc
        self.removed = True

    def close(self) -> None:
        self.held.close()


def _atomic_noreplace_rename(
    source_name: str,
    destination_name: str,
    *,
    directory_fd: int,
) -> None:
    if (
        not source_name
        or not destination_name
        or "/" in source_name
        or "/" in destination_name
        or source_name in {".", ".."}
        or destination_name in {".", ".."}
    ):
        raise DLPError("DLP receipt rename names are invalid")
    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        try:
            rename = libc.renameatx_np
        except AttributeError as exc:
            raise DLPError("atomic no-replace rename is unavailable") from exc
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(directory_fd, source, directory_fd, destination, 0x00000004)
    elif sys.platform.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as exc:
            raise DLPError("atomic no-replace rename is unavailable") from exc
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(directory_fd, source, directory_fd, destination, 0x00000001)
    else:
        raise DLPError("atomic no-replace rename is unsupported on this platform")
    if result == 0:
        return
    error_code = ctypes.get_errno()
    if error_code == errno.EEXIST:
        raise FileExistsError(error_code, os.strerror(error_code), destination_name)
    raise OSError(error_code, os.strerror(error_code), destination_name)


@dataclass(frozen=True, order=True)
class _TreeEntry:
    relative_path: str
    kind: str
    state: _NodeState


@dataclass(frozen=True)
class ImplementationDiscovery:
    root: Path
    relative_paths: tuple[str, ...]
    runtime_allowlist_sha256: str
    runtime_relative_paths: tuple[str, ...]
    builder_allowlist_sha256: str
    builder_relative_paths: tuple[str, ...]


_SYSTEM_PATH_ALIAS_TARGETS = {
    Path("/var"): Path("/private/var"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/etc"): Path("/private/etc"),
}


def _node_state(value: os.stat_result) -> _NodeState:
    return _NodeState(
        device=value.st_dev,
        inode=value.st_ino,
        mode=value.st_mode,
        link_count=value.st_nlink,
        size=value.st_size,
        mtime_ns=value.st_mtime_ns,
        ctime_ns=value.st_ctime_ns,
    )


def _same_opened_directory(
    inspected: os.stat_result,
    opened: os.stat_result,
) -> bool:
    return (
        inspected.st_dev == opened.st_dev
        and inspected.st_ino == opened.st_ino
        and stat.S_ISDIR(inspected.st_mode)
        and stat.S_ISDIR(opened.st_mode)
    )


def _open_file_descriptor_count() -> int:
    for candidate in (Path("/dev/fd"), Path("/proc/self/fd")):
        try:
            return len(os.listdir(candidate))
        except OSError:
            continue
    raise DLPError("DLP open file-descriptor count is unavailable")


def _stable_absolute_path(raw: str | Path, field: str) -> Path:
    try:
        value = os.fspath(raw)
    except TypeError as exc:
        raise DLPError(f"{field} path is invalid") from exc
    if isinstance(value, bytes) or not value or "\x00" in value:
        raise DLPError(f"{field} path is invalid")
    path = Path(value)
    if not path.is_absolute():
        path = Path(os.path.abspath(path))
    if sys.platform == "darwin":
        for alias, target in _SYSTEM_PATH_ALIAS_TARGETS.items():
            try:
                relative = path.relative_to(alias)
            except ValueError:
                continue
            return target / relative
    return path


def _open_directory_path(raw: str | Path, field: str) -> tuple[Path, int, _NodeState]:
    path = _stable_absolute_path(raw, field)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        current = os.open("/", flags)
    except OSError as exc:
        raise DLPError(f"{field} cannot be opened safely") from exc
    try:
        for component in path.parts[1:]:
            child: int | None = None
            try:
                inspected = os.stat(
                    component,
                    dir_fd=current,
                    follow_symlinks=False,
                )
                if stat.S_ISLNK(inspected.st_mode):
                    raise DLPError(
                        f"{field} must be a real directory; path contains a symlink"
                    )
                if not stat.S_ISDIR(inspected.st_mode):
                    raise DLPError(f"{field} path contains a non-directory")
                child = os.open(component, flags, dir_fd=current)
                opened = os.fstat(child)
            except DLPError:
                if child is not None:
                    _finish_cleanup(
                        _drain_cleanup((lambda: _close_descriptor(child),))
                    )
                raise
            except OSError as exc:
                if child is not None:
                    _finish_cleanup(
                        _drain_cleanup((lambda: _close_descriptor(child),))
                    )
                raise DLPError(f"{field} cannot be opened safely") from exc
            except BaseException:
                if child is not None:
                    _finish_cleanup(
                        _drain_cleanup((lambda: _close_descriptor(child),))
                    )
                raise
            if not _same_opened_directory(inspected, opened):
                _close_descriptor(child)
                raise DLPError(f"{field} identity changed while opening")
            previous = current
            current = child
            child = None
            _close_descriptor(previous)
        state = _node_state(os.fstat(current))
        if not stat.S_ISDIR(state.mode):
            raise DLPError(f"{field} is not a directory")
        return path, current, state
    except BaseException:
        _finish_cleanup(_drain_cleanup((lambda: _close_descriptor(current),)))
        raise


def _read_open_payload(
    descriptor: int,
    *,
    field: str,
    max_bytes: int,
) -> tuple[bytes, _NodeState]:
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink not in {0, 1}
            or before.st_size > max_bytes
        ):
            raise DLPError(f"{field} exceeds its stable regular-file boundary")
        chunks: list[bytes] = []
        offset = 0
        while offset < before.st_size:
            block = os.pread(
                descriptor,
                min(1024 * 1024, before.st_size - offset),
                offset,
            )
            if not block:
                raise DLPError(f"{field} became shorter while reading")
            chunks.append(block)
            offset += len(block)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    except DLPError:
        raise
    except OSError as exc:
        raise DLPError(f"{field} cannot be read safely") from exc
    if _node_state(before) != _node_state(after) or len(payload) != after.st_size:
        raise DLPError(f"{field} identity changed while reading")
    return payload, _node_state(after)


def _open_held_payload(
    raw: str | Path,
    field: str,
    *,
    max_bytes: int = MAX_SCANNED_BYTES,
    expected_state: _NodeState | None = None,
) -> _HeldPayload:
    path = _stable_absolute_path(raw, field)
    parent_path, parent_fd, parent_state = _open_directory_path(path.parent, f"{field} parent")
    descriptor: int | None = None
    try:
        try:
            inspected = os.stat(
                path.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise DLPError(f"{field} cannot be inspected") from exc
        inspected_state = _node_state(inspected)
        if stat.S_ISLNK(inspected.st_mode) or not stat.S_ISREG(inspected.st_mode):
            raise DLPError(f"{field} must be a regular unsymlinked file")
        if inspected.st_nlink != 1:
            raise DLPError(f"{field} must not be a hardlink")
        if expected_state is not None and inspected_state != expected_state:
            raise DLPError(f"{field} identity changed before scanning")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(path.name, flags, dir_fd=parent_fd)
            opened = os.fstat(descriptor)
        except OSError as exc:
            raise DLPError(f"{field} cannot be opened safely") from exc
        if _node_state(opened) != inspected_state:
            raise DLPError(f"{field} identity changed while opening")
        payload, payload_state = _read_open_payload(
            descriptor,
            field=field,
            max_bytes=max_bytes,
        )
        try:
            entry_after = os.stat(
                path.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise DLPError(f"{field} identity changed while reading") from exc
        if (
            _node_state(entry_after) != payload_state
            or _node_state(os.fstat(parent_fd)) != parent_state
            or parent_path != path.parent
        ):
            raise DLPError(f"{field} identity changed while reading")
        return _HeldPayload(
            path=path,
            field=field,
            parent_fd=parent_fd,
            descriptor=descriptor,
            parent_state=parent_state,
            file_state=payload_state,
            payload=payload,
        )
    except BaseException:
        actions: list[Callable[[], None]] = []
        if descriptor is not None:
            actions.append(lambda: _close_descriptor(descriptor))
        actions.append(lambda: _close_descriptor(parent_fd))
        _finish_cleanup(_drain_cleanup(actions))
        raise


def _revalidate_held_payload(held: _HeldPayload) -> None:
    if held.closed:
        raise DLPError(f"{held.field} held descriptor is closed")
    try:
        parent_state = _node_state(os.fstat(held.parent_fd))
        descriptor_state = _node_state(os.fstat(held.descriptor))
        entry_state = _node_state(
            os.stat(
                held.path.name,
                dir_fd=held.parent_fd,
                follow_symlinks=False,
            )
        )
    except OSError as exc:
        raise DLPError(f"{held.field} identity changed after scanning") from exc
    if parent_state != held.parent_state:
        raise DLPError(f"{held.field} parent identity changed after scanning")
    if descriptor_state != held.file_state or entry_state != held.file_state:
        raise DLPError(f"{held.field} identity changed after scanning")
    reopened_path, reopened_parent, reopened_parent_state = _open_directory_path(
        held.path.parent,
        f"{held.field} parent",
    )
    try:
        if reopened_path != held.path.parent or reopened_parent_state != held.parent_state:
            raise DLPError(f"{held.field} parent path identity changed after scanning")
        reopened_entry = os.stat(
            held.path.name,
            dir_fd=reopened_parent,
            follow_symlinks=False,
        )
        if _node_state(reopened_entry) != held.file_state:
            raise DLPError(f"{held.field} path identity changed after scanning")
    except OSError as exc:
        raise DLPError(f"{held.field} path identity changed after scanning") from exc
    finally:
        _close_descriptor(reopened_parent)
    payload, state = _read_open_payload(
        held.descriptor,
        field=held.field,
        max_bytes=max(len(held.payload), 1),
    )
    if state != held.file_state or payload != held.payload:
        raise DLPError(f"{held.field} bytes changed after scanning")


@contextlib.contextmanager
def _held_payload(
    raw: str | Path,
    field: str,
    *,
    max_bytes: int = MAX_SCANNED_BYTES,
    expected_state: _NodeState | None = None,
) -> Iterator[_HeldPayload]:
    held = _open_held_payload(
        raw,
        field,
        max_bytes=max_bytes,
        expected_state=expected_state,
    )
    body_failed = False
    try:
        yield held
    except BaseException:
        body_failed = True
        raise
    finally:
        _revalidate_then_close(
            lambda: _revalidate_held_payload(held),
            held.close,
            body_failed=body_failed,
        )


def _open_held_tree(
    raw: str | Path,
    field: str,
    *,
    allow_empty_directories: bool = False,
    capture_budget: _StableCaptureBudget | None = None,
) -> _HeldTree:
    path, descriptor, root_state = _open_directory_path(raw, field)
    files: dict[str, _HeldPayload] = {}
    budget = capture_budget or _StableCaptureBudget()
    try:
        entries = _walk_held_tree(
            descriptor,
            allow_empty_directories=allow_empty_directories,
            capture_budget=budget,
        )
        budget.require_file_descriptors(
            sum(entry.kind == "file" for entry in entries)
        )
        for entry in entries:
            if entry.kind != "file":
                continue
            files[entry.relative_path] = _open_held_payload(
                path / entry.relative_path,
                f"{field} file",
                expected_state=entry.state,
            )
        held = _HeldTree(
            path=path,
            field=field,
            descriptor=descriptor,
            root_state=root_state,
            entries=entries,
            files=files,
        )
        held.revalidate()
        return held
    except BaseException:
        actions: list[Callable[[], None]] = [
            files[relative].close for relative in sorted(files, reverse=True)
        ]
        actions.append(lambda: _close_descriptor(descriptor))
        _finish_cleanup(_drain_cleanup(actions))
        raise


@contextlib.contextmanager
def _held_tree(
    raw: str | Path,
    field: str,
    *,
    allow_empty_directories: bool = False,
    capture_budget: _StableCaptureBudget | None = None,
) -> Iterator[_HeldTree]:
    held = _open_held_tree(
        raw,
        field,
        allow_empty_directories=allow_empty_directories,
        capture_budget=capture_budget,
    )
    body_failed = False
    try:
        yield held
    except BaseException:
        body_failed = True
        raise
    finally:
        _revalidate_then_close(
            held.revalidate,
            held.close,
            body_failed=body_failed,
        )


def _available_temporary_bytes(destination: Path) -> int:
    current = destination
    while not current.exists() and current != current.parent:
        current = current.parent
    try:
        return shutil.disk_usage(current).free
    except OSError as exc:
        raise DLPError("DLP stable-capture temporary space is unavailable") from exc


def _materialize_held_tree(held: _HeldTree, destination: Path) -> Path:
    required_bytes = sum(payload.file_state.size for payload in held.files.values())
    if _available_temporary_bytes(destination.parent) < required_bytes:
        raise DLPError("DLP stable-capture temporary space is insufficient")
    destination.mkdir(mode=0o700)
    directories = [entry for entry in held.entries if entry.kind == "directory"]
    for entry in sorted(
        directories,
        key=lambda item: (len(PurePosixPath(item.relative_path).parts), item.relative_path),
    ):
        (destination / entry.relative_path).mkdir(mode=0o700)
    for relative, payload in sorted(held.files.items()):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with target.open("xb") as handle:
            handle.write(payload.payload)
            handle.flush()
            os.fsync(handle.fileno())
        target.chmod(stat.S_IMODE(payload.file_state.mode))
    held.revalidate()
    return destination.resolve(strict=True)


def _materialize_held_payload(held: _HeldPayload, destination: Path) -> Path:
    if _available_temporary_bytes(destination.parent) < held.file_state.size:
        raise DLPError("DLP stable-capture temporary space is insufficient")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with destination.open("xb") as handle:
        handle.write(held.payload)
        handle.flush()
        os.fsync(handle.fileno())
    destination.chmod(stat.S_IMODE(held.file_state.mode))
    _revalidate_held_payload(held)
    return destination.resolve(strict=True)


@dataclass(frozen=True)
class _StableApprovedSourceScope:
    source_root: Path
    governance_root: Path
    records: tuple[ApprovedSource, ...]
    source_manifest_sha256: str
    allowlist_sha256: str
    stop_a_receipt_sha256: str
    source_dlp_receipt_sha256: str
    approval_recorded_at: str
    _identity_record: Mapping[str, Any]

    def identity(self) -> dict[str, Any]:
        return dict(self._identity_record)


@dataclass(frozen=True)
class _Phase1StableView:
    scope: _StableApprovedSourceScope
    authority_root: Path
    derived_root: Path
    code_root: Path
    original_scope: ApprovedSourceScope
    original_trees: tuple[_HeldTree, ...]

    def revalidate(self) -> None:
        try:
            self.original_scope.revalidate()
        except Exception as exc:
            raise DLPError("approved source scope changed during DLP operation") from exc
        for tree in self.original_trees:
            tree.revalidate()


@contextlib.contextmanager
def _phase1_stable_view(
    *,
    scope: ApprovedSourceScope,
    authority_root: str | Path,
    derived_root: str | Path,
    code_root: str | Path,
) -> Iterator[_Phase1StableView]:
    try:
        scope.revalidate()
        source_scope_identity = scope.identity()
    except Exception as exc:
        raise DLPError("approved source scope is stale before DLP scanning") from exc
    with contextlib.ExitStack() as stack:
        capture_budget = _StableCaptureBudget()
        source = stack.enter_context(
            _held_tree(
                scope.source_root,
                "approved source root",
                allow_empty_directories=True,
                capture_budget=capture_budget,
            )
        )
        governance = stack.enter_context(
            _held_tree(
                scope.governance_root,
                "governance root",
                allow_empty_directories=True,
                capture_budget=capture_budget,
            )
        )
        authority = stack.enter_context(
            _held_tree(
                authority_root,
                "authority root",
                allow_empty_directories=True,
                capture_budget=capture_budget,
            )
        )
        derived = stack.enter_context(
            _held_tree(
                derived_root,
                "derived root",
                allow_empty_directories=True,
                capture_budget=capture_budget,
            )
        )
        implementation = stack.enter_context(
            _held_tree(
                code_root,
                "implementation root",
                allow_empty_directories=True,
                capture_budget=capture_budget,
            )
        )
        temporary = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="kg-dlp-phase1-view-"))
        )
        source_view = _materialize_held_tree(source, temporary / "source")
        governance_view = _materialize_held_tree(
            governance,
            temporary / "governance",
        )
        authority_view = _materialize_held_tree(authority, temporary / "authority")
        derived_view = _materialize_held_tree(derived, temporary / "derived")
        implementation_view = _materialize_held_tree(
            implementation,
            temporary / "implementation",
        )
        stable_scope = _StableApprovedSourceScope(
            source_root=source_view,
            governance_root=governance_view,
            records=scope.records,
            source_manifest_sha256=scope.source_manifest_sha256,
            allowlist_sha256=scope.allowlist_sha256,
            stop_a_receipt_sha256=scope.stop_a_receipt_sha256,
            source_dlp_receipt_sha256=scope.source_dlp_receipt_sha256,
            approval_recorded_at=scope.approval_recorded_at,
            _identity_record=source_scope_identity,
        )
        view = _Phase1StableView(
            scope=stable_scope,
            authority_root=authority_view,
            derived_root=derived_view,
            code_root=implementation_view,
            original_scope=scope,
            original_trees=(source, governance, authority, derived, implementation),
        )
        view.revalidate()
        yield view
        view.revalidate()


@dataclass(frozen=True)
class _FinalStableView:
    suite_root: Path
    candidate_receipt_path: Path
    evidence_roots: dict[str, Path]
    original_trees: tuple[_HeldTree, ...]
    original_files: tuple[_HeldPayload, ...]

    def revalidate(self) -> None:
        for tree in self.original_trees:
            tree.revalidate()
        for payload in self.original_files:
            _revalidate_held_payload(payload)


@contextlib.contextmanager
def _final_stable_view(
    *,
    suite_root: str | Path,
    candidate_receipt_path: str | Path,
    evidence_roots: Mapping[str, str | Path],
) -> Iterator[_FinalStableView]:
    component_path = _stable_absolute_path(
        evidence_roots["offline-test-component-set"],
        "offline test component set",
    )
    receipt_path = _stable_absolute_path(
        evidence_roots["offline-test-receipt"],
        "offline test receipt",
    )
    logs_path = _stable_absolute_path(
        evidence_roots["offline-test-logs"],
        "offline test logs",
    )
    offline_root_path = component_path.parent
    if receipt_path.parent != offline_root_path or logs_path != offline_root_path / "logs":
        raise DLPError("offline test evidence paths do not share the exact closed root")

    with contextlib.ExitStack() as stack:
        capture_budget = _StableCaptureBudget()
        suite = stack.enter_context(
            _held_tree(
                suite_root,
                "suite root",
                allow_empty_directories=True,
                capture_budget=capture_budget,
            )
        )
        expected_candidate = (
            suite.path / "server-runtime/evidence/candidate-dlp-receipt.json"
        )
        if _stable_absolute_path(
            candidate_receipt_path,
            "candidate DLP receipt",
        ) != expected_candidate:
            raise DLPError(
                "candidate DLP receipt must be the sealed suite evidence copy"
            )
        offline = stack.enter_context(
            _held_tree(
                offline_root_path,
                "offline test evidence root",
                allow_empty_directories=True,
                capture_budget=capture_budget,
            )
        )
        temporary = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="kg-dlp-final-view-"))
        )
        suite_view = _materialize_held_tree(suite, temporary / "suite")
        offline_view = _materialize_held_tree(offline, temporary / "offline-evidence")
        mapped: dict[str, Path] = {}
        extra_files: list[_HeldPayload] = []
        for label, raw in sorted(evidence_roots.items()):
            original = _stable_absolute_path(raw, f"final evidence {label}")
            try:
                relative = original.relative_to(offline.path)
            except ValueError:
                relative = None
            if relative is not None:
                mapped[label] = offline_view / relative
                continue
            if FINAL_EVIDENCE_TARGET_KINDS[label] != "file":
                raise DLPError(f"final evidence directory escaped its closed root: {label}")
            try:
                external_state = _node_state(os.lstat(original))
            except OSError as exc:
                raise DLPError(f"final evidence file is unavailable: {label}") from exc
            capture_budget.reserve_node("file", external_state)
            held = stack.enter_context(
                _held_payload(original, f"final evidence {label}")
            )
            extra_files.append(held)
            mapped[label] = _materialize_held_payload(
                held,
                temporary / "external-evidence" / label / held.path.name,
            )
        view = _FinalStableView(
            suite_root=suite_view,
            candidate_receipt_path=(
                suite_view / "server-runtime/evidence/candidate-dlp-receipt.json"
            ),
            evidence_roots=mapped,
            original_trees=(suite, offline),
            original_files=tuple(extra_files),
        )
        view.revalidate()
        yield view
        view.revalidate()


_PDF_TOOL_SEARCH_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
_PDF_TOOL_NAMES = ("pdfdetach", "pdfimages", "pdfinfo", "pdftotext")
_PDF_SANDBOX_PROFILE_TEMPLATE = (
    "(version 1)(allow default)(deny network*)"
    "(deny file-read*)(allow file-read* <bound-read-paths>)"
    "(deny file-write*)(allow file-write* <bound-write-paths>)"
    "(deny process-exec*)(allow process-exec <bound-executables>)"
    "(deny process-fork)"
)


def _poppler_runtime_data_root(tools: Mapping[str, _HeldPayload]) -> Path:
    prefixes = {held.path.parent.parent for held in tools.values()}
    if len(prefixes) != 1:
        raise DLPError("PDF DLP tools do not share one installation prefix")
    return next(iter(prefixes)) / "share" / "poppler"


def _pdf_tool_set_fd_budget(
    baseline_open_count: int,
    *,
    tool_count: int,
    runtime_data_file_count: int,
    library_path_count: int,
    unique_library_count: int,
) -> dict[str, object]:
    counts = (
        baseline_open_count,
        tool_count,
        runtime_data_file_count,
        library_path_count,
        unique_library_count,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts
    ):
        raise DLPError("PDF DLP file-descriptor budget is malformed")
    if unique_library_count > library_path_count:
        raise DLPError("PDF DLP unique-library count exceeds its path count")
    closure_increment = (
        (4 * tool_count)
        + (2 * runtime_data_file_count)
        + (2 * library_path_count)
        + (2 * unique_library_count)
        + 5
    )
    try:
        soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError) as exc:
        raise DLPError("PDF DLP file-descriptor limit is unavailable") from exc
    required = baseline_open_count + closure_increment + _PDF_TOOL_INVOCATION_FD_RESERVE
    if soft_limit != resource.RLIM_INFINITY and required > soft_limit:
        raise DLPError("PDF DLP file-descriptor limit exceeded")
    return {
        "persistent_descriptor_formula": "4T+2D+2L+2U+5",
        "tool_count": tool_count,
        "runtime_data_file_count": runtime_data_file_count,
        "library_path_count": library_path_count,
        "unique_library_count": unique_library_count,
        "persistent_descriptor_increment": closure_increment,
        "invocation_descriptor_reserve": _PDF_TOOL_INVOCATION_FD_RESERVE,
        "capacity_preflight_enforced": True,
    }


def _poppler_compiled_data_root_identity(
    tree: _HeldTree,
    source_libraries: Mapping[str, _HeldPayload],
    native_closures: Mapping[str, object],
) -> dict[str, object]:
    core_libraries = [
        held
        for held in source_libraries.values()
        if _POPPLER_CORE_LIBRARY_PATTERN.fullmatch(held.path.name)
    ]
    if len(core_libraries) != 1:
        raise DLPError("Poppler core-library closure is not unique")
    core = core_libraries[0]
    covered_tools: list[str] = []
    for tool_name, closure in sorted(native_closures.items()):
        resolved_images = getattr(closure, "resolved_images", None)
        if not isinstance(resolved_images, tuple) or core.path not in resolved_images:
            raise DLPError("Poppler core library is absent from a tool native closure")
        covered_tools.append(tool_name)
    if set(covered_tools) != set(_PDF_TOOL_NAMES):
        raise DLPError("Poppler core-library tool coverage is incomplete")

    expected_text = str(tree.path)
    candidates: list[tuple[int, str]] = []
    cursor = 0
    while cursor < len(core.payload):
        terminator = core.payload.find(b"\0", cursor)
        if terminator < 0:
            break
        segment = core.payload[cursor:terminator]
        if segment.startswith(b"/") and segment.endswith(b"/share/poppler"):
            try:
                value = segment.decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise DLPError("Poppler compiled data root is not UTF-8") from exc
            if (
                unicodedata.normalize("NFC", value) != value
                or str(PurePosixPath(value)) != value
            ):
                raise DLPError("Poppler compiled data root is not canonical")
            candidates.append((cursor, value))
        cursor = terminator + 1
    if len(candidates) != 1 or candidates[0][1] != expected_text:
        raise DLPError("Poppler compiled data root does not uniquely match runtime data")
    expected = expected_text.encode("utf-8")
    runtime_data_root_sha256 = hashlib.sha256(expected).hexdigest()
    core_library_path_sha256 = hashlib.sha256(
        str(core.path).encode("utf-8")
    ).hexdigest()
    core_library_sha256 = hashlib.sha256(core.payload).hexdigest()
    byte_offset = candidates[0][0]
    compiled_path_binding_sha256 = _canonical_identity_sha256(
        {
            "core_library_path_sha256": core_library_path_sha256,
            "core_library_sha256": core_library_sha256,
            "runtime_data_root_sha256": runtime_data_root_sha256,
            "byte_offset": byte_offset,
            "occurrence_count": 1,
        }
    )
    return {
        "contract": "single-nul-terminated-utf8-path-in-held-core-library-v2",
        "matches_runtime_data_root": True,
        "runtime_data_root_sha256": runtime_data_root_sha256,
        "core_library_path_sha256": core_library_path_sha256,
        "core_library_sha256": core_library_sha256,
        "byte_offset": byte_offset,
        "occurrence_count": 1,
        "compiled_path_binding_sha256": compiled_path_binding_sha256,
        "tool_closure_coverage_count": len(covered_tools),
        "tool_closure_coverage_sha256": _canonical_identity_sha256(covered_tools),
    }


def _poppler_runtime_data_identity(
    tree: _HeldTree,
    *,
    compiled_data_root: Mapping[str, object],
    file_descriptor_budget: Mapping[str, object],
) -> dict[str, object]:
    manifest = {
        "directories": [
            {
                "path": entry.relative_path,
                "mode": stat.S_IMODE(entry.state.mode),
            }
            for entry in tree.entries
            if entry.kind == "directory"
        ],
        "files": [
            {
                "path": relative,
                "sha256": hashlib.sha256(held.payload).hexdigest(),
                "size": held.file_state.size,
                "mode": stat.S_IMODE(held.file_state.mode),
            }
            for relative, held in sorted(tree.files.items())
        ],
    }
    return {
        "path": str(tree.path),
        "file_count": len(manifest["files"]),
        "directory_count": len(manifest["directories"]),
        "byte_count": sum(held.file_state.size for held in tree.files.values()),
        "manifest_sha256": _canonical_identity_sha256(manifest),
        "read_contract": (
            "compiled-absolute-path-exact-file-allowlist;"
            "held-descriptors-and-bytes-revalidated-before-and-after-each-command"
        ),
        "compiled_data_root": dict(compiled_data_root),
        "file_descriptor_budget": dict(file_descriptor_budget),
        "private_snapshot_consumed": False,
        "same_uid_concurrent_path_substitution_excluded": False,
        "active_same_uid_tampering_not_prevented": True,
        "production_trust_boundary": {
            "required": True,
            "policy": (
                "poppler-runtime-and-every-ancestor-root-owned-and-service-uid-nonwritable"
            ),
            "enforcement_owner": "receiving-deployment-team",
            "verified_by_this_offline_receipt": False,
        },
    }


def _private_pdf_execution_snapshot(
    root: Path,
    name: str,
    source: _HeldPayload,
    *,
    mode: int = 0o500,
) -> _HeldPayload:
    target = root / name
    descriptor: int | None = None
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            mode,
        )
        _write_all(descriptor, source.payload, f"PDF DLP execution snapshot {name}")
        os.fchmod(descriptor, mode)
        try:
            _close_descriptor(descriptor)
        finally:
            descriptor = None
        held = _open_held_payload(
            target,
            f"PDF DLP execution snapshot {name}",
            max_bytes=max(len(source.payload), 1),
        )
        if held.payload != source.payload or stat.S_IMODE(held.file_state.mode) != mode:
            held.close()
            raise DLPError("PDF DLP execution snapshot identity mismatch")
        return held
    except BaseException:
        actions: list[Callable[[], None]] = []
        if descriptor is not None:
            actions.append(lambda: _close_descriptor(descriptor))
        actions.append(lambda: target.unlink(missing_ok=True))
        _finish_cleanup(_drain_cleanup(actions))
        raise


def _open_pdf_tool_set() -> _PDFToolSet:
    baseline_open_count = _open_file_descriptor_count()
    tools: dict[str, _HeldPayload] = {}
    execution_tools: dict[str, _HeldPayload] = {}
    source_libraries: dict[str, _HeldPayload] = {}
    execution_libraries: dict[str, _HeldPayload] = {}
    native_closures: dict[str, object] = {}
    library_aliases: dict[str, str] = {}
    library_alias_states: dict[str, _NodeState] = {}
    runtime_data: _HeldTree | None = None
    execution_root: tempfile.TemporaryDirectory[str] | None = None
    sandbox_executable: _HeldPayload | None = None
    environment_executable: _HeldPayload | None = None
    try:
        if sys.platform != "darwin":
            raise DLPError("PDF DLP sandbox backend requires macOS")
        for name in _PDF_TOOL_NAMES:
            executable = shutil.which(name, path=_PDF_TOOL_SEARCH_PATH)
            if executable is None:
                raise DLPError(f"required PDF DLP tool is unavailable: {name}")
            try:
                path = Path(executable).resolve(strict=True)
            except OSError as exc:
                raise DLPError(
                    f"required PDF DLP tool cannot be resolved: {name}"
                ) from exc
            held = _open_held_payload(
                path,
                f"PDF DLP tool {name}",
                max_bytes=256 * 1024 * 1024,
            )
            if not stat.S_ISREG(held.file_state.mode) or not (
                held.file_state.mode & 0o111
            ):
                held.close()
                raise DLPError(f"required PDF DLP tool is not executable: {name}")
            tools[name] = held
        runtime_data_root = _poppler_runtime_data_root(tools)
        tool_paths = {held.path for held in tools.values()}
        library_paths: set[Path] = set()
        for name, held in sorted(tools.items()):
            try:
                closure = _external_tool_macho_closure(
                    held.path,
                    tool_name=name,
                )
            except OfflineEvidenceError as exc:
                raise DLPError("PDF DLP native closure cannot be resolved") from exc
            if held.path not in closure.resolved_images:
                raise DLPError("PDF DLP executable is absent from its native closure")
            native_closures[name] = closure
            library_paths.update(set(closure.resolved_images) - tool_paths)
        preflight_runtime_file_count = len(_regular_tree_files(runtime_data_root))
        if preflight_runtime_file_count == 0:
            raise DLPError("Poppler runtime data closure is empty")
        _pdf_tool_set_fd_budget(
            baseline_open_count,
            tool_count=len(tools),
            runtime_data_file_count=preflight_runtime_file_count,
            library_path_count=len(library_paths),
            unique_library_count=len(library_paths),
        )
        runtime_data = _open_held_tree(
            runtime_data_root,
            "Poppler runtime data root",
        )
        if len(runtime_data.files) != preflight_runtime_file_count:
            raise DLPError(
                "Poppler runtime data file count changed after FD preflight"
            )
        sandbox_executable = _open_held_payload(
            NETWORK_SANDBOX_PATH.resolve(strict=True),
            "PDF DLP sandbox executable",
            max_bytes=16 * 1024 * 1024,
        )
        environment_executable = _open_held_payload(
            Path("/usr/bin/env").resolve(strict=True),
            "PDF DLP environment executable",
            max_bytes=16 * 1024 * 1024,
        )
        for path in sorted(library_paths, key=str):
            source_libraries[str(path)] = _open_held_payload(
                path,
                "PDF DLP native library",
                max_bytes=MAX_CONTAINER_MEMBER_BYTES,
            )
        unique_library_count = len(
            {
                hashlib.sha256(held.payload).hexdigest()
                for held in source_libraries.values()
            }
        )
        file_descriptor_budget = _pdf_tool_set_fd_budget(
            baseline_open_count,
            tool_count=len(tools),
            runtime_data_file_count=len(runtime_data.files),
            library_path_count=len(source_libraries),
            unique_library_count=unique_library_count,
        )
        compiled_data_root = _poppler_compiled_data_root_identity(
            runtime_data,
            source_libraries,
            native_closures,
        )
        runtime_data_identity = _poppler_runtime_data_identity(
            runtime_data,
            compiled_data_root=compiled_data_root,
            file_descriptor_budget=file_descriptor_budget,
        )
        for name, held in sorted(tools.items()):
            try:
                current = _external_tool_macho_closure(held.path, tool_name=name)
            except OfflineEvidenceError as exc:
                raise DLPError("PDF DLP native closure cannot be revalidated") from exc
            if current != native_closures[name]:
                raise DLPError("PDF DLP native closure changed while binding")

        execution_root = tempfile.TemporaryDirectory(prefix="kg-dlp-tools-")
        private_root = Path(execution_root.name).resolve(strict=True)
        private_root.chmod(0o700)
        bundle_root = private_root / "bundle"
        executable_root = bundle_root / "bin"
        object_root = bundle_root / "objects"
        library_root = bundle_root / "lib"
        scratch_root = bundle_root / "scratch"
        for directory in (
            bundle_root,
            executable_root,
            object_root,
            library_root,
            scratch_root,
        ):
            directory.mkdir(mode=0o700)
        for name, held in sorted(tools.items()):
            execution_tools[name] = _private_pdf_execution_snapshot(
                executable_root,
                name,
                held,
            )
        for path, held in sorted(source_libraries.items()):
            digest = hashlib.sha256(held.payload).hexdigest()
            if digest not in execution_libraries:
                execution_libraries[digest] = _private_pdf_execution_snapshot(
                    object_root,
                    f"{digest}.dylib",
                    held,
                    mode=0o400,
                )

        alias_keys: dict[str, str] = {}
        resolved_libraries = {
            Path(path): hashlib.sha256(held.payload).hexdigest()
            for path, held in source_libraries.items()
        }
        alias_candidates: set[Path] = set(resolved_libraries)
        for closure in native_closures.values():
            alias_candidates.update(
                path for path in closure.read_literals if path.name.endswith(".dylib")
            )
        for candidate in sorted(alias_candidates, key=str):
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise DLPError("PDF DLP native library alias is unavailable") from exc
            digest = resolved_libraries.get(resolved)
            if digest is None:
                continue
            alias = candidate.name
            if (
                unicodedata.normalize("NFC", alias) != alias
                or not re.fullmatch(r"[A-Za-z0-9._+\-]+\.dylib", alias)
            ):
                raise DLPError("PDF DLP native library alias is not canonical")
            folded = alias.casefold()
            previous_alias = alias_keys.get(folded)
            previous_digest = library_aliases.get(previous_alias or "")
            if previous_alias is not None and (
                previous_alias != alias or previous_digest != digest
            ):
                raise DLPError("PDF DLP native library alias conflicts")
            existing_digest = library_aliases.get(alias)
            if existing_digest is not None and existing_digest != digest:
                raise DLPError("PDF DLP native library alias maps to multiple images")
            alias_keys[folded] = alias
            library_aliases[alias] = digest
        if set(library_aliases.values()) != set(execution_libraries):
            raise DLPError("PDF DLP private library alias closure is incomplete")
        for alias, digest in sorted(library_aliases.items()):
            alias_path = library_root / alias
            alias_path.symlink_to(f"../objects/{digest}.dylib")
            library_alias_states[alias] = _node_state(os.lstat(alias_path))

        executable_root.chmod(0o500)
        object_root.chmod(0o500)
        library_root.chmod(0o500)
        scratch_root.chmod(0o700)
        final_execution_parent_state = _node_state(
            os.stat(executable_root, follow_symlinks=False)
        )
        for held in execution_tools.values():
            held.parent_state = final_execution_parent_state
        final_object_parent_state = _node_state(
            os.stat(object_root, follow_symlinks=False)
        )
        for held in execution_libraries.values():
            held.parent_state = final_object_parent_state
        result = _PDFToolSet(
            tools=tools,
            execution_tools=execution_tools,
            source_libraries=source_libraries,
            execution_libraries=execution_libraries,
            native_closures=native_closures,
            library_aliases=library_aliases,
            library_alias_states=library_alias_states,
            runtime_data=runtime_data,
            runtime_data_identity=runtime_data_identity,
            execution_root=execution_root,
            bundle_root=bundle_root,
            library_root=library_root,
            scratch_root=scratch_root,
            sandbox_executable=sandbox_executable,
            environment_executable=environment_executable,
        )
        result.revalidate()
        return result
    except BaseException:
        actions: list[Callable[[], None]] = [
            execution_tools[name].close
            for name in sorted(execution_tools, reverse=True)
        ]
        actions.extend(
            execution_libraries[digest].close
            for digest in sorted(execution_libraries, reverse=True)
        )
        if execution_root is not None:
            actions.append(execution_root.cleanup)
        actions.extend(
            source_libraries[path].close
            for path in sorted(source_libraries, reverse=True)
        )
        actions.extend(tools[name].close for name in sorted(tools, reverse=True))
        if runtime_data is not None:
            actions.append(runtime_data.close)
        if sandbox_executable is not None:
            actions.append(sandbox_executable.close)
        if environment_executable is not None:
            actions.append(environment_executable.close)
        _finish_cleanup(_drain_cleanup(actions))
        raise


@contextlib.contextmanager
def _held_pdf_tool_set() -> Iterator[_PDFToolSet]:
    tools = _open_pdf_tool_set()
    body_failed = False
    try:
        yield tools
    except BaseException:
        body_failed = True
        raise
    finally:
        _revalidate_then_close(
            tools.revalidate,
            tools.close,
            body_failed=body_failed,
        )


def _write_all(descriptor: int, payload: bytes, field: str) -> None:
    offset = 0
    try:
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise DLPError(f"{field} could not be written completely")
            offset += written
        os.fsync(descriptor)
    except DLPError:
        raise
    except OSError as exc:
        raise DLPError(f"{field} could not be written safely") from exc


@contextlib.contextmanager
def _anonymous_readonly_payload(
    payload: bytes,
    *,
    suffix: str,
    field: str,
) -> Iterator[tuple[int, str]]:
    with tempfile.TemporaryDirectory(prefix="kg-dlp-stable-") as temporary:
        root = Path(temporary).resolve(strict=True)
        root_fd = os.open(
            root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        writer: int | None = None
        reader: int | None = None
        name = "payload" + suffix
        try:
            writer = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=root_fd,
            )
            _write_all(writer, payload, field)
            os.fchmod(writer, 0o400)
            written_state = os.fstat(writer)
            reader = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=root_fd,
            )
            if _node_state(os.fstat(reader)) != _node_state(written_state):
                raise DLPError(f"{field} snapshot identity changed while opening")
            snapshot, _ = _read_open_payload(
                reader,
                field=field,
                max_bytes=max(len(payload), 1),
            )
            if snapshot != payload:
                raise DLPError(f"{field} snapshot differs from its bound bytes")
            os.unlink(name, dir_fd=root_fd)
            try:
                _close_descriptor(writer)
            finally:
                writer = None
            anonymous_state = _node_state(os.fstat(reader))
            if (
                anonymous_state.link_count != 0
                or stat.S_IMODE(anonymous_state.mode) != 0o400
                or fcntl.fcntl(reader, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY
            ):
                raise DLPError(f"{field} snapshot is not anonymous and read-only")
            alias = f"/dev/fd/{reader}"
            yield reader, alias
            current, current_state = _read_open_payload(
                reader,
                field=field,
                max_bytes=max(len(payload), 1),
            )
            if current_state != anonymous_state or current != payload:
                raise DLPError(f"{field} snapshot changed during use")
        except OSError as exc:
            raise DLPError(f"{field} snapshot could not be created safely") from exc
        finally:
            actions: list[Callable[[], None]] = []
            if writer is not None:
                actions.append(lambda: _close_descriptor(writer))
            if reader is not None:
                actions.append(lambda: _close_descriptor(reader))
            actions.append(lambda: _close_descriptor(root_fd))
            _finish_cleanup(_drain_cleanup(actions))


@contextlib.contextmanager
def _anonymous_writable_output(
    root: Path,
    *,
    field: str,
) -> Iterator[tuple[int, str]]:
    with tempfile.TemporaryDirectory(prefix="output-", dir=root) as temporary:
        directory = Path(temporary).resolve(strict=True)
        directory.chmod(0o700)
        root_fd = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        descriptor: int | None = None
        try:
            descriptor = os.open(
                "payload",
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=root_fd,
            )
            os.unlink("payload", dir_fd=root_fd)
            state = _node_state(os.fstat(descriptor))
            if state.link_count != 0:
                raise DLPError(f"{field} is not anonymous")
            yield descriptor, f"/dev/fd/{descriptor}"
            if _node_state(os.fstat(descriptor)).link_count != 0:
                raise DLPError(f"{field} link state changed")
        finally:
            actions: list[Callable[[], None]] = []
            if descriptor is not None:
                actions.append(lambda: _close_descriptor(descriptor))
            actions.append(lambda: _close_descriptor(root_fd))
            _finish_cleanup(_drain_cleanup(actions))


_EXECUTED_DLP_SOURCE = _open_held_payload(
    Path(__file__),
    "DLP scanner source",
    max_bytes=4 * 1024 * 1024,
)
_FORMAL_DLP_SOURCE_SHA256: str | None = None
_FORMAL_DLP_SOURCE_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_DLP_ACTION_CLOSURE: tuple[object, ...] | None = None
_DLP_SOURCE_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)


def _dlp_source_state_identity() -> dict[str, int]:
    state = _EXECUTED_DLP_SOURCE.file_state
    return {
        "device": state.device,
        "inode": state.inode,
        "mode": state.mode,
        "nlink": state.link_count,
        "size": state.size,
        "mtime_ns": state.mtime_ns,
        "ctime_ns": state.ctime_ns,
    }


def _current_dlp_action_closure() -> tuple[object, ...]:
    return (
        scan_phase1_candidate,
        validate_phase1_dlp_receipt,
        scan_final_suite_dlp,
        validate_final_suite_dlp_receipt,
        _scan_phase1_candidate_impl,
        _validate_phase1_dlp_receipt_impl,
        _scan_final_suite_dlp_impl,
        _validate_final_suite_dlp_receipt_impl,
    )


def _install_formal_dlp_bootstrap_context(binding: Mapping[str, Any]) -> None:
    global _FORMAL_DLP_ACTION_CLOSURE
    global _FORMAL_DLP_SOURCE_SHA256
    global _FORMAL_DLP_SOURCE_STATE_IDENTITY

    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except OfflineEvidenceError as exc:
        raise DLPError("formal DLP CLI bootstrap context is required") from exc
    required = {*_DLP_SOURCE_STATE_FIELDS, "sha256"}
    if (
        not isinstance(binding, Mapping)
        or set(binding) != required
        or not isinstance(binding.get("sha256"), str)
        or not SHA256_PATTERN.fullmatch(str(binding["sha256"]))
        or any(
            type(binding.get(field)) is not int or int(binding[field]) < 0
            for field in _DLP_SOURCE_STATE_FIELDS
        )
        or binding["inode"] == 0
        or binding["nlink"] != 1
        or not stat.S_ISREG(binding["mode"])
    ):
        raise DLPError("formal DLP CLI source binding is malformed")
    expected_state = {
        field: int(binding[field]) for field in _DLP_SOURCE_STATE_FIELDS
    }
    _revalidate_held_payload(_EXECUTED_DLP_SOURCE)
    if (
        hashlib.sha256(_EXECUTED_DLP_SOURCE.payload).hexdigest()
        != binding["sha256"]
        or _dlp_source_state_identity() != expected_state
    ):
        raise DLPError("formal DLP CLI source differs from held bootstrap bytes")
    _FORMAL_DLP_SOURCE_SHA256 = str(binding["sha256"])
    _FORMAL_DLP_SOURCE_STATE_IDENTITY = expected_state
    _FORMAL_DLP_ACTION_CLOSURE = _current_dlp_action_closure()


def _require_formal_dlp_bootstrap_context() -> tuple[object, ...]:
    source_sha256 = _FORMAL_DLP_SOURCE_SHA256
    source_state = _FORMAL_DLP_SOURCE_STATE_IDENTITY
    actions = _FORMAL_DLP_ACTION_CLOSURE
    if (
        not isinstance(source_sha256, str)
        or not SHA256_PATTERN.fullmatch(source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_DLP_SOURCE_STATE_FIELDS)
        or any(
            type(source_state[field]) is not int or source_state[field] < 0
            for field in _DLP_SOURCE_STATE_FIELDS
        )
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
        or not isinstance(actions, tuple)
        or len(actions) != 8
    ):
        raise DLPError("formal DLP CLI bootstrap context is required")
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
        _revalidate_held_payload(_EXECUTED_DLP_SOURCE)
    except (OfflineEvidenceError, DLPError) as exc:
        raise DLPError("formal DLP CLI source binding changed") from exc
    if (
        hashlib.sha256(_EXECUTED_DLP_SOURCE.payload).hexdigest() != source_sha256
        or _dlp_source_state_identity() != dict(source_state)
        or any(
            current is not expected
            for current, expected in zip(
                _current_dlp_action_closure(), actions, strict=True
            )
        )
    ):
        raise DLPError("formal DLP CLI source or action closure changed")
    return actions


def _value_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _object_id(raw: str) -> str:
    if not raw or raw.startswith("/") or "\\" in raw or "//" in raw:
        raise DLPError("DLP object id must be canonical and relative")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise DLPError("DLP object id contains a dot or empty component")
    return path.as_posix()


def _canonical_container_member_name(raw: str, *, is_directory: bool) -> str:
    if not isinstance(raw, str) or not raw or raw.startswith("/"):
        raise DLPError("container member name must be non-empty and relative")
    if "\\" in raw or "//" in raw or "\x00" in raw:
        raise DLPError("container member name is not canonical POSIX")
    candidate = raw[:-1] if is_directory and raw.endswith("/") else raw
    path = PurePosixPath(candidate)
    if (
        not candidate
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != candidate
    ):
        raise DLPError("container member name contains a dot or normalized component")
    return candidate


def _real_directory(raw: str | Path, label: str) -> Path:
    path = Path(raw)
    try:
        mode = os.lstat(path).st_mode
    except OSError as exc:
        raise DLPError(f"{label} cannot be inspected") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise DLPError(f"{label} must be a real directory")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise DLPError(f"{label} cannot be resolved") from exc


def _regular_tree_files(
    root: Path,
    *,
    allow_empty_directories: bool = False,
) -> list[Path]:
    root = _real_directory(root, "DLP tree root")
    opened_path, descriptor, root_state = _open_directory_path(root, "DLP tree root")
    try:
        entries = _walk_held_tree(
            descriptor,
            allow_empty_directories=allow_empty_directories,
        )
        _revalidate_held_directory(
            opened_path,
            descriptor,
            root_state,
            "DLP tree root",
        )
        return [
            root / entry.relative_path
            for entry in entries
            if entry.kind == "file"
        ]
    finally:
        _close_descriptor(descriptor)


def _parse_pdf_attachment_list(output: str) -> tuple[str, ...]:
    lines = output.splitlines()
    if not lines:
        raise DLPError("PDF attachment listing is empty")
    header = re.fullmatch(r"(\d+) embedded files?", lines[0])
    if not header:
        raise DLPError("PDF attachment listing header is invalid")
    count = int(header.group(1))
    if len(lines) != count + 1:
        raise DLPError("PDF attachment listing count is inconsistent")
    names: list[str] = []
    for index, line in enumerate(lines[1:], 1):
        match = re.fullmatch(rf"{index}: (.+)", line)
        if not match:
            raise DLPError("PDF attachment listing record is invalid")
        names.append(match.group(1))
    return tuple(names)


def _pdf_image_list_count(output: str) -> int:
    lines = output.splitlines()
    separator_index = next(
        (
            index
            for index, line in enumerate(lines)
            if len(line.strip()) >= 8 and set(line.strip()) == {"-"}
        ),
        None,
    )
    if separator_index is None or not any(
        "page" in line.lower() and "type" in line.lower()
        for line in lines[:separator_index]
    ):
        raise DLPError("PDF image listing is malformed")
    count = sum(bool(line.strip()) for line in lines[separator_index + 1 :])
    if count > MAX_PDF_RUNTIME_IMAGE_COUNT:
        raise DLPError("PDF image-count limit exceeded")
    return count


def _pdf_image_list_has_images(output: str) -> bool:
    return _pdf_image_list_count(output) > 0


def _declared_payload_kind(name: str) -> str | None:
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in {".docx", ".zip"}:
        return "zip"
    if suffix in {".tar", ".tgz", ".gz"} or name.lower().endswith(".tar.gz"):
        return "tar"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return "sqlite"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    return None


def _payload_magic_kind(payload: bytes) -> str | None:
    head = payload[:1024]
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "zip"
    if head.lstrip().startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"SQLite format 3\x00"):
        return "sqlite"
    if head.startswith(b"\x1f\x8b"):
        return "tar"
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "tar"
    if (
        head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM"))
        or head.startswith((b"II*\x00", b"MM\x00*"))
        or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
    ):
        return "image"
    return None


def _require_payload_kind(name: str, payload: bytes) -> str | None:
    declared = _declared_payload_kind(name)
    detected = _payload_magic_kind(payload)
    if declared is not None and detected != declared:
        raise DLPError("structured payload extension and magic disagree")
    if declared is None and detected is not None:
        raise DLPError("structured payload is hidden behind an unapproved extension")
    return declared


def _zip_preflight(payload: bytes) -> tuple[int, int]:
    if len(payload) < 22:
        raise DLPError("ZIP central directory is truncated")
    search_start = max(0, len(payload) - (65_535 + 22))
    eocd_offset = payload.rfind(b"PK\x05\x06", search_start)
    if eocd_offset < 0 or eocd_offset + 22 > len(payload):
        raise DLPError("ZIP end-of-central-directory record is unavailable")
    (
        signature,
        disk_number,
        directory_disk,
        disk_entries,
        total_entries,
        directory_size,
        directory_offset,
        comment_size,
    ) = struct.unpack_from("<4s4H2LH", payload, eocd_offset)
    if signature != b"PK\x05\x06" or eocd_offset + 22 + comment_size != len(payload):
        raise DLPError("ZIP end-of-central-directory record is malformed")
    if disk_number != 0 or directory_disk != 0 or disk_entries != total_entries:
        raise DLPError("multi-disk ZIP containers are unsupported")
    if (
        total_entries == 0xFFFF
        or directory_size == 0xFFFFFFFF
        or directory_offset == 0xFFFFFFFF
    ):
        raise DLPError("ZIP64 containers are unsupported by the bounded DLP scanner")
    if directory_size > MAX_CONTAINER_DIRECTORY_BYTES:
        raise DLPError("ZIP central-directory byte limit exceeded")
    directory_end = directory_offset + directory_size
    if directory_end != eocd_offset or directory_end > len(payload):
        raise DLPError("ZIP central-directory bounds are malformed")
    cursor = directory_offset
    expanded_bytes = 0
    observed_entries = 0
    while cursor < directory_end:
        if cursor + 46 > directory_end:
            raise DLPError("ZIP central-directory entry is truncated")
        values = struct.unpack_from("<4s6H3L5H2L", payload, cursor)
        if values[0] != b"PK\x01\x02":
            raise DLPError("ZIP central-directory entry signature is invalid")
        compressed_size = values[8]
        uncompressed_size = values[9]
        name_size, extra_size, member_comment_size = values[10:13]
        local_header_offset = values[16]
        if (
            compressed_size == 0xFFFFFFFF
            or uncompressed_size == 0xFFFFFFFF
            or local_header_offset == 0xFFFFFFFF
        ):
            raise DLPError("ZIP64 members are unsupported by the bounded DLP scanner")
        entry_size = 46 + name_size + extra_size + member_comment_size
        if cursor + entry_size > directory_end:
            raise DLPError("ZIP central-directory entry exceeds its bounds")
        observed_entries += 1
        if observed_entries > MAX_SCANNED_OBJECTS:
            raise DLPError("DLP container member-count limit exceeded")
        expanded_bytes += uncompressed_size
        if expanded_bytes > MAX_SCANNED_BYTES:
            raise DLPError("DLP container declared-byte limit exceeded")
        cursor += entry_size
    if cursor != directory_end or observed_entries != total_entries:
        raise DLPError("ZIP central-directory entry count is inconsistent")
    return observed_entries, expanded_bytes


class _BoundedTarInfo(tarfile.TarInfo):
    def _require_bounded_extension(self) -> None:
        if self.size < 0 or self.size > MAX_CONTAINER_HEADER_BYTES:
            raise DLPError("tar extended header exceeds its byte limit")

    def _proc_pax(self, archive: tarfile.TarFile) -> tarfile.TarInfo | None:
        self._require_bounded_extension()
        return super()._proc_pax(archive)

    def _proc_gnulong(self, archive: tarfile.TarFile) -> tarfile.TarInfo | None:
        self._require_bounded_extension()
        return super()._proc_gnulong(archive)

    def _proc_sparse(self, archive: tarfile.TarFile) -> tarfile.TarInfo | None:
        self._require_bounded_extension()
        return super()._proc_sparse(archive)


def _canonical_implementation_relative(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or raw.startswith("/"):
        raise DLPError("implementation path must be a non-empty relative string")
    if "\\" in raw or "//" in raw or "\x00" in raw:
        raise DLPError("implementation path is not canonical POSIX")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts) or path.as_posix() != raw:
        raise DLPError("implementation path contains a dot or normalized component")
    return raw


def _canonical_inventory_relative(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or raw.startswith("/"):
        raise DLPError("inventory path must be a non-empty relative string")
    if "\\" in raw or "//" in raw or "\x00" in raw:
        raise DLPError("inventory path is not canonical POSIX")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts) or path.as_posix() != raw:
        raise DLPError("inventory path contains a dot or normalized component")
    return raw


def _safe_inventory_path(root: Path, relative: str) -> Path:
    relative = _canonical_inventory_relative(relative)
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        try:
            mode = os.lstat(path).st_mode
        except OSError as exc:
            raise DLPError("inventory path is missing") from exc
        if stat.S_ISLNK(mode):
            raise DLPError("inventory path contains a symlink")
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise DLPError("inventory path escaped its root") from exc
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise DLPError("inventory path is not a regular file")
    return path


def _implementation_root(code_root: str | Path) -> Path:
    raw_root = Path(code_root)
    if raw_root.is_symlink() or not raw_root.is_dir():
        raise DLPError("implementation root must be a real directory")
    try:
        return raw_root.resolve(strict=True)
    except OSError as exc:
        raise DLPError("implementation root cannot be resolved") from exc


def _implementation_path(root: Path, relative: str) -> Path:
    relative = _canonical_implementation_relative(relative)
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise DLPError(f"implementation path contains a symlink: {relative}")
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise DLPError(f"implementation path is missing or escaped its root: {relative}") from exc
    return path


def _required_implementation_file(root: Path, relative: str) -> Path:
    path = _implementation_path(root, relative)
    if not path.is_file() or path.is_symlink():
        raise DLPError(f"implementation file is missing or not regular: {relative}")
    return path


def _required_implementation_directory(root: Path, relative: str) -> Path:
    path = _implementation_path(root, relative)
    if not path.is_dir() or path.is_symlink():
        raise DLPError(f"fixed implementation root is missing or not a directory: {relative}")
    return path


def _is_generated_python_cache(relative: str) -> bool:
    path = PurePosixPath(relative)
    return bool(
        any(part in FORBIDDEN_IMPLEMENTATION_DIRECTORY_NAMES for part in path.parts)
        or path.suffix in FORBIDDEN_IMPLEMENTATION_FILE_SUFFIXES
    )


def _strict_json_bytes(payload: bytes, name: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DLPError(f"duplicate JSON key in {name}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                DLPError(f"non-finite JSON value in {name}: {constant}")
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DLPError(f"invalid JSON implementation artifact: {name}") from exc
    if not isinstance(value, Mapping):
        raise DLPError(f"JSON object required in {name}")
    return value


def _strict_json_mapping(path: Path) -> Mapping[str, Any]:
    with _held_payload(path, "JSON artifact") as held:
        return _strict_json_bytes(held.payload, held.path.name)


def _runtime_allowlist(root: Path) -> tuple[tuple[str, ...], str]:
    path = _required_implementation_file(root, RUNTIME_FILE_ALLOWLIST)
    value = _strict_json_mapping(path)
    if value.get("schema_version") != "cloud-v2-runtime-file-allowlist-v1":
        raise DLPError("runtime file allowlist schema mismatch")
    raw_files = value.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise DLPError("runtime file allowlist must contain a non-empty files list")
    files = tuple(_canonical_implementation_relative(item) for item in raw_files)
    if files != REQUIRED_RUNTIME_FILES:
        raise DLPError("runtime file allowlist must contain the exact reviewed dependencies")
    for relative in files:
        if _is_generated_python_cache(relative):
            raise DLPError("runtime file allowlist cannot name generated cache files")
        _required_implementation_file(root, relative)
    return files, sha256_file(path)


def _builder_allowlist(root: Path) -> tuple[tuple[str, ...], str]:
    path = _required_implementation_file(root, BUILDER_FILE_ALLOWLIST)
    value = _strict_json_mapping(path)
    if value.get("schema_version") != "cloud-v2-builder-file-allowlist-v1":
        raise DLPError("builder file allowlist schema mismatch")
    raw_files = value.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise DLPError("builder file allowlist must contain a non-empty files list")
    files = tuple(_canonical_implementation_relative(item) for item in raw_files)
    if files != REQUIRED_BUILDER_FILES:
        raise DLPError("builder file allowlist must contain the exact reviewed dependencies")
    if not set(files).issubset(REQUIRED_RUNTIME_FILES):
        raise DLPError("builder file allowlist must be included in the runtime closure")
    for relative in files:
        if _is_generated_python_cache(relative):
            raise DLPError("builder file allowlist cannot name generated cache files")
        _required_implementation_file(root, relative)
    return files, sha256_file(path)


def _tree_implementation_files(root: Path, relative_root: str) -> set[str]:
    tree_root = _required_implementation_directory(root, relative_root)
    files: set[str] = set()
    opened_path, descriptor, root_state = _open_directory_path(
        tree_root,
        "fixed implementation tree",
    )
    try:
        entries = _walk_held_tree(descriptor, allow_empty_directories=True)
        _revalidate_held_directory(
            opened_path,
            descriptor,
            root_state,
            "fixed implementation tree",
        )
    finally:
        _close_descriptor(descriptor)
    for entry in entries:
        if entry.kind != "file":
            continue
        relative = (PurePosixPath(relative_root) / entry.relative_path).as_posix()
        if PurePosixPath(relative).name in IGNORED_IMPLEMENTATION_FILE_NAMES:
            continue
        files.add(_canonical_implementation_relative(relative))
    if not files:
        raise DLPError(f"fixed implementation tree contains no files: {relative_root}")
    return files


def discover_phase1_implementation(code_root: str | Path) -> ImplementationDiscovery:
    """Discover the non-caller-reducible Phase 1 implementation closure."""

    root = _implementation_root(code_root)
    runtime_files, runtime_allowlist_sha256 = _runtime_allowlist(root)
    builder_files, builder_allowlist_sha256 = _builder_allowlist(root)
    relative_paths = set(PHASE1_TOP_LEVEL_FILES)
    for relative in PHASE1_TOP_LEVEL_FILES:
        _required_implementation_file(root, relative)
    for relative_root in PHASE1_TREE_ROOTS:
        relative_paths.update(_tree_implementation_files(root, relative_root))
    relative_paths.update(runtime_files)
    relative_paths.update(builder_files)
    for relative in relative_paths:
        _required_implementation_file(root, relative)
    if RUNTIME_FILE_ALLOWLIST not in relative_paths:
        raise DLPError("runtime file allowlist was omitted from implementation closure")
    if BUILDER_FILE_ALLOWLIST not in relative_paths:
        raise DLPError("builder file allowlist was omitted from implementation closure")
    return ImplementationDiscovery(
        root=root,
        relative_paths=tuple(sorted(relative_paths)),
        runtime_allowlist_sha256=runtime_allowlist_sha256,
        runtime_relative_paths=runtime_files,
        builder_allowlist_sha256=builder_allowlist_sha256,
        builder_relative_paths=builder_files,
    )


def _canonical_identity_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _inventory(records: list[dict[str, str]], total_bytes: int) -> dict[str, object]:
    records = sorted(records, key=lambda item: item["path"])
    paths = [record["path"] for record in records]
    hashes = [record["sha256"] for record in records]
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "file_count": len(records),
        "total_bytes": total_bytes,
        "files": records,
        "path_set_sha256": _canonical_identity_sha256(paths),
        "hash_set_sha256": _canonical_identity_sha256(hashes),
        "tree_sha256": _canonical_identity_sha256(records),
    }


def _tree_inventory(
    root: str | Path,
    *,
    allow_empty_directories: bool = False,
) -> dict[str, object]:
    resolved = _real_directory(root, "DLP inventory root")
    records: list[dict[str, str]] = []
    total_bytes = 0
    for path in _regular_tree_files(
        resolved,
        allow_empty_directories=allow_empty_directories,
    ):
        relative = path.relative_to(resolved).as_posix()
        size = path.stat().st_size
        records.append({"path": relative, "sha256": sha256_file(path)})
        total_bytes += size
    return _inventory(records, total_bytes)


def _file_inventory(path: str | Path) -> dict[str, object]:
    target = Path(path)
    try:
        mode = os.lstat(target).st_mode
    except OSError as exc:
        raise DLPError("DLP inventory file cannot be inspected") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DLPError("DLP inventory file must be regular and unsymlinked")
    return _inventory(
        [{"path": target.name, "sha256": sha256_file(target)}],
        target.stat().st_size,
    )


def _inventory_without_files(inventory: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in inventory.items()
        if key != "files"
    }


def _governance_state(scope: ApprovedSourceScope) -> dict[str, object]:
    root = _real_directory(scope.governance_root, "governance root")
    top_records: list[dict[str, str]] = []
    top_total_bytes = 0
    review_inventory: dict[str, object] | None = None
    discovered_files: list[str] = []
    discovered_directories: list[str] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        try:
            mode = os.lstat(path).st_mode
        except OSError as exc:
            raise DLPError("governance node cannot be inspected") from exc
        if stat.S_ISLNK(mode):
            raise DLPError("governance root contains a symlink")
        if stat.S_ISREG(mode):
            discovered_files.append(path.name)
            top_records.append({"path": path.name, "sha256": sha256_file(path)})
            top_total_bytes += path.stat().st_size
            continue
        if stat.S_ISDIR(mode):
            discovered_directories.append(path.name)
            if path.name != GOVERNANCE_REVIEW_EVIDENCE_ROOT:
                raise DLPError("governance root contains an unapproved directory")
            review_inventory = _tree_inventory(path)
            continue
        raise DLPError("governance root contains a nonregular node")

    if scope.records:
        if discovered_files != list(GOVERNANCE_TOP_LEVEL_FILES):
            raise DLPError("governance top-level artifact closure is not exact")
        if discovered_directories != [GOVERNANCE_REVIEW_EVIDENCE_ROOT]:
            raise DLPError("governance review-evidence root is missing")

    top_inventory = _inventory(top_records, top_total_bytes)
    review_receipt: dict[str, object] | None = None
    if review_inventory is not None:
        review_receipt = {
            "relative_root": GOVERNANCE_REVIEW_EVIDENCE_ROOT,
            "classification": "local-review-evidence-not-build-input",
            "excluded_from_candidate": True,
            "content_dlp_status": "not-asserted-requires-separate-ocr-evidence",
            **_inventory_without_files(review_inventory),
        }
    return {
        "top_level": top_inventory,
        "review_inventory": review_inventory,
        "review_receipt": review_receipt,
        "accounted_tree_sha256": _canonical_identity_sha256(
            {
                "top_level_tree_sha256": top_inventory["tree_sha256"],
                "review_tree_sha256": (
                    review_inventory["tree_sha256"] if review_inventory else None
                ),
            }
        ),
    }


def _implementation_inventory(discovery: ImplementationDiscovery) -> dict[str, object]:
    records: list[dict[str, str]] = []
    total_bytes = 0
    for relative in discovery.relative_paths:
        path = _required_implementation_file(discovery.root, relative)
        records.append({"path": relative, "sha256": sha256_file(path)})
        total_bytes += path.stat().st_size
    return _inventory(records, total_bytes)


def _implementation_scope_receipt(
    discovery: ImplementationDiscovery,
    inventory: Mapping[str, object],
) -> dict[str, object]:
    records = list(inventory["files"])
    paths = [str(record["path"]) for record in records]
    runtime_paths = list(discovery.runtime_relative_paths)
    builder_paths = list(discovery.builder_relative_paths)
    record_map = {str(record["path"]): str(record["sha256"]) for record in records}
    scanned_allowlist_sha256 = record_map.get(RUNTIME_FILE_ALLOWLIST)
    if scanned_allowlist_sha256 != discovery.runtime_allowlist_sha256:
        raise DLPError("runtime file allowlist changed during inventory")
    scanned_builder_allowlist_sha256 = record_map.get(BUILDER_FILE_ALLOWLIST)
    if scanned_builder_allowlist_sha256 != discovery.builder_allowlist_sha256:
        raise DLPError("builder file allowlist changed during inventory")
    return {
        "schema_version": IMPLEMENTATION_SCOPE_SCHEMA_VERSION,
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
        "files": records,
        "path_set_sha256": inventory["path_set_sha256"],
        "hash_set_sha256": inventory["hash_set_sha256"],
        "tree_sha256": inventory["tree_sha256"],
        "path_hash_set_sha256": inventory["tree_sha256"],
        "fixed_top_level_files": list(PHASE1_TOP_LEVEL_FILES),
        "fixed_tree_roots": list(PHASE1_TREE_ROOTS),
        "runtime_file_allowlist": {
            "path": RUNTIME_FILE_ALLOWLIST,
            "sha256": scanned_allowlist_sha256,
            "declared_file_count": len(runtime_paths),
            "declared_path_set_sha256": _canonical_identity_sha256(runtime_paths),
        },
        "builder_file_allowlist": {
            "path": BUILDER_FILE_ALLOWLIST,
            "sha256": scanned_builder_allowlist_sha256,
            "declared_file_count": len(builder_paths),
            "declared_path_set_sha256": _canonical_identity_sha256(builder_paths),
        },
    }


def _scan_inventory(
    scanner: "DLPScanner",
    *,
    root: str | Path,
    inventory: Mapping[str, object],
    object_prefix: str,
) -> list[dict[str, str]]:
    resolved = _real_directory(root, "DLP scan root")
    before = set(scanner.findings)
    raw_files = inventory.get("files")
    if not isinstance(raw_files, list):
        raise DLPError("DLP inventory is missing file records")
    for index, record in enumerate(raw_files, 1):
        if not isinstance(record, Mapping):
            raise DLPError("DLP inventory contains a malformed file record")
        relative = _canonical_inventory_relative(record.get("path"))
        path = _safe_inventory_path(resolved, relative)
        scanner.scan_text(f"{object_prefix}/files/{index}/path", relative)
        payload_id = f"{object_prefix}/files/{index}/payload"
        scanner.scan_file(path, payload_id)
        if scanner.object_hashes.get(payload_id) != record.get("sha256"):
            raise DLPError("DLP inventory bytes changed before scanning")
    return [asdict(item) for item in sorted(scanner.findings - before)]


def _strict_nonnegative_integer(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise DLPError(f"{label} must be a nonnegative integer")
    return value


def _validate_source_inventory(
    scope: ApprovedSourceScope, inventory: Mapping[str, object]
) -> None:
    raw_files = inventory.get("files")
    if not isinstance(raw_files, list):
        raise DLPError("source inventory file records are absent")
    expected = {
        record.relative_path: record.source_sha256
        for record in scope.records
    }
    actual: dict[str, str] = {}
    for record in raw_files:
        if not isinstance(record, Mapping) or set(record) != {"path", "sha256"}:
            raise DLPError("source inventory record is malformed")
        path = _canonical_inventory_relative(record.get("path"))
        digest = record.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise DLPError("source inventory digest is invalid")
        if path in actual:
            raise DLPError("source inventory contains a duplicate path")
        actual[path] = digest
    if actual != expected:
        raise DLPError("current source bytes differ from the approved source scope")


def _validate_upstream_source_dlp(scope: ApprovedSourceScope) -> dict[str, object]:
    path = _safe_inventory_path(
        _real_directory(scope.governance_root, "governance root"),
        "source_dlp_receipt.json",
    )
    with _held_payload(
        path,
        "upstream source-DLP receipt",
        max_bytes=MAX_CONTAINER_HEADER_BYTES,
    ) as held:
        if hashlib.sha256(held.payload).hexdigest() != scope.source_dlp_receipt_sha256:
            raise DLPError("upstream source-DLP receipt identity mismatch")
        receipt = _strict_json_bytes(held.payload, held.path.name)
    expected_keys = {
        "bindings",
        "coverage",
        "finding_count",
        "findings",
        "object_count",
        "object_set_sha256",
        "ok",
        "rules_sha256",
        "scanner_sha256",
        "schema_version",
    }
    if set(receipt) != expected_keys:
        raise DLPError("upstream source-DLP receipt schema is incomplete")
    if receipt.get("schema_version") != UPSTREAM_SOURCE_DLP_SCHEMA_VERSION:
        raise DLPError("upstream source-DLP receipt schema mismatch")
    if receipt.get("ok") is not True or receipt.get("findings") != []:
        raise DLPError("upstream source-DLP receipt is not passing")
    if _strict_nonnegative_integer(receipt.get("finding_count"), "finding_count") != 0:
        raise DLPError("upstream source-DLP receipt contains findings")
    for key in ("object_set_sha256", "rules_sha256", "scanner_sha256"):
        if not isinstance(receipt.get(key), str) or not SHA256_PATTERN.fullmatch(
            str(receipt.get(key))
        ):
            raise DLPError("upstream source-DLP receipt contains an invalid identity")
    if canonical_json_bytes(receipt.get("bindings")) != canonical_json_bytes(
        UPSTREAM_SOURCE_DLP_BINDINGS
    ):
        raise DLPError("upstream source-DLP OCR bindings differ from the frozen contract")

    coverage = receipt.get("coverage")
    if not isinstance(coverage, list):
        raise DLPError("upstream source-DLP coverage is absent")
    if len(coverage) != len(scope.records):
        raise DLPError("upstream source-DLP coverage is not exact")
    if _strict_nonnegative_integer(receipt.get("object_count"), "object_count") != len(
        coverage
    ):
        raise DLPError("upstream source-DLP object count differs from coverage")
    expected_paths = [record.relative_path for record in scope.records]
    coverage_paths: list[str] = []
    for expected_source, item in zip(scope.records, coverage):
        if not isinstance(item, Mapping):
            raise DLPError("upstream source-DLP coverage record is malformed")
        path_value = item.get("path")
        if path_value != expected_source.relative_path:
            raise DLPError("upstream source-DLP coverage order or path differs")
        coverage_paths.append(str(path_value))
        scanner = item.get("scanner")
        if expected_source.relative_path.lower().endswith(".docx"):
            expected_record_keys = {
                "archive_members",
                "embedded_payloads",
                "images",
                "ocr_images",
                "path",
                "scanner",
                "unique_images",
            }
            if set(item) != expected_record_keys or scanner != "docx":
                raise DLPError("upstream DOCX DLP coverage schema mismatch")
            counts = {
                key: _strict_nonnegative_integer(item.get(key), key)
                for key in (
                    "archive_members",
                    "embedded_payloads",
                    "images",
                    "ocr_images",
                    "unique_images",
                )
            }
            if counts["archive_members"] <= 0:
                raise DLPError("upstream DOCX archive coverage is empty")
            if counts["ocr_images"] != counts["unique_images"]:
                raise DLPError("upstream DOCX OCR coverage is incomplete")
            if counts["unique_images"] > counts["images"]:
                raise DLPError("upstream DOCX image counts are inconsistent")
        elif expected_source.relative_path.lower().endswith(".pdf"):
            expected_record_keys = {
                "attachments",
                "empty_pages",
                "image_enumeration_failures",
                "images",
                "ocr_images",
                "ocr_rendered_pages",
                "pages",
                "path",
                "rendered_pages",
                "scanner",
                "unique_images",
            }
            if set(item) != expected_record_keys or scanner != "pdf":
                raise DLPError("upstream PDF DLP coverage schema mismatch")
            counts = {
                key: _strict_nonnegative_integer(item.get(key), key)
                for key in expected_record_keys
                if key not in {"path", "scanner"}
            }
            if counts["pages"] <= 0:
                raise DLPError("upstream PDF page coverage is empty")
            if counts["attachments"] != 0:
                raise DLPError("approved source PDF unexpectedly contains attachments")
            if counts["image_enumeration_failures"] != 0:
                raise DLPError("upstream PDF image enumeration was incomplete")
            if counts["ocr_images"] != counts["unique_images"]:
                raise DLPError("upstream PDF OCR coverage is incomplete")
            if counts["unique_images"] > counts["images"]:
                raise DLPError("upstream PDF image counts are inconsistent")
        else:
            raise DLPError("upstream source-DLP coverage names an unsupported source")
    if len(coverage) != len(scope.records) or coverage_paths != expected_paths:
        raise DLPError("upstream source-DLP coverage is not exact")
    return {
        "schema_version": UPSTREAM_SOURCE_DLP_SCHEMA_VERSION,
        "receipt_sha256": scope.source_dlp_receipt_sha256,
        "object_count": len(coverage),
        "coverage_path_set_sha256": _canonical_identity_sha256(coverage_paths),
        "coverage_tree_sha256": _canonical_identity_sha256(coverage),
        "bindings_sha256": _canonical_identity_sha256(UPSTREAM_SOURCE_DLP_BINDINGS),
        "bound_to_exact_source_manifest": True,
        "ocr_coverage_validated": True,
    }


def _ruleset_sha256() -> str:
    return _canonical_identity_sha256(
        {
            "version": DLP_RULESET_VERSION,
            "rules": [
                {"rule_id": rule_id, "pattern": pattern.pattern, "flags": pattern.flags}
                for rule_id, pattern in RULES
            ],
            "safe_negative_contract": {
                "email_tlds": ["invalid", "test"],
                "loopback_ipv4": "not-an-internal-organization-address",
                "policy_product_names_are_not_identifiers": True,
                "placeholder_prefixes": [
                    "secretref:",
                    "fake-",
                    "redacted",
                    "<",
                    "${",
                    "{{",
                ],
            },
        }
    )


def _pdf_tool_bindings(
    tools: _PDFToolSet | None = None,
) -> dict[str, dict[str, object]]:
    if tools is not None:
        return tools.receipt()
    with _held_pdf_tool_set() as resolved:
        return resolved.receipt()


def _scanner_contract(tools: _PDFToolSet | None = None) -> dict[str, object]:
    _revalidate_held_payload(_EXECUTED_DLP_SOURCE)
    return {
        "schema_version": "cloud-v2-dlp-scanner-contract-v5",
        "scanner_source_sha256": hashlib.sha256(
            _EXECUTED_DLP_SOURCE.payload
        ).hexdigest(),
        "scanner_source_binding": (
            "import-time-held-bytes-formal-snapshot-module-origin-ledger"
        ),
        "scanner_source_receipt_time_revalidated": True,
        "pdf_tool_executable_bindings": _pdf_tool_bindings(tools),
        "pdf_tool_binding_contract": (
            "scan-start-absolute-real-path-held-descriptor-state-and-exact-bytes;"
            "executed-from-private-0500-exact-byte-snapshot;"
            "original-and-snapshot-revalidated-before-and-after-each-exec-and-before-receipt"
        ),
        "poppler_runtime_data_binding_contract": (
            "single-installation-prefix-compiled-absolute-data-root;"
            "compiled-data-root-exactly-bound-to-held-core-library-bytes;"
            "exact-file-literal-seatbelt-read-allowlist;"
            "held-descriptors-tree-membership-and-bytes-revalidated-before-and-after-"
            "each-exec-and-before-receipt;active-same-uid-tampering-not-prevented;"
            "production-requires-root-owned-service-uid-nonwritable-runtime-ancestors"
        ),
        "pdf_nonempty_stderr_fails_closed": True,
        "inventory_scan_semantic_input_contract": (
            "single-capture-exact-bytes-materialized-private-snapshot;"
            "original-roots-files-and-bytes-held-through-receipt-or-validator-return"
        ),
        "rule_ids": sorted(rule_id for rule_id, _pattern in RULES),
        "tree_path_names_scanned": True,
        "zip_tar_member_names_scanned": True,
        "zip_tar_metadata_scanned": True,
        "sqlite_table_column_schema_names_scanned": True,
        "pdf_standard_metadata_scanned": True,
        "pdf_xmp_custom_metadata_scanned_as_raw_bytes": True,
        "pdf_javascript_urls_and_structure_scanned": True,
        "pdf_images_require_approved_ocr_coverage": True,
        "pdf_tool_stderr_scanned": True,
        "pdf_attachment_listing_strict": True,
        "pdf_attachments_extracted_by_index_to_fixed_names": True,
        "pdf_environment": {
            "LANG": "C",
            "LC_ALL": "C",
            "darwin_dynamic_library_path_bound": True,
        },
        "resource_limits": {
            "container_member_bytes": MAX_CONTAINER_MEMBER_BYTES,
            "container_nesting_depth": MAX_CONTAINER_NESTING_DEPTH,
            "pdf_attachment_aggregate_bytes": MAX_PDF_RUNTIME_BYTES,
            "pdf_tool_address_space_hard_limit_bytes": None,
            "pdf_tool_address_space_limit_contract": (
                "not-applied-on-darwin-because-the-pre-exec-child-inherits-the-python-"
                "virtual-address-space-and-darwin-rejects-lowering-rlimit-as-below-it"
            ),
            "pdf_tool_cpu_hard_seconds": MAX_PDF_CPU_SECONDS,
            "pdf_tool_cpu_hard_limit_scope": "per-command-child-process",
            "pdf_tool_fsize_hard_bytes": MAX_PDF_TOOL_OUTPUT_BYTES,
            "pdf_tool_fsize_hard_limit_scope": "per-output-file",
            "pdf_tool_output_bytes_per_stream": MAX_PDF_TOOL_OUTPUT_BYTES,
            "pdf_tool_wall_timeout_seconds": MAX_PDF_TOOL_WALL_SECONDS,
            "pdf_tool_wall_timeout_scope": "per-command-not-end-to-end-pdf-scan",
            "pdf_end_to_end_wall_hard_limit_seconds": None,
            "pdf_aggregate_cpu_hard_limit_seconds": None,
            "pdf_process_memory_hard_limit_bytes": None,
            "pdf_scratch_hard_limit_bytes": None,
            "scanned_bytes": MAX_SCANNED_BYTES,
            "scanned_objects": MAX_SCANNED_OBJECTS,
            "stable_capture_checked_before_materialization": True,
            "pdf_tool_set_persistent_descriptor_formula": "4T+2D+2L+2U+5",
            "pdf_tool_invocation_descriptor_reserve": (
                _PDF_TOOL_INVOCATION_FD_RESERVE
            ),
            "pdf_tool_set_capacity_preflight_enforced": True,
        },
        "source_media_ocr_bound_to_upstream_receipt": True,
        "binary_ascii_strings_are_not_image_content_dlp": True,
        "unbound_image_payloads_rejected": True,
        "structured_payload_magic_bound_to_extension": True,
        "sqlite_all_schema_objects_scanned": True,
        "sqlite_sidecars_rejected": True,
        "symlinks_and_nonregular_nodes_rejected": True,
        "governance_visual_review_evidence": {
            "content_dlp_asserted": False,
            "excluded_from_candidate": True,
            "tree_identity_bound": True,
        },
        "network_calls": 0,
    }


def _layer_receipt(
    inventory: Mapping[str, object],
    findings: list[dict[str, str]],
    **extra: object,
) -> dict[str, object]:
    return {
        **dict(inventory),
        "finding_count": len(findings),
        "findings": findings,
        **extra,
    }


def _positive_canary_receipt(
    tools: _PDFToolSet | None = None,
) -> tuple[dict[str, object], bool]:
    scanner = DLPScanner(_pdf_tools=tools)
    payload = positive_canary()
    scanner.scan_text("canary/synthetic-positive", payload)
    detected = sorted({finding.rule_id for finding in scanner.findings})
    required = sorted(rule_id for rule_id, _pattern in RULES)
    rejected = detected == required
    return (
        {
            "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "rejected_as_expected": rejected,
            "required_rule_ids": required,
            "detected_rule_ids": detected,
            "finding_count": len(scanner.findings),
        },
        rejected,
    )


_SQLITE_SIDECAR_SUFFIXES = ("-journal", "-shm", "-wal")


def _is_sqlite_sidecar_member(name: str) -> bool:
    folded = name.casefold()
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        if not folded.endswith(suffix):
            continue
        database_name = name[: -len(suffix)]
        return PurePosixPath(database_name).suffix.casefold() in {
            ".db",
            ".sqlite",
            ".sqlite3",
        }
    return False


def _reject_sqlite_sidecar_members(names: Iterable[str]) -> None:
    if any(_is_sqlite_sidecar_member(name) for name in names):
        raise DLPError("container contains a SQLite sidecar member")


def _assert_sqlite_sidecars_absent(parent_fd: int, database_name: str) -> None:
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        try:
            os.stat(
                database_name + suffix,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise DLPError("SQLite sidecar state cannot be validated") from exc
        raise DLPError("SQLite DLP target has an unsealed sidecar")


def _walk_held_tree(
    root_fd: int,
    *,
    allow_empty_directories: bool = False,
    capture_budget: _StableCaptureBudget | None = None,
) -> tuple[_TreeEntry, ...]:
    records: list[_TreeEntry] = []
    budget = capture_budget or _StableCaptureBudget()

    def visit(
        directory_fd: int,
        prefix: PurePosixPath | None,
        depth: int,
    ) -> None:
        if depth > MAX_CONTAINER_NESTING_DEPTH:
            raise DLPError("DLP tree nesting-depth limit exceeded")
        before = _node_state(os.fstat(directory_fd))
        children: list[tuple[str, os.stat_result, str]] = []
        try:
            with os.scandir(directory_fd) as iterator:
                for directory_entry in iterator:
                    name = directory_entry.name
                    relative_path = (
                        PurePosixPath(name) if prefix is None else prefix / name
                    )
                    relative = relative_path.as_posix()
                    if _is_generated_python_cache(relative):
                        raise DLPError(
                            f"DLP tree contains generated Python cache: {relative}"
                        )
                    inspected = os.stat(
                        name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                    if stat.S_ISLNK(inspected.st_mode):
                        raise DLPError("DLP tree contains a symlink")
                    if stat.S_ISDIR(inspected.st_mode):
                        kind = "directory"
                    elif stat.S_ISREG(inspected.st_mode):
                        if inspected.st_nlink != 1:
                            raise DLPError("DLP tree contains a hardlink")
                        kind = "file"
                    else:
                        raise DLPError("DLP tree contains a nonregular node")
                    budget.reserve_node(kind, _node_state(inspected))
                    children.append((name, inspected, kind))
        except OSError as exc:
            raise DLPError("DLP tree cannot be enumerated safely") from exc
        for name, inspected, kind in sorted(children, key=lambda item: item[0]):
            relative_path = PurePosixPath(name) if prefix is None else prefix / name
            relative = relative_path.as_posix()
            if kind == "directory":
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                )
                child: int | None = None
                try:
                    try:
                        child = os.open(name, flags, dir_fd=directory_fd)
                        opened = os.fstat(child)
                    except OSError as exc:
                        raise DLPError(
                            "DLP tree directory cannot be opened safely"
                        ) from exc
                    if _node_state(opened) != _node_state(inspected):
                        raise DLPError("DLP tree directory identity changed")
                    entry = _TreeEntry(relative, "directory", _node_state(opened))
                    records.append(entry)
                    visit(child, relative_path, depth + 1)
                finally:
                    if child is not None:
                        _close_descriptor(child)
                continue
            entry = _TreeEntry(relative, "file", _node_state(inspected))
            records.append(entry)
        after = _node_state(os.fstat(directory_fd))
        if after != before:
            raise DLPError("DLP tree directory identity changed during enumeration")

    budget.reserve_node("directory", _node_state(os.fstat(root_fd)))
    visit(root_fd, None, 0)
    directories = [record.relative_path for record in records if record.kind == "directory"]
    files = [record.relative_path for record in records if record.kind == "file"]
    if not allow_empty_directories and any(
        not any(path.startswith(directory + "/") for path in files)
        for directory in directories
    ):
        raise DLPError("DLP tree contains an unaccounted empty directory")
    return tuple(sorted(records))


def _revalidate_held_directory(
    path: Path,
    descriptor: int,
    expected: _NodeState,
    field: str,
) -> None:
    try:
        if _node_state(os.fstat(descriptor)) != expected:
            raise DLPError(f"{field} identity changed")
    except OSError as exc:
        raise DLPError(f"{field} identity changed") from exc
    reopened_path, reopened, reopened_state = _open_directory_path(path, field)
    try:
        if reopened_path != path or reopened_state != expected:
            raise DLPError(f"{field} path identity changed")
    finally:
        _close_descriptor(reopened)


def _pdf_sandbox_literal(path: str | Path) -> str:
    value = os.fspath(path)
    if isinstance(value, bytes) or not value or "\x00" in value:
        raise DLPError("PDF sandbox path is invalid")
    return json.dumps(value, ensure_ascii=False)


def _pdf_sandbox_profile(
    tools: _PDFToolSet,
    *,
    tool_name: str,
    scratch: Path,
    passed_fds: tuple[int, ...],
    writable_fds: tuple[int, ...],
) -> str:
    tool = Path(tools.command_path(tool_name))
    aliases = tuple(f"/dev/fd/{descriptor}" for descriptor in passed_fds)
    writable_aliases = tuple(f"/dev/fd/{descriptor}" for descriptor in writable_fds)
    runtime_data_paths = (
        tools.runtime_data.path,
        *(
            tools.runtime_data.path / entry.relative_path
            for entry in tools.runtime_data.entries
        ),
    )
    read_filters = " ".join(
        [
            '(literal "/")',
            '(literal "/dev/null")',
            f"(literal {_pdf_sandbox_literal(tools.environment_executable.path)})",
            f"(subpath {_pdf_sandbox_literal(tools.bundle_root)})",
            f"(subpath {_pdf_sandbox_literal(scratch)})",
            *(
                f"(literal {_pdf_sandbox_literal(path)})"
                for path in runtime_data_paths
            ),
            *(f"(literal {_pdf_sandbox_literal(alias)})" for alias in aliases),
        ]
    )
    write_filters = " ".join(
        [
            '(literal "/dev/null")',
            f"(subpath {_pdf_sandbox_literal(scratch)})",
            *(
                f"(literal {_pdf_sandbox_literal(alias)})"
                for alias in writable_aliases
            ),
        ]
    )
    executable_filters = " ".join(
        (
            f"(literal {_pdf_sandbox_literal(tools.environment_executable.path)})",
            f"(literal {_pdf_sandbox_literal(tool)})",
        )
    )
    return (
        "(version 1)(allow default)(deny network*)"
        "(deny file-read*)"
        f"(allow file-read* {read_filters})"
        "(deny file-write*)"
        f"(allow file-write* {write_filters})"
        "(deny process-exec*)"
        f"(allow process-exec {executable_filters})"
        "(deny process-fork)"
    )


def _stage_pdf_sandbox_profile(scratch: Path, profile: str) -> Path:
    path = scratch / "pdf-tool.sb"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o400,
        )
        _write_all(descriptor, profile.encode("utf-8"), "PDF sandbox profile")
        os.fchmod(descriptor, 0o400)
        _close_descriptor(descriptor)
        descriptor = None
        return path
    except BaseException:
        actions: list[Callable[[], None]] = []
        if descriptor is not None:
            actions.append(lambda: _close_descriptor(descriptor))
        actions.append(lambda: path.unlink(missing_ok=True))
        _finish_cleanup(_drain_cleanup(actions))
        raise


def _lower_resource_limit(kind: int, requested: int) -> None:
    _soft_limit, hard_limit = resource.getrlimit(kind)
    limit = requested
    if hard_limit != resource.RLIM_INFINITY:
        limit = min(limit, hard_limit)
    if limit <= 0:
        raise OSError("PDF DLP child resource limit is unavailable")
    resource.setrlimit(kind, (limit, limit))


def _limit_pdf_tool_resources() -> None:
    _lower_resource_limit(resource.RLIMIT_FSIZE, MAX_PDF_TOOL_OUTPUT_BYTES)
    _lower_resource_limit(resource.RLIMIT_CPU, MAX_PDF_CPU_SECONDS)


def _bounded_pdf_tool_output(
    captured: bytes | None,
    output_file: Any,
    field: str,
) -> bytes:
    if captured is not None:
        if not isinstance(captured, bytes):
            raise DLPError(f"{field} has an invalid type")
        payload = captured
    else:
        try:
            size = os.fstat(output_file.fileno()).st_size
            if size > MAX_PDF_TOOL_OUTPUT_BYTES:
                raise DLPError(f"{field} exceeds its size limit")
            output_file.seek(0)
            payload = output_file.read(MAX_PDF_TOOL_OUTPUT_BYTES + 1)
        except OSError as exc:
            raise DLPError(f"{field} cannot be read safely") from exc
    if len(payload) > MAX_PDF_TOOL_OUTPUT_BYTES:
        raise DLPError(f"{field} exceeds its size limit")
    return payload


class DLPScanner:
    def __init__(
        self,
        *,
        _ocr_approved_container_roots: Iterable[str] = (),
        _pdf_tools: _PDFToolSet | None = None,
    ) -> None:
        self.findings: set[Finding] = set()
        self.object_hashes: dict[str, str] = {}
        self.scanned_bytes = 0
        self._ocr_approved_container_roots = tuple(
            _object_id(value) for value in _ocr_approved_container_roots
        )
        self._pdf_tools = _pdf_tools
        self._owns_pdf_tools = False

    def _ensure_pdf_tools(self) -> _PDFToolSet:
        if self._pdf_tools is None:
            self._pdf_tools = _open_pdf_tool_set()
            self._owns_pdf_tools = True
        self._pdf_tools.revalidate()
        return self._pdf_tools

    def scanner_contract(self) -> dict[str, object]:
        try:
            return _scanner_contract(self._ensure_pdf_tools())
        finally:
            if self._owns_pdf_tools:
                self.close()

    def close(self) -> None:
        if self._owns_pdf_tools and self._pdf_tools is not None:
            self._pdf_tools.close()
            self._pdf_tools = None
        self._owns_pdf_tools = False

    def __enter__(self) -> "DLPScanner":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _record_payload(self, object_id: str, payload: bytes) -> str:
        object_id = _object_id(object_id)
        if object_id in self.object_hashes:
            raise DLPError("duplicate DLP object id")
        next_object_count = len(self.object_hashes) + 1
        next_scanned_bytes = self.scanned_bytes + len(payload)
        if next_object_count > MAX_SCANNED_OBJECTS:
            raise DLPError("DLP object-count limit exceeded")
        if next_scanned_bytes > MAX_SCANNED_BYTES:
            raise DLPError("DLP expanded-byte limit exceeded")
        self.scanned_bytes = next_scanned_bytes
        self.object_hashes[object_id] = hashlib.sha256(payload).hexdigest()
        return object_id

    def _require_expansion_capacity(self, objects: int, byte_count: int) -> None:
        if type(objects) is not int or objects < 0:
            raise DLPError("DLP projected object count is invalid")
        if type(byte_count) is not int or byte_count < 0:
            raise DLPError("DLP projected byte count is invalid")
        if len(self.object_hashes) + objects > MAX_SCANNED_OBJECTS:
            raise DLPError("DLP object-count limit exceeded")
        if self.scanned_bytes + byte_count > MAX_SCANNED_BYTES:
            raise DLPError("DLP expanded-byte limit exceeded")

    def _read_container_member(
        self,
        handle: Any,
        *,
        declared_size: int,
        field: str,
    ) -> bytes:
        if declared_size < 0 or declared_size > MAX_CONTAINER_MEMBER_BYTES:
            raise DLPError(f"{field} exceeds its size limit")
        self._require_expansion_capacity(1, declared_size)
        payload = handle.read(declared_size + 1)
        if not isinstance(payload, bytes) or len(payload) != declared_size:
            raise DLPError(f"{field} size differs from its declaration")
        return payload

    def scan_text(self, object_id: str, text: str) -> None:
        if not isinstance(text, str):
            raise TypeError("DLP text must be a string")
        payload = text.encode("utf-8")
        object_id = self._record_payload(object_id, payload)
        self._scan_matches(object_id, text)

    def _scan_matches(self, object_id: str, text: str) -> None:
        for rule_id, pattern in RULES:
            for match in pattern.finditer(text):
                if rule_id == "email":
                    domain = match.group(0).rsplit("@", 1)[1].lower()
                    if domain.endswith((".test", ".invalid")):
                        continue
                self.findings.add(Finding(object_id, rule_id, _value_hash(match.group(0))))

    def scan_bytes(self, object_id: str, payload: bytes) -> None:
        object_id = self._record_payload(object_id, payload)
        strings = re.findall(rb"[\x20-\x7e]{6,}", payload)
        if strings:
            self._scan_matches(object_id, "\n".join(item.decode("ascii") for item in strings))

    def scan_file(
        self,
        path: Path,
        object_id: str,
        *,
        _expected_state: _NodeState | None = None,
    ) -> None:
        try:
            self._scan_file(
                path,
                object_id,
                _expected_state=_expected_state,
            )
        finally:
            if self._owns_pdf_tools:
                self.close()

    def _scan_file(
        self,
        path: Path,
        object_id: str,
        *,
        _expected_state: _NodeState | None = None,
    ) -> None:
        with _held_payload(
            path,
            "DLP target",
            expected_state=_expected_state,
        ) as held:
            payload = held.payload
            kind = _require_payload_kind(held.path.name, payload)
            suffix = held.path.suffix.lower()
            if kind == "zip":
                self._record_payload(object_id, payload)
                self._scan_zip(payload, object_id)
            elif kind == "tar":
                self._record_payload(object_id, payload)
                self._scan_tar(payload, object_id)
            elif kind == "pdf":
                self._record_payload(object_id, payload)
                self._scan_pdf(payload, object_id)
            elif kind == "sqlite":
                _assert_sqlite_sidecars_absent(held.parent_fd, held.path.name)
                self._record_payload(object_id, payload)
                self._scan_sqlite(payload, object_id)
                _assert_sqlite_sidecars_absent(held.parent_fd, held.path.name)
            elif suffix in TEXT_SUFFIXES or held.path.name in {
                "SHA256SUMS",
                "CODE_MANIFEST.sha256",
            }:
                try:
                    self.scan_text(object_id, payload.decode("utf-8", errors="strict"))
                except UnicodeDecodeError as exc:
                    raise DLPError("declared text artifact is not UTF-8") from exc
            elif kind == "image":
                raise DLPError("image payload requires approved OCR coverage")
            else:
                self.scan_bytes(object_id, payload)

    def _scan_zip(self, payload: bytes, object_id: str) -> None:
        declared_count, declared_bytes = _zip_preflight(payload)
        self._require_expansion_capacity(declared_count, declared_bytes)
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if len(archive.filelist) != declared_count:
                    raise DLPError("ZIP member count differs from its preflight")
                self._scan_zip_archive(archive, object_id, depth=0)
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
            raise DLPError("ZIP/DOCX DLP scan failed") from exc

    def _scan_zip_archive(
        self,
        archive: zipfile.ZipFile,
        object_id: str,
        *,
        depth: int,
    ) -> None:
        if depth > MAX_CONTAINER_NESTING_DEPTH:
            raise DLPError("DLP container nesting-depth limit exceeded")
        self.scan_bytes(object_id + "/archive-comment", archive.comment)
        self._require_expansion_capacity(len(archive.filelist), 0)
        members = [
            (
                info,
                _canonical_container_member_name(
                    info.filename,
                    is_directory=info.is_dir(),
                ),
            )
            for info in sorted(archive.infolist(), key=lambda item: item.filename)
        ]
        names = [name for _info, name in members]
        if len(set(names)) != len(names):
            raise DLPError("ZIP contains a duplicate member name")
        _reject_sqlite_sidecar_members(
            name for info, name in members if not info.is_dir()
        )
        seen_names: set[str] = set()
        for member_index, (info, name) in enumerate(members, 1):
            if name in seen_names:
                raise DLPError("ZIP contains a duplicate member name")
            seen_names.add(name)
            member = _object_id(f"{object_id}/members/{member_index}")
            self.scan_text(member + "/name", name)
            self.scan_bytes(member + "/comment", info.comment)
            self.scan_bytes(member + "/extra", info.extra)
            if info.is_dir():
                continue
            unix_mode = info.external_attr >> 16 if info.create_system == 3 else 0
            file_type = stat.S_IFMT(unix_mode)
            if (
                info.flag_bits & 0x1
                or info.file_size > MAX_CONTAINER_MEMBER_BYTES
                or (file_type and not stat.S_ISREG(unix_mode))
            ):
                raise DLPError("encrypted, oversized, or unsafe ZIP member")
            with archive.open(info, mode="r") as handle:
                member_payload = self._read_container_member(
                    handle,
                    declared_size=info.file_size,
                    field="ZIP member",
                )
            self._scan_member_payload(
                member + "/payload", name, member_payload, depth=depth
            )

    def _scan_tar(self, payload: bytes, object_id: str) -> None:
        try:
            with tarfile.open(
                fileobj=io.BytesIO(payload),
                mode="r:*",
                tarinfo=_BoundedTarInfo,
            ) as archive:
                self._scan_tar_archive(archive, object_id, depth=0)
        except (OSError, tarfile.TarError, UnicodeDecodeError) as exc:
            raise DLPError("tar DLP scan failed") from exc

    def _scan_tar_archive(
        self,
        archive: tarfile.TarFile,
        object_id: str,
        *,
        depth: int,
    ) -> None:
        if depth > MAX_CONTAINER_NESTING_DEPTH:
            raise DLPError("DLP container nesting-depth limit exceeded")
        members: list[tuple[tarfile.TarInfo, str]] = []
        projected_bytes = 0
        for info in archive:
            name = _canonical_container_member_name(
                info.name,
                is_directory=info.isdir(),
            )
            projected_bytes += info.size if info.isfile() else 0
            self._require_expansion_capacity(len(members) + 1, projected_bytes)
            members.append((info, name))
        members.sort(key=lambda item: item[0].name)
        names = [name for _info, name in members]
        if len(set(names)) != len(names):
            raise DLPError("tar contains a duplicate member name")
        _reject_sqlite_sidecar_members(
            name for info, name in members if not info.isdir()
        )
        seen_names: set[str] = set()
        for member_index, (info, name) in enumerate(members, 1):
            if name in seen_names:
                raise DLPError("tar contains a duplicate member name")
            seen_names.add(name)
            member = _object_id(f"{object_id}/members/{member_index}")
            self.scan_text(member + "/name", name)
            self.scan_text(member + "/owner", f"{info.uname}\n{info.gname}")
            self.scan_text(
                member + "/pax-headers",
                json.dumps(info.pax_headers, ensure_ascii=False, sort_keys=True),
            )
            if info.linkname:
                self.scan_text(member + "/link-name", info.linkname)
            if info.size > MAX_CONTAINER_MEMBER_BYTES:
                raise DLPError("unsafe or oversized tar member")
            if info.isdir():
                continue
            if not info.isfile():
                raise DLPError("unsafe or oversized tar member")
            handle = archive.extractfile(info)
            if handle is None:
                raise DLPError("tar member cannot be read")
            member_payload = self._read_container_member(
                handle,
                declared_size=info.size,
                field="tar member",
            )
            self._scan_member_payload(
                member + "/payload",
                name,
                member_payload,
                depth=depth,
            )

    def _scan_member_payload(
        self,
        object_id: str,
        name: str,
        payload: bytes,
        *,
        depth: int = 0,
    ) -> None:
        if depth > MAX_CONTAINER_NESTING_DEPTH:
            raise DLPError("DLP container nesting-depth limit exceeded")
        if _is_sqlite_sidecar_member(name):
            raise DLPError("container contains a SQLite sidecar member")
        kind = _require_payload_kind(name, payload)
        suffix = PurePosixPath(name).suffix.lower()
        if kind == "image":
            self._record_payload(object_id, payload)
            if not any(
                object_id.startswith(root + "/")
                for root in self._ocr_approved_container_roots
            ):
                raise DLPError("image payload requires approved OCR coverage")
        elif kind == "zip":
            self._record_payload(object_id, payload)
            declared_count, declared_bytes = _zip_preflight(payload)
            self._require_expansion_capacity(declared_count, declared_bytes)
            try:
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    if len(archive.filelist) != declared_count:
                        raise DLPError("ZIP member count differs from its preflight")
                    self._scan_zip_archive(archive, object_id, depth=depth + 1)
            except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
                raise DLPError("nested ZIP/DOCX DLP scan failed") from exc
        elif kind == "tar":
            self._record_payload(object_id, payload)
            try:
                with tarfile.open(
                    fileobj=io.BytesIO(payload),
                    mode="r:*",
                    tarinfo=_BoundedTarInfo,
                ) as archive:
                    self._scan_tar_archive(archive, object_id, depth=depth + 1)
            except (OSError, tarfile.TarError, UnicodeDecodeError) as exc:
                raise DLPError("nested tar DLP scan failed") from exc
        elif kind == "sqlite":
            self._record_payload(object_id, payload)
            self._scan_sqlite(payload, object_id)
        elif kind == "pdf":
            self._record_payload(object_id, payload)
            self._scan_pdf(payload, object_id)
        elif suffix in TEXT_SUFFIXES:
            self.scan_text(object_id, payload.decode("utf-8", errors="strict"))
        else:
            self.scan_bytes(object_id, payload)

    def _scan_pdf(self, payload: bytes, object_id: str) -> None:
        with _anonymous_readonly_payload(
            payload,
            suffix=".pdf",
            field="PDF DLP payload",
        ) as (payload_fd, payload_alias):
            text_outputs: dict[str, str] = {}
            commands: tuple[tuple[str, list[str], bool], ...] = (
                (
                    "text",
                    ["pdftotext", "-enc", "UTF-8", "-layout", payload_alias, "-"],
                    True,
                ),
                ("metadata", ["pdfinfo", payload_alias], True),
                (
                    "custom-metadata",
                    ["pdfinfo", "-enc", "UTF-8", "-custom", payload_alias],
                    True,
                ),
                ("xmp-metadata", ["pdfinfo", "-meta", payload_alias], False),
                (
                    "javascript",
                    ["pdfinfo", "-enc", "UTF-8", "-js", payload_alias],
                    True,
                ),
                ("urls", ["pdfinfo", "-enc", "UTF-8", "-url", payload_alias], True),
                (
                    "structure-text",
                    ["pdfinfo", "-enc", "UTF-8", "-struct-text", payload_alias],
                    True,
                ),
                ("image-list", ["pdfimages", "-list", payload_alias], True),
                ("attachment-list", ["pdfdetach", "-list", payload_alias], True),
            )
            for label, command, require_utf8 in commands:
                result = self._run_pdf_tool(command, payload_fd)
                self.scan_bytes(object_id + "/" + label + "-stderr", result.stderr)
                if result.stderr:
                    raise DLPError("PDF DLP tool emitted diagnostic output")
                if result.returncode != 0:
                    raise DLPError("PDF DLP tool rejected the source")
                if require_utf8:
                    try:
                        output = result.stdout.decode("utf-8", errors="strict")
                    except UnicodeDecodeError as exc:
                        raise DLPError("PDF DLP text output is not UTF-8") from exc
                    text_outputs[label] = output
                    self.scan_text(object_id + "/" + label, output)
                else:
                    self.scan_bytes(object_id + "/" + label, result.stdout)

            if _pdf_image_list_has_images(text_outputs["image-list"]) and not any(
                object_id == root or object_id.startswith(root + "/")
                for root in self._ocr_approved_container_roots
            ):
                raise DLPError("PDF image payload requires approved OCR coverage")

            raw_attachment_names = _parse_pdf_attachment_list(
                text_outputs["attachment-list"]
            )
            attachment_names = tuple(
                _canonical_container_member_name(name, is_directory=False)
                for name in raw_attachment_names
            )
            attachment_count = len(attachment_names)
            if attachment_count > MAX_PDF_RUNTIME_IMAGE_COUNT:
                raise DLPError("PDF attachment-count limit exceeded")
            if len(set(attachment_names)) != attachment_count:
                raise DLPError("PDF attachment listing contains duplicate names")
            _reject_sqlite_sidecar_members(attachment_names)
            self._require_expansion_capacity(attachment_count * 3, 0)
            if attachment_count:
                tools = self._ensure_pdf_tools()
                extracted_bytes = 0
                for attachment_index, name in enumerate(attachment_names, 1):
                    with _anonymous_writable_output(
                        tools.scratch_root,
                        field="PDF attachment output",
                    ) as (output_fd, output_alias):
                        self.scan_text(
                            f"{object_id}/attachments/{attachment_index}/declared-name",
                            name,
                        )
                        result = self._run_pdf_tool(
                            [
                                "pdfdetach",
                                "-save",
                                str(attachment_index),
                                "-o",
                                output_alias,
                                payload_alias,
                            ],
                            payload_fd,
                            extra_pass_fds=(output_fd,),
                            writable_fds=(output_fd,),
                        )
                        self.scan_bytes(
                            f"{object_id}/attachments/{attachment_index}/save-stdout",
                            result.stdout,
                        )
                        self.scan_bytes(
                            f"{object_id}/attachments/{attachment_index}/save-stderr",
                            result.stderr,
                        )
                        if result.stderr:
                            raise DLPError(
                                "PDF attachment extraction emitted diagnostic output"
                            )
                        if result.returncode != 0:
                            raise DLPError("PDF attachment extraction was rejected")
                        attachment_payload, _attachment_state = _read_open_payload(
                            output_fd,
                            field="PDF attachment output",
                            max_bytes=MAX_PDF_TOOL_OUTPUT_BYTES,
                        )
                        extracted_bytes += len(attachment_payload)
                        if extracted_bytes > MAX_PDF_RUNTIME_BYTES:
                            raise DLPError("PDF attachment aggregate-byte limit exceeded")
                        self._scan_member_payload(
                            _object_id(
                                f"{object_id}/attachments/"
                                f"{attachment_index}/payload"
                            ),
                            name,
                            attachment_payload,
                        )

    def _run_pdf_tool(
        self,
        command: list[str],
        payload_fd: int,
        *,
        extra_pass_fds: tuple[int, ...] = (),
        writable_fds: tuple[int, ...] = (),
    ) -> subprocess.CompletedProcess[bytes]:
        tools = self._ensure_pdf_tools()
        if not command:
            raise DLPError("PDF DLP tool command is empty")
        tool_name = command[0]
        bound_command = [tools.command_path(tool_name), *command[1:]]
        pass_fds = tuple(dict.fromkeys((payload_fd, *extra_pass_fds)))
        if any(descriptor not in pass_fds for descriptor in writable_fds):
            raise DLPError("PDF DLP writable descriptor is not inherited")
        tools.revalidate()
        try:
            os.lseek(payload_fd, 0, os.SEEK_SET)
            with tempfile.TemporaryDirectory(
                prefix="invocation-",
                dir=tools.scratch_root,
            ) as temporary:
                scratch = Path(temporary).resolve(strict=True)
                scratch.chmod(0o700)
                profile = _pdf_sandbox_profile(
                    tools,
                    tool_name=tool_name,
                    scratch=scratch,
                    passed_fds=pass_fds,
                    writable_fds=writable_fds,
                )
                profile_path = _stage_pdf_sandbox_profile(scratch, profile)
                isolated_command = [
                    str(tools.sandbox_executable.path),
                    "-f",
                    str(profile_path),
                    str(tools.environment_executable.path),
                    "-i",
                    f"DYLD_LIBRARY_PATH={tools.library_root}",
                    f"HOME={scratch}",
                    f"TMPDIR={scratch}",
                    f"TMP={scratch}",
                    f"TEMP={scratch}",
                    "LC_ALL=C",
                    "LANG=C",
                    *bound_command,
                ]
                with tempfile.TemporaryFile(
                    mode="w+b",
                    dir=scratch,
                ) as stdout_file, tempfile.TemporaryFile(
                    mode="w+b",
                    dir=scratch,
                ) as stderr_file:
                    result = subprocess.run(
                        isolated_command,
                        check=False,
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        pass_fds=pass_fds,
                        timeout=MAX_PDF_TOOL_WALL_SECONDS,
                        cwd=scratch,
                        env=tools.environment(),
                        start_new_session=True,
                        preexec_fn=_limit_pdf_tool_resources,
                    )
                    stdout = _bounded_pdf_tool_output(
                        result.stdout,
                        stdout_file,
                        "PDF DLP tool stdout",
                    )
                    stderr = _bounded_pdf_tool_output(
                        result.stderr,
                        stderr_file,
                        "PDF DLP tool stderr",
                    )
        except (OSError, subprocess.SubprocessError) as exc:
            raise DLPError("PDF DLP tool failed") from exc
        finally:
            tools.revalidate()
        return subprocess.CompletedProcess(
            isolated_command,
            result.returncode,
            stdout,
            stderr,
        )

    def _scan_sqlite(self, payload: bytes, object_id: str) -> None:
        with _anonymous_readonly_payload(
            payload,
            suffix=".sqlite3",
            field="SQLite DLP snapshot",
        ) as (_payload_fd, payload_alias):
            try:
                connection = sqlite3.connect(
                    Path(payload_alias).as_uri() + "?mode=ro&immutable=1",
                    uri=True,
                )
            except sqlite3.Error as exc:
                raise DLPError("SQLite DLP target cannot be opened read-only") from exc
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA query_only=ON")
                if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
                    raise DLPError("SQLite DLP snapshot is not query-only")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise DLPError("SQLite DLP target failed integrity_check")
                schema_objects = [
                    (str(row[0]), str(row[1]), str(row[2] or ""), str(row[3] or ""))
                    for row in connection.execute(
                        "SELECT type, name, tbl_name, sql FROM sqlite_master "
                        "ORDER BY type, name, tbl_name"
                    )
                ]
                for schema_index, (kind, name, table_name, schema_sql) in enumerate(
                    schema_objects,
                    1,
                ):
                    prefix = f"{object_id}/schema/objects/{schema_index}"
                    self.scan_text(prefix + "/type", kind)
                    self.scan_text(prefix + "/name", name)
                    self.scan_text(prefix + "/table-name", table_name)
                    self.scan_text(prefix + "/sql", schema_sql)
                tables = [
                    (name, schema_sql)
                    for kind, name, _table_name, schema_sql in schema_objects
                    if kind == "table" and not name.startswith("sqlite_")
                ]
                for table_index, (table, schema_sql) in enumerate(tables, 1):
                    self.scan_text(
                        f"{object_id}/schema/tables/{table_index}/name",
                        table,
                    )
                    self.scan_text(
                        f"{object_id}/schema/tables/{table_index}/sql",
                        schema_sql,
                    )
                    quoted = '"' + table.replace('"', '""') + '"'
                    columns = [
                        str(row[1])
                        for row in connection.execute(f"PRAGMA table_info({quoted})")
                    ]
                    for column_index, column in enumerate(columns, 1):
                        self.scan_text(
                            f"{object_id}/schema/tables/{table_index}/columns/"
                            f"{column_index}",
                            column,
                        )
                    rows = connection.execute(f"SELECT * FROM {quoted}")
                    for row_number, row in enumerate(rows, 1):
                        for column_index, column in enumerate(row.keys(), 1):
                            value = row[column]
                            if value is None:
                                continue
                            cell_id = (
                                f"{object_id}/tables/{table_index}/columns/"
                                f"{column_index}/rows/{row_number}"
                            )
                            if isinstance(value, bytes):
                                self._scan_member_payload(cell_id, "cell.bin", value)
                            else:
                                self.scan_text(cell_id, str(value))
            except sqlite3.Error as exc:
                raise DLPError("SQLite DLP scan failed") from exc
            finally:
                connection.close()

    def scan_tree(self, root: Path, object_prefix: str) -> None:
        try:
            self._scan_tree(root, object_prefix)
        finally:
            if self._owns_pdf_tools:
                self.close()

    def _scan_tree(self, root: Path, object_prefix: str) -> None:
        root, root_fd, root_state = _open_directory_path(root, "DLP tree root")
        try:
            before = _walk_held_tree(root_fd)
            files = [record for record in before if record.kind == "file"]
            for path_index, record in enumerate(files, 1):
                relative = record.relative_path
                self.scan_text(
                    f"{object_prefix}/path-surfaces/{path_index}",
                    relative,
                )
                self._scan_file(
                    root / relative,
                    _object_id(object_prefix + "/" + relative),
                    _expected_state=record.state,
                )
            if _walk_held_tree(root_fd) != before:
                raise DLPError("DLP tree identity changed during scanning")
            _revalidate_held_directory(root, root_fd, root_state, "DLP tree root")
        finally:
            _close_descriptor(root_fd)

    def summary(self) -> dict[str, object]:
        findings = [asdict(item) for item in sorted(self.findings)]
        return {
            "object_count": len(self.object_hashes),
            "scanned_bytes": self.scanned_bytes,
            "finding_count": len(findings),
            "findings": findings,
            "object_set_sha256": hashlib.sha256(
                json.dumps(
                    self.object_hashes,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        }


def positive_canary() -> str:
    return "\n".join(
        (
            "contact=person" + "@example.com",
            "mobile=13812" + "345678",
            "phone=010-" + "12345678",
            "path=/" + "Users/example/private",
            "tenant_" + "access_" + "token=syntheticCanaryToken1234",
            "token=" + "sk" + "-abcdefghijklmnop1234",
            "host=10.20" + ".30.40",
            "host6=fd12:" + "3456::1",
            "-----BEGIN " + "PRIVATE KEY-----",
            "pass" + "word=\"synthetic-" + "canary-secret\"",
            "service=records.customer." + "corp",
            "id=11010519" + "491231002X",
        )
    )


def _absolute_without_symlink_components(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    current = path
    while not os.path.lexists(current):
        if current == current.parent:
            break
        current = current.parent
    if os.path.lexists(current) and stat.S_ISLNK(os.lstat(current).st_mode):
        raise DLPError("receipt path contains a symlink component")
    return path.resolve(strict=False)


def _detached_receipt_path(
    raw: str | Path,
    *,
    scanned_roots: Iterable[str | Path],
    must_exist: bool,
) -> Path:
    path = _absolute_without_symlink_components(raw)
    if must_exist:
        try:
            mode = os.lstat(path).st_mode
        except OSError as exc:
            raise DLPError("DLP receipt does not exist") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise DLPError("DLP receipt must be a regular unsymlinked file")
    elif os.path.lexists(path):
        raise DLPError("DLP receipt output must not already exist")
    for raw_root in scanned_roots:
        root = Path(raw_root).resolve(strict=True)
        if path == root or root in path.parents:
            raise DLPError("DLP receipt must be detached from every scanned root")
    return path


def _fsync_directory_path(path: Path, field: str) -> None:
    resolved, descriptor, _state = _open_directory_path(path, field)
    try:
        if resolved != path:
            raise DLPError(f"{field} path is unstable")
        os.fsync(descriptor)
    except DLPError:
        raise
    except OSError as exc:
        raise DLPError(f"{field} could not be made durable") from exc
    finally:
        _finish_cleanup(_drain_cleanup((lambda: _close_descriptor(descriptor),)))


def _ensure_durable_receipt_parent(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not os.path.lexists(current):
        missing.append(current)
        if current == current.parent:
            break
        current = current.parent
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise DLPError("DLP receipt parent cannot be created safely") from exc

    # Persist each directory inode and the directory entry that names it.  The
    # leaf receipt parent is synced again for staging creation and publication.
    for created in reversed(missing):
        _fsync_directory_path(created, "new DLP receipt parent")
        _fsync_directory_path(created.parent, "new DLP receipt parent ancestor")


def _write_new_json(path: Path, value: object) -> _WrittenJSON:
    _ensure_durable_receipt_parent(path.parent)
    payload = canonical_json_bytes(value)
    parent_path, parent_fd, parent_state = _open_directory_path(
        path.parent,
        "DLP receipt parent",
    )
    descriptor: int | None = None
    staging_name: str | None = None
    try:
        if parent_path != path.parent:
            raise DLPError("DLP receipt parent path is unstable")
        before_names = set(os.listdir(parent_fd))
        if path.name in before_names:
            raise DLPError("DLP receipt output appeared during the scan")
        staging_prefix = f".{path.name}.kg-dlp-stage-"
        if any(name.startswith(staging_prefix) for name in before_names):
            raise DLPError("DLP receipt parent contains unreconciled staging state")
        for _attempt in range(128):
            candidate = f".{path.name}.kg-dlp-stage-{secrets.token_hex(16)}"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
                staging_name = candidate
                break
            except FileExistsError:
                continue
            except OSError as exc:
                raise DLPError("DLP receipt staging file cannot be created safely") from exc
        if descriptor is None or staging_name is None:
            raise DLPError("DLP receipt staging name could not be reserved")
        _write_all(descriptor, payload, "DLP receipt")
        os.fchmod(descriptor, 0o600)
        file_state = _node_state(os.fstat(descriptor))
        entry_state = _node_state(
            os.stat(staging_name, dir_fd=parent_fd, follow_symlinks=False)
        )
        after_names = set(os.listdir(parent_fd))
        written_parent_state = _node_state(os.fstat(parent_fd))
        if file_state != entry_state or file_state.link_count != 1:
            raise DLPError("DLP receipt staging identity changed while writing")
        if after_names != before_names | {staging_name} or path.name in after_names:
            raise DLPError("DLP receipt parent membership changed while writing")
        os.fsync(parent_fd)
        held = _HeldPayload(
            path=path.parent / staging_name,
            field="staged DLP receipt",
            parent_fd=parent_fd,
            descriptor=descriptor,
            parent_state=written_parent_state,
            file_state=file_state,
            payload=payload,
        )
        result = _WrittenJSON(
            held=held,
            digest=hashlib.sha256(payload).hexdigest(),
            final_path=path,
            baseline_names=frozenset(before_names),
            staging_name=staging_name,
        )
        result.revalidate()
        return result
    except BaseException as exc:
        cleanup_errors: list[BaseException] = []
        if staging_name is not None:
            try:
                current = os.stat(
                    staging_name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                if descriptor is not None and _node_state(current) == _node_state(
                    os.fstat(descriptor)
                ):
                    os.unlink(staging_name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                elif descriptor is not None:
                    cleanup_errors.append(
                        DLPError("DLP receipt staging identity changed during cleanup")
                    )
            except FileNotFoundError:
                pass
            except BaseException as cleanup_exc:
                cleanup_errors.append(cleanup_exc)
        actions: list[Callable[[], None]] = []
        if descriptor is not None:
            actions.append(lambda: _close_descriptor(descriptor))
        actions.append(lambda: _close_descriptor(parent_fd))
        cleanup_error = _drain_cleanup(actions)
        if cleanup_error is not None:
            cleanup_errors.append(cleanup_error)
        for cleanup_failure in cleanup_errors:
            try:
                exc.add_note(
                    f"DLP receipt staging cleanup failure: "
                    f"{type(cleanup_failure).__name__}"
                )
            except (AttributeError, TypeError):
                pass
        raise


def _same_canonical_json(left: object, right: object) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def _role_file_map(inventory: Mapping[str, object], label: str) -> dict[str, str]:
    raw = inventory.get("files")
    if not isinstance(raw, list) or not raw:
        raise DLPError(f"{label} role inventory must be non-empty")
    result: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise DLPError(f"{label} role inventory record is malformed")
        path = _canonical_inventory_relative(item.get("path"))
        digest = item.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise DLPError(f"{label} role inventory hash is invalid")
        if path in result:
            raise DLPError(f"{label} role inventory contains a duplicate")
        result[path] = digest
    return result


def _role_json(root: Path, relative: str) -> dict[str, Any]:
    path = _safe_inventory_path(root, relative)
    value = dict(_strict_json_mapping(path))
    if path.read_bytes() != canonical_json_bytes(value):
        raise DLPError(f"role manifest is not canonical JSON: {relative}")
    return value


def _compact_identity_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _strict_role_json_text(value: object, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise DLPError(f"duplicate JSON key in {label}")
            result[key] = item
        return result

    if not isinstance(value, str):
        raise DLPError(f"{label} must be JSON text")
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                DLPError(f"non-finite JSON value in {label}: {constant}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise DLPError(f"invalid JSON in {label}") from exc
    if not isinstance(parsed, Mapping):
        raise DLPError(f"JSON object required in {label}")
    return parsed


def _stable_role_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest[:40]}"


def _parse_vector_manifest_integer_key(value: object) -> int:
    prefix = "u64:"
    width = 16
    if (
        not isinstance(value, str)
        or len(value) != len(prefix) + width
        or not value.startswith(prefix)
        or any(character not in "0123456789abcdef" for character in value[len(prefix):])
    ):
        raise DLPError("local-vector integer key encoding is invalid")
    return int(value[len(prefix):], 16)


def _stable_vector_integer_key(
    *, data_release_id: str, embedding_identity_sha256: str, kind: str, object_id: str
) -> int:
    payload = json.dumps(
        {
            "data_release_id": data_release_id,
            "embedding_identity_sha256": embedding_identity_sha256,
            "index_kind": kind,
            "object_id": object_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _role_content_type(relative_path: str) -> str:
    if relative_path.startswith("政策法规/"):
        return "regulation"
    if relative_path.startswith("理论题库/"):
        return "question_bank"
    if relative_path.startswith("地面站考题考试条件/"):
        return "exam_condition"
    return "textbook"


def _schema_records(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        )
    ]


def _expected_authority_schema_records() -> list[tuple[Any, ...]]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(AUTHORITY_SCHEMA_SQL)
        return _schema_records(connection)
    finally:
        connection.close()


def _expected_bm25_schema_records() -> list[tuple[Any, ...]]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE chunks_fts USING fts5("
            "text, chunk_id UNINDEXED, doc_name UNINDEXED, tokenize='trigram')"
        )
        return _schema_records(connection)
    finally:
        connection.close()


def _authority_fingerprint(rows: list[dict[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    byte_count = 0
    codepoint_count = 0
    documents: set[str] = set()
    for row in sorted(rows, key=lambda item: str(item["chunk_id"])):
        text = str(row["text"])
        documents.add(str(row["doc_name"]))
        byte_count += len(text.encode("utf-8"))
        codepoint_count += len(text)
        payload = json.dumps(
            [row["chunk_id"], row["doc_name"], row["chunk_index"], text],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(payload)
        digest.update(b"\n")
    return {
        "chunk_count": len(rows),
        "document_count": len(documents),
        "text_byte_count": byte_count,
        "text_codepoint_count": codepoint_count,
        "schema_version": "chunks-v1",
        "fingerprint_algorithm": "sha256-jsonl-chunk-content-v1",
        "fingerprint": digest.hexdigest(),
    }


def _validate_authority_role(
    scope: ApprovedSourceScope,
    root: Path,
    inventory: Mapping[str, object],
    *,
    authority_database_physical_mode: int = 0o600,
) -> dict[str, Any]:
    if (
        type(authority_database_physical_mode) is not int
        or authority_database_physical_mode not in AUTHORITY_DATABASE_PHYSICAL_MODES
    ):
        raise DLPError("authority database physical mode is unsupported")
    files = _role_file_map(inventory, "authority")
    if set(files) != {"authority-manifest.json", "rag_chunks.db"}:
        raise DLPError("authority role file set is not exact")
    manifest = _role_json(root, "authority-manifest.json")
    if set(manifest) != {
        "schema_version",
        "release_id",
        "status",
        "authority",
        "source_scope",
        "database",
        "build",
        "counts",
        "sources",
    }:
        raise DLPError("authority manifest schema is not exact")
    database = manifest.get("database")
    build = manifest.get("build")
    counts = manifest.get("counts")
    sources = manifest.get("sources")
    if (
        manifest.get("schema_version") != "cloud-rag-authority-v1"
        or manifest.get("status") != "candidate"
        or not _same_canonical_json(
            manifest.get("authority"), {"owner": "rag_chunks.db", "join_key": "chunk_id"}
        )
        or not _same_canonical_json(manifest.get("source_scope"), scope.identity())
        or not isinstance(database, Mapping)
        or set(database)
        != {
            "path",
            "sha256",
            "mode",
            "sqlite_user_version",
            "integrity_check",
            "foreign_key_violation_count",
        }
        or database.get("path") != "rag_chunks.db"
        or database.get("mode") != "0600"
        or type(database.get("sqlite_user_version")) is not int
        or database.get("sqlite_user_version") != 1
        or database.get("integrity_check") != "ok"
        or type(database.get("foreign_key_violation_count")) is not int
        or database.get("foreign_key_violation_count") != 0
        or not isinstance(build, Mapping)
        or set(build)
        != {
            "extractor_version",
            "chunking_policy",
            "import_run_id",
            "network_calls",
            "old_authority_reused",
            "ocr_runtime",
        }
        or build.get("extractor_version") != "cloud-v2-source-extractor-v1"
        or build.get("chunking_policy") != CHUNKING_POLICY_VERSION
        or build.get("import_run_id")
        != f"cloud-v2:{scope.identity()['candidate_id']}:{scope.source_manifest_sha256[:16]}"
        or type(build.get("network_calls")) is not int
        or build.get("network_calls") != 0
        or build.get("old_authority_reused") is not False
        or not isinstance(counts, Mapping)
        or set(counts) != {"documents", "chunks", "provenance"}
        or not isinstance(sources, list)
        or not scope.records
    ):
        raise DLPError("authority manifest contract is invalid")
    for key in ("documents", "chunks", "provenance"):
        _strict_nonnegative_integer(counts.get(key), f"authority {key} count")
    ocr_runtime = build.get("ocr_runtime")
    if any(record.relative_path.lower().endswith(".pdf") for record in scope.records):
        if (
            not isinstance(ocr_runtime, Mapping)
            or set(ocr_runtime)
            != {
                "engine",
                "engine_sha256",
                "language_data_sha256",
                "languages",
                "page_segmentation_mode",
                "render_dpi",
            }
            or ocr_runtime.get("engine") != "tesseract"
            or ocr_runtime.get("languages") != "chi_sim+eng"
            or ocr_runtime.get("page_segmentation_mode") != 6
            or ocr_runtime.get("render_dpi") != 170
            or not isinstance(ocr_runtime.get("engine_sha256"), str)
            or not SHA256_PATTERN.fullmatch(str(ocr_runtime.get("engine_sha256")))
            or not isinstance(ocr_runtime.get("language_data_sha256"), Mapping)
            or set(ocr_runtime["language_data_sha256"]) != {"chi_sim", "eng"}
            or any(
                not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest)
                for digest in ocr_runtime["language_data_sha256"].values()
            )
        ):
            raise DLPError("authority OCR runtime identity is invalid")
    elif ocr_runtime is not None:
        raise DLPError("authority unexpectedly declares an OCR runtime")
    database_path = _safe_inventory_path(root, "rag_chunks.db")
    database_sha256 = sha256_file(database_path)
    if (
        database.get("sha256") != database_sha256
        or files["rag_chunks.db"] != database_sha256
        or manifest.get("release_id")
        != f"rag-authority:{scope.identity()['candidate_id']}:{database_sha256[:16]}"
        or stat.S_IMODE(os.lstat(database_path).st_mode)
        != authority_database_physical_mode
    ):
        raise DLPError("authority database identity is invalid")
    expected_sources = [
        (record.relative_path, record.source_sha256, record.byte_disposition)
        for record in scope.records
    ]
    if len(sources) != len(expected_sources):
        raise DLPError("authority source manifest coverage is not exact")
    source_chunk_counts: dict[str, int] = {}
    source_details: dict[str, Mapping[str, Any]] = {}
    for item, (relative, digest, _disposition) in zip(sources, expected_sources):
        if (
            not isinstance(item, Mapping)
            or set(item)
            != {
                "relative_path",
                "source_sha256",
                "extracted_text_sha256",
                "chunk_count",
                "page_count",
            }
            or item.get("relative_path") != relative
            or item.get("source_sha256") != digest
            or not isinstance(item.get("extracted_text_sha256"), str)
            or not SHA256_PATTERN.fullmatch(str(item.get("extracted_text_sha256")))
            or type(item.get("chunk_count")) is not int
            or int(item.get("chunk_count")) <= 0
            or type(item.get("page_count")) is not int
            or int(item.get("page_count")) < 0
        ):
            raise DLPError("authority source manifest differs from the approved scope")
        source_chunk_counts[relative] = int(item["chunk_count"])
        source_details[relative] = item

    for suffix in ("-journal", "-shm", "-wal"):
        if os.path.lexists(Path(str(database_path) + suffix)):
            raise DLPError("authority database has an unsealed sidecar")
    try:
        connection = sqlite3.connect(
            database_path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DLPError("authority database failed integrity_check")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise DLPError("authority database failed foreign_key_check")
        if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise DLPError("authority database user_version mismatch")
        if _schema_records(connection) != _expected_authority_schema_records():
            raise DLPError("authority database schema is not exact")

        source_rows = connection.execute(
            "SELECT document_source_id, doc_name, source_path, source_sha256, "
            "source_page_count, authority, published_at, ocr_engine, ocr_version, "
            "ocr_backend, ocr_language, extractor_version, import_run_id, metadata_json, "
            "created_at, updated_at FROM document_sources ORDER BY doc_name"
        ).fetchall()
        expected_by_path = {
            relative: (digest, disposition)
            for relative, digest, disposition in expected_sources
        }
        source_ids: dict[str, str] = {}
        for row in source_rows:
            relative = str(row["doc_name"])
            if relative not in expected_by_path:
                raise DLPError("authority contains an out-of-scope document name")
            digest, disposition = expected_by_path[relative]
            expected_metadata = {
                "byte_disposition": disposition,
                "chunking_policy": "cloud-v2-paragraph-1200-v1",
                "source_relative_path_sha256": hashlib.sha256(
                    relative.encode("utf-8")
                ).hexdigest(),
            }
            metadata = _strict_role_json_text(
                row["metadata_json"], "authority source metadata"
            )
            if (
                row["document_source_id"]
                != _stable_role_id("docsrc", relative, digest)
                or row["source_path"]
                != "kb://knowledge_base/" + quote(relative, safe="/")
                or row["source_sha256"] != digest
                or row["source_page_count"] != source_details[relative]["page_count"]
                or row["authority"] != "rag_chunks.db"
                or any(
                    row[key] is not None
                    for key in (
                        "published_at",
                        "ocr_engine",
                        "ocr_version",
                        "ocr_backend",
                        "ocr_language",
                    )
                )
                or not str(row["extractor_version"]).startswith(
                    str(build["extractor_version"]) + ":"
                )
                or row["import_run_id"] != build.get("import_run_id")
                or row["created_at"] != scope.approval_recorded_at
                or row["updated_at"] != scope.approval_recorded_at
                or metadata != expected_metadata
            ):
                raise DLPError("authority source row differs from the approved scope")
            source_ids[relative] = str(row["document_source_id"])
        if set(source_ids) != set(expected_by_path):
            raise DLPError("authority source rows are incomplete")

        document_rows = connection.execute(
            "SELECT doc_name, doc_path, chunk_count, updated_at "
            "FROM documents ORDER BY doc_name"
        ).fetchall()
        documents = {str(row["doc_name"]): int(row["chunk_count"]) for row in document_rows}
        if documents != source_chunk_counts or any(
            row["doc_path"] != "kb://knowledge_base/" + quote(str(row["doc_name"]), safe="/")
            or row["updated_at"] != scope.approval_recorded_at
            for row in document_rows
        ):
            raise DLPError("authority document rows differ from the approved scope")
        chunks = [
            dict(row)
            for row in connection.execute(
                "SELECT c.chunk_id, c.text, c.doc_name, c.chunk_index, "
                "c.created_at AS chunk_created_at, p.document_source_id, "
                "p.source_sha256, p.import_run_id, p.pdf_page_start, p.pdf_page_end, "
                "p.printed_page_start, p.printed_page_end, p.chapter_id, "
                "p.chapter_title, p.section_id, p.section_title, p.content_type, "
                "p.confidence, p.review_status, p.evidence_json, "
                "p.created_at AS provenance_created_at, d.extractor_version "
                "FROM chunks c JOIN chunk_provenance p ON p.chunk_id=c.chunk_id "
                "JOIN document_sources d ON d.document_source_id=p.document_source_id "
                "ORDER BY c.doc_name, c.chunk_index"
            )
        ]
        raw_chunk_count = int(
            connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        )
        raw_provenance_count = int(
            connection.execute("SELECT COUNT(*) FROM chunk_provenance").fetchone()[0]
        )
        if raw_chunk_count != len(chunks) or raw_provenance_count != len(chunks):
            raise DLPError("authority chunk/provenance join closure is incomplete")
        if not chunks or any(
            row["doc_name"] not in expected_by_path
            or not isinstance(row["text"], str)
            or not row["text"].strip()
            for row in chunks
        ):
            raise DLPError("authority chunks contain out-of-scope or empty data")
        per_document: dict[str, list[int]] = {}
        extracted_digests: dict[str, Any] = {}
        for row in chunks:
            doc_name = str(row["doc_name"])
            chunk_index = int(row["chunk_index"])
            per_document.setdefault(doc_name, []).append(chunk_index)
            digest = extracted_digests.setdefault(doc_name, hashlib.sha256())
            digest.update(str(row["text"]).encode("utf-8"))
            digest.update(b"\x00")
            evidence = _strict_role_json_text(
                row["evidence_json"], "authority chunk evidence"
            )
            expected_evidence = {
                "extractor": row["extractor_version"],
                "source_text_sha256": source_details[doc_name][
                    "extracted_text_sha256"
                ],
                "unit_ordinal": chunk_index,
            }
            if (
                row["chunk_id"]
                != _stable_role_id(
                    "chunk",
                    str(expected_by_path[doc_name][0]),
                    str(chunk_index),
                    str(row["text"]),
                )
                or row["document_source_id"] != source_ids[doc_name]
                or row["source_sha256"] != expected_by_path[doc_name][0]
                or row["import_run_id"] != build.get("import_run_id")
                or type(row["pdf_page_start"]) is not int
                or type(row["pdf_page_end"]) is not int
                or int(row["pdf_page_start"]) <= 0
                or int(row["pdf_page_end"]) < int(row["pdf_page_start"])
                or int(row["pdf_page_end"])
                > int(source_details[doc_name]["page_count"])
                or any(
                    row[key] is not None
                    for key in (
                        "printed_page_start",
                        "printed_page_end",
                        "chapter_id",
                        "chapter_title",
                        "section_id",
                    )
                )
                or (
                    str(row["extractor_version"]).endswith(":docx-xml")
                    and (
                        not isinstance(row["section_title"], str)
                        or not re.fullmatch(
                            r"word/(?:document|footnotes|endnotes|comments|header\d+|footer\d+)\.xml",
                            row["section_title"],
                        )
                    )
                )
                or (
                    not str(row["extractor_version"]).endswith(":docx-xml")
                    and row["section_title"] not in {"pdf", "pdf_ocr"}
                )
                or row["content_type"] != _role_content_type(doc_name)
                or row["confidence"] != 1.0
                or row["review_status"] != "approved-source-extracted"
                or row["chunk_created_at"] != scope.approval_recorded_at
                or row["provenance_created_at"] != scope.approval_recorded_at
                or not _same_canonical_json(evidence, expected_evidence)
            ):
                raise DLPError("authority chunk provenance is not exactly source-bound")
        if any(indexes != list(range(len(indexes))) for indexes in per_document.values()):
            raise DLPError("authority chunk indexes are not contiguous")
        if (
            {path: len(indexes) for path, indexes in per_document.items()}
            != source_chunk_counts
            or any(
            extracted_digests[path].hexdigest()
            != source_details[path]["extracted_text_sha256"]
            for path in expected_by_path
            )
        ):
            raise DLPError("authority extracted text identity differs from its manifest")
    except sqlite3.Error as exc:
        raise DLPError("authority role SQLite validation failed") from exc
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass
    actual_counts = {
        "documents": len(documents),
        "chunks": raw_chunk_count,
        "provenance": raw_provenance_count,
    }
    if not _same_canonical_json(counts, actual_counts) or sum(
        source_chunk_counts.values()
    ) != len(chunks):
        raise DLPError("authority manifest counts differ from SQLite")
    return {
        "manifest": manifest,
        "manifest_sha256": files["authority-manifest.json"],
        "database_sha256": database_sha256,
        "release_id": manifest["release_id"],
        "chunks": chunks,
        "chunk_ids": {str(row["chunk_id"]) for row in chunks},
        "documents": set(expected_by_path),
        "fingerprint": _authority_fingerprint(chunks),
    }


def _graph_document_id(doc_name: str) -> str:
    return "document:" + hashlib.sha256(doc_name.encode("utf-8")).hexdigest()[:40]


def _validate_fake_embedding_role(
    fake: Mapping[str, Any], *, chunk_count: int, entity_count: int
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    expected_identity = {
        "api_version": "v1",
        "base_url": "https://fake.invalid/v1/embeddings",
        "dimension": 32,
        "input_type": "document-or-query",
        "model": "sha256-fixture",
        "model_version": "whole-text-char-1-2gram-v2",
        "normalization": "l2",
        "provider": "fake-offline",
        "region": "offline",
    }
    expected_policy = {
        "batch_size": 64,
        "local_meter_execution_contract": "trusted-local-terminating-v1",
        "max_cost_microunits_per_request": 0,
        "max_input_units": 4096,
        "max_request_bytes": 8 * 1024 * 1024,
        "max_requests_per_operation": 10000,
        "max_response_bytes": 8 * 1024 * 1024,
        "max_retries": 0,
        "timeout_seconds": 2.0,
        "total_cost_budget_microunits": 0,
        "transport_control_version": (
            "spawn-kill-external-process-or-sealed-offline-fake-cooperative-v3"
        ),
    }
    if (
        set(fake)
        != {
            "schema_version",
            "status",
            "policy_version",
            "identity",
            "identity_sha256",
            "policy",
            "policy_sha256",
            "network_implementation",
            "real_data_externalized",
            "transport_call_count",
            "chunk_ledger",
            "entity_ledger",
        }
        or fake.get("schema_version") != "cloud-v2-fake-embedding-manifest-v1"
        or fake.get("status") != "offline-test-only"
        or fake.get("policy_version") != "cloud-v2-fake-provider-v1"
        or not _same_canonical_json(fake.get("identity"), expected_identity)
        or fake.get("identity_sha256")
        != _compact_identity_sha256(expected_identity)
        or not _same_canonical_json(fake.get("policy"), expected_policy)
        or fake.get("policy_sha256") != _compact_identity_sha256(expected_policy)
        or fake.get("network_implementation") is not False
        or fake.get("real_data_externalized") is not False
    ):
        raise DLPError("fake embedding manifest is not offline-safe")

    call_total = 0
    identity_sha256 = str(fake["identity_sha256"])
    for label, purpose, vector_count in (
        ("chunk_ledger", "build", chunk_count),
        ("entity_ledger", "entity", entity_count),
    ):
        ledger = fake.get(label)
        if (
            not isinstance(ledger, Mapping)
            or set(ledger) != {"purpose", "identity_sha256", "vector_count", "calls"}
            or ledger.get("purpose") != purpose
            or ledger.get("identity_sha256") != identity_sha256
            or ledger.get("vector_count") != vector_count
            or not isinstance(ledger.get("calls"), list)
        ):
            raise DLPError("fake embedding ledger schema or identity is invalid")
        calls = ledger["calls"]
        expected_call_count = (vector_count + int(expected_policy["batch_size"]) - 1) // int(
            expected_policy["batch_size"]
        )
        if len(calls) != expected_call_count:
            raise DLPError("fake embedding ledger call count is incomplete")
        for batch_index, call in enumerate(calls):
            if (
                not isinstance(call, Mapping)
                or set(call)
                != {
                    "batch_index",
                    "attempt",
                    "status",
                    "request_sha256",
                    "response_sha256",
                    "accounted_cost_microunits",
                }
                or call.get("batch_index") != batch_index
                or call.get("attempt") != 1
                or call.get("status") != "succeeded"
                or call.get("accounted_cost_microunits") != 0
                or any(
                    not isinstance(call.get(key), str)
                    or not SHA256_PATTERN.fullmatch(str(call.get(key)))
                    for key in ("request_sha256", "response_sha256")
                )
            ):
                raise DLPError("fake embedding ledger call is invalid")
        call_total += len(calls)
    if fake.get("transport_call_count") != call_total:
        raise DLPError("fake embedding transport count differs from its ledgers")
    return expected_identity, expected_policy


def _validate_derived_role(
    root: Path,
    inventory: Mapping[str, object],
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    files = _role_file_map(inventory, "derived")
    vector_manifests = [
        path
        for path in files
        if path.startswith("local-vector/candidate/")
        and path.endswith("/local_vector_manifest.json")
    ]
    if len(vector_manifests) != 1:
        raise DLPError("derived role must contain exactly one vector release")
    vector_manifest_relative = vector_manifests[0]
    vector_release_root = PurePosixPath(vector_manifest_relative).parent.as_posix()
    expected_files = {
        "derived-candidate-manifest.json",
        "bm25-manifest.json",
        "bm25.sqlite3",
        "fake-embedding-manifest.json",
        "graph/graph-manifest.json",
        "graph/scoped-graph.jsonl",
        vector_manifest_relative,
        f"{vector_release_root}/chunk-index/index.usearch",
        f"{vector_release_root}/entity-index/index.usearch",
    }
    if set(files) != expected_files:
        raise DLPError("derived role file set is not exact")
    derived = _role_json(root, "derived-candidate-manifest.json")
    bm25 = _role_json(root, "bm25-manifest.json")
    fake = _role_json(root, "fake-embedding-manifest.json")
    graph = _role_json(root, "graph/graph-manifest.json")
    vector = _role_json(root, vector_manifest_relative)
    authority_sha = authority["database_sha256"]
    authority_release = authority["release_id"]
    if (
        set(bm25)
        != {
            "schema_version",
            "status",
            "authority_release_id",
            "authority_database_sha256",
            "source",
            "index",
            "indexed_chunk_count",
            "tokenizer",
            "minimum_effective_query_codepoints",
            "short_query_fallback",
            "sqlite_backfill_required",
        }
        or bm25.get("schema_version") != "cloud-v2-sqlite-fts5-trigram-v1"
        or bm25.get("status") != "candidate"
        or bm25.get("authority_database_sha256") != authority_sha
        or bm25.get("authority_release_id") != authority_release
        or not _same_canonical_json(bm25.get("source"), authority["fingerprint"])
        or type(bm25.get("indexed_chunk_count")) is not int
        or bm25.get("indexed_chunk_count") != len(authority["chunks"])
        or bm25.get("tokenizer") != "trigram"
        or bm25.get("minimum_effective_query_codepoints") != 3
        or bm25.get("short_query_fallback") != "authority-sqlite-substring-v1"
        or bm25.get("sqlite_backfill_required") is not True
        or not isinstance(bm25.get("index"), Mapping)
        or set(bm25["index"]) != {"path", "sha256"}
        or bm25["index"].get("path") != "bm25.sqlite3"
        or bm25["index"].get("sha256") != files["bm25.sqlite3"]
    ):
        raise DLPError("BM25 manifest is not exactly authority-bound")
    bm25_path = _safe_inventory_path(root, "bm25.sqlite3")
    for suffix in ("-journal", "-shm", "-wal"):
        if os.path.lexists(Path(str(bm25_path) + suffix)):
            raise DLPError("BM25 database has an unsealed sidecar")
    try:
        connection = sqlite3.connect(
            bm25_path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DLPError("BM25 database failed integrity_check")
        if _schema_records(connection) != _expected_bm25_schema_records():
            raise DLPError("BM25 database schema is not exact")
        indexed_rows = [
            (str(row["chunk_id"]), str(row["doc_name"]), str(row["text"]))
            for row in connection.execute(
                "SELECT chunk_id, doc_name, text FROM chunks_fts ORDER BY rowid"
            )
        ]
    except sqlite3.Error as exc:
        raise DLPError("BM25 role SQLite validation failed") from exc
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass
    expected_indexed = {
        (str(row["chunk_id"]), str(row["doc_name"]), str(row["text"]))
        for row in authority["chunks"]
    }
    indexed = set(indexed_rows)
    if len(indexed_rows) != len(expected_indexed) or indexed != expected_indexed:
        raise DLPError("BM25 row set differs from SQLite authority")

    graph_data_path = _safe_inventory_path(root, "graph/scoped-graph.jsonl")
    if (
        set(graph)
        != {
            "schema_version",
            "release_id",
            "status",
            "authority_release_id",
            "authority_database_sha256",
            "graph",
            "counts",
            "binding",
            "neo4j",
            "entities",
        }
        or graph.get("schema_version") != "cloud-scoped-graph-v1"
        or graph.get("status") != "candidate"
        or graph.get("authority_database_sha256") != authority_sha
        or graph.get("authority_release_id") != authority_release
        or not isinstance(graph.get("graph"), Mapping)
        or graph["graph"]
        != {"path": "scoped-graph.jsonl", "sha256": files["graph/scoped-graph.jsonl"]}
        or graph.get("release_id")
        != "graph:"
        + str(authority_release).split(":", 1)[-1]
        + ":"
        + files["graph/scoped-graph.jsonl"][:16]
        or graph.get("neo4j")
        != {
            "import_schema_version": "cloud-scoped-neo4j-import-v1",
            "driver": "neo4j",
            "driver_version": "6.2.0",
            "node_labels": ["ChunkRef", "Document", "Entity"],
            "relationship_types": ["HAS_CHUNK", "MENTIONS"],
            "release_property": "graph_release_id",
            "runtime_access": "read_only",
        }
        or not isinstance(graph.get("entities"), list)
    ):
        raise DLPError("graph manifest is not exactly authority-bound")
    records: list[dict[str, Any]] = []
    for line in graph_data_path.read_bytes().splitlines(keepends=True):
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DLPError("graph data is not UTF-8 JSONL") from exc
        if not isinstance(record, dict) or line != (
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8"):
            raise DLPError("graph data is not canonical JSONL")
        records.append(record)
    document_nodes: dict[str, str] = {}
    chunk_nodes: dict[str, str] = {}
    entity_nodes: dict[str, tuple[str, str]] = {}
    edges: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") == "node" and record.get("label") == "Document":
            if set(record) != {"kind", "label", "node_id", "properties"}:
                raise DLPError("graph document node schema is invalid")
            properties = record.get("properties")
            if not isinstance(properties, Mapping) or set(properties) != {
                "doc_name",
                "authority_release_id",
            }:
                raise DLPError("graph document node schema is invalid")
            doc_name = str(properties["doc_name"])
            if (
                doc_name not in authority["documents"]
                or properties["authority_release_id"] != authority_release
                or record.get("node_id") != _graph_document_id(doc_name)
            ):
                raise DLPError("graph contains an out-of-scope document")
            node_id = str(record["node_id"])
            if node_id in document_nodes:
                raise DLPError("graph contains a duplicate document node")
            document_nodes[node_id] = doc_name
        elif record.get("kind") == "node" and record.get("label") == "ChunkRef":
            if set(record) != {"kind", "label", "node_id", "properties"}:
                raise DLPError("graph chunk node schema is invalid")
            properties = record.get("properties")
            if not isinstance(properties, Mapping) or set(properties) != {
                "chunk_id",
                "authority_release_id",
            }:
                raise DLPError("graph chunk node schema is invalid")
            chunk_id = str(properties["chunk_id"])
            node_id = "chunkref:" + chunk_id.removeprefix("chunk:")
            if (
                chunk_id not in authority["chunk_ids"]
                or properties["authority_release_id"] != authority_release
                or record.get("node_id") != node_id
            ):
                raise DLPError("graph contains an unknown chunk reference")
            if node_id in chunk_nodes:
                raise DLPError("graph contains a duplicate chunk node")
            chunk_nodes[node_id] = chunk_id
        elif record.get("kind") == "node" and record.get("label") == "Entity":
            if set(record) != {"kind", "label", "node_id", "properties"}:
                raise DLPError("graph entity node schema is invalid")
            properties = record.get("properties")
            if not isinstance(properties, Mapping) or set(properties) != {
                "canonical_name",
                "entity_type",
                "authority_release_id",
            } or properties["authority_release_id"] != authority_release:
                raise DLPError("graph entity node schema is invalid")
            canonical_name = str(properties["canonical_name"])
            entity_type = str(properties["entity_type"])
            node_id = str(record["node_id"])
            if (
                node_id != _stable_role_id("entity", entity_type, canonical_name)
                or node_id in entity_nodes
            ):
                raise DLPError("graph entity node identity is invalid or duplicate")
            entity_nodes[node_id] = (canonical_name, entity_type)
        elif record.get("kind") == "edge":
            edges.append(record)
        else:
            raise DLPError("graph contains an unapproved record kind")
    chunk_doc = {str(row["chunk_id"]): str(row["doc_name"]) for row in authority["chunks"]}
    expected_has_chunk = {
        (
            _graph_document_id(doc_name),
            "chunkref:" + chunk_id.removeprefix("chunk:"),
            chunk_id,
        )
        for chunk_id, doc_name in chunk_doc.items()
    }
    expected_entity_evidence: dict[tuple[str, str], set[str]] = {}
    for row in authority["chunks"]:
        text = str(row["text"])
        for name, entity_type in ENTITY_LEXICON:
            if name.casefold() in text.casefold():
                expected_entity_evidence.setdefault((name, entity_type), set()).add(
                    str(row["chunk_id"])
                )
    if not expected_entity_evidence:
        raise DLPError("graph entity extraction has no authority evidence")
    expected_entity_records = [
        {
            "entity_id": _stable_role_id("entity", entity_type, name),
            "canonical_name": name,
            "entity_type": entity_type,
            "evidence_chunk_ids": sorted(evidence_ids),
        }
        for (name, entity_type), evidence_ids in sorted(
            expected_entity_evidence.items()
        )
    ]
    expected_manifest_entities = {
        str(record["entity_id"]): (
            str(record["canonical_name"]),
            str(record["entity_type"]),
            tuple(str(item) for item in record["evidence_chunk_ids"]),
        )
        for record in expected_entity_records
    }
    manifest_entities: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for entity in graph["entities"]:
        if not isinstance(entity, Mapping) or set(entity) != {
            "entity_id",
            "canonical_name",
            "entity_type",
            "evidence_chunk_ids",
        }:
            raise DLPError("graph entity manifest schema is invalid")
        evidence_ids = entity["evidence_chunk_ids"]
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or evidence_ids != sorted(set(evidence_ids))
            or not set(evidence_ids) <= authority["chunk_ids"]
        ):
            raise DLPError("graph entity evidence is not authority-bound")
        entity_id = str(entity["entity_id"])
        if entity_id in manifest_entities:
            raise DLPError("graph entity manifest contains a duplicate")
        manifest_entities[entity_id] = (
            str(entity["canonical_name"]),
            str(entity["entity_type"]),
            tuple(str(item) for item in evidence_ids),
        )
    if (
        graph["entities"] != expected_entity_records
        or manifest_entities != expected_manifest_entities
        or set(document_nodes.values()) != authority["documents"]
        or set(chunk_nodes.values()) != authority["chunk_ids"]
        or {key: value[:2] for key, value in manifest_entities.items()}
        != entity_nodes
    ):
        raise DLPError("graph node closure differs from authority or manifest")
    actual_has_chunk: set[tuple[str, str, str]] = set()
    actual_mentions: set[tuple[str, str, str]] = set()
    for edge in edges:
        if (
            set(edge) != {"kind", "type", "from", "to", "evidence_chunk_ids"}
            or edge.get("kind") != "edge"
        ):
            raise DLPError("graph edge schema is invalid")
        evidence_ids = edge["evidence_chunk_ids"]
        if not isinstance(evidence_ids, list) or len(evidence_ids) != 1:
            raise DLPError("graph edge evidence is not singular")
        chunk_id = str(evidence_ids[0])
        if chunk_id not in authority["chunk_ids"]:
            raise DLPError("graph edge references an unknown authority chunk")
        if edge["type"] == "HAS_CHUNK":
            actual_has_chunk.add((str(edge["from"]), str(edge["to"]), chunk_id))
        elif edge["type"] == "MENTIONS":
            actual_mentions.add((str(edge["from"]), str(edge["to"]), chunk_id))
        else:
            raise DLPError("graph contains an unapproved relationship type")
    expected_mentions = {
        ("chunkref:" + chunk_id.removeprefix("chunk:"), entity_id, chunk_id)
        for entity_id, (_name, _kind, evidence_ids) in manifest_entities.items()
        for chunk_id in evidence_ids
    }
    expected_records: list[dict[str, Any]] = []
    for doc_name in sorted(authority["documents"]):
        expected_records.append(
            {
                "kind": "node",
                "label": "Document",
                "node_id": _graph_document_id(doc_name),
                "properties": {
                    "doc_name": doc_name,
                    "authority_release_id": authority_release,
                },
            }
        )
    for row in authority["chunks"]:
        chunk_id = str(row["chunk_id"])
        chunk_node_id = "chunkref:" + chunk_id.removeprefix("chunk:")
        expected_records.extend(
            (
                {
                    "kind": "node",
                    "label": "ChunkRef",
                    "node_id": chunk_node_id,
                    "properties": {
                        "chunk_id": chunk_id,
                        "authority_release_id": authority_release,
                    },
                },
                {
                    "kind": "edge",
                    "type": "HAS_CHUNK",
                    "from": _graph_document_id(str(row["doc_name"])),
                    "to": chunk_node_id,
                    "evidence_chunk_ids": [chunk_id],
                },
            )
        )
    for entity in expected_entity_records:
        expected_records.append(
            {
                "kind": "node",
                "label": "Entity",
                "node_id": entity["entity_id"],
                "properties": {
                    "canonical_name": entity["canonical_name"],
                    "entity_type": entity["entity_type"],
                    "authority_release_id": authority_release,
                },
            }
        )
        expected_records.extend(
            {
                "kind": "edge",
                "type": "MENTIONS",
                "from": "chunkref:" + chunk_id.removeprefix("chunk:"),
                "to": entity["entity_id"],
                "evidence_chunk_ids": [chunk_id],
            }
            for chunk_id in entity["evidence_chunk_ids"]
        )
    if (
        len(actual_has_chunk) + len(actual_mentions) != len(edges)
        or actual_has_chunk != expected_has_chunk
        or actual_mentions != expected_mentions
        or records != expected_records
    ):
        raise DLPError("graph record order or edge closure differs from authority evidence")
    expected_counts = {
        "document_nodes": len(document_nodes),
        "chunk_nodes": len(chunk_nodes),
        "entity_nodes": len(entity_nodes),
        "edges": len(edges),
    }
    expected_binding = {
        "text_edge_count": len(edges),
        "unresolved_sqlite_chunk_id_count": 0,
        "authoritative_text_stored_in_graph": False,
    }
    if not _same_canonical_json(
        graph.get("counts"), expected_counts
    ) or not _same_canonical_json(graph.get("binding"), expected_binding):
        raise DLPError("graph manifest counts or binding are stale")
    if len(records) != sum(expected_counts.values()):
        raise DLPError("graph record count differs from its exact node/edge closure")

    fake_identity, _fake_policy = _validate_fake_embedding_role(
        fake,
        chunk_count=len(authority["chunk_ids"]),
        entity_count=len(entity_nodes),
    )
    try:
        from .candidate_builder import (
            _fake_embedding_adapter,
            _ledger_summary,
            local_data_release_id,
        )
        from deploy.rag_store.embedding_adapter import EmbeddingInput

        embedding, transport = _fake_embedding_adapter()
        expected_chunk_result = embedding.embed_build(
            [
                EmbeddingInput(
                    str(row["chunk_id"]),
                    str(row["text"]),
                    len(str(row["text"])),
                )
                for row in authority["chunks"]
            ]
        )
        expected_entity_result = embedding.embed_entity(
            [
                EmbeddingInput(
                    str(entity["entity_id"]),
                    str(entity["canonical_name"]),
                    len(str(entity["canonical_name"])),
                )
                for entity in expected_entity_records
            ]
        )
        expected_data_release_id = local_data_release_id(
            authority_sha, str(fake["identity_sha256"])
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        raise DLPError("fake embedding replay validation is unavailable") from exc
    if (
        fake.get("chunk_ledger") != _ledger_summary(expected_chunk_result)
        or fake.get("entity_ledger") != _ledger_summary(expected_entity_result)
        or fake.get("transport_call_count") != transport.call_count
    ):
        raise DLPError("fake embedding ledgers differ from deterministic replay")
    expected_vectors = {
        "chunk": expected_chunk_result.by_id(),
        "entity": expected_entity_result.by_id(),
    }
    authority_build = authority["manifest"]["build"]
    expected_chunking_identity_sha256 = _compact_identity_sha256(
        {
            "chunking_policy": authority_build["chunking_policy"],
            "extractor_version": authority_build["extractor_version"],
        }
    )
    data_release_id = PurePosixPath(vector_release_root).name
    expected_vector_identity = {
        "authority_manifest_sha256": authority["manifest_sha256"],
        "chunking_identity_sha256": expected_chunking_identity_sha256,
        "data_release_id": data_release_id,
        "dimension": fake_identity["dimension"],
        "dtype": "f32",
        "embedding_identity_sha256": fake["identity_sha256"],
        "engine": "usearch",
        "engine_metric": "cos",
        "engine_version": "2.26.2",
        "index_names": {"chunk": "chunk-index", "entity": "entity-index"},
        "index_build_threads": 1,
        "max_vectors_per_index": max(
            100000, len(authority["chunk_ids"]) + len(entity_nodes)
        ),
        "metadata_allowlist": {
            "chunk": ["authority_release_id", "content_type"],
            "entity": ["authority_release_id", "entity_type"],
        },
        "metric": "cosine",
        "schema_version": "kg-local-vector-schema-v1",
        "top_k_max": 50,
    }
    if (
        vector.get("manifest_schema_version") != "kg-local-vector-manifest-v2"
        or set(vector) != {"manifest_schema_version", "identity", "indexes"}
        or not isinstance(vector.get("identity"), Mapping)
        or not isinstance(vector.get("indexes"), Mapping)
        or set(vector["indexes"]) != {"chunk", "entity"}
    ):
        raise DLPError("local-vector manifest schema is invalid")
    identity = vector["identity"]
    if (
        not _same_canonical_json(identity, expected_vector_identity)
        or data_release_id != expected_data_release_id
    ):
        raise DLPError("local-vector identity is not authority-bound")
    authority_content_types = {
        str(row["chunk_id"]): str(row["content_type"]) for row in authority["chunks"]
    }
    entity_types = {key: value[1] for key, value in entity_nodes.items()}
    for kind, expected_ids, metadata_values in (
        ("chunk", authority["chunk_ids"], authority_content_types),
        ("entity", set(entity_nodes), entity_types),
    ):
        index = vector["indexes"][kind]
        expected_file = f"{kind}-index/index.usearch"
        file_relative = f"{vector_release_root}/{expected_file}"
        if (
            not isinstance(index, Mapping)
            or set(index)
            != {"file", "index_name", "index_sha256", "object_count", "objects"}
            or index.get("file") != expected_file
            or index.get("index_name") != f"{kind}-index"
            or index.get("index_sha256") != files[file_relative]
            or not isinstance(index.get("objects"), list)
            or type(index.get("object_count")) is not int
            or index.get("object_count") != len(index["objects"])
            or index.get("object_count") != len(expected_ids)
        ):
            raise DLPError("local-vector index identity is invalid")
        object_ids: set[str] = set()
        integer_keys: set[int] = set()
        metadata_key = "content_type" if kind == "chunk" else "entity_type"
        for item_index, item in enumerate(index["objects"]):
            if not isinstance(item, Mapping) or set(item) != {
                "object_id",
                "integer_key",
                "metadata",
            }:
                raise DLPError("local-vector object schema is invalid")
            object_id = str(item["object_id"])
            integer_key = _parse_vector_manifest_integer_key(item["integer_key"])
            metadata = item["metadata"]
            if (
                object_id not in expected_ids
                or integer_key
                != _stable_vector_integer_key(
                    data_release_id=data_release_id,
                    embedding_identity_sha256=str(fake["identity_sha256"]),
                    kind=kind,
                    object_id=object_id,
                )
                or (item_index > 0 and object_id <= index["objects"][item_index - 1]["object_id"])
                or not isinstance(metadata, Mapping)
                or metadata
                != {
                    "authority_release_id": authority_release,
                    metadata_key: metadata_values[object_id],
                }
            ):
                raise DLPError("local-vector object is not authority-bound")
            object_ids.add(object_id)
            integer_keys.add(integer_key)
        if object_ids != expected_ids or len(integer_keys) != len(expected_ids):
            raise DLPError("local-vector object closure is incomplete")
        index_path = _safe_inventory_path(root, file_relative)
        try:
            import numpy as np
            from usearch.index import Index

            metadata = Index.metadata(index_path)
            restored = Index.restore(index_path, view=True)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise DLPError("USEarch binary validation is unavailable") from exc
        if (
            restored is None
            or len(restored) != len(expected_ids)
            or {int(key) for key in restored.keys} != integer_keys
            or not metadata
            or str(metadata.get("version")) != "2.26.2"
            or int(metadata.get("dimensions", -1)) != int(fake_identity["dimension"])
            or int(metadata.get("count_present", -1)) != len(expected_ids)
            or int(metadata.get("count_deleted", -1)) != 0
            or str(metadata.get("kind_metric")) != "MetricKind.Cos"
            or str(metadata.get("kind_scalar")) != "ScalarKind.F32"
        ):
            raise DLPError("USEarch binary differs from its frozen manifest")
        ordered_keys = np.asarray(
            [_parse_vector_manifest_integer_key(item["integer_key"]) for item in index["objects"]],
            dtype=np.uint64,
        )
        try:
            raw_stored_vectors = restored.get(ordered_keys, dtype="f32")
            if raw_stored_vectors is None or (
                isinstance(raw_stored_vectors, (list, tuple))
                and any(row is None for row in raw_stored_vectors)
            ):
                raise ValueError("USEarch returned a missing vector row")
            stored_vectors = np.asarray(raw_stored_vectors, dtype=np.float32)
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            raise DLPError("USEarch vectors cannot be replayed") from exc
        replayed_vectors = np.asarray(
            [expected_vectors[kind][str(item["object_id"])] for item in index["objects"]],
            dtype=np.float32,
        )
        if stored_vectors.shape != replayed_vectors.shape or not np.allclose(
            stored_vectors,
            replayed_vectors,
            rtol=0.0,
            atol=1e-6,
        ):
            raise DLPError("USEarch vectors differ from deterministic fake replay")
    expected_gates = {
        "sqlite_chunk_backfill_missing": 0,
        "graph_entity_backfill_missing": 0,
        "unknown_vector_id_count": 0,
        "cross_release_id_count": 0,
        "network_call_count": 0,
    }
    local_vector = derived.get("local_vector")
    if (
        set(derived)
        != {
            "schema_version",
            "status",
            "authority_release_id",
            "authority_database_sha256",
            "bm25_manifest_sha256",
            "graph_manifest_sha256",
            "embedding_identity_sha256",
            "embedding_policy_sha256",
            "fake_embedding_manifest_sha256",
            "local_vector",
            "gates",
        }
        or derived.get("schema_version") != "cloud-v2-derived-candidate-v1"
        or derived.get("status") != "candidate"
        or derived.get("authority_release_id") != authority_release
        or derived.get("authority_database_sha256") != authority_sha
        or derived.get("bm25_manifest_sha256") != files["bm25-manifest.json"]
        or derived.get("graph_manifest_sha256") != files["graph/graph-manifest.json"]
        or derived.get("fake_embedding_manifest_sha256")
        != files["fake-embedding-manifest.json"]
        or derived.get("embedding_identity_sha256") != fake.get("identity_sha256")
        or derived.get("embedding_policy_sha256") != fake.get("policy_sha256")
        or not _same_canonical_json(derived.get("gates"), expected_gates)
        or not isinstance(local_vector, Mapping)
        or set(local_vector)
        != {
            "data_release_id",
            "manifest_sha256",
            "authority_manifest_sha256",
            "chunking_identity_sha256",
            "chunk_count",
            "entity_count",
            "engine",
            "engine_version",
        }
        or local_vector.get("manifest_sha256") != files[vector_manifest_relative]
        or local_vector.get("authority_manifest_sha256") != authority["manifest_sha256"]
        or local_vector.get("data_release_id") != identity.get("data_release_id")
        or local_vector.get("chunking_identity_sha256")
        != expected_chunking_identity_sha256
        or type(local_vector.get("chunk_count")) is not int
        or local_vector.get("chunk_count") != len(authority["chunk_ids"])
        or type(local_vector.get("entity_count")) is not int
        or local_vector.get("entity_count") != len(entity_nodes)
        or local_vector.get("engine") != "usearch"
        or local_vector.get("engine_version") != "2.26.2"
        or identity.get("embedding_identity_sha256") != fake.get("identity_sha256")
    ):
        raise DLPError("derived manifest identity chain is invalid")
    return {
        "manifest_sha256": files["derived-candidate-manifest.json"],
        "tree_sha256": inventory["tree_sha256"],
        "bm25_row_set_sha256": _canonical_identity_sha256(sorted(indexed)),
        "graph_record_set_sha256": _canonical_identity_sha256(records),
        "chunk_vector_id_set_sha256": _canonical_identity_sha256(
            sorted(authority["chunk_ids"])
        ),
        "entity_vector_id_set_sha256": _canonical_identity_sha256(sorted(entity_nodes)),
    }


def _validate_role_closure(
    *,
    scope: ApprovedSourceScope,
    authority_root: Path,
    authority_inventory: Mapping[str, object],
    derived_root: Path,
    derived_inventory: Mapping[str, object],
    authority_database_physical_mode: int = 0o600,
) -> dict[str, object]:
    authority = _validate_authority_role(
        scope,
        authority_root,
        authority_inventory,
        authority_database_physical_mode=authority_database_physical_mode,
    )
    derived = _validate_derived_role(derived_root, derived_inventory, authority)
    return {
        "schema_version": ROLE_CLOSURE_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "approved_source_path_set_sha256": _canonical_identity_sha256(
            [record.relative_path for record in scope.records]
        ),
        "approved_source_hash_set_sha256": _canonical_identity_sha256(
            [record.source_sha256 for record in scope.records]
        ),
        "authority_manifest_sha256": authority["manifest_sha256"],
        "authority_database_sha256": authority["database_sha256"],
        "authority_chunk_id_set_sha256": _canonical_identity_sha256(
            sorted(authority["chunk_ids"])
        ),
        "authority_document_set_sha256": _canonical_identity_sha256(
            sorted(authority["documents"])
        ),
        "derived": derived,
        "out_of_scope_document_count": 0,
        "unknown_chunk_reference_count": 0,
        "unknown_vector_id_count": 0,
    }


def _build_phase1_receipt(
    *,
    scope: ApprovedSourceScope,
    authority_root: str | Path,
    derived_root: str | Path,
    code_root: str | Path,
    _pdf_tools: _PDFToolSet,
    authority_database_physical_mode: int = 0o600,
) -> dict[str, object]:
    source_root = _real_directory(scope.source_root, "approved source root")
    governance_root = _real_directory(scope.governance_root, "governance root")
    authority_root = _real_directory(authority_root, "authority root")
    derived_root = _real_directory(derived_root, "derived root")
    implementation = discover_phase1_implementation(code_root)

    source_before = _tree_inventory(source_root)
    _validate_source_inventory(scope, source_before)
    governance_before = _governance_state(scope)
    authority_before = _tree_inventory(authority_root)
    derived_before = _tree_inventory(derived_root)
    implementation_before = _implementation_inventory(implementation)
    upstream_source_dlp = _validate_upstream_source_dlp(scope)
    role_closure = _validate_role_closure(
        scope=scope,
        authority_root=authority_root,
        authority_inventory=authority_before,
        derived_root=derived_root,
        derived_inventory=derived_before,
        authority_database_physical_mode=authority_database_physical_mode,
    )

    scanner = DLPScanner(
        _ocr_approved_container_roots=(
            f"layers/source/files/{index}/payload"
            for index in range(1, int(source_before["file_count"]) + 1)
        ),
        _pdf_tools=_pdf_tools,
    )
    source_findings = _scan_inventory(
        scanner,
        root=source_root,
        inventory=source_before,
        object_prefix="layers/source",
    )
    governance_findings = _scan_inventory(
        scanner,
        root=governance_root,
        inventory=governance_before["top_level"],
        object_prefix="layers/governance",
    )
    authority_findings = _scan_inventory(
        scanner,
        root=authority_root,
        inventory=authority_before,
        object_prefix="layers/authority",
    )
    derived_findings = _scan_inventory(
        scanner,
        root=derived_root,
        inventory=derived_before,
        object_prefix="layers/derived",
    )
    implementation_findings = _scan_inventory(
        scanner,
        root=implementation.root,
        inventory=implementation_before,
        object_prefix="layers/implementation",
    )

    source_after = _tree_inventory(source_root)
    _validate_source_inventory(scope, source_after)
    governance_after = _governance_state(scope)
    authority_after = _tree_inventory(authority_root)
    derived_after = _tree_inventory(derived_root)
    implementation_after_discovery = discover_phase1_implementation(implementation.root)
    implementation_after = _implementation_inventory(implementation_after_discovery)
    before_after = (
        ("source", source_before, source_after),
        ("governance", governance_before, governance_after),
        ("authority", authority_before, authority_after),
        ("derived", derived_before, derived_after),
        ("implementation", implementation_before, implementation_after),
    )
    for label, before, after in before_after:
        if not _same_canonical_json(before, after):
            raise DLPError(f"{label} inventory changed during DLP scan")
    if implementation_after_discovery != implementation:
        raise DLPError("implementation membership changed during DLP scan")

    implementation_scope = _implementation_scope_receipt(
        implementation, implementation_before
    )
    layers = {
        "source": _layer_receipt(source_before, source_findings),
        "governance": _layer_receipt(
            governance_before["top_level"],
            governance_findings,
            accounted_tree_sha256=governance_before["accounted_tree_sha256"],
            excluded_review_evidence=governance_before["review_receipt"],
        ),
        "authority": _layer_receipt(authority_before, authority_findings),
        "derived": _layer_receipt(derived_before, derived_findings),
        "implementation": _layer_receipt(
            implementation_before, implementation_findings
        ),
    }
    canary, canary_ok = _positive_canary_receipt(_pdf_tools)
    real = scanner.summary()
    ok = real["finding_count"] == 0 and canary_ok
    scanner_contract = scanner.scanner_contract()
    return {
        "schema_version": DLP_SCHEMA_VERSION,
        "ruleset_version": DLP_RULESET_VERSION,
        "ruleset_sha256": _ruleset_sha256(),
        "scanner_sha256": _canonical_identity_sha256(scanner_contract),
        "status": "passed" if ok else "failed",
        "ok": ok,
        "source_scope": scope.identity(),
        "upstream_source_ocr_dlp": upstream_source_dlp,
        "role_closure": role_closure,
        "layers": layers,
        "implementation_scope": implementation_scope,
        "real_candidate": real,
        "positive_canary": canary,
        "scanner_contract": scanner_contract,
    }


def _validate_finding_list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise DLPError(f"{label} findings must be a list")
    for finding in value:
        if not isinstance(finding, Mapping) or set(finding) != {
            "object_id",
            "rule_id",
            "value_sha256",
        }:
            raise DLPError(f"{label} contains a malformed finding")
        if not isinstance(finding.get("object_id"), str) or not isinstance(
            finding.get("rule_id"), str
        ):
            raise DLPError(f"{label} contains a malformed finding identity")
        if not isinstance(finding.get("value_sha256"), str) or not SHA256_PATTERN.fullmatch(
            str(finding.get("value_sha256"))
        ):
            raise DLPError(f"{label} contains a malformed finding hash")
    return value


def _validate_inventory_layer(
    value: Any,
    *,
    label: str,
    extra_keys: set[str] | None = None,
) -> None:
    if not isinstance(value, Mapping):
        raise DLPError(f"{label} layer must be an object")
    common_keys = {
        "schema_version",
        "file_count",
        "total_bytes",
        "files",
        "path_set_sha256",
        "hash_set_sha256",
        "tree_sha256",
        "finding_count",
        "findings",
    }
    if set(value) != common_keys | (extra_keys or set()):
        raise DLPError(f"{label} layer schema is incomplete")
    if value.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        raise DLPError(f"{label} inventory schema mismatch")
    file_count = _strict_nonnegative_integer(value.get("file_count"), "file_count")
    _strict_nonnegative_integer(value.get("total_bytes"), "total_bytes")
    files = value.get("files")
    if not isinstance(files, list) or len(files) != file_count:
        raise DLPError(f"{label} inventory count differs from files")
    paths: list[str] = []
    hashes: list[str] = []
    for record in files:
        if not isinstance(record, Mapping) or set(record) != {"path", "sha256"}:
            raise DLPError(f"{label} inventory record is malformed")
        paths.append(_canonical_inventory_relative(record.get("path")))
        digest = record.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise DLPError(f"{label} inventory hash is invalid")
        hashes.append(digest)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise DLPError(f"{label} inventory paths are not unique and sorted")
    expected_identities = {
        "path_set_sha256": _canonical_identity_sha256(paths),
        "hash_set_sha256": _canonical_identity_sha256(hashes),
        "tree_sha256": _canonical_identity_sha256(files),
    }
    if any(value.get(key) != digest for key, digest in expected_identities.items()):
        raise DLPError(f"{label} inventory identity mismatch")
    findings = _validate_finding_list(value.get("findings"), label)
    finding_count = _strict_nonnegative_integer(
        value.get("finding_count"), "finding_count"
    )
    if finding_count != len(findings):
        raise DLPError(f"{label} finding count mismatch")


def _validate_phase1_receipt_structure(
    value: Mapping[str, Any],
    *,
    scanner_contract: Mapping[str, object] | None = None,
) -> None:
    if set(value) != PHASE1_DLP_RECEIPT_FIELDS:
        raise DLPError("Phase 1 DLP receipt schema is incomplete")
    if value.get("schema_version") != DLP_SCHEMA_VERSION:
        raise DLPError("Phase 1 DLP receipt schema mismatch")
    if value.get("ruleset_version") != DLP_RULESET_VERSION:
        raise DLPError("Phase 1 DLP ruleset version mismatch")
    if value.get("ruleset_sha256") != _ruleset_sha256():
        raise DLPError("Phase 1 DLP ruleset identity mismatch")
    active_scanner_contract = dict(scanner_contract or _scanner_contract())
    if not _same_canonical_json(
        value.get("scanner_contract"), active_scanner_contract
    ):
        raise DLPError("Phase 1 DLP scanner contract mismatch")
    if value.get("scanner_sha256") != _canonical_identity_sha256(
        active_scanner_contract
    ):
        raise DLPError("Phase 1 DLP scanner identity mismatch")
    if value.get("ok") is not True or value.get("status") != "passed":
        raise DLPError("Phase 1 DLP receipt is not passing")

    layers = value.get("layers")
    if not isinstance(layers, Mapping) or set(layers) != {
        "source",
        "governance",
        "authority",
        "derived",
        "implementation",
    }:
        raise DLPError("Phase 1 DLP layers are incomplete")
    for label in ("source", "authority", "derived", "implementation"):
        _validate_inventory_layer(layers[label], label=label)
    _validate_inventory_layer(
        layers["governance"],
        label="governance",
        extra_keys={"accounted_tree_sha256", "excluded_review_evidence"},
    )
    for label, layer in layers.items():
        if layer.get("finding_count") != 0 or layer.get("findings") != []:
            raise DLPError(f"Phase 1 DLP {label} layer contains a finding")

    role_closure = value.get("role_closure")
    expected_role_keys = {
        "schema_version",
        "status",
        "ok",
        "approved_source_path_set_sha256",
        "approved_source_hash_set_sha256",
        "authority_manifest_sha256",
        "authority_database_sha256",
        "authority_chunk_id_set_sha256",
        "authority_document_set_sha256",
        "derived",
        "out_of_scope_document_count",
        "unknown_chunk_reference_count",
        "unknown_vector_id_count",
    }
    if not isinstance(role_closure, Mapping) or set(role_closure) != expected_role_keys:
        raise DLPError("Phase 1 role closure schema is incomplete")
    if (
        role_closure.get("schema_version") != ROLE_CLOSURE_SCHEMA_VERSION
        or role_closure.get("status") != "passed"
        or role_closure.get("ok") is not True
    ):
        raise DLPError("Phase 1 role closure is not passing")
    role_hash_keys = expected_role_keys - {
        "schema_version",
        "status",
        "ok",
        "derived",
        "out_of_scope_document_count",
        "unknown_chunk_reference_count",
        "unknown_vector_id_count",
    }
    if any(
        not isinstance(role_closure.get(key), str)
        or not SHA256_PATTERN.fullmatch(str(role_closure.get(key)))
        for key in role_hash_keys
    ):
        raise DLPError("Phase 1 role closure contains an invalid identity")
    for key in (
        "out_of_scope_document_count",
        "unknown_chunk_reference_count",
        "unknown_vector_id_count",
    ):
        if _strict_nonnegative_integer(role_closure.get(key), key) != 0:
            raise DLPError("Phase 1 role closure contains an unresolved reference")
    derived_closure = role_closure.get("derived")
    expected_derived_keys = {
        "manifest_sha256",
        "tree_sha256",
        "bm25_row_set_sha256",
        "graph_record_set_sha256",
        "chunk_vector_id_set_sha256",
        "entity_vector_id_set_sha256",
    }
    if (
        not isinstance(derived_closure, Mapping)
        or set(derived_closure) != expected_derived_keys
        or any(
            not isinstance(derived_closure.get(key), str)
            or not SHA256_PATTERN.fullmatch(str(derived_closure.get(key)))
            for key in expected_derived_keys
        )
    ):
        raise DLPError("Phase 1 derived role closure is malformed")
    authority_files = _role_file_map(layers["authority"], "authority")
    derived_files = _role_file_map(layers["derived"], "derived")
    if (
        role_closure.get("authority_manifest_sha256")
        != authority_files.get("authority-manifest.json")
        or role_closure.get("authority_database_sha256")
        != authority_files.get("rag_chunks.db")
        or derived_closure.get("manifest_sha256")
        != derived_files.get("derived-candidate-manifest.json")
        or derived_closure.get("tree_sha256") != layers["derived"].get("tree_sha256")
        or role_closure.get("authority_document_set_sha256")
        != role_closure.get("approved_source_path_set_sha256")
        or derived_closure.get("chunk_vector_id_set_sha256")
        != role_closure.get("authority_chunk_id_set_sha256")
    ):
        raise DLPError("Phase 1 role closure differs from its scanned layers")

    implementation_scope = value.get("implementation_scope")
    if not isinstance(implementation_scope, Mapping):
        raise DLPError("implementation scope is absent")
    expected_implementation_keys = {
        "schema_version",
        "file_count",
        "total_bytes",
        "files",
        "path_set_sha256",
        "hash_set_sha256",
        "tree_sha256",
        "path_hash_set_sha256",
        "fixed_top_level_files",
        "fixed_tree_roots",
        "runtime_file_allowlist",
        "builder_file_allowlist",
    }
    if set(implementation_scope) != expected_implementation_keys:
        raise DLPError("implementation scope schema is incomplete")
    implementation_layer = layers["implementation"]
    for key in (
        "file_count",
        "total_bytes",
        "files",
        "path_set_sha256",
        "hash_set_sha256",
        "tree_sha256",
    ):
        if not _same_canonical_json(implementation_scope.get(key), implementation_layer.get(key)):
            raise DLPError("implementation scope differs from its DLP layer")
    if implementation_scope.get("path_hash_set_sha256") != implementation_scope.get(
        "tree_sha256"
    ):
        raise DLPError("implementation scope tree identity mismatch")
    implementation_files = _role_file_map(implementation_layer, "implementation")
    allowlist_contracts = (
        (
            implementation_scope.get("runtime_file_allowlist"),
            RUNTIME_FILE_ALLOWLIST,
            REQUIRED_RUNTIME_FILES,
        ),
        (
            implementation_scope.get("builder_file_allowlist"),
            BUILDER_FILE_ALLOWLIST,
            REQUIRED_BUILDER_FILES,
        ),
    )
    for contract, expected_path, exact_paths in allowlist_contracts:
        if not isinstance(contract, Mapping) or set(contract) != {
            "path",
            "sha256",
            "declared_file_count",
            "declared_path_set_sha256",
        }:
            raise DLPError("implementation allowlist binding is malformed")
        if (
            contract.get("path") != expected_path
            or contract.get("sha256") != implementation_files.get(expected_path)
            or type(contract.get("declared_file_count")) is not int
            or int(contract["declared_file_count"]) <= 0
            or not isinstance(contract.get("declared_path_set_sha256"), str)
            or not SHA256_PATTERN.fullmatch(
                str(contract.get("declared_path_set_sha256"))
            )
        ):
            raise DLPError("implementation allowlist identity mismatch")
        if exact_paths is not None and (
            contract.get("declared_file_count") != len(exact_paths)
            or contract.get("declared_path_set_sha256")
            != _canonical_identity_sha256(list(exact_paths))
            or any(path not in implementation_files for path in exact_paths)
        ):
            raise DLPError("implementation allowlist dependencies are absent from the DLP closure")

    real = value.get("real_candidate")
    if not isinstance(real, Mapping) or set(real) != {
        "object_count",
        "scanned_bytes",
        "finding_count",
        "findings",
        "object_set_sha256",
    }:
        raise DLPError("Phase 1 DLP real-candidate summary is incomplete")
    _strict_nonnegative_integer(real.get("object_count"), "object_count")
    _strict_nonnegative_integer(real.get("scanned_bytes"), "scanned_bytes")
    findings = _validate_finding_list(real.get("findings"), "real_candidate")
    if _strict_nonnegative_integer(real.get("finding_count"), "finding_count") != len(
        findings
    ):
        raise DLPError("Phase 1 DLP real-candidate finding count mismatch")
    if findings:
        raise DLPError("Phase 1 DLP receipt contains nested findings")
    if not isinstance(real.get("object_set_sha256"), str) or not SHA256_PATTERN.fullmatch(
        str(real.get("object_set_sha256"))
    ):
        raise DLPError("Phase 1 DLP object-set identity is invalid")

    canary = value.get("positive_canary")
    expected_canary_keys = {
        "payload_sha256",
        "rejected_as_expected",
        "required_rule_ids",
        "detected_rule_ids",
        "finding_count",
    }
    if not isinstance(canary, Mapping) or set(canary) != expected_canary_keys:
        raise DLPError("Phase 1 DLP canary receipt is incomplete")
    required_rules = sorted(rule_id for rule_id, _pattern in RULES)
    if (
        canary.get("rejected_as_expected") is not True
        or canary.get("required_rule_ids") != required_rules
        or canary.get("detected_rule_ids") != required_rules
        or type(canary.get("finding_count")) is not int
        or int(canary.get("finding_count")) < len(required_rules)
    ):
        raise DLPError("Phase 1 DLP positive canary is false or incomplete")


@contextlib.contextmanager
def _load_receipt(
    receipt: str | Path | Mapping[str, Any],
    *,
    scanned_roots: Iterable[str | Path],
) -> Iterator[tuple[dict[str, Any], str]]:
    if isinstance(receipt, Mapping):
        value = dict(receipt)
        declared_hash = value.pop("receipt_sha256", None)
        digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
        if declared_hash is not None and declared_hash != digest:
            raise DLPError("DLP receipt hash field is stale")
        yield value, digest
        return
    path = _detached_receipt_path(
        receipt,
        scanned_roots=scanned_roots,
        must_exist=True,
    )
    with _held_payload(path, "DLP receipt") as held:
        value = dict(_strict_json_bytes(held.payload, held.path.name))
        if held.payload != canonical_json_bytes(value):
            raise DLPError("DLP receipt is not canonical JSON")
        yield value, hashlib.sha256(held.payload).hexdigest()


def _publication_failure_after_cleanup(
    written: _WrittenJSON,
    cause: BaseException,
    *,
    post_commit_validated: bool,
) -> BaseException:
    if not written.commit_succeeded:
        cleanup_error = _drain_cleanup(
            (written.remove_if_unchanged, written.close)
        )
        if cleanup_error is None:
            return cause
        outcome = ReceiptPublicationOutcome(
            state=ReceiptPublicationState.RECONCILIATION_REQUIRED,
            receipt_sha256=written.digest,
            final_identity_verified=False,
            directory_fsync_ok=None,
            maintenance_required=True,
            maintenance_error_types=(type(cleanup_error).__name__,),
        )
        written.reconciliation_required = True
        written.publication_outcome = outcome
        return DLPReceiptPublicationError(
            "DLP receipt pre-commit cleanup requires explicit reconciliation",
            outcome,
        )

    close_error = _drain_cleanup((written.close,))
    current = written.publication_outcome or ReceiptPublicationOutcome(
        state=ReceiptPublicationState.COMMITTED_DURABILITY_UNKNOWN,
        receipt_sha256=written.digest,
        final_identity_verified=None,
        directory_fsync_ok=None,
        maintenance_required=False,
    )
    maintenance_types = list(current.maintenance_error_types)
    maintenance_types.extend(_attached_cleanup_error_types(cause))
    if post_commit_validated and not isinstance(cause, DLPError):
        maintenance_types.append(type(cause).__name__)
    if close_error is not None:
        maintenance_types.append(type(close_error).__name__)
        maintenance_types.extend(_attached_cleanup_error_types(close_error))
    maintenance_types = list(dict.fromkeys(maintenance_types))

    if current.state is ReceiptPublicationState.RECONCILIATION_REQUIRED:
        state = current.state
    elif isinstance(cause, DLPError) and not isinstance(
        cause, DLPReceiptPublicationError
    ):
        state = ReceiptPublicationState.RECONCILIATION_REQUIRED
    elif not post_commit_validated and not isinstance(
        cause, DLPReceiptPublicationError
    ):
        state = ReceiptPublicationState.RECONCILIATION_REQUIRED
    elif current.state is ReceiptPublicationState.COMMITTED_DURABILITY_UNKNOWN:
        state = current.state
    elif maintenance_types:
        state = ReceiptPublicationState.COMMITTED_MAINTENANCE_REQUIRED
    else:
        state = current.state
    outcome = ReceiptPublicationOutcome(
        state=state,
        receipt_sha256=written.digest,
        final_identity_verified=current.final_identity_verified,
        directory_fsync_ok=current.directory_fsync_ok,
        maintenance_required=bool(maintenance_types),
        maintenance_error_types=tuple(maintenance_types),
    )
    written.reconciliation_required = (
        state is ReceiptPublicationState.RECONCILIATION_REQUIRED
    )
    written.publication_outcome = outcome
    return _publication_error(outcome)


def _publication_error(
    outcome: ReceiptPublicationOutcome,
) -> DLPReceiptPublicationError:
    return DLPReceiptPublicationError(
        _publication_error_message(outcome.state),
        outcome,
    )


def _require_clean_committed_publication(written: _WrittenJSON) -> None:
    outcome = written.publication_outcome
    if outcome is not None and outcome.state is ReceiptPublicationState.COMMITTED:
        return
    if outcome is None:
        outcome = ReceiptPublicationOutcome(
            state=ReceiptPublicationState.RECONCILIATION_REQUIRED,
            receipt_sha256=written.digest,
            final_identity_verified=None,
            directory_fsync_ok=None,
            maintenance_required=False,
        )
        written.reconciliation_required = True
        written.publication_outcome = outcome
    raise _publication_error(outcome)


def _revalidate_committed_receipt(written: _WrittenJSON) -> None:
    try:
        written.revalidate()
    except BaseException as exc:
        current = written.publication_outcome
        written._require_reconciliation(
            final_identity_verified=False,
            directory_fsync_ok=(
                current.directory_fsync_ok if current is not None else None
            ),
            cause=exc,
        )


def _scan_phase1_candidate_impl(
    *,
    scope: ApprovedSourceScope,
    authority_root: str | Path,
    derived_root: str | Path,
    code_root: str | Path,
    receipt_path: str | Path,
) -> dict[str, object]:
    scanned_roots = (
        scope.source_root,
        scope.governance_root,
        authority_root,
        derived_root,
        code_root,
    )
    output = _detached_receipt_path(
        receipt_path,
        scanned_roots=scanned_roots,
        must_exist=False,
    )
    written: _WrittenJSON | None = None
    post_commit_validated = False
    try:
        with _held_pdf_tool_set() as pdf_tools, _phase1_stable_view(
            scope=scope,
            authority_root=authority_root,
            derived_root=derived_root,
            code_root=code_root,
        ) as stable:
            receipt = _build_phase1_receipt(
                scope=stable.scope,
                authority_root=stable.authority_root,
                derived_root=stable.derived_root,
                code_root=stable.code_root,
                _pdf_tools=pdf_tools,
            )
            if not receipt["ok"]:
                raise DLPError("Phase 1 candidate DLP gate failed")
            stable.revalidate()
            pdf_tools.revalidate()
            written = _write_new_json(output, receipt)
            result = {**receipt, "receipt_sha256": written.digest}
            pdf_tools.revalidate()
            written.revalidate()
            stable.revalidate()
            written.publish()
            written.revalidate()
            pdf_tools.revalidate()
            stable.revalidate()
            post_commit_validated = True
        _revalidate_committed_receipt(written)
        written.close()
    except BaseException as exc:
        if written is not None:
            replacement = _publication_failure_after_cleanup(
                written,
                exc,
                post_commit_validated=post_commit_validated,
            )
            if replacement is not exc:
                raise replacement from exc
        raise
    _require_clean_committed_publication(written)
    return result


def scan_phase1_candidate(
    *,
    scope: ApprovedSourceScope,
    authority_root: str | Path,
    derived_root: str | Path,
    code_root: str | Path,
    receipt_path: str | Path,
) -> dict[str, object]:
    actions = _require_formal_dlp_bootstrap_context()
    return actions[4](
        scope=scope,
        authority_root=authority_root,
        derived_root=derived_root,
        code_root=code_root,
        receipt_path=receipt_path,
    )


def _validate_phase1_dlp_receipt_impl(
    *,
    receipt: str | Path | Mapping[str, Any],
    scope: ApprovedSourceScope,
    authority_root: str | Path,
    derived_root: str | Path,
    code_root: str | Path,
    authority_database_physical_mode: int = 0o600,
) -> dict[str, object]:
    """Recompute every bound root and reject stale or self-reported DLP evidence.

    The authority manifest always declares the runtime mode ``0600``. Sealed
    packaging layers may require an exact physical transport mode while
    retaining the same authoritative database bytes and logical contract.
    """

    scanned_roots = (
        scope.source_root,
        scope.governance_root,
        authority_root,
        derived_root,
        code_root,
    )
    with _held_pdf_tool_set() as pdf_tools, _load_receipt(
        receipt,
        scanned_roots=scanned_roots,
    ) as (value, receipt_sha256), _phase1_stable_view(
        scope=scope,
        authority_root=authority_root,
        derived_root=derived_root,
        code_root=code_root,
    ) as stable:
        scanner_contract = _scanner_contract(pdf_tools)
        _validate_phase1_receipt_structure(
            value,
            scanner_contract=scanner_contract,
        )
        expected = _build_phase1_receipt(
            scope=stable.scope,
            authority_root=stable.authority_root,
            derived_root=stable.derived_root,
            code_root=stable.code_root,
            _pdf_tools=pdf_tools,
            authority_database_physical_mode=authority_database_physical_mode,
        )
        if not expected["ok"] or not _same_canonical_json(value, expected):
            raise DLPError("Phase 1 DLP receipt is stale or differs from current bytes")
        stable.revalidate()
        pdf_tools.revalidate()
        result = {**value, "receipt_sha256": receipt_sha256}
    return result


def validate_phase1_dlp_receipt(
    *,
    receipt: str | Path | Mapping[str, Any],
    scope: ApprovedSourceScope,
    authority_root: str | Path,
    derived_root: str | Path,
    code_root: str | Path,
    authority_database_physical_mode: int = 0o600,
) -> dict[str, object]:
    actions = _require_formal_dlp_bootstrap_context()
    return actions[5](
        receipt=receipt,
        scope=scope,
        authority_root=authority_root,
        derived_root=derived_root,
        code_root=code_root,
        authority_database_physical_mode=authority_database_physical_mode,
    )


def _inventory_target(raw: str | Path) -> tuple[str, Path, dict[str, object]]:
    path = Path(raw)
    try:
        mode = os.lstat(path).st_mode
    except OSError as exc:
        raise DLPError("DLP evidence target cannot be inspected") from exc
    if stat.S_ISLNK(mode):
        raise DLPError("DLP evidence target cannot be a symlink")
    if stat.S_ISDIR(mode):
        root = _real_directory(path, "DLP evidence root")
        return "directory", root, _tree_inventory(root)
    if stat.S_ISREG(mode):
        resolved = path.resolve(strict=True)
        return "file", resolved.parent, _file_inventory(resolved)
    raise DLPError("DLP evidence target must be a regular file or real directory")


def _load_canonical_json_file(path: str | Path) -> tuple[dict[str, Any], str]:
    with _held_payload(path, "JSON receipt") as held:
        value = dict(_strict_json_bytes(held.payload, held.path.name))
        if held.payload != canonical_json_bytes(value):
            raise DLPError("JSON receipt is not canonical")
        return value, hashlib.sha256(held.payload).hexdigest()


def _suite_bindings(
    *,
    suite_root: Path,
    suite_inventory: Mapping[str, object],
    candidate_receipt_sha256: str,
) -> dict[str, object]:
    raw_files = suite_inventory.get("files")
    if not isinstance(raw_files, list):
        raise DLPError("suite inventory file records are absent")
    file_hashes = {
        str(record["path"]): str(record["sha256"])
        for record in raw_files
        if isinstance(record, Mapping)
    }
    required = {
        "SUITE_MANIFEST.json",
        "SHA256SUMS",
        "server-runtime/evidence/candidate-dlp-receipt.json",
    }
    if not required <= set(file_hashes):
        raise DLPError("suite is missing required DLP binding artifacts")
    sums_path = _safe_inventory_path(suite_root, "SHA256SUMS")
    sums: dict[str, str] = {}
    ordered_paths: list[str] = []
    try:
        lines = sums_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise DLPError("suite SHA256SUMS is not UTF-8") from exc
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise DLPError("suite SHA256SUMS contains an invalid record")
        digest, relative_raw = match.groups()
        relative = _canonical_inventory_relative(relative_raw)
        if relative in sums:
            raise DLPError("suite SHA256SUMS contains a duplicate path")
        sums[relative] = digest
        ordered_paths.append(relative)
    if ordered_paths != sorted(ordered_paths):
        raise DLPError("suite SHA256SUMS paths are not sorted")
    expected_paths = set(file_hashes) - {"SHA256SUMS"}
    if set(sums) != expected_paths:
        raise DLPError("suite SHA256SUMS coverage differs from exact suite files")
    if any(file_hashes[path] != digest for path, digest in sums.items()):
        raise DLPError("suite SHA256SUMS contains a stale file hash")
    embedded_candidate_sha256 = file_hashes[
        "server-runtime/evidence/candidate-dlp-receipt.json"
    ]
    if embedded_candidate_sha256 != candidate_receipt_sha256:
        raise DLPError("suite embeds a different candidate DLP receipt")
    suite_manifest, _suite_manifest_sha256 = _load_canonical_json_file(
        _safe_inventory_path(suite_root, "SUITE_MANIFEST.json")
    )
    suite_release_id = suite_manifest.get("suite_release_id")
    if not isinstance(suite_release_id, str) or not suite_release_id:
        raise DLPError("suite manifest release identity is absent")
    return {
        "suite_release_id": suite_release_id,
        "suite_manifest": {
            "path": "SUITE_MANIFEST.json",
            "sha256": file_hashes["SUITE_MANIFEST.json"],
        },
        "sha256sums": {
            "path": "SHA256SUMS",
            "sha256": file_hashes["SHA256SUMS"],
            "covered_file_count": len(sums),
        },
        "candidate_dlp_receipt": {
            "path": "server-runtime/evidence/candidate-dlp-receipt.json",
            "sha256": candidate_receipt_sha256,
        },
    }


def _normalize_evidence_roots(
    evidence_roots: Mapping[str, str | Path] | None,
) -> dict[str, str | Path]:
    if not isinstance(evidence_roots, Mapping):
        raise DLPError("evidence_roots must be a label-to-path mapping")
    required = set(FINAL_EVIDENCE_TARGET_KINDS)
    if set(evidence_roots) != required:
        raise DLPError("final evidence root labels do not match the exact required closure")
    return {label: evidence_roots[label] for label in sorted(required)}


def _offline_test_evidence_root(evidence_roots: Mapping[str, str | Path]) -> Path:
    component_set = Path(evidence_roots["offline-test-component-set"]).resolve(
        strict=True
    )
    return component_set.parent


def _final_evidence_json(
    evidence_roots: Mapping[str, str | Path], label: str
) -> tuple[dict[str, Any], str]:
    return _load_canonical_json_file(evidence_roots[label])


def _validate_disclosure_evidence(value: Mapping[str, Any]) -> None:
    if set(value) != {
        "schema_version",
        "status",
        "ok",
        "created_at",
        "provider_mode",
        "real_provider_calls",
        "network_calls",
        "contains_real_source_or_user_data",
        "source_files",
        "runs",
        "gates",
    }:
        raise DLPError("offline disclosure evidence schema is not exact")
    runs = value.get("runs")
    gates = value.get("gates")
    if (
        value.get("schema_version") != OFFLINE_DISCLOSURE_SCHEMA_VERSION
        or value.get("status") != "passed"
        or value.get("ok") is not True
        or value.get("provider_mode") != "sealed-offline-fake-only"
        or value.get("real_provider_calls") != 0
        or value.get("network_calls") != 0
        or value.get("contains_real_source_or_user_data") is not False
        or not isinstance(runs, list)
        or not runs
        or not isinstance(gates, Mapping)
        or set(gates)
        != {
            "run_count",
            "started_channel_count",
            "ledger_entry_count",
            "all_started_channels_disclosed_and_accounted",
        }
        or gates.get("all_started_channels_disclosed_and_accounted") is not True
        or gates.get("run_count") != len(runs)
    ):
        raise DLPError("offline disclosure evidence did not prove fake-only closure")
    started = 0
    ledger_entries = 0
    for run in runs:
        if not isinstance(run, Mapping):
            raise DLPError("offline disclosure run is malformed")
        call_counts = run.get("transport_call_counts")
        ledger = run.get("ledger")
        if (
            not isinstance(call_counts, list)
            or not call_counts
            or any(type(count) is not int or count < 0 for count in call_counts)
            or not isinstance(ledger, list)
            or any(
                not isinstance(entry, Mapping) or entry.get("disclosed") is not True
                for entry in ledger
            )
            or sum(call_counts) != len(ledger)
        ):
            raise DLPError("offline disclosure ledger is incomplete")
        started += sum(call_counts)
        ledger_entries += len(ledger)
    if (
        gates.get("started_channel_count") != started
        or gates.get("ledger_entry_count") != ledger_entries
    ):
        raise DLPError("offline disclosure gate counts are stale")


def _validate_final_evidence_closure(
    *,
    repo_root: str | Path,
    evidence_roots: Mapping[str, str | Path],
    evidence_states: Mapping[str, tuple[str, Path, dict[str, object]]],
    suite_inventory: Mapping[str, object],
    suite_bindings: Mapping[str, object],
) -> dict[str, object]:
    for label, expected_kind in FINAL_EVIDENCE_TARGET_KINDS.items():
        state = evidence_states.get(label)
        if state is None or state[0] != expected_kind:
            raise DLPError(f"final evidence target kind mismatch: {label}")
        if state[2].get("file_count") == 0:
            raise DLPError(f"final evidence target is empty: {label}")

    disclosure, disclosure_sha256 = _final_evidence_json(
        evidence_roots, "disclosure-evidence"
    )
    _validate_disclosure_evidence(disclosure)

    component_set_path = Path(evidence_roots["offline-test-component-set"]).resolve(
        strict=True
    )
    test_receipt_path = Path(evidence_roots["offline-test-receipt"]).resolve(strict=True)
    test_evidence_root = component_set_path.parent
    logs_root = Path(evidence_roots["offline-test-logs"]).resolve(strict=True)
    if test_receipt_path.parent != test_evidence_root or logs_root != test_evidence_root / "logs":
        raise DLPError("offline test evidence paths do not share the exact closed root")
    try:
        validated_test_evidence = run_formal_validation(
            repo_root=repo_root,
            validation="validate-tests",
            receipt_path=test_receipt_path,
            evidence_root=test_evidence_root,
            component_set_path=component_set_path,
        )
    except OfflineEvidenceError as exc:
        raise DLPError("offline test evidence semantic validation failed") from exc

    build_receipt, _build_receipt_sha256 = _final_evidence_json(
        evidence_roots, "suite-build-receipt"
    )
    if set(build_receipt) != {
        "schema_version",
        "status",
        "ok",
        "structural_verification_ok",
        "final_dlp_receipt_required",
        "final_dlp_verified",
        "suite_release_id",
        "suite_manifest_sha256",
        "sha256sums_sha256",
        "candidate_dlp_receipt_sha256",
        "disclosure_evidence_sha256",
        "offline_test_receipt_sha256",
        "offline_test_count",
        "file_count",
        "real_provider_calls",
    }:
        raise DLPError("suite-build receipt schema is not exact")
    suite_manifest = suite_bindings.get("suite_manifest")
    sha256sums = suite_bindings.get("sha256sums")
    candidate = suite_bindings.get("candidate_dlp_receipt")
    if not all(isinstance(item, Mapping) for item in (suite_manifest, sha256sums, candidate)):
        raise DLPError("suite bindings are malformed")
    offline_test_count = _strict_nonnegative_integer(
        build_receipt.get("offline_test_count"), "offline_test_count"
    )
    file_count = _strict_nonnegative_integer(build_receipt.get("file_count"), "file_count")
    real_provider_calls = _strict_nonnegative_integer(
        build_receipt.get("real_provider_calls"), "real_provider_calls"
    )
    if (
        build_receipt.get("schema_version") != SUITE_BUILD_RECEIPT_SCHEMA_VERSION
        or build_receipt.get("status") != "pending-final-dlp"
        or build_receipt.get("ok") is not False
        or build_receipt.get("structural_verification_ok") is not True
        or build_receipt.get("final_dlp_receipt_required") is not True
        or build_receipt.get("final_dlp_verified") is not False
        or build_receipt.get("suite_release_id") != suite_bindings.get("suite_release_id")
        or build_receipt.get("suite_manifest_sha256") != suite_manifest.get("sha256")
        or build_receipt.get("sha256sums_sha256") != sha256sums.get("sha256")
        or build_receipt.get("candidate_dlp_receipt_sha256") != candidate.get("sha256")
        or build_receipt.get("disclosure_evidence_sha256") != disclosure_sha256
        or build_receipt.get("offline_test_receipt_sha256")
        != validated_test_evidence.get("receipt_sha256")
        or offline_test_count != validated_test_evidence.get("test_count")
        or file_count != suite_inventory.get("file_count")
        or real_provider_calls != 0
    ):
        raise DLPError("suite-build receipt does not bind the exact suite")

    return {
        "schema_version": FINAL_EVIDENCE_CLOSURE_SCHEMA_VERSION,
        "required_labels": sorted(FINAL_EVIDENCE_TARGET_KINDS),
        "semantic_validation_ok": True,
        "targets": {
            label: {
                "target_kind": evidence_states[label][0],
                "file_count": evidence_states[label][2]["file_count"],
                "tree_sha256": evidence_states[label][2]["tree_sha256"],
            }
            for label in sorted(FINAL_EVIDENCE_TARGET_KINDS)
        },
    }


def _build_final_suite_dlp_receipt(
    *,
    repo_root: str | Path,
    suite_root: str | Path,
    candidate_receipt_path: str | Path,
    evidence_roots: Mapping[str, str | Path] | None,
    _pdf_tools: _PDFToolSet,
) -> dict[str, object]:
    suite_root = _real_directory(suite_root, "suite root")
    expected_candidate_receipt = (
        suite_root / "server-runtime/evidence/candidate-dlp-receipt.json"
    )
    try:
        resolved_candidate_receipt = Path(candidate_receipt_path).resolve(strict=True)
        resolved_expected_candidate_receipt = expected_candidate_receipt.resolve(
            strict=True
        )
    except OSError as exc:
        raise DLPError("sealed suite candidate DLP receipt is unavailable") from exc
    if resolved_candidate_receipt != resolved_expected_candidate_receipt:
        raise DLPError(
            "candidate DLP receipt must be the sealed suite evidence copy"
        )
    candidate_receipt_path = resolved_candidate_receipt
    candidate_value, candidate_sha256 = _load_canonical_json_file(
        candidate_receipt_path
    )
    _validate_phase1_receipt_structure(
        candidate_value,
        scanner_contract=_scanner_contract(_pdf_tools),
    )
    normalized_evidence = _normalize_evidence_roots(evidence_roots)

    suite_before = _tree_inventory(suite_root)
    evidence_before: dict[str, tuple[str, Path, dict[str, object]]] = {
        label: _inventory_target(path) for label, path in normalized_evidence.items()
    }
    candidate_kind, candidate_scan_root, candidate_before = _inventory_target(
        candidate_receipt_path
    )
    bindings = _suite_bindings(
        suite_root=suite_root,
        suite_inventory=suite_before,
        candidate_receipt_sha256=candidate_sha256,
    )
    bindings["evidence_closure"] = _validate_final_evidence_closure(
        repo_root=repo_root,
        evidence_roots=normalized_evidence,
        evidence_states=evidence_before,
        suite_inventory=suite_before,
        suite_bindings=bindings,
    )

    scanner = DLPScanner(_pdf_tools=_pdf_tools)
    suite_findings = _scan_inventory(
        scanner,
        root=suite_root,
        inventory=suite_before,
        object_prefix="layers/suite",
    )
    candidate_findings = _scan_inventory(
        scanner,
        root=candidate_scan_root,
        inventory=candidate_before,
        object_prefix="bindings/candidate-receipt",
    )
    evidence_layers: dict[str, dict[str, object]] = {}
    for label, (target_kind, scan_root, inventory) in evidence_before.items():
        findings = _scan_inventory(
            scanner,
            root=scan_root,
            inventory=inventory,
            object_prefix=f"layers/evidence/{label}",
        )
        evidence_layers[label] = _layer_receipt(
            inventory,
            findings,
            target_kind=target_kind,
        )

    suite_after = _tree_inventory(suite_root)
    if not _same_canonical_json(suite_before, suite_after):
        raise DLPError("suite inventory changed during final DLP scan")
    candidate_after_kind, _candidate_after_root, candidate_after = _inventory_target(
        candidate_receipt_path
    )
    if candidate_after_kind != candidate_kind or not _same_canonical_json(
        candidate_before, candidate_after
    ):
        raise DLPError("candidate DLP receipt changed during final scan")
    for label, before_state in evidence_before.items():
        after_state = _inventory_target(normalized_evidence[label])
        if before_state[0] != after_state[0] or not _same_canonical_json(
            before_state[2], after_state[2]
        ):
            raise DLPError(f"evidence root changed during final DLP scan: {label}")

    canary, canary_ok = _positive_canary_receipt(_pdf_tools)
    real = scanner.summary()
    ok = real["finding_count"] == 0 and canary_ok
    scanner_contract = scanner.scanner_contract()
    bindings["candidate_dlp_receipt"] = {
        **dict(bindings["candidate_dlp_receipt"]),
        "target_kind": candidate_kind,
        "finding_count": len(candidate_findings),
        "findings": candidate_findings,
    }
    return {
        "schema_version": FINAL_SUITE_DLP_SCHEMA_VERSION,
        "ruleset_version": DLP_RULESET_VERSION,
        "ruleset_sha256": _ruleset_sha256(),
        "scanner_sha256": _canonical_identity_sha256(scanner_contract),
        "status": "passed" if ok else "failed",
        "ok": ok,
        "layers": {
            "suite": _layer_receipt(suite_before, suite_findings),
            "evidence": evidence_layers,
        },
        "bindings": bindings,
        "real_candidate": real,
        "positive_canary": canary,
        "scanner_contract": scanner_contract,
    }


def _scan_final_suite_dlp_impl(
    *,
    repo_root: str | Path,
    suite_root: str | Path,
    candidate_receipt_path: str | Path,
    receipt_path: str | Path,
    evidence_roots: Mapping[str, str | Path],
) -> dict[str, object]:
    """Scan a sealed suite and its exact required evidence into a detached receipt."""

    normalized_evidence = _normalize_evidence_roots(evidence_roots)
    scanned_roots: list[str | Path] = [suite_root]
    scanned_roots.extend(normalized_evidence.values())
    scanned_roots.append(_offline_test_evidence_root(normalized_evidence))
    output = _detached_receipt_path(
        receipt_path,
        scanned_roots=scanned_roots,
        must_exist=False,
    )
    written: _WrittenJSON | None = None
    post_commit_validated = False
    try:
        with _held_pdf_tool_set() as pdf_tools, _final_stable_view(
            suite_root=suite_root,
            candidate_receipt_path=candidate_receipt_path,
            evidence_roots=normalized_evidence,
        ) as stable:
            receipt = _build_final_suite_dlp_receipt(
                repo_root=repo_root,
                suite_root=stable.suite_root,
                candidate_receipt_path=stable.candidate_receipt_path,
                evidence_roots=stable.evidence_roots,
                _pdf_tools=pdf_tools,
            )
            if not receipt["ok"]:
                raise DLPError("final suite DLP gate failed")
            stable.revalidate()
            pdf_tools.revalidate()
            written = _write_new_json(output, receipt)
            result = {**receipt, "receipt_sha256": written.digest}
            pdf_tools.revalidate()
            written.revalidate()
            stable.revalidate()
            written.publish()
            written.revalidate()
            pdf_tools.revalidate()
            stable.revalidate()
            post_commit_validated = True
        _revalidate_committed_receipt(written)
        written.close()
    except BaseException as exc:
        if written is not None:
            replacement = _publication_failure_after_cleanup(
                written,
                exc,
                post_commit_validated=post_commit_validated,
            )
            if replacement is not exc:
                raise replacement from exc
        raise
    _require_clean_committed_publication(written)
    return result


def scan_final_suite_dlp(
    *,
    repo_root: str | Path,
    suite_root: str | Path,
    candidate_receipt_path: str | Path,
    receipt_path: str | Path,
    evidence_roots: Mapping[str, str | Path],
) -> dict[str, object]:
    actions = _require_formal_dlp_bootstrap_context()
    return actions[6](
        repo_root=repo_root,
        suite_root=suite_root,
        candidate_receipt_path=candidate_receipt_path,
        receipt_path=receipt_path,
        evidence_roots=evidence_roots,
    )


def _validate_final_suite_receipt_structure(
    value: Mapping[str, Any],
    *,
    scanner_contract: Mapping[str, object] | None = None,
) -> None:
    expected_keys = {
        "schema_version",
        "ruleset_version",
        "ruleset_sha256",
        "scanner_sha256",
        "status",
        "ok",
        "layers",
        "bindings",
        "real_candidate",
        "positive_canary",
        "scanner_contract",
    }
    if set(value) != expected_keys:
        raise DLPError("final suite DLP receipt schema is incomplete")
    if value.get("schema_version") != FINAL_SUITE_DLP_SCHEMA_VERSION:
        raise DLPError("final suite DLP receipt schema mismatch")
    if value.get("ok") is not True or value.get("status") != "passed":
        raise DLPError("final suite DLP receipt is not passing")
    if value.get("ruleset_version") != DLP_RULESET_VERSION or value.get(
        "ruleset_sha256"
    ) != _ruleset_sha256():
        raise DLPError("final suite DLP ruleset binding mismatch")
    active_scanner_contract = dict(scanner_contract or _scanner_contract())
    if not _same_canonical_json(
        value.get("scanner_contract"), active_scanner_contract
    ) or value.get("scanner_sha256") != _canonical_identity_sha256(
        active_scanner_contract
    ):
        raise DLPError("final suite DLP scanner binding mismatch")
    layers = value.get("layers")
    if not isinstance(layers, Mapping) or set(layers) != {"suite", "evidence"}:
        raise DLPError("final suite DLP layers are incomplete")
    _validate_inventory_layer(layers["suite"], label="suite")
    if layers["suite"].get("finding_count") != 0 or layers["suite"].get("findings") != []:
        raise DLPError("final suite DLP suite layer contains a finding")
    evidence = layers["evidence"]
    if not isinstance(evidence, Mapping) or set(evidence) != set(
        FINAL_EVIDENCE_TARGET_KINDS
    ):
        raise DLPError("final suite DLP evidence layers are not the exact required closure")
    for label, layer in evidence.items():
        if not isinstance(label, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", label
        ):
            raise DLPError("final suite DLP evidence label is invalid")
        _validate_inventory_layer(
            layer,
            label=f"evidence/{label}",
            extra_keys={"target_kind"},
        )
        if layer.get("target_kind") != FINAL_EVIDENCE_TARGET_KINDS[label]:
            raise DLPError("final suite DLP evidence target kind is invalid")
        if layer.get("file_count") == 0:
            raise DLPError("final suite DLP evidence target is empty")
        if layer.get("finding_count") != 0 or layer.get("findings") != []:
            raise DLPError("final suite DLP evidence layer contains a finding")
    bindings = value.get("bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != {
        "suite_release_id",
        "suite_manifest",
        "sha256sums",
        "candidate_dlp_receipt",
        "evidence_closure",
    }:
        raise DLPError("final suite DLP bindings are incomplete")
    candidate = bindings.get("candidate_dlp_receipt")
    if not isinstance(candidate, Mapping) or candidate.get("finding_count") != 0 or candidate.get(
        "findings"
    ) != []:
        raise DLPError("final suite candidate receipt scan contains a finding")
    closure = bindings.get("evidence_closure")
    if (
        not isinstance(closure, Mapping)
        or set(closure)
        != {"schema_version", "required_labels", "semantic_validation_ok", "targets"}
        or closure.get("schema_version") != FINAL_EVIDENCE_CLOSURE_SCHEMA_VERSION
        or closure.get("required_labels") != sorted(FINAL_EVIDENCE_TARGET_KINDS)
        or closure.get("semantic_validation_ok") is not True
        or not isinstance(closure.get("targets"), Mapping)
        or set(closure["targets"]) != set(FINAL_EVIDENCE_TARGET_KINDS)
    ):
        raise DLPError("final suite evidence closure binding is malformed")
    for label, layer in evidence.items():
        target = closure["targets"].get(label)
        if not isinstance(target, Mapping) or target != {
            "target_kind": layer.get("target_kind"),
            "file_count": layer.get("file_count"),
            "tree_sha256": layer.get("tree_sha256"),
        }:
            raise DLPError("final suite evidence closure identity mismatch")
    real = value.get("real_candidate")
    if not isinstance(real, Mapping) or real.get("finding_count") != 0 or real.get(
        "findings"
    ) != []:
        raise DLPError("final suite DLP receipt contains nested findings")
    canary = value.get("positive_canary")
    required_rules = sorted(rule_id for rule_id, _pattern in RULES)
    if not isinstance(canary, Mapping) or canary.get(
        "rejected_as_expected"
    ) is not True or canary.get("required_rule_ids") != required_rules or canary.get(
        "detected_rule_ids"
    ) != required_rules:
        raise DLPError("final suite DLP positive canary is false or incomplete")


def _validate_final_suite_dlp_receipt_impl(
    *,
    repo_root: str | Path,
    receipt: str | Path | Mapping[str, Any],
    suite_root: str | Path,
    candidate_receipt_path: str | Path,
    evidence_roots: Mapping[str, str | Path],
) -> dict[str, object]:
    """Recompute a suite/evidence closure and reject any stale detached receipt."""

    normalized_evidence = _normalize_evidence_roots(evidence_roots)
    scanned_roots: list[str | Path] = [suite_root]
    scanned_roots.extend(normalized_evidence.values())
    scanned_roots.append(_offline_test_evidence_root(normalized_evidence))
    with _held_pdf_tool_set() as pdf_tools, _load_receipt(
        receipt,
        scanned_roots=scanned_roots,
    ) as (value, receipt_sha256), _final_stable_view(
        suite_root=suite_root,
        candidate_receipt_path=candidate_receipt_path,
        evidence_roots=normalized_evidence,
    ) as stable:
        scanner_contract = _scanner_contract(pdf_tools)
        _validate_final_suite_receipt_structure(
            value,
            scanner_contract=scanner_contract,
        )
        expected = _build_final_suite_dlp_receipt(
            repo_root=repo_root,
            suite_root=stable.suite_root,
            candidate_receipt_path=stable.candidate_receipt_path,
            evidence_roots=stable.evidence_roots,
            _pdf_tools=pdf_tools,
        )
        if not expected["ok"] or not _same_canonical_json(value, expected):
            raise DLPError("final suite DLP receipt is stale or differs from current bytes")
        stable.revalidate()
        pdf_tools.revalidate()
        result = {**value, "receipt_sha256": receipt_sha256}
    return result


def validate_final_suite_dlp_receipt(
    *,
    repo_root: str | Path,
    receipt: str | Path | Mapping[str, Any],
    suite_root: str | Path,
    candidate_receipt_path: str | Path,
    evidence_roots: Mapping[str, str | Path],
) -> dict[str, object]:
    actions = _require_formal_dlp_bootstrap_context()
    return actions[7](
        repo_root=repo_root,
        receipt=receipt,
        suite_root=suite_root,
        candidate_receipt_path=candidate_receipt_path,
        evidence_roots=evidence_roots,
    )


def _cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="formal-dlp", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    phase1_scan = commands.add_parser(
        "scan-phase1",
        help="scan the approved source and candidate implementation closure",
    )
    phase1_validate = commands.add_parser(
        "validate-phase1",
        help="recompute and validate a detached Phase-1 DLP receipt",
    )
    for command in (phase1_scan, phase1_validate):
        command.add_argument("--source-root", required=True)
        command.add_argument("--governance-root", required=True)
        command.add_argument("--authority-root", required=True)
        command.add_argument("--derived-root", required=True)
        command.add_argument("--code-root", required=True)
        command.add_argument("--receipt-path", required=True)
    phase1_validate.add_argument(
        "--authority-database-physical-mode",
        choices=("0440", "0600", "0640"),
        default="0600",
    )

    final_scan = commands.add_parser(
        "scan-final",
        help="scan a sealed final suite and its detached evidence closure",
    )
    final_validate = commands.add_parser(
        "validate-final",
        help="recompute and validate a detached final-suite DLP receipt",
    )
    for command in (final_scan, final_validate):
        command.add_argument("--repo-root", required=True)
        command.add_argument("--suite-root", required=True)
        command.add_argument("--candidate-receipt", required=True)
        command.add_argument("--receipt-path", required=True)
        command.add_argument(
            "--evidence-root",
            action="append",
            required=True,
            metavar="LABEL=PATH",
        )
    return parser


def _parse_cli_evidence_roots(values: Iterable[str]) -> dict[str, str]:
    roots: dict[str, str] = {}
    for value in values:
        label, separator, path = value.partition("=")
        if not separator or not label or not path:
            raise DLPError("evidence root must use LABEL=PATH")
        if label in roots:
            raise DLPError("evidence root label is duplicated")
        roots[label] = path
    if set(roots) != set(FINAL_EVIDENCE_TARGET_KINDS):
        raise DLPError("evidence roots are not the exact required closure")
    return roots


def _publication_cli_error(
    error: DLPReceiptPublicationError,
) -> dict[str, object]:
    outcome = error.outcome
    return {
        "schema_version": "cloud-v2-dlp-cli-publication-error-v1",
        "status": "failed",
        "ok": False,
        "error_type": "DLPReceiptPublicationError",
        "error": _publication_error_message(outcome.state),
        "publication_outcome": {
            "state": outcome.state.value,
            "receipt_sha256": outcome.receipt_sha256,
            "final_identity_verified": outcome.final_identity_verified,
            "directory_fsync_ok": outcome.directory_fsync_ok,
            "maintenance_required": outcome.maintenance_required,
            "maintenance_error_types": list(outcome.maintenance_error_types),
            "safe_to_retry": False,
        },
    }


@contextlib.contextmanager
def _cli_approved_source_scope(
    source_root: str | Path,
    governance_root: str | Path,
) -> Iterator[ApprovedSourceScope]:
    scope = ApprovedSourceScope.load(source_root, governance_root)
    body_failed = False
    try:
        yield scope
    except BaseException:
        body_failed = True
        raise
    finally:
        _revalidate_then_close(
            scope.revalidate,
            scope.close,
            body_failed=body_failed,
        )


def _run_cli(argv: list[str] | None = None) -> int:
    args = _cli_parser().parse_args(argv)
    try:
        if args.command in {"scan-phase1", "validate-phase1"}:
            with _cli_approved_source_scope(
                args.source_root,
                args.governance_root,
            ) as scope:
                if args.command == "scan-phase1":
                    result = scan_phase1_candidate(
                        scope=scope,
                        authority_root=args.authority_root,
                        derived_root=args.derived_root,
                        code_root=args.code_root,
                        receipt_path=args.receipt_path,
                    )
                else:
                    result = validate_phase1_dlp_receipt(
                        receipt=args.receipt_path,
                        scope=scope,
                        authority_root=args.authority_root,
                        derived_root=args.derived_root,
                        code_root=args.code_root,
                        authority_database_physical_mode=int(
                            args.authority_database_physical_mode, 8
                        ),
                    )
        else:
            evidence_roots = _parse_cli_evidence_roots(args.evidence_root)
            if args.command == "scan-final":
                result = scan_final_suite_dlp(
                    repo_root=args.repo_root,
                    suite_root=args.suite_root,
                    candidate_receipt_path=args.candidate_receipt,
                    receipt_path=args.receipt_path,
                    evidence_roots=evidence_roots,
                )
            else:
                result = validate_final_suite_dlp_receipt(
                    repo_root=args.repo_root,
                    receipt=args.receipt_path,
                    suite_root=args.suite_root,
                    candidate_receipt_path=args.candidate_receipt,
                    evidence_roots=evidence_roots,
                )
    except DLPReceiptPublicationError as exc:
        print(
            json.dumps(
                _publication_cli_error(exc),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 3
    except (DLPError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "cloud-v2-dlp-cli-error-v1",
                    "status": "failed",
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        _require_formal_dlp_bootstrap_context()
    except DLPError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    return _run_cli(argv)
