#!/usr/bin/env python3
"""Plan and submit fixed-schema jobs after a separately verified confirmation."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

from lib.ops_contract import (
    OpsAccessDenied,
    OpsContractError,
    StructuredRequest,
    StructuredTransport,
    VerifiedPrincipal,
    authorize_ops_principal,
    invoke_transport,
    require_bool,
    require_enum,
    require_exact_fields,
    require_identifier,
    require_sha256,
)


PLAN_SCHEMA_VERSION = "maintenance-plan-v1"
CONFIRMATION_SCHEMA_VERSION = "maintenance-confirmation-v2"
SUBMIT_SCHEMA_VERSION = "maintenance-job-submit-v2"
CONFIRMATION_ISSUER = "private-admin-confirmation-gateway"
CONFIRMATION_AUDIENCE = "maintenance-controller-cloud"
CONFIRMATION_MAX_LIFETIME_SECONDS = 300

JOB_SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "collect_identity_snapshot": {
        "required": ("suite_release_id",),
        "optional": (),
    },
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


@dataclass(frozen=True)
class MaintenancePlan:
    schema_version: str
    plan_id: str
    job_type: str
    parameters: Mapping[str, Any]
    requested_by: str
    confirmation_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "job_type": self.job_type,
            "parameters": dict(self.parameters),
            "requested_by": self.requested_by,
            "confirmation_required": self.confirmation_required,
        }


@dataclass(frozen=True)
class VerifiedConfirmation:
    """Fresh second-confirmation claims returned by the trusted admin gateway."""

    issuer: str
    audience: str
    plan_id: str
    confirmation_id: str
    confirmed_by: str
    authn_methods: tuple[str, ...]
    decision: str
    issued_at_epoch_seconds: int
    expires_at_epoch_seconds: int
    schema_version: str = CONFIRMATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "issuer": self.issuer,
            "audience": self.audience,
            "plan_id": self.plan_id,
            "confirmation_id": self.confirmation_id,
            "confirmed_by": self.confirmed_by,
            "authn_methods": list(self.authn_methods),
            "decision": self.decision,
            "issued_at_epoch_seconds": self.issued_at_epoch_seconds,
            "expires_at_epoch_seconds": self.expires_at_epoch_seconds,
        }


class ConfirmationVerifier(Protocol):
    def verify(
        self,
        *,
        plan: MaintenancePlan,
        principal: VerifiedPrincipal,
    ) -> VerifiedConfirmation:
        ...


class MaintenanceControllerClient:
    """No generic command API: only fixed jobs and a verified second confirmation."""

    def __init__(
        self,
        *,
        principal: VerifiedPrincipal,
        transport: StructuredTransport,
        confirmation_verifier: ConfirmationVerifier,
        clock: Callable[[], float] = time.time,
    ):
        if not callable(clock):
            raise OpsContractError("maintenance_clock_required")
        self._principal = principal
        self._transport = transport
        self._confirmation_verifier = confirmation_verifier
        self._clock = clock

    def list_job_types(self) -> tuple[str, ...]:
        authorize_ops_principal(self._principal, required_role="ops-maintainer")
        return tuple(JOB_SPECS)

    def prepare_job(
        self,
        *,
        job_type: str,
        parameters: Mapping[str, Any],
    ) -> MaintenancePlan:
        authorize_ops_principal(self._principal, required_role="ops-maintainer")
        normalized = _validate_job(job_type, parameters)
        body = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "job_type": job_type,
            "parameters": normalized,
            "requested_by": self._principal.subject,
            "confirmation_required": True,
        }
        plan_id = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
        return MaintenancePlan(plan_id=plan_id, **body)

    def submit_job(self, plan: MaintenancePlan) -> dict[str, Any]:
        authorize_ops_principal(self._principal, required_role="ops-maintainer")
        _validate_plan(plan, self._principal)
        verify = getattr(self._confirmation_verifier, "verify", None)
        if not callable(verify):
            raise OpsAccessDenied("confirmation_verifier_required")
        try:
            confirmation = verify(plan=plan, principal=self._principal)
        except Exception:
            raise OpsAccessDenied("confirmation_verification_failed") from None
        _validate_confirmation(
            confirmation,
            plan,
            self._principal,
            now_epoch_seconds=_read_clock(self._clock),
        )
        payload = {
            "schema_version": SUBMIT_SCHEMA_VERSION,
            "plan_id": plan.plan_id,
            "job_type": plan.job_type,
            "parameters": dict(plan.parameters),
        }
        request = StructuredRequest(
            operation="maintenance.submit_job",
            principal_subject=self._principal.subject,
            payload=payload,
        )
        result = invoke_transport(
            transport=self._transport,
            request=request,
            response_fields=(
                "job_id",
                "job_type",
                "job_status",
                "candidate_release_id",
                "receipt_sha256",
                "status_code",
                "diagnostic_codes",
            ),
            required_ok_fields=(
                "job_id",
                "job_type",
                "job_status",
                "status_code",
                "diagnostic_codes",
            ),
            verified_maintenance_confirmation=confirmation,
        )
        if result["status"] == "ok" and result["data"]["job_type"] != plan.job_type:
            raise OpsContractError("job_response_type_mismatch")
        return result


def _validate_job(job_type: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if job_type not in JOB_SPECS:
        raise OpsContractError("job_type_not_allowlisted")
    spec = JOB_SPECS[job_type]
    normalized = require_exact_fields(
        parameters,
        required=spec["required"],
        optional=spec["optional"],
        field="job_parameters",
    )
    for field, value in normalized.items():
        if field in _ID_FIELDS:
            require_identifier(value, field)
        elif field in _SHA_FIELDS:
            require_sha256(value, field)
        elif field == "serial":
            if require_bool(value, field) is not True:
                raise OpsContractError("serial_must_be_true")
        elif field == "retry_count":
            if not isinstance(value, int) or isinstance(value, bool) or value != 0:
                raise OpsContractError("retry_count_must_be_zero")
        elif field == "target_kind":
            require_enum(
                value,
                field,
                (
                    "code_image",
                    "authority_release",
                    "bm25_index",
                    "chunk_vector_index",
                    "entity_vector_index",
                    "graph_snapshot",
                ),
            )
        else:
            raise OpsContractError("unsupported_job_parameter")
    return normalized


def _validate_plan(plan: MaintenancePlan, principal: VerifiedPrincipal) -> None:
    if not isinstance(plan, MaintenancePlan):
        raise OpsContractError("maintenance_plan_required")
    if plan.schema_version != PLAN_SCHEMA_VERSION:
        raise OpsContractError("maintenance_plan_schema_mismatch")
    if plan.requested_by != principal.subject:
        raise OpsAccessDenied("maintenance_plan_principal_mismatch")
    if plan.confirmation_required is not True:
        raise OpsContractError("maintenance_confirmation_required")
    normalized = _validate_job(plan.job_type, plan.parameters)
    body = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "job_type": plan.job_type,
        "parameters": normalized,
        "requested_by": plan.requested_by,
        "confirmation_required": True,
    }
    expected = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    if plan.plan_id != expected:
        raise OpsContractError("maintenance_plan_hash_mismatch")


def _validate_confirmation(
    confirmation: VerifiedConfirmation,
    plan: MaintenancePlan,
    principal: VerifiedPrincipal,
    *,
    now_epoch_seconds: int,
) -> None:
    if not isinstance(confirmation, VerifiedConfirmation):
        raise OpsAccessDenied("verified_confirmation_required")
    if confirmation.schema_version != CONFIRMATION_SCHEMA_VERSION:
        raise OpsAccessDenied("confirmation_schema_mismatch")
    if confirmation.issuer != CONFIRMATION_ISSUER:
        raise OpsAccessDenied("confirmation_issuer_mismatch")
    if confirmation.audience != CONFIRMATION_AUDIENCE:
        raise OpsAccessDenied("confirmation_audience_mismatch")
    if confirmation.plan_id != plan.plan_id:
        raise OpsAccessDenied("confirmation_plan_mismatch")
    if confirmation.confirmed_by != principal.subject:
        raise OpsAccessDenied("confirmation_principal_mismatch")
    methods = confirmation.authn_methods
    if (
        not isinstance(methods, Sequence)
        or isinstance(methods, (str, bytes, bytearray))
        or not methods
        or len(methods) > 8
        or any(not isinstance(method, str) for method in methods)
        or len(set(methods)) != len(methods)
    ):
        raise OpsAccessDenied("confirmation_authn_methods_invalid")
    try:
        for method in methods:
            require_identifier(method, "confirmation_authn_method")
    except OpsContractError:
        raise OpsAccessDenied("confirmation_authn_methods_invalid") from None
    if "mfa" not in methods:
        raise OpsAccessDenied("confirmation_mfa_required")
    if confirmation.decision != "approved":
        raise OpsAccessDenied("maintenance_not_confirmed")
    try:
        require_identifier(confirmation.confirmation_id, "confirmation_id")
    except OpsContractError:
        raise OpsAccessDenied("confirmation_nonce_invalid") from None
    issued_at = confirmation.issued_at_epoch_seconds
    expires_at = confirmation.expires_at_epoch_seconds
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
        raise OpsAccessDenied("confirmation_time_window_invalid")


def _read_clock(clock: Callable[[], float]) -> int:
    try:
        now_value = clock()
    except Exception:
        raise OpsContractError("maintenance_clock_invalid") from None
    if (
        isinstance(now_value, bool)
        or not isinstance(now_value, (int, float))
        or not math.isfinite(float(now_value))
        or now_value < 0
    ):
        raise OpsContractError("maintenance_clock_invalid")
    return int(now_value)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
