#!/usr/bin/env python3
"""Loopback-only legacy GET adapter for the authenticated cloud-v2 WSGI app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import ipaddress
import json
import re
import sys
import time
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "deploy") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "deploy"))

from pipeline.public_identity_middleware import PublicIdentityVerifier


LEGACY_API_PATH = "/api/ask"
ANSWER_CONTRACT_VERSION = "ordinary-qa-compat-v1"
MAX_QUERY_STRING_BYTES = 16 * 1024
MAX_QUESTION_CHARACTERS = 8 * 1024
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_LEGACY_RESPONSE_FIELDS = frozenset(
    {
        "answer",
        "conflict_ids",
        "deduplicated_sources",
        "degraded",
        "degraded_reasons",
        "evidence",
        "evidence_bindings",
        "governance_degraded",
        "graph_first",
        "graph_paths",
        "intent",
        "query",
        "rag_query",
        "request_envelope",
        "retrieval_plan",
        "review_required",
        "rewritten",
        "route",
        "route_decision",
        "semantic_plan",
        "source_counts",
        "sources",
        "stats",
    }
)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _json_segment(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _base64url(payload)


def _gateway_token(verifier: PublicIdentityVerifier, now: int) -> str:
    header = _json_segment({"alg": "HS256", "typ": "JWT"})
    lifetime = min(60, verifier.config.max_lifetime_seconds)
    payload = _json_segment(
        {
            "amr": ["gateway-hs256"],
            "aud": verifier.config.audience,
            "exp": now + lifetime,
            "iat": now,
            "iss": verifier.config.issuer,
            "nbf": now,
            "roles": ["app-user"],
            "sub": "legacy-java-loopback",
        }
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = _base64url(
        hmac.new(verifier._secret, signing_input, hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{signature}"


def _json_response(
    start_response: Callable[..., Any],
    status: str,
    payload: Mapping[str, Any],
) -> list[bytes]:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def _loopback(remote_address: Any) -> bool:
    try:
        return ipaddress.ip_address(str(remote_address or "")).is_loopback
    except ValueError:
        return False


def _question(environ: Mapping[str, Any]) -> str:
    raw = environ.get("QUERY_STRING", "")
    if not isinstance(raw, str):
        raise ValueError("invalid_query")
    if len(raw.encode("utf-8")) > MAX_QUERY_STRING_BYTES:
        raise ValueError("query_too_large")
    if _INVALID_PERCENT_ESCAPE.search(raw):
        raise ValueError("invalid_query")
    try:
        pairs = parse_qsl(
            raw,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            separator="&",
        )
    except (UnicodeDecodeError, ValueError):
        raise ValueError("invalid_query") from None
    if len(pairs) != 1 or pairs[0][0] != "q":
        raise ValueError("invalid_query")
    question = pairs[0][1]
    if not question.strip() or len(question) > MAX_QUESTION_CHARACTERS:
        raise ValueError("invalid_query")
    return question


def _legacy_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "")
    route = str(payload.get("route") or "unavailable")
    degraded = bool(payload.get("degraded"))
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    graph_paths = (
        payload.get("graph_paths") if isinstance(payload.get("graph_paths"), list) else []
    )
    evidence_bindings = (
        payload.get("evidence_bindings")
        if isinstance(payload.get("evidence_bindings"), list)
        else []
    )
    stats = payload.get("stats") if isinstance(payload.get("stats"), Mapping) else {}
    request_envelope = (
        stats.get("request_envelope")
        if isinstance(stats.get("request_envelope"), Mapping)
        else {}
    )
    retrieval_counts = (
        stats.get("retrieval_counts")
        if isinstance(stats.get("retrieval_counts"), Mapping)
        else {}
    )
    projected = {
        "answer": str(payload.get("answer") or ""),
        "conflict_ids": [],
        "deduplicated_sources": list(sources),
        "degraded": degraded,
        "degraded_reasons": list(payload.get("degraded_reasons") or []),
        "evidence": list(evidence),
        "evidence_bindings": list(evidence_bindings),
        "governance_degraded": degraded,
        "graph_first": bool(graph_paths),
        "graph_paths": list(graph_paths),
        "intent": "knowledge_qa",
        "query": query,
        "rag_query": query,
        "request_envelope": dict(request_envelope),
        "retrieval_plan": dict(request_envelope),
        "review_required": degraded,
        "rewritten": query,
        "route": route,
        "route_decision": {"route": route},
        "semantic_plan": {},
        "source_counts": dict(retrieval_counts),
        "sources": list(sources),
        "stats": dict(stats),
    }
    if frozenset(projected) != _LEGACY_RESPONSE_FIELDS:
        raise RuntimeError("legacy_response_contract_invalid")
    return projected


class LegacyCompatWSGI:
    """Translate the historical loopback GET call into authenticated cloud-v2 WSGI."""

    def __init__(
        self,
        inner_application: Callable[..., Any],
        verifier: PublicIdentityVerifier,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if (
            not callable(inner_application)
            or not callable(getattr(verifier, "verify_environ", None))
            or not hasattr(verifier, "config")
            or not hasattr(verifier, "_secret")
        ):
            raise TypeError("legacy_compat_configuration_invalid")
        self._inner_application = inner_application
        self._verifier = verifier
        self._clock = clock

    def __call__(
        self,
        environ: MutableMapping[str, Any],
        start_response: Callable[..., Any],
    ) -> list[bytes]:
        if not isinstance(environ, MutableMapping):
            return _json_response(start_response, "403 Forbidden", {"error": "access_denied"})
        if not _loopback(environ.get("REMOTE_ADDR")):
            return _json_response(start_response, "403 Forbidden", {"error": "access_denied"})
        if environ.get("REQUEST_METHOD") != "GET" or environ.get("PATH_INFO") != LEGACY_API_PATH:
            return _json_response(start_response, "404 Not Found", {"error": "not_found"})
        try:
            question = _question(environ)
        except ValueError as error:
            return _json_response(
                start_response,
                "400 Bad Request",
                {"error": str(error), "request_rejected": True},
            )

        body = json.dumps(
            {"user_query": question},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        try:
            now = int(self._clock())
            token = _gateway_token(self._verifier, now)
        except Exception:
            return _json_response(
                start_response,
                "503 Service Unavailable",
                {"error": "knowledge_service_unavailable", "request_rejected": True},
            )

        inner_environ = dict(environ)
        inner_environ.update(
            {
                "REQUEST_METHOD": "POST",
                "QUERY_STRING": "",
                "CONTENT_TYPE": "application/json",
                "CONTENT_LENGTH": str(len(body)),
                "wsgi.input": io.BytesIO(body),
                "HTTP_AUTHORIZATION": f"Bearer {token}",
                "HTTP_X_KG_ANSWER_CONTRACT": ANSWER_CONTRACT_VERSION,
            }
        )
        captured: dict[str, Any] = {}

        def capture(status: str, headers: list[tuple[str, str]], exc_info=None):
            captured["status"] = status
            captured["headers"] = headers
            captured["exc_info"] = exc_info

        try:
            iterable = self._inner_application(inner_environ, capture)
            try:
                inner_body = b"".join(iterable)
            finally:
                close = getattr(iterable, "close", None)
                if callable(close):
                    close()
            status = str(captured.get("status") or "503 Service Unavailable")
            status_code = int(status.split(" ", 1)[0])
        except Exception:
            return _json_response(
                start_response,
                "503 Service Unavailable",
                {"error": "knowledge_service_unavailable", "request_rejected": True},
            )
        if status_code != 200:
            error = (
                "knowledge_service_rejected"
                if status_code in {400, 401, 403, 412, 413, 415}
                else "knowledge_service_unavailable"
            )
            return _json_response(
                start_response,
                status,
                {"error": error, "request_rejected": True},
            )
        try:
            decoded = json.loads(inner_body.decode("utf-8"))
            if not isinstance(decoded, Mapping):
                raise ValueError("invalid_inner_response")
            projected = _legacy_projection(decoded)
        except Exception:
            return _json_response(
                start_response,
                "502 Bad Gateway",
                {"error": "knowledge_service_unavailable", "request_rejected": True},
            )
        return _json_response(start_response, "200 OK", projected)


def create_legacy_compat_wsgi_app(
    inner_application: Callable[..., Any],
    verifier: PublicIdentityVerifier,
    *,
    clock: Callable[[], float] = time.time,
) -> LegacyCompatWSGI:
    return LegacyCompatWSGI(inner_application, verifier, clock=clock)


__all__ = [
    "LEGACY_API_PATH",
    "LegacyCompatWSGI",
    "create_legacy_compat_wsgi_app",
]
