#!/usr/bin/env python3
"""Hash-bound HTTPS answer provider plus loopback Ollama embedding bootstrap."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "deploy") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "deploy"))

from pipeline.cloud_runtime import (
    CONFIG_ENVIRONMENT_VARIABLE as CLOUD_CONFIG_ENVIRONMENT_VARIABLE,
    CONFIG_SHA256_ENVIRONMENT_VARIABLE as CLOUD_CONFIG_SHA256_ENVIRONMENT_VARIABLE,
    CloudRuntimeResources,
)
from pipeline.provider_bootstrap import (
    ApprovalBinding,
    ProviderApprovalError,
    ProviderBootstrapError,
    ProviderRuntimeConfigError,
    ServerAnswerConfig,
    _canonical_sha256,
    _exact,
    _parse_approval,
    _parse_server_answer,
    _sha256,
    _stable_regular_file_bytes,
    _strict_json,
    authorization_header,
    resolve_secret,
)
from rag_store.ollama_embedding import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_DIMENSION,
    DEFAULT_OLLAMA_MODEL,
    OllamaEmbeddingTransport,
    OllamaModelInfo,
    inspect_ollama_model,
    ollama_embedding_identities,
)
from rag_store.provider_http_transport import ProviderHTTPTransport
from rag_store.provider_meters import resolve_meter
from rag_store.runtime_query_embedding import QueryEmbeddingClient, QueryEmbeddingPolicy
from rag_store.server_answer_coordinator import CoordinatorPolicy, ServerAnswerCoordinator
from rag_store.server_answer_model import ServerAnswerChannel, ServerAnswerModelAdapter


CONFIG_ENVIRONMENT_VARIABLE = "KG_MIXED_PROVIDER_RUNTIME_CONFIG"
CONFIG_SHA256_ENVIRONMENT_VARIABLE = "KG_MIXED_PROVIDER_RUNTIME_CONFIG_SHA256"
NETWORK_MODE_ENVIRONMENT_VARIABLE = "KG_MIXED_PROVIDER_NETWORK_MODE"
APPROVAL_TRUST_ANCHOR_ENVIRONMENT_VARIABLE = "KG_MIXED_STOP_B_APPROVAL_SHA256"
CONFIG_SCHEMA_VERSION = "kg-mixed-provider-runtime-config-v1"
NETWORK_MODE = "https-answer-loopback-embedding"
REQUEST_SCHEMA_VERSION = "kg-mixed-stop-b-request-v1"
RECEIPT_SCHEMA_VERSION = "kg-mixed-stop-b-approval-v1"
MATERIALS_SCHEMA_VERSION = "kg-mixed-provider-contract-materials-v1"
EGRESS_SCHEMA_VERSION = "kg-mixed-provider-egress-policy-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LocalEmbeddingConfig:
    model_digest: str
    identity_sha256: str
    policy: Mapping[str, Any]
    policy_sha256: str


@dataclass(frozen=True)
class MixedProviderRuntimeConfig:
    path: Path
    sha256: str
    contract_sha256: str
    approval_binding: ApprovalBinding
    server_answer: ServerAnswerConfig
    embedding: LocalEmbeddingConfig

    @classmethod
    def load(
        cls, path: str | Path, *, expected_sha256: str
    ) -> "MixedProviderRuntimeConfig":
        expected = _sha256(expected_sha256, code="mixed_provider_config_hash_invalid")
        resolved, payload = _stable_regular_file_bytes(
            path, code="mixed_provider_config_unavailable"
        )
        actual = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(actual, expected):
            raise ProviderRuntimeConfigError("mixed_provider_config_hash_mismatch")
        root = _exact(
            _strict_json(payload, code="mixed_provider_config_invalid_json"),
            {
                "schema_version",
                "network_mode",
                "approval_binding",
                "server_answer",
                "embedding",
            },
            code="mixed_provider_config_invalid",
        )
        if root["schema_version"] != CONFIG_SCHEMA_VERSION or root["network_mode"] != NETWORK_MODE:
            raise ProviderRuntimeConfigError("mixed_provider_config_invalid")
        answer = _parse_server_answer(root["server_answer"])
        if len(answer.channels) != 1:
            raise ProviderRuntimeConfigError("mixed_provider_answer_channel_count_invalid")
        embedding_raw = _exact(
            root["embedding"],
            {
                "provider",
                "base_url",
                "model",
                "model_digest",
                "dimension",
                "identity_sha256",
                "policy",
                "policy_sha256",
            },
            code="mixed_provider_embedding_invalid",
        )
        if (
            embedding_raw["provider"] != "ollama-local"
            or embedding_raw["base_url"] != DEFAULT_OLLAMA_BASE_URL
            or embedding_raw["model"] != DEFAULT_OLLAMA_MODEL
            or embedding_raw["dimension"] != DEFAULT_OLLAMA_DIMENSION
        ):
            raise ProviderRuntimeConfigError("mixed_provider_embedding_invalid")
        digest = _sha256(
            embedding_raw["model_digest"], code="mixed_provider_embedding_invalid"
        )
        identity_sha = _sha256(
            embedding_raw["identity_sha256"], code="mixed_provider_embedding_invalid"
        )
        info = OllamaModelInfo(DEFAULT_OLLAMA_MODEL, digest, DEFAULT_OLLAMA_DIMENSION)
        _build_identity, query_identity = ollama_embedding_identities(info)
        if query_identity.sha256 != identity_sha:
            raise ProviderRuntimeConfigError("mixed_provider_embedding_identity_mismatch")
        policy_raw = _exact(
            embedding_raw["policy"],
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
            code="mixed_provider_embedding_policy_invalid",
        )
        try:
            policy = QueryEmbeddingPolicy(**policy_raw)
        except (TypeError, ValueError):
            raise ProviderRuntimeConfigError(
                "mixed_provider_embedding_policy_invalid"
            ) from None
        policy_sha = _sha256(
            embedding_raw["policy_sha256"],
            code="mixed_provider_embedding_policy_invalid",
        )
        if policy.sha256 != policy_sha:
            raise ProviderRuntimeConfigError("mixed_provider_embedding_policy_mismatch")
        contract_sha = _canonical_sha256(
            {"server_answer": root["server_answer"], "embedding": root["embedding"]}
        )
        return cls(
            resolved,
            actual,
            contract_sha,
            _parse_approval(root["approval_binding"]),
            answer,
            LocalEmbeddingConfig(digest, identity_sha, dict(policy_raw), policy_sha),
        )


def _load_bound_json(path: Path, expected_sha256: str, code: str) -> dict[str, Any]:
    resolved, payload = _stable_regular_file_bytes(path, code=code)
    del resolved
    if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected_sha256):
        raise ProviderApprovalError(code)
    try:
        return _strict_json(payload, code=code)
    except ProviderRuntimeConfigError:
        raise ProviderApprovalError(code) from None


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProviderApprovalError(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        raise ProviderApprovalError(code) from None
    return parsed


def validate_mixed_production_approval(
    config: MixedProviderRuntimeConfig,
    environment: Mapping[str, str] | None = None,
) -> None:
    source = os.environ if environment is None else environment
    binding = config.approval_binding
    anchor = source.get(APPROVAL_TRUST_ANCHOR_ENVIRONMENT_VARIABLE, "")
    if not isinstance(anchor, str) or not hmac.compare_digest(anchor, binding.receipt_sha256):
        raise ProviderApprovalError("mixed_provider_approval_trust_anchor_invalid")
    request = _exact(
        _load_bound_json(binding.stop_b_request_path, binding.stop_b_request_sha256, "mixed_stop_b_request_invalid"),
        {"schema_version", "status", "request_id", "approved_by", "regional_policy", "data_classes", "role"},
        code="mixed_stop_b_request_invalid",
    )
    channel = config.server_answer.channels[0]
    expected_role = {
        "role_id": channel.approval_role_id,
        "role_kind": "server_answer",
        "provider": channel.provider,
        "endpoint": channel.endpoint,
        "model": channel.model,
        "identity_sha256": channel.identity_sha256,
    }
    if (
        request["schema_version"] != REQUEST_SCHEMA_VERSION
        or request["status"] != "stop_b_user_approved"
        or request["approved_by"] != "云技"
        or request["regional_policy"] != "china_only"
        or request["data_classes"] != ["user_query", "selected_knowledge_evidence"]
        or request["role"] != expected_role
    ):
        raise ProviderApprovalError("mixed_stop_b_request_invalid")
    materials = _exact(
        _load_bound_json(binding.contract_materials_path, binding.contract_materials_sha256, "mixed_provider_contract_materials_invalid"),
        {"schema_version", "stop_b_request_sha256", "provider_contract_sha256", "role"},
        code="mixed_provider_contract_materials_invalid",
    )
    expected_material_role = {
        **expected_role,
        "wire_contract_sha256": channel.wire.wire_contract_sha256,
        "request_schema_sha256": channel.wire.request_schema_sha256,
        "response_schema_sha256": channel.wire.response_schema_sha256,
    }
    if materials != {
        "schema_version": MATERIALS_SCHEMA_VERSION,
        "stop_b_request_sha256": binding.stop_b_request_sha256,
        "provider_contract_sha256": config.contract_sha256,
        "role": expected_material_role,
    }:
        raise ProviderApprovalError("mixed_provider_contract_materials_invalid")
    egress = _exact(
        _load_bound_json(binding.egress_policy_path, binding.egress_policy_sha256, "mixed_provider_egress_policy_invalid"),
        {"schema_version", "stop_b_request_sha256", "provider_contract_sha256", "allowed_endpoints", "role"},
        code="mixed_provider_egress_policy_invalid",
    )
    if egress != {
        "schema_version": EGRESS_SCHEMA_VERSION,
        "stop_b_request_sha256": binding.stop_b_request_sha256,
        "provider_contract_sha256": config.contract_sha256,
        "allowed_endpoints": [channel.endpoint],
        "role": expected_role,
    }:
        raise ProviderApprovalError("mixed_provider_egress_policy_invalid")
    receipt = _exact(
        _load_bound_json(binding.receipt_path, binding.receipt_sha256, "mixed_provider_approval_receipt_invalid"),
        {"schema_version", "status", "approval_id", "approved_by", "approved_at", "expires_at", "approval_scope", "stop_b_request_sha256", "contract_materials_sha256", "egress_policy_sha256", "provider_contract_sha256"},
        code="mixed_provider_approval_receipt_invalid",
    )
    now = datetime.now(timezone.utc)
    if (
        receipt["schema_version"] != RECEIPT_SCHEMA_VERSION
        or receipt["status"] != "stop_b_production_provider_approved"
        or receipt["approved_by"] != "云技"
        or receipt["approval_scope"] != "one_https_server_answer_role"
        or receipt["stop_b_request_sha256"] != binding.stop_b_request_sha256
        or receipt["contract_materials_sha256"] != binding.contract_materials_sha256
        or receipt["egress_policy_sha256"] != binding.egress_policy_sha256
        or receipt["provider_contract_sha256"] != config.contract_sha256
        or _timestamp(receipt["approved_at"], "mixed_provider_approval_receipt_invalid") > now
        or _timestamp(receipt["expires_at"], "mixed_provider_approval_receipt_invalid") <= now
    ):
        raise ProviderApprovalError("mixed_provider_approval_receipt_invalid")


def _answer_coordinator(config: MixedProviderRuntimeConfig, environment: Mapping[str, str]):
    answer = config.server_answer
    configured = answer.channels[0]
    secret = resolve_secret(configured.secret_ref, environment)
    channel = ServerAnswerChannel(
        channel_id=configured.channel_id,
        provider=configured.provider,
        base_url=configured.endpoint,
        region=configured.region,
        model=configured.model,
        model_version=configured.model_version,
        api_version=configured.api_version,
        **dict(configured.limits),
    )
    header_name, header_value = authorization_header(configured.auth, secret)
    transport = ProviderHTTPTransport(
        endpoint=configured.endpoint,
        request_template=configured.wire.body_template,
        response_kind="server_answer",
        response_mapping={"answer_pointer": configured.wire.answer_pointer},
        input_meter_id=configured.meters.input_meter_id,
        output_meter_id=configured.meters.output_meter_id,
        cost_meter_id=configured.meters.cost_meter_id,
        maximum_cost_microunits=channel.max_cost_microunits,
        secret_headers={header_name: header_value},
        max_request_bytes=channel.max_request_bytes,
        max_response_bytes=channel.max_response_bytes,
    )
    adapter = ServerAnswerModelAdapter(
        channel,
        transport=transport,
        transport_mode="external_process",
        input_unit_meter=resolve_meter(configured.meters.input_meter_id),
        output_unit_meter=resolve_meter(configured.meters.output_meter_id),
        cost_meter=resolve_meter(configured.meters.cost_meter_id),
    )
    return ServerAnswerCoordinator(
        (adapter,),
        policy=CoordinatorPolicy(
            strategy=answer.strategy,
            ordered_channel_ids=(channel.channel_id,),
            winner_policy=answer.winner_policy,
            total_budget_seconds=answer.total_budget_seconds,
            total_cost_budget_microunits=answer.total_cost_budget_microunits,
            circuit_breaker_failure_threshold=answer.circuit_breaker_failure_threshold,
            circuit_breaker_cooldown_seconds=answer.circuit_breaker_cooldown_seconds,
        ),
    )


def load_mixed_provider_bound_runtime_from_environment(
    environment: Mapping[str, str] | None = None,
) -> CloudRuntimeResources:
    source = os.environ if environment is None else environment
    if source.get(NETWORK_MODE_ENVIRONMENT_VARIABLE) != NETWORK_MODE:
        raise ProviderBootstrapError("mixed_provider_network_mode_invalid")
    config_path = source.get(CONFIG_ENVIRONMENT_VARIABLE, "")
    config_sha = source.get(CONFIG_SHA256_ENVIRONMENT_VARIABLE, "")
    if not config_path or not config_sha:
        raise ProviderRuntimeConfigError("mixed_provider_config_required")
    config = MixedProviderRuntimeConfig.load(config_path, expected_sha256=config_sha)
    validate_mixed_production_approval(config, source)
    cloud_path = source.get(CLOUD_CONFIG_ENVIRONMENT_VARIABLE, "")
    cloud_sha = source.get(CLOUD_CONFIG_SHA256_ENVIRONMENT_VARIABLE, "")
    if not cloud_path or not cloud_sha:
        raise ProviderRuntimeConfigError("cloud_runtime_config_required")
    runtime = CloudRuntimeResources.open(
        cloud_path, expected_config_sha256=cloud_sha, environment=source
    )
    try:
        if runtime.config.provider_runtime_config_sha256 != config.sha256:
            raise ProviderBootstrapError("mixed_provider_config_binding_mismatch")
        observed = inspect_ollama_model()
        if (
            observed.model != DEFAULT_OLLAMA_MODEL
            or observed.digest != config.embedding.model_digest
            or observed.dimension != DEFAULT_OLLAMA_DIMENSION
        ):
            raise ProviderBootstrapError("mixed_provider_ollama_identity_mismatch")
        _build_identity, query_identity = ollama_embedding_identities(observed)
        policy = QueryEmbeddingPolicy(**dict(config.embedding.policy))
        query_client = QueryEmbeddingClient(
            query_identity,
            policy=policy,
            transport=OllamaEmbeddingTransport(),
            transport_mode="external_process",
            input_unit_meter=len,
        )
        runtime.bind_provider_adapters(
            embedding_adapter=query_client,
            answer_coordinator=_answer_coordinator(config, source),
        )
        return runtime
    except BaseException:
        runtime.close()
        raise


__all__ = [
    "APPROVAL_TRUST_ANCHOR_ENVIRONMENT_VARIABLE",
    "CONFIG_ENVIRONMENT_VARIABLE",
    "CONFIG_SCHEMA_VERSION",
    "CONFIG_SHA256_ENVIRONMENT_VARIABLE",
    "MixedProviderRuntimeConfig",
    "NETWORK_MODE",
    "NETWORK_MODE_ENVIRONMENT_VARIABLE",
    "load_mixed_provider_bound_runtime_from_environment",
    "validate_mixed_production_approval",
]
