#!/usr/bin/env python3
"""Private ops route facade over sanitized, explicitly injected handlers."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Callable, Mapping

from .identity_policy import (
    AccessDenied,
    VerifiedIdentity,
    VerifiedMaintenanceConfirmation,
    authorize_ops,
)


OPS_ROUTES = {
    "/ops/audit/authority": "ops-observer",
    "/ops/audit/release": "ops-observer",
    "/ops/dashboard/quality": "ops-observer",
    "/ops/dashboard/capacity": "ops-observer",
    "/ops/maintenance/jobs": "ops-maintainer",
}
OpsHandler = Callable[
    [VerifiedIdentity, Mapping[str, Any], VerifiedMaintenanceConfirmation | None],
    Any,
]
MAX_SANITIZED_RESPONSE_BYTES = 64 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
FORBIDDEN_RESPONSE_FIELDS = frozenset(
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


class OpsServiceError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _sanitized(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise OpsServiceError("response_key_must_be_string")
            normalized = key.strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_RESPONSE_FIELDS or normalized.startswith("raw_"):
                raise OpsServiceError("sensitive_response_field")
            if _IDENTIFIER.fullmatch(normalized) is None:
                raise OpsServiceError("invalid_response_field")
            result[key] = _sanitized(nested)
        return result
    if isinstance(value, list):
        if len(value) > 1024:
            raise OpsServiceError("response_list_too_large")
        return [_sanitized(item) for item in value]
    if isinstance(value, str):
        if _IDENTIFIER.fullmatch(value) is None:
            raise OpsServiceError("non_structured_response_text")
        return value
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value < 0:
            raise OpsServiceError("negative_response_value")
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            raise OpsServiceError("invalid_response_number")
        return value
    raise OpsServiceError("response_value_not_sanitized")


class OpsService:
    def __init__(self, handlers: Mapping[str, OpsHandler]) -> None:
        if set(handlers) != set(OPS_ROUTES) or any(not callable(value) for value in handlers.values()):
            raise OpsServiceError("ops_handler_registry_mismatch")
        self._handlers = dict(handlers)

    def handle(
        self,
        identity: VerifiedIdentity,
        route: str,
        body: Mapping[str, Any],
        maintenance_confirmation: VerifiedMaintenanceConfirmation | None = None,
    ) -> dict[str, Any]:
        role = OPS_ROUTES.get(route)
        if role is None:
            raise OpsServiceError("ops_route_not_allowlisted")
        authorize_ops(identity, route, required_role=role)
        if route == "/ops/maintenance/jobs":
            if not isinstance(
                maintenance_confirmation, VerifiedMaintenanceConfirmation
            ):
                raise AccessDenied("verified_maintenance_confirmation_required")
        elif maintenance_confirmation is not None:
            raise AccessDenied("maintenance_confirmation_route_mismatch")
        if not isinstance(body, Mapping):
            raise OpsServiceError("request_body_must_be_object")
        try:
            normalized_body = json.loads(
                json.dumps(body, ensure_ascii=True, sort_keys=True, allow_nan=False)
            )
        except (TypeError, ValueError) as exc:
            raise OpsServiceError("request_body_must_be_json") from exc
        response = _sanitized(
            self._handlers[route](identity, normalized_body, maintenance_confirmation)
        )
        if not isinstance(response, dict):
            raise OpsServiceError("ops_response_must_be_object")
        encoded_response = json.dumps(
            response, ensure_ascii=True, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        if len(encoded_response) > MAX_SANITIZED_RESPONSE_BYTES:
            raise OpsServiceError("ops_response_too_large")
        return {
            "schema_version": "cloud-v2-ops-response-v1",
            "status": "ok",
            "data": response,
        }
