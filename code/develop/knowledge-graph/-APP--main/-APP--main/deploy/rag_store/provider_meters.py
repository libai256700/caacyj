"""Closed local meter registry for provider transports.

The registry contains code-owned callables only. Configuration selects a fixed
identifier; it cannot import or name an arbitrary Python object.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Callable, Mapping


UTF8_BYTES_V1 = "utf8_bytes-v1"
UNICODE_CODEPOINTS_V1 = "unicode_codepoints-v1"
MAXIMUM_REQUEST_EXPOSURE_V1 = "maximum_request_exposure-v1"


class ProviderMeterError(ValueError):
    """Sanitized failure raised by a fixed local meter."""

    def __init__(self, code: str) -> None:
        super().__init__("provider meter failed")
        self.code = code

    def __repr__(self) -> str:
        return f"ProviderMeterError(code={self.code!r})"


def _meter_texts(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if type(value) is not dict:
        raise ProviderMeterError("unsupported_input")

    question = value.get("question")
    evidence = value.get("evidence")
    if not isinstance(question, str) or type(evidence) is not list:
        raise ProviderMeterError("unsupported_input")

    texts = [question]
    for item in evidence:
        if type(item) is not dict or not isinstance(item.get("text"), str):
            raise ProviderMeterError("unsupported_input")
        texts.append(item["text"])
    return tuple(texts)


def utf8_bytes_v1(value: Any) -> int:
    """Count UTF-8 bytes in text or in disclosed answer request text fields."""

    try:
        return sum(len(item.encode("utf-8")) for item in _meter_texts(value))
    except UnicodeError:
        raise ProviderMeterError("invalid_text") from None


def unicode_codepoints_v1(value: Any) -> int:
    """Count Unicode code points in text or disclosed answer request text fields."""

    return sum(len(item) for item in _meter_texts(value))


def maximum_request_exposure_v1(owner: Any, *_unused: Any) -> int:
    """Return the frozen maximum cost for one disclosed provider request."""

    value: Any
    if isinstance(owner, bool):
        raise ProviderMeterError("invalid_maximum")
    if isinstance(owner, int):
        value = owner
    elif type(owner) is dict:
        value = owner.get("max_cost_microunits")
    else:
        try:
            value = object.__getattribute__(owner, "max_cost_microunits")
        except (AttributeError, TypeError):
            raise ProviderMeterError("invalid_maximum") from None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderMeterError("invalid_maximum")
    return value


Meter = Callable[..., int]

_METERS: Mapping[str, Meter] = MappingProxyType(
    {
        UTF8_BYTES_V1: utf8_bytes_v1,
        UNICODE_CODEPOINTS_V1: unicode_codepoints_v1,
        MAXIMUM_REQUEST_EXPOSURE_V1: maximum_request_exposure_v1,
    }
)


def meter_ids() -> tuple[str, ...]:
    """Return the complete immutable meter identifier set."""

    return tuple(_METERS)


def resolve_meter(meter_id: str) -> Meter:
    """Resolve one fixed identifier without dynamic imports or aliases."""

    if not isinstance(meter_id, str):
        raise ProviderMeterError("unknown_meter")
    try:
        return _METERS[meter_id]
    except KeyError:
        raise ProviderMeterError("unknown_meter") from None
