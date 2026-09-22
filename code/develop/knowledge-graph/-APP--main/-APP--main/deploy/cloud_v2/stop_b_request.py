#!/usr/bin/env python3
"""Closed, fail-closed Stop B request validation.

The checked-in document is a non-authorizing template.  ``approval_ready``
validation is intentionally stricter: it proves that every external role,
data-class request, cost ceiling, local-vector target, and Phase 1 receipt has
been materialized before the request can be shown for a Stop B decision.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit


SCHEMA_VERSION = "cloud-v2-stop-b-external-processing-request-v4"
SCHEMA_RELATIVE_PATH = "deploy/cloud_v2/stop-b-external-processing-request.schema.json"
REQUEST_RELATIVE_PATH = "STOP_B_EXTERNAL_PROCESSING_REQUEST.json"
FIXTURE_RELATIVE_PATH = "deploy/cloud_v2/stop-b-synthetic-probes.json"
FIXTURE_SHA256 = "b4e61988c9293425f87db47d96bc777840f9f4e216ffbe7b4deb88413b535f61"
REQUEST_SET_SHA256 = "68449564e254ef45753b8e710abcae678a5fa8ec4fc0037edab40649afd4353c"
DERIVED_CANDIDATE_ROOT = "artifacts/candidates/revision-a-r9/ollama-bge-m3-r1"
PRODUCTION_DATA_FILES = (
    (
        "authority/authority-manifest.json",
        "964658ce8e3a4a94735a9ea78df158d2a588f399d6ff26bc28a417007cfef067",
    ),
    (
        "authority/rag_chunks.db",
        "3a08cf106d6410c8780bd4a0eb001c36c154c2459feb0427e5a2d1a20c68cf9a",
    ),
    (
        "derived/bm25-manifest.json",
        "ef49bfd1e1b18bfb9d6114c368923ba9f134bad9b82ead32d8fb4b48b0a3445a",
    ),
    (
        "derived/bm25.sqlite3",
        "ba5f8ca8ea5e7b5000b347bdafbfb6ef60e4aa9253998a32b120c89381edd19f",
    ),
    (
        "derived/graph/graph-manifest.json",
        "99b14e62a4b26cfc0fb2291c3440d6641ed9c2a1ff43d959e250b52f6c44b120",
    ),
    (
        "derived/graph/scoped-graph.jsonl",
        "dd519665c574a6d93f80dc12800a9a986cbd24f5d372748e66408b98e8bde256",
    ),
)
PRODUCTION_DATA_FILE_SET_SHA256 = (
    "e860ee88bb86967ef2f8bbcca22c8dc3c5e4de9e07a7a2811487348dd243fe73"
)

DATA_CLASS_IDS = (
    "synthetic_probe",
    "redacted_r9_chunk_and_entity_embedding",
    "online_query",
    "app_user_session",
    "ops_aggregate_metrics",
)
ROLE_KINDS = frozenset(
    {"app_host_final_answer", "server_answer", "embedding", "ops_agent"}
)
REQUIRED_PHASE1_EVIDENCE_LABELS = (
    "app-package-receipt",
    "app-package-verification",
    "code-manifest-verification",
    "disclosure-evidence",
    "final-suite-dlp-receipt",
    "offline-test-component-set",
    "offline-test-logs",
    "offline-test-receipt",
    "phase1-dlp-receipt",
    "suite-build-receipt",
    "suite-verification",
)
EXPLICIT_NON_AUTHORIZATIONS = (
    "real-provider-call",
    "commit",
    "push",
    "upload",
    "publish",
    "release",
    "deploy",
    "restart",
    "traffic-switch",
    "production-write",
    "cleanup",
)
TEMPLATE_BLOCKING_REASONS = (
    "coordinator-contract-pending",
    "data-class-decisions-pending",
    "provider-role-bindings-pending",
    "synthetic-probe-cost-and-output-pending",
)

_HEX = frozenset("0123456789abcdef")
_TOP_LEVEL_KEYS = {
    "$schema",
    "schema_version",
    "status",
    "request_scope",
    "current_maximum_state",
    "approval_readiness",
    "role_cardinality",
    "role_instances",
    "region_policy",
    "data_class_decisions",
    "server_answer_coordinator",
    "synthetic_probe",
    "provider_specific_wire_compilation",
    "local_vector_contract",
    "phase1_evidence",
    "explicit_non_authorizations",
    "blocking_decisions",
}
_ROLE_KEYS = {
    "role_id",
    "role_kind",
    "ordinal",
    "purpose",
    "provider_contract",
    "endpoint_contract",
    "model_contract",
    "training_contract",
    "retention_contract",
    "deletion_exit_contract",
    "operational_limits",
    "meter_contract",
    "commercial_contract",
    "allowed_data_class_ids",
    "provider_specific_wire_slot_id",
    "evidence_refs",
}
_DATA_DECISION_KEYS = {
    "data_class_id",
    "decision",
    "authorization_status",
    "role_ids",
    "purposes",
    "payload_schema_sha256",
    "field_allowlist",
    "limits",
}
_WIRE_SLOT_KEYS = {
    "slot_id",
    "role_id",
    "semantic_fixture_sha256",
    "provider_neutral_request_set_sha256",
    "provider_contract_sha256",
    "exact_endpoint",
    "model_identity_sha256",
    "policy_sha256",
    "transport_code_sha256",
    "egress_policy_sha256",
    "wire_request_set_sha256",
    "wire_request_total_size_bytes",
    "call_cap",
    "maximum_cost_microunits",
    "currency",
    "expected_output_contract_sha256",
    "compiled_wire_receipt_sha256",
}


class StopBRequestError(ValueError):
    """The request is malformed, unsafe, or not ready for the requested mode."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _strict_json(path: Path) -> Any:
    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StopBRequestError("duplicate_json_key")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                StopBRequestError("non_finite_json_number")
            ),
        )
    except StopBRequestError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StopBRequestError("request_json_unreadable") from exc


