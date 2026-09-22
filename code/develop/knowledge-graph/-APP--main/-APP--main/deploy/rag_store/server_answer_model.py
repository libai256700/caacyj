#!/usr/bin/env python3
"""Provider-neutral, transport-injected server answer model contract.

The adapter deliberately has no network implementation.  A deployment-specific
transport may only be supplied after its provider contract is approved; Phase 1
tests inject deterministic fakes.
"""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit


REQUEST_SCHEMA_VERSION = "kg-server-answer-request-v1"
RESPONSE_SCHEMA_VERSION = "kg-server-answer-response-v1"
TRANSPORT_CONTROL_VERSION = (
    "bounded-external-process-or-sealed-offline-fake-cooperative-v3"
)
LOCAL_METER_EXECUTION_CONTRACT = "trusted-local-terminating-v1"
DEFAULT_MAX_REQUEST_BYTES = 1_048_576
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576
_TRANSPORT_MODES = frozenset({"cooperative", "external_process"})
_PROCESS_JOIN_SECONDS = 0.05
_POLL_SECONDS = 0.01
_EVIDENCE_FIELDS = frozenset({"evidence_id", "text"})

_CHILD_OK = b"O"
_CHILD_TIMEOUT = b"T"
_CHILD_FAILURE = b"F"
_CHILD_INVALID_RESPONSE = b"I"
_CHILD_RESPONSE_TOO_LARGE = b"L"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: Any, field: str) -> int:
    parsed = _non_negative_int(value, field)
    if parsed == 0:
        raise ValueError(f"{field} must be greater than zero")
    return parsed


def _is_sealed_offline_fake_transport(transport: object) -> bool:
    """Recognize the exact repository fake type, never caller-supplied markers."""

    for module_name in (
        "deploy.cloud_v2.fake_providers",
        "cloud_v2.fake_providers",
    ):
        module = sys.modules.get(module_name)
        fake_type = getattr(module, "FakeServerAnswerTransport", None)
        if isinstance(fake_type, type) and type(transport) is fake_type:
            return True
    return False


@dataclass(frozen=True)
class ServerAnswerChannel:
    """Frozen identity, limits, and maximum financial exposure for one channel."""

    channel_id: str
    provider: str
    base_url: str
    region: str
    model: str
    api_version: str
    timeout_seconds: float
    max_input_units: int
    max_output_units: int
    max_cost_microunits: int
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    model_version: str = "offline-unspecified"

    def __post_init__(self) -> None:
        for field in (
            "channel_id",
            "provider",
            "base_url",
            "region",
            "model",
            "model_version",
            "api_version",
        ):
            object.__setattr__(
                self, field, _required_text(getattr(self, field), field)
            )
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an exact HTTPS endpoint without credentials, query, or fragment")
        if isinstance(self.timeout_seconds, bool) or not isinstance(
            self.timeout_seconds, (int, float)
        ):
            raise ValueError("timeout_seconds must be a positive finite number")
        if not math.isfinite(float(self.timeout_seconds)) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        _non_negative_int(self.max_input_units, "max_input_units")
        _non_negative_int(self.max_output_units, "max_output_units")
        _non_negative_int(self.max_cost_microunits, "max_cost_microunits")
        _positive_int(self.max_request_bytes, "max_request_bytes")
        _positive_int(self.max_response_bytes, "max_response_bytes")
        if self.max_input_units == 0 or self.max_output_units == 0:
            raise ValueError("input and output limits must be greater than zero")

    def identity(self) -> dict[str, Any]:
        return {
            "api_version": self.api_version,
            "base_url": self.base_url,
            "channel_id": self.channel_id,
            "model": self.model,
            "model_version": self.model_version,
            "max_cost_microunits": self.max_cost_microunits,
            "max_input_units": self.max_input_units,
            "max_output_units": self.max_output_units,
            "max_request_bytes": self.max_request_bytes,
            "max_response_bytes": self.max_response_bytes,
            "local_meter_execution_contract": LOCAL_METER_EXECUTION_CONTRACT,
            "provider": self.provider,
            "region": self.region,
            "timeout_seconds": float(self.timeout_seconds),
            "transport_control_version": TRANSPORT_CONTROL_VERSION,
        }

    @property
    def identity_sha256(self) -> str:
        return _sha256(self.identity())


