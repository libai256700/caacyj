"""Closed provider request templates and RFC 6901 response extraction."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping


ANSWER_IDENTITY_REFS = frozenset(
    {
        "identity.api_version",
        "identity.channel_id",
        "identity.model",
        "identity.model_version",
        "identity.provider",
        "identity.region",
    }
)

ANSWER_REQUEST_REFS = frozenset(
    {
        "request.evidence",
        "request.input_units",
        "request.max_output_units",
        "request.question",
        "request.request_id",
        "request.schema_version",
    }
)

EMBEDDING_IDENTITY_REFS = frozenset(
    {
        "identity.api_version",
        "identity.dimension",
        "identity.input_type",
        "identity.model",
        "identity.model_version",
        "identity.normalization",
        "identity.provider",
        "identity.region",
    }
)

EMBEDDING_REQUEST_REFS = frozenset(
    {
        "request.embedding_identity_sha256",
        "request.input_type",
        "request.items",
        "request.purpose",
        "request.schema_version",
    }
)

ANSWER_ALLOWED_REFS = ANSWER_IDENTITY_REFS | ANSWER_REQUEST_REFS
EMBEDDING_ALLOWED_REFS = EMBEDDING_IDENTITY_REFS | EMBEDDING_REQUEST_REFS
ALLOWED_REFS = ANSWER_ALLOWED_REFS | EMBEDDING_ALLOWED_REFS
_INTERPOLATION_MARKERS = ("${", "{{", "{%", "$(")
_ARRAY_INDEX = re.compile(r"0|[1-9][0-9]*")
_MAX_DEPTH = 64
_MAX_NODES = 10_000


class ProviderWireError(ValueError):
    """Sanitized wire compilation or extraction failure."""

    def __init__(self, code: str) -> None:
        super().__init__("provider wire rejected")
        self.code = code

    def __repr__(self) -> str:
        return f"ProviderWireError(code={self.code!r})"


@dataclass(frozen=True)
class _Literal:
    value: Any


@dataclass(frozen=True)
class _Reference:
    name: str


@dataclass(frozen=True)
class _Array:
    items: tuple[Any, ...]


@dataclass(frozen=True)
class _Object:
    items: tuple[tuple[str, Any], ...]


def _contains_interpolation(value: str) -> bool:
    return any(marker in value for marker in _INTERPOLATION_MARKERS)


def _compile_node(
    value: Any,
    *,
    depth: int,
    counter: list[int],
    allowed_refs: frozenset[str],
) -> Any:
    counter[0] += 1
    if counter[0] > _MAX_NODES or depth > _MAX_DEPTH:
        raise ProviderWireError("template_too_complex")

    if value is None or isinstance(value, bool):
        return _Literal(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return _Literal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProviderWireError("non_json_literal")
        return _Literal(value)
    if isinstance(value, str):
        if _contains_interpolation(value):
            raise ProviderWireError("interpolation_forbidden")
        return _Literal(value)
    if type(value) is list:
        return _Array(
            tuple(
                _compile_node(
                    item,
                    depth=depth + 1,
                    counter=counter,
                    allowed_refs=allowed_refs,
                )
                for item in value
            )
        )
    if type(value) is dict:
        if "$ref" in value:
            if set(value) != {"$ref"}:
                raise ProviderWireError("reference_not_closed")
            name = value["$ref"]
            if not isinstance(name, str) or name not in allowed_refs:
                raise ProviderWireError("unknown_reference")
            return _Reference(name)
        compiled: list[tuple[str, Any]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProviderWireError("non_string_key")
            if _contains_interpolation(key):
                raise ProviderWireError("interpolation_forbidden")
            compiled.append(
                (
                    key,
                    _compile_node(
                        item,
                        depth=depth + 1,
                        counter=counter,
                        allowed_refs=allowed_refs,
                    ),
                )
            )
        return _Object(tuple(compiled))
    raise ProviderWireError("non_json_literal")


def _copy_json(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> Any:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > _MAX_NODES or depth > _MAX_DEPTH:
        raise ProviderWireError("value_too_complex")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProviderWireError("non_json_value")
        return value
    if isinstance(value, str):
        return value
    if type(value) is list or type(value) is tuple:
        return [
            _copy_json(item, depth=depth + 1, counter=counter) for item in value
        ]
    if type(value) is dict:
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProviderWireError("non_json_value")
            result[key] = _copy_json(item, depth=depth + 1, counter=counter)
        return result
    raise ProviderWireError("non_json_value")


def _context_value(source: Any, field: str) -> Any:
    if type(source) is dict:
        if field not in source:
            raise ProviderWireError("missing_reference")
        return source[field]
    try:
        return object.__getattribute__(source, field)
    except (AttributeError, TypeError):
        raise ProviderWireError("missing_reference") from None


def _render(node: Any, identity: Any, request: Mapping[str, Any]) -> Any:
    if isinstance(node, _Literal):
        return node.value
    if isinstance(node, _Reference):
        scope, field = node.name.split(".", 1)
        source = identity if scope == "identity" else request
        return _copy_json(_context_value(source, field))
    if isinstance(node, _Array):
        return [_render(item, identity, request) for item in node.items]
    if isinstance(node, _Object):
        return {
            key: _render(item, identity, request) for key, item in node.items
        }
    raise ProviderWireError("invalid_compiled_template")


class ProviderWire:
    """An immutable compiled request template safe for process transport."""

    def __init__(
        self,
        request_template: Mapping[str, Any],
        *,
        allowed_refs: frozenset[str] = ALLOWED_REFS,
    ) -> None:
        if type(request_template) is not dict:
            raise ProviderWireError("request_template_must_be_object")
        if (
            not isinstance(allowed_refs, frozenset)
            or not allowed_refs
            or not allowed_refs.issubset(ALLOWED_REFS)
        ):
            raise ProviderWireError("invalid_reference_contract")
        self._request_plan = _compile_node(
            request_template,
            depth=0,
            counter=[0],
            allowed_refs=allowed_refs,
        )

    def __repr__(self) -> str:
        return "ProviderWire(<closed-template>)"

    def render_request(
        self,
        identity: Any,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        if type(request) is not dict:
            raise ProviderWireError("request_context_must_be_object")
        value = _render(self._request_plan, identity, request)
        if type(value) is not dict:
            raise ProviderWireError("request_template_must_be_object")
        return value


def compile_request(
    request_template: Mapping[str, Any],
    identity: Any,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile and render one closed provider request."""

    return ProviderWire(request_template).render_request(identity, request)


