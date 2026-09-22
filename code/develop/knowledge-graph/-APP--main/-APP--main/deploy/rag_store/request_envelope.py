#!/usr/bin/env python3
"""Strict request boundary for knowledge-query routing and planning."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "kg-request-envelope-v1"
RISK_LEVELS = ("low", "standard", "high", "critical")
TIMELINESS_LEVELS = ("stable", "current", "latest")
ALLOWED_SOURCES = (
    "csa",
    "sqlite_exact",
    "bm25",
    "dense",
    "neo4j",
    "official_api",
    "web",
)
DEFAULT_ALLOWED_SOURCES = ALLOWED_SOURCES
POST_FIELDS = {"user_query", "risk_level", "timeliness", "allowed_sources"}
GET_FIELDS = POST_FIELDS | {"q", "embedding"}

_CONTROL_BLOCKS = {
    name: re.compile(
        rf"<{name}\b[^>]*>.*?</{name}>",
        re.IGNORECASE | re.DOTALL,
    )
    for name in (
        "codex_internal_context",
        "environment_context",
        "app_context",
        "subagent_context",
        "tool_context",
    )
}
_INTERNAL_PREFIX = re.compile(
    r"^\s*(?:"
    r"\[(?:Subagent Context|Subagent Task|Inter-session message)\]"
    r"|Before accepting the previous final answer"
    r"|Message Type:\s*(?:MESSAGE|FINAL_ANSWER)\b"
    r")",
    re.IGNORECASE | re.MULTILINE,
)
_CONTROL_ROLE_PREFIX = re.compile(
    r"^\s*(?:system|developer|assistant|tool)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)
_CONTROL_TAG = re.compile(
    r"</?(?:codex_internal_context|environment_context|app_context|"
    r"subagent_context|tool_context)\b[^>]*>",
    re.IGNORECASE,
)
_HIGH_RISK_PATTERN = re.compile(
    r"法规|条款|法律|CCAR|价格|费用|薪资|工资|员工|学员|客户|考勤|"
    r"正确答案|参考答案|多少|比例|百分比|排名|安全|避让|证书|资质"
)
_CRITICAL_RISK_PATTERN = re.compile(
    r"生产(?:写入|删除|清理|覆盖|发布)|批量删除|直接写(?:入)?(?:数据库|图谱)|"
    r"执行\s*(?:SQL|Cypher)|release\s+apply|rollback",
    re.IGNORECASE,
)
_LATEST_PATTERN = re.compile(r"最新|今天|今日|刚刚|实时|当前时刻|截至现在")
_CURRENT_PATTERN = re.compile(r"当前|目前|最近|现行|在职|在招|未完成|剩余")


class RequestEnvelopeError(ValueError):
    """A request cannot be reduced to the allowlisted routing contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RequestEnvelope:
    user_query: str
    risk_level: str
    timeliness: str
    allowed_sources: tuple[str, ...]
    fingerprint: str
    isolation: Mapping[str, Any]
    schema_version: str = SCHEMA_VERSION

    def allows(self, source: str) -> bool:
        return source in self.allowed_sources

    def to_dict(self, *, include_query: bool = True) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "risk_level": self.risk_level,
            "timeliness": self.timeliness,
            "allowed_sources": list(self.allowed_sources),
            "fingerprint": self.fingerprint,
            "isolation": dict(self.isolation),
        }
        if include_query:
            payload["user_query"] = self.user_query
        return payload


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RequestEnvelopeError("invalid_payload", "request JSON must be an object")
    return dict(value)


def _strip_control_blocks(raw_query: str) -> tuple[str, list[str]]:
    query = raw_query
    removed: list[str] = []
    for name, pattern in _CONTROL_BLOCKS.items():
        updated, count = pattern.subn(" ", query)
        if count:
            removed.append(name)
            query = updated
    query = re.sub(r"[ \t]+", " ", query)
    query = re.sub(r"\n{3,}", "\n\n", query).strip()
    return query, removed


def _normalize_query(raw_query: Any, max_query_length: int) -> tuple[str, dict[str, Any]]:
    if not isinstance(raw_query, str):
        raise RequestEnvelopeError("missing_user_query", "user_query must be a string")
    raw = raw_query.strip()
    if not raw:
        raise RequestEnvelopeError("missing_user_query", "user_query is empty")
    if len(raw) > max_query_length:
        raise RequestEnvelopeError(
            "user_query_too_long",
            f"raw user_query exceeds {max_query_length} characters",
        )
    if _INTERNAL_PREFIX.search(raw) or _CONTROL_ROLE_PREFIX.search(raw):
        raise RequestEnvelopeError(
            "internal_context_rejected",
            "internal, subagent, cross-session, or tool traffic is not a user query",
        )
    query, removed = _strip_control_blocks(raw)
    if _CONTROL_TAG.search(query):
        raise RequestEnvelopeError(
            "malformed_control_context",
            "unclosed or malformed internal control context was rejected",
        )
    if not query or _INTERNAL_PREFIX.search(query) or _CONTROL_ROLE_PREFIX.search(query):
        raise RequestEnvelopeError(
            "internal_context_rejected",
            "no routable user query remains after input isolation",
        )
    return query, {
        "raw_length": len(raw),
        "normalized_length": len(query),
        "stripped_context_types": removed,
        "context_stripped": bool(removed),
    }


def _normalize_enum(value: Any, field: str, choices: Sequence[str], default: str) -> str:
    normalized = str(value or default).strip().lower()
    if normalized not in choices:
        raise RequestEnvelopeError(
            f"invalid_{field}",
            f"{field} must be one of {', '.join(choices)}",
        )
    return normalized


