#!/usr/bin/env python3
"""Build deterministic, separated Phase 1 App and cloud suite candidates."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.stderr.write("formal artifact builder CLI bootstrap context is required\n")
    raise SystemExit(2)

import argparse
import hashlib
import json
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .authority_builder import canonical_json_bytes, _write_json_impl as write_json
from .dlp import (
    DLP_RULESET_VERSION,
    DLP_SCHEMA_VERSION,
    DLPError,
    INVENTORY_SCHEMA_VERSION,
    PHASE1_DLP_RECEIPT_FIELDS,
    REQUIRED_BUILDER_FILES,
    REQUIRED_RUNTIME_FILES,
    RULES,
    UPSTREAM_SOURCE_DLP_SCHEMA_VERSION,
    _open_held_payload,
    _revalidate_held_payload,
    validate_final_suite_dlp_receipt,
    validate_phase1_dlp_receipt,
)
from .offline_evidence import (
    OfflineEvidenceError,
    _require_formal_bootstrap_context,
    _require_isolated_python,
    run_formal_validation,
)
from .source_scope import (
    CANDIDATE_ID,
    EXPECTED_ALLOWLIST_SHA256,
    EXPECTED_SOURCE_COUNT,
    EXPECTED_SOURCE_DLP_RECEIPT_SHA256,
    EXPECTED_SOURCE_MANIFEST_SHA256,
    EXPECTED_STOP_A_RECEIPT_SHA256,
    SCOPE_SCHEMA_VERSION,
    ApprovedSourceScope,
    SourceScopeError,
    sha256_file,
)
from ..rag_store.runtime_sqlite_reader import (
    SQLiteSemanticValidationError,
    inspect_authority_bm25_semantics,
)
from ..rag_store.scoped_graph_contract import (
    ScopedGraphContractError,
    load_scoped_graph_package,
)


APP_PACKAGE_SCHEMA_VERSION = "cloud-v2-app-package-v1"
APP_PACKAGE_RECEIPT_SCHEMA_VERSION = "cloud-v2-app-package-receipt-v1"
SUITE_SCHEMA_VERSION = "cloud-v2-suite-manifest-v1"
SUITE_BUILD_RECEIPT_SCHEMA_VERSION = "cloud-v2-suite-build-receipt-v2"
SBOM_SCHEMA_VERSION = "SPDX-2.3"
BASE_COMMIT = "f09f090d5c7ee6b3b029d66894a9d9c13022f0d3"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

APP_SOURCE_FILES: tuple[tuple[str, str], ...] = (
    ("SKILL.md", "skill-contract"),
    ("references/APP_CONTRACT.md", "app-contract"),
    ("references/HOST_INTEGRATION.md", "host-integration"),
    ("scripts/app_answer.py", "app-runtime"),
    ("scripts/knowledge_service_client.py", "app-runtime"),
    ("tests/test_app_answer.py", "offline-app-test"),
    ("tests/test_knowledge_service_client.py", "offline-app-test"),
)
APP_GENERATED_FILES = (
    "APP_PACKAGE_MANIFEST.json",
    "CODE_MANIFEST.sha256",
)
OPERATOR_SOURCE_FILES = (
    "hybrid-audit-cloud/SKILL.md",
    "hybrid-audit-cloud/client.py",
    "lib/__init__.py",
    "lib/ops_contract.py",
    "maintenance-controller-cloud/SKILL.md",
    "maintenance-controller-cloud/client.py",
    "ops-agent-config/job-allowlist.json",
    "ops-agent-config/ops-agent-config.example.json",
    "ops-agent-config/ops-agent-config.schema.json",
    "ops-agent-config/ops-identity-config.example.json",
    "ops-agent-config/ops-identity-config.schema.json",
    "ops-agent-config/ops-runtime-config.example.json",
    "ops-agent-config/ops-runtime-config.schema.json",
    "ops-agent-config/tool-allowlist.json",
    "quality-dashboard-cloud/SKILL.md",
    "quality-dashboard-cloud/client.py",
    "server/requirements.lock",
)
OPERATOR_PRIVATE_SERVER_SOURCE_FILES = (
    ("deploy/cloud_v2/operator_server_init.py", "server/__init__.py"),
    ("deploy/cloud_v2/identity_policy.py", "server/identity_policy.py"),
    ("deploy/cloud_v2/maintenance_jobs.py", "server/maintenance_jobs.py"),
    ("deploy/cloud_v2/ops_identity_middleware.py", "server/ops_identity_middleware.py"),
    ("deploy/cloud_v2/ops_runtime.py", "server/ops_runtime.py"),
    ("deploy/cloud_v2/ops_server.py", "server/ops_server.py"),
    ("deploy/cloud_v2/ops_service.py", "server/ops_service.py"),
    ("deploy/cloud_v2/ops_wsgi.py", "server/ops_wsgi.py"),
    ("deploy/cloud_v2/release_contract.py", "server/release_contract.py"),
)
RUNTIME_ALLOWLIST = "deploy/cloud_v2/runtime-file-allowlist.json"
BUILDER_ALLOWLIST = "deploy/cloud_v2/builder-file-allowlist.json"
EMBEDDED_RUNTIME_ALLOWLIST = "server-runtime/runtime-file-allowlist.json"
EMBEDDED_BUILDER_ALLOWLIST = "server-runtime/builder-file-allowlist.json"
EMBEDDED_REQUIREMENTS_LOCK = "server-runtime/requirements.lock"
EMBEDDED_RUNTIME_ROOT = "server-runtime/code"
EMBEDDED_DATA_ROOT = "server-runtime/data"
EMBEDDED_EVIDENCE_ROOT = "server-runtime/evidence"
DISCLOSURE_EVIDENCE_PATH = f"{EMBEDDED_EVIDENCE_ROOT}/disclosure-evidence.json"
OFFLINE_TEST_COMPONENT_SET_PATH = (
    f"{EMBEDDED_EVIDENCE_ROOT}/offline-test-component-set.json"
)
OFFLINE_TEST_RECEIPT_PATH = f"{EMBEDDED_EVIDENCE_ROOT}/offline-test-receipt.json"
PRODUCTION_VECTOR_BUILD_CONTRACT_PATH = (
    "server-runtime/production-vector-build-contract.json"
)

EXACT_PHASE_STATE = {
    "stop_a": "approved",
    "stop_b": "pending",
    "stop_c": "pending",
    "stop_d": "pending",
    "real_provider_calls": 0,
    "commit_push_upload_deploy_authorized": False,
    "runtime_activation_authorized": False,
    "product_accepted": False,
}


class ArtifactBuildError(RuntimeError):
    """An artifact input, output, or sealed identity failed closed."""


_FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)
_EXECUTED_ARTIFACT_BUILDER_SOURCE = _open_held_payload(
    Path(__file__),
    "artifact builder source",
    max_bytes=4 * 1024 * 1024,
)
_FORMAL_ARTIFACT_BUILDER_SOURCE_SHA256: str | None = None
_FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_ARTIFACT_BUILDER_ACTION_CLOSURE: tuple[object, ...] | None = None


def _artifact_builder_source_state_identity() -> dict[str, int]:
    state = _EXECUTED_ARTIFACT_BUILDER_SOURCE.file_state
    return {
        "device": state.device,
        "inode": state.inode,
        "mode": state.mode,
        "nlink": state.link_count,
        "size": state.size,
        "mtime_ns": state.mtime_ns,
        "ctime_ns": state.ctime_ns,
    }


def _current_artifact_builder_action_closure() -> tuple[object, ...]:
    return (
        _parser,
        build_app_package,
        verify_app_package,
        build_suite,
        verify_suite,
        _build_app_package_impl,
        _build_suite_with_scope,
        _verify_app_package_impl,
        _verify_suite_impl,
    )


def _install_formal_artifact_builder_bootstrap_context(
    binding: Mapping[str, Any],
) -> None:
    global _FORMAL_ARTIFACT_BUILDER_ACTION_CLOSURE
    global _FORMAL_ARTIFACT_BUILDER_SOURCE_SHA256
    global _FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_IDENTITY

    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except OfflineEvidenceError as exc:
        raise ArtifactBuildError(
            "formal artifact builder CLI bootstrap context is required"
        ) from exc
    required = {*_FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_FIELDS, "sha256"}
    if (
        not isinstance(binding, Mapping)
        or set(binding) != required
        or not isinstance(binding.get("sha256"), str)
        or not SHA256_PATTERN.fullmatch(str(binding["sha256"]))
        or any(
            type(binding.get(field)) is not int or int(binding[field]) < 0
            for field in _FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_FIELDS
        )
        or binding["inode"] == 0
        or binding["nlink"] != 1
        or not stat.S_ISREG(binding["mode"])
    ):
        raise ArtifactBuildError(
            "formal artifact builder CLI source binding is malformed"
        )
    expected_state = {
        field: int(binding[field])
        for field in _FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_FIELDS
    }
    try:
        _revalidate_held_payload(_EXECUTED_ARTIFACT_BUILDER_SOURCE)
    except DLPError as exc:
        raise ArtifactBuildError(
            "formal artifact builder CLI source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_ARTIFACT_BUILDER_SOURCE.payload).hexdigest()
        != binding["sha256"]
        or _artifact_builder_source_state_identity() != expected_state
    ):
        raise ArtifactBuildError(
            "formal artifact builder CLI source differs from held bootstrap bytes"
        )
    _FORMAL_ARTIFACT_BUILDER_SOURCE_SHA256 = str(binding["sha256"])
    _FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_IDENTITY = expected_state
    _FORMAL_ARTIFACT_BUILDER_ACTION_CLOSURE = (
        _current_artifact_builder_action_closure()
    )


def _require_formal_artifact_builder_bootstrap_context() -> tuple[object, ...]:
    source_sha256 = _FORMAL_ARTIFACT_BUILDER_SOURCE_SHA256
    source_state = _FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_IDENTITY
    actions = _FORMAL_ARTIFACT_BUILDER_ACTION_CLOSURE
    if (
        not isinstance(source_sha256, str)
        or not SHA256_PATTERN.fullmatch(source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_FIELDS)
        or any(
            type(source_state.get(field)) is not int or int(source_state[field]) < 0
            for field in _FORMAL_ARTIFACT_BUILDER_SOURCE_STATE_FIELDS
        )
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
        or not isinstance(actions, tuple)
        or len(actions) != 9
    ):
        raise ArtifactBuildError(
            "formal artifact builder CLI bootstrap context is required"
        )
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
        _revalidate_held_payload(_EXECUTED_ARTIFACT_BUILDER_SOURCE)
    except (OfflineEvidenceError, DLPError) as exc:
        raise ArtifactBuildError(
            "formal artifact builder CLI source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_ARTIFACT_BUILDER_SOURCE.payload).hexdigest()
        != source_sha256
        or _artifact_builder_source_state_identity() != dict(source_state)
        or any(
            current is not expected
            for current, expected in zip(
                _current_artifact_builder_action_closure(),
                actions,
                strict=True,
            )
        )
    ):
        raise ArtifactBuildError(
            "formal artifact builder CLI source or action closure changed"
        )
    return actions


def _canonical_relative(raw: str) -> str:
    if not isinstance(raw, str) or not raw or raw.startswith("/"):
        raise ArtifactBuildError("artifact path must be canonical and relative")
    if "\\" in raw or "//" in raw or "\x00" in raw:
        raise ArtifactBuildError("artifact path is not canonical POSIX")
    path = PurePosixPath(raw)
    if (
        path.as_posix() != raw
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ArtifactBuildError("artifact path contains a dot or empty component")
    return path.as_posix()


def _reject_generated_python_cache(relative: str) -> None:
    path = PurePosixPath(relative)
    if "__pycache__" in path.parts or path.suffix == ".pyc":
        raise ArtifactBuildError(f"generated Python cache is forbidden: {relative}")


def _strict_json_bytes(payload: bytes, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ArtifactBuildError(f"duplicate JSON key in {label}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ArtifactBuildError(f"non-finite JSON value in {label}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactBuildError(f"invalid JSON in {label}") from exc
    if not isinstance(value, Mapping):
        raise ArtifactBuildError(f"JSON object required in {label}")
    return value


def _load_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ArtifactBuildError(f"required JSON is unavailable: {path.name}")
    return _strict_json_bytes(path.read_bytes(), path.name)


def _required_file(root: Path, relative: str) -> Path:
    relative = _canonical_relative(relative)
    path = root / relative
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise ArtifactBuildError(f"artifact input escaped its root: {relative}") from exc
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ArtifactBuildError(f"symlink is forbidden: {relative}")
        cursor = cursor.parent
    if not path.is_file() or path.is_symlink():
        raise ArtifactBuildError(f"regular artifact input required: {relative}")
    return path


def _hash_records(records: Iterable[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_json_bytes(list(records))).hexdigest()


def _identity_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _compact_identity_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _required_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactBuildError(f"{label} must be a JSON object")
    return value


def _exact_mapping(
    value: object,
    label: str,
    required_keys: Iterable[str],
) -> Mapping[str, Any]:
    mapping = _required_mapping(value, label)
    if set(mapping) != set(required_keys):
        raise ArtifactBuildError(f"{label} field set is not exact")
    return mapping


def _typed_mapping_equal(value: object, expected: Mapping[str, Any]) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == set(expected)
        and all(
            type(value[key]) is type(expected[key]) and value[key] == expected[key]
            for key in expected
        )
    )


def _exact_records(
    value: object,
    *,
    label: str,
    required_keys: tuple[str, ...] = ("path", "sha256"),
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ArtifactBuildError(f"{label} records are absent")
    records: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != set(required_keys):
            raise ArtifactBuildError(f"{label} record shape is not exact")
        record = {key: raw[key] for key in required_keys}
        record["path"] = _canonical_relative(record["path"])
        digest = record.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ArtifactBuildError(f"{label} record hash is invalid")
        if "role" in record and (
            not isinstance(record["role"], str) or not record["role"]
        ):
            raise ArtifactBuildError(f"{label} record role is invalid")
        records.append(record)
    paths = [str(record["path"]) for record in records]
    if len(paths) != len(set(paths)) or paths != sorted(paths):
        raise ArtifactBuildError(f"{label} records must be unique and sorted")
    return records


def _copy_new(source: Path, target: Path, *, mode: int = 0o640) -> None:
    if not source.is_file() or source.is_symlink():
        raise ArtifactBuildError(f"regular artifact input required: {source.name}")
    _write_new(target, source.read_bytes(), mode=mode)


def _require_detached(receipt_path: Path, suite_root: Path, label: str) -> None:
    try:
        receipt_path.relative_to(suite_root)
    except ValueError:
        return
    raise ArtifactBuildError(f"{label} must be detached from the suite root")


def _write_new(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    if path.exists() or path.is_symlink():
        raise ArtifactBuildError(f"artifact output already exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, mode)
    except FileExistsError:
        raise ArtifactBuildError(f"artifact output already exists: {path.name}") from None
    except OSError:
        raise ArtifactBuildError(f"artifact output could not be created: {path.name}") from None
    try:
        created = os.fstat(descriptor)
        if not stat.S_ISREG(created.st_mode) or created.st_nlink != 1:
            raise ArtifactBuildError(f"artifact output is not private: {path.name}")
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise ArtifactBuildError(f"artifact output write failed: {path.name}")
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        sealed = os.fstat(descriptor)
        observed = bytearray()
        offset = 0
        while offset < len(payload):
            block = os.pread(descriptor, min(1024 * 1024, len(payload) - offset), offset)
            if not block:
                raise ArtifactBuildError(f"artifact output verification failed: {path.name}")
            observed.extend(block)
            offset += len(block)
        verified = os.fstat(descriptor)
        entry = os.stat(path, follow_symlinks=False)
    except ArtifactBuildError:
        raise
    except OSError:
        raise ArtifactBuildError(f"artifact output write failed: {path.name}") from None
    finally:
        os.close(descriptor)
    identity_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if (
        bytes(observed) != payload
        or any(getattr(sealed, field) != getattr(verified, field) for field in identity_fields)
        or any(getattr(verified, field) != getattr(entry, field) for field in identity_fields)
        or not stat.S_ISREG(verified.st_mode)
        or verified.st_nlink != 1
        or verified.st_size != len(payload)
        or stat.S_IMODE(verified.st_mode) != mode
    ):
        raise ArtifactBuildError(f"artifact output verification failed: {path.name}")


def _zip_info(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.flag_bits |= 0x800
    return info


def _app_member(relative: str) -> str:
    return "knowledge-graph-cloud/" + _canonical_relative(relative)


def _expected_app_manifest(source_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": APP_PACKAGE_SCHEMA_VERSION,
        "package_role": "public-app-agent",
        "skill_roots": ["knowledge-graph-cloud"],
        "answer_architecture": "app-host-final",
        "knowledge_service_contract": "ordinary-qa-compat-v1",
        "source_files": [dict(record) for record in source_records],
        "generated_files": list(APP_GENERATED_FILES),
        "forbidden_surfaces": [
            "server-runtime",
            "server-data",
            "operator-companion",
            "ops-tools",
            "provider-secrets",
            "shell",
        ],
    }


def _build_app_package_impl(
    repo_root: str | Path,
    zip_path: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve(strict=True)
    skill_root = repo_root / "skills" / "knowledge-graph-cloud"
    if not skill_root.is_dir() or skill_root.is_symlink():
        raise ArtifactBuildError("knowledge-graph-cloud skill root is unavailable")

    source_records: list[dict[str, Any]] = []
    members: dict[str, tuple[bytes, int]] = {}
    for relative, role in APP_SOURCE_FILES:
        path = _required_file(skill_root, relative)
        payload = path.read_bytes()
        member = _app_member(relative)
        mode = 0o755 if relative.startswith("scripts/") else 0o644
        members[member] = (payload, mode)
        source_records.append(
            {
                "path": relative,
                "role": role,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    app_manifest = _expected_app_manifest(source_records)
    app_manifest_bytes = canonical_json_bytes(app_manifest)
    members[_app_member("APP_PACKAGE_MANIFEST.json")] = (app_manifest_bytes, 0o644)
    manifest_lines = [
        f"{hashlib.sha256(payload).hexdigest()}  {PurePosixPath(member).relative_to('knowledge-graph-cloud').as_posix()}"
        for member, (payload, _mode) in sorted(members.items())
    ]
    code_manifest_bytes = ("\n".join(manifest_lines) + "\n").encode("utf-8")
    members[_app_member("CODE_MANIFEST.sha256")] = (code_manifest_bytes, 0o644)

    zip_path = Path(zip_path).resolve()
    if zip_path.exists() or zip_path.is_symlink():
        raise ArtifactBuildError("App zip output already exists")
    zip_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    with zipfile.ZipFile(
        zip_path,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for member, (payload, mode) in sorted(members.items()):
            archive.writestr(_zip_info(member, mode), payload, compresslevel=9)
    os.chmod(zip_path, 0o640)

    verification = _verify_app_package_impl(zip_path, repo_root=repo_root)
    receipt = {
        "schema_version": APP_PACKAGE_RECEIPT_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "zip_sha256": sha256_file(zip_path),
        "zip_size_bytes": zip_path.stat().st_size,
        "member_count": verification["member_count"],
        "member_set_sha256": verification["member_set_sha256"],
        "skill_roots": ["knowledge-graph-cloud"],
        "server_or_ops_member_count": 0,
    }
    receipt_path = Path(receipt_path).resolve()
    _write_new(receipt_path, canonical_json_bytes(receipt), mode=0o640)
    receipt["receipt_sha256"] = sha256_file(receipt_path)
    return receipt


def build_app_package(
    repo_root: str | Path,
    zip_path: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    actions = _require_formal_artifact_builder_bootstrap_context()
    return actions[5](repo_root, zip_path, receipt_path)


def _zip_mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0o7777


def _verify_app_package_impl(
    zip_path: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    zip_path = Path(zip_path).resolve(strict=True)
    if not zip_path.is_file() or zip_path.is_symlink():
        raise ArtifactBuildError("App package must be a regular zip")
    repository = (
        Path(__file__).resolve(strict=True).parents[2]
        if repo_root is None
        else Path(repo_root).resolve(strict=True)
    )
    skill_root = repository / "skills" / "knowledge-graph-cloud"
    if not skill_root.is_dir() or skill_root.is_symlink():
        raise ArtifactBuildError("App package source checkout is unavailable")
    expected_relatives = {relative for relative, _role in APP_SOURCE_FILES} | set(
        APP_GENERATED_FILES
    )
    expected_members = {_app_member(relative) for relative in expected_relatives}
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ArtifactBuildError("App zip contains duplicate members")
        if set(names) != expected_members:
            raise ArtifactBuildError("App zip member set differs from the exact allowlist")
        payloads: dict[str, bytes] = {}
        for info in infos:
            if info.is_dir() or _canonical_relative(info.filename) != info.filename:
                raise ArtifactBuildError("App zip contains a noncanonical member")
            file_type = (info.external_attr >> 16) & 0o170000
            if file_type not in {0, stat.S_IFREG}:
                raise ArtifactBuildError("App zip contains a non-regular member")
            relative = PurePosixPath(info.filename).relative_to(
                "knowledge-graph-cloud"
            ).as_posix()
            required_mode = 0o755 if relative.startswith("scripts/") else 0o644
            if _zip_mode(info) != required_mode:
                raise ArtifactBuildError("App zip member mode differs from policy")
            payloads[relative] = archive.read(info)

    if sum(relative == "SKILL.md" for relative in payloads) != 1:
        raise ArtifactBuildError("App zip must contain exactly one discoverable skill")
    app_manifest = _strict_json_bytes(
        payloads["APP_PACKAGE_MANIFEST.json"], "APP_PACKAGE_MANIFEST.json"
    )
    expected_source_records = [
        {
            "path": relative,
            "role": role,
            "sha256": hashlib.sha256(payloads[relative]).hexdigest(),
        }
        for relative, role in APP_SOURCE_FILES
    ]
    declared = _exact_records(
        app_manifest.get("source_files"),
        label="App package source",
        required_keys=("path", "role", "sha256"),
    )
    if declared != expected_source_records or app_manifest != _expected_app_manifest(
        expected_source_records
    ):
        raise ArtifactBuildError("App package manifest semantics are not exact")
    for record in declared:
        relative = str(record["path"])
        checkout_payload = _required_file(skill_root, relative).read_bytes()
        if payloads[relative] != checkout_payload:
            raise ArtifactBuildError("App package source differs from the sealed checkout")

    code_records: dict[str, str] = {}
    for line in payloads["CODE_MANIFEST.sha256"].decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ArtifactBuildError("App package code manifest line is invalid")
        digest, relative = match.groups()
        relative = _canonical_relative(relative)
        if relative in code_records:
            raise ArtifactBuildError("App package code manifest path is duplicated")
        code_records[relative] = digest
    expected_code = set(payloads) - {"CODE_MANIFEST.sha256"}
    if set(code_records) != expected_code:
        raise ArtifactBuildError("App package code manifest coverage is not exact")
    for relative, digest in code_records.items():
        if hashlib.sha256(payloads[relative]).hexdigest() != digest:
            raise ArtifactBuildError("App package code manifest hash mismatch")

    forbidden = ("server-runtime", "operator-companion", "/ops/", "provider-secret")
    for relative in payloads:
        if any(marker in relative.lower() for marker in forbidden):
            raise ArtifactBuildError("App package contains a forbidden surface")
    runtime_files = {
        relative for relative, role in APP_SOURCE_FILES if role == "app-runtime"
    }
    for relative in runtime_files:
        text = payloads[relative].decode("utf-8", errors="ignore").lower()
        if any(marker in text for marker in forbidden):
            raise ArtifactBuildError("App package contains a forbidden surface")
    member_records = [
        {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
        for relative, payload in sorted(payloads.items())
    ]
    return {
        "schema_version": "cloud-v2-app-package-verification-v1",
        "status": "passed",
        "ok": True,
        "member_count": len(payloads),
        "member_set_sha256": _hash_records(member_records),
        "zip_sha256": sha256_file(zip_path),
    }


def verify_app_package(
    zip_path: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    actions = _require_formal_artifact_builder_bootstrap_context()
    return actions[7](zip_path, repo_root=repo_root)


def _validated_receipt(
    path: Path,
    *,
    expected_schema: str,
) -> tuple[Mapping[str, Any], str]:
    receipt = _load_json(path)
    if (
        receipt.get("schema_version") != expected_schema
        or receipt.get("status") != "passed"
        or receipt.get("ok") is not True
    ):
        raise ArtifactBuildError(f"upstream receipt did not pass: {path.name}")
    return receipt, sha256_file(path)


def _allowlist_paths(
    repo_root: Path,
    relative: str,
    *,
    expected_schema: str,
    expected_paths: tuple[str, ...],
) -> tuple[str, ...]:
    allowlist = _load_json(_required_file(repo_root, relative))
    if set(allowlist) != {"schema_version", "files"}:
        raise ArtifactBuildError("file allowlist shape is not exact")
    if allowlist.get("schema_version") != expected_schema:
        raise ArtifactBuildError("file allowlist schema mismatch")
    files = allowlist.get("files")
    if not isinstance(files, list) or not files:
        raise ArtifactBuildError("file allowlist is empty")
    paths = [_canonical_relative(item) for item in files]
    if tuple(paths) != expected_paths:
        raise ArtifactBuildError("file allowlist differs from the fixed reviewed closure")
    return tuple(paths)


def _runtime_code_records(repo_root: Path) -> list[dict[str, str]]:
    paths = _allowlist_paths(
        repo_root,
        RUNTIME_ALLOWLIST,
        expected_schema="cloud-v2-runtime-file-allowlist-v1",
        expected_paths=REQUIRED_RUNTIME_FILES,
    )
    records = [
        {"path": relative, "sha256": sha256_file(_required_file(repo_root, relative))}
        for relative in paths
    ]
    return records


def _builder_code_records(repo_root: Path) -> list[dict[str, str]]:
    paths = _allowlist_paths(
        repo_root,
        BUILDER_ALLOWLIST,
        expected_schema="cloud-v2-builder-file-allowlist-v1",
        expected_paths=REQUIRED_BUILDER_FILES,
    )
    return [
        {"path": relative, "sha256": sha256_file(_required_file(repo_root, relative))}
        for relative in paths
    ]


def _copy_runtime_closure(
    repo_root: Path,
    output_root: Path,
    records: list[dict[str, str]],
) -> None:
    for record in records:
        relative = str(record["path"])
        _copy_new(
            _required_file(repo_root, relative),
            output_root / EMBEDDED_RUNTIME_ROOT / relative,
        )
    _copy_new(
        _required_file(repo_root, RUNTIME_ALLOWLIST),
        output_root / EMBEDDED_RUNTIME_ALLOWLIST,
    )
    _builder_code_records(repo_root)
    _copy_new(
        _required_file(repo_root, BUILDER_ALLOWLIST),
        output_root / EMBEDDED_BUILDER_ALLOWLIST,
    )
    _copy_new(
        _required_file(repo_root, "deploy/cloud_v2/requirements.lock"),
        output_root / EMBEDDED_REQUIREMENTS_LOCK,
    )


def _tree_file_set(root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        _reject_generated_python_cache(relative)
        if path.is_symlink():
            raise ArtifactBuildError(f"candidate data contains a symlink: {relative}")
        if path.is_file():
            files.add(_canonical_relative(relative))
    return files


def _receipt_layer_files(receipt: Mapping[str, Any], layer: str) -> dict[str, str]:
    layers = _required_mapping(receipt.get("layers"), "candidate DLP layers")
    inventory = _required_mapping(layers.get(layer), f"candidate DLP {layer} layer")
    expected_keys = {
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
    if layer == "governance":
        expected_keys |= {"accounted_tree_sha256", "excluded_review_evidence"}
    if set(inventory) != expected_keys:
        raise ArtifactBuildError(f"candidate DLP {layer} layer shape is not exact")
    if inventory.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        raise ArtifactBuildError(f"candidate DLP {layer} layer schema mismatch")
    if layer == "governance":
        excluded = _required_mapping(
            inventory.get("excluded_review_evidence"),
            "candidate DLP excluded governance review evidence",
        )
        if (
            not SHA256_PATTERN.fullmatch(
                str(inventory.get("accounted_tree_sha256") or "")
            )
            or excluded.get("excluded_from_candidate") is not True
            or excluded.get("classification")
            != "local-review-evidence-not-build-input"
            or excluded.get("content_dlp_status")
            != "not-asserted-requires-separate-ocr-evidence"
            or not isinstance(excluded.get("relative_root"), str)
            or not SHA256_PATTERN.fullmatch(str(excluded.get("tree_sha256") or ""))
        ):
            raise ArtifactBuildError("candidate DLP governance exclusion is invalid")
    raw_files = inventory.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ArtifactBuildError(f"candidate DLP {layer} inventory is absent")
    files: dict[str, str] = {}
    for raw in raw_files:
        record = _required_mapping(raw, f"candidate DLP {layer} file")
        if set(record) != {"path", "sha256"}:
            raise ArtifactBuildError(f"candidate DLP {layer} file shape is not exact")
        relative = _canonical_relative(record.get("path"))
        digest = record.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ArtifactBuildError(f"candidate DLP {layer} hash is invalid")
        if relative in files:
            raise ArtifactBuildError(f"candidate DLP {layer} path is duplicated")
        files[relative] = digest
    records = [{"path": path, "sha256": digest} for path, digest in files.items()]
    paths = list(files)
    hashes = list(files.values())
    if (
        paths != sorted(paths)
        or inventory.get("file_count") != len(files)
        or not isinstance(inventory.get("total_bytes"), int)
        or inventory.get("total_bytes", -1) < 0
        or inventory.get("path_set_sha256") != _identity_sha256(paths)
        or inventory.get("hash_set_sha256") != _identity_sha256(hashes)
        or inventory.get("tree_sha256") != _identity_sha256(records)
        or inventory.get("finding_count") != len(inventory.get("findings") or [])
    ):
        raise ArtifactBuildError(f"candidate DLP {layer} count mismatch")
    return files


def _inspect_production_data(
    *,
    authority_root: Path,
    derived_root: Path,
    candidate_dlp: Mapping[str, Any],
    exact_derived_tree: bool,
) -> dict[str, Any]:
    authority_manifest_path = _required_file(authority_root, "authority-manifest.json")
    authority = _load_json(authority_manifest_path)
    if set(authority) != {
        "schema_version",
        "release_id",
        "status",
        "authority",
        "source_scope",
        "database",
        "build",
        "counts",
        "sources",
    } or authority.get("schema_version") != "cloud-rag-authority-v1":
        raise ArtifactBuildError("authority manifest schema mismatch")
    authority_database = _exact_mapping(
        authority.get("database"),
        "authority database identity",
        {
            "path",
            "sha256",
            "mode",
            "sqlite_user_version",
            "integrity_check",
            "foreign_key_violation_count",
        },
    )
    authority_counts = _exact_mapping(
        authority.get("counts"),
        "authority counts",
        {"documents", "chunks", "provenance"},
    )
    authority_owner = _exact_mapping(
        authority.get("authority"),
        "authority owner",
        {"owner", "join_key"},
    )
    authority_build = _exact_mapping(
        authority.get("build"),
        "authority build",
        {
            "extractor_version",
            "chunking_policy",
            "import_run_id",
            "network_calls",
            "old_authority_reused",
            "ocr_runtime",
        },
    )
    expected_source_scope = {
        "schema_version": SCOPE_SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "source_count": EXPECTED_SOURCE_COUNT,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "allowlist_sha256": EXPECTED_ALLOWLIST_SHA256,
        "stop_a_receipt_sha256": EXPECTED_STOP_A_RECEIPT_SHA256,
        "source_dlp_receipt_sha256": EXPECTED_SOURCE_DLP_RECEIPT_SHA256,
        "unchanged_source_count": 28,
        "approved_redacted_source_count": 7,
    }
    database_relative = _canonical_relative(authority_database.get("path"))
    if database_relative != "rag_chunks.db":
        raise ArtifactBuildError("production data file name mismatch")
    authority_db_path = _required_file(authority_root, database_relative)
    if (
        not _typed_mapping_equal(authority.get("source_scope"), expected_source_scope)
        or authority.get("status") != "candidate"
        or any(
            type(authority_counts.get(field)) is not int
            for field in ("documents", "chunks", "provenance")
        )
        or authority_counts.get("documents") != EXPECTED_SOURCE_COUNT
        or authority_counts.get("chunks") != authority_counts.get("provenance")
        or authority_counts.get("chunks", 0) <= 0
        or authority_owner != {"join_key": "chunk_id", "owner": "rag_chunks.db"}
        or type(authority_build.get("network_calls")) is not int
        or authority_build.get("network_calls") != 0
        or authority_build.get("old_authority_reused") is not False
        or not isinstance(authority_build.get("extractor_version"), str)
        or not authority_build.get("extractor_version")
        or not isinstance(authority_build.get("chunking_policy"), str)
        or not authority_build.get("chunking_policy")
        or not isinstance(authority_build.get("import_run_id"), str)
        or not authority_build.get("import_run_id")
        or authority_database.get("integrity_check") != "ok"
        or type(authority_database.get("foreign_key_violation_count")) is not int
        or authority_database.get("foreign_key_violation_count") != 0
        or type(authority_database.get("sqlite_user_version")) is not int
        or authority_database.get("sqlite_user_version") != 1
        or authority_database.get("mode") != "0600"
        or sha256_file(authority_db_path) != authority_database.get("sha256")
        or authority.get("release_id")
        != f"rag-authority:{CANDIDATE_ID}:{str(authority_database.get('sha256'))[:16]}"
    ):
        raise ArtifactBuildError("authority database identity or contract mismatch")

    bm25_manifest_path = _required_file(derived_root, "bm25-manifest.json")
    graph_manifest_path = _required_file(derived_root, "graph/graph-manifest.json")
    bm25 = _load_json(bm25_manifest_path)
    graph = _load_json(graph_manifest_path)

    if set(bm25) != {
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
    }:
        raise ArtifactBuildError("BM25 manifest field set is not exact")

    bm25_index = _exact_mapping(
        bm25.get("index"), "BM25 index identity", {"path", "sha256"}
    )
    bm25_index_relative = _canonical_relative(bm25_index.get("path"))
    if bm25_index_relative != "bm25.sqlite3":
        raise ArtifactBuildError("production data file name mismatch")
    bm25_index_path = _required_file(derived_root, bm25_index_relative)
    graph_data = _exact_mapping(
        graph.get("graph"), "graph data identity", {"path", "sha256"}
    )
    graph_data_relative = _canonical_relative(graph_data.get("path"))
    if graph_data_relative != "scoped-graph.jsonl":
        raise ArtifactBuildError("production data file name mismatch")
    graph_data_path = _required_file(derived_root / "graph", graph_data_relative)

    bm25_source = _exact_mapping(
        bm25.get("source"),
        "BM25 source identity",
        {
            "chunk_count",
            "document_count",
            "text_byte_count",
            "text_codepoint_count",
            "schema_version",
            "fingerprint_algorithm",
            "fingerprint",
        },
    )
    if (
        bm25.get("schema_version") != "cloud-v2-sqlite-fts5-trigram-v1"
        or bm25.get("status") != "candidate"
        or any(
            type(bm25_source.get(field)) is not int
            for field in (
                "chunk_count",
                "document_count",
                "text_byte_count",
                "text_codepoint_count",
            )
        )
        or type(bm25.get("indexed_chunk_count")) is not int
        or type(bm25.get("minimum_effective_query_codepoints")) is not int
        or bm25.get("authority_release_id") != authority.get("release_id")
        or bm25.get("authority_database_sha256") != authority_database.get("sha256")
        or sha256_file(bm25_index_path) != bm25_index.get("sha256")
        or bm25_source.get("chunk_count") != authority_counts.get("chunks")
        or bm25_source.get("document_count") != authority_counts.get("documents")
        or bm25_source.get("schema_version") != "chunks-v1"
        or bm25_source.get("fingerprint_algorithm")
        != "sha256-jsonl-chunk-content-v1"
        or not SHA256_PATTERN.fullmatch(str(bm25_source.get("fingerprint") or ""))
        or bm25.get("tokenizer") != "trigram"
        or bm25.get("minimum_effective_query_codepoints") != 3
        or bm25.get("short_query_fallback")
        != "authority-sqlite-substring-v1"
        or bm25.get("sqlite_backfill_required") is not True
    ):
        raise ArtifactBuildError("BM25 embedded identity or source contract mismatch")

    raw_sources = authority.get("sources")
    if not isinstance(raw_sources, list) or len(raw_sources) != EXPECTED_SOURCE_COUNT:
        raise ArtifactBuildError("authority source records are invalid")
    manifest_sources: dict[str, Mapping[str, Any]] = {}
    for raw_source in raw_sources:
        source = _exact_mapping(
            raw_source,
            "authority source record",
            {
                "relative_path",
                "source_sha256",
                "extracted_text_sha256",
                "chunk_count",
                "page_count",
            },
        )
        relative_path = _canonical_relative(source.get("relative_path"))
        if (
            relative_path in manifest_sources
            or not SHA256_PATTERN.fullmatch(str(source.get("source_sha256") or ""))
            or not SHA256_PATTERN.fullmatch(
                str(source.get("extracted_text_sha256") or "")
            )
            or isinstance(source.get("chunk_count"), bool)
            or not isinstance(source.get("chunk_count"), int)
            or source.get("chunk_count", 0) <= 0
            or isinstance(source.get("page_count"), bool)
            or not isinstance(source.get("page_count"), int)
            or source.get("page_count", 0) <= 0
        ):
            raise ArtifactBuildError("authority source record is invalid")
        manifest_sources[relative_path] = source
    if list(manifest_sources) != sorted(manifest_sources):
        raise ArtifactBuildError("authority source records must be sorted")

    try:
        semantics = inspect_authority_bm25_semantics(
            authority_db_path,
            bm25_index_path,
            expected_source_text_sha256={
                path: str(source["extracted_text_sha256"])
                for path, source in manifest_sources.items()
            },
        )
    except SQLiteSemanticValidationError as exc:
        raise ArtifactBuildError(
            f"production SQLite semantic validation failed: {exc.code}"
        ) from None
    database_sources = {
        str(record.get("doc_name") or ""): record
        for record in semantics.source_records
    }
    if (
        semantics.authority_database_sha256 != authority_database.get("sha256")
        or semantics.bm25_database_sha256 != bm25_index.get("sha256")
        or dict(semantics.source) != dict(bm25_source)
        or semantics.indexed_chunk_count != bm25.get("indexed_chunk_count")
        or len(semantics.provenance_chunk_ids) != authority_counts.get("provenance")
        or semantics.indexed_chunk_count != authority_counts.get("chunks")
        or len(semantics.document_chunk_counts) != authority_counts.get("documents")
        or set(database_sources) != set(manifest_sources)
        or any(
            semantics.document_chunk_counts.get(path)
            != manifest_sources[path].get("chunk_count")
            or database_sources[path].get("source_sha256")
            != manifest_sources[path].get("source_sha256")
            or database_sources[path].get("source_page_count")
            != manifest_sources[path].get("page_count")
            or database_sources[path].get("import_run_id")
            != authority_build.get("import_run_id")
            or database_sources[path].get("authority") != "rag_chunks.db"
            for path in manifest_sources
        )
    ):
        raise ArtifactBuildError("authority/BM25 manifest semantics mismatch")

    try:
        graph_package = load_scoped_graph_package(
            graph_manifest_path.resolve(strict=True),
            authority_chunk_documents=semantics.chunk_documents,
        )
    except (OSError, ScopedGraphContractError):
        raise ArtifactBuildError("graph package semantic validation failed") from None
    graph_binding = _exact_mapping(
        graph.get("binding"),
        "graph authority binding",
        {
            "text_edge_count",
            "unresolved_sqlite_chunk_id_count",
            "authoritative_text_stored_in_graph",
        },
    )
    graph_counts = _exact_mapping(
        graph.get("counts"),
        "graph counts",
        {"document_nodes", "chunk_nodes", "entity_nodes", "edges"},
    )
    if (
        graph.get("schema_version") != "cloud-scoped-graph-v1"
        or graph.get("status") != "candidate"
        or graph_package.manifest_sha256 != sha256_file(graph_manifest_path)
        or graph_package.graph_sha256 != graph_data.get("sha256")
        or graph_package.authority_release_id != authority.get("release_id")
        or graph.get("authority_database_sha256") != authority_database.get("sha256")
        or sha256_file(graph_data_path) != graph_data.get("sha256")
        or graph_binding.get("unresolved_sqlite_chunk_id_count") != 0
        or graph_binding.get("authoritative_text_stored_in_graph") is not False
        or graph_counts.get("chunk_nodes") != authority_counts.get("chunks")
        or graph_counts.get("document_nodes") != authority_counts.get("documents")
    ):
        raise ArtifactBuildError("graph embedded identity or authority binding mismatch")

    data_inputs: list[tuple[str, str, Path]] = [
        ("authority/authority-manifest.json", "authority-manifest", authority_manifest_path),
        (f"authority/{database_relative}", "authority-sqlite", authority_db_path),
        ("derived/bm25-manifest.json", "bm25-manifest", bm25_manifest_path),
        (f"derived/{bm25_index_relative}", "bm25-index", bm25_index_path),
        ("derived/graph/graph-manifest.json", "graph-manifest", graph_manifest_path),
        (f"derived/graph/{graph_data_relative}", "graph-data", graph_data_path),
    ]
    data_inputs.sort(key=lambda item: item[0])

    expected_authority_files = {
        relative.removeprefix("authority/"): sha256_file(path)
        for relative, _role, path in data_inputs
        if relative.startswith("authority/")
    }
    expected_derived_files = {
        relative.removeprefix("derived/"): sha256_file(path)
        for relative, _role, path in data_inputs
        if relative.startswith("derived/")
    }
    if _tree_file_set(authority_root) != set(expected_authority_files):
        raise ArtifactBuildError("authority root file set is not exact")
    if exact_derived_tree and _tree_file_set(derived_root) != set(expected_derived_files):
        raise ArtifactBuildError("derived root file set is not exact")
    if _receipt_layer_files(candidate_dlp, "authority") != expected_authority_files:
        raise ArtifactBuildError("candidate DLP authority layer identity mismatch")
    reviewed_derived_files = _receipt_layer_files(candidate_dlp, "derived")
    if any(
        reviewed_derived_files.get(relative) != digest
        for relative, digest in expected_derived_files.items()
    ):
        raise ArtifactBuildError("candidate DLP production-derived identity mismatch")

    records = [
        {"path": relative, "role": role, "sha256": sha256_file(path)}
        for relative, role, path in data_inputs
    ]
    return {
        "authority": authority,
        "authority_manifest_sha256": sha256_file(authority_manifest_path),
        "authority_database_relative": database_relative,
        "bm25": bm25,
        "bm25_manifest_sha256": sha256_file(bm25_manifest_path),
        "bm25_index_relative": bm25_index_relative,
        "graph": graph,
        "graph_manifest_sha256": sha256_file(graph_manifest_path),
        "graph_data_relative": graph_data_relative,
        "inputs": data_inputs,
        "records": records,
        "file_set_sha256": _hash_records(records),
    }


def _inspect_candidate_data(
    *,
    authority_root: Path,
    derived_root: Path,
    output_root: Path | None,
    candidate_dlp: Mapping[str, Any],
) -> dict[str, Any]:
    production = _inspect_production_data(
        authority_root=authority_root,
        derived_root=derived_root,
        candidate_dlp=candidate_dlp,
        exact_derived_tree=False,
    )
    authority = production["authority"]
    bm25 = production["bm25"]
    graph = production["graph"]
    authority_counts = _required_mapping(authority.get("counts"), "authority counts")
    graph_counts = _required_mapping(graph.get("counts"), "graph counts")

    derived_manifest_path = _required_file(
        derived_root, "derived-candidate-manifest.json"
    )
    fake_embedding_path = _required_file(derived_root, "fake-embedding-manifest.json")
    derived = _load_json(derived_manifest_path)
    fake_embedding = _load_json(fake_embedding_path)
    vector_release_root = derived_root / "local-vector" / "candidate"
    if not vector_release_root.is_dir() or vector_release_root.is_symlink():
        raise ArtifactBuildError("local-vector candidate root is unavailable")
    vector_release_dirs = [
        path
        for path in vector_release_root.iterdir()
        if path.is_dir() and not path.is_symlink()
    ]
    if len(vector_release_dirs) != 1:
        raise ArtifactBuildError("derived candidate must contain one local-vector release")
    vector_release = vector_release_dirs[0]
    vector_manifest_path = _required_file(vector_release, "local_vector_manifest.json")
    local_vector = _load_json(vector_manifest_path)
    vector_identity = _required_mapping(
        local_vector.get("identity"), "local-vector identity"
    )
    vector_indexes = _required_mapping(
        local_vector.get("indexes"), "local-vector indexes"
    )
    if (
        local_vector.get("manifest_schema_version") != "kg-local-vector-manifest-v2"
        or set(vector_indexes) != {"chunk", "entity"}
    ):
        raise ArtifactBuildError("local-vector manifest schema or index set mismatch")
    vector_files: list[tuple[str, Path, str]] = []
    for role in ("chunk", "entity"):
        index = _required_mapping(vector_indexes.get(role), f"local-vector {role} index")
        relative = _canonical_relative(index.get("file"))
        path = _required_file(vector_release, relative)
        if (
            sha256_file(path) != index.get("index_sha256")
            or index.get("object_count") != len(index.get("objects") or [])
        ):
            raise ArtifactBuildError(f"local-vector {role} index identity mismatch")
        vector_files.append((relative, path, f"local-vector-{role}-index"))

    fake_identity = _required_mapping(fake_embedding.get("identity"), "fake embedding identity")
    fake_policy = _required_mapping(fake_embedding.get("policy"), "fake embedding policy")
    if (
        fake_embedding.get("schema_version")
        != "cloud-v2-fake-embedding-manifest-v1"
        or fake_embedding.get("status") != "offline-test-only"
        or fake_embedding.get("network_implementation") is not False
        or fake_embedding.get("real_data_externalized") is not False
        or fake_embedding.get("identity_sha256")
        != _compact_identity_sha256(fake_identity)
        or fake_embedding.get("policy_sha256")
        != _compact_identity_sha256(fake_policy)
        or fake_policy.get("max_retries") != 0
        or fake_policy.get("max_cost_microunits_per_request") != 0
        or fake_policy.get("total_cost_budget_microunits") != 0
    ):
        raise ArtifactBuildError("fake embedding identity or offline policy mismatch")

    authority_manifest_sha256 = production["authority_manifest_sha256"]
    if (
        vector_identity.get("authority_manifest_sha256")
        != authority_manifest_sha256
        or vector_identity.get("embedding_identity_sha256")
        != fake_embedding.get("identity_sha256")
        or vector_identity.get("dimension") != fake_identity.get("dimension")
        or vector_identity.get("data_release_id") != vector_release.name
        or _required_mapping(vector_indexes["chunk"], "chunk index").get("object_count")
        != authority_counts.get("chunks")
        or _required_mapping(vector_indexes["entity"], "entity index").get("object_count")
        != graph_counts.get("entity_nodes")
    ):
        raise ArtifactBuildError("local-vector authority or embedding binding mismatch")

    expected_gates = {
        "sqlite_chunk_backfill_missing": 0,
        "graph_entity_backfill_missing": 0,
        "unknown_vector_id_count": 0,
        "cross_release_id_count": 0,
        "network_call_count": 0,
    }
    derived_local_vector = _required_mapping(
        derived.get("local_vector"), "derived local-vector identity"
    )
    if (
        derived.get("schema_version") != "cloud-v2-derived-candidate-v1"
        or derived.get("status") != "candidate"
        or derived.get("authority_database_sha256")
        != authority["database"]["sha256"]
        or derived.get("bm25_manifest_sha256") != production["bm25_manifest_sha256"]
        or derived.get("graph_manifest_sha256") != production["graph_manifest_sha256"]
        or derived.get("fake_embedding_manifest_sha256")
        != sha256_file(fake_embedding_path)
        or derived.get("embedding_identity_sha256")
        != fake_embedding.get("identity_sha256")
        or derived.get("embedding_policy_sha256")
        != fake_embedding.get("policy_sha256")
        or derived_local_vector.get("manifest_sha256")
        != sha256_file(vector_manifest_path)
        or derived_local_vector.get("data_release_id") != vector_release.name
        or derived.get("gates") != expected_gates
    ):
        raise ArtifactBuildError("derived candidate identity chain mismatch")

    candidate_inputs = list(production["inputs"])
    candidate_inputs.extend(
        (
            (
                "derived/derived-candidate-manifest.json",
                "derived-candidate-manifest",
                derived_manifest_path,
            ),
            (
                "derived/fake-embedding-manifest.json",
                "fake-embedding-manifest",
                fake_embedding_path,
            ),
            (
                f"derived/local-vector/candidate/{vector_release.name}/local_vector_manifest.json",
                "local-vector-manifest",
                vector_manifest_path,
            ),
        )
    )
    candidate_inputs.extend(
        (
            f"derived/local-vector/candidate/{vector_release.name}/{relative}",
            role,
            path,
        )
        for relative, path, role in vector_files
    )
    candidate_inputs.sort(key=lambda item: item[0])
    expected_derived_files = {
        relative.removeprefix("derived/"): sha256_file(path)
        for relative, _role, path in candidate_inputs
        if relative.startswith("derived/")
    }
    if _tree_file_set(derived_root) != set(expected_derived_files):
        raise ArtifactBuildError("derived candidate root file set is not exact")
    if _receipt_layer_files(candidate_dlp, "derived") != expected_derived_files:
        raise ArtifactBuildError("candidate DLP derived layer identity mismatch")

    if output_root is not None:
        for relative, _role, source in production["inputs"]:
            _copy_new(source, output_root / EMBEDDED_DATA_ROOT / relative)
    return {
        **production,
        "offline_fixture_validation": {
            "derived_manifest_sha256": sha256_file(derived_manifest_path),
            "fake_embedding_manifest_sha256": sha256_file(fake_embedding_path),
            "local_vector_manifest_sha256": sha256_file(vector_manifest_path),
            "fake_dimension": fake_identity.get("dimension"),
            "status": "validated-not-packaged",
        },
    }


def _operator_file_sources(
    repo_root: Path,
) -> list[tuple[str, str, Path]]:
    sources = [
        (
            relative,
            f"operator-companion/{relative}",
            _required_file(repo_root / "operator-companion", relative),
        )
        for relative in OPERATOR_SOURCE_FILES
    ]
    sources.extend(
        (
            target_relative,
            source_relative,
            _required_file(repo_root, source_relative),
        )
        for source_relative, target_relative in OPERATOR_PRIVATE_SERVER_SOURCE_FILES
    )
    return sorted(sources, key=lambda item: item[0])


def _operator_checkout_records(repo_root: Path) -> list[dict[str, str]]:
    return [
        {"path": target, "sha256": sha256_file(source)}
        for target, _source_relative, source in _operator_file_sources(repo_root)
    ]


def _operator_source_mapping_records(repo_root: Path) -> list[dict[str, str]]:
    return [
        {
            "package_path": target,
            "sha256": sha256_file(source),
            "source_path": source_relative,
        }
        for target, source_relative, source in _operator_file_sources(repo_root)
    ]


def _exact_operator_source_mappings(
    value: object,
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ArtifactBuildError("operator source-to-package mappings are absent")
    records: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != {
            "package_path",
            "sha256",
            "source_path",
        }:
            raise ArtifactBuildError("operator source-to-package mapping shape is not exact")
        package_path = _canonical_relative(raw["package_path"])
        source_path = _canonical_relative(raw["source_path"])
        digest = raw["sha256"]
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ArtifactBuildError("operator source-to-package mapping hash is invalid")
        records.append(
            {
                "package_path": package_path,
                "sha256": digest,
                "source_path": source_path,
            }
        )
    package_paths = [record["package_path"] for record in records]
    source_paths = [record["source_path"] for record in records]
    if (
        package_paths != sorted(package_paths)
        or len(package_paths) != len(set(package_paths))
        or len(source_paths) != len(set(source_paths))
    ):
        raise ArtifactBuildError(
            "operator source-to-package mappings must be unique and package-sorted"
        )
    return records


def _copy_operator_companion(repo_root: Path, output_root: Path) -> dict[str, Any]:
    records: list[dict[str, str]] = []
    for relative, _source_relative, source in _operator_file_sources(repo_root):
        payload = source.read_bytes()
        target = output_root / "operator-companion" / relative
        _write_new(target, payload, mode=0o644)
        records.append({"path": relative, "sha256": hashlib.sha256(payload).hexdigest()})
    mappings = _operator_source_mapping_records(repo_root)
    manifest = _expected_operator_manifest(records, mappings)
    write_json(output_root / "operator-companion" / "OPERATOR_MANIFEST.json", manifest)
    os.chmod(output_root / "operator-companion" / "OPERATOR_MANIFEST.json", 0o644)
    return manifest


def _expected_operator_manifest(
    records: list[dict[str, str]],
    source_mappings: list[dict[str, str]],
) -> dict[str, Any]:
    lock_records = [
        record for record in records if record.get("path") == "server/requirements.lock"
    ]
    if len(lock_records) != 1 or not SHA256_PATTERN.fullmatch(
        str(lock_records[0].get("sha256") or "")
    ):
        raise ArtifactBuildError("operator dependency lock record is not exact")
    lock_sha256 = lock_records[0]["sha256"]
    return {
        "schema_version": "cloud-v2-operator-companion-manifest-v1",
        "status": "production-unconfigured-candidate",
        "agent_audience": "ops-admin-agent",
        "tool_roots": [
            "hybrid-audit-cloud",
            "quality-dashboard-cloud",
            "maintenance-controller-cloud",
        ],
        "shared_runtime": "lib",
        "private_server_runtime": "server",
        "private_server_modules": [
            "identity_policy",
            "maintenance_jobs",
            "ops_identity_middleware",
            "ops_runtime",
            "ops_server",
            "ops_service",
            "ops_wsgi",
            "release_contract",
        ],
        "private_server_entrypoint": {
            "entrypoint_id": "ops-admin-agent-wsgi-v1",
            "module": "server.ops_wsgi",
            "wsgi_application": "server.ops_wsgi:application",
            "application_factory": "server.ops_server:create_production_ops_app",
            "startup_command": ["python", "-m", "server.ops_server"],
            "server": "waitress",
            "required_process_role": "ops-admin-agent",
            "required_environment": {
                "KG_PROCESS_ROLE": "ops-admin-agent",
                "KG_OPS_RUNTIME_CONFIG": "deployment-controlled-absolute-path",
                "KG_OPS_RUNTIME_CONFIG_SHA256": (
                    "deployment-control-plane-exact-byte-sha256"
                ),
                "KG_OPS_IDENTITY_CONFIG": "deployment-controlled-absolute-path",
                "KG_OPS_IDENTITY_CONFIG_SHA256": (
                    "deployment-control-plane-exact-byte-sha256"
                ),
                "KG_OPS_IDENTITY_HS256_SECRET": (
                    "secret-manager-base64url-minimum-32-bytes"
                ),
                "KG_OPS_CONFIRMATION_HS256_SECRET": (
                    "independent-secret-manager-base64url-minimum-32-bytes"
                ),
            },
            "forbidden_environment": ["KG_OPS_HANDLER_MODE"],
            "bind_scope": "deployment-configured-loopback-only",
            "route_prefix": "/ops/",
        },
        "production_handler_assembly": {
            "mode": "production-hash-bound",
            "configured_at_build_time": False,
            "config_schema_path": "ops-agent-config/ops-runtime-config.schema.json",
            "unconfigured_template_path": (
                "ops-agent-config/ops-runtime-config.example.json"
            ),
            "identity_config_schema_path": (
                "ops-agent-config/ops-identity-config.schema.json"
            ),
            "identity_config_template_path": (
                "ops-agent-config/ops-identity-config.example.json"
            ),
            "identity_preflight_before_runtime": True,
            "identity_and_confirmation_secrets_independent": True,
            "handler_identity_contract": (
                "verified-identity-and-maintenance-confirmation-plus-json-body-v2"
            ),
            "maintenance_submit_schema": "maintenance-job-submit-v2",
            "maintenance_runner_bridge": "candidate-plan-backends-v1",
            "real_data_access_after_configuration": True,
            "network_calls": 0,
            "maintenance_execution": False,
            "candidate_plan_only": True,
            "active_write": False,
            "release_switch": False,
            "waitress_only": True,
            "legacy_or_fake_handler_mode_forbidden": True,
        },
        "dependency_lock": {
            "path": "server/requirements.lock",
            "sha256": lock_sha256,
            "format": "python-exact-pins-v1",
        },
        "public_app_discoverable": False,
        "source_to_package_mappings": source_mappings,
        "source_to_package_mapping_sha256": _hash_records(source_mappings),
        "files": records,
        "file_set_sha256": _hash_records(records),
    }


def _parse_lock(lock_path: Path) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", value)
        if not match:
            raise ArtifactBuildError("requirements.lock contains an invalid record")
        name, version = match.groups()
        packages.append({"name": name, "version": version})
    if len(packages) != len({item["name"].lower() for item in packages}):
        raise ArtifactBuildError("requirements.lock contains duplicate packages")
    return packages


def _expected_sbom(
    packages: list[dict[str, str]],
    created_at: str,
    runtime_identity_sha256: str,
    builder_allowlist_sha256: str,
    builder_file_set_sha256: str,
) -> dict[str, Any]:
    return {
        "spdxVersion": SBOM_SCHEMA_VERSION,
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "knowledge-qa-cloud-v2-offline-candidate",
        "documentNamespace": (
            "https://spdx.invalid/knowledge-qa-cloud-v2/"
            + runtime_identity_sha256
            + "/"
            + builder_allowlist_sha256
        ),
        "creationInfo": {
            "created": created_at,
            "creators": ["Tool: cloud-v2-artifact-builder"],
        },
        "packages": [
            {
                "SPDXID": f"SPDXRef-Package-{index}",
                "name": item["name"],
                "versionInfo": item["version"],
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
            }
            for index, item in enumerate(packages, start=1)
        ],
        "annotations": [
            {
                "annotationDate": created_at,
                "annotationType": "OTHER",
                "annotator": "Tool: cloud-v2-artifact-builder",
                "comment": (
                    "Exact candidate versions; provider SDK pending Stop B; "
                    f"builder-file-allowlist-sha256={builder_allowlist_sha256}; "
                    f"builder-file-set-sha256={builder_file_set_sha256}."
                ),
            }
        ],
    }


def _expected_app_host_contract() -> dict[str, Any]:
    return {
        "schema_version": "cloud-v2-app-host-model-contract-v1",
        "status": "pending-stop-b",
        "role": "app-host-final-answer",
        "provider": None,
        "model": None,
        "endpoint": None,
        "region": None,
        "training_retention_delete_contract": None,
        "real_data_authorized": False,
    }


def _expected_server_model_set() -> dict[str, Any]:
    return {
        "schema_version": "cloud-v2-server-answer-model-set-v1",
        "status": "pending-stop-b",
        "provider_neutral": True,
        "channel_count": None,
        "ordered_channels": [],
        "strategy": None,
        "winner_policy": None,
        "total_budget_seconds": None,
        "total_cost_budget_microunits": None,
        "real_data_authorized": False,
    }


def _expected_rollback(runtime_sha256: str, authority_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": "cloud-v2-rollback-plan-v1",
        "status": "pending-stop-c-and-stop-d",
        "execution_authorized": False,
        "candidate_code_identity_sha256": runtime_sha256,
        "candidate_authority_sha256": authority_sha256,
        "rollback_release_id": None,
        "pre_state_sha256": None,
        "switch_restart_or_traffic_action": None,
    }


def _expected_cleanup() -> dict[str, Any]:
    return {
        "schema_version": "cloud-v2-cleanup-plan-v1",
        "status": "pending-stop-d",
        "execution_authorized": False,
        "exact_targets": [],
        "glob_targets_allowed": False,
        "shared_root_targets_allowed": False,
    }


def _expected_data_manifest(
    data: Mapping[str, Any],
    candidate_dlp_sha256: str,
    production_vector_build_contract_sha256: str,
) -> dict[str, Any]:
    authority = data["authority"]
    bm25 = data["bm25"]
    graph = data["graph"]
    return {
        "schema_version": "cloud-v2-data-release-manifest-v1",
        "status": "offline-handoff-data-no-production-vector",
        "release_id": authority["release_id"],
        "source_scope": authority["source_scope"],
        "authority": {
            "manifest_path": "authority/authority-manifest.json",
            "manifest_sha256": data["authority_manifest_sha256"],
            "database_path": f"authority/{data['authority_database_relative']}",
            "database_sha256": authority["database"]["sha256"],
            "document_count": authority["counts"]["documents"],
            "chunk_count": authority["counts"]["chunks"],
        },
        "derived": {
            "bm25_manifest_path": "derived/bm25-manifest.json",
            "bm25_manifest_sha256": data["bm25_manifest_sha256"],
            "bm25_index_path": f"derived/{data['bm25_index_relative']}",
            "bm25_index_sha256": bm25["index"]["sha256"],
            "graph_manifest_path": "derived/graph/graph-manifest.json",
            "graph_manifest_sha256": data["graph_manifest_sha256"],
            "graph_data_path": f"derived/graph/{data['graph_data_relative']}",
            "graph_data_sha256": graph["graph"]["sha256"],
        },
        "files": data["records"],
        "file_set_sha256": data["file_set_sha256"],
        "phase1_dlp_receipt_sha256": candidate_dlp_sha256,
        "production_vector_build_contract_path": (
            "production-vector-build-contract.json"
        ),
        "production_vector_build_contract_sha256": (
            production_vector_build_contract_sha256
        ),
        "production_vector_packaged": False,
        "fake_fixture_packaged": False,
        "production_vector_build_required_after_stop_b": True,
        "active_switch_authorized": False,
    }


def _expected_embedding_manifest(
    production_vector_build_contract_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": "cloud-v2-embedding-release-manifest-v1",
        "status": "unconfigured-pending-stop-b-production-provider-approval",
        "provider_neutral": True,
        "provider": None,
        "endpoint": None,
        "region": None,
        "model": None,
        "model_version": None,
        "dimension": None,
        "normalization": None,
        "production_vector_build_contract_path": (
            "production-vector-build-contract.json"
        ),
        "production_vector_build_contract_sha256": (
            production_vector_build_contract_sha256
        ),
        "production_vector_packaged": False,
        "fake_fixture_packaged": False,
        "real_data_externalized": False,
        "real_provider_calls_authorized": False,
        "production_build_required": True,
    }


def _expected_local_vector_manifest(
    production_vector_build_contract_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": "cloud-v2-local-vector-release-manifest-v1",
        "status": "production-vector-not-built",
        "engine": "usearch",
        "engine_version": "2.26.2",
        "dtype": "f32",
        "production_manifest_path": None,
        "production_manifest_sha256": None,
        "production_vector_build_contract_path": (
            "production-vector-build-contract.json"
        ),
        "production_vector_build_contract_sha256": (
            production_vector_build_contract_sha256
        ),
        "production_vector_packaged": False,
        "fake_fixture_packaged": False,
        "runtime_read_only": True,
        "network_listener": False,
        "active_data_root": None,
        "owner_group_mode": None,
        "capacity_memory_disk_backup_contract": None,
        "production_dimension_pending_stop_b": True,
        "active_state_schema_version": "kg-local-vector-active-state-v1",
        "active_state_required_for_delete_plan": True,
        "exact_delete_execution_authorized": False,
    }


def _expected_production_builder_command(command: str) -> list[str]:
    prefix = [
        "<absolute-python-executable>",
        "-I",
        "-S",
        "-B",
        "<exact-release-bootstrap-path>",
    ]
    if command == "capture-runtime":
        return [
            *prefix,
            "capture-runtime",
            "--output",
            "<absolute-runtime-lock-path>",
        ]
    suffix = [
        "--runtime-lock",
        "<absolute-runtime-lock-path>",
        command,
        "--config",
        "<absolute-config-path>",
    ]
    if command == "materialize":
        return [
            *prefix,
            *suffix,
            "--output",
            "<absolute-configured-contract-path>",
        ]
    return [
        *prefix,
        *suffix,
        "--contract",
        "<absolute-configured-contract-path>",
    ]


def _expected_production_vector_build_contract(
    data: Mapping[str, Any],
    builder_records: list[dict[str, str]],
    builder_allowlist_sha256: str,
) -> dict[str, Any]:
    builder_hashes = {record["path"]: record["sha256"] for record in builder_records}
    required_contract_paths = {
        "entrypoint": "deploy/pipeline/production_embedding_candidate.py",
        "bootstrap": "deploy/pipeline/production_embedding_bootstrap.py",
        "candidate_config_schema": (
            "deploy/pipeline/production_embedding_config.schema.json"
        ),
        "provider_runtime_schema": "deploy/pipeline/provider_runtime_config.schema.json",
        "production_embedding_runtime_lock_schema": (
            "deploy/pipeline/production_embedding_runtime_lock.schema.json"
        ),
        "stop_b_request_schema": (
            "deploy/cloud_v2/stop-b-external-processing-request.schema.json"
        ),
    }
    if any(path not in builder_hashes for path in required_contract_paths.values()):
        raise ArtifactBuildError("production vector builder contract closure is incomplete")
    authority = data["authority"]
    return {
        "schema_version": "cloud-v2-production-vector-build-contract-v1",
        "status": "unconfigured-pending-stop-b-production-provider-approval",
        "provider_neutral": True,
        "builder": {
            "working_directory": "not-required-isolated-bootstrap",
            "module": "pipeline.production_embedding_candidate",
            "bootstrap_path": f"code/{required_contract_paths['bootstrap']}",
            "bootstrap_sha256": builder_hashes[required_contract_paths["bootstrap"]],
            "source_path": f"code/{required_contract_paths['entrypoint']}",
            "source_sha256": builder_hashes[required_contract_paths["entrypoint"]],
            "runtime_capture_command": _expected_production_builder_command(
                "capture-runtime"
            ),
            "runtime_verify_command": [
                "<absolute-python-executable>",
                "-I",
                "-S",
                "-B",
                "<exact-release-bootstrap-path>",
                "--runtime-lock",
                "<absolute-runtime-lock-path>",
                "verify-runtime",
            ],
            "materialize_command": _expected_production_builder_command("materialize"),
            "validate_command": _expected_production_builder_command("validate"),
            "build_command": _expected_production_builder_command("build"),
            "file_allowlist_path": "builder-file-allowlist.json",
            "file_allowlist_sha256": builder_allowlist_sha256,
            "file_set_sha256": _hash_records(builder_records),
            "files": builder_records,
        },
        "schemas": {
            name: {
                "path": f"code/{path}",
                "sha256": builder_hashes[path],
            }
            for name, path in required_contract_paths.items()
            if name not in {"entrypoint", "bootstrap"}
        },
        "sealed_inputs": {
            "file_set_sha256": data["file_set_sha256"],
            "files": data["records"],
            "authority_manifest_sha256": data["authority_manifest_sha256"],
            "authority_database_sha256": authority["database"]["sha256"],
            "bm25_manifest_sha256": data["bm25_manifest_sha256"],
            "bm25_index_sha256": data["bm25"]["index"]["sha256"],
            "graph_manifest_sha256": data["graph_manifest_sha256"],
            "graph_data_sha256": data["graph"]["graph"]["sha256"],
        },
        "production_embedding_identity": {
            "provider": None,
            "endpoint": None,
            "region": None,
            "model": None,
            "model_version": None,
            "dimension": None,
            "normalization": None,
        },
        "output_contract": {
            "mode": "candidate-only",
            "chunk_and_entity_indexes_required": True,
            "production_vector_packaged": False,
            "fake_fixture_packaged": False,
            "active_write_authorized": False,
            "release_switch_authorized": False,
        },
        "approval_contract": {
            "stop_b_production_provider_approved_required": True,
            "real_provider_calls_authorized": False,
            "production_build_authorized": False,
        },
    }


def _expected_graph_manifest(data: Mapping[str, Any]) -> dict[str, Any]:
    graph = data["graph"]
    return {
        "schema_version": "cloud-v2-graph-release-manifest-v1",
        "status": "offline-candidate",
        "candidate_manifest_path": "data/derived/graph/graph-manifest.json",
        "candidate_manifest_sha256": data["graph_manifest_sha256"],
        "graph_release_id": graph["release_id"],
        "authority_database_sha256": graph["authority_database_sha256"],
        "counts": graph["counts"],
        "unresolved_sqlite_chunk_id_count": graph["binding"][
            "unresolved_sqlite_chunk_id_count"
        ],
        "authoritative_text_stored_in_graph": False,
        "active_graph_write_authorized": False,
    }


def _expected_runtime_manifest(
    records: list[dict[str, Any]],
    runtime_allowlist_sha256: str,
    builder_allowlist_sha256: str,
    builder_file_set_sha256: str,
    requirements_lock_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": "cloud-v2-runtime-code-manifest-v1",
        "status": "offline-candidate-no-image",
        "base_commit": BASE_COMMIT,
        "embedded_root": "code",
        "file_set_sha256": _hash_records(records),
        "files": records,
        "runtime_file_allowlist_path": "runtime-file-allowlist.json",
        "runtime_file_allowlist_sha256": runtime_allowlist_sha256,
        "builder_file_allowlist_path": "builder-file-allowlist.json",
        "builder_file_allowlist_sha256": builder_allowlist_sha256,
        "builder_file_set_sha256": builder_file_set_sha256,
        "requirements_lock_path": "requirements.lock",
        "requirements_lock_sha256": requirements_lock_sha256,
        "image_digest": None,
    }


def _write_server_manifest(root: Path, name: str, value: Mapping[str, Any]) -> Path:
    path = root / "server-runtime" / name
    _write_new(path, canonical_json_bytes(value), mode=0o640)
    return path


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
        raise ArtifactBuildError(
            "approved source scope final revalidation failed"
        ) from failure


def _build_suite_impl(
    *,
    repo_root: str | Path,
    source_root: str | Path,
    governance_root: str | Path,
    authority_root: str | Path,
    derived_root: str | Path,
    app_zip: str | Path,
    app_receipt: str | Path,
    candidate_dlp_receipt: str | Path,
    disclosure_evidence: str | Path,
    offline_test_evidence_root: str | Path,
    offline_test_component_set: str | Path,
    offline_test_receipt: str | Path,
    output_root: str | Path,
    receipt_path: str | Path,
    created_at: str,
    _scope_holder: list[ApprovedSourceScope],
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve(strict=True)
    try:
        disclosure_value = run_formal_validation(
            repo_root=repo_root,
            validation="validate-disclosure",
            receipt_path=disclosure_evidence,
        )
        offline_test_value = run_formal_validation(
            repo_root=repo_root,
            validation="validate-tests",
            evidence_root=offline_test_evidence_root,
            component_set_path=offline_test_component_set,
            receipt_path=offline_test_receipt,
        )
    except (OfflineEvidenceError, OSError, ValueError) as exc:
        raise ArtifactBuildError("offline test or disclosure evidence validation failed") from exc
    disclosure_evidence = Path(disclosure_evidence).resolve(strict=True)
    offline_test_evidence_root = Path(offline_test_evidence_root).resolve(strict=True)
    offline_test_component_set = Path(offline_test_component_set).resolve(strict=True)
    offline_test_receipt = Path(offline_test_receipt).resolve(strict=True)
    authority_root = Path(authority_root).resolve(strict=True)
    derived_root = Path(derived_root).resolve(strict=True)
    app_zip = Path(app_zip).resolve(strict=True)
    app_receipt = Path(app_receipt).resolve(strict=True)
    candidate_dlp_receipt = Path(candidate_dlp_receipt).resolve(strict=True)
    output_root = Path(output_root).resolve()
    receipt_path = Path(receipt_path).resolve()
    if not any(part in {"candidate", "candidates", "suites"} for part in output_root.parts):
        raise ArtifactBuildError("suite output must be under an explicit candidate or suites root")
    if output_root.exists() or output_root.is_symlink():
        raise ArtifactBuildError("suite output already exists")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ArtifactBuildError("suite build receipt already exists")
    _require_detached(receipt_path, output_root, "suite build receipt")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created_at):
        raise ArtifactBuildError("created_at must be an exact UTC RFC3339 second")

    app_verification = _verify_app_package_impl(app_zip, repo_root=repo_root)
    app_receipt_value, app_receipt_sha256 = _validated_receipt(
        app_receipt,
        expected_schema=APP_PACKAGE_RECEIPT_SCHEMA_VERSION,
    )
    if app_receipt_value.get("zip_sha256") != app_verification["zip_sha256"]:
        raise ArtifactBuildError("App package receipt does not bind the current zip")
    try:
        scope = ApprovedSourceScope.load(source_root, governance_root)
        _scope_holder.append(scope)
        candidate_dlp_value = validate_phase1_dlp_receipt(
            receipt=candidate_dlp_receipt,
            scope=scope,
            authority_root=authority_root,
            derived_root=derived_root,
            code_root=repo_root,
        )
    except (DLPError, SourceScopeError, OSError, ValueError) as exc:
        raise ArtifactBuildError("candidate DLP receipt validation failed") from exc
    candidate_dlp_sha256 = sha256_file(candidate_dlp_receipt)

    output_root.mkdir(parents=True, mode=0o750)
    data = _inspect_candidate_data(
        authority_root=authority_root,
        derived_root=derived_root,
        output_root=output_root,
        candidate_dlp=candidate_dlp_value,
    )
    authority = data["authority"]
    bm25 = data["bm25"]
    graph = data["graph"]

    app_target = output_root / "app-upload" / "knowledge-graph-cloud-app-upload.zip"
    _write_new(app_target, app_zip.read_bytes(), mode=0o640)
    _write_new(
        output_root / "server-runtime" / "evidence" / "app-package-receipt.json",
        app_receipt.read_bytes(),
        mode=0o640,
    )
    _write_new(
        output_root / "server-runtime" / "evidence" / "candidate-dlp-receipt.json",
        candidate_dlp_receipt.read_bytes(),
        mode=0o640,
    )
    _copy_new(
        disclosure_evidence,
        output_root / DISCLOSURE_EVIDENCE_PATH,
        mode=0o400,
    )
    _copy_new(
        offline_test_component_set,
        output_root / OFFLINE_TEST_COMPONENT_SET_PATH,
        mode=0o400,
    )
    _copy_new(
        offline_test_receipt,
        output_root / OFFLINE_TEST_RECEIPT_PATH,
        mode=0o400,
    )
    offline_log_records: list[dict[str, str]] = []
    for component in offline_test_value["components"]:
        relative = _canonical_relative(component["evidence_path"])
        source = _required_file(offline_test_evidence_root, relative)
        target_relative = f"{EMBEDDED_EVIDENCE_ROOT}/{relative}"
        _copy_new(source, output_root / target_relative, mode=0o400)
        offline_log_records.append(
            {"path": target_relative, "sha256": sha256_file(source)}
        )
    image_status = (
        "status=pending-stop-c\n"
        "digest=not-created\n"
        "external-write-authorized=false\n"
    ).encode("ascii")
    _write_new(output_root / "server-runtime" / "image-digest.txt", image_status, mode=0o640)

    runtime_records = _runtime_code_records(repo_root)
    runtime_identity_sha256 = _hash_records(runtime_records)
    builder_records = _builder_code_records(repo_root)
    builder_file_set_sha256 = _hash_records(builder_records)
    builder_allowlist_sha256 = sha256_file(
        _required_file(repo_root, BUILDER_ALLOWLIST)
    )
    _copy_runtime_closure(repo_root, output_root, runtime_records)
    production_vector_contract = _expected_production_vector_build_contract(
        data,
        builder_records,
        builder_allowlist_sha256,
    )
    production_vector_contract_path = _write_server_manifest(
        output_root,
        "production-vector-build-contract.json",
        production_vector_contract,
    )
    production_vector_contract_sha256 = sha256_file(production_vector_contract_path)
    data_manifest = _expected_data_manifest(
        data,
        candidate_dlp_sha256,
        production_vector_contract_sha256,
    )
    _write_server_manifest(output_root, "data-release-manifest.json", data_manifest)
    _write_server_manifest(
        output_root,
        "app-host-model-contract.json",
        _expected_app_host_contract(),
    )
    _write_server_manifest(
        output_root,
        "server-answer-model-set-manifest.json",
        _expected_server_model_set(),
    )
    _write_server_manifest(
        output_root,
        "embedding-manifest.json",
        _expected_embedding_manifest(production_vector_contract_sha256),
    )
    _write_server_manifest(
        output_root,
        "local-vector-manifest.json",
        _expected_local_vector_manifest(production_vector_contract_sha256),
    )
    _write_server_manifest(
        output_root,
        "graph-manifest.json",
        _expected_graph_manifest(data),
    )
    _write_server_manifest(
        output_root,
        "ROLLBACK_PLAN.json",
        _expected_rollback(runtime_identity_sha256, authority["database"]["sha256"]),
    )
    _write_server_manifest(
        output_root,
        "CLEANUP_PLAN.json",
        _expected_cleanup(),
    )

    lock_path = _required_file(repo_root, "deploy/cloud_v2/requirements.lock")
    packages = _parse_lock(lock_path)
    sbom = _expected_sbom(
        packages,
        created_at,
        runtime_identity_sha256,
        builder_allowlist_sha256,
        builder_file_set_sha256,
    )
    _write_server_manifest(output_root, "SBOM.spdx.json", sbom)
    _write_server_manifest(
        output_root,
        "runtime-code-manifest.json",
        _expected_runtime_manifest(
            runtime_records,
            sha256_file(_required_file(repo_root, RUNTIME_ALLOWLIST)),
            builder_allowlist_sha256,
            builder_file_set_sha256,
            sha256_file(lock_path),
        ),
    )
    operator_manifest = _copy_operator_companion(repo_root, output_root)

    component_records: list[dict[str, str]] = []
    for path in sorted(
        output_root.rglob("*"),
        key=lambda item: item.relative_to(output_root).as_posix(),
    ):
        if path.is_symlink():
            raise ArtifactBuildError("suite output contains a symlink")
        if path.is_file():
            relative = path.relative_to(output_root).as_posix()
            component_records.append({"path": relative, "sha256": sha256_file(path)})
    component_set_sha256 = _hash_records(component_records)
    suite_release_id = "knowledge-qa-suite:r9-offline:" + component_set_sha256[:16]
    suite_manifest = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "suite_release_id": suite_release_id,
        "status": "offline-provider-candidate",
        "created_at": created_at,
        "base_commit": BASE_COMMIT,
        "components": component_records,
        "component_set_sha256": component_set_sha256,
        "identities": {
            "app_zip_sha256": app_verification["zip_sha256"],
            "authority_manifest_sha256": data["authority_manifest_sha256"],
            "authority_database_sha256": authority["database"]["sha256"],
            "bm25_manifest_sha256": data["bm25_manifest_sha256"],
            "bm25_index_sha256": bm25["index"]["sha256"],
            "graph_candidate_manifest_sha256": data["graph_manifest_sha256"],
            "graph_data_sha256": graph["graph"]["sha256"],
            "runtime_code_file_set_sha256": runtime_identity_sha256,
            "runtime_file_allowlist_sha256": sha256_file(
                output_root / EMBEDDED_RUNTIME_ALLOWLIST
            ),
            "builder_file_allowlist_sha256": sha256_file(
                output_root / EMBEDDED_BUILDER_ALLOWLIST
            ),
            "builder_code_file_set_sha256": builder_file_set_sha256,
            "requirements_lock_sha256": sha256_file(
                output_root / EMBEDDED_REQUIREMENTS_LOCK
            ),
            "data_release_manifest_sha256": sha256_file(
                output_root / "server-runtime" / "data-release-manifest.json"
            ),
            "app_host_contract_sha256": sha256_file(
                output_root / "server-runtime" / "app-host-model-contract.json"
            ),
            "server_model_set_sha256": sha256_file(
                output_root / "server-runtime" / "server-answer-model-set-manifest.json"
            ),
            "embedding_manifest_sha256": sha256_file(
                output_root / "server-runtime" / "embedding-manifest.json"
            ),
            "local_vector_manifest_sha256": sha256_file(
                output_root / "server-runtime" / "local-vector-manifest.json"
            ),
            "production_vector_build_contract_sha256": (
                production_vector_contract_sha256
            ),
            "graph_manifest_sha256": sha256_file(
                output_root / "server-runtime" / "graph-manifest.json"
            ),
            "runtime_code_manifest_sha256": sha256_file(
                output_root / "server-runtime" / "runtime-code-manifest.json"
            ),
            "sbom_sha256": sha256_file(
                output_root / "server-runtime" / "SBOM.spdx.json"
            ),
            "rollback_plan_sha256": sha256_file(
                output_root / "server-runtime" / "ROLLBACK_PLAN.json"
            ),
            "cleanup_plan_sha256": sha256_file(
                output_root / "server-runtime" / "CLEANUP_PLAN.json"
            ),
            "operator_manifest_sha256": sha256_file(
                output_root / "operator-companion" / "OPERATOR_MANIFEST.json"
            ),
            "operator_file_set_sha256": operator_manifest["file_set_sha256"],
            "operator_source_to_package_mapping_sha256": operator_manifest[
                "source_to_package_mapping_sha256"
            ],
        },
        "evidence": {
            "app_package_receipt_path": "server-runtime/evidence/app-package-receipt.json",
            "app_package_receipt_sha256": app_receipt_sha256,
            "candidate_dlp_receipt_path": "server-runtime/evidence/candidate-dlp-receipt.json",
            "candidate_dlp_receipt_sha256": candidate_dlp_sha256,
            "disclosure_evidence_path": DISCLOSURE_EVIDENCE_PATH,
            "disclosure_evidence_sha256": disclosure_value["receipt_sha256"],
            "offline_test_component_set_path": OFFLINE_TEST_COMPONENT_SET_PATH,
            "offline_test_component_set_sha256": sha256_file(
                offline_test_component_set
            ),
            "offline_test_receipt_path": OFFLINE_TEST_RECEIPT_PATH,
            "offline_test_receipt_sha256": offline_test_value["receipt_sha256"],
            "offline_test_log_records": offline_log_records,
            "offline_test_count": offline_test_value["test_count"],
        },
        "phase_state": EXACT_PHASE_STATE,
    }
    suite_manifest_path = output_root / "SUITE_MANIFEST.json"
    _write_new(suite_manifest_path, canonical_json_bytes(suite_manifest), mode=0o640)

    sum_paths = sorted(
        (
            path
            for path in output_root.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        key=lambda item: item.relative_to(output_root).as_posix(),
    )
    sums = "\n".join(
        f"{sha256_file(path)}  {path.relative_to(output_root).as_posix()}"
        for path in sum_paths
    ) + "\n"
    _write_new(output_root / "SHA256SUMS", sums.encode("utf-8"), mode=0o640)
    verification = _verify_suite_structure(output_root, repo_root=repo_root)
    build_receipt = {
        "schema_version": SUITE_BUILD_RECEIPT_SCHEMA_VERSION,
        "status": "pending-final-dlp",
        "ok": False,
        "structural_verification_ok": True,
        "final_dlp_receipt_required": True,
        "final_dlp_verified": False,
        "suite_release_id": suite_release_id,
        "suite_manifest_sha256": sha256_file(suite_manifest_path),
        "sha256sums_sha256": sha256_file(output_root / "SHA256SUMS"),
        "candidate_dlp_receipt_sha256": candidate_dlp_sha256,
        "disclosure_evidence_sha256": disclosure_value["receipt_sha256"],
        "offline_test_receipt_sha256": offline_test_value["receipt_sha256"],
        "offline_test_count": offline_test_value["test_count"],
        "file_count": verification["file_count"],
        "real_provider_calls": 0,
    }
    _finalize_source_scope(_scope_holder.pop())
    _write_new(receipt_path, canonical_json_bytes(build_receipt), mode=0o640)
    result = dict(build_receipt)
    result["receipt_sha256"] = sha256_file(receipt_path)
    return result


def _build_suite_with_scope(
    *,
    repo_root: str | Path,
    source_root: str | Path,
    governance_root: str | Path,
    authority_root: str | Path,
    derived_root: str | Path,
    app_zip: str | Path,
    app_receipt: str | Path,
    candidate_dlp_receipt: str | Path,
    disclosure_evidence: str | Path,
    offline_test_evidence_root: str | Path,
    offline_test_component_set: str | Path,
    offline_test_receipt: str | Path,
    output_root: str | Path,
    receipt_path: str | Path,
    created_at: str,
) -> dict[str, Any]:
    scope_holder: list[ApprovedSourceScope] = []
    try:
        return _build_suite_impl(
            repo_root=repo_root,
            source_root=source_root,
            governance_root=governance_root,
            authority_root=authority_root,
            derived_root=derived_root,
            app_zip=app_zip,
            app_receipt=app_receipt,
            candidate_dlp_receipt=candidate_dlp_receipt,
            disclosure_evidence=disclosure_evidence,
            offline_test_evidence_root=offline_test_evidence_root,
            offline_test_component_set=offline_test_component_set,
            offline_test_receipt=offline_test_receipt,
            output_root=output_root,
            receipt_path=receipt_path,
            created_at=created_at,
            _scope_holder=scope_holder,
        )
    finally:
        if scope_holder:
            _finalize_source_scope(scope_holder.pop())


def build_suite(
    *,
    repo_root: str | Path,
    source_root: str | Path,
    governance_root: str | Path,
    authority_root: str | Path,
    derived_root: str | Path,
    app_zip: str | Path,
    app_receipt: str | Path,
    candidate_dlp_receipt: str | Path,
    disclosure_evidence: str | Path,
    offline_test_evidence_root: str | Path,
    offline_test_component_set: str | Path,
    offline_test_receipt: str | Path,
    output_root: str | Path,
    receipt_path: str | Path,
    created_at: str,
) -> dict[str, Any]:
    actions = _require_formal_artifact_builder_bootstrap_context()
    return actions[6](
        repo_root=repo_root,
        source_root=source_root,
        governance_root=governance_root,
        authority_root=authority_root,
        derived_root=derived_root,
        app_zip=app_zip,
        app_receipt=app_receipt,
        candidate_dlp_receipt=candidate_dlp_receipt,
        disclosure_evidence=disclosure_evidence,
        offline_test_evidence_root=offline_test_evidence_root,
        offline_test_component_set=offline_test_component_set,
        offline_test_receipt=offline_test_receipt,
        output_root=output_root,
        receipt_path=receipt_path,
        created_at=created_at,
    )


def _require_candidate_dlp_shape(
    receipt: Mapping[str, Any], source_scope: Mapping[str, Any]
) -> dict[str, str]:
    scanner_contract = receipt.get("scanner_contract")
    required_canary_rules = sorted(rule_id for rule_id, _pattern in RULES)
    if set(receipt) != PHASE1_DLP_RECEIPT_FIELDS:
        raise ArtifactBuildError("candidate DLP receipt schema is not exact")
    if (
        receipt.get("schema_version") != DLP_SCHEMA_VERSION
        or receipt.get("ruleset_version") != DLP_RULESET_VERSION
        or not SHA256_PATTERN.fullmatch(str(receipt.get("ruleset_sha256") or ""))
        or not SHA256_PATTERN.fullmatch(str(receipt.get("scanner_sha256") or ""))
        or not isinstance(scanner_contract, Mapping)
        or receipt.get("scanner_sha256") != _identity_sha256(scanner_contract)
        or scanner_contract.get("rule_ids") != required_canary_rules
        or scanner_contract.get("network_calls") != 0
        or receipt.get("status") != "passed"
        or receipt.get("ok") is not True
        or receipt.get("source_scope") != source_scope
    ):
        raise ArtifactBuildError("candidate DLP receipt status or scope mismatch")
    upstream = _required_mapping(
        receipt.get("upstream_source_ocr_dlp"), "upstream source DLP binding"
    )
    if (
        set(upstream)
        != {
            "schema_version",
            "receipt_sha256",
            "object_count",
            "coverage_path_set_sha256",
            "coverage_tree_sha256",
            "bindings_sha256",
            "bound_to_exact_source_manifest",
            "ocr_coverage_validated",
        }
        or upstream.get("schema_version") != UPSTREAM_SOURCE_DLP_SCHEMA_VERSION
        or not isinstance(upstream.get("object_count"), int)
        or upstream.get("object_count", -1) < 0
        or any(
            not SHA256_PATTERN.fullmatch(str(upstream.get(key) or ""))
            for key in (
                "receipt_sha256",
                "coverage_path_set_sha256",
                "coverage_tree_sha256",
                "bindings_sha256",
            )
        )
        or upstream.get("bound_to_exact_source_manifest") is not True
        or upstream.get("ocr_coverage_validated") is not True
        or upstream.get("receipt_sha256")
        != source_scope.get("source_dlp_receipt_sha256")
    ):
        raise ArtifactBuildError("candidate DLP upstream source binding mismatch")
    real = _required_mapping(receipt.get("real_candidate"), "candidate DLP result")
    if (
        set(real)
        != {
            "object_count",
            "scanned_bytes",
            "finding_count",
            "findings",
            "object_set_sha256",
        }
        or not isinstance(real.get("object_count"), int)
        or real.get("object_count", -1) < 0
        or not isinstance(real.get("scanned_bytes"), int)
        or real.get("scanned_bytes", -1) < 0
        or real.get("finding_count") != 0
        or real.get("findings") != []
        or not SHA256_PATTERN.fullmatch(str(real.get("object_set_sha256") or ""))
    ):
        raise ArtifactBuildError("candidate DLP receipt contains a finding")
    canary = _required_mapping(receipt.get("positive_canary"), "DLP positive canary")
    detected = canary.get("detected_rule_ids")
    if (
        set(canary)
        != {
            "payload_sha256",
            "rejected_as_expected",
            "required_rule_ids",
            "detected_rule_ids",
            "finding_count",
        }
        or not SHA256_PATTERN.fullmatch(str(canary.get("payload_sha256") or ""))
        or canary.get("rejected_as_expected") is not True
        or canary.get("required_rule_ids") != required_canary_rules
        or detected != required_canary_rules
        or not isinstance(canary.get("finding_count"), int)
        or canary.get("finding_count", 0) < len(required_canary_rules)
    ):
        raise ArtifactBuildError("candidate DLP positive canary did not pass")
    layers = _required_mapping(receipt.get("layers"), "candidate DLP layers")
    if set(layers) != {"source", "governance", "authority", "derived", "implementation"}:
        raise ArtifactBuildError("candidate DLP layer set is not exact")
    for name, raw_layer in layers.items():
        layer = _required_mapping(raw_layer, f"candidate DLP {name} layer")
        if layer.get("finding_count") != 0 or layer.get("findings") != []:
            raise ArtifactBuildError("candidate DLP receipt contains a nested finding")
        _receipt_layer_files(receipt, str(name))
    implementation = _required_mapping(
        receipt.get("implementation_scope"), "candidate DLP implementation scope"
    )
    implementation_layer = _required_mapping(
        layers.get("implementation"), "candidate DLP implementation layer"
    )
    if (
        implementation.get("files") != implementation_layer.get("files")
        or implementation.get("file_count") != implementation_layer.get("file_count")
    ):
        raise ArtifactBuildError("candidate DLP implementation layer binding mismatch")
    return _receipt_layer_files(receipt, "implementation")


def _require_reviewed_checkout_binding(
    repository: Path,
    implementation_files: Mapping[str, str],
    source_paths: Iterable[str],
) -> None:
    for relative in sorted(set(source_paths)):
        path = _required_file(repository, relative)
        digest = sha256_file(path)
        if implementation_files.get(relative) != digest:
            raise ArtifactBuildError(
                "suite source differs from the reviewed DLP implementation inventory"
            )


def _verify_suite_structure(
    output_root: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(output_root).resolve(strict=True)
    repository = (
        Path(__file__).resolve(strict=True).parents[2]
        if repo_root is None
        else Path(repo_root).resolve(strict=True)
    )
    if not root.is_dir() or root.is_symlink():
        raise ArtifactBuildError("suite root must be a real directory")
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        _reject_generated_python_cache(relative)
        if path.is_symlink():
            raise ArtifactBuildError("suite contains a symlink")
    fixed_files = {
        "app-upload/knowledge-graph-cloud-app-upload.zip",
        "server-runtime/image-digest.txt",
        "server-runtime/data-release-manifest.json",
        "server-runtime/app-host-model-contract.json",
        "server-runtime/server-answer-model-set-manifest.json",
        "server-runtime/embedding-manifest.json",
        "server-runtime/local-vector-manifest.json",
        PRODUCTION_VECTOR_BUILD_CONTRACT_PATH,
        "server-runtime/graph-manifest.json",
        "server-runtime/runtime-code-manifest.json",
        "server-runtime/SBOM.spdx.json",
        "server-runtime/ROLLBACK_PLAN.json",
        "server-runtime/CLEANUP_PLAN.json",
        "server-runtime/evidence/app-package-receipt.json",
        "server-runtime/evidence/candidate-dlp-receipt.json",
        DISCLOSURE_EVIDENCE_PATH,
        OFFLINE_TEST_COMPONENT_SET_PATH,
        OFFLINE_TEST_RECEIPT_PATH,
        EMBEDDED_RUNTIME_ALLOWLIST,
        EMBEDDED_BUILDER_ALLOWLIST,
        EMBEDDED_REQUIREMENTS_LOCK,
        "operator-companion/OPERATOR_MANIFEST.json",
        "SUITE_MANIFEST.json",
        "SHA256SUMS",
    }
    discovered = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    try:
        disclosure_value = run_formal_validation(
            repo_root=repository,
            validation="validate-disclosure",
            receipt_path=root / DISCLOSURE_EVIDENCE_PATH,
        )
        offline_test_value = run_formal_validation(
            repo_root=repository,
            validation="validate-tests",
            evidence_root=root / EMBEDDED_EVIDENCE_ROOT,
            component_set_path=root / OFFLINE_TEST_COMPONENT_SET_PATH,
            receipt_path=root / OFFLINE_TEST_RECEIPT_PATH,
        )
    except (OfflineEvidenceError, OSError, ValueError) as exc:
        raise ArtifactBuildError("embedded offline evidence validation failed") from exc
    expected_offline_logs = {
        f"{EMBEDDED_EVIDENCE_ROOT}/{component['evidence_path']}"
        for component in offline_test_value["components"]
    }
    fixed_files |= expected_offline_logs
    if not fixed_files <= discovered:
        raise ArtifactBuildError("suite required file set is incomplete")

    candidate_dlp_path = root / "server-runtime/evidence/candidate-dlp-receipt.json"
    candidate_dlp = _load_json(candidate_dlp_path)
    embedded_authority = _load_json(
        root / EMBEDDED_DATA_ROOT / "authority/authority-manifest.json"
    )
    source_scope = _required_mapping(
        embedded_authority.get("source_scope"), "embedded authority source scope"
    )
    implementation_files = _require_candidate_dlp_shape(candidate_dlp, source_scope)
    reviewed_source_paths = {
        RUNTIME_ALLOWLIST,
        BUILDER_ALLOWLIST,
        "deploy/cloud_v2/requirements.lock",
        *[record["path"] for record in _runtime_code_records(repository)],
        *[
            f"skills/knowledge-graph-cloud/{relative}"
            for relative, _role in APP_SOURCE_FILES
        ],
        *[
            source_relative
            for _target, source_relative, _source in _operator_file_sources(repository)
        ],
    }
    _require_reviewed_checkout_binding(
        repository,
        implementation_files,
        reviewed_source_paths,
    )
    data = _inspect_production_data(
        authority_root=root / EMBEDDED_DATA_ROOT / "authority",
        derived_root=root / EMBEDDED_DATA_ROOT / "derived",
        candidate_dlp=candidate_dlp,
        exact_derived_tree=True,
    )
    candidate_dlp_sha256 = sha256_file(candidate_dlp_path)
    production_vector_contract_path = root / PRODUCTION_VECTOR_BUILD_CONTRACT_PATH
    production_vector_contract_sha256 = sha256_file(production_vector_contract_path)
    data_manifest = _load_json(root / "server-runtime/data-release-manifest.json")
    if data_manifest != _expected_data_manifest(
        data,
        candidate_dlp_sha256,
        production_vector_contract_sha256,
    ):
        raise ArtifactBuildError("data release manifest semantic binding mismatch")
    data_records = _exact_records(
        data_manifest.get("files"),
        label="data release",
        required_keys=("path", "role", "sha256"),
    )
    if data_records != data["records"]:
        raise ArtifactBuildError("data release file records differ from embedded data")

    runtime_manifest = _load_json(root / "server-runtime/runtime-code-manifest.json")
    runtime_records = _exact_records(
        runtime_manifest.get("files"), label="runtime code"
    )
    if runtime_records != _runtime_code_records(repository):
        raise ArtifactBuildError("runtime code differs from the sealed checkout")
    allowlist_path = root / EMBEDDED_RUNTIME_ALLOWLIST
    reviewed_allowlist_path = _required_file(repository, RUNTIME_ALLOWLIST)
    if allowlist_path.read_bytes() != reviewed_allowlist_path.read_bytes():
        raise ArtifactBuildError(
            "runtime allowlist differs from the reviewed DLP checkout"
        )
    allowlist = _load_json(allowlist_path)
    if (
        allowlist.get("schema_version") != "cloud-v2-runtime-file-allowlist-v1"
        or allowlist.get("files") != [record["path"] for record in runtime_records]
    ):
        raise ArtifactBuildError("runtime allowlist differs from embedded runtime files")
    for record in runtime_records:
        embedded_path = _required_file(
            root, f"{EMBEDDED_RUNTIME_ROOT}/{record['path']}"
        )
        if sha256_file(embedded_path) != record["sha256"]:
            raise ArtifactBuildError("runtime embedded file identity mismatch")
    builder_records = _builder_code_records(repository)
    builder_file_set_sha256 = _hash_records(builder_records)
    builder_allowlist_path = root / EMBEDDED_BUILDER_ALLOWLIST
    reviewed_builder_allowlist_path = _required_file(repository, BUILDER_ALLOWLIST)
    if (
        builder_allowlist_path.read_bytes()
        != reviewed_builder_allowlist_path.read_bytes()
    ):
        raise ArtifactBuildError(
            "builder allowlist differs from the reviewed DLP checkout"
        )
    builder_allowlist = _load_json(builder_allowlist_path)
    if (
        builder_allowlist.get("schema_version")
        != "cloud-v2-builder-file-allowlist-v1"
        or builder_allowlist.get("files")
        != [record["path"] for record in builder_records]
    ):
        raise ArtifactBuildError("builder allowlist differs from embedded builder files")
    runtime_record_map = {
        str(record["path"]): str(record["sha256"]) for record in runtime_records
    }
    if any(
        runtime_record_map.get(record["path"]) != record["sha256"]
        for record in builder_records
    ):
        raise ArtifactBuildError("builder code differs from the embedded runtime closure")
    lock_path = root / EMBEDDED_REQUIREMENTS_LOCK
    reviewed_lock_path = _required_file(
        repository, "deploy/cloud_v2/requirements.lock"
    )
    if lock_path.read_bytes() != reviewed_lock_path.read_bytes():
        raise ArtifactBuildError(
            "requirements lock differs from the reviewed DLP checkout"
        )
    lock_sha256 = sha256_file(lock_path)
    builder_allowlist_sha256 = sha256_file(builder_allowlist_path)
    expected_runtime_manifest = _expected_runtime_manifest(
        runtime_records,
        sha256_file(allowlist_path),
        builder_allowlist_sha256,
        builder_file_set_sha256,
        lock_sha256,
    )
    if runtime_manifest != expected_runtime_manifest:
        raise ArtifactBuildError("runtime code manifest semantic binding mismatch")

    vector_contract = _load_json(production_vector_contract_path)
    expected_vector_contract = _expected_production_vector_build_contract(
        data,
        builder_records,
        builder_allowlist_sha256,
    )
    if vector_contract != expected_vector_contract:
        raise ArtifactBuildError("production vector build contract semantic mismatch")

    operator_manifest = _load_json(root / "operator-companion/OPERATOR_MANIFEST.json")
    operator_records = _exact_records(
        operator_manifest.get("files"), label="operator companion"
    )
    operator_mappings = _exact_operator_source_mappings(
        operator_manifest.get("source_to_package_mappings")
    )
    if operator_records != _operator_checkout_records(repository):
        raise ArtifactBuildError("operator companion differs from the sealed checkout")
    expected_operator_mappings = _operator_source_mapping_records(repository)
    if operator_mappings != expected_operator_mappings:
        raise ArtifactBuildError(
            "operator source-to-package mapping differs from the sealed checkout"
        )
    if operator_manifest != _expected_operator_manifest(
        operator_records,
        expected_operator_mappings,
    ):
        raise ArtifactBuildError("operator manifest semantic binding mismatch")
    for record in operator_records:
        path = _required_file(root, f"operator-companion/{record['path']}")
        if sha256_file(path) != record["sha256"]:
            raise ArtifactBuildError("operator embedded file identity mismatch")

    expected_files = fixed_files | {
        f"{EMBEDDED_DATA_ROOT}/{record['path']}" for record in data_records
    }
    expected_files |= {
        f"{EMBEDDED_RUNTIME_ROOT}/{record['path']}" for record in runtime_records
    }
    expected_files |= {
        f"operator-companion/{record['path']}" for record in operator_records
    }
    if discovered != expected_files:
        raise ArtifactBuildError("suite file set is not exact")

    app_verification = _verify_app_package_impl(
        root / "app-upload" / "knowledge-graph-cloud-app-upload.zip",
        repo_root=repository,
    )
    sums: dict[str, str] = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ArtifactBuildError("SHA256SUMS contains an invalid record")
        digest, relative = match.groups()
        relative = _canonical_relative(relative)
        if relative in sums:
            raise ArtifactBuildError("SHA256SUMS contains a duplicate path")
        sums[relative] = digest
    expected_sums = discovered - {"SHA256SUMS"}
    if set(sums) != expected_sums:
        raise ArtifactBuildError("SHA256SUMS coverage differs from suite files")
    for relative, digest in sums.items():
        if sha256_file(_required_file(root, relative)) != digest:
            raise ArtifactBuildError("suite file hash mismatch")
    suite = _load_json(root / "SUITE_MANIFEST.json")
    if set(suite) != {
        "schema_version",
        "suite_release_id",
        "status",
        "created_at",
        "base_commit",
        "components",
        "component_set_sha256",
        "identities",
        "evidence",
        "phase_state",
    }:
        raise ArtifactBuildError("suite manifest shape is not exact")
    if (
        suite.get("schema_version") != SUITE_SCHEMA_VERSION
        or suite.get("status") != "offline-provider-candidate"
        or suite.get("base_commit") != BASE_COMMIT
        or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            str(suite.get("created_at") or ""),
        )
        or suite.get("phase_state") != EXACT_PHASE_STATE
    ):
        raise ArtifactBuildError("suite schema, status, or phase state mismatch")
    components = _exact_records(suite.get("components"), label="suite component")
    component_map = {record["path"]: record["sha256"] for record in components}
    expected_components = discovered - {"SUITE_MANIFEST.json", "SHA256SUMS"}
    if set(component_map) != expected_components:
        raise ArtifactBuildError("suite component coverage is not exact")
    for relative, digest in component_map.items():
        if not SHA256_PATTERN.fullmatch(digest) or sha256_file(
            _required_file(root, relative)
        ) != digest:
            raise ArtifactBuildError("suite component identity mismatch")
    if suite.get("component_set_sha256") != _hash_records(components):
        raise ArtifactBuildError("suite component-set identity mismatch")
    expected_release_id = (
        "knowledge-qa-suite:r9-offline:" + str(suite["component_set_sha256"])[:16]
    )
    if suite.get("suite_release_id") != expected_release_id:
        raise ArtifactBuildError("suite release identity mismatch")
    evidence = suite.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ArtifactBuildError("suite evidence bindings are absent")
    if set(evidence) != {
        "app_package_receipt_path",
        "app_package_receipt_sha256",
        "candidate_dlp_receipt_path",
        "candidate_dlp_receipt_sha256",
        "disclosure_evidence_path",
        "disclosure_evidence_sha256",
        "offline_test_component_set_path",
        "offline_test_component_set_sha256",
        "offline_test_receipt_path",
        "offline_test_receipt_sha256",
        "offline_test_log_records",
        "offline_test_count",
    }:
        raise ArtifactBuildError("suite evidence binding shape is not exact")
    app_receipt_path = _canonical_relative(
        str(evidence.get("app_package_receipt_path") or "")
    )
    dlp_receipt_path = _canonical_relative(
        str(evidence.get("candidate_dlp_receipt_path") or "")
    )
    if (
        app_receipt_path != "server-runtime/evidence/app-package-receipt.json"
        or dlp_receipt_path != "server-runtime/evidence/candidate-dlp-receipt.json"
    ):
        raise ArtifactBuildError("suite evidence paths are not exact")
    disclosure_path = _canonical_relative(
        str(evidence.get("disclosure_evidence_path") or "")
    )
    component_set_path = _canonical_relative(
        str(evidence.get("offline_test_component_set_path") or "")
    )
    offline_receipt_path = _canonical_relative(
        str(evidence.get("offline_test_receipt_path") or "")
    )
    if (
        disclosure_path != DISCLOSURE_EVIDENCE_PATH
        or component_set_path != OFFLINE_TEST_COMPONENT_SET_PATH
        or offline_receipt_path != OFFLINE_TEST_RECEIPT_PATH
    ):
        raise ArtifactBuildError("suite offline evidence paths are not exact")
    app_receipt_value, app_receipt_sha256 = _validated_receipt(
        _required_file(root, app_receipt_path),
        expected_schema=APP_PACKAGE_RECEIPT_SCHEMA_VERSION,
    )
    dlp_receipt_sha256 = sha256_file(_required_file(root, dlp_receipt_path))
    expected_app_receipt = {
        "schema_version": APP_PACKAGE_RECEIPT_SCHEMA_VERSION,
        "status": "passed",
        "ok": True,
        "zip_sha256": app_verification["zip_sha256"],
        "zip_size_bytes": (
            root / "app-upload/knowledge-graph-cloud-app-upload.zip"
        ).stat().st_size,
        "member_count": app_verification["member_count"],
        "member_set_sha256": app_verification["member_set_sha256"],
        "skill_roots": ["knowledge-graph-cloud"],
        "server_or_ops_member_count": 0,
    }
    if (
        evidence.get("app_package_receipt_sha256") != app_receipt_sha256
        or evidence.get("candidate_dlp_receipt_sha256") != dlp_receipt_sha256
        or app_receipt_value != expected_app_receipt
    ):
        raise ArtifactBuildError("suite evidence receipt binding mismatch")
    expected_log_records = [
        {
            "path": f"{EMBEDDED_EVIDENCE_ROOT}/{component['evidence_path']}",
            "sha256": str(component["evidence_sha256"]),
        }
        for component in offline_test_value["components"]
    ]
    actual_log_records = _exact_records(
        evidence.get("offline_test_log_records"), label="offline test log"
    )
    if (
        evidence.get("disclosure_evidence_sha256")
        != disclosure_value["receipt_sha256"]
        or evidence.get("offline_test_component_set_sha256")
        != sha256_file(_required_file(root, component_set_path))
        or evidence.get("offline_test_receipt_sha256")
        != offline_test_value["receipt_sha256"]
        or evidence.get("offline_test_count") != offline_test_value["test_count"]
        or actual_log_records != expected_log_records
    ):
        raise ArtifactBuildError("suite offline evidence binding mismatch")

    authority = data["authority"]
    if (root / "server-runtime/image-digest.txt").read_bytes() != (
        b"status=pending-stop-c\n"
        b"digest=not-created\n"
        b"external-write-authorized=false\n"
    ):
        raise ArtifactBuildError("image digest pending state mismatch")
    exact_manifests = {
        "server-runtime/app-host-model-contract.json": _expected_app_host_contract(),
        "server-runtime/server-answer-model-set-manifest.json": (
            _expected_server_model_set()
        ),
        "server-runtime/embedding-manifest.json": _expected_embedding_manifest(
            production_vector_contract_sha256
        ),
        "server-runtime/local-vector-manifest.json": (
            _expected_local_vector_manifest(production_vector_contract_sha256)
        ),
        "server-runtime/graph-manifest.json": _expected_graph_manifest(data),
        "server-runtime/ROLLBACK_PLAN.json": _expected_rollback(
            runtime_manifest["file_set_sha256"], authority["database"]["sha256"]
        ),
        "server-runtime/CLEANUP_PLAN.json": _expected_cleanup(),
        "server-runtime/SBOM.spdx.json": _expected_sbom(
            _parse_lock(lock_path),
            str(suite["created_at"]),
            str(runtime_manifest["file_set_sha256"]),
            builder_allowlist_sha256,
            builder_file_set_sha256,
        ),
    }
    for relative, expected in exact_manifests.items():
        if _load_json(root / relative) != expected:
            raise ArtifactBuildError(f"suite manifest semantics mismatch: {relative}")

    expected_identities = {
        "app_zip_sha256": app_verification["zip_sha256"],
        "authority_manifest_sha256": data["authority_manifest_sha256"],
        "authority_database_sha256": authority["database"]["sha256"],
        "bm25_manifest_sha256": data["bm25_manifest_sha256"],
        "bm25_index_sha256": data["bm25"]["index"]["sha256"],
        "graph_candidate_manifest_sha256": data["graph_manifest_sha256"],
        "graph_data_sha256": data["graph"]["graph"]["sha256"],
        "runtime_code_file_set_sha256": runtime_manifest["file_set_sha256"],
        "runtime_file_allowlist_sha256": sha256_file(allowlist_path),
        "builder_file_allowlist_sha256": builder_allowlist_sha256,
        "builder_code_file_set_sha256": builder_file_set_sha256,
        "requirements_lock_sha256": lock_sha256,
        "data_release_manifest_sha256": sha256_file(
            root / "server-runtime/data-release-manifest.json"
        ),
        "app_host_contract_sha256": sha256_file(
            root / "server-runtime/app-host-model-contract.json"
        ),
        "server_model_set_sha256": sha256_file(
            root / "server-runtime/server-answer-model-set-manifest.json"
        ),
        "embedding_manifest_sha256": sha256_file(
            root / "server-runtime/embedding-manifest.json"
        ),
        "local_vector_manifest_sha256": sha256_file(
            root / "server-runtime/local-vector-manifest.json"
        ),
        "production_vector_build_contract_sha256": (
            production_vector_contract_sha256
        ),
        "graph_manifest_sha256": sha256_file(
            root / "server-runtime/graph-manifest.json"
        ),
        "runtime_code_manifest_sha256": sha256_file(
            root / "server-runtime/runtime-code-manifest.json"
        ),
        "sbom_sha256": sha256_file(root / "server-runtime/SBOM.spdx.json"),
        "rollback_plan_sha256": sha256_file(root / "server-runtime/ROLLBACK_PLAN.json"),
        "cleanup_plan_sha256": sha256_file(root / "server-runtime/CLEANUP_PLAN.json"),
        "operator_manifest_sha256": sha256_file(
            root / "operator-companion/OPERATOR_MANIFEST.json"
        ),
        "operator_file_set_sha256": operator_manifest["file_set_sha256"],
        "operator_source_to_package_mapping_sha256": operator_manifest[
            "source_to_package_mapping_sha256"
        ],
    }
    if suite.get("identities") != expected_identities:
        raise ArtifactBuildError("suite embedded identities are not exact")
    return {
        "schema_version": "cloud-v2-suite-structural-verification-v1",
        "status": "passed-pending-final-dlp",
        "ok": False,
        "structural_verification_ok": True,
        "final_dlp_verified": False,
        "suite_release_id": suite["suite_release_id"],
        "suite_manifest_sha256": sha256_file(root / "SUITE_MANIFEST.json"),
        "file_count": len(discovered),
        "app_member_count": app_verification["member_count"],
    }


def _verify_suite_impl(
    output_root: str | Path,
    final_dlp_receipt: str | Path,
    evidence_roots: Mapping[str, str | Path],
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    root = Path(output_root).resolve(strict=True)
    repository = Path(repo_root).resolve(strict=True)
    receipt_path = Path(final_dlp_receipt).resolve(strict=True)
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise ArtifactBuildError("final suite DLP receipt must be a regular file")
    _require_detached(receipt_path, root, "final suite DLP receipt")
    structural = _verify_suite_structure(root, repo_root=repository)
    candidate_receipt_path = (
        root / "server-runtime/evidence/candidate-dlp-receipt.json"
    )
    try:
        final_dlp = validate_final_suite_dlp_receipt(
            receipt=receipt_path,
            suite_root=root,
            candidate_receipt_path=candidate_receipt_path,
            evidence_roots=evidence_roots,
            repo_root=repository,
        )
    except (DLPError, OSError, ValueError) as exc:
        raise ArtifactBuildError("final suite DLP receipt validation failed") from exc
    if final_dlp.get("status") != "passed" or final_dlp.get("ok") is not True:
        raise ArtifactBuildError("final suite DLP receipt did not pass")
    return {
        "schema_version": "cloud-v2-suite-verification-v2",
        "status": "passed",
        "ok": True,
        "suite_release_id": structural["suite_release_id"],
        "suite_manifest_sha256": structural["suite_manifest_sha256"],
        "file_count": structural["file_count"],
        "app_member_count": structural["app_member_count"],
        "final_dlp_receipt_sha256": sha256_file(receipt_path),
        "final_dlp_verified": True,
    }


def verify_suite(
    output_root: str | Path,
    final_dlp_receipt: str | Path,
    evidence_roots: Mapping[str, str | Path],
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    actions = _require_formal_artifact_builder_bootstrap_context()
    return actions[8](
        output_root,
        final_dlp_receipt,
        evidence_roots,
        repo_root=repo_root,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    app = subparsers.add_parser("app")
    app.add_argument("--repo-root", required=True)
    app.add_argument("--zip-path", required=True)
    app.add_argument("--receipt-path", required=True)
    verify_app = subparsers.add_parser("verify-app")
    verify_app.add_argument("--repo-root", required=True)
    verify_app.add_argument("--zip-path", required=True)
    suite = subparsers.add_parser("suite")
    suite.add_argument("--repo-root", required=True)
    suite.add_argument("--source-root", required=True)
    suite.add_argument("--governance-root", required=True)
    suite.add_argument("--authority-root", required=True)
    suite.add_argument("--derived-root", required=True)
    suite.add_argument("--app-zip", required=True)
    suite.add_argument("--app-receipt", required=True)
    suite.add_argument("--candidate-dlp-receipt", required=True)
    suite.add_argument("--disclosure-evidence", required=True)
    suite.add_argument("--offline-test-evidence-root", required=True)
    suite.add_argument("--offline-test-component-set", required=True)
    suite.add_argument("--offline-test-receipt", required=True)
    suite.add_argument("--output-root", required=True)
    suite.add_argument("--receipt-path", required=True)
    suite.add_argument("--created-at", required=True)
    verify_suite_parser = subparsers.add_parser("verify-suite")
    verify_suite_parser.add_argument("--repo-root", required=True)
    verify_suite_parser.add_argument("--output-root", required=True)
    verify_suite_parser.add_argument("--final-dlp-receipt", required=True)
    verify_suite_parser.add_argument(
        "--evidence-root",
        action="append",
        required=True,
        metavar="LABEL=PATH",
    )
    return parser


def _parse_evidence_roots(values: Sequence[str]) -> dict[str, str]:
    roots: dict[str, str] = {}
    for value in values:
        label, separator, path = value.partition("=")
        if not separator or not label or not path:
            raise ArtifactBuildError("evidence root must use LABEL=PATH")
        if label in roots:
            raise ArtifactBuildError("evidence root label is duplicated")
        roots[label] = path
    return roots


def _run_cli(
    argv: list[str] | None = None,
    *,
    _action_closure: tuple[object, ...] | None = None,
) -> int:
    actions = (
        _current_artifact_builder_action_closure()[:5]
        if _action_closure is None
        else _action_closure
    )
    if not isinstance(actions, tuple) or len(actions) != 5 or any(
        not callable(action) for action in actions
    ):
        raise ArtifactBuildError("artifact builder CLI action closure is malformed")
    parser_action, app_action, verify_app_action, suite_action, verify_suite_action = (
        actions
    )
    args = parser_action().parse_args(argv)
    if args.command == "app":
        result = app_action(args.repo_root, args.zip_path, args.receipt_path)
    elif args.command == "verify-app":
        result = verify_app_action(args.zip_path, repo_root=args.repo_root)
    elif args.command == "suite":
        result = suite_action(
            repo_root=args.repo_root,
            source_root=args.source_root,
            governance_root=args.governance_root,
            authority_root=args.authority_root,
            derived_root=args.derived_root,
            app_zip=args.app_zip,
            app_receipt=args.app_receipt,
            candidate_dlp_receipt=args.candidate_dlp_receipt,
            disclosure_evidence=args.disclosure_evidence,
            offline_test_evidence_root=args.offline_test_evidence_root,
            offline_test_component_set=args.offline_test_component_set,
            offline_test_receipt=args.offline_test_receipt,
            output_root=args.output_root,
            receipt_path=args.receipt_path,
            created_at=args.created_at,
        )
    else:
        result = verify_suite_action(
            args.output_root,
            args.final_dlp_receipt,
            _parse_evidence_roots(args.evidence_root),
            repo_root=args.repo_root,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        actions = _require_formal_artifact_builder_bootstrap_context()
    except ArtifactBuildError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    return _run_cli(argv, _action_closure=actions[:5])


if __name__ == "__main__":
    raise SystemExit(main())
