#!/usr/bin/env python3
"""Structured read-only client for hybrid architecture and release audits."""

from __future__ import annotations

from typing import Any, Mapping

from lib.ops_contract import (
    StructuredTransport,
    VerifiedPrincipal,
    authorize_ops_principal,
    invoke_read_only,
    require_enum,
)


AUDIT_OPERATIONS = (
    "audit.authority_identity",
    "audit.retrieval_identity",
    "audit.graph_identity",
    "audit.route_summary",
    "audit.release_identity",
)

_RESPONSE_FIELDS = {
    "audit.authority_identity": (
        "authority_release_id",
        "authority_sha256",
        "document_count",
        "chunk_count",
        "status_code",
        "diagnostic_codes",
    ),
    "audit.retrieval_identity": (
        "bm25_manifest_sha256",
        "chunk_vector_manifest_sha256",
        "entity_vector_manifest_sha256",
        "bm25_entry_count",
        "chunk_vector_count",
        "entity_vector_count",
        "status_code",
        "diagnostic_codes",
    ),
    "audit.graph_identity": (
        "graph_release_id",
        "graph_manifest_sha256",
        "document_count",
        "entity_count",
        "relation_count",
        "status_code",
        "diagnostic_codes",
    ),
    "audit.route_summary": (
        "window",
        "request_count",
        "route_counts",
        "degraded_count",
        "status_code",
        "diagnostic_codes",
    ),
    "audit.release_identity": (
        "code_image_digest",
        "data_release_id",
        "authority_sha256",
        "app_host_contract_sha256",
        "server_model_set_sha256",
        "embedding_manifest_sha256",
        "local_vector_manifest_sha256",
        "graph_manifest_sha256",
        "operator_companion_identity",
        "status_code",
        "diagnostic_codes",
    ),
}


class HybridAuditClient:
    """Expose only named read-only audit operations to the ops Agent."""

    def __init__(self, *, principal: VerifiedPrincipal, transport: StructuredTransport):
        self._principal = principal
        self._transport = transport

    def list_tools(self) -> tuple[str, ...]:
        authorize_ops_principal(self._principal, required_role="ops-observer")
        return AUDIT_OPERATIONS

    def authority_identity(self) -> dict[str, Any]:
        return self._invoke("audit.authority_identity", {})

    def retrieval_identity(self) -> dict[str, Any]:
        return self._invoke("audit.retrieval_identity", {})

    def graph_identity(self) -> dict[str, Any]:
        return self._invoke("audit.graph_identity", {})

    def route_summary(self, *, window: str) -> dict[str, Any]:
        return self._invoke(
            "audit.route_summary",
            {"window": require_enum(window, "window", ("1h", "24h", "7d"))},
        )

    def release_identity(self) -> dict[str, Any]:
        return self._invoke("audit.release_identity", {})

    def _invoke(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return invoke_read_only(
            principal=self._principal,
            transport=self._transport,
            operation=operation,
            payload=payload,
            allowed_operations=AUDIT_OPERATIONS,
            response_fields=_RESPONSE_FIELDS[operation],
        )