@dataclass(frozen=True)
class ServerAnswerRequest:
    """Minimal disclosed input; token accounting is supplied by the caller."""

    request_id: str
    question: str
    evidence: Sequence[Mapping[str, str]]
    input_units: int

    def payload(self, channel: ServerAnswerChannel) -> dict[str, Any]:
        request_id = _required_text(self.request_id, "request_id")
        question = _required_text(self.question, "question")
        input_units = _non_negative_int(self.input_units, "input_units")
        if input_units == 0 or input_units > channel.max_input_units:
            raise ValueError("input_units is outside the frozen channel limit")
        if not isinstance(self.evidence, Sequence) or isinstance(
            self.evidence, (str, bytes, bytearray)
        ):
            raise ValueError("evidence must be a sequence")

        normalized_evidence: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in self.evidence:
            if not isinstance(item, Mapping):
                raise ValueError("each evidence item must be an object")
            unknown_fields = set(item) - _EVIDENCE_FIELDS
            if unknown_fields:
                raise ValueError("evidence contains fields outside the disclosure contract")
            evidence_id = _required_text(item.get("evidence_id"), "evidence_id")
            text = _required_text(item.get("text"), "evidence.text")
            if evidence_id in seen_ids:
                raise ValueError("duplicate evidence_id")
            seen_ids.add(evidence_id)
            normalized_evidence.append({"evidence_id": evidence_id, "text": text})

        if not normalized_evidence:
            raise ValueError("at least one selected evidence item is required")
        return {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "request_id": request_id,
            "question": question,
            "evidence": normalized_evidence,
            "input_units": input_units,
            "max_output_units": channel.max_output_units,
        }


@dataclass(frozen=True)
class ServerAnswerUsage:
    input_units: int
    output_units: int
    cost_microunits: int


@dataclass(frozen=True)
class ServerAnswerModelResult:
    answer: str
    channel_id: str
    usage: ServerAnswerUsage
    latency_ms: int
    request_sha256: str
    response_sha256: str


class ServerAnswerModelError(RuntimeError):
    """Sanitized channel failure safe to pass to orchestration telemetry."""

    def __init__(
        self,
        code: str,
        *,
        latency_ms: int,
        request_sha256: str | None,
        response_sha256: str | None = None,
        disclosed: bool = False,
    ) -> None:
        super().__init__("server answer channel failed")
        self.code = code
        self.latency_ms = max(0, int(latency_ms))
        self.request_sha256 = request_sha256
        self.response_sha256 = response_sha256
        self.disclosed = bool(disclosed)


class TransportDeadline(float):
    """Float-compatible timeout carrying the mandatory cancellation signal."""

    def __new__(
        cls,
        seconds: float,
        cancellation_event: Any | None = None,
    ) -> TransportDeadline:
        instance = super().__new__(cls, seconds)
        instance.cancellation_event = cancellation_event or threading.Event()
        return instance

    @property
    def cancelled(self) -> bool:
        return self.cancellation_event.is_set()

    def cancel(self) -> None:
        self.cancellation_event.set()


Transport = Callable[
    [ServerAnswerChannel, Mapping[str, Any], TransportDeadline], Mapping[str, Any]
]


