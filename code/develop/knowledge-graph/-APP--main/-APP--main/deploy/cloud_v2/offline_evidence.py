#!/usr/bin/env python3
"""Build deterministic, zero-network evidence for the pre-Stop-B candidate."""

from __future__ import annotations

import argparse
import ast
import base64
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
import contextlib
import csv
import ctypes
from datetime import datetime
import errno
import fcntl
from functools import partial
import hashlib
import hmac
import io
import importlib.machinery
import importlib.metadata
import json
import math
import os
import re
import select
import signal
import shutil
import socket
import stat
import struct
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import types
import unicodedata
import unittest
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

DISCLOSURE_EVIDENCE_SCHEMA_VERSION = "cloud-v2-offline-disclosure-evidence-v1"
TEST_COMPONENT_SET_SCHEMA_VERSION = "cloud-v2-offline-test-component-set-v8"
TEST_RECEIPT_SCHEMA_VERSION = "cloud-v2-offline-test-receipt-v8"
_DEFAULT_JSON_MAX_BYTES = 16 * 1024 * 1024
_TEST_COMPONENT_SET_MAX_BYTES = 64 * 1024 * 1024
_TEST_RECEIPT_MAX_BYTES = 64 * 1024 * 1024
_BROKER_FRAME_MAX_BYTES = 32 * 1024 * 1024
_BROKER_STDOUT_MAX_BYTES = 23 * 1024 * 1024
_BROKER_STDERR_MAX_BYTES = 4 * 1024 * 1024
_BROKER_TOTAL_OUTPUT_MAX_BYTES = 23 * 1024 * 1024
_BROKER_RESPONSE_ENVELOPE_MAX_BYTES = 64 * 1024
_BROKER_BASE64_OUTPUT_MAX_BYTES = (
    4 * ((_BROKER_TOTAL_OUTPUT_MAX_BYTES + 2) // 3) + 4
)
_PARENT_PROBE_OUTPUT_MAX_BYTES = 24 * 1024 * 1024
_PARENT_WORKER_ERROR_MAX_BYTES = 4096
if (
    _BROKER_BASE64_OUTPUT_MAX_BYTES + _BROKER_RESPONSE_ENVELOPE_MAX_BYTES
    > _BROKER_FRAME_MAX_BYTES
):
    raise RuntimeError("parent broker output budgets exceed the frame envelope")
TEST_RUNNER_SCHEMA_VERSION = "cloud-v2-offline-test-runner-v8"
NETWORK_POLICY_SCHEMA_VERSION = "cloud-v2-network-policy-v3"
NETWORK_ENFORCEMENT_SCHEMA_VERSION = "cloud-v2-network-enforcement-v1"
SANDBOX_ENFORCEMENT_SCHEMA_VERSION = "cloud-v2-sandbox-enforcement-v1"
TEST_PROCESS_RESULT_SCHEMA_VERSION = "cloud-v2-test-process-result-v5"
PARENT_PROBE_RESULT_SCHEMA_VERSION = "cloud-v2-parent-formal-probe-result-v2"
PARENT_PROBE_RECORD_SCHEMA_VERSION = "cloud-v2-formal-parent-probe-record-v2"
PARENT_BROKER_PROTOCOL_SCHEMA_VERSION = "cloud-v2-parent-broker-protocol-v4"
PARENT_BROKER_TRANSCRIPT_SCHEMA_VERSION = "cloud-v2-parent-broker-transcript-v7"
PARENT_WORKER_SANDBOX_SCHEMA_VERSION = "cloud-v2-parent-worker-sandbox-v1"
PARENT_WORKER_LAUNCH_SCHEMA_VERSION = "cloud-v2-parent-worker-launch-v4"
TEST_SCOPE_SCHEMA_VERSION = "cloud-v2-offline-test-scope-v2"
RUNTIME_ENVIRONMENT_SCHEMA_VERSION = "cloud-v2-runtime-environment-v4"
MODULE_ORIGIN_LEDGER_SCHEMA_VERSION = "cloud-v2-module-origin-ledger-v1"
NETWORK_SANDBOX_PROFILE = "(version 1)(allow default)(deny network*)"
CHILD_FILESYSTEM_SANDBOX_TEMPLATE = (
    "(version 1)(allow default)(deny network*)"
    "(deny file-read*)(allow file-read* <bound-read-closure>)"
    "(deny file-write*)(allow file-write* (literal \"/dev/null\") "
    "(subpath \"<component-scratch>\"))"
    "(deny process-exec*)(allow process-exec <bound-exec-closure>)"
)
PARENT_WORKER_SANDBOX_TEMPLATE = (
    "(version 1)(allow default)(deny network*)"
    "(deny file-read*)(allow file-read* <bound-read-closure>)"
    "(deny file-write*)(allow file-write* (literal \"/dev/null\") "
    "(subpath \"<parent-worker-scratch>\"))"
    "(deny process-exec*)(allow process-exec <bound-python-executables>)"
)
NETWORK_SANDBOX_PATH = Path("/usr/bin/sandbox-exec")
_DARWIN_DESCRIPTOR_ALIAS_READ_SUBPATHS = (Path("/dev/fd"),)
_DARWIN_SYSTEM_VERSION_FILE = Path(
    "/System/Library/CoreServices/SystemVersion.plist"
)
_INHERITED_COMPONENT_SANDBOX_ENV = "KG_STOP_B_INHERITED_COMPONENT_SANDBOX"
_PRODUCTION_EMBEDDING_FIXTURE_ENV = (
    "KG_TEST_PRODUCTION_EMBEDDING_WHEELHOUSE",
    "KG_TEST_PRODUCTION_EMBEDDING_INSTALLER_PYTHON",
    "KG_TEST_PRODUCTION_EMBEDDING_INSTALLER_SHA256",
)
_PRODUCTION_EMBEDDING_SCRATCH_ENV = (
    "KG_TEST_PRODUCTION_EMBEDDING_SCRATCH_ROOT"
)
_PRODUCTION_EMBEDDING_PROBE_ID = "production-embedding-runtime-smoke"
_PRODUCTION_EMBEDDING_TEST_ID = (
    "test_production_embedding_candidate.ProductionEmbeddingCandidateTests."
    "test_empty_copied_no_pip_venv_capture_verify_smoke"
)
_PRODUCTION_EMBEDDING_TARGET_RELATIVE = (
    "empty-copied-runtime-venv/bin/python"
)
_OCR_TESSDATA_ENV = "KG_CLOUD_V2_TEST_TESSDATA_DIR"
_OCR_TESSDATA_SNAPSHOT_NAMES = (
    "chi_sim.traineddata",
    "eng.traineddata",
)
_OCR_TESSDATA_EXPECTED_SHA256 = {
    "chi_sim.traineddata": (
        "a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730"
    ),
    "eng.traineddata": (
        "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
    ),
}
_REAL_OCR_PROBE_ID = "real-ocr-native-runtime"
_REAL_OCR_TEST_ID = (
    "test_source_extract.SourceExtractRealIntegrationTests."
    "test_real_ten_page_ocr_uses_four_workers_and_private_native_runtime"
)
_REAL_PAGE_132_PROBE_ID = "real-page-132-private-font-render"
_REAL_PAGE_132_TEST_ID = (
    "test_source_extract.SourceExtractRealIntegrationTests."
    "test_real_page_132_private_font_render_matches_approved_hash"
)
_OCR_NATIVE_PROBE_IDS = frozenset(
    {_REAL_OCR_PROBE_ID, _REAL_PAGE_132_PROBE_ID}
)
_OCR_PAGE_132_SOURCE_RELATIVE = (
    "knowledge_base/无人机理论书籍/"
    "2021_民用无人机安全飞行基础_清华大学出版社_史彦斌.pdf"
)
_OCR_PAGE_132_INPUT_ANCHOR = {
    "size": 29_440_121,
    "sha256": "af637911542156a1b4b0426005f672e6fe35d4e7b255482b28ad907c42564dbd",
}
_OCR_PAGE_132_OUTPUT_ANCHOR = {
    "page_number": 132,
    "size": 45_170,
    "sha256": "c991f990c828ef6c95e77b5231c2c1059ff58dbaf1bcff5ea4f209c582d72619",
}


def _is_ocr_native_probe(probe_id: object) -> bool:
    return type(probe_id) is str and probe_id in _OCR_NATIVE_PROBE_IDS


def _is_ocr_tessdata_probe(probe_id: object) -> bool:
    return probe_id == _REAL_OCR_PROBE_ID


_OCR_NATIVE_TOOL_SEARCH_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
_OCR_POPPLER_FALLBACK_FONT_PATH = Path(
    "/System/Library/Fonts/Supplemental/Songti.ttc"
)
_OCR_POPPLER_FONTCONFIG_FILES = (
    {
        "relative_path": "fontconfig/Songti.ttc",
        "mode": 0o400,
        "size": 66_933_080,
        "sha256": "6873ac2ccab5c2e74d87d6b690f3773098dd6a6238805363a3b3567f2caf6f47",
    },
    {
        "relative_path": "fontconfig/fonts.conf",
        "mode": 0o400,
        "size": 82,
        "sha256": "785951929a30ee23e9fbd2d804651e71386721461883d61b59e2a50951f35004",
    },
)
_OCR_NATIVE_INPUT_MAX_BYTES = 16 * 1024 * 1024
_OCR_NATIVE_WORKER_LIMIT = 4
_OCR_NATIVE_BATCH_SIZES = (4, 4, 2)
_OCR_FIXED_FIXTURE_ANCHORS = {
    "pdf": {
        "size": 18033,
        "sha256": "a5db88003c282490f613f6816104f54e4be53bdcfc5be768b42d12ebbc1310fc",
    },
    "executables": {
        "pdftoppm": "504dd5b6efe73d7d23bc04c90d2cfd75962b8893df95de6db7f45ab54bf47fc1",
        "tesseract": "6855d30ee1e9e97de11a58624973d2c7eb115a050df64fc3ba88b4077e153997",
    },
    "rendered_pages": [
        {"page_number": 1, "size": 16842, "sha256": "6289c2705fc77c5cf87d402e72f3723bea1e47146d7a16768a9d6324304797c2"},
        {"page_number": 2, "size": 23039, "sha256": "33c0d5d7806ff243534ee5047a6d14a19fab79479a5a415aa5d0cc9fd60b5180"},
        {"page_number": 3, "size": 29137, "sha256": "5f96fe607f2825521489fa53e107698528cec7fcdb26692251e4a57708b7052e"},
        {"page_number": 4, "size": 35485, "sha256": "fbd6e0bd62cf2d2d68a4e3bc60a421e17ef608ebd93a15057950526b064ee358"},
        {"page_number": 5, "size": 41759, "sha256": "20599862d928d7a69725a03c879c3b9237091aecb2b956848f93dc2cd9239efd"},
        {"page_number": 6, "size": 48055, "sha256": "65fcb63cb60af4b896c3eb8ba595cdf3048a0933514b60c4a5a3b4574e66971a"},
        {"page_number": 7, "size": 54336, "sha256": "772982b5d9cbc44a4ce3cbd7feb75959270e0925e6752c7e5a4310b38eed2525"},
        {"page_number": 8, "size": 60666, "sha256": "66cce4f7af6fcfbbdf9f6639fc741753f59b3265d975804d5301e4d63b47d139"},
        {"page_number": 9, "size": 66856, "sha256": "8a78c174e5df790c1aa553c0f755fa5602c53ce3c512f136e027972b9cff57d2"},
        {"page_number": 10, "size": 72958, "sha256": "ab140308aa3c73c7a92be6613c439cc69dd6a4ba672d0f91eb5f15d619f0b22d"},
    ],
    "stdout": [
        {"page_number": 1, "size": 6, "sha256": "c8eac3e7c6d3baf348fe723015ce6a34c332c65d9dfcd3a1c2729ce962b64ce9"},
        {"page_number": 2, "size": 11, "sha256": "9cfdf45c1e44837ba0514e3bc22fd2bd215997bf5d8de183744bcd0af14f9007"},
        {"page_number": 3, "size": 16, "sha256": "4f2daa266b889b874eb67b4a772a21d585db6bf5d65285e4821762c5d68cb638"},
        {"page_number": 4, "size": 23, "sha256": "5ea25442f2f8deea1a3186847363e3c76545e3708733bcb136880c656c5386aa"},
        {"page_number": 5, "size": 28, "sha256": "2255ea675a0a5d6d1b31467ecca1991edfdbb4b61db9d2778f459930be4c74d1"},
        {"page_number": 6, "size": 34, "sha256": "5f00535e927a1506cb2b4b2334599bddaf9794a3324f86d33c6dde64c2af769f"},
        {"page_number": 7, "size": 41, "sha256": "5d5179d62fde427eed4bee9855d0dd79555cee14fb2c3d6a76906a7fede4129f1"},
        {"page_number": 8, "size": 44, "sha256": "d91175b579f33b94604baf8982a29cf1909586ce7770e84237054693e77f7d34"},
        {"page_number": 9, "size": 50, "sha256": "6cc479f23e52ac62e8d81388febfaca6106c8f6408947e435912d9b52a96d40f"},
        {"page_number": 10, "size": 55, "sha256": "a8ebe07d3b2a3f54e22f1c1a9b31f8bed1d8e1d1aa86864b0247e3991fc70b8f"},
    ],
}
_OCR_NATIVE_PARAMETER_FIELDS = {
    "kind",
    "tool",
    "containment_relative",
    "native_runtime_relative",
    "private_executable_relative",
    "private_library_relative",
    "private_fontconfig_relative",
    "scratch_relative",
    "output_prefix_relative",
    "approved_page_relative",
    "private_tessdata_relative",
    "page_number",
    "profile_base64",
    "profile_size",
    "profile_sha256",
    "environment",
    "environment_sha256",
    "stdin_role",
    "input_delivery",
    "input_base64",
    "input_snapshot_relative",
    "input_size",
    "input_sha256",
    "timeout_seconds",
    "capture_mode",
}
_OCR_NATIVE_OPERATION_EXTRA_FIELDS = {
    "profile_delivery",
    "input_identity",
    "native_runtime_identity",
    "page_identity",
    "private_tessdata_identity",
    "output_identity",
    "sealed_tessdata_snapshot_identity_sha256",
    "process_timing",
    "execution_slot",
}
_DISCLOSURE_SUBPROCESS_TIMEOUT_SECONDS = 60.0
_FORMAL_VALIDATION_TIMEOUT_SECONDS = 900.0
_FORMAL_VALIDATION_OUTPUT_MAX_BYTES = 16 * 1024 * 1024
FORMAL_CLI_BOOTSTRAP = """\
import base64
import hashlib
import json
import os
import stat
import sys
import sysconfig
import types
import unicodedata
from pathlib import Path

EXPECTED_CLOSURE = (
    ("deploy.cloud_v2.source_scope", "deploy/cloud_v2/source_scope.py"),
    ("deploy.cloud_v2.source_extract", "deploy/cloud_v2/source_extract.py"),
    ("deploy.cloud_v2.authority_builder", "deploy/cloud_v2/authority_builder.py"),
    ("deploy.rag_store.embedding_adapter", "deploy/rag_store/embedding_adapter.py"),
    ("deploy.rag_store.local_vector_store", "deploy/rag_store/local_vector_store.py"),
    ("deploy.rag_store.server_answer_model", "deploy/rag_store/server_answer_model.py"),
    ("deploy.rag_store.server_answer_coordinator", "deploy/rag_store/server_answer_coordinator.py"),
    ("deploy.cloud_v2.fake_providers", "deploy/cloud_v2/fake_providers.py"),
    ("deploy.rag_store.scoped_graph_contract", "deploy/rag_store/scoped_graph_contract.py"),
    ("deploy.cloud_v2.graph_builder", "deploy/cloud_v2/graph_builder.py"),
    ("deploy.cloud_v2.candidate_builder", "deploy/cloud_v2/candidate_builder.py"),
    ("deploy.cloud_v2.offline_evidence", "deploy/cloud_v2/offline_evidence.py"),
    ("deploy.cloud_v2.dlp", "deploy/cloud_v2/dlp.py"),
    ("deploy.rag_store.runtime_sqlite_reader", "deploy/rag_store/runtime_sqlite_reader.py"),
    ("deploy.cloud_v2.stop_b_request", "deploy/cloud_v2/stop_b_request.py"),
    ("deploy.cloud_v2.artifact_builder", "deploy/cloud_v2/artifact_builder.py"),
    ("deploy.cloud_v2.stop_b_handoff", "deploy/cloud_v2/stop_b_handoff.py"),
    ("deploy.cloud_v2.stop_b_probe", "deploy/cloud_v2/stop_b_probe.py"),
    ("deploy.rag_store.neo4j_graph_importer", "deploy/rag_store/neo4j_graph_importer.py"),
    ("deploy.rag_store.runtime_neo4j_reader", "deploy/rag_store/runtime_neo4j_reader.py"),
    ("cloud_gold", "skills/knowledge-graph-cloud/scripts/cloud_gold.py"),
    ("eval_cloud_subset", "skills/knowledge-graph-cloud/scripts/eval_cloud_subset.py"),
    ("deploy.pipeline.neo4j_import_candidate", "deploy/pipeline/neo4j_import_candidate.py"),
)
SNAPSHOT_PACKAGE_ANCHORS = {
    "deploy/__init__.py": b'"' * 3 + b"Sealed offline-test package anchor." + b'"' * 3 + bytes((10,)),
    "deploy/pipeline/__init__.py": b'"' * 3 + b"Sealed offline-test package anchor." + b'"' * 3 + bytes((10,)),
    "deploy/rag_store/__init__.py": b'"' * 3 + b"Sealed offline-test package anchor." + b'"' * 3 + bytes((10,)),
}
FORMAL_SOURCE_CONTEXT_SCHEMA_VERSION = "cloud-v2-formal-source-context-v1"

def fail(message):
    sys.stderr.write(message + "\\n")
    raise SystemExit(2)

def is_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )

inactive = [
    name
    for name, active in (
        ("isolated", sys.flags.isolated == 1),
        ("no_site", sys.flags.no_site == 1),
        ("dont_write_bytecode", sys.flags.dont_write_bytecode == 1),
    )
    if not active
]
if inactive:
    fail("formal CLI requires Python -I -S -B; inactive: " + ",".join(inactive))
if len(sys.argv) < 5:
    fail("formal CLI bootstrap binding is incomplete")

def state_identity(value):
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "mode": value.st_mode,
        "nlink": value.st_nlink,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }

def checked_names(descriptor, field):
    try:
        names = tuple(os.listdir(descriptor))
    except OSError:
        fail(field + " could not be inspected safely")
    folded = {}
    for name in names:
        if (
            not isinstance(name, str)
            or unicodedata.normalize("NFC", name) != name
            or any(
                unicodedata.category(character) in {"Cc", "Cf", "Cs"}
                for character in name
            )
        ):
            fail(field + " contains a non-canonical name")
        key = unicodedata.normalize("NFC", name).casefold()
        if key in folded:
            fail(field + " contains a case or Unicode alias collision")
        folded[key] = name
    return names, folded

def open_directory(parent, name, field):
    names, folded = checked_names(parent, field + " parent")
    if name not in names or folded.get(name.casefold()) != name:
        fail(field + " is missing or aliased")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        child = os.open(name, flags, dir_fd=parent)
        after = os.fstat(child)
    except OSError:
        fail(field + " could not be opened safely")
    if not stat.S_ISDIR(after.st_mode) or state_identity(before) != state_identity(after):
        os.close(child)
        fail(field + " changed while it was opened")
    return child

def stable_module_bytes(root_descriptor, relative, expected_binding):
    parts = relative.split("/")
    if (
        not parts
        or any(not part or part in {".", ".."} for part in parts)
        or "/".join(parts) != relative
    ):
        fail("formal CLI module path is malformed")
    parent = os.dup(root_descriptor)
    try:
        for index, component in enumerate(parts[:-1]):
            child = open_directory(
                parent,
                component,
                "formal CLI module directory " + "/".join(parts[: index + 1]),
            )
            os.close(parent)
            parent = child
        name = parts[-1]
        names, folded = checked_names(parent, "formal CLI module parent")
        if name not in names or folded.get(name.casefold()) != name:
            fail("formal CLI module is missing or aliased: " + relative)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            descriptor = os.open(name, flags, dir_fd=parent)
            opened = os.fstat(descriptor)
        except OSError:
            fail("formal CLI module could not be opened safely: " + relative)
        try:
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or state_identity(before) != state_identity(opened)
                or state_identity(opened)
                != {key: expected_binding[key] for key in state_identity(opened)}
            ):
                fail("formal CLI module identity changed: " + relative)
            chunks = []
            offset = 0
            while offset < opened.st_size:
                block = os.pread(
                    descriptor,
                    min(1024 * 1024, opened.st_size - offset),
                    offset,
                )
                if not block:
                    fail("formal CLI module became shorter: " + relative)
                chunks.append(block)
                offset += len(block)
            payload = b"".join(chunks)
            if state_identity(os.fstat(descriptor)) != state_identity(opened):
                fail("formal CLI module changed while reading: " + relative)
            if hashlib.sha256(payload).hexdigest() != expected_binding["sha256"]:
                fail("formal CLI module bytes changed: " + relative)
            return payload
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)

def require_exact_anchor(root_descriptor, relative, expected_payload):
    parts = relative.split("/")
    parent = os.dup(root_descriptor)
    try:
        for index, component in enumerate(parts[:-1]):
            child = open_directory(
                parent,
                component,
                "formal CLI snapshot package anchor directory " + "/".join(parts[: index + 1]),
            )
            os.close(parent)
            parent = child
        name = parts[-1]
        names, folded = checked_names(parent, "formal CLI snapshot package anchor parent")
        if name not in names or folded.get(name.casefold()) != name:
            fail("formal CLI snapshot package anchor is missing or aliased: " + relative)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            descriptor = os.open(name, flags, dir_fd=parent)
            opened = os.fstat(descriptor)
        except OSError:
            fail("formal CLI snapshot package anchor could not be opened safely: " + relative)
        try:
            if (
                not stat.S_ISREG(opened.st_mode)
                or stat.S_IMODE(opened.st_mode) != 0o400
                or opened.st_nlink != 1
                or state_identity(before) != state_identity(opened)
            ):
                fail("formal CLI snapshot package anchor identity changed: " + relative)
            chunks = []
            offset = 0
            while offset < opened.st_size:
                block = os.pread(
                    descriptor,
                    min(1024 * 1024, opened.st_size - offset),
                    offset,
                )
                if not block:
                    fail("formal CLI snapshot package anchor became shorter: " + relative)
                chunks.append(block)
                offset += len(block)
            payload = b"".join(chunks)
            if state_identity(os.fstat(descriptor)) != state_identity(opened):
                fail("formal CLI snapshot package anchor changed while reading: " + relative)
            if payload != expected_payload:
                fail("formal CLI snapshot package anchor byte identity mismatch: " + relative)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)

try:
    manifest_payload = base64.b64decode(sys.argv[2], validate=True)
    manifest = json.loads(manifest_payload.decode("utf-8"))
except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
    fail("formal CLI closure manifest is malformed")
canonical_manifest = (
    json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    + "\\n"
).encode("utf-8")
if (
    manifest_payload != canonical_manifest
    or base64.b64encode(manifest_payload).decode("ascii") != sys.argv[2]
    or not isinstance(manifest, dict)
):
    fail("formal CLI closure manifest is not canonical")
if set(manifest) != {"schema_version", "modules"}:
    fail("formal CLI closure manifest schema is closed")
if manifest["schema_version"] != "cloud-v2-formal-bootstrap-closure-v1":
    fail("formal CLI closure manifest schema mismatch")
modules = manifest["modules"]
if not isinstance(modules, list) or len(modules) != len(EXPECTED_CLOSURE):
    fail("formal CLI closure coverage is not exact")
for record, expected in zip(modules, EXPECTED_CLOSURE):
    if (
        not isinstance(record, dict)
        or set(record) != {"module", "path", "binding"}
        or (record["module"], record["path"]) != expected
        or not isinstance(record["binding"], dict)
        or set(record["binding"])
        != {"device", "inode", "mode", "nlink", "size", "mtime_ns", "ctime_ns", "sha256"}
    ):
        fail("formal CLI closure record is malformed")

try:
    source_context_payload = base64.b64decode(sys.argv[3], validate=True)
    source_context = json.loads(source_context_payload.decode("utf-8"))
except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
    fail("formal CLI source context is malformed")
canonical_source_context = (
    json.dumps(
        source_context,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    + "\\n"
).encode("utf-8")
if (
    source_context_payload != canonical_source_context
    or base64.b64encode(source_context_payload).decode("ascii") != sys.argv[3]
    or not isinstance(source_context, dict)
):
    fail("formal CLI source context is not canonical")
if set(source_context) != {
    "schema_version",
    "source_kind",
    "held_root_identity",
    "closure_manifest_sha256",
    "package_anchors_sha256",
}:
    fail("formal CLI source context schema is closed")
if source_context["schema_version"] != FORMAL_SOURCE_CONTEXT_SCHEMA_VERSION:
    fail("formal CLI source context schema mismatch")
source_kind = source_context["source_kind"]
if source_kind not in {"live-repository", "materialized-snapshot"}:
    fail("formal CLI source kind is not allowlisted")
held_root_identity = source_context["held_root_identity"]
if (
    not isinstance(held_root_identity, list)
    or len(held_root_identity) != 3
    or any(type(value) is not int or value < 0 for value in held_root_identity)
    or held_root_identity[1] == 0
    or held_root_identity[2] != stat.S_IFDIR
):
    fail("formal CLI held root identity is malformed")
if (
    not is_sha256(source_context["closure_manifest_sha256"])
    or source_context["closure_manifest_sha256"]
    != hashlib.sha256(manifest_payload).hexdigest()
):
    fail("formal CLI closure manifest binding mismatch")
anchor_records = [
    {
        "path": relative,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    for relative, payload in sorted(SNAPSHOT_PACKAGE_ANCHORS.items())
]
canonical_anchor_records = (
    json.dumps(
        anchor_records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    + "\\n"
).encode("utf-8")
if (
    not is_sha256(source_context["package_anchors_sha256"])
    or source_context["package_anchors_sha256"]
    != hashlib.sha256(canonical_anchor_records).hexdigest()
):
    fail("formal CLI package anchor binding mismatch")
if source_kind == "live-repository" and sys.argv[4] == "formal-parent-probe-worker":
    fail("formal parent probe worker requires a materialized snapshot")
if source_kind == "materialized-snapshot" and sys.argv[4] != "formal-parent-probe-worker":
    fail("materialized formal source only permits the parent probe worker")

root_arg = Path(sys.argv[1])
root_flags = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
try:
    root_fd = os.open(root_arg, root_flags)
    root_state = os.fstat(root_fd)
except OSError:
    fail("repository root must be a real directory")
if [
    root_state.st_dev,
    root_state.st_ino,
    stat.S_IFMT(root_state.st_mode),
] != held_root_identity:
    fail("formal CLI held root identity mismatch")
root_names, root_folded = checked_names(root_fd, "repository root")
if "deploy.py" in root_folded:
    fail("repository root contains a deploy.py import shadow")
if "deploy" not in root_names or root_folded.get("deploy") != "deploy":
    fail("repository deploy root is missing or aliased")
deploy_fd = open_directory(root_fd, "deploy", "repository deploy root")
_deploy_names, deploy_folded = checked_names(deploy_fd, "repository deploy root")
if source_kind == "materialized-snapshot":
    for relative, expected_payload in sorted(SNAPSHOT_PACKAGE_ANCHORS.items()):
        require_exact_anchor(root_fd, relative, expected_payload)
else:
    if "__init__.py" in deploy_folded:
        fail("repository root contains a deploy/__init__.py import shadow")
    for package in ("pipeline", "rag_store"):
        if package not in deploy_folded:
            continue
        package_fd = open_directory(deploy_fd, package, "repository deploy/" + package)
        try:
            _names, folded = checked_names(package_fd, "repository deploy/" + package)
            if "__init__.py" in folded:
                fail(
                    "repository deploy/"
                    + package
                    + "/__init__.py conflicts with the sealed package anchor"
                )
        finally:
            os.close(package_fd)

held_payloads = {}
held_bindings = {}
compiled = {}
for record in modules:
    payload = stable_module_bytes(root_fd, record["path"], record["binding"])
    held_payloads[record["module"]] = payload
    held_bindings[record["module"]] = record["binding"]
for module_name, relative in EXPECTED_CLOSURE:
    try:
        compiled[module_name] = compile(
            held_payloads[module_name],
            str(root_arg / relative),
            "exec",
            dont_inherit=True,
        )
    except (SyntaxError, ValueError, TypeError):
        fail("formal CLI module could not be compiled: " + relative)
try:
    current_root = os.stat(root_arg, follow_symlinks=False)
except OSError:
    fail("repository root changed before formal CLI execution")
if (
    current_root.st_dev,
    current_root.st_ino,
    stat.S_IFMT(current_root.st_mode),
) != (root_state.st_dev, root_state.st_ino, stat.S_IFMT(root_state.st_mode)):
    fail("repository root changed before formal CLI execution")

runtime_prefix = Path(sys.prefix).resolve(strict=True)
library_paths = []
for key in ("purelib", "platlib"):
    value = sysconfig.get_path(key)
    if not value:
        fail("isolated Python library path is unavailable")
    candidate = Path(value)
    if candidate.is_symlink():
        fail("isolated Python library path is a symlink")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(runtime_prefix)
    except ValueError:
        fail("isolated Python library path escapes its venv")
    if resolved not in library_paths:
        library_paths.append(resolved)
for entry in sys.path:
    if not entry:
        continue
    candidate = Path(entry)
    if candidate.exists() and candidate.resolve(strict=True).name in {"site-packages", "dist-packages"}:
        fail("unexpected preloaded Python library path")
sys.path.extend(str(path) for path in library_paths)

def namespace(name, path):
    module = types.ModuleType(name)
    module.__package__ = name
    module.__path__ = [str(path)]
    sys.modules[name] = module
    return module

deploy_package = namespace("deploy", root_arg / "deploy")
cloud_package = namespace("deploy.cloud_v2", root_arg / "deploy/cloud_v2")
rag_package = namespace("deploy.rag_store", root_arg / "deploy/rag_store")
pipeline_package = namespace("deploy.pipeline", root_arg / "deploy/pipeline")
deploy_package.cloud_v2 = cloud_package
deploy_package.rag_store = rag_package
deploy_package.pipeline = pipeline_package
package_modules = {
    "deploy.cloud_v2": cloud_package,
    "deploy.rag_store": rag_package,
    "deploy.pipeline": pipeline_package,
}
loaded = {}
for module_name, relative in EXPECTED_CLOSURE:
    module = types.ModuleType(module_name)
    module.__file__ = str(root_arg / relative)
    module.__spec__ = None
    sys.modules[module_name] = module
    if "." in module_name:
        package_name, attribute = module_name.rsplit(".", 1)
        if package_name not in package_modules:
            fail("formal CLI module package is not allowlisted")
        module.__package__ = package_name
        setattr(package_modules[package_name], attribute, module)
    else:
        module.__package__ = ""
    loaded[module_name] = module
sys.modules["rag_store"] = rag_package
for attribute in (
    "neo4j_graph_importer",
    "runtime_neo4j_reader",
    "runtime_sqlite_reader",
    "scoped_graph_contract",
):
    target = loaded["deploy.rag_store." + attribute]
    sys.modules["rag_store." + attribute] = target
for module_name, _relative in EXPECTED_CLOSURE:
    exec(compiled[module_name], loaded[module_name].__dict__)
evidence = loaded["deploy.cloud_v2.offline_evidence"]
runner_binding = held_bindings["deploy.cloud_v2.offline_evidence"]
evidence._FORMAL_REPOSITORY_IDENTITY = (
    root_state.st_dev,
    root_state.st_ino,
    stat.S_IFMT(root_state.st_mode),
)
evidence._FORMAL_MATERIALIZED_SNAPSHOT_IDENTITY = None
evidence._EXECUTED_RUNNER_SOURCE_SHA256 = runner_binding["sha256"]
evidence._EXECUTED_RUNNER_STATE_IDENTITY = {
    key: runner_binding[key]
    for key in ("device", "inode", "mode", "nlink", "size", "mtime_ns", "ctime_ns")
}
authority = loaded["deploy.cloud_v2.authority_builder"]
authority_binding = held_bindings["deploy.cloud_v2.authority_builder"]
candidate = loaded["deploy.cloud_v2.candidate_builder"]
candidate_binding = held_bindings["deploy.cloud_v2.candidate_builder"]
dlp = loaded["deploy.cloud_v2.dlp"]
dlp_binding = held_bindings["deploy.cloud_v2.dlp"]
artifact = loaded["deploy.cloud_v2.artifact_builder"]
artifact_binding = held_bindings["deploy.cloud_v2.artifact_builder"]
handoff = loaded["deploy.cloud_v2.stop_b_handoff"]
handoff_binding = held_bindings["deploy.cloud_v2.stop_b_handoff"]
probe = loaded["deploy.cloud_v2.stop_b_probe"]
probe_binding = held_bindings["deploy.cloud_v2.stop_b_probe"]
gold = loaded["cloud_gold"]
gold_binding = held_bindings["cloud_gold"]
cloud80 = loaded["eval_cloud_subset"]
cloud80_binding = held_bindings["eval_cloud_subset"]
neo4j_import = loaded["deploy.pipeline.neo4j_import_candidate"]
neo4j_import_binding = held_bindings["deploy.pipeline.neo4j_import_candidate"]
try:
    evidence._install_formal_test_evidence_bootstrap_context()
    authority._install_formal_authority_builder_bootstrap_context(
        authority_binding
    )
    candidate._install_formal_candidate_builder_bootstrap_context(
        candidate_binding
    )
    dlp._install_formal_dlp_bootstrap_context(dlp_binding)
    artifact._install_formal_artifact_builder_bootstrap_context(artifact_binding)
    handoff._install_formal_stop_b_handoff_bootstrap_context(handoff_binding)
    probe._install_formal_stop_b_probe_bootstrap_context(probe_binding)
    gold._install_formal_cloud_gold_bootstrap_context(gold_binding)
    cloud80._install_formal_cloud80_bootstrap_context(cloud80_binding)
    neo4j_import._install_formal_neo4j_import_bootstrap_context(
        neo4j_import_binding
    )
except Exception as exc:
    fail(str(exc))
# Module execution and bootstrap-context installation may run arbitrary held
# module code. Re-open every declared path against its original state binding
# before dispatch so a same-inode mutate/restore cannot escape the initial hold.
for record in modules:
    payload = stable_module_bytes(root_fd, record["path"], record["binding"])
    if payload != held_payloads[record["module"]]:
        fail("formal CLI module bytes changed before dispatch: " + record["path"])
try:
    current_root = os.stat(root_arg, follow_symlinks=False)
except OSError:
    fail("repository root changed before formal CLI dispatch")
if (
    current_root.st_dev,
    current_root.st_ino,
    stat.S_IFMT(current_root.st_mode),
) != (
    root_state.st_dev,
    root_state.st_ino,
    stat.S_IFMT(root_state.st_mode),
):
    fail("repository root changed before formal CLI dispatch")
os.close(deploy_fd)
sys.argv = [str(root_arg / "deploy/cloud_v2/offline_evidence.py"), *sys.argv[4:]]
raise SystemExit(evidence.main())
"""
_UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_UNITTEST_SUMMARY = re.compile(r"(?m)^Ran ([1-9][0-9]*) tests? in [0-9]+(?:\.[0-9]+)?s$")
_FAILURE_MARKER = re.compile(
    r"(?m)(?<!\S)(?:FAIL(?:ED)?|ERROR)(?=\s|\(|:|$)"
)
# macOS exposes these fixed root aliases. Expand only these spellings
# lexically; resolving an arbitrary caller-controlled path before descriptor
# traversal would follow a symlink inserted between inspection and resolve.
_SYSTEM_PATH_ALIAS_TARGETS = {
    Path("/var"): Path("/private/var"),
    Path("/tmp"): Path("/private/tmp"),
    Path("/etc"): Path("/private/etc"),
}
_STICKY_TRANSIT_PATHS = {Path("/tmp"), Path("/private/tmp")}
DISCLOSURE_SOURCE_PATHS = (
    "deploy/cloud_v2/fake_providers.py",
    "deploy/cloud_v2/offline_evidence.py",
    "deploy/rag_store/server_answer_coordinator.py",
    "deploy/rag_store/server_answer_model.py",
)
OFFLINE_EVIDENCE_SOURCE_PATH = "deploy/cloud_v2/offline_evidence.py"
FORMAL_SOURCE_CONTEXT_SCHEMA_VERSION = "cloud-v2-formal-source-context-v1"
_FORMAL_MODULE_CLOSURE = (
    ("deploy.cloud_v2.source_scope", "deploy/cloud_v2/source_scope.py"),
    ("deploy.cloud_v2.source_extract", "deploy/cloud_v2/source_extract.py"),
    ("deploy.cloud_v2.authority_builder", "deploy/cloud_v2/authority_builder.py"),
    ("deploy.rag_store.embedding_adapter", "deploy/rag_store/embedding_adapter.py"),
    (
        "deploy.rag_store.local_vector_store",
        "deploy/rag_store/local_vector_store.py",
    ),
    ("deploy.rag_store.server_answer_model", "deploy/rag_store/server_answer_model.py"),
    (
        "deploy.rag_store.server_answer_coordinator",
        "deploy/rag_store/server_answer_coordinator.py",
    ),
    ("deploy.cloud_v2.fake_providers", "deploy/cloud_v2/fake_providers.py"),
    (
        "deploy.rag_store.scoped_graph_contract",
        "deploy/rag_store/scoped_graph_contract.py",
    ),
    ("deploy.cloud_v2.graph_builder", "deploy/cloud_v2/graph_builder.py"),
    ("deploy.cloud_v2.candidate_builder", "deploy/cloud_v2/candidate_builder.py"),
    ("deploy.cloud_v2.offline_evidence", OFFLINE_EVIDENCE_SOURCE_PATH),
    ("deploy.cloud_v2.dlp", "deploy/cloud_v2/dlp.py"),
    (
        "deploy.rag_store.runtime_sqlite_reader",
        "deploy/rag_store/runtime_sqlite_reader.py",
    ),
    ("deploy.cloud_v2.stop_b_request", "deploy/cloud_v2/stop_b_request.py"),
    ("deploy.cloud_v2.artifact_builder", "deploy/cloud_v2/artifact_builder.py"),
    ("deploy.cloud_v2.stop_b_handoff", "deploy/cloud_v2/stop_b_handoff.py"),
    ("deploy.cloud_v2.stop_b_probe", "deploy/cloud_v2/stop_b_probe.py"),
    (
        "deploy.rag_store.neo4j_graph_importer",
        "deploy/rag_store/neo4j_graph_importer.py",
    ),
    (
        "deploy.rag_store.runtime_neo4j_reader",
        "deploy/rag_store/runtime_neo4j_reader.py",
    ),
    ("cloud_gold", "skills/knowledge-graph-cloud/scripts/cloud_gold.py"),
    (
        "eval_cloud_subset",
        "skills/knowledge-graph-cloud/scripts/eval_cloud_subset.py",
    ),
    (
        "deploy.pipeline.neo4j_import_candidate",
        "deploy/pipeline/neo4j_import_candidate.py",
    ),
)
_FORMAL_MODULE_ORIGIN_ALIASES = {
    "rag_store.neo4j_graph_importer": "deploy.rag_store.neo4j_graph_importer",
    "rag_store.runtime_neo4j_reader": "deploy.rag_store.runtime_neo4j_reader",
    "rag_store.runtime_sqlite_reader": "deploy.rag_store.runtime_sqlite_reader",
    "rag_store.scoped_graph_contract": "deploy.rag_store.scoped_graph_contract",
}
_CHILD_HELD_CLOSURE_BOOTSTRAP = """\
import base64
import hashlib
import json
import os
import stat
import sys
import sysconfig
import types
import unicodedata
from pathlib import Path

EXPECTED_CLOSURE = (
    ("deploy.cloud_v2.source_scope", "deploy/cloud_v2/source_scope.py"),
    ("deploy.cloud_v2.source_extract", "deploy/cloud_v2/source_extract.py"),
    ("deploy.cloud_v2.authority_builder", "deploy/cloud_v2/authority_builder.py"),
    ("deploy.rag_store.embedding_adapter", "deploy/rag_store/embedding_adapter.py"),
    ("deploy.rag_store.local_vector_store", "deploy/rag_store/local_vector_store.py"),
    ("deploy.rag_store.server_answer_model", "deploy/rag_store/server_answer_model.py"),
    ("deploy.rag_store.server_answer_coordinator", "deploy/rag_store/server_answer_coordinator.py"),
    ("deploy.cloud_v2.fake_providers", "deploy/cloud_v2/fake_providers.py"),
    ("deploy.rag_store.scoped_graph_contract", "deploy/rag_store/scoped_graph_contract.py"),
    ("deploy.cloud_v2.graph_builder", "deploy/cloud_v2/graph_builder.py"),
    ("deploy.cloud_v2.candidate_builder", "deploy/cloud_v2/candidate_builder.py"),
    ("deploy.cloud_v2.offline_evidence", "deploy/cloud_v2/offline_evidence.py"),
    ("deploy.cloud_v2.dlp", "deploy/cloud_v2/dlp.py"),
    ("deploy.rag_store.runtime_sqlite_reader", "deploy/rag_store/runtime_sqlite_reader.py"),
    ("deploy.cloud_v2.stop_b_request", "deploy/cloud_v2/stop_b_request.py"),
    ("deploy.cloud_v2.artifact_builder", "deploy/cloud_v2/artifact_builder.py"),
    ("deploy.cloud_v2.stop_b_handoff", "deploy/cloud_v2/stop_b_handoff.py"),
    ("deploy.cloud_v2.stop_b_probe", "deploy/cloud_v2/stop_b_probe.py"),
    ("deploy.rag_store.neo4j_graph_importer", "deploy/rag_store/neo4j_graph_importer.py"),
    ("deploy.rag_store.runtime_neo4j_reader", "deploy/rag_store/runtime_neo4j_reader.py"),
    ("cloud_gold", "skills/knowledge-graph-cloud/scripts/cloud_gold.py"),
    ("eval_cloud_subset", "skills/knowledge-graph-cloud/scripts/eval_cloud_subset.py"),
    ("deploy.pipeline.neo4j_import_candidate", "deploy/pipeline/neo4j_import_candidate.py"),
)

def fail(message):
    sys.stderr.write(message + "\\n")
    raise SystemExit(2)

inactive = [
    name
    for name, active in (
        ("isolated", sys.flags.isolated == 1),
        ("no_site", sys.flags.no_site == 1),
        ("dont_write_bytecode", sys.flags.dont_write_bytecode == 1),
    )
    if not active
]
if inactive:
    fail("formal CLI requires Python -I -S -B; inactive: " + ",".join(inactive))
if len(sys.argv) < 2:
    fail("child bootstrap binding is incomplete")

def state_identity(value):
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "mode": value.st_mode,
        "nlink": value.st_nlink,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }

def checked_names(descriptor, field):
    try:
        names = tuple(os.listdir(descriptor))
    except OSError:
        fail(field + " could not be inspected safely")
    folded = {}
    for name in names:
        if (
            not isinstance(name, str)
            or unicodedata.normalize("NFC", name) != name
            or any(
                unicodedata.category(character) in {"Cc", "Cf", "Cs"}
                for character in name
            )
        ):
            fail(field + " contains a non-canonical name")
        key = unicodedata.normalize("NFC", name).casefold()
        if key in folded:
            fail(field + " contains a case or Unicode alias collision")
        folded[key] = name
    return names, folded

def open_directory(parent, name, field):
    names, folded = checked_names(parent, field + " parent")
    if name not in names or folded.get(name.casefold()) != name:
        fail(field + " is missing or aliased")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        child = os.open(name, flags, dir_fd=parent)
        after = os.fstat(child)
    except OSError:
        fail(field + " could not be opened safely")
    if not stat.S_ISDIR(after.st_mode) or state_identity(before) != state_identity(after):
        os.close(child)
        fail(field + " changed while it was opened")
    return child

def stable_module_bytes(root_descriptor, relative, expected_binding):
    parts = relative.split("/")
    if (
        not parts
        or any(not part or part in {".", ".."} for part in parts)
        or "/".join(parts) != relative
    ):
        fail("child bootstrap module path is malformed")
    parent = os.dup(root_descriptor)
    try:
        for index, component in enumerate(parts[:-1]):
            child = open_directory(
                parent,
                component,
                "child bootstrap module directory " + "/".join(parts[: index + 1]),
            )
            os.close(parent)
            parent = child
        name = parts[-1]
        names, folded = checked_names(parent, "child bootstrap module parent")
        if name not in names or folded.get(name.casefold()) != name:
            fail("child bootstrap module is missing or aliased: " + relative)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            descriptor = os.open(name, flags, dir_fd=parent)
            opened = os.fstat(descriptor)
        except OSError:
            fail("child bootstrap module could not be opened safely: " + relative)
        try:
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or state_identity(before) != state_identity(opened)
                or state_identity(opened)
                != {key: expected_binding[key] for key in state_identity(opened)}
            ):
                fail("child bootstrap module identity changed: " + relative)
            chunks = []
            offset = 0
            while offset < opened.st_size:
                block = os.pread(
                    descriptor,
                    min(1024 * 1024, opened.st_size - offset),
                    offset,
                )
                if not block:
                    fail("child bootstrap module became shorter: " + relative)
                chunks.append(block)
                offset += len(block)
            payload = b"".join(chunks)
            if state_identity(os.fstat(descriptor)) != state_identity(opened):
                fail("child bootstrap module changed while reading: " + relative)
            if hashlib.sha256(payload).hexdigest() != expected_binding["sha256"]:
                fail("child bootstrap module bytes changed: " + relative)
            return payload
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)

try:
    manifest_payload = base64.b64decode(sys.argv[1], validate=True)
    manifest = json.loads(manifest_payload.decode("utf-8"))
except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
    fail("child bootstrap closure manifest is malformed")
canonical_manifest = (
    json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    + "\\n"
).encode("utf-8")
if (
    manifest_payload != canonical_manifest
    or base64.b64encode(manifest_payload).decode("ascii") != sys.argv[1]
    or not isinstance(manifest, dict)
):
    fail("child bootstrap closure manifest is not canonical")
if set(manifest) != {"schema_version", "modules"}:
    fail("child bootstrap closure manifest schema is closed")
if manifest["schema_version"] != "cloud-v2-child-bootstrap-closure-v1":
    fail("child bootstrap closure manifest schema mismatch")
modules = manifest["modules"]
if not isinstance(modules, list) or len(modules) != len(EXPECTED_CLOSURE):
    fail("child bootstrap closure coverage is not exact")
for record, expected in zip(modules, EXPECTED_CLOSURE):
    if (
        not isinstance(record, dict)
        or set(record) != {"module", "path", "binding"}
        or (record["module"], record["path"]) != expected
        or not isinstance(record["binding"], dict)
        or set(record["binding"])
        != {"device", "inode", "mode", "nlink", "size", "mtime_ns", "ctime_ns", "sha256"}
    ):
        fail("child bootstrap closure record is malformed")

snapshot_root = Path.cwd().resolve(strict=True)
root_flags = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
try:
    root_fd = os.open(".", root_flags)
except OSError:
    fail("child bootstrap snapshot root is unavailable")
snapshot_root_state = os.fstat(root_fd)
root_names, root_folded = checked_names(root_fd, "child bootstrap snapshot root")
if "deploy.py" in root_folded:
    fail("child bootstrap snapshot contains a deploy.py import shadow")
if "deploy" not in root_names or root_folded.get("deploy") != "deploy":
    fail("child bootstrap deploy root is missing or aliased")

held_payloads = {}
held_bindings = {}
compiled = {}
for record in modules:
    payload = stable_module_bytes(root_fd, record["path"], record["binding"])
    held_payloads[record["module"]] = payload
    held_bindings[record["module"]] = record["binding"]
for module_name, relative in EXPECTED_CLOSURE:
    try:
        compiled[module_name] = compile(
            held_payloads[module_name],
            str(snapshot_root / relative),
            "exec",
            dont_inherit=True,
        )
    except (SyntaxError, ValueError, TypeError):
        fail("child bootstrap module could not be compiled: " + relative)
if state_identity(os.fstat(root_fd)) != state_identity(snapshot_root_state):
    fail("child bootstrap snapshot root changed while loading modules")
os.close(root_fd)

runtime_prefix = Path(sys.prefix).resolve(strict=True)
library_paths = []
for key in ("purelib", "platlib"):
    value = sysconfig.get_path(key)
    if not value:
        fail("isolated Python library path is unavailable")
    candidate = Path(value)
    if candidate.is_symlink():
        fail("isolated Python library path is a symlink")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(runtime_prefix)
    except ValueError:
        fail("isolated Python library path escapes its venv")
    if resolved not in library_paths:
        library_paths.append(resolved)
for entry in sys.path:
    if not entry:
        continue
    candidate = Path(entry)
    if candidate.exists() and candidate.resolve(strict=True).name in {"site-packages", "dist-packages"}:
        fail("unexpected preloaded Python library path")
sys.path.extend(str(path) for path in library_paths)

def namespace(name, path):
    module = types.ModuleType(name)
    module.__package__ = name
    module.__path__ = [str(path)]
    sys.modules[name] = module
    return module

deploy_package = namespace("deploy", snapshot_root / "deploy")
cloud_package = namespace("deploy.cloud_v2", snapshot_root / "deploy/cloud_v2")
rag_package = namespace("deploy.rag_store", snapshot_root / "deploy/rag_store")
pipeline_package = namespace("deploy.pipeline", snapshot_root / "deploy/pipeline")
deploy_package.cloud_v2 = cloud_package
deploy_package.rag_store = rag_package
deploy_package.pipeline = pipeline_package
package_modules = {
    "deploy.cloud_v2": cloud_package,
    "deploy.rag_store": rag_package,
    "deploy.pipeline": pipeline_package,
}
loaded = {}
for module_name, relative in EXPECTED_CLOSURE:
    module = types.ModuleType(module_name)
    module.__file__ = str(snapshot_root / relative)
    module.__spec__ = None
    sys.modules[module_name] = module
    if "." in module_name:
        package_name, attribute = module_name.rsplit(".", 1)
        if package_name not in package_modules:
            fail("child bootstrap module package is not allowlisted")
        module.__package__ = package_name
        setattr(package_modules[package_name], attribute, module)
    else:
        module.__package__ = ""
    loaded[module_name] = module
sys.modules["rag_store"] = rag_package
for attribute in (
    "neo4j_graph_importer",
    "runtime_neo4j_reader",
    "runtime_sqlite_reader",
    "scoped_graph_contract",
):
    target = loaded["deploy.rag_store." + attribute]
    sys.modules["rag_store." + attribute] = target
for module_name, _relative in EXPECTED_CLOSURE:
    exec(compiled[module_name], loaded[module_name].__dict__)
evidence = loaded["deploy.cloud_v2.offline_evidence"]
runner_binding = held_bindings["deploy.cloud_v2.offline_evidence"]
evidence._FORMAL_REPOSITORY_IDENTITY = (
    snapshot_root_state.st_dev,
    snapshot_root_state.st_ino,
    stat.S_IFMT(snapshot_root_state.st_mode),
)
evidence._EXECUTED_RUNNER_SOURCE_SHA256 = runner_binding["sha256"]
evidence._EXECUTED_RUNNER_STATE_IDENTITY = {
    key: runner_binding[key]
    for key in ("device", "inode", "mode", "nlink", "size", "mtime_ns", "ctime_ns")
}
authority = loaded["deploy.cloud_v2.authority_builder"]
authority_binding = held_bindings["deploy.cloud_v2.authority_builder"]
candidate = loaded["deploy.cloud_v2.candidate_builder"]
candidate_binding = held_bindings["deploy.cloud_v2.candidate_builder"]
dlp = loaded["deploy.cloud_v2.dlp"]
dlp_binding = held_bindings["deploy.cloud_v2.dlp"]
artifact = loaded["deploy.cloud_v2.artifact_builder"]
artifact_binding = held_bindings["deploy.cloud_v2.artifact_builder"]
handoff = loaded["deploy.cloud_v2.stop_b_handoff"]
handoff_binding = held_bindings["deploy.cloud_v2.stop_b_handoff"]
probe = loaded["deploy.cloud_v2.stop_b_probe"]
probe_binding = held_bindings["deploy.cloud_v2.stop_b_probe"]
gold = loaded["cloud_gold"]
gold_binding = held_bindings["cloud_gold"]
cloud80 = loaded["eval_cloud_subset"]
cloud80_binding = held_bindings["eval_cloud_subset"]
neo4j_import = loaded["deploy.pipeline.neo4j_import_candidate"]
neo4j_import_binding = held_bindings["deploy.pipeline.neo4j_import_candidate"]
try:
    evidence._install_formal_test_evidence_bootstrap_context()
    authority._install_formal_authority_builder_bootstrap_context(
        authority_binding
    )
    candidate._install_formal_candidate_builder_bootstrap_context(
        candidate_binding
    )
    dlp._install_formal_dlp_bootstrap_context(dlp_binding)
    artifact._install_formal_artifact_builder_bootstrap_context(artifact_binding)
    handoff._install_formal_stop_b_handoff_bootstrap_context(handoff_binding)
    probe._install_formal_stop_b_probe_bootstrap_context(probe_binding)
    gold._install_formal_cloud_gold_bootstrap_context(gold_binding)
    cloud80._install_formal_cloud80_bootstrap_context(cloud80_binding)
    neo4j_import._install_formal_neo4j_import_bootstrap_context(
        neo4j_import_binding
    )
except Exception as exc:
    fail(str(exc))
"""
_DISCLOSURE_SUBPROCESS_BOOTSTRAP = _CHILD_HELD_CLOSURE_BOOTSTRAP + """\
try:
    if len(sys.argv) != 8:
        raise evidence.OfflineEvidenceError(
            "disclosure child bootstrap binding is incomplete"
        )
    evidence._require_isolated_python()
    sandbox_enforcement = evidence._install_active_component_sandbox_context(
        sys.argv[7]
    )
    expected_source = (
        snapshot_root / evidence.OFFLINE_EVIDENCE_SOURCE_PATH
    ).resolve(strict=True)
    loaded_source = Path(evidence.__file__).resolve(strict=True)
    if loaded_source != expected_source:
        raise evidence.OfflineEvidenceError(
            "disclosure child imported offline evidence outside its snapshot"
        )
    expected_python_identity = evidence._decode_expected_identity(sys.argv[5])
    if evidence._python_identity() != expected_python_identity:
        raise evidence.OfflineEvidenceError(
            "disclosure child Python identity mismatch"
        )
    expected_snapshot_identity = evidence._decode_expected_identity(sys.argv[6])
    actual_snapshot_identity = evidence._activate_formal_materialized_snapshot(
        snapshot_root,
        expected_snapshot_identity,
        field="disclosure child snapshot",
    )
    result = evidence._sandboxed_disclosure_operation(
        action=sys.argv[2],
        target_path=sys.argv[3],
        created_at=sys.argv[4],
    )
    if evidence._python_identity() != expected_python_identity:
        raise evidence.OfflineEvidenceError(
            "disclosure child Python identity changed during execution"
        )
    if evidence._require_active_component_sandbox_context() != sandbox_enforcement:
        raise evidence.OfflineEvidenceError(
            "disclosure child sandbox enforcement changed during execution"
        )
except evidence.OfflineEvidenceError as exc:
    sys.stdout.buffer.write(evidence.canonical_json_bytes({"error": str(exc)}))
    raise SystemExit(2)
sys.stdout.buffer.write(evidence.canonical_json_bytes(result))
"""
_UNITTEST_BOOTSTRAP = _CHILD_HELD_CLOSURE_BOOTSTRAP + """\
import contextlib
import io
import unittest
try:
    if len(sys.argv) != 9:
        raise evidence.OfflineEvidenceError(
            "test child bootstrap binding is incomplete"
        )
    evidence._require_isolated_python()
    sandbox_enforcement = evidence._install_active_component_sandbox_context(
        sys.argv[8]
    )
    expected_source = (
        snapshot_root / evidence.OFFLINE_EVIDENCE_SOURCE_PATH
    ).resolve(strict=True)
    loaded_source = Path(evidence.__file__).resolve(strict=True)
    if loaded_source != expected_source:
        raise evidence.OfflineEvidenceError(
            "test child imported offline evidence from another repository"
        )
    component_name = sys.argv[2]
    start_directory = sys.argv[3]
    expected_python_identity = evidence._decode_expected_identity(sys.argv[4])
    python_identity = evidence._python_identity()
    if python_identity != expected_python_identity:
        raise evidence.OfflineEvidenceError(
            "test child Python identity mismatch: expected="
            + evidence._identity_sha256(expected_python_identity)
            + ",actual="
            + evidence._identity_sha256(python_identity)
        )
    process_identity = evidence._current_process_identity(
        require_session_leader=True
    )
    expected_test_scope = evidence._decode_expected_identity(sys.argv[5])
    test_scope = evidence._activate_formal_materialized_snapshot(
        snapshot_root,
        expected_test_scope,
        field="test child snapshot",
    )
    expected_selection = evidence._decode_expected_identity(sys.argv[6])
    if expected_selection != evidence._component_test_selection(component_name):
        raise evidence.OfflineEvidenceError("test child selection policy mismatch")
    expected_baseline = evidence._decode_expected_identity(sys.argv[7])
    if expected_baseline != evidence._component_test_baseline(component_name):
        raise evidence.OfflineEvidenceError("test child ID baseline mismatch")
    network_enforcement = evidence._require_network_denial()
except evidence.OfflineEvidenceError as exc:
    sys.stdout.buffer.write(evidence.canonical_json_bytes({"error": str(exc)}))
    raise SystemExit(2)
captured = io.StringIO()
with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
    discovered = unittest.defaultTestLoader.discover(start_directory, pattern="test_*.py")

    def flattened_tests(value):
        selected = []
        for item in value:
            if isinstance(item, unittest.TestSuite):
                selected.extend(flattened_tests(item))
                continue
            selected.append(item)
        return selected

    discovered_tests = flattened_tests(discovered)
    discovered_by_id = {}
    for test in discovered_tests:
        test_id = test.id()
        if test_id in discovered_by_id:
            raise evidence.OfflineEvidenceError("test discovery returned a duplicate ID")
        discovered_by_id[test_id] = test
    included_ids = set(expected_selection["included_test_ids"])
    excluded_ids = set(expected_selection["excluded_test_ids"])
    discovered_ids = set(discovered_by_id)
    if not included_ids.issubset(discovered_ids) or not excluded_ids.issubset(discovered_ids):
        raise evidence.OfflineEvidenceError("test selection references an unknown ID")
    selected_ids = sorted(
        included_ids if included_ids else discovered_ids - excluded_ids
    )
    test_id_manifest = evidence._validated_test_id_manifest(
        component_name,
        selected_ids,
        expected_baseline,
    )
    suite = unittest.TestSuite(discovered_by_id[test_id] for test_id in selected_ids)
    result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
log_payload = captured.getvalue().encode("utf-8")
try:
    post_python_identity = evidence._python_identity()
    if post_python_identity != expected_python_identity:
        raise evidence.OfflineEvidenceError(
            "test child Python identity changed during execution"
        )
    post_test_scope = evidence._test_scope_identity(
        snapshot_root,
        force_content=True,
        materialized=True,
        tree_roots=tuple(expected_test_scope.get("tree_roots", ())),
        exact_files=tuple(expected_test_scope.get("exact_files", ())),
    )
    if post_test_scope != expected_test_scope:
        raise evidence.OfflineEvidenceError(
            "test child snapshot identity changed during execution"
        )
    module_origin_ledger = evidence._loaded_module_origin_ledger(snapshot_root)
    network_enforcement = evidence._require_network_denial()
    if evidence._validated_test_id_manifest(
        component_name,
        selected_ids,
        expected_baseline,
    ) != test_id_manifest:
        raise evidence.OfflineEvidenceError("test ID manifest changed during execution")
    if evidence._require_active_component_sandbox_context() != sandbox_enforcement:
        raise evidence.OfflineEvidenceError(
            "test child sandbox enforcement changed during execution"
        )
except evidence.OfflineEvidenceError as exc:
    sys.stdout.buffer.write(evidence.canonical_json_bytes({"error": str(exc)}))
    raise SystemExit(2)
sys.stdout.buffer.write(
    evidence._test_process_payload(
        log_payload=log_payload,
        runner_source_sha256=runner_binding["sha256"],
        python_identity=post_python_identity,
        test_scope=post_test_scope,
        process_identity=process_identity,
        module_origin_ledger=module_origin_ledger,
        network_enforcement=network_enforcement,
        sandbox_enforcement=sandbox_enforcement,
        test_id_manifest=test_id_manifest,
        test_count=result.testsRun,
        successful=result.wasSuccessful(),
        failure_count=len(result.failures),
        error_count=len(result.errors),
        skipped_count=len(result.skipped),
    )
)
raise SystemExit(0 if result.wasSuccessful() else 1)
"""
_TEST_COMPONENTS = {
    "cloud-v2-tests": (
        "deny-network-cloud-v2-unittest",
        "deploy/cloud_v2/tests",
    ),
    "knowledge-graph-cloud-tests": (
        "deny-network-knowledge-graph-cloud-unittest",
        "skills/knowledge-graph-cloud/tests",
    ),
    "operator-companion-tests": (
        "deny-network-operator-companion-unittest",
        "operator-companion/tests",
    ),
    "formal-security-probes": (
        "deny-network-formal-security-unittest",
        "deploy/cloud_v2/tests",
    ),
}
_FORMAL_SECURITY_TEST_IDS = (
    "test_formal_product_entrypoints.FormalProductEntrypointTests.test_direct_file_and_module_execution_fail_before_help_or_output",
    "test_formal_product_entrypoints.FormalProductEntrypointTests.test_fake_environment_markers_cannot_authorize_public_writers",
    "test_formal_product_entrypoints.FormalProductEntrypointTests.test_frozen_delegate_replacement_fails_before_dispatch",
    "test_formal_product_entrypoints.FormalProductEntrypointTests.test_installed_context_routes_only_to_frozen_delegates",
    "test_formal_product_entrypoints.FormalProductEntrypointTests.test_source_replacement_and_same_inode_restore_fail_closed",
    "test_offline_evidence.MachOClosureTests.test_record_bound_console_scripts_are_read_only_sandbox_inputs",
    "test_offline_evidence.OfflineEvidenceTests.test_direct_file_help_requires_the_held_formal_bootstrap",
    "test_offline_evidence.OfflineEvidenceTests.test_disclosure_build_rejects_output_swap_during_final_runtime_closure",
    "test_offline_evidence.OfflineEvidenceTests.test_disclosure_build_rejects_permanent_repository_drift_after_output_write",
    "test_offline_evidence.OfflineEvidenceTests.test_disclosure_cleanup_failure_runs_all_later_closers_and_withdraws_output",
    "test_offline_evidence.OfflineEvidenceTests.test_disclosure_setup_failure_before_profile_staging_closes_every_owner",
    "test_offline_evidence.OfflineEvidenceTests.test_disclosure_validate_rejects_late_input_swap",
    "test_offline_evidence.OfflineEvidenceTests.test_forged_inherited_sandbox_marker_is_rejected_before_child_start",
    "test_offline_evidence.OfflineEvidenceTests.test_formal_bootstrap_rejects_each_missing_isolation_flag",
    "test_offline_evidence.OfflineEvidenceTests.test_formal_dlp_ignores_startup_cwd_and_bytecode_injection",
    "test_offline_evidence.OfflineEvidenceTests.test_formal_dlp_rejects_source_mutation_between_hold_and_execution",
    "test_offline_evidence.OfflineEvidenceTests.test_formal_dlp_routes_all_four_actions_in_real_subprocesses",
    "test_offline_evidence.OfflineEvidenceTests.test_formal_help_uses_isolated_control_plane_bootstrap",
    "test_offline_evidence.OfflineEvidenceTests.test_held_sandbox_profile_rejects_path_state_and_descriptor_byte_drift",
    "test_offline_evidence.OfflineEvidenceTests.test_parent_broker_rejects_missing_extra_or_reordered_profile_descriptors",
    "test_offline_evidence.OfflineEvidenceTests.test_product_suite_exclusion_policy_is_exact_and_auditable",
    "test_offline_evidence.OfflineEvidenceTests.test_real_child_sandbox_denies_escape_and_allows_bound_processes",
    "test_offline_evidence.OfflineEvidenceTests.test_run_formal_validation_component_check_detects_receipt_replacement",
    "test_offline_evidence.OfflineEvidenceTests.test_run_formal_validation_first_cleanup_failure_still_runs_every_closer",
    "test_offline_evidence.OfflineEvidenceTests.test_run_formal_validation_rejects_late_complete_log_tree_mutation",
    "test_offline_evidence.OfflineEvidenceTests.test_run_formal_validation_rejects_repository_drift_after_child_return",
    "test_offline_evidence.OfflineEvidenceTests.test_run_formal_validation_rejects_terminal_mode_change",
    "test_offline_evidence.OfflineEvidenceTests.test_run_formal_validation_setup_failure_closes_all_acquired_descriptors",
    "test_offline_evidence.OfflineEvidenceTests.test_stage_child_sandbox_profile_rejects_post_write_tampering",
    "test_offline_evidence.OfflineEvidenceTests.test_test_id_baseline_rejects_a_deleted_test",
)
_FORMAL_PARENT_PROBE_SPECS = (
    (
        "disclosure-evidence-determinism",
        "deploy/cloud_v2/tests/test_offline_evidence.py",
        "test_offline_evidence.OfflineEvidenceTests.test_disclosure_evidence_is_deterministic_and_accounts_every_call",
    ),
    (
        _PRODUCTION_EMBEDDING_PROBE_ID,
        "skills/knowledge-graph-cloud/tests/test_production_embedding_candidate.py",
        _PRODUCTION_EMBEDDING_TEST_ID,
    ),
    (
        "public-ops-process-isolation",
        "deploy/cloud_v2/tests/test_process_isolation.py",
        "test_process_isolation.ProcessIsolationTests.test_public_and_ops_entrypoints_are_process_isolated_and_fail_closed",
    ),
    (
        _REAL_OCR_PROBE_ID,
        "deploy/cloud_v2/tests/test_source_extract.py",
        _REAL_OCR_TEST_ID,
    ),
    (
        _REAL_PAGE_132_PROBE_ID,
        "deploy/cloud_v2/tests/test_source_extract.py",
        _REAL_PAGE_132_TEST_ID,
    ),
    (
        "runner-minimal-suite-sealing",
        "deploy/cloud_v2/tests/test_offline_evidence.py",
        "test_offline_evidence.OfflineEvidenceTests.test_runner_seals_real_minimal_suites_with_machine_result",
    ),
    (
        "runner-sitecustomize-rejection",
        "deploy/cloud_v2/tests/test_offline_evidence.py",
        "test_offline_evidence.OfflineEvidenceTests.test_runner_rejects_repository_sitecustomize_log_forgery",
    ),
)
_FORMAL_PARENT_BROKER_PLANS = {
    "disclosure-evidence-determinism": (
        "disclosure-build",
        "disclosure-validate",
        "disclosure-build",
        "disclosure-validate",
    ),
    _PRODUCTION_EMBEDDING_PROBE_ID: (
        f"test-component-{_PRODUCTION_EMBEDDING_PROBE_ID}",
    ),
    "public-ops-process-isolation": (
        "process-isolation-public-app-agent",
        "process-isolation-ops-admin-agent",
    ),
    _REAL_OCR_PROBE_ID: (
        "ocr-native-pdftoppm",
        *("ocr-native-tesseract" for _index in range(10)),
    ),
    _REAL_PAGE_132_PROBE_ID: (
        "ocr-native-pdftoppm",
    ),
    "runner-minimal-suite-sealing": tuple(
        f"test-component-{name}" for name in sorted(_TEST_COMPONENTS)
    ),
    "runner-sitecustomize-rejection": (
        "test-component-cloud-v2-tests",
        "test-component-cloud-v2-tests",
    ),
}
_FORMAL_PARENT_COVERED_TEST_IDS = tuple(
    sorted(spec[2] for spec in _FORMAL_PARENT_PROBE_SPECS)
)
_CLOUD_FORMAL_PARENT_COVERED_TEST_IDS = tuple(
    sorted(
        covered_test_id
        for _probe_id, source_path, covered_test_id in _FORMAL_PARENT_PROBE_SPECS
        if source_path.startswith("deploy/cloud_v2/tests/")
    )
)
_KNOWLEDGE_FORMAL_PARENT_COVERED_TEST_IDS = tuple(
    sorted(
        covered_test_id
        for _probe_id, source_path, covered_test_id in _FORMAL_PARENT_PROBE_SPECS
        if source_path.startswith("skills/knowledge-graph-cloud/tests/")
    )
)
_ALL_FORMAL_SECURITY_TEST_IDS = tuple(
    sorted((*_FORMAL_SECURITY_TEST_IDS, *_CLOUD_FORMAL_PARENT_COVERED_TEST_IDS))
)
_TEST_COMPONENT_SELECTIONS = {
    "cloud-v2-tests": {
        "included_test_ids": (),
        "excluded_test_ids": _ALL_FORMAL_SECURITY_TEST_IDS,
    },
    "formal-security-probes": {
        "included_test_ids": _FORMAL_SECURITY_TEST_IDS,
        "excluded_test_ids": _CLOUD_FORMAL_PARENT_COVERED_TEST_IDS,
    },
    "knowledge-graph-cloud-tests": {
        "included_test_ids": (),
        "excluded_test_ids": _KNOWLEDGE_FORMAL_PARENT_COVERED_TEST_IDS,
    },
    "operator-companion-tests": {
        "included_test_ids": (),
        "excluded_test_ids": (),
    },
}
_PARENT_PROBE_TEST_COMPONENTS = {
    _PRODUCTION_EMBEDDING_PROBE_ID: (
        "skills/knowledge-graph-cloud/tests",
        {
            "included_test_ids": (_PRODUCTION_EMBEDDING_TEST_ID,),
            "excluded_test_ids": (),
        },
        {
            "test_count": 1,
            "test_ids_sha256": (
                "066ae64bf7044d72d250b970fa7038ee964c7088632285fdcdd05fa0db768a63"
            ),
        },
    ),
}
_TEST_ID_BASELINES: dict[str, dict[str, Any]] = {
    "cloud-v2-tests": {
        "test_count": 401,
        "test_ids_sha256": (
            "a7bd7ea6366b27c251eb422a858d55b6adbf2152922d2ab6124d6ce5c33a0c83"
        ),
    },
    "formal-security-probes": {
        "test_count": 30,
        "test_ids_sha256": (
            "6be6e6030183d3bc02bd49c1a4852cf63d98c90c05c6723076fa1dedd014091f"
        ),
    },
    "knowledge-graph-cloud-tests": {
        "test_count": 401,
        "test_ids_sha256": (
            "a6647f37bb02ef24f16467d06a192bce00798eba8e5645a165d587927b593aff"
        ),
    },
    "operator-companion-tests": {
        "test_count": 26,
        "test_ids_sha256": (
            "b87d4d35e5343bfa313d3a0ad9795e3b120b388bdb720b30b6bd71b6c1031883"
        ),
    },
}
_FORMAL_PARENT_PROBE_BASELINE = {
    "probe_count": 7,
    "probe_ids_sha256": "6f78ac6f62a2f3a80ad90121beadf1a90f63b8248b978cf0e8734f941af267a9",
    "coverage_mapping_sha256": "adb4ebb05652e7587c52d853fbebf9a072d1e083cf57338f78b792df7a487a4f",
}
_TEST_SCOPE_ROOTS = (
    "deploy/cloud_v2",
    "deploy/pipeline",
    "deploy/rag_store",
    "operator-companion",
    "skills/knowledge-graph-cloud",
)
_TEST_SNAPSHOT_TREE_ROOTS = (
    "deploy",
    "operator-companion",
    "skills",
    "eval",
    "artifacts/candidates/revision-a-r9/authority-r10",
    "artifacts/candidates/revision-a-r9/derived-r10",
    "knowledge_base",
)
_TEST_SNAPSHOT_FILES = (
    ".gitattributes",
    "README.md",
    "DEPLOY.md",
    "USAGE.md",
    "APP_KNOWLEDGE_QA_SYNC_REQUIREMENTS.md",
    "KNOWLEDGE_QA_MIGRATION_AND_HANDOFF_MANUAL.md",
    "STOP_B_EXTERNAL_PROCESSING_REQUEST.json",
    "CLOUD_MIGRATION_DECISIONS.json",
    "CODE_MANIFEST.sha256",
    "MANIFEST.sha256",
)
_DISCLOSURE_SNAPSHOT_FILES = tuple(
    sorted(
        {
            *DISCLOSURE_SOURCE_PATHS,
            *(relative for _module, relative in _FORMAL_MODULE_CLOSURE),
            "deploy/cloud_v2/__init__.py",
            "deploy/cloud_v2/requirements.lock",
        }
    )
)
_SNAPSHOT_PACKAGE_ANCHORS = {
    "deploy/__init__.py": b'"""Sealed offline-test package anchor."""\n',
    "deploy/pipeline/__init__.py": b'"""Sealed offline-test package anchor."""\n',
    "deploy/rag_store/__init__.py": b'"""Sealed offline-test package anchor."""\n',
}
_RUNTIME_MODULES = {
    "blinker": "blinker",
    "click": "click",
    "flask": "flask",
    "flask-cors": "flask_cors",
    "itsdangerous": "itsdangerous",
    "jinja2": "jinja2",
    "jieba": "jieba",
    "markupsafe": "markupsafe",
    "neo4j": "neo4j",
    "numkong": "numkong",
    "numpy": "numpy",
    "pytz": "pytz",
    "tqdm": "tqdm",
    "usearch": "usearch",
    "waitress": "waitress",
    "werkzeug": "werkzeug",
    "whoosh": "whoosh",
}
_HOMEBREW_MACHO_TOOL_NAMES = (
    "pdfdetach",
    "pdfimages",
    "pdfinfo",
    "pdftotext",
    "pdftoppm",
    "tesseract",
)
_SYSTEM_TOOL_NAMES = ("env", "ssh-keygen")
_EXTERNAL_TOOL_NAMES = (*_HOMEBREW_MACHO_TOOL_NAMES, *_SYSTEM_TOOL_NAMES)
_SYSTEM_TOOL_EXACT_PATHS = {
    "env": Path("/usr/bin/env"),
    "ssh-keygen": Path("/usr/bin/ssh-keygen"),
}
_EXTERNAL_TOOL_SEARCH_DIRECTORIES = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
    Path("/usr/sbin"),
    Path("/sbin"),
)
_FORMAL_REPOSITORY_IDENTITY: tuple[int, int, int] | None = None
_FORMAL_MATERIALIZED_SNAPSHOT_IDENTITY: tuple[int, int, int] | None = None
_EXECUTED_RUNNER_SOURCE_SHA256: str | None = None
_EXECUTED_RUNNER_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_TEST_EVIDENCE_ACTION_CLOSURE: tuple[object, ...] | None = None
_ACTIVE_COMPONENT_SANDBOX_CONTEXT: dict[str, Any] | None = None
_PARENT_BROKER_CLIENT: Any | None = None
_OS_SOCKET = socket.socket
_OS_SUBPROCESS_RUN = subprocess.run
_RUNNER_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)
_PYTHON_NATIVE_LIBRARY_ALIASES = (
    Path("/opt/homebrew/opt/mpdecimal/lib/libmpdec.4.dylib"),
    Path("/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib"),
    Path("/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib"),
    Path("/opt/homebrew/opt/sqlite/lib/libsqlite3.dylib"),
    Path("/opt/homebrew/opt/xz/lib/liblzma.5.dylib"),
    Path("/opt/homebrew/opt/zstd/lib/libzstd.1.dylib"),
)
_DYLD_SHARED_CACHE_RUNTIME_LITERALS = (
    Path("/usr/lib/libffi-trampolines.dylib"),
)
_HOMEBREW_ROOT = Path("/opt/homebrew")
_HOMEBREW_CELLAR_ROOT = _HOMEBREW_ROOT / "Cellar"
_HOMEBREW_BIN_ROOT = _HOMEBREW_ROOT / "bin"
_HOMEBREW_POPPLER_VERSION = "26.08.0"
_HOMEBREW_POPPLER_ROOT = (
    _HOMEBREW_CELLAR_ROOT / "poppler" / _HOMEBREW_POPPLER_VERSION
)
_HOMEBREW_POPPLER_DATA_ROOT = _HOMEBREW_POPPLER_ROOT / "share" / "poppler"
_HOMEBREW_TESSERACT_VERSION = "5.5.2"
_HOMEBREW_TESSERACT_ROOT = (
    _HOMEBREW_CELLAR_ROOT / "tesseract" / _HOMEBREW_TESSERACT_VERSION
)
_HOMEBREW_TOOL_ROOTS = {
    **{
        name: _HOMEBREW_POPPLER_ROOT
        for name in _HOMEBREW_MACHO_TOOL_NAMES
        if name != "tesseract"
    },
    "tesseract": _HOMEBREW_TESSERACT_ROOT,
}
_SYSTEM_TOOL_ROOTS = (
    Path("/usr/bin"),
    Path("/bin"),
    Path("/usr/sbin"),
    Path("/sbin"),
)
_MACHO_SYSTEM_BOUNDARIES = (Path("/usr/lib"), Path("/System/Library"))
_MH_MAGIC_64 = 0xFEEDFACF
_CPU_TYPE_ARM64 = 0x0100000C
_MH_EXECUTE = 0x02
_MH_DYLIB = 0x06
_LC_LOAD_DYLIB = 0x0C
_LC_ID_DYLIB = 0x0D
_LC_LOAD_WEAK_DYLIB = 0x80000018
_LC_RPATH = 0x8000001C
_LC_REEXPORT_DYLIB = 0x8000001F
_LC_LAZY_LOAD_DYLIB = 0x20
_LC_LOAD_UPWARD_DYLIB = 0x80000023
_MACHO_LOAD_COMMANDS = {
    _LC_LOAD_DYLIB: "load",
    _LC_LOAD_WEAK_DYLIB: "weak",
    _LC_REEXPORT_DYLIB: "reexport",
    _LC_LAZY_LOAD_DYLIB: "lazy",
    _LC_LOAD_UPWARD_DYLIB: "upward",
}


class OfflineEvidenceError(RuntimeError):
    """An evidence input, output, or observed ledger failed closed."""


def canonical_json_bytes(value: object) -> bytes:
    """Serialize evidence without importing mutable repository helpers."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _type_sensitive_equal(actual: object, expected: object) -> bool:
    """Compare JSON-shaped evidence without Python's bool/int aliases."""

    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(
                _type_sensitive_equal(actual[key], expected[key])
                for key in expected
            )
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _type_sensitive_equal(left, right)
                for left, right in zip(actual, expected)
            )
        )
    if isinstance(expected, tuple):
        return (
            isinstance(actual, tuple)
            and len(actual) == len(expected)
            and all(
                _type_sensitive_equal(left, right)
                for left, right in zip(actual, expected)
            )
        )
    return type(actual) is type(expected) and actual == expected


def _validated_process_identity(
    value: object,
    field: str,
    *,
    require_session_leader: bool,
) -> dict[str, int]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"pid", "pgid"}
        or type(value["pid"]) is not int
        or type(value["pgid"]) is not int
        or value["pid"] <= 0
        or value["pgid"] <= 0
        or (require_session_leader and value["pid"] != value["pgid"])
    ):
        raise OfflineEvidenceError(f"{field} process identity is malformed")
    return {"pid": value["pid"], "pgid": value["pgid"]}


def _current_process_identity(*, require_session_leader: bool) -> dict[str, int]:
    return _validated_process_identity(
        {"pid": os.getpid(), "pgid": os.getpgrp()},
        "current",
        require_session_leader=require_session_leader,
    )


def _observed_new_session_process_identity(
    process: subprocess.Popen[Any],
    field: str,
) -> dict[str, int]:
    pid = process.pid
    if type(pid) is not int or pid <= 0:
        raise OfflineEvidenceError(f"{field} process identity is unavailable")
    try:
        pgid = os.getpgid(pid)
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} process identity is unavailable") from exc
    return _validated_process_identity(
        {"pid": pid, "pgid": pgid},
        field,
        require_session_leader=True,
    )


class _StepClock:
    def __init__(self, start: float) -> None:
        self._value = float(start)

    def __call__(self) -> float:
        current = self._value
        self._value += 0.001
        return current


def _has_control_character(value: str) -> bool:
    return any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in value
    )


def _require_utc_second(value: object, field: str) -> str:
    if not isinstance(value, str) or not _UTC_SECOND.fullmatch(value):
        raise OfflineEvidenceError(f"{field} must be an exact UTC RFC3339 second")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise OfflineEvidenceError(
            f"{field} must be an exact UTC RFC3339 second"
        ) from exc
    return value


def _require_positive_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OfflineEvidenceError(
            "timeout_seconds must be a finite positive number"
        )
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise OfflineEvidenceError(
            "timeout_seconds must be a finite positive number"
        )
    return timeout


def _absolute_path(path: str | Path, field: str) -> Path:
    """Return an absolute spelling that cannot normalize through a dot/link.

    Pathlib's ``resolve`` is deliberately avoided here: resolving before the
    descriptor is opened would re-introduce a symlink replacement window.  The
    descriptor walkers below resolve each directory component with
    ``O_NOFOLLOW`` instead.
    """

    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise OfflineEvidenceError(f"{field} path is invalid") from exc
    if isinstance(raw, bytes):
        raise OfflineEvidenceError(f"{field} path must be text")
    if (
        not raw
        or "\\" in raw
        or "//" in raw
        or _has_control_character(raw)
        or unicodedata.normalize("NFC", raw) != raw
    ):
        raise OfflineEvidenceError(f"{field} path is not canonical")
    spelled = Path(raw)
    if any(part in {"", ".", ".."} for part in spelled.parts):
        raise OfflineEvidenceError(f"{field} path contains a dot component")
    if not spelled.is_absolute():
        # ``abspath`` only prefixes cwd; it does not resolve links in the
        # resulting path, which is exactly what the fd walker needs.
        spelled = Path(os.path.abspath(spelled))
    return spelled


def _resolved_parent_path(path: str | Path, field: str) -> Path:
    """Expand fixed macOS root aliases without resolving arbitrary links."""

    absolute = _absolute_path(path, field)
    if sys.platform == "darwin":
        for alias, target in _SYSTEM_PATH_ALIAS_TARGETS.items():
            try:
                relative = absolute.relative_to(alias)
            except ValueError:
                continue
            return target / relative
    return absolute


def _inode_identity(state: os.stat_result) -> tuple[int, int, int]:
    return (state.st_dev, state.st_ino, stat.S_IFMT(state.st_mode))


def _state_identity(
    state: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        state.st_dev,
        state.st_ino,
        stat.S_IFMT(state.st_mode),
        state.st_nlink,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
    )


def _rename_stable_state_identity(
    state: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        state.st_dev,
        state.st_ino,
        state.st_mode,
        state.st_nlink,
        state.st_uid,
        state.st_gid,
        state.st_size,
        state.st_mtime_ns,
    )


def _safe_mode(
    state: os.stat_result,
    field: str,
    *,
    directory: bool = False,
    allow_sticky: bool = False,
) -> None:
    """Reject writable-by-group/other and special permission bits.

    Evidence is generated in a private workspace but may be copied into a
    broader staging tree.  Owner-write remains allowed during construction;
    group/other writes and set-id/sticky bits are never meaningful for an
    evidence file and would make its identity unsafe to review.
    """

    mode = stat.S_IMODE(state.st_mode)
    special_bits = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX
    # A sticky system scratch directory (for example macOS /private/tmp) is
    # intentionally writable by other users; O_EXCL plus the held directory
    # descriptor still gives us an unambiguous new entry there.  Ordinary
    # group/other-writable evidence directories remain forbidden.
    sticky_scratch = directory and allow_sticky and bool(mode & stat.S_ISVTX)
    if sticky_scratch:
        special_bits &= ~stat.S_ISVTX
    if (mode & 0o022 and not sticky_scratch) or mode & special_bits:
        raise OfflineEvidenceError(f"{field} has unsafe permissions")
    if directory and not (mode & 0o500) == 0o500:
        raise OfflineEvidenceError(f"{field} directory is not owner-accessible")
    if not directory and not (mode & 0o400):
        raise OfflineEvidenceError(f"{field} is not owner-readable")


def _require_sealed_file_mode(state: os.stat_result, field: str) -> None:
    if stat.S_IMODE(state.st_mode) != 0o400:
        raise OfflineEvidenceError(f"{field} is not sealed with exact mode 0400")


def _open_directory_fd(
    path: str | Path,
    field: str,
    *,
    enforce_safe_ancestors: bool = True,
) -> tuple[Path, int]:
    """Open every directory component without following a symlink."""

    absolute = _resolved_parent_path(path, field)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(os.sep, flags)
        if enforce_safe_ancestors:
            _safe_mode(os.fstat(descriptor), field, directory=True)
        current = Path(os.sep)
        for component in absolute.parts[1:]:
            current /= component
            _reject_component_alias(descriptor, component, field)
            before = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(before.st_mode):
                raise OfflineEvidenceError(f"{field} contains a symlink")
            if not stat.S_ISDIR(before.st_mode):
                raise OfflineEvidenceError(f"{field} contains a non-directory component")
            child = os.open(component, flags, dir_fd=descriptor)
            try:
                opened = os.fstat(child)
                if _state_identity(opened) != _state_identity(before):
                    raise OfflineEvidenceError(
                        f"{field} directory changed while opened"
                    )
                if enforce_safe_ancestors:
                    _safe_mode(
                        opened,
                        field,
                        directory=True,
                        allow_sticky=current in _STICKY_TRANSIT_PATHS,
                    )
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        state = os.fstat(descriptor)
        if not stat.S_ISDIR(state.st_mode):
            raise OfflineEvidenceError(f"{field} must be a real directory")
        return absolute, descriptor
    except OfflineEvidenceError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise OfflineEvidenceError(f"{field} contains a symlink or cannot be opened safely") from exc


def _reject_component_alias(parent_fd: int, component: str, field: str) -> None:
    """Reject case/Unicode aliases that the host filesystem may resolve."""

    try:
        entries = os.listdir(parent_fd)
    except OSError as exc:
        raise OfflineEvidenceError(
            f"{field} parent directory could not be inspected safely"
        ) from exc
    folded = unicodedata.normalize("NFC", component).casefold()
    aliases = [
        entry
        for entry in entries
        if entry != component
        and unicodedata.normalize("NFC", entry).casefold() == folded
    ]
    if aliases:
        raise OfflineEvidenceError(f"{field} uses a case or Unicode alias")


def _open_relative_directory_fd(
    root_fd: int,
    relative: str,
    field: str,
) -> int:
    """Open a canonical relative directory beneath an already-held root."""

    relative = _canonical_relative(relative, field)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.dup(root_fd)
        for component in PurePosixPath(relative).parts:
            _reject_component_alias(descriptor, component, field)
            before = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(before.st_mode):
                raise OfflineEvidenceError(f"{field} contains a symlink")
            if not stat.S_ISDIR(before.st_mode):
                raise OfflineEvidenceError(f"{field} contains a non-directory component")
            child = os.open(component, flags, dir_fd=descriptor)
            try:
                opened = os.fstat(child)
                if _state_identity(opened) != _state_identity(before):
                    raise OfflineEvidenceError(
                        f"{field} directory changed while it was opened"
                    )
                _safe_mode(opened, field, directory=True)
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OfflineEvidenceError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise OfflineEvidenceError(
            f"{field} contains a symlink or cannot be opened safely"
        ) from exc


def _stable_relative_file_bytes(
    root_fd: int,
    relative: str,
    field: str,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Read a canonical relative regular file through a held root descriptor."""

    relative = _canonical_relative(relative, field)
    parts = PurePosixPath(relative).parts
    parent_fd: int | None = None
    descriptor: int | None = None
    try:
        if len(parts) == 1:
            parent_fd = os.dup(root_fd)
        else:
            parent_fd = _open_relative_directory_fd(
                root_fd,
                "/".join(parts[:-1]),
                f"{field} parent",
            )
        name = parts[-1]
        _reject_component_alias(parent_fd, name, field)
        state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode):
            raise OfflineEvidenceError(f"{field} must be a regular unsymlinked file")
        if state.st_nlink != 1:
            raise OfflineEvidenceError(f"{field} must not be hard-linked")
        _safe_mode(state, field)
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(descriptor)
        if _state_identity(opened) != _state_identity(state):
            raise OfflineEvidenceError(f"{field} changed while it was opened")
        return _read_open_bytes(
            descriptor,
            opened,
            field,
            max_bytes=max_bytes,
        )
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(
            f"{field} could not be opened without following links"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)


def _stable_relative_file_binding(
    root_fd: int,
    relative: str,
    field: str,
    *,
    max_bytes: int | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Return bytes and exact state from the same held repository descriptor."""

    relative = _canonical_relative(relative, field)
    parts = PurePosixPath(relative).parts
    parent_fd: int | None = None
    descriptor: int | None = None
    try:
        if len(parts) == 1:
            parent_fd = os.dup(root_fd)
        else:
            parent_fd = _open_relative_directory_fd(
                root_fd,
                "/".join(parts[:-1]),
                f"{field} parent",
            )
        name = parts[-1]
        _reject_component_alias(parent_fd, name, field)
        state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode):
            raise OfflineEvidenceError(f"{field} must be a regular unsymlinked file")
        if state.st_nlink != 1:
            raise OfflineEvidenceError(f"{field} must not be hard-linked")
        _safe_mode(state, field)
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(descriptor)
        if _state_identity(opened) != _state_identity(state):
            raise OfflineEvidenceError(f"{field} changed while it was opened")
        payload = _read_open_bytes(
            descriptor,
            opened,
            field,
            max_bytes=max_bytes,
        )
        binding: dict[str, Any] = {
            "device": opened.st_dev,
            "inode": opened.st_ino,
            "mode": opened.st_mode,
            "nlink": opened.st_nlink,
            "size": opened.st_size,
            "mtime_ns": opened.st_mtime_ns,
            "ctime_ns": opened.st_ctime_ns,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        return payload, binding
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(
            f"{field} could not be opened without following links"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)


@dataclass
class _HeldRelativeInput:
    relative_path: str
    descriptor: int
    parent_fd: int
    state: os.stat_result
    parent_state_identity: tuple[int, int, int, int, int, int, int]
    size: int
    sha256: str
    field: str


def _hash_held_relative_input(
    descriptor: int,
    expected_state: os.stat_result,
    field: str,
) -> str:
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o400
            or _state_identity(before) != _state_identity(expected_state)
        ):
            raise OfflineEvidenceError(f"{field} held descriptor identity changed")
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            block = os.pread(
                descriptor,
                min(1024 * 1024, before.st_size - offset),
                offset,
            )
            if not block:
                raise OfflineEvidenceError(f"{field} became shorter while hashing")
            digest.update(block)
            offset += len(block)
        after = os.fstat(descriptor)
        if _state_identity(after) != _state_identity(before):
            raise OfflineEvidenceError(f"{field} changed while hashing")
        return digest.hexdigest()
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} could not be hashed safely") from exc


def _hold_relative_input_file(
    root_fd: int,
    relative: str,
    field: str,
    *,
    expected_size: int,
    expected_sha256: str,
) -> _HeldRelativeInput:
    relative = _canonical_relative(relative, field)
    if (
        type(expected_size) is not int
        or expected_size <= 0
        or not isinstance(expected_sha256, str)
        or not _SHA256.fullmatch(expected_sha256)
    ):
        raise OfflineEvidenceError(f"{field} approved identity is malformed")
    parts = PurePosixPath(relative).parts
    parent_fd: int | None = None
    descriptor: int | None = None
    try:
        if len(parts) == 1:
            parent_fd = os.dup(root_fd)
        else:
            parent_fd = _open_relative_directory_fd(
                root_fd,
                "/".join(parts[:-1]),
                f"{field} parent",
            )
        name = parts[-1]
        _reject_component_alias(parent_fd, name, field)
        state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(state.st_mode)
            or not stat.S_ISREG(state.st_mode)
            or state.st_nlink != 1
            or stat.S_IMODE(state.st_mode) != 0o400
            or state.st_size != expected_size
        ):
            raise OfflineEvidenceError(f"{field} is not the sealed approved file")
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(descriptor)
        if _state_identity(opened) != _state_identity(state):
            raise OfflineEvidenceError(f"{field} changed while it was opened")
        digest = _hash_held_relative_input(descriptor, opened, field)
        if digest != expected_sha256:
            raise OfflineEvidenceError(f"{field} SHA-256 is not approved")
        return _HeldRelativeInput(
            relative_path=relative,
            descriptor=descriptor,
            parent_fd=parent_fd,
            state=opened,
            parent_state_identity=_state_identity(os.fstat(parent_fd)),
            size=opened.st_size,
            sha256=digest,
            field=field,
        )
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(
            f"{field} could not be opened without following links"
        ) from exc
    finally:
        if sys.exception() is not None:
            if descriptor is not None:
                os.close(descriptor)
            if parent_fd is not None:
                os.close(parent_fd)


def _revalidate_held_relative_input(
    held: _HeldRelativeInput,
    root_fd: int,
) -> None:
    parts = PurePosixPath(held.relative_path).parts
    reopened_parent: int | None = None
    reopened: int | None = None
    try:
        descriptor_state = os.fstat(held.descriptor)
        parent_state = os.fstat(held.parent_fd)
        parent_entry = os.stat(
            parts[-1],
            dir_fd=held.parent_fd,
            follow_symlinks=False,
        )
        if (
            _state_identity(descriptor_state) != _state_identity(held.state)
            or _state_identity(parent_state) != held.parent_state_identity
            or _state_identity(parent_entry) != _state_identity(held.state)
        ):
            raise OfflineEvidenceError(f"{held.field} held identity changed")
        if len(parts) == 1:
            reopened_parent = os.dup(root_fd)
        else:
            reopened_parent = _open_relative_directory_fd(
                root_fd,
                "/".join(parts[:-1]),
                f"{held.field} parent",
            )
        if _state_identity(os.fstat(reopened_parent)) != held.parent_state_identity:
            raise OfflineEvidenceError(f"{held.field} snapshot path changed")
        _reject_component_alias(reopened_parent, parts[-1], held.field)
        reopened_state = os.stat(
            parts[-1],
            dir_fd=reopened_parent,
            follow_symlinks=False,
        )
        reopened = os.open(
            parts[-1],
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=reopened_parent,
        )
        if (
            _state_identity(reopened_state) != _state_identity(held.state)
            or _state_identity(os.fstat(reopened)) != _state_identity(held.state)
            or _hash_held_relative_input(held.descriptor, held.state, held.field)
            != held.sha256
        ):
            raise OfflineEvidenceError(f"{held.field} byte identity changed")
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(
            f"{held.field} held identity is unavailable"
        ) from exc
    finally:
        if reopened is not None:
            os.close(reopened)
        if reopened_parent is not None:
            os.close(reopened_parent)


def _close_held_relative_input(held: _HeldRelativeInput) -> None:
    cleanup_error: Exception | None = None
    for label, descriptor in (
        ("held relative input descriptor", held.descriptor),
        ("held relative input parent descriptor", held.parent_fd),
    ):
        try:
            os.close(descriptor)
        except Exception as exc:
            cleanup_error = _merge_cleanup_error(cleanup_error, exc, label=label)
    if cleanup_error is not None:
        raise cleanup_error


def _module_closure_manifest(
    root_fd: int,
    *,
    schema_version: str,
    field: str,
) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    for module_name, relative in _FORMAL_MODULE_CLOSURE:
        _payload, binding = _stable_relative_file_binding(
            root_fd,
            relative,
            f"{field} {module_name}",
            max_bytes=4 * 1024 * 1024,
        )
        modules.append(
            {
                "module": module_name,
                "path": relative,
                "binding": binding,
            }
        )
    return {
        "schema_version": schema_version,
        "modules": modules,
    }


def _module_closure_source_sha256(manifest: Mapping[str, Any]) -> str:
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise OfflineEvidenceError("formal module closure manifest is malformed")
    records: list[dict[str, str]] = []
    for record in modules:
        if (
            not isinstance(record, Mapping)
            or set(record) != {"module", "path", "binding"}
            or not isinstance(record["module"], str)
            or not isinstance(record["path"], str)
            or not isinstance(record["binding"], Mapping)
            or not isinstance(record["binding"].get("sha256"), str)
            or not _SHA256.fullmatch(record["binding"]["sha256"])
        ):
            raise OfflineEvidenceError("formal module closure manifest is malformed")
        records.append(
            {
                "module": record["module"],
                "path": record["path"],
                "sha256": record["binding"]["sha256"],
            }
        )
    expected = [
        {"module": module_name, "path": relative}
        for module_name, relative in _FORMAL_MODULE_CLOSURE
    ]
    if [
        {"module": record["module"], "path": record["path"]}
        for record in records
    ] != expected:
        raise OfflineEvidenceError("formal module closure coverage is not exact")
    return _identity_sha256(records)


def _encoded_module_closure_manifest(
    root_fd: int,
    *,
    schema_version: str,
    field: str,
) -> str:
    manifest = _module_closure_manifest(
        root_fd,
        schema_version=schema_version,
        field=field,
    )
    return base64.b64encode(canonical_json_bytes(manifest)).decode("ascii")


def _stable_relative_file_sha256(
    root_fd: int,
    relative: str,
    field: str,
) -> str:
    return hashlib.sha256(
        _stable_relative_file_bytes(root_fd, relative, field)
    ).hexdigest()


def _open_regular_fd(
    path: str | Path,
    field: str,
    *,
    allow_hardlink: bool = False,
    enforce_safe_ancestors: bool = True,
) -> tuple[int, int, os.stat_result, Path]:
    """Open a regular file while retaining its verified parent descriptor."""

    absolute = _absolute_path(path, field)
    if not absolute.name or absolute.name in {".", ".."}:
        raise OfflineEvidenceError(f"{field} path is invalid")
    canonical_parent, parent_fd = _open_directory_fd(
        absolute.parent,
        f"{field} parent",
        enforce_safe_ancestors=enforce_safe_ancestors,
    )
    descriptor: int | None = None
    try:
        _reject_component_alias(parent_fd, absolute.name, field)
        state = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode):
            raise OfflineEvidenceError(f"{field} must be a regular unsymlinked file")
        if not allow_hardlink and state.st_nlink != 1:
            raise OfflineEvidenceError(f"{field} must not be hard-linked")
        _safe_mode(state, field)
        descriptor = os.open(
            absolute.name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(descriptor)
        if _state_identity(opened) != _state_identity(state):
            raise OfflineEvidenceError(f"{field} changed while it was opened")
        return descriptor, parent_fd, opened, canonical_parent / absolute.name
    except OfflineEvidenceError:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)
        raise OfflineEvidenceError(f"{field} could not be opened without following links") from exc


def _read_open_bytes(
    descriptor: int,
    expected_state: os.stat_result,
    field: str,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Read a held descriptor and reject any mutation during the read."""

    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != expected_state.st_nlink
            or _state_identity(before) != _state_identity(expected_state)
        ):
            raise OfflineEvidenceError(f"{field} changed before reading")
        if max_bytes is not None and before.st_size > max_bytes:
            raise OfflineEvidenceError(f"{field} exceeds the closed size limit")
        chunks: list[bytes] = []
        offset = 0
        while offset < before.st_size:
            block = os.pread(
                descriptor,
                min(1024 * 1024, before.st_size - offset),
                offset,
            )
            if not block:
                raise OfflineEvidenceError(f"{field} became shorter while reading")
            chunks.append(block)
            offset += len(block)
        after = os.fstat(descriptor)
        if _state_identity(after) != _state_identity(before):
            raise OfflineEvidenceError(f"{field} changed while reading")
        return b"".join(chunks)
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} could not be read safely") from exc


def _stable_file_bytes(
    path: str | Path,
    field: str,
    *,
    max_bytes: int | None = None,
    enforce_safe_ancestors: bool = True,
) -> bytes:
    descriptor, parent_fd, state, _absolute = _open_regular_fd(
        path,
        field,
        enforce_safe_ancestors=enforce_safe_ancestors,
    )
    try:
        return _read_open_bytes(descriptor, state, field, max_bytes=max_bytes)
    finally:
        os.close(descriptor)
        os.close(parent_fd)


def _stable_file_sha256(
    path: str | Path,
    field: str,
    *,
    max_bytes: int | None = None,
    enforce_safe_ancestors: bool = True,
) -> str:
    payload = _stable_file_bytes(
        path,
        field,
        max_bytes=max_bytes,
        enforce_safe_ancestors=enforce_safe_ancestors,
    )
    return hashlib.sha256(payload).hexdigest()


@dataclass
class _HeldFile:
    path: Path
    descriptor: int
    parent_fd: int
    state: os.stat_result
    parent_state_identity: tuple[int, int, int, int, int, int, int]
    payload: bytes
    field: str


def _hold_file_under_root(
    path: str | Path,
    root: Path,
    field: str,
    *,
    max_bytes: int,
) -> _HeldFile:
    descriptor, parent_fd, state, canonical = _open_regular_fd(path, field)
    try:
        _require_sealed_file_mode(state, field)
        resolved_root = _resolved_parent_path(root, f"{field} root")
        try:
            canonical.relative_to(resolved_root)
        except ValueError as exc:
            raise OfflineEvidenceError(f"{field} escaped its evidence root") from exc
        payload = _read_open_bytes(
            descriptor,
            state,
            field,
            max_bytes=max_bytes,
        )
        return _HeldFile(
            canonical,
            descriptor,
            parent_fd,
            state,
            _state_identity(os.fstat(parent_fd)),
            payload,
            field,
        )
    except Exception:
        os.close(descriptor)
        os.close(parent_fd)
        raise


def _revalidate_held_file(held: _HeldFile) -> None:
    try:
        descriptor_state = os.fstat(held.descriptor)
        parent_state = os.fstat(held.parent_fd)
        parent_entry = os.stat(
            held.path.name,
            dir_fd=held.parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise OfflineEvidenceError(f"{held.field} held identity is unavailable") from exc
    if (
        _state_identity(descriptor_state) != _state_identity(held.state)
        or _state_identity(parent_state) != held.parent_state_identity
        or _state_identity(parent_entry) != _state_identity(held.state)
    ):
        raise OfflineEvidenceError(f"{held.field} held identity changed")
    reopened, reopened_parent, reopened_state, canonical = _open_regular_fd(
        held.path,
        held.field,
    )
    try:
        if (
            canonical != held.path
            or _state_identity(reopened_state) != _state_identity(held.state)
            or _state_identity(os.fstat(reopened)) != _state_identity(held.state)
        ):
            raise OfflineEvidenceError(f"{held.field} path identity changed")
    finally:
        os.close(reopened)
        os.close(reopened_parent)


def _close_held_file(held: _HeldFile) -> None:
    cleanup_error: Exception | None = None
    for label, descriptor in (
        ("held file descriptor", held.descriptor),
        ("held file parent descriptor", held.parent_fd),
    ):
        try:
            os.close(descriptor)
        except Exception as exc:
            cleanup_error = _merge_cleanup_error(cleanup_error, exc, label=label)
    if cleanup_error is not None:
        raise cleanup_error


def _revalidate_held_file_bytes(
    held: _HeldFile,
    *,
    max_bytes: int,
) -> None:
    """Close a held file over descriptor, path, state, and exact bytes."""

    _revalidate_held_file(held)
    if (
        _read_open_bytes(
            held.descriptor,
            held.state,
            held.field,
            max_bytes=max_bytes,
        )
        != held.payload
    ):
        raise OfflineEvidenceError(f"{held.field} bytes changed")
    _revalidate_held_file(held)



@dataclass
class _ApprovedTessdataInput:
    identity: dict[str, Any]
    root: Path
    root_fd: int
    root_state: os.stat_result
    files: dict[str, _HeldFile]


def _approved_tessdata_identity(
    root: Path,
    root_state: os.stat_result,
    files: Mapping[str, _HeldFile],
) -> dict[str, Any]:
    records = [
        {
            "name": name,
            "device": held.state.st_dev,
            "inode": held.state.st_ino,
            "mode": held.state.st_mode,
            "nlink": held.state.st_nlink,
            "size": held.state.st_size,
            "mtime_ns": held.state.st_mtime_ns,
            "ctime_ns": held.state.st_ctime_ns,
            "sha256": hashlib.sha256(held.payload).hexdigest(),
        }
        for name, held in sorted(files.items())
    ]
    value: dict[str, Any] = {
        "schema_version": "cloud-v2-approved-ocr-tessdata-input-v1",
        "status": "configured",
        "environment_variable_name": _OCR_TESSDATA_ENV,
        "root_path_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
        "root_device": root_state.st_dev,
        "root_inode": root_state.st_ino,
        "root_mode": root_state.st_mode,
        "root_nlink": root_state.st_nlink,
        "root_size": root_state.st_size,
        "root_mtime_ns": root_state.st_mtime_ns,
        "root_ctime_ns": root_state.st_ctime_ns,
        "file_count": len(records),
        "file_names": list(_OCR_TESSDATA_SNAPSHOT_NAMES),
        "file_set_sha256": _identity_sha256(records),
        "files": records,
        "source_access": "held-root-openat-no-follow-exact-two-files",
    }
    value["identity_sha256"] = _identity_sha256(value)
    return value


def _resolve_approved_tessdata_input(
    *,
    required: bool,
) -> _ApprovedTessdataInput | None:
    raw = os.environ.get(_OCR_TESSDATA_ENV)
    if raw is None:
        if required:
            raise OfflineEvidenceError("approved OCR tessdata input is required")
        return None
    if (
        not raw
        or _has_control_character(raw)
        or unicodedata.normalize("NFC", raw) != raw
    ):
        raise OfflineEvidenceError("approved OCR tessdata path is malformed")
    spelled = Path(raw)
    if (
        not spelled.is_absolute()
        or str(_lexically_normal_absolute(spelled, "approved OCR tessdata")) != raw
        or spelled.is_symlink()
    ):
        raise OfflineEvidenceError("approved OCR tessdata path is not exact")
    root, root_fd = _open_directory_fd(
        spelled,
        "approved OCR tessdata root",
        enforce_safe_ancestors=False,
    )
    files: dict[str, _HeldFile] = {}
    try:
        if root != spelled:
            raise OfflineEvidenceError("approved OCR tessdata path is not exact")
        root_state = os.fstat(root_fd)
        names = tuple(sorted(os.listdir(root_fd)))
        if names != _OCR_TESSDATA_SNAPSHOT_NAMES:
            raise OfflineEvidenceError(
                "approved OCR tessdata file set is not exact"
            )
        for name in _OCR_TESSDATA_SNAPSHOT_NAMES:
            _reject_component_alias(root_fd, name, f"approved OCR tessdata {name}")
            state = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(state.st_mode)
                or not stat.S_ISREG(state.st_mode)
                or state.st_nlink != 1
            ):
                raise OfflineEvidenceError(
                    f"approved OCR tessdata file is unsafe: {name}"
                )
            _safe_mode(state, f"approved OCR tessdata {name}")
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=root_fd,
            )
            try:
                opened = os.fstat(descriptor)
                if _state_identity(opened) != _state_identity(state):
                    raise OfflineEvidenceError(
                        f"approved OCR tessdata changed while opened: {name}"
                    )
                payload = _read_open_bytes(
                    descriptor,
                    opened,
                    f"approved OCR tessdata {name}",
                    max_bytes=16 * 1024 * 1024,
                )
                if not hmac.compare_digest(
                    hashlib.sha256(payload).hexdigest(),
                    _OCR_TESSDATA_EXPECTED_SHA256[name],
                ):
                    raise OfflineEvidenceError(
                        f"approved OCR tessdata SHA-256 mismatch: {name}"
                    )
                files[name] = _HeldFile(
                    path=root / name,
                    descriptor=descriptor,
                    parent_fd=os.dup(root_fd),
                    state=opened,
                    parent_state_identity=_state_identity(root_state),
                    payload=payload,
                    field=f"approved OCR tessdata {name}",
                )
                descriptor = -1
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        identity = _approved_tessdata_identity(root, root_state, files)
        fixture = _ApprovedTessdataInput(
            identity=identity,
            root=root,
            root_fd=root_fd,
            root_state=root_state,
            files=files,
        )
        _revalidate_approved_tessdata_input(fixture)
        return fixture
    except Exception:
        for held in files.values():
            _close_held_file(held)
        os.close(root_fd)
        raise


def _revalidate_approved_tessdata_input(
    fixture: _ApprovedTessdataInput,
) -> None:
    canonical, reopened_fd = _open_directory_fd(
        fixture.root,
        "approved OCR tessdata root",
        enforce_safe_ancestors=False,
    )
    try:
        if (
            canonical != fixture.root
            or _state_identity(os.fstat(reopened_fd))
            != _state_identity(fixture.root_state)
            or _inode_identity(os.fstat(reopened_fd))
            != _inode_identity(os.fstat(fixture.root_fd))
        ):
            raise OfflineEvidenceError(
                "approved OCR tessdata root path identity changed"
            )
    finally:
        os.close(reopened_fd)
    if (
        _state_identity(os.fstat(fixture.root_fd))
        != _state_identity(fixture.root_state)
        or tuple(sorted(os.listdir(fixture.root_fd)))
        != _OCR_TESSDATA_SNAPSHOT_NAMES
    ):
        raise OfflineEvidenceError("approved OCR tessdata root identity changed")
    for name in _OCR_TESSDATA_SNAPSHOT_NAMES:
        held = fixture.files.get(name)
        if held is None:
            raise OfflineEvidenceError("approved OCR tessdata binding is incomplete")
        try:
            descriptor_state = os.fstat(held.descriptor)
            parent_entry = os.stat(
                held.path.name,
                dir_fd=held.parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise OfflineEvidenceError(
                f"approved OCR tessdata held identity is unavailable: {name}"
            ) from exc
        if (
            _state_identity(descriptor_state) != _state_identity(held.state)
            or _state_identity(parent_entry) != _state_identity(held.state)
            or _state_identity(os.fstat(held.parent_fd))
            != held.parent_state_identity
        ):
            raise OfflineEvidenceError(
                f"approved OCR tessdata held identity changed: {name}"
            )
        reopened, reopened_parent, reopened_state, canonical = _open_regular_fd(
            held.path,
            held.field,
            enforce_safe_ancestors=False,
        )
        try:
            if (
                canonical != held.path
                or _state_identity(reopened_state) != _state_identity(held.state)
                or _state_identity(os.fstat(reopened)) != _state_identity(held.state)
            ):
                raise OfflineEvidenceError(
                    f"approved OCR tessdata path identity changed: {name}"
                )
        finally:
            os.close(reopened)
            os.close(reopened_parent)
        if _read_open_bytes(
            held.descriptor,
            held.state,
            held.field,
            max_bytes=16 * 1024 * 1024,
        ) != held.payload:
            raise OfflineEvidenceError(f"approved OCR tessdata bytes changed: {name}")
        if (
            hashlib.sha256(held.payload).hexdigest()
            != _OCR_TESSDATA_EXPECTED_SHA256[name]
        ):
            raise OfflineEvidenceError(f"approved OCR tessdata bytes changed: {name}")
    current = _approved_tessdata_identity(
        fixture.root,
        os.fstat(fixture.root_fd),
        fixture.files,
    )
    if current != fixture.identity:
        raise OfflineEvidenceError("approved OCR tessdata identity changed")


def _close_approved_tessdata_input(fixture: _ApprovedTessdataInput) -> None:
    cleanup_error: Exception | None = None
    for held in fixture.files.values():
        try:
            _close_held_file(held)
        except Exception as exc:
            cleanup_error = _merge_cleanup_error(
                cleanup_error,
                exc,
                label="approved OCR tessdata file",
            )
    try:
        os.close(fixture.root_fd)
    except Exception as exc:
        cleanup_error = _merge_cleanup_error(
            cleanup_error,
            exc,
            label="approved OCR tessdata root",
        )
    if cleanup_error is not None:
        raise cleanup_error

def _revalidate_held_test_artifacts(
    *,
    root_path: Path,
    root_fd: int,
    logs_fd: int,
    expected_log_stems: Sequence[str],
    component_held: _HeldFile,
    receipt_held: _HeldFile,
    log_held: Sequence[_HeldFile],
    expected_root_state: tuple[int, int, int, int, int, int, int],
    expected_logs_state: tuple[int, int, int, int, int, int, int],
) -> None:
    """Perform the final low-level closure of a complete test evidence tree."""

    if (
        _state_identity(os.fstat(root_fd)) != expected_root_state
        or _state_identity(os.fstat(logs_fd)) != expected_logs_state
    ):
        raise OfflineEvidenceError("test evidence tree state changed")
    _revalidate_child_directory(
        root_fd,
        "logs",
        logs_fd,
        "test evidence logs directory",
    )
    _validate_logs_fd(
        logs_fd,
        expected_names=expected_log_stems,
        require_sealed=True,
    )
    _revalidate_held_file_bytes(
        component_held,
        max_bytes=_TEST_COMPONENT_SET_MAX_BYTES,
    )
    _revalidate_held_file_bytes(
        receipt_held,
        max_bytes=_TEST_RECEIPT_MAX_BYTES,
    )
    for held in log_held:
        _revalidate_held_file_bytes(held, max_bytes=16 * 1024 * 1024)
    _revalidate_child_directory(
        root_fd,
        "logs",
        logs_fd,
        "test evidence logs directory",
    )
    _validate_logs_fd(
        logs_fd,
        expected_names=expected_log_stems,
        require_sealed=True,
    )
    if (
        _state_identity(os.fstat(root_fd)) != expected_root_state
        or _state_identity(os.fstat(logs_fd)) != expected_logs_state
    ):
        raise OfflineEvidenceError("test evidence tree state changed")
    _revalidate_directory_path(root_path, root_fd, "test evidence root")


def _canonical_file_under_root(
    path: str | Path,
    root: Path,
    field: str,
) -> Path:
    descriptor, parent_fd, _state, canonical = _open_regular_fd(path, field)
    try:
        try:
            canonical.relative_to(root)
        except ValueError as exc:
            raise OfflineEvidenceError(f"{field} escaped its evidence root") from exc
        return canonical
    finally:
        os.close(descriptor)
        os.close(parent_fd)


def _revalidate_directory_path(
    path: str | Path,
    held_fd: int,
    field: str,
) -> None:
    _canonical, reopened_fd = _open_directory_fd(path, field)
    try:
        if _inode_identity(os.fstat(reopened_fd)) != _inode_identity(os.fstat(held_fd)):
            raise OfflineEvidenceError(f"{field} path identity changed")
    finally:
        os.close(reopened_fd)


def _create_child_directory(
    parent_fd: int,
    name: str,
    field: str,
) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor: int | None = None
    created_state: os.stat_result | None = None
    try:
        _reject_component_alias(parent_fd, name, field)
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OfflineEvidenceError(f"{field} already exists")
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        created_state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(created_state.st_mode) or stat.S_ISLNK(created_state.st_mode):
            raise OfflineEvidenceError(f"{field} is not a real directory")
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        opened = os.fstat(descriptor)
        if _state_identity(opened) != _state_identity(created_state):
            raise OfflineEvidenceError(f"{field} changed while it was opened")
        _safe_mode(opened, field, directory=True)
        return descriptor
    except OfflineEvidenceError:
        _discard_created_child_directory(
            parent_fd,
            name,
            descriptor=descriptor,
            created_state=created_state,
            flags=flags,
        )
        raise
    except OSError as exc:
        _discard_created_child_directory(
            parent_fd,
            name,
            descriptor=descriptor,
            created_state=created_state,
            flags=flags,
        )
        raise OfflineEvidenceError(f"{field} could not be created safely") from exc


def _discard_created_child_directory(
    parent_fd: int,
    name: str,
    *,
    descriptor: int | None,
    created_state: os.stat_result | None,
    flags: int,
) -> None:
    """Discard only the directory inode proven to have been created here."""

    cleanup_fd = descriptor
    try:
        if cleanup_fd is None and created_state is not None:
            cleanup_fd = os.open(name, flags, dir_fd=parent_fd)
        if (
            cleanup_fd is not None
            and created_state is not None
            and _state_identity(os.fstat(cleanup_fd))
            == _state_identity(created_state)
        ):
            _discard_child_directory_if_owned(parent_fd, name, cleanup_fd)
    except (OSError, OfflineEvidenceError):
        return
    finally:
        if cleanup_fd is not None:
            os.close(cleanup_fd)


def _revalidate_child_directory(
    parent_fd: int,
    name: str,
    held_fd: int,
    field: str,
) -> None:
    try:
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        held = os.fstat(held_fd)
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} is unavailable") from exc
    if (
        not stat.S_ISDIR(entry.st_mode)
        or stat.S_ISLNK(entry.st_mode)
        or _inode_identity(entry) != _inode_identity(held)
    ):
        raise OfflineEvidenceError(f"{field} path identity changed")
    _safe_mode(entry, field, directory=True)


def _discard_child_directory_if_owned(
    parent_fd: int,
    name: str,
    held_fd: int,
) -> None:
    """Quarantine a directory entry only while it is bound to the held inode."""

    _quarantine_entry_if_owned(
        parent_fd,
        name,
        held_fd,
        field="owned child directory",
        directory=True,
    )


def _revalidate_reserved_path(
    reservation: _ReservedOutput,
    field: str,
) -> None:
    descriptor, parent_fd, reopened, canonical = _open_regular_fd(
        reservation.path, field
    )
    try:
        held = _verify_reserved_output(reservation, field)
        if (
            canonical != reservation.path
            or reopened.st_mode != held.st_mode
            or _state_identity(reopened) != _state_identity(held)
            or _inode_identity(os.fstat(parent_fd))
            != _inode_identity(os.fstat(reservation.parent_fd))
        ):
            raise OfflineEvidenceError(f"{field} path identity changed")
    finally:
        os.close(descriptor)
        os.close(parent_fd)


def _canonical_relative(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise OfflineEvidenceError(f"{field} must be a relative path")
    if (
        "\\" in value
        or "//" in value
        or _has_control_character(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        raise OfflineEvidenceError(f"{field} is not canonical POSIX")
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise OfflineEvidenceError(f"{field} contains a dot or normalized component")
    return value


@dataclass
class _ReservedOutput:
    path: Path
    parent_fd: int
    descriptor: int
    readable: bool
    initial_state_identity: tuple[int, int, int, int, int, int, int]
    sealed_state_identity: tuple[int, int, int, int, int, int, int] | None = None
    sealed_size: int | None = None
    sealed_sha256: str | None = None


def _merge_cleanup_error(
    current: Exception | None,
    error: Exception,
    *,
    label: str,
) -> Exception:
    if current is None:
        return error
    current.add_note(f"additional cleanup failure ({label}): {type(error).__name__}: {error}")
    return current


def _atomic_noreplace_rename(
    source_name: str,
    destination_name: str,
    *,
    directory_descriptor: int,
) -> None:
    """Rename inside one held directory without replacing an existing entry."""

    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        try:
            rename = libc.renameatx_np
        except AttributeError as exc:
            raise OfflineEvidenceError(
                "atomic no-replace quarantine is unavailable"
            ) from exc
        flag = 0x00000004
    elif sys.platform.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as exc:
            raise OfflineEvidenceError(
                "atomic no-replace quarantine is unavailable"
            ) from exc
        flag = 0x00000001
    else:
        raise OfflineEvidenceError("atomic no-replace quarantine is unsupported")
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


def _quarantine_entry_if_owned(
    parent_fd: int,
    name: str,
    descriptor: int,
    *,
    field: str,
    directory: bool,
) -> str:
    """Move an owned entry aside atomically; foreign replacements are retained."""

    try:
        held = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} is unavailable for quarantine") from exc
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected_kind(held.st_mode)
        or not expected_kind(entry.st_mode)
        or _inode_identity(entry) != _inode_identity(held)
    ):
        raise OfflineEvidenceError(f"{field} ownership changed before quarantine")

    quarantine_name: str | None = None
    for index in range(32):
        candidate = f".{name}.cleanup-{index:02d}"
        try:
            _atomic_noreplace_rename(
                name,
                candidate,
                directory_descriptor=parent_fd,
            )
        except FileExistsError:
            continue
        except (OfflineEvidenceError, OSError) as exc:
            raise OfflineEvidenceError(f"{field} could not be quarantined") from exc
        quarantine_name = candidate
        break
    if quarantine_name is None:
        raise OfflineEvidenceError(f"{field} quarantine namespace is exhausted")

    try:
        os.fsync(parent_fd)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        if directory:
            flags |= getattr(os, "O_DIRECTORY", 0)
        quarantine_fd = os.open(quarantine_name, flags, dir_fd=parent_fd)
        try:
            quarantined = os.fstat(quarantine_fd)
            if (
                not expected_kind(quarantined.st_mode)
                or _inode_identity(quarantined) != _inode_identity(held)
            ):
                raise OfflineEvidenceError(f"{field} quarantine identity changed")
        finally:
            os.close(quarantine_fd)
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OfflineEvidenceError(
                f"{field} was replaced while its owned entry was quarantined"
            )
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} quarantine could not be verified") from exc
    return quarantine_name


def _discard_reserved_entry_if_owned(
    output: Path,
    parent_fd: int,
    descriptor: int,
) -> None:
    """Quarantine only the entry still bound to this reservation descriptor."""

    _quarantine_entry_if_owned(
        parent_fd,
        output.name,
        descriptor,
        field="reserved evidence output",
        directory=False,
    )


def _new_output_parent(path: str | Path) -> tuple[Path, int]:
    output = _absolute_path(path, "evidence output")
    if not output.name or output.name in {".", ".."}:
        raise OfflineEvidenceError("evidence output path is invalid")
    try:
        absolute_parent, parent_fd = _open_directory_fd(
            output.parent, "evidence output parent"
        )
    except OfflineEvidenceError:
        raise
    try:
        _reject_component_alias(parent_fd, output.name, "evidence output")
        try:
            state = os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            state = None
        if state is not None:
            raise OfflineEvidenceError("evidence output already exists")
        return absolute_parent / output.name, parent_fd
    except OfflineEvidenceError:
        os.close(parent_fd)
        raise
    except OSError as exc:
        os.close(parent_fd)
        raise OfflineEvidenceError("evidence output cannot be inspected safely") from exc


def _new_output_slot_under_root(
    path: str | Path,
    root: Path,
    field: str,
) -> tuple[Path, int]:
    output, parent_fd = _new_output_parent(path)
    try:
        relative = output.relative_to(root)
        if not relative.parts or relative.parts[0] == "logs":
            raise OfflineEvidenceError(f"{field} overlaps the sealed logs directory")
        return output, parent_fd
    except ValueError as exc:
        os.close(parent_fd)
        raise OfflineEvidenceError(f"{field} escaped its evidence root") from exc
    except OfflineEvidenceError:
        os.close(parent_fd)
        raise


def _reserve_output_slot(
    output: Path,
    parent_fd: int,
    *,
    readable: bool = False,
) -> _ReservedOutput:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            output.name,
            (os.O_RDWR if readable else os.O_WRONLY)
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent_fd,
        )
        os.fchmod(descriptor, 0o600)
        opened = os.fstat(descriptor)
        entry = os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o600
            or _state_identity(opened) != _state_identity(entry)
        ):
            raise OfflineEvidenceError(
                "evidence output reservation is not a unique regular file"
            )
        _safe_mode(opened, "evidence output reservation")
        return _ReservedOutput(
            path=output,
            parent_fd=parent_fd,
            descriptor=descriptor,
            readable=readable,
            initial_state_identity=_state_identity(opened),
        )
    except Exception as exc:
        cleanup_error: Exception | None = None
        if descriptor is not None:
            try:
                _discard_reserved_entry_if_owned(output, parent_fd, descriptor)
            except Exception as cleanup_exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    cleanup_exc,
                    label="failed reservation quarantine",
                )
            try:
                os.close(descriptor)
            except Exception as cleanup_exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    cleanup_exc,
                    label="failed reservation descriptor",
                )
        try:
            os.close(parent_fd)
        except Exception as cleanup_exc:
            cleanup_error = _merge_cleanup_error(
                cleanup_error,
                cleanup_exc,
                label="failed reservation parent descriptor",
            )
        if cleanup_error is not None:
            exc.add_note(
                "secondary reservation cleanup failure: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        if isinstance(exc, OfflineEvidenceError):
            raise
        if isinstance(exc, OSError):
            raise OfflineEvidenceError(
                "evidence output could not be created exclusively"
            ) from exc
        raise


def _reserve_new_output(
    path: str | Path,
    *,
    readable: bool = False,
) -> _ReservedOutput:
    output, parent_fd = _new_output_parent(path)
    return _reserve_output_slot(output, parent_fd, readable=readable)


def _reserved_entry_state(
    reservation: _ReservedOutput,
    field: str,
) -> os.stat_result:
    sealed_fields = (
        reservation.sealed_state_identity,
        reservation.sealed_size,
        reservation.sealed_sha256,
    )
    if any(value is None for value in sealed_fields) and any(
        value is not None for value in sealed_fields
    ):
        raise OfflineEvidenceError(f"{field} reservation seal is incomplete")
    sealed = all(value is not None for value in sealed_fields)
    try:
        opened = os.fstat(reservation.descriptor)
        entry = os.stat(
            reservation.path.name,
            dir_fd=reservation.parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} reservation is unavailable") from exc
    expected_identity = (
        reservation.sealed_state_identity
        if sealed
        else reservation.initial_state_identity
    )
    expected_mode = 0o400 if sealed else 0o600
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or stat.S_IMODE(opened.st_mode) != expected_mode
        or _state_identity(opened) != expected_identity
        or opened.st_mode != entry.st_mode
        or _state_identity(opened) != _state_identity(entry)
    ):
        raise OfflineEvidenceError(f"{field} reservation identity changed")
    if sealed and opened.st_size != reservation.sealed_size:
        raise OfflineEvidenceError(f"{field} reservation byte count changed")
    _safe_mode(opened, field)
    return opened


def _read_reserved_output_bytes(
    reservation: _ReservedOutput,
    field: str,
    *,
    max_bytes: int | None = None,
) -> bytes:
    state = _reserved_entry_state(reservation, field)
    reader: int | None = None
    try:
        if reservation.readable:
            reader = reservation.descriptor
        else:
            reader = os.open(
                reservation.path.name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=reservation.parent_fd,
            )
            if (
                os.fstat(reader).st_mode != state.st_mode
                or _state_identity(os.fstat(reader)) != _state_identity(state)
            ):
                raise OfflineEvidenceError(f"{field} reservation identity changed")
        payload = _read_open_bytes(
            reader,
            state,
            field,
            max_bytes=max_bytes,
        )
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} reservation could not be read") from exc
    finally:
        if reader is not None and reader != reservation.descriptor:
            os.close(reader)
    if reservation.sealed_sha256 is not None and (
        len(payload) != reservation.sealed_size
        or hashlib.sha256(payload).hexdigest() != reservation.sealed_sha256
    ):
        raise OfflineEvidenceError(f"{field} reservation bytes changed")
    return payload


def _verify_reserved_output(reservation: _ReservedOutput, field: str) -> os.stat_result:
    opened = _reserved_entry_state(reservation, field)
    if reservation.sealed_sha256 is not None:
        _read_reserved_output_bytes(reservation, field)
    return opened


def _revalidate_reserved_test_artifacts(
    *,
    root_path: Path,
    root_fd: int,
    logs_fd: int,
    expected_log_stems: Sequence[str],
    log_reservations: Mapping[str, _ReservedOutput],
    expected_log_payloads: Mapping[str, bytes],
    component_reservation: _ReservedOutput,
    component_payload: bytes,
    receipt_reservation: _ReservedOutput,
    receipt_payload: bytes,
    expected_root_state: tuple[int, int, int, int, int, int, int],
    expected_logs_state: tuple[int, int, int, int, int, int, int],
) -> None:
    """Perform the final low-level closure of newly written test artifacts."""

    if (
        _state_identity(os.fstat(root_fd)) != expected_root_state
        or _state_identity(os.fstat(logs_fd)) != expected_logs_state
    ):
        raise OfflineEvidenceError("test evidence tree state changed")
    _revalidate_child_directory(
        root_fd,
        "logs",
        logs_fd,
        "test evidence logs directory",
    )
    _validate_logs_fd(
        logs_fd,
        expected_names=expected_log_stems,
        require_sealed=True,
    )
    for name in sorted(log_reservations):
        reservation = log_reservations[name]
        expected = expected_log_payloads[f"logs/{name}.log"]
        if _read_reserved_output_bytes(
            reservation,
            f"test evidence log {name}",
            max_bytes=16 * 1024 * 1024,
        ) != expected:
            raise OfflineEvidenceError(f"test evidence log {name} bytes changed")
        _revalidate_reserved_path(reservation, f"test evidence log {name}")
    if _read_reserved_output_bytes(
        component_reservation,
        "test component set",
        max_bytes=_TEST_COMPONENT_SET_MAX_BYTES,
    ) != component_payload:
        raise OfflineEvidenceError("test component set bytes changed")
    _revalidate_reserved_path(component_reservation, "test component set")
    if _read_reserved_output_bytes(
        receipt_reservation,
        "test receipt",
        max_bytes=_TEST_RECEIPT_MAX_BYTES,
    ) != receipt_payload:
        raise OfflineEvidenceError("test receipt bytes changed")
    _revalidate_reserved_path(receipt_reservation, "test receipt")
    _revalidate_child_directory(
        root_fd,
        "logs",
        logs_fd,
        "test evidence logs directory",
    )
    _validate_logs_fd(
        logs_fd,
        expected_names=expected_log_stems,
        require_sealed=True,
    )
    if (
        _state_identity(os.fstat(root_fd)) != expected_root_state
        or _state_identity(os.fstat(logs_fd)) != expected_logs_state
    ):
        raise OfflineEvidenceError("test evidence tree state changed")
    _revalidate_directory_path(root_path, root_fd, "test evidence root")


def _write_reserved_bytes(
    reservation: _ReservedOutput,
    payload: bytes,
    field: str,
    *,
    max_bytes: int | None = None,
) -> Path:
    if not isinstance(payload, bytes):
        raise OfflineEvidenceError(f"{field} payload must be bytes")
    if max_bytes is not None and len(payload) > max_bytes:
        raise OfflineEvidenceError(f"{field} exceeds the closed size limit")
    if any(
        value is not None
        for value in (
            reservation.sealed_state_identity,
            reservation.sealed_size,
            reservation.sealed_sha256,
        )
    ):
        raise OfflineEvidenceError(f"{field} reservation is already sealed")
    before = _verify_reserved_output(reservation, field)
    if before.st_size != 0:
        raise OfflineEvidenceError(f"{field} reservation is not empty")
    try:
        offset = 0
        while offset < len(payload):
            written = os.pwrite(reservation.descriptor, payload[offset:], offset)
            if written <= 0:
                raise OfflineEvidenceError(f"{field} could not be written completely")
            offset += written
        os.fsync(reservation.descriptor)
        os.fchmod(reservation.descriptor, 0o400)
        os.fsync(reservation.descriptor)
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} could not be written safely") from exc
    try:
        after = os.fstat(reservation.descriptor)
        entry = os.stat(
            reservation.path.name,
            dir_fd=reservation.parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} reservation is unavailable") from exc
    if (
        not stat.S_ISREG(after.st_mode)
        or after.st_nlink != 1
        or stat.S_IMODE(after.st_mode) != 0o400
        or _inode_identity(after) != _inode_identity(before)
        or after.st_mode != entry.st_mode
        or _state_identity(after) != _state_identity(entry)
    ):
        raise OfflineEvidenceError(f"{field} reservation identity changed")
    if after.st_size != len(payload):
        raise OfflineEvidenceError(f"{field} byte count differs after writing")
    reservation.sealed_state_identity = _state_identity(after)
    reservation.sealed_size = len(payload)
    reservation.sealed_sha256 = hashlib.sha256(payload).hexdigest()
    if _read_reserved_output_bytes(
        reservation,
        field,
        max_bytes=max_bytes,
    ) != payload:
        raise OfflineEvidenceError(f"{field} bytes differ after writing")
    _verify_reserved_output(reservation, field)
    return reservation.path


def _close_reserved_output(
    reservation: _ReservedOutput,
    *,
    discard: bool = False,
) -> None:
    cleanup_error: Exception | None = None
    if discard:
        try:
            _discard_reserved_entry_if_owned(
                reservation.path,
                reservation.parent_fd,
                reservation.descriptor,
            )
        except Exception as exc:
            cleanup_error = _merge_cleanup_error(
                cleanup_error,
                exc,
                label="reserved output quarantine",
            )
    for label, descriptor in (
        ("reserved output descriptor", reservation.descriptor),
        ("reserved output parent descriptor", reservation.parent_fd),
    ):
        try:
            os.close(descriptor)
        except Exception as exc:
            cleanup_error = _merge_cleanup_error(cleanup_error, exc, label=label)
    if cleanup_error is not None:
        raise cleanup_error


def _strict_output(path: str | Path) -> Path:
    output, parent_fd = _new_output_parent(path)
    os.close(parent_fd)
    return output


def _write_new(path: str | Path, value: Mapping[str, Any]) -> Path:
    try:
        payload = canonical_json_bytes(value)
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OfflineEvidenceError("evidence output is not canonical UTF-8 JSON") from exc
    reservation = _reserve_new_output(path)
    try:
        output = _write_reserved_bytes(reservation, payload, "evidence output")
    except Exception:
        _close_reserved_output(reservation, discard=True)
        raise
    _close_reserved_output(reservation)
    return output


def _write_new_bytes(path: str | Path, payload: bytes) -> Path:
    reservation = _reserve_new_output(path)
    try:
        output = _write_reserved_bytes(reservation, payload, "evidence output")
    except Exception:
        _close_reserved_output(reservation, discard=True)
        raise
    _close_reserved_output(reservation)
    return output


def _strict_json_bytes(payload: bytes, *, field: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise OfflineEvidenceError("JSON contains duplicate keys")
            value[key] = item
        return value

    def require_utf8_strings(item: object) -> None:
        if isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise OfflineEvidenceError(
                    f"{field} contains a non-UTF-8 string"
                ) from exc
            return
        if isinstance(item, Mapping):
            for key, child in item.items():
                require_utf8_strings(key)
                require_utf8_strings(child)
            return
        if isinstance(item, list):
            for child in item:
                require_utf8_strings(child)

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                OfflineEvidenceError(f"non-finite JSON value: {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfflineEvidenceError(f"invalid {field}") from exc
    if not isinstance(value, Mapping):
        raise OfflineEvidenceError(f"{field} must be an object")
    require_utf8_strings(value)
    return value


def _strict_json(
    path: Path,
    *,
    max_bytes: int = _DEFAULT_JSON_MAX_BYTES,
) -> Mapping[str, Any]:
    payload = _stable_file_bytes(
        path,
        "JSON evidence input",
        max_bytes=max_bytes,
    )
    return _strict_json_bytes(payload, field="JSON evidence input")


def _channel(channel_id: str) -> Any:
    from deploy.rag_store.server_answer_model import ServerAnswerChannel

    return ServerAnswerChannel(
        channel_id=channel_id,
        provider=f"fake-offline-{channel_id}",
        base_url=f"https://{channel_id}.invalid/v1/answer",
        region="synthetic-offline-region",
        model=f"fake-offline-model-{channel_id}",
        model_version=f"fake-offline-model-version-{channel_id}",
        api_version="fake-v1",
        timeout_seconds=0.2,
        max_input_units=200,
        max_output_units=80,
        max_cost_microunits=100,
    )


def _request() -> Any:
    from deploy.rag_store.server_answer_model import ServerAnswerRequest

    question = "合成问题"
    evidence = "合成证据"
    return ServerAnswerRequest(
        request_id="offline-evidence-request",
        question=question,
        evidence=({"evidence_id": "synthetic-evidence-1", "text": evidence},),
        input_units=len(question) + len(evidence),
    )


def _policy(strategy: str, channel_ids: Sequence[str]) -> Any:
    from deploy.rag_store.server_answer_coordinator import CoordinatorPolicy

    return CoordinatorPolicy(
        strategy=strategy,
        ordered_channel_ids=tuple(channel_ids),
        winner_policy="ordered_success",
        total_budget_seconds=0.3,
        total_cost_budget_microunits=100 * len(channel_ids),
        circuit_breaker_failure_threshold=2,
        circuit_breaker_cooldown_seconds=10.0,
    )


def _adapter(
    channel: Any,
    transport: Any,
    *,
    clock_start: float,
) -> Any:
    from deploy.rag_store.server_answer_model import ServerAnswerModelAdapter

    return ServerAnswerModelAdapter(
        channel,
        transport=transport,
        clock=_StepClock(clock_start),
    )


def _run_record(run_id: str, strategy: str, behaviors: Sequence[str]) -> dict[str, Any]:
    from deploy.cloud_v2.fake_providers import FakeServerAnswerTransport
    from deploy.rag_store.server_answer_coordinator import ServerAnswerCoordinator

    channel_ids = tuple(f"synthetic-{index}" for index in range(1, len(behaviors) + 1))
    channels = tuple(_channel(channel_id) for channel_id in channel_ids)
    transports = tuple(FakeServerAnswerTransport(behavior=behavior) for behavior in behaviors)
    adapters = tuple(
        _adapter(channel, transport, clock_start=100.0 + index)
        for index, (channel, transport) in enumerate(zip(channels, transports))
    )
    coordinator = ServerAnswerCoordinator(
        adapters,
        policy=_policy(strategy, channel_ids),
        clock=_StepClock(200.0),
    )
    result = coordinator.coordinate(_request())
    ledger = [asdict(entry) for entry in result.ledger]
    transport_call_counts = [item.call_count for item in transports]
    if any(call_count not in {0, 1} for call_count in transport_call_counts):
        raise OfflineEvidenceError("offline fake transport was called more than once")
    started_channel_ids = [
        channel_id
        for channel_id, call_count in zip(channel_ids, transport_call_counts)
        if call_count == 1
    ]
    if [entry["channel_id"] for entry in ledger] != started_channel_ids:
        raise OfflineEvidenceError("ledger does not cover every disclosed fake call")
    if any(not entry["disclosed"] for entry in ledger):
        raise OfflineEvidenceError("offline evidence unexpectedly contains an undisclosed entry")
    if result.winner_channel_id != channel_ids[-1 if strategy == "sequential_fallback" else 0]:
        raise OfflineEvidenceError("offline coordinator winner drifted")
    return {
        "run_id": run_id,
        "policy": {
            "strategy": strategy,
            "ordered_channel_ids": list(channel_ids),
            "winner_policy": "ordered_success",
        },
        "winner_channel_id": result.winner_channel_id,
        "answer_sha256": hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
        "channel_identities": [channel.identity() for channel in channels],
        "channel_identity_sha256s": [channel.identity_sha256 for channel in channels],
        "started_channel_ids": started_channel_ids,
        "transport_call_counts": transport_call_counts,
        "transport_request_sha256s": [list(item.request_hashes) for item in transports],
        "ledger": ledger,
        "skipped_channel_ids": list(result.skipped_channel_ids),
    }


def _disclosure_source_records(root: Path) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for relative in DISCLOSURE_SOURCE_PATHS:
        path = root / relative
        try:
            digest = _stable_file_sha256(path, f"evidence source {relative}")
        except OfflineEvidenceError as exc:
            raise OfflineEvidenceError(
                f"evidence source is unavailable: {relative}"
            ) from exc
        sources.append({"path": relative, "sha256": digest})
    return sources


def _require_disclosure_sources_unchanged(
    root: Path,
    expected: object,
) -> None:
    if _disclosure_source_records(root) != expected:
        raise OfflineEvidenceError("disclosure evidence source files changed during build")


def _disclosure_receipt_value(
    *, repo_root: str | Path, created_at: str
) -> dict[str, Any]:
    created_at = _require_utc_second(created_at, "created_at")
    raw_root = Path(repo_root)
    if raw_root.is_symlink():
        raise OfflineEvidenceError("repository root must be a real directory")
    root, root_fd = _open_directory_fd(raw_root, "repository root")
    os.close(root_fd)
    sources = _disclosure_source_records(root)
    runs = [
        _run_record("single-success", "single", ("success",)),
        _run_record(
            "sequential-fallback",
            "sequential_fallback",
            ("failure", "success"),
        ),
        _run_record(
            "parallel-hedge",
            "parallel_hedge",
            ("success", "success"),
        ),
    ]
    return {
        "schema_version": DISCLOSURE_EVIDENCE_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "created_at": created_at,
        "provider_mode": "sealed-offline-fake-only",
        "real_provider_calls": 0,
        "network_calls": 0,
        "contains_real_source_or_user_data": False,
        "source_files": sources,
        "runs": runs,
        "gates": {
            "run_count": len(runs),
            "started_channel_count": sum(
                sum(run["transport_call_counts"]) for run in runs
            ),
            "ledger_entry_count": sum(len(run["ledger"]) for run in runs),
            "all_started_channels_disclosed_and_accounted": True,
        },
    }


def _build_disclosure_evidence_in_process(
    *,
    repo_root: str | Path,
    output_path: str | Path,
    created_at: str,
) -> dict[str, Any]:
    raw_root = Path(repo_root)
    if raw_root.is_symlink():
        raise OfflineEvidenceError("repository root must be a real directory")
    root, root_fd = _open_directory_fd(raw_root, "repository root")
    reservation: _ReservedOutput | None = None
    completed = False
    try:
        receipt = _disclosure_receipt_value(repo_root=root, created_at=created_at)
        expected_sources = receipt["source_files"]
        _revalidate_directory_path(raw_root, root_fd, "repository root")
        _require_disclosure_sources_unchanged(root, expected_sources)
        reservation = _reserve_new_output(output_path, readable=True)
        receipt_payload = canonical_json_bytes(receipt)
        _revalidate_directory_path(raw_root, root_fd, "repository root")
        _require_disclosure_sources_unchanged(root, expected_sources)
        _write_reserved_bytes(
            reservation,
            receipt_payload,
            "disclosure evidence",
        )
        _revalidate_directory_path(raw_root, root_fd, "repository root")
        _require_disclosure_sources_unchanged(root, expected_sources)
        _revalidate_reserved_path(reservation, "disclosure evidence")
        receipt["receipt_sha256"] = hashlib.sha256(receipt_payload).hexdigest()
        completed = True
        return receipt
    finally:
        if reservation is not None:
            _close_reserved_output(reservation, discard=not completed)
        os.close(root_fd)


def _validate_disclosure_evidence_in_process(
    *, repo_root: str | Path, receipt_path: str | Path
) -> dict[str, Any]:
    descriptor, parent_fd, state, _path = _open_regular_fd(
        receipt_path,
        "disclosure evidence",
    )
    try:
        _require_sealed_file_mode(state, "disclosure evidence")
        payload = _read_open_bytes(
            descriptor,
            state,
            "disclosure evidence",
            max_bytes=16 * 1024 * 1024,
        )
    finally:
        os.close(descriptor)
        os.close(parent_fd)
    value = dict(_strict_json_bytes(payload, field="disclosure evidence"))
    if payload != canonical_json_bytes(value):
        raise OfflineEvidenceError("disclosure evidence is not canonical JSON")
    created_at = value.get("created_at")
    expected = _disclosure_receipt_value(
        repo_root=repo_root,
        created_at=created_at if isinstance(created_at, str) else "",
    )
    if not _type_sensitive_equal(value, expected):
        raise OfflineEvidenceError(
            "disclosure evidence is stale or differs from current coordinator bytes"
        )
    return {**value, "receipt_sha256": hashlib.sha256(payload).hexdigest()}


def _network_probe_specs() -> tuple[tuple[str, int, int, tuple[Any, ...]], ...]:
    probes: list[tuple[str, int, int, tuple[Any, ...]]] = [
        ("ipv4-tcp-loopback", socket.AF_INET, socket.SOCK_STREAM, ("127.0.0.1", 9)),
        ("ipv4-udp-loopback", socket.AF_INET, socket.SOCK_DGRAM, ("127.0.0.1", 9)),
    ]
    if socket.has_ipv6:
        probes.extend(
            (
                (
                    "ipv6-tcp-loopback",
                    socket.AF_INET6,
                    socket.SOCK_STREAM,
                    ("::1", 9, 0, 0),
                ),
                (
                    "ipv6-udp-loopback",
                    socket.AF_INET6,
                    socket.SOCK_DGRAM,
                    ("::1", 9, 0, 0),
                ),
            )
        )
    return tuple(probes)


def _network_enforcement_success() -> dict[str, Any]:
    return {
        "schema_version": NETWORK_ENFORCEMENT_SCHEMA_VERSION,
        "status": "passed",
        "denied_probe_ids": [probe[0] for probe in _network_probe_specs()],
    }


def _require_network_denial() -> dict[str, Any]:
    """Prove that the current process is subject to an OS network deny rule."""

    for probe_id, family, socket_type, address in _network_probe_specs():
        try:
            with _OS_SOCKET(family, socket_type) as probe:
                probe.settimeout(0.2)
                probe.connect(address)
        except OSError as exc:
            if exc.errno in {errno.EPERM, errno.EACCES}:
                continue
            raise OfflineEvidenceError(
                f"network sandbox did not deny active probe: {probe_id}"
            ) from exc
        raise OfflineEvidenceError(
            f"network sandbox did not deny active probe: {probe_id}"
        )
    return _network_enforcement_success()


def _loaded_module_origin_ledger(snapshot_root: Path) -> dict[str, Any]:
    """Bind every file-backed module loaded by a test child.

    The child may execute only modules from the private snapshot or the sealed
    Python runtime.  Absolute local paths are deliberately omitted from the
    receipt; the root class plus relative path and byte hash are sufficient to
    review the executed-origin closure without leaking the workstation path.
    """

    try:
        snapshot = snapshot_root.resolve(strict=True)
    except OSError as exc:
        raise OfflineEvidenceError("module origin snapshot is unavailable") from exc
    runtime_roots: list[tuple[str, Path]] = []
    seen_roots: set[Path] = set()
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = sysconfig.get_path(key)
        if not value:
            raise OfflineEvidenceError("module origin runtime path is unavailable")
        try:
            root = Path(value).resolve(strict=True)
        except OSError as exc:
            raise OfflineEvidenceError(
                "module origin runtime path is unavailable"
            ) from exc
        if root in seen_roots:
            continue
        seen_roots.add(root)
        runtime_roots.append((key, root))

    records: list[dict[str, str]] = []
    for module_name, module in sorted(sys.modules.items()):
        canonical_name = _FORMAL_MODULE_ORIGIN_ALIASES.get(module_name)
        if canonical_name is not None and module is sys.modules.get(canonical_name):
            # The held bootstraps install these compatibility aliases for legacy
            # imports. The canonical formal module record owns the source path.
            continue
        origin = getattr(module, "__file__", None)
        if origin is None:
            continue
        if (
            not isinstance(module_name, str)
            or not module_name
            or _has_control_character(module_name)
            or unicodedata.normalize("NFC", module_name) != module_name
            or not isinstance(origin, str)
            or not origin
        ):
            raise OfflineEvidenceError("loaded module origin is malformed")
        try:
            resolved = Path(origin).resolve(strict=True)
        except OSError as exc:
            raise OfflineEvidenceError(
                f"loaded module origin is unavailable: {module_name}"
            ) from exc
        root_kind: str | None = None
        relative: str | None = None
        try:
            relative = resolved.relative_to(snapshot).as_posix()
        except ValueError:
            for kind, root in runtime_roots:
                try:
                    relative = resolved.relative_to(root).as_posix()
                except ValueError:
                    continue
                root_kind = kind
                break
        else:
            root_kind = "snapshot"
        if root_kind is None or relative is None or not relative:
            raise OfflineEvidenceError(
                f"loaded module originated outside the sealed closure: {module_name}"
            )
        records.append(
            {
                "module": module_name,
                "root": root_kind,
                "relative_path": relative,
                "sha256": _stable_file_sha256(
                    resolved,
                    f"loaded module origin {module_name}",
                    enforce_safe_ancestors=False,
                ),
            }
        )
    if not records:
        raise OfflineEvidenceError("loaded module origin ledger is empty")
    value: dict[str, Any] = {
        "schema_version": MODULE_ORIGIN_LEDGER_SCHEMA_VERSION,
        "module_count": len(records),
        "origin_set_sha256": _identity_sha256(records),
        "origins": records,
    }
    value["identity_sha256"] = _identity_sha256(value)
    return value


def _snapshot_origin_is_in_scope(relative: str, test_scope: Mapping[str, Any]) -> bool:
    if relative in _SNAPSHOT_PACKAGE_ANCHORS:
        return True
    exact_files = test_scope.get("exact_files")
    tree_roots = test_scope.get("tree_roots")
    if not isinstance(exact_files, list) or not isinstance(tree_roots, list):
        raise OfflineEvidenceError("test child module origin scope is malformed")
    path = PurePosixPath(relative)
    return relative in exact_files or any(
        path == PurePosixPath(root) or PurePosixPath(root) in path.parents
        for root in tree_roots
    )


def _runtime_origin_sha256(root_kind: str, relative: str, field: str) -> str:
    configured = sysconfig.get_path(root_kind)
    if not configured:
        raise OfflineEvidenceError(f"{field} runtime root is unavailable")
    try:
        root = Path(configured).resolve(strict=True)
        candidate = (root / relative).resolve(strict=True)
        candidate.relative_to(root)
    except (OSError, ValueError) as exc:
        raise OfflineEvidenceError(f"{field} runtime path is unavailable") from exc
    return _stable_file_sha256(
        candidate,
        field,
        max_bytes=32 * 1024 * 1024,
        enforce_safe_ancestors=False,
    )


def _validated_module_origin_ledger(
    value: object,
    *,
    repo_fd: int | None = None,
    test_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "module_count",
        "origin_set_sha256",
        "origins",
        "identity_sha256",
    }:
        raise OfflineEvidenceError("test child module origin ledger is malformed")
    if value["schema_version"] != MODULE_ORIGIN_LEDGER_SCHEMA_VERSION:
        raise OfflineEvidenceError("test child module origin ledger schema mismatch")
    origins = value["origins"]
    if not isinstance(origins, list) or not origins:
        raise OfflineEvidenceError("test child module origin ledger is empty")
    formal_paths = {
        relative: module_name for module_name, relative in _FORMAL_MODULE_CLOSURE
    }
    formal_modules = dict(_FORMAL_MODULE_CLOSURE)
    observed_formal_modules: set[str] = set()
    previous_module = ""
    for record in origins:
        if not isinstance(record, Mapping) or set(record) != {
            "module",
            "root",
            "relative_path",
            "sha256",
        }:
            raise OfflineEvidenceError("test child module origin record is malformed")
        module_name = record["module"]
        relative = record["relative_path"]
        if (
            not isinstance(module_name, str)
            or not module_name
            or module_name <= previous_module
            or _has_control_character(module_name)
            or unicodedata.normalize("NFC", module_name) != module_name
            or record["root"]
            not in {"snapshot", "stdlib", "platstdlib", "purelib", "platlib"}
            or not isinstance(relative, str)
            or not relative
            or relative.startswith("/")
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in PurePosixPath(relative).parts)
            or not isinstance(record["sha256"], str)
            or not _SHA256.fullmatch(record["sha256"])
        ):
            raise OfflineEvidenceError("test child module origin record is invalid")
        if (repo_fd is None) != (test_scope is None):
            raise OfflineEvidenceError("test child module origin validation is unbound")
        expected_formal_path = formal_modules.get(module_name)
        if expected_formal_path is not None:
            if record["root"] != "snapshot" or relative != expected_formal_path:
                raise OfflineEvidenceError(
                    "test child formal module origin mapping mismatch"
                )
            observed_formal_modules.add(module_name)
        elif record["root"] == "snapshot" and relative in formal_paths:
            raise OfflineEvidenceError(
                "test child formal module path is claimed by an unexpected module"
            )
        if repo_fd is not None and test_scope is not None:
            if record["root"] == "snapshot":
                if not _snapshot_origin_is_in_scope(relative, test_scope):
                    raise OfflineEvidenceError(
                        "test child module origin escaped the declared snapshot"
                    )
                if relative in _SNAPSHOT_PACKAGE_ANCHORS:
                    actual_sha256 = hashlib.sha256(
                        _SNAPSHOT_PACKAGE_ANCHORS[relative]
                    ).hexdigest()
                else:
                    actual_sha256 = _stable_relative_file_sha256(
                        repo_fd,
                        relative,
                        f"test child module origin {module_name}",
                    )
            else:
                actual_sha256 = _runtime_origin_sha256(
                    record["root"],
                    relative,
                    f"test child module origin {module_name}",
                )
            if record["sha256"] != actual_sha256:
                raise OfflineEvidenceError(
                    "test child module origin does not match the sealed bytes"
                )
        previous_module = module_name
    if observed_formal_modules != set(formal_modules):
        raise OfflineEvidenceError(
            "test child formal module origin coverage is not exact"
        )
    core = {
        "schema_version": value["schema_version"],
        "module_count": len(origins),
        "origin_set_sha256": _identity_sha256(origins),
        "origins": origins,
    }
    if (
        type(value["module_count"]) is not int
        or value["module_count"] != len(origins)
        or value["origin_set_sha256"] != core["origin_set_sha256"]
        or value["identity_sha256"] != _identity_sha256(core)
    ):
        raise OfflineEvidenceError("test child module origin ledger identity mismatch")
    return dict(value)


def _test_process_payload(
    *,
    log_payload: bytes,
    runner_source_sha256: str,
    python_identity: Mapping[str, Any],
    test_scope: Mapping[str, Any],
    process_identity: Mapping[str, Any],
    module_origin_ledger: Mapping[str, Any],
    network_enforcement: Mapping[str, Any],
    sandbox_enforcement: Mapping[str, Any],
    test_id_manifest: Mapping[str, Any],
    test_count: int,
    successful: bool,
    failure_count: int,
    error_count: int,
    skipped_count: int,
) -> bytes:
    if not isinstance(log_payload, bytes) or len(log_payload) > 16 * 1024 * 1024:
        raise OfflineEvidenceError("test child log exceeds the closed size limit")
    if not isinstance(runner_source_sha256, str) or not _SHA256.fullmatch(
        runner_source_sha256
    ):
        raise OfflineEvidenceError("test child runner source SHA-256 is invalid")
    for field, value in (
        ("test_count", test_count),
        ("failure_count", failure_count),
        ("error_count", error_count),
        ("skipped_count", skipped_count),
    ):
        if type(value) is not int or value < 0:
            raise OfflineEvidenceError(f"test child {field} is invalid")
    if not isinstance(successful, bool):
        raise OfflineEvidenceError("test child success state is invalid")
    return canonical_json_bytes(
        {
            "schema_version": TEST_PROCESS_RESULT_SCHEMA_VERSION,
            "runner_source_path": OFFLINE_EVIDENCE_SOURCE_PATH,
            "runner_source_sha256": runner_source_sha256,
            "python_identity": dict(python_identity),
            "test_scope": dict(test_scope),
            "process_identity": _validated_process_identity(
                process_identity,
                "test child",
                require_session_leader=True,
            ),
            "module_origin_ledger": _validated_module_origin_ledger(
                module_origin_ledger
            ),
            "network_enforcement": dict(network_enforcement),
            "sandbox_enforcement": _validated_sandbox_enforcement(
                sandbox_enforcement
            ),
            "test_id_manifest": _validated_test_id_manifest(
                str(test_id_manifest.get("component", "")),
                test_id_manifest.get("test_ids", ()),
            ),
            "test_count": test_count,
            "successful": successful,
            "failure_count": failure_count,
            "error_count": error_count,
            "skipped_count": skipped_count,
            "unittest_log_base64": base64.b64encode(log_payload).decode("ascii"),
        }
    )


def _parse_test_process_payload(
    payload: bytes,
    *,
    runner: Mapping[str, Any],
    repo_fd: int | None = None,
    test_scope: Mapping[str, Any] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    if len(payload) > 24 * 1024 * 1024:
        raise OfflineEvidenceError("test child result exceeds the closed size limit")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfflineEvidenceError("test child result is not canonical JSON") from exc
    expected_fields = {
        "schema_version",
        "runner_source_path",
        "runner_source_sha256",
        "python_identity",
        "test_scope",
        "process_identity",
        "module_origin_ledger",
        "network_enforcement",
        "sandbox_enforcement",
        "test_id_manifest",
        "test_count",
        "successful",
        "failure_count",
        "error_count",
        "skipped_count",
        "unittest_log_base64",
    }
    if not isinstance(value, Mapping):
        raise OfflineEvidenceError("test child result identity mismatch")
    try:
        module_origin_ledger = _validated_module_origin_ledger(
            value.get("module_origin_ledger"),
            repo_fd=repo_fd,
            test_scope=test_scope,
        )
        process_identity = _validated_process_identity(
            value.get("process_identity"),
            "test child",
            require_session_leader=True,
        )
        sandbox_enforcement = _validated_sandbox_enforcement(
            value.get("sandbox_enforcement")
        )
        test_id_manifest_value = value.get("test_id_manifest")
        if not isinstance(test_id_manifest_value, Mapping):
            raise OfflineEvidenceError("test ID manifest is malformed")
        test_id_manifest = _validated_test_id_manifest(
            str(test_id_manifest_value.get("component", "")),
            test_id_manifest_value.get("test_ids", ()),
        )
    except OfflineEvidenceError as exc:
        raise OfflineEvidenceError("test child result identity mismatch") from exc
    if (
        set(value) != expected_fields
        or payload != canonical_json_bytes(value)
        or value["schema_version"] != TEST_PROCESS_RESULT_SCHEMA_VERSION
        or value["runner_source_path"] != OFFLINE_EVIDENCE_SOURCE_PATH
        or value["runner_source_sha256"] != runner.get("source_sha256")
        or not _type_sensitive_equal(
            value["python_identity"], runner.get("python_identity")
        )
        or not _type_sensitive_equal(value["test_scope"], runner.get("test_scope"))
        or not _type_sensitive_equal(value["process_identity"], process_identity)
        or not _type_sensitive_equal(value["module_origin_ledger"], module_origin_ledger)
        or not _type_sensitive_equal(
            value["network_enforcement"], _network_enforcement_success()
        )
        or not _type_sensitive_equal(value["sandbox_enforcement"], sandbox_enforcement)
        or value["test_id_manifest"] != test_id_manifest
        or value["test_count"] != test_id_manifest["test_count"]
        or not isinstance(value["successful"], bool)
    ):
        raise OfflineEvidenceError("test child result identity mismatch")
    for field in ("test_count", "failure_count", "error_count", "skipped_count"):
        if type(value[field]) is not int or value[field] < 0:
            raise OfflineEvidenceError("test child result count is invalid")
    encoded_log = value["unittest_log_base64"]
    if not isinstance(encoded_log, str):
        raise OfflineEvidenceError("test child log encoding is invalid")
    try:
        log_payload = base64.b64decode(encoded_log, validate=True)
    except (ValueError, TypeError) as exc:
        raise OfflineEvidenceError("test child log encoding is invalid") from exc
    if len(log_payload) > 16 * 1024 * 1024:
        raise OfflineEvidenceError("test child log exceeds the closed size limit")
    return log_payload, dict(value)


def _machine_result_from_process_result(
    process_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the persisted child result without duplicating the sealed log."""

    expected_fields = {
        "schema_version",
        "runner_source_path",
        "runner_source_sha256",
        "python_identity",
        "test_scope",
        "process_identity",
        "module_origin_ledger",
        "network_enforcement",
        "sandbox_enforcement",
        "test_id_manifest",
        "test_count",
        "successful",
        "failure_count",
        "error_count",
        "skipped_count",
        "unittest_log_base64",
    }
    if not isinstance(process_result, Mapping) or set(process_result) != expected_fields:
        raise OfflineEvidenceError("test child machine result is malformed")
    return {
        key: process_result[key]
        for key in sorted(expected_fields - {"unittest_log_base64"})
    }


def _reconstructed_process_payload(
    machine_result: object,
    log_payload: bytes,
    *,
    runner: Mapping[str, Any],
    repo_fd: int | None = None,
) -> tuple[bytes, dict[str, Any]]:
    if not isinstance(machine_result, Mapping):
        raise OfflineEvidenceError("test component machine result is malformed")
    expected_fields = {
        "schema_version",
        "runner_source_path",
        "runner_source_sha256",
        "python_identity",
        "test_scope",
        "process_identity",
        "module_origin_ledger",
        "network_enforcement",
        "sandbox_enforcement",
        "test_id_manifest",
        "test_count",
        "successful",
        "failure_count",
        "error_count",
        "skipped_count",
    }
    if set(machine_result) != expected_fields:
        raise OfflineEvidenceError("test component machine result is malformed")
    payload = canonical_json_bytes(
        {
            **dict(machine_result),
            "unittest_log_base64": base64.b64encode(log_payload).decode("ascii"),
        }
    )
    parsed_log, parsed_result = _parse_test_process_payload(
        payload,
        runner=runner,
        repo_fd=repo_fd,
        test_scope=(runner.get("test_scope") if repo_fd is not None else None),
    )
    if parsed_log != log_payload:
        raise OfflineEvidenceError("test component machine result log mismatch")
    return payload, parsed_result


def _create_cloexec_pipe() -> tuple[int, int]:
    try:
        read_fd, write_fd = os.pipe()
        for descriptor in (read_fd, write_fd):
            os.set_inheritable(descriptor, False)
            os.set_blocking(descriptor, False)
    except OSError as exc:
        for descriptor in (locals().get("read_fd"), locals().get("write_fd")):
            if isinstance(descriptor, int):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        raise OfflineEvidenceError("parent broker pipe could not be created") from exc
    if (
        os.get_inheritable(read_fd)
        or os.get_inheritable(write_fd)
        or os.get_blocking(read_fd)
        or os.get_blocking(write_fd)
    ):
        os.close(read_fd)
        os.close(write_fd)
        raise OfflineEvidenceError("parent broker pipe is inheritable")
    return read_fd, write_fd


def _write_broker_frame(
    descriptor: int,
    payload: bytes,
    *,
    deadline: float | None = None,
) -> None:
    if (
        not isinstance(payload, bytes)
        or not payload
        or len(payload) > _BROKER_FRAME_MAX_BYTES
    ):
        raise OfflineEvidenceError("parent broker frame is invalid")
    framed = struct.pack(">I", len(payload)) + payload
    written = 0
    while written < len(framed):
        remaining = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OfflineEvidenceError("parent broker protocol timed out")
        try:
            _readable, writable, exceptional = select.select(
                [], [descriptor], [descriptor], remaining
            )
        except InterruptedError:
            continue
        except (OSError, ValueError) as exc:
            raise OfflineEvidenceError(
                "parent broker frame descriptor could not be polled"
            ) from exc
        if exceptional:
            raise OfflineEvidenceError("parent broker frame descriptor failed")
        if not writable:
            raise OfflineEvidenceError("parent broker protocol timed out")
        try:
            count = os.write(descriptor, framed[written:])
        except (BlockingIOError, InterruptedError):
            continue
        except OSError as exc:
            raise OfflineEvidenceError("parent broker frame could not be written") from exc
        if count <= 0:
            raise OfflineEvidenceError("parent broker frame could not be written")
        written += count


def _read_broker_bytes(
    descriptor: int,
    length: int,
    *,
    deadline: float | None,
    allow_initial_eof: bool = False,
) -> bytes | None:
    payload = bytearray()
    while len(payload) < length:
        remaining = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OfflineEvidenceError("parent broker protocol timed out")
        try:
            readable, _writable, exceptional = select.select(
                [descriptor], [], [descriptor], remaining
            )
        except InterruptedError:
            continue
        except (OSError, ValueError) as exc:
            raise OfflineEvidenceError(
                "parent broker frame descriptor could not be polled"
            ) from exc
        if exceptional:
            raise OfflineEvidenceError("parent broker frame descriptor failed")
        if not readable:
            raise OfflineEvidenceError("parent broker protocol timed out")
        try:
            chunk = os.read(descriptor, length - len(payload))
        except (BlockingIOError, InterruptedError):
            continue
        except OSError as exc:
            raise OfflineEvidenceError("parent broker frame could not be read") from exc
        if not chunk:
            if allow_initial_eof and not payload:
                return None
            raise OfflineEvidenceError("parent broker frame is truncated")
        payload.extend(chunk)
    return bytes(payload)


def _read_broker_frame(
    descriptor: int,
    *,
    deadline: float | None = None,
    allow_eof: bool = False,
) -> bytes | None:
    header = _read_broker_bytes(
        descriptor,
        4,
        deadline=deadline,
        allow_initial_eof=allow_eof,
    )
    if header is None:
        return None
    length = struct.unpack(">I", header)[0]
    if length <= 0 or length > _BROKER_FRAME_MAX_BYTES:
        raise OfflineEvidenceError("parent broker frame length is invalid")
    return _read_broker_bytes(descriptor, length, deadline=deadline)


def _validated_parent_broker_output(
    stdout: object,
    stderr: object,
    *,
    field: str,
) -> tuple[bytes, bytes | None]:
    if not isinstance(stdout, bytes) or (
        stderr is not None and not isinstance(stderr, bytes)
    ):
        raise OfflineEvidenceError(f"{field} output is malformed")
    stderr_size = 0 if stderr is None else len(stderr)
    if (
        len(stdout) > _BROKER_STDOUT_MAX_BYTES
        or stderr_size > _BROKER_STDERR_MAX_BYTES
        or len(stdout) + stderr_size > _BROKER_TOTAL_OUTPUT_MAX_BYTES
    ):
        raise OfflineEvidenceError(f"{field} output exceeds the size limit")
    return stdout, stderr


def _canonical_parent_broker_response_payload(response: Mapping[str, Any]) -> bytes:
    payload = canonical_json_bytes(response)
    stdout_base64 = response.get("stdout_base64")
    stderr_base64 = response.get("stderr_base64")
    if not isinstance(stdout_base64, str) or not (
        stderr_base64 is None or isinstance(stderr_base64, str)
    ):
        raise OfflineEvidenceError("parent broker response envelope is malformed")
    try:
        encoded_output_size = len(stdout_base64.encode("ascii")) + (
            0 if stderr_base64 is None else len(stderr_base64.encode("ascii"))
        )
    except UnicodeEncodeError as exc:
        raise OfflineEvidenceError("parent broker response envelope is malformed") from exc
    envelope_size = len(payload) - encoded_output_size
    if (
        envelope_size < 0
        or envelope_size > _BROKER_RESPONSE_ENVELOPE_MAX_BYTES
        or len(payload) > _BROKER_FRAME_MAX_BYTES
    ):
        raise OfflineEvidenceError("parent broker response exceeds the frame envelope")
    return payload


def _descriptor_directory_path(descriptor: int, field: str) -> Path:
    if type(descriptor) is not int or descriptor <= 2:
        raise OfflineEvidenceError(f"{field} descriptor is invalid")
    try:
        state = os.fstat(descriptor)
        if sys.platform == "darwin":
            raw = fcntl.fcntl(descriptor, 50, b"\0" * 1024)
            encoded = bytes(raw).split(b"\0", 1)[0]
            path = Path(os.fsdecode(encoded))
        else:
            path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        resolved = path.resolve(strict=True)
        path_state = resolved.stat(follow_symlinks=False)
    except (OSError, UnicodeError, ValueError) as exc:
        raise OfflineEvidenceError(f"{field} descriptor path is unavailable") from exc
    if (
        not stat.S_ISDIR(state.st_mode)
        or _inode_identity(state) != _inode_identity(path_state)
        or not resolved.is_absolute()
    ):
        raise OfflineEvidenceError(f"{field} descriptor path identity mismatch")
    return resolved


def _descriptor_regular_file_path(descriptor: int, field: str) -> Path:
    if type(descriptor) is not int or descriptor <= 2:
        raise OfflineEvidenceError(f"{field} descriptor is invalid")
    try:
        state = os.fstat(descriptor)
        if sys.platform == "darwin":
            raw = fcntl.fcntl(descriptor, 50, b"\0" * 1024)
            encoded = bytes(raw).split(b"\0", 1)[0]
            path = Path(os.fsdecode(encoded))
        else:
            path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        resolved = path.resolve(strict=True)
        path_state = resolved.stat(follow_symlinks=False)
    except (OSError, UnicodeError, ValueError) as exc:
        raise OfflineEvidenceError(f"{field} descriptor path is unavailable") from exc
    if (
        not stat.S_ISREG(state.st_mode)
        or _inode_identity(state) != _inode_identity(path_state)
        or not resolved.is_absolute()
    ):
        raise OfflineEvidenceError(f"{field} descriptor path identity mismatch")
    return resolved


def _sandbox_profile_input(
    command_value: str,
    input_payload: object,
    pass_fds: tuple[int, ...],
) -> bytes:
    if (
        command_value != "/dev/stdin"
        or type(input_payload) is not bytes
        or not input_payload
        or len(input_payload) > 2 * 1024 * 1024
        or subprocess.PIPE in pass_fds
    ):
        raise OfflineEvidenceError("sandbox profile pipe input is not fixed")
    return input_payload


def _worker_relative_directory(
    path: Path,
    worker_scratch: Path,
    field: str,
) -> str:
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(worker_scratch.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise OfflineEvidenceError(f"{field} escapes the parent worker scratch") from exc
    canonical = _canonical_relative(relative, field)
    if not resolved.is_dir() or resolved.is_symlink():
        raise OfflineEvidenceError(f"{field} must be a real directory")
    return canonical


def _parent_broker_plan(probe_id: str) -> tuple[str, ...]:
    if set(_FORMAL_PARENT_BROKER_PLANS) != {
        spec[0] for spec in _FORMAL_PARENT_PROBE_SPECS
    }:
        raise OfflineEvidenceError("formal parent broker plan coverage is not exact")
    try:
        plan = tuple(_FORMAL_PARENT_BROKER_PLANS[probe_id])
    except KeyError as exc:
        raise OfflineEvidenceError("formal parent broker probe is not allowlisted") from exc
    if (
        not plan
        or any(
            not isinstance(operation, str)
            or not _IDENTIFIER.fullmatch(operation)
            for operation in plan
        )
    ):
        raise OfflineEvidenceError("formal parent broker plan is malformed")
    return plan


def _parent_broker_session_identity(
    *,
    probe_id: str,
    runner: Mapping[str, Any],
    worker_sandbox_binding_sha256: str,
) -> str:
    test_scope = runner.get("test_scope")
    python_identity = runner.get("python_identity")
    if (
        not isinstance(test_scope, Mapping)
        or not isinstance(test_scope.get("identity_sha256"), str)
        or not _SHA256.fullmatch(test_scope["identity_sha256"])
        or not isinstance(python_identity, Mapping)
        or not isinstance(worker_sandbox_binding_sha256, str)
        or not _SHA256.fullmatch(worker_sandbox_binding_sha256)
    ):
        raise OfflineEvidenceError("formal parent broker session input is malformed")
    return _identity_sha256(
        {
            "protocol": PARENT_BROKER_PROTOCOL_SCHEMA_VERSION,
            "probe_id": probe_id,
            "snapshot_identity_sha256": test_scope["identity_sha256"],
            "python_identity_sha256": _identity_sha256(python_identity),
            "worker_sandbox_binding_sha256": worker_sandbox_binding_sha256,
            "operation_ids": list(_parent_broker_plan(probe_id)),
        }
    )


def _ocr_worker_relative_path(
    path: Path,
    worker_scratch: Path,
    field: str,
    *,
    directory: bool,
) -> str:
    canonical = _lexically_normal_absolute(path, field)
    try:
        worker = worker_scratch.resolve(strict=True)
        state = canonical.lstat()
        resolved = canonical.resolve(strict=True)
        relative = resolved.relative_to(worker).as_posix()
    except (OSError, ValueError) as exc:
        raise OfflineEvidenceError(f"{field} escapes the parent worker scratch") from exc
    if (
        canonical != resolved
        or stat.S_ISLNK(state.st_mode)
        or (directory and not stat.S_ISDIR(state.st_mode))
        or (not directory and (not stat.S_ISREG(state.st_mode) or state.st_nlink != 1))
    ):
        raise OfflineEvidenceError(f"{field} is not a fixed real path")
    return _canonical_relative(relative, field)


def _ocr_native_invocation(
    command: Sequence[str],
    kwargs: Mapping[str, Any],
    *,
    probe_id: str,
    worker_scratch: Path,
) -> tuple[str, dict[str, Any]]:
    if not _is_ocr_native_probe(probe_id):
        raise OfflineEvidenceError("parent broker OCR probe is not allowlisted")
    values = list(command)
    if (
        len(values) < 7
        or values[:2] != [str(NETWORK_SANDBOX_PATH), "-p"]
        or values[3:5] != ["/usr/bin/env", "-i"]
        or not isinstance(values[2], str)
        or not values[2]
    ):
        raise OfflineEvidenceError("parent broker OCR command is not allowlisted")
    tool_index = next(
        (index for index in range(5, len(values)) if "=" not in values[index]),
        len(values),
    )
    assignment_values = values[5:tool_index]
    if not assignment_values or tool_index == len(values):
        raise OfflineEvidenceError("parent broker OCR environment is malformed")
    assignments: dict[str, str] = {}
    for assignment in assignment_values:
        name, separator, item = assignment.partition("=")
        if (
            separator != "="
            or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
            or name in assignments
            or _has_control_character(item)
        ):
            raise OfflineEvidenceError("parent broker OCR environment is malformed")
        assignments[name] = item
    if assignment_values != [
        f"{name}={assignments[name]}" for name in sorted(assignments)
    ]:
        raise OfflineEvidenceError("parent broker OCR environment is not canonical")
    environment = kwargs.get("env")
    if (
        not isinstance(environment, Mapping)
        or any(
            not isinstance(name, str) or not isinstance(item, str)
            for name, item in environment.items()
        )
        or not _type_sensitive_equal(dict(environment), assignments)
    ):
        raise OfflineEvidenceError("parent broker OCR environment is not exact")
    tool_command = values[tool_index:]
    executable = Path(tool_command[0])
    tool = executable.name
    approved_tools = (
        {"pdftoppm", "tesseract"}
        if _is_ocr_tessdata_probe(probe_id)
        else {"pdftoppm"}
    )
    if tool not in approved_tools:
        raise OfflineEvidenceError("parent broker OCR tool is not allowlisted")
    expected_kwargs = {
        "check",
        "stdout",
        "stderr",
        "timeout",
        "env",
        "cwd",
        "input" if tool == "pdftoppm" else "stdin",
    }
    if (
        set(kwargs) != expected_kwargs
        or kwargs["check"] is not False
        or kwargs["stdout"] != subprocess.PIPE
        or kwargs["stderr"] != subprocess.PIPE
        or not isinstance(kwargs["cwd"], str)
    ):
        raise OfflineEvidenceError("parent broker OCR invocation is malformed")
    scratch_path = Path(kwargs["cwd"])
    scratch_relative = _ocr_worker_relative_path(
        scratch_path,
        worker_scratch,
        "parent broker OCR scratch",
        directory=True,
    )
    private_executable_relative = _ocr_worker_relative_path(
        executable,
        worker_scratch,
        "parent broker OCR private executable",
        directory=False,
    )
    if environment.get("PATH") != _OCR_NATIVE_TOOL_SEARCH_PATH:
        raise OfflineEvidenceError("parent broker OCR PATH is not fixed")
    scratch_values = [
        environment.get(name) for name in ("TMPDIR", "TMP", "TEMP", "HOME")
    ]
    if scratch_values != [str(scratch_path)] * 4:
        raise OfflineEvidenceError("parent broker OCR scratch environment is not fixed")
    library_path = Path(str(environment.get("DYLD_LIBRARY_PATH", "")))
    private_library_relative = _ocr_worker_relative_path(
        library_path,
        worker_scratch,
        "parent broker OCR private library",
        directory=True,
    )
    profile_payload = values[2].encode("utf-8")
    if len(profile_payload) > 2 * 1024 * 1024:
        raise OfflineEvidenceError("parent broker OCR profile exceeds the size limit")

    output_prefix_relative: str | None = None
    approved_page_relative: str | None = None
    private_tessdata_relative: str | None = None
    private_fontconfig_relative: str | None = None
    input_snapshot_relative: str | None = None
    page_number: int | None = None
    input_payload: bytes | None
    input_size: int
    input_sha256: str | None
    if tool == "pdftoppm":
        input_value = kwargs["input"]
        if type(input_value) is not bytes or not input_value:
            raise OfflineEvidenceError("parent broker pdftoppm input is malformed")
        input_digest = hashlib.sha256(input_value).hexdigest()
        containment = scratch_path.parent
        native_runtime = executable.parents[1]
        if _is_ocr_tessdata_probe(probe_id):
            if (
                tool_command[1:7]
                != ["-r", "170", "-jpeg", "-jpegopt", "quality=92", "-"]
                or len(tool_command) != 8
                or scratch_path.name != "poppler-scratch"
            ):
                raise OfflineEvidenceError(
                    "parent broker pdftoppm command is not fixed"
                )
            output_prefix = Path(tool_command[7])
            if (
                native_runtime.name != "poppler-runtime"
                or native_runtime.parent != containment
                or executable.parent.name != "bin"
                or library_path != native_runtime / "lib"
                or output_prefix.name != "page"
                or output_prefix.parent.name != "rendered-pages"
                or output_prefix.parent.parent != containment
            ):
                raise OfflineEvidenceError(
                    "parent broker pdftoppm paths are not fixed"
                )
            output_parent_relative = _ocr_worker_relative_path(
                output_prefix.parent,
                worker_scratch,
                "parent broker pdftoppm output root",
                directory=True,
            )
            output_prefix_relative = f"{output_parent_relative}/page"
            if len(input_value) > _OCR_NATIVE_INPUT_MAX_BYTES:
                raise OfflineEvidenceError(
                    "parent broker pdftoppm input is malformed"
                )
            input_payload = input_value
            input_delivery = "inline-base64"
            input_size = len(input_value)
            input_sha256 = input_digest
            expected_timeout = 900
        else:
            if (
                tool_command[1:]
                != [
                    "-f",
                    "132",
                    "-l",
                    "132",
                    "-singlefile",
                    "-r",
                    "170",
                    "-jpeg",
                    "-jpegopt",
                    "quality=92",
                    "-",
                ]
                or native_runtime != containment / "native-runtime"
                or executable.parent.name != "bin"
                or library_path != native_runtime / "lib"
                or scratch_path != containment / "scratch"
                or len(input_value) != _OCR_PAGE_132_INPUT_ANCHOR["size"]
                or input_digest != _OCR_PAGE_132_INPUT_ANCHOR["sha256"]
            ):
                raise OfflineEvidenceError(
                    "parent broker page 132 pdftoppm invocation is not fixed"
                )
            page_number = 132
            input_payload = None
            input_delivery = "sealed-snapshot-held-descriptor"
            input_snapshot_relative = _OCR_PAGE_132_SOURCE_RELATIVE
            input_size = len(input_value)
            input_sha256 = input_digest
            expected_timeout = 300
        fontconfig_path = Path(str(environment.get("FONTCONFIG_FILE", "")))
        if fontconfig_path != native_runtime / "fontconfig/fonts.conf":
            raise OfflineEvidenceError("parent broker pdftoppm fontconfig is not fixed")
        private_fontconfig_relative = _ocr_worker_relative_path(
            fontconfig_path,
            worker_scratch,
            "parent broker pdftoppm fontconfig",
            directory=False,
        )
        stdin_role = "pdf-bytes-pipe"
    else:
        if (
            len(tool_command) != 7
            or tool_command[2:]
            != ["stdout", "-l", "chi_sim+eng", "--psm", "6"]
            or kwargs["stdin"] != subprocess.DEVNULL
            or scratch_path.parent.name != "tesseract-scratch"
        ):
            raise OfflineEvidenceError("parent broker tesseract command is not fixed")
        containment = scratch_path.parents[1]
        native_runtime = executable.parents[2]
        native_leaf = executable.parents[1]
        page = Path(tool_command[1])
        match = re.fullmatch(r"page-([0-9]{2})\.jpg", page.name)
        scratch_match = re.fullmatch(r"page-([1-9]|10)", scratch_path.name)
        if match is None or scratch_match is None:
            raise OfflineEvidenceError("parent broker tesseract page is malformed")
        page_number = int(match.group(1))
        if (
            page_number != int(scratch_match.group(1))
            or page_number not in range(1, 11)
            or native_runtime.name != "ocr-runtime"
            or native_runtime.parent != containment
            or native_leaf != native_runtime / "native"
            or executable.parent.name != "bin"
            or library_path != native_leaf / "lib"
            or page.parent != containment / "approved-pages"
        ):
            raise OfflineEvidenceError("parent broker tesseract paths are not fixed")
        approved_page_relative = _ocr_worker_relative_path(
            page,
            worker_scratch,
            "parent broker tesseract approved page",
            directory=False,
        )
        tessdata_path = Path(str(environment.get("TESSDATA_PREFIX", "")))
        if (
            environment.get("OMP_THREAD_LIMIT") != "1"
            or tessdata_path != native_runtime / "tessdata"
        ):
            raise OfflineEvidenceError("parent broker tesseract environment is not fixed")
        private_tessdata_relative = _ocr_worker_relative_path(
            tessdata_path,
            worker_scratch,
            "parent broker tesseract private tessdata",
            directory=True,
        )
        input_payload = None
        input_delivery = "none"
        input_size = 0
        input_sha256 = None
        stdin_role = "devnull"
        expected_timeout = 120
    expected_environment_names = {
        "PATH",
        "DYLD_LIBRARY_PATH",
        "TMPDIR",
        "TMP",
        "TEMP",
        "HOME",
        *(
            ("FONTCONFIG_FILE",)
            if tool == "pdftoppm"
            else ("TESSDATA_PREFIX", "OMP_THREAD_LIMIT")
        ),
    }
    timeout = kwargs["timeout"]
    if (
        set(environment) != expected_environment_names
        or type(timeout) is not int
        or timeout != expected_timeout
    ):
        raise OfflineEvidenceError("parent broker OCR invocation is not fixed")
    containment_relative = _ocr_worker_relative_path(
        containment,
        worker_scratch,
        "parent broker OCR containment",
        directory=True,
    )
    native_runtime_relative = _ocr_worker_relative_path(
        native_runtime,
        worker_scratch,
        "parent broker OCR native runtime",
        directory=True,
    )
    return f"ocr-native-{tool}", {
        "kind": "ocr-native",
        "tool": tool,
        "containment_relative": containment_relative,
        "native_runtime_relative": native_runtime_relative,
        "private_executable_relative": private_executable_relative,
        "private_library_relative": private_library_relative,
        "private_fontconfig_relative": private_fontconfig_relative,
        "scratch_relative": scratch_relative,
        "output_prefix_relative": output_prefix_relative,
        "approved_page_relative": approved_page_relative,
        "private_tessdata_relative": private_tessdata_relative,
        "page_number": page_number,
        "profile_base64": base64.b64encode(profile_payload).decode("ascii"),
        "profile_size": len(profile_payload),
        "profile_sha256": hashlib.sha256(profile_payload).hexdigest(),
        "environment": dict(environment),
        "environment_sha256": _identity_sha256(environment),
        "stdin_role": stdin_role,
        "input_delivery": input_delivery,
        "input_base64": (
            None
            if input_payload is None
            else base64.b64encode(input_payload).decode("ascii")
        ),
        "input_snapshot_relative": input_snapshot_relative,
        "input_size": input_size,
        "input_sha256": input_sha256,
        "timeout_seconds": float(timeout),
        "capture_mode": "bytes-separate-stdout-stderr",
    }


def _parent_broker_invocation(
    command: object,
    kwargs: Mapping[str, Any],
    *,
    probe_id: str,
    worker_scratch: Path,
) -> tuple[str, dict[str, Any]]:
    if (
        not isinstance(command, (list, tuple))
        or not command
        or any(not isinstance(item, str) for item in command)
    ):
        raise OfflineEvidenceError("parent broker command is malformed")
    values = list(command)
    if _is_ocr_native_probe(probe_id):
        return _ocr_native_invocation(
            values,
            kwargs,
            probe_id=probe_id,
            worker_scratch=worker_scratch,
        )
    if (
        len(values) < 9
        or values[0] != str(NETWORK_SANDBOX_PATH)
        or values[1] != "-f"
        or values[3] != str(_python_executable())
        or values[4:8] != ["-I", "-S", "-B", "-c"]
        or kwargs.get("cwd") is not None
        or kwargs.get("check") is not False
        or "stdin" in kwargs
    ):
        raise OfflineEvidenceError("parent broker command is not allowlisted")
    pass_fds = kwargs.get("pass_fds")
    if (
        not isinstance(pass_fds, tuple)
        or len(pass_fds) != 1
        or any(type(descriptor) is not int or descriptor <= 2 for descriptor in pass_fds)
        or len(set(pass_fds)) != 1
    ):
        raise OfflineEvidenceError("parent broker child descriptor set is not exact")
    supplied_profile_payload = _sandbox_profile_input(
        values[2], kwargs.get("input"), pass_fds
    )
    snapshot_path = _descriptor_directory_path(
        pass_fds[0], "parent broker child snapshot"
    )
    snapshot_relative = _worker_relative_directory(
        snapshot_path, worker_scratch, "parent broker child snapshot"
    )
    environment = kwargs.get("env")
    if not isinstance(environment, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise OfflineEvidenceError("parent broker child environment is malformed")
    scratch_values = [environment.get(key) for key in ("TMPDIR", "TMP", "TEMP", "HOME")]
    if any(not isinstance(value, str) for value in scratch_values) or len(
        set(scratch_values)
    ) != 1:
        raise OfflineEvidenceError("parent broker child scratch environment is not exact")
    child_scratch_path = Path(str(scratch_values[0]))
    scratch_relative = _worker_relative_directory(
        child_scratch_path, worker_scratch, "parent broker child scratch"
    )
    staged_profile = _hold_file_under_root(
        child_scratch_path / "component.sb",
        child_scratch_path,
        "parent broker supplied profile",
        max_bytes=2 * 1024 * 1024,
    )
    try:
        if staged_profile.payload != supplied_profile_payload:
            raise OfflineEvidenceError(
                "parent broker profile pipe bytes differ from held profile"
            )
    finally:
        _close_held_file(staged_profile)
    try:
        supplied_profile_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OfflineEvidenceError("parent broker supplied profile is not UTF-8") from exc
    supplied_profile_sha256 = hashlib.sha256(supplied_profile_payload).hexdigest()
    timeout = kwargs.get("timeout")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise OfflineEvidenceError("parent broker child timeout is invalid")

    common: dict[str, Any] = {
        "snapshot_relative": snapshot_relative,
        "scratch_relative": scratch_relative,
        "supplied_profile_parent_relative": scratch_relative,
        "supplied_profile_size": len(supplied_profile_payload),
        "stdin_role": "sandbox-profile-pipe",
        "supplied_profile_sha256": supplied_profile_sha256,
        "timeout_seconds": float(timeout),
    }
    bootstrap = values[8]
    if bootstrap == _DISCLOSURE_SUBPROCESS_BOOTSTRAP:
        if (
            len(values) != 16
            or kwargs.get("stdout") != subprocess.PIPE
            or kwargs.get("stderr") != subprocess.STDOUT
            or kwargs.get("capture_output") is not None
            or kwargs.get("text") is not None
        ):
            raise OfflineEvidenceError("parent broker disclosure invocation is malformed")
        action = values[10]
        operation_id = f"disclosure-{action}"
        if action not in {"build", "validate"}:
            raise OfflineEvidenceError("parent broker disclosure action is not allowlisted")
        if Path(values[11]) != child_scratch_path / "disclosure-evidence.json":
            raise OfflineEvidenceError("parent broker disclosure target is not fixed")
        snapshot_identity = _decode_expected_identity(values[14])
        context = _decode_expected_identity(values[15])
        denial_relative = _worker_relative_directory(
            Path(context.get("denied_read_path", "")).parent,
            worker_scratch,
            "parent broker disclosure denial probe",
        )
        common.update(
            {
                "kind": "disclosure",
                "action": action,
                "created_at": values[12],
                "snapshot_identity": snapshot_identity,
                "denial_probe_relative": denial_relative,
                "capture_mode": "bytes-stdout-stderr-merged",
            }
        )
        return operation_id, common

    if bootstrap == _UNITTEST_BOOTSTRAP:
        if (
            len(values) != 17
            or kwargs.get("stdout") != subprocess.PIPE
            or kwargs.get("stderr") != subprocess.STDOUT
            or kwargs.get("capture_output") is not None
            or kwargs.get("text") is not None
        ):
            raise OfflineEvidenceError("parent broker unittest invocation is malformed")
        component = values[10]
        operation_id = f"test-component-{component}"
        context = _decode_expected_identity(values[16])
        denial_relative = _worker_relative_directory(
            Path(context.get("denied_read_path", "")).parent,
            worker_scratch,
            "parent broker unittest denial probe",
        )
        common.update(
            {
                "kind": "test-component",
                "component": component,
                "start_directory": values[11],
                "test_scope": _decode_expected_identity(values[13]),
                "selection": _decode_expected_identity(values[14]),
                "baseline": _decode_expected_identity(values[15]),
                "denial_probe_relative": denial_relative,
                "capture_mode": "bytes-stdout-stderr-merged",
            }
        )
        return operation_id, common

    if probe_id != "public-ops-process-isolation" or len(values) != 12:
        raise OfflineEvidenceError("parent broker bootstrap is not allowlisted")
    if (
        kwargs.get("capture_output") is not True
        or kwargs.get("text") is not None
        or kwargs.get("stdout") is not None
        or kwargs.get("stderr") is not None
        or Path(values[10]).resolve(strict=True) != snapshot_path
    ):
        raise OfflineEvidenceError("parent broker process-isolation invocation is malformed")
    role = environment.get("KG_PROCESS_ROLE")
    if role not in {"public-app-agent", "ops-admin-agent"}:
        raise OfflineEvidenceError("parent broker process-isolation role is not allowlisted")
    common.update(
        {
            "kind": "process-isolation",
            "role": role,
            "marker": environment.get("KG_PROCESS_MARKER"),
            "public_allowed_hosts": environment.get("KG_PUBLIC_ALLOWED_HOSTS"),
            "bootstrap_sha256": hashlib.sha256(bootstrap.encode("utf-8")).hexdigest(),
            "script_sha256": hashlib.sha256(values[9].encode("ascii")).hexdigest(),
            "library_bindings_sha256": hashlib.sha256(
                values[11].encode("ascii")
            ).hexdigest(),
            "capture_mode": "bytes-separate-stdout-stderr",
        }
    )
    return f"process-isolation-{role}", common


class _ParentBrokerClient:
    def __init__(
        self,
        *,
        request_fd: int,
        response_fd: int,
        session: str,
        probe_id: str,
        worker_scratch: Path,
        deadline_monotonic_ns: int,
    ) -> None:
        if (
            not isinstance(session, str)
            or not _SHA256.fullmatch(session)
            or type(deadline_monotonic_ns) is not int
            or deadline_monotonic_ns <= time.monotonic_ns()
        ):
            raise OfflineEvidenceError("parent broker session is malformed")
        self.request_fd = request_fd
        self.response_fd = response_fd
        self.session = session
        self.probe_id = probe_id
        self.worker_scratch = worker_scratch.resolve(strict=True)
        self.plan = _parent_broker_plan(probe_id)
        self.request_sequence = 0
        self.sequence = 0
        self.operation_ids: list[str] = []
        self.exchange_hashes: list[dict[str, str]] = []
        self.exchange_lock = threading.Lock()
        self.request_lock = threading.Lock()
        self.response_condition = threading.Condition(threading.RLock())
        self.chain_sha256 = hashlib.sha256(session.encode("ascii")).hexdigest()
        self.deadline_monotonic_ns = deadline_monotonic_ns
        self.failure: str | None = None
        self.closed = False

    def run(self, command: object, *args: object, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if args:
            raise OfflineEvidenceError("parent broker client invocation is invalid")
        if _is_ocr_native_probe(self.probe_id):
            operation_id, parameters = _parent_broker_invocation(
                command,
                kwargs,
                probe_id=self.probe_id,
                worker_scratch=self.worker_scratch,
            )
            if operation_id == "ocr-native-tesseract":
                return self._run_ocr_concurrent(
                    command,
                    operation_id=operation_id,
                    parameters=parameters,
                )
        with self.exchange_lock:
            return self._run_locked(command, *args, **kwargs)

    def _deadline(self) -> float:
        if self.deadline_monotonic_ns <= time.monotonic_ns():
            raise OfflineEvidenceError("parent broker protocol timed out")
        return self.deadline_monotonic_ns / 1_000_000_000

    def _build_request(
        self,
        *,
        sequence: int,
        operation_id: str,
        parameters: Mapping[str, Any],
    ) -> tuple[bytes, str]:
        if sequence >= len(self.plan) or operation_id != self.plan[sequence]:
            raise OfflineEvidenceError("parent broker operation sequence is not allowlisted")
        request: dict[str, Any] = {
            "schema_version": PARENT_BROKER_PROTOCOL_SCHEMA_VERSION,
            "session": self.session,
            "sequence": sequence,
            "probe_id": self.probe_id,
            "operation_id": operation_id,
            "parameters": parameters,
            "parameters_sha256": _identity_sha256(parameters),
        }
        payload = canonical_json_bytes(request)
        return payload, hashlib.sha256(payload).hexdigest()

    def _consume_response(
        self,
        *,
        command: object,
        sequence: int,
        operation_id: str,
        parameters: Mapping[str, Any],
        request_sha256: str,
        response_payload: bytes | None,
    ) -> tuple[subprocess.CompletedProcess[Any], str]:
        if response_payload is None:
            raise OfflineEvidenceError("parent broker response is missing")
        try:
            response = json.loads(response_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineEvidenceError("parent broker response is malformed") from exc
        expected_fields = {
            "schema_version",
            "session",
            "sequence",
            "probe_id",
            "operation_id",
            "process_identity",
            "request_sha256",
            "status",
            "returncode",
            "stdout_base64",
            "stderr_base64",
            "text_mode",
            "timed_out",
            "process_timing",
            "execution_slot",
        }
        ocr_response = _is_ocr_native_probe(self.probe_id)
        if (
            not isinstance(response, Mapping)
            or set(response) != expected_fields
            or response_payload != canonical_json_bytes(response)
            or response["schema_version"] != PARENT_BROKER_PROTOCOL_SCHEMA_VERSION
            or response["session"] != self.session
            or type(response["sequence"]) is not int
            or response["sequence"] != sequence
            or response["probe_id"] != self.probe_id
            or response["operation_id"] != operation_id
            or not _type_sensitive_equal(
                response["process_identity"],
                _validated_process_identity(
                    response["process_identity"],
                    "parent broker child",
                    require_session_leader=True,
                ),
            )
            or response["request_sha256"] != request_sha256
            or response["status"] != "completed"
            or type(response["returncode"]) is not int
            or not isinstance(response["text_mode"], bool)
            or not isinstance(response["timed_out"], bool)
            or (
                ocr_response
                and not _type_sensitive_equal(
                    response["execution_slot"],
                    _ocr_native_execution_slot(sequence),
                )
            )
            or (
                not ocr_response
                and (
                    response["process_timing"] is not None
                    or response["execution_slot"] is not None
                )
            )
        ):
            raise OfflineEvidenceError("parent broker response identity mismatch")
        if ocr_response:
            _validated_ocr_process_timing(
                response["process_timing"],
                shared_deadline_monotonic_ns=self.deadline_monotonic_ns,
                timeout_seconds=parameters["timeout_seconds"],
            )
        try:
            stdout = base64.b64decode(response["stdout_base64"], validate=True)
            stderr = (
                None
                if response["stderr_base64"] is None
                else base64.b64decode(response["stderr_base64"], validate=True)
            )
        except (TypeError, ValueError) as exc:
            raise OfflineEvidenceError("parent broker response output is malformed") from exc
        stdout, stderr = _validated_parent_broker_output(
            stdout,
            stderr,
            field="parent broker response",
        )
        if response["timed_out"] is True:
            raise subprocess.TimeoutExpired(command, parameters["timeout_seconds"])
        if response["text_mode"] is True:
            try:
                stdout_value: Any = stdout.decode("utf-8")
                stderr_value: Any = None if stderr is None else stderr.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise OfflineEvidenceError(
                    "parent broker text response is not UTF-8"
                ) from exc
        else:
            stdout_value = stdout
            stderr_value = stderr
        completed = subprocess.CompletedProcess(
            command,
            response["returncode"],
            stdout_value,
            stderr_value,
        )
        completed.process_identity = dict(response["process_identity"])
        completed.process_timing = response["process_timing"]
        completed.execution_slot = response["execution_slot"]
        return completed, hashlib.sha256(response_payload).hexdigest()

    def _commit_exchange(
        self,
        *,
        sequence: int,
        operation_id: str,
        request_sha256: str,
        response_sha256: str,
    ) -> None:
        if sequence != self.sequence:
            raise OfflineEvidenceError("parent broker response sequence is not deterministic")
        self.chain_sha256 = _identity_sha256(
            [self.chain_sha256, request_sha256, response_sha256]
        )
        self.operation_ids.append(operation_id)
        self.exchange_hashes.append(
            {
                "request_sha256": request_sha256,
                "response_sha256": response_sha256,
            }
        )
        self.sequence += 1

    def _record_concurrent_failure(self, error: BaseException) -> None:
        detail = str(error)
        if not detail or len(detail) > 512 or _has_control_character(detail):
            detail = type(error).__name__
        with self.response_condition:
            if self.failure is None:
                self.failure = detail
                self.closed = True
                for descriptor in (self.request_fd, self.response_fd):
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
            self.response_condition.notify_all()

    def _run_ocr_concurrent(
        self,
        command: object,
        *,
        operation_id: str,
        parameters: Mapping[str, Any],
    ) -> subprocess.CompletedProcess[Any]:
        remaining = (self.deadline_monotonic_ns - time.monotonic_ns()) / 1_000_000_000
        if remaining <= 0 or not self.request_lock.acquire(timeout=remaining):
            raise OfflineEvidenceError("parent broker protocol timed out")
        try:
            if self.closed or self.failure is not None:
                raise OfflineEvidenceError(
                    self.failure or "parent broker client invocation is invalid"
                )
            sequence = self.request_sequence
            request_payload, request_sha256 = self._build_request(
                sequence=sequence,
                operation_id=operation_id,
                parameters=parameters,
            )
            _write_broker_frame(
                self.request_fd,
                request_payload,
                deadline=self._deadline(),
            )
            self.request_sequence += 1
        except BaseException as exc:
            self._record_concurrent_failure(exc)
            raise
        finally:
            self.request_lock.release()

        try:
            with self.response_condition:
                while sequence != self.sequence and self.failure is None:
                    remaining = (
                        self.deadline_monotonic_ns - time.monotonic_ns()
                    ) / 1_000_000_000
                    if remaining <= 0:
                        raise OfflineEvidenceError("parent broker protocol timed out")
                    self.response_condition.wait(timeout=remaining)
                if self.failure is not None:
                    raise OfflineEvidenceError(self.failure)
                response_payload = _read_broker_frame(
                    self.response_fd,
                    deadline=self._deadline(),
                )
                completed, response_sha256 = self._consume_response(
                    command=command,
                    sequence=sequence,
                    operation_id=operation_id,
                    parameters=parameters,
                    request_sha256=request_sha256,
                    response_payload=response_payload,
                )
                self._commit_exchange(
                    sequence=sequence,
                    operation_id=operation_id,
                    request_sha256=request_sha256,
                    response_sha256=response_sha256,
                )
                self.response_condition.notify_all()
                return completed
        except BaseException as exc:
            self._record_concurrent_failure(exc)
            raise

    def _run_locked(
        self,
        command: object,
        *args: object,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any]:
        if args or self.closed or self.failure is not None:
            raise OfflineEvidenceError("parent broker client invocation is invalid")
        operation_id, parameters = _parent_broker_invocation(
            command,
            kwargs,
            probe_id=self.probe_id,
            worker_scratch=self.worker_scratch,
        )
        sequence = self.request_sequence
        request_payload, request_sha256 = self._build_request(
            sequence=sequence,
            operation_id=operation_id,
            parameters=parameters,
        )
        _write_broker_frame(
            self.request_fd,
            request_payload,
            deadline=self._deadline(),
        )
        self.request_sequence += 1
        response_payload = _read_broker_frame(
            self.response_fd,
            deadline=self._deadline(),
        )
        completed, response_sha256 = self._consume_response(
            command=command,
            sequence=sequence,
            operation_id=operation_id,
            parameters=parameters,
            request_sha256=request_sha256,
            response_payload=response_payload,
        )
        with self.response_condition:
            self._commit_exchange(
                sequence=sequence,
                operation_id=operation_id,
                request_sha256=request_sha256,
                response_sha256=response_sha256,
            )
            self.response_condition.notify_all()
        return completed

    def transcript(self) -> dict[str, Any]:
        with self.exchange_lock:
            with self.response_condition:
                if (
                    tuple(self.operation_ids) != self.plan
                    or self.sequence != len(self.plan)
                    or self.request_sequence != len(self.plan)
                    or self.failure is not None
                ):
                    raise OfflineEvidenceError(
                        "parent broker client transcript is incomplete"
                    )
                return {
                    "schema_version": PARENT_BROKER_TRANSCRIPT_SCHEMA_VERSION,
                    "session": self.session,
                    "probe_id": self.probe_id,
                    "deadline_monotonic_ns": self.deadline_monotonic_ns,
                    "operation_count": self.sequence,
                    "operation_ids": list(self.operation_ids),
                    "operation_ids_sha256": _identity_sha256(self.operation_ids),
                    "exchange_hashes": list(self.exchange_hashes),
                    "exchange_chain_sha256": self.chain_sha256,
                }

    def close(self) -> None:
        with self.exchange_lock:
            with self.response_condition:
                if self.closed:
                    return
                self.closed = True
                for descriptor in (self.request_fd, self.response_fd):
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                self.response_condition.notify_all()


def _parent_broker_subprocess_run(
    command: object,
    *args: object,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    client = _PARENT_BROKER_CLIENT
    if not isinstance(client, _ParentBrokerClient):
        raise OfflineEvidenceError("parent broker client is not active")
    return client.run(command, *args, **kwargs)


def _run_production_embedding_parent_test(
    *,
    repository: Path,
    repository_fd: int,
    python_identity: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    fixture = _resolve_production_embedding_fixture(required=True)
    assert fixture is not None
    python = _python_executable()
    external_tools = _empty_external_tool_set()
    base_closure = _runtime_sandbox_closure(
        python=python,
        python_identity=python_identity,
        external_tools=external_tools,
    )
    snapshot: _PrivateSnapshot | None = None
    scratch: _ComponentScratch | None = None
    denial_probe: _ComponentScratch | None = None
    held_profile: _HeldFile | None = None
    try:
        snapshot = _build_private_snapshot(
            repository_fd,
            tree_roots=_TEST_SNAPSHOT_TREE_ROOTS,
            exact_files=_TEST_SNAPSHOT_FILES,
        )
        scratch = _create_component_scratch(_PRODUCTION_EMBEDDING_PROBE_ID)
        denial_probe = _create_denial_probe(_PRODUCTION_EMBEDDING_PROBE_ID)
        target_executable = scratch.path / _PRODUCTION_EMBEDDING_TARGET_RELATIVE
        closure = _production_embedding_probe_closure(
            base_closure,
            fixture,
            target_executable=target_executable,
        )
        profile = _child_sandbox_profile(snapshot.path, scratch.path, closure)
        held_profile = _stage_child_sandbox_profile(scratch, profile)
        child_sandbox = _child_sandbox_binding(
            profile=profile,
            snapshot=snapshot,
            scratch=scratch,
            denial_probe=denial_probe,
            closure=closure,
        )
        sandbox_context = _component_sandbox_context(
            child_sandbox,
            denial_probe,
        )
        component = _PRODUCTION_EMBEDDING_PROBE_ID
        selection = _component_test_selection(component)
        baseline = _component_test_baseline(component)
        encoded_closure = _encoded_module_closure_manifest(
            snapshot.root_fd,
            schema_version="cloud-v2-child-bootstrap-closure-v1",
            field="production embedding parent probe child module",
        )
        command = [
            str(NETWORK_SANDBOX_PATH),
            "-f",
            _held_sandbox_profile_argument(held_profile),
            str(python),
            "-I",
            "-S",
            "-B",
            "-c",
            _UNITTEST_BOOTSTRAP,
            encoded_closure,
            component,
            _PARENT_PROBE_TEST_COMPONENTS[component][0],
            _encode_expected_identity(python_identity),
            _encode_expected_identity(snapshot.identity),
            _encode_expected_identity(selection),
            _encode_expected_identity(baseline),
            _encode_expected_identity(sandbox_context),
        ]
        environment = _expected_parent_broker_environment(
            parameters={"kind": "test-component", "component": component},
            scratch_path=scratch.path,
            python=python,
            full_external_tools=external_tools,
            child_sandbox_binding=child_sandbox,
            production_embedding_fixture=fixture,
        )
        child_runner = _test_runner_identity(
            repository,
            repo_fd=repository_fd,
            test_scope=snapshot.identity,
            python_identity=python_identity,
            external_tool_identity=external_tools.identity,
            sandbox_closure_identity=base_closure.identity,
            production_embedding_fixture=fixture,
        )
        _revalidate_private_snapshot(snapshot)
        _revalidate_component_scratch(scratch)
        _revalidate_component_scratch(denial_probe)
        _revalidate_production_embedding_fixture(fixture)
        _revalidate_held_sandbox_profile(held_profile, profile)
        completed = _run_test_component_process(
            command,
            cwd=None,
            env=environment,
            stdin=subprocess.PIPE,
            input_payload=held_profile.payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=900.0,
            check=False,
            preexec_fn=partial(os.fchdir, snapshot.root_fd),
            pass_fds=(snapshot.root_fd,),
        )
        _revalidate_held_sandbox_profile(held_profile, profile)
        if (
            type(completed.returncode) is not int
            or completed.returncode != 0
            or not isinstance(completed.stdout, bytes)
        ):
            raise OfflineEvidenceError(
                "production embedding parent probe child failed"
            )
        log_payload, process_result = _parse_test_process_payload(
            completed.stdout,
            runner=child_runner,
        )
        if (
            process_result["successful"] is not True
            or process_result["test_count"] != 1
            or process_result["failure_count"] != 0
            or process_result["error_count"] != 0
            or process_result["skipped_count"] != 0
            or process_result["test_id_manifest"]["test_ids"]
            != [_PRODUCTION_EMBEDDING_TEST_ID]
            or process_result["sandbox_enforcement"][
                "sandbox_binding_sha256"
            ]
            != child_sandbox["identity_sha256"]
        ):
            raise OfflineEvidenceError(
                "production embedding parent probe result is not passing"
            )
        _revalidate_private_snapshot(snapshot)
        _revalidate_component_scratch(scratch)
        _revalidate_component_scratch(denial_probe)
        _revalidate_production_embedding_fixture(fixture)
        return log_payload, process_result
    finally:
        primary_error = sys.exception()
        cleanup_error: Exception | None = None
        for value, closer in (
            (held_profile, _close_held_file),
            (denial_probe, _close_component_scratch),
            (scratch, _close_component_scratch),
            (snapshot, _close_private_snapshot),
        ):
            if value is None:
                continue
            try:
                closer(value)
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        _finish_process_cleanup(cleanup_error, primary_error=primary_error)


def _run_formal_parent_probe_worker(
    *,
    probe_id: str,
    expected_snapshot_identity: str,
    expected_python_identity: str,
) -> dict[str, Any]:
    client = _PARENT_BROKER_CLIENT
    if (
        os.environ.get(_INHERITED_COMPONENT_SANDBOX_ENV) is None
        or _ACTIVE_COMPONENT_SANDBOX_CONTEXT is None
        or not isinstance(client, _ParentBrokerClient)
    ):
        raise OfflineEvidenceError(
            "formal parent probe worker requires a bound sandbox and broker"
        )
    initial_sandbox_enforcement = _require_active_component_sandbox_context()
    worker_process_identity = _current_process_identity(require_session_leader=True)
    spec = _formal_parent_probe_spec(probe_id)
    snapshot_identity = _decode_expected_identity(expected_snapshot_identity)
    python_identity = _decode_expected_identity(expected_python_identity)
    repository = _module_repository_root()
    _root, repository_fd = _open_directory_fd(
        repository,
        "formal parent probe snapshot",
    )
    try:
        actual_snapshot_identity = _activate_formal_materialized_snapshot(
            repository,
            snapshot_identity,
            field="formal parent probe snapshot",
        )
        if _python_identity(_python_executable()) != python_identity:
            raise OfflineEvidenceError("formal parent probe Python identity mismatch")
        source_payload, source_binding = _stable_relative_file_binding(
            repository_fd,
            spec["source_path"],
            "formal parent probe source",
            max_bytes=4 * 1024 * 1024,
        )
        module_name, class_name, method_name = spec["covered_test_id"].split(".")
        if PurePosixPath(spec["source_path"]).stem != module_name:
            raise OfflineEvidenceError("formal parent probe source mapping mismatch")
        try:
            compiled = compile(
                source_payload,
                str(repository / spec["source_path"]),
                "exec",
                dont_inherit=True,
            )
        except (SyntaxError, ValueError, TypeError) as exc:
            raise OfflineEvidenceError(
                "formal parent probe source could not be compiled"
            ) from exc
        selected_ids = [spec["covered_test_id"]]
        if probe_id == _PRODUCTION_EMBEDDING_PROBE_ID:
            log_payload, child_result = _run_production_embedding_parent_test(
                repository=repository,
                repository_fd=repository_fd,
                python_identity=python_identity,
            )
            successful = child_result["successful"]
            test_count = child_result["test_count"]
            failure_count = child_result["failure_count"]
            error_count = child_result["error_count"]
            skipped_count = child_result["skipped_count"]
        else:
            module = types.ModuleType(module_name)
            module.__file__ = str(repository / spec["source_path"])
            module.__package__ = ""
            module.__spec__ = None
            sys.modules[module_name] = module
            original_subprocess_run = subprocess.run
            subprocess.run = _parent_broker_subprocess_run
            try:
                exec(compiled, module.__dict__)
                if (
                    probe_id == "public-ops-process-isolation"
                    and module.__dict__.get("SANDBOX_EXEC")
                    != str(NETWORK_SANDBOX_PATH)
                ):
                    raise OfflineEvidenceError(
                        "formal process-isolation probe could not discover sandbox-exec"
                    )
                suite = unittest.defaultTestLoader.loadTestsFromName(
                    f"{class_name}.{method_name}",
                    module,
                )
                selected_tests: list[unittest.TestCase] = []

                def flatten(value: unittest.TestSuite) -> None:
                    for item in value:
                        if isinstance(item, unittest.TestSuite):
                            flatten(item)
                        else:
                            selected_tests.append(item)

                flatten(suite)
                selected_ids = [test.id() for test in selected_tests]
                if selected_ids != [spec["covered_test_id"]]:
                    raise OfflineEvidenceError(
                        "formal parent probe selected test identity mismatch"
                    )
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(
                    captured
                ):
                    result = unittest.TextTestRunner(
                        stream=captured,
                        verbosity=2,
                    ).run(suite)
                log_payload = captured.getvalue().encode("utf-8")
                successful = result.wasSuccessful()
                test_count = result.testsRun
                failure_count = len(result.failures)
                error_count = len(result.errors)
                skipped_count = len(result.skipped)
                if not successful:
                    traces = [
                        trace
                        for _test, trace in (*result.failures, *result.errors)
                        if isinstance(trace, str)
                    ]
                    lines = [
                        line.strip()
                        for line in (traces[0].splitlines()[-4:] if traces else ())
                        if line.strip()
                    ]
                    detail = " | ".join(lines)
                    if (
                        not detail
                        or len(detail) > 768
                        or _has_control_character(detail)
                    ):
                        detail = "no safe detail"
                    raise OfflineEvidenceError(
                        f"formal parent probe unittest failed: {detail}"
                    )
            finally:
                subprocess.run = original_subprocess_run
                sys.modules.pop(module_name, None)
        post_snapshot_identity = _test_scope_identity(
            repository,
            repo_fd=repository_fd,
            materialized=True,
            tree_roots=tuple(snapshot_identity.get("tree_roots", ())),
            exact_files=tuple(snapshot_identity.get("exact_files", ())),
        )
        post_python_identity = _python_identity(_python_executable())
        if post_snapshot_identity != snapshot_identity:
            raise OfflineEvidenceError(
                "formal parent probe snapshot changed during execution"
            )
        if post_python_identity != python_identity:
            raise OfflineEvidenceError(
                "formal parent probe Python identity changed during execution"
            )
        final_sandbox_enforcement = _require_active_component_sandbox_context()
        if final_sandbox_enforcement != initial_sandbox_enforcement:
            raise OfflineEvidenceError(
                "formal parent probe worker sandbox enforcement changed"
            )
        module_origin_ledger = _loaded_module_origin_ledger(repository)
        broker_client_transcript = client.transcript()
        return {
            "schema_version": PARENT_PROBE_RESULT_SCHEMA_VERSION,
            "probe_id": probe_id,
            "covered_test_id": spec["covered_test_id"],
            "source_path": spec["source_path"],
            "source_sha256": source_binding["sha256"],
            "runner_source_sha256": _EXECUTED_RUNNER_SOURCE_SHA256,
            "python_identity": post_python_identity,
            "test_scope": post_snapshot_identity,
            "worker_process_identity": worker_process_identity,
            "module_origin_ledger": _validated_module_origin_ledger(
                module_origin_ledger
            ),
            "test_id_count": 1,
            "test_ids_sha256": _identity_sha256(selected_ids),
            "successful": successful,
            "test_count": test_count,
            "failure_count": failure_count,
            "error_count": error_count,
            "skipped_count": skipped_count,
            "worker_sandbox_enforcement": {
                "initial": initial_sandbox_enforcement,
                "final": final_sandbox_enforcement,
            },
            "broker_client_transcript": broker_client_transcript,
            "unittest_log_base64": base64.b64encode(log_payload).decode("ascii"),
        }
    finally:
        os.close(repository_fd)


def _validated_parent_broker_client_transcript(
    value: object,
    *,
    probe_id: str,
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "session",
        "probe_id",
        "deadline_monotonic_ns",
        "operation_count",
        "operation_ids",
        "operation_ids_sha256",
        "exchange_hashes",
        "exchange_chain_sha256",
    }
    plan = _parent_broker_plan(probe_id)
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value["schema_version"] != PARENT_BROKER_TRANSCRIPT_SCHEMA_VERSION
        or not isinstance(value["session"], str)
        or not _SHA256.fullmatch(value["session"])
        or value["probe_id"] != probe_id
        or type(value["deadline_monotonic_ns"]) is not int
        or value["deadline_monotonic_ns"] <= 0
        or type(value["operation_count"]) is not int
        or value["operation_count"] != len(plan)
        or value["operation_ids"] != list(plan)
        or value["operation_ids_sha256"] != _identity_sha256(plan)
        or not isinstance(value["exchange_hashes"], list)
        or len(value["exchange_hashes"]) != len(plan)
    ):
        raise OfflineEvidenceError("formal parent broker client transcript is malformed")
    chain = hashlib.sha256(value["session"].encode("ascii")).hexdigest()
    for exchange in value["exchange_hashes"]:
        if (
            not isinstance(exchange, Mapping)
            or set(exchange) != {"request_sha256", "response_sha256"}
            or any(
                not isinstance(exchange[field], str)
                or not _SHA256.fullmatch(exchange[field])
                for field in ("request_sha256", "response_sha256")
            )
        ):
            raise OfflineEvidenceError(
                "formal parent broker client transcript is malformed"
            )
        chain = _identity_sha256(
            [chain, exchange["request_sha256"], exchange["response_sha256"]]
        )
    if value["exchange_chain_sha256"] != chain:
        raise OfflineEvidenceError("formal parent broker client transcript is malformed")
    return dict(value)


def _parse_parent_probe_process_payload(
    payload: bytes,
    *,
    runner: Mapping[str, Any],
    spec: Mapping[str, str],
    expected_source_sha256: str,
    repo_fd: int | None = None,
) -> tuple[bytes, dict[str, Any]]:
    if len(payload) > _PARENT_PROBE_OUTPUT_MAX_BYTES:
        raise OfflineEvidenceError("formal parent probe result exceeds the size limit")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfflineEvidenceError(
            "formal parent probe result is not canonical JSON"
        ) from exc
    fields = {
        "schema_version",
        "probe_id",
        "covered_test_id",
        "source_path",
        "source_sha256",
        "runner_source_sha256",
        "python_identity",
        "test_scope",
        "worker_process_identity",
        "module_origin_ledger",
        "test_id_count",
        "test_ids_sha256",
        "successful",
        "test_count",
        "failure_count",
        "error_count",
        "skipped_count",
        "worker_sandbox_enforcement",
        "broker_client_transcript",
        "unittest_log_base64",
    }
    if not isinstance(value, Mapping):
        raise OfflineEvidenceError("formal parent probe result is malformed")
    try:
        module_origin_ledger = _validated_module_origin_ledger(
            value.get("module_origin_ledger"),
            repo_fd=repo_fd,
            test_scope=(runner.get("test_scope") if repo_fd is not None else None),
        )
        worker_process_identity = _validated_process_identity(
            value.get("worker_process_identity"),
            "formal parent worker",
            require_session_leader=True,
        )
    except OfflineEvidenceError as exc:
        raise OfflineEvidenceError("formal parent probe result is malformed") from exc
    expected_test_ids = [spec["covered_test_id"]]
    worker_enforcement = value.get("worker_sandbox_enforcement")
    if (
        not isinstance(worker_enforcement, Mapping)
        or set(worker_enforcement) != {"initial", "final"}
    ):
        raise OfflineEvidenceError("formal parent probe result is malformed")
    try:
        initial_enforcement = _validated_sandbox_enforcement(
            worker_enforcement["initial"]
        )
        final_enforcement = _validated_sandbox_enforcement(worker_enforcement["final"])
        broker_client_transcript = _validated_parent_broker_client_transcript(
            value.get("broker_client_transcript"),
            probe_id=spec["probe_id"],
        )
    except OfflineEvidenceError as exc:
        raise OfflineEvidenceError("formal parent probe result is malformed") from exc
    if (
        set(value) != fields
        or payload != canonical_json_bytes(value)
        or value["schema_version"] != PARENT_PROBE_RESULT_SCHEMA_VERSION
        or value["probe_id"] != spec["probe_id"]
        or value["covered_test_id"] != spec["covered_test_id"]
        or value["source_path"] != spec["source_path"]
        or value["source_sha256"] != expected_source_sha256
        or value["runner_source_sha256"] != runner.get("source_sha256")
        or not _type_sensitive_equal(
            value["python_identity"], runner.get("python_identity")
        )
        or not _type_sensitive_equal(value["test_scope"], runner.get("test_scope"))
        or not _type_sensitive_equal(
            value["worker_process_identity"], worker_process_identity
        )
        or not _type_sensitive_equal(value["module_origin_ledger"], module_origin_ledger)
        or type(value["test_id_count"]) is not int
        or value["test_id_count"] != 1
        or value["test_ids_sha256"] != _identity_sha256(expected_test_ids)
        or not isinstance(value["successful"], bool)
        or not _type_sensitive_equal(initial_enforcement, final_enforcement)
        or not _type_sensitive_equal(
            value["worker_sandbox_enforcement"],
            {"initial": initial_enforcement, "final": final_enforcement},
        )
        or not _type_sensitive_equal(
            value["broker_client_transcript"], broker_client_transcript
        )
    ):
        raise OfflineEvidenceError("formal parent probe result identity mismatch")
    for field in ("test_count", "failure_count", "error_count", "skipped_count"):
        if type(value[field]) is not int or value[field] < 0:
            raise OfflineEvidenceError("formal parent probe result count is invalid")
    encoded_log = value["unittest_log_base64"]
    if not isinstance(encoded_log, str):
        raise OfflineEvidenceError("formal parent probe log encoding is invalid")
    try:
        log_payload = base64.b64decode(encoded_log, validate=True)
    except (ValueError, TypeError) as exc:
        raise OfflineEvidenceError("formal parent probe log encoding is invalid") from exc
    if len(log_payload) > 16 * 1024 * 1024:
        raise OfflineEvidenceError("formal parent probe log exceeds the size limit")
    return log_payload, dict(value)


def _parent_probe_machine_result(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or "unittest_log_base64" not in value:
        raise OfflineEvidenceError("formal parent probe machine result is malformed")
    return {
        key: value[key]
        for key in sorted(set(value) - {"unittest_log_base64"})
    }


def _reconstructed_parent_probe_payload(
    machine_result: object,
    log_payload: bytes,
    *,
    runner: Mapping[str, Any],
    spec: Mapping[str, str],
    expected_source_sha256: str,
    repo_fd: int | None = None,
) -> tuple[bytes, dict[str, Any]]:
    if not isinstance(machine_result, Mapping):
        raise OfflineEvidenceError("formal parent probe machine result is malformed")
    payload = canonical_json_bytes(
        {
            **dict(machine_result),
            "unittest_log_base64": base64.b64encode(log_payload).decode("ascii"),
        }
    )
    parsed_log, parsed = _parse_parent_probe_process_payload(
        payload,
        runner=runner,
        spec=spec,
        expected_source_sha256=expected_source_sha256,
        repo_fd=repo_fd,
    )
    if parsed_log != log_payload:
        raise OfflineEvidenceError("formal parent probe machine result log mismatch")
    return payload, parsed


def _open_parent_worker_directory(
    worker_scratch: _ComponentScratch,
    relative: object,
    field: str,
) -> tuple[Path, int]:
    canonical = _canonical_relative(relative, field)
    descriptor = _open_relative_directory_fd(worker_scratch.root_fd, canonical, field)
    path = worker_scratch.path / canonical
    try:
        _revalidate_directory_path(path, descriptor, field)
    except Exception:
        os.close(descriptor)
        raise
    return path.resolve(strict=True), descriptor


def _process_isolation_constants(parent_snapshot_fd: int) -> dict[str, str]:
    payload = _stable_relative_file_bytes(
        parent_snapshot_fd,
        "deploy/cloud_v2/tests/test_process_isolation.py",
        "process-isolation formal probe source",
        max_bytes=1024 * 1024,
    )
    try:
        tree = ast.parse(payload, filename="test_process_isolation.py")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise OfflineEvidenceError(
            "process-isolation formal probe source is invalid"
        ) from exc
    expected = {"PROCESS_CHILD_BOOTSTRAP", "PUBLIC_CHILD", "OPS_CHILD"}
    values: dict[str, str] = {}
    for node in tree.body:
        if (
            not isinstance(node, ast.Assign)
            or len(node.targets) != 1
            or not isinstance(node.targets[0], ast.Name)
            or node.targets[0].id not in expected
        ):
            continue
        name = node.targets[0].id
        if name in values or not isinstance(node.value, ast.Constant) or not isinstance(
            node.value.value, str
        ):
            raise OfflineEvidenceError(
                "process-isolation formal probe constants are malformed"
            )
        values[name] = node.value.value
    if set(values) != expected:
        raise OfflineEvidenceError(
            "process-isolation formal probe constants are incomplete"
        )
    return values


def _process_isolation_library_bindings() -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for key in ("purelib", "platlib"):
        configured = sysconfig.get_path(key)
        if not configured:
            raise OfflineEvidenceError("process-isolation library path is unavailable")
        path = Path(configured)
        if not path.is_absolute() or path.is_symlink():
            raise OfflineEvidenceError("process-isolation library path is unsafe")
        resolved = path.resolve(strict=True)
        if any(record["path"] == str(resolved) for record in bindings):
            continue
        bindings.append(
            {
                "path": str(resolved),
                "identity": _directory_identity(
                    resolved, f"process-isolation {key} library"
                ),
            }
        )
    return bindings


def _validated_ocr_fixed_fixture_anchors() -> dict[str, Any]:
    value = _OCR_FIXED_FIXTURE_ANCHORS
    if not isinstance(value, Mapping) or set(value) != {
        "pdf",
        "executables",
        "rendered_pages",
        "stdout",
    }:
        raise OfflineEvidenceError("parent broker OCR fixed fixture anchors are malformed")
    pdf = value["pdf"]
    executables = value["executables"]
    rendered_pages = value["rendered_pages"]
    stdout = value["stdout"]
    if (
        not isinstance(pdf, Mapping)
        or set(pdf) != {"size", "sha256"}
        or type(pdf["size"]) is not int
        or pdf["size"] <= 0
        or not isinstance(pdf["sha256"], str)
        or not _SHA256.fullmatch(pdf["sha256"])
        or not isinstance(executables, Mapping)
        or set(executables) != {"pdftoppm", "tesseract"}
        or any(
            not isinstance(executables[tool], str)
            or not _SHA256.fullmatch(executables[tool])
            for tool in ("pdftoppm", "tesseract")
        )
    ):
        raise OfflineEvidenceError("parent broker OCR fixed fixture anchors are malformed")

    validated_records: dict[str, list[dict[str, Any]]] = {}
    for field, records in (("rendered_pages", rendered_pages), ("stdout", stdout)):
        if not isinstance(records, list) or len(records) != 10:
            raise OfflineEvidenceError(
                "parent broker OCR fixed fixture anchors are malformed"
            )
        validated: list[dict[str, Any]] = []
        for page_number, record in enumerate(records, 1):
            if (
                not isinstance(record, Mapping)
                or set(record) != {"page_number", "size", "sha256"}
                or type(record["page_number"]) is not int
                or record["page_number"] != page_number
                or type(record["size"]) is not int
                or record["size"] <= 0
                or not isinstance(record["sha256"], str)
                or not _SHA256.fullmatch(record["sha256"])
            ):
                raise OfflineEvidenceError(
                    "parent broker OCR fixed fixture anchors are malformed"
                )
            validated.append(dict(record))
        validated_records[field] = validated
    return {
        "pdf": dict(pdf),
        "executables": dict(executables),
        **validated_records,
    }


def _validated_ocr_native_parameters(
    value: object,
    *,
    probe_id: str,
    operation_id: str,
) -> dict[str, Any]:
    if (
        not _is_ocr_native_probe(probe_id)
        or not isinstance(value, Mapping)
        or set(value) != _OCR_NATIVE_PARAMETER_FIELDS
        or value.get("kind") != "ocr-native"
        or value.get("tool") not in {"pdftoppm", "tesseract"}
        or (
            not _is_ocr_tessdata_probe(probe_id)
            and value.get("tool") != "pdftoppm"
        )
    ):
        raise OfflineEvidenceError("parent broker OCR parameters are malformed")
    tool = value["tool"]
    if operation_id != f"ocr-native-{tool}":
        raise OfflineEvidenceError("parent broker OCR operation is not fixed")
    relative_fields = (
        "containment_relative",
        "native_runtime_relative",
        "private_executable_relative",
        "private_library_relative",
        "scratch_relative",
    )
    paths = {
        field: PurePosixPath(
            _canonical_relative(value[field], f"parent broker OCR {field}")
        )
        for field in relative_fields
    }
    containment = paths["containment_relative"]
    native_runtime = paths["native_runtime_relative"]
    executable = paths["private_executable_relative"]
    library = paths["private_library_relative"]
    scratch = paths["scratch_relative"]
    profile_payload = _decoded_canonical_base64(
        value["profile_base64"],
        field="parent broker OCR profile",
        max_bytes=2 * 1024 * 1024,
    )
    try:
        profile_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OfflineEvidenceError("parent broker OCR profile is not UTF-8") from exc
    environment = value["environment"]
    if (
        not isinstance(environment, Mapping)
        or any(
            not isinstance(name, str)
            or not isinstance(item, str)
            or _has_control_character(name)
            or _has_control_character(item)
            for name, item in environment.items()
        )
        or value["environment_sha256"] != _identity_sha256(environment)
        or type(value["profile_size"]) is not int
        or value["profile_size"] != len(profile_payload)
        or type(value["input_size"]) is not int
        or value["profile_sha256"] != hashlib.sha256(profile_payload).hexdigest()
        or type(value["timeout_seconds"]) is not float
        or value["capture_mode"] != "bytes-separate-stdout-stderr"
    ):
        raise OfflineEvidenceError("parent broker OCR parameters are malformed")
    expected_environment_names = {
        "PATH",
        "DYLD_LIBRARY_PATH",
        "TMPDIR",
        "TMP",
        "TEMP",
        "HOME",
        *(
            ("FONTCONFIG_FILE",)
            if tool == "pdftoppm"
            else ("TESSDATA_PREFIX", "OMP_THREAD_LIMIT")
        ),
    }
    if (
        set(environment) != expected_environment_names
        or environment["PATH"] != _OCR_NATIVE_TOOL_SEARCH_PATH
    ):
        raise OfflineEvidenceError("parent broker OCR environment is not fixed")

    if tool == "pdftoppm":
        fontconfig = PurePosixPath(
            _canonical_relative(
                value["private_fontconfig_relative"],
                "parent broker OCR private fontconfig",
            )
        )
        if _is_ocr_tessdata_probe(probe_id):
            output_prefix = PurePosixPath(
                _canonical_relative(
                    value["output_prefix_relative"],
                    "parent broker OCR output prefix",
                )
            )
            input_payload = _decoded_canonical_base64(
                value["input_base64"],
                field="parent broker OCR PDF input",
                max_bytes=_OCR_NATIVE_INPUT_MAX_BYTES,
            )
            fixed_pdf = _validated_ocr_fixed_fixture_anchors()["pdf"]
            input_digest = hashlib.sha256(input_payload).hexdigest()
            if (
                not input_payload
                or native_runtime != containment / "poppler-runtime"
                or executable != containment / "poppler-runtime/bin/pdftoppm"
                or library != containment / "poppler-runtime/lib"
                or scratch != containment / "poppler-scratch"
                or fontconfig
                != containment / "poppler-runtime/fontconfig/fonts.conf"
                or output_prefix != containment / "rendered-pages/page"
                or value["approved_page_relative"] is not None
                or value["private_tessdata_relative"] is not None
                or value["page_number"] is not None
                or value["stdin_role"] != "pdf-bytes-pipe"
                or value["input_delivery"] != "inline-base64"
                or value["input_snapshot_relative"] is not None
                or value["input_size"] != len(input_payload)
                or value["input_sha256"] != input_digest
                or len(input_payload) != fixed_pdf["size"]
                or input_digest != fixed_pdf["sha256"]
                or value["timeout_seconds"] != 900.0
            ):
                raise OfflineEvidenceError(
                    "parent broker pdftoppm parameters are not fixed"
                )
        else:
            input_snapshot_relative = _canonical_relative(
                value["input_snapshot_relative"],
                "parent broker page 132 input snapshot path",
            )
            if (
                native_runtime != containment / "native-runtime"
                or executable != containment / "native-runtime/bin/pdftoppm"
                or library != containment / "native-runtime/lib"
                or scratch != containment / "scratch"
                or fontconfig
                != containment / "native-runtime/fontconfig/fonts.conf"
                or value["output_prefix_relative"] is not None
                or value["approved_page_relative"] is not None
                or value["private_tessdata_relative"] is not None
                or value["page_number"] != 132
                or value["stdin_role"] != "pdf-bytes-pipe"
                or value["input_delivery"]
                != "sealed-snapshot-held-descriptor"
                or value["input_base64"] is not None
                or input_snapshot_relative != _OCR_PAGE_132_SOURCE_RELATIVE
                or value["input_size"] != _OCR_PAGE_132_INPUT_ANCHOR["size"]
                or value["input_sha256"]
                != _OCR_PAGE_132_INPUT_ANCHOR["sha256"]
                or value["timeout_seconds"] != 300.0
            ):
                raise OfflineEvidenceError(
                    "parent broker page 132 pdftoppm parameters are not fixed"
                )
    else:
        page = PurePosixPath(
            _canonical_relative(
                value["approved_page_relative"],
                "parent broker OCR approved page",
            )
        )
        tessdata = PurePosixPath(
            _canonical_relative(
                value["private_tessdata_relative"],
                "parent broker OCR private tessdata",
            )
        )
        page_number = value["page_number"]
        if (
            not _is_ocr_tessdata_probe(probe_id)
            or type(page_number) is not int
            or page_number not in range(1, 11)
        ):
            raise OfflineEvidenceError("parent broker tesseract page is not fixed")
        if (
            native_runtime != containment / "ocr-runtime"
            or executable != containment / "ocr-runtime/native/bin/tesseract"
            or library != containment / "ocr-runtime/native/lib"
            or scratch != containment / f"tesseract-scratch/page-{page_number}"
            or page != containment / f"approved-pages/page-{page_number:02d}.jpg"
            or tessdata != containment / "ocr-runtime/tessdata"
            or value["output_prefix_relative"] is not None
            or value["private_fontconfig_relative"] is not None
            or value["stdin_role"] != "devnull"
            or value["input_delivery"] != "none"
            or value["input_base64"] is not None
            or value["input_snapshot_relative"] is not None
            or value["input_size"] != 0
            or value["input_sha256"] is not None
            or value["timeout_seconds"] != 120.0
            or environment["TESSDATA_PREFIX"].endswith("/")
            or environment["OMP_THREAD_LIMIT"] != "1"
        ):
            raise OfflineEvidenceError("parent broker tesseract parameters are not fixed")
    return dict(value)


def _validated_parent_broker_parameters(
    value: object,
    *,
    probe_id: str,
    operation_id: str,
) -> dict[str, Any]:
    if isinstance(value, Mapping) and value.get("kind") == "ocr-native":
        return _validated_ocr_native_parameters(
            value,
            probe_id=probe_id,
            operation_id=operation_id,
        )
    common = {
        "kind",
        "snapshot_relative",
        "scratch_relative",
        "supplied_profile_parent_relative",
        "supplied_profile_sha256",
        "supplied_profile_size",
        "stdin_role",
        "timeout_seconds",
        "capture_mode",
    }
    kind_fields = {
        "disclosure": {
            "action",
            "created_at",
            "snapshot_identity",
            "denial_probe_relative",
        },
        "test-component": {
            "component",
            "start_directory",
            "test_scope",
            "selection",
            "baseline",
            "denial_probe_relative",
        },
        "process-isolation": {
            "role",
            "marker",
            "public_allowed_hosts",
            "bootstrap_sha256",
            "script_sha256",
            "library_bindings_sha256",
        },
    }
    if not isinstance(value, Mapping) or value.get("kind") not in kind_fields:
        raise OfflineEvidenceError("parent broker operation parameters are malformed")
    kind = value["kind"]
    if set(value) != common | kind_fields[kind]:
        raise OfflineEvidenceError("parent broker operation parameters are malformed")
    for field in (
        "snapshot_relative",
        "scratch_relative",
        "supplied_profile_parent_relative",
    ):
        _canonical_relative(value[field], f"parent broker {field}")
    if (
        value["supplied_profile_parent_relative"] != value["scratch_relative"]
        or not isinstance(value["supplied_profile_sha256"], str)
        or type(value["supplied_profile_size"]) is not int
        or value["supplied_profile_size"] <= 0
        or value["supplied_profile_size"] > 2 * 1024 * 1024
        or value["stdin_role"] != "sandbox-profile-pipe"
        or not _SHA256.fullmatch(value["supplied_profile_sha256"])
        or type(value["timeout_seconds"]) is not float
        or not math.isfinite(value["timeout_seconds"])
        or value["timeout_seconds"] <= 0
        or value["timeout_seconds"] > 900
    ):
        raise OfflineEvidenceError("parent broker operation parameters are malformed")
    if kind in {"disclosure", "test-component"}:
        _canonical_relative(
            value["denial_probe_relative"],
            "parent broker denial probe",
        )
        if value["capture_mode"] != "bytes-stdout-stderr-merged":
            raise OfflineEvidenceError("parent broker capture mode is not allowlisted")
    else:
        if value["capture_mode"] != "bytes-separate-stdout-stderr":
            raise OfflineEvidenceError("parent broker capture mode is not allowlisted")
    if kind == "disclosure":
        snapshot_identity = _validated_persisted_snapshot_identity(
            value["snapshot_identity"]
        )
        if (
            snapshot_identity["tree_roots"] != []
            or snapshot_identity["exact_files"] != list(_DISCLOSURE_SNAPSHOT_FILES)
        ):
            raise OfflineEvidenceError("parent broker disclosure scope is not fixed")
        if (
            value["action"] not in {"build", "validate"}
            or operation_id != f"disclosure-{value['action']}"
            or value["timeout_seconds"] != _DISCLOSURE_SUBPROCESS_TIMEOUT_SECONDS
            or value["created_at"]
            != (
                "2026-09-02T00:00:00Z"
                if value["action"] == "build"
                else ""
            )
        ):
            raise OfflineEvidenceError("parent broker disclosure parameters are not fixed")
    elif kind == "test-component":
        component = value["component"]
        production_embedding_probe = (
            probe_id == _PRODUCTION_EMBEDDING_PROBE_ID
            and component == _PRODUCTION_EMBEDDING_PROBE_ID
        )
        expected_start_directory = (
            _PARENT_PROBE_TEST_COMPONENTS[component][0]
            if production_embedding_probe
            else _TEST_COMPONENTS.get(component, (None, None))[1]
        )
        if (
            expected_start_directory is None
            or operation_id != f"test-component-{component}"
            or value["start_directory"] != expected_start_directory
            or value["timeout_seconds"] != 900.0
        ):
            raise OfflineEvidenceError("parent broker unittest parameters are not fixed")
        if production_embedding_probe:
            expected_selection = _component_test_selection(component)
            expected_baseline = _component_test_baseline(component)
        else:
            expected_test_id = (
                "test_fixture.Passing.test_example"
                if probe_id == "runner-minimal-suite-sealing"
                else "test_fixture.DeliberateFailure.test_must_run"
            )
            expected_selection = {
                "schema_version": "cloud-v2-test-component-selection-v1",
                "included_test_ids": [],
                "excluded_test_ids": [],
                "excluded_modules": [],
            }
            expected_baseline = {
                "test_count": 1,
                "test_ids_sha256": _identity_sha256([expected_test_id]),
            }
        if not _type_sensitive_equal(
            value["selection"], expected_selection
        ) or not _type_sensitive_equal(value["baseline"], expected_baseline):
            raise OfflineEvidenceError("parent broker unittest policy is not fixed")
    else:
        role = value["role"]
        if (
            probe_id != "public-ops-process-isolation"
            or role not in {"public-app-agent", "ops-admin-agent"}
            or operation_id != f"process-isolation-{role}"
            or value["timeout_seconds"] != 60.0
            or value["marker"]
            != (
                "public-process-only"
                if role == "public-app-agent"
                else "ops-process-only"
            )
            or value["public_allowed_hosts"]
            != ("localhost" if role == "public-app-agent" else None)
            or any(
                not isinstance(value[field], str)
                or not _SHA256.fullmatch(value[field])
                for field in (
                    "bootstrap_sha256",
                    "script_sha256",
                    "library_bindings_sha256",
                )
            )
        ):
            raise OfflineEvidenceError(
                "parent broker process-isolation parameters are not fixed"
            )
    return dict(value)


def _parent_broker_normalized_command(
    parameters: Mapping[str, Any],
    *,
    operation_id: str,
) -> dict[str, Any]:
    kind = parameters.get("kind")
    if kind == "disclosure":
        bootstrap_sha256 = hashlib.sha256(
            _DISCLOSURE_SUBPROCESS_BOOTSTRAP.encode("utf-8")
        ).hexdigest()
        argument_count = 16
    elif kind == "test-component":
        bootstrap_sha256 = hashlib.sha256(_UNITTEST_BOOTSTRAP.encode("utf-8")).hexdigest()
        argument_count = 17
    elif kind == "process-isolation":
        bootstrap_sha256 = parameters.get("bootstrap_sha256")
        if not isinstance(bootstrap_sha256, str) or not _SHA256.fullmatch(
            bootstrap_sha256
        ):
            raise OfflineEvidenceError("parent broker command identity is malformed")
        argument_count = 12
    elif kind == "ocr-native":
        tool = parameters.get("tool")
        if tool not in {"pdftoppm", "tesseract"}:
            raise OfflineEvidenceError("parent broker OCR command identity is malformed")
        environment = parameters.get("environment")
        input_delivery = parameters.get("input_delivery")
        if (
            not isinstance(environment, Mapping)
            or input_delivery
            not in {"inline-base64", "sealed-snapshot-held-descriptor", "none"}
        ):
            raise OfflineEvidenceError("parent broker OCR command identity is malformed")
        tool_argument_count = (
            12
            if tool == "pdftoppm"
            and input_delivery == "sealed-snapshot-held-descriptor"
            else 8 if tool == "pdftoppm" else 7
        )
        return {
            "kind": kind,
            "operation_id": operation_id,
            "sandbox": "sandbox-exec-inline-profile",
            "tool": tool,
            "profile_sha256": parameters.get("profile_sha256"),
            "environment_sha256": parameters.get("environment_sha256"),
            "stdin_role": parameters.get("stdin_role"),
            "input_delivery": input_delivery,
            "input_snapshot_relative": parameters.get("input_snapshot_relative"),
            "page_number": parameters.get("page_number"),
            "argument_count": 5 + len(environment) + tool_argument_count,
        }
    else:
        raise OfflineEvidenceError("parent broker command kind is not allowlisted")
    return {
        "kind": kind,
        "operation_id": operation_id,
        "sandbox": "sandbox-exec-held-profile-stdin",
        "python_flags": ["-I", "-S", "-B", "-c"],
        "bootstrap_sha256": bootstrap_sha256,
        "argument_count": argument_count,
    }


def _parent_broker_network_source(kind: str) -> str:
    try:
        return {
            "disclosure": "bound-disclosure-bootstrap-active-probes-before-and-after",
            "test-component": "bound-unittest-bootstrap-active-probes-before-and-after",
            "process-isolation": "bound-process-isolation-child-active-probe",
        }[kind]
    except KeyError as exc:
        raise OfflineEvidenceError(
            "parent broker network evidence kind is not allowlisted"
        ) from exc


def _broker_child_network_evidence(
    *,
    kind: str,
    stdout: bytes,
    returncode: int,
) -> dict[str, Any]:
    if kind == "disclosure":
        if returncode != 0:
            raise OfflineEvidenceError(
                "parent broker disclosure child did not prove network denial"
            )
    elif kind == "test-component":
        try:
            value = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineEvidenceError(
                "parent broker unittest child network proof is malformed"
            ) from exc
        if (
            not isinstance(value, Mapping)
            or value.get("network_enforcement") != _network_enforcement_success()
            or not isinstance(value.get("sandbox_enforcement"), Mapping)
            or value["sandbox_enforcement"].get("network_enforcement")
            != _network_enforcement_success()
        ):
            raise OfflineEvidenceError(
                "parent broker unittest child did not prove network denial"
            )
    else:
        try:
            lines = [line for line in stdout.decode("utf-8").splitlines() if line]
            value = json.loads(lines[-1]) if len(lines) == 1 else None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineEvidenceError(
                "parent broker process-isolation network proof is malformed"
            ) from exc
        if returncode != 0 or not isinstance(value, Mapping) or value.get(
            "network_denied"
        ) is not True:
            raise OfflineEvidenceError(
                "parent broker process-isolation child did not prove network denial"
            )
    return {
        "schema_version": NETWORK_ENFORCEMENT_SCHEMA_VERSION,
        "status": "passed",
        "source": _parent_broker_network_source(kind),
        "required_result": _network_enforcement_success(),
    }


def _production_embedding_target_identity_after_child(
    path: Path | None,
    *,
    returncode: int,
    python_identity: Mapping[str, Any],
) -> dict[str, Any] | None:
    if path is None or returncode != 0:
        return None
    return _verify_production_embedding_target_executable(
        path,
        python_identity=python_identity,
    )


def _ocr_native_profile_literal(path: Path) -> str:
    value = str(path)
    if (
        not path.is_absolute()
        or value != os.path.normpath(value)
        or _has_control_character(value)
    ):
        raise OfflineEvidenceError("parent broker OCR profile path is not canonical")
    return json.dumps(value, ensure_ascii=False)


def _expected_ocr_native_profile(
    command_path: Path,
    *,
    writable_roots: tuple[Path, ...],
    read_only_roots: tuple[Path, ...],
    read_only_files: tuple[Path, ...],
) -> str:
    process_paths = {command_path, Path("/usr/bin/env")}
    read_roots = set(read_only_roots) | set(writable_roots)
    read_files = set(read_only_files) | process_paths | {Path("/dev/null")}
    read_ancestors = {
        ancestor
        for path in read_roots | read_files
        for ancestor in path.parents
    } - read_roots - read_files

    def literals(paths: Iterable[Path]) -> Iterable[str]:
        return (
            _ocr_native_profile_literal(path)
            for path in sorted(set(paths), key=str)
        )

    read_ancestor_rules = "".join(
        f"(allow file-read* (literal {literal}))"
        for literal in literals(read_ancestors)
    )
    read_root_rules = "".join(
        f"(allow file-read* (literal {literal}))(allow file-read* (subpath {literal}))"
        for literal in literals(read_roots)
    )
    read_file_rules = "".join(
        f"(allow file-read* (literal {literal}))"
        for literal in literals(read_files)
    )
    read_only_rules = "".join(
        f"(deny file-write* (literal {literal}))(deny file-write* (subpath {literal}))"
        for literal in literals(read_only_roots)
    )
    read_only_file_rules = "".join(
        f"(deny file-write* (literal {literal}))"
        for literal in literals(set(read_only_files) | process_paths)
    )
    writable_rules = "".join(
        f"(allow file-write* (literal {literal}))(allow file-write* (subpath {literal}))"
        for literal in literals(writable_roots)
    )
    process_exec_rules = "".join(
        f"(allow process-exec (literal {literal}))"
        for literal in literals(process_paths)
    )
    return (
        "(version 1)(allow default)(deny network*)"
        "(deny file-read*)"
        "(deny file-write*)"
        + read_ancestor_rules
        + read_root_rules
        + read_file_rules
        + read_only_rules
        + read_only_file_rules
        + '(allow file-write* (literal "/dev/null"))'
        + writable_rules
        + "(deny process-fork)(deny process-exec*)"
        + process_exec_rules
    )


def _ocr_private_tessdata_identity(
    path: Path,
    snapshot: _SealedTessdataSnapshot,
) -> dict[str, Any]:
    _revalidate_sealed_tessdata_snapshot(snapshot)
    root, root_fd = _open_directory_fd(
        path,
        "parent broker private OCR tessdata",
        enforce_safe_ancestors=False,
    )
    try:
        if root != path or tuple(sorted(os.listdir(root_fd))) != _OCR_TESSDATA_SNAPSHOT_NAMES:
            raise OfflineEvidenceError("parent broker private OCR tessdata scope changed")
        records: list[dict[str, Any]] = []
        for expected in snapshot.identity["files"]:
            payload, binding = _stable_relative_file_binding(
                root_fd,
                expected["name"],
                f"parent broker private OCR tessdata {expected['name']}",
                max_bytes=16 * 1024 * 1024,
            )
            record = {
                "name": expected["name"],
                "mode": stat.S_IMODE(binding["mode"]),
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            if record != expected:
                raise OfflineEvidenceError(
                    "parent broker private OCR tessdata differs from the sealed input"
                )
            records.append(record)
        core: dict[str, Any] = {
            "schema_version": "cloud-v2-parent-broker-private-tessdata-v1",
            "sealed_snapshot_identity_sha256": snapshot.identity["identity_sha256"],
            "path_sha256": hashlib.sha256(str(path).encode("utf-8")).hexdigest(),
            "root_identity": _directory_identity(
                path, "parent broker private OCR tessdata"
            ),
            "files": records,
            "file_set_sha256": _identity_sha256(records),
        }
        core["identity_sha256"] = _identity_sha256(core)
        return core
    finally:
        os.close(root_fd)


def _approved_poppler_fontconfig_materialization_contract() -> dict[str, Any]:
    files = [dict(item) for item in _OCR_POPPLER_FONTCONFIG_FILES]
    core: dict[str, Any] = {
        "schema_version": (
            "cloud-v2-parent-broker-poppler-fontconfig-materialization-v1"
        ),
        "directory": {"relative_path": "fontconfig", "mode": 0o500},
        "files": files,
        "file_set_sha256": _identity_sha256(files),
    }
    core["identity_sha256"] = _identity_sha256(core)
    return core


def _validated_poppler_fontconfig_materialization_contract(
    value: object,
) -> dict[str, Any]:
    expected = _approved_poppler_fontconfig_materialization_contract()
    if not isinstance(value, Mapping) or not _type_sensitive_equal(value, expected):
        raise OfflineEvidenceError(
            "parent broker OCR approved fontconfig contract is malformed"
        )
    return expected


def _observed_poppler_fontconfig_materialization_contract(
    path: Path,
    approved: Mapping[str, Any],
) -> dict[str, Any]:
    expected = _validated_poppler_fontconfig_materialization_contract(approved)
    try:
        unresolved_state = path.lstat()
        resolved = path.resolve(strict=True)
        names = sorted(os.listdir(path))
        directory_state = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise OfflineEvidenceError(
            "parent broker OCR private fontconfig cannot be enumerated"
        ) from exc
    expected_names = sorted(
        PurePosixPath(item["relative_path"]).name for item in expected["files"]
    )
    if (
        resolved != path
        or stat.S_ISLNK(unresolved_state.st_mode)
        or not stat.S_ISDIR(directory_state.st_mode)
        or stat.S_IMODE(directory_state.st_mode)
        != expected["directory"]["mode"]
        or names != expected_names
    ):
        raise OfflineEvidenceError(
            "parent broker OCR private fontconfig layout is not exact"
        )

    files: list[dict[str, Any]] = []
    inode_keys: set[tuple[int, int]] = set()
    for expected_file in expected["files"]:
        relative = PurePosixPath(expected_file["relative_path"])
        candidate = path / relative.name
        identity = _bound_regular_file_identity(
            candidate,
            f"parent broker OCR private fontconfig {relative.name}",
        )
        inode_key = (identity["device"], identity["inode"])
        observed = {
            "relative_path": f"fontconfig/{relative.name}",
            "mode": stat.S_IMODE(identity["mode"]),
            "size": identity["size"],
            "sha256": identity["sha256"],
        }
        expected_path_sha256 = hashlib.sha256(
            str(candidate).encode("utf-8")
        ).hexdigest()
        if (
            relative.parent != PurePosixPath("fontconfig")
            or identity["path_sha256"] != expected_path_sha256
            or identity["resolved_path_sha256"] != expected_path_sha256
            or identity["path_is_symlink"] is not False
            or identity["nlink"] != 1
            or inode_key in inode_keys
            or not _type_sensitive_equal(observed, expected_file)
        ):
            raise OfflineEvidenceError(
                "parent broker OCR private fontconfig file identity mismatch"
            )
        inode_keys.add(inode_key)
        files.append(observed)

    core: dict[str, Any] = {
        "schema_version": expected["schema_version"],
        "directory": {
            "relative_path": "fontconfig",
            "mode": stat.S_IMODE(directory_state.st_mode),
        },
        "files": files,
        "file_set_sha256": _identity_sha256(files),
    }
    core["identity_sha256"] = _identity_sha256(core)
    if not _type_sensitive_equal(core, expected):
        raise OfflineEvidenceError(
            "parent broker OCR private fontconfig differs from the approved snapshot"
        )
    return core


def _approved_ocr_native_materialization_contract(
    tool: str,
    external_tools: _ExternalToolSet,
) -> dict[str, Any]:
    if tool not in {"pdftoppm", "tesseract"}:
        raise OfflineEvidenceError("parent broker OCR native tool is not approved")
    tool_set = external_tools.identity
    records = tool_set.get("tools") if isinstance(tool_set, Mapping) else None
    matching = (
        [record for record in records if isinstance(record, Mapping) and record.get("name") == tool]
        if isinstance(records, list)
        else []
    )
    launcher = external_tools.executable_paths.get(tool)
    if (
        tool_set.get("schema_version") != "cloud-v2-external-tool-set-v2"
        or not isinstance(tool_set.get("identity_sha256"), str)
        or tool_set["identity_sha256"]
        != _identity_sha256(
            {key: item for key, item in tool_set.items() if key != "identity_sha256"}
        )
        or len(matching) != 1
        or launcher is None
    ):
        raise OfflineEvidenceError("parent broker OCR approved tool record is malformed")
    record = matching[0]
    closure = _external_tool_macho_closure(launcher, tool_name=tool)
    executable = launcher.resolve(strict=True)
    try:
        executable_state = executable.stat(follow_symlinks=False)
    except OSError as exc:
        raise OfflineEvidenceError(
            "parent broker OCR approved executable is unavailable"
        ) from exc
    executable_sha256 = _stable_file_sha256(
        executable,
        f"parent broker approved OCR executable {tool}",
        enforce_safe_ancestors=False,
    )
    fixed_executables = _validated_ocr_fixed_fixture_anchors()["executables"]
    if (
        not stat.S_ISREG(executable_state.st_mode)
        or record.get("dependency_closure") != closure.identity
        or record.get("executable_sha256") != executable_sha256
        or closure.identity.get("root_executable_sha256") != executable_sha256
        or fixed_executables.get(tool) != executable_sha256
    ):
        raise OfflineEvidenceError(
            "parent broker OCR approved executable closure mismatch"
        )

    dependency_by_path: dict[Path, tuple[str, int]] = {}
    object_by_digest: dict[str, int] = {}
    for image in closure.resolved_images:
        resolved = image.resolve(strict=True)
        if resolved == executable:
            continue
        try:
            state = resolved.stat(follow_symlinks=False)
        except OSError as exc:
            raise OfflineEvidenceError(
                "parent broker OCR approved native image is unavailable"
            ) from exc
        digest = _stable_file_sha256(
            resolved,
            f"parent broker approved OCR native image {tool}",
            enforce_safe_ancestors=False,
        )
        existing_size = object_by_digest.get(digest)
        if (
            not stat.S_ISREG(state.st_mode)
            or (existing_size is not None and existing_size != state.st_size)
        ):
            raise OfflineEvidenceError(
                "parent broker OCR approved native image set is malformed"
            )
        dependency_by_path[resolved] = (digest, state.st_size)
        object_by_digest[digest] = state.st_size
    if not dependency_by_path:
        raise OfflineEvidenceError(
            "parent broker OCR approved native dependency closure is empty"
        )

    aliases: dict[str, str] = {}
    alias_keys: dict[str, str] = {}
    alias_candidates = set(dependency_by_path)
    alias_candidates.update(
        path for path in closure.read_literals if path.name.endswith(".dylib")
    )
    for candidate in sorted(alias_candidates, key=str):
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise OfflineEvidenceError(
                "parent broker OCR approved native alias is unavailable"
            ) from exc
        binding = dependency_by_path.get(resolved)
        if binding is None:
            continue
        digest = binding[0]
        alias = candidate.name
        if not re.fullmatch(r"[A-Za-z0-9._+\-]+\.dylib", alias):
            raise OfflineEvidenceError(
                "parent broker OCR approved native alias is not canonical"
            )
        folded = alias.casefold()
        previous_alias = alias_keys.get(folded)
        if previous_alias is not None and (
            previous_alias != alias or aliases[previous_alias] != digest
        ):
            raise OfflineEvidenceError(
                "parent broker OCR approved native alias conflicts"
            )
        previous_digest = aliases.get(alias)
        if previous_digest is not None and previous_digest != digest:
            raise OfflineEvidenceError(
                "parent broker OCR approved native alias maps to multiple images"
            )
        alias_keys[folded] = alias
        aliases[alias] = digest
    if set(aliases.values()) != set(object_by_digest):
        raise OfflineEvidenceError(
            "parent broker OCR approved native alias closure is incomplete"
        )

    layout_prefix = "" if tool == "pdftoppm" else "native"
    prefix = "" if not layout_prefix else layout_prefix + "/"
    objects = [
        {
            "relative_path": f"{prefix}objects/{digest}.dylib",
            "mode": 0o400,
            "size": object_by_digest[digest],
            "sha256": digest,
        }
        for digest in sorted(object_by_digest)
    ]
    alias_records = [
        {
            "relative_path": f"{prefix}lib/{alias}",
            "target": f"../objects/{digest}.dylib",
            "object_sha256": digest,
        }
        for alias, digest in sorted(aliases.items())
    ]
    core: dict[str, Any] = {
        "schema_version": "cloud-v2-parent-broker-native-materialization-v2",
        "tool": tool,
        "source_tool_set_identity_sha256": tool_set["identity_sha256"],
        "source_tool_record_sha256": _identity_sha256(record),
        "source_macho_closure_identity_sha256": closure.identity["identity_sha256"],
        "source_macho_image_set_sha256": closure.identity["image_set_sha256"],
        "layout_prefix": layout_prefix,
        "fontconfig": (
            _approved_poppler_fontconfig_materialization_contract()
            if tool == "pdftoppm"
            else None
        ),
        "executable": {
            "relative_path": f"{prefix}bin/{tool}",
            "mode": 0o500,
            "size": executable_state.st_size,
            "sha256": executable_sha256,
        },
        "objects": objects,
        "object_set_sha256": _identity_sha256(objects),
        "aliases": alias_records,
        "alias_set_sha256": _identity_sha256(alias_records),
    }
    core["identity_sha256"] = _identity_sha256(core)
    return core


def _observed_ocr_native_materialization_contract(
    *,
    tool: str,
    runtime_path: Path,
    executable_path: Path,
    library_path: Path,
    approved: Mapping[str, Any],
) -> dict[str, Any]:
    layout_prefix = "" if tool == "pdftoppm" else "native"
    materialization_root = runtime_path if not layout_prefix else runtime_path / layout_prefix
    if (
        executable_path != materialization_root / "bin" / tool
        or library_path != materialization_root / "lib"
    ):
        raise OfflineEvidenceError(
            "parent broker OCR private native runtime layout is not fixed"
        )
    expected_root_names = {"bin", "objects", "lib"}
    if tool == "pdftoppm":
        expected_root_names.add("fontconfig")
    try:
        if set(os.listdir(materialization_root)) != expected_root_names:
            raise OfflineEvidenceError(
                "parent broker OCR private native runtime contains extra nodes"
            )
        if os.listdir(executable_path.parent) != [tool]:
            raise OfflineEvidenceError(
                "parent broker OCR private executable set is not exact"
            )
    except OSError as exc:
        raise OfflineEvidenceError(
            "parent broker OCR private native runtime cannot be enumerated"
        ) from exc

    executable_identity = _bound_regular_file_identity(
        executable_path,
        "parent broker OCR private executable materialization",
    )
    prefix = "" if not layout_prefix else layout_prefix + "/"
    executable = {
        "relative_path": f"{prefix}bin/{tool}",
        "mode": stat.S_IMODE(executable_identity["mode"]),
        "size": executable_identity["size"],
        "sha256": executable_identity["sha256"],
    }
    try:
        object_names = sorted(os.listdir(materialization_root / "objects"))
        alias_names = sorted(os.listdir(library_path))
    except OSError as exc:
        raise OfflineEvidenceError(
            "parent broker OCR private native runtime cannot be enumerated"
        ) from exc
    objects: list[dict[str, Any]] = []
    for name in object_names:
        if not re.fullmatch(r"[0-9a-f]{64}\.dylib", name):
            raise OfflineEvidenceError(
                "parent broker OCR private native object name is not canonical"
            )
        identity = _bound_regular_file_identity(
            materialization_root / "objects" / name,
            f"parent broker OCR private native object {name}",
        )
        objects.append(
            {
                "relative_path": f"{prefix}objects/{name}",
                "mode": stat.S_IMODE(identity["mode"]),
                "size": identity["size"],
                "sha256": identity["sha256"],
            }
        )
    aliases: list[dict[str, Any]] = []
    for name in alias_names:
        alias_path = library_path / name
        try:
            state_before = alias_path.lstat()
            target = os.readlink(alias_path)
            state_after = alias_path.lstat()
            resolved = alias_path.resolve(strict=True)
        except OSError as exc:
            raise OfflineEvidenceError(
                "parent broker OCR private native alias is malformed"
            ) from exc
        if (
            _state_identity(state_before) != _state_identity(state_after)
            or not stat.S_ISLNK(state_after.st_mode)
            or not re.fullmatch(r"\.\./objects/[0-9a-f]{64}\.dylib", target)
            or resolved != materialization_root / target.removeprefix("../")
        ):
            raise OfflineEvidenceError(
                "parent broker OCR private native alias is malformed"
            )
        aliases.append(
            {
                "relative_path": f"{prefix}lib/{name}",
                "target": target,
                "object_sha256": target.removeprefix("../objects/").removesuffix(
                    ".dylib"
                ),
            }
        )
    fontconfig = (
        _observed_poppler_fontconfig_materialization_contract(
            materialization_root / "fontconfig",
            approved.get("fontconfig", {}),
        )
        if tool == "pdftoppm"
        else None
    )
    observed = {
        **{
            key: item
            for key, item in approved.items()
            if key
            not in {
                "executable",
                "fontconfig",
                "objects",
                "object_set_sha256",
                "aliases",
                "alias_set_sha256",
                "identity_sha256",
            }
        },
        "fontconfig": fontconfig,
        "executable": executable,
        "objects": objects,
        "object_set_sha256": _identity_sha256(objects),
        "aliases": aliases,
        "alias_set_sha256": _identity_sha256(aliases),
    }
    observed["identity_sha256"] = _identity_sha256(observed)
    if not _type_sensitive_equal(observed, approved):
        raise OfflineEvidenceError(
            "parent broker OCR private native runtime differs from the approved closure"
        )
    return observed


def _expected_ocr_runtime_nodes(
    *,
    tool: str,
    approved_materialization: Mapping[str, Any],
    sealed_tessdata_snapshot_identity: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    materialization_fields = {
        "schema_version",
        "tool",
        "source_tool_set_identity_sha256",
        "source_tool_record_sha256",
        "source_macho_closure_identity_sha256",
        "source_macho_image_set_sha256",
        "layout_prefix",
        "fontconfig",
        "executable",
        "objects",
        "object_set_sha256",
        "aliases",
        "alias_set_sha256",
        "identity_sha256",
    }
    if (
        tool not in {"pdftoppm", "tesseract"}
        or not isinstance(approved_materialization, Mapping)
        or set(approved_materialization) != materialization_fields
        or approved_materialization["schema_version"]
        != "cloud-v2-parent-broker-native-materialization-v2"
        or approved_materialization["tool"] != tool
        or approved_materialization["layout_prefix"]
        != ("" if tool == "pdftoppm" else "native")
        or not isinstance(approved_materialization["objects"], list)
        or not isinstance(approved_materialization["aliases"], list)
        or approved_materialization["object_set_sha256"]
        != _identity_sha256(approved_materialization["objects"])
        or approved_materialization["alias_set_sha256"]
        != _identity_sha256(approved_materialization["aliases"])
        or approved_materialization["identity_sha256"]
        != _identity_sha256(
            {
                key: item
                for key, item in approved_materialization.items()
                if key != "identity_sha256"
            }
        )
    ):
        raise OfflineEvidenceError(
            "parent broker OCR approved runtime contract is malformed"
        )
    fontconfig = approved_materialization["fontconfig"]
    if tool == "pdftoppm":
        fontconfig = _validated_poppler_fontconfig_materialization_contract(
            fontconfig
        )
    elif fontconfig is not None:
        raise OfflineEvidenceError(
            "parent broker OCR approved runtime contract is malformed"
        )
    prefix = "" if tool == "pdftoppm" else "native/"
    directory_modes = (
        {
            ".": 0o700,
            "bin": 0o500,
            "fontconfig": 0o500,
            "lib": 0o500,
            "objects": 0o500,
        }
        if tool == "pdftoppm"
        else {
            ".": 0o700,
            "native": 0o700,
            "native/bin": 0o500,
            "native/lib": 0o500,
            "native/objects": 0o500,
            "tessdata": 0o500,
        }
    )
    nodes: list[dict[str, Any]] = [
        {"path": path, "kind": "directory", "mode": mode}
        for path, mode in directory_modes.items()
    ]
    native_files = [
        approved_materialization["executable"],
        *approved_materialization["objects"],
    ]
    for item in native_files:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"relative_path", "mode", "size", "sha256"}
            or type(item["mode"]) is not int
            or item["mode"] not in {0o400, 0o500}
            or type(item["size"]) is not int
            or item["size"] <= 0
            or not isinstance(item["sha256"], str)
            or not _SHA256.fullmatch(item["sha256"])
        ):
            raise OfflineEvidenceError(
                "parent broker OCR approved runtime contract is malformed"
            )
        relative = _canonical_relative(
            item["relative_path"],
            "parent broker OCR runtime node",
        )
        if not relative.startswith(prefix):
            raise OfflineEvidenceError(
                "parent broker OCR approved runtime contract is malformed"
            )
        nodes.append(
            {
                "path": relative,
                "kind": "file",
                "mode": item["mode"],
                "size": item["size"],
                "sha256": item["sha256"],
            }
        )
    if tool == "pdftoppm":
        for item in fontconfig["files"]:
            nodes.append(
                {
                    "path": item["relative_path"],
                    "kind": "file",
                    "mode": item["mode"],
                    "size": item["size"],
                    "sha256": item["sha256"],
                }
            )
    for item in approved_materialization["aliases"]:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"relative_path", "target", "object_sha256"}
            or not isinstance(item["target"], str)
            or not isinstance(item["object_sha256"], str)
            or not _SHA256.fullmatch(item["object_sha256"])
            or item["target"]
            != f"../objects/{item['object_sha256']}.dylib"
        ):
            raise OfflineEvidenceError(
                "parent broker OCR approved runtime contract is malformed"
            )
        relative = _canonical_relative(
            item["relative_path"],
            "parent broker OCR runtime node",
        )
        if not relative.startswith(f"{prefix}lib/"):
            raise OfflineEvidenceError(
                "parent broker OCR approved runtime contract is malformed"
            )
        nodes.append(
            {
                "path": relative,
                "kind": "symlink",
                "mode": 0o777,
                "target_sha256": hashlib.sha256(
                    item["target"].encode("utf-8")
                ).hexdigest(),
            }
        )

    if tool == "tesseract":
        tessdata_fields = {
            "schema_version",
            "source_identity_sha256",
            "root_mode",
            "file_count",
            "file_names",
            "file_set_sha256",
            "files",
            "identity_sha256",
        }
        files = (
            sealed_tessdata_snapshot_identity.get("files")
            if isinstance(sealed_tessdata_snapshot_identity, Mapping)
            else None
        )
        if (
            not isinstance(sealed_tessdata_snapshot_identity, Mapping)
            or set(sealed_tessdata_snapshot_identity) != tessdata_fields
            or sealed_tessdata_snapshot_identity["schema_version"]
            != "cloud-v2-private-ocr-tessdata-snapshot-v1"
            or type(sealed_tessdata_snapshot_identity["root_mode"]) is not int
            or sealed_tessdata_snapshot_identity["root_mode"] != 0o500
            or sealed_tessdata_snapshot_identity["file_names"]
            != list(_OCR_TESSDATA_SNAPSHOT_NAMES)
            or type(sealed_tessdata_snapshot_identity["file_count"]) is not int
            or sealed_tessdata_snapshot_identity["file_count"]
            != len(_OCR_TESSDATA_SNAPSHOT_NAMES)
            or not isinstance(files, list)
            or len(files) != len(_OCR_TESSDATA_SNAPSHOT_NAMES)
            or sealed_tessdata_snapshot_identity["file_set_sha256"]
            != _identity_sha256(files)
            or sealed_tessdata_snapshot_identity["identity_sha256"]
            != _identity_sha256(
                {
                    key: item
                    for key, item in sealed_tessdata_snapshot_identity.items()
                    if key != "identity_sha256"
                }
            )
        ):
            raise OfflineEvidenceError(
                "parent broker OCR sealed tessdata node contract is malformed"
            )
        for expected_name, item in zip(
            _OCR_TESSDATA_SNAPSHOT_NAMES,
            files,
            strict=True,
        ):
            if (
                not isinstance(item, Mapping)
                or set(item) != {"name", "mode", "size", "sha256"}
                or item["name"] != expected_name
                or type(item["mode"]) is not int
                or item["mode"] != 0o400
                or type(item["size"]) is not int
                or item["size"] <= 0
                or not isinstance(item["sha256"], str)
                or not _SHA256.fullmatch(item["sha256"])
            ):
                raise OfflineEvidenceError(
                    "parent broker OCR sealed tessdata node contract is malformed"
                )
            nodes.append(
                {
                    "path": f"tessdata/{expected_name}",
                    "kind": "file",
                    "mode": item["mode"],
                    "size": item["size"],
                    "sha256": item["sha256"],
                }
            )
    nodes.sort(key=lambda item: item["path"])
    if len({item["path"] for item in nodes}) != len(nodes):
        raise OfflineEvidenceError(
            "parent broker OCR runtime node contract is not unique"
        )
    return nodes


def _ocr_native_runtime_identity(
    runtime_path: Path,
    executable_path: Path,
    library_path: Path,
    *,
    tool: str,
    external_tools: _ExternalToolSet,
    sealed_tessdata_snapshot_identity: Mapping[str, Any] | None,
) -> dict[str, Any]:
    approved_materialization = _approved_ocr_native_materialization_contract(
        tool,
        external_tools,
    )
    materialization = _observed_ocr_native_materialization_contract(
        tool=tool,
        runtime_path=runtime_path,
        executable_path=executable_path,
        library_path=library_path,
        approved=approved_materialization,
    )
    expected_nodes = _expected_ocr_runtime_nodes(
        tool=tool,
        approved_materialization=approved_materialization,
        sealed_tessdata_snapshot_identity=sealed_tessdata_snapshot_identity,
    )
    tree, _read_literals = _bound_runtime_tree_identity(
        runtime_path,
        "parent broker private OCR native runtime",
        include_canonical_nodes=True,
    )
    if not _type_sensitive_equal(tree["nodes"], expected_nodes):
        raise OfflineEvidenceError(
            "parent broker OCR runtime nodes differ from the canonical contract"
        )
    core: dict[str, Any] = {
        "schema_version": "cloud-v2-parent-broker-native-runtime-v4",
        "tree": tree,
        "executable": _bound_regular_file_identity(
            executable_path,
            "parent broker private OCR executable",
        ),
        "library_root": _directory_identity(
            library_path,
            "parent broker private OCR library",
        ),
        "approved_materialization": approved_materialization,
        "materialization": materialization,
    }
    core["identity_sha256"] = _identity_sha256(core)
    return core


def _ocr_rendered_page_set_identity(path: Path) -> dict[str, Any]:
    root, root_fd = _open_directory_fd(
        path,
        "parent broker rendered OCR pages",
        enforce_safe_ancestors=False,
    )
    try:
        names = tuple(sorted(os.listdir(root_fd)))
        expected_names = tuple(f"page-{number:02d}.jpg" for number in range(1, 11))
        if root != path or names != expected_names:
            raise OfflineEvidenceError(
                "parent broker pdftoppm output page set is not exact"
            )
        records: list[dict[str, Any]] = []
        fixed_records = _validated_ocr_fixed_fixture_anchors()["rendered_pages"]
        for page_number, name in enumerate(expected_names, 1):
            payload, binding = _stable_relative_file_binding(
                root_fd,
                name,
                f"parent broker rendered OCR page {name}",
                max_bytes=16 * 1024 * 1024,
            )
            if not payload:
                raise OfflineEvidenceError("parent broker rendered OCR page is empty")
            record = {
                "page_number": page_number,
                "name": name,
                "mode": stat.S_IMODE(binding["mode"]),
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            fixed = fixed_records[page_number - 1]
            if any(record[field] != fixed[field] for field in fixed):
                raise OfflineEvidenceError(
                    "parent broker rendered OCR page differs from the fixed fixture"
                )
            records.append(record)
        core: dict[str, Any] = {
            "schema_version": "cloud-v2-parent-broker-rendered-pages-v1",
            "page_count": len(records),
            "page_numbers": list(range(1, 11)),
            "files": records,
            "file_set_sha256": _identity_sha256(records),
        }
        core["identity_sha256"] = _identity_sha256(core)
        return core
    finally:
        os.close(root_fd)


def _run_ocr_native_process(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    input_payload: bytes | None,
    timeout: float,
    shared_deadline_monotonic_ns: int,
    cancel_event: threading.Event,
    input_descriptor: int | None = None,
    input_size: int | None = None,
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, int], dict[str, Any]]:
    descriptor_input = input_descriptor is not None
    payload_input = input_payload is not None
    if (
        type(shared_deadline_monotonic_ns) is not int
        or shared_deadline_monotonic_ns <= 0
        or not isinstance(cancel_event, threading.Event)
        or cancel_event.is_set()
        or (payload_input and type(input_payload) is not bytes)
        or (payload_input and descriptor_input)
        or (
            descriptor_input
            and (
                type(input_descriptor) is not int
                or input_descriptor <= 2
                or type(input_size) is not int
                or input_size <= 0
            )
        )
        or (not descriptor_input and input_size is not None)
    ):
        raise OfflineEvidenceError("parent broker OCR execution context is invalid")
    if descriptor_input:
        assert input_descriptor is not None
        try:
            descriptor_state = os.fstat(input_descriptor)
        except OSError as exc:
            raise OfflineEvidenceError(
                "parent broker OCR input descriptor is unavailable"
            ) from exc
        if (
            not stat.S_ISREG(descriptor_state.st_mode)
            or descriptor_state.st_size != input_size
        ):
            raise OfflineEvidenceError(
                "parent broker OCR input descriptor identity is invalid"
            )
    input_length = (
        input_size
        if descriptor_input
        else 0 if input_payload is None else len(input_payload)
    )
    has_input = payload_input or descriptor_input
    process: subprocess.Popen[bytes] | None = None
    process_group_quiescent = False
    started_monotonic_ns = time.monotonic_ns()
    effective_deadline_monotonic_ns = min(
        shared_deadline_monotonic_ns,
        started_monotonic_ns + int(timeout * 1_000_000_000),
    )
    if effective_deadline_monotonic_ns <= started_monotonic_ns:
        raise subprocess.TimeoutExpired(command, timeout)
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=dict(environment),
            stdin=subprocess.PIPE if has_input else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
        process_identity = _observed_new_session_process_identity(
            process,
            "parent broker OCR child",
        )
        if process.stdout is None or process.stderr is None:
            raise OfflineEvidenceError("parent broker OCR output pipes are unavailable")
        stdout_buffer = bytearray()
        stderr_buffer = bytearray()
        read_streams: dict[int, tuple[bytearray, int]] = {
            process.stdout.fileno(): (stdout_buffer, _BROKER_STDOUT_MAX_BYTES),
            process.stderr.fileno(): (stderr_buffer, _BROKER_STDERR_MAX_BYTES),
        }
        if len(read_streams) != 2:
            raise OfflineEvidenceError("parent broker OCR output pipes are not independent")
        input_stream = process.stdin if has_input else None
        input_fd = None if input_stream is None else input_stream.fileno()
        for descriptor in (*read_streams, *((input_fd,) if input_fd is not None else ())):
            os.set_blocking(descriptor, False)
        input_offset = 0
        total_output = 0
        while read_streams or input_fd is not None:
            if cancel_event.is_set():
                raise OfflineEvidenceError("parent broker OCR batch was cancelled")
            remaining_ns = effective_deadline_monotonic_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            polled = [*read_streams, *((input_fd,) if input_fd is not None else ())]
            try:
                readable, writable, exceptional = select.select(
                    list(read_streams),
                    [] if input_fd is None else [input_fd],
                    polled,
                    min(remaining_ns / 1_000_000_000, 0.05),
                )
            except InterruptedError:
                continue
            except (OSError, ValueError) as exc:
                raise OfflineEvidenceError(
                    "parent broker OCR pipes could not be polled"
                ) from exc
            if exceptional:
                raise OfflineEvidenceError("parent broker OCR pipe failed")
            for descriptor in readable:
                output, limit = read_streams[descriptor]
                try:
                    chunk = os.read(
                        descriptor,
                        max(
                            1,
                            min(
                                64 * 1024,
                                limit + 1 - len(output),
                                _BROKER_TOTAL_OUTPUT_MAX_BYTES + 1 - total_output,
                            ),
                        ),
                    )
                except (BlockingIOError, InterruptedError):
                    continue
                except OSError as exc:
                    raise OfflineEvidenceError(
                        "parent broker OCR output pipe could not be read"
                    ) from exc
                if not chunk:
                    read_streams.pop(descriptor)
                    continue
                output.extend(chunk)
                total_output += len(chunk)
                if (
                    len(output) > limit
                    or total_output > _BROKER_TOTAL_OUTPUT_MAX_BYTES
                ):
                    raise OfflineEvidenceError(
                        "parent broker OCR output exceeds the streaming size limit"
                    )
            if input_fd is not None and input_fd in writable:
                try:
                    if input_payload is not None:
                        input_chunk = input_payload[
                            input_offset : input_offset + 64 * 1024
                        ]
                    else:
                        assert input_descriptor is not None
                        input_chunk = os.pread(
                            input_descriptor,
                            min(64 * 1024, input_length - input_offset),
                            input_offset,
                        )
                        if not input_chunk and input_offset < input_length:
                            raise OfflineEvidenceError(
                                "parent broker OCR held input became shorter"
                            )
                    count = os.write(input_fd, input_chunk)
                except (BlockingIOError, InterruptedError):
                    continue
                except BrokenPipeError:
                    count = 0
                    input_offset = input_length
                except OfflineEvidenceError:
                    raise
                except OSError as exc:
                    raise OfflineEvidenceError(
                        "parent broker OCR stdin pipe could not be written"
                    ) from exc
                if count < 0:
                    raise OfflineEvidenceError("parent broker OCR stdin write failed")
                input_offset += count
                if input_offset == input_length:
                    assert input_stream is not None
                    input_stream.close()
                    input_stream = None
                    input_fd = None
        while process.poll() is None:
            if cancel_event.is_set():
                raise OfflineEvidenceError("parent broker OCR batch was cancelled")
            remaining_ns = effective_deadline_monotonic_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                process.wait(timeout=min(remaining_ns / 1_000_000_000, 0.05))
            except subprocess.TimeoutExpired:
                continue
        _require_brokered_process_group_quiescence(
            process,
            field="parent broker OCR child",
        )
        process_group_quiescent = True
        ended_monotonic_ns = time.monotonic_ns()
        if ended_monotonic_ns > effective_deadline_monotonic_ns:
            raise subprocess.TimeoutExpired(command, timeout)
        timing: dict[str, Any] = {
            "schema_version": "cloud-v2-parent-broker-process-timing-v1",
            "clock": "parent-monotonic-ns",
            "started_monotonic_ns": started_monotonic_ns,
            "ended_monotonic_ns": ended_monotonic_ns,
            "duration_ns": ended_monotonic_ns - started_monotonic_ns,
            "effective_deadline_monotonic_ns": effective_deadline_monotonic_ns,
            "shared_deadline_monotonic_ns": shared_deadline_monotonic_ns,
        }
        timing["identity_sha256"] = _identity_sha256(timing)
        return (
            subprocess.CompletedProcess(
                args=list(command),
                returncode=process.returncode,
                stdout=bytes(stdout_buffer),
                stderr=bytes(stderr_buffer),
            ),
            process_identity,
            timing,
        )
    finally:
        primary_error = sys.exception()
        cleanup_error: Exception | None = None
        if process is not None and not process_group_quiescent:
            try:
                _terminate_brokered_process(process)
            except Exception as exc:
                cleanup_error = exc
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if isinstance(stream, io.IOBase):
                    try:
                        stream.close()
                    except OSError as exc:
                        cleanup_error = _merge_cleanup_error(
                            cleanup_error,
                            exc,
                            label="parent broker OCR pipe",
                        )
        _finish_process_cleanup(cleanup_error, primary_error=primary_error)


def _ocr_native_execution_slot(sequence: int) -> dict[str, Any]:
    if type(sequence) is not int or sequence not in range(0, 11):
        raise OfflineEvidenceError("parent broker OCR execution sequence is invalid")
    if sequence == 0:
        core: dict[str, Any] = {
            "schema_version": "cloud-v2-parent-broker-execution-slot-v1",
            "phase": "render",
            "batch_index": 0,
            "batch_size": 1,
            "slot_index": 0,
            "worker_limit": 1,
        }
    else:
        offset = sequence - 1
        consumed = 0
        for batch_index, batch_size in enumerate(_OCR_NATIVE_BATCH_SIZES, 1):
            if offset < consumed + batch_size:
                core = {
                    "schema_version": "cloud-v2-parent-broker-execution-slot-v1",
                    "phase": "tesseract",
                    "batch_index": batch_index,
                    "batch_size": batch_size,
                    "slot_index": offset - consumed,
                    "worker_limit": _OCR_NATIVE_WORKER_LIMIT,
                }
                break
            consumed += batch_size
        else:
            raise OfflineEvidenceError("parent broker OCR execution slot is invalid")
    core["identity_sha256"] = _identity_sha256(core)
    return core


def _validated_ocr_process_timing(
    value: object,
    *,
    shared_deadline_monotonic_ns: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "clock",
        "started_monotonic_ns",
        "ended_monotonic_ns",
        "duration_ns",
        "effective_deadline_monotonic_ns",
        "shared_deadline_monotonic_ns",
        "identity_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OfflineEvidenceError("parent broker OCR process timing is malformed")
    started = value["started_monotonic_ns"]
    ended = value["ended_monotonic_ns"]
    effective_deadline = value["effective_deadline_monotonic_ns"]
    if (
        value["schema_version"]
        != "cloud-v2-parent-broker-process-timing-v1"
        or value["clock"] != "parent-monotonic-ns"
        or type(shared_deadline_monotonic_ns) is not int
        or type(timeout_seconds) is not float
        or any(
            type(value[name]) is not int or value[name] <= 0
            for name in (
                "started_monotonic_ns",
                "ended_monotonic_ns",
                "duration_ns",
                "effective_deadline_monotonic_ns",
                "shared_deadline_monotonic_ns",
            )
        )
        or value["shared_deadline_monotonic_ns"]
        != shared_deadline_monotonic_ns
        or effective_deadline
        != min(
            shared_deadline_monotonic_ns,
            started + int(timeout_seconds * 1_000_000_000),
        )
        or not started < ended <= effective_deadline
        or value["duration_ns"] != ended - started
        or value["identity_sha256"]
        != _identity_sha256(
            {key: item for key, item in value.items() if key != "identity_sha256"}
        )
    ):
        raise OfflineEvidenceError("parent broker OCR process timing is malformed")
    return dict(value)


def _execute_ocr_native_operation(
    *,
    probe_id: str,
    operation_id: str,
    parameters: Mapping[str, Any],
    worker_scratch: _ComponentScratch,
    parent_snapshot: _PrivateSnapshot,
    python: Path,
    python_identity: Mapping[str, Any],
    full_external_tools: _ExternalToolSet,
    full_closure: _RuntimeSandboxClosure,
    tessdata_snapshot: _SealedTessdataSnapshot | None,
    sequence: int,
    shared_deadline_monotonic_ns: int,
    cancel_event: threading.Event,
    execution_slot: Mapping[str, Any],
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    value = _validated_ocr_native_parameters(
        parameters,
        probe_id=probe_id,
        operation_id=operation_id,
    )
    tessdata_probe = _is_ocr_tessdata_probe(probe_id)
    if tessdata_probe != (tessdata_snapshot is not None):
        raise OfflineEvidenceError(
            "parent broker OCR tessdata snapshot scope is not exact"
        )
    expected_slot = _ocr_native_execution_slot(sequence)
    if (sequence == 0) != (value["tool"] == "pdftoppm"):
        raise OfflineEvidenceError("parent broker OCR execution sequence mismatch")
    if not _type_sensitive_equal(execution_slot, expected_slot):
        raise OfflineEvidenceError("parent broker OCR execution slot mismatch")
    _revalidate_component_scratch(worker_scratch)
    _revalidate_private_snapshot(parent_snapshot)
    _revalidate_runtime_sandbox_closure(
        full_closure.identity,
        python=python,
        python_identity=python_identity,
        external_tools=full_external_tools,
    )
    if tessdata_snapshot is not None:
        _revalidate_sealed_tessdata_snapshot(tessdata_snapshot)

    def existing_path(relative: str, field: str, *, directory: bool) -> Path:
        path = worker_scratch.path / relative
        observed = _ocr_worker_relative_path(
            path,
            worker_scratch.path,
            field,
            directory=directory,
        )
        if observed != relative:
            raise OfflineEvidenceError(f"{field} relative identity changed")
        return path.resolve(strict=True)

    containment = existing_path(
        value["containment_relative"],
        "parent broker OCR containment",
        directory=True,
    )
    native_runtime = existing_path(
        value["native_runtime_relative"],
        "parent broker OCR native runtime",
        directory=True,
    )
    executable = existing_path(
        value["private_executable_relative"],
        "parent broker OCR private executable",
        directory=False,
    )
    library = existing_path(
        value["private_library_relative"],
        "parent broker OCR private library",
        directory=True,
    )
    scratch = existing_path(
        value["scratch_relative"],
        "parent broker OCR scratch",
        directory=True,
    )
    tool = value["tool"]
    environment = dict(value["environment"])
    expected_environment = {
        "PATH": _OCR_NATIVE_TOOL_SEARCH_PATH,
        "DYLD_LIBRARY_PATH": str(library),
        "TMPDIR": str(scratch),
        "TMP": str(scratch),
        "TEMP": str(scratch),
        "HOME": str(scratch),
    }
    page: Path | None = None
    private_tessdata: Path | None = None
    private_fontconfig: Path | None = None
    output_root: Path | None = None
    input_payload: bytes | None = None
    if tool == "pdftoppm":
        private_fontconfig = existing_path(
            value["private_fontconfig_relative"],
            "parent broker OCR private fontconfig",
            directory=False,
        )
        if private_fontconfig != native_runtime / "fontconfig/fonts.conf":
            raise OfflineEvidenceError(
                "parent broker OCR private fontconfig path changed"
            )
        expected_environment["FONTCONFIG_FILE"] = str(private_fontconfig)
        if value["input_delivery"] == "inline-base64":
            output_prefix_relative = value["output_prefix_relative"]
            output_prefix = worker_scratch.path / output_prefix_relative
            output_root = existing_path(
                str(PurePosixPath(output_prefix_relative).parent),
                "parent broker OCR output root",
                directory=True,
            )
            if output_prefix != output_root / "page" or os.listdir(output_root):
                raise OfflineEvidenceError(
                    "parent broker pdftoppm output root is not empty"
                )
            input_payload = _decoded_canonical_base64(
                value["input_base64"],
                field="parent broker OCR PDF input",
                max_bytes=_OCR_NATIVE_INPUT_MAX_BYTES,
            )
            tool_command = [
                str(executable),
                "-r",
                "170",
                "-jpeg",
                "-jpegopt",
                "quality=92",
                "-",
                str(output_prefix),
            ]
            writable_roots = (scratch, output_root)
        else:
            tool_command = [
                str(executable),
                "-f",
                "132",
                "-l",
                "132",
                "-singlefile",
                "-r",
                "170",
                "-jpeg",
                "-jpegopt",
                "quality=92",
                "-",
            ]
            writable_roots = (scratch,)
        expected_profile = _expected_ocr_native_profile(
            executable,
            writable_roots=writable_roots,
            read_only_roots=(native_runtime, _HOMEBREW_POPPLER_DATA_ROOT),
            read_only_files=(),
        )
    else:
        page = existing_path(
            value["approved_page_relative"],
            "parent broker OCR approved page",
            directory=False,
        )
        private_tessdata = existing_path(
            value["private_tessdata_relative"],
            "parent broker OCR private tessdata",
            directory=True,
        )
        expected_environment.update(
            {
                "TESSDATA_PREFIX": str(private_tessdata),
                "OMP_THREAD_LIMIT": "1",
            }
        )
        tool_command = [
            str(executable),
            str(page),
            "stdout",
            "-l",
            "chi_sim+eng",
            "--psm",
            "6",
        ]
        expected_profile = _expected_ocr_native_profile(
            executable,
            writable_roots=(scratch,),
            read_only_roots=(native_runtime,),
            read_only_files=(page,),
        )
    if not _type_sensitive_equal(environment, expected_environment):
        raise OfflineEvidenceError("parent broker OCR environment path binding mismatch")
    profile_payload = _decoded_canonical_base64(
        value["profile_base64"],
        field="parent broker OCR profile",
        max_bytes=2 * 1024 * 1024,
    )
    if profile_payload != expected_profile.encode("utf-8"):
        raise OfflineEvidenceError(
            "parent broker OCR profile differs from the reconstructed fixed profile"
        )
    native_runtime_identity = _ocr_native_runtime_identity(
        native_runtime,
        executable,
        library,
        tool=tool,
        external_tools=full_external_tools,
        sealed_tessdata_snapshot_identity=(
            None if tessdata_snapshot is None else tessdata_snapshot.identity
        ),
    )
    page_identity = (
        None
        if page is None
        else _bound_regular_file_identity(page, "parent broker OCR approved page")
    )
    if page_identity is not None and page_identity["nlink"] != 1:
        raise OfflineEvidenceError("parent broker OCR approved page is hard-linked")
    private_tessdata_identity = (
        None
        if private_tessdata is None
        else _ocr_private_tessdata_identity(private_tessdata, tessdata_snapshot)
    )
    input_identity: dict[str, Any] | None = None
    if input_payload is not None:
        input_identity = {
            "schema_version": "cloud-v2-parent-broker-ocr-input-v1",
            "role": "pdf-bytes-pipe",
            "size": len(input_payload),
            "sha256": hashlib.sha256(input_payload).hexdigest(),
        }
        input_identity["identity_sha256"] = _identity_sha256(input_identity)

    assignments = [
        f"{name}={environment[name]}" for name in sorted(environment)
    ]
    command = [
        str(NETWORK_SANDBOX_PATH),
        "-p",
        expected_profile,
        "/usr/bin/env",
        "-i",
        *assignments,
        *tool_command,
    ]
    held_input: _HeldRelativeInput | None = None
    try:
        if value["input_delivery"] == "sealed-snapshot-held-descriptor":
            held_input = _hold_relative_input_file(
                parent_snapshot.root_fd,
                value["input_snapshot_relative"],
                "parent broker page 132 snapshot input",
                expected_size=_OCR_PAGE_132_INPUT_ANCHOR["size"],
                expected_sha256=_OCR_PAGE_132_INPUT_ANCHOR["sha256"],
            )
            _revalidate_held_relative_input(held_input, parent_snapshot.root_fd)
            input_core = {
                "schema_version": "cloud-v2-parent-broker-ocr-held-input-v1",
                "role": "pdf-bytes-pipe",
                "delivery": "sealed-snapshot-held-descriptor",
                "snapshot_relative": held_input.relative_path,
                "mode": held_input.state.st_mode,
                "nlink": held_input.state.st_nlink,
                "size": held_input.size,
                "sha256": held_input.sha256,
            }
            input_identity = {
                **input_core,
                "identity_sha256": _identity_sha256(input_core),
            }
        completed, process_identity, process_timing = _run_ocr_native_process(
            command,
            cwd=scratch,
            environment=environment,
            input_payload=input_payload,
            input_descriptor=(
                None if held_input is None else held_input.descriptor
            ),
            input_size=None if held_input is None else held_input.size,
            timeout=value["timeout_seconds"],
            shared_deadline_monotonic_ns=shared_deadline_monotonic_ns,
            cancel_event=cancel_event,
        )
        if held_input is not None:
            _revalidate_held_relative_input(held_input, parent_snapshot.root_fd)
    finally:
        if held_input is not None:
            _close_held_relative_input(held_input)
    stdout, stderr = _validated_parent_broker_output(
        completed.stdout,
        completed.stderr,
        field="parent broker OCR child",
    )
    assert stderr is not None
    if completed.returncode != 0:
        raise OfflineEvidenceError("parent broker OCR native child failed")
    completed = subprocess.CompletedProcess(
        args=command,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )
    if _ocr_native_runtime_identity(
        native_runtime,
        executable,
        library,
        tool=tool,
        external_tools=full_external_tools,
        sealed_tessdata_snapshot_identity=(
            None if tessdata_snapshot is None else tessdata_snapshot.identity
        ),
    ) != native_runtime_identity:
        raise OfflineEvidenceError("parent broker OCR native runtime changed")
    if page is not None and _bound_regular_file_identity(
        page, "parent broker OCR approved page"
    ) != page_identity:
        raise OfflineEvidenceError("parent broker OCR approved page changed")
    if private_tessdata is not None and _ocr_private_tessdata_identity(
        private_tessdata, tessdata_snapshot
    ) != private_tessdata_identity:
        raise OfflineEvidenceError("parent broker private OCR tessdata changed")
    output_identity: dict[str, Any]
    if output_root is not None:
        output_identity = _ocr_rendered_page_set_identity(output_root)
    else:
        output_identity = {
            "schema_version": "cloud-v2-parent-broker-ocr-stdout-v1",
            "page_number": value["page_number"],
            "size": len(stdout),
            "sha256": hashlib.sha256(stdout).hexdigest(),
        }
        fixed = (
            _OCR_PAGE_132_OUTPUT_ANCHOR
            if probe_id == _REAL_PAGE_132_PROBE_ID
            else _validated_ocr_fixed_fixture_anchors()["stdout"][
                value["page_number"] - 1
            ]
        )
        if any(output_identity[field] != fixed[field] for field in fixed):
            raise OfflineEvidenceError(
                "parent broker OCR stdout differs from the fixed fixture"
            )
        output_identity["identity_sha256"] = _identity_sha256(output_identity)
    _revalidate_component_scratch(worker_scratch)
    _revalidate_private_snapshot(parent_snapshot)
    _revalidate_runtime_sandbox_closure(
        full_closure.identity,
        python=python,
        python_identity=python_identity,
        external_tools=full_external_tools,
    )
    if tessdata_snapshot is not None:
        _revalidate_sealed_tessdata_snapshot(tessdata_snapshot)

    normalized_command = _parent_broker_normalized_command(
        value,
        operation_id=operation_id,
    )
    profile_sha256 = hashlib.sha256(profile_payload).hexdigest()
    profile_delivery = {
        "mode": "sandbox-exec-inline-profile-argv",
        "argument_index": 2,
        "size": len(profile_payload),
        "sha256": profile_sha256,
    }
    profile_delivery["identity_sha256"] = _identity_sha256(profile_delivery)
    network_evidence = {
        "schema_version": NETWORK_ENFORCEMENT_SCHEMA_VERSION,
        "status": "passed",
        "source": "reconstructed-source-extract-inline-seatbelt-profile",
        "required_result": {
            "profile_rule": "(deny network*)",
            "sandbox": "sandbox-exec-inline-profile",
        },
    }
    operation_record: dict[str, Any] = {
        "sequence": -1,
        "operation_id": operation_id,
        "parameters_sha256": _identity_sha256(value),
        "normalized_command": normalized_command,
        "normalized_command_sha256": _identity_sha256(normalized_command),
        "profile_base64": base64.b64encode(profile_payload).decode("ascii"),
        "profile_sha256": profile_sha256,
        "stdin_role": value["stdin_role"],
        "stdin_profile_size": 0,
        "stdin_profile_sha256": hashlib.sha256(b"").hexdigest(),
        "runtime_closure_identity": dict(full_closure.identity),
        "runtime_closure_identity_sha256": full_closure.identity["identity_sha256"],
        "snapshot_identity": dict(parent_snapshot.identity),
        "snapshot_identity_sha256": parent_snapshot.identity["identity_sha256"],
        "environment": environment,
        "environment_sha256": _identity_sha256(environment),
        "snapshot_path": str(parent_snapshot.path),
        "scratch_path": str(scratch),
        "denial_probe_path": None,
        "child_sandbox_binding": None,
        "target_executable_identity": None,
        "pass_fd_roles": [],
        "process_identity": process_identity,
        "returncode": completed.returncode,
        "stdout_size": len(stdout),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_size": len(stderr),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "text_mode": False,
        "network_enforcement": network_evidence,
        "direct_child_waited": True,
        "process_group_quiescence_verified": True,
        "timeout_cleanup_contract": (
            "new-session-process-group-quiescence-or-killpg-and-wait"
        ),
        "profile_scratch": None,
        "profile_delivery": profile_delivery,
        "input_identity": input_identity,
        "native_runtime_identity": native_runtime_identity,
        "page_identity": page_identity,
        "private_tessdata_identity": private_tessdata_identity,
        "output_identity": output_identity,
        "sealed_tessdata_snapshot_identity_sha256": (
            None
            if tessdata_snapshot is None
            else tessdata_snapshot.identity["identity_sha256"]
        ),
        "process_timing": process_timing,
        "execution_slot": dict(execution_slot),
    }
    return completed, operation_record


def _execute_parent_broker_operation(
    *,
    probe_id: str,
    sequence: int,
    operation_id: str,
    parameters: Mapping[str, Any],
    worker_scratch: _ComponentScratch,
    parent_snapshot: _PrivateSnapshot,
    python: Path,
    python_identity: Mapping[str, Any],
    full_external_tools: _ExternalToolSet,
    full_closure: _RuntimeSandboxClosure,
    production_embedding_fixture: _ProductionEmbeddingFixture | None = None,
    ocr_tessdata_snapshot: _SealedTessdataSnapshot | None = None,
    shared_deadline_monotonic_ns: int,
    cancel_event: threading.Event,
    execution_slot: Mapping[str, Any] | None,
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    value = _validated_parent_broker_parameters(
        parameters,
        probe_id=probe_id,
        operation_id=operation_id,
    )
    production_embedding_probe = probe_id == _PRODUCTION_EMBEDDING_PROBE_ID
    ocr_probe = _is_ocr_native_probe(probe_id)
    ocr_tessdata_probe = _is_ocr_tessdata_probe(probe_id)
    if production_embedding_probe != (production_embedding_fixture is not None):
        raise OfflineEvidenceError(
            "parent broker production embedding fixture scope is not exact"
        )
    if production_embedding_fixture is not None:
        _revalidate_production_embedding_fixture(production_embedding_fixture)
    if ocr_tessdata_probe != (ocr_tessdata_snapshot is not None):
        raise OfflineEvidenceError(
            "parent broker OCR tessdata snapshot scope is not exact"
        )
    if ocr_probe:
        if execution_slot is None:
            raise OfflineEvidenceError("parent broker OCR execution slot is missing")
        return _execute_ocr_native_operation(
            probe_id=probe_id,
            operation_id=operation_id,
            parameters=value,
            worker_scratch=worker_scratch,
            parent_snapshot=parent_snapshot,
            python=python,
            python_identity=python_identity,
            full_external_tools=full_external_tools,
            full_closure=full_closure,
            tessdata_snapshot=ocr_tessdata_snapshot,
            sequence=sequence,
            shared_deadline_monotonic_ns=shared_deadline_monotonic_ns,
            cancel_event=cancel_event,
            execution_slot=execution_slot,
        )
    if execution_slot is not None:
        raise OfflineEvidenceError("parent broker execution slot is unexpected")
    snapshot_path, snapshot_fd = _open_parent_worker_directory(
        worker_scratch,
        value["snapshot_relative"],
        "parent broker child snapshot",
    )
    child_scratch_path, child_scratch_fd = _open_parent_worker_directory(
        worker_scratch,
        value["scratch_relative"],
        "parent broker child scratch",
    )
    denial_path: Path | None = None
    denial_fd: int | None = None
    profile_scratch: _ComponentScratch | None = None
    held_profile: _HeldFile | None = None
    child_sandbox: dict[str, Any] | None = None
    process: subprocess.Popen[bytes] | None = None
    process_group_quiescent = False
    try:
        if snapshot_path == child_scratch_path:
            raise OfflineEvidenceError("parent broker child roots are not independent")
        kind = value["kind"]
        production_embedding_target: Path | None = None
        production_embedding_base_closure: _RuntimeSandboxClosure | None = None
        if kind == "test-component":
            expected_scope = value["test_scope"]
            if not isinstance(expected_scope, Mapping):
                raise OfflineEvidenceError("parent broker unittest scope is malformed")
            snapshot_identity = _test_scope_identity_from_fd(
                snapshot_fd,
                materialized=True,
                tree_roots=tuple(expected_scope.get("tree_roots", ())),
                exact_files=tuple(expected_scope.get("exact_files", ())),
            )
            if snapshot_identity != expected_scope:
                raise OfflineEvidenceError(
                    "parent broker unittest snapshot identity mismatch"
                )
            external_tools = full_external_tools
            if production_embedding_probe:
                if value["component"] != _PRODUCTION_EMBEDDING_PROBE_ID:
                    raise OfflineEvidenceError(
                        "parent broker production embedding component is not exact"
                    )
                assert production_embedding_fixture is not None
                production_embedding_target = (
                    child_scratch_path / _PRODUCTION_EMBEDDING_TARGET_RELATIVE
                )
                external_tools = _empty_external_tool_set()
                production_embedding_base_closure = _runtime_sandbox_closure(
                    python=python,
                    python_identity=python_identity,
                    external_tools=external_tools,
                )
                closure = _production_embedding_probe_closure(
                    production_embedding_base_closure,
                    production_embedding_fixture,
                    target_executable=production_embedding_target,
                )
            else:
                closure = full_closure
        elif kind == "disclosure":
            snapshot_identity = _test_scope_identity_from_fd(
                snapshot_fd,
                materialized=True,
                tree_roots=(),
                exact_files=_DISCLOSURE_SNAPSHOT_FILES,
            )
            if snapshot_identity != value["snapshot_identity"]:
                raise OfflineEvidenceError(
                    "parent broker disclosure snapshot identity mismatch"
                )
            external_tools = _empty_external_tool_set()
            closure = _runtime_sandbox_closure(
                python=python,
                python_identity=python_identity,
                external_tools=external_tools,
            )
        else:
            snapshot_identity = _test_scope_identity_from_fd(
                snapshot_fd,
                materialized=True,
                tree_roots=("deploy",),
                exact_files=(),
            )
            external_tools = _empty_external_tool_set()
            closure = _runtime_sandbox_closure(
                python=python,
                python_identity=python_identity,
                external_tools=external_tools,
            )

        def revalidate_operation_runtime() -> None:
            base_closure = production_embedding_base_closure or closure
            _revalidate_runtime_sandbox_closure(
                base_closure.identity,
                python=python,
                python_identity=python_identity,
                external_tools=external_tools,
            )
            if production_embedding_fixture is not None:
                assert production_embedding_base_closure is not None
                _revalidate_production_embedding_probe_closure(
                    closure,
                    production_embedding_base_closure,
                    production_embedding_fixture,
                    target_executable=production_embedding_target,
                )

        revalidate_operation_runtime()
        profile_payload = _child_sandbox_profile(
            snapshot_path,
            child_scratch_path,
            closure,
        ).encode("utf-8")
        if (
            len(profile_payload) != value["supplied_profile_size"]
            or hashlib.sha256(profile_payload).hexdigest()
            != value["supplied_profile_sha256"]
        ):
            raise OfflineEvidenceError(
                "parent broker supplied profile differs from the fixed profile"
            )
        profile_scratch = _create_component_scratch(
            f"broker-{probe_id}-{operation_id}"
        )
        held_profile = _stage_child_sandbox_profile(profile_scratch, profile)

        environment: dict[str, str]
        if kind in {"disclosure", "test-component"}:
            denial_path, denial_fd = _open_parent_worker_directory(
                worker_scratch,
                value["denial_probe_relative"],
                "parent broker denial probe",
            )
            denied_payload = _stable_relative_file_bytes(
                denial_fd,
                "read-probe",
                "parent broker denied-read probe",
                max_bytes=1024,
            )
            if denied_payload != b"must-not-be-readable-by-component\n":
                raise OfflineEvidenceError("parent broker denial probe changed")
            child_sandbox = _child_sandbox_binding_for_paths(
                profile=profile,
                snapshot_path=snapshot_path,
                snapshot_identity=snapshot_identity,
                scratch_path=child_scratch_path,
                denial_probe_path=denial_path,
                closure=closure,
            )
            sandbox_context = _component_sandbox_context(
                child_sandbox,
                types.SimpleNamespace(path=denial_path),
            )
            encoded_context = _encode_expected_identity(sandbox_context)
        if kind == "disclosure":
            encoded_closure = _encoded_module_closure_manifest(
                snapshot_fd,
                schema_version="cloud-v2-child-bootstrap-closure-v1",
                field="broker disclosure child module",
            )
            command = [
                str(NETWORK_SANDBOX_PATH),
                "-f",
                _held_sandbox_profile_argument(held_profile),
                str(python),
                "-I",
                "-S",
                "-B",
                "-c",
                _DISCLOSURE_SUBPROCESS_BOOTSTRAP,
                encoded_closure,
                value["action"],
                str(child_scratch_path / "disclosure-evidence.json"),
                value["created_at"],
                _encode_expected_identity(python_identity),
                _encode_expected_identity(snapshot_identity),
                encoded_context,
            ]
            environment = {
                "PATH": str(python.parent),
                "TMPDIR": str(child_scratch_path),
                "TMP": str(child_scratch_path),
                "TEMP": str(child_scratch_path),
                "HOME": str(child_scratch_path),
                "LC_ALL": "C.UTF-8",
                "LANG": "C.UTF-8",
                _INHERITED_COMPONENT_SANDBOX_ENV: child_sandbox["identity_sha256"],
            }
            stderr_target: Any = subprocess.STDOUT
        elif kind == "test-component":
            encoded_closure = _encoded_module_closure_manifest(
                snapshot_fd,
                schema_version="cloud-v2-child-bootstrap-closure-v1",
                field="broker unittest child module",
            )
            component = value["component"]
            command = [
                str(NETWORK_SANDBOX_PATH),
                "-f",
                _held_sandbox_profile_argument(held_profile),
                str(python),
                "-I",
                "-S",
                "-B",
                "-c",
                _UNITTEST_BOOTSTRAP,
                encoded_closure,
                component,
                value["start_directory"],
                _encode_expected_identity(python_identity),
                _encode_expected_identity(snapshot_identity),
                _encode_expected_identity(value["selection"]),
                _encode_expected_identity(value["baseline"]),
                encoded_context,
            ]
            environment = _expected_parent_broker_environment(
                parameters=value,
                scratch_path=child_scratch_path,
                python=python,
                full_external_tools=external_tools,
                child_sandbox_binding=child_sandbox,
                production_embedding_fixture=production_embedding_fixture,
            )
            stderr_target = subprocess.STDOUT
        else:
            constants = _process_isolation_constants(parent_snapshot.root_fd)
            role = value["role"]
            script = (
                constants["PUBLIC_CHILD"]
                if role == "public-app-agent"
                else constants["OPS_CHILD"]
            )
            encoded_script = base64.b64encode(
                __import__("textwrap").dedent(script).encode("utf-8")
            ).decode("ascii")
            bindings = _process_isolation_library_bindings()
            encoded_bindings = base64.b64encode(canonical_json_bytes(bindings)).decode(
                "ascii"
            )
            if (
                hashlib.sha256(
                    constants["PROCESS_CHILD_BOOTSTRAP"].encode("utf-8")
                ).hexdigest()
                != value["bootstrap_sha256"]
                or hashlib.sha256(encoded_script.encode("ascii")).hexdigest()
                != value["script_sha256"]
                or hashlib.sha256(encoded_bindings.encode("ascii")).hexdigest()
                != value["library_bindings_sha256"]
            ):
                raise OfflineEvidenceError(
                    "parent broker process-isolation command identity mismatch"
                )
            command = [
                str(NETWORK_SANDBOX_PATH),
                "-f",
                _held_sandbox_profile_argument(held_profile),
                str(python),
                "-I",
                "-S",
                "-B",
                "-c",
                constants["PROCESS_CHILD_BOOTSTRAP"],
                encoded_script,
                str(snapshot_path),
                encoded_bindings,
            ]
            environment = {
                "PATH": str(python.parent),
                "PYTHONDONTWRITEBYTECODE": "1",
                "TMPDIR": str(child_scratch_path),
                "TMP": str(child_scratch_path),
                "TEMP": str(child_scratch_path),
                "HOME": str(child_scratch_path),
                "LC_ALL": "C.UTF-8",
                "LANG": "C.UTF-8",
                "KG_PROCESS_ROLE": role,
                "KG_PROCESS_MARKER": value["marker"],
            }
            if role == "public-app-agent":
                environment["KG_PUBLIC_ALLOWED_HOSTS"] = "localhost"
            stderr_target = subprocess.PIPE

        _revalidate_directory_path(snapshot_path, snapshot_fd, "broker child snapshot")
        _revalidate_directory_path(
            child_scratch_path, child_scratch_fd, "broker child scratch"
        )
        revalidate_operation_runtime()
        _revalidate_held_sandbox_profile(held_profile, profile)
        deadline = time.monotonic() + value["timeout_seconds"]
        process = subprocess.Popen(
            command,
            cwd=None,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_target,
            preexec_fn=partial(os.fchdir, snapshot_fd),
            pass_fds=(snapshot_fd,),
            close_fds=True,
            start_new_session=True,
        )
        child_process_identity = _observed_new_session_process_identity(
            process,
            "parent broker child",
        )
        try:
            _write_sandbox_profile_pipe(
                process,
                held_profile.payload,
                command=command,
                field="parent broker child",
                timeout=value["timeout_seconds"],
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, value["timeout_seconds"])
            stdout, stderr = _read_bounded_process_output(
                process,
                command=command,
                field="parent broker child",
                timeout=remaining,
                stdout_max_bytes=_BROKER_STDOUT_MAX_BYTES,
                stderr_max_bytes=(
                    None
                    if stderr_target == subprocess.STDOUT
                    else _BROKER_STDERR_MAX_BYTES
                ),
                total_max_bytes=_BROKER_TOTAL_OUTPUT_MAX_BYTES,
            )
        except subprocess.TimeoutExpired as exc:
            _terminate_brokered_process(process)
            process_group_quiescent = True
            raise OfflineEvidenceError("parent broker child timed out") from exc
        process_group_quiescent = True
        _revalidate_held_sandbox_profile(held_profile, profile)
        stdout, stderr = _validated_parent_broker_output(
            stdout,
            stderr,
            field="parent broker child",
        )
        network_evidence = _broker_child_network_evidence(
            kind=kind,
            stdout=stdout,
            returncode=process.returncode,
        )
        target_executable_identity = (
            _production_embedding_target_identity_after_child(
                production_embedding_target,
                returncode=process.returncode,
                python_identity=python_identity,
            )
        )
        _revalidate_directory_path(snapshot_path, snapshot_fd, "broker child snapshot")
        _revalidate_directory_path(
            child_scratch_path, child_scratch_fd, "broker child scratch"
        )
        revalidate_operation_runtime()
        observed_normalized_command = {
            "kind": kind,
            "operation_id": operation_id,
            "sandbox": "sandbox-exec-held-profile-stdin",
            "python_flags": ["-I", "-S", "-B", "-c"],
            "bootstrap_sha256": hashlib.sha256(command[8].encode("utf-8")).hexdigest(),
            "argument_count": len(command),
        }
        normalized_command = _parent_broker_normalized_command(
            value,
            operation_id=operation_id,
        )
        if not _type_sensitive_equal(observed_normalized_command, normalized_command):
            raise OfflineEvidenceError("parent broker command identity mismatch")
        completed = subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
        operation_record: dict[str, Any] = {
            "sequence": -1,
            "operation_id": operation_id,
            "parameters_sha256": _identity_sha256(value),
            "normalized_command": normalized_command,
            "normalized_command_sha256": _identity_sha256(normalized_command),
            "profile_base64": base64.b64encode(profile.encode("utf-8")).decode(
                "ascii"
            ),
            "profile_sha256": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
            "stdin_role": "sandbox-profile-pipe",
            "stdin_profile_size": len(profile.encode("utf-8")),
            "stdin_profile_sha256": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
            "runtime_closure_identity": dict(closure.identity),
            "runtime_closure_identity_sha256": closure.identity["identity_sha256"],
            "snapshot_identity": dict(snapshot_identity),
            "snapshot_identity_sha256": snapshot_identity["identity_sha256"],
            "environment": dict(environment),
            "environment_sha256": _identity_sha256(environment),
            "snapshot_path": str(snapshot_path),
            "scratch_path": str(child_scratch_path),
            "denial_probe_path": None if denial_path is None else str(denial_path),
            "child_sandbox_binding": child_sandbox,
            "target_executable_identity": target_executable_identity,
            "pass_fd_roles": ["snapshot-root"],
            "process_identity": child_process_identity,
            "returncode": process.returncode,
            "stdout_size": len(stdout),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_size": 0 if stderr is None else len(stderr),
            "stderr_sha256": hashlib.sha256(stderr or b"").hexdigest(),
            "text_mode": False,
            "network_enforcement": network_evidence,
            "direct_child_waited": True,
            "process_group_quiescence_verified": True,
            "timeout_cleanup_contract": (
                "new-session-process-group-quiescence-or-killpg-and-wait"
            ),
        }
        return completed, operation_record
    finally:
        primary_error = sys.exception()
        cleanup_error: Exception | None = None
        if process is not None and not process_group_quiescent:
            try:
                _terminate_brokered_process(process)
            except Exception as exc:
                cleanup_error = exc
        if held_profile is not None:
            try:
                _close_held_file(held_profile)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="parent broker held profile",
                )
        try:
            if profile_scratch is not None:
                profile_receipt = _close_component_scratch(profile_scratch)
                if "operation_record" in locals():
                    operation_record["profile_scratch"] = profile_receipt
                    operation_record["identity_sha256"] = _identity_sha256(
                        operation_record
                    )
        except Exception as exc:
            if cleanup_error is None:
                cleanup_error = exc
        for descriptor in (denial_fd, child_scratch_fd, snapshot_fd):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except OSError:
                if cleanup_error is None:
                    cleanup_error = OfflineEvidenceError(
                        "parent broker child descriptor cleanup failed"
                    )
        _finish_process_cleanup(
            cleanup_error,
            primary_error=primary_error,
        )


def _ocr_native_summary(
    operations: Sequence[Mapping[str, Any]],
    *,
    sealed_tessdata_snapshot_identity_sha256: str,
    shared_deadline_monotonic_ns: int,
) -> dict[str, Any]:
    if (
        len(operations) != 11
        or not isinstance(sealed_tessdata_snapshot_identity_sha256, str)
        or not _SHA256.fullmatch(sealed_tessdata_snapshot_identity_sha256)
        or type(shared_deadline_monotonic_ns) is not int
        or shared_deadline_monotonic_ns <= 0
        or operations[0].get("operation_id") != "ocr-native-pdftoppm"
        or any(
            operation.get("operation_id") != "ocr-native-tesseract"
            for operation in operations[1:]
        )
    ):
        raise OfflineEvidenceError("parent broker OCR operation set is not exact")
    fixed_anchors = _validated_ocr_fixed_fixture_anchors()
    render_sequence = operations[0].get("sequence")
    render_slot = operations[0].get("execution_slot")
    render_timing = _validated_ocr_process_timing(
        operations[0].get("process_timing"),
        shared_deadline_monotonic_ns=shared_deadline_monotonic_ns,
        timeout_seconds=900.0,
    )
    if (
        type(render_sequence) is not int
        or render_sequence != 0
        or not _type_sensitive_equal(render_slot, _ocr_native_execution_slot(0))
    ):
        raise OfflineEvidenceError("parent broker OCR render execution slot is malformed")
    rendered = operations[0].get("output_identity")
    if (
        not isinstance(rendered, Mapping)
        or rendered.get("schema_version")
        != "cloud-v2-parent-broker-rendered-pages-v1"
        or type(rendered.get("page_count")) is not int
        or rendered.get("page_count") != 10
        or not _type_sensitive_equal(
            rendered.get("page_numbers"), list(range(1, 11))
        )
        or not isinstance(rendered.get("files"), list)
        or len(rendered["files"]) != 10
        or rendered.get("file_set_sha256")
        != _identity_sha256(rendered["files"])
        or rendered.get("identity_sha256")
        != _identity_sha256(
            {key: item for key, item in rendered.items() if key != "identity_sha256"}
        )
    ):
        raise OfflineEvidenceError("parent broker OCR rendered page identity is malformed")
    rendered_by_page: dict[int, Mapping[str, Any]] = {}
    for expected_page, record in enumerate(rendered["files"], 1):
        fixed_record = fixed_anchors["rendered_pages"][expected_page - 1]
        if (
            not isinstance(record, Mapping)
            or set(record) != {"page_number", "name", "mode", "size", "sha256"}
            or type(record.get("page_number")) is not int
            or record.get("page_number") != expected_page
            or record.get("name") != f"page-{expected_page:02d}.jpg"
            or type(record.get("mode")) is not int
            or type(record.get("size")) is not int
            or record["size"] <= 0
            or not isinstance(record.get("sha256"), str)
            or not _SHA256.fullmatch(record["sha256"])
            or not _type_sensitive_equal(
                {field: record[field] for field in fixed_record},
                fixed_record,
            )
        ):
            raise OfflineEvidenceError(
                "parent broker OCR rendered page identity is malformed"
            )
        rendered_by_page[expected_page] = record

    page_bindings: list[dict[str, Any]] = []
    tesseract_runtime_identities: set[str] = set()
    private_tessdata_identities: set[str] = set()
    observed_pages: set[int] = set()
    timing_records: list[dict[str, Any]] = []
    for operation in operations[1:]:
        output = operation.get("output_identity")
        page_identity = operation.get("page_identity")
        tessdata_identity = operation.get("private_tessdata_identity")
        runtime_identity = operation.get("native_runtime_identity")
        if not all(
            isinstance(item, Mapping)
            for item in (output, page_identity, tessdata_identity, runtime_identity)
        ):
            raise OfflineEvidenceError("parent broker OCR page binding is malformed")
        page_number = output.get("page_number")
        if type(page_number) is not int or page_number not in range(1, 11):
            raise OfflineEvidenceError("parent broker OCR page binding is malformed")
        if page_number in observed_pages:
            raise OfflineEvidenceError("parent broker OCR page binding is duplicated")
        observed_pages.add(page_number)
        rendered_record = rendered_by_page[page_number]
        operation_sequence = operation.get("sequence")
        if type(operation_sequence) is not int or operation_sequence not in range(1, 11):
            raise OfflineEvidenceError("parent broker OCR page binding is malformed")
        execution_slot = operation.get("execution_slot")
        expected_slot = _ocr_native_execution_slot(operation_sequence)
        timing = _validated_ocr_process_timing(
            operation.get("process_timing"),
            shared_deadline_monotonic_ns=shared_deadline_monotonic_ns,
            timeout_seconds=120.0,
        )
        fixed_stdout = fixed_anchors["stdout"][page_number - 1]
        output_core = {
            key: item for key, item in output.items() if key != "identity_sha256"
        }
        if (
            output.get("schema_version")
            != "cloud-v2-parent-broker-ocr-stdout-v1"
            or set(output)
            != {
                "schema_version",
                "page_number",
                "size",
                "sha256",
                "identity_sha256",
            }
            or type(output.get("size")) is not int
            or output["size"] <= 0
            or output.get("sha256") != operation.get("stdout_sha256")
            or output.get("identity_sha256") != _identity_sha256(output_core)
            or page_identity.get("sha256") != rendered_record["sha256"]
            or page_identity.get("size") != rendered_record["size"]
            or not _type_sensitive_equal(
                {field: output[field] for field in fixed_stdout},
                fixed_stdout,
            )
            or not _type_sensitive_equal(execution_slot, expected_slot)
            or operation.get("sealed_tessdata_snapshot_identity_sha256")
            != sealed_tessdata_snapshot_identity_sha256
            or tessdata_identity.get("sealed_snapshot_identity_sha256")
            != sealed_tessdata_snapshot_identity_sha256
        ):
            raise OfflineEvidenceError("parent broker OCR page binding is malformed")
        runtime_identity_sha256 = runtime_identity.get("identity_sha256")
        private_tessdata_identity_sha256 = tessdata_identity.get("identity_sha256")
        if (
            not isinstance(runtime_identity_sha256, str)
            or not _SHA256.fullmatch(runtime_identity_sha256)
            or not isinstance(private_tessdata_identity_sha256, str)
            or not _SHA256.fullmatch(private_tessdata_identity_sha256)
        ):
            raise OfflineEvidenceError("parent broker OCR page binding is malformed")
        tesseract_runtime_identities.add(runtime_identity_sha256)
        private_tessdata_identities.add(private_tessdata_identity_sha256)
        page_bindings.append(
            {
                "page_number": page_number,
                "operation_sequence": operation_sequence,
                "batch_index": expected_slot["batch_index"],
                "slot_index": expected_slot["slot_index"],
                "rendered_page_sha256": rendered_record["sha256"],
                "approved_page_identity_sha256": _identity_sha256(page_identity),
                "stdout_sha256": operation["stdout_sha256"],
                "output_identity_sha256": output["identity_sha256"],
                "process_timing_identity_sha256": timing["identity_sha256"],
                "execution_slot_identity_sha256": expected_slot["identity_sha256"],
            }
        )
        timing_records.append(
            {
                "operation_sequence": operation_sequence,
                "page_number": page_number,
                "batch_index": expected_slot["batch_index"],
                "slot_index": expected_slot["slot_index"],
                "started_monotonic_ns": timing["started_monotonic_ns"],
                "ended_monotonic_ns": timing["ended_monotonic_ns"],
                "duration_ns": timing["duration_ns"],
                "process_timing_identity_sha256": timing["identity_sha256"],
                "execution_slot_identity_sha256": expected_slot["identity_sha256"],
            }
        )
    page_bindings.sort(key=lambda item: item["page_number"])
    timing_records.sort(key=lambda item: item["operation_sequence"])
    if (
        observed_pages != set(range(1, 11))
        or len(tesseract_runtime_identities) != 1
        or len(private_tessdata_identities) != 1
        or any(
            type(binding["operation_sequence"]) is not int
            or binding["operation_sequence"] not in range(1, 11)
            for binding in page_bindings
        )
        or {binding["operation_sequence"] for binding in page_bindings}
        != set(range(1, 11))
    ):
        raise OfflineEvidenceError("parent broker OCR page set is not exact")

    batch_records: list[dict[str, Any]] = []
    previous_batch_end: int | None = None
    consumed = 1
    for batch_index, batch_size in enumerate(_OCR_NATIVE_BATCH_SIZES, 1):
        expected_sequences = list(range(consumed, consumed + batch_size))
        records = [
            record for record in timing_records if record["batch_index"] == batch_index
        ]
        if (
            [record["operation_sequence"] for record in records] != expected_sequences
            or [record["slot_index"] for record in records] != list(range(batch_size))
        ):
            raise OfflineEvidenceError("parent broker OCR batch identity is malformed")
        overlap_start = max(record["started_monotonic_ns"] for record in records)
        overlap_end = min(record["ended_monotonic_ns"] for record in records)
        batch_start = min(record["started_monotonic_ns"] for record in records)
        batch_end = max(record["ended_monotonic_ns"] for record in records)
        if (
            overlap_start >= overlap_end
            or (previous_batch_end is not None and previous_batch_end > batch_start)
        ):
            raise OfflineEvidenceError(
                "parent broker OCR batches do not prove the fixed concurrency plan"
            )
        batch_core: dict[str, Any] = {
            "batch_index": batch_index,
            "batch_size": batch_size,
            "worker_limit": _OCR_NATIVE_WORKER_LIMIT,
            "operation_sequences": expected_sequences,
            "page_numbers": [record["page_number"] for record in records],
            "slot_indexes": list(range(batch_size)),
            "started_monotonic_ns": batch_start,
            "ended_monotonic_ns": batch_end,
            "common_overlap_started_monotonic_ns": overlap_start,
            "common_overlap_ended_monotonic_ns": overlap_end,
            "common_overlap_duration_ns": overlap_end - overlap_start,
            "process_timing_identity_sha256s": [
                record["process_timing_identity_sha256"] for record in records
            ],
        }
        batch_records.append(
            {**batch_core, "identity_sha256": _identity_sha256(batch_core)}
        )
        previous_batch_end = batch_end
        consumed += batch_size
    if consumed != 11:
        raise OfflineEvidenceError("parent broker OCR batch identity is malformed")
    if render_timing["ended_monotonic_ns"] > batch_records[0]["started_monotonic_ns"]:
        raise OfflineEvidenceError("parent broker OCR render and Tesseract phases overlap")

    events = sorted(
        (
            event
            for record in timing_records
            for event in (
                (record["started_monotonic_ns"], 1),
                (record["ended_monotonic_ns"], -1),
            )
        ),
        key=lambda event: (event[0], event[1]),
    )
    active = 0
    maximum_overlap = 0
    for _timestamp, delta in events:
        active += delta
        if active < 0:
            raise OfflineEvidenceError("parent broker OCR timing intervals are malformed")
        maximum_overlap = max(maximum_overlap, active)
    if active != 0 or maximum_overlap != _OCR_NATIVE_WORKER_LIMIT:
        raise OfflineEvidenceError(
            "parent broker OCR timing does not prove four-worker execution"
        )

    pdftoppm_runtime = operations[0].get("native_runtime_identity")
    if not isinstance(pdftoppm_runtime, Mapping):
        raise OfflineEvidenceError("parent broker OCR render runtime identity is malformed")
    core: dict[str, Any] = {
        "schema_version": "cloud-v2-parent-broker-ocr-native-summary-v2",
        "operation_count": 11,
        "pdftoppm_sequence": 0,
        "tesseract_operation_count": 10,
        "worker_limit": _OCR_NATIVE_WORKER_LIMIT,
        "batch_sizes": list(_OCR_NATIVE_BATCH_SIZES),
        "maximum_global_overlap": maximum_overlap,
        "shared_deadline_monotonic_ns": shared_deadline_monotonic_ns,
        "page_numbers": list(range(1, 11)),
        "fixed_fixture_identity_sha256": _identity_sha256(fixed_anchors),
        "sealed_tessdata_snapshot_identity_sha256": (
            sealed_tessdata_snapshot_identity_sha256
        ),
        "pdftoppm_native_runtime_identity_sha256": pdftoppm_runtime.get(
            "identity_sha256"
        ),
        "render_process_timing_identity_sha256": render_timing["identity_sha256"],
        "render_execution_slot_identity_sha256": render_slot["identity_sha256"],
        "rendered_page_set_identity_sha256": rendered["identity_sha256"],
        "rendered_page_file_set_sha256": rendered["file_set_sha256"],
        "tesseract_native_runtime_identity_sha256": next(
            iter(tesseract_runtime_identities)
        ),
        "private_tessdata_identity_sha256": next(
            iter(private_tessdata_identities)
        ),
        "page_bindings": page_bindings,
        "page_bindings_sha256": _identity_sha256(page_bindings),
        "tesseract_timing_records": timing_records,
        "tesseract_timing_records_sha256": _identity_sha256(timing_records),
        "batch_records": batch_records,
        "batch_records_sha256": _identity_sha256(batch_records),
    }
    core["identity_sha256"] = _identity_sha256(core)
    return core


def _serve_parent_broker(
    *,
    request_fd: int,
    response_fd: int,
    session: str,
    probe_id: str,
    worker_scratch: _ComponentScratch,
    parent_snapshot: _PrivateSnapshot,
    python: Path,
    python_identity: Mapping[str, Any],
    full_external_tools: _ExternalToolSet,
    full_closure: _RuntimeSandboxClosure,
    production_embedding_fixture: _ProductionEmbeddingFixture | None = None,
    ocr_tessdata_snapshot: _SealedTessdataSnapshot | None = None,
    deadline: float,
    deadline_monotonic_ns: int | None = None,
) -> dict[str, Any]:
    plan = _parent_broker_plan(probe_id)
    if deadline_monotonic_ns is None:
        deadline_monotonic_ns = int(deadline * 1_000_000_000)
    if (
        type(deadline_monotonic_ns) is not int
        or deadline_monotonic_ns <= time.monotonic_ns()
        or abs(int(deadline * 1_000_000_000) - deadline_monotonic_ns) > 1
    ):
        raise OfflineEvidenceError("parent broker protocol timed out")
    deadline = deadline_monotonic_ns / 1_000_000_000
    broker_process_identity = _current_process_identity(require_session_leader=False)
    operations: list[dict[str, Any]] = []
    exchange_hashes: list[dict[str, str]] = []
    chain_sha256 = hashlib.sha256(session.encode("ascii")).hexdigest()
    cancel_event = threading.Event()

    def read_request(
        sequence: int,
        expected_operation: str,
    ) -> tuple[bytes, Mapping[str, Any], str]:
        payload = _read_broker_frame(request_fd, deadline=deadline)
        if payload is None:
            raise OfflineEvidenceError("parent broker request is missing")
        try:
            request = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineEvidenceError("parent broker request is malformed") from exc
        fields = {
            "schema_version",
            "session",
            "sequence",
            "probe_id",
            "operation_id",
            "parameters",
            "parameters_sha256",
        }
        if (
            not isinstance(request, Mapping)
            or set(request) != fields
            or payload != canonical_json_bytes(request)
            or request["schema_version"] != PARENT_BROKER_PROTOCOL_SCHEMA_VERSION
            or request["session"] != session
            or type(request["sequence"]) is not int
            or request["sequence"] != sequence
            or request["probe_id"] != probe_id
            or request["operation_id"] != expected_operation
            or request["parameters_sha256"]
            != _identity_sha256(request["parameters"])
        ):
            raise OfflineEvidenceError("parent broker request identity mismatch")
        request_sha256 = hashlib.sha256(payload).hexdigest()
        return payload, request, request_sha256

    def execute_request(
        sequence: int,
        expected_operation: str,
        request: Mapping[str, Any],
        execution_slot: Mapping[str, Any] | None,
    ) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
        if cancel_event.is_set():
            raise OfflineEvidenceError("parent broker OCR batch was cancelled")
        completed, operation = _execute_parent_broker_operation(
            probe_id=probe_id,
            sequence=sequence,
            operation_id=expected_operation,
            parameters=request["parameters"],
            worker_scratch=worker_scratch,
            parent_snapshot=parent_snapshot,
            python=python,
            python_identity=python_identity,
            full_external_tools=full_external_tools,
            full_closure=full_closure,
            production_embedding_fixture=production_embedding_fixture,
            ocr_tessdata_snapshot=ocr_tessdata_snapshot,
            shared_deadline_monotonic_ns=deadline_monotonic_ns,
            cancel_event=cancel_event,
            execution_slot=execution_slot,
        )
        return completed, operation

    def emit_response(
        sequence: int,
        expected_operation: str,
        payload: bytes,
        request_sha256: str,
        completed: subprocess.CompletedProcess[bytes],
        operation: dict[str, Any],
    ) -> None:
        nonlocal chain_sha256
        stdout = completed.stdout
        stderr = completed.stderr
        response = {
            "schema_version": PARENT_BROKER_PROTOCOL_SCHEMA_VERSION,
            "session": session,
            "sequence": sequence,
            "probe_id": probe_id,
            "operation_id": expected_operation,
            "process_identity": operation["process_identity"],
            "request_sha256": request_sha256,
            "status": "completed",
            "returncode": completed.returncode,
            "stdout_base64": base64.b64encode(stdout).decode("ascii"),
            "stderr_base64": (
                None if stderr is None else base64.b64encode(stderr).decode("ascii")
            ),
            "text_mode": operation["text_mode"],
            "timed_out": False,
            "process_timing": operation.get("process_timing"),
            "execution_slot": operation.get("execution_slot"),
        }
        response_payload = _canonical_parent_broker_response_payload(response)
        response_sha256 = hashlib.sha256(response_payload).hexdigest()
        _write_broker_frame(response_fd, response_payload, deadline=deadline)
        operation["sequence"] = sequence
        operation["request_base64"] = base64.b64encode(payload).decode("ascii")
        operation["response_base64"] = base64.b64encode(response_payload).decode(
            "ascii"
        )
        operation["request_sha256"] = request_sha256
        operation["response_sha256"] = response_sha256
        operation["identity_sha256"] = _identity_sha256(
            {key: item for key, item in operation.items() if key != "identity_sha256"}
        )
        operations.append(operation)
        exchange_hashes.append(
            {
                "request_sha256": request_sha256,
                "response_sha256": response_sha256,
            }
        )
        chain_sha256 = _identity_sha256(
            [chain_sha256, request_sha256, response_sha256]
        )

    try:
        if not _is_ocr_native_probe(probe_id):
            for sequence, expected_operation in enumerate(plan):
                payload, request, request_sha256 = read_request(
                    sequence,
                    expected_operation,
                )
                completed, operation = execute_request(
                    sequence,
                    expected_operation,
                    request,
                    None,
                )
                emit_response(
                    sequence,
                    expected_operation,
                    payload,
                    request_sha256,
                    completed,
                    operation,
                )
        else:
            if (
                _is_ocr_tessdata_probe(probe_id)
                != (ocr_tessdata_snapshot is not None)
                or plan[0] != "ocr-native-pdftoppm"
            ):
                raise OfflineEvidenceError("parent broker OCR scope is not exact")
            payload, request, request_sha256 = read_request(0, plan[0])
            completed, operation = execute_request(
                0,
                plan[0],
                request,
                _ocr_native_execution_slot(0),
            )
            emit_response(
                0,
                plan[0],
                payload,
                request_sha256,
                completed,
                operation,
            )

            next_sequence = 1
            if _is_ocr_tessdata_probe(probe_id):
                with ThreadPoolExecutor(
                    max_workers=_OCR_NATIVE_WORKER_LIMIT,
                    thread_name_prefix="kg-ocr-native",
                ) as executor:
                    for batch_size in _OCR_NATIVE_BATCH_SIZES:
                        batch_requests: list[
                            tuple[int, str, bytes, Mapping[str, Any], str]
                        ] = []
                        for sequence in range(
                            next_sequence,
                            next_sequence + batch_size,
                        ):
                            expected_operation = plan[sequence]
                            payload, request, request_sha256 = read_request(
                                sequence,
                                expected_operation,
                            )
                            batch_requests.append(
                                (
                                    sequence,
                                    expected_operation,
                                    payload,
                                    request,
                                    request_sha256,
                                )
                            )
                        futures = [
                            executor.submit(
                                execute_request,
                                sequence,
                                expected_operation,
                                request,
                                _ocr_native_execution_slot(sequence),
                            )
                            for (
                                sequence,
                                expected_operation,
                                _payload,
                                request,
                                _request_sha256,
                            ) in batch_requests
                        ]
                        _done, pending = wait(
                            futures,
                            return_when=FIRST_EXCEPTION,
                        )
                        failures = [
                            future.exception()
                            for future in futures
                            if future.done() and not future.cancelled()
                        ]
                        first_failure = next(
                            (
                                failure
                                for failure in failures
                                if failure is not None
                            ),
                            None,
                        )
                        if first_failure is not None:
                            cancel_event.set()
                            for future in pending:
                                future.cancel()
                            wait(futures)
                            raise first_failure
                        results = [future.result() for future in futures]
                        for request_record, result in zip(
                            batch_requests,
                            results,
                            strict=True,
                        ):
                            (
                                sequence,
                                expected_operation,
                                payload,
                                _request,
                                request_sha256,
                            ) = request_record
                            completed, operation = result
                            emit_response(
                                sequence,
                                expected_operation,
                                payload,
                                request_sha256,
                                completed,
                                operation,
                            )
                        next_sequence += batch_size
            if next_sequence != len(plan):
                raise OfflineEvidenceError("parent broker OCR batch plan is incomplete")
    except BaseException:
        cancel_event.set()
        raise
    extra = _read_broker_frame(request_fd, deadline=deadline, allow_eof=True)
    if extra is not None:
        raise OfflineEvidenceError("parent broker received an extra request")
    transcript: dict[str, Any] = {
        "schema_version": PARENT_BROKER_TRANSCRIPT_SCHEMA_VERSION,
        "protocol_schema_version": PARENT_BROKER_PROTOCOL_SCHEMA_VERSION,
        "session": session,
        "probe_id": probe_id,
        "deadline_monotonic_ns": deadline_monotonic_ns,
        "broker_process_identity": broker_process_identity,
        "broker_network_assurance": (
            "held-byte-fixed-command-broker-no-provider-data-plane"
        ),
        "broker_os_network_enforced": False,
        "expected_operation_count": len(plan),
        "accepted_operation_count": len(operations),
        "rejected_operation_count": 0,
        "operation_ids": list(plan),
        "operation_ids_sha256": _identity_sha256(plan),
        "exchange_hashes": exchange_hashes,
        "exchange_chain_sha256": chain_sha256,
        "operations": operations,
    }
    if _is_ocr_tessdata_probe(probe_id):
        assert ocr_tessdata_snapshot is not None
        transcript["ocr_native_summary"] = _ocr_native_summary(
            operations,
            sealed_tessdata_snapshot_identity_sha256=(
                ocr_tessdata_snapshot.identity["identity_sha256"]
            ),
            shared_deadline_monotonic_ns=deadline_monotonic_ns,
        )
    transcript["identity_sha256"] = _identity_sha256(transcript)
    return transcript


def _terminate_brokered_process(process: subprocess.Popen[Any]) -> None:
    pid = process.pid
    if type(pid) is not int or pid <= 0:
        raise OfflineEvidenceError("brokered process identity is unavailable")
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise OfflineEvidenceError("brokered process group could not be killed") from exc
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OfflineEvidenceError("brokered process leader could not be reaped") from exc

    deadline = time.monotonic() + 5.0
    while True:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        except OSError as exc:
            raise OfflineEvidenceError(
                "brokered process group could not be verified"
            ) from exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OfflineEvidenceError("brokered process group did not become quiescent")
        time.sleep(min(0.01, remaining))


def _finish_process_cleanup(
    cleanup_error: Exception | None,
    *,
    primary_error: BaseException | None,
) -> None:
    if cleanup_error is None:
        return
    if primary_error is None:
        raise cleanup_error
    primary_error.add_note(
        "secondary process cleanup failure: "
        f"{type(cleanup_error).__name__}: {cleanup_error}"
    )


def _read_bounded_process_output(
    process: subprocess.Popen[bytes],
    *,
    command: Sequence[str],
    field: str,
    timeout: float,
    stdout_max_bytes: int,
    stderr_max_bytes: int | None,
    total_max_bytes: int,
) -> tuple[bytes, bytes | None]:
    limits = (stdout_max_bytes, total_max_bytes)
    if any(type(limit) is not int or limit <= 0 for limit in limits) or (
        stderr_max_bytes is not None
        and (type(stderr_max_bytes) is not int or stderr_max_bytes <= 0)
    ):
        raise OfflineEvidenceError(f"{field} output limit is invalid")
    if process.stdout is None or (
        (stderr_max_bytes is None and process.stderr is not None)
        or (stderr_max_bytes is not None and process.stderr is None)
    ):
        raise OfflineEvidenceError(f"{field} output pipes are unavailable")

    stdout_payload = bytearray()
    stderr_payload: bytearray | None = (
        None if stderr_max_bytes is None else bytearray()
    )
    streams: dict[int, tuple[bytearray, int]] = {}
    try:
        streams[process.stdout.fileno()] = (stdout_payload, stdout_max_bytes)
        if process.stderr is not None and stderr_payload is not None:
            assert stderr_max_bytes is not None
            stderr_descriptor = process.stderr.fileno()
            if stderr_descriptor in streams:
                raise OfflineEvidenceError(f"{field} output pipes are not independent")
            streams[stderr_descriptor] = (stderr_payload, stderr_max_bytes)
        for descriptor in streams:
            os.set_blocking(descriptor, False)
    except (OSError, ValueError) as exc:
        raise OfflineEvidenceError(f"{field} output pipes are unavailable") from exc

    deadline = time.monotonic() + timeout
    total_bytes = 0
    while streams:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        readable, _writable, _exceptional = select.select(
            list(streams),
            [],
            [],
            remaining,
        )
        if not readable:
            raise subprocess.TimeoutExpired(command, timeout)
        for descriptor in readable:
            output, stream_max_bytes = streams[descriptor]
            read_size = min(
                64 * 1024,
                stream_max_bytes + 1 - len(output),
                total_max_bytes + 1 - total_bytes,
            )
            try:
                chunk = os.read(descriptor, max(1, read_size))
            except BlockingIOError:
                continue
            except OSError as exc:
                raise OfflineEvidenceError(
                    f"{field} output could not be read safely"
                ) from exc
            if not chunk:
                streams.pop(descriptor)
                continue
            output.extend(chunk)
            total_bytes += len(chunk)
            if len(output) > stream_max_bytes or total_bytes > total_max_bytes:
                raise OfflineEvidenceError(
                    f"{field} output exceeds the streaming size limit"
                )

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(command, timeout)
    process.wait(timeout=remaining)
    _require_brokered_process_group_quiescence(process, field=field)
    return bytes(stdout_payload), (
        None if stderr_payload is None else bytes(stderr_payload)
    )


def _write_sandbox_profile_pipe(
    process: subprocess.Popen[bytes],
    payload: bytes,
    *,
    command: Sequence[str],
    field: str,
    timeout: float,
) -> None:
    if (
        not isinstance(payload, bytes)
        or not payload
        or len(payload) > 2 * 1024 * 1024
        or isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise OfflineEvidenceError(f"{field} sandbox profile input is invalid")
    stream = process.stdin
    if not isinstance(stream, io.IOBase):
        raise OfflineEvidenceError(f"{field} sandbox profile pipe is unavailable")
    try:
        descriptor = stream.fileno()
    except (OSError, ValueError) as exc:
        raise OfflineEvidenceError(
            f"{field} sandbox profile pipe is unavailable"
        ) from exc
    if descriptor <= 2:
        raise OfflineEvidenceError(f"{field} sandbox profile pipe is invalid")
    deadline = time.monotonic() + float(timeout)
    offset = 0
    try:
        try:
            os.set_blocking(descriptor, False)
        except (OSError, ValueError) as exc:
            raise OfflineEvidenceError(
                f"{field} sandbox profile pipe could not be configured"
            ) from exc
        while offset < len(payload):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                _readable, writable, exceptional = select.select(
                    [], [descriptor], [descriptor], min(remaining, 0.25)
                )
            except (OSError, ValueError) as exc:
                raise OfflineEvidenceError(
                    f"{field} sandbox profile pipe could not be polled"
                ) from exc
            if exceptional:
                raise OfflineEvidenceError(
                    f"{field} sandbox profile pipe failed before completion"
                )
            if not writable:
                if process.poll() is not None:
                    raise OfflineEvidenceError(
                        f"{field} closed before reading the sandbox profile"
                    )
                continue
            try:
                written = os.write(descriptor, payload[offset:])
            except BlockingIOError:
                continue
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise OfflineEvidenceError(
                    f"{field} sandbox profile pipe write failed"
                ) from exc
            if written <= 0:
                raise OfflineEvidenceError(
                    f"{field} sandbox profile pipe write failed"
                )
            offset += written
    finally:
        primary_error = sys.exception()
        try:
            stream.close()
        except (OSError, ValueError) as exc:
            close_error = OfflineEvidenceError(
                f"{field} sandbox profile pipe could not be closed"
            )
            if primary_error is None:
                raise close_error from exc
            primary_error.add_note(
                f"secondary sandbox profile pipe close failure: {type(exc).__name__}"
            )


def _run_new_session_process(
    command: Sequence[str],
    *,
    field: str,
    cwd: str | Path | None,
    env: Mapping[str, str],
    stdin: Any,
    stdout: Any,
    stderr: Any,
    timeout: float,
    check: bool,
    preexec_fn: Any,
    pass_fds: tuple[int, ...],
    input_payload: bytes | None = None,
) -> Any:
    if check is not False:
        raise OfflineEvidenceError(f"{field} check mode is not allowlisted")
    if (
        (input_payload is None and stdin == subprocess.PIPE)
        or (input_payload is not None and stdin != subprocess.PIPE)
        or (
            input_payload is not None
            and (
                type(input_payload) is not bytes
                or not input_payload
                or len(input_payload) > 2 * 1024 * 1024
            )
        )
    ):
        raise OfflineEvidenceError(f"{field} sandbox profile pipe input is invalid")
    client = _PARENT_BROKER_CLIENT
    if isinstance(client, _ParentBrokerClient):
        broker_kwargs: dict[str, Any] = {
            "cwd": cwd,
            "env": dict(env),
            "stdout": stdout,
            "stderr": stderr,
            "timeout": timeout,
            "check": check,
            "preexec_fn": preexec_fn,
            "pass_fds": pass_fds,
        }
        if input_payload is None:
            broker_kwargs["stdin"] = stdin
        else:
            broker_kwargs["input"] = input_payload
        return client.run(command, **broker_kwargs)
    if client is not None:
        raise OfflineEvidenceError("parent broker client is invalid")
    process: subprocess.Popen[bytes] | None = None
    quiescent = False
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=dict(env),
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            preexec_fn=preexec_fn,
            pass_fds=pass_fds,
            close_fds=True,
            start_new_session=True,
        )
        process_identity = _observed_new_session_process_identity(
            process,
            field,
        )
        if input_payload is not None:
            _write_sandbox_profile_pipe(
                process,
                input_payload,
                command=command,
                field=field,
                timeout=timeout,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        captured_stdout, captured_stderr = _read_bounded_process_output(
            process,
            command=command,
            field=field,
            timeout=remaining,
            stdout_max_bytes=_BROKER_STDOUT_MAX_BYTES,
            stderr_max_bytes=(
                None if stderr == subprocess.STDOUT else _BROKER_STDERR_MAX_BYTES
            ),
            total_max_bytes=_BROKER_TOTAL_OUTPUT_MAX_BYTES,
        )
        quiescent = True
        return types.SimpleNamespace(
            args=command,
            returncode=process.returncode,
            stdout=captured_stdout,
            stderr=captured_stderr,
            process_identity=process_identity,
        )
    finally:
        primary_error = sys.exception()
        cleanup_error: Exception | None = None
        if process is not None and not quiescent:
            try:
                _terminate_brokered_process(process)
            except Exception as exc:
                cleanup_error = exc
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if isinstance(stream, io.IOBase):
                    try:
                        stream.close()
                    except OSError as exc:
                        if cleanup_error is None:
                            cleanup_error = exc
        _finish_process_cleanup(
            cleanup_error,
            primary_error=primary_error,
        )


def _run_bounded_new_session_process(
    command: Sequence[str],
    *,
    field: str,
    cwd: str | Path | None,
    env: Mapping[str, str],
    timeout: float,
    output_max_bytes: int,
) -> Any:
    """Run a formal child while bounding stdout and stderr during the read."""

    if type(output_max_bytes) is not int or output_max_bytes <= 0:
        raise OfflineEvidenceError(f"{field} output limit is invalid")
    process: subprocess.Popen[bytes] | None = None
    quiescent = False
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
        process_identity = _observed_new_session_process_identity(process, field)
        stdout_payload, stderr_payload = _read_bounded_process_output(
            process,
            command=command,
            field=field,
            timeout=timeout,
            stdout_max_bytes=output_max_bytes,
            stderr_max_bytes=output_max_bytes,
            total_max_bytes=output_max_bytes,
        )
        quiescent = True
        return types.SimpleNamespace(
            args=process.args,
            returncode=process.returncode,
            stdout=stdout_payload,
            stderr=stderr_payload,
            process_identity=process_identity,
        )
    finally:
        primary_error = sys.exception()
        cleanup_error: Exception | None = None
        if process is not None and not quiescent:
            try:
                _terminate_brokered_process(process)
            except Exception as exc:
                cleanup_error = exc
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if isinstance(stream, io.IOBase):
                    try:
                        stream.close()
                    except OSError as exc:
                        if cleanup_error is None:
                            cleanup_error = exc
        _finish_process_cleanup(cleanup_error, primary_error=primary_error)


def _run_test_component_process(
    command: Sequence[str],
    *,
    cwd: str | Path | None,
    env: Mapping[str, str],
    stdin: Any,
    stdout: Any,
    stderr: Any,
    timeout: float,
    check: bool,
    preexec_fn: Any,
    pass_fds: tuple[int, ...],
    input_payload: bytes | None = None,
) -> Any:
    return _run_new_session_process(
        command,
        field="test component",
        cwd=cwd,
        env=env,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        timeout=timeout,
        check=check,
        preexec_fn=preexec_fn,
        pass_fds=pass_fds,
        input_payload=input_payload,
    )

def _require_brokered_process_group_quiescence(
    process: subprocess.Popen[Any],
    *,
    field: str,
) -> None:
    if type(process.returncode) is not int:
        raise OfflineEvidenceError(f"{field} was not waited")
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return
    except OSError as exc:
        raise OfflineEvidenceError(
            f"{field} process group could not be verified"
        ) from exc
    _terminate_brokered_process(process)
    raise OfflineEvidenceError(f"{field} left a live descendant process")


def _bounded_parent_worker_error(payload: bytes) -> str | None:
    if (
        not isinstance(payload, bytes)
        or len(payload) > _PARENT_WORKER_ERROR_MAX_BYTES
    ):
        return None
    try:
        value = payload.decode("utf-8").removesuffix("\n")
    except UnicodeDecodeError:
        return None
    if (
        not value
        or "\n" in value
        or len(value) > 1024
        or _has_control_character(value)
    ):
        return None
    return value


def _run_brokered_parent_probe(
    *,
    spec: Mapping[str, str],
    snapshot: _PrivateSnapshot,
    runner: Mapping[str, Any],
    python: Path,
    python_identity: Mapping[str, Any],
    external_tools: _ExternalToolSet,
    closure: _RuntimeSandboxClosure,
    production_embedding_fixture: _ProductionEmbeddingFixture,
    ocr_tessdata_snapshot: _SealedTessdataSnapshot,
    timeout_seconds: float,
) -> dict[str, Any]:
    probe_id = spec["probe_id"]
    if not _type_sensitive_equal(
        runner.get("production_embedding_fixture"),
        production_embedding_fixture.identity,
    ):
        raise OfflineEvidenceError(
            "formal parent probe production embedding fixture identity mismatch"
        )
    _revalidate_production_embedding_fixture(production_embedding_fixture)
    probe_fixture = (
        production_embedding_fixture
        if probe_id == _PRODUCTION_EMBEDDING_PROBE_ID
        else None
    )
    ocr_probe = _is_ocr_native_probe(probe_id)
    ocr_tessdata_probe = _is_ocr_tessdata_probe(probe_id)
    approved_tessdata_identity = runner.get("approved_ocr_tessdata_input")
    if ocr_tessdata_probe:
        if (
            not isinstance(approved_tessdata_identity, Mapping)
            or approved_tessdata_identity.get("identity_sha256")
            != ocr_tessdata_snapshot.identity["source_identity_sha256"]
        ):
            raise OfflineEvidenceError(
                "formal parent probe approved OCR tessdata identity mismatch"
            )
        _revalidate_sealed_tessdata_snapshot(ocr_tessdata_snapshot)
    worker_external_tools = external_tools
    worker_base_closure = closure
    worker_closure = closure
    if probe_fixture is not None:
        worker_closure = _production_embedding_probe_closure(
            worker_base_closure,
            probe_fixture,
            target_executable=None,
        )
    elif ocr_probe:
        worker_closure = _ocr_parent_probe_closure(
            worker_base_closure,
            probe_id=probe_id,
            tessdata_path=(
                ocr_tessdata_snapshot.path if ocr_tessdata_probe else None
            ),
            tessdata_identity=(
                ocr_tessdata_snapshot.identity if ocr_tessdata_probe else None
            ),
        )
    worker_scratch = _create_component_scratch(f"parent-{probe_id}")
    denial_probe: _ComponentScratch | None = None
    held_worker_profile: _HeldFile | None = None
    process: subprocess.Popen[bytes] | None = None
    pipe_fds: set[int] = set()
    run_succeeded = False
    process_group_quiescent = False
    denial_receipt: dict[str, Any] | None = None
    worker_receipt: dict[str, Any] | None = None
    try:
        denial_probe = _create_denial_probe(f"parent-{probe_id}")
        worker_profile = _parent_worker_sandbox_profile(
            snapshot.path,
            worker_scratch.path,
            worker_closure,
        )
        held_worker_profile = _stage_child_sandbox_profile(
            worker_scratch,
            worker_profile,
        )
        worker_binding = _parent_worker_sandbox_binding(
            profile=worker_profile,
            snapshot=snapshot,
            scratch=worker_scratch,
            denial_probe=denial_probe,
            closure=worker_closure,
        )
        worker_context = _component_sandbox_context(worker_binding, denial_probe)
        session = _parent_broker_session_identity(
            probe_id=probe_id,
            runner=runner,
            worker_sandbox_binding_sha256=worker_binding["identity_sha256"],
        )
        deadline_monotonic_ns = time.monotonic_ns() + int(
            timeout_seconds * 1_000_000_000
        )
        deadline = deadline_monotonic_ns / 1_000_000_000
        request_read, request_write = _create_cloexec_pipe()
        response_read, response_write = _create_cloexec_pipe()
        pipe_fds.update((request_read, request_write, response_read, response_write))
        encoded_test_scope = _encode_expected_identity(runner["test_scope"])
        encoded_python_identity = _encode_expected_identity(runner["python_identity"])
        formal_command, formal_closure_sha256 = (
            _formal_cli_command_from_private_snapshot(
                snapshot,
                [
                    "formal-parent-probe-worker",
                    "--probe-id",
                    probe_id,
                    "--snapshot-identity",
                    encoded_test_scope,
                    "--python-identity",
                    encoded_python_identity,
                    "--worker-sandbox-context",
                    _encode_expected_identity(worker_context),
                    "--broker-request-fd",
                    str(request_write),
                    "--broker-response-fd",
                    str(response_read),
                    "--broker-session",
                    session,
                    "--broker-deadline-monotonic-ns",
                    str(deadline_monotonic_ns),
                ],
            )
        )
        actual_command = [
            str(NETWORK_SANDBOX_PATH),
            "-f",
            _held_sandbox_profile_argument(held_worker_profile),
            *formal_command,
        ]
        environment = _expected_parent_worker_environment(
            scratch_path=worker_scratch.path,
            python=python,
            external_tools=worker_external_tools,
            sandbox_binding=worker_binding,
            probe_id=probe_id,
            production_embedding_fixture=probe_fixture,
            ocr_tessdata_path=(
                ocr_tessdata_snapshot.path if ocr_tessdata_probe else None
            ),
        )
        _revalidate_private_snapshot(snapshot)
        _revalidate_component_scratch(worker_scratch)
        _revalidate_component_scratch(denial_probe)
        _revalidate_runtime_sandbox_closure(
            closure.identity,
            python=python,
            python_identity=python_identity,
            external_tools=external_tools,
        )
        if probe_fixture is not None:
            _revalidate_production_embedding_probe_closure(
                worker_closure,
                worker_base_closure,
                probe_fixture,
                target_executable=None,
            )
        elif ocr_probe:
            _revalidate_ocr_parent_probe_closure(
                worker_closure,
                worker_base_closure,
                probe_id=probe_id,
                snapshot=(
                    ocr_tessdata_snapshot if ocr_tessdata_probe else None
                ),
            )
        _revalidate_held_sandbox_profile(held_worker_profile, worker_profile)
        process = subprocess.Popen(
            actual_command,
            cwd=None,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=partial(os.fchdir, snapshot.root_fd),
            pass_fds=(
                snapshot.root_fd,
                request_write,
                response_read,
            ),
            close_fds=True,
            start_new_session=True,
        )
        worker_process_identity = _observed_new_session_process_identity(
            process,
            "formal parent probe worker",
        )
        _write_sandbox_profile_pipe(
            process,
            held_worker_profile.payload,
            command=actual_command,
            field="formal parent probe worker",
            timeout=timeout_seconds,
        )
        os.close(request_write)
        pipe_fds.remove(request_write)
        os.close(response_read)
        pipe_fds.remove(response_read)
        try:
            broker_transcript = _serve_parent_broker(
                request_fd=request_read,
                response_fd=response_write,
                session=session,
                probe_id=probe_id,
                worker_scratch=worker_scratch,
                parent_snapshot=snapshot,
                python=python,
                python_identity=python_identity,
                full_external_tools=external_tools,
                full_closure=closure,
                production_embedding_fixture=probe_fixture,
                ocr_tessdata_snapshot=(
                    ocr_tessdata_snapshot if ocr_tessdata_probe else None
                ),
                deadline=deadline,
                deadline_monotonic_ns=deadline_monotonic_ns,
            )
        except OfflineEvidenceError as exc:
            for descriptor in (request_read, response_write):
                if descriptor in pipe_fds:
                    os.close(descriptor)
                    pipe_fds.remove(descriptor)
            remaining = max(0.1, min(5.0, deadline - time.monotonic()))
            try:
                failure_stdout, _failure_stderr = _read_bounded_process_output(
                    process,
                    command=actual_command,
                    field="formal parent probe worker",
                    timeout=remaining,
                    stdout_max_bytes=_PARENT_WORKER_ERROR_MAX_BYTES,
                    stderr_max_bytes=None,
                    total_max_bytes=_PARENT_WORKER_ERROR_MAX_BYTES,
                )
                process_group_quiescent = True
            except (OfflineEvidenceError, subprocess.TimeoutExpired):
                failure_stdout = b""
            if not process_group_quiescent:
                _terminate_brokered_process(process)
                process_group_quiescent = True
            detail = _bounded_parent_worker_error(failure_stdout)
            if detail is not None:
                raise OfflineEvidenceError(f"{exc}; worker: {detail}") from exc
            raise
        os.close(request_read)
        pipe_fds.remove(request_read)
        os.close(response_write)
        pipe_fds.remove(response_write)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OfflineEvidenceError(f"formal parent probe timed out: {probe_id}")
        try:
            stdout, _stderr = _read_bounded_process_output(
                process,
                command=actual_command,
                field="formal parent probe worker",
                timeout=remaining,
                stdout_max_bytes=_PARENT_PROBE_OUTPUT_MAX_BYTES,
                stderr_max_bytes=None,
                total_max_bytes=_PARENT_PROBE_OUTPUT_MAX_BYTES,
            )
        except subprocess.TimeoutExpired as exc:
            _terminate_brokered_process(process)
            process_group_quiescent = True
            raise OfflineEvidenceError(
                f"formal parent probe timed out: {probe_id}"
            ) from exc
        if not isinstance(stdout, bytes) or type(process.returncode) is not int:
            raise OfflineEvidenceError(
                f"formal parent probe returned a malformed result: {probe_id}"
            )
        process_group_quiescent = True
        source_payload, _source_binding = _stable_relative_file_binding(
            snapshot.root_fd,
            spec["source_path"],
            "formal parent probe snapshot source",
            max_bytes=4 * 1024 * 1024,
        )
        log_payload, process_result = _parse_parent_probe_process_payload(
            stdout,
            runner=runner,
            spec=spec,
            expected_source_sha256=hashlib.sha256(source_payload).hexdigest(),
        )
        if not _type_sensitive_equal(
            process_result["worker_process_identity"],
            worker_process_identity,
        ):
            raise OfflineEvidenceError(
                "formal parent worker process identity mismatch"
            )
        client_transcript = process_result["broker_client_transcript"]
        for field in (
            "session",
            "probe_id",
            "deadline_monotonic_ns",
            "operation_ids",
            "operation_ids_sha256",
            "exchange_hashes",
            "exchange_chain_sha256",
        ):
            if client_transcript[field] != broker_transcript[field]:
                raise OfflineEvidenceError(
                    "formal parent broker client/server transcript mismatch"
                )
        if client_transcript["operation_count"] != broker_transcript[
            "accepted_operation_count"
        ]:
            raise OfflineEvidenceError(
                "formal parent broker client/server transcript mismatch"
            )
        enforcement = process_result["worker_sandbox_enforcement"]
        if any(
            item["sandbox_binding_sha256"] != worker_binding["identity_sha256"]
            or item["context_identity_sha256"] != worker_context["identity_sha256"]
            for item in (enforcement["initial"], enforcement["final"])
        ):
            raise OfflineEvidenceError(
                "formal parent worker sandbox result identity mismatch"
            )
        _revalidate_private_snapshot(snapshot)
        _revalidate_component_scratch(worker_scratch)
        _revalidate_component_scratch(denial_probe)
        _revalidate_runtime_sandbox_closure(
            closure.identity,
            python=python,
            python_identity=python_identity,
            external_tools=external_tools,
        )
        if probe_fixture is not None:
            _revalidate_production_embedding_probe_closure(
                worker_closure,
                worker_base_closure,
                probe_fixture,
                target_executable=None,
            )
        elif ocr_probe:
            _revalidate_ocr_parent_probe_closure(
                worker_closure,
                worker_base_closure,
                probe_id=probe_id,
                snapshot=(
                    ocr_tessdata_snapshot if ocr_tessdata_probe else None
                ),
            )
        _revalidate_held_sandbox_profile(held_worker_profile, worker_profile)
        normalized_command = _expected_parent_probe_command(probe_id)[1]
        worker_launch = {
            "schema_version": PARENT_WORKER_LAUNCH_SCHEMA_VERSION,
            "sandbox_binding": worker_binding,
            "sandbox_context": dict(worker_context),
            "sandbox_context_identity_sha256": worker_context["identity_sha256"],
            "normalized_command": normalized_command,
            "normalized_command_sha256": _identity_sha256(normalized_command),
            "profile_base64": base64.b64encode(worker_profile.encode("utf-8")).decode(
                "ascii"
            ),
            "stdin_role": "sandbox-profile-pipe",
            "stdin_profile_size": len(worker_profile.encode("utf-8")),
            "stdin_profile_sha256": hashlib.sha256(worker_profile.encode("utf-8")).hexdigest(),
            "formal_closure_sha256": formal_closure_sha256,
            "environment": dict(environment),
            "environment_sha256": _identity_sha256(environment),
            "snapshot_path": str(snapshot.path),
            "scratch_path": str(worker_scratch.path),
            "denial_probe_path": str(denial_probe.path),
            "inherited_fd_roles": [
                "snapshot-root",
                "broker-request-write",
                "broker-response-read",
            ],
            "broker_session": session,
            "broker_deadline_monotonic_ns": deadline_monotonic_ns,
            "process_identity": worker_process_identity,
            "direct_worker_waited": True,
            "process_group_quiescence_verified": True,
            "timeout_cleanup_contract": (
                "new-session-process-group-quiescence-or-killpg-and-wait"
            ),
        }
        if ocr_tessdata_probe:
            worker_launch.update(
                {
                    "ocr_tessdata_snapshot_identity": dict(
                        ocr_tessdata_snapshot.identity
                    ),
                    "ocr_tessdata_snapshot_path": str(
                        ocr_tessdata_snapshot.path
                    ),
                }
            )
        worker_launch["identity_sha256"] = _identity_sha256(worker_launch)
        run_succeeded = True
        result = {
            "stdout": stdout,
            "returncode": process.returncode,
            "log_payload": log_payload,
            "process_result": process_result,
            "broker_transcript": broker_transcript,
            "worker_launch": worker_launch,
        }
    finally:
        primary_error = sys.exception()
        for descriptor in tuple(pipe_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass
        cleanup_error: Exception | None = None
        if process is not None and not process_group_quiescent:
            try:
                _terminate_brokered_process(process)
            except Exception as exc:
                cleanup_error = exc
        if held_worker_profile is not None:
            try:
                _close_held_file(held_worker_profile)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="formal parent worker held profile",
                )
        if denial_probe is not None:
            try:
                denial_receipt = _close_component_scratch(denial_probe)
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        try:
            worker_receipt = _close_component_scratch(worker_scratch)
        except Exception as exc:
            if cleanup_error is None:
                cleanup_error = exc
        _finish_process_cleanup(
            cleanup_error,
            primary_error=primary_error,
        )
    if (
        not run_succeeded
        or denial_receipt is None
        or worker_receipt is None
    ):
        raise OfflineEvidenceError(f"formal parent probe failed: {probe_id}")
    result["worker_scratch"] = worker_receipt
    result["worker_denial_probe_scratch"] = denial_receipt
    return result


def _sandboxed_disclosure_operation(
    *,
    action: str,
    target_path: str | Path,
    created_at: str,
) -> dict[str, Any]:
    _require_network_denial()
    if action == "build":
        return _build_disclosure_evidence_in_process(
            repo_root=Path.cwd(),
            output_path=target_path,
            created_at=created_at,
        )
    if action == "validate":
        return _validate_disclosure_evidence_in_process(
            repo_root=Path.cwd(),
            receipt_path=target_path,
        )
    raise OfflineEvidenceError("sandboxed disclosure action is not allowlisted")


def _sandboxed_error(payload: bytes) -> str | None:
    if len(payload) > 4096:
        return None
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, Mapping)
        or set(value) != {"error"}
        or not isinstance(value["error"], str)
        or not value["error"]
        or len(value["error"]) > 1024
        or _has_control_character(value["error"])
        or payload != canonical_json_bytes(value)
    ):
        return None
    return value["error"]


def _run_sandboxed_disclosure(
    *,
    action: str,
    repo_root: str | Path,
    target_path: str | Path,
    created_at: str = "",
) -> dict[str, Any]:
    if action not in {"build", "validate"}:
        raise OfflineEvidenceError("sandboxed disclosure action is not allowlisted")
    if action == "build":
        created_at = _require_utc_second(created_at, "created_at")
    if os.environ.get(_INHERITED_COMPONENT_SANDBOX_ENV) is not None:
        if isinstance(_PARENT_BROKER_CLIENT, _ParentBrokerClient):
            _require_active_component_sandbox_binding()
        else:
            _require_active_component_sandbox_context()
    repository_fd: int | None = None
    snapshot: _PrivateSnapshot | None = None
    scratch: _ComponentScratch | None = None
    denial_probe: _ComponentScratch | None = None
    held_profile: _HeldFile | None = None
    output_reservation: _ReservedOutput | None = None
    held_target: _HeldFile | None = None
    completed_successfully = False

    def capture_cleanup(
        current: Exception | None,
        *,
        label: str,
        operation: Any,
    ) -> tuple[Exception | None, bool]:
        try:
            operation()
        except Exception as exc:
            return _merge_cleanup_error(current, exc, label=label), False
        return current, True

    try:
        target = _absolute_path(target_path, "disclosure evidence")
        if action == "validate":
            held_target = _hold_file_under_root(
                target,
                target.parent,
                "disclosure evidence",
                max_bytes=16 * 1024 * 1024,
            )
            target = held_target.path
        else:
            output_reservation = _reserve_new_output(target, readable=True)
            target = output_reservation.path

        raw_repository = Path(repo_root)
        if raw_repository.is_symlink():
            raise OfflineEvidenceError("repository root must be a real directory")
        repository, repository_fd = _open_directory_fd(
            raw_repository,
            "repository root",
        )
        _require_formal_bootstrap_context(repository_fd)
        python = _python_executable()
        python_identity = _python_identity(python)
        _require_sealed_runtime_environment(python_identity["runtime_environment"])
        _network_policy()
        external_tools = _empty_external_tool_set()
        closure = _runtime_sandbox_closure(
            python=python,
            python_identity=python_identity,
            external_tools=external_tools,
        )
        snapshot = _build_private_snapshot(
            repository_fd,
            tree_roots=(),
            exact_files=_DISCLOSURE_SNAPSHOT_FILES,
        )
        encoded_module_closure = _encoded_module_closure_manifest(
            snapshot.root_fd,
            schema_version="cloud-v2-child-bootstrap-closure-v1",
            field="disclosure child module",
        )
        scratch = _create_component_scratch(f"disclosure-{action}")
        denial_probe = _create_denial_probe(f"disclosure-{action}")
        staged_target = scratch.path / "disclosure-evidence.json"
        staged_input_binding: dict[str, Any] | None = None
        if action == "validate":
            if held_target is None:
                raise OfflineEvidenceError(
                    "disclosure validation input binding is unavailable"
                )
            staged_input_binding = _write_component_scratch_input(
                scratch,
                staged_target.name,
                held_target.payload,
                "staged disclosure evidence",
            )
        child_profile = _child_sandbox_profile(
            snapshot.path,
            scratch.path,
            closure,
        )
        held_profile = _stage_child_sandbox_profile(scratch, child_profile)
        child_sandbox = _child_sandbox_binding(
            profile=child_profile,
            snapshot=snapshot,
            scratch=scratch,
            denial_probe=denial_probe,
            closure=closure,
        )
        snapshot_identity = _test_scope_identity_from_fd(
            snapshot.root_fd,
            materialized=True,
            tree_roots=(),
            exact_files=_DISCLOSURE_SNAPSHOT_FILES,
        )
        sandbox_context = _component_sandbox_context(child_sandbox, denial_probe)
        command = [
            str(NETWORK_SANDBOX_PATH),
            "-f",
            _held_sandbox_profile_argument(held_profile),
            str(python),
            "-I",
            "-S",
            "-B",
            "-c",
            _DISCLOSURE_SUBPROCESS_BOOTSTRAP,
            encoded_module_closure,
            action,
            str(staged_target),
            created_at,
            _encode_expected_identity(python_identity),
            _encode_expected_identity(snapshot_identity),
            _encode_expected_identity(sandbox_context),
        ]
        environment = {
            "PATH": str(python.parent),
            "TMPDIR": str(scratch.path),
            "TMP": str(scratch.path),
            "TEMP": str(scratch.path),
            "HOME": str(scratch.path),
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
        }
        environment[_INHERITED_COMPONENT_SANDBOX_ENV] = child_sandbox[
            "identity_sha256"
        ]

        def revalidate_python() -> None:
            if _python_identity(python) != python_identity:
                raise OfflineEvidenceError(
                    f"Python identity changed during sandboxed disclosure {action}"
                )

        def revalidate_runtime() -> None:
            _revalidate_runtime_sandbox_closure(
                closure.identity,
                python=python,
                python_identity=python_identity,
                external_tools=external_tools,
            )

        _revalidate_directory_path(
            raw_repository,
            repository_fd,
            "repository root",
        )
        _revalidate_private_snapshot(snapshot)
        _revalidate_live_snapshot_inputs(repository_fd, snapshot)
        _revalidate_component_scratch(scratch)
        revalidate_python()
        revalidate_runtime()
        _revalidate_held_sandbox_profile(held_profile, child_profile)
        try:
            completed = _run_new_session_process(
                command,
                field=f"sandboxed disclosure {action}",
                cwd=None,
                env=environment,
                stdin=subprocess.PIPE,
                input_payload=held_profile.payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=_DISCLOSURE_SUBPROCESS_TIMEOUT_SECONDS,
                check=False,
                preexec_fn=partial(os.fchdir, snapshot.root_fd),
                pass_fds=(snapshot.root_fd,),
            )
        except subprocess.TimeoutExpired as exc:
            raise OfflineEvidenceError(
                f"sandboxed disclosure {action} timed out"
            ) from exc
        except Exception as exc:
            raise OfflineEvidenceError(
                f"sandboxed disclosure {action} could not be started"
            ) from exc
        _revalidate_held_sandbox_profile(held_profile, child_profile)
        _revalidate_directory_path(
            raw_repository,
            repository_fd,
            "repository root",
        )
        _revalidate_private_snapshot(snapshot)
        _revalidate_live_snapshot_inputs(repository_fd, snapshot)
        _revalidate_component_scratch(scratch)
        revalidate_python()
        revalidate_runtime()
        if not isinstance(completed.stdout, bytes) or type(completed.returncode) is not int:
            raise OfflineEvidenceError(
                f"sandboxed disclosure {action} returned a malformed result"
            )
        if completed.returncode != 0:
            message = _sandboxed_error(completed.stdout)
            raise OfflineEvidenceError(
                message or f"sandboxed disclosure {action} failed"
            )
        try:
            result = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineEvidenceError(
                f"sandboxed disclosure {action} returned invalid JSON"
            ) from exc
        if (
            not isinstance(result, Mapping)
            or completed.stdout != canonical_json_bytes(result)
        ):
            raise OfflineEvidenceError(
                f"sandboxed disclosure {action} returned non-canonical evidence"
            )
        receipt_payload, staged_binding = _stable_relative_file_binding(
            scratch.root_fd,
            staged_target.name,
            "staged disclosure evidence",
            max_bytes=16 * 1024 * 1024,
        )
        if action == "validate" and staged_binding != staged_input_binding:
            raise OfflineEvidenceError(
                "staged disclosure evidence changed during validation"
            )
        if result.get("receipt_sha256") != hashlib.sha256(receipt_payload).hexdigest():
            raise OfflineEvidenceError(
                f"sandboxed disclosure {action} returned an unbound receipt"
            )
        if action == "validate":
            if held_target is None:
                raise OfflineEvidenceError(
                    "disclosure validation input binding is unavailable"
                )
            _revalidate_held_file_bytes(
                held_target,
                max_bytes=16 * 1024 * 1024,
            )
            if receipt_payload != held_target.payload:
                raise OfflineEvidenceError(
                    "staged disclosure evidence differs from its parent input"
                )
        revalidate_python()
        revalidate_runtime()
        _revalidate_private_snapshot(snapshot)
        _revalidate_live_snapshot_inputs(repository_fd, snapshot)
        _revalidate_directory_path(
            raw_repository,
            repository_fd,
            "repository root",
        )
        _revalidate_held_sandbox_profile(held_profile, child_profile)

        if action == "build":
            if output_reservation is None:
                raise OfflineEvidenceError(
                    "disclosure output reservation is unavailable"
                )
            _write_reserved_bytes(
                output_reservation,
                receipt_payload,
                "disclosure evidence",
            )
            if (
                _read_reserved_output_bytes(
                    output_reservation,
                    "disclosure evidence",
                    max_bytes=16 * 1024 * 1024,
                )
                != receipt_payload
            ):
                raise OfflineEvidenceError(
                    "disclosure evidence bytes differ after writing"
                )
            _revalidate_reserved_path(output_reservation, "disclosure evidence")

        cleanup_error: Exception | None = None
        if held_profile is not None:
            closing_profile = held_profile
            cleanup_error, closed = capture_cleanup(
                cleanup_error,
                label="disclosure sandbox profile",
                operation=lambda: _close_held_file(closing_profile),
            )
            if closed:
                held_profile = None
        if denial_probe is not None:
            closing_denial_probe = denial_probe
            cleanup_error, closed = capture_cleanup(
                cleanup_error,
                label="disclosure denial probe scratch",
                operation=lambda: _close_component_scratch(closing_denial_probe),
            )
            if closed:
                denial_probe = None
        if scratch is not None:
            closing_scratch = scratch
            cleanup_error, closed = capture_cleanup(
                cleanup_error,
                label="disclosure component scratch",
                operation=lambda: _close_component_scratch(closing_scratch),
            )
            if closed:
                scratch = None

        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure Python revalidation after scratch cleanup",
            operation=revalidate_python,
        )
        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure runtime revalidation after scratch cleanup",
            operation=revalidate_runtime,
        )
        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure private snapshot revalidation after scratch cleanup",
            operation=lambda: _revalidate_private_snapshot(snapshot),
        )
        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure live repository revalidation after scratch cleanup",
            operation=lambda: _revalidate_live_snapshot_inputs(
                repository_fd,
                snapshot,
            ),
        )
        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure repository path revalidation after scratch cleanup",
            operation=lambda: _revalidate_directory_path(
                raw_repository,
                repository_fd,
                "repository root",
            ),
        )

        closed_snapshot = snapshot
        if closed_snapshot is not None:
            cleanup_error, closed = capture_cleanup(
                cleanup_error,
                label="disclosure private snapshot",
                operation=lambda: _close_private_snapshot(closed_snapshot),
            )
            if closed:
                snapshot = None
        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure live repository revalidation after snapshot cleanup",
            operation=lambda: _revalidate_live_snapshot_inputs(
                repository_fd,
                closed_snapshot,
            ),
        )
        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure Python revalidation after snapshot cleanup",
            operation=revalidate_python,
        )
        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure runtime revalidation after snapshot cleanup",
            operation=revalidate_runtime,
        )
        cleanup_error, _ = capture_cleanup(
            cleanup_error,
            label="disclosure repository path revalidation after snapshot cleanup",
            operation=lambda: _revalidate_directory_path(
                raw_repository,
                repository_fd,
                "repository root",
            ),
        )
        if repository_fd is not None:
            closing_repository_fd = repository_fd
            cleanup_error, closed = capture_cleanup(
                cleanup_error,
                label="disclosure repository root descriptor",
                operation=lambda: os.close(closing_repository_fd),
            )
            if closed:
                repository_fd = None
        _finish_process_cleanup(cleanup_error, primary_error=None)

        if action == "validate":
            if held_target is None:
                raise OfflineEvidenceError(
                    "disclosure validation input binding is unavailable"
                )
            target_error: Exception | None = None
            target_error, _ = capture_cleanup(
                target_error,
                label="disclosure validation input final closure",
                operation=lambda: _revalidate_held_file_bytes(
                    held_target,
                    max_bytes=16 * 1024 * 1024,
                ),
            )
            closing_target = held_target
            target_error, closed = capture_cleanup(
                target_error,
                label="disclosure validation input descriptor",
                operation=lambda: _close_held_file(closing_target),
            )
            if closed:
                held_target = None
            _finish_process_cleanup(target_error, primary_error=None)
        else:
            if output_reservation is None:
                raise OfflineEvidenceError(
                    "disclosure output reservation is unavailable"
                )
            output_error: Exception | None = None
            output_verified = False
            try:
                if (
                    _read_reserved_output_bytes(
                        output_reservation,
                        "disclosure evidence",
                        max_bytes=16 * 1024 * 1024,
                    )
                    != receipt_payload
                ):
                    raise OfflineEvidenceError(
                        "disclosure evidence bytes differ during final closure"
                    )
                _revalidate_reserved_path(
                    output_reservation,
                    "disclosure evidence",
                )
                output_verified = True
            except Exception as exc:
                output_error = _merge_cleanup_error(
                    output_error,
                    exc,
                    label="disclosure output final closure",
                )
            closing_output = output_reservation
            output_error, closed = capture_cleanup(
                output_error,
                label="disclosure output reservation",
                operation=lambda: _close_reserved_output(
                    closing_output,
                    discard=not output_verified,
                ),
            )
            if closed:
                output_reservation = None
            _finish_process_cleanup(output_error, primary_error=None)

        result_value = dict(result)
        completed_successfully = True
        return result_value
    finally:
        primary_error = sys.exception()
        cleanup_error: Exception | None = None
        if held_profile is not None:
            cleanup_error, _ = capture_cleanup(
                cleanup_error,
                label="disclosure sandbox profile",
                operation=lambda: _close_held_file(held_profile),
            )
        if denial_probe is not None:
            cleanup_error, _ = capture_cleanup(
                cleanup_error,
                label="disclosure denial probe scratch",
                operation=lambda: _close_component_scratch(denial_probe),
            )
        if scratch is not None:
            cleanup_error, _ = capture_cleanup(
                cleanup_error,
                label="disclosure component scratch",
                operation=lambda: _close_component_scratch(scratch),
            )
        if snapshot is not None:
            cleanup_error, _ = capture_cleanup(
                cleanup_error,
                label="disclosure private snapshot",
                operation=lambda: _close_private_snapshot(snapshot),
            )
        if repository_fd is not None:
            cleanup_error, _ = capture_cleanup(
                cleanup_error,
                label="disclosure repository root descriptor",
                operation=lambda: os.close(repository_fd),
            )
        if held_target is not None:
            cleanup_error, _ = capture_cleanup(
                cleanup_error,
                label="disclosure validation input descriptor",
                operation=lambda: _close_held_file(held_target),
            )
        if output_reservation is not None:
            cleanup_error, _ = capture_cleanup(
                cleanup_error,
                label="disclosure output reservation",
                operation=lambda: _close_reserved_output(
                    output_reservation,
                    discard=not completed_successfully,
                ),
            )
        _finish_process_cleanup(
            cleanup_error,
            primary_error=primary_error,
        )


def build_disclosure_evidence(
    *,
    repo_root: str | Path,
    output_path: str | Path,
    created_at: str,
) -> dict[str, Any]:
    return _run_sandboxed_disclosure(
        action="build",
        repo_root=repo_root,
        target_path=output_path,
        created_at=created_at,
    )


def validate_disclosure_evidence(
    *,
    repo_root: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    return _run_sandboxed_disclosure(
        action="validate",
        repo_root=repo_root,
        target_path=receipt_path,
    )


def _identity_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _snapshot_package_anchor_records() -> list[dict[str, str]]:
    return [
        {
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for path, payload in sorted(_SNAPSHOT_PACKAGE_ANCHORS.items())
    ]


def _formal_source_context(
    root_fd: int,
    *,
    source_kind: str,
    closure_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if source_kind not in {"live-repository", "materialized-snapshot"}:
        raise OfflineEvidenceError("formal CLI source kind is not allowlisted")
    _module_closure_source_sha256(closure_manifest)
    root_state = os.fstat(root_fd)
    root_identity = _inode_identity(root_state)
    if root_identity[1] == 0 or root_identity[2] != stat.S_IFDIR:
        raise OfflineEvidenceError("formal CLI held root identity is malformed")
    context = {
        "schema_version": FORMAL_SOURCE_CONTEXT_SCHEMA_VERSION,
        "source_kind": source_kind,
        "held_root_identity": list(root_identity),
        "closure_manifest_sha256": hashlib.sha256(
            canonical_json_bytes(closure_manifest)
        ).hexdigest(),
        "package_anchors_sha256": _identity_sha256(
            _snapshot_package_anchor_records()
        ),
    }
    if _inode_identity(os.fstat(root_fd)) != root_identity:
        raise OfflineEvidenceError("formal CLI held root identity changed")
    return context


def _require_isolated_python() -> None:
    inactive = [
        name
        for name, active in (
            ("isolated", sys.flags.isolated == 1),
            ("no_site", sys.flags.no_site == 1),
            ("dont_write_bytecode", sys.flags.dont_write_bytecode == 1),
        )
        if not active
    ]
    if inactive:
        raise OfflineEvidenceError(
            "formal CLI requires Python -I -S -B; inactive: " + ",".join(inactive)
        )


def _startup_flags_identity() -> dict[str, bool]:
    return {
        "isolated": sys.flags.isolated == 1,
        "no_site": sys.flags.no_site == 1,
        "dont_write_bytecode": sys.flags.dont_write_bytecode == 1,
        "ignore_environment": sys.flags.ignore_environment == 1,
        "no_user_site": sys.flags.no_user_site == 1,
        "safe_path": sys.flags.safe_path is True,
    }


def _encode_expected_identity(value: Mapping[str, Any]) -> str:
    return base64.b64encode(canonical_json_bytes(value)).decode("ascii")


def _decode_expected_identity(value: str) -> dict[str, Any]:
    if not isinstance(value, str) or len(value) > 1024 * 1024:
        raise OfflineEvidenceError("child expected identity is invalid")
    try:
        payload = base64.b64decode(value, validate=True)
        parsed = json.loads(payload.decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfflineEvidenceError("child expected identity is invalid") from exc
    if (
        not isinstance(parsed, Mapping)
        or payload != canonical_json_bytes(parsed)
        or base64.b64encode(payload).decode("ascii") != value
    ):
        raise OfflineEvidenceError("child expected identity is not canonical")
    return dict(parsed)


def _reject_repository_import_shadows(
    repo_fd: int,
    *,
    allow_snapshot_package_anchors: bool = False,
) -> None:
    try:
        root_names = os.listdir(repo_fd)
    except OSError as exc:
        raise OfflineEvidenceError("repository root could not be inspected safely") from exc
    folded_root: dict[str, str] = {}
    for name in root_names:
        if (
            not isinstance(name, str)
            or _has_control_character(name)
            or unicodedata.normalize("NFC", name) != name
        ):
            raise OfflineEvidenceError("repository root contains a non-canonical name")
        folded = unicodedata.normalize("NFC", name).casefold()
        if folded in folded_root:
            raise OfflineEvidenceError(
                "repository root contains a case or Unicode alias collision"
            )
        folded_root[folded] = name
    if "deploy.py" in folded_root:
        raise OfflineEvidenceError("repository root contains a deploy.py import shadow")
    if "deploy" not in folded_root or folded_root["deploy"] != "deploy":
        raise OfflineEvidenceError("repository deploy root is missing or aliased")

    deploy_fd = _open_relative_directory_fd(repo_fd, "deploy", "repository deploy root")
    try:
        try:
            deploy_names = os.listdir(deploy_fd)
        except OSError as exc:
            raise OfflineEvidenceError(
                "repository deploy root could not be inspected safely"
            ) from exc
        deploy_initializers = [
            name
            for name in deploy_names
            if unicodedata.normalize("NFC", name).casefold() == "__init__.py"
        ]
        if deploy_initializers:
            relative = "deploy/__init__.py"
            if (
                not allow_snapshot_package_anchors
                or deploy_initializers != ["__init__.py"]
                or _stable_relative_file_bytes(
                    repo_fd,
                    relative,
                    "private snapshot package anchor",
                )
                != _SNAPSHOT_PACKAGE_ANCHORS[relative]
            ):
                raise OfflineEvidenceError(
                    "repository root contains a deploy/__init__.py import shadow"
                )
        for package in ("pipeline", "rag_store"):
            if package not in deploy_names:
                continue
            package_fd = _open_relative_directory_fd(
                deploy_fd,
                package,
                f"repository deploy/{package} root",
            )
            try:
                initializers = [
                    name
                    for name in os.listdir(package_fd)
                    if unicodedata.normalize("NFC", name).casefold() == "__init__.py"
                ]
                relative = f"deploy/{package}/__init__.py"
                if initializers and (
                    not allow_snapshot_package_anchors
                    or initializers != ["__init__.py"]
                    or _stable_relative_file_bytes(
                        repo_fd,
                        relative,
                        "private snapshot package anchor",
                    )
                    != _SNAPSHOT_PACKAGE_ANCHORS[relative]
                ):
                    raise OfflineEvidenceError(
                        f"repository deploy/{package}/__init__.py conflicts with "
                        "the sealed package anchor"
                    )
            finally:
                os.close(package_fd)
    finally:
        os.close(deploy_fd)


def _require_formal_repository_identity(repo_fd: int) -> None:
    if (
        _FORMAL_REPOSITORY_IDENTITY is not None
        and _inode_identity(os.fstat(repo_fd)) != _FORMAL_REPOSITORY_IDENTITY
    ):
        raise OfflineEvidenceError(
            "formal CLI repository differs from its held bootstrap root"
        )


def _require_materialized_snapshot_anchors(repo_fd: int) -> None:
    for relative, expected_payload in sorted(_SNAPSHOT_PACKAGE_ANCHORS.items()):
        actual, binding = _stable_relative_file_binding(
            repo_fd,
            relative,
            f"materialized snapshot package anchor {relative}",
            max_bytes=1024,
        )
        if (
            actual != expected_payload
            or stat.S_IMODE(binding["mode"]) != 0o400
        ):
            raise OfflineEvidenceError(
                "snapshot package anchor byte identity mismatch"
            )


def _activate_formal_materialized_snapshot(
    repo_root: str | Path,
    expected_scope: Mapping[str, Any],
    *,
    field: str,
) -> dict[str, Any]:
    global _FORMAL_MATERIALIZED_SNAPSHOT_IDENTITY
    if _FORMAL_MATERIALIZED_SNAPSHOT_IDENTITY is not None:
        raise OfflineEvidenceError(
            f"{field} materialized snapshot marker is already active"
        )
    expected = _validated_persisted_snapshot_identity(expected_scope)
    repository, repository_fd = _open_directory_fd(repo_root, field)
    try:
        _require_formal_bootstrap_context(repository_fd)
        marker_identity = _inode_identity(os.fstat(repository_fd))
        if marker_identity != _FORMAL_REPOSITORY_IDENTITY:
            raise OfflineEvidenceError(f"{field} root identity mismatch")
        actual = _test_scope_identity(
            repository,
            repo_fd=repository_fd,
            force_content=True,
            materialized=True,
            tree_roots=tuple(expected["tree_roots"]),
            exact_files=tuple(expected["exact_files"]),
        )
        if not _type_sensitive_equal(actual, expected):
            raise OfflineEvidenceError(f"{field} identity mismatch")
        _require_materialized_snapshot_anchors(repository_fd)
        final = _test_scope_identity(
            repository,
            repo_fd=repository_fd,
            force_content=True,
            materialized=True,
            tree_roots=tuple(expected["tree_roots"]),
            exact_files=tuple(expected["exact_files"]),
        )
        if not _type_sensitive_equal(final, expected):
            raise OfflineEvidenceError(f"{field} changed during activation")
    finally:
        os.close(repository_fd)
    _FORMAL_MATERIALIZED_SNAPSHOT_IDENTITY = marker_identity
    return final


def _formal_materialized_snapshot_matches(repo_fd: int) -> bool:
    marker = _FORMAL_MATERIALIZED_SNAPSHOT_IDENTITY
    matches = (
        isinstance(marker, tuple)
        and len(marker) == 3
        and all(type(value) is int and value >= 0 for value in marker)
        and marker[1] > 0
        and marker[2] == stat.S_IFDIR
        and _FORMAL_REPOSITORY_IDENTITY == marker
        and _inode_identity(os.fstat(repo_fd)) == marker
    )
    if matches:
        _require_materialized_snapshot_anchors(repo_fd)
    return matches


def _runner_state_from_binding(binding: Mapping[str, Any]) -> dict[str, int]:
    return {field: binding[field] for field in _RUNNER_STATE_FIELDS}


def _require_formal_bootstrap_context(repo_fd: int | None = None) -> None:
    root_identity = _FORMAL_REPOSITORY_IDENTITY
    source_sha256 = _EXECUTED_RUNNER_SOURCE_SHA256
    source_state = _EXECUTED_RUNNER_STATE_IDENTITY
    if (
        not isinstance(root_identity, tuple)
        or len(root_identity) != 3
        or any(type(value) is not int or value < 0 for value in root_identity)
        or not isinstance(source_sha256, str)
        or not _SHA256.fullmatch(source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_RUNNER_STATE_FIELDS)
        or any(type(source_state[field]) is not int or source_state[field] < 0 for field in _RUNNER_STATE_FIELDS)
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
    ):
        raise OfflineEvidenceError("formal CLI bootstrap context is required")
    if repo_fd is None:
        return
    if _inode_identity(os.fstat(repo_fd)) != root_identity:
        raise OfflineEvidenceError(
            "formal CLI repository differs from its held bootstrap root"
        )
    _payload, repository_binding = _stable_relative_file_binding(
        repo_fd,
        OFFLINE_EVIDENCE_SOURCE_PATH,
        "formal CLI offline evidence source",
        max_bytes=4 * 1024 * 1024,
    )
    if (
        repository_binding["sha256"] != source_sha256
        or _runner_state_from_binding(repository_binding) != dict(source_state)
    ):
        raise OfflineEvidenceError(
            "formal CLI runner differs from its held bootstrap source"
        )


def _current_test_evidence_action_closure() -> tuple[object, ...]:
    return (validate_test_evidence, _validate_test_evidence_impl)


def _install_formal_test_evidence_bootstrap_context() -> None:
    global _FORMAL_TEST_EVIDENCE_ACTION_CLOSURE
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except OfflineEvidenceError as exc:
        raise OfflineEvidenceError(
            "formal test evidence bootstrap context is required"
        ) from exc
    _FORMAL_TEST_EVIDENCE_ACTION_CLOSURE = (
        _current_test_evidence_action_closure()
    )


def _require_formal_test_evidence_bootstrap_context() -> tuple[object, ...]:
    actions = _FORMAL_TEST_EVIDENCE_ACTION_CLOSURE
    if not isinstance(actions, tuple) or len(actions) != 2:
        raise OfflineEvidenceError(
            "formal test evidence bootstrap context is required"
        )
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except OfflineEvidenceError as exc:
        raise OfflineEvidenceError(
            "formal test evidence bootstrap context changed"
        ) from exc
    if any(
        current is not expected
        for current, expected in zip(
            _current_test_evidence_action_closure(), actions, strict=True
        )
    ):
        raise OfflineEvidenceError(
            "formal test evidence action closure changed"
        )
    return actions


def _canonical_snapshot_name(name: object, field: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or _has_control_character(name)
        or unicodedata.normalize("NFC", name) != name
    ):
        raise OfflineEvidenceError(f"{field} contains a non-canonical name")
    return name


def _snapshot_source_identity_from_fd(
    repo_fd: int,
    *,
    tree_roots: Sequence[str],
    exact_files: Sequence[str],
    materialized: bool,
    file_sink: Any | None = None,
) -> dict[str, Any]:
    roots = tuple(_canonical_relative(item, "snapshot tree root") for item in tree_roots)
    files = tuple(_canonical_relative(item, "snapshot exact file") for item in exact_files)
    if len(set(roots)) != len(roots) or len(set(files)) != len(files):
        raise OfflineEvidenceError("snapshot input allowlist contains a duplicate")
    for index, left in enumerate(roots):
        left_path = PurePosixPath(left)
        for right in roots[index + 1 :]:
            right_path = PurePosixPath(right)
            if left_path in right_path.parents or right_path in left_path.parents:
                raise OfflineEvidenceError("snapshot tree roots overlap")
    if any(
        PurePosixPath(relative) == PurePosixPath(root)
        or PurePosixPath(root) in PurePosixPath(relative).parents
        for relative in files
        for root in roots
    ):
        raise OfflineEvidenceError("snapshot exact file overlaps a tree root")

    directory_paths: list[str] = []
    file_records: list[dict[str, str]] = []
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )

    def consume_file(directory_fd: int, name: str, relative: str, state: os.stat_result) -> None:
        if relative in _SNAPSHOT_PACKAGE_ANCHORS:
            if not materialized:
                raise OfflineEvidenceError(
                    f"repository contains a reserved snapshot package anchor: {relative}"
                )
        if state.st_nlink != 1:
            raise OfflineEvidenceError("snapshot input contains a hard-linked file")
        _safe_mode(state, f"snapshot input file {relative}")
        descriptor: int | None = None
        try:
            descriptor = os.open(name, file_flags, dir_fd=directory_fd)
            opened = os.fstat(descriptor)
            if _state_identity(opened) != _state_identity(state):
                raise OfflineEvidenceError(
                    "snapshot input file changed while it was opened"
                )
            payload = _read_open_bytes(
                descriptor,
                opened,
                f"snapshot input file {relative}",
            )
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if relative in _SNAPSHOT_PACKAGE_ANCHORS:
            if payload != _SNAPSHOT_PACKAGE_ANCHORS[relative]:
                raise OfflineEvidenceError("snapshot package anchor byte identity mismatch")
            return
        file_records.append(
            {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
        )
        if file_sink is not None:
            file_sink(relative, payload)

    def visit(directory_fd: int, relative_prefix: str) -> None:
        directory_paths.append(relative_prefix)
        try:
            entries = sorted(os.scandir(directory_fd), key=lambda item: item.name)
        except OSError as exc:
            raise OfflineEvidenceError("snapshot input tree could not be inspected") from exc
        folded_names: dict[str, str] = {}
        for entry in entries:
            name = _canonical_snapshot_name(entry.name, "snapshot input tree")
            folded = unicodedata.normalize("NFC", name).casefold()
            if folded in folded_names:
                raise OfflineEvidenceError(
                    "snapshot input contains a case or Unicode alias collision"
                )
            folded_names[folded] = name
        for entry in entries:
            name = entry.name
            relative = f"{relative_prefix}/{name}"
            try:
                state = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise OfflineEvidenceError("snapshot input could not be inspected") from exc
            if stat.S_ISLNK(state.st_mode):
                raise OfflineEvidenceError("snapshot input contains a symlink")
            if stat.S_ISDIR(state.st_mode):
                _safe_mode(state, f"snapshot input directory {relative}", directory=True)
                if name == "__pycache__":
                    continue
                child_fd: int | None = None
                try:
                    child_fd = os.open(name, directory_flags, dir_fd=directory_fd)
                    opened = os.fstat(child_fd)
                    if _state_identity(opened) != _state_identity(state):
                        raise OfflineEvidenceError(
                            "snapshot input directory changed while it was opened"
                        )
                    visit(child_fd, relative)
                finally:
                    if child_fd is not None:
                        os.close(child_fd)
                continue
            if not stat.S_ISREG(state.st_mode):
                raise OfflineEvidenceError("snapshot input contains a special node")
            if Path(name).suffix in {".pyc", ".pyo"}:
                if state.st_nlink != 1:
                    raise OfflineEvidenceError(
                        "snapshot input contains a hard-linked generated file"
                    )
                continue
            consume_file(directory_fd, name, relative, state)

    for relative_root in roots:
        root_fd = _open_relative_directory_fd(
            repo_fd,
            relative_root,
            f"snapshot tree root {relative_root}",
        )
        try:
            visit(root_fd, relative_root)
        finally:
            os.close(root_fd)

    for relative in files:
        payload = _stable_relative_file_bytes(
            repo_fd,
            relative,
            f"snapshot exact file {relative}",
        )
        file_records.append(
            {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
        )
        if file_sink is not None:
            file_sink(relative, payload)

    directory_paths.sort()
    file_records.sort(key=lambda item: item["path"])
    file_paths = [item["path"] for item in file_records]
    if len(file_paths) != len(set(file_paths)):
        raise OfflineEvidenceError("snapshot input file coverage is not unique")
    contract = {
        "schema_version": TEST_SCOPE_SCHEMA_VERSION,
        "tree_roots": list(roots),
        "exact_files": list(files),
        "directory_count": len(directory_paths),
        "directory_set_sha256": _identity_sha256(directory_paths),
        "file_count": len(file_records),
        "path_set_sha256": _identity_sha256(file_paths),
        "file_set_sha256": _identity_sha256(file_records),
        "package_anchors_sha256": _identity_sha256(
            [
                {
                    "path": path,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
                for path, payload in sorted(_SNAPSHOT_PACKAGE_ANCHORS.items())
            ]
        ),
    }
    contract["identity_sha256"] = _identity_sha256(contract)
    return contract


def _snapshot_live_state_identity_from_fd(
    repo_fd: int,
    *,
    tree_roots: Sequence[str],
    exact_files: Sequence[str],
) -> str:
    records: dict[str, dict[str, Any]] = {}

    def add(relative: str, kind: str, state: os.stat_result) -> None:
        record = {
            "path": relative,
            "kind": kind,
            "device": state.st_dev,
            "inode": state.st_ino,
            "mode": state.st_mode,
            "nlink": state.st_nlink,
            "size": state.st_size,
            "mtime_ns": state.st_mtime_ns,
            "ctime_ns": state.st_ctime_ns,
        }
        previous = records.get(relative)
        if previous is not None and previous != record:
            raise OfflineEvidenceError(
                "repository input state changed while it was inspected"
            )
        records[relative] = record

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )

    def visit(directory_fd: int, relative_prefix: str) -> None:
        add(relative_prefix, "directory", os.fstat(directory_fd))
        try:
            entries = sorted(os.scandir(directory_fd), key=lambda item: item.name)
        except OSError as exc:
            raise OfflineEvidenceError("repository input state could not be inspected") from exc
        folded: set[str] = set()
        for entry in entries:
            name = _canonical_snapshot_name(entry.name, "repository input state")
            key = unicodedata.normalize("NFC", name).casefold()
            if key in folded:
                raise OfflineEvidenceError(
                    "repository input state contains a case or Unicode alias collision"
                )
            folded.add(key)
        for entry in entries:
            relative = f"{relative_prefix}/{entry.name}"
            state = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(state.st_mode):
                raise OfflineEvidenceError("repository input state contains a symlink")
            if stat.S_ISDIR(state.st_mode):
                if entry.name == "__pycache__":
                    continue
                child_fd = os.open(entry.name, directory_flags, dir_fd=directory_fd)
                try:
                    if _state_identity(os.fstat(child_fd)) != _state_identity(state):
                        raise OfflineEvidenceError(
                            "repository input directory changed while it was opened"
                        )
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(state.st_mode):
                raise OfflineEvidenceError("repository input state contains a special node")
            if Path(entry.name).suffix in {".pyc", ".pyo"}:
                continue
            add(relative, "file", state)

    for relative_root in tree_roots:
        relative_root = _canonical_relative(relative_root, "snapshot tree root")
        root_fd = _open_relative_directory_fd(
            repo_fd,
            relative_root,
            f"snapshot tree root {relative_root}",
        )
        try:
            visit(root_fd, relative_root)
        finally:
            os.close(root_fd)

    for relative in exact_files:
        relative = _canonical_relative(relative, "snapshot exact file")
        parts = PurePosixPath(relative).parts
        parent_fd = (
            os.dup(repo_fd)
            if len(parts) == 1
            else _open_relative_directory_fd(
                repo_fd,
                "/".join(parts[:-1]),
                f"snapshot exact file {relative} parent",
            )
        )
        try:
            state = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(state.st_mode) or stat.S_ISLNK(state.st_mode):
                raise OfflineEvidenceError(
                    "repository exact input state is not a regular file"
                )
            add(relative, "file", state)
        finally:
            os.close(parent_fd)
    return _identity_sha256([records[path] for path in sorted(records)])


def _snapshot_materialized_state_identity_from_fd(root_fd: int) -> str:
    """Return a ctime-bound identity for every node in a private snapshot."""

    records: list[dict[str, Any]] = []
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )

    def record(relative: str, kind: str, state: os.stat_result) -> None:
        expected_mode = 0o500 if kind == "directory" else 0o400
        if stat.S_IMODE(state.st_mode) != expected_mode:
            raise OfflineEvidenceError("private snapshot permissions changed")
        if kind == "file" and state.st_nlink != 1:
            raise OfflineEvidenceError("private snapshot contains a hard-linked file")
        records.append(
            {
                "path": relative,
                "kind": kind,
                "device": state.st_dev,
                "inode": state.st_ino,
                "mode": state.st_mode,
                "nlink": state.st_nlink,
                "size": state.st_size,
                "mtime_ns": state.st_mtime_ns,
                "ctime_ns": state.st_ctime_ns,
            }
        )

    def visit(directory_fd: int, relative_prefix: str) -> None:
        record(relative_prefix, "directory", os.fstat(directory_fd))
        try:
            entries = sorted(os.scandir(directory_fd), key=lambda entry: entry.name)
        except OSError as exc:
            raise OfflineEvidenceError("private snapshot state could not be inspected") from exc
        folded: set[str] = set()
        for entry in entries:
            name = _canonical_snapshot_name(entry.name, "private snapshot state")
            key = unicodedata.normalize("NFC", name).casefold()
            if key in folded:
                raise OfflineEvidenceError(
                    "private snapshot contains a case or Unicode alias collision"
                )
            folded.add(key)
        for entry in entries:
            relative = (
                entry.name
                if relative_prefix == "."
                else f"{relative_prefix}/{entry.name}"
            )
            try:
                state = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise OfflineEvidenceError(
                    "private snapshot state could not be inspected"
                ) from exc
            if stat.S_ISLNK(state.st_mode):
                raise OfflineEvidenceError("private snapshot contains a symlink")
            if stat.S_ISDIR(state.st_mode):
                child_fd = os.open(entry.name, directory_flags, dir_fd=directory_fd)
                try:
                    if _state_identity(os.fstat(child_fd)) != _state_identity(state):
                        raise OfflineEvidenceError(
                            "private snapshot directory changed while inspected"
                        )
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(state.st_mode):
                raise OfflineEvidenceError("private snapshot contains a special node")
            descriptor = os.open(entry.name, file_flags, dir_fd=directory_fd)
            try:
                if _state_identity(os.fstat(descriptor)) != _state_identity(state):
                    raise OfflineEvidenceError(
                        "private snapshot file changed while inspected"
                    )
                record(relative, "file", state)
            finally:
                os.close(descriptor)

    visit(root_fd, ".")
    return _identity_sha256(records)


@dataclass
class _PrivateSnapshot:
    path: Path
    root_fd: int
    parent_fd: int
    name: str
    root_identity: tuple[int, int, int]
    identity: dict[str, Any]
    live_state_identity_sha256: str
    materialized_state_identity_sha256: str
    tree_roots: tuple[str, ...]
    exact_files: tuple[str, ...]
    source_is_materialized: bool


@dataclass
class _ComponentScratch:
    path: Path
    root_fd: int
    parent_fd: int
    name: str
    root_identity: dict[str, int]



@dataclass
class _SealedTessdataSnapshot:
    identity: dict[str, Any]
    path: Path
    root_fd: int
    parent_fd: int
    name: str
    root_identity: tuple[int, int, int]
    materialized_state_identity_sha256: str


def _expected_sealed_tessdata_identity(
    source_identity: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(source_identity, Mapping)
        or source_identity.get("schema_version")
        != "cloud-v2-approved-ocr-tessdata-input-v1"
        or source_identity.get("file_names")
        != list(_OCR_TESSDATA_SNAPSHOT_NAMES)
        or not isinstance(source_identity.get("files"), list)
    ):
        raise OfflineEvidenceError("approved OCR tessdata identity is malformed")
    source_by_name = {
        record.get("name"): record
        for record in source_identity["files"]
        if isinstance(record, Mapping)
    }
    if set(source_by_name) != set(_OCR_TESSDATA_SNAPSHOT_NAMES):
        raise OfflineEvidenceError("approved OCR tessdata identity is malformed")
    records = []
    for name in _OCR_TESSDATA_SNAPSHOT_NAMES:
        record = source_by_name[name]
        if (
            not isinstance(record.get("sha256"), str)
            or record["sha256"] != _OCR_TESSDATA_EXPECTED_SHA256[name]
            or type(record.get("size")) is not int
            or record["size"] <= 0
        ):
            raise OfflineEvidenceError("approved OCR tessdata identity is malformed")
        records.append(
            {
                "name": name,
                "mode": 0o400,
                "size": record["size"],
                "sha256": record["sha256"],
            }
        )
    value: dict[str, Any] = {
        "schema_version": "cloud-v2-private-ocr-tessdata-snapshot-v1",
        "source_identity_sha256": source_identity.get("identity_sha256"),
        "root_mode": 0o500,
        "file_count": len(records),
        "file_names": list(_OCR_TESSDATA_SNAPSHOT_NAMES),
        "file_set_sha256": _identity_sha256(records),
        "files": records,
    }
    if (
        not isinstance(value["source_identity_sha256"], str)
        or not _SHA256.fullmatch(value["source_identity_sha256"])
    ):
        raise OfflineEvidenceError("approved OCR tessdata identity is malformed")
    value["identity_sha256"] = _identity_sha256(value)
    return value


def _build_sealed_tessdata_snapshot(
    source: _ApprovedTessdataInput,
) -> _SealedTessdataSnapshot:
    _revalidate_approved_tessdata_input(source)
    path = Path(tempfile.mkdtemp(prefix="cloud-v2-ocr-tessdata-")).resolve(
        strict=True
    )
    parent_fd: int | None = None
    root_fd: int | None = None
    try:
        _parent, parent_fd = _open_directory_fd(
            path.parent,
            "private OCR tessdata snapshot parent",
        )
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        root_fd = os.open(
            path.name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o700
            or opened.st_uid != os.geteuid()
            or _state_identity(opened) != _state_identity(before)
        ):
            raise OfflineEvidenceError(
                "private OCR tessdata snapshot root is not owned and private"
            )
        records: list[dict[str, Any]] = []
        for name in _OCR_TESSDATA_SNAPSHOT_NAMES:
            held = source.files[name]
            descriptor = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=root_fd,
            )
            try:
                written = 0
                while written < len(held.payload):
                    count = os.write(descriptor, held.payload[written:])
                    if count <= 0:
                        raise OfflineEvidenceError(
                            f"private OCR tessdata could not be written: {name}"
                        )
                    written += count
                os.fsync(descriptor)
                os.fchmod(descriptor, 0o400)
            finally:
                os.close(descriptor)
            payload, binding = _stable_relative_file_binding(
                root_fd,
                name,
                f"private OCR tessdata {name}",
                max_bytes=16 * 1024 * 1024,
            )
            if payload != held.payload:
                raise OfflineEvidenceError(
                    f"private OCR tessdata differs from held bytes: {name}"
                )
            records.append(
                {
                    "name": name,
                    "mode": stat.S_IMODE(binding["mode"]),
                    "size": binding["size"],
                    "sha256": binding["sha256"],
                }
            )
        os.fchmod(root_fd, 0o500)
        os.fsync(root_fd)
        _revalidate_approved_tessdata_input(source)
        identity = _expected_sealed_tessdata_identity(source.identity)
        if records != identity["files"]:
            raise OfflineEvidenceError(
                "private OCR tessdata snapshot identity differs from held bytes"
            )
        snapshot = _SealedTessdataSnapshot(
            identity=identity,
            path=path,
            root_fd=root_fd,
            parent_fd=parent_fd,
            name=path.name,
            root_identity=_inode_identity(os.fstat(root_fd)),
            materialized_state_identity_sha256=(
                _snapshot_materialized_state_identity_from_fd(root_fd)
            ),
        )
        _revalidate_sealed_tessdata_snapshot(snapshot)
        return snapshot
    except Exception as exc:
        cleanup_error: Exception | None = None
        if root_fd is not None and parent_fd is not None:
            try:
                _quarantine_entry_if_owned(
                    parent_fd,
                    path.name,
                    root_fd,
                    field="failed private OCR tessdata snapshot",
                    directory=True,
                )
                _clear_quarantined_directory(
                    root_fd,
                    field="failed private OCR tessdata snapshot cleanup",
                )
            except Exception as cleanup_exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    cleanup_exc,
                    label="failed private OCR tessdata snapshot quarantine",
                )
        for label, descriptor in (
            ("failed private OCR tessdata root", root_fd),
            ("failed private OCR tessdata parent", parent_fd),
        ):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except Exception as cleanup_exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error, cleanup_exc, label=label
                )
        if cleanup_error is not None:
            exc.add_note(
                "secondary OCR tessdata snapshot cleanup failure: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        raise


def _revalidate_sealed_tessdata_snapshot(
    snapshot: _SealedTessdataSnapshot,
) -> None:
    _revalidate_directory_path(
        snapshot.path,
        snapshot.root_fd,
        "private OCR tessdata snapshot",
    )
    root_state = os.fstat(snapshot.root_fd)
    if (
        _inode_identity(root_state) != snapshot.root_identity
        or stat.S_IMODE(root_state.st_mode) != 0o500
        or tuple(sorted(os.listdir(snapshot.root_fd)))
        != _OCR_TESSDATA_SNAPSHOT_NAMES
        or _snapshot_materialized_state_identity_from_fd(snapshot.root_fd)
        != snapshot.materialized_state_identity_sha256
    ):
        raise OfflineEvidenceError(
            "private OCR tessdata snapshot identity changed"
        )
    records: list[dict[str, Any]] = []
    for name in _OCR_TESSDATA_SNAPSHOT_NAMES:
        payload, binding = _stable_relative_file_binding(
            snapshot.root_fd,
            name,
            f"private OCR tessdata {name}",
            max_bytes=16 * 1024 * 1024,
        )
        records.append(
            {
                "name": name,
                "mode": stat.S_IMODE(binding["mode"]),
                "size": binding["size"],
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    expected = {
        field: snapshot.identity[field]
        for field in (
            "schema_version",
            "source_identity_sha256",
            "root_mode",
            "file_count",
            "file_names",
            "file_set_sha256",
            "files",
        )
    }
    current = {
        **{field: expected[field] for field in (
            "schema_version",
            "source_identity_sha256",
        )},
        "root_mode": stat.S_IMODE(root_state.st_mode),
        "file_count": len(records),
        "file_names": list(_OCR_TESSDATA_SNAPSHOT_NAMES),
        "file_set_sha256": _identity_sha256(records),
        "files": records,
    }
    if current != expected or snapshot.identity["identity_sha256"] != _identity_sha256(
        expected
    ):
        raise OfflineEvidenceError("private OCR tessdata snapshot bytes changed")


def _close_sealed_tessdata_snapshot(snapshot: _SealedTessdataSnapshot) -> None:
    primary_error: BaseException | None = None
    try:
        _revalidate_sealed_tessdata_snapshot(snapshot)
        _quarantine_entry_if_owned(
            snapshot.parent_fd,
            snapshot.name,
            snapshot.root_fd,
            field="private OCR tessdata snapshot",
            directory=True,
        )
        _clear_quarantined_directory(
            snapshot.root_fd,
            field="private OCR tessdata snapshot cleanup",
        )
        if os.listdir(snapshot.root_fd):
            raise OfflineEvidenceError(
                "private OCR tessdata snapshot cleanup is incomplete"
            )
    except BaseException:
        primary_error = sys.exception()
        raise
    finally:
        cleanup_error: Exception | None = None
        for label, descriptor in (
            ("private OCR tessdata root", snapshot.root_fd),
            ("private OCR tessdata parent", snapshot.parent_fd),
        ):
            try:
                os.close(descriptor)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error, exc, label=label
                )
        _finish_process_cleanup(cleanup_error, primary_error=primary_error)

def _scratch_root_identity(state: os.stat_result) -> dict[str, int]:
    return {
        "device": state.st_dev,
        "inode": state.st_ino,
        "file_type": stat.S_IFMT(state.st_mode),
        "mode": stat.S_IMODE(state.st_mode),
        "uid": state.st_uid,
        "gid": state.st_gid,
    }


def _revalidate_component_scratch(scratch: _ComponentScratch) -> None:
    try:
        path_state = os.stat(
            scratch.name,
            dir_fd=scratch.parent_fd,
            follow_symlinks=False,
        )
        held_state = os.fstat(scratch.root_fd)
    except OSError as exc:
        raise OfflineEvidenceError("component scratch is unavailable") from exc
    if (
        _scratch_root_identity(path_state) != scratch.root_identity
        or _scratch_root_identity(held_state) != scratch.root_identity
        or not stat.S_ISDIR(held_state.st_mode)
        or stat.S_IMODE(held_state.st_mode) != 0o700
        or held_state.st_uid != os.geteuid()
    ):
        raise OfflineEvidenceError("component scratch identity changed")


def _scratch_inventory(root_fd: int) -> dict[str, Any]:
    records: list[dict[str, Any]] = []

    def visit(directory_fd: int, prefix: str) -> None:
        try:
            names = os.listdir(directory_fd)
        except OSError as exc:
            raise OfflineEvidenceError("component scratch could not be inventoried") from exc
        folded: dict[str, str] = {}
        for name in names:
            canonical = _canonical_snapshot_name(name, "component scratch")
            key = unicodedata.normalize("NFC", canonical).casefold()
            if key in folded:
                raise OfflineEvidenceError(
                    "component scratch contains a case or Unicode alias collision"
                )
            folded[key] = canonical
        for name in sorted(names):
            relative = name if prefix == "." else f"{prefix}/{name}"
            try:
                before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise OfflineEvidenceError("component scratch node is unavailable") from exc
            common = {
                "path": relative,
                "device": before.st_dev,
                "inode": before.st_ino,
                "mode": before.st_mode,
                "nlink": before.st_nlink,
                "size": before.st_size,
                "mtime_ns": before.st_mtime_ns,
                "ctime_ns": before.st_ctime_ns,
            }
            if stat.S_ISDIR(before.st_mode):
                child = _open_relative_directory_fd(
                    directory_fd,
                    name,
                    "component scratch directory",
                )
                try:
                    records.append({**common, "kind": "directory"})
                    visit(child, relative)
                finally:
                    os.close(child)
                continue
            if stat.S_ISLNK(before.st_mode):
                try:
                    target = os.readlink(name, dir_fd=directory_fd)
                    after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as exc:
                    raise OfflineEvidenceError(
                        "component scratch symlink is unavailable"
                    ) from exc
                if _state_identity(after) != _state_identity(before):
                    raise OfflineEvidenceError("component scratch symlink changed")
                records.append(
                    {
                        **common,
                        "kind": "symlink",
                        "target_sha256": hashlib.sha256(
                            target.encode("utf-8")
                        ).hexdigest(),
                    }
                )
                continue
            if stat.S_ISREG(before.st_mode):
                descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=directory_fd,
                )
                try:
                    opened = os.fstat(descriptor)
                    if _state_identity(opened) != _state_identity(before):
                        raise OfflineEvidenceError("component scratch file changed")
                    payload = _read_open_bytes(
                        descriptor,
                        opened,
                        "component scratch file",
                    )
                finally:
                    os.close(descriptor)
                records.append(
                    {
                        **common,
                        "kind": "file",
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
                continue
            records.append({**common, "kind": "special"})

    visit(root_fd, ".")
    value: dict[str, Any] = {
        "node_count": len(records),
        "node_set_sha256": _identity_sha256(records),
    }
    return value


def _quarantine_unheld_entry(
    parent_fd: int,
    name: str,
    expected: os.stat_result,
    *,
    field: str,
) -> str:
    quarantine_name: str | None = None
    for index in range(32):
        candidate = f".{name}.cleanup-{index:02d}"
        try:
            _atomic_noreplace_rename(
                name,
                candidate,
                directory_descriptor=parent_fd,
            )
        except FileExistsError:
            continue
        except (OfflineEvidenceError, OSError) as exc:
            raise OfflineEvidenceError(f"{field} could not be quarantined") from exc
        quarantine_name = candidate
        break
    if quarantine_name is None:
        raise OfflineEvidenceError(f"{field} quarantine namespace is exhausted")
    try:
        os.fsync(parent_fd)
        quarantined = os.stat(
            quarantine_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if _rename_stable_state_identity(
            quarantined
        ) != _rename_stable_state_identity(expected):
            raise OfflineEvidenceError(f"{field} quarantine identity changed")
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OfflineEvidenceError(
                f"{field} was replaced while its owned entry was quarantined"
            )
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} quarantine could not be verified") from exc
    return quarantine_name


def _clear_quarantined_directory(directory_fd: int, *, field: str) -> None:
    """Clear only entries proven inside an already quarantined private root."""

    try:
        os.fchmod(directory_fd, 0o700)
        names = tuple(os.listdir(directory_fd))
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} could not be prepared for cleanup") from exc
    folded: set[str] = set()
    for name in names:
        canonical = _canonical_snapshot_name(name, field)
        key = unicodedata.normalize("NFC", canonical).casefold()
        if key in folded:
            raise OfflineEvidenceError(f"{field} contains a cleanup alias collision")
        folded.add(key)
    for name in names:
        try:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise OfflineEvidenceError(f"{field} entry is unavailable") from exc
        if stat.S_ISDIR(before.st_mode):
            child = _open_relative_directory_fd(directory_fd, name, field)
            quarantine_name: str | None = None
            try:
                if _state_identity(os.fstat(child)) != _state_identity(before):
                    raise OfflineEvidenceError(f"{field} directory changed while opened")
                quarantine_name = _quarantine_entry_if_owned(
                    directory_fd,
                    name,
                    child,
                    field=field,
                    directory=True,
                )
                _clear_quarantined_directory(child, field=field)
                if os.listdir(child):
                    raise OfflineEvidenceError(f"{field} directory cleanup is incomplete")
                quarantined = os.stat(
                    quarantine_name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if _inode_identity(quarantined) != _inode_identity(os.fstat(child)):
                    raise OfflineEvidenceError(f"{field} directory quarantine changed")
                os.rmdir(quarantine_name, dir_fd=directory_fd)
            finally:
                os.close(child)
            continue
        quarantine_name = _quarantine_unheld_entry(
            directory_fd,
            name,
            before,
            field=field,
        )
        try:
            quarantined = os.stat(
                quarantine_name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if _rename_stable_state_identity(
                quarantined
            ) != _rename_stable_state_identity(before):
                raise OfflineEvidenceError(f"{field} entry quarantine changed")
            os.unlink(quarantine_name, dir_fd=directory_fd)
        except OfflineEvidenceError:
            raise
        except OSError as exc:
            raise OfflineEvidenceError(f"{field} entry could not be removed") from exc
    if os.listdir(directory_fd):
        raise OfflineEvidenceError(f"{field} received a late cleanup entry")


def _create_component_scratch(component: str) -> _ComponentScratch:
    try:
        raw_path = Path(tempfile.mkdtemp(prefix=f"cloud-v2-{component}-scratch-"))
        raw_path.chmod(0o700)
        path = raw_path.resolve(strict=True)
        _parent, parent_fd = _open_directory_fd(
            path.parent,
            "component scratch parent",
        )
        _reject_component_alias(parent_fd, path.name, "component scratch")
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        root_fd = os.open(
            path.name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(root_fd)
    except Exception:
        if "root_fd" in locals():
            try:
                if "parent_fd" in locals() and "path" in locals():
                    _quarantine_entry_if_owned(
                        parent_fd,
                        path.name,
                        root_fd,
                        field="failed component scratch",
                        directory=True,
                    )
            except (OSError, OfflineEvidenceError):
                pass
            os.close(root_fd)
        if "parent_fd" in locals():
            os.close(parent_fd)
        raise
    identity = _scratch_root_identity(opened)
    if (
        identity != _scratch_root_identity(before)
        or not stat.S_ISDIR(opened.st_mode)
        or stat.S_IMODE(opened.st_mode) != 0o700
        or opened.st_uid != os.geteuid()
        or os.listdir(root_fd)
    ):
        try:
            _quarantine_entry_if_owned(
                parent_fd,
                path.name,
                root_fd,
                field="invalid component scratch",
                directory=True,
            )
        except (OSError, OfflineEvidenceError):
            pass
        os.close(root_fd)
        os.close(parent_fd)
        raise OfflineEvidenceError("component scratch is not private and empty")
    return _ComponentScratch(
        path=path,
        root_fd=root_fd,
        parent_fd=parent_fd,
        name=path.name,
        root_identity=identity,
    )


def _write_component_scratch_input(
    scratch: _ComponentScratch,
    name: str,
    payload: bytes,
    field: str,
) -> dict[str, Any]:
    canonical = _canonical_relative(name, field)
    if len(PurePosixPath(canonical).parts) != 1:
        raise OfflineEvidenceError(f"{field} must be a direct scratch child")
    if not isinstance(payload, bytes):
        raise OfflineEvidenceError(f"{field} payload must be bytes")
    _revalidate_component_scratch(scratch)
    _reject_component_alias(scratch.root_fd, canonical, field)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            canonical,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=scratch.root_fd,
        )
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OfflineEvidenceError(f"{field} could not be written completely")
            written += count
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} could not be staged safely") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    _revalidate_component_scratch(scratch)
    staged, binding = _stable_relative_file_binding(
        scratch.root_fd,
        canonical,
        field,
        max_bytes=16 * 1024 * 1024,
    )
    if staged != payload:
        raise OfflineEvidenceError(f"{field} changed while it was staged")
    return binding


def _close_component_scratch(scratch: _ComponentScratch) -> dict[str, Any]:
    primary_error: BaseException | None = None
    try:
        _revalidate_component_scratch(scratch)
        inventory = _scratch_inventory(scratch.root_fd)
        if _scratch_inventory(scratch.root_fd) != inventory:
            raise OfflineEvidenceError("component scratch changed before cleanup")
        _quarantine_entry_if_owned(
            scratch.parent_fd,
            scratch.name,
            scratch.root_fd,
            field="component scratch root",
            directory=True,
        )
        _clear_quarantined_directory(
            scratch.root_fd,
            field="component scratch cleanup",
        )
        if os.listdir(scratch.root_fd):
            raise OfflineEvidenceError("component scratch cleanup is incomplete")
        receipt: dict[str, Any] = {
            "schema_version": "cloud-v2-component-scratch-v1",
            "root_device": scratch.root_identity["device"],
            "root_inode": scratch.root_identity["inode"],
            "root_mode": scratch.root_identity["mode"],
            "root_uid": scratch.root_identity["uid"],
            "root_gid": scratch.root_identity["gid"],
            "initially_empty": True,
            "post_run_inventory": inventory,
            "cleanup_verified_empty": True,
        }
        receipt["identity_sha256"] = _identity_sha256(receipt)
        return receipt
    except BaseException:
        primary_error = sys.exception()
        raise
    finally:
        cleanup_error: Exception | None = None
        for label, descriptor in (
            ("component scratch root descriptor", scratch.root_fd),
            ("component scratch parent descriptor", scratch.parent_fd),
        ):
            try:
                os.close(descriptor)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label=label,
                )
        _finish_process_cleanup(cleanup_error, primary_error=primary_error)


def _close_component_scratch_pair(
    denial_probe: _ComponentScratch | None,
    scratch: _ComponentScratch,
    *,
    primary_error: BaseException | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    cleanup_error: Exception | None = None
    denial_receipt = None
    if denial_probe is not None:
        try:
            denial_receipt = _close_component_scratch(denial_probe)
        except Exception as exc:
            cleanup_error = exc
    scratch_receipt = None
    try:
        scratch_receipt = _close_component_scratch(scratch)
    except Exception as exc:
        if cleanup_error is None:
            cleanup_error = exc
    _finish_process_cleanup(cleanup_error, primary_error=primary_error)
    return denial_receipt, scratch_receipt


def _build_private_snapshot(
    repo_fd: int,
    *,
    tree_roots: Sequence[str],
    exact_files: Sequence[str],
) -> _PrivateSnapshot:
    source_is_parent_snapshot = _formal_materialized_snapshot_matches(repo_fd)
    _reject_repository_import_shadows(
        repo_fd,
        allow_snapshot_package_anchors=source_is_parent_snapshot,
    )
    snapshot_path = Path(
        tempfile.mkdtemp(prefix="cloud-v2-offline-snapshot-")
    ).resolve(strict=True)
    parent_fd: int | None = None
    root_fd: int | None = None
    try:
        _parent, parent_fd = _open_directory_fd(
            snapshot_path.parent,
            "private test snapshot parent",
        )
        before = os.stat(
            snapshot_path.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        root_fd = os.open(
            snapshot_path.name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or stat.S_ISLNK(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o700
            or opened.st_uid != os.geteuid()
            or _state_identity(opened) != _state_identity(before)
        ):
            raise OfflineEvidenceError("private snapshot root is not owned and private")
    except Exception:
        if root_fd is not None:
            os.close(root_fd)
        if parent_fd is not None:
            os.close(parent_fd)
        raise

    def sink(relative: str, payload: bytes) -> None:
        target = snapshot_path / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            with target.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            target.chmod(0o400)
        except OSError as exc:
            raise OfflineEvidenceError(
                f"private snapshot file could not be materialized: {relative}"
            ) from exc

    try:
        identity = _snapshot_source_identity_from_fd(
            repo_fd,
            tree_roots=tree_roots,
            exact_files=exact_files,
            materialized=source_is_parent_snapshot,
            file_sink=sink,
        )
        for relative, payload in sorted(_SNAPSHOT_PACKAGE_ANCHORS.items()):
            sink(relative, payload)
        for directory in sorted(
            (path for path in snapshot_path.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            directory.chmod(0o500)
        _revalidate_directory_path(
            snapshot_path,
            root_fd,
            "private test snapshot",
        )
        materialized_identity = _snapshot_source_identity_from_fd(
            root_fd,
            tree_roots=tree_roots,
            exact_files=exact_files,
            materialized=True,
        )
        if materialized_identity != identity:
            raise OfflineEvidenceError("private snapshot differs from its source bytes")
        for relative, expected_payload in sorted(_SNAPSHOT_PACKAGE_ANCHORS.items()):
            if _stable_relative_file_bytes(
                root_fd,
                relative,
                f"private snapshot package anchor {relative}",
            ) != expected_payload:
                raise OfflineEvidenceError("snapshot package anchor byte identity mismatch")
        current_live = _snapshot_source_identity_from_fd(
            repo_fd,
            tree_roots=tree_roots,
            exact_files=exact_files,
            materialized=source_is_parent_snapshot,
        )
        if current_live != identity:
            raise OfflineEvidenceError(
                "repository inputs changed while the private snapshot was built"
            )
        live_state_identity = _snapshot_live_state_identity_from_fd(
            repo_fd,
            tree_roots=tree_roots,
            exact_files=exact_files,
        )
        snapshot_path.chmod(0o500)
        materialized_state_identity = _snapshot_materialized_state_identity_from_fd(
            root_fd
        )
        return _PrivateSnapshot(
            path=snapshot_path,
            root_fd=root_fd,
            parent_fd=parent_fd,
            name=snapshot_path.name,
            root_identity=_inode_identity(os.fstat(root_fd)),
            identity=identity,
            live_state_identity_sha256=live_state_identity,
            materialized_state_identity_sha256=materialized_state_identity,
            tree_roots=tuple(tree_roots),
            exact_files=tuple(exact_files),
            source_is_materialized=source_is_parent_snapshot,
        )
    except Exception as exc:
        cleanup_error: Exception | None = None
        try:
            _quarantine_entry_if_owned(
                parent_fd,
                snapshot_path.name,
                root_fd,
                field="failed private snapshot",
                directory=True,
            )
            _clear_quarantined_directory(
                root_fd,
                field="failed private snapshot cleanup",
            )
        except Exception as cleanup_exc:
            cleanup_error = _merge_cleanup_error(
                cleanup_error,
                cleanup_exc,
                label="failed private snapshot quarantine",
            )
        for label, descriptor in (
            ("failed private snapshot root descriptor", root_fd),
            ("failed private snapshot parent descriptor", parent_fd),
        ):
            try:
                os.close(descriptor)
            except Exception as cleanup_exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    cleanup_exc,
                    label=label,
                )
        if cleanup_error is not None:
            exc.add_note(
                "secondary private snapshot cleanup failure: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        raise


def _revalidate_private_snapshot(snapshot: _PrivateSnapshot) -> None:
    _revalidate_directory_path(snapshot.path, snapshot.root_fd, "private test snapshot")
    if (
        _snapshot_materialized_state_identity_from_fd(snapshot.root_fd)
        != snapshot.materialized_state_identity_sha256
    ):
        raise OfflineEvidenceError("private snapshot state changed during execution")
    current = _snapshot_source_identity_from_fd(
        snapshot.root_fd,
        tree_roots=snapshot.tree_roots,
        exact_files=snapshot.exact_files,
        materialized=True,
    )
    if current != snapshot.identity:
        raise OfflineEvidenceError("private snapshot changed during execution")


def _revalidate_live_snapshot_inputs(repo_fd: int, snapshot: _PrivateSnapshot) -> None:
    _reject_repository_import_shadows(
        repo_fd,
        allow_snapshot_package_anchors=snapshot.source_is_materialized,
    )
    state_before = _snapshot_live_state_identity_from_fd(
        repo_fd,
        tree_roots=snapshot.tree_roots,
        exact_files=snapshot.exact_files,
    )
    if state_before != snapshot.live_state_identity_sha256:
        raise OfflineEvidenceError("repository input state changed during snapshot execution")
    current = _snapshot_source_identity_from_fd(
        repo_fd,
        tree_roots=snapshot.tree_roots,
        exact_files=snapshot.exact_files,
        materialized=snapshot.source_is_materialized,
    )
    if current != snapshot.identity:
        raise OfflineEvidenceError("repository inputs changed during snapshot execution")
    state_after = _snapshot_live_state_identity_from_fd(
        repo_fd,
        tree_roots=snapshot.tree_roots,
        exact_files=snapshot.exact_files,
    )
    if state_after != snapshot.live_state_identity_sha256:
        raise OfflineEvidenceError("repository input state changed during snapshot execution")


def _close_private_snapshot(snapshot: _PrivateSnapshot) -> None:
    primary_error: BaseException | None = None
    try:
        if _inode_identity(os.fstat(snapshot.root_fd)) != snapshot.root_identity:
            raise OfflineEvidenceError("private snapshot held identity changed")
        _quarantine_entry_if_owned(
            snapshot.parent_fd,
            snapshot.name,
            snapshot.root_fd,
            field="private snapshot root",
            directory=True,
        )
        _clear_quarantined_directory(
            snapshot.root_fd,
            field="private snapshot cleanup",
        )
        if os.listdir(snapshot.root_fd):
            raise OfflineEvidenceError("private snapshot cleanup is incomplete")
    except BaseException:
        primary_error = sys.exception()
        raise
    finally:
        cleanup_error: Exception | None = None
        for label, descriptor in (
            ("private snapshot root descriptor", snapshot.root_fd),
            ("private snapshot parent descriptor", snapshot.parent_fd),
        ):
            try:
                os.close(descriptor)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label=label,
                )
        _finish_process_cleanup(cleanup_error, primary_error=primary_error)


def _test_scope_identity_from_fd(
    repo_fd: int,
    *,
    materialized: bool = False,
    tree_roots: Sequence[str] | None = None,
    exact_files: Sequence[str] | None = None,
) -> dict[str, Any]:
    if not materialized:
        _reject_repository_import_shadows(repo_fd)
    return _snapshot_source_identity_from_fd(
        repo_fd,
        tree_roots=_TEST_SNAPSHOT_TREE_ROOTS if tree_roots is None else tree_roots,
        exact_files=_TEST_SNAPSHOT_FILES if exact_files is None else exact_files,
        materialized=materialized,
    )


def _canonical_distribution_name(value: object) -> str:
    if not isinstance(value, str) or not value or _has_control_character(value):
        raise OfflineEvidenceError("runtime distribution name is invalid")
    return re.sub(r"[-_.]+", "-", value).lower()


def _runtime_requirements_identity() -> tuple[dict[str, str], dict[str, Any]]:
    lock_path = _module_repository_root() / "deploy/cloud_v2/requirements.lock"
    payload = _stable_file_bytes(
        lock_path,
        "runtime requirements.lock",
        max_bytes=1024 * 1024,
    )
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise OfflineEvidenceError("runtime requirements.lock must be ASCII") from exc
    requirements: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("==") != 1:
            raise OfflineEvidenceError(
                "runtime requirements.lock must use exact name==version pins"
            )
        raw_name, version = line.split("==", 1)
        name = _canonical_distribution_name(raw_name)
        if (
            name in requirements
            or name not in _RUNTIME_MODULES
            or not version
            or version.strip() != version
            or _has_control_character(version)
        ):
            raise OfflineEvidenceError("runtime requirements.lock is invalid")
        requirements[name] = version
    if set(requirements) != set(_RUNTIME_MODULES):
        raise OfflineEvidenceError(
            "runtime requirements.lock differs from the supported module set"
        )
    records = [
        {"name": name, "version": requirements[name]}
        for name in sorted(requirements)
    ]
    return requirements, {
        "path": "deploy/cloud_v2/requirements.lock",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "requirement_count": len(records),
        "requirement_set_sha256": _identity_sha256(records),
    }


def _runtime_distribution_record_identity(
    distribution: importlib.metadata.Distribution,
    *,
    distribution_name: str,
    environment_root: Path,
    covered_paths: set[str],
) -> dict[str, Any]:
    files = tuple(distribution.files or ())
    record_candidates = [
        item
        for item in files
        if item.name == "RECORD" and item.parent.name.endswith(".dist-info")
    ]
    if len(record_candidates) != 1:
        raise OfflineEvidenceError(
            f"runtime distribution RECORD is not unique: {distribution_name}"
        )
    record_path = Path(distribution.locate_file(record_candidates[0]))
    if record_path.is_symlink():
        raise OfflineEvidenceError(
            f"runtime distribution RECORD is a symlink: {distribution_name}"
        )
    try:
        record_path = record_path.resolve(strict=True)
        record_path.relative_to(environment_root)
    except (OSError, ValueError) as exc:
        raise OfflineEvidenceError(
            f"runtime distribution RECORD escapes its venv: {distribution_name}"
        ) from exc
    record_payload = _stable_file_bytes(
        record_path,
        f"runtime distribution {distribution_name} RECORD",
        max_bytes=16 * 1024 * 1024,
        enforce_safe_ancestors=False,
    )
    try:
        record_text = record_payload.decode("utf-8")
        rows = list(csv.reader(record_text.splitlines()))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise OfflineEvidenceError(
            f"runtime distribution RECORD is malformed: {distribution_name}"
        ) from exc
    if not rows:
        raise OfflineEvidenceError(
            f"runtime distribution RECORD is empty: {distribution_name}"
        )

    installed_records: list[dict[str, Any]] = []
    observed_paths: set[str] = set()
    verified_hash_count = 0
    unhashed_count = 0
    for row in rows:
        if len(row) != 3:
            raise OfflineEvidenceError(
                f"runtime distribution RECORD row is malformed: {distribution_name}"
            )
        relative_path, encoded_hash, encoded_size = row
        if (
            not relative_path
            or "\\" in relative_path
            or _has_control_character(relative_path)
            or unicodedata.normalize("NFC", relative_path) != relative_path
        ):
            raise OfflineEvidenceError(
                f"runtime distribution RECORD path is invalid: {distribution_name}"
            )
        unresolved_target = Path(distribution.locate_file(relative_path))
        if unresolved_target.is_symlink():
            raise OfflineEvidenceError(
                f"runtime distribution installed file is a symlink: {distribution_name}"
            )
        try:
            target = unresolved_target.resolve(strict=True)
            target_relative = target.relative_to(environment_root).as_posix()
        except (OSError, ValueError) as exc:
            raise OfflineEvidenceError(
                f"runtime distribution installed file escapes its venv: {distribution_name}"
            ) from exc
        if target_relative in observed_paths:
            raise OfflineEvidenceError(
                f"runtime distribution RECORD contains a duplicate: {distribution_name}"
            )
        observed_paths.add(target_relative)
        covered_paths.add(target_relative)
        try:
            state_before = target.stat(follow_symlinks=False)
        except OSError as exc:
            raise OfflineEvidenceError(
                f"runtime distribution installed file is unavailable: {distribution_name}"
            ) from exc
        payload = _stable_file_bytes(
            target,
            f"runtime distribution {distribution_name} file {target_relative}",
            enforce_safe_ancestors=False,
        )
        try:
            state_after = target.stat(follow_symlinks=False)
        except OSError as exc:
            raise OfflineEvidenceError(
                f"runtime distribution installed file is unavailable: {distribution_name}"
            ) from exc
        if _state_identity(state_before) != _state_identity(state_after):
            raise OfflineEvidenceError(
                f"runtime distribution installed file changed: {distribution_name}"
            )
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if encoded_size:
            if not encoded_size.isascii() or not encoded_size.isdigit():
                raise OfflineEvidenceError(
                    f"runtime distribution RECORD size is invalid: {distribution_name}"
                )
            if int(encoded_size) != len(payload):
                raise OfflineEvidenceError(
                    f"runtime distribution RECORD size mismatch: {distribution_name}"
                )
        if encoded_hash:
            try:
                algorithm, expected_hash = encoded_hash.split("=", 1)
            except ValueError as exc:
                raise OfflineEvidenceError(
                    f"runtime distribution RECORD hash is invalid: {distribution_name}"
                ) from exc
            if algorithm != "sha256" or not expected_hash:
                raise OfflineEvidenceError(
                    f"runtime distribution RECORD hash is unsupported: {distribution_name}"
                )
            observed_hash = base64.urlsafe_b64encode(
                bytes.fromhex(actual_sha256)
            ).rstrip(b"=").decode("ascii")
            if observed_hash != expected_hash:
                raise OfflineEvidenceError(
                    f"runtime distribution RECORD hash mismatch: {distribution_name}"
                )
            verified_hash_count += 1
        else:
            if target != record_path or encoded_size:
                raise OfflineEvidenceError(
                    f"runtime distribution RECORD has an unbound file: {distribution_name}"
                )
            unhashed_count += 1
        installed_records.append(
            {
                "path": target_relative,
                "size": len(payload),
                "sha256": actual_sha256,
                "device": state_after.st_dev,
                "inode": state_after.st_ino,
                "mode": state_after.st_mode,
                "nlink": state_after.st_nlink,
                "mtime_ns": state_after.st_mtime_ns,
                "ctime_ns": state_after.st_ctime_ns,
            }
        )
    if unhashed_count != 1 or record_path.relative_to(environment_root).as_posix() not in observed_paths:
        raise OfflineEvidenceError(
            f"runtime distribution RECORD does not bind itself exactly once: {distribution_name}"
        )
    installed_records.sort(key=lambda item: item["path"])
    return {
        "record_sha256": hashlib.sha256(record_payload).hexdigest(),
        "file_count": len(installed_records),
        "verified_hash_count": verified_hash_count,
        "unhashed_record_count": unhashed_count,
        "path_set_sha256": _identity_sha256(
            [item["path"] for item in installed_records]
        ),
        "installed_file_set_sha256": _identity_sha256(installed_records),
    }


def _runtime_distribution_identity(
    distribution_name: str,
    module_name: str,
    expected_version: str,
    *,
    candidates: Sequence[importlib.metadata.Distribution],
    environment_root: Path,
    library_roots: Sequence[Path],
    covered_paths: set[str],
) -> dict[str, Any]:
    if len(candidates) != 1:
        return {
            "name": distribution_name,
            "expected_version": expected_version,
            "present": False,
            "candidate_count": len(candidates),
        }
    distribution = candidates[0]
    try:
        observed_version = distribution.version
    except Exception:
        observed_version = None
    record_identity = _runtime_distribution_record_identity(
        distribution,
        distribution_name=distribution_name,
        environment_root=environment_root,
        covered_paths=covered_paths,
    )
    spec = importlib.machinery.PathFinder.find_spec(
        module_name,
        [str(root) for root in library_roots],
    )
    origin = None if spec is None else spec.origin
    if not origin or origin in {"built-in", "frozen"}:
        origin_identity = None
    else:
        try:
            origin_path = Path(origin).resolve(strict=True)
        except OSError:
            origin_identity = None
        else:
            in_library_root = any(
                origin_path == root or root in origin_path.parents
                for root in library_roots
            )
            origin_identity = {
                "module": module_name,
                "inside_isolated_library_root": in_library_root,
                "sha256": _stable_file_sha256(
                    origin_path,
                    f"runtime module {module_name}",
                    enforce_safe_ancestors=False,
                ),
            }
    return {
        "name": distribution_name,
        "expected_version": expected_version,
        "present": True,
        "version": observed_version,
        "record_closure": record_identity,
        "module_origin": origin_identity,
    }


def _runtime_tree_identity(root: Path, field: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    try:
        paths = [root, *sorted(root.rglob("*"))]
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} could not be enumerated") from exc
    for path in paths:
        try:
            relative = "." if path == root else path.relative_to(root).as_posix()
            state_before = path.lstat()
            if path.is_symlink():
                target = os.readlink(path)
                state_after = path.lstat()
                if _state_identity(state_before) != _state_identity(state_after):
                    raise OfflineEvidenceError(f"{field} symlink changed during inspection")
                records.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "target_sha256": hashlib.sha256(
                            target.encode("utf-8")
                        ).hexdigest(),
                        "device": state_after.st_dev,
                        "inode": state_after.st_ino,
                        "mode": state_after.st_mode,
                        "nlink": state_after.st_nlink,
                        "size": state_after.st_size,
                        "mtime_ns": state_after.st_mtime_ns,
                        "ctime_ns": state_after.st_ctime_ns,
                    }
                )
                continue
            if path.is_dir():
                state_after = path.stat(follow_symlinks=False)
                if _state_identity(state_before) != _state_identity(state_after):
                    raise OfflineEvidenceError(f"{field} directory changed during inspection")
                records.append(
                    {
                        "path": relative,
                        "kind": "directory",
                        "device": state_after.st_dev,
                        "inode": state_after.st_ino,
                        "mode": state_after.st_mode,
                        "nlink": state_after.st_nlink,
                        "size": state_after.st_size,
                        "mtime_ns": state_after.st_mtime_ns,
                        "ctime_ns": state_after.st_ctime_ns,
                    }
                )
                continue
            if not path.is_file():
                continue
            digest = _stable_file_sha256(
                path,
                f"{field} file {relative}",
                enforce_safe_ancestors=False,
            )
            state_after = path.stat(follow_symlinks=False)
            if _state_identity(state_before) != _state_identity(state_after):
                raise OfflineEvidenceError(f"{field} file changed during inspection")
            records.append(
                {
                    "path": relative,
                    "kind": "file",
                    "sha256": digest,
                    "device": state_after.st_dev,
                    "inode": state_after.st_ino,
                    "mode": state_after.st_mode,
                    "nlink": state_after.st_nlink,
                    "size": state_after.st_size,
                    "mtime_ns": state_after.st_mtime_ns,
                    "ctime_ns": state_after.st_ctime_ns,
                }
            )
        except OSError as exc:
            raise OfflineEvidenceError(f"{field} could not be inspected") from exc
    if not records:
        raise OfflineEvidenceError(f"{field} is empty")
    return {
        "node_count": len(records),
        "path_set_sha256": _identity_sha256([item["path"] for item in records]),
        "node_set_sha256": _identity_sha256(records),
    }


def _runtime_environment_identity() -> dict[str, Any]:
    requirements, requirements_identity = _runtime_requirements_identity()
    paths: list[dict[str, Any]] = []
    resolved_paths: dict[str, Path] = {}
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = sysconfig.get_path(key)
        if not value:
            raise OfflineEvidenceError(f"Python runtime path is unavailable: {key}")
        try:
            resolved = Path(value).resolve(strict=True)
            state = resolved.stat()
        except OSError as exc:
            raise OfflineEvidenceError(f"Python runtime path is unavailable: {key}") from exc
        if not resolved.is_dir() or resolved.is_symlink():
            raise OfflineEvidenceError(f"Python runtime path is unsafe: {key}")
        resolved_paths[key] = resolved
        paths.append(
            {
                "kind": key,
                "path_sha256": hashlib.sha256(str(resolved).encode("utf-8")).hexdigest(),
                "device": state.st_dev,
                "inode": state.st_ino,
                "mode": state.st_mode,
                "nlink": state.st_nlink,
                "size": state.st_size,
                "mtime_ns": state.st_mtime_ns,
                "ctime_ns": state.st_ctime_ns,
            }
        )

    prefix_path = Path(sys.prefix)
    base_prefix_path = Path(sys.base_prefix)
    prefix_is_symlink = prefix_path.is_symlink()
    base_prefix_is_symlink = base_prefix_path.is_symlink()
    try:
        prefix = prefix_path.resolve(strict=True)
        base_prefix = base_prefix_path.resolve(strict=True)
        prefix_state = prefix.stat()
        base_prefix_state = base_prefix.stat()
    except OSError as exc:
        raise OfflineEvidenceError("Python prefix identity is unavailable") from exc
    prefix_identity = {
        "path_sha256": hashlib.sha256(str(prefix).encode("utf-8")).hexdigest(),
        "device": prefix_state.st_dev,
        "inode": prefix_state.st_ino,
        "mode": prefix_state.st_mode,
        "nlink": prefix_state.st_nlink,
        "size": prefix_state.st_size,
        "mtime_ns": prefix_state.st_mtime_ns,
        "ctime_ns": prefix_state.st_ctime_ns,
        "is_symlink": prefix_is_symlink,
    }
    base_prefix_identity = {
        "path_sha256": hashlib.sha256(str(base_prefix).encode("utf-8")).hexdigest(),
        "device": base_prefix_state.st_dev,
        "inode": base_prefix_state.st_ino,
        "mode": base_prefix_state.st_mode,
        "nlink": base_prefix_state.st_nlink,
        "size": base_prefix_state.st_size,
        "mtime_ns": base_prefix_state.st_mtime_ns,
        "ctime_ns": base_prefix_state.st_ctime_ns,
        "is_symlink": base_prefix_is_symlink,
    }
    pyvenv_path = prefix / "pyvenv.cfg"
    if pyvenv_path.is_file() and not pyvenv_path.is_symlink():
        pyvenv_payload = _stable_file_bytes(
            pyvenv_path,
            "Python pyvenv.cfg",
            max_bytes=1024 * 1024,
            enforce_safe_ancestors=False,
        )
        pyvenv_state = pyvenv_path.stat(follow_symlinks=False)
        pyvenv_identity: dict[str, Any] = {
            "present": True,
            "sha256": hashlib.sha256(pyvenv_payload).hexdigest(),
            "size": len(pyvenv_payload),
            "device": pyvenv_state.st_dev,
            "inode": pyvenv_state.st_ino,
            "mode": pyvenv_state.st_mode,
            "nlink": pyvenv_state.st_nlink,
            "mtime_ns": pyvenv_state.st_mtime_ns,
            "ctime_ns": pyvenv_state.st_ctime_ns,
        }
    else:
        pyvenv_identity = {"present": False}

    library_roots = tuple(
        sorted(
            {resolved_paths["purelib"], resolved_paths["platlib"]},
            key=str,
        )
    )
    distribution_catalog: dict[str, list[importlib.metadata.Distribution]] = {}
    installed_distribution_names: list[str] = []
    try:
        installed_distributions = tuple(
            importlib.metadata.distributions(path=[str(path) for path in library_roots])
        )
    except Exception as exc:
        raise OfflineEvidenceError("runtime distributions could not be enumerated") from exc
    for distribution in installed_distributions:
        try:
            raw_name = distribution.metadata["Name"]
            canonical_name = _canonical_distribution_name(raw_name)
        except Exception as exc:
            raise OfflineEvidenceError("runtime distribution metadata is malformed") from exc
        installed_distribution_names.append(canonical_name)
        distribution_catalog.setdefault(canonical_name, []).append(distribution)
    installed_distribution_names.sort()

    landmarks: list[dict[str, str]] = []
    stdlib = resolved_paths["stdlib"]
    for relative in (
        "json/__init__.py",
        "os.py",
        "ssl.py",
        "sqlite3/__init__.py",
        "subprocess.py",
        "unittest/__init__.py",
    ):
        path = stdlib / relative
        if not path.is_file() or path.is_symlink():
            raise OfflineEvidenceError(f"Python stdlib landmark is unavailable: {relative}")
        landmarks.append(
            {
                "path": relative,
                "sha256": _stable_file_sha256(
                    path,
                    f"Python stdlib landmark {relative}",
                    enforce_safe_ancestors=False,
                ),
            }
        )
    covered_distribution_paths: set[str] = set()
    distributions = [
        _runtime_distribution_identity(
            name,
            _RUNTIME_MODULES[name],
            requirements[name],
            candidates=distribution_catalog.get(
                _canonical_distribution_name(name),
                (),
            ),
            environment_root=prefix,
            library_roots=library_roots,
            covered_paths=covered_distribution_paths,
        )
        for name in sorted(requirements)
    ]
    isolated_library_files: list[str] = []
    for library_root in library_roots:
        for path in sorted(library_root.rglob("*")):
            if path.is_symlink():
                raise OfflineEvidenceError("isolated Python library contains a symlink")
            if not path.is_file():
                continue
            isolated_library_files.append(path.relative_to(prefix).as_posix())
    isolated_library_files.sort()
    if set(isolated_library_files) != {
        path
        for path in covered_distribution_paths
        if any(
            (prefix / path) == root or root in (prefix / path).parents
            for root in library_roots
        )
    }:
        raise OfflineEvidenceError(
            "isolated Python library contains files outside verified RECORD closures"
        )
    outside_library_files: list[dict[str, Any]] = []
    for relative in sorted(covered_distribution_paths):
        target = prefix / relative
        if any(target == root or root in target.parents for root in library_roots):
            continue
        identity = _bound_regular_file_identity(
            target,
            f"runtime RECORD file outside library roots {relative}",
        )
        if identity["path_is_symlink"]:
            raise OfflineEvidenceError(
                "runtime RECORD file outside library roots is a symlink"
            )
        outside_library_files.append(
            {
                "path": relative,
                "identity": identity,
            }
        )
    value = {
        "schema_version": RUNTIME_ENVIRONMENT_SCHEMA_VERSION,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "python_build_sha256": hashlib.sha256(sys.version.encode("utf-8")).hexdigest(),
        "cache_tag": sys.implementation.cache_tag,
        "soabi": str(sysconfig.get_config_var("SOABI") or ""),
        "prefix": prefix_identity,
        "base_prefix": base_prefix_identity,
        "pyvenv_configuration": pyvenv_identity,
        "requirements_lock": requirements_identity,
        "paths": paths,
        "isolated_library_root_count": len(library_roots),
        "isolated_library_file_count": len(isolated_library_files),
        "isolated_library_file_set_sha256": _identity_sha256(
            isolated_library_files
        ),
        "outside_library_file_count": len(outside_library_files),
        "outside_library_file_set_sha256": _identity_sha256(
            outside_library_files
        ),
        "outside_library_files": outside_library_files,
        "installed_distribution_names": installed_distribution_names,
        "stdlib_landmarks": landmarks,
        "stdlib_tree": _runtime_tree_identity(stdlib, "Python stdlib"),
        "distributions": distributions,
    }
    value["identity_sha256"] = _identity_sha256(value)
    return value


def _runtime_outside_library_read_literals(
    python_identity: Mapping[str, Any],
    *,
    prefix: Path,
    library_roots: Sequence[Path],
) -> tuple[Path, ...]:
    runtime = python_identity.get("runtime_environment")
    if (
        not isinstance(runtime, Mapping)
        or runtime.get("schema_version") != RUNTIME_ENVIRONMENT_SCHEMA_VERSION
    ):
        raise OfflineEvidenceError("runtime environment identity is malformed")
    records = runtime.get("outside_library_files")
    if (
        not isinstance(records, list)
        or type(runtime.get("outside_library_file_count")) is not int
        or runtime["outside_library_file_count"] != len(records)
        or runtime.get("outside_library_file_set_sha256")
        != _identity_sha256(records)
    ):
        raise OfflineEvidenceError(
            "runtime outside-library file identity is malformed"
        )
    paths: list[Path] = []
    previous: str | None = None
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {"path", "identity"}:
            raise OfflineEvidenceError(
                "runtime outside-library file identity is malformed"
            )
        relative = _canonical_relative(
            record["path"],
            "runtime outside-library file",
        )
        if previous is not None and relative <= previous:
            raise OfflineEvidenceError(
                "runtime outside-library file identity is malformed"
            )
        previous = relative
        unresolved = prefix / relative
        if unresolved.is_symlink():
            raise OfflineEvidenceError(
                "runtime outside-library file is a symlink"
            )
        try:
            resolved = unresolved.resolve(strict=True)
            resolved.relative_to(prefix)
        except (OSError, ValueError) as exc:
            raise OfflineEvidenceError(
                "runtime outside-library file escapes its venv"
            ) from exc
        if resolved != unresolved or any(
            resolved == root or root in resolved.parents for root in library_roots
        ):
            raise OfflineEvidenceError(
                "runtime outside-library file identity is malformed"
            )
        if record["identity"] != _bound_regular_file_identity(
            resolved,
            f"runtime outside-library file {relative}",
        ):
            raise OfflineEvidenceError(
                "runtime outside-library file identity changed"
            )
        paths.append(resolved)
    return tuple(paths)


def _require_sealed_runtime_environment(identity: Mapping[str, Any]) -> None:
    if sys.prefix == sys.base_prefix:
        raise OfflineEvidenceError(
            "formal offline evidence requires an isolated virtual environment"
        )
    current_python = _python_identity(_python_executable())
    if current_python.get("runtime_environment") != identity:
        raise OfflineEvidenceError("Python runtime environment identity changed")
    if current_python.get("independent_executable_copy") is not True:
        raise OfflineEvidenceError(
            "formal offline evidence requires an independent Python executable copy"
        )
    prefix = Path(sys.prefix).resolve(strict=True)
    for key in ("purelib", "platlib"):
        path = Path(sysconfig.get_path(key)).resolve(strict=True)
        try:
            path.relative_to(prefix)
        except ValueError as exc:
            raise OfflineEvidenceError(
                f"formal offline evidence {key} escapes the isolated environment"
            ) from exc
    prefix_identity = identity.get("prefix")
    base_prefix_identity = identity.get("base_prefix")
    pyvenv_identity = identity.get("pyvenv_configuration")
    if (
        not isinstance(prefix_identity, Mapping)
        or not isinstance(base_prefix_identity, Mapping)
        or prefix_identity.get("is_symlink") is not False
        or base_prefix_identity.get("is_symlink") is not False
        or not isinstance(pyvenv_identity, Mapping)
        or pyvenv_identity.get("present") is not True
    ):
        raise OfflineEvidenceError("formal offline evidence venv identity is incomplete")
    expected_distribution_names = sorted(
        _RUNTIME_MODULES
    )
    if identity.get("installed_distribution_names") != expected_distribution_names:
        raise OfflineEvidenceError(
            "isolated environment contains distributions outside requirements.lock"
        )
    distributions = identity.get("distributions")
    if not isinstance(distributions, list):
        raise OfflineEvidenceError("runtime distribution identity is malformed")
    requirements, requirements_identity = _runtime_requirements_identity()
    if identity.get("requirements_lock") != requirements_identity:
        raise OfflineEvidenceError("runtime requirements.lock identity mismatch")
    expected = dict(requirements)
    observed: dict[str, str] = {}
    for item in distributions:
        if not isinstance(item, Mapping) or item.get("present") is not True:
            name = item.get("name") if isinstance(item, Mapping) else "unknown"
            raise OfflineEvidenceError(f"required runtime distribution is missing: {name}")
        name = item.get("name")
        version = item.get("version")
        if (
            not isinstance(name, str)
            or not isinstance(version, str)
            or not isinstance(item.get("module_origin"), Mapping)
            or item["module_origin"].get("inside_isolated_library_root") is not True
            or not isinstance(item.get("record_closure"), Mapping)
            or item["record_closure"].get("unhashed_record_count") != 1
            or item["record_closure"].get("file_count", 0) <= 1
            or item["record_closure"].get("verified_hash_count")
            != item["record_closure"].get("file_count") - 1
        ):
            raise OfflineEvidenceError("runtime distribution identity is malformed")
        observed[_canonical_distribution_name(name)] = version
    if observed != expected:
        raise OfflineEvidenceError("runtime distributions differ from requirements.lock")


@dataclass(frozen=True)
class _MachODependency:
    command: int
    kind: str
    install_name: str


@dataclass(frozen=True)
class _ThinArm64MachO:
    cpu_subtype: int
    filetype: int
    command_count: int
    command_bytes: int
    dependencies: tuple[_MachODependency, ...]
    rpaths: tuple[str, ...]


@dataclass(frozen=True)
class _ExternalMachOClosure:
    identity: dict[str, Any]
    read_literals: tuple[Path, ...]
    resolved_images: tuple[Path, ...]
    symlink_records: tuple[dict[str, Any], ...]


def _macho_lc_string(
    payload: bytes,
    *,
    command_offset: int,
    command_size: int,
    string_offset: int,
    minimum_offset: int,
    field: str,
) -> str:
    if (
        string_offset < minimum_offset
        or string_offset >= command_size
        or string_offset % 4 != 0
    ):
        raise OfflineEvidenceError(f"{field} has an invalid string offset")
    command_end = command_offset + command_size
    start = command_offset + string_offset
    nul = payload.find(b"\0", start, command_end)
    if nul < 0 or nul == start:
        raise OfflineEvidenceError(f"{field} has no bounded non-empty string")
    if any(payload[command_offset + minimum_offset : start]):
        raise OfflineEvidenceError(f"{field} has non-zero pre-string padding")
    if any(payload[nul + 1 : command_end]):
        raise OfflineEvidenceError(f"{field} has non-zero trailing padding")
    try:
        value = payload[start:nul].decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise OfflineEvidenceError(f"{field} is not UTF-8") from exc
    if (
        not value
        or "\\" in value
        or _has_control_character(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        raise OfflineEvidenceError(f"{field} is not canonical")
    return value


def _parse_thin_arm64_macho(payload: bytes, field: str) -> _ThinArm64MachO:
    if len(payload) < 32:
        raise OfflineEvidenceError(f"{field} has a truncated Mach-O header")
    (
        magic,
        cpu_type,
        cpu_subtype,
        filetype,
        command_count,
        command_bytes,
        _flags,
        _reserved,
    ) = struct.unpack_from("<IiiIIIII", payload, 0)
    if magic != _MH_MAGIC_64:
        raise OfflineEvidenceError(f"{field} is not thin little-endian Mach-O 64")
    if cpu_type != _CPU_TYPE_ARM64:
        raise OfflineEvidenceError(f"{field} is not arm64")
    command_end = 32 + command_bytes
    if (
        command_bytes % 8 != 0
        or command_end > len(payload)
        or command_count > command_bytes // 8
    ):
        raise OfflineEvidenceError(f"{field} has invalid load-command bounds")
    dependencies: list[_MachODependency] = []
    rpaths: list[str] = []
    cursor = 32
    for index in range(command_count):
        if cursor + 8 > command_end:
            raise OfflineEvidenceError(f"{field} load command {index} is truncated")
        command, command_size = struct.unpack_from("<II", payload, cursor)
        if (
            command_size < 8
            or command_size % 8 != 0
            or cursor + command_size > command_end
        ):
            raise OfflineEvidenceError(
                f"{field} load command {index} is out of bounds"
            )
        if command in _MACHO_LOAD_COMMANDS or command == _LC_ID_DYLIB:
            if command_size < 24:
                raise OfflineEvidenceError(f"{field} dylib command is truncated")
            name_offset = struct.unpack_from("<I", payload, cursor + 8)[0]
            install_name = _macho_lc_string(
                payload,
                command_offset=cursor,
                command_size=command_size,
                string_offset=name_offset,
                minimum_offset=24,
                field=f"{field} dylib command {index}",
            )
            if command != _LC_ID_DYLIB:
                dependencies.append(
                    _MachODependency(
                        command=command,
                        kind=_MACHO_LOAD_COMMANDS[command],
                        install_name=install_name,
                    )
                )
        elif command == _LC_RPATH:
            if command_size < 12:
                raise OfflineEvidenceError(f"{field} LC_RPATH is truncated")
            path_offset = struct.unpack_from("<I", payload, cursor + 8)[0]
            rpaths.append(
                _macho_lc_string(
                    payload,
                    command_offset=cursor,
                    command_size=command_size,
                    string_offset=path_offset,
                    minimum_offset=12,
                    field=f"{field} LC_RPATH {index}",
                )
            )
        cursor += command_size
    if cursor != command_end:
        raise OfflineEvidenceError(f"{field} load commands do not consume sizeofcmds")
    return _ThinArm64MachO(
        cpu_subtype=cpu_subtype,
        filetype=filetype,
        command_count=command_count,
        command_bytes=command_bytes,
        dependencies=tuple(dependencies),
        rpaths=tuple(rpaths),
    )


def _lexically_normal_absolute(path: Path, field: str) -> Path:
    if not path.is_absolute():
        raise OfflineEvidenceError(f"{field} must be absolute")
    parts: list[str] = []
    for component in path.parts[1:]:
        if component in {"", "."}:
            continue
        if component == "..":
            if not parts:
                raise OfflineEvidenceError(f"{field} escapes the filesystem root")
            parts.pop()
            continue
        if (
            "\\" in component
            or _has_control_character(component)
            or unicodedata.normalize("NFC", component) != component
        ):
            raise OfflineEvidenceError(f"{field} is not canonical")
        parts.append(component)
    return Path(os.sep, *parts)


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _expanded_macho_path(
    value: str,
    *,
    loader_directory: Path,
    executable_directory: Path,
    field: str,
) -> Path:
    if value.startswith("@loader_path/"):
        candidate = loader_directory / value.removeprefix("@loader_path/")
    elif value.startswith("@executable_path/"):
        candidate = executable_directory / value.removeprefix("@executable_path/")
    elif value.startswith("@"):
        raise OfflineEvidenceError(f"{field} uses an unsupported Mach-O token")
    elif value.startswith("/"):
        candidate = Path(value)
    else:
        raise OfflineEvidenceError(f"{field} is a bare relative Mach-O path")
    return _lexically_normal_absolute(candidate, field)


def _macho_system_boundary(path: Path) -> Path | None:
    for boundary in _MACHO_SYSTEM_BOUNDARIES:
        if _path_within(path, boundary) and path != boundary:
            return boundary
    return None


def _macho_binding(
    lexical_path: Path,
    field: str,
) -> tuple[Path, dict[str, Any], tuple[Path, ...]]:
    lexical_path = _lexically_normal_absolute(lexical_path, field)
    if not _path_within(lexical_path, _HOMEBREW_ROOT):
        raise OfflineEvidenceError(f"{field} is outside the Homebrew root")
    identity, literals = _symlink_chain_identity(
        lexical_path,
        field,
        allowed_root=_HOMEBREW_ROOT,
    )
    try:
        resolved = lexical_path.resolve(strict=True)
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} is unavailable") from exc
    if not _path_within(resolved, _HOMEBREW_CELLAR_ROOT):
        raise OfflineEvidenceError(f"{field} resolves outside the Homebrew Cellar")
    return resolved, identity, literals


def _existing_macho_rpath_candidate(path: Path, field: str) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} could not be inspected") from exc
    return True


def _external_tool_macho_closure(
    launcher: Path,
    *,
    tool_name: str,
) -> _ExternalMachOClosure:
    root, launcher_identity, launcher_literals = _macho_binding(
        launcher,
        f"external tool launcher {tool_name}",
    )
    if root.name != tool_name:
        raise OfflineEvidenceError(f"external tool target name mismatch: {tool_name}")
    read_literals: set[Path] = set(launcher_literals)
    symlink_records: dict[str, dict[str, Any]] = {
        record["path_sha256"]: record
        for record in launcher_identity["symlinks"]
    }
    binding_by_image: dict[Path, dict[str, Any]] = {
        root: launcher_identity["resolved_file"]
    }
    queue: list[tuple[Path, tuple[Path, ...]]] = [(root, ())]
    seen_contexts: set[tuple[Path, tuple[Path, ...]]] = set()
    parsed_by_image: dict[Path, _ThinArm64MachO] = {}
    images: dict[Path, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    executable_directory = root.parent
    while queue:
        image, inherited_rpaths = queue.pop(0)
        context = (image, inherited_rpaths)
        if context in seen_contexts:
            continue
        seen_contexts.add(context)
        if len(seen_contexts) > 256:
            raise OfflineEvidenceError(
                f"external tool Mach-O context limit exceeded: {tool_name}"
            )
        payload = _stable_file_bytes(
            image,
            f"external tool Mach-O image {tool_name}",
            max_bytes=128 * 1024 * 1024,
            enforce_safe_ancestors=False,
        )
        binding = binding_by_image[image]
        if hashlib.sha256(payload).hexdigest() != binding["sha256"]:
            raise OfflineEvidenceError(
                f"external tool Mach-O image binding mismatch: {tool_name}"
            )
        parsed = parsed_by_image.get(image)
        if parsed is None:
            parsed = _parse_thin_arm64_macho(
                payload,
                f"external tool Mach-O image {tool_name}",
            )
            expected_filetype = _MH_EXECUTE if image == root else _MH_DYLIB
            if parsed.filetype != expected_filetype:
                raise OfflineEvidenceError(
                    f"external tool Mach-O filetype mismatch: {tool_name}"
                )
            parsed_by_image[image] = parsed
            images[image] = {
                "path_sha256": hashlib.sha256(str(image).encode("utf-8")).hexdigest(),
                "file": binding,
                "cpu_subtype": parsed.cpu_subtype,
                "filetype": parsed.filetype,
                "command_count": parsed.command_count,
                "command_bytes": parsed.command_bytes,
                "rpath_count": len(parsed.rpaths),
                "rpath_set_sha256": _identity_sha256(list(parsed.rpaths)),
                "dependency_count": len(parsed.dependencies),
            }
        own_rpaths = tuple(
            _expanded_macho_path(
                value,
                loader_directory=image.parent,
                executable_directory=executable_directory,
                field=f"external tool Mach-O rpath {tool_name}",
            )
            for value in parsed.rpaths
        )
        effective_rpaths = tuple(dict.fromkeys((*own_rpaths, *inherited_rpaths)))
        for dependency in parsed.dependencies:
            raw_name = dependency.install_name
            candidate_hashes: list[str] = []
            if raw_name.startswith("@rpath/"):
                raw_suffix = raw_name.removeprefix("@rpath/")
                try:
                    suffix = _canonical_relative(
                        raw_suffix,
                        f"external tool Mach-O rpath suffix {tool_name}",
                    )
                except OfflineEvidenceError as exc:
                    raise OfflineEvidenceError(
                        f"external tool Mach-O rpath dependency is malformed: {tool_name}"
                    ) from exc
                candidates = [
                    _lexically_normal_absolute(
                        directory / suffix,
                        f"external tool Mach-O rpath candidate {tool_name}",
                    )
                    for directory in effective_rpaths
                ]
                candidate_hashes = [
                    hashlib.sha256(str(path).encode("utf-8")).hexdigest()
                    for path in candidates
                ]
                existing = [
                    path
                    for path in candidates
                    if _existing_macho_rpath_candidate(
                        path,
                        f"external tool Mach-O rpath candidate {tool_name}",
                    )
                ]
                if len(existing) != 1:
                    raise OfflineEvidenceError(
                        f"external tool Mach-O rpath resolution is not unique: {tool_name}"
                    )
                lexical_dependency = existing[0]
            else:
                lexical_dependency = _expanded_macho_path(
                    raw_name,
                    loader_directory=image.parent,
                    executable_directory=executable_directory,
                    field=f"external tool Mach-O dependency {tool_name}",
                )
                candidate_hashes = [
                    hashlib.sha256(
                        str(lexical_dependency).encode("utf-8")
                    ).hexdigest()
                ]
            boundary = _macho_system_boundary(lexical_dependency)
            edge: dict[str, Any] = {
                "owner_path_sha256": hashlib.sha256(
                    str(image).encode("utf-8")
                ).hexdigest(),
                "command": dependency.command,
                "kind": dependency.kind,
                "raw_name_sha256": hashlib.sha256(
                    raw_name.encode("utf-8")
                ).hexdigest(),
                "candidate_path_sha256s": candidate_hashes,
            }
            if boundary is not None:
                edge.update(
                    {
                        "resolution": "system-boundary",
                        "boundary_path_sha256": hashlib.sha256(
                            str(boundary).encode("utf-8")
                        ).hexdigest(),
                    }
                )
                edges.append(edge)
                continue
            resolved, dependency_binding, literals = _macho_binding(
                lexical_dependency,
                f"external tool Mach-O dependency {tool_name}",
            )
            read_literals.update(literals)
            for record in dependency_binding["symlinks"]:
                existing_record = symlink_records.get(record["path_sha256"])
                if existing_record is not None and existing_record != record:
                    raise OfflineEvidenceError(
                        f"external tool symlink identity conflict: {tool_name}"
                    )
                symlink_records[record["path_sha256"]] = record
            resolved_file = dependency_binding["resolved_file"]
            previous_binding = binding_by_image.get(resolved)
            if previous_binding is not None and previous_binding != resolved_file:
                raise OfflineEvidenceError(
                    f"external tool image identity conflict: {tool_name}"
                )
            binding_by_image[resolved] = resolved_file
            edge.update(
                {
                    "resolution": "homebrew-image",
                    "chosen_path_sha256": hashlib.sha256(
                        str(lexical_dependency).encode("utf-8")
                    ).hexdigest(),
                    "resolved_file_sha256": resolved_file["sha256"],
                }
            )
            edges.append(edge)
            queue.append((resolved, effective_rpaths))
            if len(edges) > 2048:
                raise OfflineEvidenceError(
                    f"external tool Mach-O edge limit exceeded: {tool_name}"
                )
    image_records = sorted(images.values(), key=lambda item: item["path_sha256"])
    edge_records = sorted(edges, key=canonical_json_bytes)
    link_records = tuple(
        sorted(symlink_records.values(), key=lambda item: item["path_sha256"])
    )
    identity: dict[str, Any] = {
        "schema_version": "cloud-v2-external-macho-closure-v1",
        "policy": "homebrew-thin-arm64-recursive-system-boundary-v1",
        "root_executable_sha256": binding_by_image[root]["sha256"],
        "image_count": len(image_records),
        "dependency_image_count": len(image_records) - 1,
        "image_set_sha256": _identity_sha256(image_records),
        "edge_count": len(edge_records),
        "edge_set_sha256": _identity_sha256(edge_records),
        "symlink_count": len(link_records),
        "symlink_set_sha256": _identity_sha256(list(link_records)),
        "system_boundary_edge_count": sum(
            edge["resolution"] == "system-boundary" for edge in edge_records
        ),
        "unresolved_count": 0,
        "read_literal_count": len(read_literals),
        "read_literal_path_set_sha256": _identity_sha256(
            sorted(str(path) for path in read_literals)
        ),
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return _ExternalMachOClosure(
        identity=identity,
        read_literals=tuple(sorted(read_literals, key=str)),
        resolved_images=tuple(sorted(images, key=str)),
        symlink_records=link_records,
    )


@dataclass(frozen=True)
class _ExternalToolSet:
    identity: dict[str, Any]
    executable_paths: dict[str, Path]
    path_directories: tuple[Path, ...]
    read_literals: tuple[Path, ...]


def _empty_external_tool_set() -> _ExternalToolSet:
    macho_union: dict[str, Any] = {
        "schema_version": "cloud-v2-external-macho-union-v1",
        "tool_count": 0,
        "tool_closure_set_sha256": _identity_sha256([]),
        "image_count": 0,
        "image_path_set_sha256": _identity_sha256([]),
        "shared_image_count": 0,
        "shared_image_path_set_sha256": _identity_sha256([]),
        "symlink_count": 0,
        "symlink_set_sha256": _identity_sha256([]),
        "unresolved_count": 0,
    }
    macho_union["identity_sha256"] = _identity_sha256(macho_union)
    identity: dict[str, Any] = {
        "schema_version": "cloud-v2-external-tool-set-v2",
        "search_directory_set_sha256": _identity_sha256([]),
        "read_literal_count": 0,
        "read_literal_path_set_sha256": _identity_sha256([]),
        "macho_union": macho_union,
        "runtime_data_trees": [],
        "tools": [],
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return _ExternalToolSet(
        identity=identity,
        executable_paths={},
        path_directories=(),
        read_literals=(),
    )


def _resolve_external_tools() -> _ExternalToolSet:
    search_path = os.pathsep.join(str(path) for path in _EXTERNAL_TOOL_SEARCH_DIRECTORIES)
    brokered_worker = isinstance(_PARENT_BROKER_CLIENT, _ParentBrokerClient)
    records: list[dict[str, Any]] = []
    executable_paths: dict[str, Path] = {}
    path_directories: set[Path] = set()
    read_literals: set[Path] = set()
    macho_closures: list[_ExternalMachOClosure] = []
    macho_symlink_records: dict[str, dict[str, Any]] = {}
    for name in _EXTERNAL_TOOL_NAMES:
        if brokered_worker:
            launcher_value = str(
                _HOMEBREW_BIN_ROOT / name
                if name in _HOMEBREW_MACHO_TOOL_NAMES
                else _SYSTEM_TOOL_EXACT_PATHS.get(name, Path(""))
            )
        else:
            launcher_value = shutil.which(name, path=search_path)
        if launcher_value is None:
            raise OfflineEvidenceError(f"required external tool is unavailable: {name}")
        launcher = Path(launcher_value)
        if not launcher.is_absolute():
            raise OfflineEvidenceError(f"external tool launcher is not absolute: {name}")
        try:
            launcher_state_before = launcher.lstat()
            link_target = os.readlink(launcher) if launcher.is_symlink() else None
            resolved = launcher.resolve(strict=True)
            resolved_state_before = resolved.stat(follow_symlinks=False)
        except OSError as exc:
            raise OfflineEvidenceError(f"external tool is unavailable: {name}") from exc
        if (
            not stat.S_ISREG(resolved_state_before.st_mode)
            or resolved.is_symlink()
            or resolved.name != name
            or (
                not bool(stat.S_IMODE(resolved_state_before.st_mode) & 0o111)
                if brokered_worker
                else not os.access(resolved, os.X_OK)
            )
        ):
            raise OfflineEvidenceError(f"external tool target is unsafe: {name}")
        dependency_closure: dict[str, Any]
        if name in _HOMEBREW_MACHO_TOOL_NAMES:
            approved_root = _HOMEBREW_TOOL_ROOTS.get(name)
            if (
                launcher != _HOMEBREW_BIN_ROOT / name
                or approved_root is None
                or resolved != approved_root / "bin" / name
            ):
                raise OfflineEvidenceError(
                    f"external Homebrew tool path is not approved: {name}"
                )
            closure = _external_tool_macho_closure(launcher, tool_name=name)
            if resolved not in closure.resolved_images:
                raise OfflineEvidenceError(
                    f"external tool executable is absent from its Mach-O closure: {name}"
                )
            dependency_closure = closure.identity
            read_literals.update(closure.read_literals)
            macho_closures.append(closure)
            for symlink_record in closure.symlink_records:
                path_sha256 = symlink_record["path_sha256"]
                existing_record = macho_symlink_records.get(path_sha256)
                if existing_record is not None and existing_record != symlink_record:
                    raise OfflineEvidenceError(
                        f"external tool symlink identity conflict: {name}"
                    )
                macho_symlink_records[path_sha256] = symlink_record
        else:
            expected_system_path = _SYSTEM_TOOL_EXACT_PATHS.get(name)
            if (
                expected_system_path is None
                or launcher != expected_system_path
                or resolved != expected_system_path
                or resolved.parent not in _SYSTEM_TOOL_ROOTS
            ):
                raise OfflineEvidenceError(
                    f"external system tool path is not approved: {name}"
                )
            dependency_closure = {
                "schema_version": "cloud-v2-system-tool-leaf-v1",
                "policy": "apple-ssv-exact-executable-system-boundary-v1",
                "resolved_parent_path_sha256": hashlib.sha256(
                    str(resolved.parent).encode("utf-8")
                ).hexdigest(),
            }
            dependency_closure["identity_sha256"] = _identity_sha256(
                dependency_closure
            )
            read_literals.update((launcher, resolved, *launcher.parents, *resolved.parents))
        digest = _stable_file_sha256(
            resolved,
            f"external tool {name}",
            enforce_safe_ancestors=False,
        )
        try:
            launcher_state_after = launcher.lstat()
            resolved_state_after = resolved.stat(follow_symlinks=False)
            parent_state = resolved.parent.stat(follow_symlinks=False)
        except OSError as exc:
            raise OfflineEvidenceError(f"external tool is unavailable: {name}") from exc
        if (
            _state_identity(launcher_state_before) != _state_identity(launcher_state_after)
            or _state_identity(resolved_state_before) != _state_identity(resolved_state_after)
        ):
            raise OfflineEvidenceError(f"external tool changed during inspection: {name}")
        record = {
            "name": name,
            "present": True,
            "launcher_path_sha256": hashlib.sha256(
                str(launcher).encode("utf-8")
            ).hexdigest(),
            "launcher_is_symlink": stat.S_ISLNK(launcher_state_after.st_mode),
            "launcher_link_target_sha256": (
                hashlib.sha256(link_target.encode("utf-8")).hexdigest()
                if link_target is not None
                else None
            ),
            "launcher_device": launcher_state_after.st_dev,
            "launcher_inode": launcher_state_after.st_ino,
            "launcher_mode": launcher_state_after.st_mode,
            "launcher_nlink": launcher_state_after.st_nlink,
            "launcher_size": launcher_state_after.st_size,
            "launcher_mtime_ns": launcher_state_after.st_mtime_ns,
            "launcher_ctime_ns": launcher_state_after.st_ctime_ns,
            "resolved_path_sha256": hashlib.sha256(
                str(resolved).encode("utf-8")
            ).hexdigest(),
            "executable_sha256": digest,
            "executable_device": resolved_state_after.st_dev,
            "executable_inode": resolved_state_after.st_ino,
            "executable_mode": resolved_state_after.st_mode,
            "executable_nlink": resolved_state_after.st_nlink,
            "executable_size": resolved_state_after.st_size,
            "executable_mtime_ns": resolved_state_after.st_mtime_ns,
            "executable_ctime_ns": resolved_state_after.st_ctime_ns,
            "directory_path_sha256": hashlib.sha256(
                str(resolved.parent).encode("utf-8")
            ).hexdigest(),
            "directory_device": parent_state.st_dev,
            "directory_inode": parent_state.st_ino,
            "directory_mode": parent_state.st_mode,
            "directory_nlink": parent_state.st_nlink,
            "directory_size": parent_state.st_size,
            "directory_mtime_ns": parent_state.st_mtime_ns,
            "directory_ctime_ns": parent_state.st_ctime_ns,
            "dependency_closure": dependency_closure,
        }
        records.append(record)
        executable_paths[name] = launcher
        path_directories.add(launcher.parent)
        path_directories.add(resolved.parent)
    runtime_data_trees: list[dict[str, Any]] = []
    if macho_closures:
        poppler_data_identity, poppler_data_literals = (
            _bound_runtime_tree_identity(
                _HOMEBREW_POPPLER_DATA_ROOT,
                "Poppler runtime data tree",
                reject_symlinks=True,
            )
        )
        read_literals.update(poppler_data_literals)
        runtime_data_trees.append(
            {"name": "poppler", "tree": poppler_data_identity}
        )
    sorted_read_literals = tuple(sorted(read_literals, key=str))
    macho_image_sets = [set(closure.resolved_images) for closure in macho_closures]
    macho_image_union = set().union(*macho_image_sets) if macho_image_sets else set()
    macho_shared_images = (
        set.intersection(*macho_image_sets) if macho_image_sets else set()
    )
    sorted_macho_symlinks = sorted(
        macho_symlink_records.values(),
        key=lambda item: item["path_sha256"],
    )
    macho_union_identity: dict[str, Any] = {
        "schema_version": "cloud-v2-external-macho-union-v1",
        "tool_count": len(macho_closures),
        "tool_closure_set_sha256": _identity_sha256(
            sorted(
                (closure.identity["identity_sha256"] for closure in macho_closures)
            )
        ),
        "image_count": len(macho_image_union),
        "image_path_set_sha256": _identity_sha256(
            sorted(str(path) for path in macho_image_union)
        ),
        "shared_image_count": len(macho_shared_images),
        "shared_image_path_set_sha256": _identity_sha256(
            sorted(str(path) for path in macho_shared_images)
        ),
        "symlink_count": len(sorted_macho_symlinks),
        "symlink_set_sha256": _identity_sha256(sorted_macho_symlinks),
        "unresolved_count": sum(
            closure.identity["unresolved_count"] for closure in macho_closures
        ),
    }
    macho_union_identity["identity_sha256"] = _identity_sha256(
        macho_union_identity
    )
    identity: dict[str, Any] = {
        "schema_version": "cloud-v2-external-tool-set-v2",
        "search_directory_set_sha256": _identity_sha256(
            [str(path) for path in _EXTERNAL_TOOL_SEARCH_DIRECTORIES]
        ),
        "read_literal_count": len(sorted_read_literals),
        "read_literal_path_set_sha256": _identity_sha256(
            [str(path) for path in sorted_read_literals]
        ),
        "macho_union": macho_union_identity,
        "runtime_data_trees": runtime_data_trees,
        "tools": records,
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return _ExternalToolSet(
        identity=identity,
        executable_paths=executable_paths,
        path_directories=tuple(sorted(path_directories, key=str)),
        read_literals=sorted_read_literals,
    )


def _revalidate_external_tools(expected: Mapping[str, Any]) -> None:
    if _resolve_external_tools().identity != expected:
        raise OfflineEvidenceError("external tool identity changed during execution")


@dataclass(frozen=True)
class _RuntimeSandboxClosure:
    identity: dict[str, Any]
    read_subpaths: tuple[Path, ...]
    read_literals: tuple[Path, ...]
    executable_paths: tuple[Path, ...]


@dataclass(frozen=True)
class _ProductionEmbeddingFixture:
    identity: dict[str, Any]
    wheelhouse: Path
    installer: Path
    installer_root: Path
    read_literals: tuple[Path, ...]

    def environment(self) -> dict[str, str]:
        return {
            _PRODUCTION_EMBEDDING_FIXTURE_ENV[0]: str(self.wheelhouse),
            _PRODUCTION_EMBEDDING_FIXTURE_ENV[1]: str(self.installer),
            _PRODUCTION_EMBEDDING_FIXTURE_ENV[2]: self.identity[
                "declared_installer_sha256"
            ],
        }


def _directory_identity(path: Path, field: str) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
        state = resolved.stat(follow_symlinks=False)
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} identity is unavailable") from exc
    if not stat.S_ISDIR(state.st_mode):
        raise OfflineEvidenceError(f"{field} must be a real directory")
    return {
        "path_sha256": hashlib.sha256(str(resolved).encode("utf-8")).hexdigest(),
        "device": state.st_dev,
        "inode": state.st_ino,
        "mode": state.st_mode,
        "nlink": state.st_nlink,
        "size": state.st_size,
        "mtime_ns": state.st_mtime_ns,
        "ctime_ns": state.st_ctime_ns,
    }


def _bound_runtime_tree_identity(
    root: Path,
    field: str,
    *,
    reject_symlinks: bool = False,
    include_canonical_nodes: bool = False,
) -> tuple[dict[str, Any], tuple[Path, ...]]:
    try:
        root = root.resolve(strict=True)
        _opened_root, root_fd = _open_directory_fd(
            root,
            field,
            enforce_safe_ancestors=False,
        )
    except (OSError, OfflineEvidenceError) as exc:
        raise OfflineEvidenceError(f"{field} is unavailable") from exc
    records: list[dict[str, Any]] = []
    read_literals: set[Path] = {root, *root.parents}
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )

    def state_record(relative: str, kind: str, state: os.stat_result) -> dict[str, Any]:
        return {
            "path": relative,
            "kind": kind,
            "device": state.st_dev,
            "inode": state.st_ino,
            "mode": state.st_mode,
            "nlink": state.st_nlink,
            "size": state.st_size,
            "mtime_ns": state.st_mtime_ns,
            "ctime_ns": state.st_ctime_ns,
        }

    def visit(directory_fd: int, relative_root: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory_fd), key=lambda entry: entry.name)
        except OSError as exc:
            raise OfflineEvidenceError(f"{field} could not be enumerated") from exc
        folded: set[str] = set()
        for entry in entries:
            name = _canonical_snapshot_name(entry.name, field)
            key = unicodedata.normalize("NFC", name).casefold()
            if key in folded:
                raise OfflineEvidenceError(f"{field} contains an alias collision")
            folded.add(key)
            relative_path = relative_root / name
            relative = relative_path.as_posix()
            absolute = root / relative
            try:
                before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise OfflineEvidenceError(f"{field} changed during enumeration") from exc
            read_literals.add(absolute)
            if stat.S_ISLNK(before.st_mode):
                if reject_symlinks:
                    raise OfflineEvidenceError(f"{field} contains a symlink")
                try:
                    target = os.readlink(name, dir_fd=directory_fd)
                    after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as exc:
                    raise OfflineEvidenceError(
                        f"{field} symlink changed during enumeration"
                    ) from exc
                if _state_identity(before) != _state_identity(after):
                    raise OfflineEvidenceError(
                        f"{field} symlink changed during enumeration"
                    )
                try:
                    resolved_target = absolute.resolve(strict=True)
                except OSError as exc:
                    raise OfflineEvidenceError(
                        f"{field} symlink target is unavailable"
                    ) from exc
                if resolved_target.is_dir():
                    resolved_identity = _directory_identity(
                        resolved_target,
                        f"{field} symlink target {relative}",
                    )
                    identity_sha256 = _identity_sha256(resolved_identity)
                    literals = (resolved_target, *resolved_target.parents)
                else:
                    identity, literals = _symlink_chain_identity(
                        absolute,
                        f"{field} symlink {relative}",
                    )
                    identity_sha256 = identity["identity_sha256"]
                records.append(
                    {
                        **state_record(relative, "symlink", after),
                        "target_sha256": hashlib.sha256(
                            target.encode("utf-8")
                        ).hexdigest(),
                        "resolved_identity_sha256": identity_sha256,
                    }
                )
                read_literals.update(literals)
                continue
            if stat.S_ISDIR(before.st_mode):
                _safe_mode(before, f"{field} directory {relative}", directory=True)
                child_fd = os.open(name, directory_flags, dir_fd=directory_fd)
                try:
                    opened = os.fstat(child_fd)
                    if _state_identity(opened) != _state_identity(before):
                        raise OfflineEvidenceError(
                            f"{field} directory changed during enumeration"
                        )
                    records.append(state_record(relative, "directory", opened))
                    visit(child_fd, relative_path)
                    if _state_identity(os.fstat(child_fd)) != _state_identity(opened):
                        raise OfflineEvidenceError(
                            f"{field} directory changed during enumeration"
                        )
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise OfflineEvidenceError(f"{field} contains a non-unique file")
            _safe_mode(before, f"{field} file {relative}")
            descriptor = os.open(name, file_flags, dir_fd=directory_fd)
            try:
                opened = os.fstat(descriptor)
                if _state_identity(opened) != _state_identity(before):
                    raise OfflineEvidenceError(
                        f"{field} file changed during enumeration"
                    )
                payload = _read_open_bytes(descriptor, opened, field)
                records.append(
                    {
                        **state_record(relative, "file", opened),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            finally:
                os.close(descriptor)

    try:
        root_state = os.fstat(root_fd)
        _safe_mode(root_state, field, directory=True)
        records.append(state_record(".", "directory", root_state))
        visit(root_fd, PurePosixPath())
        if _state_identity(os.fstat(root_fd)) != _state_identity(root_state):
            raise OfflineEvidenceError(f"{field} changed during enumeration")
    finally:
        os.close(root_fd)
    if include_canonical_nodes:
        canonical_nodes: list[dict[str, Any]] = []
        for record in records:
            canonical: dict[str, Any] = {
                "path": record["path"],
                "kind": record["kind"],
                "mode": stat.S_IMODE(record["mode"]),
            }
            if record["kind"] == "file":
                canonical.update(
                    {
                        "size": record["size"],
                        "sha256": record["sha256"],
                    }
                )
            elif record["kind"] == "symlink":
                canonical["target_sha256"] = record["target_sha256"]
            canonical_nodes.append(canonical)
        identity = {
            "schema_version": "cloud-v2-bound-runtime-tree-v2",
            "root_path_sha256": hashlib.sha256(
                str(root).encode("utf-8")
            ).hexdigest(),
            "node_count": len(canonical_nodes),
            "nodes": canonical_nodes,
            "node_set_sha256": _identity_sha256(canonical_nodes),
            "observed_state_sha256": _identity_sha256(records),
        }
    else:
        identity = {
            "schema_version": "cloud-v2-bound-runtime-tree-v1",
            "root_path_sha256": hashlib.sha256(
                str(root).encode("utf-8")
            ).hexdigest(),
            "node_count": len(records),
            "node_set_sha256": _identity_sha256(records),
        }
    identity["identity_sha256"] = _identity_sha256(identity)
    return identity, tuple(sorted(read_literals, key=str))


def _symlink_chain_identity(
    path: Path,
    field: str,
    *,
    allowed_root: Path | None = None,
) -> tuple[dict[str, Any], tuple[Path, ...]]:
    if not path.is_absolute():
        raise OfflineEvidenceError(f"{field} path must be absolute")
    if allowed_root is not None:
        allowed_root = _lexically_normal_absolute(allowed_root, f"{field} root")
        if not _path_within(path, allowed_root) or path == allowed_root:
            raise OfflineEvidenceError(f"{field} path is outside its approved root")
    records: list[dict[str, Any]] = []
    read_literals: set[Path] = {Path(os.sep)}
    lexical = Path(os.sep)
    for component in path.parts[1:]:
        lexical /= component
        read_literals.add(lexical)
    if allowed_root is None:
        current = Path(os.sep)
        pending = list(path.parts[1:])
    else:
        current = allowed_root
        pending = list(path.relative_to(allowed_root).parts)
        read_literals.add(allowed_root)
        read_literals.update(allowed_root.parents)
    seen_links: set[tuple[int, int]] = set()
    symlink_hops = 0
    while pending:
        component = pending.pop(0)
        if component in {"", "."}:
            continue
        if component == "..":
            if allowed_root is not None and current == allowed_root:
                raise OfflineEvidenceError(f"{field} path chain escapes its approved root")
            current = current.parent
            read_literals.add(current)
            continue
        candidate = current / component
        try:
            state_before = candidate.lstat()
            link_target = (
                os.readlink(candidate) if stat.S_ISLNK(state_before.st_mode) else None
            )
            state_after = candidate.lstat()
        except OSError as exc:
            raise OfflineEvidenceError(f"{field} path chain is unavailable") from exc
        if _state_identity(state_before) != _state_identity(state_after):
            raise OfflineEvidenceError(f"{field} path chain changed during inspection")
        read_literals.add(candidate)
        read_literals.update(candidate.parents)
        if link_target is not None:
            symlink_hops += 1
            link_identity = (state_after.st_dev, state_after.st_ino)
            if symlink_hops > 64 or link_identity in seen_links:
                raise OfflineEvidenceError(f"{field} path chain contains a symlink loop")
            seen_links.add(link_identity)
            records.append(
                {
                    "path_sha256": hashlib.sha256(
                        str(candidate).encode("utf-8")
                    ).hexdigest(),
                    "target_sha256": hashlib.sha256(
                        link_target.encode("utf-8")
                    ).hexdigest(),
                    "device": state_after.st_dev,
                    "inode": state_after.st_ino,
                    "mode": state_after.st_mode,
                    "nlink": state_after.st_nlink,
                    "size": state_after.st_size,
                    "mtime_ns": state_after.st_mtime_ns,
                    "ctime_ns": state_after.st_ctime_ns,
                }
            )
            target = Path(link_target)
            if target.is_absolute():
                normalized_target = _lexically_normal_absolute(
                    target,
                    f"{field} symlink target",
                )
                if allowed_root is not None:
                    if not _path_within(normalized_target, allowed_root):
                        raise OfflineEvidenceError(
                            f"{field} symlink target escapes its approved root"
                        )
                    current = allowed_root
                    target_parts = list(normalized_target.relative_to(allowed_root).parts)
                else:
                    current = Path(os.sep)
                    target_parts = list(normalized_target.parts[1:])
            else:
                target_parts = list(target.parts)
            pending = [*target_parts, *pending]
            continue
        current = candidate
    resolved = current
    try:
        if resolved != path.resolve(strict=True):
            raise OfflineEvidenceError(f"{field} path chain resolved inconsistently")
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} path chain is unavailable") from exc
    for ancestor in (resolved, *resolved.parents):
        read_literals.add(ancestor)
    identity = {
        "lexical_path_sha256": hashlib.sha256(str(path).encode("utf-8")).hexdigest(),
        "resolved_file": _bound_regular_file_identity(resolved, field),
        "symlink_count": len(records),
        "symlinks": records,
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return identity, tuple(sorted(read_literals, key=str))


def _python_framework_base_executable_alias_bindings(
    base_executable: Path,
) -> tuple[list[dict[str, Any]], tuple[Path, ...]]:
    if sys.platform != "darwin" or not sysconfig.get_config_var("PYTHONFRAMEWORK"):
        return [], ()
    raw_framework_prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX")
    if not isinstance(raw_framework_prefix, str) or not raw_framework_prefix:
        raise OfflineEvidenceError(
            "runtime sandbox Python framework prefix is unavailable"
        )
    framework_prefix = _lexically_normal_absolute(
        Path(raw_framework_prefix),
        "runtime sandbox Python framework prefix",
    )
    alias = _lexically_normal_absolute(
        framework_prefix.parent / "bin" / base_executable.name,
        "runtime sandbox Python framework base executable alias",
    )
    if not os.path.lexists(alias):
        return [], ()
    try:
        resolved_alias = alias.resolve(strict=True)
    except OSError as exc:
        raise OfflineEvidenceError(
            "runtime sandbox Python framework base executable alias is unavailable"
        ) from exc
    if resolved_alias != base_executable:
        raise OfflineEvidenceError(
            "runtime sandbox Python framework base executable alias target mismatch"
        )
    identity, read_literals = _symlink_chain_identity(
        alias,
        "Python framework base executable alias",
    )
    return [
        {
            "source": "sysconfig-python-framework-prefix-bin",
            "chain": identity,
        }
    ], read_literals


def _runtime_sandbox_closure(
    *,
    python: Path,
    python_identity: Mapping[str, Any],
    external_tools: _ExternalToolSet,
) -> _RuntimeSandboxClosure:
    try:
        prefix = Path(sys.prefix).resolve(strict=True)
        base_prefix = Path(sys.base_prefix).resolve(strict=True)
        process_executable = _current_process_executable()
        base_executable = Path(sys._base_executable).resolve(strict=True)
    except OSError as exc:
        raise OfflineEvidenceError("runtime sandbox Python closure is unavailable") from exc
    base_executable_aliases, base_executable_alias_literals = (
        _python_framework_base_executable_alias_bindings(base_executable)
    )
    base_prefix_tree, base_prefix_tree_literals = _bound_runtime_tree_identity(
        base_prefix,
        "runtime sandbox base prefix tree",
    )
    library_records: list[dict[str, Any]] = []
    library_tree_cache: dict[Path, tuple[dict[str, Any], tuple[Path, ...]]] = {}
    library_roots: list[Path] = []
    library_read_literals: set[Path] = set()
    for role, key, approved_root in (
        ("stdlib", "stdlib", base_prefix),
        ("purelib", "purelib", prefix),
        ("platlib", "platlib", prefix),
    ):
        configured = sysconfig.get_path(key)
        if not configured:
            raise OfflineEvidenceError(f"runtime sandbox {role} path is unavailable")
        lexical = Path(configured)
        if not lexical.is_absolute() or lexical.is_symlink():
            raise OfflineEvidenceError(f"runtime sandbox {role} path is unsafe")
        try:
            resolved = lexical.resolve(strict=True)
            resolved.relative_to(approved_root)
        except (OSError, ValueError) as exc:
            raise OfflineEvidenceError(
                f"runtime sandbox {role} path escapes its approved prefix"
            ) from exc
        if resolved == approved_root:
            raise OfflineEvidenceError(
                f"runtime sandbox {role} path is broader than its library root"
            )
        cached_tree = library_tree_cache.get(resolved)
        if cached_tree is None:
            cached_tree = _bound_runtime_tree_identity(
                resolved,
                f"runtime sandbox {role} root",
            )
            library_tree_cache[resolved] = cached_tree
        tree_identity, _tree_literals = cached_tree
        library_read_literals.update(_tree_literals)
        record = {"role": role, "tree": tree_identity}
        library_records.append(record)
        if resolved not in library_roots:
            library_roots.append(resolved)

    exact_runtime_files: list[Path] = []
    if sys.platform == "darwin":
        _bound_regular_file_identity(
            _DARWIN_SYSTEM_VERSION_FILE,
            "runtime macOS system version file",
        )
        exact_runtime_files.append(_DARWIN_SYSTEM_VERSION_FILE)
    pyvenv_config = prefix / "pyvenv.cfg"
    if prefix != base_prefix:
        _bound_regular_file_identity(pyvenv_config, "runtime pyvenv.cfg")
        exact_runtime_files.append(pyvenv_config)
    framework_binary = base_prefix / "Python"
    if framework_binary.exists():
        _bound_regular_file_identity(
            framework_binary,
            "runtime Python framework binary",
        )
        exact_runtime_files.append(framework_binary)
    exact_runtime_files.extend(
        _runtime_outside_library_read_literals(
            python_identity,
            prefix=prefix,
            library_roots=library_roots,
        )
    )
    native_records: list[dict[str, Any]] = []
    native_literals: set[Path] = set()
    for alias in _PYTHON_NATIVE_LIBRARY_ALIASES:
        identity, literals = _symlink_chain_identity(
            alias,
            f"Python native library {alias.name}",
        )
        native_records.append(identity)
        native_literals.update(literals)
    sandbox_identity = _bound_regular_file_identity(
        NETWORK_SANDBOX_PATH,
        "sandbox-exec executable",
    )
    external_executables = tuple(external_tools.executable_paths.values())
    executable_paths = tuple(
        dict.fromkeys(
            (
                python,
                process_executable,
                NETWORK_SANDBOX_PATH.resolve(strict=True),
                *external_executables,
                *(path.resolve(strict=True) for path in external_executables),
            )
        )
    )
    executable_identities = [
        _bound_regular_file_identity(path, f"sandbox executable {path.name}")
        for path in executable_paths
    ]
    descriptor_alias_read_subpaths: tuple[Path, ...] = ()
    descriptor_alias_directory_identities: list[dict[str, Any]] = []
    if sys.platform == "darwin":
        descriptor_alias_read_subpaths = _DARWIN_DESCRIPTOR_ALIAS_READ_SUBPATHS
        for path in descriptor_alias_read_subpaths:
            try:
                state = path.stat(follow_symlinks=False)
                resolved = path.resolve(strict=True)
            except OSError as exc:
                raise OfflineEvidenceError(
                    "runtime sandbox descriptor alias directory is unavailable"
                ) from exc
            if path != resolved or path.is_symlink() or not stat.S_ISDIR(state.st_mode):
                raise OfflineEvidenceError(
                    "runtime sandbox descriptor alias directory is unsafe"
                )
            descriptor_alias_directory_identities.append(
                _directory_identity(path, "runtime sandbox descriptor alias directory")
            )
    read_literals: set[Path] = {
        Path(os.sep),
        Path("/dev/null"),
        python,
        process_executable,
        base_executable,
        NETWORK_SANDBOX_PATH.resolve(strict=True),
        *exact_runtime_files,
        *_DYLD_SHARED_CACHE_RUNTIME_LITERALS,
        *native_literals,
        *base_executable_alias_literals,
        *base_prefix_tree_literals,
        *library_read_literals,
        *external_tools.read_literals,
        *executable_paths,
    }
    for path in tuple(read_literals):
        read_literals.update(path.parents)
    identity: dict[str, Any] = {
        "schema_version": "cloud-v2-runtime-sandbox-closure-v5",
        "python_identity_sha256": _identity_sha256(python_identity),
        "prefix": _directory_identity(prefix, "runtime sandbox venv prefix"),
        "base_prefix": _directory_identity(
            base_prefix,
            "runtime sandbox base prefix",
        ),
        "base_prefix_tree": base_prefix_tree,
        "library_roots": library_records,
        "exact_runtime_files": [
            _bound_regular_file_identity(path, f"runtime exact file {path.name}")
            for path in exact_runtime_files
        ],
        "dyld_shared_cache_literals_sha256": _identity_sha256(
            [str(path) for path in _DYLD_SHARED_CACHE_RUNTIME_LITERALS]
        ),
        "native_libraries": native_records,
        "sandbox_executable": sandbox_identity,
        "base_executable_aliases": base_executable_aliases,
        "descriptor_alias_policy": "held-descriptor-reopen-read-only",
        "descriptor_alias_read_subpaths": [
            str(path) for path in descriptor_alias_read_subpaths
        ],
        "descriptor_alias_directory_identities": (
            descriptor_alias_directory_identities
        ),
        "external_tool_set_sha256": external_tools.identity["identity_sha256"],
        "executable_count": len(executable_identities),
        "executable_set_sha256": _identity_sha256(executable_identities),
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return _RuntimeSandboxClosure(
        identity=identity,
        read_subpaths=tuple((*library_roots, *descriptor_alias_read_subpaths)),
        read_literals=tuple(sorted(read_literals, key=str)),
        executable_paths=executable_paths,
    )


def _revalidate_runtime_sandbox_closure(
    expected: Mapping[str, Any],
    *,
    python: Path,
    python_identity: Mapping[str, Any],
    external_tools: _ExternalToolSet,
) -> None:
    current = _runtime_sandbox_closure(
        python=python,
        python_identity=python_identity,
        external_tools=external_tools,
    )
    if current.identity != expected:
        raise OfflineEvidenceError("runtime sandbox closure identity changed")


def _network_policy() -> dict[str, Any]:
    try:
        sandbox_sha256 = _stable_file_sha256(
            NETWORK_SANDBOX_PATH, "sandbox-exec executable"
        )
    except OfflineEvidenceError as exc:
        raise OfflineEvidenceError(
            "sandbox-exec is unavailable or not a regular file"
        ) from exc
    return {
        "schema_version": NETWORK_POLICY_SCHEMA_VERSION,
        "implementation": "macos-sandbox-exec",
        "sandbox_executable_sha256": sandbox_sha256,
        "component_network_profile": NETWORK_SANDBOX_PROFILE,
        "component_network_profile_sha256": hashlib.sha256(
            NETWORK_SANDBOX_PROFILE.encode("utf-8")
        ).hexdigest(),
        "network_access": "deny-all",
        "formal_control_plane": "isolated-bootstrap-components-sandboxed-once",
        "child_filesystem_profile_template": CHILD_FILESYSTEM_SANDBOX_TEMPLATE,
        "child_file_read_policy": "deny-by-default-exact-bound-closure",
        "child_process_exec_policy": "deny-by-default-exact-bound-executables",
        "child_live_repository_access": "not-allowlisted",
        "child_private_snapshot_access": "read-only",
        "child_component_scratch": "independent-parent-owned-0700-read-write",
        "child_tmp_environment": "TMPDIR=TMP=TEMP=HOME=component-scratch",
        "formal_cli_startup": _startup_flags_identity(),
        "active_probe_required_result": _network_enforcement_success(),
    }


def _sandbox_path_literal(path: Path) -> str:
    value = str(path)
    if _has_control_character(value):
        raise OfflineEvidenceError("sandbox path contains a control character")
    return json.dumps(value, ensure_ascii=False)


def _sandbox_ancestor_literals(paths: Iterable[Path]) -> tuple[Path, ...]:
    ancestors: set[Path] = {Path(os.sep)}
    for path in paths:
        if not path.is_absolute():
            raise OfflineEvidenceError("sandbox closure path must be absolute")
        ancestors.add(path)
        ancestors.update(path.parents)
    return tuple(sorted(ancestors, key=str))


def _child_sandbox_profile(
    snapshot: Path,
    scratch: Path,
    closure: _RuntimeSandboxClosure,
) -> str:
    snapshot = snapshot.resolve(strict=True)
    scratch = scratch.resolve(strict=True)
    return _child_sandbox_profile_from_bound_paths(snapshot, scratch, closure)


def _child_sandbox_profile_from_bound_paths(
    snapshot: Path,
    scratch: Path,
    closure: _RuntimeSandboxClosure,
) -> str:
    if (
        not snapshot.is_absolute()
        or str(snapshot) != os.path.normpath(str(snapshot))
        or not scratch.is_absolute()
        or str(scratch) != os.path.normpath(str(scratch))
        or snapshot == scratch
    ):
        raise OfflineEvidenceError("child sandbox bound paths are malformed")
    read_subpaths = tuple(dict.fromkeys((snapshot, scratch, *closure.read_subpaths)))
    read_literals = _sandbox_ancestor_literals(
        (*read_subpaths, *closure.read_literals, *closure.executable_paths)
    )
    read_filters = " ".join(
        [
            *(f"(literal {_sandbox_path_literal(path)})" for path in read_literals),
            *(f"(subpath {_sandbox_path_literal(path)})" for path in read_subpaths),
        ]
    )
    exec_filters = " ".join(
        f"(literal {_sandbox_path_literal(path)})"
        for path in closure.executable_paths
    )
    return (
        NETWORK_SANDBOX_PROFILE
        + "(deny file-read*)"
        f"(allow file-read* {read_filters})"
        "(deny file-write*)"
        f"(allow file-write* (literal \"/dev/null\") (subpath {_sandbox_path_literal(scratch)}))"
        "(deny process-exec*)"
        f"(allow process-exec {exec_filters})"
    )


def _parent_worker_sandbox_profile(
    snapshot: Path,
    scratch: Path,
    closure: _RuntimeSandboxClosure,
) -> str:
    snapshot = snapshot.resolve(strict=True)
    scratch = scratch.resolve(strict=True)
    return _parent_worker_sandbox_profile_from_bound_paths(snapshot, scratch, closure)


def _parent_worker_sandbox_profile_from_bound_paths(
    snapshot: Path,
    scratch: Path,
    closure: _RuntimeSandboxClosure,
) -> str:
    if (
        not snapshot.is_absolute()
        or str(snapshot) != os.path.normpath(str(snapshot))
        or not scratch.is_absolute()
        or str(scratch) != os.path.normpath(str(scratch))
        or snapshot == scratch
    ):
        raise OfflineEvidenceError("parent worker sandbox bound paths are malformed")
    read_subpaths = tuple(dict.fromkeys((snapshot, scratch, *closure.read_subpaths)))
    read_literals = _sandbox_ancestor_literals(
        (*read_subpaths, *closure.read_literals, *closure.executable_paths)
    )
    read_filters = " ".join(
        [
            *(f"(literal {_sandbox_path_literal(path)})" for path in read_literals),
            *(f"(subpath {_sandbox_path_literal(path)})" for path in read_subpaths),
        ]
    )
    exec_filters = " ".join(
        f"(literal {_sandbox_path_literal(path)})"
        for path in tuple(dict.fromkeys(closure.executable_paths[:2]))
    )
    return (
        NETWORK_SANDBOX_PROFILE
        + "(deny file-read*)"
        f"(allow file-read* {read_filters})"
        "(deny file-write*)"
        f"(allow file-write* (literal \"/dev/null\") (subpath {_sandbox_path_literal(scratch)}))"
        "(deny process-exec*)"
        f"(allow process-exec {exec_filters})"
    )


def _stage_child_sandbox_profile(
    scratch: _ComponentScratch,
    profile: str,
) -> _HeldFile:
    if not isinstance(profile, str) or not profile:
        raise OfflineEvidenceError("child sandbox profile is invalid")
    payload = profile.encode("utf-8")
    _write_component_scratch_input(
        scratch,
        "component.sb",
        payload,
        "child sandbox profile",
    )
    held = _hold_file_under_root(
        scratch.path / "component.sb",
        scratch.path,
        "child sandbox profile",
        max_bytes=2 * 1024 * 1024,
    )
    if held.payload != payload:
        _close_held_file(held)
        raise OfflineEvidenceError("child sandbox profile bytes changed while held")
    return held


def _held_sandbox_profile_argument(held: _HeldFile) -> str:
    if type(held.descriptor) is not int or held.descriptor <= 2:
        raise OfflineEvidenceError("child sandbox profile descriptor is invalid")
    return "/dev/stdin"


def _revalidate_held_sandbox_profile(held: _HeldFile, profile: str) -> None:
    expected = profile.encode("utf-8")
    if held.payload != expected:
        raise OfflineEvidenceError("child sandbox held profile bytes mismatch")
    try:
        descriptor_state = os.fstat(held.descriptor)
        named_state = os.stat(
            held.path.name,
            dir_fd=held.parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise OfflineEvidenceError("child sandbox held profile is unavailable") from exc
    if (
        _state_identity(descriptor_state) != _state_identity(held.state)
        or _state_identity(named_state) != _state_identity(held.state)
        or _descriptor_regular_file_path(
            held.descriptor,
            "child sandbox held profile",
        )
        != held.path
    ):
        raise OfflineEvidenceError("child sandbox held profile identity changed")
    if (
        _read_open_bytes(
            held.descriptor,
            held.state,
            "child sandbox held profile",
            max_bytes=2 * 1024 * 1024,
        )
        != expected
    ):
        raise OfflineEvidenceError("child sandbox held profile bytes changed")


def _child_sandbox_binding(
    *,
    profile: str,
    snapshot: _PrivateSnapshot,
    scratch: _ComponentScratch,
    denial_probe: _ComponentScratch,
    closure: _RuntimeSandboxClosure,
) -> dict[str, Any]:
    return _child_sandbox_binding_for_paths(
        profile=profile,
        snapshot_path=snapshot.path,
        snapshot_identity=snapshot.identity,
        scratch_path=scratch.path,
        denial_probe_path=denial_probe.path,
        closure=closure,
    )


def _child_sandbox_binding_for_paths(
    *,
    profile: str,
    snapshot_path: Path,
    snapshot_identity: Mapping[str, Any],
    scratch_path: Path,
    denial_probe_path: Path,
    closure: _RuntimeSandboxClosure,
) -> dict[str, Any]:
    read_probe = denial_probe_path / "read-probe"
    write_probe = denial_probe_path / "write-probe"
    value: dict[str, Any] = {
        "schema_version": "cloud-v2-child-sandbox-binding-v2",
        "profile_sha256": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
        "profile_template_sha256": hashlib.sha256(
            CHILD_FILESYSTEM_SANDBOX_TEMPLATE.encode("utf-8")
        ).hexdigest(),
        "snapshot_path_sha256": hashlib.sha256(
            str(snapshot_path).encode("utf-8")
        ).hexdigest(),
        "snapshot_identity_sha256": snapshot_identity["identity_sha256"],
        "scratch_path_sha256": hashlib.sha256(
            str(scratch_path).encode("utf-8")
        ).hexdigest(),
        "denied_read_probe_path_sha256": hashlib.sha256(
            str(read_probe).encode("utf-8")
        ).hexdigest(),
        "denied_write_probe_path_sha256": hashlib.sha256(
            str(write_probe).encode("utf-8")
        ).hexdigest(),
        "runtime_closure_identity_sha256": closure.identity["identity_sha256"],
    }
    value["identity_sha256"] = _identity_sha256(value)
    return value


def _parent_worker_sandbox_binding(
    *,
    profile: str,
    snapshot: _PrivateSnapshot,
    scratch: _ComponentScratch,
    denial_probe: _ComponentScratch,
    closure: _RuntimeSandboxClosure,
) -> dict[str, Any]:
    return _parent_worker_sandbox_binding_for_paths(
        profile=profile,
        snapshot_path=snapshot.path,
        snapshot_identity=snapshot.identity,
        scratch_path=scratch.path,
        denial_probe_path=denial_probe.path,
        closure=closure,
    )


def _parent_worker_sandbox_binding_for_paths(
    *,
    profile: str,
    snapshot_path: Path,
    snapshot_identity: Mapping[str, Any],
    scratch_path: Path,
    denial_probe_path: Path,
    closure: _RuntimeSandboxClosure,
) -> dict[str, Any]:
    value = _child_sandbox_binding_for_paths(
        profile=profile,
        snapshot_path=snapshot_path,
        snapshot_identity=snapshot_identity,
        scratch_path=scratch_path,
        denial_probe_path=denial_probe_path,
        closure=closure,
    )
    value["schema_version"] = PARENT_WORKER_SANDBOX_SCHEMA_VERSION
    value["profile_template_sha256"] = hashlib.sha256(
        PARENT_WORKER_SANDBOX_TEMPLATE.encode("utf-8")
    ).hexdigest()
    value["identity_sha256"] = _identity_sha256(
        {key: item for key, item in value.items() if key != "identity_sha256"}
    )
    return value


def _create_denial_probe(component: str) -> _ComponentScratch:
    probe = _create_component_scratch(f"{component}-denial-probe")
    try:
        _write_component_scratch_input(
            probe,
            "read-probe",
            b"must-not-be-readable-by-component\n",
            "component denied-read probe",
        )
        return probe
    except Exception:
        _close_component_scratch(probe)
        raise


def _component_sandbox_context(
    child_sandbox: Mapping[str, Any],
    denial_probe: _ComponentScratch,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "cloud-v2-active-component-sandbox-v1",
        "sandbox_binding_sha256": child_sandbox["identity_sha256"],
        "denied_read_path": str(denial_probe.path / "read-probe"),
        "denied_write_path": str(denial_probe.path / "write-probe"),
        "denied_exec_path": "/usr/bin/true",
    }
    value["identity_sha256"] = _identity_sha256(value)
    return value


def _validated_component_sandbox_context(value: object) -> dict[str, Any]:
    expected = {
        "schema_version",
        "sandbox_binding_sha256",
        "denied_read_path",
        "denied_write_path",
        "denied_exec_path",
        "identity_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise OfflineEvidenceError("active component sandbox context is malformed")
    core = {key: value[key] for key in expected if key != "identity_sha256"}
    if (
        value["schema_version"] != "cloud-v2-active-component-sandbox-v1"
        or not isinstance(value["sandbox_binding_sha256"], str)
        or not _SHA256.fullmatch(value["sandbox_binding_sha256"])
        or value["identity_sha256"] != _identity_sha256(core)
    ):
        raise OfflineEvidenceError("active component sandbox context is malformed")
    paths: dict[str, Path] = {}
    for field in ("denied_read_path", "denied_write_path", "denied_exec_path"):
        raw_path = value[field]
        if (
            not isinstance(raw_path, str)
            or not raw_path
            or _has_control_character(raw_path)
        ):
            raise OfflineEvidenceError("active component sandbox context is malformed")
        path = Path(raw_path)
        if not path.is_absolute() or path != Path(os.path.normpath(raw_path)):
            raise OfflineEvidenceError("active component sandbox context is malformed")
        paths[field] = path
    if (
        paths["denied_read_path"].parent != paths["denied_write_path"].parent
        or paths["denied_read_path"].name != "read-probe"
        or paths["denied_write_path"].name != "write-probe"
        or paths["denied_exec_path"] != Path("/usr/bin/true")
    ):
        raise OfflineEvidenceError("active component sandbox context is malformed")
    return dict(value)


def _probe_active_component_sandbox(
    context: Mapping[str, Any],
) -> dict[str, Any]:
    network_enforcement = _require_network_denial()
    read_denied = False
    try:
        Path(context["denied_read_path"]).read_bytes()
    except PermissionError:
        read_denied = True
    except OSError:
        read_denied = False
    write_denied = False
    write_path = Path(context["denied_write_path"])
    descriptor: int | None = None
    try:
        descriptor = os.open(
            write_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except PermissionError:
        write_denied = True
    except OSError:
        write_denied = False
    finally:
        if descriptor is not None:
            os.close(descriptor)
            try:
                write_path.unlink()
            except OSError:
                pass
    exec_denied = False
    try:
        _OS_SUBPROCESS_RUN(
            [context["denied_exec_path"]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except PermissionError:
        exec_denied = True
    except OSError:
        exec_denied = False
    if not (read_denied and write_denied and exec_denied):
        raise OfflineEvidenceError("active component sandbox denial probes failed")
    return {
        "schema_version": SANDBOX_ENFORCEMENT_SCHEMA_VERSION,
        "context_identity_sha256": context["identity_sha256"],
        "sandbox_binding_sha256": context["sandbox_binding_sha256"],
        "network_enforcement": network_enforcement,
        "denied_read": True,
        "denied_write": True,
        "denied_exec": True,
    }


def _install_active_component_sandbox_context(encoded: str) -> dict[str, Any]:
    global _ACTIVE_COMPONENT_SANDBOX_CONTEXT
    context = _validated_component_sandbox_context(_decode_expected_identity(encoded))
    marker = os.environ.get(_INHERITED_COMPONENT_SANDBOX_ENV)
    if marker != context["sandbox_binding_sha256"]:
        raise OfflineEvidenceError("inherited component sandbox is not bound")
    enforcement = _probe_active_component_sandbox(context)
    _ACTIVE_COMPONENT_SANDBOX_CONTEXT = context
    return enforcement


def _require_active_component_sandbox_binding() -> dict[str, Any]:
    context = _ACTIVE_COMPONENT_SANDBOX_CONTEXT
    if context is None:
        raise OfflineEvidenceError("inherited component sandbox is not bound")
    validated = _validated_component_sandbox_context(context)
    if os.environ.get(_INHERITED_COMPONENT_SANDBOX_ENV) != validated[
        "sandbox_binding_sha256"
    ]:
        raise OfflineEvidenceError("inherited component sandbox is not bound")
    return validated


def _require_active_component_sandbox_context() -> dict[str, Any]:
    validated = _require_active_component_sandbox_binding()
    return _probe_active_component_sandbox(validated)


def _validated_sandbox_enforcement(value: object) -> dict[str, Any]:
    fields = {
        "schema_version",
        "context_identity_sha256",
        "sandbox_binding_sha256",
        "network_enforcement",
        "denied_read",
        "denied_write",
        "denied_exec",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value["schema_version"] != SANDBOX_ENFORCEMENT_SCHEMA_VERSION
        or any(
            not isinstance(value[field], str) or not _SHA256.fullmatch(value[field])
            for field in ("context_identity_sha256", "sandbox_binding_sha256")
        )
        or not _type_sensitive_equal(
            value["network_enforcement"], _network_enforcement_success()
        )
        or any(value[field] is not True for field in ("denied_read", "denied_write", "denied_exec"))
    ):
        raise OfflineEvidenceError("test child sandbox enforcement is malformed")
    return dict(value)


def _current_process_executable() -> Path:
    """Return the kernel-observed executable, not the Python launcher label."""

    if sys.platform != "darwin":
        candidate = Path(sys.executable)
    else:
        try:
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            proc_pidpath = libproc.proc_pidpath
            proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
            proc_pidpath.restype = ctypes.c_int
            buffer = ctypes.create_string_buffer(4096)
            length = proc_pidpath(os.getpid(), buffer, len(buffer))
        except (AttributeError, OSError) as exc:
            raise OfflineEvidenceError(
                "Python process executable identity is unavailable"
            ) from exc
        if length <= 0:
            raise OfflineEvidenceError("Python process executable identity is unavailable")
        try:
            candidate = Path(os.fsdecode(buffer.raw[:length]))
        except (TypeError, UnicodeDecodeError) as exc:
            raise OfflineEvidenceError(
                "Python process executable identity is malformed"
            ) from exc
    if not candidate.is_absolute() or candidate.is_symlink():
        raise OfflineEvidenceError("Python process executable is unsafe")
    try:
        resolved = candidate.resolve(strict=True)
        state = resolved.stat(follow_symlinks=False)
    except OSError as exc:
        raise OfflineEvidenceError("Python process executable is unavailable") from exc
    if not stat.S_ISREG(state.st_mode) or not os.access(resolved, os.X_OK):
        raise OfflineEvidenceError("Python process executable is unsafe")
    return resolved


def _bound_regular_file_identity(path: Path, field: str) -> dict[str, Any]:
    descriptor: int | None = None
    parent_fd: int | None = None
    try:
        unresolved_state = path.lstat()
        resolved = path.resolve(strict=True)
        descriptor, parent_fd, opened, canonical = _open_regular_fd(
            resolved,
            field,
            allow_hardlink=True,
            enforce_safe_ancestors=False,
        )
        payload = _read_open_bytes(descriptor, opened, field)
        descriptor_state = os.fstat(descriptor)
        named_state = os.stat(
            resolved.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        unresolved_after = path.lstat()
        resolved_after = path.resolve(strict=True)
    except (OSError, OfflineEvidenceError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)
        raise OfflineEvidenceError(f"{field} identity is unavailable") from exc
    try:
        if (
            canonical != resolved
            or resolved_after != resolved
            or not stat.S_ISREG(descriptor_state.st_mode)
            or _state_identity(descriptor_state) != _state_identity(opened)
            or _state_identity(named_state) != _state_identity(opened)
            or _state_identity(unresolved_after) != _state_identity(unresolved_state)
        ):
            raise OfflineEvidenceError(f"{field} changed during inspection")
        return {
            "path_sha256": hashlib.sha256(str(path).encode("utf-8")).hexdigest(),
            "resolved_path_sha256": hashlib.sha256(
                str(resolved).encode("utf-8")
            ).hexdigest(),
            "path_is_symlink": stat.S_ISLNK(unresolved_state.st_mode),
            "device": descriptor_state.st_dev,
            "inode": descriptor_state.st_ino,
            "mode": descriptor_state.st_mode,
            "nlink": descriptor_state.st_nlink,
            "size": descriptor_state.st_size,
            "mtime_ns": descriptor_state.st_mtime_ns,
            "ctime_ns": descriptor_state.st_ctime_ns,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)


def _exact_production_embedding_fixture_path(
    value: object,
    *,
    field: str,
    directory: bool,
) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or _has_control_character(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        raise OfflineEvidenceError(f"{field} is malformed")
    raw = Path(value)
    canonical = _lexically_normal_absolute(raw, field)
    if str(canonical) != value or raw.is_symlink():
        raise OfflineEvidenceError(f"{field} is not an exact real path")
    try:
        resolved = raw.resolve(strict=True)
        state = raw.stat(follow_symlinks=False)
    except OSError as exc:
        raise OfflineEvidenceError(f"{field} is unavailable") from exc
    if resolved != raw or (
        directory and not stat.S_ISDIR(state.st_mode)
    ) or (
        not directory and not stat.S_ISREG(state.st_mode)
    ):
        raise OfflineEvidenceError(f"{field} is not an exact real path")
    return resolved


def _resolve_production_embedding_fixture(
    *,
    required: bool,
) -> _ProductionEmbeddingFixture | None:
    values = {name: os.environ.get(name) for name in _PRODUCTION_EMBEDDING_FIXTURE_ENV}
    present = {name: value is not None for name, value in values.items()}
    if not any(present.values()):
        if required:
            raise OfflineEvidenceError(
                "production embedding offline fixture is required"
            )
        return None
    if not all(present.values()) or any(values[name] == "" for name in values):
        raise OfflineEvidenceError(
            "production embedding offline fixture is incomplete"
        )
    declared_sha256 = values[_PRODUCTION_EMBEDDING_FIXTURE_ENV[2]]
    if not isinstance(declared_sha256, str) or not _SHA256.fullmatch(
        declared_sha256
    ):
        raise OfflineEvidenceError(
            "production embedding installer SHA-256 is malformed"
        )
    wheelhouse = _exact_production_embedding_fixture_path(
        values[_PRODUCTION_EMBEDDING_FIXTURE_ENV[0]],
        field="production embedding wheelhouse",
        directory=True,
    )
    installer = _exact_production_embedding_fixture_path(
        values[_PRODUCTION_EMBEDDING_FIXTURE_ENV[1]],
        field="production embedding installer",
        directory=False,
    )
    if installer.name != "python" or installer.parent.name != "bin":
        raise OfflineEvidenceError(
            "production embedding installer layout is not fixed"
        )
    installer_root = _exact_production_embedding_fixture_path(
        str(installer.parent.parent),
        field="production embedding installer root",
        directory=True,
    )
    wheelhouse_identity, wheelhouse_literals = _bound_runtime_tree_identity(
        wheelhouse,
        "production embedding wheelhouse tree",
        reject_symlinks=True,
    )
    installer_tree_identity, installer_literals = _bound_runtime_tree_identity(
        installer_root,
        "production embedding installer tree",
        reject_symlinks=True,
    )
    installer_identity = _bound_regular_file_identity(
        installer,
        "production embedding installer executable",
    )
    if (
        installer_identity["path_is_symlink"] is not False
        or installer_identity["nlink"] != 1
        or stat.S_IMODE(installer_identity["mode"]) & 0o111 == 0
    ):
        raise OfflineEvidenceError(
            "production embedding installer executable is unsafe"
        )
    if not hmac.compare_digest(installer_identity["sha256"], declared_sha256):
        raise OfflineEvidenceError(
            "production embedding installer SHA-256 mismatch"
        )
    identity: dict[str, Any] = {
        "schema_version": "cloud-v2-production-embedding-offline-fixture-v1",
        "status": "configured",
        "environment_variable_names": list(_PRODUCTION_EMBEDDING_FIXTURE_ENV),
        "wheelhouse_tree": wheelhouse_identity,
        "installer_tree": installer_tree_identity,
        "installer_executable": installer_identity,
        "declared_installer_sha256": declared_sha256,
        "symlink_policy": "reject-entire-fixture-tree",
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return _ProductionEmbeddingFixture(
        identity=identity,
        wheelhouse=wheelhouse,
        installer=installer,
        installer_root=installer_root,
        read_literals=tuple(
            sorted(set((*wheelhouse_literals, *installer_literals)), key=str)
        ),
    )


def _revalidate_production_embedding_fixture(
    fixture: _ProductionEmbeddingFixture,
) -> None:
    current = _resolve_production_embedding_fixture(required=True)
    if (
        current is None
        or current.identity != fixture.identity
        or current.wheelhouse != fixture.wheelhouse
        or current.installer != fixture.installer
        or current.installer_root != fixture.installer_root
        or current.read_literals != fixture.read_literals
    ):
        raise OfflineEvidenceError(
            "production embedding offline fixture identity changed"
        )


def _production_embedding_probe_closure(
    base: _RuntimeSandboxClosure,
    fixture: _ProductionEmbeddingFixture,
    *,
    target_executable: Path | None,
) -> _RuntimeSandboxClosure:
    base_executable = Path(sys._base_executable).resolve(strict=True)
    planned_target: Path | None = None
    if target_executable is not None:
        planned_target = _lexically_normal_absolute(
            target_executable,
            "production embedding planned target executable",
        )
        if planned_target != target_executable:
            raise OfflineEvidenceError(
                "production embedding planned target executable is not canonical"
            )
    executable_paths = tuple(
        dict.fromkeys(
            (
                *base.executable_paths,
                *(() if planned_target is None else (base_executable, fixture.installer, planned_target)),
            )
        )
    )
    identity: dict[str, Any] = {
        "schema_version": "cloud-v2-production-embedding-probe-closure-v1",
        "base_runtime_closure_identity_sha256": base.identity["identity_sha256"],
        "fixture_identity_sha256": fixture.identity["identity_sha256"],
        "mode": "fixture-read-only" if planned_target is None else "smoke-child",
        "planned_target_path_sha256": (
            None
            if planned_target is None
            else hashlib.sha256(str(planned_target).encode("utf-8")).hexdigest()
        ),
        "executable_path_set_sha256": _identity_sha256(
            [str(path) for path in executable_paths]
        ),
        "read_literal_path_set_sha256": _identity_sha256(
            sorted(str(path) for path in {*base.read_literals, *fixture.read_literals})
        ),
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return _RuntimeSandboxClosure(
        identity=identity,
        read_subpaths=base.read_subpaths,
        read_literals=tuple(
            sorted({*base.read_literals, *fixture.read_literals}, key=str)
        ),
        executable_paths=executable_paths,
    )



def _ocr_parent_probe_font_identity() -> dict[str, Any]:
    path = _OCR_POPPLER_FALLBACK_FONT_PATH
    anchor = _OCR_POPPLER_FONTCONFIG_FILES[0]
    identity = _bound_regular_file_identity(
        path,
        "real OCR parent probe fallback font",
    )
    path_sha256 = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
    if (
        path.resolve(strict=True) != path
        or identity["path_sha256"] != path_sha256
        or identity["resolved_path_sha256"] != path_sha256
        or identity["path_is_symlink"] is not False
        or identity["nlink"] != 1
        or identity["size"] != anchor["size"]
        or identity["sha256"] != anchor["sha256"]
    ):
        raise OfflineEvidenceError(
            "real OCR parent probe fallback font identity is not approved"
        )
    core: dict[str, Any] = {
        "schema_version": "cloud-v2-real-ocr-parent-probe-font-v1",
        "source_path_sha256": path_sha256,
        "approved_size": anchor["size"],
        "approved_sha256": anchor["sha256"],
        "file_identity": identity,
    }
    core["identity_sha256"] = _identity_sha256(core)
    return core


def _ocr_parent_probe_closure(
    base: _RuntimeSandboxClosure,
    *,
    probe_id: str,
    tessdata_path: Path | None = None,
    tessdata_identity: Mapping[str, Any] | None = None,
) -> _RuntimeSandboxClosure:
    tessdata_probe = _is_ocr_tessdata_probe(probe_id)
    if (
        not _is_ocr_native_probe(probe_id)
        or (tessdata_path is None) != (tessdata_identity is None)
        or tessdata_probe != (tessdata_path is not None)
    ):
        raise OfflineEvidenceError("real OCR parent probe closure scope is not exact")
    canonical: Path | None = None
    if tessdata_path is not None:
        assert tessdata_identity is not None
        canonical = _lexically_normal_absolute(
            tessdata_path,
            "private OCR tessdata snapshot path",
        )
        if canonical != tessdata_path:
            raise OfflineEvidenceError(
                "private OCR tessdata snapshot path is not canonical"
            )
        identity_core = {
            field: tessdata_identity.get(field)
            for field in (
                "schema_version",
                "source_identity_sha256",
                "root_mode",
                "file_count",
                "file_names",
                "file_set_sha256",
                "files",
            )
        }
        if (
            tessdata_identity.get("identity_sha256")
            != _identity_sha256(identity_core)
            or identity_core["schema_version"]
            != "cloud-v2-private-ocr-tessdata-snapshot-v1"
            or identity_core["file_names"] != list(_OCR_TESSDATA_SNAPSHOT_NAMES)
        ):
            raise OfflineEvidenceError(
                "private OCR tessdata snapshot identity is malformed"
            )
    read_subpaths = tuple(
        dict.fromkeys(
            (
                *base.read_subpaths,
                *(() if canonical is None else (canonical,)),
            )
        )
    )
    font_identity = _ocr_parent_probe_font_identity()
    read_literals = tuple(
        sorted(
            {
                *base.read_literals,
                _OCR_POPPLER_FALLBACK_FONT_PATH,
                *_OCR_POPPLER_FALLBACK_FONT_PATH.parents,
            },
            key=str,
        )
    )
    identity: dict[str, Any] = {
        "schema_version": "cloud-v2-real-ocr-parent-probe-closure-v2",
        "base_runtime_closure_identity_sha256": base.identity["identity_sha256"],
        "font_source_identity": font_identity,
        "font_source_identity_sha256": font_identity["identity_sha256"],
        "tessdata_snapshot_identity_sha256": (
            None
            if tessdata_identity is None
            else tessdata_identity["identity_sha256"]
        ),
        "tessdata_snapshot_path_sha256": (
            None
            if canonical is None
            else hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()
        ),
        "read_subpath_set_sha256": _identity_sha256(
            [str(path) for path in read_subpaths]
        ),
        "read_literal_path_set_sha256": _identity_sha256(
            [str(path) for path in read_literals]
        ),
        "executable_path_set_sha256": _identity_sha256(
            [str(path) for path in base.executable_paths]
        ),
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return _RuntimeSandboxClosure(
        identity=identity,
        read_subpaths=read_subpaths,
        read_literals=read_literals,
        executable_paths=base.executable_paths,
    )


def _revalidate_ocr_parent_probe_closure(
    expected: _RuntimeSandboxClosure,
    base: _RuntimeSandboxClosure,
    *,
    probe_id: str,
    snapshot: _SealedTessdataSnapshot | None,
) -> None:
    if _is_ocr_tessdata_probe(probe_id) != (snapshot is not None):
        raise OfflineEvidenceError("real OCR parent probe closure scope is not exact")
    if snapshot is not None:
        _revalidate_sealed_tessdata_snapshot(snapshot)
    current = _ocr_parent_probe_closure(
        base,
        probe_id=probe_id,
        tessdata_path=None if snapshot is None else snapshot.path,
        tessdata_identity=None if snapshot is None else snapshot.identity,
    )
    if current != expected:
        raise OfflineEvidenceError(
            "real OCR parent probe runtime closure identity changed"
        )

def _revalidate_production_embedding_probe_closure(
    expected: _RuntimeSandboxClosure,
    base: _RuntimeSandboxClosure,
    fixture: _ProductionEmbeddingFixture,
    *,
    target_executable: Path | None,
) -> None:
    _revalidate_production_embedding_fixture(fixture)
    current = _production_embedding_probe_closure(
        base,
        fixture,
        target_executable=target_executable,
    )
    if current != expected:
        raise OfflineEvidenceError(
            "production embedding probe runtime closure identity changed"
        )


def _verify_production_embedding_target_executable(
    path: Path,
    *,
    python_identity: Mapping[str, Any],
) -> dict[str, Any]:
    expected = _lexically_normal_absolute(
        path,
        "production embedding target executable",
    )
    if expected != path or path.is_symlink():
        raise OfflineEvidenceError(
            "production embedding target executable is unsafe"
        )
    identity = _bound_regular_file_identity(
        path,
        "production embedding target executable",
    )
    if (
        identity["path_is_symlink"] is not False
        or identity["nlink"] != 1
        or not stat.S_ISREG(identity["mode"])
        or not stat.S_IMODE(identity["mode"]) & 0o111
        or identity["path_sha256"] != identity["resolved_path_sha256"]
    ):
        raise OfflineEvidenceError(
            "production embedding target executable is unsafe"
        )
    identity["identity_sha256"] = _identity_sha256(identity)
    return _validated_production_embedding_target_executable_identity(
        identity,
        expected_path=path,
        python_identity=python_identity,
    )


def _validated_production_embedding_target_executable_identity(
    value: object,
    *,
    expected_path: Path,
    python_identity: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "path_sha256",
        "resolved_path_sha256",
        "path_is_symlink",
        "device",
        "inode",
        "mode",
        "nlink",
        "size",
        "mtime_ns",
        "ctime_ns",
        "sha256",
        "identity_sha256",
    }
    expected = _lexically_normal_absolute(
        expected_path,
        "production embedding persisted target executable",
    )
    if not isinstance(python_identity, Mapping):
        raise OfflineEvidenceError(
            "production embedding target executable identity is malformed"
        )
    base_sha256 = python_identity.get("base_executable_sha256")
    base_size = python_identity.get("base_executable_size")
    if (
        expected != expected_path
        or not isinstance(value, Mapping)
        or set(value) != fields
        or not isinstance(base_sha256, str)
        or not _SHA256.fullmatch(base_sha256)
        or type(base_size) is not int
        or base_size <= 0
    ):
        raise OfflineEvidenceError(
            "production embedding target executable identity is malformed"
        )
    expected_path_sha256 = hashlib.sha256(str(expected).encode("utf-8")).hexdigest()
    for field in ("path_sha256", "resolved_path_sha256", "sha256", "identity_sha256"):
        if not isinstance(value[field], str) or not _SHA256.fullmatch(value[field]):
            raise OfflineEvidenceError(
                "production embedding target executable identity is malformed"
            )
    for field in ("device", "inode", "mode", "nlink", "size", "mtime_ns", "ctime_ns"):
        if type(value[field]) is not int or value[field] < 0:
            raise OfflineEvidenceError(
                "production embedding target executable identity is malformed"
            )
    core = {field: value[field] for field in fields if field != "identity_sha256"}
    if (
        value["path_sha256"] != expected_path_sha256
        or value["resolved_path_sha256"] != expected_path_sha256
        or value["path_is_symlink"] is not False
        or value["inode"] <= 0
        or value["nlink"] != 1
        or value["size"] <= 0
        or not stat.S_ISREG(value["mode"])
        or not stat.S_IMODE(value["mode"]) & 0o111
        or not hmac.compare_digest(value["sha256"], base_sha256)
        or value["size"] != base_size
        or value["identity_sha256"] != _identity_sha256(core)
    ):
        raise OfflineEvidenceError(
            "production embedding target executable identity mismatch"
        )
    return dict(value)


def _python_executable() -> Path:
    executable = Path(sys.executable)
    if not executable.is_absolute():
        raise OfflineEvidenceError("Python executable must be an absolute path")
    if executable.is_symlink():
        raise OfflineEvidenceError("Python executable launcher must not be a symlink")
    try:
        resolved = executable.resolve(strict=True)
    except OSError as exc:
        raise OfflineEvidenceError("Python executable is unavailable") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise OfflineEvidenceError("Python executable is unavailable")
    return resolved


def _python_identity(executable: Path | None = None) -> dict[str, Any]:
    executable = _python_executable() if executable is None else executable
    try:
        executable = executable.resolve(strict=True)
        executable_parent_state = executable.parent.stat(follow_symlinks=False)
        base_executable = Path(sys._base_executable).resolve(strict=True)
        process_executable = _current_process_executable()
        executable_identity = _bound_regular_file_identity(
            executable,
            "Python executable",
        )
        base_identity = _bound_regular_file_identity(
            base_executable,
            "Python base executable",
        )
        process_identity = _bound_regular_file_identity(
            process_executable,
            "Python process executable",
        )
        runtime_environment = _runtime_environment_identity()
        if (
            _state_identity(executable.parent.stat(follow_symlinks=False))
            != _state_identity(executable_parent_state)
            or _bound_regular_file_identity(executable, "Python executable")
            != executable_identity
            or _bound_regular_file_identity(
                base_executable,
                "Python base executable",
            )
            != base_identity
            or _bound_regular_file_identity(
                process_executable,
                "Python process executable",
            )
            != process_identity
        ):
            raise OfflineEvidenceError(
                "Python executable identity changed during inspection"
            )
    except (OSError, OfflineEvidenceError) as exc:
        raise OfflineEvidenceError("Python executable identity is unavailable") from exc
    return {
        "implementation": sys.implementation.name,
        "version": ".".join(str(part) for part in sys.version_info[:3]),
        "executable_sha256": executable_identity["sha256"],
        "executable_device": executable_identity["device"],
        "executable_inode": executable_identity["inode"],
        "executable_mode": executable_identity["mode"],
        "executable_nlink": executable_identity["nlink"],
        "executable_size": executable_identity["size"],
        "executable_mtime_ns": executable_identity["mtime_ns"],
        "executable_ctime_ns": executable_identity["ctime_ns"],
        "executable_parent_path_sha256": hashlib.sha256(
            str(executable.parent).encode("utf-8")
        ).hexdigest(),
        "executable_parent_device": executable_parent_state.st_dev,
        "executable_parent_inode": executable_parent_state.st_ino,
        "executable_parent_mode": executable_parent_state.st_mode,
        "executable_parent_nlink": executable_parent_state.st_nlink,
        "executable_parent_size": executable_parent_state.st_size,
        "executable_parent_mtime_ns": executable_parent_state.st_mtime_ns,
        "executable_parent_ctime_ns": executable_parent_state.st_ctime_ns,
        "base_executable_sha256": base_identity["sha256"],
        "base_executable_device": base_identity["device"],
        "base_executable_inode": base_identity["inode"],
        "base_executable_mode": base_identity["mode"],
        "base_executable_nlink": base_identity["nlink"],
        "base_executable_size": base_identity["size"],
        "base_executable_mtime_ns": base_identity["mtime_ns"],
        "base_executable_ctime_ns": base_identity["ctime_ns"],
        "process_executable_sha256": process_identity["sha256"],
        "process_executable_device": process_identity["device"],
        "process_executable_inode": process_identity["inode"],
        "process_executable_mode": process_identity["mode"],
        "process_executable_nlink": process_identity["nlink"],
        "process_executable_size": process_identity["size"],
        "process_executable_mtime_ns": process_identity["mtime_ns"],
        "process_executable_ctime_ns": process_identity["ctime_ns"],
        "process_executable_path_sha256": hashlib.sha256(
            str(process_executable).encode("utf-8")
        ).hexdigest(),
        "independent_executable_copy": (
            executable_identity["device"],
            executable_identity["inode"],
        )
        != (base_identity["device"], base_identity["inode"]),
        "runtime_environment": runtime_environment,
    }


def _test_scope_identity(
    repo_root: Path,
    *,
    repo_fd: int | None = None,
    force_content: bool = False,
    materialized: bool = False,
    tree_roots: Sequence[str] | None = None,
    exact_files: Sequence[str] | None = None,
) -> dict[str, Any]:
    del force_content
    raw_root = Path(repo_root)
    owned_fd: int | None = None
    if repo_fd is None:
        if raw_root.is_symlink():
            raise OfflineEvidenceError("repository root must be a real directory")
        repository, owned_fd = _open_directory_fd(raw_root, "repository root")
        active_fd = owned_fd
    else:
        repository = _resolved_parent_path(raw_root, "repository root")
        active_fd = repo_fd
    try:
        _require_formal_repository_identity(active_fd)
        identity = _test_scope_identity_from_fd(
            active_fd,
            materialized=materialized,
            tree_roots=tree_roots,
            exact_files=exact_files,
        )
        _revalidate_directory_path(repository, active_fd, "repository root")
        return identity
    finally:
        if owned_fd is not None:
            os.close(owned_fd)


def _validated_repository_root(repo_root: str | Path) -> Path:
    raw_root = Path(repo_root)
    if raw_root.is_symlink():
        raise OfflineEvidenceError("repository root must be a real directory")
    root, root_fd = _open_directory_fd(raw_root, "repository root")
    try:
        _require_formal_repository_identity(root_fd)
        return root
    finally:
        os.close(root_fd)


def _module_repository_root() -> Path:
    return _absolute_path(__file__, "offline evidence source").parents[2]


def _test_runner_identity(
    repo_root: Path,
    *,
    repo_fd: int | None = None,
    test_scope: Mapping[str, Any] | None = None,
    python_identity: Mapping[str, Any] | None = None,
    external_tool_identity: Mapping[str, Any] | None = None,
    sandbox_closure_identity: Mapping[str, Any] | None = None,
    production_embedding_fixture: _ProductionEmbeddingFixture | None = None,
    approved_tessdata_input: _ApprovedTessdataInput | None = None,
    executed_runner_source_sha256: str | None = None,
    executed_runner_state_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_root = Path(repo_root)
    owned_fd: int | None = None
    owned_tessdata_input: _ApprovedTessdataInput | None = None
    if repo_fd is None:
        if raw_root.is_symlink():
            raise OfflineEvidenceError("repository root must be a real directory")
        repository, owned_fd = _open_directory_fd(raw_root, "repository root")
        active_fd = owned_fd
    else:
        repository = _resolved_parent_path(raw_root, "repository root")
        active_fd = repo_fd
    try:
        _require_formal_repository_identity(active_fd)
        materialized = _formal_materialized_snapshot_matches(active_fd)
        scope_state_before = _snapshot_live_state_identity_from_fd(
            active_fd,
            tree_roots=_TEST_SNAPSHOT_TREE_ROOTS,
            exact_files=_TEST_SNAPSHOT_FILES,
        )
        _repository_source, repository_binding = _stable_relative_file_binding(
            active_fd,
            OFFLINE_EVIDENCE_SOURCE_PATH,
            "offline evidence source",
            max_bytes=4 * 1024 * 1024,
        )
        repository_source_sha256 = repository_binding["sha256"]
        loaded_source_sha256 = (
            _EXECUTED_RUNNER_SOURCE_SHA256
            if executed_runner_source_sha256 is None
            else executed_runner_source_sha256
        )
        loaded_source_state = (
            _EXECUTED_RUNNER_STATE_IDENTITY
            if executed_runner_state_identity is None
            else executed_runner_state_identity
        )
        if (
            not isinstance(loaded_source_sha256, str)
            or not _SHA256.fullmatch(loaded_source_sha256)
            or not isinstance(loaded_source_state, Mapping)
            or set(loaded_source_state) != set(_RUNNER_STATE_FIELDS)
        ):
            raise OfflineEvidenceError("formal CLI bootstrap context is required")
        if (
            repository_source_sha256 != loaded_source_sha256
            or _runner_state_from_binding(repository_binding)
            != dict(loaded_source_state)
        ):
            raise OfflineEvidenceError(
                "loaded offline evidence source differs from the repository source"
            )
        observed_scope_identity = _test_scope_identity(
            repository,
            repo_fd=active_fd,
            force_content=True,
            materialized=materialized,
        )
        if test_scope is None:
            scope_identity = observed_scope_identity
        elif not isinstance(test_scope, Mapping):
            raise OfflineEvidenceError("test runner scope identity is malformed")
        else:
            scope_identity = dict(test_scope)
            if not _type_sensitive_equal(scope_identity, observed_scope_identity):
                raise OfflineEvidenceError(
                    "test runner scope differs from the repository source"
                )
        resolved_python_identity = (
            dict(python_identity)
            if python_identity is not None
            else _python_identity()
        )
        external_tool_set = _resolve_external_tools()
        resolved_external_tool_identity = (
            dict(external_tool_identity)
            if external_tool_identity is not None
            else external_tool_set.identity
        )
        resolved_sandbox_closure_identity = (
            dict(sandbox_closure_identity)
            if sandbox_closure_identity is not None
            else _runtime_sandbox_closure(
                python=_python_executable(),
                python_identity=resolved_python_identity,
                external_tools=external_tool_set,
            ).identity
        )
        resolved_production_embedding_fixture = (
            _resolve_production_embedding_fixture(required=False)
            if production_embedding_fixture is None
            else production_embedding_fixture
        )
        if resolved_production_embedding_fixture is not None:
            _revalidate_production_embedding_fixture(
                resolved_production_embedding_fixture
            )
        if approved_tessdata_input is None:
            resolved_tessdata_input = _resolve_approved_tessdata_input(
                required=False
            )
            owned_tessdata_input = resolved_tessdata_input
        else:
            resolved_tessdata_input = approved_tessdata_input
        if resolved_tessdata_input is not None:
            _revalidate_approved_tessdata_input(resolved_tessdata_input)
        identity = {
            "schema_version": TEST_RUNNER_SCHEMA_VERSION,
            "source_sha256": repository_source_sha256,
            "python_identity": resolved_python_identity,
            "network_policy": _network_policy(),
            "external_tools": resolved_external_tool_identity,
            "sandbox_closure": resolved_sandbox_closure_identity,
            "production_embedding_fixture": (
                None
                if resolved_production_embedding_fixture is None
                else resolved_production_embedding_fixture.identity
            ),
            "approved_ocr_tessdata_input": (
                None
                if resolved_tessdata_input is None
                else resolved_tessdata_input.identity
            ),
            "test_scope": scope_identity,
            "formal_parent_probe_policy": _formal_parent_probe_policy(),
        }
        final_scope_identity = _test_scope_identity(
            repository,
            repo_fd=active_fd,
            force_content=True,
            materialized=materialized,
        )
        scope_state_after = _snapshot_live_state_identity_from_fd(
            active_fd,
            tree_roots=_TEST_SNAPSHOT_TREE_ROOTS,
            exact_files=_TEST_SNAPSHOT_FILES,
        )
        if (
            not _type_sensitive_equal(final_scope_identity, scope_identity)
            or scope_state_after != scope_state_before
        ):
            raise OfflineEvidenceError(
                "repository test scope changed while runner identity was built"
            )
        _revalidate_directory_path(repository, active_fd, "repository root")
        return identity
    finally:
        if owned_tessdata_input is not None:
            _close_approved_tessdata_input(owned_tessdata_input)
        if owned_fd is not None:
            os.close(owned_fd)


def _formal_parent_probe_policy() -> dict[str, Any]:
    if "formal-security-probes" not in _TEST_COMPONENTS:
        value: dict[str, Any] = {
            "schema_version": "cloud-v2-formal-parent-probe-policy-v3",
            "enabled": False,
            "broker_protocol_schema_version": PARENT_BROKER_PROTOCOL_SCHEMA_VERSION,
            "broker_network_assurance": (
                "held-byte-fixed-command-broker-no-provider-data-plane"
            ),
            "broker_os_network_enforced": False,
            "broker_fsm_sha256": _identity_sha256({}),
            "probe_count": 0,
            "probe_ids_sha256": _identity_sha256([]),
            "coverage_mapping_sha256": _identity_sha256([]),
            "probes": [],
        }
        value["identity_sha256"] = _identity_sha256(value)
        return value
    mapping_records = [
        {
            "probe_id": probe_id,
            "source_path": source_path,
            "covered_test_id": covered_test_id,
        }
        for probe_id, source_path, covered_test_id in _FORMAL_PARENT_PROBE_SPECS
    ]
    if set(_FORMAL_PARENT_BROKER_PLANS) != {
        record["probe_id"] for record in mapping_records
    }:
        raise OfflineEvidenceError("formal parent broker plan coverage is not exact")
    records = [
        {
            **record,
            "broker_operation_ids": list(_parent_broker_plan(record["probe_id"])),
            "broker_operation_ids_sha256": _identity_sha256(
                _parent_broker_plan(record["probe_id"])
            ),
        }
        for record in mapping_records
    ]
    probe_ids = [record["probe_id"] for record in records]
    covered_ids = [record["covered_test_id"] for record in records]
    test_id_pattern = re.compile(
        r"^test_[a-z0-9_]+\.[A-Za-z_][A-Za-z0-9_]*\.test_[a-z0-9_]+$"
    )
    if (
        probe_ids != sorted(probe_ids)
        or len(probe_ids) != len(set(probe_ids))
        or len(covered_ids) != len(set(covered_ids))
        or bool(set(probe_ids) & set(_TEST_COMPONENTS))
        or any(not _IDENTIFIER.fullmatch(probe_id) for probe_id in probe_ids)
        or any(
            _canonical_relative(record["source_path"], "formal probe source")
            != record["source_path"]
            or not test_id_pattern.fullmatch(record["covered_test_id"])
            for record in records
        )
        or set(_FORMAL_PARENT_COVERED_TEST_IDS) != set(covered_ids)
        or _TEST_COMPONENT_SELECTIONS["formal-security-probes"][
            "excluded_test_ids"
        ]
        != _CLOUD_FORMAL_PARENT_COVERED_TEST_IDS
        or _TEST_COMPONENT_SELECTIONS["cloud-v2-tests"]["excluded_test_ids"]
        != _ALL_FORMAL_SECURITY_TEST_IDS
        or _TEST_COMPONENT_SELECTIONS["knowledge-graph-cloud-tests"][
            "excluded_test_ids"
        ]
        != _KNOWLEDGE_FORMAL_PARENT_COVERED_TEST_IDS
        or set(_PARENT_PROBE_TEST_COMPONENTS)
        != (
            {_PRODUCTION_EMBEDDING_PROBE_ID}
            if _PRODUCTION_EMBEDDING_PROBE_ID in probe_ids
            else set()
        )
    ):
        raise OfflineEvidenceError("formal parent probe mapping is malformed")
    baseline = {
        "probe_count": len(records),
        "probe_ids_sha256": _identity_sha256(probe_ids),
        "coverage_mapping_sha256": _identity_sha256(mapping_records),
    }
    if baseline != _FORMAL_PARENT_PROBE_BASELINE:
        raise OfflineEvidenceError("formal parent probe baseline mismatch")
    value = {
        "schema_version": "cloud-v2-formal-parent-probe-policy-v3",
        "enabled": bool(records),
        "broker_protocol_schema_version": PARENT_BROKER_PROTOCOL_SCHEMA_VERSION,
        "broker_network_assurance": (
            "held-byte-fixed-command-broker-no-provider-data-plane"
        ),
        "broker_os_network_enforced": False,
        "broker_fsm_sha256": _identity_sha256(
            {
                probe_id: list(_parent_broker_plan(probe_id))
                for probe_id in sorted(_FORMAL_PARENT_BROKER_PLANS)
            }
        ),
        **baseline,
        "probes": records,
    }
    value["identity_sha256"] = _identity_sha256(value)
    return value


def _formal_parent_probe_spec(probe_id: str) -> dict[str, Any]:
    policy = _formal_parent_probe_policy()
    for record in policy["probes"]:
        if record["probe_id"] == probe_id:
            return dict(record)
    raise OfflineEvidenceError("formal parent probe ID is not allowlisted")


def _expected_parent_probe_command(probe_id: str) -> tuple[str, list[str]]:
    _formal_parent_probe_spec(probe_id)
    return f"formal-parent-{probe_id}", [
        "sandbox-exec",
        "-f",
        "<bound-parent-worker-profile-stdin-pipe>",
        "python",
        "-I",
        "-S",
        "-B",
        "-c",
        "<held-formal-bootstrap>",
        "<bound-private-snapshot>",
        "<bound-formal-closure-manifest>",
        "<bound-formal-source-context>",
        "formal-parent-probe-worker",
        "--probe-id",
        probe_id,
        "--snapshot-identity",
        "<bound-private-snapshot-identity>",
        "--python-identity",
        "<bound-python-identity>",
        "--worker-sandbox-context",
        "<bound-parent-worker-sandbox-context>",
        "--broker-request-fd",
        "<broker-request-write-fd>",
        "--broker-response-fd",
        "<broker-response-read-fd>",
        "--broker-session",
        "<bound-broker-session>",
        "--broker-deadline-monotonic-ns",
        "<bound-parent-probe-deadline>",
    ]


def _expected_test_log_stems() -> tuple[str, ...]:
    policy = _formal_parent_probe_policy()
    return tuple(
        sorted(
            (
                *tuple(_TEST_COMPONENTS),
                *(record["probe_id"] for record in policy["probes"]),
            )
        )
    )


def _component_test_selection(name: str) -> dict[str, Any]:
    if name in _TEST_COMPONENTS:
        if set(_TEST_COMPONENT_SELECTIONS) != set(_TEST_COMPONENTS):
            raise OfflineEvidenceError("test component selection coverage is not exact")
        raw = _TEST_COMPONENT_SELECTIONS[name]
    elif name in _PARENT_PROBE_TEST_COMPONENTS:
        raw = _PARENT_PROBE_TEST_COMPONENTS[name][1]
    else:
        raise OfflineEvidenceError("test component name is not allowlisted")
    if not isinstance(raw, Mapping) or set(raw) != {
        "included_test_ids",
        "excluded_test_ids",
    }:
        raise OfflineEvidenceError("test component selection policy is malformed")
    included = raw["included_test_ids"]
    excluded = raw["excluded_test_ids"]
    test_id_pattern = re.compile(
        r"^test_[a-z0-9_]+\.[A-Za-z_][A-Za-z0-9_]*\.test_[a-z0-9_]+$"
    )
    for values in (included, excluded):
        if (
            not isinstance(values, tuple)
            or tuple(sorted(values)) != values
            or len(values) != len(set(values))
            or any(
                not isinstance(test_id, str)
                or not test_id_pattern.fullmatch(test_id)
                for test_id in values
            )
        ):
            raise OfflineEvidenceError("test component selection policy is malformed")
    if set(included) & set(excluded):
        raise OfflineEvidenceError("test component selection policy overlaps")
    return {
        "schema_version": "cloud-v2-test-component-selection-v1",
        "included_test_ids": list(included),
        "excluded_test_ids": list(excluded),
        "excluded_modules": [],
    }


def _component_test_baseline(name: str) -> dict[str, Any]:
    if name in _TEST_COMPONENTS:
        if set(_TEST_ID_BASELINES) != set(_TEST_COMPONENTS):
            raise OfflineEvidenceError("test ID baseline coverage is not exact")
        baseline = _TEST_ID_BASELINES[name]
    elif name in _PARENT_PROBE_TEST_COMPONENTS:
        baseline = _PARENT_PROBE_TEST_COMPONENTS[name][2]
    else:
        raise OfflineEvidenceError("test component name is not allowlisted")
    if (
        not isinstance(baseline, Mapping)
        or set(baseline) != {"test_count", "test_ids_sha256"}
        or type(baseline["test_count"]) is not int
        or baseline["test_count"] <= 0
        or not isinstance(baseline["test_ids_sha256"], str)
        or not _SHA256.fullmatch(baseline["test_ids_sha256"])
    ):
        raise OfflineEvidenceError("test ID baseline is malformed")
    return dict(baseline)


def _validated_test_id_manifest(
    name: str,
    test_ids: Sequence[str],
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if name not in {*_TEST_COMPONENTS, *_PARENT_PROBE_TEST_COMPONENTS}:
        raise OfflineEvidenceError("test component name is not allowlisted")
    ids = list(test_ids)
    if (
        not ids
        or ids != sorted(ids)
        or len(ids) != len(set(ids))
        or any(
            not isinstance(test_id, str)
            or len(test_id) > 512
            or _has_control_character(test_id)
            or unicodedata.normalize("NFC", test_id) != test_id
            for test_id in ids
        )
    ):
        raise OfflineEvidenceError("test ID manifest is malformed")
    expected = dict(_component_test_baseline(name) if baseline is None else baseline)
    digest = _identity_sha256(ids)
    if (
        set(expected) != {"test_count", "test_ids_sha256"}
        or type(expected.get("test_count")) is not int
        or expected.get("test_count") != len(ids)
        or not isinstance(expected.get("test_ids_sha256"), str)
        or expected.get("test_ids_sha256") != digest
    ):
        raise OfflineEvidenceError(f"test ID baseline mismatch: {name}")
    return {
        "schema_version": "cloud-v2-test-id-manifest-v1",
        "component": name,
        "test_count": len(ids),
        "test_ids_sha256": digest,
        "test_ids": ids,
    }


def _expected_test_command(name: str) -> tuple[str, list[str]]:
    try:
        command_id, start_directory = _TEST_COMPONENTS[name]
    except KeyError as exc:
        raise OfflineEvidenceError("test component name is not allowlisted") from exc
    return command_id, [
        "sandbox-exec",
        "-f",
        "<bound-child-profile-stdin-pipe>",
        "python",
        "-I",
        "-S",
        "-B",
        "-c",
        _UNITTEST_BOOTSTRAP,
        "<bound-module-closure-manifest>",
        name,
        start_directory,
        "<bound-python-identity>",
        "<bound-private-snapshot-identity>",
        _encode_expected_identity(_component_test_selection(name)),
        _encode_expected_identity(_component_test_baseline(name)),
        "<bound-active-sandbox-context>",
    ]


def _parse_unittest_log(payload: bytes) -> int:
    if len(payload) > 16 * 1024 * 1024:
        raise OfflineEvidenceError("test evidence log exceeds the closed size limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OfflineEvidenceError("test evidence log is not UTF-8") from exc
    summaries = _UNITTEST_SUMMARY.findall(text)
    if len(summaries) != 1:
        raise OfflineEvidenceError("test evidence log lacks one unittest summary")
    if _FAILURE_MARKER.search(text) or "Traceback (most recent call last)" in text:
        raise OfflineEvidenceError("test evidence log contains a failure marker")
    lines = text.splitlines()
    if not lines or lines[-1] != "OK":
        raise OfflineEvidenceError("test evidence log lacks a final exact OK result")
    try:
        count = int(summaries[0])
    except (TypeError, ValueError) as exc:
        raise OfflineEvidenceError("test evidence log has an invalid test count") from exc
    if count <= 0:
        raise OfflineEvidenceError("test evidence log has an invalid test count")
    return count


def _validated_component_set(
    component_set_file: Path,
    evidence_root: Path,
    *,
    repo_root: Path | None = None,
    repo_fd: int | None = None,
    component_set_payload: bytes | None = None,
    held_log_payloads: Mapping[str, bytes] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if component_set_payload is None:
        component_set_payload = _stable_file_bytes(
            component_set_file,
            "test component set",
            max_bytes=_TEST_COMPONENT_SET_MAX_BYTES,
        )
    elif len(component_set_payload) > _TEST_COMPONENT_SET_MAX_BYTES:
        raise OfflineEvidenceError("test component set exceeds the closed size limit")
    value = dict(
        _strict_json_bytes(component_set_payload, field="JSON evidence input")
    )
    if component_set_payload != canonical_json_bytes(value):
        raise OfflineEvidenceError("test component set is not canonical JSON")
    if set(value) != {"schema_version", "created_at", "runner", "components"}:
        raise OfflineEvidenceError("test component set does not match its closed schema")
    if value["schema_version"] != TEST_COMPONENT_SET_SCHEMA_VERSION:
        raise OfflineEvidenceError("test component set schema mismatch")
    created_at = _require_utc_second(
        value["created_at"], "test component set created_at"
    )
    runner = value["runner"]
    repository = _module_repository_root() if repo_root is None else Path(repo_root)
    owned_repo_fd: int | None = None
    try:
        try:
            if repo_fd is None:
                repository, owned_repo_fd = _open_directory_fd(
                    repository,
                    "repository root",
                )
                active_repo_fd = owned_repo_fd
            else:
                active_repo_fd = repo_fd
            _source, runner_binding = _stable_relative_file_binding(
                active_repo_fd,
                OFFLINE_EVIDENCE_SOURCE_PATH,
                "offline evidence validation source",
                max_bytes=4 * 1024 * 1024,
            )
            expected_runner = _test_runner_identity(
                repository,
                repo_fd=active_repo_fd,
                executed_runner_source_sha256=runner_binding["sha256"],
                executed_runner_state_identity=_runner_state_from_binding(
                    runner_binding
                ),
            )
        except OfflineEvidenceError as exc:
            raise OfflineEvidenceError(
                "test runner identity or network policy mismatch"
            ) from exc
        if not _type_sensitive_equal(runner, expected_runner):
            raise OfflineEvidenceError("test runner identity or network policy mismatch")
        # Close the directory set before opening any declared log bytes.  This
        # prevents an unreferenced node from being treated as harmless merely
        # because the declared files happen to validate first.
        _validate_logs_tree(evidence_root, expected_names=_expected_test_log_stems())
        components = _test_components(
            value["components"],
            evidence_root,
            runner,
            repo_fd=active_repo_fd,
            held_log_payloads=held_log_payloads,
        )
        if [item["name"] for item in components] != sorted(_TEST_COMPONENTS):
            raise OfflineEvidenceError("test component coverage is not exact")
        # Recheck after content reads to close the add/remove window around the
        # directory scan. Individual file reads are descriptor-stable below.
        _validate_logs_tree(evidence_root, expected_names=_expected_test_log_stems())
        return value, components
    finally:
        if owned_repo_fd is not None:
            os.close(owned_repo_fd)


def _validate_logs_tree(
    evidence_root: Path,
    *,
    expected_names: Sequence[str],
) -> None:
    """Require the log directory to contain exactly the declared log files.

    Component records bind individual log bytes, but validating only those
    paths would leave an unreferenced file, directory, or symlink inside the
    evidence root.  Such a node could carry undisclosed material and would be
    copied into a later handoff, so the directory itself is a closed set.
    """

    logs = evidence_root / "logs"
    expected = {f"{name}.log" for name in expected_names}
    seen: set[str] = set()
    _logs_absolute, logs_fd = _open_directory_fd(
        logs, "test evidence logs directory"
    )
    try:
        _validate_logs_fd(
            logs_fd,
            expected_names=expected_names,
            require_sealed=True,
        )
    finally:
        os.close(logs_fd)


def _validate_logs_fd(
    logs_fd: int,
    *,
    expected_names: Sequence[str],
    require_sealed: bool = False,
) -> None:
    expected = {f"{name}.log" for name in expected_names}
    seen: set[str] = set()
    try:
        entries = sorted(os.scandir(logs_fd), key=lambda entry: entry.name)
        for entry in entries:
            name = entry.name
            if name not in expected:
                raise OfflineEvidenceError(
                    "test evidence logs contain an undeclared node"
                )
            if name in seen:
                raise OfflineEvidenceError("test evidence logs contain a duplicate name")
            seen.add(name)
            state = entry.stat(follow_symlinks=False)
            if (
                stat.S_ISLNK(state.st_mode)
                or not stat.S_ISREG(state.st_mode)
                or state.st_nlink != 1
            ):
                raise OfflineEvidenceError(
                    "test evidence logs contain a non-unique regular file"
                )
            _safe_mode(state, f"test evidence log {name}")
            if require_sealed:
                _require_sealed_file_mode(state, f"test evidence log {name}")
    except OfflineEvidenceError:
        raise
    except OSError as exc:
        raise OfflineEvidenceError("test evidence logs could not be inspected safely") from exc
    if seen != expected:
        raise OfflineEvidenceError("test evidence logs do not match the exact component set")


def _validated_scratch_record(
    value: object,
    *,
    field: str,
    scratch_roots: set[tuple[int, int]],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "root_device",
        "root_inode",
        "root_mode",
        "root_uid",
        "root_gid",
        "initially_empty",
        "post_run_inventory",
        "cleanup_verified_empty",
        "identity_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OfflineEvidenceError(f"{field} is malformed")
    inventory = value["post_run_inventory"]
    if (
        value["schema_version"] != "cloud-v2-component-scratch-v1"
        or any(
            type(value[name]) is not int or value[name] < 0
            for name in (
                "root_device",
                "root_inode",
                "root_mode",
                "root_uid",
                "root_gid",
            )
        )
        or value["root_inode"] == 0
        or value["root_mode"] != 0o700
        or value["initially_empty"] is not True
        or value["cleanup_verified_empty"] is not True
        or not isinstance(inventory, Mapping)
        or set(inventory) != {"node_count", "node_set_sha256"}
        or type(inventory["node_count"]) is not int
        or inventory["node_count"] < 0
        or not isinstance(inventory["node_set_sha256"], str)
        or not _SHA256.fullmatch(inventory["node_set_sha256"])
    ):
        raise OfflineEvidenceError(f"{field} is malformed")
    if (
        inventory["node_count"] == 0
        and inventory["node_set_sha256"] != _identity_sha256([])
    ):
        raise OfflineEvidenceError(f"{field} empty inventory identity mismatch")
    core = {name: value[name] for name in fields if name != "identity_sha256"}
    if value["identity_sha256"] != _identity_sha256(core):
        raise OfflineEvidenceError(f"{field} identity mismatch")
    root_identity = (value["root_device"], value["root_inode"])
    if root_identity in scratch_roots:
        raise OfflineEvidenceError("test component scratch roots are not independent")
    scratch_roots.add(root_identity)
    return dict(value)


def _validated_persisted_absolute_path(value: object, field: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or _has_control_character(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        raise OfflineEvidenceError(f"{field} is malformed")
    path = Path(value)
    if not path.is_absolute() or str(path) != value or os.path.normpath(value) != value:
        raise OfflineEvidenceError(f"{field} is not a canonical absolute path")
    return path


def _persisted_relative_parent(path: Path, relative: str, field: str) -> Path:
    parts = PurePosixPath(_canonical_relative(relative, field)).parts
    current = path
    for expected_name in reversed(parts):
        if current.name != expected_name:
            raise OfflineEvidenceError(f"{field} does not bind its absolute path")
        current = current.parent
    return current


def _decoded_canonical_base64(
    value: object,
    *,
    field: str,
    max_bytes: int,
) -> bytes:
    if not isinstance(value, str):
        raise OfflineEvidenceError(f"{field} is malformed")
    try:
        payload = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise OfflineEvidenceError(f"{field} is malformed") from exc
    if (
        len(payload) > max_bytes
        or base64.b64encode(payload).decode("ascii") != value
    ):
        raise OfflineEvidenceError(f"{field} is malformed")
    return payload


def _validated_persisted_snapshot_identity(value: object) -> dict[str, Any]:
    fields = {
        "schema_version",
        "tree_roots",
        "exact_files",
        "directory_count",
        "directory_set_sha256",
        "file_count",
        "path_set_sha256",
        "file_set_sha256",
        "package_anchors_sha256",
        "identity_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OfflineEvidenceError("parent broker snapshot identity is malformed")
    for name in ("tree_roots", "exact_files"):
        paths = value[name]
        if (
            not isinstance(paths, list)
            or any(
                not isinstance(path, str)
                or _canonical_relative(path, f"parent broker snapshot {name}") != path
                for path in paths
            )
            or len(paths) != len(set(paths))
        ):
            raise OfflineEvidenceError("parent broker snapshot identity is malformed")
    if (
        value["schema_version"] != TEST_SCOPE_SCHEMA_VERSION
        or type(value["directory_count"]) is not int
        or value["directory_count"] < 0
        or type(value["file_count"]) is not int
        or value["file_count"] < 0
        or any(
            not isinstance(value[field], str) or not _SHA256.fullmatch(value[field])
            for field in fields
            - {"schema_version", "tree_roots", "exact_files", "directory_count", "file_count"}
        )
    ):
        raise OfflineEvidenceError("parent broker snapshot identity is malformed")
    core = {field: value[field] for field in fields if field != "identity_sha256"}
    if value["identity_sha256"] != _identity_sha256(core):
        raise OfflineEvidenceError("parent broker snapshot identity mismatch")
    return dict(value)


def _expected_parent_broker_environment(
    *,
    parameters: Mapping[str, Any],
    scratch_path: Path,
    python: Path,
    full_external_tools: _ExternalToolSet,
    child_sandbox_binding: Mapping[str, Any] | None,
    production_embedding_fixture: _ProductionEmbeddingFixture | None = None,
) -> dict[str, str]:
    kind = parameters["kind"]
    environment = {
        "PATH": str(python.parent),
        "TMPDIR": str(scratch_path),
        "TMP": str(scratch_path),
        "TEMP": str(scratch_path),
        "HOME": str(scratch_path),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
    }
    if kind == "test-component":
        path_directories = tuple(
            dict.fromkeys((python.parent, *full_external_tools.path_directories))
        )
        environment["PATH"] = os.pathsep.join(str(path) for path in path_directories)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if parameters.get("component") == _PRODUCTION_EMBEDDING_PROBE_ID:
            if production_embedding_fixture is None:
                raise OfflineEvidenceError(
                    "production embedding broker fixture is missing"
                )
            environment.update(production_embedding_fixture.environment())
            environment[_PRODUCTION_EMBEDDING_SCRATCH_ENV] = str(scratch_path)
        elif production_embedding_fixture is not None:
            raise OfflineEvidenceError(
                "production embedding fixture reached an unrelated broker child"
            )
    elif kind == "process-isolation":
        environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "KG_PROCESS_ROLE": parameters["role"],
                "KG_PROCESS_MARKER": parameters["marker"],
            }
        )
        if parameters["role"] == "public-app-agent":
            environment["KG_PUBLIC_ALLOWED_HOSTS"] = "localhost"
    if kind in {"disclosure", "test-component"}:
        if not isinstance(child_sandbox_binding, Mapping):
            raise OfflineEvidenceError("parent broker child sandbox binding is missing")
        environment[_INHERITED_COMPONENT_SANDBOX_ENV] = child_sandbox_binding[
            "identity_sha256"
        ]
    return environment


def _expected_parent_worker_environment(
    *,
    scratch_path: Path,
    python: Path,
    external_tools: _ExternalToolSet,
    sandbox_binding: Mapping[str, Any],
    probe_id: str | None = None,
    production_embedding_fixture: _ProductionEmbeddingFixture | None = None,
    ocr_tessdata_path: Path | None = None,
) -> dict[str, str]:
    path_directories = tuple(
        dict.fromkeys((python.parent, *external_tools.path_directories))
    )
    binding_identity = sandbox_binding.get("identity_sha256")
    if not isinstance(binding_identity, str) or not _SHA256.fullmatch(
        binding_identity
    ):
        raise OfflineEvidenceError("formal parent worker sandbox binding is malformed")
    environment = {
        "PATH": os.pathsep.join(str(path) for path in path_directories),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(scratch_path),
        "TMP": str(scratch_path),
        "TEMP": str(scratch_path),
        "HOME": str(scratch_path),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        _INHERITED_COMPONENT_SANDBOX_ENV: binding_identity,
    }
    if probe_id == _PRODUCTION_EMBEDDING_PROBE_ID:
        if production_embedding_fixture is None:
            raise OfflineEvidenceError(
                "production embedding parent probe fixture is missing"
            )
        environment.update(production_embedding_fixture.environment())
    elif production_embedding_fixture is not None:
        raise OfflineEvidenceError(
            "production embedding fixture reached an unrelated parent probe"
        )
    if probe_id == _REAL_OCR_PROBE_ID:
        if ocr_tessdata_path is None:
            raise OfflineEvidenceError(
                "private OCR tessdata snapshot is missing from the parent probe"
            )
        canonical_tessdata = _lexically_normal_absolute(
            ocr_tessdata_path,
            "private OCR tessdata snapshot path",
        )
        if canonical_tessdata != ocr_tessdata_path:
            raise OfflineEvidenceError(
                "private OCR tessdata snapshot path is not canonical"
            )
        environment[_OCR_TESSDATA_ENV] = str(canonical_tessdata)
    elif ocr_tessdata_path is not None:
        raise OfflineEvidenceError(
            "private OCR tessdata snapshot reached an unrelated parent probe"
        )
    return environment


def _expected_process_isolation_result(role: str) -> dict[str, Any]:
    if role == "public-app-agent":
        return {
            "module": "deploy.pipeline.server",
            "entrypoint": {
                "schema_version": "cloud-v2-public-entrypoint-v1",
                "entrypoint_id": "public-app-agent-wsgi-v1",
                "process_role": "public-app-agent",
                "network_zone": "public-app",
                "routes": ["/api/ask"],
                "tool_registry": ["knowledge-graph-cloud"],
                "ops_agent_discoverable": False,
                "ops_routes": [],
            },
            "process_environment": {
                "KG_PROCESS_MARKER": "public-process-only",
                "KG_PROCESS_ROLE": "public-app-agent",
                "KG_PUBLIC_ALLOWED_HOSTS": "localhost",
            },
            "public_status": 412,
            "ops_status": 404,
            "negative_statuses": {
                "audience": 403,
                "network_zone": 403,
                "service_account": 403,
            },
            "network_denied": True,
        }
    if role == "ops-admin-agent":
        return {
            "module": "deploy.cloud_v2.ops_server",
            "entrypoint": {
                "schema_version": "cloud-v2-ops-entrypoint-v1",
                "entrypoint_id": "ops-admin-agent-wsgi-v1",
                "process_role": "ops-admin-agent",
                "network_zone": "private-admin",
                "route_prefix": "/ops/",
                "routes": [
                    "/ops/audit/authority",
                    "/ops/audit/release",
                    "/ops/dashboard/capacity",
                    "/ops/dashboard/quality",
                    "/ops/maintenance/jobs",
                ],
                "tool_registry": [
                    "hybrid-audit-cloud",
                    "quality-dashboard-cloud",
                    "maintenance-controller-cloud",
                ],
                "handler_mode": "injected-test",
                "handler_identity_contract": (
                    "verified-identity-and-maintenance-confirmation-plus-json-body-v2"
                ),
                "maintenance_submit_schema": "maintenance-job-submit-v2",
                "maintenance_runner_bridge": "injected-candidate-job-runner-v2",
                "real_data_access": False,
                "network_calls": 0,
                "public_app_discoverable": False,
                "public_routes": [],
            },
            "process_environment": {
                "KG_PROCESS_MARKER": "ops-process-only",
                "KG_PROCESS_ROLE": "ops-admin-agent",
            },
            "ops_status": 200,
            "ops_diagnostic_codes": ["injected_test_only"],
            "ipv6_status": 200,
            "public_status": 404,
            "negative_statuses": {
                "audience": 403,
                "authn_mfa": 403,
                "authn_mtls": 403,
                "authn_oidc": 403,
                "network_zone": 403,
                "service_account": 403,
            },
            "public_token_body_statuses": {
                "invalid_content_type": 403,
                "oversized_body": 403,
            },
            "unsafe_response_status": 400,
            "unsafe_response_error": "non_structured_response_text",
            "identity_status": 200,
            "identity_forwarding": {
                "body_principal": "forged-admin",
                "trusted_subject": "ops-admin:test",
            },
            "wrong_role_status": 503,
            "network_denied": True,
        }
    raise OfflineEvidenceError("formal parent broker process role is not allowlisted")


def _validated_process_isolation_result(
    value: object,
    *,
    role: str,
    observed_pids: set[int],
    expected_pid: int,
) -> dict[str, Any]:
    expected = _expected_process_isolation_result(role)
    if not isinstance(value, Mapping) or set(value) != {"pid", *expected}:
        raise OfflineEvidenceError(
            "formal parent broker process result is malformed"
        )
    pid = value["pid"]
    if (
        type(expected_pid) is not int
        or expected_pid <= 0
        or type(pid) is not int
        or pid != expected_pid
        or pid in observed_pids
    ):
        raise OfflineEvidenceError(
            "formal parent broker process result identity mismatch"
        )
    actual = {field: value[field] for field in expected}
    if not _type_sensitive_equal(actual, expected):
        raise OfflineEvidenceError(
            "formal parent broker process result identity mismatch"
        )
    observed_pids.add(pid)
    return dict(value)


def _runner_ocr_tessdata_snapshot_identity(
    runner: Mapping[str, Any],
) -> dict[str, Any]:
    approved = runner.get("approved_ocr_tessdata_input")
    if not isinstance(approved, Mapping):
        raise OfflineEvidenceError(
            "formal parent worker approved OCR tessdata identity is missing"
        )
    expected = _expected_sealed_tessdata_identity(approved)
    if expected["source_identity_sha256"] != approved.get("identity_sha256"):
        raise OfflineEvidenceError(
            "formal parent worker approved OCR tessdata identity mismatch"
        )
    return expected


def _validated_parent_worker_launch(
    value: object,
    *,
    probe_id: str,
    runner: Mapping[str, Any],
    expected_closure_sha256: str,
    full_external_tools: _ExternalToolSet,
    full_closure: _RuntimeSandboxClosure,
    production_embedding_fixture: _ProductionEmbeddingFixture | None = None,
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "sandbox_binding",
        "sandbox_context",
        "sandbox_context_identity_sha256",
        "normalized_command",
        "normalized_command_sha256",
        "profile_base64",
        "stdin_role",
        "stdin_profile_size",
        "stdin_profile_sha256",
        "formal_closure_sha256",
        "environment",
        "environment_sha256",
        "snapshot_path",
        "scratch_path",
        "denial_probe_path",
        "inherited_fd_roles",
        "broker_session",
        "broker_deadline_monotonic_ns",
        "process_identity",
        "direct_worker_waited",
        "process_group_quiescence_verified",
        "timeout_cleanup_contract",
        "identity_sha256",
    }
    ocr_probe = _is_ocr_native_probe(probe_id)
    ocr_tessdata_probe = _is_ocr_tessdata_probe(probe_id)
    if ocr_tessdata_probe:
        fields |= {
            "ocr_tessdata_snapshot_identity",
            "ocr_tessdata_snapshot_path",
        }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OfflineEvidenceError("formal parent worker launch is malformed")
    snapshot_path = _validated_persisted_absolute_path(
        value["snapshot_path"], "formal parent worker snapshot path"
    )
    scratch_path = _validated_persisted_absolute_path(
        value["scratch_path"], "formal parent worker scratch path"
    )
    denial_probe_path = _validated_persisted_absolute_path(
        value["denial_probe_path"], "formal parent worker denial probe path"
    )
    ocr_tessdata_path = (
        _validated_persisted_absolute_path(
            value["ocr_tessdata_snapshot_path"],
            "formal parent worker OCR tessdata snapshot path",
        )
        if ocr_tessdata_probe
        else None
    )
    if len({snapshot_path, scratch_path, denial_probe_path}) != 3:
        raise OfflineEvidenceError("formal parent worker paths are not independent")
    runner_scope = runner.get("test_scope")
    runner_closure = runner.get("sandbox_closure")
    if (
        not isinstance(runner_scope, Mapping)
        or not isinstance(runner_closure, Mapping)
        or not _type_sensitive_equal(full_closure.identity, runner_closure)
    ):
        raise OfflineEvidenceError("formal parent worker runtime closure mismatch")
    worker_external_tools = full_external_tools
    worker_closure = full_closure
    if probe_id == _PRODUCTION_EMBEDDING_PROBE_ID:
        if (
            production_embedding_fixture is None
            or not _type_sensitive_equal(
                runner.get("production_embedding_fixture"),
                production_embedding_fixture.identity,
            )
        ):
            raise OfflineEvidenceError(
                "formal parent worker production embedding fixture mismatch"
            )
        _revalidate_production_embedding_fixture(production_embedding_fixture)
        worker_closure = _production_embedding_probe_closure(
            full_closure,
            production_embedding_fixture,
            target_executable=None,
        )
    elif ocr_probe:
        expected_ocr_tessdata_identity = (
            _runner_ocr_tessdata_snapshot_identity(runner)
            if ocr_tessdata_probe
            else None
        )
        if ocr_tessdata_probe:
            if not _type_sensitive_equal(
                value["ocr_tessdata_snapshot_identity"],
                expected_ocr_tessdata_identity,
            ):
                raise OfflineEvidenceError(
                    "formal parent worker OCR tessdata snapshot identity mismatch"
                )
            assert ocr_tessdata_path is not None
        worker_closure = _ocr_parent_probe_closure(
            full_closure,
            probe_id=probe_id,
            tessdata_path=ocr_tessdata_path,
            tessdata_identity=expected_ocr_tessdata_identity,
        )
    elif production_embedding_fixture is not None:
        raise OfflineEvidenceError(
            "production embedding fixture reached an unrelated parent worker"
        )
    profile_payload = _decoded_canonical_base64(
        value["profile_base64"],
        field="formal parent worker profile bytes",
        max_bytes=2 * 1024 * 1024,
    )
    expected_profile = _parent_worker_sandbox_profile_from_bound_paths(
        snapshot_path,
        scratch_path,
        worker_closure,
    ).encode("utf-8")
    if (
        profile_payload != expected_profile
        or value["stdin_role"] != "sandbox-profile-pipe"
        or type(value["stdin_profile_size"]) is not int
        or value["stdin_profile_size"] != len(profile_payload)
        or value["stdin_profile_sha256"]
        != hashlib.sha256(profile_payload).hexdigest()
    ):
        raise OfflineEvidenceError("formal parent worker profile bytes mismatch")
    expected_binding = _parent_worker_sandbox_binding_for_paths(
        profile=expected_profile.decode("utf-8"),
        snapshot_path=snapshot_path,
        snapshot_identity=runner_scope,
        scratch_path=scratch_path,
        denial_probe_path=denial_probe_path,
        closure=worker_closure,
    )
    if not _type_sensitive_equal(value["sandbox_binding"], expected_binding):
        raise OfflineEvidenceError("formal parent worker sandbox binding mismatch")
    expected_context = _component_sandbox_context(
        expected_binding,
        types.SimpleNamespace(path=denial_probe_path),
    )
    if not _type_sensitive_equal(value["sandbox_context"], expected_context):
        raise OfflineEvidenceError("formal parent worker sandbox context mismatch")
    python = _python_executable()
    expected_environment = _expected_parent_worker_environment(
        scratch_path=scratch_path,
        python=python,
        external_tools=worker_external_tools,
        sandbox_binding=expected_binding,
        probe_id=probe_id,
        production_embedding_fixture=production_embedding_fixture,
        ocr_tessdata_path=ocr_tessdata_path,
    )
    if not _type_sensitive_equal(value["environment"], expected_environment):
        raise OfflineEvidenceError("formal parent worker environment mismatch")
    normalized_command = _expected_parent_probe_command(probe_id)[1]
    if not _type_sensitive_equal(value["normalized_command"], normalized_command):
        raise OfflineEvidenceError("formal parent worker command identity mismatch")
    if (
        value["schema_version"] != PARENT_WORKER_LAUNCH_SCHEMA_VERSION
        or value["sandbox_context_identity_sha256"]
        != expected_context["identity_sha256"]
        or value["normalized_command_sha256"] != _identity_sha256(normalized_command)
        or value["formal_closure_sha256"] != expected_closure_sha256
        or value["environment_sha256"] != _identity_sha256(expected_environment)
        or not _type_sensitive_equal(
            value["inherited_fd_roles"],
            [
                "snapshot-root",
                "broker-request-write",
                "broker-response-read",
            ],
        )
        or value["direct_worker_waited"] is not True
        or type(value["broker_deadline_monotonic_ns"]) is not int
        or value["broker_deadline_monotonic_ns"] <= 0
        or value["process_group_quiescence_verified"] is not True
        or value["timeout_cleanup_contract"]
        != "new-session-process-group-quiescence-or-killpg-and-wait"
    ):
        raise OfflineEvidenceError("formal parent worker launch identity mismatch")
    for field in (
        "sandbox_context_identity_sha256",
        "normalized_command_sha256",
        "formal_closure_sha256",
        "environment_sha256",
        "broker_session",
        "identity_sha256",
    ):
        if not isinstance(value[field], str) or not _SHA256.fullmatch(value[field]):
            raise OfflineEvidenceError("formal parent worker launch digest is invalid")
    expected_session = _parent_broker_session_identity(
        probe_id=probe_id,
        runner=runner,
        worker_sandbox_binding_sha256=expected_binding["identity_sha256"],
    )
    if value["broker_session"] != expected_session:
        raise OfflineEvidenceError("formal parent worker broker session mismatch")
    _validated_process_identity(
        value["process_identity"],
        "formal parent worker",
        require_session_leader=True,
    )
    core = {field: value[field] for field in fields if field != "identity_sha256"}
    if value["identity_sha256"] != _identity_sha256(core):
        raise OfflineEvidenceError("formal parent worker launch identity mismatch")
    return dict(value)


def _validated_ocr_file_identity(
    value: object,
    *,
    field: str,
    expected_path: Path,
) -> dict[str, Any]:
    fields = {
        "path_sha256",
        "resolved_path_sha256",
        "path_is_symlink",
        "device",
        "inode",
        "mode",
        "nlink",
        "size",
        "mtime_ns",
        "ctime_ns",
        "sha256",
    }
    expected_path_sha256 = hashlib.sha256(
        str(expected_path).encode("utf-8")
    ).hexdigest()
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value["path_sha256"] != expected_path_sha256
        or value["resolved_path_sha256"] != expected_path_sha256
        or value["path_is_symlink"] is not False
        or any(
            type(value[name]) is not int or value[name] < 0
            for name in (
                "device",
                "inode",
                "mode",
                "nlink",
                "size",
                "mtime_ns",
                "ctime_ns",
            )
        )
        or not stat.S_ISREG(value["mode"])
        or value["nlink"] != 1
        or not isinstance(value["sha256"], str)
        or not _SHA256.fullmatch(value["sha256"])
    ):
        raise OfflineEvidenceError(f"{field} is malformed")
    return dict(value)


def _validated_ocr_directory_identity(
    value: object,
    *,
    field: str,
    expected_path: Path,
) -> dict[str, Any]:
    fields = {
        "path_sha256",
        "device",
        "inode",
        "mode",
        "nlink",
        "size",
        "mtime_ns",
        "ctime_ns",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value["path_sha256"]
        != hashlib.sha256(str(expected_path).encode("utf-8")).hexdigest()
        or any(
            type(value[name]) is not int or value[name] < 0
            for name in fields - {"path_sha256"}
        )
        or not stat.S_ISDIR(value["mode"])
    ):
        raise OfflineEvidenceError(f"{field} is malformed")
    return dict(value)


def _validated_ocr_native_operation_extras(
    operation: Mapping[str, Any],
    *,
    probe_id: str,
    sequence: int,
    parameters: Mapping[str, Any],
    worker_scratch_path: Path,
    profile_payload: bytes,
    sealed_tessdata_snapshot_identity: Mapping[str, Any] | None,
    shared_deadline_monotonic_ns: int,
    approved_materialization: Mapping[str, Any],
) -> None:
    if not _is_ocr_native_probe(probe_id):
        raise OfflineEvidenceError("formal parent broker OCR probe is not allowlisted")
    tessdata_probe = _is_ocr_tessdata_probe(probe_id)
    sealed_digest = (
        sealed_tessdata_snapshot_identity.get("identity_sha256")
        if isinstance(sealed_tessdata_snapshot_identity, Mapping)
        else None
    )
    if tessdata_probe:
        if (
            not isinstance(sealed_digest, str)
            or not _SHA256.fullmatch(sealed_digest)
            or operation["sealed_tessdata_snapshot_identity_sha256"]
            != sealed_digest
        ):
            raise OfflineEvidenceError(
                "formal parent broker OCR sealed tessdata identity mismatch"
            )
    elif (
        sealed_tessdata_snapshot_identity is not None
        or operation["sealed_tessdata_snapshot_identity_sha256"] is not None
    ):
        raise OfflineEvidenceError(
            "formal parent broker page 132 tessdata identity is unexpected"
        )
    expected_slot = _ocr_native_execution_slot(sequence)
    if not _type_sensitive_equal(operation["execution_slot"], expected_slot):
        raise OfflineEvidenceError(
            "formal parent broker OCR execution slot identity mismatch"
        )
    _validated_ocr_process_timing(
        operation["process_timing"],
        shared_deadline_monotonic_ns=shared_deadline_monotonic_ns,
        timeout_seconds=parameters["timeout_seconds"],
    )
    profile_delivery = operation["profile_delivery"]
    if (
        not isinstance(profile_delivery, Mapping)
        or set(profile_delivery)
        != {"mode", "argument_index", "size", "sha256", "identity_sha256"}
        or profile_delivery["mode"] != "sandbox-exec-inline-profile-argv"
        or type(profile_delivery["argument_index"]) is not int
        or profile_delivery["argument_index"] != 2
        or type(profile_delivery["size"]) is not int
        or profile_delivery["size"] != len(profile_payload)
        or profile_delivery["sha256"]
        != hashlib.sha256(profile_payload).hexdigest()
        or profile_delivery["identity_sha256"]
        != _identity_sha256(
            {
                key: item
                for key, item in profile_delivery.items()
                if key != "identity_sha256"
            }
        )
    ):
        raise OfflineEvidenceError(
            "formal parent broker OCR profile delivery identity mismatch"
        )

    native_runtime_path = worker_scratch_path / parameters[
        "native_runtime_relative"
    ]
    executable_path = worker_scratch_path / parameters[
        "private_executable_relative"
    ]
    library_path = worker_scratch_path / parameters["private_library_relative"]
    expected_runtime_nodes = _expected_ocr_runtime_nodes(
        tool=parameters["tool"],
        approved_materialization=approved_materialization,
        sealed_tessdata_snapshot_identity=sealed_tessdata_snapshot_identity,
    )
    runtime_identity = operation["native_runtime_identity"]
    if not isinstance(runtime_identity, Mapping) or set(runtime_identity) != {
        "schema_version",
        "tree",
        "executable",
        "library_root",
        "approved_materialization",
        "materialization",
        "identity_sha256",
    }:
        raise OfflineEvidenceError(
            "formal parent broker OCR native runtime identity is malformed"
        )
    tree = runtime_identity["tree"]
    if (
        not isinstance(tree, Mapping)
        or set(tree)
        != {
            "schema_version",
            "root_path_sha256",
            "node_count",
            "nodes",
            "node_set_sha256",
            "observed_state_sha256",
            "identity_sha256",
        }
        or tree["schema_version"] != "cloud-v2-bound-runtime-tree-v2"
        or tree["root_path_sha256"]
        != hashlib.sha256(str(native_runtime_path).encode("utf-8")).hexdigest()
        or type(tree["node_count"]) is not int
        or tree["node_count"] != len(expected_runtime_nodes)
        or not isinstance(tree["nodes"], list)
        or not _type_sensitive_equal(tree["nodes"], expected_runtime_nodes)
        or tree["node_set_sha256"] != _identity_sha256(tree["nodes"])
        or not isinstance(tree["observed_state_sha256"], str)
        or not _SHA256.fullmatch(tree["observed_state_sha256"])
        or tree["identity_sha256"]
        != _identity_sha256(
            {key: item for key, item in tree.items() if key != "identity_sha256"}
        )
    ):
        raise OfflineEvidenceError(
            "formal parent broker OCR native runtime tree is malformed"
        )
    executable_identity = _validated_ocr_file_identity(
        runtime_identity["executable"],
        field="formal parent broker OCR executable identity",
        expected_path=executable_path,
    )
    _validated_ocr_directory_identity(
        runtime_identity["library_root"],
        field="formal parent broker OCR library identity",
        expected_path=library_path,
    )
    approved_executable = approved_materialization.get("executable")
    if (
        runtime_identity["schema_version"]
        != "cloud-v2-parent-broker-native-runtime-v4"
        or not isinstance(approved_materialization, Mapping)
        or approved_materialization.get("tool") != parameters["tool"]
        or approved_materialization.get("identity_sha256")
        != _identity_sha256(
            {
                key: item
                for key, item in approved_materialization.items()
                if key != "identity_sha256"
            }
        )
        or not isinstance(approved_executable, Mapping)
        or executable_identity["sha256"] != approved_executable.get("sha256")
        or executable_identity["size"] != approved_executable.get("size")
        or stat.S_IMODE(executable_identity["mode"])
        != approved_executable.get("mode")
        or not _type_sensitive_equal(
            runtime_identity["approved_materialization"], approved_materialization
        )
        or not _type_sensitive_equal(
            runtime_identity["materialization"], approved_materialization
        )
        or runtime_identity["identity_sha256"]
        != _identity_sha256(
            {
                key: item
                for key, item in runtime_identity.items()
                if key != "identity_sha256"
            }
        )
    ):
        raise OfflineEvidenceError(
            "formal parent broker OCR native runtime identity mismatch"
        )

    if parameters["tool"] == "pdftoppm":
        if not tessdata_probe:
            input_identity = operation["input_identity"]
            input_fields = {
                "schema_version",
                "role",
                "delivery",
                "snapshot_relative",
                "mode",
                "nlink",
                "size",
                "sha256",
                "identity_sha256",
            }
            if (
                probe_id != _REAL_PAGE_132_PROBE_ID
                or not isinstance(input_identity, Mapping)
                or set(input_identity) != input_fields
                or input_identity["schema_version"]
                != "cloud-v2-parent-broker-ocr-held-input-v1"
                or input_identity["role"] != "pdf-bytes-pipe"
                or input_identity["delivery"]
                != "sealed-snapshot-held-descriptor"
                or input_identity["snapshot_relative"]
                != _OCR_PAGE_132_SOURCE_RELATIVE
                or type(input_identity["mode"]) is not int
                or not stat.S_ISREG(input_identity["mode"])
                or stat.S_IMODE(input_identity["mode"]) != 0o400
                or type(input_identity["nlink"]) is not int
                or input_identity["nlink"] != 1
                or type(input_identity["size"]) is not int
                or input_identity["size"] != parameters["input_size"]
                or input_identity["size"] != _OCR_PAGE_132_INPUT_ANCHOR["size"]
                or input_identity["sha256"] != parameters["input_sha256"]
                or input_identity["sha256"]
                != _OCR_PAGE_132_INPUT_ANCHOR["sha256"]
                or input_identity["identity_sha256"]
                != _identity_sha256(
                    {
                        key: item
                        for key, item in input_identity.items()
                        if key != "identity_sha256"
                    }
                )
                or operation["page_identity"] is not None
                or operation["private_tessdata_identity"] is not None
            ):
                raise OfflineEvidenceError(
                    "formal parent broker page 132 input identity mismatch"
                )
            output = operation["output_identity"]
            if (
                not isinstance(output, Mapping)
                or set(output)
                != {
                    "schema_version",
                    "page_number",
                    "size",
                    "sha256",
                    "identity_sha256",
                }
                or output["schema_version"]
                != "cloud-v2-parent-broker-ocr-stdout-v1"
                or output["page_number"] != 132
                or type(output["size"]) is not int
                or output["size"] != _OCR_PAGE_132_OUTPUT_ANCHOR["size"]
                or output["sha256"] != _OCR_PAGE_132_OUTPUT_ANCHOR["sha256"]
                or output["sha256"] != operation["stdout_sha256"]
                or output["identity_sha256"]
                != _identity_sha256(
                    {
                        key: item
                        for key, item in output.items()
                        if key != "identity_sha256"
                    }
                )
            ):
                raise OfflineEvidenceError(
                    "formal parent broker page 132 stdout identity mismatch"
                )
            return
        fixed_anchors = _validated_ocr_fixed_fixture_anchors()
        fixed_pdf = fixed_anchors["pdf"]
        input_identity = operation["input_identity"]
        if (
            not isinstance(input_identity, Mapping)
            or set(input_identity)
            != {"schema_version", "role", "size", "sha256", "identity_sha256"}
            or input_identity["schema_version"]
            != "cloud-v2-parent-broker-ocr-input-v1"
            or input_identity["role"] != "pdf-bytes-pipe"
            or type(input_identity["size"]) is not int
            or input_identity["size"] != parameters["input_size"]
            or input_identity["sha256"] != parameters["input_sha256"]
            or input_identity["size"] != fixed_pdf["size"]
            or input_identity["sha256"] != fixed_pdf["sha256"]
            or input_identity["identity_sha256"]
            != _identity_sha256(
                {
                    key: item
                    for key, item in input_identity.items()
                    if key != "identity_sha256"
                }
            )
            or operation["page_identity"] is not None
            or operation["private_tessdata_identity"] is not None
        ):
            raise OfflineEvidenceError(
                "formal parent broker OCR PDF input identity mismatch"
            )
        output = operation["output_identity"]
        if (
            not isinstance(output, Mapping)
            or output.get("schema_version")
            != "cloud-v2-parent-broker-rendered-pages-v1"
            or type(output.get("page_count")) is not int
            or output.get("page_count") != 10
            or not _type_sensitive_equal(
                output.get("page_numbers"), list(range(1, 11))
            )
            or not isinstance(output.get("files"), list)
            or len(output["files"]) != 10
            or output.get("file_set_sha256") != _identity_sha256(output["files"])
            or output.get("identity_sha256")
            != _identity_sha256(
                {key: item for key, item in output.items() if key != "identity_sha256"}
            )
        ):
            raise OfflineEvidenceError(
                "formal parent broker OCR rendered output identity mismatch"
            )
        for page_number, record in enumerate(output["files"], 1):
            fixed = fixed_anchors["rendered_pages"][page_number - 1]
            if (
                not isinstance(record, Mapping)
                or set(record)
                != {"page_number", "name", "mode", "size", "sha256"}
                or type(record["page_number"]) is not int
                or record["page_number"] != page_number
                or record["name"] != f"page-{page_number:02d}.jpg"
                or type(record["mode"]) is not int
                or type(record["size"]) is not int
                or record["size"] <= 0
                or not _type_sensitive_equal(
                    {field: record[field] for field in fixed},
                    fixed,
                )
            ):
                raise OfflineEvidenceError(
                    "formal parent broker OCR rendered output identity mismatch"
                )
        return

    if not tessdata_probe or operation["input_identity"] is not None:
        raise OfflineEvidenceError(
            "formal parent broker OCR tesseract input identity is unexpected"
        )
    page_path = worker_scratch_path / parameters["approved_page_relative"]
    page_identity = _validated_ocr_file_identity(
        operation["page_identity"],
        field="formal parent broker OCR approved page identity",
        expected_path=page_path,
    )
    private_tessdata_path = worker_scratch_path / parameters[
        "private_tessdata_relative"
    ]
    private_tessdata = operation["private_tessdata_identity"]
    expected_files = sealed_tessdata_snapshot_identity.get("files")
    if (
        not isinstance(expected_files, list)
        or not isinstance(private_tessdata, Mapping)
        or set(private_tessdata)
        != {
            "schema_version",
            "sealed_snapshot_identity_sha256",
            "path_sha256",
            "root_identity",
            "files",
            "file_set_sha256",
            "identity_sha256",
        }
        or private_tessdata["schema_version"]
        != "cloud-v2-parent-broker-private-tessdata-v1"
        or private_tessdata["sealed_snapshot_identity_sha256"] != sealed_digest
        or private_tessdata["path_sha256"]
        != hashlib.sha256(str(private_tessdata_path).encode("utf-8")).hexdigest()
        or not _type_sensitive_equal(
            private_tessdata["files"], expected_files
        )
        or private_tessdata["file_set_sha256"] != _identity_sha256(expected_files)
        or private_tessdata["identity_sha256"]
        != _identity_sha256(
            {
                key: item
                for key, item in private_tessdata.items()
                if key != "identity_sha256"
            }
        )
    ):
        raise OfflineEvidenceError(
            "formal parent broker private OCR tessdata identity mismatch"
        )
    _validated_ocr_directory_identity(
        private_tessdata["root_identity"],
        field="formal parent broker private OCR tessdata root identity",
        expected_path=private_tessdata_path,
    )
    output = operation["output_identity"]
    fixed_stdout = _validated_ocr_fixed_fixture_anchors()["stdout"][
        parameters["page_number"] - 1
    ]
    fixed_page = _validated_ocr_fixed_fixture_anchors()["rendered_pages"][
        parameters["page_number"] - 1
    ]
    if (
        not isinstance(output, Mapping)
        or set(output)
        != {
            "schema_version",
            "page_number",
            "size",
            "sha256",
            "identity_sha256",
        }
        or output["schema_version"] != "cloud-v2-parent-broker-ocr-stdout-v1"
        or type(output["page_number"]) is not int
        or output["page_number"] != parameters["page_number"]
        or type(output["size"]) is not int
        or output["size"] <= 0
        or output["sha256"] != operation["stdout_sha256"]
        or not _type_sensitive_equal(
            {field: output[field] for field in fixed_stdout},
            fixed_stdout,
        )
        or page_identity["size"] != fixed_page["size"]
        or page_identity["sha256"] != fixed_page["sha256"]
        or output["identity_sha256"]
        != _identity_sha256(
            {key: item for key, item in output.items() if key != "identity_sha256"}
        )
    ):
        raise OfflineEvidenceError(
            "formal parent broker OCR stdout identity mismatch"
        )


def _validated_parent_broker_transcript(
    value: object,
    *,
    probe_id: str,
    client_transcript: Mapping[str, Any],
    runner: Mapping[str, Any],
    worker_launch: Mapping[str, Any],
    repo_fd: int,
    full_external_tools: _ExternalToolSet,
    full_closure: _RuntimeSandboxClosure,
    restricted_closure: _RuntimeSandboxClosure,
    scratch_roots: set[tuple[int, int]],
    production_embedding_fixture: _ProductionEmbeddingFixture | None = None,
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "protocol_schema_version",
        "session",
        "probe_id",
        "deadline_monotonic_ns",
        "broker_process_identity",
        "broker_network_assurance",
        "broker_os_network_enforced",
        "expected_operation_count",
        "accepted_operation_count",
        "rejected_operation_count",
        "operation_ids",
        "operation_ids_sha256",
        "exchange_hashes",
        "exchange_chain_sha256",
        "operations",
        "identity_sha256",
    }
    plan = _parent_broker_plan(probe_id)
    ocr_probe = _is_ocr_native_probe(probe_id)
    ocr_tessdata_probe = _is_ocr_tessdata_probe(probe_id)
    if ocr_tessdata_probe:
        fields.add("ocr_native_summary")
    production_embedding_probe = probe_id == _PRODUCTION_EMBEDDING_PROBE_ID
    if production_embedding_probe != (production_embedding_fixture is not None):
        raise OfflineEvidenceError(
            "formal parent broker production embedding fixture scope is not exact"
        )
    if production_embedding_fixture is not None:
        if not _type_sensitive_equal(
            runner.get("production_embedding_fixture"),
            production_embedding_fixture.identity,
        ):
            raise OfflineEvidenceError(
                "formal parent broker production embedding fixture mismatch"
            )
        _revalidate_production_embedding_fixture(production_embedding_fixture)
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OfflineEvidenceError("formal parent broker transcript is malformed")
    broker_process_identity = _validated_process_identity(
        value["broker_process_identity"],
        "formal parent broker",
        require_session_leader=False,
    )
    worker_process_identity = _validated_process_identity(
        worker_launch.get("process_identity"),
        "formal parent worker",
        require_session_leader=True,
    )
    worker_binding = worker_launch.get("sandbox_binding")
    if not isinstance(worker_binding, Mapping):
        raise OfflineEvidenceError("formal parent worker sandbox binding is malformed")
    worker_scratch_path = _validated_persisted_absolute_path(
        worker_launch.get("scratch_path"),
        "formal parent worker scratch path",
    )
    expected_session = _parent_broker_session_identity(
        probe_id=probe_id,
        runner=runner,
        worker_sandbox_binding_sha256=worker_binding.get("identity_sha256", ""),
    )
    shared_deadline_monotonic_ns = worker_launch.get(
        "broker_deadline_monotonic_ns"
    )
    if (
        value["schema_version"] != PARENT_BROKER_TRANSCRIPT_SCHEMA_VERSION
        or value["protocol_schema_version"] != PARENT_BROKER_PROTOCOL_SCHEMA_VERSION
        or value["session"] != expected_session
        or worker_launch.get("broker_session") != expected_session
        or client_transcript.get("session") != expected_session
        or type(shared_deadline_monotonic_ns) is not int
        or shared_deadline_monotonic_ns <= 0
        or value["deadline_monotonic_ns"] != shared_deadline_monotonic_ns
        or client_transcript.get("deadline_monotonic_ns")
        != shared_deadline_monotonic_ns
        or broker_process_identity["pid"] == worker_process_identity["pid"]
        or value["probe_id"] != probe_id
        or value["broker_network_assurance"]
        != "held-byte-fixed-command-broker-no-provider-data-plane"
        or value["broker_os_network_enforced"] is not False
        or type(value["expected_operation_count"]) is not int
        or value["expected_operation_count"] != len(plan)
        or type(value["accepted_operation_count"]) is not int
        or value["accepted_operation_count"] != len(plan)
        or type(value["rejected_operation_count"]) is not int
        or value["rejected_operation_count"] != 0
        or value["operation_ids"] != list(plan)
        or value["operation_ids_sha256"] != _identity_sha256(plan)
        or not isinstance(value["exchange_hashes"], list)
        or len(value["exchange_hashes"]) != len(plan)
        or not isinstance(value["operations"], list)
        or len(value["operations"]) != len(plan)
    ):
        raise OfflineEvidenceError("formal parent broker transcript identity mismatch")
    operation_fields = {
        "sequence",
        "operation_id",
        "parameters_sha256",
        "normalized_command",
        "normalized_command_sha256",
        "stdin_role",
        "stdin_profile_size",
        "stdin_profile_sha256",
        "profile_base64",
        "profile_sha256",
        "runtime_closure_identity",
        "runtime_closure_identity_sha256",
        "snapshot_identity",
        "snapshot_identity_sha256",
        "environment",
        "environment_sha256",
        "snapshot_path",
        "scratch_path",
        "denial_probe_path",
        "child_sandbox_binding",
        "target_executable_identity",
        "pass_fd_roles",
        "process_identity",
        "returncode",
        "stdout_size",
        "stdout_sha256",
        "stderr_size",
        "stderr_sha256",
        "text_mode",
        "network_enforcement",
        "direct_child_waited",
        "process_group_quiescence_verified",
        "timeout_cleanup_contract",
        "profile_scratch",
        "request_base64",
        "response_base64",
        "request_sha256",
        "response_sha256",
        "identity_sha256",
    }
    request_fields = {
        "schema_version",
        "session",
        "sequence",
        "probe_id",
        "operation_id",
        "parameters",
        "parameters_sha256",
    }
    response_fields = {
        "schema_version",
        "session",
        "sequence",
        "probe_id",
        "operation_id",
        "process_identity",
        "request_sha256",
        "status",
        "returncode",
        "stdout_base64",
        "stderr_base64",
        "text_mode",
        "timed_out",
        "process_timing",
        "execution_slot",
    }
    expected_snapshots: dict[str, dict[str, Any]] = {}
    expected_disclosure_output: dict[str, Any] | None = None
    broker_child_pids: set[int] = set()
    process_isolation_pids: set[int] = set()
    recomputed_exchanges: list[dict[str, str]] = []
    recomputed_chain = hashlib.sha256(expected_session.encode("ascii")).hexdigest()
    expected_ocr_tessdata_identity = (
        _runner_ocr_tessdata_snapshot_identity(runner)
        if ocr_tessdata_probe
        else None
    )
    approved_ocr_materializations = (
        {
            tool: _approved_ocr_native_materialization_contract(
                tool,
                full_external_tools,
            )
            for tool in (
                ("pdftoppm", "tesseract")
                if ocr_tessdata_probe
                else ("pdftoppm",)
            )
        }
        if ocr_probe
        else {}
    )
    python = _python_executable()
    for sequence, (operation, expected_operation) in enumerate(
        zip(value["operations"], plan)
    ):
        if not isinstance(operation, Mapping):
            raise OfflineEvidenceError("formal parent broker operation is malformed")
        request_payload = _decoded_canonical_base64(
            operation["request_base64"],
            field="formal parent broker request bytes",
            max_bytes=2 * 1024 * 1024,
        )
        try:
            request = json.loads(request_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineEvidenceError("formal parent broker request is malformed") from exc
        if (
            not isinstance(request, Mapping)
            or set(request) != request_fields
            or request_payload != canonical_json_bytes(request)
            or request["schema_version"] != PARENT_BROKER_PROTOCOL_SCHEMA_VERSION
            or request["session"] != expected_session
            or type(request["sequence"]) is not int
            or request["sequence"] != sequence
            or request["probe_id"] != probe_id
            or request["operation_id"] != expected_operation
        ):
            raise OfflineEvidenceError("formal parent broker request identity mismatch")
        parameters = _validated_parent_broker_parameters(
            request["parameters"],
            probe_id=probe_id,
            operation_id=expected_operation,
        )
        kind = parameters["kind"]
        expected_operation_fields = (
            operation_fields | _OCR_NATIVE_OPERATION_EXTRA_FIELDS
            if kind == "ocr-native"
            else operation_fields
        )
        if set(operation) != expected_operation_fields:
            raise OfflineEvidenceError("formal parent broker operation is malformed")
        child_process_identity = _validated_process_identity(
            operation["process_identity"],
            "formal parent broker child",
            require_session_leader=True,
        )
        if child_process_identity["pid"] in {
            broker_process_identity["pid"],
            worker_process_identity["pid"],
        } or child_process_identity["pid"] in broker_child_pids:
            raise OfflineEvidenceError(
                "formal parent broker process identities are not independent"
            )
        broker_child_pids.add(child_process_identity["pid"])
        if kind == "process-isolation":
            constants = _process_isolation_constants(repo_fd)
            script = (
                constants["PUBLIC_CHILD"]
                if parameters["role"] == "public-app-agent"
                else constants["OPS_CHILD"]
            )
            encoded_script = base64.b64encode(
                __import__("textwrap").dedent(script).encode("utf-8")
            ).decode("ascii")
            encoded_bindings = base64.b64encode(
                canonical_json_bytes(_process_isolation_library_bindings())
            ).decode("ascii")
            expected_process_identities = {
                "bootstrap_sha256": hashlib.sha256(
                    constants["PROCESS_CHILD_BOOTSTRAP"].encode("utf-8")
                ).hexdigest(),
                "script_sha256": hashlib.sha256(
                    encoded_script.encode("ascii")
                ).hexdigest(),
                "library_bindings_sha256": hashlib.sha256(
                    encoded_bindings.encode("ascii")
                ).hexdigest(),
            }
            if any(
                parameters[field] != expected
                for field, expected in expected_process_identities.items()
            ):
                raise OfflineEvidenceError(
                    "formal parent broker process-isolation command identity mismatch"
                )
        parameters_sha256 = _identity_sha256(parameters)
        request_sha256 = hashlib.sha256(request_payload).hexdigest()
        if request["parameters_sha256"] != parameters_sha256:
            raise OfflineEvidenceError("formal parent broker request parameter mismatch")

        snapshot_path = _validated_persisted_absolute_path(
            operation["snapshot_path"], "formal parent broker snapshot path"
        )
        scratch_path = _validated_persisted_absolute_path(
            operation["scratch_path"], "formal parent broker scratch path"
        )
        if kind == "ocr-native":
            if (
                str(snapshot_path) != worker_launch.get("snapshot_path")
                or _persisted_relative_parent(
                    scratch_path,
                    parameters["scratch_relative"],
                    "formal parent broker OCR scratch relative path",
                )
                != worker_scratch_path
            ):
                raise OfflineEvidenceError(
                    "formal parent broker OCR paths do not bind"
                )
            common_parent = worker_scratch_path
        else:
            if snapshot_path == scratch_path:
                raise OfflineEvidenceError(
                    "formal parent broker child roots are not independent"
                )
            common_parent = _persisted_relative_parent(
                snapshot_path,
                parameters["snapshot_relative"],
                "formal parent broker snapshot relative path",
            )
            if (
                common_parent != worker_scratch_path
                or _persisted_relative_parent(
                    scratch_path,
                    parameters["scratch_relative"],
                    "formal parent broker scratch relative path",
                )
                != common_parent
            ):
                raise OfflineEvidenceError(
                    "formal parent broker child path roots do not bind"
                )
        denial_path: Path | None
        if kind in {"disclosure", "test-component"}:
            denial_path = _validated_persisted_absolute_path(
                operation["denial_probe_path"],
                "formal parent broker denial probe path",
            )
            if (
                denial_path in {snapshot_path, scratch_path}
                or _persisted_relative_parent(
                    denial_path,
                    parameters["denial_probe_relative"],
                    "formal parent broker denial probe relative path",
                )
                != common_parent
            ):
                raise OfflineEvidenceError("formal parent broker denial probe path mismatch")
        else:
            if operation["denial_probe_path"] is not None:
                raise OfflineEvidenceError("formal parent broker denial probe is unexpected")
            denial_path = None

        snapshot_identity = _validated_persisted_snapshot_identity(
            operation["snapshot_identity"]
        )
        if kind == "test-component":
            expected_snapshot = parameters["test_scope"]
        elif kind == "ocr-native":
            expected_snapshot = runner.get("test_scope")
        else:
            snapshot_key = "disclosure" if kind == "disclosure" else "process-isolation"
            if snapshot_key not in expected_snapshots:
                expected_snapshots[snapshot_key] = _snapshot_source_identity_from_fd(
                    repo_fd,
                    tree_roots=() if kind == "disclosure" else ("deploy",),
                    exact_files=(
                        _DISCLOSURE_SNAPSHOT_FILES if kind == "disclosure" else ()
                    ),
                    materialized=False,
                )
            expected_snapshot = expected_snapshots[snapshot_key]
        if not _type_sensitive_equal(snapshot_identity, expected_snapshot):
            raise OfflineEvidenceError("formal parent broker snapshot identity mismatch")

        production_embedding_operation = (
            production_embedding_probe
            and kind == "test-component"
            and parameters["component"] == _PRODUCTION_EMBEDDING_PROBE_ID
        )
        if production_embedding_operation:
            assert production_embedding_fixture is not None
            production_embedding_target = (
                scratch_path / _PRODUCTION_EMBEDDING_TARGET_RELATIVE
            )
            expected_closure = _production_embedding_probe_closure(
                restricted_closure,
                production_embedding_fixture,
                target_executable=production_embedding_target,
            )
            operation_external_tools = _empty_external_tool_set()
            _validated_production_embedding_target_executable_identity(
                operation["target_executable_identity"],
                expected_path=production_embedding_target,
                python_identity=runner["python_identity"],
            )
        else:
            if operation["target_executable_identity"] is not None:
                raise OfflineEvidenceError(
                    "production embedding target executable identity is unexpected"
                )
            expected_closure = (
                full_closure
                if kind in {"test-component", "ocr-native"}
                else restricted_closure
            )
            operation_external_tools = full_external_tools
        if not _type_sensitive_equal(
            operation["runtime_closure_identity"], expected_closure.identity
        ):
            raise OfflineEvidenceError("formal parent broker runtime closure mismatch")
        profile_payload = _decoded_canonical_base64(
            operation["profile_base64"],
            field="formal parent broker profile bytes",
            max_bytes=2 * 1024 * 1024,
        )
        if kind == "ocr-native":
            containment_path = worker_scratch_path / parameters[
                "containment_relative"
            ]
            native_runtime_path = worker_scratch_path / parameters[
                "native_runtime_relative"
            ]
            executable_path = worker_scratch_path / parameters[
                "private_executable_relative"
            ]
            library_path = worker_scratch_path / parameters[
                "private_library_relative"
            ]
            for persisted_path, relative, field in (
                (
                    containment_path,
                    parameters["containment_relative"],
                    "formal parent broker OCR containment",
                ),
                (
                    native_runtime_path,
                    parameters["native_runtime_relative"],
                    "formal parent broker OCR native runtime",
                ),
                (
                    executable_path,
                    parameters["private_executable_relative"],
                    "formal parent broker OCR executable",
                ),
                (
                    library_path,
                    parameters["private_library_relative"],
                    "formal parent broker OCR library",
                ),
            ):
                if (
                    _persisted_relative_parent(persisted_path, relative, field)
                    != worker_scratch_path
                ):
                    raise OfflineEvidenceError(
                        "formal parent broker OCR path roots do not bind"
                    )
            expected_ocr_environment = {
                "PATH": _OCR_NATIVE_TOOL_SEARCH_PATH,
                "DYLD_LIBRARY_PATH": str(library_path),
                "TMPDIR": str(scratch_path),
                "TMP": str(scratch_path),
                "TEMP": str(scratch_path),
                "HOME": str(scratch_path),
            }
            if parameters["tool"] == "pdftoppm":
                private_fontconfig_path = worker_scratch_path / parameters[
                    "private_fontconfig_relative"
                ]
                for persisted_path, relative, field in (
                    (
                        private_fontconfig_path,
                        parameters["private_fontconfig_relative"],
                        "formal parent broker OCR private fontconfig",
                    ),
                ):
                    if (
                        _persisted_relative_parent(
                            persisted_path,
                            relative,
                            field,
                        )
                        != worker_scratch_path
                    ):
                        raise OfflineEvidenceError(
                            "formal parent broker OCR path does not bind"
                        )
                expected_ocr_environment["FONTCONFIG_FILE"] = str(
                    private_fontconfig_path
                )
                output_prefix_relative = parameters["output_prefix_relative"]
                if parameters["input_delivery"] == "inline-base64":
                    output_prefix_path = (
                        worker_scratch_path / output_prefix_relative
                    )
                    if (
                        _persisted_relative_parent(
                            output_prefix_path,
                            output_prefix_relative,
                            "formal parent broker OCR output prefix",
                        )
                        != worker_scratch_path
                    ):
                        raise OfflineEvidenceError(
                            "formal parent broker OCR path does not bind"
                        )
                    writable_roots = (
                        scratch_path,
                        output_prefix_path.parent,
                    )
                else:
                    writable_roots = (scratch_path,)
                expected_profile = _expected_ocr_native_profile(
                    executable_path,
                    writable_roots=writable_roots,
                    read_only_roots=(
                        native_runtime_path,
                        _HOMEBREW_POPPLER_DATA_ROOT,
                    ),
                    read_only_files=(),
                ).encode("utf-8")
            else:
                page_path = worker_scratch_path / parameters[
                    "approved_page_relative"
                ]
                private_tessdata_path = worker_scratch_path / parameters[
                    "private_tessdata_relative"
                ]
                for persisted_path, relative, field in (
                    (
                        page_path,
                        parameters["approved_page_relative"],
                        "formal parent broker OCR approved page",
                    ),
                    (
                        private_tessdata_path,
                        parameters["private_tessdata_relative"],
                        "formal parent broker OCR private tessdata",
                    ),
                ):
                    if (
                        _persisted_relative_parent(persisted_path, relative, field)
                        != worker_scratch_path
                    ):
                        raise OfflineEvidenceError(
                            "formal parent broker OCR path roots do not bind"
                        )
                expected_ocr_environment.update(
                    {
                        "TESSDATA_PREFIX": str(private_tessdata_path),
                        "OMP_THREAD_LIMIT": "1",
                    }
                )
                expected_profile = _expected_ocr_native_profile(
                    executable_path,
                    writable_roots=(scratch_path,),
                    read_only_roots=(native_runtime_path,),
                    read_only_files=(page_path,),
                ).encode("utf-8")
        else:
            expected_profile = _child_sandbox_profile_from_bound_paths(
                snapshot_path,
                scratch_path,
                expected_closure,
            ).encode("utf-8")
        if profile_payload != expected_profile:
            raise OfflineEvidenceError("formal parent broker profile bytes mismatch")
        profile_sha256 = hashlib.sha256(profile_payload).hexdigest()
        if kind == "ocr-native":
            supplied_profile_size = parameters["profile_size"]
            supplied_profile_sha256 = parameters["profile_sha256"]
        else:
            supplied_profile_size = parameters["supplied_profile_size"]
            supplied_profile_sha256 = parameters["supplied_profile_sha256"]
        if (
            type(supplied_profile_size) is not int
            or supplied_profile_size != len(profile_payload)
            or supplied_profile_sha256 != profile_sha256
        ):
            raise OfflineEvidenceError("formal parent broker supplied profile mismatch")

        if denial_path is None:
            expected_child_sandbox = None
        else:
            expected_child_sandbox = _child_sandbox_binding_for_paths(
                profile=profile_payload.decode("utf-8"),
                snapshot_path=snapshot_path,
                snapshot_identity=snapshot_identity,
                scratch_path=scratch_path,
                denial_probe_path=denial_path,
                closure=expected_closure,
            )
        if not _type_sensitive_equal(
            operation["child_sandbox_binding"], expected_child_sandbox
        ):
            raise OfflineEvidenceError("formal parent broker child sandbox binding mismatch")
        if kind == "ocr-native":
            expected_environment = expected_ocr_environment
        else:
            expected_environment = _expected_parent_broker_environment(
                parameters=parameters,
                scratch_path=scratch_path,
                python=python,
                full_external_tools=operation_external_tools,
                child_sandbox_binding=expected_child_sandbox,
                production_embedding_fixture=(
                    production_embedding_fixture
                    if production_embedding_operation
                    else None
                ),
            )
        if not _type_sensitive_equal(operation["environment"], expected_environment):
            raise OfflineEvidenceError("formal parent broker child environment mismatch")
        normalized_command = _parent_broker_normalized_command(
            parameters,
            operation_id=expected_operation,
        )
        if not _type_sensitive_equal(
            operation["normalized_command"], normalized_command
        ):
            raise OfflineEvidenceError("formal parent broker command identity mismatch")

        response_payload = _decoded_canonical_base64(
            operation["response_base64"],
            field="formal parent broker response bytes",
            max_bytes=_BROKER_FRAME_MAX_BYTES,
        )
        try:
            response = json.loads(response_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfflineEvidenceError("formal parent broker response is malformed") from exc
        expected_text_mode = False
        separate_stderr = parameters["capture_mode"] == (
            "bytes-separate-stdout-stderr"
        )
        if (
            not isinstance(response, Mapping)
            or set(response) != response_fields
            or response_payload != canonical_json_bytes(response)
            or response["schema_version"] != PARENT_BROKER_PROTOCOL_SCHEMA_VERSION
            or response["session"] != expected_session
            or type(response["sequence"]) is not int
            or response["sequence"] != sequence
            or response["probe_id"] != probe_id
            or response["operation_id"] != expected_operation
            or not _type_sensitive_equal(
                response["process_identity"], child_process_identity
            )
            or response["request_sha256"] != request_sha256
            or response["status"] != "completed"
            or type(response["returncode"]) is not int
            or type(response["text_mode"]) is not bool
            or response["text_mode"] is not expected_text_mode
            or response["timed_out"] is not False
            or (
                kind == "ocr-native"
                and (
                    not _type_sensitive_equal(
                        response["process_timing"], operation["process_timing"]
                    )
                    or not _type_sensitive_equal(
                        response["execution_slot"], operation["execution_slot"]
                    )
                )
            )
            or (
                kind != "ocr-native"
                and (
                    response["process_timing"] is not None
                    or response["execution_slot"] is not None
                )
            )
        ):
            raise OfflineEvidenceError("formal parent broker response identity mismatch")
        stdout = _decoded_canonical_base64(
            response["stdout_base64"],
            field="formal parent broker response stdout",
            max_bytes=_BROKER_STDOUT_MAX_BYTES,
        )
        if separate_stderr:
            stderr = _decoded_canonical_base64(
                response["stderr_base64"],
                field="formal parent broker response stderr",
                max_bytes=_BROKER_STDERR_MAX_BYTES,
            )
        else:
            if response["stderr_base64"] is not None:
                raise OfflineEvidenceError(
                    "formal parent broker merged stderr response is malformed"
                )
            stderr = b""
        _validated_parent_broker_output(
            stdout,
            stderr if separate_stderr else None,
            field="formal parent broker response",
        )

        expected_returncode = (
            1
            if probe_id == "runner-sitecustomize-rejection"
            and kind == "test-component"
            else 0
        )
        if response["returncode"] != expected_returncode:
            raise OfflineEvidenceError("formal parent broker child outcome mismatch")
        if kind == "test-component":
            try:
                child_result = json.loads(stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OfflineEvidenceError(
                    "formal parent broker unittest result is malformed"
                ) from exc
            child_fields = {
                "schema_version",
                "runner_source_path",
                "runner_source_sha256",
                "python_identity",
                "test_scope",
                "process_identity",
                "module_origin_ledger",
                "network_enforcement",
                "sandbox_enforcement",
                "test_id_manifest",
                "test_count",
                "successful",
                "failure_count",
                "error_count",
                "skipped_count",
                "unittest_log_base64",
            }
            if not isinstance(child_result, Mapping) or set(child_result) != child_fields:
                raise OfflineEvidenceError(
                    "formal parent broker unittest result is malformed"
                )
            module_ledger = _validated_module_origin_ledger(
                child_result["module_origin_ledger"],
                repo_fd=repo_fd,
                test_scope=snapshot_identity,
            )
            sandbox_enforcement = _validated_sandbox_enforcement(
                child_result["sandbox_enforcement"]
            )
            manifest_value = child_result["test_id_manifest"]
            if not isinstance(manifest_value, Mapping):
                raise OfflineEvidenceError(
                    "formal parent broker unittest manifest is malformed"
                )
            manifest = _validated_test_id_manifest(
                parameters["component"],
                manifest_value.get("test_ids", ()),
                parameters["baseline"],
            )
            expected_success = expected_returncode == 0
            if (
                stdout != canonical_json_bytes(child_result)
                or child_result["schema_version"] != TEST_PROCESS_RESULT_SCHEMA_VERSION
                or child_result["runner_source_path"] != OFFLINE_EVIDENCE_SOURCE_PATH
                or not isinstance(child_result["runner_source_sha256"], str)
                or not _SHA256.fullmatch(child_result["runner_source_sha256"])
                or not _type_sensitive_equal(
                    child_result["python_identity"], runner["python_identity"]
                )
                or not _type_sensitive_equal(child_result["test_scope"], snapshot_identity)
                or not _type_sensitive_equal(
                    child_result["process_identity"], child_process_identity
                )
                or not _type_sensitive_equal(child_result["module_origin_ledger"], module_ledger)
                or not _type_sensitive_equal(
                    child_result["network_enforcement"], _network_enforcement_success()
                )
                or not _type_sensitive_equal(
                    child_result["sandbox_enforcement"], sandbox_enforcement
                )
                or sandbox_enforcement["sandbox_binding_sha256"]
                != expected_child_sandbox["identity_sha256"]
                or not _type_sensitive_equal(child_result["test_id_manifest"], manifest)
                or type(child_result["test_count"]) is not int
                or child_result["test_count"] != 1
                or type(child_result["successful"]) is not bool
                or child_result["successful"] is not expected_success
                or type(child_result["failure_count"]) is not int
                or child_result["failure_count"] != (0 if expected_success else 1)
                or type(child_result["error_count"]) is not int
                or child_result["error_count"] != 0
                or type(child_result["skipped_count"]) is not int
                or child_result["skipped_count"] != 0
            ):
                raise OfflineEvidenceError(
                    "formal parent broker unittest result identity mismatch"
                )
            child_log = _decoded_canonical_base64(
                child_result["unittest_log_base64"],
                field="formal parent broker unittest log",
                max_bytes=16 * 1024 * 1024,
            )
            if expected_success:
                if _parse_unittest_log(child_log) != 1:
                    raise OfflineEvidenceError(
                        "formal parent broker unittest log count mismatch"
                    )
            elif b"FAILED (failures=1)" not in child_log:
                raise OfflineEvidenceError(
                    "formal parent broker failing unittest log is malformed"
                )
        elif kind == "disclosure":
            try:
                disclosure_result = json.loads(stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OfflineEvidenceError(
                    "formal parent broker disclosure result is malformed"
                ) from exc
            if expected_disclosure_output is None:
                repository = _descriptor_directory_path(
                    repo_fd, "formal parent broker disclosure repository"
                )
                disclosure_core = _disclosure_receipt_value(
                    repo_root=repository,
                    created_at="2026-09-02T00:00:00Z",
                )
                expected_disclosure_output = {
                    **disclosure_core,
                    "receipt_sha256": hashlib.sha256(
                        canonical_json_bytes(disclosure_core)
                    ).hexdigest(),
                }
            if (
                stdout != canonical_json_bytes(disclosure_result)
                or not _type_sensitive_equal(
                    disclosure_result, expected_disclosure_output
                )
            ):
                raise OfflineEvidenceError(
                    "formal parent broker disclosure result identity mismatch"
                )
        elif kind == "process-isolation":
            try:
                process_result = json.loads(stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OfflineEvidenceError(
                    "formal parent broker process result is malformed"
                ) from exc
            if stdout != (json.dumps(process_result, sort_keys=True) + "\n").encode(
                "utf-8"
            ):
                raise OfflineEvidenceError(
                    "formal parent broker process result identity mismatch"
                )
            _validated_process_isolation_result(
                process_result,
                role=parameters["role"],
                observed_pids=process_isolation_pids,
                expected_pid=child_process_identity["pid"],
            )

        response_sha256 = hashlib.sha256(response_payload).hexdigest()
        if kind == "ocr-native":
            expected_network = {
                "schema_version": NETWORK_ENFORCEMENT_SCHEMA_VERSION,
                "status": "passed",
                "source": "reconstructed-source-extract-inline-seatbelt-profile",
                "required_result": {
                    "profile_rule": "(deny network*)",
                    "sandbox": "sandbox-exec-inline-profile",
                },
            }
            expected_stdin_role = parameters["stdin_role"]
            expected_stdin_profile_size = 0
            expected_stdin_profile_sha256 = hashlib.sha256(b"").hexdigest()
            expected_pass_fd_roles: list[str] = []
        else:
            expected_network = {
                "schema_version": NETWORK_ENFORCEMENT_SCHEMA_VERSION,
                "status": "passed",
                "source": _parent_broker_network_source(kind),
                "required_result": _network_enforcement_success(),
            }
            expected_stdin_role = "sandbox-profile-pipe"
            expected_stdin_profile_size = len(profile_payload)
            expected_stdin_profile_sha256 = profile_sha256
            expected_pass_fd_roles = ["snapshot-root"]
        operation_core = {
            field: operation[field]
            for field in expected_operation_fields
            if field != "identity_sha256"
        }
        if (
            type(operation["sequence"]) is not int
            or operation["sequence"] != sequence
            or operation["operation_id"] != expected_operation
            or operation["parameters_sha256"] != parameters_sha256
            or operation["normalized_command_sha256"]
            != _identity_sha256(normalized_command)
            or operation["stdin_role"] != expected_stdin_role
            or type(operation["stdin_profile_size"]) is not int
            or operation["stdin_profile_size"] != expected_stdin_profile_size
            or operation["stdin_profile_sha256"]
            != expected_stdin_profile_sha256
            or operation["profile_sha256"] != profile_sha256
            or operation["runtime_closure_identity_sha256"]
            != expected_closure.identity["identity_sha256"]
            or operation["snapshot_identity_sha256"]
            != snapshot_identity["identity_sha256"]
            or operation["environment_sha256"] != _identity_sha256(expected_environment)
            or not _type_sensitive_equal(
                operation["pass_fd_roles"],
                expected_pass_fd_roles,
            )
            or type(operation["returncode"]) is not int
            or operation["returncode"] != response["returncode"]
            or type(operation["stdout_size"]) is not int
            or operation["stdout_size"] != len(stdout)
            or operation["stdout_sha256"] != hashlib.sha256(stdout).hexdigest()
            or type(operation["stderr_size"]) is not int
            or operation["stderr_size"] != len(stderr)
            or operation["stderr_sha256"] != hashlib.sha256(stderr).hexdigest()
            or type(operation["text_mode"]) is not bool
            or operation["text_mode"] is not response["text_mode"]
            or not _type_sensitive_equal(operation["network_enforcement"], expected_network)
            or operation["direct_child_waited"] is not True
            or operation["process_group_quiescence_verified"] is not True
            or operation["timeout_cleanup_contract"]
            != "new-session-process-group-quiescence-or-killpg-and-wait"
            or operation["request_sha256"] != request_sha256
            or operation["response_sha256"] != response_sha256
            or operation["identity_sha256"] != _identity_sha256(operation_core)
        ):
            raise OfflineEvidenceError("formal parent broker operation identity mismatch")
        if kind == "ocr-native":
            _validated_ocr_native_operation_extras(
                operation,
                probe_id=probe_id,
                sequence=sequence,
                parameters=parameters,
                worker_scratch_path=worker_scratch_path,
                profile_payload=profile_payload,
                sealed_tessdata_snapshot_identity=expected_ocr_tessdata_identity,
                shared_deadline_monotonic_ns=shared_deadline_monotonic_ns,
                approved_materialization=approved_ocr_materializations[
                    parameters["tool"]
                ],
            )
        for field in (
            "parameters_sha256",
            "normalized_command_sha256",
            "stdin_profile_sha256",
            "profile_sha256",
            "runtime_closure_identity_sha256",
            "snapshot_identity_sha256",
            "environment_sha256",
            "stdout_sha256",
            "stderr_sha256",
            "request_sha256",
            "response_sha256",
            "identity_sha256",
        ):
            if not isinstance(operation[field], str) or not _SHA256.fullmatch(
                operation[field]
            ):
                raise OfflineEvidenceError(
                    "formal parent broker operation digest is invalid"
                )
        if kind == "ocr-native":
            if operation["profile_scratch"] is not None:
                raise OfflineEvidenceError(
                    "formal parent broker OCR profile scratch is unexpected"
                )
        else:
            _validated_scratch_record(
                operation["profile_scratch"],
                field="formal parent broker profile scratch",
                scratch_roots=scratch_roots,
            )
        exchange = {
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        }
        recomputed_exchanges.append(exchange)
        recomputed_chain = _identity_sha256(
            [recomputed_chain, request_sha256, response_sha256]
        )
    if ocr_tessdata_probe:
        assert expected_ocr_tessdata_identity is not None
        expected_ocr_summary = _ocr_native_summary(
            value["operations"],
            sealed_tessdata_snapshot_identity_sha256=(
                expected_ocr_tessdata_identity["identity_sha256"]
            ),
            shared_deadline_monotonic_ns=shared_deadline_monotonic_ns,
        )
        if not _type_sensitive_equal(
            value["ocr_native_summary"], expected_ocr_summary
        ):
            raise OfflineEvidenceError(
                "formal parent broker OCR native summary mismatch"
            )
    core = {field: value[field] for field in fields if field != "identity_sha256"}
    if (
        not _type_sensitive_equal(value["exchange_hashes"], recomputed_exchanges)
        or not _type_sensitive_equal(
            client_transcript.get("exchange_hashes"), recomputed_exchanges
        )
        or value["exchange_chain_sha256"] != recomputed_chain
        or client_transcript.get("exchange_chain_sha256") != recomputed_chain
        or value["identity_sha256"] != _identity_sha256(core)
    ):
        raise OfflineEvidenceError("formal parent broker transcript identity mismatch")
    if production_embedding_fixture is not None:
        _revalidate_production_embedding_fixture(production_embedding_fixture)
    return dict(value)


def _validated_parent_probe_records(
    value: object,
    evidence_root: Path,
    runner: Mapping[str, Any],
    *,
    repo_fd: int,
    scratch_roots: set[tuple[int, int]],
    held_log_payloads: Mapping[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    policy = runner.get("formal_parent_probe_policy")
    if not isinstance(policy, Mapping) or not _type_sensitive_equal(
        policy, _formal_parent_probe_policy()
    ):
        raise OfflineEvidenceError("formal parent probe policy is malformed")
    expected_specs = policy["probes"]
    if not isinstance(value, list) or len(value) != len(expected_specs):
        raise OfflineEvidenceError("formal parent probe coverage is not exact")
    production_embedding_required = any(
        isinstance(spec, Mapping)
        and spec.get("probe_id") == _PRODUCTION_EMBEDDING_PROBE_ID
        for spec in expected_specs
    )
    production_embedding_fixture = _resolve_production_embedding_fixture(
        required=production_embedding_required
    )
    if production_embedding_required:
        if (
            production_embedding_fixture is None
            or not _type_sensitive_equal(
                runner.get("production_embedding_fixture"),
                production_embedding_fixture.identity,
            )
        ):
            raise OfflineEvidenceError(
                "formal parent probe production embedding fixture mismatch"
            )
        _revalidate_production_embedding_fixture(production_embedding_fixture)
    python = _python_executable()
    python_identity = _python_identity(python)
    if not _type_sensitive_equal(python_identity, runner.get("python_identity")):
        raise OfflineEvidenceError("formal parent broker Python identity mismatch")
    full_external_tools = _resolve_external_tools()
    if not _type_sensitive_equal(
        full_external_tools.identity, runner.get("external_tools")
    ):
        raise OfflineEvidenceError("formal parent broker external tool identity mismatch")
    full_closure = _runtime_sandbox_closure(
        python=python,
        python_identity=python_identity,
        external_tools=full_external_tools,
    )
    if not _type_sensitive_equal(full_closure.identity, runner.get("sandbox_closure")):
        raise OfflineEvidenceError("formal parent broker runtime closure mismatch")
    restricted_closure = _runtime_sandbox_closure(
        python=python,
        python_identity=python_identity,
        external_tools=_empty_external_tool_set(),
    )
    closure_manifest = _module_closure_manifest(
        repo_fd,
        schema_version="cloud-v2-formal-bootstrap-closure-v1",
        field="formal parent probe validation module",
    )
    expected_closure_sha256 = _module_closure_source_sha256(closure_manifest)
    records: list[dict[str, Any]] = []
    mapping: list[dict[str, str]] = []
    probe_ids: list[str] = []
    fields = {
        "schema_version",
        "probe_id",
        "covered_test_id",
        "source_path",
        "source_sha256",
        "command_id",
        "command",
        "command_sha256",
        "formal_closure_sha256",
        "exit_code",
        "test_count",
        "status",
        "machine_result",
        "raw_result_sha256",
        "worker_launch",
        "broker_transcript",
        "scratch",
        "worker_denial_probe_scratch",
        "evidence_path",
        "evidence_sha256",
    }
    for index, (item, spec) in enumerate(zip(value, expected_specs)):
        if not isinstance(item, Mapping) or set(item) != fields:
            raise OfflineEvidenceError(
                f"formal parent probe {index} does not match its schema"
            )
        probe_id = item["probe_id"]
        expected_command_id, expected_command = _expected_parent_probe_command(
            spec["probe_id"]
        )
        _source_payload, source_binding = _stable_relative_file_binding(
            repo_fd,
            spec["source_path"],
            "formal parent probe validation source",
            max_bytes=4 * 1024 * 1024,
        )
        if (
            item["schema_version"] != PARENT_PROBE_RECORD_SCHEMA_VERSION
            or probe_id != spec["probe_id"]
            or item["covered_test_id"] != spec["covered_test_id"]
            or item["source_path"] != spec["source_path"]
            or item["source_sha256"] != source_binding["sha256"]
            or item["command_id"] != expected_command_id
            or item["command"] != expected_command
            or item["command_sha256"] != _identity_sha256(expected_command)
            or item["formal_closure_sha256"] != expected_closure_sha256
            or type(item["exit_code"]) is not int
            or item["exit_code"] != 0
            or type(item["test_count"]) is not int
            or item["test_count"] != 1
            or item["status"] != "passed"
        ):
            raise OfflineEvidenceError("formal parent probe identity mismatch")
        for digest_field in (
            "source_sha256",
            "command_sha256",
            "formal_closure_sha256",
            "raw_result_sha256",
            "evidence_sha256",
        ):
            if (
                not isinstance(item[digest_field], str)
                or not _SHA256.fullmatch(item[digest_field])
            ):
                raise OfflineEvidenceError("formal parent probe digest is invalid")
        _validated_scratch_record(
            item["scratch"],
            field="formal parent probe scratch record",
            scratch_roots=scratch_roots,
        )
        _validated_scratch_record(
            item["worker_denial_probe_scratch"],
            field="formal parent worker denial-probe scratch record",
            scratch_roots=scratch_roots,
        )
        relative = _canonical_relative(
            item["evidence_path"],
            "formal parent probe evidence_path",
        )
        if relative != f"logs/{probe_id}.log":
            raise OfflineEvidenceError("formal parent probe log path is not fixed")
        if held_log_payloads is None:
            log_payload = _stable_file_bytes(
                evidence_root / relative,
                f"formal parent probe log {probe_id}",
                max_bytes=16 * 1024 * 1024,
            )
        else:
            try:
                log_payload = held_log_payloads[relative]
            except KeyError as exc:
                raise OfflineEvidenceError(
                    "formal parent probe held log is missing"
                ) from exc
        if hashlib.sha256(log_payload).hexdigest() != item["evidence_sha256"]:
            raise OfflineEvidenceError("formal parent probe log identity mismatch")
        process_payload, process_result = _reconstructed_parent_probe_payload(
            item["machine_result"],
            log_payload,
            runner=runner,
            spec=spec,
            expected_source_sha256=source_binding["sha256"],
            repo_fd=repo_fd,
        )
        if hashlib.sha256(process_payload).hexdigest() != item["raw_result_sha256"]:
            raise OfflineEvidenceError("formal parent probe result identity mismatch")
        worker_launch = _validated_parent_worker_launch(
            item["worker_launch"],
            probe_id=probe_id,
            runner=runner,
            expected_closure_sha256=expected_closure_sha256,
            full_external_tools=full_external_tools,
            full_closure=full_closure,
            production_embedding_fixture=(
                production_embedding_fixture
                if probe_id == _PRODUCTION_EMBEDDING_PROBE_ID
                else None
            ),
        )
        client_transcript = process_result["broker_client_transcript"]
        broker_transcript = _validated_parent_broker_transcript(
            item["broker_transcript"],
            probe_id=probe_id,
            client_transcript=client_transcript,
            runner=runner,
            worker_launch=worker_launch,
            repo_fd=repo_fd,
            full_external_tools=full_external_tools,
            full_closure=full_closure,
            restricted_closure=restricted_closure,
            scratch_roots=scratch_roots,
            production_embedding_fixture=(
                production_embedding_fixture
                if probe_id == _PRODUCTION_EMBEDDING_PROBE_ID
                else None
            ),
        )
        enforcement = process_result["worker_sandbox_enforcement"]
        worker_binding = worker_launch["sandbox_binding"]
        if (
            worker_launch["broker_session"] != broker_transcript["session"]
            or not _type_sensitive_equal(
                worker_launch["process_identity"],
                process_result["worker_process_identity"],
            )
            or any(
                item_enforcement["sandbox_binding_sha256"]
                != worker_binding["identity_sha256"]
                or item_enforcement["context_identity_sha256"]
                != worker_launch["sandbox_context_identity_sha256"]
                for item_enforcement in (
                    enforcement["initial"],
                    enforcement["final"],
                )
            )
        ):
            raise OfflineEvidenceError(
                "formal parent worker and broker identities do not bind"
            )
        if (
            process_result["successful"] is not True
            or process_result["test_count"] != item["test_count"]
            or process_result["failure_count"] != 0
            or process_result["error_count"] != 0
            or process_result["skipped_count"] != 0
            or _parse_unittest_log(log_payload) != item["test_count"]
        ):
            raise OfflineEvidenceError("formal parent probe result is not passing")
        probe_ids.append(probe_id)
        mapping.append(
            {
                "probe_id": probe_id,
                "source_path": item["source_path"],
                "covered_test_id": item["covered_test_id"],
            }
        )
        records.append(dict(item))
    if (
        len(records) != policy["probe_count"]
        or _identity_sha256(probe_ids) != policy["probe_ids_sha256"]
        or _identity_sha256(mapping) != policy["coverage_mapping_sha256"]
    ):
        raise OfflineEvidenceError("formal parent probe mapping identity mismatch")
    if production_embedding_fixture is not None:
        _revalidate_production_embedding_fixture(production_embedding_fixture)
    return records


def _test_components(
    value: object,
    evidence_root: Path,
    runner: Mapping[str, Any],
    *,
    repo_fd: int | None = None,
    held_log_payloads: Mapping[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise OfflineEvidenceError("test components must be a non-empty array")
    records: list[dict[str, Any]] = []
    names: list[str] = []
    scratch_roots: set[tuple[int, int]] = set()
    scratch_path_hashes: set[str] = set()
    sandbox_profile_hashes: set[str] = set()
    snapshot_path_hashes: set[str] = set()
    for index, item in enumerate(value):
        expected = {
            "name",
            "command_id",
            "command",
            "command_sha256",
            "exit_code",
            "test_count",
            "status",
            "process_identity",
            "machine_result",
            "child_result_sha256",
            "child_sandbox",
            "denial_probe",
            "scratch",
            "evidence_path",
            "evidence_sha256",
            "parent_probes",
        }
        if not isinstance(item, Mapping) or set(item) != expected:
            raise OfflineEvidenceError(f"test component {index} does not match its schema")
        name = item["name"]
        command_id = item["command_id"]
        if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
            raise OfflineEvidenceError("test component name is invalid")
        if not isinstance(command_id, str) or not _IDENTIFIER.fullmatch(command_id):
            raise OfflineEvidenceError("test command id is invalid")
        expected_command_id, expected_command = _expected_test_command(name)
        if command_id != expected_command_id or item["command"] != expected_command:
            raise OfflineEvidenceError("test command is not the fixed allowlisted command")
        if item["command_sha256"] != _identity_sha256(expected_command):
            raise OfflineEvidenceError("test command identity mismatch")
        if type(item["exit_code"]) is not int or item["exit_code"] != 0:
            raise OfflineEvidenceError("only a zero test exit code can be sealed")
        if type(item["test_count"]) is not int or item["test_count"] <= 0:
            raise OfflineEvidenceError("test count must be a positive integer")
        if item["status"] != "passed":
            raise OfflineEvidenceError("only passing test evidence can be sealed")
        process_identity = _validated_process_identity(
            item["process_identity"],
            f"test component {name}",
            require_session_leader=True,
        )
        child_sandbox = item["child_sandbox"]
        child_sandbox_fields = {
            "schema_version",
            "profile_sha256",
            "profile_template_sha256",
            "snapshot_path_sha256",
            "snapshot_identity_sha256",
            "scratch_path_sha256",
            "denied_read_probe_path_sha256",
            "denied_write_probe_path_sha256",
            "runtime_closure_identity_sha256",
            "identity_sha256",
        }
        if (
            not isinstance(child_sandbox, Mapping)
            or set(child_sandbox) != child_sandbox_fields
            or child_sandbox["schema_version"]
            != "cloud-v2-child-sandbox-binding-v2"
            or any(
                not isinstance(child_sandbox[field], str)
                or not _SHA256.fullmatch(child_sandbox[field])
                for field in child_sandbox_fields - {"schema_version"}
            )
            or child_sandbox["profile_template_sha256"]
            != hashlib.sha256(
                CHILD_FILESYSTEM_SANDBOX_TEMPLATE.encode("utf-8")
            ).hexdigest()
            or child_sandbox["snapshot_identity_sha256"]
            != runner["test_scope"]["identity_sha256"]
            or child_sandbox["runtime_closure_identity_sha256"]
            != runner["sandbox_closure"]["identity_sha256"]
        ):
            raise OfflineEvidenceError("test component child sandbox binding is malformed")
        sandbox_without_identity = {
            key: child_sandbox[key]
            for key in child_sandbox_fields
            if key != "identity_sha256"
        }
        if child_sandbox["identity_sha256"] != _identity_sha256(
            sandbox_without_identity
        ):
            raise OfflineEvidenceError("test component child sandbox identity mismatch")
        scratch_path_sha256 = child_sandbox["scratch_path_sha256"]
        profile_sha256 = child_sandbox["profile_sha256"]
        if scratch_path_sha256 in scratch_path_hashes:
            raise OfflineEvidenceError("test component scratch paths are not independent")
        if profile_sha256 in sandbox_profile_hashes:
            raise OfflineEvidenceError("test component sandbox profiles are not independent")
        scratch_path_hashes.add(scratch_path_sha256)
        sandbox_profile_hashes.add(profile_sha256)
        snapshot_path_hashes.add(child_sandbox["snapshot_path_sha256"])
        scratch = item["scratch"]
        scratch_fields = {
            "schema_version",
            "root_device",
            "root_inode",
            "root_mode",
            "root_uid",
            "root_gid",
            "initially_empty",
            "post_run_inventory",
            "cleanup_verified_empty",
            "identity_sha256",
        }
        if not isinstance(scratch, Mapping) or set(scratch) != scratch_fields:
            raise OfflineEvidenceError("test component scratch record is malformed")
        inventory = scratch["post_run_inventory"]
        if (
            scratch["schema_version"] != "cloud-v2-component-scratch-v1"
            or any(
                type(scratch[field]) is not int or scratch[field] < 0
                for field in (
                    "root_device",
                    "root_inode",
                    "root_mode",
                    "root_uid",
                    "root_gid",
                )
            )
            or scratch["root_inode"] == 0
            or scratch["root_mode"] != 0o700
            or scratch["initially_empty"] is not True
            or scratch["cleanup_verified_empty"] is not True
            or not isinstance(inventory, Mapping)
            or set(inventory) != {"node_count", "node_set_sha256"}
            or type(inventory["node_count"]) is not int
            or inventory["node_count"] < 0
            or not isinstance(inventory["node_set_sha256"], str)
            or not _SHA256.fullmatch(inventory["node_set_sha256"])
        ):
            raise OfflineEvidenceError("test component scratch record is malformed")
        scratch_root = (scratch["root_device"], scratch["root_inode"])
        if scratch_root in scratch_roots:
            raise OfflineEvidenceError("test component scratch roots are not independent")
        scratch_roots.add(scratch_root)
        if (
            inventory["node_count"] == 0
            and inventory["node_set_sha256"] != _identity_sha256([])
        ):
            raise OfflineEvidenceError("empty test component scratch identity mismatch")
        scratch_without_identity = {
            key: scratch[key] for key in scratch_fields if key != "identity_sha256"
        }
        if scratch["identity_sha256"] != _identity_sha256(scratch_without_identity):
            raise OfflineEvidenceError("test component scratch identity mismatch")
        denial_probe = item["denial_probe"]
        if not isinstance(denial_probe, Mapping) or set(denial_probe) != scratch_fields:
            raise OfflineEvidenceError("test component denial probe record is malformed")
        denial_inventory = denial_probe["post_run_inventory"]
        if (
            denial_probe["schema_version"] != "cloud-v2-component-scratch-v1"
            or any(
                type(denial_probe[field]) is not int or denial_probe[field] < 0
                for field in (
                    "root_device",
                    "root_inode",
                    "root_mode",
                    "root_uid",
                    "root_gid",
                )
            )
            or denial_probe["root_inode"] == 0
            or denial_probe["root_mode"] != 0o700
            or denial_probe["initially_empty"] is not True
            or denial_probe["cleanup_verified_empty"] is not True
            or not isinstance(denial_inventory, Mapping)
            or set(denial_inventory) != {"node_count", "node_set_sha256"}
            or denial_inventory["node_count"] != 1
            or not isinstance(denial_inventory["node_set_sha256"], str)
            or not _SHA256.fullmatch(denial_inventory["node_set_sha256"])
        ):
            raise OfflineEvidenceError("test component denial probe record is malformed")
        denial_root = (
            denial_probe["root_device"],
            denial_probe["root_inode"],
        )
        if denial_root in scratch_roots:
            raise OfflineEvidenceError("test component scratch roots are not independent")
        scratch_roots.add(denial_root)
        denial_without_identity = {
            key: denial_probe[key]
            for key in scratch_fields
            if key != "identity_sha256"
        }
        if denial_probe["identity_sha256"] != _identity_sha256(
            denial_without_identity
        ):
            raise OfflineEvidenceError("test component denial probe identity mismatch")
        child_result_sha256 = item["child_result_sha256"]
        if (
            not isinstance(child_result_sha256, str)
            or not _SHA256.fullmatch(child_result_sha256)
        ):
            raise OfflineEvidenceError("test child result SHA-256 is invalid")
        relative = _canonical_relative(item["evidence_path"], "evidence_path")
        if relative != f"logs/{name}.log":
            raise OfflineEvidenceError("test evidence path is not the fixed component log")
        digest = item["evidence_sha256"]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise OfflineEvidenceError("test evidence SHA-256 is invalid")
        if held_log_payloads is None:
            payload = _stable_file_bytes(
                evidence_root / relative,
                f"test evidence {relative}",
                max_bytes=16 * 1024 * 1024,
            )
        else:
            try:
                payload = held_log_payloads[relative]
            except KeyError as exc:
                raise OfflineEvidenceError("test evidence held log is missing") from exc
        if hashlib.sha256(payload).hexdigest() != digest:
            raise OfflineEvidenceError("test evidence byte identity mismatch")
        process_payload, process_result = _reconstructed_process_payload(
            item["machine_result"],
            payload,
            runner=runner,
            repo_fd=repo_fd,
        )
        if hashlib.sha256(process_payload).hexdigest() != child_result_sha256:
            raise OfflineEvidenceError("test child result byte identity mismatch")
        if (
            process_result["successful"] is not True
            or not _type_sensitive_equal(
                process_result["process_identity"], process_identity
            )
            or process_result["failure_count"] != 0
            or process_result["error_count"] != 0
            or process_result["skipped_count"] != 0
            or process_result["test_count"] != item["test_count"]
            or process_result["test_id_manifest"]["component"] != name
            or process_result["test_id_manifest"]["test_count"]
            != item["test_count"]
            or process_result["sandbox_enforcement"][
                "sandbox_binding_sha256"
            ]
            != child_sandbox["identity_sha256"]
        ):
            raise OfflineEvidenceError("test component machine result is not passing")
        if _parse_unittest_log(payload) != process_result["test_count"]:
            raise OfflineEvidenceError("test count differs from the parsed unittest log")
        validated_parent_probes: list[dict[str, Any]]
        if name == "formal-security-probes":
            if repo_fd is None:
                repository = _module_repository_root()
                _repository, owned_repo_fd = _open_directory_fd(
                    repository,
                    "formal parent probe validation repository",
                )
                try:
                    validated_parent_probes = _validated_parent_probe_records(
                        item["parent_probes"],
                        evidence_root,
                        runner,
                        repo_fd=owned_repo_fd,
                        scratch_roots=scratch_roots,
                        held_log_payloads=held_log_payloads,
                    )
                finally:
                    os.close(owned_repo_fd)
            else:
                validated_parent_probes = _validated_parent_probe_records(
                    item["parent_probes"],
                    evidence_root,
                    runner,
                    repo_fd=repo_fd,
                    scratch_roots=scratch_roots,
                    held_log_payloads=held_log_payloads,
                )
        elif item["parent_probes"] != []:
            raise OfflineEvidenceError(
                "formal parent probes belong only to formal-security-probes"
            )
        else:
            validated_parent_probes = []
        names.append(name)
        records.append({**dict(item), "parent_probes": validated_parent_probes})
    if len(snapshot_path_hashes) != 1:
        raise OfflineEvidenceError("test components do not share one bound snapshot")
    if names != sorted(names) or len(names) != len(set(names)):
        raise OfflineEvidenceError("test components must be unique and sorted")
    return records


def _test_receipt_value(
    *,
    component_set: Mapping[str, Any],
    component_set_sha256: str,
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    formal_components = [
        item for item in components if item["name"] == "formal-security-probes"
    ]
    if len(formal_components) > 1:
        raise OfflineEvidenceError("formal security component coverage is not exact")
    parent_probes = (
        formal_components[0]["parent_probes"] if formal_components else []
    )
    parent_probe_ids = [item["probe_id"] for item in parent_probes]
    parent_probe_mapping = [
        {
            "probe_id": item["probe_id"],
            "source_path": item["source_path"],
            "covered_test_id": item["covered_test_id"],
        }
        for item in parent_probes
    ]
    policy = component_set["runner"]["formal_parent_probe_policy"]
    if (
        len(parent_probes) != policy["probe_count"]
        or _identity_sha256(parent_probe_ids) != policy["probe_ids_sha256"]
        or _identity_sha256(parent_probe_mapping)
        != policy["coverage_mapping_sha256"]
    ):
        raise OfflineEvidenceError("formal parent probe receipt summary mismatch")
    component_test_count = sum(item["test_count"] for item in components)
    parent_probe_test_count = sum(item["test_count"] for item in parent_probes)
    return {
        "schema_version": TEST_RECEIPT_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "assurance": {
            "scope": "local-integrity-evidence-only",
            "final_trust_requirement": (
                "user-review-and-approval-of-externally-reported-receipt-sha256"
            ),
            "signature": "not-provided",
            "remote_attestation": "not-provided",
        },
        "created_at": component_set["created_at"],
        "component_set_sha256": component_set_sha256,
        "runner": component_set["runner"],
        "components": components,
        "component_count": len(components),
        "component_test_count": component_test_count,
        "parent_probe_count": len(parent_probes),
        "parent_probe_test_count": parent_probe_test_count,
        "parent_probe_ids_sha256": _identity_sha256(parent_probe_ids),
        "parent_probe_coverage_mapping_sha256": _identity_sha256(
            parent_probe_mapping
        ),
        "test_count": component_test_count + parent_probe_test_count,
        "real_provider_calls": 0,
        "network_calls": 0,
    }


def build_test_receipt(
    *,
    evidence_root: str | Path,
    component_set_path: str | Path,
    output_path: str | Path,
    created_at: str,
) -> dict[str, Any]:
    del evidence_root, component_set_path, output_path, created_at
    raise OfflineEvidenceError(
        "standalone test receipt construction is disabled; use atomic run-tests"
    )


def _validate_test_evidence_impl(
    *,
    repo_root: str | Path | None = None,
    evidence_root: str | Path,
    component_set_path: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    raw_root = Path(evidence_root)
    if raw_root.is_symlink():
        raise OfflineEvidenceError("test evidence root must be a real directory")
    root, root_fd = _open_directory_fd(raw_root, "test evidence root")
    logs_fd: int | None = None
    repository_fd: int | None = None
    held_files: list[_HeldFile] = []
    held_logs: list[_HeldFile] = []
    try:
        raw_repository = (
            _module_repository_root() if repo_root is None else Path(repo_root)
        )
        if raw_repository.is_symlink():
            raise OfflineEvidenceError("repository root must be a real directory")
        repository, repository_fd = _open_directory_fd(
            raw_repository,
            "repository root",
        )
        repository_state_before = _snapshot_live_state_identity_from_fd(
            repository_fd,
            tree_roots=_TEST_SNAPSHOT_TREE_ROOTS,
            exact_files=_TEST_SNAPSHOT_FILES,
        )
        component_held = _hold_file_under_root(
            component_set_path,
            root,
            "test component set",
            max_bytes=_TEST_COMPONENT_SET_MAX_BYTES,
        )
        held_files.append(component_held)
        _require_sealed_file_mode(component_held.state, "test component set")
        receipt_held = _hold_file_under_root(
            receipt_path,
            root,
            "test receipt",
            max_bytes=_TEST_RECEIPT_MAX_BYTES,
        )
        held_files.append(receipt_held)
        _require_sealed_file_mode(receipt_held.state, "test receipt")
        _logs_path, logs_fd = _open_directory_fd(
            root / "logs", "test evidence logs directory"
        )
        _revalidate_child_directory(
            root_fd,
            "logs",
            logs_fd,
            "test evidence logs directory",
        )
        expected_log_stems = _expected_test_log_stems()
        _validate_logs_fd(
            logs_fd,
            expected_names=expected_log_stems,
            require_sealed=True,
        )
        held_log_payloads: dict[str, bytes] = {}
        for stem in expected_log_stems:
            relative = f"logs/{stem}.log"
            held = _hold_file_under_root(
                root / relative,
                root,
                f"test evidence {relative}",
                max_bytes=16 * 1024 * 1024,
            )
            held_files.append(held)
            held_logs.append(held)
            held_log_payloads[relative] = held.payload
        _revalidate_child_directory(
            root_fd,
            "logs",
            logs_fd,
            "test evidence logs directory",
        )
        _validate_logs_fd(
            logs_fd,
            expected_names=expected_log_stems,
            require_sealed=True,
        )
        expected_evidence_root_state = _state_identity(os.fstat(root_fd))
        expected_logs_state = _state_identity(os.fstat(logs_fd))
        component_set, components = _validated_component_set(
            component_held.path,
            root,
            repo_root=repository,
            repo_fd=repository_fd,
            component_set_payload=component_held.payload,
            held_log_payloads=held_log_payloads,
        )
        receipt_payload = receipt_held.payload
        receipt = dict(
            _strict_json_bytes(receipt_payload, field="JSON evidence input")
        )
        if receipt_payload != canonical_json_bytes(receipt):
            raise OfflineEvidenceError("test receipt is not canonical JSON")
        expected = _test_receipt_value(
            component_set=component_set,
            component_set_sha256=hashlib.sha256(component_held.payload).hexdigest(),
            components=components,
        )
        if not _type_sensitive_equal(receipt, expected):
            raise OfflineEvidenceError(
                "test receipt is stale or differs from executed evidence"
            )

        # Component validation above exercises the full receipt closure. Rebuild
        # the runner identity afterwards so a permanent repository mutation
        # during that work cannot inherit the earlier passing identity.
        _source, runner_binding = _stable_relative_file_binding(
            repository_fd,
            OFFLINE_EVIDENCE_SOURCE_PATH,
            "offline evidence final validation source",
            max_bytes=4 * 1024 * 1024,
        )
        final_runner = _test_runner_identity(
            repository,
            repo_fd=repository_fd,
            executed_runner_source_sha256=runner_binding["sha256"],
            executed_runner_state_identity=_runner_state_from_binding(
                runner_binding
            ),
        )
        if not _type_sensitive_equal(component_set["runner"], final_runner):
            raise OfflineEvidenceError(
                "test runner identity or network policy mismatch"
            )

        # Artifact checks are deliberately last because runner reconstruction
        # above includes comparatively expensive runtime and repository reads.
        _revalidate_child_directory(
            root_fd,
            "logs",
            logs_fd,
            "test evidence logs directory",
        )
        _validate_logs_fd(
            logs_fd,
            expected_names=expected_log_stems,
            require_sealed=True,
        )
        for held in held_files:
            _revalidate_held_file(held)
            max_bytes = (
                _TEST_COMPONENT_SET_MAX_BYTES
                if held is component_held
                else _TEST_RECEIPT_MAX_BYTES
                if held is receipt_held
                else 16 * 1024 * 1024
            )
            if (
                _read_open_bytes(
                    held.descriptor,
                    held.state,
                    held.field,
                    max_bytes=max_bytes,
                )
                != held.payload
            ):
                raise OfflineEvidenceError(f"{held.field} bytes changed")
        for held in held_files:
            _revalidate_held_file(held)
        _revalidate_child_directory(
            root_fd,
            "logs",
            logs_fd,
            "test evidence logs directory",
        )
        _validate_logs_fd(
            logs_fd,
            expected_names=expected_log_stems,
            require_sealed=True,
        )

        # Artifact verification can be attacker-controlled work. Reconstruct
        # the complete runner identity after it so repository content or state
        # drift during those checks cannot escape via an unchanged root inode.
        _source, runner_binding = _stable_relative_file_binding(
            repository_fd,
            OFFLINE_EVIDENCE_SOURCE_PATH,
            "offline evidence terminal validation source",
            max_bytes=4 * 1024 * 1024,
        )
        terminal_runner = _test_runner_identity(
            repository,
            repo_fd=repository_fd,
            executed_runner_source_sha256=runner_binding["sha256"],
            executed_runner_state_identity=_runner_state_from_binding(
                runner_binding
            ),
        )
        if not _type_sensitive_equal(component_set["runner"], terminal_runner):
            raise OfflineEvidenceError(
                "test runner identity or network policy mismatch"
            )
        for held in held_files:
            _revalidate_held_file(held)
        _revalidate_child_directory(
            root_fd,
            "logs",
            logs_fd,
            "test evidence logs directory",
        )
        repository_state_after = _snapshot_live_state_identity_from_fd(
            repository_fd,
            tree_roots=_TEST_SNAPSHOT_TREE_ROOTS,
            exact_files=_TEST_SNAPSHOT_FILES,
        )
        if repository_state_after != repository_state_before:
            raise OfflineEvidenceError(
                "repository input state changed during evidence validation"
            )
        _revalidate_directory_path(raw_root, root_fd, "test evidence root")
        _revalidate_directory_path(
            raw_repository,
            repository_fd,
            "repository root",
        )
        _revalidate_held_test_artifacts(
            root_path=raw_root,
            root_fd=root_fd,
            logs_fd=logs_fd,
            expected_log_stems=expected_log_stems,
            component_held=component_held,
            receipt_held=receipt_held,
            log_held=held_logs,
            expected_root_state=expected_evidence_root_state,
            expected_logs_state=expected_logs_state,
        )
        return {
            **receipt,
            "receipt_sha256": hashlib.sha256(receipt_payload).hexdigest(),
        }
    finally:
        for held in reversed(held_files):
            _close_held_file(held)
        if logs_fd is not None:
            os.close(logs_fd)
        if repository_fd is not None:
            os.close(repository_fd)
        os.close(root_fd)


def validate_test_evidence(
    *,
    repo_root: str | Path | None = None,
    evidence_root: str | Path,
    component_set_path: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    actions = _require_formal_test_evidence_bootstrap_context()
    return actions[1](
        repo_root=repo_root,
        evidence_root=evidence_root,
        component_set_path=component_set_path,
        receipt_path=receipt_path,
    )


def run_offline_tests(
    *,
    repo_root: str | Path,
    evidence_root: str | Path,
    component_set_path: str | Path,
    receipt_path: str | Path,
    created_at: str,
    timeout_seconds: float = 900.0,
) -> dict[str, Any]:
    created_at = _require_utc_second(created_at, "created_at")
    timeout_seconds = _require_positive_timeout(timeout_seconds)
    raw_repository = Path(repo_root)
    if raw_repository.is_symlink():
        raise OfflineEvidenceError("repository root must be a real directory")
    repository, repository_fd = _open_directory_fd(
        raw_repository, "repository root"
    )
    approved_tessdata_input: _ApprovedTessdataInput | None = None
    try:
        _require_formal_bootstrap_context(repository_fd)
        production_embedding_fixture = _resolve_production_embedding_fixture(
            required=True
        )
        assert production_embedding_fixture is not None
        approved_tessdata_input = _resolve_approved_tessdata_input(required=True)
        assert approved_tessdata_input is not None
    except Exception:
        if approved_tessdata_input is not None:
            _close_approved_tessdata_input(approved_tessdata_input)
        os.close(repository_fd)
        raise
    raw_evidence_root = Path(evidence_root)
    if raw_evidence_root.is_symlink():
        os.close(repository_fd)
        raise OfflineEvidenceError("test evidence root must be a real directory")
    try:
        root, evidence_fd = _open_directory_fd(
            raw_evidence_root, "test evidence root"
        )
    except Exception:
        os.close(repository_fd)
        raise
    component_reservation: _ReservedOutput | None = None
    receipt_reservation: _ReservedOutput | None = None
    log_reservations: dict[str, _ReservedOutput] = {}
    logs_fd: int | None = None
    component_slot: tuple[Path, int] | None = None
    receipt_slot: tuple[Path, int] | None = None
    snapshot: _PrivateSnapshot | None = None
    ocr_tessdata_snapshot: _SealedTessdataSnapshot | None = None
    run_succeeded = False
    try:
        # Validate both JSON targets and hold their verified parent directory
        # descriptors before creating the logs directory or starting tests.
        component_slot = _new_output_slot_under_root(
            component_set_path,
            root,
            "test component set output",
        )
        try:
            receipt_slot = _new_output_slot_under_root(
                receipt_path,
                root,
                "test receipt output",
            )
        except Exception:
            os.close(component_slot[1])
            component_slot = None
            raise
        if (
            component_slot[0] == receipt_slot[0]
            or (
                component_slot[0].parent == receipt_slot[0].parent
                and unicodedata.normalize("NFC", component_slot[0].name).casefold()
                == unicodedata.normalize("NFC", receipt_slot[0].name).casefold()
            )
        ):
            raise OfflineEvidenceError(
                "test component set and receipt outputs must be distinct"
            )
        _reject_component_alias(evidence_fd, "logs", "test evidence logs directory")
        try:
            os.stat("logs", dir_fd=evidence_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OfflineEvidenceError("test evidence logs already exist")

        python = _python_executable()
        python_identity = _python_identity(python)
        _require_sealed_runtime_environment(python_identity["runtime_environment"])
        external_tool_set = _resolve_external_tools()
        closure = _runtime_sandbox_closure(
            python=python,
            python_identity=python_identity,
            external_tools=external_tool_set,
        )
        snapshot = _build_private_snapshot(
            repository_fd,
            tree_roots=_TEST_SNAPSHOT_TREE_ROOTS,
            exact_files=_TEST_SNAPSHOT_FILES,
        )
        ocr_tessdata_snapshot = _build_sealed_tessdata_snapshot(
            approved_tessdata_input
        )
        runner = _test_runner_identity(
            repository,
            repo_fd=repository_fd,
            test_scope=snapshot.identity,
            python_identity=python_identity,
            external_tool_identity=external_tool_set.identity,
            sandbox_closure_identity=closure.identity,
            production_embedding_fixture=production_embedding_fixture,
            approved_tessdata_input=approved_tessdata_input,
        )
        if runner["python_identity"] != python_identity:
            raise OfflineEvidenceError("Python identity changed before test execution")
        encoded_python_identity = _encode_expected_identity(runner["python_identity"])
        encoded_test_scope = _encode_expected_identity(runner["test_scope"])
        encoded_module_closure = _encoded_module_closure_manifest(
            snapshot.root_fd,
            schema_version="cloud-v2-child-bootstrap-closure-v1",
            field="test child module",
        )
        path_directories = tuple(
            dict.fromkeys((python.parent, *external_tool_set.path_directories))
        )
        commands: list[tuple[str, str, list[str], str]] = []
        for name in sorted(_TEST_COMPONENTS):
            command_id, normalized_command = _expected_test_command(name)
            start_directory = _TEST_COMPONENTS[name][1]
            test_fd = _open_relative_directory_fd(
                snapshot.root_fd,
                start_directory,
                f"allowlisted test directory {name}",
            )
            os.close(test_fd)
            commands.append((name, command_id, normalized_command, start_directory))

        component_output, component_parent_fd = component_slot
        component_slot = None
        component_reservation = _reserve_output_slot(
            component_output,
            component_parent_fd,
            readable=True,
        )
        receipt_output, receipt_parent_fd = receipt_slot
        receipt_slot = None
        receipt_reservation = _reserve_output_slot(
            receipt_output,
            receipt_parent_fd,
            readable=True,
        )
        logs_fd = _create_child_directory(
            evidence_fd,
            "logs",
            "test evidence logs directory",
        )
        for name in _expected_test_log_stems():
            filename = f"{name}.log"
            _reject_component_alias(logs_fd, filename, "test evidence log")
            log_reservations[name] = _reserve_output_slot(
                root / "logs" / filename,
                os.dup(logs_fd),
                readable=True,
            )
        _validate_logs_fd(logs_fd, expected_names=_expected_test_log_stems())

        components: list[dict[str, Any]] = []
        parent_probe_records: list[dict[str, Any]] = []

        def revalidate_execution_environment() -> None:
            if _python_identity(python) != python_identity:
                raise OfflineEvidenceError("Python identity changed during test execution")
            _revalidate_external_tools(external_tool_set.identity)
            _revalidate_runtime_sandbox_closure(
                closure.identity,
                python=python,
                python_identity=python_identity,
                external_tools=external_tool_set,
            )
            _revalidate_production_embedding_fixture(
                production_embedding_fixture
            )
            _revalidate_approved_tessdata_input(approved_tessdata_input)
            _revalidate_sealed_tessdata_snapshot(ocr_tessdata_snapshot)

        for spec in runner["formal_parent_probe_policy"]["probes"]:
            probe_id = spec["probe_id"]
            source_payload, _source_binding = _stable_relative_file_binding(
                snapshot.root_fd,
                spec["source_path"],
                "formal parent probe snapshot source",
                max_bytes=4 * 1024 * 1024,
            )
            source_sha256 = hashlib.sha256(source_payload).hexdigest()
            command_id, normalized_command = _expected_parent_probe_command(probe_id)
            _revalidate_directory_path(
                raw_repository,
                repository_fd,
                "repository root",
            )
            _revalidate_private_snapshot(snapshot)
            _revalidate_live_snapshot_inputs(repository_fd, snapshot)
            revalidate_execution_environment()
            try:
                brokered = _run_brokered_parent_probe(
                    spec=spec,
                    snapshot=snapshot,
                    runner=runner,
                    python=python,
                    python_identity=python_identity,
                    external_tools=external_tool_set,
                    closure=closure,
                    production_embedding_fixture=production_embedding_fixture,
                    ocr_tessdata_snapshot=ocr_tessdata_snapshot,
                    timeout_seconds=timeout_seconds,
                )
            except OfflineEvidenceError as exc:
                raise OfflineEvidenceError(
                    f"formal parent probe failed: {probe_id}: {exc}"
                ) from exc
            stdout = brokered["stdout"]
            returncode = brokered["returncode"]
            log_payload = brokered["log_payload"]
            process_result = brokered["process_result"]
            test_count = _parse_unittest_log(log_payload)
            if (
                returncode != 0
                or process_result["successful"] is not True
                or process_result["test_count"] != 1
                or process_result["test_count"] != test_count
                or process_result["failure_count"] != 0
                or process_result["error_count"] != 0
                or process_result["skipped_count"] != 0
            ):
                raise OfflineEvidenceError(f"formal parent probe failed: {probe_id}")
            _revalidate_directory_path(
                raw_repository,
                repository_fd,
                "repository root",
            )
            _revalidate_private_snapshot(snapshot)
            _revalidate_live_snapshot_inputs(repository_fd, snapshot)
            revalidate_execution_environment()
            _write_reserved_bytes(
                log_reservations[probe_id],
                log_payload,
                f"formal parent probe log {probe_id}",
            )
            parent_probe_records.append(
                {
                    "schema_version": PARENT_PROBE_RECORD_SCHEMA_VERSION,
                    "probe_id": probe_id,
                    "covered_test_id": spec["covered_test_id"],
                    "source_path": spec["source_path"],
                    "source_sha256": source_sha256,
                    "command_id": command_id,
                    "command": normalized_command,
                    "command_sha256": _identity_sha256(normalized_command),
                    "formal_closure_sha256": brokered["worker_launch"][
                        "formal_closure_sha256"
                    ],
                    "exit_code": returncode,
                    "test_count": test_count,
                    "status": "passed",
                    "machine_result": _parent_probe_machine_result(
                        process_result
                    ),
                    "raw_result_sha256": hashlib.sha256(stdout).hexdigest(),
                    "worker_launch": brokered["worker_launch"],
                    "broker_transcript": brokered["broker_transcript"],
                    "scratch": brokered["worker_scratch"],
                    "worker_denial_probe_scratch": brokered[
                        "worker_denial_probe_scratch"
                    ],
                    "evidence_path": f"logs/{probe_id}.log",
                    "evidence_sha256": hashlib.sha256(log_payload).hexdigest(),
                }
            )

        for name, command_id, normalized_command, start_directory in commands:
            scratch = _create_component_scratch(name)
            denial_probe: _ComponentScratch | None = None
            held_profile: _HeldFile | None = None
            try:
                denial_probe = _create_denial_probe(name)
                child_profile = _child_sandbox_profile(
                    snapshot.path,
                    scratch.path,
                    closure,
                )
                held_profile = _stage_child_sandbox_profile(
                    scratch,
                    child_profile,
                )
                child_sandbox = _child_sandbox_binding(
                    profile=child_profile,
                    snapshot=snapshot,
                    scratch=scratch,
                    denial_probe=denial_probe,
                    closure=closure,
                )
                sandbox_context = _component_sandbox_context(
                    child_sandbox,
                    denial_probe,
                )
                actual_command = [
                    str(NETWORK_SANDBOX_PATH),
                    "-f",
                    _held_sandbox_profile_argument(held_profile),
                    str(python),
                    "-I",
                    "-S",
                    "-B",
                    "-c",
                    _UNITTEST_BOOTSTRAP,
                    encoded_module_closure,
                    name,
                    start_directory,
                    encoded_python_identity,
                    encoded_test_scope,
                    _encode_expected_identity(_component_test_selection(name)),
                    _encode_expected_identity(_component_test_baseline(name)),
                    _encode_expected_identity(sandbox_context),
                ]
                environment = {
                    "PATH": os.pathsep.join(str(path) for path in path_directories),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "TMPDIR": str(scratch.path),
                    "TMP": str(scratch.path),
                    "TEMP": str(scratch.path),
                    "HOME": str(scratch.path),
                    "LC_ALL": "C.UTF-8",
                    "LANG": "C.UTF-8",
                }
                environment[_INHERITED_COMPONENT_SANDBOX_ENV] = child_sandbox[
                    "identity_sha256"
                ]
                _revalidate_child_directory(
                    evidence_fd,
                    "logs",
                    logs_fd,
                    "test evidence logs directory",
                )
                _validate_logs_fd(
                    logs_fd,
                    expected_names=_expected_test_log_stems(),
                )
                _revalidate_directory_path(
                    raw_repository,
                    repository_fd,
                    "repository root",
                )
                _revalidate_private_snapshot(snapshot)
                _revalidate_live_snapshot_inputs(repository_fd, snapshot)
                _revalidate_component_scratch(scratch)
                revalidate_execution_environment()
                _revalidate_held_sandbox_profile(held_profile, child_profile)
                try:
                    completed_process = _run_test_component_process(
                        actual_command,
                        cwd=None,
                        env=environment,
                        stdin=subprocess.PIPE,
                        input_payload=held_profile.payload,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        timeout=timeout_seconds,
                        check=False,
                        preexec_fn=partial(os.fchdir, snapshot.root_fd),
                        pass_fds=(snapshot.root_fd,),
                    )
                except subprocess.TimeoutExpired as exc:
                    raise OfflineEvidenceError(
                        f"test component timed out: {name}"
                    ) from exc
                except Exception as exc:
                    raise OfflineEvidenceError(
                        f"test component could not be started: {name}"
                    ) from exc
                _revalidate_held_sandbox_profile(held_profile, child_profile)
                _revalidate_directory_path(
                    raw_repository,
                    repository_fd,
                    "repository root",
                )
                _revalidate_private_snapshot(snapshot)
                _revalidate_live_snapshot_inputs(repository_fd, snapshot)
                _revalidate_component_scratch(scratch)
                revalidate_execution_environment()
                try:
                    stdout = completed_process.stdout
                    returncode = completed_process.returncode
                    observed_process_identity = _validated_process_identity(
                        completed_process.process_identity,
                        f"test component {name}",
                        require_session_leader=True,
                    )
                except Exception as exc:
                    raise OfflineEvidenceError(
                        f"test component returned a malformed result: {name}"
                    ) from exc
                if not isinstance(stdout, bytes) or type(returncode) is not int:
                    raise OfflineEvidenceError(
                        f"test component returned a malformed result: {name}"
                    )
                if returncode != 0:
                    message = _sandboxed_error(stdout)
                    if message is not None:
                        raise OfflineEvidenceError(message)
                    try:
                        log_payload, process_result = _parse_test_process_payload(
                            stdout,
                            runner=runner,
                        )
                    except OfflineEvidenceError:
                        raise OfflineEvidenceError(f"test component failed: {name}")
                else:
                    try:
                        log_payload, process_result = _parse_test_process_payload(
                            stdout,
                            runner=runner,
                        )
                    except OfflineEvidenceError as exc:
                        raise OfflineEvidenceError(
                            f"test component returned an untrusted result: {name}"
                        ) from exc
                if returncode != 0:
                    raise OfflineEvidenceError(f"test component failed: {name}")
                if not _type_sensitive_equal(
                    process_result["process_identity"],
                    observed_process_identity,
                ):
                    raise OfflineEvidenceError(
                        f"test component process identity mismatch: {name}"
                    )
                if (
                    process_result["successful"] is not True
                    or process_result["failure_count"] != 0
                    or process_result["error_count"] != 0
                    or process_result["skipped_count"] != 0
                ):
                    raise OfflineEvidenceError(
                        f"test component machine result is not passing: {name}"
                    )
                if process_result["sandbox_enforcement"][
                    "sandbox_binding_sha256"
                ] != child_sandbox["identity_sha256"]:
                    raise OfflineEvidenceError(
                        f"test component sandbox enforcement is unbound: {name}"
                    )
                test_count = _parse_unittest_log(log_payload)
                if process_result["test_count"] != test_count:
                    raise OfflineEvidenceError(
                        f"test component count differs from its machine result: {name}"
                    )
            finally:
                primary_error = sys.exception()
                cleanup_error: Exception | None = None
                if held_profile is not None:
                    try:
                        _close_held_file(held_profile)
                    except Exception as exc:
                        cleanup_error = _merge_cleanup_error(
                            cleanup_error,
                            exc,
                            label=f"test component held profile {name}",
                        )
                try:
                    denial_probe_receipt, scratch_receipt = (
                        _close_component_scratch_pair(
                            denial_probe,
                            scratch,
                            primary_error=primary_error,
                        )
                    )
                except Exception as exc:
                    cleanup_error = _merge_cleanup_error(
                        cleanup_error,
                        exc,
                        label=f"test component scratch pair {name}",
                    )
                _finish_process_cleanup(
                    cleanup_error,
                    primary_error=primary_error,
                )
            _write_reserved_bytes(
                log_reservations[name],
                log_payload,
                f"test evidence log {name}",
            )
            components.append(
                {
                    "name": name,
                    "command_id": command_id,
                    "command": normalized_command,
                    "command_sha256": _identity_sha256(normalized_command),
                    "exit_code": returncode,
                    "test_count": test_count,
                    "status": "passed",
                    "process_identity": observed_process_identity,
                    "machine_result": _machine_result_from_process_result(
                        process_result
                    ),
                    "child_result_sha256": hashlib.sha256(stdout).hexdigest(),
                    "child_sandbox": child_sandbox,
                    "denial_probe": denial_probe_receipt,
                    "scratch": scratch_receipt,
                    "evidence_path": f"logs/{name}.log",
                    "evidence_sha256": hashlib.sha256(log_payload).hexdigest(),
                    "parent_probes": (
                        parent_probe_records
                        if name == "formal-security-probes"
                        else []
                    ),
                }
            )

        component_set = {
            "schema_version": TEST_COMPONENT_SET_SCHEMA_VERSION,
            "created_at": created_at,
            "runner": runner,
            "components": components,
        }
        component_set_payload = canonical_json_bytes(component_set)
        _revalidate_private_snapshot(snapshot)
        _revalidate_live_snapshot_inputs(repository_fd, snapshot)
        revalidate_execution_environment()
        _write_reserved_bytes(
            component_reservation,
            component_set_payload,
            "test component set",
            max_bytes=_TEST_COMPONENT_SET_MAX_BYTES,
        )
        written_component_set_payload = _read_reserved_output_bytes(
            component_reservation,
            "test component set",
            max_bytes=_TEST_COMPONENT_SET_MAX_BYTES,
        )
        if written_component_set_payload != component_set_payload:
            raise OfflineEvidenceError("test component set bytes differ after writing")
        _revalidate_reserved_path(component_reservation, "test component set")
        _revalidate_child_directory(
            evidence_fd,
            "logs",
            logs_fd,
            "test evidence logs directory",
        )
        _validate_logs_fd(logs_fd, expected_names=_expected_test_log_stems())
        held_log_payloads: dict[str, bytes] = {}
        for name, reservation in log_reservations.items():
            _revalidate_reserved_path(reservation, f"test evidence log {name}")
            relative = f"logs/{name}.log"
            held_log_payloads[relative] = _read_open_bytes(
                reservation.descriptor,
                _verify_reserved_output(reservation, f"test evidence log {name}"),
                f"test evidence {relative}",
                max_bytes=16 * 1024 * 1024,
            )

        validated_set, validated_components = _validated_component_set(
            component_reservation.path,
            root,
            repo_root=repository,
            repo_fd=repository_fd,
            component_set_payload=written_component_set_payload,
            held_log_payloads=held_log_payloads,
        )
        receipt = _test_receipt_value(
            component_set=validated_set,
            component_set_sha256=hashlib.sha256(
                written_component_set_payload
            ).hexdigest(),
            components=validated_components,
        )
        receipt_payload = canonical_json_bytes(receipt)
        _revalidate_private_snapshot(snapshot)
        _revalidate_live_snapshot_inputs(repository_fd, snapshot)
        revalidate_execution_environment()
        _write_reserved_bytes(
            receipt_reservation,
            receipt_payload,
            "test receipt",
            max_bytes=_TEST_RECEIPT_MAX_BYTES,
        )
        written_receipt_payload = _read_reserved_output_bytes(
            receipt_reservation,
            "test receipt",
            max_bytes=_TEST_RECEIPT_MAX_BYTES,
        )
        if written_receipt_payload != receipt_payload:
            raise OfflineEvidenceError("test receipt bytes differ after writing")

        expected_evidence_root_state = _state_identity(os.fstat(evidence_fd))
        expected_logs_state = _state_identity(os.fstat(logs_fd))
        _revalidate_directory_path(
            raw_repository,
            repository_fd,
            "repository root",
        )
        _revalidate_private_snapshot(snapshot)
        _revalidate_live_snapshot_inputs(repository_fd, snapshot)
        revalidate_execution_environment()
        closed_ocr_tessdata_snapshot = ocr_tessdata_snapshot
        ocr_tessdata_snapshot = None
        _close_sealed_tessdata_snapshot(closed_ocr_tessdata_snapshot)
        _revalidate_approved_tessdata_input(approved_tessdata_input)
        closed_snapshot = snapshot
        snapshot = None
        _close_private_snapshot(closed_snapshot)
        _revalidate_live_snapshot_inputs(repository_fd, closed_snapshot)
        _revalidate_production_embedding_fixture(production_embedding_fixture)
        if _python_identity(python) != python_identity:
            raise OfflineEvidenceError("Python identity changed during test execution")
        _revalidate_external_tools(external_tool_set.identity)
        _revalidate_runtime_sandbox_closure(
            closure.identity,
            python=python,
            python_identity=python_identity,
            external_tools=external_tool_set,
        )
        closed_approved_tessdata_input = approved_tessdata_input
        approved_tessdata_input = None
        _close_approved_tessdata_input(closed_approved_tessdata_input)
        _revalidate_directory_path(
            raw_repository,
            repository_fd,
            "repository root",
        )
        _revalidate_reserved_test_artifacts(
            root_path=raw_evidence_root,
            root_fd=evidence_fd,
            logs_fd=logs_fd,
            expected_log_stems=_expected_test_log_stems(),
            log_reservations=log_reservations,
            expected_log_payloads=held_log_payloads,
            component_reservation=component_reservation,
            component_payload=component_set_payload,
            receipt_reservation=receipt_reservation,
            receipt_payload=receipt_payload,
            expected_root_state=expected_evidence_root_state,
            expected_logs_state=expected_logs_state,
        )
        receipt["receipt_sha256"] = hashlib.sha256(
            written_receipt_payload
        ).hexdigest()
        run_succeeded = True
        return receipt
    finally:
        primary_error = sys.exception()
        cleanup_error: Exception | None = None
        if component_slot is not None:
            try:
                os.close(component_slot[1])
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="component output slot parent descriptor",
                )
        if receipt_slot is not None:
            try:
                os.close(receipt_slot[1])
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="receipt output slot parent descriptor",
                )
        for reservation in log_reservations.values():
            try:
                _close_reserved_output(reservation, discard=not run_succeeded)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="test log reservation",
                )
        if component_reservation is not None:
            try:
                _close_reserved_output(
                    component_reservation,
                    discard=not run_succeeded,
                )
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="component set reservation",
                )
        if receipt_reservation is not None:
            try:
                _close_reserved_output(
                    receipt_reservation,
                    discard=not run_succeeded,
                )
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="test receipt reservation",
                )
        if logs_fd is not None:
            if not run_succeeded:
                try:
                    _discard_child_directory_if_owned(
                        evidence_fd,
                        "logs",
                        logs_fd,
                    )
                except Exception as exc:
                    cleanup_error = _merge_cleanup_error(
                        cleanup_error,
                        exc,
                        label="test logs directory quarantine",
                    )
            try:
                os.close(logs_fd)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="test logs descriptor",
                )
        if snapshot is not None:
            try:
                _close_private_snapshot(snapshot)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="private snapshot",
                )
        if ocr_tessdata_snapshot is not None:
            try:
                _close_sealed_tessdata_snapshot(ocr_tessdata_snapshot)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="private OCR tessdata snapshot",
                )
        if approved_tessdata_input is not None:
            try:
                _close_approved_tessdata_input(approved_tessdata_input)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="approved OCR tessdata input",
                )
        for label, descriptor in (
            ("test evidence root descriptor", evidence_fd),
            ("repository root descriptor", repository_fd),
        ):
            try:
                os.close(descriptor)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label=label,
                )
        _finish_process_cleanup(cleanup_error, primary_error=primary_error)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    authority_build = subparsers.add_parser(
        "authority-build",
        add_help=False,
        help="build authority through the held-byte formal bootstrap",
    )
    authority_build.add_argument("arguments", nargs=argparse.REMAINDER)
    candidate_build = subparsers.add_parser(
        "candidate-build",
        add_help=False,
        help="build derived candidate data through the held-byte formal bootstrap",
    )
    candidate_build.add_argument("arguments", nargs=argparse.REMAINDER)
    dlp = subparsers.add_parser(
        "dlp",
        add_help=False,
        help="run a DLP action through the held-byte formal bootstrap",
    )
    dlp.add_argument("arguments", nargs=argparse.REMAINDER)
    artifact = subparsers.add_parser(
        "artifact",
        add_help=False,
        help="run an artifact action through the held-byte formal bootstrap",
    )
    artifact.add_argument("arguments", nargs=argparse.REMAINDER)
    handoff = subparsers.add_parser(
        "handoff",
        add_help=False,
        help="run a handoff action through the held-byte formal bootstrap",
    )
    handoff.add_argument("arguments", nargs=argparse.REMAINDER)
    probe = subparsers.add_parser(
        "probe",
        add_help=False,
        help="run a Stop B probe action through the held-byte formal bootstrap",
    )
    probe.add_argument("arguments", nargs=argparse.REMAINDER)
    cloud_gold = subparsers.add_parser(
        "cloud80-gold",
        add_help=False,
        help="run Cloud Gold through the held-byte formal bootstrap",
    )
    cloud_gold.add_argument("arguments", nargs=argparse.REMAINDER)
    cloud_eval = subparsers.add_parser(
        "cloud80-eval",
        add_help=False,
        help="run Cloud80 evaluation through the held-byte formal bootstrap",
    )
    cloud_eval.add_argument("arguments", nargs=argparse.REMAINDER)
    neo4j_import = subparsers.add_parser(
        "neo4j-import-candidate",
        add_help=False,
        help="run the Neo4j candidate importer through the held-byte formal bootstrap",
    )
    neo4j_import.add_argument("arguments", nargs=argparse.REMAINDER)
    disclosure = subparsers.add_parser("disclosure")
    disclosure.add_argument("--repo-root", required=True)
    disclosure.add_argument("--output", required=True)
    disclosure.add_argument("--created-at", required=True)
    validate_disclosure = subparsers.add_parser("validate-disclosure")
    validate_disclosure.add_argument("--repo-root", required=True)
    validate_disclosure.add_argument("--receipt", required=True)
    validate_tests = subparsers.add_parser("validate-tests")
    validate_tests.add_argument("--repo-root", required=True)
    validate_tests.add_argument("--evidence-root", required=True)
    validate_tests.add_argument("--component-set", required=True)
    validate_tests.add_argument("--receipt", required=True)
    runner = subparsers.add_parser("run-tests")
    runner.add_argument("--repo-root", required=True)
    runner.add_argument("--evidence-root", required=True)
    runner.add_argument("--component-set", required=True)
    runner.add_argument("--output", required=True)
    runner.add_argument("--created-at", required=True)
    runner.add_argument("--timeout-seconds", type=float, default=900.0)
    parent_probe = subparsers.add_parser(
        "formal-parent-probe-worker",
        help=argparse.SUPPRESS,
    )
    parent_probe.add_argument("--probe-id", required=True)
    parent_probe.add_argument("--snapshot-identity", required=True)
    parent_probe.add_argument("--python-identity", required=True)
    parent_probe.add_argument("--worker-sandbox-context", required=True)
    parent_probe.add_argument("--broker-request-fd", required=True, type=int)
    parent_probe.add_argument("--broker-response-fd", required=True, type=int)
    parent_probe.add_argument("--broker-session", required=True)
    parent_probe.add_argument(
        "--broker-deadline-monotonic-ns",
        required=True,
        type=int,
    )
    return parser


def _formal_cli_command_from_private_snapshot(
    snapshot: _PrivateSnapshot,
    arguments: Sequence[str],
) -> tuple[list[str], str]:
    if not arguments or arguments[0] != "formal-parent-probe-worker":
        raise OfflineEvidenceError(
            "private formal command only permits the parent probe worker"
        )
    if snapshot.source_is_materialized is not False:
        raise OfflineEvidenceError(
            "private formal command requires a first-generation snapshot"
        )
    _revalidate_private_snapshot(snapshot)
    snapshot_path = _descriptor_directory_path(
        snapshot.root_fd,
        "formal parent probe private snapshot",
    )
    _revalidate_directory_path(
        snapshot_path,
        snapshot.root_fd,
        "formal parent probe private snapshot",
    )
    _reject_repository_import_shadows(
        snapshot.root_fd,
        allow_snapshot_package_anchors=True,
    )
    _require_materialized_snapshot_anchors(snapshot.root_fd)
    closure_manifest = _module_closure_manifest(
        snapshot.root_fd,
        schema_version="cloud-v2-formal-bootstrap-closure-v1",
        field="formal parent probe module",
    )
    source_context = _formal_source_context(
        snapshot.root_fd,
        source_kind="materialized-snapshot",
        closure_manifest=closure_manifest,
    )
    _revalidate_private_snapshot(snapshot)
    _require_materialized_snapshot_anchors(snapshot.root_fd)
    if not _type_sensitive_equal(
        source_context,
        _formal_source_context(
            snapshot.root_fd,
            source_kind="materialized-snapshot",
            closure_manifest=closure_manifest,
        ),
    ):
        raise OfflineEvidenceError("formal private snapshot context changed")
    manifest_payload = canonical_json_bytes(closure_manifest)
    return (
        [
            str(_python_executable()),
            "-I",
            "-S",
            "-B",
            "-c",
            FORMAL_CLI_BOOTSTRAP,
            str(snapshot_path),
            base64.b64encode(manifest_payload).decode("ascii"),
            _encode_expected_identity(source_context),
            *arguments,
        ],
        _module_closure_source_sha256(closure_manifest),
    )


def formal_cli_command(
    repo_root: str | Path,
    arguments: Sequence[str],
) -> list[str]:
    if not arguments:
        raise OfflineEvidenceError("formal command arguments are incomplete")
    if arguments[0] == "formal-parent-probe-worker":
        raise OfflineEvidenceError("formal parent probe worker is private")
    repository = _validated_repository_root(repo_root)
    _root, repository_fd = _open_directory_fd(repository, "repository root")
    try:
        _reject_repository_import_shadows(repository_fd)
        closure_manifest = _module_closure_manifest(
            repository_fd,
            schema_version="cloud-v2-formal-bootstrap-closure-v1",
            field="formal CLI module",
        )
        source_context = _formal_source_context(
            repository_fd,
            source_kind="live-repository",
            closure_manifest=closure_manifest,
        )
        _revalidate_directory_path(repository, repository_fd, "repository root")
        _reject_repository_import_shadows(repository_fd)
        if not _type_sensitive_equal(
            source_context,
            _formal_source_context(
                repository_fd,
                source_kind="live-repository",
                closure_manifest=closure_manifest,
            ),
        ):
            raise OfflineEvidenceError("formal CLI source context changed")
    finally:
        os.close(repository_fd)
    manifest_payload = canonical_json_bytes(closure_manifest)
    return [
        str(_python_executable()),
        "-I",
        "-S",
        "-B",
        "-c",
        FORMAL_CLI_BOOTSTRAP,
        str(repository),
        base64.b64encode(manifest_payload).decode("ascii"),
        _encode_expected_identity(source_context),
        *arguments,
    ]


def run_formal_validation(
    *,
    repo_root: str | Path,
    validation: str,
    receipt_path: str | Path,
    evidence_root: str | Path | None = None,
    component_set_path: str | Path | None = None,
    timeout_seconds: float = _FORMAL_VALIDATION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run a downstream evidence check through the held formal bootstrap."""

    timeout = _require_positive_timeout(timeout_seconds)
    repository: Path | None = None
    receipt: Path | None = None
    repository_fd: int | None = None
    evidence_fd: int | None = None
    logs_fd: int | None = None
    held_files: list[_HeldFile] = []
    held_logs: list[_HeldFile] = []
    component_held: _HeldFile | None = None
    receipt_held: _HeldFile | None = None
    expected_log_stems: tuple[str, ...] = ()
    expected_evidence_root_state: tuple[int, int, int, int, int, int, int] | None = None
    expected_logs_state: tuple[int, int, int, int, int, int, int] | None = None
    raw_evidence: Path | None = None
    approved_tessdata_input: _ApprovedTessdataInput | None = None
    primary_error: BaseException | None = None
    try:
        repository = _absolute_path(repo_root, "formal validation repository")
        receipt = _absolute_path(receipt_path, "formal validation receipt")
        if Path(repo_root).is_symlink():
            raise OfflineEvidenceError(
                "formal validation repository must be a real directory"
            )
        repository, repository_fd = _open_directory_fd(
            repository,
            "formal validation repository",
        )
        if validation == "validate-disclosure":
            if evidence_root is not None or component_set_path is not None:
                raise OfflineEvidenceError(
                    "disclosure formal validation arguments are not exact"
                )
            arguments = [
                "validate-disclosure",
                "--repo-root",
                str(repository),
                "--receipt",
                str(receipt),
            ]
            expected_schema = DISCLOSURE_EVIDENCE_SCHEMA_VERSION
            max_receipt_bytes = _DEFAULT_JSON_MAX_BYTES
            component_set_payload = None
            receipt_held = _hold_file_under_root(
                receipt,
                receipt.parent,
                "formal validation receipt",
                max_bytes=max_receipt_bytes,
            )
            held_files.append(receipt_held)
            tree_roots: Sequence[str] = ()
            exact_files: Sequence[str] = _DISCLOSURE_SNAPSHOT_FILES
        elif validation == "validate-tests":
            if evidence_root is None or component_set_path is None:
                raise OfflineEvidenceError("test formal validation arguments are incomplete")
            raw_evidence = Path(evidence_root)
            if raw_evidence.is_symlink():
                raise OfflineEvidenceError(
                    "formal test evidence root must be a real directory"
                )
            evidence, evidence_fd = _open_directory_fd(
                raw_evidence,
                "formal test evidence root",
            )
            component_set = _absolute_path(
                component_set_path,
                "formal test component set",
            )
            arguments = [
                "validate-tests",
                "--repo-root",
                str(repository),
                "--evidence-root",
                str(evidence),
                "--component-set",
                str(component_set),
                "--receipt",
                str(receipt),
            ]
            expected_schema = TEST_RECEIPT_SCHEMA_VERSION
            max_receipt_bytes = _TEST_RECEIPT_MAX_BYTES
            component_held = _hold_file_under_root(
                component_set,
                evidence,
                "formal test component set",
                max_bytes=_TEST_COMPONENT_SET_MAX_BYTES,
            )
            held_files.append(component_held)
            component_set_payload = component_held.payload
            receipt_held = _hold_file_under_root(
                receipt,
                evidence,
                "formal validation receipt",
                max_bytes=max_receipt_bytes,
            )
            held_files.append(receipt_held)
            _logs_path, logs_fd = _open_directory_fd(
                evidence / "logs",
                "formal test evidence logs directory",
            )
            _revalidate_child_directory(
                evidence_fd,
                "logs",
                logs_fd,
                "test evidence logs directory",
            )
            expected_log_stems = _expected_test_log_stems()
            _validate_logs_fd(
                logs_fd,
                expected_names=expected_log_stems,
                require_sealed=True,
            )
            for stem in expected_log_stems:
                held = _hold_file_under_root(
                    evidence / f"logs/{stem}.log",
                    evidence,
                    f"formal test evidence logs/{stem}.log",
                    max_bytes=16 * 1024 * 1024,
                )
                held_files.append(held)
                held_logs.append(held)
            _validate_logs_fd(
                logs_fd,
                expected_names=expected_log_stems,
                require_sealed=True,
            )
            expected_evidence_root_state = _state_identity(os.fstat(evidence_fd))
            expected_logs_state = _state_identity(os.fstat(logs_fd))
            tree_roots = _TEST_SNAPSHOT_TREE_ROOTS
            exact_files = _TEST_SNAPSHOT_FILES
        else:
            raise OfflineEvidenceError("formal validation action is not allowlisted")

        if receipt_held is None:
            raise OfflineEvidenceError("formal validation receipt binding is unavailable")
        receipt_payload = receipt_held.payload
        receipt_value = dict(
            _strict_json_bytes(receipt_payload, field="formal validation receipt")
        )
        if receipt_payload != canonical_json_bytes(receipt_value):
            raise OfflineEvidenceError("formal validation receipt is not canonical JSON")
        repository_state_before = _snapshot_live_state_identity_from_fd(
            repository_fd,
            tree_roots=tree_roots,
            exact_files=exact_files,
        )
        command = formal_cli_command(repository, arguments)
        environment = {
            "PATH": os.pathsep.join(
                str(path) for path in _EXTERNAL_TOOL_SEARCH_DIRECTORIES
            ),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
        }
        if validation == "validate-tests":
            fixture = _resolve_production_embedding_fixture(required=False)
            if fixture is not None:
                environment.update(fixture.environment())
            approved_tessdata_input = _resolve_approved_tessdata_input(required=True)
            assert approved_tessdata_input is not None
            environment[_OCR_TESSDATA_ENV] = str(approved_tessdata_input.root)
        child_primary_error: BaseException | None = None
        try:
            if approved_tessdata_input is not None:
                _revalidate_approved_tessdata_input(approved_tessdata_input)
            try:
                completed = _run_bounded_new_session_process(
                    command,
                    field=f"formal evidence {validation}",
                    cwd=None,
                    env=environment,
                    timeout=timeout,
                    output_max_bytes=_FORMAL_VALIDATION_OUTPUT_MAX_BYTES,
                )
            except subprocess.TimeoutExpired as exc:
                raise OfflineEvidenceError(
                    f"formal evidence {validation} timed out"
                ) from exc
            except (OSError, ValueError) as exc:
                raise OfflineEvidenceError(
                    f"formal evidence {validation} could not be started"
                ) from exc
        except BaseException:
            child_primary_error = sys.exception()
            raise
        finally:
            child_revalidation_error: Exception | None = None
            if approved_tessdata_input is not None:
                try:
                    _revalidate_approved_tessdata_input(
                        approved_tessdata_input
                    )
                except Exception as exc:
                    child_revalidation_error = exc
            _finish_process_cleanup(
                child_revalidation_error,
                primary_error=child_primary_error,
            )
        if (
        not _type_sensitive_equal(completed.args, command)
        or type(completed.returncode) is not int
        or completed.returncode != 0
        or not isinstance(completed.stdout, bytes)
        or not isinstance(completed.stderr, bytes)
        or completed.stderr
        ):
            raise OfflineEvidenceError(f"formal evidence {validation} failed")
        result = dict(
        _strict_json_bytes(
            completed.stdout,
            field=f"formal evidence {validation} result",
        )
        )
        if completed.stdout != canonical_json_bytes(result):
            raise OfflineEvidenceError(
                f"formal evidence {validation} result is not canonical JSON"
            )
        receipt_sha256 = hashlib.sha256(receipt_payload).hexdigest()
        expected_result = {**receipt_value, "receipt_sha256": receipt_sha256}
        if (
        not _type_sensitive_equal(result, expected_result)
        or result.get("schema_version") != expected_schema
        or result.get("status") != "passed"
        or result.get("ok") is not True
        or result.get("receipt_sha256") != receipt_sha256
        or type(result.get("real_provider_calls")) is not int
        or result.get("real_provider_calls") != 0
        or type(result.get("network_calls")) is not int
        or result.get("network_calls") != 0
        or (
            component_set_payload is not None
            and result.get("component_set_sha256")
            != hashlib.sha256(component_set_payload).hexdigest()
        )
        ):
            raise OfflineEvidenceError(
                f"formal evidence {validation} result does not bind its receipt"
            )

        if validation == "validate-tests":
            if (
                raw_evidence is None
                or evidence_fd is None
                or logs_fd is None
                or component_held is None
                or expected_evidence_root_state is None
                or expected_logs_state is None
            ):
                raise OfflineEvidenceError(
                    "formal test evidence terminal binding is unavailable"
                )
            _revalidate_held_test_artifacts(
                root_path=raw_evidence,
                root_fd=evidence_fd,
                logs_fd=logs_fd,
                expected_log_stems=expected_log_stems,
                component_held=component_held,
                receipt_held=receipt_held,
                log_held=held_logs,
                expected_root_state=expected_evidence_root_state,
                expected_logs_state=expected_logs_state,
            )
        else:
            _revalidate_held_file_bytes(
                receipt_held,
                max_bytes=max_receipt_bytes,
            )

        terminal_command = formal_cli_command(repository, arguments)
        if not _type_sensitive_equal(terminal_command, command):
            raise OfflineEvidenceError(
                f"formal evidence {validation} repository or runtime closure changed"
            )
        repository_state_after = _snapshot_live_state_identity_from_fd(
            repository_fd,
            tree_roots=tree_roots,
            exact_files=exact_files,
        )
        if repository_state_after != repository_state_before:
            raise OfflineEvidenceError(
                f"formal evidence {validation} repository input state changed"
            )
        _revalidate_directory_path(
            repository,
            repository_fd,
            "formal validation repository",
        )

        for held in held_files:
            held_max_bytes = (
                _TEST_COMPONENT_SET_MAX_BYTES
                if held is component_held
                else max_receipt_bytes
                if held is receipt_held
                else 16 * 1024 * 1024
            )
            _revalidate_held_file_bytes(held, max_bytes=held_max_bytes)

        if validation == "validate-tests":
            if (
                _state_identity(os.fstat(evidence_fd))
                != expected_evidence_root_state
                or _state_identity(os.fstat(logs_fd)) != expected_logs_state
            ):
                raise OfflineEvidenceError("test evidence tree state changed")
            _revalidate_child_directory(
                evidence_fd,
                "logs",
                logs_fd,
                "test evidence logs directory",
            )
            _validate_logs_fd(
                logs_fd,
                expected_names=expected_log_stems,
                require_sealed=True,
            )
            _revalidate_directory_path(
                raw_evidence,
                evidence_fd,
                "test evidence root",
            )

        terminal_repository_state = _snapshot_live_state_identity_from_fd(
            repository_fd,
            tree_roots=tree_roots,
            exact_files=exact_files,
        )
        if terminal_repository_state != repository_state_before:
            raise OfflineEvidenceError(
                f"formal evidence {validation} repository input state changed"
            )
        _revalidate_directory_path(
            repository,
            repository_fd,
            "formal validation repository",
        )
        for held in held_files:
            _revalidate_held_file(held)
        return result
    except BaseException:
        primary_error = sys.exception()
        raise
    finally:
        cleanup_error: Exception | None = None
        for held in reversed(held_files):
            try:
                _close_held_file(held)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="formal validation held file",
                )
        if approved_tessdata_input is not None:
            try:
                _close_approved_tessdata_input(approved_tessdata_input)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label="formal validation approved OCR tessdata input",
                )
        for label, descriptor in (
            ("formal validation logs descriptor", logs_fd),
            ("formal validation evidence descriptor", evidence_fd),
            ("formal validation repository descriptor", repository_fd),
        ):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except Exception as exc:
                cleanup_error = _merge_cleanup_error(
                    cleanup_error,
                    exc,
                    label=label,
                )
        _finish_process_cleanup(cleanup_error, primary_error=primary_error)


def main(argv: Sequence[str] | None = None) -> int:
    global _PARENT_BROKER_CLIENT
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except OfflineEvidenceError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    delegated_modules = {
        "authority-build": (
            "deploy.cloud_v2.authority_builder",
            "formal authority builder",
            True,
        ),
        "candidate-build": (
            "deploy.cloud_v2.candidate_builder",
            "formal candidate builder",
            True,
        ),
        "dlp": ("deploy.cloud_v2.dlp", "formal DLP", True),
        "artifact": ("deploy.cloud_v2.artifact_builder", "formal artifact", True),
        "handoff": ("deploy.cloud_v2.stop_b_handoff", "formal handoff", True),
        "probe": ("deploy.cloud_v2.stop_b_probe", "formal Stop B probe", True),
        "cloud80-gold": ("cloud_gold", "formal Cloud Gold", True),
        "cloud80-eval": ("eval_cloud_subset", "formal Cloud80", True),
        "neo4j-import-candidate": (
            "deploy.pipeline.neo4j_import_candidate",
            "formal Neo4j candidate import",
            False,
        ),
    }
    if arguments[:1] and arguments[0] in delegated_modules:
        module_name, label, accepts_arguments = delegated_modules[arguments[0]]
        delegated = sys.modules.get(module_name)
        if not isinstance(delegated, types.ModuleType) or not callable(
            getattr(delegated, "main", None)
        ):
            sys.stderr.write(label + " module is unavailable\n")
            return 2
        if accepts_arguments:
            return int(delegated.main(arguments[1:]))
        if len(arguments) != 1:
            sys.stderr.write(label + " arguments are not permitted\n")
            return 2
        return int(delegated.main())
    args = _parser().parse_args(arguments)
    try:
        python_identity = _python_identity(_python_executable())
        _require_sealed_runtime_environment(python_identity["runtime_environment"])
        if args.command == "formal-parent-probe-worker":
            request_state = os.fstat(args.broker_request_fd)
            response_state = os.fstat(args.broker_response_fd)
            if (
                args.broker_request_fd == args.broker_response_fd
                or args.broker_request_fd <= 2
                or args.broker_response_fd <= 2
                or not stat.S_ISFIFO(request_state.st_mode)
                or not stat.S_ISFIFO(response_state.st_mode)
                or not isinstance(args.broker_session, str)
                or not _SHA256.fullmatch(args.broker_session)
            ):
                raise OfflineEvidenceError("formal parent broker descriptors are invalid")
            sandbox_enforcement = _install_active_component_sandbox_context(
                args.worker_sandbox_context
            )
            worker_scratch = Path(os.environ.get("TMPDIR", ""))
            if (
                not worker_scratch.is_absolute()
                or worker_scratch.is_symlink()
                or not worker_scratch.is_dir()
                or stat.S_IMODE(worker_scratch.stat().st_mode) != 0o700
            ):
                raise OfflineEvidenceError("formal parent worker scratch is invalid")
            _PARENT_BROKER_CLIENT = _ParentBrokerClient(
                request_fd=args.broker_request_fd,
                response_fd=args.broker_response_fd,
                session=args.broker_session,
                probe_id=args.probe_id,
                worker_scratch=worker_scratch,
                deadline_monotonic_ns=args.broker_deadline_monotonic_ns,
            )
            try:
                try:
                    result = _run_formal_parent_probe_worker(
                        probe_id=args.probe_id,
                        expected_snapshot_identity=args.snapshot_identity,
                        expected_python_identity=args.python_identity,
                    )
                except OfflineEvidenceError as exc:
                    traceback_cursor = exc.__traceback__
                    while (
                        traceback_cursor is not None
                        and traceback_cursor.tb_next is not None
                    ):
                        traceback_cursor = traceback_cursor.tb_next
                    location = (
                        "unknown"
                        if traceback_cursor is None
                        else (
                            f"{traceback_cursor.tb_frame.f_code.co_name}:"
                            f"{traceback_cursor.tb_lineno}"
                        )
                    )
                    raise OfflineEvidenceError(
                        f"formal parent probe worker failed at {location}: {exc}"
                    ) from exc
                except Exception as exc:
                    detail = str(exc)
                    if (
                        not detail
                        or len(detail) > 512
                        or _has_control_character(detail)
                    ):
                        detail = "no safe detail"
                    raise OfflineEvidenceError(
                        "formal parent probe worker raised "
                        f"{type(exc).__name__}: {detail}"
                    ) from exc
                if (
                    result["worker_sandbox_enforcement"]["initial"]
                    != sandbox_enforcement
                ):
                    raise OfflineEvidenceError(
                        "formal parent worker initial sandbox proof changed"
                    )
            finally:
                _PARENT_BROKER_CLIENT.close()
                _PARENT_BROKER_CLIENT = None
            sys.stdout.buffer.write(canonical_json_bytes(result))
            return 0 if result["successful"] is True else 1
        if args.command == "disclosure":
            result = build_disclosure_evidence(
                repo_root=args.repo_root,
                output_path=args.output,
                created_at=args.created_at,
            )
        elif args.command == "validate-disclosure":
            result = validate_disclosure_evidence(
                repo_root=args.repo_root,
                receipt_path=args.receipt,
            )
        elif args.command == "validate-tests":
            result = validate_test_evidence(
                repo_root=args.repo_root,
                evidence_root=args.evidence_root,
                component_set_path=args.component_set,
                receipt_path=args.receipt,
            )
        else:
            result = run_offline_tests(
                repo_root=args.repo_root,
                evidence_root=args.evidence_root,
                component_set_path=args.component_set,
                receipt_path=args.output,
                created_at=args.created_at,
                timeout_seconds=args.timeout_seconds,
            )
    except OfflineEvidenceError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