def _object(value: object, keys: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise StopBRequestError(f"{field}_closed_schema_mismatch")
    return value


def _array(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise StopBRequestError(f"{field}_must_be_array")
    return value


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise StopBRequestError(f"{field}_must_be_normalized_text")
    return value


def _sha(value: object, field: str) -> str:
    if type(value) is not str or len(value) != 64 or not set(value).issubset(_HEX):
        raise StopBRequestError(f"{field}_must_be_sha256")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise StopBRequestError(f"{field}_must_be_integer_at_least_{minimum}")
    return value


def _boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise StopBRequestError(f"{field}_must_be_boolean")
    return value


def _unique_texts(value: object, field: str) -> tuple[str, ...]:
    items = _array(value, field)
    normalized = tuple(_text(item, field) for item in items)
    if len(normalized) != len(set(normalized)):
        raise StopBRequestError(f"{field}_must_be_unique")
    return normalized


def _https_endpoint(value: object, field: str) -> str:
    endpoint = _text(value, field)
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise StopBRequestError(f"{field}_must_be_exact_https_endpoint")
    return endpoint


def _relative_path(value: object, field: str) -> str:
    raw = _text(value, field)
    if raw.startswith("/") or "\\" in raw or "//" in raw or any(
        character in raw for character in "*?[]{}"
    ):
        raise StopBRequestError(f"{field}_must_be_canonical_relative_path")
    path = PurePosixPath(raw)
    if path.as_posix() != raw or any(part in {"", ".", ".."} for part in path.parts):
        raise StopBRequestError(f"{field}_must_be_canonical_relative_path")
    return path.as_posix()


def _absolute_path(value: object, field: str) -> str:
    raw = _text(value, field)
    if not raw.startswith("/") or "\\" in raw or "//" in raw or any(
        character in raw for character in "*?[]{}"
    ):
        raise StopBRequestError(f"{field}_must_be_exact_absolute_path")
    path = PurePosixPath(raw)
    if path.as_posix() != raw or any(part in {"", ".", ".."} for part in path.parts):
        raise StopBRequestError(f"{field}_must_be_exact_absolute_path")
    return path.as_posix()


def _canonical_json_sha256(value: object) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def load_stop_b_request(
    path: str | Path,
    *,
    mode: str = "template",
) -> Mapping[str, Any]:
    request_path = Path(path)
    value = _strict_json(request_path)
    return validate_stop_b_request(value, mode=mode)


def validate_stop_b_request(
    value: object,
    *,
    mode: str = "template",
) -> Mapping[str, Any]:
    if mode not in {"template", "approval_ready"}:
        raise StopBRequestError("unsupported_validation_mode")
    root = _object(value, _TOP_LEVEL_KEYS, "request")
    if root["$schema"] != SCHEMA_RELATIVE_PATH:
        raise StopBRequestError("schema_path_mismatch")
    if root["schema_version"] != SCHEMA_VERSION:
        raise StopBRequestError("schema_version_mismatch")
    if root["request_scope"] != "stop-b-external-processing-only":
        raise StopBRequestError("request_scope_mismatch")
    if root["current_maximum_state"] != "stop_b_offline_handoff_ready":
        raise StopBRequestError("status_token_mismatch")
    if tuple(root["explicit_non_authorizations"]) != EXPLICIT_NON_AUTHORIZATIONS:
        raise StopBRequestError("explicit_non_authorizations_mismatch")

    readiness = _validate_readiness(root["approval_readiness"], mode)
    cardinality = _validate_cardinality(root["role_cardinality"], mode)
    region = _validate_region_policy(root["region_policy"])
    roles = _validate_roles(root["role_instances"], region)
    decisions = _validate_data_decisions(root["data_class_decisions"], mode)
    coordinator = _validate_coordinator(root["server_answer_coordinator"], mode)
    probe = _validate_synthetic_probe(root["synthetic_probe"], mode)
    wire_slots = _validate_wire_slots(
        root["provider_specific_wire_compilation"], mode
    )
    local_vector = _validate_local_vector(root["local_vector_contract"], mode)
    _validate_phase1_evidence(root["phase1_evidence"], mode)

    blocking = _unique_texts(root["blocking_decisions"], "blocking_decisions")
    if mode == "template":
        if root["status"] != "pending-user-provider-and-deployment-decisions":
            raise StopBRequestError("template_status_mismatch")
        if tuple(readiness["blocking_reason_codes"]) != TEMPLATE_BLOCKING_REASONS:
            raise StopBRequestError("template_blocking_reasons_mismatch")
        if not blocking:
            raise StopBRequestError("template_blocking_decisions_required")
        if roles or wire_slots:
            raise StopBRequestError("template_cannot_bind_roles_or_wire_slots")
        return root

    if root["status"] != "ready-for-user-stop-b-decision":
        raise StopBRequestError("approval_ready_status_mismatch")
    if blocking:
        raise StopBRequestError("approval_ready_cannot_have_blocking_decisions")
    _validate_approval_ready_cross_contract(
        cardinality=cardinality,
        roles=roles,
        decisions=decisions,
        coordinator=coordinator,
        probe=probe,
        wire_slots=wire_slots,
        local_vector=local_vector,
    )
    return root


def _validate_readiness(value: object, mode: str) -> Mapping[str, Any]:
    state = _object(
        value,
        {"mode", "approval_ready", "blocking_reason_codes"},
        "approval_readiness",
    )
    reasons = _unique_texts(
        state["blocking_reason_codes"], "approval_readiness.blocking_reason_codes"
    )
    if state["mode"] != mode or state["approval_ready"] is not (mode == "approval_ready"):
        raise StopBRequestError("approval_readiness_mode_mismatch")
    if mode == "approval_ready" and reasons:
        raise StopBRequestError("approval_ready_has_blocking_reasons")
    if mode == "template" and not reasons:
        raise StopBRequestError("template_requires_blocking_reasons")
    return state


def _validate_cardinality(value: object, mode: str) -> Mapping[str, Any]:
    state = _object(
        value,
        {
            "formula",
            "server_answer_channel_count_N",
            "ops_agent_llm_enabled",
            "ops_agent_model_count_M",
            "materialized_role_count",
        },
        "role_cardinality",
    )
    if state["formula"] != "N+M+2":
        raise StopBRequestError("role_formula_mismatch")
    materialized = _integer(
        state["materialized_role_count"], "materialized_role_count"
    )
    if mode == "template":
        if any(
            state[field] is not None
            for field in (
                "server_answer_channel_count_N",
                "ops_agent_llm_enabled",
                "ops_agent_model_count_M",
            )
        ) or materialized != 0:
            raise StopBRequestError("template_role_cardinality_must_be_unbound")
        return state

    n = _integer(
        state["server_answer_channel_count_N"],
        "server_answer_channel_count_N",
        minimum=1,
    )
    enabled = _boolean(state["ops_agent_llm_enabled"], "ops_agent_llm_enabled")
    m = _integer(state["ops_agent_model_count_M"], "ops_agent_model_count_M")
    if (enabled and m < 1) or (not enabled and m != 0):
        raise StopBRequestError("ops_agent_model_count_inconsistent")
    if materialized != n + m + 2:
        raise StopBRequestError("materialized_role_count_mismatch")
    return state


def _validate_region_policy(value: object) -> Mapping[str, Any]:
    state = _object(
        value,
        {"default", "exception_requires_explicit_stop_b_decision", "exception_decision"},
        "region_policy",
    )
    if state["default"] != "exact-china-region-endpoint-required":
        raise StopBRequestError("region_default_mismatch")
    if state["exception_requires_explicit_stop_b_decision"] is not True:
        raise StopBRequestError("region_exception_gate_missing")
    exception = state["exception_decision"]
    if exception is not None:
        record = _object(
            exception,
            {"decision_id", "reason", "evidence_sha256"},
            "region_exception_decision",
        )
        _text(record["decision_id"], "region_exception_decision_id")
        _text(record["reason"], "region_exception_reason")
        _sha(record["evidence_sha256"], "region_exception_evidence")
    return state


def _validate_roles(
    value: object,
    region_policy: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    records: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    seen_slots: set[str] = set()
    for index, raw in enumerate(_array(value, "role_instances")):
        role = _object(raw, _ROLE_KEYS, f"role_instances_{index}")
        role_id = _text(role["role_id"], "role_id")
        if role_id in seen_ids:
            raise StopBRequestError("duplicate_role_id")
        seen_ids.add(role_id)
        if role["role_kind"] not in ROLE_KINDS:
            raise StopBRequestError("unsupported_role_kind")
        _integer(role["ordinal"], "role_ordinal", minimum=1)
        _text(role["purpose"], "role_purpose")
        _validate_provider_contract(role["provider_contract"])
        endpoint = _validate_endpoint_contract(role["endpoint_contract"])
        if (
            endpoint["china_region_default_satisfied"] is not True
            and region_policy["exception_decision"] is None
        ):
            raise StopBRequestError("non_china_role_requires_region_exception")
        _validate_model_contract(role["model_contract"])
        _validate_training_contract(role["training_contract"])
        _validate_retention_contract(role["retention_contract"])
        _validate_deletion_contract(role["deletion_exit_contract"])
        _validate_operational_limits(role["operational_limits"])
        _validate_meter_contract(role["meter_contract"])
        _validate_commercial_contract(role["commercial_contract"])
        allowed = _unique_texts(role["allowed_data_class_ids"], "allowed_data_class_ids")
        if not set(allowed).issubset(DATA_CLASS_IDS):
            raise StopBRequestError("role_has_unknown_data_class")
        slot_id = _text(
            role["provider_specific_wire_slot_id"], "provider_specific_wire_slot_id"
        )
        if slot_id in seen_slots:
            raise StopBRequestError("duplicate_provider_wire_slot_id")
        seen_slots.add(slot_id)
        _validate_evidence_refs(role["evidence_refs"])
        records.append(role)
    return tuple(records)


def _validate_provider_contract(value: object) -> None:
    record = _object(
        value,
        {
            "provider_legal_entity",
            "service_name",
            "account_contract_principal",
            "account_reference",
        },
        "provider_contract",
    )
    for field in record:
        _text(record[field], f"provider_contract_{field}")


def _validate_endpoint_contract(value: object) -> Mapping[str, Any]:
    record = _object(
        value,
        {"exact_endpoint", "region", "data_residency", "china_region_default_satisfied"},
        "endpoint_contract",
    )
    _https_endpoint(record["exact_endpoint"], "exact_endpoint")
    _text(record["region"], "region")
    _text(record["data_residency"], "data_residency")
    _boolean(record["china_region_default_satisfied"], "china_region_default_satisfied")
    return record


def _validate_model_contract(value: object) -> None:
    record = _object(
        value,
        {
            "model_id",
            "model_version",
            "api_version",
            "request_schema_sha256",
            "response_schema_sha256",
        },
        "model_contract",
    )
    for field in ("model_id", "model_version", "api_version"):
        _text(record[field], f"model_contract_{field}")
    for field in ("request_schema_sha256", "response_schema_sha256"):
        _sha(record[field], f"model_contract_{field}")


def _validate_training_contract(value: object) -> None:
    record = _object(
        value,
        {
            "input_used",
            "output_used",
            "embeddings_used",
            "derivatives_used",
            "human_review_used",
            "evidence_sha256",
        },
        "training_contract",
    )
    for field in (
        "input_used",
        "output_used",
        "embeddings_used",
        "derivatives_used",
        "human_review_used",
    ):
        if record[field] is not False:
            raise StopBRequestError("provider_training_or_product_improvement_forbidden")
    _sha(record["evidence_sha256"], "training_evidence_sha256")


def _validate_retention_contract(value: object) -> None:
    record = _object(
        value,
        {"mode", "retention_seconds", "covered_scopes", "evidence_sha256"},
        "retention_contract",
    )
    if record["mode"] not in {"zero_persistence", "fixed_retention"}:
        raise StopBRequestError("unsupported_retention_mode")
    seconds = _integer(record["retention_seconds"], "retention_seconds")
    if record["mode"] == "zero_persistence" and seconds != 0:
        raise StopBRequestError("zero_persistence_requires_zero_seconds")
    if not _unique_texts(record["covered_scopes"], "retention_covered_scopes"):
        raise StopBRequestError("retention_scopes_required")
    _sha(record["evidence_sha256"], "retention_evidence_sha256")


def _validate_deletion_contract(value: object) -> None:
    record = _object(
        value,
        {
            "procedure_id",
            "deletion_sla_seconds",
            "verification_method",
            "key_revocation_procedure",
            "exit_procedure",
            "evidence_sha256",
        },
        "deletion_exit_contract",
    )
    for field in (
        "procedure_id",
        "verification_method",
        "key_revocation_procedure",
        "exit_procedure",
    ):
        _text(record[field], f"deletion_exit_{field}")
    _integer(record["deletion_sla_seconds"], "deletion_sla_seconds")
    _sha(record["evidence_sha256"], "deletion_exit_evidence_sha256")


def _validate_operational_limits(value: object) -> Mapping[str, Any]:
    keys = {
        "timeout_ms",
        "max_retries",
        "max_concurrency",
        "rate_limit_requests",
        "rate_limit_window_seconds",
        "max_input_units",
        "max_output_units",
        "max_request_bytes",
        "max_response_bytes",
    }
    record = _object(value, keys, "operational_limits")
    for field in keys - {"max_retries"}:
        _integer(record[field], f"operational_limits_{field}", minimum=1)
    _integer(record["max_retries"], "operational_limits_max_retries")
    return record


def _validate_meter_contract(value: object) -> None:
    record = _object(
        value,
        {"unit_name", "definition", "code_sha256", "termination_evidence_sha256"},
        "meter_contract",
    )
    _text(record["unit_name"], "meter_unit_name")
    _text(record["definition"], "meter_definition")
    _sha(record["code_sha256"], "meter_code_sha256")
    _sha(record["termination_evidence_sha256"], "meter_termination_evidence_sha256")


def _validate_commercial_contract(value: object) -> Mapping[str, Any]:
    keys = {
        "currency",
        "unit_price_microunits",
        "quota_requests_per_minute",
        "quota_input_units_daily",
        "quota_output_units_daily",
        "budget_per_call_microunits",
        "budget_daily_microunits",
        "budget_monthly_microunits",
        "breaker_action",
        "evidence_sha256",
    }
    record = _object(value, keys, "commercial_contract")
    currency = _text(record["currency"], "commercial_currency")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise StopBRequestError("commercial_currency_must_be_iso4217")
    for field in (
        "quota_requests_per_minute",
        "quota_input_units_daily",
        "quota_output_units_daily",
    ):
        _integer(record[field], f"commercial_{field}", minimum=1)
    for field in (
        "unit_price_microunits",
        "budget_per_call_microunits",
        "budget_daily_microunits",
        "budget_monthly_microunits",
    ):
        _integer(record[field], f"commercial_{field}")
    if not (
        record["budget_per_call_microunits"]
        <= record["budget_daily_microunits"]
        <= record["budget_monthly_microunits"]
    ):
        raise StopBRequestError("commercial_budget_order_invalid")
    _text(record["breaker_action"], "commercial_breaker_action")
    _sha(record["evidence_sha256"], "commercial_evidence_sha256")
    return record


def _validate_evidence_refs(value: object) -> None:
    records = _array(value, "evidence_refs")
    if len(records) < 2:
        raise StopBRequestError("role_requires_official_and_binding_evidence")
    kinds: set[str] = set()
    ids: set[str] = set()
    for raw in records:
        record = _object(
            raw,
            {
                "evidence_id",
                "kind",
                "document_title",
                "effective_date",
                "sha256",
                "binding_to_actual_account",
            },
            "evidence_ref",
        )
        evidence_id = _text(record["evidence_id"], "evidence_id")
        if evidence_id in ids:
            raise StopBRequestError("duplicate_evidence_id")
        ids.add(evidence_id)
        kind = _text(record["kind"], "evidence_kind")
        if kind not in {
            "official_document",
            "binding_terms",
            "dpa",
            "account_setting",
            "deletion_procedure",
        }:
            raise StopBRequestError("unsupported_evidence_kind")
        kinds.add(kind)
        _text(record["document_title"], "evidence_document_title")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(record["effective_date"])):
            raise StopBRequestError("evidence_effective_date_invalid")
        _sha(record["sha256"], "evidence_sha256")
        if record["binding_to_actual_account"] is not True:
            raise StopBRequestError("evidence_not_bound_to_actual_account")
    if not {"official_document", "binding_terms"}.issubset(kinds):
        raise StopBRequestError("role_requires_official_and_binding_evidence")


def _validate_data_decisions(
    value: object,
    mode: str,
) -> dict[str, Mapping[str, Any]]:
    records: dict[str, Mapping[str, Any]] = {}
    for raw in _array(value, "data_class_decisions"):
        record = _object(raw, _DATA_DECISION_KEYS, "data_class_decision")
        class_id = _text(record["data_class_id"], "data_class_id")
        if class_id not in DATA_CLASS_IDS or class_id in records:
            raise StopBRequestError("data_class_set_mismatch")
        if record["authorization_status"] != "not_authorized":
            raise StopBRequestError("stop_b_request_cannot_authorize_data")
        role_ids = _unique_texts(record["role_ids"], "data_class_role_ids")
        purposes = _unique_texts(record["purposes"], "data_class_purposes")
        fields = _unique_texts(record["field_allowlist"], "data_class_field_allowlist")
        if mode == "template":
            if (
                record["decision"] != "pending"
                or role_ids
                or purposes
                or record["payload_schema_sha256"] is not None
                or fields
                or record["limits"] is not None
            ):
                raise StopBRequestError("template_data_class_must_be_unbound")
        else:
            if record["decision"] not in {"request_approval", "deny"}:
                raise StopBRequestError("approval_ready_data_class_decision_missing")
            if record["decision"] == "deny":
                if role_ids or purposes or fields or record["payload_schema_sha256"] is not None or record["limits"] is not None:
                    raise StopBRequestError("denied_data_class_must_have_no_flow")
            else:
                if not role_ids or not purposes or not fields:
                    raise StopBRequestError("requested_data_class_flow_incomplete")
                _sha(record["payload_schema_sha256"], "data_class_payload_schema_sha256")
                _validate_data_limits(record["limits"])
        records[class_id] = record
    if tuple(records) != DATA_CLASS_IDS:
        raise StopBRequestError("data_class_order_or_coverage_mismatch")
    return records


def _validate_data_limits(value: object) -> None:
    record = _object(
        value,
        {
            "max_records_per_call",
            "max_bytes_per_call",
            "max_input_units_per_call",
            "max_calls_per_day",
            "expires_at",
        },
        "data_class_limits",
    )
    for field in record.keys() - {"expires_at"}:
        _integer(record[field], f"data_class_limits_{field}", minimum=1)
    expires_at = _text(record["expires_at"], "data_class_expires_at")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", expires_at):
        raise StopBRequestError("data_class_expiry_must_be_utc_second")


def _validate_coordinator(value: object, mode: str) -> Mapping[str, Any]:
    keys = {
        "provider_neutral",
        "selected_strategy",
        "ordered_channel_role_ids",
        "winner_policy",
        "winner_qualification_schema_sha256",
        "global_deadline_ms",
        "parallel_max_started_channels",
        "hedge_delay_ms",
        "per_channel_limits",
        "aggregate_limits",
        "circuit_breaker",
        "disclosure_ledger_contract",
        "transport_must_acknowledge_cancellation_or_run_in_bounded_process",
    }
    state = _object(value, keys, "server_answer_coordinator")
    if state["provider_neutral"] is not True or state[
        "transport_must_acknowledge_cancellation_or_run_in_bounded_process"
    ] is not True:
        raise StopBRequestError("coordinator_safety_contract_missing")
    ordered = _unique_texts(state["ordered_channel_role_ids"], "ordered_channel_role_ids")
    per_channel = _array(state["per_channel_limits"], "per_channel_limits")
    if mode == "template":
        nullable = (
            "selected_strategy",
            "winner_policy",
            "winner_qualification_schema_sha256",
            "global_deadline_ms",
            "parallel_max_started_channels",
            "hedge_delay_ms",
            "aggregate_limits",
            "circuit_breaker",
            "disclosure_ledger_contract",
        )
        if any(state[field] is not None for field in nullable) or ordered or per_channel:
            raise StopBRequestError("template_coordinator_must_be_unbound")
        return state
    if state["selected_strategy"] not in {
        "single",
        "sequential_fallback",
        "parallel_hedge",
    }:
        raise StopBRequestError("coordinator_strategy_missing")
    if state["winner_policy"] not in {"first_success", "ordered_success"}:
        raise StopBRequestError("coordinator_winner_policy_missing")
    _sha(
        state["winner_qualification_schema_sha256"],
        "winner_qualification_schema_sha256",
    )
    _integer(state["global_deadline_ms"], "global_deadline_ms", minimum=1)
    _integer(
        state["parallel_max_started_channels"],
        "parallel_max_started_channels",
        minimum=1,
    )
    _integer(state["hedge_delay_ms"], "hedge_delay_ms")
    for raw in per_channel:
        record = _object(
            raw,
            {"role_id", "timeout_ms", "max_retries", "max_cost_microunits"},
            "coordinator_per_channel_limit",
        )
        _text(record["role_id"], "coordinator_role_id")
        _integer(record["timeout_ms"], "coordinator_timeout_ms", minimum=1)
        _integer(record["max_retries"], "coordinator_max_retries")
        _integer(record["max_cost_microunits"], "coordinator_max_cost_microunits")
    _validate_coordinator_aggregate(state["aggregate_limits"])
    _validate_circuit_breaker(state["circuit_breaker"])
    _validate_disclosure_contract(state["disclosure_ledger_contract"])
    return state


def _validate_coordinator_aggregate(value: object) -> None:
    record = _object(
        value,
        {
            "max_started_calls_per_request",
            "total_cost_budget_microunits",
            "daily_cost_budget_microunits",
            "monthly_cost_budget_microunits",
        },
        "coordinator_aggregate_limits",
    )
    _integer(record["max_started_calls_per_request"], "max_started_calls_per_request", minimum=1)
    for field in (
        "total_cost_budget_microunits",
        "daily_cost_budget_microunits",
        "monthly_cost_budget_microunits",
    ):
        _integer(record[field], field)
    if not (
        record["total_cost_budget_microunits"]
        <= record["daily_cost_budget_microunits"]
        <= record["monthly_cost_budget_microunits"]
    ):
        raise StopBRequestError("coordinator_budget_order_invalid")


def _validate_circuit_breaker(value: object) -> None:
    record = _object(
        value,
        {
            "failure_threshold",
            "failure_window_seconds",
            "cooldown_seconds",
            "half_open_max_calls",
        },
        "coordinator_circuit_breaker",
    )
    for field in record:
        _integer(record[field], f"circuit_breaker_{field}", minimum=1)


def _validate_disclosure_contract(value: object) -> None:
    record = _object(
        value,
        {
            "schema_version",
            "schema_sha256",
            "every_started_channel_disclosed_and_accounted",
            "retention_seconds",
            "late_completion_accounted",
        },
        "disclosure_ledger_contract",
    )
    _text(record["schema_version"], "disclosure_schema_version")
    _sha(record["schema_sha256"], "disclosure_schema_sha256")
    if record["every_started_channel_disclosed_and_accounted"] is not True:
        raise StopBRequestError("started_channel_disclosure_required")
    _integer(record["retention_seconds"], "disclosure_retention_seconds")
    if record["late_completion_accounted"] is not True:
        raise StopBRequestError("late_completion_accounting_required")


def _validate_synthetic_probe(value: object, mode: str) -> Mapping[str, Any]:
    state = _object(
        value,
        {
            "status",
            "fixture",
            "provider_neutral_compilation_receipt",
            "provider_calls_authorized",
            "authorization_status",
            "maximum_total_calls",
            "maximum_total_cost",
            "expected_outputs",
        },
        "synthetic_probe",
    )
    if state["status"] != "sealed-offline-provider-neutral-fixture":
        raise StopBRequestError("synthetic_probe_status_mismatch")
    fixture = _object(
        state["fixture"],
        {"path", "sha256", "contains_real_source_or_user_data"},
        "synthetic_probe_fixture",
    )
    if (
        fixture["path"] != FIXTURE_RELATIVE_PATH
        or fixture["sha256"] != FIXTURE_SHA256
        or fixture["contains_real_source_or_user_data"] is not False
    ):
        raise StopBRequestError("synthetic_probe_fixture_mismatch")
    if state["provider_calls_authorized"] is not False or state[
        "authorization_status"
    ] != "not_authorized":
        raise StopBRequestError("synthetic_probe_must_remain_unauthorized")
    _validate_provider_neutral_receipt(state["provider_neutral_compilation_receipt"])
    if mode == "template":
        if any(
            state[field] is not None
            for field in ("maximum_total_calls", "maximum_total_cost", "expected_outputs")
        ):
            raise StopBRequestError("template_synthetic_probe_costs_must_be_unbound")
        return state
    _integer(state["maximum_total_calls"], "synthetic_probe_maximum_total_calls", minimum=1)
    _validate_probe_cost(state["maximum_total_cost"])
    _validate_expected_outputs(state["expected_outputs"])
    return state


def _validate_provider_neutral_receipt(value: object) -> None:
    receipt = _object(
        value,
        {
            "schema_version",
            "status",
            "authorized",
            "fixture_sha256",
            "runner_sha256",
            "request_set_sha256",
            "adapter_contracts",
            "call_counts",
            "requests",
            "compilation_boundary",
        },
        "provider_neutral_compilation_receipt",
    )
    if (
        receipt["schema_version"] != "cloud-v2-stop-b-probe-compilation-receipt-v1"
        or receipt["status"] != "offline-provider-neutral-payloads-compiled"
        or receipt["authorized"] is not False
        or receipt["fixture_sha256"] != FIXTURE_SHA256
        or receipt["request_set_sha256"] != REQUEST_SET_SHA256
    ):
        raise StopBRequestError("provider_neutral_receipt_identity_mismatch")
    _sha(receipt["runner_sha256"], "probe_runner_sha256")
    adapters = _object(
        receipt["adapter_contracts"],
        {
            "server_answer_channel_identity_sha256",
            "embedding_identity_sha256",
            "embedding_policy_sha256",
        },
        "probe_adapter_contracts",
    )
    for field, item in adapters.items():
        _sha(item, f"probe_adapter_{field}")
    counts = _object(
        receipt["call_counts"],
        {
            "server_answer_calls_per_approved_channel",
            "embedding_calls_by_purpose",
            "single_server_channel_total",
        },
        "probe_call_counts",
    )
    embedding_counts = _object(
        counts["embedding_calls_by_purpose"],
        {"build", "query", "entity"},
        "probe_embedding_call_counts",
    )
    server_answer_calls = _integer(
        counts["server_answer_calls_per_approved_channel"],
        "server_answer_calls_per_approved_channel",
        minimum=1,
    )
    embedding_calls = tuple(
        _integer(
            embedding_counts[purpose],
            f"embedding_calls_by_purpose_{purpose}",
            minimum=1,
        )
        for purpose in ("build", "query", "entity")
    )
    single_server_channel_total = _integer(
        counts["single_server_channel_total"],
        "single_server_channel_total",
        minimum=1,
    )
    if (
        server_answer_calls != 1
        or any(call_count != 1 for call_count in embedding_calls)
        or single_server_channel_total != 4
    ):
        raise StopBRequestError("provider_neutral_call_count_mismatch")
    requests = _array(receipt["requests"], "probe_requests")
    if [item.get("request_key") for item in requests if isinstance(item, Mapping)] != [
        "server_answer",
        "embedding.build.0",
        "embedding.query.0",
        "embedding.entity.0",
    ]:
        raise StopBRequestError("provider_neutral_request_set_mismatch")
    for raw in requests:
        record = _object(
            raw,
            {"request_key", "payload_sha256", "payload_size_bytes", "call_count"},
            "provider_neutral_request",
        )
        _text(record["request_key"], "probe_request_key")
        _sha(record["payload_sha256"], "probe_payload_sha256")
        _integer(record["payload_size_bytes"], "probe_payload_size_bytes", minimum=1)
        if _integer(record["call_count"], "probe_request_call_count", minimum=1) != 1:
            raise StopBRequestError("provider_neutral_request_call_count_mismatch")
    boundary = _object(
        receipt["compilation_boundary"],
        {
            "semantic_fixture",
            "provider_neutral_adapter_payload_bytes",
            "provider_specific_wire_bytes",
        },
        "probe_compilation_boundary",
    )
    if (
        boundary["semantic_fixture"] is not True
        or boundary["provider_neutral_adapter_payload_bytes"] is not True
        or boundary["provider_specific_wire_bytes"] is not False
    ):
        raise StopBRequestError("provider_neutral_compilation_boundary_mismatch")


def _validate_probe_cost(value: object) -> Mapping[str, Any]:
    record = _object(
        value,
        {
            "currency",
            "maximum_total_cost_microunits",
            "calculation",
            "unit_price_evidence_set_sha256",
            "calculation_sha256",
        },
        "synthetic_probe_maximum_total_cost",
    )
    currency = _text(record["currency"], "probe_cost_currency")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise StopBRequestError("probe_cost_currency_must_be_iso4217")
    _integer(record["maximum_total_cost_microunits"], "probe_maximum_cost")
    if record["calculation"] != "sum(role_slots.maximum_cost_microunits)":
        raise StopBRequestError("probe_cost_calculation_mismatch")
    _sha(record["unit_price_evidence_set_sha256"], "probe_price_evidence_sha256")
    expected_calculation = {
        "calculation": record["calculation"],
        "currency": record["currency"],
        "maximum_total_cost_microunits": record["maximum_total_cost_microunits"],
        "unit_price_evidence_set_sha256": record["unit_price_evidence_set_sha256"],
    }
    if record["calculation_sha256"] != _canonical_json_sha256(expected_calculation):
        raise StopBRequestError("probe_cost_calculation_sha256_mismatch")
    return record


def _validate_expected_outputs(value: object) -> Mapping[str, Any]:
    record = _object(
        value,
        {"contract_sha256", "role_expectations"},
        "synthetic_probe_expected_outputs",
    )
    _sha(record["contract_sha256"], "expected_outputs_contract_sha256")
    expectations = _array(record["role_expectations"], "role_expectations")
    seen: set[str] = set()
    for raw in expectations:
        item = _object(
            raw,
            {
                "role_id",
                "response_schema_sha256",
                "validator_code_sha256",
                "assertions",
                "embedding_dimension",
            },
            "role_expectation",
        )
        role_id = _text(item["role_id"], "expectation_role_id")
        if role_id in seen:
            raise StopBRequestError("duplicate_role_expectation")
        seen.add(role_id)
        _sha(item["response_schema_sha256"], "expected_response_schema_sha256")
        _sha(item["validator_code_sha256"], "expected_validator_code_sha256")
        assertions = _unique_texts(item["assertions"], "expected_output_assertions")
        if not {"schema_valid", "no_provider_error_fields"}.issubset(assertions):
            raise StopBRequestError("expected_output_assertions_incomplete")
        dimension = item["embedding_dimension"]
        if dimension is not None:
            _integer(dimension, "expected_embedding_dimension", minimum=1)
            required = {
                "item_count_matches_request",
                "object_id_order_preserved",
                "finite_vector_values",
                "exact_embedding_dimension",
            }
            if not required.issubset(assertions):
                raise StopBRequestError("embedding_expected_output_assertions_incomplete")
    if not expectations:
        raise StopBRequestError("expected_output_roles_required")
    return record


def _validate_wire_slots(value: object, mode: str) -> tuple[Mapping[str, Any], ...]:
    state = _object(
        value,
        {"status", "provider_calls_authorized", "role_slots"},
        "provider_specific_wire_compilation",
    )
    if state["provider_calls_authorized"] is not False:
        raise StopBRequestError("provider_wire_compilation_cannot_authorize_calls")
    slots: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    seen_roles: set[str] = set()
    for raw in _array(state["role_slots"], "provider_wire_role_slots"):
        slot = _object(raw, _WIRE_SLOT_KEYS, "provider_wire_role_slot")
        slot_id = _text(slot["slot_id"], "wire_slot_id")
        role_id = _text(slot["role_id"], "wire_role_id")
        if slot_id in seen_ids or role_id in seen_roles:
            raise StopBRequestError("duplicate_provider_wire_role_slot")
        seen_ids.add(slot_id)
        seen_roles.add(role_id)
        for field in (
            "semantic_fixture_sha256",
            "provider_neutral_request_set_sha256",
            "provider_contract_sha256",
            "model_identity_sha256",
            "policy_sha256",
            "transport_code_sha256",
            "egress_policy_sha256",
            "wire_request_set_sha256",
            "expected_output_contract_sha256",
            "compiled_wire_receipt_sha256",
        ):
            _sha(slot[field], f"wire_slot_{field}")
        if slot["semantic_fixture_sha256"] != FIXTURE_SHA256:
            raise StopBRequestError("wire_slot_fixture_mismatch")
        _https_endpoint(slot["exact_endpoint"], "wire_exact_endpoint")
        _integer(slot["wire_request_total_size_bytes"], "wire_request_total_size_bytes", minimum=1)
        _integer(slot["call_cap"], "wire_call_cap", minimum=1)
        _integer(slot["maximum_cost_microunits"], "wire_maximum_cost_microunits")
        if not re.fullmatch(r"[A-Z]{3}", _text(slot["currency"], "wire_currency")):
            raise StopBRequestError("wire_currency_must_be_iso4217")
        slots.append(slot)
    expected_status = (
        "pending-role-bindings"
        if mode == "template"
        else "compiled-offline-awaiting-stop-b-approval"
    )
    if state["status"] != expected_status:
        raise StopBRequestError("provider_wire_compilation_status_mismatch")
    if mode == "template" and slots:
        raise StopBRequestError("template_provider_wire_slots_must_be_empty")
    if mode == "approval_ready" and not slots:
        raise StopBRequestError("approval_ready_provider_wire_slots_required")
    return tuple(slots)


def _validate_local_vector(value: object, mode: str) -> Mapping[str, Any]:
    state = _object(
        value,
        {"candidate", "production", "approval_status"},
        "local_vector_contract",
    )
    _validate_local_vector_candidate(state["candidate"])
    if mode == "template":
        if state["production"] is not None or state["approval_status"] != "pending_receiving_team":
            raise StopBRequestError("template_local_vector_production_must_be_unbound")
        return state
    if state["approval_status"] != "requested":
        raise StopBRequestError("local_vector_approval_request_missing")
    _validate_local_vector_production(state["production"])
    return state


def _validate_local_vector_candidate(value: object) -> None:
    keys = {
        "engine",
        "engine_version",
        "builder_python",
        "index_build_threads",
        "dimension",
        "dtype",
        "normalization",
        "metric",
        "engine_metric",
        "schema_version",
        "data_release_id",
        "authority_manifest_sha256",
        "chunking_identity_sha256",
        "embedding_identity_sha256",
        "derived_candidate_root",
        "derived_candidate_manifest_sha256",
        "embedding_policy_sha256",
        "provider",
        "base_url",
        "model",
        "model_digest",
        "credentials",
        "network_scope",
        "build_query_entity_identity_shared",
        "candidate_data_root",
        "production_data_files",
        "production_data_file_set_sha256",
        "chunk_index_name",
        "entity_index_name",
        "chunk_count",
        "entity_count",
        "top_k_max",
        "max_vectors_per_index",
        "metadata_allowlist",
        "candidate_manifest_sha256",
        "runtime_read_only",
        "network_listener",
        "production_suite_vector",
    }
    record = _object(value, keys, "local_vector_candidate")
    expected_scalars = {
        "engine": "usearch",
        "engine_version": "2.26.2",
        "builder_python": "3.14.6",
        "index_build_threads": 1,
        "dimension": 1024,
        "dtype": "f32",
        "normalization": "l2",
        "metric": "cosine",
        "engine_metric": "cos",
        "schema_version": "kg-local-vector-schema-v1",
        "data_release_id": "r9-fb70102bbfb4007b4546cf305b237d376cbd077496a4fc72a344feff583d0063",
        "authority_manifest_sha256": "964658ce8e3a4a94735a9ea78df158d2a588f399d6ff26bc28a417007cfef067",
        "chunking_identity_sha256": "47fdd2ad20d81a7fe69f28c1aeee4feb41770d7f3b27058696c88657a2bb556a",
        "embedding_identity_sha256": "1420abc56de9dc70b55517f0879a64acc66947d89d194b6f43bb326e135b9d4b",
        "derived_candidate_manifest_sha256": "713e15a96b6a6fb637acd5ecca73884b1d25095c185285eee58e67f75a1d3e",
        "embedding_policy_sha256": "80ba02591c49c23fd1285245b1d6582291660961fe7a54fee29f5360c15e37d5",
        "provider": "ollama-local",
        "base_url": "http://127.0.0.1:11434/api/embed",
        "model": "bge-m3:latest",
        "model_digest": "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab",
        "credentials": "none",
        "network_scope": "loopback-only",
        "build_query_entity_identity_shared": True,
        "chunk_index_name": "chunk-index",
        "entity_index_name": "entity-index",
        "chunk_count": 1482,
        "entity_count": 22,
        "top_k_max": 50,
        "max_vectors_per_index": 100000,
        "candidate_manifest_sha256": "625101f5813457da633978f7ee09e6f19c44045dbd54d63b09ff8f316295085b",
        "runtime_read_only": True,
        "network_listener": False,
        "production_suite_vector": True,
    }
    for field, expected in expected_scalars.items():
        if type(record[field]) is not type(expected) or record[field] != expected:
            raise StopBRequestError(f"local_vector_candidate_{field}_mismatch")
    derived_candidate_root = _relative_path(
        record["derived_candidate_root"], "derived_candidate_root"
    )
    if derived_candidate_root != DERIVED_CANDIDATE_ROOT:
        raise StopBRequestError("local_vector_candidate_derived_root_mismatch")
    candidate_data_root = _relative_path(
        record["candidate_data_root"], "candidate_data_root"
    )
    expected_candidate_data_root = (
        f"{derived_candidate_root}/local-vector/candidate/{record['data_release_id']}"
    )
    if candidate_data_root != expected_candidate_data_root:
        raise StopBRequestError("local_vector_candidate_data_root_mismatch")
    production_data_files: list[dict[str, str]] = []
    for item in _array(
        record["production_data_files"], "local_vector_candidate_production_data_files"
    ):
        file_record = _object(
            item,
            {"path", "sha256"},
            "local_vector_candidate_production_data_file",
        )
        production_data_files.append(
            {
                "path": _relative_path(
                    file_record["path"], "local_vector_candidate_production_data_path"
                ),
                "sha256": _sha(
                    file_record["sha256"],
                    "local_vector_candidate_production_data_sha256",
                ),
            }
        )
    expected_production_data_files = [
        {"path": path, "sha256": digest}
        for path, digest in PRODUCTION_DATA_FILES
    ]
    production_data_file_set_sha256 = _sha(
        record["production_data_file_set_sha256"],
        "local_vector_candidate_production_data_file_set_sha256",
    )
    if production_data_files != expected_production_data_files:
        raise StopBRequestError(
            "local_vector_candidate_production_data_files_mismatch"
        )
    if (
        production_data_file_set_sha256 != PRODUCTION_DATA_FILE_SET_SHA256
        or _canonical_json_sha256(production_data_files)
        != production_data_file_set_sha256
    ):
        raise StopBRequestError(
            "local_vector_candidate_production_data_file_set_mismatch"
        )
    metadata = _object(
        record["metadata_allowlist"],
        {"chunk", "entity"},
        "local_vector_candidate_metadata_allowlist",
    )
    if metadata != {
        "chunk": ["authority_release_id", "content_type"],
        "entity": ["authority_release_id", "entity_type"],
    }:
        raise StopBRequestError("local_vector_candidate_metadata_allowlist_mismatch")


def _validate_local_vector_production(value: object) -> None:
    record = _object(
        value,
        {
            "target_platform",
            "engine",
            "data_layout",
            "indexes",
            "vector_identity",
            "capacity",
            "static_encryption",
            "backup",
            "exact_delete",
            "runtime_read_only",
            "network_listener",
            "rebuild_from_real_embedding_required",
        },
        "local_vector_production",
    )
    platform = _object(
        record["target_platform"],
        {"os_name", "os_version", "architecture", "cpu_model", "cpu_features", "filesystem"},
        "local_vector_target_platform",
    )
    for field in ("os_name", "os_version", "architecture", "cpu_model", "filesystem"):
        _text(platform[field], f"local_vector_platform_{field}")
    if not _unique_texts(platform["cpu_features"], "local_vector_cpu_features"):
        raise StopBRequestError("local_vector_cpu_features_required")
    engine = _object(
        record["engine"],
        {"name", "version", "package_sha256", "python_version", "index_build_threads"},
        "local_vector_production_engine",
    )
    if engine["name"] != "usearch" or engine["version"] != "2.26.2":
        raise StopBRequestError("local_vector_production_engine_mismatch")
    _sha(engine["package_sha256"], "local_vector_engine_package_sha256")
    _text(engine["python_version"], "local_vector_python_version")
    _integer(engine["index_build_threads"], "local_vector_index_build_threads", minimum=1)
    layout = _object(
        record["data_layout"],
        {
            "data_root",
            "candidate_root",
            "active_root",
            "owner",
            "group",
            "directory_mode",
            "file_mode",
        },
        "local_vector_data_layout",
    )
    data_root = _absolute_path(layout["data_root"], "local_vector_data_root")
    candidate_root = _absolute_path(layout["candidate_root"], "local_vector_candidate_root")
    active_root = _absolute_path(layout["active_root"], "local_vector_active_root")
    if not candidate_root.startswith(data_root + "/") or not active_root.startswith(data_root + "/") or candidate_root == active_root:
        raise StopBRequestError("local_vector_roots_not_isolated_under_data_root")
    _text(layout["owner"], "local_vector_owner")
    _text(layout["group"], "local_vector_group")
    for field in ("directory_mode", "file_mode"):
        if not re.fullmatch(r"0[0-7]{3}", str(layout[field])):
            raise StopBRequestError(f"local_vector_{field}_invalid")
    indexes = _object(record["indexes"], {"chunk", "entity"}, "local_vector_indexes")
    if indexes != {"chunk": "chunk-index", "entity": "entity-index"}:
        raise StopBRequestError("local_vector_index_names_mismatch")
    identity = _object(
        record["vector_identity"],
        {
            "embedding_identity_sha256",
            "dimension",
            "dtype",
            "normalization",
            "metric",
            "engine_metric",
            "schema_version",
            "authority_manifest_sha256",
            "chunking_identity_sha256",
            "metadata_allowlist",
            "top_k_max",
            "max_vectors_per_index",
        },
        "local_vector_production_identity",
    )
    embedding_identity = _sha(identity["embedding_identity_sha256"], "production_embedding_identity_sha256")
    if embedding_identity == "1420abc56de9dc70b55517f0879a64acc66947d89d194b6f43bb326e135b9d4b":
        raise StopBRequestError("production_cannot_use_fake_embedding_identity")
    _integer(identity["dimension"], "production_vector_dimension", minimum=1)
    if identity["dtype"] != "f32" or identity["normalization"] not in {"l2", "none"}:
        raise StopBRequestError("production_vector_dtype_or_normalization_invalid")
    if identity["metric"] not in {"cosine", "dot", "euclidean"}:
        raise StopBRequestError("production_vector_metric_invalid")
    _text(identity["engine_metric"], "production_engine_metric")
    if identity["schema_version"] != "kg-local-vector-schema-v1":
        raise StopBRequestError("production_vector_schema_mismatch")
    for field in ("authority_manifest_sha256", "chunking_identity_sha256"):
        _sha(identity[field], f"production_{field}")
    if identity["authority_manifest_sha256"] != "964658ce8e3a4a94735a9ea78df158d2a588f399d6ff26bc28a417007cfef067" or identity["chunking_identity_sha256"] != "47fdd2ad20d81a7fe69f28c1aeee4feb41770d7f3b27058696c88657a2bb556a":
        raise StopBRequestError("production_vector_authority_or_chunking_mismatch")
    metadata = _object(identity["metadata_allowlist"], {"chunk", "entity"}, "production_metadata_allowlist")
    if metadata != {
        "chunk": ["authority_release_id", "content_type"],
        "entity": ["authority_release_id", "entity_type"],
    }:
        raise StopBRequestError("production_metadata_allowlist_mismatch")
    _integer(identity["top_k_max"], "production_top_k_max", minimum=1)
    _integer(identity["max_vectors_per_index"], "production_max_vectors_per_index", minimum=1)
    capacity = _object(
        record["capacity"],
        {"chunk_capacity", "entity_capacity", "memory_budget_bytes", "disk_budget_bytes"},
        "local_vector_capacity",
    )
    if _integer(capacity["chunk_capacity"], "chunk_capacity", minimum=1482) < 1482 or _integer(capacity["entity_capacity"], "entity_capacity", minimum=22) < 22:
        raise StopBRequestError("local_vector_capacity_below_candidate_count")
    _integer(capacity["memory_budget_bytes"], "local_vector_memory_budget", minimum=1)
    _integer(capacity["disk_budget_bytes"], "local_vector_disk_budget", minimum=1)
    encryption = _object(
        record["static_encryption"],
        {"algorithm", "key_reference"},
        "local_vector_static_encryption",
    )
    _text(encryption["algorithm"], "local_vector_encryption_algorithm")
    if not _text(encryption["key_reference"], "local_vector_key_reference").startswith("secretref:"):
        raise StopBRequestError("local_vector_encryption_key_must_be_secret_reference")
    backup = _object(
        record["backup"],
        {"backup_root", "retention_seconds", "rpo_seconds", "rto_seconds", "restore_test_evidence_sha256"},
        "local_vector_backup",
    )
    backup_root = _absolute_path(backup["backup_root"], "local_vector_backup_root")
    if backup_root.startswith(data_root + "/"):
        raise StopBRequestError("local_vector_backup_must_be_outside_data_root")
    for field in ("retention_seconds", "rpo_seconds", "rto_seconds"):
        _integer(backup[field], f"local_vector_backup_{field}", minimum=1)
    _sha(backup["restore_test_evidence_sha256"], "local_vector_restore_test_evidence")
    deletion = _object(
        record["exact_delete"],
        {"target_kinds", "procedure_id", "verification_method", "verification_schema_sha256"},
        "local_vector_exact_delete",
    )
    if tuple(deletion["target_kinds"]) != ("candidate_root", "active_root", "backup_root"):
        raise StopBRequestError("local_vector_exact_delete_target_set_mismatch")
    _text(deletion["procedure_id"], "local_vector_delete_procedure_id")
    _text(deletion["verification_method"], "local_vector_delete_verification_method")
    _sha(deletion["verification_schema_sha256"], "local_vector_delete_verification_schema")
    if record["runtime_read_only"] is not True or record["network_listener"] is not False or record["rebuild_from_real_embedding_required"] is not True:
        raise StopBRequestError("local_vector_production_safety_boundary_mismatch")


def _validate_phase1_evidence(value: object, mode: str) -> None:
    state = _object(
        value,
        {"status", "required_labels", "receipts"},
        "phase1_evidence",
    )
    if tuple(state["required_labels"]) != REQUIRED_PHASE1_EVIDENCE_LABELS:
        raise StopBRequestError("phase1_evidence_required_labels_mismatch")
    receipts = _array(state["receipts"], "phase1_evidence_receipts")
    if mode == "template":
        if state["status"] != "pending-formal-evidence" or receipts:
            raise StopBRequestError("template_phase1_evidence_must_be_pending")
        return
    if state["status"] != "sealed":
        raise StopBRequestError("approval_ready_phase1_evidence_not_sealed")
    labels: list[str] = []
    for raw in receipts:
        record = _object(
            raw,
            {"label", "kind", "path", "sha256", "schema_version", "status"},
            "phase1_evidence_receipt",
        )
        labels.append(_text(record["label"], "phase1_evidence_label"))
        if record["kind"] not in {"file", "directory_file_set"}:
            raise StopBRequestError("phase1_evidence_kind_invalid")
        _relative_path(record["path"], "phase1_evidence_path")
        _sha(record["sha256"], "phase1_evidence_sha256")
        _text(record["schema_version"], "phase1_evidence_schema_version")
        if record["status"] != "passed":
            raise StopBRequestError("phase1_evidence_receipt_not_passing")
    if tuple(labels) != REQUIRED_PHASE1_EVIDENCE_LABELS:
        raise StopBRequestError("phase1_evidence_receipt_coverage_mismatch")


def _validate_approval_ready_cross_contract(
    *,
    cardinality: Mapping[str, Any],
    roles: tuple[Mapping[str, Any], ...],
    decisions: Mapping[str, Mapping[str, Any]],
    coordinator: Mapping[str, Any],
    probe: Mapping[str, Any],
    wire_slots: tuple[Mapping[str, Any], ...],
    local_vector: Mapping[str, Any],
) -> None:
    n = cardinality["server_answer_channel_count_N"]
    m = cardinality["ops_agent_model_count_M"]
    by_kind = {
        kind: tuple(role for role in roles if role["role_kind"] == kind)
        for kind in ROLE_KINDS
    }
    expected_counts = {
        "app_host_final_answer": 1,
        "server_answer": n,
        "embedding": 1,
        "ops_agent": m,
    }
    if any(len(by_kind[kind]) != count for kind, count in expected_counts.items()):
        raise StopBRequestError("role_kind_cardinality_mismatch")
    if len(roles) != cardinality["materialized_role_count"]:
        raise StopBRequestError("role_instance_count_mismatch")
    for kind, kind_roles in by_kind.items():
        if tuple(role["ordinal"] for role in kind_roles) != tuple(range(1, len(kind_roles) + 1)):
            raise StopBRequestError(f"{kind}_ordinals_must_be_contiguous")

    all_role_ids = {role["role_id"] for role in roles}
    app_ids = {role["role_id"] for role in by_kind["app_host_final_answer"]}
    server_ids = {role["role_id"] for role in by_kind["server_answer"]}
    embedding_ids = {role["role_id"] for role in by_kind["embedding"]}
    ops_ids = {role["role_id"] for role in by_kind["ops_agent"]}
    expected_flows = {
        "synthetic_probe": server_ids | embedding_ids,
        "redacted_r9_chunk_and_entity_embedding": embedding_ids,
        "online_query": server_ids | embedding_ids,
        "app_user_session": app_ids,
        "ops_aggregate_metrics": ops_ids,
    }
    expected_purposes = {
        "synthetic_probe": {"provider_contract_probe"},
        "redacted_r9_chunk_and_entity_embedding": {"chunk_embedding", "entity_embedding"},
        "online_query": {"query_embedding", "server_answer_synthesis"},
        "app_user_session": {"app_host_final_answer"},
        "ops_aggregate_metrics": {"ops_agent_reasoning"},
    }
    for class_id, decision in decisions.items():
        if class_id == "synthetic_probe" and decision["decision"] != "request_approval":
            raise StopBRequestError("synthetic_probe_must_be_requested_before_real_data")
        if class_id == "ops_aggregate_metrics" and not ops_ids:
            if decision["decision"] != "deny":
                raise StopBRequestError("ops_metrics_must_be_denied_when_ops_llm_disabled")
            continue
        if decision["decision"] == "request_approval":
            if set(decision["role_ids"]) != expected_flows[class_id]:
                raise StopBRequestError(f"{class_id}_role_flow_mismatch")
            if set(decision["purposes"]) != expected_purposes[class_id]:
                raise StopBRequestError(f"{class_id}_purpose_mismatch")

    requested_classes_by_role = {role_id: set() for role_id in all_role_ids}
    for class_id, decision in decisions.items():
        if decision["decision"] == "request_approval":
            for role_id in decision["role_ids"]:
                if role_id not in all_role_ids:
                    raise StopBRequestError("data_class_references_unknown_role")
                requested_classes_by_role[role_id].add(class_id)
    for role in roles:
        if set(role["allowed_data_class_ids"]) != requested_classes_by_role[role["role_id"]]:
            raise StopBRequestError("role_data_class_allowlist_mismatch")

    ordered = tuple(coordinator["ordered_channel_role_ids"])
    if set(ordered) != server_ids or len(ordered) != n:
        raise StopBRequestError("coordinator_channel_set_mismatch")
    strategy = coordinator["selected_strategy"]
    winner = coordinator["winner_policy"]
    if strategy == "single":
        if n != 1 or winner != "ordered_success":
            raise StopBRequestError("single_coordinator_contract_mismatch")
    elif strategy == "sequential_fallback":
        if winner != "ordered_success" or coordinator["parallel_max_started_channels"] != 1:
            raise StopBRequestError("sequential_coordinator_contract_mismatch")
    else:
        if n < 2 or coordinator["parallel_max_started_channels"] != n:
            raise StopBRequestError("parallel_hedge_contract_mismatch")
    per_channel = coordinator["per_channel_limits"]
    if tuple(item["role_id"] for item in per_channel) != ordered:
        raise StopBRequestError("coordinator_per_channel_order_mismatch")
    role_by_id = {role["role_id"]: role for role in roles}
    maximum_cost = 0
    maximum_calls = 0
    for item in per_channel:
        role = role_by_id[item["role_id"]]
        limits = role["operational_limits"]
        commercial = role["commercial_contract"]
        if item["timeout_ms"] != limits["timeout_ms"] or item["max_retries"] != limits["max_retries"]:
            raise StopBRequestError("coordinator_role_limit_mismatch")
        if item["max_retries"] != 0:
            raise StopBRequestError("server_answer_runtime_does_not_support_retries")
        if item["max_cost_microunits"] != commercial["budget_per_call_microunits"]:
            raise StopBRequestError("coordinator_role_cost_mismatch")
        if item["timeout_ms"] > coordinator["global_deadline_ms"]:
            raise StopBRequestError("channel_timeout_exceeds_global_deadline")
        maximum_cost += item["max_cost_microunits"]
        maximum_calls += item["max_retries"] + 1
    aggregate = coordinator["aggregate_limits"]
    if aggregate["max_started_calls_per_request"] != maximum_calls or aggregate[
        "total_cost_budget_microunits"
    ] != maximum_cost:
        raise StopBRequestError("coordinator_aggregate_exposure_mismatch")

    slot_by_role = {slot["role_id"]: slot for slot in wire_slots}
    probe_role_ids = set(decisions["synthetic_probe"]["role_ids"])
    if set(slot_by_role) != probe_role_ids:
        raise StopBRequestError("synthetic_probe_wire_slot_coverage_mismatch")
    expected_slot_ids = {
        role["role_id"]: role["provider_specific_wire_slot_id"]
        for role in roles
        if role["role_id"] in probe_role_ids
    }
    for role_id, slot in slot_by_role.items():
        if slot["slot_id"] != expected_slot_ids[role_id]:
            raise StopBRequestError("wire_slot_role_binding_mismatch")
        if slot["exact_endpoint"] != role_by_id[role_id]["endpoint_contract"]["exact_endpoint"]:
            raise StopBRequestError("wire_slot_endpoint_mismatch")
        expected_calls = 3 if role_by_id[role_id]["role_kind"] == "embedding" else 1
        if slot["call_cap"] != expected_calls:
            raise StopBRequestError("wire_slot_call_cap_mismatch")
    if probe["maximum_total_calls"] != sum(slot["call_cap"] for slot in wire_slots):
        raise StopBRequestError("synthetic_probe_total_call_cap_mismatch")
    currencies = {slot["currency"] for slot in wire_slots}
    cost = probe["maximum_total_cost"]
    if currencies != {cost["currency"]} or cost["maximum_total_cost_microunits"] != sum(
        slot["maximum_cost_microunits"] for slot in wire_slots
    ):
        raise StopBRequestError("synthetic_probe_total_cost_mismatch")
    expectations = probe["expected_outputs"]["role_expectations"]
    expectation_by_role = {item["role_id"]: item for item in expectations}
    if set(expectation_by_role) != probe_role_ids:
        raise StopBRequestError("synthetic_probe_expected_output_coverage_mismatch")
    production_dimension = local_vector["production"]["vector_identity"]["dimension"]
    for role_id, expectation in expectation_by_role.items():
        if expectation["response_schema_sha256"] != role_by_id[role_id]["model_contract"]["response_schema_sha256"]:
            raise StopBRequestError("expected_output_response_schema_mismatch")
        if expectation["embedding_dimension"] is not None:
            if role_by_id[role_id]["role_kind"] != "embedding" or expectation["embedding_dimension"] != production_dimension:
                raise StopBRequestError("expected_embedding_dimension_mismatch")
        if slot_by_role[role_id]["expected_output_contract_sha256"] != probe["expected_outputs"]["contract_sha256"]:
            raise StopBRequestError("wire_slot_expected_output_contract_mismatch")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    try:
        validate_stop_b_request(
            _strict_json(root / REQUEST_RELATIVE_PATH),
            mode="template",
        )
    except StopBRequestError as exc:
        result = {"ok": False, "mode": "template", "error": exc.code}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    result = {
        "ok": True,
        "mode": "template",
        "approval_ready": False,
        "real_provider_calls_authorized": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
