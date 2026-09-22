#!/usr/bin/env python3
"""Structured client for sanitized aggregate quality and capacity metrics."""

from __future__ import annotations

from typing import Any, Mapping

from lib.ops_contract import (
    StructuredTransport,
    VerifiedPrincipal,
    authorize_ops_principal,
    invoke_read_only,
    require_enum,
    require_identifier,
)


DASHBOARD_OPERATIONS = (
    "dashboard.quality",
    "dashboard.latency",
    "dashboard.errors",
    "dashboard.capacity",
    "dashboard.provider_budget",
    "dashboard.job_status",
)

_RESPONSE_FIELDS = {
    "dashboard.quality": (
        "window",
        "request_count",
        "route_counts",
        "degraded_count",
        "degraded_rate",
        "evidence_bound_rate",
        "false_verified_count",
        "status_code",
        "diagnostic_codes",
    ),
    "dashboard.latency": (
        "window",
        "request_count",
        "latency_ms_by_route",
        "status_code",
        "diagnostic_codes",
    ),
    "dashboard.errors": (
        "window",
        "request_count",
        "error_counts",
        "degraded_reason_counts",
        "status_code",
        "diagnostic_codes",
    ),
    "dashboard.capacity": (
        "authority_chunk_count",
        "bm25_entry_count",
        "chunk_vector_count",
        "entity_vector_count",
        "graph_entity_count",
        "disk_utilization_percent",
        "status_code",
        "diagnostic_codes",
    ),
    "dashboard.provider_budget": (
        "window",
        "role_usage",
        "aggregate_calls",
        "aggregate_cost_microunits",
        "aggregate_budget_microunits",
        "status_code",
        "diagnostic_codes",
    ),
    "dashboard.job_status": (
        "job_id",
        "job_type",
        "job_status",
        "candidate_release_id",
        "receipt_sha256",
        "status_code",
        "diagnostic_codes",
    ),
}


class QualityDashboardClient:
    """Return aggregate telemetry only; raw traces and questions fail closed."""

    def __init__(self, *, principal: VerifiedPrincipal, transport: StructuredTransport):
        self._principal = principal
        self._transport = transport

    def list_tools(self) -> tuple[str, ...]:
        authorize_ops_principal(self._principal, required_role="ops-observer")
        return DASHBOARD_OPERATIONS

    def quality(self, *, window: str) -> dict[str, Any]:
        return self._windowed("dashboard.quality", window)

    def latency(self, *, window: str) -> dict[str, Any]:
        return self._windowed("dashboard.latency", window)

    def errors(self, *, window: str) -> dict[str, Any]:
        return self._windowed("dashboard.errors", window)

    def capacity(self) -> dict[str, Any]:
        return self._invoke("dashboard.capacity", {})

    def provider_budget(self, *, window: str) -> dict[str, Any]:
        return self._windowed("dashboard.provider_budget", window)

    def job_status(self, *, job_id: str) -> dict[str, Any]:
        return self._invoke(
            "dashboard.job_status",
            {"job_id": require_identifier(job_id, "job_id")},
        )

    def _windowed(self, operation: str, window: str) -> dict[str, Any]:
        return self._invoke(
            operation,
            {"window": require_enum(window, "window", ("1h", "24h", "7d", "30d"))},
        )

    def _invoke(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return invoke_read_only(
            principal=self._principal,
            transport=self._transport,
            operation=operation,
            payload=payload,
            allowed_operations=DASHBOARD_OPERATIONS,
            response_fields=_RESPONSE_FIELDS[operation],
        )
