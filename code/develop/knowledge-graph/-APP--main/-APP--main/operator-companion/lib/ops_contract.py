#!/usr/bin/env python3
"""Fail-closed identity and transport contract for private ops tools."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


OPS_AUDIENCE = "ops-admin-agent"
OPS_SERVICE_ACCOUNT = "ops-admin-agent"
OPS_TOKEN_KIND = "ops-admin-access"
OPS_NETWORK_ZONE = "private-admin"
OPS_REQUIRED_AUTHN_METHODS = frozenset({"mfa", "mtls", "oidc"})
REQUEST_SCHEMA_VERSION = "ops-structured-request-v1"
RESULT_SCHEMA_VERSION = "ops-structured-result-v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "command",
        "command_output",
        "conversation",
        "credential",
        "cypher",
        "knowledge_text",
        "password",
        "prompt",
        "provider_payload",
        "provider_secret",
        "query",
        "raw_provider_payload",
        "raw_trace",
        "secret",
        "shell",
        "source_text",
        "sql",
        "stderr",
        "stdout",
        "token",
        "user_question",
    }
)


class OpsAccessDenied(PermissionError):
    """The verified caller is not an ops principal for this capability."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class OpsContractError(ValueError):
    """A request or response violates the fixed structured contract."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class VerifiedPrincipal:
    """Claims already verified by the private gateway, never by prompt text."""

    subject: str
    audience: str
    service_account: str
    token_kind: str
    network_zone: str
    authn_methods: tuple[str, ...]
    roles: tuple[str, ...]


@dataclass(frozen=True)
class StructuredRequest:
    """Operation request passed to an injected transport without URL or token data."""

    operation: str
    principal_subject: str
    payload: Mapping[str, Any]
    schema_version: str = REQUEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "principal_subject": self.principal_subject,
            "payload": _json_object(self.payload, field="payload"),
        }


class StructuredTransport(Protocol):
    """Deployment-owned private transport; tests inject an in-memory fake."""

    def invoke(
        self,
        request: StructuredRequest,
        *,
        verified_maintenance_confirmation: object | None = None,
    ) -> Mapping[str, Any]:
        ...


def authorize_ops_principal(
    principal: VerifiedPrincipal,
    *,
    required_role: str,
) -> None:
    if not isinstance(principal, VerifiedPrincipal):
        raise OpsAccessDenied("verified_principal_required")
    if principal.audience != OPS_AUDIENCE:
        raise OpsAccessDenied("ops_audience_required")
    if principal.service_account != OPS_SERVICE_ACCOUNT:
        raise OpsAccessDenied("ops_service_account_required")
    if principal.token_kind != OPS_TOKEN_KIND:
        raise OpsAccessDenied("ops_token_required")
    if principal.network_zone != OPS_NETWORK_ZONE:
        raise OpsAccessDenied("private_admin_network_required")
    if not OPS_REQUIRED_AUTHN_METHODS.issubset(principal.authn_methods):
        raise OpsAccessDenied("ops_authn_methods_required")
    if required_role not in principal.roles:
        raise OpsAccessDenied("ops_role_required")
    require_identifier(principal.subject, "principal_subject")


def authorize_ops_route(
    principal: VerifiedPrincipal,
    route: str,
    *,
    required_role: str = "ops-observer",
) -> None:
    """Authorize a canonical private route; prompt text is intentionally absent."""
    if (
        not isinstance(route, str)
        or not route.startswith("/ops/")
        or "\\" in route
        or "?" in route
        or "#" in route
        or "//" in route
        or any(part in {"", ".", ".."} for part in route.split("/")[2:])
    ):
        raise OpsAccessDenied("canonical_ops_route_required")
    authorize_ops_principal(principal, required_role=required_role)


def require_exact_fields(
    value: Mapping[str, Any],
    *,
    required: Sequence[str],
    optional: Sequence[str] = (),
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OpsContractError(f"{field}_must_be_object")
    required_set = set(required)
    allowed = required_set | set(optional)
    present = set(value)
    missing = sorted(required_set - present)
    unknown = sorted(present - allowed)
    if missing:
        raise OpsContractError(f"{field}_missing_fields")
    if unknown:
        raise OpsContractError(f"{field}_unknown_fields")
    return _json_object(value, field=field)


def require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise OpsContractError(f"invalid_{field}")
    return value


def require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise OpsContractError(f"invalid_{field}")
    return value


def require_enum(value: Any, field: str, allowed: Sequence[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise OpsContractError(f"invalid_{field}")
    return value


def require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise OpsContractError(f"invalid_{field}")
    return value


def invoke_read_only(
    *,
    principal: VerifiedPrincipal,
    transport: StructuredTransport,
    operation: str,
    payload: Mapping[str, Any],
    allowed_operations: Sequence[str],
    response_fields: Sequence[str],
) -> dict[str, Any]:
    authorize_ops_principal(principal, required_role="ops-observer")
    if operation not in allowed_operations:
        raise OpsContractError("operation_not_allowlisted")
    request = StructuredRequest(
        operation=operation,
        principal_subject=principal.subject,
        payload=_json_object(payload, field="payload"),
    )
    return invoke_transport(
        transport=transport,
        request=request,
        response_fields=response_fields,
        required_ok_fields=response_fields,
    )


def invoke_transport(
    *,
    transport: StructuredTransport,
    request: StructuredRequest,
    response_fields: Sequence[str],
    required_ok_fields: Sequence[str] | None = None,
    verified_maintenance_confirmation: object | None = None,
) -> dict[str, Any]:
    invoke = getattr(transport, "invoke", None)
    if not callable(invoke):
        raise OpsContractError("structured_transport_required")
    try:
        if verified_maintenance_confirmation is None:
            response = invoke(request)
        else:
            response = invoke(
                request,
                verified_maintenance_confirmation=verified_maintenance_confirmation,
            )
    except Exception:
        raise OpsContractError("structured_transport_failed") from None
    envelope = require_exact_fields(
        response,
        required=("schema_version", "operation", "status", "request_id", "data"),
        field="response",
    )
    if envelope["schema_version"] != RESULT_SCHEMA_VERSION:
        raise OpsContractError("response_schema_mismatch")
    if envelope["operation"] != request.operation:
        raise OpsContractError("response_operation_mismatch")
    status = require_enum(
        envelope["status"], "response_status", ("ok", "degraded", "failed")
    )
    require_identifier(envelope["request_id"], "request_id")
    data = require_exact_fields(
        envelope["data"],
        required=tuple(required_ok_fields or ()) if status == "ok" else (),
        optional=response_fields,
        field="response_data",
    )
    _validate_sanitized_response(data)
    envelope["data"] = data
    return envelope


def _json_object(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise OpsContractError(f"{field}_must_be_json_object")
    try:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise OpsContractError(f"{field}_must_be_json") from exc
    if not isinstance(decoded, dict):
        raise OpsContractError(f"{field}_must_be_json_object")
    if len(encoded.encode("utf-8")) > 64 * 1024:
        raise OpsContractError(f"{field}_too_large")
    return decoded


def _validate_sanitized_response(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_RESPONSE_KEYS or normalized.startswith("raw_"):
                raise OpsContractError("sensitive_response_field")
            if _IDENTIFIER.fullmatch(normalized) is None:
                raise OpsContractError("invalid_response_field")
            _validate_sanitized_response(nested)
    elif isinstance(value, list):
        if len(value) > 1024:
            raise OpsContractError("response_list_too_large")
        for nested in value:
            _validate_sanitized_response(nested)
    elif isinstance(value, str):
        if _IDENTIFIER.fullmatch(value) is None:
            raise OpsContractError("non_structured_response_text")
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, int):
        if value < 0:
            raise OpsContractError("negative_response_value")
    elif isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            raise OpsContractError("invalid_response_number")
    else:
        raise OpsContractError("invalid_response_value")
