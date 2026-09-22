#!/usr/bin/env python3
"""Provider-neutral, query-only embedding client for the cloud runtime."""

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
        raise ValueError(f"{field} must be non-empty text")
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
class QueryEmbeddingIdentity:
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
            raise ValueError("base_url must be an exact credential-free HTTPS endpoint")
        if (
            isinstance(self.dimension, bool)
            or not isinstance(self.dimension, int)
            or self.dimension <= 0
        ):
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
class QueryEmbeddingPolicy:
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
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(float(self.timeout_seconds))
            or self.timeout_seconds <= 0
        ):
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
class QueryEmbeddingInput:
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
class QueryEmbeddingLedgerEntry:
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
class QueryEmbeddingResult:
    purpose: str
    identity_sha256: str
    object_id: str
    vector: tuple[float, ...]
    ledger: tuple[QueryEmbeddingLedgerEntry, ...]


class RetryableQueryEmbeddingTransportError(RuntimeError):
    """The approved transport reported a retryable failure."""


class QueryEmbeddingError(RuntimeError):
    """Sanitized failure without provider text or payload content."""

    def __init__(
        self,
        code: str,
        *,
        ledger: Sequence[QueryEmbeddingLedgerEntry] = (),
    ) -> None:
        super().__init__("query embedding operation failed")
        self.code = code
        self.ledger = tuple(ledger)


class _TransportFailure(RuntimeError):
    pass


class _ResponseTooLarge(RuntimeError):
    pass


class QueryTransportDeadline(float):
    def __new__(cls, seconds: float) -> "QueryTransportDeadline":
        instance = super().__new__(cls, seconds)
        instance.cancellation_event = threading.Event()
        return instance

    def cancel(self) -> None:
        self.cancellation_event.set()


Transport = Callable[
    [QueryEmbeddingIdentity, Mapping[str, Any], QueryTransportDeadline],
    Mapping[str, Any],
]
InputUnitMeter = Callable[[str], int]


def _is_sealed_offline_fake_transport(transport: object) -> bool:
    for module_name in ("deploy.cloud_v2.fake_providers", "cloud_v2.fake_providers"):
        module = sys.modules.get(module_name)
        fake_type = getattr(module, "FakeEmbeddingTransport", None)
        if isinstance(fake_type, type) and type(transport) is fake_type:
            return True
    return False


def _external_transport_worker(
    connection: Any,
    transport: Transport,
    identity: QueryEmbeddingIdentity,
    payload: Mapping[str, Any],
    timeout_seconds: float,
    max_response_bytes: int,
) -> None:
    try:
        try:
            response = transport(
                identity,
                payload,
                QueryTransportDeadline(timeout_seconds),
            )
        except TimeoutError:
            message = b"T"
        except RetryableQueryEmbeddingTransportError:
            message = b"R"
        except BaseException:
            message = b"F"
        else:
            try:
                if not isinstance(response, Mapping):
                    raise TypeError("transport response must be an object")
                encoded = _canonical_json(response)
                message = b"L" if len(encoded) > max_response_bytes else b"O" + encoded
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


