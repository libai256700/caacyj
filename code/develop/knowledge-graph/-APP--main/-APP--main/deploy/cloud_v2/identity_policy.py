#!/usr/bin/env python3
"""Server-side public/ops identity, audience, and route separation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


PUBLIC_AUDIENCE = "public-app-agent"
OPS_AUDIENCE = "ops-admin-agent"
OPS_REQUIRED_AUTHN_METHODS = frozenset({"mfa", "mtls", "oidc"})
VERIFIED_IDENTITY_ENVIRON_KEY = "kg.verified_identity"
VERIFIED_MAINTENANCE_CONFIRMATION_ENVIRON_KEY = (
    "kg.verified_maintenance_confirmation"
)
MAINTENANCE_CONFIRMATION_SCHEMA_VERSION = "maintenance-confirmation-v2"
MAINTENANCE_CONFIRMATION_ISSUER = "private-admin-confirmation-gateway"


class AccessDenied(PermissionError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class VerifiedIdentity:
    """Claims already verified by TLS/OIDC infrastructure outside prompt text."""

    subject: str
    audience: str
    service_account: str
    token_kind: str
    network_zone: str
    authn_methods: tuple[str, ...]
    roles: tuple[str, ...]


@dataclass(frozen=True)
class VerifiedMaintenanceConfirmation:
    """Short-lived confirmation claims installed by trusted WSGI middleware."""

    issuer: str
    audience: str
    plan_id: str
    confirmation_id: str
    confirmed_by: str
    authn_methods: tuple[str, ...]
    decision: str
    issued_at_epoch_seconds: int
    expires_at_epoch_seconds: int
    schema_version: str = MAINTENANCE_CONFIRMATION_SCHEMA_VERSION

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


def verified_identity_from_wsgi_environ(
    environ: Mapping[str, Any],
) -> VerifiedIdentity:
    """Read only the object installed by trusted WSGI authentication middleware."""

    if not isinstance(environ, Mapping):
        raise AccessDenied("trusted_wsgi_environ_required")
    identity = environ.get(VERIFIED_IDENTITY_ENVIRON_KEY)
    if not isinstance(identity, VerifiedIdentity):
        raise AccessDenied("verified_identity_required")
    return identity


def verified_maintenance_confirmation_from_wsgi_environ(
    environ: Mapping[str, Any],
) -> VerifiedMaintenanceConfirmation:
    """Accept only the typed object installed by confirmation middleware."""

    if not isinstance(environ, Mapping):
        raise AccessDenied("trusted_wsgi_environ_required")
    confirmation = environ.get(VERIFIED_MAINTENANCE_CONFIRMATION_ENVIRON_KEY)
    if not isinstance(confirmation, VerifiedMaintenanceConfirmation):
        raise AccessDenied("verified_maintenance_confirmation_required")
    return confirmation


def _canonical_route(route: str) -> str:
    if (
        not isinstance(route, str)
        or not route.startswith("/")
        or "\\" in route
        or "?" in route
        or "#" in route
        or "//" in route
        or any(part in {"", ".", ".."} for part in route.split("/")[1:])
    ):
        raise AccessDenied("canonical_route_required")
    return route


def authorize_public_ask(identity: VerifiedIdentity, route: str) -> None:
    if not isinstance(identity, VerifiedIdentity):
        raise AccessDenied("verified_identity_required")
    if _canonical_route(route) != "/api/ask":
        raise AccessDenied("public_route_not_allowed")
    if identity.audience != PUBLIC_AUDIENCE:
        raise AccessDenied("public_audience_required")
    if identity.service_account != PUBLIC_AUDIENCE:
        raise AccessDenied("public_service_account_required")
    if identity.token_kind != "public-app-access":
        raise AccessDenied("public_token_required")
    if identity.network_zone != "public-app":
        raise AccessDenied("public_network_required")
    if "app-user" not in identity.roles:
        raise AccessDenied("public_role_required")


def authorize_ops(identity: VerifiedIdentity, route: str, *, required_role: str) -> None:
    if not isinstance(identity, VerifiedIdentity):
        raise AccessDenied("verified_identity_required")
    route = _canonical_route(route)
    if not route.startswith("/ops/"):
        raise AccessDenied("ops_route_required")
    if identity.audience != OPS_AUDIENCE:
        raise AccessDenied("ops_audience_required")
    if identity.service_account != OPS_AUDIENCE:
        raise AccessDenied("ops_service_account_required")
    if identity.token_kind != "ops-admin-access":
        raise AccessDenied("ops_token_required")
    if identity.network_zone != "private-admin":
        raise AccessDenied("private_admin_network_required")
    if not OPS_REQUIRED_AUTHN_METHODS.issubset(identity.authn_methods):
        raise AccessDenied("ops_authn_methods_required")
    if required_role not in identity.roles:
        raise AccessDenied("ops_role_required")


def public_tool_registry() -> tuple[str, ...]:
    return ("knowledge-graph-cloud",)


def ops_tool_registry() -> tuple[str, ...]:
    return (
        "hybrid-audit-cloud",
        "quality-dashboard-cloud",
        "maintenance-controller-cloud",
    )
