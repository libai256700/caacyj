#!/usr/bin/env python3
"""Run and gate the immutable 80-question cloud migration subset."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

from cloud_gold import (
    ATTESTATION_DECISION,
    ATTESTATION_SCHEMA_VERSION,
    ATTESTATION_SIGNATURE_IDENTITY,
    ATTESTATION_SIGNATURE_NAMESPACE,
    GoldContractError,
    QUESTION_COUNT,
    build_attestation_decision_bytes,
    canonical_json_bytes,
    evaluate_gold_answer,
    gold_validation_metadata,
    is_safe_refusal_answer,
    load_gold_standard,
    parse_authority_snapshot_bytes,
    read_regular_bytes,
    sha256_bytes,
    strict_json_object,
    strict_json_value,
    verify_attestation_decision,
    verify_trace_file,
)


FIXTURE_SHA256 = "7f9cc4c2470f6aa5dcfef6d928429e6b08fb73453d592e3a188d913128e85e2d"
ALLOWED_DOC_PREFIXES = (
    "政策法规_",
    "理论题库_",
    "无人机理论书籍_",
    "实操题库_",
)
FULL_COVERAGE_IDS = frozenset({"sys_04", "app_05"})
ALLOWED_ROUTES = frozenset({"rag", "hybrid", "graph_first", "csa"})
REPORT_ONLY_EXIT_CODE = 3
PREPARE_ATTESTATION_EXIT_CODE = 4
COLLECTION_SCHEMA_VERSION = "cloud80-report-collection-v1"
GATE_CORE_SCHEMA_VERSION = "cloud80-formal-gate-core-v1"
FORMAL_RECEIPT_SCHEMA_VERSION = "cloud80-formal-receipt-v1"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_COLLECTION_BYTES = 2 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_ask_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https with a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("credentials in URL are forbidden")
    if parsed.query or parsed.fragment or parsed.path.rstrip("/") != "/api/ask":
        raise ValueError("URL must be the exact /api/ask endpoint")
    return url


def normalize_doc_name(value: Any) -> str:
    name = str(value or "").strip()
    return name[:-4] if name.lower().endswith(".txt") else name


def _claim_telemetry(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = payload.get("claim_evidence")
    if isinstance(direct, Mapping):
        return direct
    stats = payload.get("stats")
    nested = stats.get("claim_evidence") if isinstance(stats, Mapping) else None
    return nested if isinstance(nested, Mapping) else {}


def evaluate_case(
    case: Mapping[str, Any],
    http_status: int,
    payload: Mapping[str, Any] | Any,
    *,
    elapsed_s: float,
    gold_case_context: Mapping[str, Any] | None = None,
    gold_activated: bool = False,
    report_only: bool = False,
    authority_snapshot: Mapping[str, Mapping[str, str]] | None = None,
    oracle_registry: Mapping[str, Any] | None = None,
    oracle_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if http_status != 200:
        reasons.append(f"http_status:{http_status}")
    if not isinstance(payload, Mapping):
        payload = {}
        reasons.append("response_not_object")

    raw_route = payload.get("route")
    route = raw_route.strip() if isinstance(raw_route, str) else ""
    if not isinstance(raw_route, str):
        reasons.append("route_invalid_type")
    if route not in ALLOWED_ROUTES:
        reasons.append(f"unexpected_route:{route or 'missing'}")
    raw_degraded = payload.get("degraded")
    degraded = raw_degraded if isinstance(raw_degraded, bool) else True
    if not isinstance(raw_degraded, bool):
        reasons.append("degraded_invalid_type")
    if degraded:
        reasons.append("degraded_response")

    raw_stats = payload.get("stats")
    stats = raw_stats if isinstance(raw_stats, Mapping) else {}
    if not isinstance(raw_stats, Mapping):
        reasons.append("stats_invalid_type")
    raw_trace_id = stats.get("trace_id")
    trace_id = raw_trace_id.strip() if isinstance(raw_trace_id, str) else ""
    if raw_trace_id is not None and not isinstance(raw_trace_id, str):
        reasons.append("trace_id_invalid_type")
    if not trace_id:
        reasons.append("trace_id_missing")
    raw_answer_model = stats.get("answer_model")
    answer_model = raw_answer_model if isinstance(raw_answer_model, Mapping) else {}
    if not isinstance(raw_answer_model, Mapping):
        reasons.append("answer_model_invalid_type")
    raw_unrecovered = answer_model.get("unrecovered_model_failure")
    if not isinstance(raw_unrecovered, bool):
        reasons.append("unrecovered_model_failure_invalid_type")
        unrecovered_model_failure = True
    else:
        unrecovered_model_failure = raw_unrecovered
    raw_recovery_status = answer_model.get("recovery_status")
    allowed_recovery_statuses = {
        "not_required",
        "model_fallback_succeeded",
        "extractive_fallback_succeeded",
        "unrecovered",
        "pipeline_error",
    }
    if (
        not isinstance(raw_recovery_status, str)
        or raw_recovery_status not in allowed_recovery_statuses
    ):
        reasons.append("answer_recovery_status_invalid")
        answer_recovery_status = "invalid"
    else:
        answer_recovery_status = raw_recovery_status
    expected_unrecovered = answer_recovery_status in {
        "unrecovered",
        "pipeline_error",
    }
    if isinstance(raw_unrecovered, bool) and raw_unrecovered != expected_unrecovered:
        reasons.append("unrecovered_model_failure_inconsistent")
    if unrecovered_model_failure:
        reasons.append("unrecovered_model_failure")

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        reasons.append("sources_invalid_type")
        sources: list[Mapping[str, Any]] = []
    else:
        sources = []
        for source in raw_sources:
            if not isinstance(source, Mapping):
                reasons.append("source_entry_invalid_type")
                continue
            raw_name = source.get("doc_name") or source.get("source_doc")
            if raw_name is not None and not isinstance(raw_name, str):
                reasons.append("source_name_invalid_type")
                continue
            sources.append(source)
    actual_docs = set()
    for source in sources:
        raw_name = source.get("doc_name") or source.get("source_doc")
        name = normalize_doc_name(raw_name) if isinstance(raw_name, str) else ""
        if name:
            actual_docs.add(name)
    if not actual_docs:
        reasons.append("sources_missing")
    out_of_scope_docs = sorted(
        name for name in actual_docs if not name.startswith(ALLOWED_DOC_PREFIXES)
    )
    if out_of_scope_docs:
        reasons.append("out_of_scope_sources")

    expected_docs = {
        normalize_doc_name(name) for name in case.get("expected_docs") or []
    }
    if str(case.get("id") or "") in FULL_COVERAGE_IDS:
        if not expected_docs.issubset(actual_docs):
            reasons.append("expected_documents_not_fully_covered")
    elif expected_docs and not expected_docs.intersection(actual_docs):
        reasons.append("expected_document_not_hit")

    direct_claim = payload.get("claim_evidence")
    nested_claim = stats.get("claim_evidence")
    if direct_claim is not None:
        if not isinstance(direct_claim, Mapping):
            reasons.append("claim_evidence_invalid_type")
            claim_evidence: Mapping[str, Any] = {}
        else:
            claim_evidence = direct_claim
    elif nested_claim is not None:
        if not isinstance(nested_claim, Mapping):
            reasons.append("claim_evidence_invalid_type")
            claim_evidence = {}
        else:
            claim_evidence = nested_claim
    else:
        claim_evidence = {}
        reasons.append("claim_evidence_missing")
    raw_finalizer = claim_evidence.get("finalizer_invoked")
    finalizer_invoked = raw_finalizer is True
    if not isinstance(raw_finalizer, bool):
        reasons.append("claim_finalizer_invoked_invalid_type")
    if not finalizer_invoked:
        reasons.append("claim_finalizer_not_invoked")
    raw_outcome = claim_evidence.get("outcome")
    if not isinstance(raw_outcome, str):
        reasons.append("claim_finalizer_outcome_invalid_type")
    if raw_outcome != "passed":
        reasons.append("claim_finalizer_not_passed")
    raw_unsupported = claim_evidence.get("unsupported_high_risk_claims")
    if (
        isinstance(raw_unsupported, bool)
        or not isinstance(raw_unsupported, int)
        or raw_unsupported < 0
    ):
        reasons.append("unsupported_high_risk_claims_invalid_type")
        unsupported_high_risk = 1
    else:
        unsupported_high_risk = raw_unsupported
    if unsupported_high_risk:
        reasons.append("unsupported_high_risk_claim")

    raw_answer = payload.get("answer")
    answer = raw_answer if isinstance(raw_answer, str) else ""
    if not isinstance(raw_answer, str):
        reasons.append("answer_invalid_type")
    safe_refusal = is_safe_refusal_answer(answer)
    retrieval_backed = bool(actual_docs) and not out_of_scope_docs and not any(
        reason.startswith("expected_document") for reason in reasons
    )
    claim_supported = bool(
        finalizer_invoked
        and claim_evidence.get("outcome") == "passed"
        and unsupported_high_risk == 0
    )
    if report_only:
        gold_result = {
            "evaluated": False,
            "correct": None,
            "safe_refusal": safe_refusal,
            "reason_codes": ["report_only_correctness_not_evaluated"],
            "required_claims_passed": None,
            "required_claims_total": None,
            "forbidden_claims_hit": [],
            "oracle": None,
        }
    elif not gold_activated:
        gold_result = {
            "evaluated": False,
            "correct": False,
            "safe_refusal": safe_refusal,
            "reason_codes": ["gold_not_activated"],
            "required_claims_passed": 0,
            "required_claims_total": 0,
            "forbidden_claims_hit": [],
            "oracle": None,
        }
        reasons.append("gold_not_activated")
    elif gold_case_context is None:
        gold_result = {
            "evaluated": False,
            "correct": False,
            "safe_refusal": safe_refusal,
            "reason_codes": ["gold_case_missing"],
            "required_claims_passed": 0,
            "required_claims_total": 0,
            "forbidden_claims_hit": [],
            "oracle": None,
        }
        reasons.append("gold_case_missing")
    else:
        gold_result = evaluate_gold_answer(
            gold_case_context,
            answer,
            authority_snapshot=authority_snapshot,
            oracle_registry=oracle_registry,
            oracle_context=oracle_context,
        )
        reasons.extend(gold_result["reason_codes"])

    result = {
        "id": str(case.get("id") or ""),
        "category": str(case.get("category") or ""),
        "reasons": list(dict.fromkeys(reasons)),
        "http_status": http_status,
        "elapsed_s": round(float(elapsed_s), 4),
        "route": route,
        "degraded": degraded,
        "trace_id": trace_id,
        "actual_docs": sorted(actual_docs),
        "expected_docs": sorted(expected_docs),
        "finalizer_invoked": finalizer_invoked,
        "claim_finalizer_outcome": claim_evidence.get("outcome"),
        "unsupported_high_risk_claims": unsupported_high_risk,
        "answer_model_present": isinstance(raw_answer_model, Mapping),
        "answer_recovery_status": answer_recovery_status,
        "unrecovered_model_failure": unrecovered_model_failure,
        "retrieval_backed": retrieval_backed,
        "claim_supported": claim_supported,
        "safe_refusal": safe_refusal,
        "gold_correctness_evaluated": bool(gold_result["evaluated"]),
        "gold_correct": gold_result["correct"],
        "gold_reason_codes": gold_result["reason_codes"],
        "gold_required_claims_passed": gold_result["required_claims_passed"],
        "gold_required_claims_total": gold_result["required_claims_total"],
        "gold_forbidden_claims_hit": gold_result["forbidden_claims_hit"],
        "gold_oracle": gold_result["oracle"],
        "quality_gate_evaluated": not report_only,
        "quality_gate_passed": None if report_only else not reasons,
    }
    if not report_only:
        result["passed"] = not reasons
    return result


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def build_summary(
    results: list[Mapping[str, Any]],
    expected_categories: Mapping[str, int],
    *,
    report_only: bool = False,
    gold_activated: bool = False,
    trace_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    latencies = [float(item.get("elapsed_s") or 0) for item in results]
    category_counts = Counter(str(item.get("category") or "") for item in results)
    normalized_expected = {str(key): int(value) for key, value in expected_categories.items()}
    normalized_actual = {
        key: category_counts.get(key, 0)
        for key in sorted(set(normalized_expected).union(category_counts))
    }
    finalizer_count = sum(item.get("finalizer_invoked") is True for item in results)
    degraded_count = sum(bool(item.get("degraded")) for item in results)
    unsupported_high_risk = sum(
        int(item.get("unsupported_high_risk_claims") or 0) for item in results
    )
    answer_model_count = sum(item.get("answer_model_present") is True for item in results)
    unrecovered_model_failures = sum(
        item.get("unrecovered_model_failure") is not False for item in results
    )
    gold_evaluated_count = sum(
        item.get("gold_correctness_evaluated") is True for item in results
    )
    gold_correct_count = sum(item.get("gold_correct") is True for item in results)
    safe_refusal_policy_failures = sum(
        any(
            reason in {
                "unexpected_safe_refusal",
                "safe_refusal_required",
                "safe_refusal_not_exact",
            }
            for reason in item.get("gold_reason_codes") or []
        )
        for item in results
    )
    p95 = percentile_nearest_rank(latencies, 0.95)
    maximum = max(latencies, default=0.0)
    observations = {
        "category_counts_match": normalized_actual == normalized_expected,
        "finalizer_coverage_100": bool(results) and finalizer_count == len(results),
        "unsupported_high_risk_zero": unsupported_high_risk == 0,
        "answer_model_telemetry_coverage_100": bool(results)
        and answer_model_count == len(results),
        "unrecovered_model_failure_zero": unrecovered_model_failures == 0,
        "degraded_zero": degraded_count == 0,
        "p95_latency_lte_7s": p95 <= 7.0,
        "max_latency_lte_12s": maximum <= 12.0,
    }
    gates = {
        "all_cases_passed": bool(results) and all(bool(item.get("passed")) for item in results),
        **observations,
        "gold_activated": gold_activated,
        "gold_correctness_coverage_100": bool(results)
        and gold_evaluated_count == len(results),
        "gold_correct_100": bool(results) and gold_correct_count == len(results),
        "safe_refusal_policy_failures_zero": safe_refusal_policy_failures == 0,
        "trace_binding_verified": bool(
            trace_binding and trace_binding.get("verified") is True
        ),
    }
    summary = {
        "quality_gate_evaluated": not report_only,
        "quality_gate_passed": None if report_only else all(gates.values()),
        "total": len(results),
        "category_counts": normalized_actual,
        "expected_category_counts": normalized_expected,
        "finalizer_invoked": finalizer_count,
        "unsupported_high_risk_claims": unsupported_high_risk,
        "answer_model_telemetry": answer_model_count,
        "unrecovered_model_failures": unrecovered_model_failures,
        "degraded_count": degraded_count,
        "gold_correctness_evaluated": gold_evaluated_count,
        "gold_correct_cases": gold_correct_count,
        "safe_refusal_policy_failures": safe_refusal_policy_failures,
        "latency_s": {
            "average": round(sum(latencies) / len(latencies), 4) if latencies else 0.0,
            "p95": round(p95, 4),
            "max": round(maximum, 4),
        },
        "observations": observations,
        "trace_binding": dict(trace_binding or {"verified": False}),
        "issues": [
            {"id": item.get("id"), "reasons": item.get("reasons")}
            for item in results
            if item.get("reasons")
        ],
    }
    if not report_only:
        summary.update({
            "passed": all(gates.values()),
            "passed_cases": sum(bool(item.get("passed")) for item in results),
            "failed_cases": sum(not bool(item.get("passed")) for item in results),
            "gates": gates,
            "failures": [
                {"id": item.get("id"), "reasons": item.get("reasons")}
                for item in results
                if not item.get("passed")
            ],
        })
    return summary


def _load_fixture(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FIXTURE_SHA256:
        raise ValueError(f"fixture sha256 mismatch: {digest}")
    payload = json.loads(raw)
    questions = payload.get("questions")
    if not isinstance(questions, list) or len(questions) != int(payload.get("meta", {}).get("total", -1)):
        raise ValueError("fixture total does not match questions")
    ids = [str(item.get("id") or "") for item in questions if isinstance(item, Mapping)]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("fixture question ids must be non-empty and unique")
    computed_categories = Counter(
        str(item.get("category") or "") for item in questions if isinstance(item, Mapping)
    )
    declared_categories = payload.get("categories")
    if not isinstance(declared_categories, Mapping):
        raise ValueError("fixture categories do not match questions")
    normalized_declared = {
        str(key): int(value) for key, value in declared_categories.items()
    }
    if (
        any(key not in normalized_declared for key in computed_categories)
        or any(
            computed_categories.get(key, 0) != value
            for key, value in normalized_declared.items()
        )
    ):
        raise ValueError("fixture categories do not match questions")
    return payload


def _request_body_bytes(question: str) -> bytes:
    return canonical_json_bytes({
        "user_query": question,
        "allowed_sources": ["csa", "sqlite_exact", "bm25", "dense", "neo4j"],
    })


def _post_question(
    url: str,
    question: str,
    timeout_s: float,
) -> tuple[int, Any, float, bytes]:
    body = _request_body_bytes(question)
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = int(response.status)
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        status = 0
        raw = json.dumps({
            "error": str(exc),
            "error_type": "service_unavailable",
            "degraded": True,
            "sources": [],
        }, ensure_ascii=False).encode("utf-8")
    elapsed = time.monotonic() - started
    if len(raw) > MAX_RESPONSE_BYTES:
        payload = {
            "error": "response_too_large",
            "degraded": True,
            "sources": [],
        }
        return status, payload, elapsed, raw[:MAX_RESPONSE_BYTES]
    try:
        payload = strict_json_value(raw, "HTTP response")
    except (GoldContractError, TypeError, ValueError):
        payload = {"_invalid_json": raw.decode("utf-8", errors="replace")[:1000]}
    return status, payload, elapsed, raw


def _write_bytes_exclusive(path: Path, data: bytes) -> str:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValueError(f"refusing to overwrite evaluation artifact: {path}") from exc
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("evaluation artifact write made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return sha256_bytes(data)


def _write_json_exclusive(
    path: Path,
    value: object,
    *,
    canonical: bool = False,
) -> str:
    data = (
        canonical_json_bytes(value)
        if canonical
        else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return _write_bytes_exclusive(path, data)


def _ensure_restricted_directory(path: Path, label: str) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise GoldContractError(f"{label} cannot be inspected") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise GoldContractError(f"{label} must be a private real directory")
    return candidate.resolve()


def _read_private_artifact(path: Path, label: str, *, max_bytes: int) -> bytes:
    raw = read_regular_bytes(path, label, max_bytes=max_bytes)
    if stat.S_IMODE(Path(path).lstat().st_mode) & 0o077:
        raise GoldContractError(f"{label} must not grant group or other permissions")
    return raw


def _question_ids_sha256(questions: list[Mapping[str, Any]]) -> str:
    return sha256_bytes(canonical_json_bytes([str(item["id"]) for item in questions]))


def _response_source_names(payload: Mapping[str, Any]) -> list[str]:
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or any(
        not isinstance(item, Mapping) for item in raw_sources
    ):
        raise GoldContractError("response sources are invalid")
    names: list[str] = []
    for source in raw_sources:
        raw_name = (
            source.get("doc_name")
            or source.get("doc")
            or source.get("source_doc")
            or source.get("file")
            or ""
        )
        if not isinstance(raw_name, str):
            raise GoldContractError("response source name is invalid")
        names.append(raw_name)
    return names


def _response_claim_evidence(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = payload.get("claim_evidence")
    stats = payload.get("stats")
    nested = stats.get("claim_evidence") if isinstance(stats, Mapping) else None
    value = direct if direct is not None else nested
    if not isinstance(value, Mapping):
        raise GoldContractError("response claim_evidence is invalid")
    return value


def _load_full_collection(
    collection_dir: Path,
    fixture: Mapping[str, Any],
) -> tuple[dict[str, Any], str, list[dict[str, Any]], list[dict[str, Any]]]:
    root = _ensure_restricted_directory(collection_dir, "collection directory")
    raw_dir = _ensure_restricted_directory(root / "raw", "collection raw directory")
    manifest_bytes = _read_private_artifact(
        root / "collection.json",
        "collection manifest",
        max_bytes=MAX_COLLECTION_BYTES,
    )
    manifest = strict_json_object(manifest_bytes, "collection manifest")
    required_fields = {
        "schema_version",
        "run_id",
        "collected_at",
        "url",
        "fixture_sha256",
        "question_ids_sha256",
        "question_count",
        "selected_ids",
        "cases",
    }
    if set(manifest) != required_fields:
        raise GoldContractError("collection manifest fields drifted")
    if manifest.get("schema_version") != COLLECTION_SCHEMA_VERSION:
        raise GoldContractError("collection manifest schema is unsupported")
    try:
        run_id = UUID(str(manifest.get("run_id") or ""))
    except ValueError as exc:
        raise GoldContractError("collection run_id is invalid") from exc
    if run_id.version != 4:
        raise GoldContractError("collection run_id must be UUIDv4")
    try:
        collected_at = datetime.fromisoformat(
            str(manifest.get("collected_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise GoldContractError("collection timestamp is invalid") from exc
    if collected_at.tzinfo is None:
        raise GoldContractError("collection timestamp must be timezone-aware")
    questions = list(fixture["questions"])
    expected_ids = [str(item["id"]) for item in questions]
    if (
        manifest.get("fixture_sha256") != FIXTURE_SHA256
        or manifest.get("question_ids_sha256") != _question_ids_sha256(questions)
        or manifest.get("question_count") != QUESTION_COUNT
        or manifest.get("selected_ids") != expected_ids
    ):
        raise GoldContractError("collection is not the exact full Cloud 80 fixture")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != QUESTION_COUNT:
        raise GoldContractError("collection must contain exactly 80 cases")
    expected_case_fields = {
        "index",
        "id",
        "question_sha256",
        "request_body_sha256",
        "raw_path",
        "raw_response_sha256",
        "http_status",
        "elapsed_s",
        "trace_id",
    }
    payloads: list[dict[str, Any]] = []
    normalized_cases: list[dict[str, Any]] = []
    expected_raw_names: set[str] = set()
    for index, (entry, question) in enumerate(zip(cases, questions)):
        if not isinstance(entry, Mapping) or set(entry) != expected_case_fields:
            raise GoldContractError(f"collection case {index} fields drifted")
        case_id = str(question["id"])
        raw_name = f"{case_id}.json"
        expected_raw_names.add(raw_name)
        status = entry.get("http_status")
        elapsed = entry.get("elapsed_s")
        if (
            entry.get("index") != index
            or entry.get("id") != case_id
            or entry.get("question_sha256")
            != sha256_bytes(str(question["question"]).encode("utf-8"))
            or entry.get("request_body_sha256")
            != sha256_bytes(_request_body_bytes(str(question["question"])))
            or entry.get("raw_path") != f"raw/{raw_name}"
            or not _SHA256_RE.fullmatch(str(entry.get("raw_response_sha256") or ""))
            or isinstance(status, bool)
            or not isinstance(status, int)
            or not 0 <= status <= 599
            or isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(float(elapsed))
            or float(elapsed) < 0
            or not isinstance(entry.get("trace_id"), str)
        ):
            raise GoldContractError(f"collection case {case_id} is invalid")
        raw_bytes = _read_private_artifact(
            raw_dir / raw_name,
            f"raw response {case_id}",
            max_bytes=MAX_RESPONSE_BYTES,
        )
        if sha256_bytes(raw_bytes) != entry["raw_response_sha256"]:
            raise GoldContractError(f"raw response hash mismatch: {case_id}")
        payload = strict_json_object(raw_bytes, f"raw response {case_id}")
        payloads.append(payload)
        normalized_cases.append(dict(entry))
    actual_raw_names = {item.name for item in raw_dir.iterdir()}
    if actual_raw_names != expected_raw_names:
        raise GoldContractError("collection raw file set drifted")
    return (
        manifest,
        sha256_bytes(manifest_bytes),
        normalized_cases,
        payloads,
    )


def _bind_full_trace(
    fixture: Mapping[str, Any],
    collection_cases: list[Mapping[str, Any]],
    payloads: list[Mapping[str, Any]],
    results: list[Mapping[str, Any]],
    trace_state: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trace_index: dict[str, list[tuple[Mapping[str, Any], str]]] = {}
    for record, line_sha in zip(
        trace_state.chained_records,
        trace_state.chained_line_sha256s,
    ):
        trace_id = record.get("trace_id")
        if isinstance(trace_id, str) and trace_id.strip():
            trace_index.setdefault(trace_id.strip(), []).append((record, line_sha))
    bindings: list[dict[str, Any]] = []
    sequences: list[int] = []
    seen_trace_ids: set[str] = set()
    for index, (question, entry, payload, result) in enumerate(zip(
        fixture["questions"], collection_cases, payloads, results
    )):
        trace_id = entry["trace_id"].strip()
        if not trace_id or trace_id in seen_trace_ids:
            raise GoldContractError("collection trace ids must be non-empty and unique")
        seen_trace_ids.add(trace_id)
        matches = trace_index.get(trace_id, [])
        if len(matches) != 1:
            raise GoldContractError(f"trace id must bind exactly one chained record: {trace_id}")
        trace_record, trace_line_sha = matches[0]
        integrity = trace_record.get("integrity")
        sequence = integrity.get("sequence") if isinstance(integrity, Mapping) else None
        event_sha = integrity.get("event_sha256") if isinstance(integrity, Mapping) else None
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise GoldContractError(f"trace sequence is invalid: {trace_id}")
        if trace_record.get("query") != question.get("question"):
            raise GoldContractError(f"trace query mismatch: {trace_id}")
        if not result.get("route") or trace_record.get("route") != result.get("route"):
            raise GoldContractError(f"trace route mismatch: {trace_id}")
        source_names = _response_source_names(payload)
        trace_source_count = trace_record.get("source_count")
        trace_top_sources = trace_record.get("top_sources")
        if (
            isinstance(trace_source_count, bool)
            or not isinstance(trace_source_count, int)
            or not isinstance(trace_top_sources, list)
            or any(not isinstance(source, str) for source in trace_top_sources)
        ):
            raise GoldContractError(f"trace source summary types are invalid: {trace_id}")
        if (
            trace_source_count != len(source_names)
            or trace_top_sources != source_names[:10]
        ):
            raise GoldContractError(f"trace source summary mismatch: {trace_id}")
        claim_evidence = _response_claim_evidence(payload)
        if canonical_json_bytes(trace_record.get("claim_evidence")) != canonical_json_bytes(
            claim_evidence
        ):
            raise GoldContractError(f"trace claim evidence mismatch: {trace_id}")
        response_stats = payload.get("stats")
        if not isinstance(response_stats, Mapping):
            raise GoldContractError(f"response stats are invalid: {trace_id}")
        response_answer_model = response_stats.get("answer_model")
        trace_answer_model = trace_record.get("answer_model")
        if not isinstance(response_answer_model, Mapping) or not isinstance(
            trace_answer_model, Mapping
        ):
            raise GoldContractError(f"trace answer_model telemetry is missing: {trace_id}")
        if canonical_json_bytes(trace_answer_model) != canonical_json_bytes(
            response_answer_model
        ):
            raise GoldContractError(f"trace answer_model telemetry mismatch: {trace_id}")
        if "model" in trace_record and canonical_json_bytes(
            trace_record.get("model")
        ) != canonical_json_bytes(response_stats.get("model")):
            raise GoldContractError(
                f"trace model telemetry mismatch: {trace_id}"
            )
        raw_answer = payload.get("answer")
        if not isinstance(raw_answer, str):
            raise GoldContractError(f"response answer must be a string: {trace_id}")
        sequences.append(sequence)
        bindings.append({
            "index": index,
            "case_id": str(question["id"]),
            "question_sha256": entry["question_sha256"],
            "request_body_sha256": entry["request_body_sha256"],
            "trace_id": trace_id,
            "trace_sequence": sequence,
            "trace_event_sha256": event_sha,
            "trace_line_sha256": trace_line_sha,
            "raw_response_sha256": entry["raw_response_sha256"],
            "response_canonical_sha256": sha256_bytes(canonical_json_bytes(payload)),
            "answer_sha256": sha256_bytes(raw_answer.encode("utf-8")),
            "source_names_sha256": sha256_bytes(canonical_json_bytes(source_names)),
            "claim_evidence_sha256": sha256_bytes(canonical_json_bytes(claim_evidence)),
            "answer_model_sha256": sha256_bytes(
                canonical_json_bytes(response_answer_model)
            ),
            "http_status": entry["http_status"],
            "result_sha256": sha256_bytes(canonical_json_bytes(result)),
        })
    if sequences != list(range(sequences[0], sequences[0] + QUESTION_COUNT)):
        raise GoldContractError("Cloud 80 trace records must be contiguous and in fixture order")
    return ({
        "verified": True,
        "matched_trace_count": QUESTION_COUNT,
        "first_sequence": sequences[0],
        "last_sequence": sequences[-1],
        "trace_line_count": trace_state.line_count,
        "trace_legacy_count": trace_state.legacy_count,
        "trace_chain_head_event_sha256": trace_state.chain_head_event_sha256,
        "trace_file_sha256": trace_state.file_sha256,
        "trace_size_bytes": trace_state.size_bytes,
    }, bindings)


def _activated_gold_context(args: argparse.Namespace, fixture_path: Path) -> dict[str, Any]:
    approval_values = (
        args.gold_approval_decision,
        args.gold_approval_signature,
        args.gold_approval_public_key,
        args.gold_expected_fingerprint,
    )
    if not all(value is not None for value in approval_values):
        raise GoldContractError(
            "activated Gold requires decision, signature, public key, and expected fingerprint"
        )
    context = load_gold_standard(
        args.gold,
        args.gold_schema,
        fixture_path,
        decision_path=args.gold_approval_decision,
        signature_path=args.gold_approval_signature,
        public_key_path=args.gold_approval_public_key,
        expected_fingerprint=args.gold_expected_fingerprint,
    )
    if context.get("activated") is not True:
        raise GoldContractError("formal evaluation requires activated Cloud Gold")
    return context


def _prepare_formal_materials(
    args: argparse.Namespace,
    fixture: Mapping[str, Any],
    gold_context: Mapping[str, Any],
    authority_snapshot: Mapping[str, Mapping[str, str]],
    authority_snapshot_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    manifest, manifest_sha, collection_cases, payloads = _load_full_collection(
        args.collection_dir,
        fixture,
    )
    results: list[dict[str, Any]] = []
    for case, entry, payload in zip(fixture["questions"], collection_cases, payloads):
        result = evaluate_case(
            case,
            entry["http_status"],
            payload,
            elapsed_s=float(entry["elapsed_s"]),
            gold_case_context=gold_context["case_contexts"].get(str(case["id"])),
            gold_activated=True,
            authority_snapshot=authority_snapshot,
        )
        if result.get("trace_id") != entry["trace_id"]:
            raise GoldContractError(f"collection trace id drifted: {case['id']}")
        results.append(result)
    trace_state = verify_trace_file(args.trace_log)
    trace_binding, case_bindings = _bind_full_trace(
        fixture,
        collection_cases,
        payloads,
        results,
        trace_state,
    )
    gate_core = build_summary(
        results,
        fixture["categories"],
        report_only=False,
        gold_activated=True,
        trace_binding=trace_binding,
    )
    gate_core.update({
        "schema_version": GATE_CORE_SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "fixture_sha256": FIXTURE_SHA256,
        "gold_sha256": gold_context["gold_sha256"],
        "gold_schema_sha256": gold_context["gold_schema_sha256"],
        "authority_snapshot_sha256": authority_snapshot_sha256,
        "collection_manifest_sha256": manifest_sha,
    })
    results_sha = sha256_bytes(canonical_json_bytes(results))
    gate_core_sha = sha256_bytes(canonical_json_bytes(gate_core))
    case_bindings_sha = sha256_bytes(canonical_json_bytes(case_bindings))
    gold_approval = gold_context.get("approval")
    if not isinstance(gold_approval, Mapping):
        raise GoldContractError("activated Gold approval metadata is missing")
    basis = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "decision": ATTESTATION_DECISION,
        "run_id": manifest["run_id"],
        "collected_at": manifest["collected_at"],
        "endpoint_url": manifest["url"],
        "fixture_sha256": FIXTURE_SHA256,
        "question_ids_sha256": manifest["question_ids_sha256"],
        "question_count": QUESTION_COUNT,
        "gold_id": gold_context["gold_id"],
        "gold_sha256": gold_context["gold_sha256"],
        "gold_schema_sha256": gold_context["gold_schema_sha256"],
        "gold_approval_decision_sha256": gold_approval["decision_sha256"],
        "gold_approval_signature_sha256": gold_approval["signature_sha256"],
        "gold_approval_public_key_sha256": gold_approval["public_key_sha256"],
        "gold_approval_public_key_fingerprint": gold_approval["public_key_fingerprint"],
        "gold_approval_approved_by": gold_approval["approved_by"],
        "gold_approval_approved_at": gold_approval["approved_at"],
        "authority_snapshot_sha256": authority_snapshot_sha256,
        "collection_manifest_sha256": manifest_sha,
        "trace_log_sha256": trace_state.file_sha256,
        "trace_chain_head_event_sha256": trace_state.chain_head_event_sha256,
        "trace_last_sequence": trace_state.last_sequence,
        "trace_line_count": trace_state.line_count,
        "trace_legacy_count": trace_state.legacy_count,
        "evaluation_results_sha256": results_sha,
        "gate_core_sha256": gate_core_sha,
        "case_bindings_sha256": case_bindings_sha,
        "case_bindings": case_bindings,
        "signature_identity": ATTESTATION_SIGNATURE_IDENTITY,
        "signature_namespace": ATTESTATION_SIGNATURE_NAMESPACE,
    }
    return basis, results, gate_core


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[3]
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument(
        "--report-only",
        action="store_true",
        help="Collect raw observations; never evaluate or pass the release gate",
    )
    modes.add_argument(
        "--prepare-attestation",
        action="store_true",
        help="Recompute a full collection and emit a canonical decision for external signing",
    )
    modes.add_argument(
        "--formal-offline",
        action="store_true",
        help="Verify the signed attestation and recompute the formal offline gate",
    )
    parser.add_argument("--url", default="", help="Exact /api/ask URL")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=repo_root / "eval" / "online_subset_20260803.json",
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=repo_root / "eval" / "cloud80_gold_standard_v1.json",
    )
    parser.add_argument(
        "--gold-schema",
        type=Path,
        default=repo_root / "eval" / "cloud80_gold_standard_v1.schema.json",
    )
    parser.add_argument("--gold-approval-decision", type=Path)
    parser.add_argument("--gold-approval-signature", type=Path)
    parser.add_argument("--gold-approval-public-key", type=Path)
    parser.add_argument("--gold-expected-fingerprint")
    parser.add_argument("--authority-snapshot", type=Path)
    parser.add_argument("--trace-log", type=Path)
    parser.add_argument("--collection-dir", type=Path)
    parser.add_argument("--attested-by")
    parser.add_argument("--attested-at")
    parser.add_argument("--attestation-decision", type=Path)
    parser.add_argument("--attestation-signature", type=Path)
    parser.add_argument("--attestation-public-key", type=Path)
    parser.add_argument("--attestation-expected-fingerprint")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--ids",
        help="Comma-separated report-only subset; formal correctness gate always runs all 80",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected_ids = {
        item.strip() for item in str(args.ids or "").split(",") if item.strip()
    }
    fixture_path = args.fixture
    try:
        fixture = _load_fixture(fixture_path)
    except (GoldContractError, OSError, ValueError) as exc:
        raise SystemExit(f"fixture validation failed: {exc}") from exc
    output_dir = args.output_dir.resolve()
    repo_root = Path(__file__).resolve().parents[3]
    try:
        output_dir.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise SystemExit("--output-dir must be outside the repository")

    if args.report_only:
        report_url = args.url or os.getenv("RAG_URL", "")
        if not report_url:
            raise SystemExit("--report-only requires --url or RAG_URL")
        try:
            ask_url = validate_ask_url(report_url)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if not 0 < args.timeout <= 60:
            raise SystemExit("--timeout must be greater than 0 and at most 60 seconds")
        forbidden = (
            args.gold_approval_decision,
            args.gold_approval_signature,
            args.gold_approval_public_key,
            args.gold_expected_fingerprint,
            args.authority_snapshot,
            args.trace_log,
            args.collection_dir,
            args.attested_by,
            args.attested_at,
            args.attestation_decision,
            args.attestation_signature,
            args.attestation_public_key,
            args.attestation_expected_fingerprint,
        )
        if any(value is not None for value in forbidden):
            raise SystemExit("--report-only cannot consume activation or attestation artifacts")
        try:
            gold_context = load_gold_standard(args.gold, args.gold_schema, fixture_path)
        except (GoldContractError, OSError, ValueError) as exc:
            raise SystemExit(f"Cloud Gold validation failed: {exc}") from exc
        questions = [
            item for item in fixture["questions"]
            if not selected_ids or str(item.get("id")) in selected_ids
        ]
        actual_ids = {str(item["id"]) for item in questions}
        if selected_ids and selected_ids != actual_ids:
            raise SystemExit(
                "unknown question ids: " + ",".join(sorted(selected_ids - actual_ids))
            )
        raw_dir = output_dir / "raw"
        try:
            output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
            raw_dir.mkdir(mode=0o700)
        except OSError as exc:
            raise SystemExit(
                f"output directory must be new and safely creatable: {output_dir}"
            ) from exc
        run_id = str(uuid4())
        collected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        results: list[dict[str, Any]] = []
        collection_cases: list[dict[str, Any]] = []
        for index, case in enumerate(questions):
            question = str(case["question"])
            status, payload, elapsed, raw_bytes = _post_question(
                ask_url,
                question,
                args.timeout,
            )
            raw_sha = _write_bytes_exclusive(
                raw_dir / f"{case['id']}.json",
                raw_bytes,
            )
            result = evaluate_case(
                case,
                status,
                payload,
                elapsed_s=elapsed,
                gold_case_context=gold_context["case_contexts"].get(str(case["id"])),
                gold_activated=False,
                report_only=True,
            )
            results.append(result)
            collection_cases.append({
                "index": index,
                "id": str(case["id"]),
                "question_sha256": sha256_bytes(question.encode("utf-8")),
                "request_body_sha256": sha256_bytes(_request_body_bytes(question)),
                "raw_path": f"raw/{case['id']}.json",
                "raw_response_sha256": raw_sha,
                "http_status": status,
                "elapsed_s": round(float(elapsed), 4),
                "trace_id": result["trace_id"],
            })
            print(json.dumps({
                "id": result["id"],
                "quality_gate_evaluated": False,
                "quality_gate_passed": None,
                "elapsed_s": result["elapsed_s"],
                "reasons": result["reasons"],
            }, ensure_ascii=False), flush=True)
        expected_categories = (
            fixture["categories"]
            if not selected_ids
            else Counter(str(item["category"]) for item in questions)
        )
        summary = build_summary(results, expected_categories, report_only=True)
        summary.update({
            "schema_version": "kg-cloud-eval-summary-v2",
            "mode": "report_only",
            "fixture_sha256": FIXTURE_SHA256,
            "url": ask_url,
            "run_id": run_id,
            "selected_ids": [str(item["id"]) for item in questions],
            "gold_contract": {
                "schema_version": "cloud80-gold-report-only-metadata-v1",
                "gold_id": gold_context["gold_id"],
                "gold_sha256": gold_context["gold_sha256"],
                "reviewed_question_count": gold_context["reviewed_question_count"],
                "pending_question_count": len(gold_context["pending_question_ids"]),
                "activation_evaluated": False,
            },
        })
        collection = {
            "schema_version": COLLECTION_SCHEMA_VERSION,
            "run_id": run_id,
            "collected_at": collected_at,
            "url": ask_url,
            "fixture_sha256": FIXTURE_SHA256,
            "question_ids_sha256": _question_ids_sha256(list(fixture["questions"])),
            "question_count": len(questions),
            "selected_ids": [str(item["id"]) for item in questions],
            "cases": collection_cases,
        }
        _write_json_exclusive(output_dir / "results.json", results)
        _write_json_exclusive(output_dir / "summary.json", summary)
        _write_json_exclusive(output_dir / "collection.json", collection, canonical=True)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return REPORT_ONLY_EXIT_CODE

    if args.url or selected_ids:
        raise SystemExit("live HTTP formal evaluation is forbidden; use a full collection")
    if args.collection_dir is None or args.trace_log is None or args.authority_snapshot is None:
        raise SystemExit(
            "attestation modes require --collection-dir, --trace-log, and --authority-snapshot"
        )
    try:
        gold_context = _activated_gold_context(args, fixture_path)
        authority_bytes = read_regular_bytes(
            args.authority_snapshot,
            "authority snapshot",
            max_bytes=2 * 1024 * 1024,
        )
        authority_snapshot = parse_authority_snapshot_bytes(authority_bytes)
        basis, results, gate_core = _prepare_formal_materials(
            args,
            fixture,
            gold_context,
            authority_snapshot,
            sha256_bytes(authority_bytes),
        )
    except (GoldContractError, OSError, ValueError) as exc:
        raise SystemExit(f"formal material validation failed: {exc}") from exc

    if args.prepare_attestation:
        if (
            not args.attested_by
            or not args.attested_at
            or args.attestation_public_key is None
            or not args.attestation_expected_fingerprint
            or args.attestation_decision is not None
            or args.attestation_signature is not None
        ):
            raise SystemExit(
                "--prepare-attestation requires --attested-by, --attested-at, "
                "--attestation-public-key, and --attestation-expected-fingerprint"
            )
        try:
            public_key_bytes = read_regular_bytes(
                args.attestation_public_key,
                "attestation public key",
                max_bytes=16 * 1024,
            )
            decision_bytes = build_attestation_decision_bytes(
                basis,
                attested_by=args.attested_by,
                attested_at=args.attested_at,
                public_key_bytes=public_key_bytes,
                expected_fingerprint=args.attestation_expected_fingerprint,
            )
        except (GoldContractError, OSError, ValueError) as exc:
            raise SystemExit(f"attestation preparation failed: {exc}") from exc
        try:
            output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        except OSError as exc:
            raise SystemExit(
                f"output directory must be new and safely creatable: {output_dir}"
            ) from exc
        decision_sha = _write_bytes_exclusive(
            output_dir / "attestation-decision.json",
            decision_bytes,
        )
        preparation = {
            "schema_version": "cloud80-attestation-preparation-v1",
            "status": "pending_external_signature",
            "quality_gate_evaluated": False,
            "quality_gate_passed": None,
            "run_id": basis["run_id"],
            "attestation_decision_sha256": decision_sha,
            "evaluation_results_sha256": basis["evaluation_results_sha256"],
            "gate_core_sha256": basis["gate_core_sha256"],
        }
        _write_json_exclusive(output_dir / "preparation.json", preparation)
        print(json.dumps(preparation, ensure_ascii=False, indent=2))
        return PREPARE_ATTESTATION_EXIT_CODE

    if (
        args.attestation_decision is None
        or args.attestation_signature is None
        or args.attestation_public_key is None
        or not args.attestation_expected_fingerprint
        or args.attested_by is not None
        or args.attested_at is not None
    ):
        raise SystemExit(
            "--formal-offline requires attestation decision, signature, public key, and expected fingerprint"
        )
    try:
        attestation = verify_attestation_decision(
            basis,
            args.attestation_decision,
            args.attestation_signature,
            args.attestation_public_key,
            expected_fingerprint=args.attestation_expected_fingerprint,
        )
    except (GoldContractError, OSError, ValueError) as exc:
        raise SystemExit(f"evaluation attestation validation failed: {exc}") from exc
    try:
        output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    except OSError as exc:
        raise SystemExit(
            f"output directory must be new and safely creatable: {output_dir}"
        ) from exc
    results_sha = _write_json_exclusive(
        output_dir / "results.json", results, canonical=True
    )
    gate_core_sha = _write_json_exclusive(
        output_dir / "gate-core.json", gate_core, canonical=True
    )
    if (
        results_sha != basis["evaluation_results_sha256"]
        or gate_core_sha != basis["gate_core_sha256"]
    ):
        raise SystemExit("formal output hashes drifted from the signed attestation")
    summary = {
        **gate_core,
        "schema_version": "kg-cloud-eval-summary-v3",
        "mode": "formal_offline_signed_attestation",
        "gold_validation": gold_validation_metadata(gold_context),
        "attestation_validation": attestation,
        "signed_gate_core_sha256": gate_core_sha,
        "signed_results_sha256": results_sha,
    }
    summary_sha = _write_json_exclusive(output_dir / "summary.json", summary)
    receipt = {
        "schema_version": FORMAL_RECEIPT_SCHEMA_VERSION,
        "run_id": basis["run_id"],
        "quality_gate_evaluated": True,
        "quality_gate_passed": gate_core["quality_gate_passed"],
        "results_sha256": results_sha,
        "gate_core_sha256": gate_core_sha,
        "summary_sha256": summary_sha,
        "attestation": attestation,
    }
    _write_json_exclusive(output_dir / "receipt.json", receipt, canonical=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if gate_core["quality_gate_passed"] is True else 1


if __name__ == "__main__":
    sys.exit(main())
