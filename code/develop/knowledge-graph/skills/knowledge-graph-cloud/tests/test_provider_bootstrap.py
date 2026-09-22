#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from pipeline.provider_bootstrap import (
    ProviderApprovalError,
    ProviderBootstrapError,
    ProviderRuntimeConfig,
    bootstrap_provider_runtime,
)
from rag_store.embedding_adapter import EmbeddingIdentity, EmbeddingPolicy
from rag_store.runtime_query_embedding import QueryEmbeddingInput
from rag_store.server_answer_model import ServerAnswerChannel, ServerAnswerRequest


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class AnswerExecutor:
    def __init__(self, answer: str, fail: bool = False) -> None:
        self.answer = answer
        self.fail = fail

    def __call__(self, **_request):
        if self.fail:
            raise RuntimeError("provider diagnostic must be sanitized")
        return (
            200,
            {"Content-Type": "application/json"},
            canonical_bytes({"result": {"text": self.answer}}),
        )


class EmbeddingExecutor:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def __call__(self, **request):
        body = json.loads(request["body"])
        vectors = []
        for index, _item in enumerate(body["inputs"]):
            values = [0.0] * self.dimension
            values[index % self.dimension] = 1.0
            vectors.append({"embedding": values})
        return (
            200,
            {"Content-Type": "application/json"},
            canonical_bytes({"data": vectors}),
        )


class ExecutorFactory:
    def __init__(self, failed_answer_ids: tuple[str, ...] = ()) -> None:
        self.failed_answer_ids = frozenset(failed_answer_ids)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, role: str, role_id: str):
        self.calls.append((role, role_id))
        if role == "embedding":
            return EmbeddingExecutor(4)
        return AnswerExecutor(
            f"answer-{role_id}", fail=role_id in self.failed_answer_ids
        )


class FakeRuntime:
    def __init__(self, config: object) -> None:
        self.config = config
        self.embedding_adapter = None
        self.answer_coordinator = None

    def bind_provider_adapters(self, *, embedding_adapter, answer_coordinator):
        if self.embedding_adapter is not None or self.answer_coordinator is not None:
            raise RuntimeError("already bound")
        self.embedding_adapter = embedding_adapter
        self.answer_coordinator = answer_coordinator


class ProviderBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="kg-provider-bootstrap-test-")
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)

    def _config(self, strategy: str, count: int) -> dict[str, object]:
        channels = []
        channel_objects = []
        answer_wire = {
            "schema_version": "kg-provider-answer-wire-v1",
            "request_schema_sha256": "1" * 64,
            "response_schema_sha256": "2" * 64,
            "body_template": {
                "model": {"$ref": "identity.model"},
                "question": {"$ref": "request.question"},
                "evidence": {"$ref": "request.evidence"},
            },
            "answer_pointer": "/result/text",
        }
        answer_wire["wire_contract_sha256"] = canonical_sha256(answer_wire)
        meters = {
            "input_meter_id": "unicode_codepoints-v1",
            "output_meter_id": "unicode_codepoints-v1",
            "cost_meter_id": "maximum_request_exposure-v1",
        }
        auth = {"header_name": "Authorization", "prefix": "Bearer "}
        for index in range(1, count + 1):
            channel = ServerAnswerChannel(
                channel_id=f"channel-{index}",
                provider=f"provider-neutral-fixture-{index}",
                base_url=f"https://answer-{index}.invalid/v1/generate",
                region="synthetic-region",
                model=f"model-{index}",
                model_version=f"model-{index}-v1",
                api_version="api-v1",
                timeout_seconds=2.0,
                max_input_units=4096,
                max_output_units=1024,
                max_cost_microunits=10,
                max_request_bytes=65536,
                max_response_bytes=65536,
            )
            channel_objects.append(channel)
            channels.append(
                {
                    "channel_id": channel.channel_id,
                    "approval_role_id": f"server_answer:{channel.channel_id}",
                    "provider": channel.provider,
                    "endpoint": channel.base_url,
                    "region": channel.region,
                    "model": channel.model,
                    "model_version": channel.model_version,
                    "api_version": channel.api_version,
                    "identity_sha256": channel.identity_sha256,
                    "secret_ref": f"secretref:KG_CHANNEL_{index}_KEY",
                    "auth": auth,
                    "limits": {
                        "timeout_seconds": channel.timeout_seconds,
                        "max_input_units": channel.max_input_units,
                        "max_output_units": channel.max_output_units,
                        "max_cost_microunits": channel.max_cost_microunits,
                        "max_request_bytes": channel.max_request_bytes,
                        "max_response_bytes": channel.max_response_bytes,
                    },
                    "meters": meters,
                    "wire": answer_wire,
                }
            )
        identity = EmbeddingIdentity(
            provider="provider-neutral-embedding-fixture",
            base_url="https://embedding.invalid/v1/embed",
            region="synthetic-region",
            model="embedding-model",
            model_version="embedding-model-v1",
            api_version="api-v1",
            dimension=4,
            normalization="l2",
            input_type="document-or-query-text-v1",
        )
        policy = EmbeddingPolicy(
            batch_size=16,
            max_input_units=4096,
            timeout_seconds=2.0,
            max_retries=0,
            max_requests_per_operation=100,
            max_cost_microunits_per_request=5,
            total_cost_budget_microunits=500,
            max_request_bytes=65536,
            max_response_bytes=65536,
        )
        embedding_wire = {
            "schema_version": "kg-provider-embedding-wire-v1",
            "request_schema_sha256": "3" * 64,
            "response_schema_sha256": "4" * 64,
            "body_template": {
                "model": {"$ref": "identity.model"},
                "inputs": {"$ref": "request.items"},
            },
            "vectors_pointer": "/data",
            "values_pointer": "/embedding",
            "match_by": "input_order",
            "id_pointer": None,
        }
        embedding_wire["wire_contract_sha256"] = canonical_sha256(embedding_wire)
        value = {
            "schema_version": "kg-provider-runtime-config-v1",
            "network_mode": "https",
            "approval_binding": {
                "receipt_path": str(self.root / "approval.json"),
                "receipt_sha256": "5" * 64,
                "stop_b_request_path": str(self.root / "stop-b-request.json"),
                "stop_b_request_sha256": "6" * 64,
                "contract_materials_path": str(
                    self.root / "contract-materials.json"
                ),
                "contract_materials_sha256": "7" * 64,
                "egress_policy_path": str(self.root / "egress.json"),
                "egress_policy_sha256": "8" * 64,
            },
            "server_answer": {
                "strategy": strategy,
                "winner_policy": (
                    "first_success" if strategy == "parallel_hedge" else "ordered_success"
                ),
                "total_budget_seconds": 2.0,
                "total_cost_budget_microunits": 10 * count,
                "circuit_breaker_failure_threshold": 2,
                "circuit_breaker_cooldown_seconds": 30.0,
                "channels": channels,
            },
            "embedding": {
                "approval_role_id": "embedding",
                "identity": {
                    "provider": identity.provider,
                    "endpoint": identity.base_url,
                    "region": identity.region,
                    "model": identity.model,
                    "model_version": identity.model_version,
                    "api_version": identity.api_version,
                    "dimension": identity.dimension,
                    "normalization": identity.normalization,
                    "input_type": identity.input_type,
                },
                "identity_sha256": identity.sha256,
                "policy": {
                    "batch_size": policy.batch_size,
                    "max_input_units": policy.max_input_units,
                    "timeout_seconds": policy.timeout_seconds,
                    "max_retries": policy.max_retries,
                    "max_requests_per_operation": policy.max_requests_per_operation,
                    "max_cost_microunits_per_request": policy.max_cost_microunits_per_request,
                    "total_cost_budget_microunits": policy.total_cost_budget_microunits,
                    "max_request_bytes": policy.max_request_bytes,
                    "max_response_bytes": policy.max_response_bytes,
                },
                "policy_sha256": policy.sha256,
                "secret_ref": "secretref:KG_EMBEDDING_KEY",
                "auth": auth,
                "meters": meters,
                "wire": embedding_wire,
            },
        }
        self.channel_objects = tuple(channel_objects)
        self.embedding_identity = identity
        self.embedding_policy = policy
        return value

    def _load(self, strategy: str, count: int):
        value = self._config(strategy, count)
        path = self.root / f"provider-{strategy}.json"
        path.write_bytes(canonical_bytes(value) + b"\n")
        config = ProviderRuntimeConfig.load(path)
        answer = config.server_answer
        runtime_config = SimpleNamespace(
            provider_runtime_config_sha256=config.sha256,
            server_answer=SimpleNamespace(
                strategy=answer.strategy,
                winner_policy=answer.winner_policy,
                ordered_channels=tuple(
                    SimpleNamespace(
                        channel_id=channel.channel_id,
                        identity_sha256=channel.identity_sha256,
                    )
                    for channel in answer.channels
                ),
                total_budget_seconds=answer.total_budget_seconds,
                total_cost_budget_microunits=answer.total_cost_budget_microunits,
                circuit_breaker_failure_threshold=answer.circuit_breaker_failure_threshold,
                circuit_breaker_cooldown_seconds=answer.circuit_breaker_cooldown_seconds,
            ),
            embedding_identity_sha256=config.embedding.identity_sha256,
            embedding_policy_sha256=config.embedding.policy_sha256,
            local_vector={"dimension": config.embedding.identity["dimension"]},
        )
        runtime = FakeRuntime(runtime_config)
        environment = {
            "KG_PROVIDER_NETWORK_MODE": "https",
            "KG_EMBEDDING_KEY": "embedding-secret-value",
            **{
                f"KG_CHANNEL_{index}_KEY": f"channel-{index}-secret-value"
                for index in range(1, count + 1)
            },
        }
        return config, runtime, environment

    @staticmethod
    def _approved(_config) -> None:
        return None

    def test_single_binds_and_runs_answer_and_query_embedding(self) -> None:
        config, runtime, environment = self._load("single", 1)
        factory = ExecutorFactory()
        result = bootstrap_provider_runtime(
            runtime,
            config,
            environment=environment,
            approval_validator=self._approved,
            executor_factory=factory,
        )
        self.assertEqual(1, result.answer_channel_count)
        self.assertEqual("single", result.answer_strategy)
        query = runtime.embedding_adapter.embed_query(
            QueryEmbeddingInput("query:1", "abcd", 4)
        )
        self.assertEqual(4, len(query.vector))
        answer = runtime.answer_coordinator.coordinate(
            ServerAnswerRequest(
                request_id="request-1",
                question="abc",
                evidence=({"evidence_id": "e-1", "text": "defg"},),
                input_units=7,
            )
        )
        self.assertEqual("answer-channel-1", answer.answer)
        self.assertEqual(
            [("server_answer", "channel-1"), ("embedding", "embedding")],
            factory.calls,
        )

    def test_fallback_two_channels_and_hedge_three_channels_are_data_driven(self) -> None:
        fallback_config, fallback_runtime, fallback_environment = self._load(
            "sequential_fallback", 2
        )
        fallback_factory = ExecutorFactory(("channel-1",))
        bootstrap_provider_runtime(
            fallback_runtime,
            fallback_config,
            environment=fallback_environment,
            approval_validator=self._approved,
            executor_factory=fallback_factory,
        )
        outcome = fallback_runtime.answer_coordinator.coordinate(
            ServerAnswerRequest(
                request_id="request-2",
                question="abc",
                evidence=({"evidence_id": "e-1", "text": "defg"},),
                input_units=7,
            )
        )
        self.assertEqual("channel-2", outcome.winner_channel_id)

        hedge_config, hedge_runtime, hedge_environment = self._load(
            "parallel_hedge", 3
        )
        hedge_factory = ExecutorFactory()
        bootstrap_provider_runtime(
            hedge_runtime,
            hedge_config,
            environment=hedge_environment,
            approval_validator=self._approved,
            executor_factory=hedge_factory,
        )
        self.assertEqual(3, len(hedge_runtime.answer_coordinator.adapters))
        self.assertEqual(
            ("channel-1", "channel-2", "channel-3"),
            hedge_runtime.answer_coordinator.policy.ordered_channel_ids,
        )

    def test_gate_hash_and_approval_fail_before_executor_or_secret_use(self) -> None:
        config, runtime, _environment = self._load("single", 1)
        factory = ExecutorFactory()
        with self.assertRaises(ProviderBootstrapError) as caught:
            bootstrap_provider_runtime(
                runtime,
                config,
                environment={},
                approval_validator=self._approved,
                executor_factory=factory,
            )
        self.assertEqual("provider_network_disabled", caught.exception.code)
        self.assertEqual([], factory.calls)

        runtime.config.provider_runtime_config_sha256 = "0" * 64
        with self.assertRaises(ProviderBootstrapError) as caught:
            bootstrap_provider_runtime(
                runtime,
                config,
                environment={"KG_PROVIDER_NETWORK_MODE": "https"},
                approval_validator=self._approved,
                executor_factory=factory,
            )
        self.assertEqual("provider_config_hash_mismatch", caught.exception.code)
        self.assertEqual([], factory.calls)

        runtime.config.provider_runtime_config_sha256 = config.sha256

        def reject(_config):
            raise ProviderApprovalError("provider_approval_missing")

        with self.assertRaises(ProviderApprovalError):
            bootstrap_provider_runtime(
                runtime,
                config,
                environment={"KG_PROVIDER_NETWORK_MODE": "https"},
                approval_validator=reject,
                executor_factory=factory,
            )
        self.assertEqual([], factory.calls)


if __name__ == "__main__":
    unittest.main()
