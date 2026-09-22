#!/usr/bin/env python3
"""Bounded serial answer-model policy for the portable cloud runtime."""

from __future__ import annotations

import json
import queue
import threading
import time
import urllib.request
from typing import Any, Callable, Mapping


TOTAL_BUDGET_S = 5.2
PRIMARY_TIMEOUT_S = 2.4
FALLBACK_TIMEOUT_S = 2.8
MIN_ATTEMPT_BUDGET_S = 0.05
DEFAULT_FALLBACK_MODEL = "doubao-seed-2-0-mini-260428"
PRIMARY_MODEL = "deepseek-v4-flash"
POLICY_VERSION = "cloud-deepseek-2.4s-doubao-mini-5.2s-v1"
TELEMETRY_SCHEMA_VERSION = "kg-answer-model-telemetry-v1"
_RECOVERED_FALLBACK_STATUSES = frozenset({
    "model_fallback_succeeded",
    "extractive_fallback_succeeded",
})


Transport = Callable[[str, dict[str, Any], dict[str, str], float], Mapping[str, Any]]


class AnswerModelUnavailable(RuntimeError):
    """No configured answer channel succeeded inside the request budget."""

    def __init__(self, message: str, *, attempts: list[dict[str, Any]], latency_ms: int):
        super().__init__(message)
        self.attempts = attempts
        self.latency_ms = latency_ms
        self.policy_version = POLICY_VERSION


def recovery_status_after_finalizer(recovery_status: str, finalizer_outcome: str) -> str:
    """A generated fallback is recovered only when the finalizer accepts it."""
    if finalizer_outcome == "blocked" and recovery_status in _RECOVERED_FALLBACK_STATUSES:
        return "unrecovered"
    return recovery_status


def _attempt_status(attempts: list[dict[str, Any]], model: str) -> tuple[bool, str]:
    attempt = next(
        (item for item in attempts if str(item.get("model") or "") == model),
        None,
    )
    if attempt is None:
        return False, "not_attempted"
    if str(attempt.get("status") or "") == "succeeded":
        return True, "succeeded"
    error_type = str(attempt.get("error_type") or "").lower()
    return True, "timed_out" if "timeout" in error_type else "failed"


def build_answer_model_telemetry(
    *,
    attempts: list[dict[str, Any]],
    selected_model: str | None,
    latency_ms: int,
    recovery_status: str,
    extractive_fallback_used: bool,
    extractive_fallback_recovered: bool,
    extractive_policy_version: str,
    answer_method: str,
    answer_status: str,
) -> dict[str, Any]:
    """Build the response/trace contract for the complete recovery chain."""

    normalized_attempts = [dict(item) for item in attempts]
    primary_attempted, primary_status = _attempt_status(
        normalized_attempts, PRIMARY_MODEL
    )
    fallback_attempted, fallback_status = _attempt_status(
        normalized_attempts, DEFAULT_FALLBACK_MODEL
    )
    fallback_recovered_answer = (
        recovery_status
        in {"model_fallback_succeeded", "extractive_fallback_succeeded"}
        and answer_status == "recovered"
    )
    return {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "selected_model": selected_model,
        "attempts": normalized_attempts,
        "latency_ms": max(0, int(latency_ms)),
        "primary_status": primary_status,
        "primary_failed": primary_attempted and primary_status != "succeeded",
        "primary_timed_out": primary_status == "timed_out",
        "model_fallback_status": fallback_status,
        "model_fallback_attempted": fallback_attempted,
        "model_fallback_succeeded": fallback_status == "succeeded",
        "extractive_fallback_policy_version": extractive_policy_version,
        "extractive_fallback_used": bool(extractive_fallback_used),
        "extractive_fallback_recovered": bool(extractive_fallback_recovered),
        "fallback_recovered_answer": fallback_recovered_answer,
        "unrecovered_model_failure": recovery_status in {
            "unrecovered",
            "pipeline_error",
        },
        "answer_method": answer_method,
        "answer_status": answer_status,
        "recovery_status": recovery_status,
    }


