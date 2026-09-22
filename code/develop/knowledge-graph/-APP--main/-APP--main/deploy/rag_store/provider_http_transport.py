"""Bounded provider-neutral HTTPS JSON transport.

Network authorization is deliberately outside this module. When called, the
production path opens one direct verified TLS connection to the exact endpoint.
Tests may inject an executor or connection factory without opening a socket.
"""

from __future__ import annotations

import http.client
import json
import math
import re
import ssl
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .embedding_adapter import EMBEDDING_RESPONSE_SCHEMA_VERSION
from .provider_meters import (
    MAXIMUM_REQUEST_EXPOSURE_V1,
    UNICODE_CODEPOINTS_V1,
    UTF8_BYTES_V1,
    ProviderMeterError,
    resolve_meter,
)
from .provider_wire import (
    ANSWER_ALLOWED_REFS,
    EMBEDDING_ALLOWED_REFS,
    ProviderWire,
    ProviderWireError,
    resolve_json_pointer,
    validate_json_pointer,
)
from .server_answer_model import RESPONSE_SCHEMA_VERSION


_RESPONSE_KINDS = frozenset({"server_answer", "embedding"})
_TEXT_METER_IDS = frozenset({UTF8_BYTES_V1, UNICODE_CODEPOINTS_V1})
_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_RESERVED_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "proxy-authorization",
        "proxy-connection",
        "transfer-encoding",
        "upgrade",
    }
)
_READ_CHUNK_BYTES = 64 * 1024
_MAX_ENDPOINT_BYTES = 4096


class ProviderTransportError(RuntimeError):
    """Sanitized provider transport failure with a closed local code."""

    def __init__(self, code: str) -> None:
        super().__init__("provider HTTPS transport failed")
        self.code = code

    def __repr__(self) -> str:
        return f"ProviderTransportError(code={self.code!r})"


class _DuplicateJSONKey(ValueError):
    pass


