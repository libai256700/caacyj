#!/usr/bin/env python3
"""Private WSGI entrypoint for the isolated ops-admin-agent process."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from .identity_policy import (
    OPS_AUDIENCE,
    AccessDenied,
    VerifiedIdentity,
    VerifiedMaintenanceConfirmation,
    authorize_ops,
    ops_tool_registry,
    verified_identity_from_wsgi_environ,
    verified_maintenance_confirmation_from_wsgi_environ,
)
from .maintenance_jobs import (
    BUILTIN_BACKEND_REGISTRY_ID,
    MAINTENANCE_SUBMIT_SCHEMA_VERSION,
    CandidateWorkspaceBinding,
    CandidateJobRunner,
    MaintenanceJobError,
    maintenance_job_from_submit,
)
from .ops_runtime import (
    OpsRuntimeError,
    ProductionOpsRuntime,
    load_production_ops_runtime_from_environment,
)
from .ops_identity_middleware import create_authenticated_ops_wsgi_app
from .ops_service import OPS_ROUTES, OpsHandler, OpsService, OpsServiceError


OPS_ENTRYPOINT_SCHEMA_VERSION = "cloud-v2-ops-entrypoint-v1"
OPS_ENTRYPOINT_ID = "ops-admin-agent-wsgi-v1"
OPS_HANDLER_MODE_ENV = "KG_OPS_HANDLER_MODE"
PRODUCTION_HANDLER_MODE = "production-hash-bound"
MAX_OPS_REQUEST_BODY_BYTES = 64 * 1024
_DEFAULT_ALLOWED_HOSTS = (
    "127.0.0.1",
    "127.0.0.1:5101",
    "[::1]",
    "[::1]:5101",
    "localhost",
    "localhost:5101",
)


class OpsEntrypointError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _strict_json_object() -> Mapping[str, Any]:
    if not request.is_json:
        raise OpsEntrypointError("invalid_content_type")
    if (
        request.content_length is not None
        and request.content_length > MAX_OPS_REQUEST_BODY_BYTES
    ):
        raise RequestEntityTooLarge()
    raw = request.stream.read(MAX_OPS_REQUEST_BODY_BYTES + 1)
    if len(raw) > MAX_OPS_REQUEST_BODY_BYTES:
        raise RequestEntityTooLarge()

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("non-finite JSON number")
            ),
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise OpsEntrypointError("invalid_json") from exc
    if not isinstance(value, Mapping):
        raise OpsEntrypointError("request_body_must_be_object")
    return value


def _allowed_hosts() -> frozenset[str]:
    raw = os.getenv("KG_OPS_ALLOWED_HOSTS")
    values = _DEFAULT_ALLOWED_HOSTS if raw is None else tuple(raw.split(","))
    return frozenset(item.strip().lower() for item in values if item.strip())


def _normalize_allowed_hosts(values: Sequence[str]) -> frozenset[str]:
    if isinstance(values, (str, bytes, bytearray)):
        raise OpsEntrypointError("allowed_hosts_invalid")
    normalized = tuple(
        item.strip().lower()
        for item in values
        if isinstance(item, str) and item.strip()
    )
    if len(normalized) != len(values) or not normalized:
        raise OpsEntrypointError("allowed_hosts_invalid")
    return frozenset(normalized)


def create_ops_app(
    handlers: Mapping[str, OpsHandler],
    *,
    verified_identity_loader: Callable[[Mapping[str, Any]], VerifiedIdentity]
    | None = None,
    verified_confirmation_loader: Callable[
        [Mapping[str, Any]], VerifiedMaintenanceConfirmation
    ]
    | None = None,
    handler_mode: str = "injected",
    allowed_hosts: Sequence[str] | None = None,
    process_role: str | None = None,
    real_data_access: bool = False,
    maintenance_runner_bridge: str = "injected-candidate-job-runner-v2",
) -> Flask:
    """Create the private app without opening data, sockets, or provider clients."""

    service = OpsService(handlers)
    load_identity = verified_identity_loader or verified_identity_from_wsgi_environ
    load_confirmation = (
        verified_confirmation_loader
        or verified_maintenance_confirmation_from_wsgi_environ
    )
    accepted_hosts = (
        _allowed_hosts()
        if allowed_hosts is None
        else _normalize_allowed_hosts(allowed_hosts)
    )
    configured_process_role = process_role or os.getenv("KG_PROCESS_ROLE")
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = MAX_OPS_REQUEST_BODY_BYTES
    app.extensions["ops_entrypoint_contract"] = {
        "schema_version": OPS_ENTRYPOINT_SCHEMA_VERSION,
        "entrypoint_id": OPS_ENTRYPOINT_ID,
        "process_role": OPS_AUDIENCE,
        "network_zone": "private-admin",
        "route_prefix": "/ops/",
        "routes": tuple(sorted(OPS_ROUTES)),
        "tool_registry": ops_tool_registry(),
        "handler_mode": handler_mode,
        "handler_identity_contract": (
            "verified-identity-and-maintenance-confirmation-plus-json-body-v2"
        ),
        "maintenance_submit_schema": MAINTENANCE_SUBMIT_SCHEMA_VERSION,
        "maintenance_runner_bridge": maintenance_runner_bridge,
        "real_data_access": real_data_access,
        "network_calls": 0,
        "public_app_discoverable": False,
        "public_routes": (),
    }

    @app.errorhandler(RequestEntityTooLarge)
    def request_body_too_large(_error: RequestEntityTooLarge):
        return jsonify({"error": "request_body_too_large", "request_rejected": True}), 413

    @app.before_request
    def guard_private_surface():
        if configured_process_role != OPS_AUDIENCE:
            return jsonify(
                {"error": "ops_process_unavailable", "request_rejected": True}
            ), 503
        if request.path not in OPS_ROUTES:
            return jsonify({"error": "not_found"}), 404
        if str(request.host or "").lower() not in accepted_hosts:
            return jsonify({"error": "forbidden_host", "request_rejected": True}), 403
        try:
            identity = load_identity(request.environ)
            authorize_ops(
                identity,
                request.path,
                required_role=OPS_ROUTES[request.path],
            )
            g.verified_identity = identity
            g.verified_maintenance_confirmation = (
                load_confirmation(request.environ)
                if request.path == "/ops/maintenance/jobs"
                else None
            )
        except Exception:
            return jsonify({"error": "access_denied", "request_rejected": True}), 403
        return None

    def view_for(route: str):
        def view():
            try:
                body = _strict_json_object()
            except RequestEntityTooLarge:
                raise
            except OpsEntrypointError as exc:
                return jsonify({"error": exc.code, "request_rejected": True}), 400
            try:
                result = service.handle(
                    g.verified_identity,
                    route,
                    body,
                    g.verified_maintenance_confirmation,
                )
            except AccessDenied:
                return jsonify({"error": "access_denied", "request_rejected": True}), 403
            except OpsServiceError as exc:
                return jsonify({"error": exc.code, "request_rejected": True}), 400
            except OpsRuntimeError:
                return jsonify(
                    {"error": "ops_request_rejected", "request_rejected": True}
                ), 400
            except Exception:
                return jsonify(
                    {"error": "ops_handler_unavailable", "request_rejected": True}
                ), 503
            return jsonify(result), 200

        view.__name__ = "handle_" + route.removeprefix("/ops/").replace("/", "_")
        return view

    for ops_route in sorted(OPS_ROUTES):
        app.add_url_rule(
            ops_route,
            endpoint="ops_" + ops_route.removeprefix("/ops/").replace("/", "_"),
            view_func=view_for(ops_route),
            methods=("POST",),
        )
    return app


def create_maintenance_job_handler(
    runner: CandidateJobRunner,
    *,
    workspace_root: str | Path,
) -> OpsHandler:
    """Bind the maintenance route to a deployment-owned candidate workspace."""

    if not isinstance(runner, CandidateJobRunner):
        raise OpsEntrypointError("candidate_job_runner_required")
    try:
        workspace = CandidateWorkspaceBinding(workspace_root)
    except MaintenanceJobError as exc:
        raise OpsEntrypointError(exc.code) from None

    def handle(
        identity: VerifiedIdentity,
        body: Mapping[str, Any],
        confirmation: VerifiedMaintenanceConfirmation | None,
    ) -> Any:
        try:
            if not isinstance(confirmation, VerifiedMaintenanceConfirmation):
                raise MaintenanceJobError("verified_confirmation_required")
            job = maintenance_job_from_submit(
                body,
                verified_confirmation=confirmation,
            )
            return runner.submit(job, workspace=workspace, identity=identity)
        except MaintenanceJobError:
            raise OpsServiceError("maintenance_job_rejected") from None

    return handle


def _production_maintenance_handler(runtime: ProductionOpsRuntime) -> OpsHandler:
    def handle(
        identity: VerifiedIdentity,
        body: Mapping[str, Any],
        confirmation: VerifiedMaintenanceConfirmation | None,
    ) -> dict[str, Any]:
        try:
            if not isinstance(confirmation, VerifiedMaintenanceConfirmation):
                raise MaintenanceJobError("verified_confirmation_required")
            runtime.verify_active_bindings()
            job = maintenance_job_from_submit(
                body,
                verified_confirmation=confirmation,
            )
            raw = runtime.runner.submit(
                job,
                workspace=runtime.workspace,
                identity=identity,
            )
        except MaintenanceJobError:
            raise OpsServiceError("maintenance_job_rejected") from None
        if (
            raw.get("status") != "candidate-job-planned"
            or raw.get("job_status") != "planned"
            or raw.get("active_write") is not False
            or raw.get("release_switch") is not False
        ):
            raise OpsServiceError("maintenance_backend_contract_mismatch")
        result = {
            "job_id": raw.get("job_id"),
            "job_type": raw.get("job_type"),
            "job_status": "planned",
            "receipt_sha256": raw.get("receipt_sha256"),
            "status_code": "candidate_plan_created",
            "diagnostic_codes": ["execution_not_authorized", "active_unchanged"],
        }
        candidate_release_id = job.parameters.get("candidate_release_id")
        if isinstance(candidate_release_id, str):
            result["candidate_release_id"] = candidate_release_id
        return result

    return handle


def create_production_ops_app() -> Flask:
    """Eagerly bind the private app to one approved production runtime."""

    if os.getenv("KG_PROCESS_ROLE") != OPS_AUDIENCE:
        raise OpsEntrypointError("ops_process_role_required")
    if os.getenv(OPS_HANDLER_MODE_ENV) is not None:
        raise OpsEntrypointError("legacy_or_fake_ops_handler_mode_forbidden")

    def create_bound_application() -> Flask:
        runtime = load_production_ops_runtime_from_environment()
        handlers = runtime.read_handlers()
        handlers["/ops/maintenance/jobs"] = _production_maintenance_handler(runtime)
        application = create_ops_app(
            handlers,
            handler_mode=PRODUCTION_HANDLER_MODE,
            allowed_hosts=runtime.config.allowed_hosts,
            process_role=OPS_AUDIENCE,
            real_data_access=True,
            maintenance_runner_bridge=BUILTIN_BACKEND_REGISTRY_ID,
        )
        application.extensions["production_ops_runtime"] = runtime
        return application

    application = create_authenticated_ops_wsgi_app(create_bound_application)
    if not isinstance(application, Flask):
        raise OpsEntrypointError("ops_authenticated_wsgi_application_invalid")
    return application


def main() -> int:
    from waitress import serve as waitress_serve

    application = create_production_ops_app()
    runtime = application.extensions["production_ops_runtime"]
    waitress_serve(
        application,
        host=runtime.config.listen_host,
        port=runtime.config.listen_port,
        threads=runtime.config.listen_threads,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