def _external_transport_child(
    transport: Transport,
    channel: ServerAnswerChannel,
    payload_bytes: bytes,
    timeout_seconds: float,
    cancellation_event: Any,
    send_connection: Any,
    max_response_bytes: int,
) -> None:
    """Run untrusted transport in a killable child and return no exception text."""

    message = _CHILD_FAILURE
    try:
        payload = json.loads(payload_bytes)
    except BaseException:
        payload = None
    if isinstance(payload, Mapping):
        deadline = TransportDeadline(timeout_seconds, cancellation_event)
        try:
            response = transport(channel, payload, deadline)
        except TimeoutError:
            message = _CHILD_TIMEOUT
        except BaseException:
            message = _CHILD_FAILURE
        else:
            if not isinstance(response, Mapping):
                message = _CHILD_INVALID_RESPONSE
            else:
                try:
                    response_bytes = _canonical_json(response)
                except BaseException:
                    message = _CHILD_INVALID_RESPONSE
                else:
                    if len(response_bytes) > max_response_bytes:
                        message = _CHILD_RESPONSE_TOO_LARGE
                    else:
                        message = _CHILD_OK + response_bytes
    try:
        send_connection.send_bytes(message)
    except BaseException:
        pass
    try:
        send_connection.close()
    except BaseException:
        pass


class _TransportCancelled(RuntimeError):
    def __init__(self, *, disclosed: bool) -> None:
        super().__init__("server answer transport cancelled")
        self.disclosed = disclosed


class _TransportExecutionError(RuntimeError):
    def __init__(self, *, disclosed: bool) -> None:
        super().__init__("server answer transport execution failed")
        self.disclosed = disclosed


class _RequestContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__("server answer request rejected")
        self.code = code


class _ResponseContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__("server answer response rejected")
        self.code = code