def _positive_int(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProviderTransportError(code)
    return value


def _non_negative_int(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderTransportError(code)
    return value


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError):
        raise ProviderTransportError("invalid_wire_request") from None


def _strict_json_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey()
        result[key] = value
    return result


def _parse_json(data: bytes) -> Any:
    def reject_constant(_value: str) -> Any:
        raise ValueError()

    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_json_object_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        raise ProviderTransportError("invalid_json_response") from None


def _validated_endpoint(endpoint: Any) -> tuple[str, int, str]:
    try:
        endpoint_size = len(endpoint.encode("utf-8")) if isinstance(endpoint, str) else 0
    except UnicodeError:
        raise ProviderTransportError("invalid_endpoint") from None
    if (
        not isinstance(endpoint, str)
        or not endpoint
        or endpoint_size > _MAX_ENDPOINT_BYTES
        or any(ord(character) <= 0x20 for character in endpoint)
        or "\\" in endpoint
    ):
        raise ProviderTransportError("invalid_endpoint")
    parsed = urlsplit(endpoint)
    try:
        port = parsed.port
    except ValueError:
        raise ProviderTransportError("invalid_endpoint") from None
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderTransportError("invalid_endpoint")
    try:
        host = parsed.hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise ProviderTransportError("invalid_endpoint") from None
    if not host or port is not None and not 1 <= port <= 65535:
        raise ProviderTransportError("invalid_endpoint")
    return host, port or 443, parsed.path or "/"


def _validated_headers(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if type(value) is not dict:
        raise ProviderTransportError("invalid_headers")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, header_value in value.items():
        if (
            not isinstance(name, str)
            or _HEADER_NAME.fullmatch(name) is None
            or not isinstance(header_value, str)
            or not header_value
        ):
            raise ProviderTransportError("invalid_headers")
        lowered = name.lower()
        if lowered in seen or lowered in _RESERVED_HEADERS:
            raise ProviderTransportError("invalid_headers")
        seen.add(lowered)
        if any(ord(character) < 0x20 or ord(character) > 0x7E for character in header_value):
            raise ProviderTransportError("invalid_headers")
        result.append((name, header_value))
    return tuple(result)


def _looks_sensitive_header(name: str) -> bool:
    compact = name.lower().replace("-", "").replace("_", "")
    return any(
        marker in compact
        for marker in ("authorization", "apikey", "credential", "secret", "token")
    )


def _header_dict(
    public_headers: tuple[tuple[str, str], ...],
    secret_headers: tuple[tuple[str, str], ...],
    body_length: int,
) -> dict[str, str]:
    result: dict[str, str] = {}
    seen: set[str] = set()
    for name, value in public_headers + secret_headers:
        lowered = name.lower()
        if lowered in seen:
            raise ProviderTransportError("invalid_headers")
        seen.add(lowered)
        result[name] = value

    for name, value in (("Accept", "application/json"), ("Content-Type", "application/json")):
        lowered = name.lower()
        existing_name = next(
            (candidate for candidate in result if candidate.lower() == lowered),
            None,
        )
        if existing_name is None:
            result[name] = value
        elif result[existing_name].lower() != value:
            raise ProviderTransportError("invalid_headers")
    result["Content-Length"] = str(body_length)
    return result


def _secret_fragments(headers: tuple[tuple[str, str], ...]) -> tuple[bytes, ...]:
    fragments: list[bytes] = []
    for _name, value in headers:
        candidates = [value]
        if " " in value:
            scheme, remainder = value.split(" ", 1)
            if scheme.lower() in {"basic", "bearer", "token"} and remainder:
                candidates.append(remainder)
        for candidate in candidates:
            encoded = candidate.encode("ascii")
            if encoded and encoded not in fragments:
                fragments.append(encoded)
    return tuple(fragments)


def _contains_secret(data: bytes, fragments: tuple[bytes, ...]) -> bool:
    return any(fragment in data for fragment in fragments)


def _request_size(headers: Mapping[str, str], body: bytes) -> int:
    return len(body) + sum(
        len(name.encode("ascii")) + len(value.encode("ascii")) + 4
        for name, value in headers.items()
    )


def _verified_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _response_headers(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        items = list(value.items())
    elif type(value) is list:
        items = value
    else:
        raise ProviderTransportError("invalid_http_response")
    result: dict[str, str] = {}
    for item in items:
        if type(item) not in {tuple, list} or len(item) != 2:
            raise ProviderTransportError("invalid_http_response")
        name, header_value = item
        if not isinstance(name, str) or not isinstance(header_value, str):
            raise ProviderTransportError("invalid_http_response")
        lowered = name.lower()
        if lowered in result:
            raise ProviderTransportError("invalid_http_response")
        result[lowered] = header_value.strip()
    return result


def _validate_http_metadata(status: Any, headers: Any, max_response_bytes: int) -> None:
    if isinstance(status, bool) or not isinstance(status, int):
        raise ProviderTransportError("invalid_http_response")
    if 300 <= status <= 399:
        raise ProviderTransportError("redirect_rejected")
    if not 200 <= status <= 299:
        raise ProviderTransportError("http_status_failure")
    normalized = _response_headers(headers)
    content_type = normalized.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise ProviderTransportError("invalid_content_type")
    content_encoding = normalized.get("content-encoding", "identity").lower()
    if content_encoding not in {"", "identity"}:
        raise ProviderTransportError("unsupported_content_encoding")
    content_length = normalized.get("content-length")
    if content_length is not None:
        if not content_length.isdigit() or int(content_length) > max_response_bytes:
            raise ProviderTransportError("response_too_large")


def _read_bounded(response: Any, max_response_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining_with_sentinel = max_response_bytes - total + 1
        try:
            chunk = response.read(min(_READ_CHUNK_BYTES, remaining_with_sentinel))
        except TimeoutError:
            raise TimeoutError("provider HTTPS request timed out") from None
        except Exception:
            raise ProviderTransportError("response_read_failure") from None
        if not isinstance(chunk, bytes):
            raise ProviderTransportError("invalid_http_response")
        if not chunk:
            break
        total += len(chunk)
        if total > max_response_bytes:
            raise ProviderTransportError("response_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


class _BufferedExecutorResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self._offset = 0

    def read(self, amount: int) -> bytes:
        chunk = self._body[self._offset : self._offset + amount]
        self._offset += len(chunk)
        return chunk


def _identity_value(identity: Any, field: str) -> Any:
    if type(identity) is dict:
        if field not in identity:
            raise ProviderTransportError("identity_mismatch")
        return identity[field]
    try:
        return object.__getattribute__(identity, field)
    except (AttributeError, TypeError):
        raise ProviderTransportError("identity_mismatch") from None


class ProviderHTTPTransport:
    """Compile one request, perform one bounded POST, and freeze its response."""

    def __init__(
        self,
        *,
        endpoint: str,
        request_template: Mapping[str, Any],
        response_kind: str,
        response_mapping: Mapping[str, Any],
        input_meter_id: str,
        output_meter_id: str = UNICODE_CODEPOINTS_V1,
        cost_meter_id: str = MAXIMUM_REQUEST_EXPOSURE_V1,
        maximum_cost_microunits: int = 0,
        headers: Mapping[str, str] | None = None,
        secret_headers: Mapping[str, str] | None = None,
        max_request_bytes: int = 1_048_576,
        max_response_bytes: int = 1_048_576,
        connection_factory: Callable[..., Any] | None = None,
        executor: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self._host, self._port, self._target = _validated_endpoint(endpoint)
        if (
            not isinstance(response_kind, str)
            or response_kind not in _RESPONSE_KINDS
        ):
            raise ProviderTransportError("invalid_response_kind")
        if (
            not isinstance(input_meter_id, str)
            or input_meter_id not in _TEXT_METER_IDS
        ):
            raise ProviderTransportError("invalid_input_meter")
        if (
            response_kind == "server_answer"
            and (
                not isinstance(output_meter_id, str)
                or output_meter_id not in _TEXT_METER_IDS
            )
        ):
            raise ProviderTransportError("invalid_output_meter")
        if (
            not isinstance(cost_meter_id, str)
            or cost_meter_id != MAXIMUM_REQUEST_EXPOSURE_V1
        ):
            raise ProviderTransportError("invalid_cost_meter")
        resolve_meter(input_meter_id)
        resolve_meter(output_meter_id)
        resolve_meter(cost_meter_id)
        self.response_kind = response_kind
        self.input_meter_id = input_meter_id
        self.output_meter_id = output_meter_id
        self.cost_meter_id = cost_meter_id
        self.maximum_cost_microunits = _non_negative_int(
            maximum_cost_microunits,
            "invalid_maximum_cost",
        )
        self.max_request_bytes = _positive_int(
            max_request_bytes,
            "invalid_request_limit",
        )
        self.max_response_bytes = _positive_int(
            max_response_bytes,
            "invalid_response_limit",
        )
        self._wire = ProviderWire(
            request_template,
            allowed_refs=(
                ANSWER_ALLOWED_REFS
                if response_kind == "server_answer"
                else EMBEDDING_ALLOWED_REFS
            ),
        )
        self._public_headers = _validated_headers(headers)
        self._secret_headers = _validated_headers(secret_headers)
        if any(
            _looks_sensitive_header(name) for name, _value in self._public_headers
        ):
            raise ProviderTransportError("sensitive_header_must_be_secret")
        public_names = {name.lower() for name, _value in self._public_headers}
        secret_names = {name.lower() for name, _value in self._secret_headers}
        if public_names & secret_names:
            raise ProviderTransportError("invalid_headers")
        self._secret_fragments = _secret_fragments(self._secret_headers)
        if connection_factory is not None and not callable(connection_factory):
            raise ProviderTransportError("invalid_connection_factory")
        if executor is not None and not callable(executor):
            raise ProviderTransportError("invalid_executor")
        if connection_factory is not None and executor is not None:
            raise ProviderTransportError("ambiguous_test_injection")
        self._connection_factory = connection_factory
        self._executor = executor
        self._configure_response_mapping(response_mapping)

    def __repr__(self) -> str:
        return f"ProviderHTTPTransport(response_kind={self.response_kind!r})"

    def _configure_response_mapping(self, mapping: Any) -> None:
        if type(mapping) is not dict:
            raise ProviderTransportError("invalid_response_mapping")
        if self.response_kind == "server_answer":
            if set(mapping) != {"answer_pointer"}:
                raise ProviderTransportError("invalid_response_mapping")
            self._answer_pointer = validate_json_pointer(mapping["answer_pointer"])
            self._vectors_pointer = None
            self._values_pointer = None
            self._match_by = None
            self._id_pointer = None
            return

        required = {"vectors_pointer", "values_pointer", "match_by"}
        optional = {"id_pointer"}
        if not required.issubset(mapping) or set(mapping) - required - optional:
            raise ProviderTransportError("invalid_response_mapping")
        match_by = mapping["match_by"]
        if (
            not isinstance(match_by, str)
            or match_by not in {"input_order", "response_id"}
        ):
            raise ProviderTransportError("invalid_response_mapping")
        if match_by == "response_id" and "id_pointer" not in mapping:
            raise ProviderTransportError("invalid_response_mapping")
        if match_by == "input_order" and "id_pointer" in mapping:
            raise ProviderTransportError("invalid_response_mapping")
        self._answer_pointer = None
        self._vectors_pointer = validate_json_pointer(mapping["vectors_pointer"])
        self._values_pointer = validate_json_pointer(mapping["values_pointer"])
        self._match_by = match_by
        self._id_pointer = (
            validate_json_pointer(mapping["id_pointer"])
            if "id_pointer" in mapping
            else None
        )

    def __call__(
        self,
        identity: Any,
        request: Mapping[str, Any],
        deadline: Any,
    ) -> Mapping[str, Any]:
        try:
            return self._invoke(identity, request, deadline)
        except TimeoutError:
            raise TimeoutError("provider HTTPS request timed out") from None
        except ProviderTransportError:
            raise
        except (ProviderWireError, ProviderMeterError):
            raise ProviderTransportError("provider_contract_failure") from None
        except Exception:
            raise ProviderTransportError("transport_failure") from None

    def _invoke(
        self,
        identity: Any,
        request: Mapping[str, Any],
        deadline: Any,
    ) -> Mapping[str, Any]:
        if _identity_value(identity, "base_url") != self.endpoint:
            raise ProviderTransportError("identity_mismatch")
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise ProviderTransportError("invalid_deadline")
        try:
            timeout = float(deadline)
        except (TypeError, ValueError, OverflowError):
            raise ProviderTransportError("invalid_deadline") from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise ProviderTransportError("invalid_deadline")
        if bool(getattr(deadline, "cancelled", False)):
            raise TimeoutError("provider HTTPS request timed out")

        provider_request = self._wire.render_request(identity, request)
        body = _canonical_json(provider_request)
        if len(body) > self.max_request_bytes:
            raise ProviderTransportError("request_too_large")
        if _contains_secret(body, self._secret_fragments):
            raise ProviderTransportError("secret_in_request_body")
        headers = _header_dict(self._public_headers, self._secret_headers, len(body))
        if _request_size(headers, body) > self.max_request_bytes:
            raise ProviderTransportError("request_too_large")
        raw_response = self._exchange(headers, body, timeout)
        if bool(getattr(deadline, "cancelled", False)):
            raise TimeoutError("provider HTTPS request timed out")
        if _contains_secret(raw_response, self._secret_fragments):
            raise ProviderTransportError("secret_in_response")
        provider_response = _parse_json(raw_response)
        if self.response_kind == "server_answer":
            return self._server_answer_response(identity, request, provider_response)
        return self._embedding_response(identity, request, provider_response)

    def _exchange(self, headers: Mapping[str, str], body: bytes, timeout: float) -> bytes:
        if self._executor is not None:
            try:
                result = self._executor(
                    method="POST",
                    endpoint=self.endpoint,
                    headers=dict(headers),
                    body=body,
                    timeout_seconds=timeout,
                    max_response_bytes=self.max_response_bytes,
                )
            except TimeoutError:
                raise TimeoutError("provider HTTPS request timed out") from None
            except Exception:
                raise ProviderTransportError("transport_failure") from None
            if type(result) is not tuple or len(result) != 3:
                raise ProviderTransportError("invalid_http_response")
            status, response_headers, response_body = result
            if not isinstance(response_body, bytes):
                raise ProviderTransportError("invalid_http_response")
            _validate_http_metadata(status, response_headers, self.max_response_bytes)
            return _read_bounded(
                _BufferedExecutorResponse(response_body),
                self.max_response_bytes,
            )

        context = _verified_tls_context()
        factory = self._connection_factory or http.client.HTTPSConnection
        connection: Any = None
        response: Any = None
        try:
            connection = factory(
                host=self._host,
                port=self._port,
                timeout=timeout,
                context=context,
            )
            connection.request(
                "POST",
                self._target,
                body=body,
                headers=dict(headers),
                encode_chunked=False,
            )
            response = connection.getresponse()
            _validate_http_metadata(
                response.status,
                response.getheaders(),
                self.max_response_bytes,
            )
            return _read_bounded(response, self.max_response_bytes)
        except TimeoutError:
            raise TimeoutError("provider HTTPS request timed out") from None
        except ProviderTransportError:
            raise
        except (http.client.HTTPException, OSError, ssl.SSLError):
            raise ProviderTransportError("transport_failure") from None
        except Exception:
            raise ProviderTransportError("transport_failure") from None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def _server_answer_response(
        self,
        identity: Any,
        request: Mapping[str, Any],
        provider_response: Any,
    ) -> Mapping[str, Any]:
        answer = resolve_json_pointer(provider_response, self._answer_pointer or "")
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderTransportError("invalid_provider_response")
        try:
            input_units = resolve_meter(self.input_meter_id)(request)
            output_units = resolve_meter(self.output_meter_id)(answer)
            cost = resolve_meter(self.cost_meter_id)(identity, input_units, output_units)
        except ProviderMeterError:
            raise ProviderTransportError("meter_failure") from None
        identity_sha256 = _identity_value(identity, "identity_sha256")
        if not isinstance(identity_sha256, str):
            raise ProviderTransportError("identity_mismatch")
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "channel_identity_sha256": identity_sha256,
            "answer": answer,
            "usage": {
                "input_units": input_units,
                "output_units": output_units,
                "cost_microunits": cost,
            },
        }

    def _embedding_response(
        self,
        identity: Any,
        request: Mapping[str, Any],
        provider_response: Any,
    ) -> Mapping[str, Any]:
        vectors = resolve_json_pointer(provider_response, self._vectors_pointer or "")
        if type(vectors) is not list:
            raise ProviderTransportError("invalid_provider_response")
        items = request.get("items") if type(request) is dict else None
        if type(items) is not list or not items:
            raise ProviderTransportError("invalid_provider_request")
        expected_ids: list[str] = []
        input_units = 0
        input_meter = resolve_meter(self.input_meter_id)
        for item in items:
            if (
                type(item) is not dict
                or not isinstance(item.get("id"), str)
                or not isinstance(item.get("text"), str)
            ):
                raise ProviderTransportError("invalid_provider_request")
            expected_ids.append(item["id"])
            try:
                input_units += input_meter(item["text"])
            except ProviderMeterError:
                raise ProviderTransportError("meter_failure") from None
        if len(expected_ids) != len(set(expected_ids)) or len(vectors) != len(expected_ids):
            raise ProviderTransportError("invalid_provider_response")

        parsed: dict[str, Any] = {}
        if self._match_by == "input_order":
            for object_id, item in zip(expected_ids, vectors, strict=True):
                parsed[object_id] = resolve_json_pointer(item, self._values_pointer or "")
        else:
            for item in vectors:
                object_id = resolve_json_pointer(item, self._id_pointer or "")
                if (
                    not isinstance(object_id, str)
                    or object_id not in expected_ids
                    or object_id in parsed
                ):
                    raise ProviderTransportError("invalid_provider_response")
                parsed[object_id] = resolve_json_pointer(item, self._values_pointer or "")
        if set(parsed) != set(expected_ids):
            raise ProviderTransportError("invalid_provider_response")
        try:
            cost = resolve_meter(self.cost_meter_id)(self.maximum_cost_microunits)
        except ProviderMeterError:
            raise ProviderTransportError("meter_failure") from None
        identity_sha256 = _identity_value(identity, "sha256")
        if not isinstance(identity_sha256, str):
            raise ProviderTransportError("identity_mismatch")
        return {
            "schema_version": EMBEDDING_RESPONSE_SCHEMA_VERSION,
            "embedding_identity_sha256": identity_sha256,
            "vectors": [
                {"id": object_id, "values": parsed[object_id]}
                for object_id in expected_ids
            ],
            "failed_ids": [],
            "usage": {
                "input_units": input_units,
                "cost_microunits": cost,
            },
        }