def _endpoint(base_url: Any, default: str) -> str:
    base = str(base_url or default).rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def _default_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
) -> Mapping[str, Any]:
    """Bound both connection and response-body reads by one wall deadline."""
    outcome: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
    response_holder: dict[str, object] = {}

    def request_worker() -> None:
        response = None
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
            )
            response = urllib.request.urlopen(request, timeout=timeout_s)
            response_holder["response"] = response
            outcome.put(("ok", response.read()))
        except Exception as exc:  # transport errors are reported by the policy
            outcome.put(("error", exc))
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    worker = threading.Thread(target=request_worker, name="kg-answer-provider", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        close = getattr(response_holder.get("response"), "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        raise TimeoutError("answer provider wall deadline exceeded")

    try:
        status, value = outcome.get_nowait()
    except queue.Empty as exc:
        raise RuntimeError("answer provider exited without a result") from exc
    if status == "error":
        if isinstance(value, BaseException):
            raise value
        raise RuntimeError("answer provider returned an invalid error")
    if not isinstance(value, bytes):
        raise TypeError("answer provider response must be bytes")
    parsed = json.loads(value)
    if not isinstance(parsed, Mapping):
        raise TypeError("answer provider response must be a JSON object")
    return parsed


def _channels(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    models = config.get("models") if isinstance(config, Mapping) else {}
    models = models if isinstance(models, Mapping) else {}
    primary = models.get("flash") if isinstance(models.get("flash"), Mapping) else {}
    mini = models.get("doubao_mini") if isinstance(models.get("doubao_mini"), Mapping) else {}
    configured_primary = str(primary.get("name") or PRIMARY_MODEL)
    if configured_primary != PRIMARY_MODEL:
        raise ValueError(f"unsupported primary answer model: {configured_primary}")
    configured_fallback = str(mini.get("name") or DEFAULT_FALLBACK_MODEL) if mini else ""
    if configured_fallback and configured_fallback != DEFAULT_FALLBACK_MODEL:
        raise ValueError(f"unsupported fallback answer model: {configured_fallback}")

    channels = [{
        "model": PRIMARY_MODEL,
        "url": _endpoint(primary.get("base_url"), "https://api.deepseek.com"),
        "api_key": str(primary.get("api_key") or ""),
        "timeout_s": PRIMARY_TIMEOUT_S,
    }]
    if mini:
        channels.append({
            "model": DEFAULT_FALLBACK_MODEL,
            "url": _endpoint(mini.get("base_url"), "https://ark.cn-beijing.volces.com/api/v3"),
            "api_key": str(mini.get("api_key") or ""),
            "timeout_s": FALLBACK_TIMEOUT_S,
        })

    unique = []
    seen_models = set()
    for channel in channels:
        if channel["model"] in seen_models:
            continue
        seen_models.add(channel["model"])
        unique.append(channel)
    return unique


def run_answer_model(
    payload: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    transport: Transport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Try the primary once, then Doubao Mini once, inside 5.2 seconds total."""
    transport = transport or _default_transport
    started = clock()
    attempts: list[dict[str, Any]] = []
    last_error: BaseException | None = None

    for channel in _channels(config):
        remaining = TOTAL_BUDGET_S - (clock() - started)
        if remaining < MIN_ATTEMPT_BUDGET_S:
            last_error = TimeoutError("answer model budget exhausted")
            break
        timeout_s = min(float(channel["timeout_s"]), remaining)
        attempt_started = clock()
        status = "failed"
        error_type = None
        content = ""
        try:
            if not channel["api_key"]:
                raise RuntimeError("answer model credential unavailable")
            attempt_payload = dict(payload)
            attempt_payload["model"] = channel["model"]
            attempt_payload["thinking"] = {"type": "disabled"}
            response = transport(
                channel["url"],
                attempt_payload,
                {
                    "Authorization": f"Bearer {channel['api_key']}",
                    "Content-Type": "application/json",
                },
                timeout_s,
            )
            content = str(response["choices"][0]["message"]["content"] or "").strip()
            if not content:
                raise RuntimeError("empty answer content")
            status = "succeeded"
        except Exception as exc:
            last_error = exc
            error_type = type(exc).__name__
        attempt = {
            "model": channel["model"],
            "status": status,
            "error_type": error_type,
            "timeout_ms": int(timeout_s * 1000),
            "latency_ms": max(0, int((clock() - attempt_started) * 1000)),
        }
        attempts.append(attempt)
        if status == "succeeded":
            return {
                "answer": content,
                "model": channel["model"],
                "attempts": attempts,
                "latency_ms": max(0, int((clock() - started) * 1000)),
                "policy_version": POLICY_VERSION,
            }

    latency_ms = max(0, int((clock() - started) * 1000))
    detail = type(last_error).__name__ if last_error is not None else "no_channel"
    raise AnswerModelUnavailable(
        f"all answer channels failed: {detail}",
        attempts=attempts,
        latency_ms=latency_ms,
    )
