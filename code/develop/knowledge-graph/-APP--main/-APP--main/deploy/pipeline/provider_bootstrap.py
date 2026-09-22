#!/usr/bin/env python3
"""Fail-closed provider configuration and production runtime bootstrap.

The checked-in default is disabled. Production HTTPS can only be assembled
from a hash-bound config, a Stop B approval binding, and secret references.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit


CONFIG_ENVIRONMENT_VARIABLE = "KG_PROVIDER_RUNTIME_CONFIG"
NETWORK_MODE_ENVIRONMENT_VARIABLE = "KG_PROVIDER_NETWORK_MODE"
APPROVAL_TRUST_ANCHOR_ENVIRONMENT_VARIABLE = (
    "KG_STOP_B_PRODUCTION_APPROVAL_SHA256"
)
CONFIG_SCHEMA_VERSION = "kg-provider-runtime-config-v1"
MAX_CONFIG_BYTES = 8 * 1024 * 1024
MAX_CONTRACT_EVIDENCE_BYTES = 64 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECRET_REF = re.compile(r"^secretref:(KG_[A-Z0-9_]{1,96})$")
_HEADER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
_UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_FORBIDDEN_AUTH_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_ANSWER_STRATEGIES = frozenset(
    {"single", "sequential_fallback", "parallel_hedge"}
)
_WINNER_POLICIES = frozenset({"first_success", "ordered_success"})
_TEXT_METERS = frozenset({"utf8_bytes-v1", "unicode_codepoints-v1"})
_COST_METERS = frozenset({"maximum_request_exposure-v1"})
_APPROVAL_PLACEHOLDER_MARKERS = (
    "fake",
    "fixture",
    "offline",
    "synthetic",
    "test-only",
)


class ProviderBootstrapError(RuntimeError):
    """Sanitized startup failure with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        super().__init__("provider runtime bootstrap failed")
        self.code = code

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "kg-provider-bootstrap-error-v1",
            "error": self.code,
            "provider_runtime_ready": False,
        }


class ProviderRuntimeConfigError(ProviderBootstrapError):
    pass


class ProviderApprovalError(ProviderBootstrapError):
    pass