class QueryEmbeddingClient:
    """Embed exactly one online query using a frozen identity and policy."""

    def __init__(
        self,
        identity: QueryEmbeddingIdentity,
        *,
        policy: QueryEmbeddingPolicy,
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

    def embed_query(self, item: QueryEmbeddingInput) -> QueryEmbeddingResult:
        if not isinstance(item, QueryEmbeddingInput):
            raise TypeError("embed_query requires one QueryEmbeddingInput")
        normalized = item.normalized(self.policy.max_input_units)
        maximum_attempts = self.policy.max_retries + 1
        if maximum_attempts > self.policy.max_requests_per_operation:
            raise QueryEmbeddingError("quota_exceeded")
        if (
            maximum_attempts * self.policy.max_cost_microunits_per_request
            > self.policy.total_cost_budget_microunits
        ):
            raise QueryEmbeddingError("budget_exceeded")
        payload = {
            "schema_version": EMBEDDING_REQUEST_SCHEMA_VERSION,
            "embedding_identity_sha256": self.identity.sha256,
            "purpose": "query",
            "input_type": self.identity.input_type,
            "items": [normalized],
        }
        request_bytes = _canonical_json(payload)
        if len(request_bytes) > self.policy.max_request_bytes:
            raise QueryEmbeddingError("request_too_large")
        request_sha256 = hashlib.sha256(request_bytes).hexdigest()
        local_units = self._local_input_units(normalized)
        ledger: list[QueryEmbeddingLedgerEntry] = []
        for attempt in range(1, maximum_attempts + 1):
            started = self._clock()
            response: Mapping[str, Any] | None = None
            try:
                response = self._call_transport(payload, float(self.policy.timeout_seconds))
                if self._clock() - started > float(self.policy.timeout_seconds):
                    raise TimeoutError("query embedding deadline exceeded")
                vector, response_cost = self._validate_response(
                    response,
                    normalized,
                    local_input_units=local_units,
                )
            except (TimeoutError, RetryableQueryEmbeddingTransportError) as exc:
                ledger.append(
                    self._ledger_entry(
                        attempt,
                        "timed_out" if isinstance(exc, TimeoutError) else "retryable_failure",
                        request_sha256,
                        self._safe_response_sha256(response),
                        started,
                        self.policy.max_cost_microunits_per_request,
                        "maximum_request_exposure",
                    )
                )
                if attempt < maximum_attempts:
                    continue
                code = "timeout" if isinstance(exc, TimeoutError) else "transport_failure"
                raise QueryEmbeddingError(code, ledger=ledger) from None
            except _TransportFailure:
                ledger.append(
                    self._ledger_entry(
                        attempt,
                        "failed",
                        request_sha256,
                        None,
                        started,
                        self.policy.max_cost_microunits_per_request,
                        "maximum_request_exposure",
                    )
                )
                raise QueryEmbeddingError("transport_failure", ledger=ledger) from None
            except _ResponseTooLarge:
                ledger.append(
                    self._ledger_entry(
                        attempt,
                        "failed",
                        request_sha256,
                        None,
                        started,
                        self.policy.max_cost_microunits_per_request,
                        "maximum_request_exposure",
                    )
                )
                raise QueryEmbeddingError("response_too_large", ledger=ledger) from None
            except Exception:
                ledger.append(
                    self._ledger_entry(
                        attempt,
                        "failed",
                        request_sha256,
                        self._safe_response_sha256(response),
                        started,
                        self.policy.max_cost_microunits_per_request,
                        "maximum_request_exposure",
                    )
                )
                raise QueryEmbeddingError("invalid_response", ledger=ledger) from None
            ledger.append(
                self._ledger_entry(
                    attempt,
                    "succeeded",
                    request_sha256,
                    _sha256(response),
                    started,
                    response_cost,
                    "reported_usage",
                )
            )
            if sum(entry.accounted_cost_microunits for entry in ledger) > (
                self.policy.total_cost_budget_microunits
            ):
                raise QueryEmbeddingError("budget_exceeded", ledger=ledger)
            return QueryEmbeddingResult(
                purpose="query",
                identity_sha256=self.identity.sha256,
                object_id=str(normalized["id"]),
                vector=vector,
                ledger=tuple(ledger),
            )
        raise AssertionError("unreachable query embedding attempt loop")

    def measure_input_units(self, text: str) -> int:
        """Measure one query with the locally approved provider unit contract."""

        content = _text(text, "query embedding text")
        try:
            measured = _non_negative_int(
                (
                    len(content)
                    if self._input_unit_meter is None
                    else self._input_unit_meter(content)
                ),
                "locally measured input_units",
            )
        except Exception:
            raise QueryEmbeddingError("input_meter_failure") from None
        if measured == 0 or measured > self.policy.max_input_units:
            raise QueryEmbeddingError("input_limit_exceeded")
        return measured

    def _validate_response(
        self,
        response: Any,
        item: Mapping[str, Any],
        *,
        local_input_units: int,
    ) -> tuple[tuple[float, ...], int]:
        if not isinstance(response, Mapping) or set(response) != {
            "schema_version",
            "embedding_identity_sha256",
            "vectors",
            "failed_ids",
            "usage",
        }:
            raise ValueError("query embedding response shape mismatch")
        if (
            response["schema_version"] != EMBEDDING_RESPONSE_SCHEMA_VERSION
            or response["embedding_identity_sha256"] != self.identity.sha256
        ):
            raise ValueError("query embedding response identity mismatch")
        if response["failed_ids"] != []:
            raise ValueError("query embedding response contains a failed id")
        vectors = response["vectors"]
        if not isinstance(vectors, list) or len(vectors) != 1:
            raise ValueError("query embedding response must contain exactly one vector")
        vector = vectors[0]
        if (
            not isinstance(vector, Mapping)
            or set(vector) != {"id", "values"}
            or vector["id"] != item["id"]
        ):
            raise ValueError("query embedding vector identity mismatch")
        usage = response["usage"]
        if not isinstance(usage, Mapping) or set(usage) != {
            "input_units",
            "cost_microunits",
        }:
            raise ValueError("query embedding usage shape mismatch")
        reported_units = _non_negative_int(usage["input_units"], "input_units")
        if reported_units != int(item["input_units"]) or reported_units != local_input_units:
            raise ValueError("query embedding usage mismatch")
        cost = _non_negative_int(usage["cost_microunits"], "cost_microunits")
        if cost > self.policy.max_cost_microunits_per_request:
            raise ValueError("query embedding cost exceeds the frozen limit")
        return self._normalize_vector(vector["values"]), cost

    def _local_input_units(self, item: Mapping[str, Any]) -> int:
        declared = int(item["input_units"])
        measured = self.measure_input_units(str(item["text"]))
        if measured != declared:
            raise QueryEmbeddingError("usage_mismatch")
        return measured

    def _normalize_vector(self, values: Any) -> tuple[float, ...]:
        if not isinstance(values, Sequence) or isinstance(
            values, (str, bytes, bytearray)
        ):
            raise ValueError("query embedding vector must be numeric")
        if len(values) != self.identity.dimension:
            raise ValueError("query embedding dimension mismatch")
        parsed: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("query embedding values must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("query embedding values must be finite")
            parsed.append(number)
        scale = max(abs(value) for value in parsed)
        if scale == 0:
            raise ValueError("query embedding vector cannot have zero norm")
        if self.identity.normalization == "l2":
            scaled = [value / scale for value in parsed]
            norm = math.sqrt(sum(value * value for value in scaled))
            parsed = [value / norm for value in scaled]
        return tuple(parsed)

    def _call_transport(
        self, payload: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        if self.transport_mode == "cooperative":
            return self._call_cooperative(payload, timeout_seconds)
        return self._call_external_process(payload, timeout_seconds)

    def _call_cooperative(
        self, payload: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        deadline = QueryTransportDeadline(timeout_seconds)
        started = time.monotonic()
        try:
            value = self._transport(self.identity, payload, deadline)
        except TimeoutError:
            raise TimeoutError("query embedding transport timed out") from None
        except RetryableQueryEmbeddingTransportError:
            raise
        except BaseException:
            raise _TransportFailure("query embedding transport failed") from None
        if time.monotonic() - started > timeout_seconds:
            deadline.cancel()
            raise TimeoutError("query embedding transport exceeded its deadline")
        if not isinstance(value, Mapping):
            raise TypeError("query embedding transport must return an object")
        try:
            encoded = _canonical_json(value)
        except (TypeError, ValueError, OverflowError):
            raise TypeError("query embedding transport returned an invalid object") from None
        if len(encoded) > self.policy.max_response_bytes:
            raise _ResponseTooLarge("query embedding response exceeded its byte limit")
        return value

    def _call_external_process(
        self, payload: Mapping[str, Any], timeout_seconds: float
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
            name="kg-query-embedding-external-transport",
            daemon=True,
        )
        started = False
        try:
            try:
                process.start()
                started = True
            except BaseException:
                raise _TransportFailure("query embedding transport could not start") from None
            send_connection.close()
            remaining = wall_deadline - time.monotonic()
            if remaining <= 0 or not receive_connection.poll(remaining):
                raise TimeoutError("query embedding transport exceeded its deadline")
            try:
                message = receive_connection.recv_bytes(
                    maxlength=self.policy.max_response_bytes + 1
                )
            except (OSError, EOFError):
                raise _TransportFailure("query embedding transport returned no result") from None
            process.join(_EXTERNAL_PROCESS_STOP_GRACE_SECONDS)
            if process.is_alive() or not message:
                raise _TransportFailure("query embedding transport did not terminate")
            status, encoded = message[:1], message[1:]
            if status == b"T":
                raise TimeoutError("query embedding transport timed out")
            if status == b"R":
                raise RetryableQueryEmbeddingTransportError(
                    "retryable query embedding transport failure"
                )
            if status == b"F":
                raise _TransportFailure("query embedding transport failed")
            if status == b"L":
                raise _ResponseTooLarge("query embedding response exceeded its byte limit")
            if status == b"I" or status != b"O" or not encoded:
                raise TypeError("query embedding transport returned invalid data")
            try:
                response = json.loads(encoded.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise TypeError("query embedding transport returned invalid JSON") from None
            if not isinstance(response, Mapping):
                raise TypeError("query embedding transport must return an object")
            return response
        finally:
            receive_connection.close()
            send_connection.close()
            if started:
                self._stop_process(process)

    @staticmethod
    def _stop_process(process: Any) -> None:
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

    def _ledger_entry(
        self,
        attempt: int,
        status: str,
        request_sha256: str,
        response_sha256: str | None,
        started: float,
        cost: int,
        cost_basis: str,
    ) -> QueryEmbeddingLedgerEntry:
        return QueryEmbeddingLedgerEntry(
            purpose="query",
            batch_index=0,
            attempt=attempt,
            status=status,
            request_sha256=request_sha256,
            response_sha256=response_sha256,
            latency_ms=max(0, int((self._clock() - started) * 1000)),
            accounted_cost_microunits=cost,
            cost_basis=cost_basis,
        )

    @staticmethod
    def _safe_response_sha256(response: Any) -> str | None:
        try:
            return _sha256(response)
        except (TypeError, ValueError):
            return None


__all__ = [
    "QueryEmbeddingClient",
    "QueryEmbeddingError",
    "QueryEmbeddingIdentity",
    "QueryEmbeddingInput",
    "QueryEmbeddingLedgerEntry",
    "QueryEmbeddingPolicy",
    "QueryEmbeddingResult",
    "QueryTransportDeadline",
    "RetryableQueryEmbeddingTransportError",
]
