#!/usr/bin/env python3
"""Provider-neutral external embedding contract with no built-in network path."""

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


EMBEDDING_REQUEST_SCHEMA_VERSION = "kg-embedding-request-v1"
EMBEDDING_RESPONSE_SCHEMA_VERSION = "kg-embedding-response-v1"
EMBEDDING_TRANSPORT_CONTROL_VERSION = (
    "spawn-kill-external-process-or-sealed-offline-fake-cooperative-v3"
)
LOCAL_METER_EXECUTION_CONTRACT = "trusted-local-terminating-v1"
_PURPOSES = frozenset({"build", "query", "entity"})
_NORMALIZATIONS = frozenset({"l2", "none"})
_TRANSPORT_MODES = frozenset({"cooperative", "external_process"})
_EXTERNAL_PROCESS_STOP_GRACE_SECONDS = 0.1
_DEFAULT_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


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


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _is_local_ollama_endpoint(provider: str, base_url: str) -> bool:
    parsed = urlsplit(base_url)
    return (
        provider == "ollama-local"
        and parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and parsed.path.rstrip("/") == "/api/embed"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


@dataclass(frozen=True)
class EmbeddingIdentity:
    provider: str
    base_url: str
    region: str
    model: str
    model_version: str
    api_version: str
    dimension: int
    normalization: str
    input_type: str

    def __post_init__(self) -> None:
        for field in (
            "provider",
            "base_url",
            "region",
            "model",
            "model_version",
            "api_version",
            "input_type",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        parsed = urlsplit(self.base_url)
        if (
            (parsed.scheme != "https"
            and not _is_local_ollama_endpoint(self.provider, self.base_url))
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an exact HTTPS endpoint without credentials, query, or fragment")
        if isinstance(self.dimension, bool) or not isinstance(self.dimension, int):
            raise ValueError("dimension must be a positive integer")
        if self.dimension <= 0:
            raise ValueError("dimension must be a positive integer")
        if self.normalization not in _NORMALIZATIONS:
            raise ValueError("normalization must be l2 or none")

    def manifest(self) -> dict[str, Any]:
        return {
            "api_version": self.api_version,
            "base_url": self.base_url,
            "dimension": self.dimension,
            "input_type": self.input_type,
            "model": self.model,
            "model_version": self.model_version,
            "normalization": self.normalization,
            "provider": self.provider,
            "region": self.region,
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.manifest())


@dataclass(frozen=True)
class EmbeddingPolicy:
    batch_size: int
    max_input_units: int
    timeout_seconds: float
    max_retries: int
    max_requests_per_operation: int
    max_cost_microunits_per_request: int
    total_cost_budget_microunits: int
    max_request_bytes: int = _DEFAULT_MAX_REQUEST_BYTES
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        for value, field, allow_zero in (
            (self.batch_size, "batch_size", False),
            (self.max_input_units, "max_input_units", False),
            (self.max_retries, "max_retries", True),
            (self.max_requests_per_operation, "max_requests_per_operation", False),
            (
                self.max_cost_microunits_per_request,
                "max_cost_microunits_per_request",
                True,
            ),
            (
                self.total_cost_budget_microunits,
                "total_cost_budget_microunits",
                True,
            ),
            (self.max_request_bytes, "max_request_bytes", False),
            (self.max_response_bytes, "max_response_bytes", False),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field} must be an integer")
            if value < 0 or (not allow_zero and value == 0):
                raise ValueError(f"{field} is outside the frozen limit")
        if isinstance(self.timeout_seconds, bool) or not isinstance(
            self.timeout_seconds, (int, float)
        ):
            raise ValueError("timeout_seconds must be positive and finite")
        if not math.isfinite(float(self.timeout_seconds)) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")

    def manifest(self) -> dict[str, Any]:
        return {
            "batch_size": self.batch_size,
            "max_cost_microunits_per_request": self.max_cost_microunits_per_request,
            "max_input_units": self.max_input_units,
            "max_request_bytes": self.max_request_bytes,
            "max_requests_per_operation": self.max_requests_per_operation,
            "max_response_bytes": self.max_response_bytes,
            "max_retries": self.max_retries,
            "local_meter_execution_contract": LOCAL_METER_EXECUTION_CONTRACT,
            "timeout_seconds": float(self.timeout_seconds),
            "total_cost_budget_microunits": self.total_cost_budget_microunits,
            "transport_control_version": EMBEDDING_TRANSPORT_CONTROL_VERSION,
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.manifest())


@dataclass(frozen=True)
class EmbeddingInput:
    object_id: str
    text: str
    input_units: int

    def normalized(self, max_input_units: int) -> dict[str, Any]:
        object_id = _text(self.object_id, "object_id")
        content = _text(self.text, "text")
        input_units = _non_negative_int(self.input_units, "input_units")
        if input_units == 0 or input_units > max_input_units:
            raise ValueError("input_units is outside the frozen embedding limit")
        return {"id": object_id, "text": content, "input_units": input_units}


@dataclass(frozen=True)
class EmbeddingVector:
    object_id: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingLedgerEntry:
    purpose: str
    batch_index: int
    attempt: int
    status: str
    request_sha256: str
    response_sha256: str | None
    latency_ms: int
    accounted_cost_microunits: int
    cost_basis: str


@dataclass(frozen=True)
class EmbeddingResult:
    purpose: str
    identity_sha256: str
    vectors: tuple[EmbeddingVector, ...]
    ledger: tuple[EmbeddingLedgerEntry, ...]

    def by_id(self) -> dict[str, tuple[float, ...]]:
        return {item.object_id: item.values for item in self.vectors}


class RetryableEmbeddingTransportError(RuntimeError):
    """Transport may use this controlled type for an approved retryable failure."""


class _EmbeddingTransportFailure(RuntimeError):
    pass


class _EmbeddingResponseTooLarge(RuntimeError):
    pass


class EmbeddingError(RuntimeError):
    """Sanitized operation failure; provider text and payloads are never retained."""

    def __init__(
        self,
        code: str,
        *,
        ledger: Sequence[EmbeddingLedgerEntry] = (),
        completed_ids: Sequence[str] = (),
    ) -> None:
        super().__init__("embedding operation failed")
        self.code = code
        self.ledger = tuple(ledger)
        self.completed_ids = tuple(completed_ids)


class TransportDeadline(float):
    """Float-compatible timeout carrying the mandatory cancellation signal."""

    def __new__(cls, seconds: float) -> TransportDeadline:
        instance = super().__new__(cls, seconds)
        instance.cancellation_event = threading.Event()
        return instance

    @property
    def cancelled(self) -> bool:
        return self.cancellation_event.is_set()

    def cancel(self) -> None:
        self.cancellation_event.set()


Transport = Callable[
    [EmbeddingIdentity, Mapping[str, Any], TransportDeadline], Mapping[str, Any]
]
InputUnitMeter = Callable[[str], int]


def _is_sealed_offline_fake_transport(transport: object) -> bool:
    """Recognize the exact repository fake type, never caller-supplied markers."""

    for module_name in (
        "deploy.cloud_v2.fake_providers",
        "cloud_v2.fake_providers",
    ):
        module = sys.modules.get(module_name)
        fake_type = getattr(module, "FakeEmbeddingTransport", None)
        if isinstance(fake_type, type) and type(transport) is fake_type:
            return True
    return False


def _external_transport_worker(
    connection: Any,
    transport: Transport,
    identity: EmbeddingIdentity,
    payload: Mapping[str, Any],
    timeout_seconds: float,
    max_response_bytes: int,
) -> None:
    try:
        deadline = TransportDeadline(timeout_seconds)
        try:
            response = transport(identity, payload, deadline)
        except TimeoutError:
            message = b"T"
        except RetryableEmbeddingTransportError:
            message = b"R"
        except BaseException:
            message = b"F"
        else:
            try:
                if not isinstance(response, Mapping):
                    raise TypeError("embedding transport must return an object")
                encoded = _canonical_json(response)
                if len(encoded) > max_response_bytes:
                    message = b"L"
                else:
                    message = b"O" + encoded
            except (TypeError, ValueError, OverflowError):
                message = b"I"
        connection.send_bytes(message)
    except BaseException:
        try:
            connection.send_bytes(b"F")
        except BaseException:
            pass
    finally:
        connection.close()


class EmbeddingAdapter:
    """Use one frozen identity for build, online query, and entity vectors."""

    def __init__(
        self,
        identity: EmbeddingIdentity,
        *,
        policy: EmbeddingPolicy,
        transport: Transport,
        transport_mode: str | None = None,
        input_unit_meter: InputUnitMeter | None = None,
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
        if transport_mode not in _TRANSPORT_MODES:
            raise ValueError("transport_mode must be cooperative or external_process")
        if transport_mode == "cooperative" and not _is_sealed_offline_fake_transport(
            transport
        ):
            raise ValueError("cooperative transport requires the sealed offline fake")
        if input_unit_meter is not None and not callable(input_unit_meter):
            raise TypeError("input_unit_meter must be callable")
        if transport_mode == "external_process" and input_unit_meter is None:
            raise ValueError("external_process transport requires a local input unit meter")
        self.identity = identity
        self.policy = policy
        self._transport = transport
        self.transport_mode = transport_mode
        self._input_unit_meter = input_unit_meter
        self._clock = clock

    def embed_build(self, items: Sequence[EmbeddingInput]) -> EmbeddingResult:
        return self.embed("build", items)

    def embed_query(self, item: EmbeddingInput) -> EmbeddingResult:
        return self.embed("query", (item,))

    def embed_entity(self, items: Sequence[EmbeddingInput]) -> EmbeddingResult:
        return self.embed("entity", items)

    def embed(
        self, purpose: str, items: Sequence[EmbeddingInput]
    ) -> EmbeddingResult:
        if purpose not in _PURPOSES:
            raise ValueError("unsupported embedding purpose")
        if not isinstance(items, Sequence) or isinstance(
            items, (str, bytes, bytearray)
        ):
            raise ValueError("items must be a sequence")
        normalized = [item.normalized(self.policy.max_input_units) for item in items]
        if not normalized:
            raise ValueError("at least one embedding input is required")
        ids = [item["id"] for item in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("embedding input ids must be unique")
        if purpose == "query" and len(normalized) != 1:
            raise ValueError("query embedding requires exactly one input")

        batches = [
            normalized[offset : offset + self.policy.batch_size]
            for offset in range(0, len(normalized), self.policy.batch_size)
        ]
        maximum_attempts = len(batches) * (self.policy.max_retries + 1)
        if maximum_attempts > self.policy.max_requests_per_operation:
            raise EmbeddingError("quota_exceeded")
        maximum_cost = (
            maximum_attempts * self.policy.max_cost_microunits_per_request
        )
        if maximum_cost > self.policy.total_cost_budget_microunits:
            raise EmbeddingError("budget_exceeded")

        ledger: list[EmbeddingLedgerEntry] = []
        vectors: list[EmbeddingVector] = []
        completed_ids: list[str] = []
        for batch_index, batch in enumerate(batches):
            try:
                batch_vectors = self._embed_batch(
                    purpose, batch_index, batch, ledger
                )
            except EmbeddingError as exc:
                code = "partial_failure" if completed_ids else exc.code
                raise EmbeddingError(
                    code,
                    ledger=ledger,
                    completed_ids=completed_ids,
                ) from exc
            vectors.extend(batch_vectors)
            completed_ids.extend(item.object_id for item in batch_vectors)

        if completed_ids != ids:
            raise EmbeddingError(
                "partial_failure", ledger=ledger, completed_ids=completed_ids
            )
        return EmbeddingResult(
            purpose=purpose,
            identity_sha256=self.identity.sha256,
            vectors=tuple(vectors),
            ledger=tuple(ledger),
        )

    def _embed_batch(
        self,
        purpose: str,
        batch_index: int,
        batch: Sequence[Mapping[str, Any]],
        ledger: list[EmbeddingLedgerEntry],
    ) -> list[EmbeddingVector]:
        preflight_started = self._clock()
        payload = {
            "schema_version": EMBEDDING_REQUEST_SCHEMA_VERSION,
            "embedding_identity_sha256": self.identity.sha256,
            "purpose": purpose,
            "input_type": self.identity.input_type,
            "items": list(batch),
        }
        request_bytes = _canonical_json(payload)
        if len(request_bytes) > self.policy.max_request_bytes:
            raise EmbeddingError("request_too_large")
        request_sha256 = hashlib.sha256(request_bytes).hexdigest()
        local_input_units = self._local_batch_input_units(batch)
        first_attempt_timeout = float(self.policy.timeout_seconds) - (
            self._clock() - preflight_started
        )
        if first_attempt_timeout <= 0:
            raise EmbeddingError("timeout")
        for attempt in range(1, self.policy.max_retries + 2):
            started = self._clock()
            attempt_timeout = (
                first_attempt_timeout
                if attempt == 1
                else float(self.policy.timeout_seconds)
            )
            response: Mapping[str, Any] | None = None
            try:
                response = self._call_transport(payload, attempt_timeout)
                latency_ms = self._latency_ms(started)
                if self._clock() - started > attempt_timeout:
                    raise TimeoutError("embedding deadline exceeded")
                parsed, response_cost = self._validate_response(
                    response,
                    batch,
                    local_input_units=local_input_units,
                )
            except (TimeoutError, RetryableEmbeddingTransportError) as exc:
                ledger.append(
                    EmbeddingLedgerEntry(
                        purpose=purpose,
                        batch_index=batch_index,
                        attempt=attempt,
                        status="timed_out"
                        if isinstance(exc, TimeoutError)
                        else "retryable_failure",
                        request_sha256=request_sha256,
                        response_sha256=self._safe_response_sha256(response),
                        latency_ms=self._latency_ms(started),
                        accounted_cost_microunits=self.policy.max_cost_microunits_per_request,
                        cost_basis="maximum_request_exposure",
                    )
                )
                if attempt <= self.policy.max_retries:
                    continue
                code = "timeout" if isinstance(exc, TimeoutError) else "transport_failure"
                raise EmbeddingError(code, ledger=ledger) from None
            except _EmbeddingTransportFailure:
                ledger.append(
                    EmbeddingLedgerEntry(
                        purpose=purpose,
                        batch_index=batch_index,
                        attempt=attempt,
                        status="failed",
                        request_sha256=request_sha256,
                        response_sha256=None,
                        latency_ms=self._latency_ms(started),
                        accounted_cost_microunits=self.policy.max_cost_microunits_per_request,
                        cost_basis="maximum_request_exposure",
                    )
                )
                raise EmbeddingError("transport_failure", ledger=ledger) from None
            except _EmbeddingResponseTooLarge:
                ledger.append(
                    EmbeddingLedgerEntry(
                        purpose=purpose,
                        batch_index=batch_index,
                        attempt=attempt,
                        status="failed",
                        request_sha256=request_sha256,
                        response_sha256=None,
                        latency_ms=self._latency_ms(started),
                        accounted_cost_microunits=self.policy.max_cost_microunits_per_request,
                        cost_basis="maximum_request_exposure",
                    )
                )
                raise EmbeddingError("response_too_large", ledger=ledger) from None
            except EmbeddingError as exc:
                ledger.append(
                    EmbeddingLedgerEntry(
                        purpose=purpose,
                        batch_index=batch_index,
                        attempt=attempt,
                        status="partial_failure"
                        if exc.code == "partial_failure"
                        else "failed",
                        request_sha256=request_sha256,
                        response_sha256=self._safe_response_sha256(response),
                        latency_ms=self._latency_ms(started),
                        accounted_cost_microunits=self.policy.max_cost_microunits_per_request,
                        cost_basis="maximum_request_exposure",
                    )
                )
                raise EmbeddingError(exc.code, ledger=ledger) from None
            except Exception:
                ledger.append(
                    EmbeddingLedgerEntry(
                        purpose=purpose,
                        batch_index=batch_index,
                        attempt=attempt,
                        status="failed",
                        request_sha256=request_sha256,
                        response_sha256=self._safe_response_sha256(response),
                        latency_ms=self._latency_ms(started),
                        accounted_cost_microunits=self.policy.max_cost_microunits_per_request,
                        cost_basis="maximum_request_exposure",
                    )
                )
                raise EmbeddingError("invalid_response", ledger=ledger) from None

            ledger.append(
                EmbeddingLedgerEntry(
                    purpose=purpose,
                    batch_index=batch_index,
                    attempt=attempt,
                    status="succeeded",
                    request_sha256=request_sha256,
                    response_sha256=_sha256(response),
                    latency_ms=latency_ms,
                    accounted_cost_microunits=response_cost,
                    cost_basis="reported_usage",
                )
            )
            if sum(item.accounted_cost_microunits for item in ledger) > (
                self.policy.total_cost_budget_microunits
            ):
                raise EmbeddingError("budget_exceeded", ledger=ledger)
            return parsed
        raise AssertionError("unreachable embedding attempt loop")

    def _validate_response(
        self,
        response: Any,
        batch: Sequence[Mapping[str, Any]],
        *,
        local_input_units: int,
    ) -> tuple[list[EmbeddingVector], int]:
        if not isinstance(response, Mapping) or set(response) != {
            "schema_version",
            "embedding_identity_sha256",
            "vectors",
            "failed_ids",
            "usage",
        }:
            raise ValueError("embedding response fields do not match the frozen schema")
        if response["schema_version"] != EMBEDDING_RESPONSE_SCHEMA_VERSION:
            raise ValueError("embedding response schema mismatch")
        if response["embedding_identity_sha256"] != self.identity.sha256:
            raise ValueError("embedding identity mismatch")
        expected_ids = [str(item["id"]) for item in batch]
        failed_ids = response["failed_ids"]
        if not isinstance(failed_ids, list) or any(
            not isinstance(item, str) for item in failed_ids
        ):
            raise ValueError("failed_ids must be a string list")
        if failed_ids:
            raise EmbeddingError("partial_failure")
        raw_vectors = response["vectors"]
        if not isinstance(raw_vectors, list):
            raise ValueError("vectors must be a list")
        parsed_by_id: dict[str, EmbeddingVector] = {}
        for item in raw_vectors:
            if not isinstance(item, Mapping) or set(item) != {"id", "values"}:
                raise ValueError("vector item fields do not match the frozen schema")
            object_id = _text(item["id"], "vector.id")
            if object_id not in expected_ids or object_id in parsed_by_id:
                raise ValueError("vector ids contain an unknown or duplicate id")
            parsed_by_id[object_id] = EmbeddingVector(
                object_id=object_id,
                values=self._normalize_vector(item["values"]),
            )
        if set(parsed_by_id) != set(expected_ids):
            raise EmbeddingError("partial_failure")

        usage = response["usage"]
        if not isinstance(usage, Mapping) or set(usage) != {
            "input_units",
            "cost_microunits",
        }:
            raise ValueError("usage fields do not match the frozen schema")
        reported_input = _non_negative_int(usage["input_units"], "input_units")
        declared_input = sum(int(item["input_units"]) for item in batch)
        if reported_input != declared_input or reported_input != local_input_units:
            raise ValueError("reported input usage differs from the submitted batch")
        cost = _non_negative_int(usage["cost_microunits"], "cost_microunits")
        if cost > self.policy.max_cost_microunits_per_request:
            raise ValueError("reported cost exceeds the frozen request budget")
        return [parsed_by_id[object_id] for object_id in expected_ids], cost

    def _local_batch_input_units(
        self,
        batch: Sequence[Mapping[str, Any]],
    ) -> int:
        declared_total = sum(int(item["input_units"]) for item in batch)
        if self._input_unit_meter is None:
            return declared_total
        measured_total = 0
        for item in batch:
            try:
                measured = self._input_unit_meter(str(item["text"]))
                measured = _non_negative_int(measured, "locally measured input_units")
            except Exception:
                raise EmbeddingError("input_meter_failure") from None
            if measured != int(item["input_units"]):
                raise EmbeddingError("usage_mismatch")
            measured_total += measured
        if measured_total != declared_total:
            raise EmbeddingError("usage_mismatch")
        return measured_total

    def _normalize_vector(self, values: Any) -> tuple[float, ...]:
        if not isinstance(values, Sequence) or isinstance(
            values, (str, bytes, bytearray)
        ):
            raise ValueError("embedding vector must be a numeric sequence")
        if len(values) != self.identity.dimension:
            raise ValueError("embedding dimension mismatch")
        parsed: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("embedding values must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("embedding values must be finite")
            parsed.append(number)
        if not parsed:
            raise ValueError("embedding vector cannot be empty")
        scale = max(abs(value) for value in parsed)
        if scale == 0:
            raise ValueError("embedding vector cannot have zero norm")
        if self.identity.normalization == "l2":
            scaled = [value / scale for value in parsed]
            scaled_norm = math.sqrt(sum(value * value for value in scaled))
            parsed = [value / scaled_norm for value in scaled]
        return tuple(parsed)

    def _call_transport(
        self,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        if self.transport_mode == "cooperative":
            return self._call_cooperative_transport(payload, timeout_seconds)
        return self._call_external_process_transport(payload, timeout_seconds)

    def _call_cooperative_transport(
        self,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        deadline = TransportDeadline(timeout_seconds)
        started = time.monotonic()
        try:
            value = self._transport(self.identity, payload, deadline)
        except TimeoutError:
            raise TimeoutError("embedding transport timed out") from None
        except RetryableEmbeddingTransportError:
            raise RetryableEmbeddingTransportError(
                "retryable embedding transport failure"
            ) from None
        except BaseException:
            raise _EmbeddingTransportFailure("embedding transport failed") from None
        if time.monotonic() - started > timeout_seconds:
            deadline.cancel()
            raise TimeoutError("embedding transport exceeded its wall deadline")
        if not isinstance(value, Mapping):
            raise TypeError("embedding transport must return an object")
        try:
            response_bytes = _canonical_json(value)
        except (TypeError, ValueError, OverflowError):
            raise TypeError("embedding transport returned an invalid object") from None
        if len(response_bytes) > self.policy.max_response_bytes:
            raise _EmbeddingResponseTooLarge("embedding response exceeded its byte limit")
        return value

    def _call_external_process_transport(
        self,
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        wall_deadline = time.monotonic() + timeout_seconds
        context = multiprocessing.get_context("spawn")
        receive_connection, send_connection = context.Pipe(duplex=False)
        process = context.Process(
            target=_external_transport_worker,
            args=(
                send_connection,
                self._transport,
                self.identity,
                dict(payload),
                timeout_seconds,
                self.policy.max_response_bytes,
            ),
            name="kg-embedding-external-transport",
            daemon=True,
        )
        started = False
        try:
            try:
                process.start()
                started = True
            except BaseException:
                raise _EmbeddingTransportFailure(
                    "embedding external transport could not start"
                ) from None
            finally:
                send_connection.close()

            remaining = wall_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("embedding external transport exceeded its wall deadline")
            try:
                ready = receive_connection.poll(remaining)
            except (OSError, EOFError):
                raise _EmbeddingTransportFailure(
                    "embedding external transport control failed"
                ) from None
            if not ready:
                raise TimeoutError("embedding external transport exceeded its wall deadline")
            try:
                message = receive_connection.recv_bytes(
                    maxlength=self.policy.max_response_bytes + 1
                )
            except (OSError, EOFError):
                raise _EmbeddingTransportFailure(
                    "embedding external transport returned no bounded result"
                ) from None

            process.join(_EXTERNAL_PROCESS_STOP_GRACE_SECONDS)
            if process.is_alive():
                raise _EmbeddingTransportFailure(
                    "embedding external transport did not terminate after its result"
                )
            if not message:
                raise _EmbeddingTransportFailure(
                    "embedding external transport returned an empty result"
                )
            status, encoded = message[:1], message[1:]
            if status == b"T":
                raise TimeoutError("embedding external transport timed out")
            if status == b"R":
                raise RetryableEmbeddingTransportError(
                    "retryable embedding transport failure"
                )
            if status == b"F":
                raise _EmbeddingTransportFailure("embedding external transport failed")
            if status == b"L":
                raise _EmbeddingResponseTooLarge(
                    "embedding response exceeded its byte limit"
                )
            if status == b"I":
                raise TypeError("embedding external transport returned an invalid object")
            if status != b"O" or not encoded:
                raise _EmbeddingTransportFailure(
                    "embedding external transport returned an invalid control result"
                )
            try:
                response = json.loads(encoded.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise TypeError("embedding external transport returned invalid JSON") from None
            if not isinstance(response, Mapping):
                raise TypeError("embedding external transport must return an object")
            return response
        finally:
            receive_connection.close()
            if started:
                self._stop_external_process(process)

    @staticmethod
    def _stop_external_process(process: Any) -> None:
        try:
            if process.is_alive():
                process.terminate()
                process.join(_EXTERNAL_PROCESS_STOP_GRACE_SECONDS)
            if process.is_alive():
                process.kill()
                process.join(_EXTERNAL_PROCESS_STOP_GRACE_SECONDS)
            if not process.is_alive():
                process.close()
        except (OSError, ValueError, AttributeError):
            pass

    @staticmethod
    def _safe_response_sha256(response: Any) -> str | None:
        try:
            return _sha256(response)
        except (TypeError, ValueError):
            return None

    def _latency_ms(self, started: float) -> int:
        return max(0, int((self._clock() - started) * 1000))