def _max_level(requested: str, inferred: str, levels: Sequence[str]) -> str:
    return levels[max(levels.index(requested), levels.index(inferred))]


def _infer_risk_level(query: str) -> str:
    if _CRITICAL_RISK_PATTERN.search(query):
        return "critical"
    if _HIGH_RISK_PATTERN.search(query):
        return "high"
    return "standard"


def _infer_timeliness(query: str) -> str:
    if _LATEST_PATTERN.search(query):
        return "latest"
    if _CURRENT_PATTERN.search(query):
        return "current"
    return "stable"


def _normalize_sources(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        requested = list(DEFAULT_ALLOWED_SOURCES)
    elif isinstance(value, str):
        requested = [part.strip().lower() for part in value.split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        requested = [str(part).strip().lower() for part in value if str(part).strip()]
    else:
        raise RequestEnvelopeError(
            "invalid_allowed_sources",
            "allowed_sources must be a list or comma-separated string",
        )
    if not requested:
        raise RequestEnvelopeError("invalid_allowed_sources", "allowed_sources cannot be empty")
    unknown = sorted(set(requested) - set(ALLOWED_SOURCES))
    if unknown:
        raise RequestEnvelopeError(
            "invalid_allowed_sources",
            f"unsupported allowed_sources: {', '.join(unknown)}",
        )
    requested_set = set(requested)
    return tuple(source for source in ALLOWED_SOURCES if source in requested_set)


def build_request_envelope(
    payload: Mapping[str, Any],
    *,
    transport: str,
    max_query_length: int = 2000,
) -> RequestEnvelope:
    data = dict(payload)
    accepted_fields = GET_FIELDS - {"q"} if transport == "legacy_get" else POST_FIELDS
    unknown = sorted(set(data) - accepted_fields)
    if unknown:
        raise RequestEnvelopeError(
            "forbidden_request_fields",
            f"request fields are not routable: {', '.join(unknown)}",
        )
    requested_embedding = data.get("embedding")
    if requested_embedding is not None and not isinstance(requested_embedding, str):
        raise RequestEnvelopeError(
            "invalid_embedding",
            "embedding must be a string when provided",
        )
    query, isolation = _normalize_query(data.get("user_query"), max_query_length)
    requested_risk = _normalize_enum(
        data.get("risk_level"), "risk_level", RISK_LEVELS, "standard"
    )
    requested_timeliness = _normalize_enum(
        data.get("timeliness"), "timeliness", TIMELINESS_LEVELS, "stable"
    )
    risk = _max_level(requested_risk, _infer_risk_level(query), RISK_LEVELS)
    timeliness = _max_level(
        requested_timeliness,
        _infer_timeliness(query),
        TIMELINESS_LEVELS,
    )
    allowed_sources = _normalize_sources(data.get("allowed_sources"))
    isolation["transport"] = transport
    normalized_embedding = (requested_embedding or "").strip().lower()
    isolation["requested_embedding"] = (
        "bge_m3"
        if normalized_embedding in {"bge_m3", "bge-m3"}
        else "unsupported"
        if normalized_embedding
        else ""
    )
    isolation["risk_escalated"] = risk != requested_risk
    isolation["timeliness_escalated"] = timeliness != requested_timeliness
    fingerprint_payload = {
        "schema_version": SCHEMA_VERSION,
        "user_query": query,
        "risk_level": risk,
        "timeliness": timeliness,
        "allowed_sources": list(allowed_sources),
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return RequestEnvelope(
        user_query=query,
        risk_level=risk,
        timeliness=timeliness,
        allowed_sources=allowed_sources,
        fingerprint=fingerprint,
        isolation=MappingProxyType(dict(isolation)),
    )


def parse_request_envelope(
    *,
    method: str,
    query_args: Mapping[str, Any] | None = None,
    json_body: Mapping[str, Any] | None = None,
    max_query_length: int = 2000,
) -> RequestEnvelope:
    normalized_method = str(method or "GET").upper()
    if normalized_method == "POST":
        data = _coerce_mapping(json_body)
        unknown = sorted(set(data) - POST_FIELDS)
        if unknown:
            raise RequestEnvelopeError(
                "forbidden_request_fields",
                f"request fields are not routable: {', '.join(unknown)}",
            )
        return build_request_envelope(
            data,
            transport="json_post",
            max_query_length=max_query_length,
        )
    if normalized_method != "GET":
        raise RequestEnvelopeError("unsupported_method", "only GET and POST are supported")
    args = _coerce_mapping(query_args)
    unknown = sorted(set(args) - GET_FIELDS)
    if unknown:
        raise RequestEnvelopeError(
            "forbidden_request_fields",
            f"request fields are not routable: {', '.join(unknown)}",
        )
    repeated = sorted(
        key
        for key, value in args.items()
        if isinstance(value, (list, tuple)) and len(value) != 1
    )
    if repeated:
        raise RequestEnvelopeError(
            "ambiguous_query_fields",
            f"repeated query fields are not allowed: {', '.join(repeated)}",
        )
    args = {
        key: value[0] if isinstance(value, (list, tuple)) else value
        for key, value in args.items()
    }
    if args.get("q") not in (None, "") and args.get("user_query") not in (None, ""):
        raise RequestEnvelopeError(
            "ambiguous_query_fields",
            "use either q or user_query, not both",
        )
    q_value = args.get("user_query")
    if q_value in (None, ""):
        q_value = args.get("q")
    payload = {
        "user_query": q_value,
        "risk_level": args.get("risk_level"),
        "timeliness": args.get("timeliness"),
        "allowed_sources": args.get("allowed_sources"),
        "embedding": args.get("embedding"),
    }
    return build_request_envelope(
        payload,
        transport="legacy_get",
        max_query_length=max_query_length,
    )
