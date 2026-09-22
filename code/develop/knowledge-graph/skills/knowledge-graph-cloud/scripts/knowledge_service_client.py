#!/usr/bin/env python3
"""Read-only HTTPS client for optional App knowledge references.

The public App owns final-answer generation. This module deliberately exposes
only a usable natural-language answer or ``None``; backend response metadata is
never returned to the App prompt layer.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit


ANSWER_CONTRACT = "ordinary-qa-compat-v1"
ANSWER_CONTRACT_HEADER = "X-KG-Answer-Contract"
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576

_RESERVED_HEADERS = frozenset(
    {
        "accept",
        "content-type",
        ANSWER_CONTRACT_HEADER.lower(),
    }
)
_UNUSABLE_ROUTES = frozenset(
    {"error", "governance_error", "miss", "no_match", "unavailable"}
)
_UNUSABLE_ANSWER_MARKERS = (
    "知识库中没有",
    "不在本服务覆盖范围",
    "请求已拒绝",
    "服务不可用",
    "查询失败",
    "无法回答",
)


@dataclass(frozen=True)
class TransportRequest:
    """Complete, bounded HTTP request passed to an injected transport."""

    url: str
    method: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)
    timeout_s: float
    max_response_bytes: int


@dataclass(frozen=True)
class TransportResponse:
    """Minimal HTTP response accepted from a transport implementation."""

    status: int
    body: bytes = field(repr=False)


Transport = Callable[[TransportRequest], TransportResponse]


def _validated_endpoint(endpoint: str) -> str:
    if not isinstance(endpoint, str):
        raise TypeError("knowledge service endpoint must be a string")
    value = endpoint.strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https":
        raise ValueError("knowledge service endpoint must use https")
    if not parsed.hostname:
        raise ValueError("knowledge service endpoint must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("knowledge service endpoint must not contain credentials")
    if "?" in value or "#" in value:
        raise ValueError("knowledge service endpoint must not contain query or fragment")
    if parsed.path != "/api/ask":
        raise ValueError("knowledge service endpoint path must be /api/ask")
    return value


def _validated_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    normalized = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        ANSWER_CONTRACT_HEADER: ANSWER_CONTRACT,
    }
    if headers is None:
        return normalized
    if not isinstance(headers, Mapping):
        raise TypeError("headers must be a mapping")

    for raw_name, raw_value in headers.items():
        if not isinstance(raw_name, str) or not isinstance(raw_value, str):
            raise TypeError("header names and values must be strings")
        name = raw_name.strip()
        value = raw_value.strip()
        if not name or not value:
            raise ValueError("header names and values must not be empty")
        if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            raise ValueError("header names and values must not contain newlines")
        if name.lower() in _RESERVED_HEADERS:
            raise ValueError(f"reserved header cannot be overridden: {name}")
        normalized[name] = value
    return normalized


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_transport(request: TransportRequest) -> TransportResponse:
    http_request = urllib.request.Request(
        request.url,
        data=request.body,
        headers=dict(request.headers),
        method=request.method,
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(http_request, timeout=request.timeout_s) as response:
            status = int(response.status)
            body = response.read(request.max_response_bytes + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read(request.max_response_bytes + 1)
    return TransportResponse(status=status, body=body)


def _optional_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strict_json_object(raw: bytes) -> Mapping[str, Any] | None:
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _usable_answer(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    if payload.get("degraded") is not False:
        return None
    if (
        "request_rejected" in payload
        and payload.get("request_rejected") is not False
    ):
        return None
    for field in ("error", "error_type"):
        if field in payload:
            value = payload.get(field)
            if value is not None and value is not False and value != "":
                return None
    route = payload.get("route")
    if route is not None and not isinstance(route, str):
        return None
    if _optional_text(route).lower() in _UNUSABLE_ROUTES:
        return None
    for field in ("hit", "matched", "knowledge_available"):
        if field in payload and payload.get(field) is not True:
            return None

    answer = _optional_text(payload.get("answer"))
    if not answer or any(marker in answer for marker in _UNUSABLE_ANSWER_MARKERS):
        return None
    return answer


class KnowledgeServiceClient:
    """Fetch optional professional reference text without exposing raw payloads."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_s: float,
        headers: Mapping[str, str] | None = None,
        transport: Transport | None = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._endpoint = _validated_endpoint(endpoint)
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise TypeError("timeout_s must be a positive number")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int):
            raise TypeError("max_response_bytes must be a positive integer")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if transport is not None and not callable(transport):
            raise TypeError("transport must be callable")

        self._timeout_s = float(timeout_s)
        self._headers = _validated_headers(headers)
        self._transport = transport or _urllib_transport
        self._max_response_bytes = max_response_bytes

    def ask(self, user_query: str) -> str | None:
        """Return a usable knowledge answer, or ``None`` for every miss/failure."""
        if not isinstance(user_query, str):
            raise TypeError("user_query must be a string")
        question = user_query.strip()
        if not question:
            raise ValueError("user_query must not be empty")

        body = json.dumps(
            {"user_query": question},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = TransportRequest(
            url=self._endpoint,
            method="POST",
            headers=dict(self._headers),
            body=body,
            timeout_s=self._timeout_s,
            max_response_bytes=self._max_response_bytes,
        )
        try:
            response = self._transport(request)
        except (TimeoutError, urllib.error.URLError, OSError):
            return None

        if not isinstance(response, TransportResponse):
            raise TypeError("transport must return TransportResponse")
        if isinstance(response.status, bool) or not isinstance(response.status, int):
            raise TypeError("transport response status must be an integer")
        if not isinstance(response.body, bytes):
            raise TypeError("transport response body must be bytes")
        if not 200 <= response.status < 300:
            return None
        if not response.body or len(response.body) > self._max_response_bytes:
            return None

        payload = _strict_json_object(response.body)
        return _usable_answer(payload)


__all__ = [
    "ANSWER_CONTRACT",
    "ANSWER_CONTRACT_HEADER",
    "KnowledgeServiceClient",
    "Transport",
    "TransportRequest",
    "TransportResponse",
]
