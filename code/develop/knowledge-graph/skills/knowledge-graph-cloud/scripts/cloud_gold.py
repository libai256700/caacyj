#!/usr/bin/env python3
"""Strict Cloud 80 Gold validation, activation, scoring, and trace binding."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.stderr.write("formal Cloud Gold CLI bootstrap context is required\n")
    raise SystemExit(2)

import argparse
import base64
import binascii
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from deploy.cloud_v2.dlp import (
    DLPError,
    _open_held_payload,
    _revalidate_held_payload,
)
from deploy.cloud_v2.offline_evidence import (
    OfflineEvidenceError,
    _require_formal_bootstrap_context,
    _require_isolated_python,
)


GOLD_SCHEMA_VERSION = "cloud80-gold-standard-v1"
GOLD_SCHEMA_SHA256 = "be36c702f4fd6c87637442c7dcf27bd89650bde1e1b74688b3f0bae482caee18"
GOLD_ID = "cloud80-20260803-v1"
QUESTION_FIXTURE_PATH = "eval/online_subset_20260803.json"
QUESTION_FIXTURE_SHA256 = "7f9cc4c2470f6aa5dcfef6d928429e6b08fb73453d592e3a188d913128e85e2d"
QUESTION_COUNT = 80
DECISION_SCHEMA_VERSION = "cloud80-gold-approval-decision-v1"
APPROVAL_DECISION = "approve"
SIGNATURE_IDENTITY = "cloud80-gold-approver"
SIGNATURE_NAMESPACE = "cloud80-gold-standard-approval-v1"
AUTHORITY_SNAPSHOT_SCHEMA_VERSION = "cloud80-authority-snapshot-v1"
TRACE_INTEGRITY_SCHEMA_VERSION = "kg-audit-chain-v1"
SHA256_ZERO = "0" * 64
MAX_SAFE_SEQUENCE = 9_007_199_254_740_991
MAX_GOLD_BYTES = 2 * 1024 * 1024
MAX_SCHEMA_BYTES = 256 * 1024
MAX_FIXTURE_BYTES = 2 * 1024 * 1024
MAX_DECISION_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 64 * 1024
MAX_PUBLIC_KEY_BYTES = 16 * 1024
MAX_AUTHORITY_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_TRACE_BYTES = 64 * 1024 * 1024
MAX_ATTESTATION_DECISION_BYTES = 512 * 1024
ATTESTATION_SCHEMA_VERSION = "cloud80-eval-attestation-v1"
ATTESTATION_DECISION = "attest"
ATTESTATION_SIGNATURE_IDENTITY = "cloud80-eval-attester"
ATTESTATION_SIGNATURE_NAMESPACE = "cloud80-eval-attestation-v1"
PREPARE_APPROVAL_EXIT_CODE = 3

APPROVAL_DECISION_FIELDS = frozenset({
    "schema_version",
    "decision",
    "gold_id",
    "gold_sha256",
    "gold_schema_sha256",
    "question_fixture_sha256",
    "question_ids_sha256",
    "question_count",
    "reviewed_question_count",
    "approved_by",
    "reviewer_type",
    "approved_at",
    "public_key_fingerprint",
    "signature_identity",
    "signature_namespace",
})
ATTESTATION_METADATA_FIELDS = frozenset({
    "attested_by",
    "attester_type",
    "attested_at",
    "public_key_fingerprint",
})
GOLD_APPROVAL_ATTESTATION_FIELDS = frozenset({
    "gold_approval_decision_sha256",
    "gold_approval_signature_sha256",
    "gold_approval_public_key_sha256",
    "gold_approval_public_key_fingerprint",
    "gold_approval_approved_by",
    "gold_approval_approved_at",
})
GOLD_APPROVAL_ATTESTATION_HASH_FIELDS = (
    "gold_approval_decision_sha256",
    "gold_approval_signature_sha256",
    "gold_approval_public_key_sha256",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MACHINE_REVIEWER_RE = re.compile(
    r"(?:^|[^a-z0-9])(?:agent|automation|bot|model|gpt|openai|claude|deepseek)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
_SAFE_REFUSAL_RE = re.compile(
    r"证据不足|没有直接证据|没有检索到可支持|无法核实|无法证实|无法确认|"
    r"不在本服务覆盖范围|停止输出|拒绝生成|服务不可用|大模型忙"
)
_REFUSAL_BYPASS_RE = re.compile(
    r"(?:但|但是|不过|然而|其实|仍然|仍|结论是).{0,120}"
    r"(?:\d|必须|应当|不得|禁止|确定|就是|属于|有效|正确)"
)
_REFUSAL_SPECULATION_RE = re.compile(
    r"我猜|猜测|推测|个人认为|大概|也许|或许|可能(?:是|为|可以)|"
    r"应该(?:是|为|可以)|可以|允许|结论(?:是|为)"
)
_HIGH_RISK_RE = re.compile(
    r"\d|[%％]|必须|应当|不得|禁止|安全|法规|规章|条款|执照|"
    r"资格|资质|证书|登记|许可|罚款|处罚|吊销|撤销|有效期|正确答案"
)
_LIST_PREFIX_RE = re.compile(r"^(?:#{1,6}\s*|[-*+]\s+|\d+[.)、]\s*)")
_PRESENTATION_RE = re.compile(
    r"^(?:结构化数据|知识库补充|结论|回答|要点|说明|依据|来源)[:：]?$"
)
_MATCH_NOISE_RE = re.compile(r"[\s，,。.;；:：!?！？、（）()\[\]【】{}“”‘’\"'《》<>]+")
_NEGATED_MATCH_PREFIX_RE = re.compile(
    r"(?:不|并不|并非|不是|并不是|无需|无须|未|没有|不能|不可|不应|不必|"
    r"未必|绝非|否认)$"
)
_REJECTED_MATCH_SUFFIX_RE = re.compile(
    r"^(?:是|属于|为)?(?:错误|错误说法|不正确|不成立|有误|并非事实|并非如此)"
)
_QUOTE_PAIRS = (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'"), ("《", "》"))
_STRICT_SEGMENT_FORBIDDEN_RE = re.compile(
    r"[“”‘’\"'《》?？]|如果|假如|倘若|若是|可能|也许|或许|大概|似乎|"
    r"我猜|猜测|推测|个人认为|有人认为|据说|所谓|错误说法|不正确|不成立"
)


class GoldContractError(ValueError):
    """Raised when Gold, approval, authority, or trace evidence is invalid."""


_FORMAL_CLOUD_GOLD_SOURCE_STATE_FIELDS = (
    "device",
    "inode",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
)
_EXECUTED_CLOUD_GOLD_SOURCE = _open_held_payload(
    Path(__file__),
    "Cloud Gold source",
    max_bytes=4 * 1024 * 1024,
)
_FORMAL_CLOUD_GOLD_SOURCE_SHA256: str | None = None
_FORMAL_CLOUD_GOLD_SOURCE_STATE_IDENTITY: dict[str, int] | None = None
_FORMAL_CLOUD_GOLD_ACTION_CLOSURE: tuple[object, ...] | None = None


def _cloud_gold_source_state_identity() -> dict[str, int]:
    state = _EXECUTED_CLOUD_GOLD_SOURCE.file_state
    return {
        "device": state.device,
        "inode": state.inode,
        "mode": state.mode,
        "nlink": state.link_count,
        "size": state.size,
        "mtime_ns": state.mtime_ns,
        "ctime_ns": state.ctime_ns,
    }


def _current_cloud_gold_action_closure() -> tuple[object, ...]:
    return (main, _main_impl, _parser, _write_exclusive_bytes)


def _install_formal_cloud_gold_bootstrap_context(
    binding: Mapping[str, Any],
) -> None:
    global _FORMAL_CLOUD_GOLD_ACTION_CLOSURE
    global _FORMAL_CLOUD_GOLD_SOURCE_SHA256
    global _FORMAL_CLOUD_GOLD_SOURCE_STATE_IDENTITY

    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
    except OfflineEvidenceError as exc:
        raise GoldContractError(
            "formal Cloud Gold CLI bootstrap context is required"
        ) from exc
    required = {*_FORMAL_CLOUD_GOLD_SOURCE_STATE_FIELDS, "sha256"}
    if (
        not isinstance(binding, Mapping)
        or set(binding) != required
        or not isinstance(binding.get("sha256"), str)
        or not _SHA256_RE.fullmatch(str(binding["sha256"]))
        or any(
            type(binding.get(field)) is not int or int(binding[field]) < 0
            for field in _FORMAL_CLOUD_GOLD_SOURCE_STATE_FIELDS
        )
        or binding["inode"] == 0
        or binding["nlink"] != 1
        or not stat.S_ISREG(binding["mode"])
    ):
        raise GoldContractError("formal Cloud Gold CLI source binding is malformed")
    expected_state = {
        field: int(binding[field])
        for field in _FORMAL_CLOUD_GOLD_SOURCE_STATE_FIELDS
    }
    try:
        _revalidate_held_payload(_EXECUTED_CLOUD_GOLD_SOURCE)
    except DLPError as exc:
        raise GoldContractError(
            "formal Cloud Gold CLI source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_CLOUD_GOLD_SOURCE.payload).hexdigest()
        != binding["sha256"]
        or _cloud_gold_source_state_identity() != expected_state
    ):
        raise GoldContractError(
            "formal Cloud Gold CLI source differs from held bootstrap bytes"
        )
    _FORMAL_CLOUD_GOLD_SOURCE_SHA256 = str(binding["sha256"])
    _FORMAL_CLOUD_GOLD_SOURCE_STATE_IDENTITY = expected_state
    _FORMAL_CLOUD_GOLD_ACTION_CLOSURE = _current_cloud_gold_action_closure()


def _require_formal_cloud_gold_bootstrap_context() -> tuple[object, ...]:
    source_sha256 = _FORMAL_CLOUD_GOLD_SOURCE_SHA256
    source_state = _FORMAL_CLOUD_GOLD_SOURCE_STATE_IDENTITY
    actions = _FORMAL_CLOUD_GOLD_ACTION_CLOSURE
    if (
        not isinstance(source_sha256, str)
        or not _SHA256_RE.fullmatch(source_sha256)
        or not isinstance(source_state, Mapping)
        or set(source_state) != set(_FORMAL_CLOUD_GOLD_SOURCE_STATE_FIELDS)
        or any(
            type(source_state.get(field)) is not int
            or int(source_state[field]) < 0
            for field in _FORMAL_CLOUD_GOLD_SOURCE_STATE_FIELDS
        )
        or source_state["inode"] == 0
        or source_state["nlink"] != 1
        or not stat.S_ISREG(source_state["mode"])
        or not isinstance(actions, tuple)
        or len(actions) != 4
    ):
        raise GoldContractError(
            "formal Cloud Gold CLI bootstrap context is required"
        )
    try:
        _require_formal_bootstrap_context()
        _require_isolated_python()
        _revalidate_held_payload(_EXECUTED_CLOUD_GOLD_SOURCE)
    except (OfflineEvidenceError, DLPError) as exc:
        raise GoldContractError(
            "formal Cloud Gold CLI source binding changed"
        ) from exc
    if (
        hashlib.sha256(_EXECUTED_CLOUD_GOLD_SOURCE.payload).hexdigest()
        != source_sha256
        or _cloud_gold_source_state_identity() != dict(source_state)
        or any(
            current is not expected
            for current, expected in zip(
                _current_cloud_gold_action_closure(), actions, strict=True
            )
        )
    ):
        raise GoldContractError(
            "formal Cloud Gold CLI source or action closure changed"
        )
    return actions


@dataclass(frozen=True)
class TraceChainState:
    records: tuple[dict[str, Any], ...]
    chained_records: tuple[dict[str, Any], ...]
    line_count: int
    legacy_count: int
    last_sequence: int
    chain_head_event_sha256: str | None
    file_sha256: str
    size_bytes: int
    chained_line_sha256s: tuple[str, ...]


DynamicOracle = Callable[
    [str, Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]
]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GoldContractError("value is not canonical finite JSON") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise GoldContractError(f"JSON contains duplicate key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise GoldContractError(f"JSON contains non-finite number: {value}")


def _assert_finite_json(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise GoldContractError(f"JSON contains non-finite number at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite_json(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite_json(child, f"{path}[{index}]")


def strict_json_value(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise GoldContractError(f"{label} must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise GoldContractError(f"{label} must be valid JSON") from exc
    _assert_finite_json(value)
    return value


def strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    value = strict_json_value(raw, label)
    if not isinstance(value, dict):
        raise GoldContractError(f"{label} must be a JSON object")
    return value


def read_regular_bytes(
    path: Path,
    label: str,
    *,
    max_bytes: int,
    require_private_owner: bool = False,
) -> bytes:
    target = Path(path)
    try:
        before = target.lstat()
    except OSError as exc:
        raise GoldContractError(f"{label} cannot be inspected") from exc
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise GoldContractError(f"{label} must be a single-link regular file")
    if before.st_size > max_bytes:
        raise GoldContractError(f"{label} exceeds the size limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise GoldContractError(f"{label} cannot be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise GoldContractError(f"{label} identity changed before read")
        if require_private_owner and (
            opened.st_uid != os.geteuid() or stat.S_IMODE(opened.st_mode) & 0o077
        ):
            raise GoldContractError(
                f"{label} must be owned by the current euid and inaccessible to group/other"
            )
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    data = b"".join(chunks)
    if len(data) != opened.st_size or (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) != (
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_ctime_ns,
    ):
        raise GoldContractError(f"{label} changed during read")
    return data


def _json_type_matches(value: object, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _resolve_local_schema_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise GoldContractError(f"unsupported schema reference: {reference}")
    current: object = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise GoldContractError(f"schema reference does not resolve: {reference}")
        current = current[part]
    if not isinstance(current, dict):
        raise GoldContractError(f"schema reference is not an object: {reference}")
    return current


def validate_json_schema(
    value: object,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str = "$",
) -> None:
    if "$ref" in schema:
        validate_json_schema(
            value,
            _resolve_local_schema_ref(root_schema, str(schema["$ref"])),
            root_schema,
            path,
        )
        return
    if "const" in schema and value != schema["const"]:
        raise GoldContractError(f"schema violation at {path}: const mismatch")
    if "enum" in schema and value not in schema["enum"]:
        raise GoldContractError(f"schema violation at {path}: invalid enum value")
    raw_types = schema.get("type")
    allowed_types = [raw_types] if isinstance(raw_types, str) else list(raw_types or [])
    if allowed_types and not any(_json_type_matches(value, item) for item in allowed_types):
        raise GoldContractError(
            f"schema violation at {path}: expected type {allowed_types}"
        )
    if value is None:
        return
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if key not in value:
                raise GoldContractError(f"schema violation at {path}: missing field {key}")
        extra = set(value) - set(properties)
        additional = schema.get("additionalProperties", True)
        if extra and additional is False:
            raise GoldContractError(
                f"schema violation at {path}: unexpected fields "
                + ", ".join(sorted(extra))
            )
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                validate_json_schema(child, child_schema, root_schema, f"{path}.{key}")
            elif isinstance(additional, dict):
                validate_json_schema(child, additional, root_schema, f"{path}.{key}")
    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise GoldContractError(f"schema violation at {path}: too few items")
        if isinstance(maximum, int) and len(value) > maximum:
            raise GoldContractError(f"schema violation at {path}: too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, child in enumerate(value):
                validate_json_schema(
                    child, item_schema, root_schema, f"{path}[{index}]"
                )
    if isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            raise GoldContractError(f"schema violation at {path}: string too short")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise GoldContractError(f"schema violation at {path}: pattern mismatch")
        if schema.get("format") == "date-time" and parse_datetime(value) is None:
            raise GoldContractError(f"schema violation at {path}: invalid date-time")


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def parse_effective_at(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    try:
        if "T" in normalized:
            if parse_datetime(normalized) is None:
                return None
        else:
            date.fromisoformat(normalized)
    except ValueError:
        return None
    return normalized


def question_ids_sha256(question_ids: list[str]) -> str:
    return sha256_bytes(canonical_json_bytes(question_ids))


def _human_identity(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text and not _MACHINE_REVIEWER_RE.search(text))


def _normalized_human_identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _gold_approval_attestation_metadata(
    basis: Mapping[str, Any],
) -> dict[str, str]:
    if not GOLD_APPROVAL_ATTESTATION_FIELDS.issubset(basis):
        raise GoldContractError("attestation basis is missing Gold approval metadata")
    for field in GOLD_APPROVAL_ATTESTATION_HASH_FIELDS:
        if not _SHA256_RE.fullmatch(str(basis.get(field) or "")):
            raise GoldContractError(f"attestation basis Gold approval hash is invalid: {field}")
    fingerprint = basis.get("gold_approval_public_key_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.startswith("SHA256:"):
        raise GoldContractError("attestation basis Gold approval fingerprint is invalid")
    approved_by = basis.get("gold_approval_approved_by")
    if not isinstance(approved_by, str) or not _human_identity(approved_by):
        raise GoldContractError("attestation basis Gold approver is not a named human")
    approved_at = basis.get("gold_approval_approved_at")
    if not isinstance(approved_at, str) or parse_datetime(approved_at) is None:
        raise GoldContractError("attestation basis Gold approval timestamp is invalid")
    return {
        "public_key_fingerprint": fingerprint,
        "approved_by": approved_by,
        "approved_at": approved_at,
    }


def _require_independent_attester(
    basis: Mapping[str, Any],
    *,
    attested_by: str,
    public_key_fingerprint: str,
) -> None:
    approval = _gold_approval_attestation_metadata(basis)
    if _normalized_human_identity(attested_by) == _normalized_human_identity(
        approval["approved_by"]
    ):
        raise GoldContractError("attestation signer must differ from the Gold approver")
    if public_key_fingerprint == approval["public_key_fingerprint"]:
        raise GoldContractError(
            "attestation public key must differ from the Gold approval public key"
        )


def _contract_issues(contract: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    mode = contract.get("answer_mode")
    required_claims = list(contract.get("required_claim_groups") or [])
    oracle = contract.get("dynamic_oracle")
    if contract.get("scoring_policy_version") != "cloud80-strict-segment-v1":
        issues.append("scoring_policy_version_invalid")
    if mode == "claim_spec":
        if not required_claims and contract.get("safe_refusal_policy") != "required":
            issues.append("required_claim_groups_missing")
        if oracle is not None:
            issues.append("claim_spec_dynamic_oracle_forbidden")
    elif mode == "exact_segment_set":
        if (
            not required_claims
            and contract.get("safe_refusal_policy") != "required"
        ):
            issues.append("exact_required_claim_groups_missing")
        if oracle is not None:
            issues.append("exact_segment_dynamic_oracle_forbidden")
        for claim in required_claims:
            if not list(claim.get("accepted_segments") or []):
                issues.append("accepted_segments_missing")
    elif mode == "dynamic_oracle":
        if not isinstance(oracle, Mapping):
            issues.append("dynamic_oracle_missing")
        if required_claims or list(contract.get("optional_segments") or []):
            issues.append("dynamic_oracle_static_segments_forbidden")
    required_ids = [str(item.get("claim_id") or "") for item in required_claims]
    forbidden_ids = [
        str(item.get("claim_id") or "")
        for item in contract.get("forbidden_claims") or []
    ]
    if len(required_ids) != len(set(required_ids)):
        issues.append("required_claim_ids_not_unique")
    if len(forbidden_ids) != len(set(forbidden_ids)):
        issues.append("forbidden_claim_ids_not_unique")
    synonyms = list(contract.get("acceptable_synonyms") or [])
    canonical_terms = [str(item.get("canonical") or "") for item in synonyms]
    if len(canonical_terms) != len(set(canonical_terms)):
        issues.append("synonym_canonical_terms_not_unique")
    templates = [str(item) for item in contract.get("safe_refusal_templates") or []]
    if not templates:
        issues.append("safe_refusal_templates_missing")
    if len({_normalize_strict_segment(item) for item in templates}) != len(templates):
        issues.append("safe_refusal_templates_not_unique")
    optional_segments = [str(item) for item in contract.get("optional_segments") or []]
    accepted_segments = [
        str(segment)
        for claim in required_claims
        for segment in claim.get("accepted_segments") or []
    ]
    normalized_segments = [
        _normalize_strict_segment(item)
        for item in (*accepted_segments, *optional_segments)
    ]
    if any(not item for item in normalized_segments):
        issues.append("exact_segment_empty_after_normalization")
    if len(normalized_segments) != len(set(normalized_segments)):
        issues.append("exact_segments_not_unique")
    authority_sources = list(contract.get("authority_sources") or [])
    source_names = [str(item.get("source_name") or "") for item in authority_sources]
    if len(source_names) != len(set(source_names)):
        issues.append("authority_source_names_not_unique")
    for source in authority_sources:
        if not _SHA256_RE.fullmatch(str(source.get("sha256") or "")):
            issues.append("authority_source_sha256_missing")
        if parse_effective_at(source.get("effective_at")) is None:
            issues.append("authority_source_effective_at_invalid")
    if contract.get("safe_refusal_policy") == "required":
        if required_claims or optional_segments:
            issues.append("safe_refusal_contract_cannot_require_positive_segments")
        if mode != "exact_segment_set":
            issues.append("safe_refusal_requires_exact_segment_mode")
    return sorted(set(issues))


def _fixture_payload(raw: bytes) -> dict[str, Any]:
    if sha256_bytes(raw) != QUESTION_FIXTURE_SHA256:
        raise GoldContractError("question fixture sha256 mismatch")
    fixture = strict_json_object(raw, "question fixture")
    questions = fixture.get("questions")
    if not isinstance(questions, list) or len(questions) != QUESTION_COUNT:
        raise GoldContractError("question fixture must contain exactly 80 questions")
    if (fixture.get("meta") or {}).get("total") != QUESTION_COUNT:
        raise GoldContractError("question fixture meta.total mismatch")
    ids = [str(item.get("id") or "") for item in questions if isinstance(item, Mapping)]
    if len(ids) != QUESTION_COUNT or any(not item for item in ids) or len(set(ids)) != len(ids):
        raise GoldContractError("question fixture ids must be non-empty and unique")
    for item in questions:
        if not isinstance(item, Mapping) or not str(item.get("question") or "").strip():
            raise GoldContractError("question fixture contains an invalid question")
    return fixture


def validate_gold_standard(
    gold: dict[str, Any],
    schema: dict[str, Any],
    fixture: dict[str, Any],
    *,
    gold_sha256: str,
    schema_sha256: str,
) -> dict[str, Any]:
    if schema_sha256 != GOLD_SCHEMA_SHA256:
        raise GoldContractError("Gold schema sha256 mismatch")
    validate_json_schema(gold, schema, schema)
    if gold.get("schema_version") != GOLD_SCHEMA_VERSION or gold.get("gold_id") != GOLD_ID:
        raise GoldContractError("Gold identity mismatch")
    questions = fixture["questions"]
    ids = [str(item["id"]) for item in questions]
    metadata = gold["question_fixture"]
    if (
        metadata.get("path") != QUESTION_FIXTURE_PATH
        or metadata.get("sha256") != QUESTION_FIXTURE_SHA256
        or metadata.get("question_count") != QUESTION_COUNT
        or metadata.get("question_ids_sha256") != question_ids_sha256(ids)
    ):
        raise GoldContractError("Gold question fixture binding mismatch")
    cases = gold["cases"]
    case_ids = [str(item.get("id") or "") for item in cases]
    if case_ids != ids:
        raise GoldContractError("Gold case ids must exactly match fixture order")

    reviewed = 0
    pending_ids: list[str] = []
    rejected_ids: list[str] = []
    formal_ineligible_ids: list[str] = []
    latest_reviewed_at: datetime | None = None
    case_contexts: dict[str, dict[str, Any]] = {}
    for index, (case, question) in enumerate(zip(cases, questions)):
        case_id = str(case["id"])
        label = f"Gold case {case_id}"
        if case.get("question") != question.get("question"):
            raise GoldContractError(f"{label} question text binding mismatch")
        status_value = case["review_status"]
        blockers = list(case.get("blockers") or [])
        contract = case.get("answer_contract")
        if status_value == "pending":
            pending_ids.append(case_id)
            if any(
                case.get(key) is not None
                for key in ("reviewer_type", "reviewed_by", "reviewed_at", "answer_contract")
            ):
                raise GoldContractError(f"{label} pending review self-asserts completion")
            if not blockers:
                raise GoldContractError(f"{label} pending review must retain blockers")
        else:
            if case.get("reviewer_type") != "human" or not _human_identity(case.get("reviewed_by")):
                raise GoldContractError(f"{label} must be reviewed by a named human")
            reviewed_at = parse_datetime(case.get("reviewed_at"))
            if reviewed_at is None:
                raise GoldContractError(f"{label} reviewed_at must be timezone-aware")
            latest_reviewed_at = max(latest_reviewed_at, reviewed_at) if latest_reviewed_at else reviewed_at
            if status_value == "rejected":
                rejected_ids.append(case_id)
                if not blockers:
                    raise GoldContractError(f"{label} rejected review must retain blockers")
            else:
                reviewed += 1
                if blockers:
                    raise GoldContractError(f"{label} reviewed case cannot retain blockers")
                if not isinstance(contract, Mapping):
                    raise GoldContractError(f"{label} reviewed case needs an answer contract")
                issues = _contract_issues(contract)
                if issues:
                    raise GoldContractError(f"{label} contract is incomplete: {', '.join(issues)}")
                if contract.get("answer_mode") != "exact_segment_set":
                    formal_ineligible_ids.append(case_id)
        case_contexts[case_id] = {
            "index": index,
            "case": case,
            "question": question,
            "answer_contract": contract,
        }

    policy = gold["review_policy"]
    eligible = bool(
        policy.get("status") == "reviewed-pending-signature"
        and reviewed == QUESTION_COUNT
        and not pending_ids
        and not rejected_ids
        and not formal_ineligible_ids
    )
    if policy.get("status") == "reviewed-pending-signature" and not eligible:
        if formal_ineligible_ids:
            raise GoldContractError(
                "formal Gold v1 requires exact_segment_set: "
                + ",".join(formal_ineligible_ids)
            )
        raise GoldContractError("reviewed-pending-signature requires 80 reviewed cases")
    activation_basis = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "decision": APPROVAL_DECISION,
        "gold_id": GOLD_ID,
        "gold_sha256": gold_sha256,
        "gold_schema_sha256": schema_sha256,
        "question_fixture_sha256": QUESTION_FIXTURE_SHA256,
        "question_ids_sha256": metadata["question_ids_sha256"],
        "question_count": QUESTION_COUNT,
        "reviewed_question_count": reviewed,
        "signature_identity": SIGNATURE_IDENTITY,
        "signature_namespace": SIGNATURE_NAMESPACE,
    }
    return {
        "gold": gold,
        "gold_id": GOLD_ID,
        "gold_sha256": gold_sha256,
        "gold_schema_sha256": schema_sha256,
        "questions": questions,
        "question_ids_sha256": metadata["question_ids_sha256"],
        "reviewed_question_count": reviewed,
        "pending_question_ids": pending_ids,
        "rejected_question_ids": rejected_ids,
        "formal_ineligible_question_ids": formal_ineligible_ids,
        "activation_eligible": eligible,
        "activated": False,
        "activation_basis": activation_basis,
        "latest_reviewed_at": latest_reviewed_at,
        "case_contexts": case_contexts,
        "approval": None,
    }


def public_key_identity(raw: bytes) -> tuple[str, str]:
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeError as exc:
        raise GoldContractError("Gold approval public key must be ASCII") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise GoldContractError("Gold approval public key must contain one key")
    parts = lines[0].split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise GoldContractError("Gold approval public key must be ssh-ed25519")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise GoldContractError("Gold approval public key is malformed") from exc
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode(
        "ascii"
    ).rstrip("=")
    return " ".join(parts[:2]), fingerprint


def _verify_ssh_signature(
    decision_bytes: bytes,
    signature_bytes: bytes,
    public_key_bytes: bytes,
    *,
    identity: str,
    namespace: str,
) -> str:
    public_key, fingerprint = public_key_identity(public_key_bytes)
    verifier = shutil.which("ssh-keygen")
    if not verifier:
        raise GoldContractError("ssh-keygen is required for Gold activation")
    with tempfile.TemporaryDirectory(prefix="cloud80-gold-verify-") as raw_tmp:
        temporary = Path(raw_tmp)
        allowed = temporary / "allowed_signers"
        signature = temporary / "gold.sig"
        allowed.write_bytes(f"{identity} {public_key}\n".encode("ascii"))
        signature.write_bytes(signature_bytes)
        os.chmod(allowed, 0o600)
        os.chmod(signature, 0o600)
        try:
            completed = subprocess.run(
                [
                    verifier,
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed),
                    "-I",
                    identity,
                    "-n",
                    namespace,
                    "-s",
                    str(signature),
                ],
                input=decision_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GoldContractError("Gold approval signature verifier failed") from exc
    if completed.returncode:
        detail = completed.stdout.decode("utf-8", errors="replace")[-1000:]
        raise GoldContractError(f"Gold approval signature verification failed: {detail}")
    return fingerprint


def verify_gold_activation(
    context: dict[str, Any],
    decision_path: Path,
    signature_path: Path,
    public_key_path: Path,
    *,
    expected_fingerprint: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if context.get("activation_eligible") is not True:
        raise GoldContractError("Gold is not eligible for activation")
    if not str(expected_fingerprint or "").startswith("SHA256:"):
        raise GoldContractError("expected public key fingerprint is required")
    decision_bytes = read_regular_bytes(
        decision_path, "Gold approval decision", max_bytes=MAX_DECISION_BYTES
    )
    signature_bytes = read_regular_bytes(
        signature_path, "Gold approval signature", max_bytes=MAX_SIGNATURE_BYTES
    )
    public_key_bytes = read_regular_bytes(
        public_key_path, "Gold approval public key", max_bytes=MAX_PUBLIC_KEY_BYTES
    )
    decision = strict_json_object(decision_bytes, "Gold approval decision")
    if canonical_json_bytes(decision) != decision_bytes:
        raise GoldContractError("Gold approval decision must use canonical JSON bytes")
    if set(decision) != APPROVAL_DECISION_FIELDS:
        raise GoldContractError("Gold approval decision fields drifted")
    for key, expected in context["activation_basis"].items():
        if decision.get(key) != expected:
            raise GoldContractError(f"Gold approval binding mismatch: {key}")
    if decision.get("reviewer_type") != "human" or not _human_identity(
        decision.get("approved_by")
    ):
        raise GoldContractError("Gold approval must be an explicit human decision")
    approved_at = parse_datetime(decision.get("approved_at"))
    if approved_at is None:
        raise GoldContractError("Gold approval timestamp must be timezone-aware")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if approved_at > current + timedelta(minutes=5):
        raise GoldContractError("Gold approval timestamp is too far in the future")
    latest_reviewed_at = context.get("latest_reviewed_at")
    if isinstance(latest_reviewed_at, datetime) and approved_at < latest_reviewed_at:
        raise GoldContractError("Gold approval predates the latest case review")
    fingerprint = _verify_ssh_signature(
        decision_bytes,
        signature_bytes,
        public_key_bytes,
        identity=SIGNATURE_IDENTITY,
        namespace=SIGNATURE_NAMESPACE,
    )
    if decision.get("public_key_fingerprint") != fingerprint:
        raise GoldContractError("Gold decision public key fingerprint mismatch")
    if fingerprint != expected_fingerprint:
        raise GoldContractError("Gold public key does not match expected fingerprint")
    activated = dict(context)
    activated["activated"] = True
    activated["approval"] = {
        "decision_sha256": sha256_bytes(decision_bytes),
        "signature_sha256": sha256_bytes(signature_bytes),
        "public_key_sha256": sha256_bytes(public_key_bytes),
        "public_key_fingerprint": fingerprint,
        "approved_by": decision["approved_by"],
        "approved_at": decision["approved_at"],
        "signature_identity": SIGNATURE_IDENTITY,
        "signature_namespace": SIGNATURE_NAMESPACE,
    }
    return activated


def build_gold_approval_decision_bytes(
    context: Mapping[str, Any],
    *,
    approved_by: str,
    approved_at: str,
    public_key_bytes: bytes,
    expected_fingerprint: str,
    now: datetime | None = None,
) -> bytes:
    if context.get("activation_eligible") is not True:
        raise GoldContractError("Gold is not eligible for an approval decision")
    if not _human_identity(approved_by):
        raise GoldContractError("Gold approval requires a named human")
    timestamp = parse_datetime(approved_at)
    if timestamp is None:
        raise GoldContractError("Gold approval timestamp must be timezone-aware")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if timestamp > current + timedelta(minutes=5):
        raise GoldContractError("Gold approval timestamp is too far in the future")
    latest_reviewed_at = context.get("latest_reviewed_at")
    if isinstance(latest_reviewed_at, datetime) and timestamp < latest_reviewed_at:
        raise GoldContractError("Gold approval predates the latest case review")
    _public_key, fingerprint = public_key_identity(public_key_bytes)
    if fingerprint != expected_fingerprint:
        raise GoldContractError("Gold approval public key does not match expected fingerprint")
    decision = {
        **dict(context["activation_basis"]),
        "approved_by": approved_by,
        "reviewer_type": "human",
        "approved_at": approved_at,
        "public_key_fingerprint": fingerprint,
    }
    if set(decision) != APPROVAL_DECISION_FIELDS:
        raise GoldContractError("Gold approval decision fields drifted")
    return canonical_json_bytes(decision)


def load_gold_standard(
    gold_path: Path,
    schema_path: Path,
    fixture_path: Path,
    *,
    decision_path: Path | None = None,
    signature_path: Path | None = None,
    public_key_path: Path | None = None,
    expected_fingerprint: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    schema_bytes = read_regular_bytes(schema_path, "Gold schema", max_bytes=MAX_SCHEMA_BYTES)
    gold_bytes = read_regular_bytes(gold_path, "Gold fixture", max_bytes=MAX_GOLD_BYTES)
    fixture_bytes = read_regular_bytes(
        fixture_path, "question fixture", max_bytes=MAX_FIXTURE_BYTES
    )
    schema = strict_json_object(schema_bytes, "Gold schema")
    gold = strict_json_object(gold_bytes, "Gold fixture")
    fixture = _fixture_payload(fixture_bytes)
    context = validate_gold_standard(
        gold,
        schema,
        fixture,
        gold_sha256=sha256_bytes(gold_bytes),
        schema_sha256=sha256_bytes(schema_bytes),
    )
    approval_values = (
        decision_path,
        signature_path,
        public_key_path,
        expected_fingerprint,
    )
    if any(value is not None for value in approval_values):
        if not all(value is not None for value in approval_values):
            raise GoldContractError(
                "Gold decision, signature, public key, and expected fingerprint are required together"
            )
        context = verify_gold_activation(
            context,
            decision_path,
            signature_path,
            public_key_path,
            expected_fingerprint=str(expected_fingerprint),
            now=now,
        )
    return context


def gold_validation_metadata(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "cloud80-gold-validation-result-v1",
        "gold_id": context["gold_id"],
        "gold_sha256": context["gold_sha256"],
        "gold_schema_sha256": context["gold_schema_sha256"],
        "question_ids_sha256": context["question_ids_sha256"],
        "question_count": QUESTION_COUNT,
        "reviewed_question_count": context["reviewed_question_count"],
        "pending_question_count": len(context["pending_question_ids"]),
        "rejected_question_count": len(context["rejected_question_ids"]),
        "activation_eligible": bool(context["activation_eligible"]),
        "activated": bool(context["activated"]),
        "approval": context.get("approval"),
    }


def build_attestation_decision_bytes(
    basis: Mapping[str, Any],
    *,
    attested_by: str,
    attested_at: str,
    public_key_bytes: bytes,
    expected_fingerprint: str,
    now: datetime | None = None,
) -> bytes:
    if basis.get("schema_version") != ATTESTATION_SCHEMA_VERSION:
        raise GoldContractError("attestation basis schema is unsupported")
    if basis.get("decision") != ATTESTATION_DECISION:
        raise GoldContractError("attestation basis decision is invalid")
    if (
        basis.get("signature_identity") != ATTESTATION_SIGNATURE_IDENTITY
        or basis.get("signature_namespace") != ATTESTATION_SIGNATURE_NAMESPACE
    ):
        raise GoldContractError("attestation signature protocol drifted")
    if not isinstance(attested_by, str) or not _human_identity(attested_by):
        raise GoldContractError("attestation requires a named human")
    timestamp = parse_datetime(attested_at)
    if timestamp is None:
        raise GoldContractError("attestation timestamp must be timezone-aware")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if timestamp > current + timedelta(minutes=5):
        raise GoldContractError("attestation timestamp is too far in the future")
    collected_at = parse_datetime(basis.get("collected_at"))
    if collected_at is None or timestamp < collected_at:
        raise GoldContractError("attestation timestamp predates the collection")
    _public_key, fingerprint = public_key_identity(public_key_bytes)
    if fingerprint != expected_fingerprint:
        raise GoldContractError("attestation public key does not match expected fingerprint")
    _require_independent_attester(
        basis,
        attested_by=attested_by,
        public_key_fingerprint=fingerprint,
    )
    decision = {
        **dict(basis),
        "attested_by": attested_by,
        "attester_type": "human",
        "attested_at": attested_at,
        "public_key_fingerprint": fingerprint,
    }
    return canonical_json_bytes(decision)


def verify_attestation_decision(
    expected_basis: Mapping[str, Any],
    decision_path: Path,
    signature_path: Path,
    public_key_path: Path,
    *,
    expected_fingerprint: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not str(expected_fingerprint or "").startswith("SHA256:"):
        raise GoldContractError("expected attestation public key fingerprint is required")
    decision_bytes = read_regular_bytes(
        decision_path,
        "evaluation attestation decision",
        max_bytes=MAX_ATTESTATION_DECISION_BYTES,
    )
    signature_bytes = read_regular_bytes(
        signature_path,
        "evaluation attestation signature",
        max_bytes=MAX_SIGNATURE_BYTES,
    )
    public_key_bytes = read_regular_bytes(
        public_key_path,
        "evaluation attestation public key",
        max_bytes=MAX_PUBLIC_KEY_BYTES,
    )
    decision = strict_json_object(decision_bytes, "evaluation attestation decision")
    if canonical_json_bytes(decision) != decision_bytes:
        raise GoldContractError("evaluation attestation decision must use canonical JSON bytes")
    if set(decision) != set(expected_basis) | ATTESTATION_METADATA_FIELDS:
        raise GoldContractError("evaluation attestation decision fields drifted")
    for key, expected in expected_basis.items():
        if decision.get(key) != expected:
            raise GoldContractError(f"evaluation attestation binding mismatch: {key}")
    if (
        decision.get("attester_type") != "human"
        or not isinstance(decision.get("attested_by"), str)
        or not _human_identity(decision.get("attested_by"))
    ):
        raise GoldContractError("evaluation attestation requires a named human")
    attested_at = parse_datetime(decision.get("attested_at"))
    if attested_at is None:
        raise GoldContractError("evaluation attestation timestamp must be timezone-aware")
    collected_at = parse_datetime(expected_basis.get("collected_at"))
    if collected_at is None or attested_at < collected_at:
        raise GoldContractError("evaluation attestation predates the collection")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if attested_at > current + timedelta(minutes=5):
        raise GoldContractError("evaluation attestation timestamp is too far in the future")
    fingerprint = _verify_ssh_signature(
        decision_bytes,
        signature_bytes,
        public_key_bytes,
        identity=ATTESTATION_SIGNATURE_IDENTITY,
        namespace=ATTESTATION_SIGNATURE_NAMESPACE,
    )
    if decision.get("public_key_fingerprint") != fingerprint:
        raise GoldContractError("evaluation attestation public key fingerprint mismatch")
    if fingerprint != expected_fingerprint:
        raise GoldContractError("evaluation attestation key does not match expected fingerprint")
    _require_independent_attester(
        expected_basis,
        attested_by=decision["attested_by"],
        public_key_fingerprint=fingerprint,
    )
    return {
        "verified": True,
        "decision_sha256": sha256_bytes(decision_bytes),
        "signature_sha256": sha256_bytes(signature_bytes),
        "public_key_sha256": sha256_bytes(public_key_bytes),
        "public_key_fingerprint": fingerprint,
        "attested_by": decision["attested_by"],
        "attested_at": decision["attested_at"],
        "signature_identity": ATTESTATION_SIGNATURE_IDENTITY,
        "signature_namespace": ATTESTATION_SIGNATURE_NAMESPACE,
    }


def parse_authority_snapshot_bytes(raw: bytes) -> dict[str, dict[str, str]]:
    payload = strict_json_object(raw, "authority snapshot")
    if set(payload) != {"schema_version", "sources"}:
        raise GoldContractError("authority snapshot fields drifted")
    if payload.get("schema_version") != AUTHORITY_SNAPSHOT_SCHEMA_VERSION:
        raise GoldContractError("authority snapshot schema is unsupported")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise GoldContractError("authority snapshot sources must be an array")
    result: dict[str, dict[str, str]] = {}
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping) or set(source) != {
            "source_name",
            "sha256",
            "effective_at",
        }:
            raise GoldContractError(f"authority snapshot source {index} is invalid")
        name = str(source.get("source_name") or "").strip()
        digest = str(source.get("sha256") or "")
        effective_at = parse_effective_at(source.get("effective_at"))
        if not name or name in result or not _SHA256_RE.fullmatch(digest) or not effective_at:
            raise GoldContractError(f"authority snapshot source {index} is invalid")
        result[name] = {
            "sha256": digest,
            "effective_at": effective_at,
        }
    return result


def load_authority_snapshot(path: Path) -> dict[str, dict[str, str]]:
    raw = read_regular_bytes(
        path, "authority snapshot", max_bytes=MAX_AUTHORITY_SNAPSHOT_BYTES
    )
    return parse_authority_snapshot_bytes(raw)


def _authority_reasons(
    contract: Mapping[str, Any],
    authority_snapshot: Mapping[str, Mapping[str, str]] | None,
) -> list[str]:
    if authority_snapshot is None:
        return ["authority_snapshot_missing"]
    reasons: list[str] = []
    for expected in contract.get("authority_sources") or []:
        name = str(expected.get("source_name") or "")
        actual = authority_snapshot.get(name)
        if actual is None:
            reasons.append(f"authority_source_missing:{name}")
        elif actual.get("sha256") != expected.get("sha256"):
            reasons.append(f"authority_source_sha256_drift:{name}")
        elif actual.get("effective_at") != expected.get("effective_at"):
            reasons.append(f"authority_source_effective_at_drift:{name}")
    return reasons


def _normalize_match_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return _MATCH_NOISE_RE.sub("", text)


def _expression_variants(
    expression: str,
    synonyms: list[Mapping[str, Any]],
) -> set[str]:
    variants = {str(expression)}
    for synonym in synonyms:
        terms = [
            str(synonym.get("canonical") or ""),
            *(str(item) for item in synonym.get("variants") or []),
        ]
        terms = [item for item in terms if item]
        expanded = set(variants)
        for value in tuple(variants):
            for source in terms:
                if source not in value:
                    continue
                for replacement in terms:
                    expanded.add(value.replace(source, replacement))
                    if len(expanded) >= 128:
                        return expanded
        variants = expanded
    return variants


def _expression_matches(
    answer: str,
    expression: str,
    synonyms: list[Mapping[str, Any]],
) -> bool:
    normalized_answer = _normalize_match_text(answer)
    normalized_variants = {
        _normalize_match_text(variant)
        for variant in _expression_variants(expression, synonyms)
        if _normalize_match_text(variant)
    }
    quoted_fragments: list[str] = []
    normalized_raw = unicodedata.normalize("NFKC", str(answer or "")).casefold()
    for opening, closing in _QUOTE_PAIRS:
        if opening == closing:
            parts = normalized_raw.split(opening)
            quoted_fragments.extend(parts[index] for index in range(1, len(parts), 2))
            continue
        cursor = 0
        while True:
            start = normalized_raw.find(opening, cursor)
            if start < 0:
                break
            end = normalized_raw.find(closing, start + len(opening))
            if end < 0:
                break
            quoted_fragments.append(normalized_raw[start + len(opening):end])
            cursor = end + len(closing)
    normalized_quotes = [_normalize_match_text(item) for item in quoted_fragments]

    for variant in normalized_variants:
        offset = 0
        while True:
            index = normalized_answer.find(variant, offset)
            if index < 0:
                break
            prefix = normalized_answer[max(0, index - 16):index]
            suffix = normalized_answer[index + len(variant):index + len(variant) + 20]
            quoted = any(variant in fragment for fragment in normalized_quotes)
            if (
                not quoted
                and _NEGATED_MATCH_PREFIX_RE.search(prefix) is None
                and _REJECTED_MATCH_SUFFIX_RE.search(suffix) is None
            ):
                return True
            offset = index + max(1, len(variant))
    return False


def _normalize_strict_segment(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = _LIST_PREFIX_RE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip("。！？!?；;").strip()


def _strict_segment_variants(
    segment: object,
    synonyms: list[Mapping[str, Any]],
) -> set[str]:
    return {
        normalized
        for item in _expression_variants(str(segment or ""), synonyms)
        if (normalized := _normalize_strict_segment(item))
    }


def _strict_answer_segments(answer: object) -> tuple[list[str], list[str]]:
    text = str(answer or "").strip()
    reasons: list[str] = []
    if not text:
        return [], ["answer_empty"]
    if _STRICT_SEGMENT_FORBIDDEN_RE.search(text):
        reasons.append("strict_segment_unsafe_expression")
    segments: list[str] = []
    for raw_line in text.splitlines():
        line = _LIST_PREFIX_RE.sub("", raw_line.strip()).strip()
        if not line or _PRESENTATION_RE.fullmatch(line):
            continue
        for part in re.split(r"[。！？!?；;]+", line):
            normalized = _normalize_strict_segment(part)
            if normalized:
                segments.append(normalized)
    if not segments:
        reasons.append("answer_segments_missing")
    return segments, reasons


def _matches_safe_refusal_template(
    answer: object,
    templates: list[object],
) -> bool:
    return isinstance(answer, str) and answer in {
        item for item in templates if isinstance(item, str)
    }


def _answer_segments(answer: object) -> list[str]:
    segments: list[str] = []
    for raw_line in str(answer or "").splitlines():
        line = _LIST_PREFIX_RE.sub("", raw_line.strip()).strip()
        if not line or _PRESENTATION_RE.fullmatch(line):
            continue
        if line.endswith(("：", ":")) and len(line) <= 24:
            continue
        for part in re.split(r"(?<=[，,。！？!?；;])\s*", line):
            if _normalize_match_text(part):
                segments.append(part.strip())
    return segments


def is_safe_refusal_answer(answer: object) -> bool:
    text = str(answer or "").strip()
    residual = _SAFE_REFUSAL_RE.sub("", text)
    if (
        not text
        or _REFUSAL_BYPASS_RE.search(text)
        or _REFUSAL_SPECULATION_RE.search(residual)
        or _HIGH_RISK_RE.search(residual)
    ):
        return False
    segments = _answer_segments(text)
    return bool(segments) and all(_SAFE_REFUSAL_RE.search(item) for item in segments)


def evaluate_gold_answer(
    case_context: Mapping[str, Any],
    answer: object,
    *,
    authority_snapshot: Mapping[str, Mapping[str, str]] | None,
    oracle_registry: Mapping[str, DynamicOracle] | None = None,
    oracle_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = case_context.get("answer_contract")
    if not isinstance(contract, Mapping):
        return {
            "evaluated": False,
            "correct": False,
            "safe_refusal": is_safe_refusal_answer(answer),
            "reason_codes": ["gold_case_not_reviewed"],
            "required_claims_passed": 0,
            "required_claims_total": 0,
            "forbidden_claims_hit": [],
            "oracle": None,
        }
    answer_text = answer if isinstance(answer, str) else ""
    safe_refusal = _matches_safe_refusal_template(
        answer_text,
        list(contract.get("safe_refusal_templates") or []),
    )
    reasons = _authority_reasons(contract, authority_snapshot)
    refusal_policy = contract.get("safe_refusal_policy")
    if refusal_policy == "forbidden" and safe_refusal:
        reasons.append("unexpected_safe_refusal")
    if refusal_policy == "required" and not safe_refusal:
        reasons.append("safe_refusal_not_exact")

    synonyms = list(contract.get("acceptable_synonyms") or [])
    required_passed = 0
    required_claims = list(contract.get("required_claim_groups") or [])
    mode = contract.get("answer_mode")
    if mode == "exact_segment_set" and refusal_policy != "required":
        answer_segments, segment_reasons = _strict_answer_segments(answer_text)
        reasons.extend(segment_reasons)
        allowed_segments = {
            variant
            for claim in required_claims
            for segment in claim.get("accepted_segments") or []
            for variant in _strict_segment_variants(segment, synonyms)
        }
        allowed_segments.update(
            variant
            for segment in contract.get("optional_segments") or []
            for variant in _strict_segment_variants(segment, synonyms)
        )
        for claim in required_claims:
            claim_segments = {
                variant
                for segment in claim.get("accepted_segments") or []
                for variant in _strict_segment_variants(segment, synonyms)
            }
            if any(segment in claim_segments for segment in answer_segments):
                required_passed += 1
            else:
                reasons.append(f"required_claim_missing:{claim.get('claim_id')}")
        for segment in answer_segments:
            if segment not in allowed_segments:
                digest = sha256_bytes(segment.encode("utf-8"))[:12]
                reasons.append(f"unscored_answer_segment:{digest}")
    elif mode == "claim_spec":
        for claim in required_claims:
            claim_passed = all(
                any(
                    _expression_matches(answer_text, str(expression), synonyms)
                    for expression in expression_group
                )
                for expression_group in claim.get("expression_groups") or []
            )
            if claim_passed:
                required_passed += 1
            else:
                reasons.append(f"required_claim_missing:{claim.get('claim_id')}")

    forbidden_hits: list[str] = []
    for claim in contract.get("forbidden_claims") or []:
        if any(
            _expression_matches(answer_text, str(expression), synonyms)
            for expression in claim.get("expressions") or []
        ):
            claim_id = str(claim.get("claim_id") or "")
            forbidden_hits.append(claim_id)
            reasons.append(f"forbidden_claim_present:{claim_id}")

    oracle_result: dict[str, Any] | None = None
    oracle = contract.get("dynamic_oracle")
    if mode == "dynamic_oracle":
        oracle_name = str((oracle or {}).get("name") or "")
        callable_oracle = (oracle_registry or {}).get(oracle_name)
        if not callable(callable_oracle):
            reasons.append(f"dynamic_oracle_unavailable:{oracle_name}")
        else:
            try:
                raw_result = callable_oracle(
                    answer_text,
                    dict((oracle or {}).get("parameters") or {}),
                    dict(oracle_context or {}),
                )
            except Exception as exc:
                reasons.append(f"dynamic_oracle_error:{type(exc).__name__}")
            else:
                if (
                    not isinstance(raw_result, Mapping)
                    or not isinstance(raw_result.get("passed"), bool)
                    or not isinstance(raw_result.get("reason_codes", []), list)
                    or any(
                        not isinstance(item, str)
                        for item in raw_result.get("reason_codes", [])
                    )
                ):
                    reasons.append("dynamic_oracle_invalid_result")
                else:
                    oracle_passed = raw_result["passed"]
                    oracle_reasons = list(raw_result.get("reason_codes") or [])
                    if (oracle_passed and oracle_reasons) or (
                        not oracle_passed and not oracle_reasons
                    ):
                        reasons.append("dynamic_oracle_result_inconsistent")
                    else:
                        oracle_result = {
                            "name": oracle_name,
                            "passed": oracle_passed,
                            "reason_codes": oracle_reasons,
                        }
                        if oracle_passed is not True:
                            reasons.extend(oracle_reasons)
    return {
        "evaluated": True,
        "correct": not reasons,
        "safe_refusal": safe_refusal,
        "reason_codes": list(dict.fromkeys(reasons)),
        "required_claims_passed": required_passed,
        "required_claims_total": len(required_claims),
        "forbidden_claims_hit": forbidden_hits,
        "oracle": oracle_result,
    }


def verify_trace_bytes(data: bytes) -> TraceChainState:
    if len(data) > MAX_TRACE_BYTES:
        raise GoldContractError("trace log exceeds the size limit")
    if not data or not data.endswith(b"\n"):
        raise GoldContractError("trace log is empty or has a partial line")
    lines = data.splitlines(keepends=True)
    if any(line == b"\n" for line in lines):
        raise GoldContractError("trace log contains a blank line")
    records: list[dict[str, Any]] = []
    chained: list[dict[str, Any]] = []
    chained_line_sha256s: list[str] = []
    legacy_lines: list[bytes] = []
    chain_started = False
    last_sequence = 0
    last_raw: bytes | None = None
    last_event: str | None = None
    required_fields = {
        "schema_version",
        "sequence",
        "previous_event_sha256",
        "event_sha256",
    }
    legacy_fields = {"legacy_prefix_sha256", "legacy_prefix_size_bytes"}
    for line_number, raw_line in enumerate(lines, start=1):
        try:
            record = strict_json_object(raw_line[:-1], f"trace line {line_number}")
        except GoldContractError as exc:
            raise GoldContractError(f"trace line {line_number} is invalid") from exc
        integrity = record.get("integrity")
        if integrity is None:
            if chain_started:
                raise GoldContractError("legacy trace appears after hash chain start")
            legacy_lines.append(raw_line)
            records.append(record)
            last_raw = raw_line
            continue
        if not isinstance(integrity, Mapping):
            raise GoldContractError("trace integrity envelope is invalid")
        fields = set(integrity)
        if not required_fields.issubset(fields) or not fields.issubset(
            required_fields | legacy_fields
        ):
            raise GoldContractError("trace integrity envelope fields drifted")
        if fields & legacy_fields and fields & legacy_fields != legacy_fields:
            raise GoldContractError("trace legacy prefix envelope is incomplete")
        if integrity.get("schema_version") != TRACE_INTEGRITY_SCHEMA_VERSION:
            raise GoldContractError("trace integrity schema is unsupported")
        sequence = integrity.get("sequence")
        previous = integrity.get("previous_event_sha256")
        event = integrity.get("event_sha256")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not 1 <= sequence <= MAX_SAFE_SEQUENCE
            or not _SHA256_RE.fullmatch(str(previous or ""))
            or not _SHA256_RE.fullmatch(str(event or ""))
        ):
            raise GoldContractError("trace integrity sequence or digest is invalid")
        unsigned = dict(record)
        unsigned_integrity = dict(integrity)
        del unsigned_integrity["event_sha256"]
        unsigned["integrity"] = unsigned_integrity
        if sha256_bytes(canonical_json_bytes(unsigned)) != event:
            raise GoldContractError("trace event self hash is invalid")
        if raw_line != canonical_json_bytes(record) + b"\n":
            raise GoldContractError("trace chain line is not canonical JSONL")
        if not chain_started:
            if sequence != 1:
                raise GoldContractError("trace chain must start at sequence 1")
            if legacy_lines:
                prefix = b"".join(legacy_lines)
                if (
                    previous != sha256_bytes(legacy_lines[-1])
                    or integrity.get("legacy_prefix_sha256") != sha256_bytes(prefix)
                    or integrity.get("legacy_prefix_size_bytes") != len(prefix)
                ):
                    raise GoldContractError("trace legacy prefix anchor is invalid")
            elif previous != SHA256_ZERO or fields & legacy_fields:
                raise GoldContractError("trace genesis anchor is invalid")
            chain_started = True
        elif sequence != last_sequence + 1 or previous != sha256_bytes(last_raw or b""):
            raise GoldContractError("trace hash chain is discontinuous")
        records.append(record)
        chained.append(record)
        chained_line_sha256s.append(sha256_bytes(raw_line))
        last_sequence = sequence
        last_event = str(event)
        last_raw = raw_line
    if not chained:
        raise GoldContractError("trace log does not contain a hash chain")
    return TraceChainState(
        records=tuple(records),
        chained_records=tuple(chained),
        line_count=len(records),
        legacy_count=len(legacy_lines),
        last_sequence=last_sequence,
        chain_head_event_sha256=last_event,
        file_sha256=sha256_bytes(data),
        size_bytes=len(data),
        chained_line_sha256s=tuple(chained_line_sha256s),
    )


def verify_trace_file(path: Path) -> TraceChainState:
    data = read_regular_bytes(
        path,
        "trace log",
        max_bytes=MAX_TRACE_BYTES,
        require_private_owner=True,
    )
    return verify_trace_bytes(data)


def bind_results_to_trace(
    results: list[Mapping[str, Any]],
    trace_state: TraceChainState,
) -> dict[str, Any]:
    if len(results) != QUESTION_COUNT:
        raise GoldContractError("formal trace binding requires exactly 80 results")
    trace_ids = [str(item.get("trace_id") or "").strip() for item in results]
    if any(not trace_id for trace_id in trace_ids) or len(set(trace_ids)) != QUESTION_COUNT:
        raise GoldContractError("result trace ids must be non-empty and unique")
    by_trace_id: dict[str, list[Mapping[str, Any]]] = {}
    for record in trace_state.chained_records:
        trace_id = str(record.get("trace_id") or "").strip()
        if trace_id:
            by_trace_id.setdefault(trace_id, []).append(record)
    for result, trace_id in zip(results, trace_ids):
        matches = by_trace_id.get(trace_id, [])
        if len(matches) != 1:
            raise GoldContractError(
                f"trace id must bind exactly one chained record: {trace_id}"
            )
        trace_route = str(matches[0].get("route") or "")
        result_route = str(result.get("route") or "")
        if trace_route and trace_route != result_route:
            raise GoldContractError(f"trace route mismatch: {trace_id}")
    return {
        "verified": True,
        "matched_trace_count": QUESTION_COUNT,
        "trace_line_count": trace_state.line_count,
        "trace_legacy_count": trace_state.legacy_count,
        "trace_last_sequence": trace_state.last_sequence,
        "trace_chain_head_event_sha256": trace_state.chain_head_event_sha256,
    }


def _write_exclusive_bytes(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise GoldContractError(f"refusing to overwrite approval decision: {path}") from exc
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("approval decision write made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a canonical Cloud 80 Gold approval candidate for external SSHSIG"
        )
    )
    repo_root = Path(__file__).resolve().parents[3]
    parser.add_argument(
        "--prepare-approval-candidate",
        action="store_true",
        required=True,
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=repo_root / "eval" / "cloud80_gold_standard_v1.json",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=repo_root / "eval" / "cloud80_gold_standard_v1.schema.json",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=repo_root / "eval" / "online_subset_20260803.json",
    )
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approved-at", required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--expected-fingerprint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _main_impl(
    argv: list[str] | None = None,
    *,
    _action_closure: tuple[object, ...] | None = None,
) -> int:
    actions = (
        (_parser, _write_exclusive_bytes)
        if _action_closure is None
        else _action_closure
    )
    if (
        not isinstance(actions, tuple)
        or len(actions) != 2
        or any(not callable(action) for action in actions)
    ):
        raise GoldContractError("Cloud Gold CLI action closure is malformed")
    parser_action, writer_action = actions
    args = parser_action().parse_args(argv)
    try:
        context = load_gold_standard(args.gold, args.schema, args.fixture)
        public_key_bytes = read_regular_bytes(
            args.public_key,
            "Gold approval public key",
            max_bytes=MAX_PUBLIC_KEY_BYTES,
        )
        decision_bytes = build_gold_approval_decision_bytes(
            context,
            approved_by=args.approved_by,
            approved_at=args.approved_at,
            public_key_bytes=public_key_bytes,
            expected_fingerprint=args.expected_fingerprint,
        )
        writer_action(args.output, decision_bytes)
    except (GoldContractError, OSError, ValueError) as exc:
        raise SystemExit(f"Gold approval candidate preparation failed: {exc}") from exc
    result = {
        "schema_version": "cloud80-gold-approval-candidate-v1",
        "status": "pending_external_signature",
        "activated": False,
        "formal_approval_receipt": False,
        "candidate_path": str(args.output),
        "candidate_sha256": sha256_bytes(decision_bytes),
        "signature_identity": SIGNATURE_IDENTITY,
        "signature_namespace": SIGNATURE_NAMESPACE,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return PREPARE_APPROVAL_EXIT_CODE


def main(argv: list[str] | None = None) -> int:
    try:
        actions = _require_formal_cloud_gold_bootstrap_context()
    except GoldContractError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    return actions[1](argv, _action_closure=actions[2:])


if __name__ == "__main__":
    raise SystemExit(main())