class ServerAnswerModelAdapter:
    """Validate one approved channel around an injected provider transport."""

    def __init__(
        self,
        channel: ServerAnswerChannel,
        *,
        transport: Transport,
        transport_mode: str | None = None,
        input_unit_meter: Callable[[Mapping[str, Any]], int] | None = None,
        output_unit_meter: Callable[[str], int] | None = None,
        cost_meter: Callable[[ServerAnswerChannel, int, int], int] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not callable(transport):
            raise TypeError("transport must be injected and callable")
        if transport_mode is None:
            transport_mode = (
                "cooperative"
                if _is_sealed_offline_fake_transport(transport)
                else "external_process"
            )
        if (
            not isinstance(transport_mode, str)
            or transport_mode not in _TRANSPORT_MODES
        ):
            raise ValueError("unsupported server answer transport mode")
        if transport_mode == "cooperative" and not _is_sealed_offline_fake_transport(
            transport
        ):
            raise ValueError("cooperative transport requires the sealed offline fake")
        meters = (input_unit_meter, output_unit_meter, cost_meter)
        if transport_mode == "external_process" and any(
            meter is None for meter in meters
        ):
            raise ValueError("external_process requires local usage and cost meters")
        if any(meter is not None and not callable(meter) for meter in meters):
            raise TypeError("usage and cost meters must be callable")
        self.channel = channel
        self._transport = transport
        self.transport_mode = transport_mode
        self._input_unit_meter = input_unit_meter
        self._output_unit_meter = output_unit_meter
        self._cost_meter = cost_meter
        self._clock = clock

    def request_sha256(self, request: ServerAnswerRequest) -> str:
        return _sha256(request.payload(self.channel))

    def invoke(
        self,
        request: ServerAnswerRequest,
        *,
        timeout_seconds: float | None = None,
        cancellation_event: threading.Event | None = None,
    ) -> ServerAnswerModelResult:
        started = self._clock()
        payload: dict[str, Any] | None = None
        response: Mapping[str, Any] | None = None
        request_sha256: str | None = None
        expected_input_units: int | None = None
        try:
            if isinstance(timeout_seconds, bool):
                raise ValueError("timeout must be a positive finite number")
            effective_timeout = (
                float(self.channel.timeout_seconds)
                if timeout_seconds is None
                else min(float(timeout_seconds), float(self.channel.timeout_seconds))
            )
        except (TypeError, ValueError, OverflowError):
            effective_timeout = 0.0
        if not math.isfinite(effective_timeout) or effective_timeout <= 0:
            raise ServerAnswerModelError(
                "timeout",
                latency_ms=0,
                request_sha256=None,
            )

        try:
            payload = request.payload(self.channel)
            payload_bytes = _canonical_json(payload)
            request_sha256 = hashlib.sha256(payload_bytes).hexdigest()
            if len(payload_bytes) > self.channel.max_request_bytes:
                raise _RequestContractError("request_too_large")
            expected_input_units = self._measure_input_units(payload)
            if expected_input_units != payload["input_units"]:
                raise _RequestContractError("usage_mismatch")
            remaining_timeout = effective_timeout - (self._clock() - started)
            if remaining_timeout <= 0:
                raise _RequestContractError("timeout")
            response = self._call_transport(
                payload,
                payload_bytes,
                remaining_timeout,
                cancellation_event=cancellation_event,
            )
        except _RequestContractError as exc:
            raise ServerAnswerModelError(
                exc.code,
                latency_ms=self._latency_ms(started),
                request_sha256=request_sha256,
                disclosed=False,
            ) from None
        except _TransportCancelled as exc:
            raise ServerAnswerModelError(
                "cancelled",
                latency_ms=self._latency_ms(started),
                request_sha256=request_sha256,
                disclosed=exc.disclosed,
            ) from None
        except _TransportExecutionError as exc:
            raise ServerAnswerModelError(
                "transport_failure",
                latency_ms=self._latency_ms(started),
                request_sha256=request_sha256,
                disclosed=exc.disclosed,
            ) from None
        except _ResponseContractError as exc:
            raise ServerAnswerModelError(
                exc.code,
                latency_ms=self._latency_ms(started),
                request_sha256=request_sha256,
                disclosed=True,
            ) from None
        except TimeoutError:
            raise ServerAnswerModelError(
                "timeout",
                latency_ms=self._latency_ms(started),
                request_sha256=request_sha256,
                disclosed=True,
            ) from None
        except (TypeError, ValueError):
            code = "invalid_request" if payload is None else "invalid_response"
            raise ServerAnswerModelError(
                code,
                latency_ms=self._latency_ms(started),
                request_sha256=request_sha256,
                disclosed=payload is not None,
            ) from None
        except Exception:
            raise ServerAnswerModelError(
                "transport_failure",
                latency_ms=self._latency_ms(started),
                request_sha256=request_sha256,
                disclosed=True,
            ) from None

        latency_ms = self._latency_ms(started)
        if self._clock() - started > effective_timeout:
            raise ServerAnswerModelError(
                "timeout",
                latency_ms=latency_ms,
                request_sha256=request_sha256,
                response_sha256=self._safe_response_sha256(response),
                disclosed=True,
            )
        try:
            response_bytes = _canonical_json(response)
            if len(response_bytes) > self.channel.max_response_bytes:
                raise _ResponseContractError("response_too_large")
            result = self._validate_response(
                response,
                expected_input_units=expected_input_units,
            )
        except _ResponseContractError as exc:
            raise ServerAnswerModelError(
                exc.code,
                latency_ms=latency_ms,
                request_sha256=request_sha256,
                response_sha256=self._safe_response_sha256(response),
                disclosed=True,
            ) from None
        except (TypeError, ValueError, KeyError):
            raise ServerAnswerModelError(
                "invalid_response",
                latency_ms=latency_ms,
                request_sha256=request_sha256,
                response_sha256=self._safe_response_sha256(response),
                disclosed=True,
            ) from None
        latency_ms = self._latency_ms(started)
        if self._clock() - started > effective_timeout:
            raise ServerAnswerModelError(
                "timeout",
                latency_ms=latency_ms,
                request_sha256=request_sha256,
                response_sha256=hashlib.sha256(response_bytes).hexdigest(),
                disclosed=True,
            )
        return ServerAnswerModelResult(
            answer=result["answer"],
            channel_id=self.channel.channel_id,
            usage=result["usage"],
            latency_ms=latency_ms,
            request_sha256=request_sha256 or "",
            response_sha256=hashlib.sha256(response_bytes).hexdigest(),
        )

    def _validate_response(
        self,
        response: Any,
        *,
        expected_input_units: int | None,
    ) -> dict[str, Any]:
        if not isinstance(response, Mapping):
            raise TypeError("response must be an object")
        expected_fields = {
            "schema_version",
            "channel_identity_sha256",
            "answer",
            "usage",
        }
        if set(response) != expected_fields:
            raise ValueError("response fields do not match the frozen schema")
        if response["schema_version"] != RESPONSE_SCHEMA_VERSION:
            raise ValueError("response schema mismatch")
        if response["channel_identity_sha256"] != self.channel.identity_sha256:
            raise _ResponseContractError("identity_mismatch")
        if not isinstance(response["answer"], str) or not response["answer"].strip():
            raise _ResponseContractError("empty_response")
        raw_answer = response["answer"]
        answer = raw_answer.strip()
        usage = response["usage"]
        if not isinstance(usage, Mapping) or set(usage) != {
            "input_units",
            "output_units",
            "cost_microunits",
        }:
            raise ValueError("usage fields do not match the frozen schema")
        parsed_usage = ServerAnswerUsage(
            input_units=_non_negative_int(usage["input_units"], "input_units"),
            output_units=_non_negative_int(usage["output_units"], "output_units"),
            cost_microunits=_non_negative_int(
                usage["cost_microunits"], "cost_microunits"
            ),
        )
        if (
            expected_input_units is None
            or parsed_usage.input_units != expected_input_units
        ):
            raise _ResponseContractError("usage_mismatch")
        expected_output_units = self._measure_optional_units(
            self._output_unit_meter,
            raw_answer,
            "output_units",
        )
        if (
            expected_output_units is not None
            and parsed_usage.output_units != expected_output_units
        ):
            raise _ResponseContractError("usage_mismatch")
        expected_cost = self._measure_cost(
            parsed_usage.input_units,
            expected_output_units
            if expected_output_units is not None
            else parsed_usage.output_units,
        )
        if (
            expected_cost is not None
            and parsed_usage.cost_microunits != expected_cost
        ):
            raise _ResponseContractError("cost_mismatch")
        if parsed_usage.input_units > self.channel.max_input_units:
            raise ValueError("reported input usage exceeds the frozen limit")
        if parsed_usage.output_units > self.channel.max_output_units:
            raise ValueError("reported output usage exceeds the frozen limit")
        if parsed_usage.cost_microunits > self.channel.max_cost_microunits:
            raise ValueError("reported cost exceeds the frozen channel budget")
        return {"answer": answer, "usage": parsed_usage}

    def _call_transport(
        self,
        payload: Mapping[str, Any],
        payload_bytes: bytes,
        timeout_seconds: float,
        *,
        cancellation_event: threading.Event | None,
    ) -> Mapping[str, Any]:
        if self.transport_mode == "external_process":
            return self._call_external_process(
                payload_bytes,
                timeout_seconds,
                cancellation_event=cancellation_event,
            )
        deadline = TransportDeadline(timeout_seconds, cancellation_event)
        if deadline.cancelled:
            raise _TransportCancelled(disclosed=False)
        value = self._transport(self.channel, payload, deadline)
        if not isinstance(value, Mapping):
            raise TypeError("server answer transport must return an object")
        return value

    def _call_external_process(
        self,
        payload_bytes: bytes,
        timeout_seconds: float,
        *,
        cancellation_event: threading.Event | None,
    ) -> Mapping[str, Any]:
        if cancellation_event is not None and cancellation_event.is_set():
            raise _TransportCancelled(disclosed=False)
        context = multiprocessing.get_context("spawn")
        receive_connection, send_connection = context.Pipe(duplex=False)
        child_cancellation = context.Event()
        process = context.Process(
            target=_external_transport_child,
            args=(
                self._transport,
                self.channel,
                payload_bytes,
                timeout_seconds,
                child_cancellation,
                send_connection,
                self.channel.max_response_bytes,
            ),
            name=f"kg-answer-transport-{self.channel.channel_id}",
        )
        process_started = False
        force_reap = False
        wall_deadline = time.monotonic() + timeout_seconds
        try:
            try:
                process.start()
            except Exception:
                raise _TransportExecutionError(disclosed=False) from None
            process_started = True
            send_connection.close()

            while True:
                if cancellation_event is not None and cancellation_event.is_set():
                    force_reap = True
                    child_cancellation.set()
                    raise _TransportCancelled(disclosed=True)
                remaining = wall_deadline - time.monotonic()
                if remaining <= 0:
                    force_reap = True
                    child_cancellation.set()
                    raise TimeoutError("server answer transport exceeded its wall deadline")
                if receive_connection.poll(min(remaining, _POLL_SECONDS)):
                    try:
                        message = receive_connection.recv_bytes(
                            maxlength=self.channel.max_response_bytes + 1
                        )
                    except (EOFError, OSError):
                        raise _TransportExecutionError(disclosed=True) from None
                    return self._decode_child_message(message)
                if not process.is_alive():
                    if receive_connection.poll(0):
                        continue
                    raise _TransportExecutionError(disclosed=True)
        finally:
            try:
                send_connection.close()
            except OSError:
                pass
            if process_started:
                self._reap_process(
                    process,
                    child_cancellation,
                    force=force_reap,
                )
            receive_connection.close()

    @staticmethod
    def _decode_child_message(message: bytes) -> Mapping[str, Any]:
        if message == _CHILD_TIMEOUT:
            raise TimeoutError("server answer transport timed out")
        if message == _CHILD_RESPONSE_TOO_LARGE:
            raise _ResponseContractError("response_too_large")
        if message == _CHILD_INVALID_RESPONSE:
            raise TypeError("server answer transport returned an invalid response")
        if message == _CHILD_FAILURE or not message.startswith(_CHILD_OK):
            raise _TransportExecutionError(disclosed=True)
        try:
            response = json.loads(message[1:])
        except (TypeError, ValueError):
            raise TypeError("server answer transport returned invalid JSON") from None
        if not isinstance(response, Mapping):
            raise TypeError("server answer transport must return an object")
        return response

    @staticmethod
    def _reap_process(process: Any, cancellation_event: Any, *, force: bool) -> None:
        cancellation_event.set()
        if force and process.is_alive():
            process.terminate()
        process.join(timeout=_PROCESS_JOIN_SECONDS)
        if process.is_alive():
            process.terminate()
            process.join(timeout=_PROCESS_JOIN_SECONDS)
        if process.is_alive():
            process.kill()
            process.join(timeout=_PROCESS_JOIN_SECONDS)
        if not process.is_alive():
            process.close()

    def _measure_input_units(self, payload: Mapping[str, Any]) -> int:
        if self._input_unit_meter is None:
            return _non_negative_int(payload["input_units"], "input_units")
        try:
            measured = self._input_unit_meter(payload)
            return _positive_int(measured, "input_units")
        except Exception:
            raise _RequestContractError("invalid_request") from None

    @staticmethod
    def _measure_optional_units(
        meter: Callable[[str], int] | None,
        value: str,
        field: str,
    ) -> int | None:
        if meter is None:
            return None
        try:
            return _non_negative_int(meter(value), field)
        except Exception:
            raise ValueError("local usage meter rejected the response") from None

    def _measure_cost(self, input_units: int, output_units: int) -> int | None:
        if self._cost_meter is None:
            return None
        try:
            return _non_negative_int(
                self._cost_meter(self.channel, input_units, output_units),
                "cost_microunits",
            )
        except Exception:
            raise ValueError("local cost meter rejected the response") from None

    @staticmethod
    def _safe_response_sha256(response: Any) -> str | None:
        try:
            return _sha256(response)
        except (TypeError, ValueError):
            return None

    def _latency_ms(self, started: float) -> int:
        return max(0, int((self._clock() - started) * 1000))
