#!/usr/bin/env python3
"""Candidate-only server job registry; no arbitrary command or active write path."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from .identity_policy import (
    MAINTENANCE_CONFIRMATION_ISSUER,
    MAINTENANCE_CONFIRMATION_SCHEMA_VERSION,
    VerifiedIdentity,
    VerifiedMaintenanceConfirmation,
    authorize_ops,
)


JOB_SCHEMA_VERSION = "cloud-v2-maintenance-job-v2"
MAINTENANCE_SUBMIT_SCHEMA_VERSION = "maintenance-job-submit-v2"
PLAN_SCHEMA_VERSION = "maintenance-plan-v1"
CONFIRMATION_SCHEMA_VERSION = MAINTENANCE_CONFIRMATION_SCHEMA_VERSION
CONFIRMATION_AUDIENCE = "maintenance-controller-cloud"
CONFIRMATION_ISSUER = MAINTENANCE_CONFIRMATION_ISSUER
CONFIRMATION_MAX_LIFETIME_SECONDS = 300
CONFIRMATION_CONSUMPTION_SCHEMA_VERSION = "maintenance-confirmation-consumption-v1"
BUILTIN_BACKEND_REGISTRY_ID = "candidate-plan-backends-v1"
BUILTIN_PLAN_SCHEMA_VERSION = "cloud-v2-candidate-job-request-v1"
BUILTIN_PLAN_STATUS = "candidate_plan_created"
JOB_SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "collect_identity_snapshot": {"required": ("suite_release_id",), "optional": ()},
    "run_sealed_regression": {
        "required": (
            "candidate_release_id",
            "fixture_id",
            "fixture_sha256",
            "serial",
            "retry_count",
        ),
        "optional": (),
    },
    "rebuild_candidate_bm25": {
        "required": ("candidate_release_id", "source_release_id", "authority_sha256"),
        "optional": (),
    },
    "rebuild_candidate_chunk_vector": {
        "required": (
            "candidate_release_id",
            "source_release_id",
            "authority_sha256",
            "embedding_manifest_sha256",
        ),
        "optional": (),
    },
    "rebuild_candidate_entity_vector": {
        "required": (
            "candidate_release_id",
            "source_release_id",
            "authority_sha256",
            "embedding_manifest_sha256",
        ),
        "optional": (),
    },
    "rebuild_candidate_graph": {
        "required": ("candidate_release_id", "source_release_id", "authority_sha256"),
        "optional": (),
    },
    "compare_active_candidate_manifest": {
        "required": ("active_release_id", "candidate_release_id"),
        "optional": (),
    },
    "generate_rollback_plan": {
        "required": ("active_release_id", "rollback_release_id"),
        "optional": (),
    },
    "generate_switch_plan": {
        "required": ("active_release_id", "candidate_release_id"),
        "optional": (),
    },
    "generate_cleanup_plan": {
        "required": ("active_release_id", "retired_release_id"),
        "optional": (),
    },
    "verify_exact_delete_target": {
        "required": (
            "active_release_id",
            "target_kind",
            "target_id",
            "expected_manifest_sha256",
        ),
        "optional": (),
    },
}
CANDIDATE_JOB_TYPES = frozenset(JOB_SPECS)
_ID_FIELDS = frozenset(
    {
        "active_release_id",
        "candidate_release_id",
        "fixture_id",
        "rollback_release_id",
        "retired_release_id",
        "source_release_id",
        "suite_release_id",
        "target_id",
    }
)
_SHA_FIELDS = frozenset(
    {
        "authority_sha256",
        "embedding_manifest_sha256",
        "expected_manifest_sha256",
        "fixture_sha256",
    }
)
_TARGET_KINDS = frozenset(
    {
        "code_image",
        "authority_release",
        "bm25_index",
        "chunk_vector_index",
        "entity_vector_index",
        "graph_snapshot",
    }
)
_REBUILD_OUTPUT_COMPONENTS = {
    "rebuild_candidate_bm25": "bm25",
    "rebuild_candidate_chunk_vector": "chunk-vector",
    "rebuild_candidate_entity_vector": "entity-vector",
    "rebuild_candidate_graph": "graph",
}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_PARAMETER_KEYS = frozenset(
    {
        "active_write",
        "command",
        "cypher",
        "delete",
        "password",
        "provider_secret",
        "shell",
        "sql",
        "token",
    }
)


class MaintenanceJobError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MaintenanceJob:
    job_type: str
    parameters: Mapping[str, Any]
    candidate_output: str | None
    plan_id: str
    confirmation: Mapping[str, Any]
    schema_version: str = JOB_SCHEMA_VERSION


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _candidate_path(raw: str) -> str:
    if not isinstance(raw, str) or raw.startswith("/") or "\\" in raw or "//" in raw:
        raise MaintenanceJobError("candidate_output_must_be_relative")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise MaintenanceJobError("candidate_output_not_canonical")
    if "active" in path.parts or not any(part in {"candidate", "candidates"} for part in path.parts):
        raise MaintenanceJobError("candidate_output_required")
    return path.as_posix()


class CandidateWorkspaceBinding:
    """Process-lifetime binding to one service-owned candidate directory inode."""

    def __init__(self, root: str | Path) -> None:
        raw_root = Path(root)
        if not raw_root.is_absolute():
            raise MaintenanceJobError("candidate_workspace_must_be_absolute")
        try:
            root_stat = raw_root.lstat()
        except OSError as exc:
            raise MaintenanceJobError("candidate_workspace_unavailable") from exc
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise MaintenanceJobError("candidate_workspace_must_be_directory")
        if root_stat.st_uid != os.geteuid() or stat.S_IMODE(root_stat.st_mode) & 0o022:
            raise MaintenanceJobError("candidate_workspace_permissions_invalid")
        resolved = raw_root.resolve(strict=True)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            root_fd = os.open(resolved, flags)
        except OSError as exc:
            raise MaintenanceJobError("candidate_workspace_unavailable") from exc
        try:
            opened = os.fstat(root_fd)
        except OSError as exc:
            os.close(root_fd)
            raise MaintenanceJobError("candidate_workspace_unavailable") from exc
        if (
            opened.st_dev != root_stat.st_dev
            or opened.st_ino != root_stat.st_ino
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
        ):
            os.close(root_fd)
            raise MaintenanceJobError("candidate_workspace_identity_changed")
        self._root = resolved
        self._root_fd = root_fd
        self._device = opened.st_dev
        self._inode = opened.st_ino

    def _verify_path_and_fd(self, descriptor: int) -> None:
        try:
            opened = os.fstat(descriptor)
            current = self._root.lstat()
        except OSError as exc:
            raise MaintenanceJobError("candidate_workspace_unavailable") from exc
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or opened.st_dev != self._device
            or opened.st_ino != self._inode
            or current.st_dev != self._device
            or current.st_ino != self._inode
            or opened.st_uid != os.geteuid()
            or current.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
            or stat.S_IMODE(current.st_mode) & 0o022
        ):
            raise MaintenanceJobError("candidate_workspace_identity_changed")

    def open_session(self) -> int:
        try:
            descriptor = os.dup(self._root_fd)
        except OSError as exc:
            raise MaintenanceJobError("candidate_workspace_unavailable") from exc
        try:
            self._verify_path_and_fd(descriptor)
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    def verify_session(self, descriptor: int) -> None:
        self._verify_path_and_fd(descriptor)


class CandidateOutput:
    """Directory-FD capability for one server-derived candidate output."""

    __slots__ = (
        "_active",
        "_device",
        "_inode",
        "_lock",
        "_relative_path",
        "_workspace_fd",
    )

    def __init__(self, workspace_fd: int, relative_path: str) -> None:
        try:
            opened = os.fstat(workspace_fd)
        except (OSError, TypeError) as exc:
            raise MaintenanceJobError("candidate_workspace_unavailable") from exc
        if (
            not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
        ):
            raise MaintenanceJobError("candidate_workspace_permissions_invalid")
        object.__setattr__(self, "_workspace_fd", workspace_fd)
        object.__setattr__(self, "_relative_path", _candidate_path(relative_path))
        object.__setattr__(self, "_device", opened.st_dev)
        object.__setattr__(self, "_inode", opened.st_ino)
        object.__setattr__(self, "_active", True)
        object.__setattr__(self, "_lock", threading.RLock())

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("CandidateOutput bindings are immutable")

    @property
    def relative_path(self) -> str:
        return self._relative_path

    def __repr__(self) -> str:
        return f"CandidateOutput(relative_path={self.relative_path!r})"

    def _invalidate(self) -> None:
        with self._lock:
            object.__setattr__(self, "_active", False)

    def _open_workspace_directory(self) -> int:
        with self._lock:
            if not self._active:
                raise MaintenanceJobError("candidate_output_expired")
            try:
                opened = os.fstat(self._workspace_fd)
            except OSError as exc:
                raise MaintenanceJobError("candidate_workspace_unavailable") from exc
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_dev != self._device
                or opened.st_ino != self._inode
                or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) & 0o022
            ):
                raise MaintenanceJobError("candidate_workspace_identity_changed")
            try:
                current_fd = os.dup(self._workspace_fd)
            except OSError as exc:
                raise MaintenanceJobError("candidate_workspace_unavailable") from exc
            try:
                duplicate = os.fstat(current_fd)
            except OSError as exc:
                os.close(current_fd)
                raise MaintenanceJobError("candidate_workspace_unavailable") from exc
            if (
                duplicate.st_dev != self._device
                or duplicate.st_ino != self._inode
            ):
                os.close(current_fd)
                raise MaintenanceJobError("candidate_workspace_identity_changed")
            return current_fd

    def open_directory(self, *, create: bool = False) -> int:
        """Open the output with openat/no-follow; caller owns the returned FD."""

        with self._lock:
            current_fd = self._open_workspace_directory()
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
            try:
                relative_path = _candidate_path(self._relative_path)
                for part in PurePosixPath(relative_path).parts:
                    try:
                        next_fd = os.open(part, flags, dir_fd=current_fd)
                    except FileNotFoundError:
                        if not create:
                            raise MaintenanceJobError(
                                "candidate_output_unavailable"
                            ) from None
                        try:
                            os.mkdir(part, 0o700, dir_fd=current_fd)
                            os.fsync(current_fd)
                            next_fd = os.open(part, flags, dir_fd=current_fd)
                        except OSError as exc:
                            raise MaintenanceJobError(
                                "candidate_output_create_failed"
                            ) from exc
                    except OSError as exc:
                        raise MaintenanceJobError(
                            "candidate_output_unavailable"
                        ) from exc
                    os.close(current_fd)
                    current_fd = next_fd
                    opened = os.fstat(current_fd)
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or opened.st_uid != os.geteuid()
                        or stat.S_IMODE(opened.st_mode) & 0o022
                    ):
                        raise MaintenanceJobError(
                            "candidate_output_permissions_invalid"
                        )
                return current_fd
            except Exception:
                os.close(current_fd)
                raise

    def write_json_once(self, filename: str, value: Mapping[str, Any]) -> str:
        """Persist one immutable candidate request below this output capability."""

        if not isinstance(filename, str) or _IDENTIFIER.fullmatch(filename) is None:
            raise MaintenanceJobError("candidate_filename_invalid")
        try:
            payload = _canonical_json(dict(value)) + b"\n"
        except (TypeError, ValueError) as exc:
            raise MaintenanceJobError("candidate_payload_must_be_json") from exc
        directory_fd = self.open_directory(create=True)
        file_fd: int | None = None
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            try:
                file_fd = os.open(filename, flags, 0o600, dir_fd=directory_fd)
            except FileExistsError as exc:
                raise MaintenanceJobError("candidate_output_already_exists") from exc
            except OSError as exc:
                raise MaintenanceJobError("candidate_output_create_failed") from exc
            try:
                os.fchmod(file_fd, 0o600)
                offset = 0
                while offset < len(payload):
                    written = os.write(file_fd, payload[offset:])
                    if written <= 0:
                        raise OSError("short candidate output write")
                    offset += written
                os.fsync(file_fd)
                os.fsync(directory_fd)
            except OSError as exc:
                raise MaintenanceJobError("candidate_output_write_failed") from exc
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(directory_fd)
        return hashlib.sha256(payload).hexdigest()


class BuiltinCandidateBackendRegistry:
    """Fixed plan-only backends; deployment configuration cannot inject code."""

    def __init__(self, *, active_identity_sha256: str) -> None:
        self._active_identity_sha256 = _sha256(
            active_identity_sha256,
            "active_identity_sha256",
        )

    @property
    def registry_id(self) -> str:
        return BUILTIN_BACKEND_REGISTRY_ID

    def handlers(
        self,
    ) -> dict[str, Callable[[Mapping[str, Any], CandidateOutput | None], Any]]:
        return {
            job_type: self._plan_handler(job_type)
            for job_type in sorted(CANDIDATE_JOB_TYPES)
        }

    def _plan_handler(
        self,
        job_type: str,
    ) -> Callable[[Mapping[str, Any], CandidateOutput | None], Any]:
        if job_type not in CANDIDATE_JOB_TYPES:
            raise MaintenanceJobError("job_type_not_allowlisted")

        def handle(
            parameters: Mapping[str, Any],
            output: CandidateOutput | None,
        ) -> dict[str, Any]:
            normalized = _normalize_parameters(job_type, parameters)
            plan = {
                "schema_version": BUILTIN_PLAN_SCHEMA_VERSION,
                "backend_registry_id": BUILTIN_BACKEND_REGISTRY_ID,
                "job_type": job_type,
                "parameters": normalized,
                "candidate_output": output.relative_path if output is not None else None,
                "active_identity_sha256": self._active_identity_sha256,
                "execution_authorized": False,
                "active_write": False,
                "release_switch": False,
                "status": BUILTIN_PLAN_STATUS,
            }
            plan_sha256 = hashlib.sha256(_canonical_json(plan)).hexdigest()
            receipt_sha256 = plan_sha256
            if output is not None:
                receipt_sha256 = output.write_json_once(
                    f"request-{plan_sha256}.json",
                    plan,
                )
            return {
                "execution_status": BUILTIN_PLAN_STATUS,
                "backend_registry_id": BUILTIN_BACKEND_REGISTRY_ID,
                "plan_sha256": plan_sha256,
                "candidate_receipt_sha256": receipt_sha256,
                "active_write": False,
                "active_completion": False,
            }

        return handle


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise MaintenanceJobError(f"invalid_{field}")
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MaintenanceJobError(f"invalid_{field}")
    return value


def _normalize_parameters(job_type: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if job_type not in JOB_SPECS:
        raise MaintenanceJobError("job_type_not_allowlisted")
    if not isinstance(parameters, Mapping) or not all(
        isinstance(key, str) for key in parameters
    ):
        raise MaintenanceJobError("job_parameters_must_be_object")
    lowered = {key.strip().lower() for key in parameters}
    if lowered & FORBIDDEN_PARAMETER_KEYS or any(key.startswith("raw_") for key in lowered):
        raise MaintenanceJobError("forbidden_job_parameter")
    spec = JOB_SPECS[job_type]
    required = set(spec["required"])
    allowed = required | set(spec["optional"])
    if required - set(parameters):
        raise MaintenanceJobError("job_parameters_missing_fields")
    if set(parameters) - allowed:
        raise MaintenanceJobError("job_parameters_unknown_fields")
    try:
        normalized = json.loads(_canonical_json(dict(parameters)))
    except (TypeError, ValueError) as exc:
        raise MaintenanceJobError("job_parameters_must_be_json") from exc
    for field, value in normalized.items():
        if field in _ID_FIELDS:
            _identifier(value, field)
        elif field in _SHA_FIELDS:
            _sha256(value, field)
        elif field == "serial":
            if value is not True:
                raise MaintenanceJobError("serial_must_be_true")
        elif field == "retry_count":
            if isinstance(value, bool) or not isinstance(value, int) or value != 0:
                raise MaintenanceJobError("retry_count_must_be_zero")
        elif field == "target_kind":
            if not isinstance(value, str) or value not in _TARGET_KINDS:
                raise MaintenanceJobError("invalid_target_kind")
        else:
            raise MaintenanceJobError("unsupported_job_parameter")
    return normalized


def maintenance_plan_id(
    job_type: str,
    parameters: Mapping[str, Any],
    requested_by: str,
) -> str:
    normalized = _normalize_parameters(job_type, parameters)
    subject = _identifier(requested_by, "requested_by")
    body = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "job_type": job_type,
        "parameters": normalized,
        "requested_by": subject,
        "confirmation_required": True,
    }
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def candidate_output_for_job(
    job_type: str,
    parameters: Mapping[str, Any],
) -> str | None:
    normalized = _normalize_parameters(job_type, parameters)
    component = _REBUILD_OUTPUT_COMPONENTS.get(job_type)
    if component is None:
        return None
    release_id = str(normalized["candidate_release_id"])
    return _candidate_path(f"candidates/{release_id}/{component}")


def _planned_candidate_output(
    job_type: str,
    parameters: Mapping[str, Any],
    plan_id: str,
) -> str:
    output = candidate_output_for_job(job_type, parameters)
    if output is not None:
        return output
    return _candidate_path(f"candidates/job-plans/{job_type}/{plan_id}")


def maintenance_job_from_submit(
    body: Mapping[str, Any],
    *,
    verified_confirmation: VerifiedMaintenanceConfirmation,
) -> MaintenanceJob:
    """Translate an exact body plus out-of-band gateway confirmation."""

    required_fields = {
        "schema_version",
        "plan_id",
        "job_type",
        "parameters",
    }
    if not isinstance(body, Mapping) or not all(isinstance(key, str) for key in body):
        raise MaintenanceJobError("maintenance_submit_body_must_be_object")
    if set(body) != required_fields:
        raise MaintenanceJobError("maintenance_submit_shape_mismatch")
    if body.get("schema_version") != MAINTENANCE_SUBMIT_SCHEMA_VERSION:
        raise MaintenanceJobError("maintenance_submit_schema_mismatch")

    job_type = _identifier(body.get("job_type"), "job_type")
    parameters = body.get("parameters")
    if not isinstance(parameters, Mapping):
        raise MaintenanceJobError("job_parameters_must_be_object")
    normalized_parameters = _normalize_parameters(job_type, parameters)
    plan_id = _sha256(body.get("plan_id"), "plan_id")
    if not isinstance(verified_confirmation, VerifiedMaintenanceConfirmation):
        raise MaintenanceJobError("verified_confirmation_required")
    normalized_confirmation = verified_confirmation.to_dict()

    return MaintenanceJob(
        job_type=job_type,
        parameters=normalized_parameters,
        candidate_output=_planned_candidate_output(
            job_type,
            normalized_parameters,
            plan_id,
        ),
        plan_id=plan_id,
        confirmation=normalized_confirmation,
    )


def _validate_confirmation(
    confirmation: Mapping[str, Any],
    *,
    plan_id: str,
    subject: str,
    now_epoch_seconds: int,
) -> dict[str, Any]:
    if not isinstance(confirmation, Mapping):
        raise MaintenanceJobError("verified_confirmation_required")
    if set(confirmation) != {
        "schema_version",
        "issuer",
        "audience",
        "plan_id",
        "confirmation_id",
        "confirmed_by",
        "authn_methods",
        "decision",
        "issued_at_epoch_seconds",
        "expires_at_epoch_seconds",
    }:
        raise MaintenanceJobError("confirmation_shape_mismatch")
    methods = confirmation.get("authn_methods")
    if (
        not isinstance(methods, Sequence)
        or isinstance(methods, (str, bytes, bytearray))
        or not methods
        or len(methods) > 8
        or len(set(methods)) != len(methods)
        or any(not isinstance(method, str) or _IDENTIFIER.fullmatch(method) is None for method in methods)
    ):
        raise MaintenanceJobError("confirmation_authn_methods_invalid")
    issued_at = confirmation.get("issued_at_epoch_seconds")
    expires_at = confirmation.get("expires_at_epoch_seconds")
    if (
        isinstance(issued_at, bool)
        or not isinstance(issued_at, int)
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, int)
        or issued_at < 0
        or expires_at <= issued_at
        or expires_at - issued_at > CONFIRMATION_MAX_LIFETIME_SECONDS
        or now_epoch_seconds < issued_at
        or now_epoch_seconds >= expires_at
    ):
        raise MaintenanceJobError("confirmation_time_window_invalid")
    if (
        confirmation.get("schema_version") != CONFIRMATION_SCHEMA_VERSION
        or confirmation.get("issuer") != CONFIRMATION_ISSUER
        or confirmation.get("audience") != CONFIRMATION_AUDIENCE
        or confirmation.get("plan_id") != plan_id
        or confirmation.get("confirmed_by") != subject
        or confirmation.get("decision") != "approved"
        or "mfa" not in methods
    ):
        raise MaintenanceJobError("confirmation_not_plan_bound")
    _identifier(confirmation.get("confirmation_id"), "confirmation_id")
    try:
        return json.loads(_canonical_json(dict(confirmation)))
    except (TypeError, ValueError) as exc:
        raise MaintenanceJobError("confirmation_must_be_json") from exc


def validate_job(
    job: MaintenanceJob,
    *,
    identity: VerifiedIdentity,
    now_epoch_seconds: int,
) -> dict[str, Any]:
    if not isinstance(job, MaintenanceJob):
        raise MaintenanceJobError("maintenance_job_required")
    if job.schema_version != JOB_SCHEMA_VERSION:
        raise MaintenanceJobError("maintenance_job_schema_mismatch")
    try:
        authorize_ops(identity, "/ops/maintenance/jobs", required_role="ops-maintainer")
    except Exception:
        raise MaintenanceJobError("verified_ops_maintainer_required") from None
    normalized = _normalize_parameters(job.job_type, job.parameters)
    expected_plan_id = maintenance_plan_id(job.job_type, normalized, identity.subject)
    if job.plan_id != expected_plan_id:
        raise MaintenanceJobError("maintenance_plan_hash_mismatch")
    confirmation = _validate_confirmation(
        job.confirmation,
        plan_id=expected_plan_id,
        subject=identity.subject,
        now_epoch_seconds=now_epoch_seconds,
    )
    expected_output = _planned_candidate_output(
        job.job_type,
        normalized,
        expected_plan_id,
    )
    output = _candidate_path(job.candidate_output) if job.candidate_output is not None else None
    if output != expected_output:
        raise MaintenanceJobError("candidate_output_plan_mismatch")
    return {
        "schema_version": job.schema_version,
        "job_type": job.job_type,
        "parameters": normalized,
        "candidate_output": output,
        "plan_id": expected_plan_id,
        "confirmation": confirmation,
    }


class ConfirmationReplayLedger:
    """Durably consume second confirmations before a maintenance handler runs."""

    def __init__(self, root: str | Path) -> None:
        path = Path(root)
        if not path.is_absolute():
            raise MaintenanceJobError("confirmation_ledger_must_be_absolute")
        try:
            path_stat = path.lstat()
        except OSError as exc:
            raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
            raise MaintenanceJobError("confirmation_ledger_must_be_private_directory")
        if path_stat.st_uid != os.geteuid():
            raise MaintenanceJobError("confirmation_ledger_owner_mismatch")
        if stat.S_IMODE(path_stat.st_mode) != 0o700:
            raise MaintenanceJobError("confirmation_ledger_mode_mismatch")
        try:
            self._root = path.resolve(strict=True)
        except OSError as exc:
            raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
        self._device = path_stat.st_dev
        self._inode = path_stat.st_ino
        root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            self._root_fd = os.open(self._root, root_flags)
        except OSError as exc:
            raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
        try:
            opened = os.fstat(self._root_fd)
        except OSError as exc:
            os.close(self._root_fd)
            raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
        if opened.st_dev != self._device or opened.st_ino != self._inode:
            os.close(self._root_fd)
            raise MaintenanceJobError("confirmation_ledger_identity_changed")

    def _verify_root(self, descriptor: int) -> None:
        try:
            opened_root = os.fstat(descriptor)
            current_root = self._root.lstat()
        except OSError as exc:
            raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or stat.S_ISLNK(current_root.st_mode)
            or not stat.S_ISDIR(current_root.st_mode)
            or opened_root.st_dev != current_root.st_dev
            or opened_root.st_ino != current_root.st_ino
            or opened_root.st_dev != self._device
            or opened_root.st_ino != self._inode
            or current_root.st_dev != self._device
            or current_root.st_ino != self._inode
            or opened_root.st_uid != os.geteuid()
            or current_root.st_uid != os.geteuid()
            or stat.S_IMODE(opened_root.st_mode) != 0o700
            or stat.S_IMODE(current_root.st_mode) != 0o700
        ):
            raise MaintenanceJobError("confirmation_ledger_identity_changed")

    def verify(self) -> None:
        try:
            root_fd = os.dup(self._root_fd)
        except OSError as exc:
            raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
        try:
            self._verify_root(root_fd)
        finally:
            os.close(root_fd)

    def consume(self, normalized_job: Mapping[str, Any]) -> str:
        confirmation = normalized_job["confirmation"]
        confirmation_id = str(confirmation["confirmation_id"])
        record = {
            "schema_version": CONFIRMATION_CONSUMPTION_SCHEMA_VERSION,
            "confirmation_id": confirmation_id,
            "confirmation_sha256": hashlib.sha256(
                _canonical_json(confirmation)
            ).hexdigest(),
            "plan_id": normalized_job["plan_id"],
            "confirmed_by": confirmation["confirmed_by"],
            "job_type": normalized_job["job_type"],
            "candidate_output": normalized_job["candidate_output"],
            "consumed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        payload = _canonical_json(record) + b"\n"
        filename = hashlib.sha256(confirmation_id.encode("utf-8")).hexdigest() + ".json"
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            root_fd = os.dup(self._root_fd)
        except OSError as exc:
            raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
        file_fd: int | None = None
        try:
            self._verify_root(root_fd)
            try:
                file_fd = os.open(filename, file_flags, 0o600, dir_fd=root_fd)
            except FileExistsError as exc:
                raise MaintenanceJobError("confirmation_already_consumed") from exc
            except OSError as exc:
                raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
            try:
                os.fchmod(file_fd, 0o600)
                offset = 0
                while offset < len(payload):
                    written = os.write(file_fd, payload[offset:])
                    if written <= 0:
                        raise OSError("short confirmation ledger write")
                    offset += written
                os.fsync(file_fd)
                os.fsync(root_fd)
                self._verify_root(root_fd)
            except OSError as exc:
                # A partial record remains consumed so a storage failure cannot enable replay.
                raise MaintenanceJobError("confirmation_ledger_unavailable") from exc
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(root_fd)
        return hashlib.sha256(payload).hexdigest()


class CandidateJobRunner:
    def __init__(
        self,
        handlers: Mapping[
            str, Callable[[Mapping[str, Any], CandidateOutput | None], Any]
        ],
        *,
        confirmation_ledger_root: str | Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(handlers, Mapping) or set(handlers) - CANDIDATE_JOB_TYPES:
            raise MaintenanceJobError("handler_registry_not_allowlisted")
        if any(not callable(handler) for handler in handlers.values()):
            raise MaintenanceJobError("handler_must_be_callable")
        self._handlers = dict(handlers)
        self._confirmation_ledger = ConfirmationReplayLedger(confirmation_ledger_root)
        if not callable(clock):
            raise MaintenanceJobError("maintenance_clock_required")
        self._clock = clock

    def submit(
        self,
        job: MaintenanceJob,
        *,
        workspace: CandidateWorkspaceBinding,
        identity: VerifiedIdentity,
    ) -> dict[str, Any]:
        now_value = self._clock()
        if (
            isinstance(now_value, bool)
            or not isinstance(now_value, (int, float))
            or not math.isfinite(float(now_value))
            or now_value < 0
        ):
            raise MaintenanceJobError("maintenance_clock_invalid")
        normalized = validate_job(
            job,
            identity=identity,
            now_epoch_seconds=int(now_value),
        )
        handler = self._handlers.get(job.job_type)
        if handler is None:
            raise MaintenanceJobError("job_handler_unavailable")
        if not isinstance(workspace, CandidateWorkspaceBinding):
            raise MaintenanceJobError("candidate_workspace_binding_required")
        workspace_fd = workspace.open_session()
        output: CandidateOutput | None = None
        try:
            output = (
                CandidateOutput(workspace_fd, normalized["candidate_output"])
                if normalized["candidate_output"] is not None
                else None
            )
            confirmation_consumption_sha256 = self._confirmation_ledger.consume(
                normalized
            )
            self._confirmation_ledger.verify()
            result = handler(normalized["parameters"], output)
            workspace.verify_session(workspace_fd)
        finally:
            if output is not None:
                output._invalidate()
            os.close(workspace_fd)
        result_sha256 = hashlib.sha256(_canonical_json(result)).hexdigest()
        planned = (
            isinstance(result, Mapping)
            and result.get("execution_status") == BUILTIN_PLAN_STATUS
        )
        receipt_sha256 = result_sha256
        if planned:
            candidate_receipt = result.get("candidate_receipt_sha256")
            if isinstance(candidate_receipt, str) and _SHA256.fullmatch(candidate_receipt):
                receipt_sha256 = candidate_receipt
        return {
            "schema_version": "cloud-v2-maintenance-job-result-v1",
            "status": "candidate-job-planned" if planned else "candidate-job-completed",
            "job_id": f"job-{normalized['plan_id'][:24]}",
            "job_type": job.job_type,
            "job_status": "planned" if planned else "completed",
            "result_sha256": result_sha256,
            "receipt_sha256": receipt_sha256,
            "confirmation_consumption_sha256": confirmation_consumption_sha256,
            "active_write": False,
            "release_switch": False,
        }