class ProviderSecretError(ProviderBootstrapError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_regular_file_bytes(
    path: str | Path,
    *,
    code: str,
    maximum_bytes: int = MAX_CONFIG_BYTES,
) -> tuple[Path, bytes]:
    raw = Path(path)
    if not raw.is_absolute():
        raise ProviderRuntimeConfigError(code)
    lexical = Path(os.path.abspath(raw))
    try:
        resolved = raw.resolve(strict=True)
    except OSError:
        raise ProviderRuntimeConfigError(code) from None
    if resolved != lexical or resolved.is_symlink():
        raise ProviderRuntimeConfigError(code)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError:
        raise ProviderRuntimeConfigError(code) from None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum_bytes:
            raise ProviderRuntimeConfigError(code)
        blocks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining > 0:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        payload = b"".join(blocks)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if (
            identity_before != identity_after
            or len(payload) != before.st_size
            or len(payload) > maximum_bytes
        ):
            raise ProviderRuntimeConfigError(code)
        return resolved, payload
    finally:
        os.close(descriptor)


def _strict_json(payload: bytes, *, code: str) -> dict[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise ProviderRuntimeConfigError(code) from None
    if not isinstance(value, dict):
        raise ProviderRuntimeConfigError(code)
    return value


def _exact(value: Any, fields: set[str], *, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ProviderRuntimeConfigError(code)
    return dict(value)


def _text(value: Any, *, code: str, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
        or "\x00" in value
        or "\r" in value
        or "\n" in value
    ):
        raise ProviderRuntimeConfigError(code)
    return value


def _sha256(value: Any, *, code: str) -> str:
    parsed = _text(value, code=code, maximum=64)
    if not _SHA256.fullmatch(parsed):
        raise ProviderRuntimeConfigError(code)
    return parsed


def _positive_int(value: Any, *, code: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProviderRuntimeConfigError(code)
    if value < 0 or (value == 0 and not allow_zero):
        raise ProviderRuntimeConfigError(code)
    return value


def _positive_number(value: Any, *, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderRuntimeConfigError(code)
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ProviderRuntimeConfigError(code)
    return parsed


def _https_endpoint(value: Any, *, code: str) -> str:
    endpoint = _text(value, code=code, maximum=2048)
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or "//" in parsed.path
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise ProviderRuntimeConfigError(code)
    try:
        parsed.port
    except ValueError:
        raise ProviderRuntimeConfigError(code) from None
    return endpoint


def _absolute_path(value: Any, *, code: str) -> Path:
    path = Path(_text(value, code=code, maximum=4096))
    if not path.is_absolute():
        raise ProviderRuntimeConfigError(code)
    return path


def _json_pointer(value: Any, *, code: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    pointer = _text(value, code=code, maximum=2048)
    if not pointer.startswith("/") or "*" in pointer:
        raise ProviderRuntimeConfigError(code)
    for token in pointer[1:].split("/"):
        index = 0
        while index < len(token):
            if token[index] == "~":
                if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
                    raise ProviderRuntimeConfigError(code)
                index += 2
            else:
                index += 1
    return pointer


@dataclass(frozen=True)
class AuthBinding:
    header_name: str
    prefix: str


@dataclass(frozen=True)
class MeterBinding:
    input_meter_id: str
    output_meter_id: str
    cost_meter_id: str


@dataclass(frozen=True)
class ApprovalBinding:
    receipt_path: Path
    receipt_sha256: str
    stop_b_request_path: Path
    stop_b_request_sha256: str
    contract_materials_path: Path
    contract_materials_sha256: str
    egress_policy_path: Path
    egress_policy_sha256: str


@dataclass(frozen=True)
class AnswerWireBinding:
    request_schema_sha256: str
    response_schema_sha256: str
    body_template: Any
    answer_pointer: str
    wire_contract_sha256: str


@dataclass(frozen=True)
class AnswerChannelConfig:
    channel_id: str
    approval_role_id: str
    provider: str
    endpoint: str
    region: str
    model: str
    model_version: str
    api_version: str
    identity_sha256: str
    secret_ref: str
    auth: AuthBinding
    limits: Mapping[str, Any]
    meters: MeterBinding
    wire: AnswerWireBinding


@dataclass(frozen=True)
class ServerAnswerConfig:
    strategy: str
    winner_policy: str
    total_budget_seconds: float
    total_cost_budget_microunits: int
    circuit_breaker_failure_threshold: int
    circuit_breaker_cooldown_seconds: float
    channels: tuple[AnswerChannelConfig, ...]


@dataclass(frozen=True)
class EmbeddingWireBinding:
    request_schema_sha256: str
    response_schema_sha256: str
    body_template: Any
    vectors_pointer: str
    values_pointer: str
    match_by: str
    id_pointer: str | None
    wire_contract_sha256: str


@dataclass(frozen=True)
class EmbeddingConfig:
    approval_role_id: str
    identity: Mapping[str, Any]
    identity_sha256: str
    policy: Mapping[str, Any]
    policy_sha256: str
    secret_ref: str
    auth: AuthBinding
    meters: MeterBinding
    wire: EmbeddingWireBinding


@dataclass(frozen=True)
class ResolvedSecret:
    environment_name: str
    _value: str = field(repr=False)

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"ResolvedSecret(environment_name={self.environment_name!r}, value=<redacted>)"


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    path: Path
    sha256: str
    contract_sha256: str
    network_mode: str
    approval_binding: ApprovalBinding | None
    server_answer: ServerAnswerConfig | None
    embedding: EmbeddingConfig | None

    @classmethod
    def load(cls, path: str | Path) -> "ProviderRuntimeConfig":
        resolved, payload = _stable_regular_file_bytes(
            path, code="provider_config_unavailable"
        )
        root = _strict_json(payload, code="provider_config_invalid_json")
        root = _exact(
            root,
            {
                "schema_version",
                "network_mode",
                "approval_binding",
                "server_answer",
                "embedding",
            },
            code="provider_config_shape_invalid",
        )
        if root["schema_version"] != CONFIG_SCHEMA_VERSION:
            raise ProviderRuntimeConfigError("provider_config_schema_mismatch")
        network_mode = root["network_mode"]
        if network_mode not in {"disabled", "https"}:
            raise ProviderRuntimeConfigError("provider_network_mode_invalid")
        if network_mode == "disabled":
            if any(
                root[field] is not None
                for field in ("approval_binding", "server_answer", "embedding")
            ):
                raise ProviderRuntimeConfigError("disabled_provider_config_not_empty")
            return cls(
                path=resolved,
                sha256=_sha256_bytes(payload),
                contract_sha256=_canonical_sha256(
                    {
                        "schema_version": CONFIG_SCHEMA_VERSION,
                        "network_mode": "disabled",
                        "server_answer": None,
                        "embedding": None,
                    }
                ),
                network_mode=network_mode,
                approval_binding=None,
                server_answer=None,
                embedding=None,
            )
        approval = _parse_approval(root["approval_binding"])
        server_answer = _parse_server_answer(root["server_answer"])
        embedding = _parse_embedding(root["embedding"])
        contract = {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "network_mode": network_mode,
            "server_answer": root["server_answer"],
            "embedding": root["embedding"],
        }
        return cls(
            path=resolved,
            sha256=_sha256_bytes(payload),
            contract_sha256=_canonical_sha256(contract),
            network_mode=network_mode,
            approval_binding=approval,
            server_answer=server_answer,
            embedding=embedding,
        )


def _parse_auth(value: Any, *, code: str) -> AuthBinding:
    item = _exact(value, {"header_name", "prefix"}, code=code)
    header = _text(item["header_name"], code=code, maximum=64)
    prefix = item["prefix"]
    if (
        not _HEADER_NAME.fullmatch(header)
        or header.lower() in _FORBIDDEN_AUTH_HEADERS
        or not isinstance(prefix, str)
        or len(prefix) > 128
        or any(character in prefix for character in "\r\n\x00")
    ):
        raise ProviderRuntimeConfigError(code)
    return AuthBinding(header, prefix)


def _parse_meters(value: Any, *, code: str) -> MeterBinding:
    item = _exact(
        value,
        {"input_meter_id", "output_meter_id", "cost_meter_id"},
        code=code,
    )
    if (
        item["input_meter_id"] not in _TEXT_METERS
        or item["output_meter_id"] not in _TEXT_METERS
        or item["cost_meter_id"] not in _COST_METERS
    ):
        raise ProviderRuntimeConfigError(code)
    return MeterBinding(
        item["input_meter_id"], item["output_meter_id"], item["cost_meter_id"]
    )


def _secret_ref(value: Any, *, code: str) -> str:
    parsed = _text(value, code=code, maximum=110)
    if not _SECRET_REF.fullmatch(parsed):
        raise ProviderRuntimeConfigError(code)
    return parsed


def _parse_approval(value: Any) -> ApprovalBinding:
    item = _exact(
        value,
        {
            "receipt_path",
            "receipt_sha256",
            "stop_b_request_path",
            "stop_b_request_sha256",
            "contract_materials_path",
            "contract_materials_sha256",
            "egress_policy_path",
            "egress_policy_sha256",
        },
        code="approval_binding_invalid",
    )
    return ApprovalBinding(
        _absolute_path(item["receipt_path"], code="approval_binding_invalid"),
        _sha256(item["receipt_sha256"], code="approval_binding_invalid"),
        _absolute_path(item["stop_b_request_path"], code="approval_binding_invalid"),
        _sha256(item["stop_b_request_sha256"], code="approval_binding_invalid"),
        _absolute_path(item["contract_materials_path"], code="approval_binding_invalid"),
        _sha256(item["contract_materials_sha256"], code="approval_binding_invalid"),
        _absolute_path(item["egress_policy_path"], code="approval_binding_invalid"),
        _sha256(item["egress_policy_sha256"], code="approval_binding_invalid"),
    )


def _parse_server_answer(value: Any) -> ServerAnswerConfig:
    item = _exact(
        value,
        {
            "strategy",
            "winner_policy",
            "total_budget_seconds",
            "total_cost_budget_microunits",
            "circuit_breaker_failure_threshold",
            "circuit_breaker_cooldown_seconds",
            "channels",
        },
        code="server_answer_config_invalid",
    )
    strategy = item["strategy"]
    winner = item["winner_policy"]
    if strategy not in _ANSWER_STRATEGIES or winner not in _WINNER_POLICIES:
        raise ProviderRuntimeConfigError("server_answer_policy_invalid")
    channels_raw = item["channels"]
    if not isinstance(channels_raw, list) or not channels_raw:
        raise ProviderRuntimeConfigError("server_answer_channels_invalid")
    channels = tuple(
        _parse_answer_channel(value, index) for index, value in enumerate(channels_raw)
    )
    ids = [channel.channel_id for channel in channels]
    if len(ids) != len(set(ids)):
        raise ProviderRuntimeConfigError("server_answer_channels_invalid")
    if strategy == "single" and len(channels) != 1:
        raise ProviderRuntimeConfigError("server_answer_policy_invalid")
    if strategy != "parallel_hedge" and winner != "ordered_success":
        raise ProviderRuntimeConfigError("server_answer_policy_invalid")
    return ServerAnswerConfig(
        strategy=strategy,
        winner_policy=winner,
        total_budget_seconds=_positive_number(
            item["total_budget_seconds"], code="server_answer_policy_invalid"
        ),
        total_cost_budget_microunits=_positive_int(
            item["total_cost_budget_microunits"],
            code="server_answer_policy_invalid",
        ),
        circuit_breaker_failure_threshold=_positive_int(
            item["circuit_breaker_failure_threshold"],
            code="server_answer_policy_invalid",
        ),
        circuit_breaker_cooldown_seconds=_positive_number(
            item["circuit_breaker_cooldown_seconds"],
            code="server_answer_policy_invalid",
        ),
        channels=channels,
    )


def _parse_answer_channel(value: Any, index: int) -> AnswerChannelConfig:
    code = "server_answer_channel_invalid"
    item = _exact(
        value,
        {
            "channel_id",
            "approval_role_id",
            "provider",
            "endpoint",
            "region",
            "model",
            "model_version",
            "api_version",
            "identity_sha256",
            "secret_ref",
            "auth",
            "limits",
            "meters",
            "wire",
        },
        code=code,
    )
    limits = _exact(
        item["limits"],
        {
            "timeout_seconds",
            "max_input_units",
            "max_output_units",
            "max_cost_microunits",
            "max_request_bytes",
            "max_response_bytes",
        },
        code=code,
    )
    parsed_limits = {
        "timeout_seconds": _positive_number(limits["timeout_seconds"], code=code),
        "max_input_units": _positive_int(limits["max_input_units"], code=code),
        "max_output_units": _positive_int(limits["max_output_units"], code=code),
        "max_cost_microunits": _positive_int(
            limits["max_cost_microunits"], code=code, allow_zero=True
        ),
        "max_request_bytes": _positive_int(limits["max_request_bytes"], code=code),
        "max_response_bytes": _positive_int(limits["max_response_bytes"], code=code),
    }
    wire_raw = _exact(
        item["wire"],
        {
            "schema_version",
            "request_schema_sha256",
            "response_schema_sha256",
            "body_template",
            "answer_pointer",
            "wire_contract_sha256",
        },
        code=code,
    )
    if wire_raw["schema_version"] != "kg-provider-answer-wire-v1":
        raise ProviderRuntimeConfigError(code)
    try:
        from rag_store.provider_wire import ANSWER_ALLOWED_REFS, ProviderWire

        ProviderWire(
            wire_raw["body_template"], allowed_refs=ANSWER_ALLOWED_REFS
        )
    except Exception:
        raise ProviderRuntimeConfigError(code) from None
    expected_wire_sha = _canonical_sha256(
        {key: value for key, value in wire_raw.items() if key != "wire_contract_sha256"}
    )
    declared_wire_sha = _sha256(wire_raw["wire_contract_sha256"], code=code)
    if declared_wire_sha != expected_wire_sha:
        raise ProviderRuntimeConfigError("server_answer_wire_hash_mismatch")
    channel = AnswerChannelConfig(
        channel_id=_text(item["channel_id"], code=code),
        approval_role_id=_text(item["approval_role_id"], code=code),
        provider=_text(item["provider"], code=code),
        endpoint=_https_endpoint(item["endpoint"], code=code),
        region=_text(item["region"], code=code),
        model=_text(item["model"], code=code),
        model_version=_text(item["model_version"], code=code),
        api_version=_text(item["api_version"], code=code),
        identity_sha256=_sha256(item["identity_sha256"], code=code),
        secret_ref=_secret_ref(item["secret_ref"], code=code),
        auth=_parse_auth(item["auth"], code=code),
        limits=parsed_limits,
        meters=_parse_meters(item["meters"], code=code),
        wire=AnswerWireBinding(
            request_schema_sha256=_sha256(
                wire_raw["request_schema_sha256"], code=code
            ),
            response_schema_sha256=_sha256(
                wire_raw["response_schema_sha256"], code=code
            ),
            body_template=wire_raw["body_template"],
            answer_pointer=_json_pointer(wire_raw["answer_pointer"], code=code) or "",
            wire_contract_sha256=declared_wire_sha,
        ),
    )
    from rag_store.server_answer_model import ServerAnswerChannel

    runtime_channel = ServerAnswerChannel(
        channel_id=channel.channel_id,
        provider=channel.provider,
        base_url=channel.endpoint,
        region=channel.region,
        model=channel.model,
        model_version=channel.model_version,
        api_version=channel.api_version,
        **dict(channel.limits),
    )
    if runtime_channel.identity_sha256 != channel.identity_sha256:
        raise ProviderRuntimeConfigError("server_answer_identity_hash_mismatch")
    return channel


def _parse_embedding(value: Any) -> EmbeddingConfig:
    code = "embedding_config_invalid"
    item = _exact(
        value,
        {
            "approval_role_id",
            "identity",
            "identity_sha256",
            "policy",
            "policy_sha256",
            "secret_ref",
            "auth",
            "meters",
            "wire",
        },
        code=code,
    )
    identity_raw = _exact(
        item["identity"],
        {
            "provider",
            "endpoint",
            "region",
            "model",
            "model_version",
            "api_version",
            "dimension",
            "normalization",
            "input_type",
        },
        code=code,
    )
    identity = {
        "provider": _text(identity_raw["provider"], code=code),
        "base_url": _https_endpoint(identity_raw["endpoint"], code=code),
        "region": _text(identity_raw["region"], code=code),
        "model": _text(identity_raw["model"], code=code),
        "model_version": _text(identity_raw["model_version"], code=code),
        "api_version": _text(identity_raw["api_version"], code=code),
        "dimension": _positive_int(identity_raw["dimension"], code=code),
        "normalization": identity_raw["normalization"],
        "input_type": _text(identity_raw["input_type"], code=code),
    }
    if identity["normalization"] not in {"l2", "none"}:
        raise ProviderRuntimeConfigError(code)
    policy_raw = _exact(
        item["policy"],
        {
            "batch_size",
            "max_input_units",
            "timeout_seconds",
            "max_retries",
            "max_requests_per_operation",
            "max_cost_microunits_per_request",
            "total_cost_budget_microunits",
            "max_request_bytes",
            "max_response_bytes",
        },
        code=code,
    )
    policy = {
        "batch_size": _positive_int(policy_raw["batch_size"], code=code),
        "max_input_units": _positive_int(policy_raw["max_input_units"], code=code),
        "timeout_seconds": _positive_number(policy_raw["timeout_seconds"], code=code),
        "max_retries": _positive_int(
            policy_raw["max_retries"], code=code, allow_zero=True
        ),
        "max_requests_per_operation": _positive_int(
            policy_raw["max_requests_per_operation"], code=code
        ),
        "max_cost_microunits_per_request": _positive_int(
            policy_raw["max_cost_microunits_per_request"],
            code=code,
            allow_zero=True,
        ),
        "total_cost_budget_microunits": _positive_int(
            policy_raw["total_cost_budget_microunits"], code=code, allow_zero=True
        ),
        "max_request_bytes": _positive_int(
            policy_raw["max_request_bytes"], code=code
        ),
        "max_response_bytes": _positive_int(
            policy_raw["max_response_bytes"], code=code
        ),
    }
    if (
        policy["max_retries"] + 1 > policy["max_requests_per_operation"]
        or policy["max_cost_microunits_per_request"]
        > policy["total_cost_budget_microunits"]
    ):
        raise ProviderRuntimeConfigError(code)
    wire_raw = _exact(
        item["wire"],
        {
            "schema_version",
            "request_schema_sha256",
            "response_schema_sha256",
            "body_template",
            "vectors_pointer",
            "values_pointer",
            "match_by",
            "id_pointer",
            "wire_contract_sha256",
        },
        code=code,
    )
    if wire_raw["schema_version"] != "kg-provider-embedding-wire-v1":
        raise ProviderRuntimeConfigError(code)
    try:
        from rag_store.provider_wire import EMBEDDING_ALLOWED_REFS, ProviderWire

        ProviderWire(
            wire_raw["body_template"], allowed_refs=EMBEDDING_ALLOWED_REFS
        )
    except Exception:
        raise ProviderRuntimeConfigError(code) from None
    match_by = wire_raw["match_by"]
    id_pointer = _json_pointer(wire_raw["id_pointer"], code=code, nullable=True)
    if match_by not in {"input_order", "response_id"} or (
        (match_by == "input_order" and id_pointer is not None)
        or (match_by == "response_id" and id_pointer is None)
    ):
        raise ProviderRuntimeConfigError(code)
    expected_wire_sha = _canonical_sha256(
        {key: value for key, value in wire_raw.items() if key != "wire_contract_sha256"}
    )
    declared_wire_sha = _sha256(wire_raw["wire_contract_sha256"], code=code)
    if declared_wire_sha != expected_wire_sha:
        raise ProviderRuntimeConfigError("embedding_wire_hash_mismatch")
    from rag_store.embedding_adapter import EmbeddingIdentity, EmbeddingPolicy
    from rag_store.runtime_query_embedding import (
        QueryEmbeddingIdentity,
        QueryEmbeddingPolicy,
    )

    build_identity = EmbeddingIdentity(**identity)
    query_identity = QueryEmbeddingIdentity(**identity)
    build_policy = EmbeddingPolicy(**policy)
    query_policy = QueryEmbeddingPolicy(**policy)
    declared_identity = _sha256(item["identity_sha256"], code=code)
    declared_policy = _sha256(item["policy_sha256"], code=code)
    if (
        build_identity.sha256 != query_identity.sha256
        or build_identity.sha256 != declared_identity
    ):
        raise ProviderRuntimeConfigError("embedding_identity_hash_mismatch")
    if build_policy.sha256 != query_policy.sha256 or build_policy.sha256 != declared_policy:
        raise ProviderRuntimeConfigError("embedding_policy_hash_mismatch")
    return EmbeddingConfig(
        approval_role_id=_text(item["approval_role_id"], code=code),
        identity=identity,
        identity_sha256=declared_identity,
        policy=policy,
        policy_sha256=declared_policy,
        secret_ref=_secret_ref(item["secret_ref"], code=code),
        auth=_parse_auth(item["auth"], code=code),
        meters=_parse_meters(item["meters"], code=code),
        wire=EmbeddingWireBinding(
            request_schema_sha256=_sha256(
                wire_raw["request_schema_sha256"], code=code
            ),
            response_schema_sha256=_sha256(
                wire_raw["response_schema_sha256"], code=code
            ),
            body_template=wire_raw["body_template"],
            vectors_pointer=_json_pointer(wire_raw["vectors_pointer"], code=code)
            or "",
            values_pointer=_json_pointer(wire_raw["values_pointer"], code=code)
            or "",
            match_by=match_by,
            id_pointer=id_pointer,
            wire_contract_sha256=declared_wire_sha,
        ),
    )


def resolve_secret(
    secret_ref: str,
    environment: Mapping[str, str] | None = None,
) -> ResolvedSecret:
    match = _SECRET_REF.fullmatch(secret_ref) if isinstance(secret_ref, str) else None
    if match is None:
        raise ProviderSecretError("provider_secret_ref_invalid")
    name = match.group(1)
    source = os.environ if environment is None else environment
    value = source.get(name)
    if (
        not isinstance(value, str)
        or not value
        or not value.strip()
        or len(value) > 4096
        or any(character in value for character in "\r\n\x00")
    ):
        raise ProviderSecretError("provider_secret_unavailable")
    return ResolvedSecret(name, value)


def authorization_header(auth: AuthBinding, secret: ResolvedSecret) -> tuple[str, str]:
    value = auth.prefix + secret.reveal()
    if not value or len(value) > 8192 or any(character in value for character in "\r\n\x00"):
        raise ProviderSecretError("provider_auth_header_invalid")
    return auth.header_name, value


def _load_bound_json(path: Path, expected_sha256: str, *, code: str) -> dict[str, Any]:
    try:
        _resolved, payload = _stable_regular_file_bytes(path, code=code)
    except ProviderRuntimeConfigError:
        raise ProviderApprovalError(code) from None
    if _sha256_bytes(payload) != expected_sha256:
        raise ProviderApprovalError(code)
    try:
        return _strict_json(payload, code=code)
    except ProviderRuntimeConfigError:
        raise ProviderApprovalError(code) from None


def _configured_role_contracts(
    config: ProviderRuntimeConfig,
) -> dict[str, dict[str, Any]]:
    answer = config.server_answer
    embedding = config.embedding
    if answer is None or embedding is None:
        raise ProviderApprovalError("provider_approval_missing")
    contracts: dict[str, dict[str, Any]] = {}
    for channel in answer.channels:
        role_id = channel.approval_role_id
        if role_id in contracts:
            raise ProviderApprovalError("provider_role_binding_invalid")
        runtime_contract = {
            "role_id": role_id,
            "role_kind": "server_answer",
            "provider": channel.provider,
            "endpoint": channel.endpoint,
            "region": channel.region,
            "model": channel.model,
            "model_version": channel.model_version,
            "api_version": channel.api_version,
            "provider_identity_sha256": channel.identity_sha256,
            "wire_contract_sha256": channel.wire.wire_contract_sha256,
            "request_schema_sha256": channel.wire.request_schema_sha256,
            "response_schema_sha256": channel.wire.response_schema_sha256,
            "limits": dict(channel.limits),
            "meters": {
                "input_meter_id": channel.meters.input_meter_id,
                "output_meter_id": channel.meters.output_meter_id,
                "cost_meter_id": channel.meters.cost_meter_id,
            },
            "coordination": {
                "strategy": answer.strategy,
                "winner_policy": answer.winner_policy,
                "total_budget_seconds": answer.total_budget_seconds,
                "total_cost_budget_microunits": (
                    answer.total_cost_budget_microunits
                ),
                "circuit_breaker_failure_threshold": (
                    answer.circuit_breaker_failure_threshold
                ),
                "circuit_breaker_cooldown_seconds": (
                    answer.circuit_breaker_cooldown_seconds
                ),
            },
        }
        contracts[role_id] = {
            **runtime_contract,
            "runtime_contract_sha256": _canonical_sha256(runtime_contract),
        }
    embedding_role_id = embedding.approval_role_id
    if embedding_role_id in contracts:
        raise ProviderApprovalError("provider_role_binding_invalid")
    embedding_runtime_contract = {
        "role_id": embedding_role_id,
        "role_kind": "embedding",
        "provider": embedding.identity["provider"],
        "endpoint": embedding.identity["base_url"],
        "region": embedding.identity["region"],
        "model": embedding.identity["model"],
        "model_version": embedding.identity["model_version"],
        "api_version": embedding.identity["api_version"],
        "provider_identity_sha256": embedding.identity_sha256,
        "identity": dict(embedding.identity),
        "policy": dict(embedding.policy),
        "policy_sha256": embedding.policy_sha256,
        "meters": {
            "input_meter_id": embedding.meters.input_meter_id,
            "output_meter_id": embedding.meters.output_meter_id,
            "cost_meter_id": embedding.meters.cost_meter_id,
        },
        "wire_contract_sha256": embedding.wire.wire_contract_sha256,
        "request_schema_sha256": embedding.wire.request_schema_sha256,
        "response_schema_sha256": embedding.wire.response_schema_sha256,
    }
    contracts[embedding_role_id] = {
        **embedding_runtime_contract,
        "runtime_contract_sha256": _canonical_sha256(
            embedding_runtime_contract
        ),
    }
    return contracts


def _approval_exact(value: Any, fields: set[str], *, code: str) -> dict[str, Any]:
    try:
        return _exact(value, fields, code=code)
    except ProviderRuntimeConfigError:
        raise ProviderApprovalError(code) from None


def _approval_text(value: Any, *, code: str, maximum: int = 512) -> str:
    try:
        return _text(value, code=code, maximum=maximum)
    except ProviderRuntimeConfigError:
        raise ProviderApprovalError(code) from None


def _approval_sha256(value: Any, *, code: str) -> str:
    try:
        return _sha256(value, code=code)
    except ProviderRuntimeConfigError:
        raise ProviderApprovalError(code) from None


def _approval_endpoint(value: Any, *, code: str) -> str:
    try:
        return _https_endpoint(value, code=code)
    except ProviderRuntimeConfigError:
        raise ProviderApprovalError(code) from None


def _milliseconds(value: float, *, code: str) -> int:
    milliseconds = value * 1000.0
    rounded = round(milliseconds)
    if not math.isclose(milliseconds, rounded, rel_tol=0.0, abs_tol=1e-9):
        raise ProviderApprovalError(code)
    return int(rounded)


def _utc_datetime(value: Any, *, code: str) -> datetime:
    parsed = _approval_text(value, code=code, maximum=20)
    if not _UTC_TIMESTAMP.fullmatch(parsed):
        raise ProviderApprovalError(code)
    try:
        return datetime.strptime(parsed, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        raise ProviderApprovalError(code) from None


def _validated_stop_b_request(value: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from deploy.cloud_v2.stop_b_request import (
            StopBRequestError,
            validate_stop_b_request,
        )

        return validate_stop_b_request(value, mode="approval_ready")
    except (ImportError, StopBRequestError):
        raise ProviderApprovalError("provider_stop_b_request_invalid") from None


def _validate_runtime_role_bindings(
    config: ProviderRuntimeConfig,
    request: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    code = "provider_role_binding_invalid"
    roles = {str(role["role_id"]): role for role in request["role_instances"]}
    configured = _configured_role_contracts(config)
    expected_ids = {
        role_id
        for role_id, role in roles.items()
        if role["role_kind"] in {"server_answer", "embedding"}
    }
    if set(configured) != expected_ids:
        raise ProviderApprovalError(code)

    for role_id, runtime in configured.items():
        role = roles[role_id]
        endpoint = role["endpoint_contract"]
        model = role["model_contract"]
        if (
            role["role_kind"] != runtime["role_kind"]
            or endpoint["exact_endpoint"] != runtime["endpoint"]
            or endpoint["region"] != runtime["region"]
            or endpoint["china_region_default_satisfied"] is not True
            or model["model_id"] != runtime["model"]
            or model["model_version"] != runtime["model_version"]
            or model["api_version"] != runtime["api_version"]
            or model["request_schema_sha256"]
            != runtime["request_schema_sha256"]
            or model["response_schema_sha256"]
            != runtime["response_schema_sha256"]
        ):
            raise ProviderApprovalError(code)
        limits = role["operational_limits"]
        commercial = role["commercial_contract"]
        if runtime["role_kind"] == "server_answer":
            configured_limits = runtime["limits"]
            if (
                limits["timeout_ms"]
                != _milliseconds(configured_limits["timeout_seconds"], code=code)
                or limits["max_retries"] != 0
                or limits["max_input_units"]
                != configured_limits["max_input_units"]
                or limits["max_output_units"]
                != configured_limits["max_output_units"]
                or limits["max_request_bytes"]
                != configured_limits["max_request_bytes"]
                or limits["max_response_bytes"]
                != configured_limits["max_response_bytes"]
                or commercial["budget_per_call_microunits"]
                != configured_limits["max_cost_microunits"]
            ):
                raise ProviderApprovalError(code)
        else:
            policy = runtime["policy"]
            if (
                limits["timeout_ms"]
                != _milliseconds(policy["timeout_seconds"], code=code)
                or limits["max_retries"] != policy["max_retries"]
                or limits["max_input_units"] != policy["max_input_units"]
                or limits["max_request_bytes"] != policy["max_request_bytes"]
                or limits["max_response_bytes"] != policy["max_response_bytes"]
                or commercial["budget_per_call_microunits"]
                != policy["max_cost_microunits_per_request"]
            ):
                raise ProviderApprovalError(code)

    answer = config.server_answer
    embedding = config.embedding
    if answer is None or embedding is None:
        raise ProviderApprovalError(code)
    coordinator = request["server_answer_coordinator"]
    ordered_ids = tuple(channel.approval_role_id for channel in answer.channels)
    if (
        tuple(coordinator["ordered_channel_role_ids"]) != ordered_ids
        or coordinator["selected_strategy"] != answer.strategy
        or coordinator["winner_policy"] != answer.winner_policy
        or coordinator["global_deadline_ms"]
        != _milliseconds(answer.total_budget_seconds, code=code)
        or coordinator["aggregate_limits"]["total_cost_budget_microunits"]
        != answer.total_cost_budget_microunits
        or coordinator["circuit_breaker"]["failure_threshold"]
        != answer.circuit_breaker_failure_threshold
        or coordinator["circuit_breaker"]["cooldown_seconds"]
        != answer.circuit_breaker_cooldown_seconds
    ):
        raise ProviderApprovalError(code)
    per_channel = coordinator["per_channel_limits"]
    for item, channel in zip(per_channel, answer.channels, strict=True):
        if (
            item["role_id"] != channel.approval_role_id
            or item["timeout_ms"]
            != _milliseconds(channel.limits["timeout_seconds"], code=code)
            or item["max_retries"] != 0
            or item["max_cost_microunits"]
            != channel.limits["max_cost_microunits"]
        ):
            raise ProviderApprovalError(code)

    vector = request["local_vector_contract"]["production"]["vector_identity"]
    if (
        vector["embedding_identity_sha256"] != embedding.identity_sha256
        or vector["dimension"] != embedding.identity["dimension"]
        or vector["normalization"] != embedding.identity["normalization"]
    ):
        raise ProviderApprovalError(code)
    return configured


def _expected_contract_materials(
    request: Mapping[str, Any],
) -> dict[tuple[str, str, str | None], str]:
    expected: dict[tuple[str, str, str | None], str] = {}
    for role in request["role_instances"]:
        role_id = str(role["role_id"])
        fixed = {
            "model_contract.request_schema_sha256": role["model_contract"][
                "request_schema_sha256"
            ],
            "model_contract.response_schema_sha256": role["model_contract"][
                "response_schema_sha256"
            ],
            "training_contract.evidence_sha256": role["training_contract"][
                "evidence_sha256"
            ],
            "retention_contract.evidence_sha256": role["retention_contract"][
                "evidence_sha256"
            ],
            "deletion_exit_contract.evidence_sha256": role[
                "deletion_exit_contract"
            ]["evidence_sha256"],
            "meter_contract.code_sha256": role["meter_contract"]["code_sha256"],
            "meter_contract.termination_evidence_sha256": role["meter_contract"][
                "termination_evidence_sha256"
            ],
            "commercial_contract.evidence_sha256": role["commercial_contract"][
                "evidence_sha256"
            ],
        }
        for field_name, sha256 in fixed.items():
            expected[(role_id, field_name, None)] = str(sha256)
        for evidence in role["evidence_refs"]:
            expected[(role_id, "evidence_refs.sha256", evidence["evidence_id"])] = str(
                evidence["sha256"]
            )
    return expected


def _validate_contract_materials(
    value: Mapping[str, Any],
    *,
    config: ProviderRuntimeConfig,
    request: Mapping[str, Any],
    request_sha256: str,
) -> None:
    code = "provider_contract_materials_invalid"
    manifest = _approval_exact(
        value,
        {
            "schema_version",
            "status",
            "provider_contract_sha256",
            "stop_b_request_sha256",
            "materials",
        },
        code=code,
    )
    if (
        manifest["schema_version"] != "kg-provider-contract-material-manifest-v1"
        or manifest["status"] != "bound-to-stop-b-request"
        or manifest["provider_contract_sha256"] != config.contract_sha256
        or manifest["stop_b_request_sha256"] != request_sha256
        or not isinstance(manifest["materials"], list)
    ):
        raise ProviderApprovalError(code)
    expected = _expected_contract_materials(request)
    observed: set[tuple[str, str, str | None]] = set()
    for raw in manifest["materials"]:
        item = _approval_exact(
            raw,
            {"role_id", "contract_field", "evidence_id", "path", "sha256"},
            code=code,
        )
        evidence_id = item["evidence_id"]
        if evidence_id is not None:
            evidence_id = _approval_text(evidence_id, code=code)
        key = (
            _approval_text(item["role_id"], code=code),
            _approval_text(item["contract_field"], code=code),
            evidence_id,
        )
        expected_sha256 = expected.get(key)
        declared_sha256 = _approval_sha256(item["sha256"], code=code)
        if key in observed or expected_sha256 != declared_sha256:
            raise ProviderApprovalError(code)
        try:
            _resolved, payload = _stable_regular_file_bytes(
                item["path"],
                code=code,
                maximum_bytes=MAX_CONTRACT_EVIDENCE_BYTES,
            )
        except ProviderRuntimeConfigError:
            raise ProviderApprovalError(code) from None
        if not payload or _sha256_bytes(payload) != declared_sha256:
            raise ProviderApprovalError(code)
        observed.add(key)
    if observed != set(expected):
        raise ProviderApprovalError(code)


def _validate_egress_policy(
    value: Mapping[str, Any],
    *,
    config: ProviderRuntimeConfig,
    request: Mapping[str, Any],
    request_sha256: str,
    configured: Mapping[str, Mapping[str, Any]],
) -> None:
    code = "provider_egress_policy_invalid"
    policy = _approval_exact(
        value,
        {
            "schema_version",
            "status",
            "provider_contract_sha256",
            "stop_b_request_sha256",
            "allowed_endpoints",
            "role_mappings",
        },
        code=code,
    )
    if (
        policy["schema_version"] != "kg-provider-egress-policy-v3"
        or policy["status"] != "approved"
        or policy["provider_contract_sha256"] != config.contract_sha256
        or policy["stop_b_request_sha256"] != request_sha256
        or not isinstance(policy["allowed_endpoints"], list)
        or not isinstance(policy["role_mappings"], list)
    ):
        raise ProviderApprovalError(code)
    roles = list(request["role_instances"])
    if len(policy["role_mappings"]) != len(roles):
        raise ProviderApprovalError(code)
    observed_endpoints: set[str] = set()
    for raw, role in zip(policy["role_mappings"], roles, strict=True):
        item = _approval_exact(
            raw,
            {
                "role_id",
                "role_kind",
                "ordinal",
                "purpose",
                "data_class_ids",
                "provider",
                "endpoint",
                "region",
                "model",
                "model_version",
                "api_version",
                "identity_sha256",
            },
            code=code,
        )
        endpoint = _approval_endpoint(item["endpoint"], code=code)
        identity_sha256 = _approval_sha256(item["identity_sha256"], code=code)
        role_id = _approval_text(item["role_id"], code=code)
        runtime = configured.get(role_id)
        if (
            role_id != role["role_id"]
            or item["role_kind"] != role["role_kind"]
            or type(item["ordinal"]) is not int
            or item["ordinal"] != role["ordinal"]
            or item["purpose"] != role["purpose"]
            or item["data_class_ids"] != role["allowed_data_class_ids"]
            or endpoint != role["endpoint_contract"]["exact_endpoint"]
            or item["region"] != role["endpoint_contract"]["region"]
            or item["model"] != role["model_contract"]["model_id"]
            or item["model_version"] != role["model_contract"]["model_version"]
            or item["api_version"] != role["model_contract"]["api_version"]
            or not _approval_text(item["provider"], code=code)
        ):
            raise ProviderApprovalError(code)
        if runtime is not None and (
            item["provider"] != runtime["provider"]
            or identity_sha256 != runtime["provider_identity_sha256"]
        ):
            raise ProviderApprovalError(code)
        observed_endpoints.add(endpoint)
    allowed_endpoints = [
        _approval_endpoint(item, code=code) for item in policy["allowed_endpoints"]
    ]
    if (
        len(allowed_endpoints) != len(set(allowed_endpoints))
        or set(allowed_endpoints) != observed_endpoints
    ):
        raise ProviderApprovalError(code)


def _validate_receipt(
    value: Mapping[str, Any],
    *,
    config: ProviderRuntimeConfig,
    request: Mapping[str, Any],
    binding: ApprovalBinding,
) -> None:
    code = "provider_approval_receipt_invalid"
    receipt = _approval_exact(
        value,
        {
            "schema_version",
            "status",
            "approval_id",
            "approved_by",
            "approved_at",
            "expires_at",
            "approval_scope",
            "regional_policy",
            "data_class_policy_version",
            "external_role_count",
            "provider_contract_sha256",
            "stop_b_request_sha256",
            "contract_materials_sha256",
            "egress_policy_sha256",
            "data_class_decisions",
        },
        code=code,
    )
    approval_id = _approval_text(receipt["approval_id"], code=code)
    approved_by = _approval_text(receipt["approved_by"], code=code)
    if any(
        marker in f"{approval_id} {approved_by}".lower()
        for marker in _APPROVAL_PLACEHOLDER_MARKERS
    ):
        raise ProviderApprovalError(code)
    now = datetime.now(timezone.utc)
    approved_at = _utc_datetime(receipt["approved_at"], code=code)
    expires_at = _utc_datetime(receipt["expires_at"], code=code)
    if (
        receipt["schema_version"] != "kg-stop-b-production-provider-approval-v3"
        or receipt["status"] != "stop_b_production_provider_approved"
        or approved_at > now
        or expires_at <= now
        or expires_at <= approved_at
        or receipt["approval_scope"] != "all_external_processing_roles"
        or receipt["regional_policy"] != "china_only"
        or receipt["data_class_policy_version"] != "kg-stop-b-data-classes-v1"
        or type(receipt["external_role_count"]) is not int
        or receipt["external_role_count"] != len(request["role_instances"])
        or receipt["provider_contract_sha256"] != config.contract_sha256
        or receipt["stop_b_request_sha256"] != binding.stop_b_request_sha256
        or receipt["contract_materials_sha256"]
        != binding.contract_materials_sha256
        or receipt["egress_policy_sha256"] != binding.egress_policy_sha256
        or not isinstance(receipt["data_class_decisions"], list)
    ):
        raise ProviderApprovalError(code)
    try:
        from deploy.cloud_v2.stop_b_request import DATA_CLASS_IDS
    except ImportError:
        raise ProviderApprovalError(code) from None
    decisions = receipt["data_class_decisions"]
    request_decisions = request["data_class_decisions"]
    if len(decisions) != len(DATA_CLASS_IDS):
        raise ProviderApprovalError(code)
    for class_id, raw, requested in zip(
        DATA_CLASS_IDS, decisions, request_decisions, strict=True
    ):
        item = _approval_exact(raw, {"data_class_id", "decision"}, code=code)
        expected = "approved" if requested["decision"] == "request_approval" else "denied"
        if item != {"data_class_id": class_id, "decision": expected}:
            raise ProviderApprovalError(code)
        if requested["decision"] == "request_approval":
            if _utc_datetime(requested["limits"]["expires_at"], code=code) <= now:
                raise ProviderApprovalError(code)


def validate_production_approval(
    config: ProviderRuntimeConfig,
    environment: Mapping[str, str] | None = None,
) -> None:
    binding = config.approval_binding
    answer = config.server_answer
    embedding = config.embedding
    if binding is None or answer is None or embedding is None:
        raise ProviderApprovalError("provider_approval_missing")
    source = os.environ if environment is None else environment
    trust_anchor = source.get(APPROVAL_TRUST_ANCHOR_ENVIRONMENT_VARIABLE)
    if (
        not isinstance(trust_anchor, str)
        or not _SHA256.fullmatch(trust_anchor)
        or trust_anchor != binding.receipt_sha256
    ):
        raise ProviderApprovalError("provider_approval_trust_anchor_invalid")
    receipt = _load_bound_json(
        binding.receipt_path,
        binding.receipt_sha256,
        code="provider_approval_receipt_invalid",
    )
    stop_b_request = _load_bound_json(
        binding.stop_b_request_path,
        binding.stop_b_request_sha256,
        code="provider_stop_b_request_invalid",
    )
    materials = _load_bound_json(
        binding.contract_materials_path,
        binding.contract_materials_sha256,
        code="provider_contract_materials_invalid",
    )
    egress = _load_bound_json(
        binding.egress_policy_path,
        binding.egress_policy_sha256,
        code="provider_egress_policy_invalid",
    )
    request = _validated_stop_b_request(stop_b_request)
    if request["region_policy"]["exception_decision"] is not None:
        raise ProviderApprovalError("provider_role_binding_invalid")
    configured = _validate_runtime_role_bindings(config, request)
    _validate_contract_materials(
        materials,
        config=config,
        request=request,
        request_sha256=binding.stop_b_request_sha256,
    )
    _validate_egress_policy(
        egress,
        config=config,
        request=request,
        request_sha256=binding.stop_b_request_sha256,
        configured=configured,
    )
    _validate_receipt(receipt, config=config, request=request, binding=binding)


def load_provider_config_from_environment(
    environment: Mapping[str, str] | None = None,
) -> ProviderRuntimeConfig:
    source = os.environ if environment is None else environment
    configured = source.get(CONFIG_ENVIRONMENT_VARIABLE, "")
    if not configured:
        raise ProviderRuntimeConfigError("provider_config_required")
    return ProviderRuntimeConfig.load(configured)


def require_https_network_mode(
    config: ProviderRuntimeConfig,
    environment: Mapping[str, str] | None = None,
) -> None:
    source = os.environ if environment is None else environment
    if source.get(NETWORK_MODE_ENVIRONMENT_VARIABLE) != "https":
        raise ProviderBootstrapError("provider_network_disabled")
    if config.network_mode != "https":
        raise ProviderBootstrapError("provider_network_disabled")


@dataclass(frozen=True)
class ProviderRuntimeBindings:
    provider_config_sha256: str
    provider_contract_sha256: str
    answer_channel_count: int
    answer_strategy: str
    embedding_identity_sha256: str
    embedding_policy_sha256: str


TransportExecutorFactory = Callable[[str, str], Callable[..., Any] | None]
ApprovalValidator = Callable[[ProviderRuntimeConfig], None]


def _answer_channel(config: AnswerChannelConfig) -> Any:
    from rag_store.server_answer_model import ServerAnswerChannel

    return ServerAnswerChannel(
        channel_id=config.channel_id,
        provider=config.provider,
        base_url=config.endpoint,
        region=config.region,
        model=config.model,
        model_version=config.model_version,
        api_version=config.api_version,
        **dict(config.limits),
    )


def _executor(
    factory: TransportExecutorFactory | None,
    role: str,
    role_id: str,
) -> Callable[..., Any] | None:
    if factory is None:
        return None
    if not callable(factory):
        raise ProviderBootstrapError("provider_executor_factory_invalid")
    value = factory(role, role_id)
    if value is not None and not callable(value):
        raise ProviderBootstrapError("provider_executor_factory_invalid")
    return value


def _assert_runtime_binding(runtime: Any, config: ProviderRuntimeConfig) -> None:
    expected_hash = runtime.config.provider_runtime_config_sha256
    if config.sha256 != expected_hash:
        raise ProviderBootstrapError("provider_config_hash_mismatch")
    answer = config.server_answer
    embedding = config.embedding
    if answer is None or embedding is None:
        raise ProviderBootstrapError("provider_config_incomplete")
    expected_answer = runtime.config.server_answer
    actual_channels = tuple(
        (item.channel_id, item.identity_sha256) for item in answer.channels
    )
    expected_channels = tuple(
        (item.channel_id, item.identity_sha256)
        for item in expected_answer.ordered_channels
    )
    actual_policy = (
        answer.strategy,
        answer.winner_policy,
        float(answer.total_budget_seconds),
        answer.total_cost_budget_microunits,
        answer.circuit_breaker_failure_threshold,
        float(answer.circuit_breaker_cooldown_seconds),
    )
    expected_policy = (
        expected_answer.strategy,
        expected_answer.winner_policy,
        float(expected_answer.total_budget_seconds),
        expected_answer.total_cost_budget_microunits,
        expected_answer.circuit_breaker_failure_threshold,
        float(expected_answer.circuit_breaker_cooldown_seconds),
    )
    if actual_channels != expected_channels or actual_policy != expected_policy:
        raise ProviderBootstrapError("provider_answer_binding_mismatch")
    if (
        embedding.identity_sha256 != runtime.config.embedding_identity_sha256
        or embedding.policy_sha256 != runtime.config.embedding_policy_sha256
        or int(embedding.identity["dimension"])
        != int(runtime.config.local_vector["dimension"])
    ):
        raise ProviderBootstrapError("provider_embedding_binding_mismatch")


def bootstrap_provider_runtime(
    runtime: Any,
    provider_config: ProviderRuntimeConfig,
    *,
    environment: Mapping[str, str] | None = None,
    approval_validator: ApprovalValidator = validate_production_approval,
    executor_factory: TransportExecutorFactory | None = None,
) -> ProviderRuntimeBindings:
    """Build and bind all provider adapters before the public listener starts."""

    source = os.environ if environment is None else environment
    require_https_network_mode(provider_config, source)
    _assert_runtime_binding(runtime, provider_config)
    if not callable(approval_validator):
        raise ProviderBootstrapError("provider_approval_validator_invalid")
    try:
        if approval_validator is validate_production_approval:
            validate_production_approval(provider_config, source)
        else:
            approval_validator(provider_config)
    except ProviderBootstrapError:
        raise
    except Exception:
        raise ProviderApprovalError("provider_approval_validation_failed") from None

    answer = provider_config.server_answer
    embedding = provider_config.embedding
    if answer is None or embedding is None:
        raise ProviderBootstrapError("provider_config_incomplete")

    # Resolve every required secret before constructing any callable transport.
    answer_secrets = tuple(
        resolve_secret(channel.secret_ref, source) for channel in answer.channels
    )
    embedding_secret = resolve_secret(embedding.secret_ref, source)
    try:
        from rag_store.provider_http_transport import ProviderHTTPTransport
        from rag_store.provider_meters import resolve_meter
        from rag_store.runtime_query_embedding import (
            QueryEmbeddingClient,
            QueryEmbeddingIdentity,
            QueryEmbeddingPolicy,
        )
        from rag_store.server_answer_coordinator import (
            CoordinatorPolicy,
            ServerAnswerCoordinator,
        )
        from rag_store.server_answer_model import ServerAnswerModelAdapter

        adapters = []
        for channel_config, secret in zip(
            answer.channels, answer_secrets, strict=True
        ):
            channel = _answer_channel(channel_config)
            header_name, header_value = authorization_header(
                channel_config.auth, secret
            )
            transport = ProviderHTTPTransport(
                endpoint=channel_config.endpoint,
                request_template=channel_config.wire.body_template,
                response_kind="server_answer",
                response_mapping={
                    "answer_pointer": channel_config.wire.answer_pointer
                },
                input_meter_id=channel_config.meters.input_meter_id,
                output_meter_id=channel_config.meters.output_meter_id,
                cost_meter_id=channel_config.meters.cost_meter_id,
                maximum_cost_microunits=channel.max_cost_microunits,
                secret_headers={header_name: header_value},
                max_request_bytes=channel.max_request_bytes,
                max_response_bytes=channel.max_response_bytes,
                executor=_executor(
                    executor_factory, "server_answer", channel.channel_id
                ),
            )
            adapters.append(
                ServerAnswerModelAdapter(
                    channel,
                    transport=transport,
                    transport_mode="external_process",
                    input_unit_meter=resolve_meter(
                        channel_config.meters.input_meter_id
                    ),
                    output_unit_meter=resolve_meter(
                        channel_config.meters.output_meter_id
                    ),
                    cost_meter=resolve_meter(channel_config.meters.cost_meter_id),
                )
            )
        coordinator = ServerAnswerCoordinator(
            tuple(adapters),
            policy=CoordinatorPolicy(
                strategy=answer.strategy,
                ordered_channel_ids=tuple(
                    channel.channel_id for channel in answer.channels
                ),
                winner_policy=answer.winner_policy,
                total_budget_seconds=answer.total_budget_seconds,
                total_cost_budget_microunits=answer.total_cost_budget_microunits,
                circuit_breaker_failure_threshold=answer.circuit_breaker_failure_threshold,
                circuit_breaker_cooldown_seconds=answer.circuit_breaker_cooldown_seconds,
            ),
        )
        query_identity = QueryEmbeddingIdentity(**dict(embedding.identity))
        query_policy = QueryEmbeddingPolicy(**dict(embedding.policy))
        embedding_header_name, embedding_header_value = authorization_header(
            embedding.auth, embedding_secret
        )
        embedding_mapping: dict[str, Any] = {
            "vectors_pointer": embedding.wire.vectors_pointer,
            "values_pointer": embedding.wire.values_pointer,
            "match_by": embedding.wire.match_by,
        }
        if embedding.wire.id_pointer is not None:
            embedding_mapping["id_pointer"] = embedding.wire.id_pointer
        embedding_transport = ProviderHTTPTransport(
            endpoint=str(embedding.identity["base_url"]),
            request_template=embedding.wire.body_template,
            response_kind="embedding",
            response_mapping=embedding_mapping,
            input_meter_id=embedding.meters.input_meter_id,
            output_meter_id=embedding.meters.output_meter_id,
            cost_meter_id=embedding.meters.cost_meter_id,
            maximum_cost_microunits=query_policy.max_cost_microunits_per_request,
            secret_headers={embedding_header_name: embedding_header_value},
            max_request_bytes=query_policy.max_request_bytes,
            max_response_bytes=query_policy.max_response_bytes,
            executor=_executor(executor_factory, "embedding", "embedding"),
        )
        query_client = QueryEmbeddingClient(
            query_identity,
            policy=query_policy,
            transport=embedding_transport,
            transport_mode="external_process",
            input_unit_meter=resolve_meter(embedding.meters.input_meter_id),
        )
        runtime.bind_provider_adapters(
            embedding_adapter=query_client,
            answer_coordinator=coordinator,
        )
    except ProviderBootstrapError:
        raise
    except Exception:
        raise ProviderBootstrapError("provider_binding_failed") from None
    return ProviderRuntimeBindings(
        provider_config_sha256=provider_config.sha256,
        provider_contract_sha256=provider_config.contract_sha256,
        answer_channel_count=len(answer.channels),
        answer_strategy=answer.strategy,
        embedding_identity_sha256=embedding.identity_sha256,
        embedding_policy_sha256=embedding.policy_sha256,
    )


def load_provider_bound_runtime_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    approval_validator: ApprovalValidator = validate_production_approval,
    executor_factory: TransportExecutorFactory | None = None,
) -> Any:
    """Open active data and return only after provider dependencies are bound."""

    source = os.environ if environment is None else environment
    if source.get(NETWORK_MODE_ENVIRONMENT_VARIABLE) != "https":
        raise ProviderBootstrapError("provider_network_disabled")
    provider_config = load_provider_config_from_environment(source)
    require_https_network_mode(provider_config, source)
    from pipeline.cloud_runtime import (
        CONFIG_ENVIRONMENT_VARIABLE as CLOUD_CONFIG_ENVIRONMENT_VARIABLE,
        CONFIG_SHA256_ENVIRONMENT_VARIABLE as CLOUD_CONFIG_SHA256_ENVIRONMENT_VARIABLE,
        CloudRuntimeConfigError,
        CloudRuntimeResources,
    )

    cloud_config_path = source.get(CLOUD_CONFIG_ENVIRONMENT_VARIABLE, "")
    if not cloud_config_path:
        raise CloudRuntimeConfigError(
            f"{CLOUD_CONFIG_ENVIRONMENT_VARIABLE} must identify the explicit active runtime config"
        )
    cloud_config_sha256 = source.get(CLOUD_CONFIG_SHA256_ENVIRONMENT_VARIABLE, "")
    if not cloud_config_sha256:
        raise CloudRuntimeConfigError(
            f"{CLOUD_CONFIG_SHA256_ENVIRONMENT_VARIABLE} must identify the approved runtime config hash"
        )
    runtime = CloudRuntimeResources.open(
        cloud_config_path,
        expected_config_sha256=cloud_config_sha256,
        environment=source,
    )
    try:
        bootstrap_provider_runtime(
            runtime,
            provider_config,
            environment=source,
            approval_validator=approval_validator,
            executor_factory=executor_factory,
        )
        return runtime
    except BaseException:
        runtime.close()
        raise


__all__ = [
    "ApprovalBinding",
    "AnswerChannelConfig",
    "AnswerWireBinding",
    "AuthBinding",
    "CONFIG_ENVIRONMENT_VARIABLE",
    "CONFIG_SCHEMA_VERSION",
    "EmbeddingConfig",
    "EmbeddingWireBinding",
    "MeterBinding",
    "NETWORK_MODE_ENVIRONMENT_VARIABLE",
    "ProviderApprovalError",
    "ProviderBootstrapError",
    "ProviderRuntimeConfig",
    "ProviderRuntimeBindings",
    "ProviderRuntimeConfigError",
    "ProviderSecretError",
    "ResolvedSecret",
    "ServerAnswerConfig",
    "authorization_header",
    "bootstrap_provider_runtime",
    "load_provider_config_from_environment",
    "load_provider_bound_runtime_from_environment",
    "require_https_network_mode",
    "resolve_secret",
    "validate_production_approval",
]