def _pointer_tokens(pointer: str) -> tuple[str, ...]:
    if not isinstance(pointer, str):
        raise ProviderWireError("invalid_json_pointer")
    if pointer == "":
        return ()
    if not pointer.startswith("/") or "*" in pointer:
        raise ProviderWireError("invalid_json_pointer")
    tokens: list[str] = []
    for raw in pointer[1:].split("/"):
        index = 0
        decoded: list[str] = []
        while index < len(raw):
            if raw[index] != "~":
                decoded.append(raw[index])
                index += 1
                continue
            if index + 1 >= len(raw) or raw[index + 1] not in {"0", "1"}:
                raise ProviderWireError("invalid_json_pointer")
            decoded.append("~" if raw[index + 1] == "0" else "/")
            index += 2
        token = "".join(decoded)
        if "*" in token:
            raise ProviderWireError("invalid_json_pointer")
        tokens.append(token)
    if len(tokens) > _MAX_DEPTH:
        raise ProviderWireError("invalid_json_pointer")
    return tuple(tokens)


def validate_json_pointer(pointer: str) -> str:
    """Validate an RFC 6901 pointer while forbidding wildcard notation."""

    _pointer_tokens(pointer)
    return pointer


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    """Resolve a strict JSON pointer and return a detached JSON value."""

    value = document
    for token in _pointer_tokens(pointer):
        if type(value) is dict:
            if token not in value:
                raise ProviderWireError("pointer_not_found")
            value = value[token]
            continue
        if type(value) is list:
            if not _ARRAY_INDEX.fullmatch(token):
                raise ProviderWireError("pointer_not_found")
            index = int(token)
            if index >= len(value):
                raise ProviderWireError("pointer_not_found")
            value = value[index]
            continue
        raise ProviderWireError("pointer_not_found")
    return _copy_json(value)


def _compile_pointer_shape(value: Any, *, depth: int, counter: list[int]) -> Any:
    counter[0] += 1
    if counter[0] > _MAX_NODES or depth > _MAX_DEPTH:
        raise ProviderWireError("response_mapping_too_complex")
    if isinstance(value, str):
        validate_json_pointer(value)
        return _Literal(value)
    if type(value) is list:
        return _Array(
            tuple(
                _compile_pointer_shape(item, depth=depth + 1, counter=counter)
                for item in value
            )
        )
    if type(value) is dict:
        items: list[tuple[str, Any]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProviderWireError("non_string_key")
            items.append(
                (key, _compile_pointer_shape(item, depth=depth + 1, counter=counter))
            )
        return _Object(tuple(items))
    raise ProviderWireError("response_mapping_must_use_pointers")


def _render_pointer_shape(node: Any, document: Any) -> Any:
    if isinstance(node, _Literal):
        return resolve_json_pointer(document, node.value)
    if isinstance(node, _Array):
        return [_render_pointer_shape(item, document) for item in node.items]
    if isinstance(node, _Object):
        return {
            key: _render_pointer_shape(item, document) for key, item in node.items
        }
    raise ProviderWireError("invalid_response_mapping")


def compile_response(pointer_mapping: Mapping[str, Any], document: Any) -> dict[str, Any]:
    """Build a neutral response using only strict JSON Pointer leaves."""

    if type(pointer_mapping) is not dict or not pointer_mapping:
        raise ProviderWireError("response_mapping_must_be_object")
    plan = _compile_pointer_shape(pointer_mapping, depth=0, counter=[0])
    result = _render_pointer_shape(plan, document)
    if type(result) is not dict:
        raise ProviderWireError("response_mapping_must_be_object")
    return result
