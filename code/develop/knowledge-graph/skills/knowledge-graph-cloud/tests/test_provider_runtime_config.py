#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
STOP_B_REQUEST_TEMPLATE = REPO_ROOT / "STOP_B_EXTERNAL_PROCESSING_REQUEST.json"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from pipeline.provider_bootstrap import (
    APPROVAL_TRUST_ANCHOR_ENVIRONMENT_VARIABLE,
    ProviderApprovalError,
    ProviderBootstrapError,
    ProviderRuntimeConfig,
    ProviderRuntimeConfigError,
    ProviderSecretError,
    authorization_header,
    _configured_role_contracts,
    require_https_network_mode,
    resolve_secret,
    validate_production_approval,
)
from deploy.cloud_v2.tests.stop_b_request_fixture import approval_ready_request
from rag_store.embedding_adapter import EmbeddingIdentity, EmbeddingPolicy
from rag_store.server_answer_model import ServerAnswerChannel


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


class ProviderRuntimeConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="kg-provider-config-test-")
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)

    def _write(self, value: object, name: str = "provider-config.json") -> Path:
        path = self.root / name
        path.write_bytes(canonical_bytes(value) + b"\n")
        return path

    def _write_blob(self, value: bytes, name: str) -> Path:
        path = self.root / name
        path.write_bytes(value)
        return path

    def _disabled(self) -> dict[str, object]:
        return {
            "schema_version": "kg-provider-runtime-config-v1",
            "network_mode": "disabled",
            "approval_binding": None,
            "server_answer": None,
            "embedding": None,
        }

    def _https(self) -> dict[str, object]:
        channel = ServerAnswerChannel(
            channel_id="answer-1",
            provider="offline-provider-fixture",
            base_url="https://answer.invalid/v1/generate",
            region="synthetic-region",
            model="offline-model",
            model_version="offline-model-v1",
            api_version="offline-api-v1",
            timeout_seconds=1.5,
            max_input_units=4096,
            max_output_units=1024,
            max_cost_microunits=100,
            max_request_bytes=65536,
            max_response_bytes=65536,
        )
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
        identity = EmbeddingIdentity(
            provider="offline-provider-fixture",
            base_url="https://embedding.invalid/v1/embed",
            region="synthetic-region",
            model="offline-embedding",
            model_version="offline-embedding-v1",
            api_version="offline-api-v1",
            dimension=8,
            normalization="l2",
            input_type="document-or-query-text-v1",
        )
        policy = EmbeddingPolicy(
            batch_size=16,
            max_input_units=4096,
            timeout_seconds=2.0,
            max_retries=0,
            max_requests_per_operation=100,
            max_cost_microunits_per_request=100,
            total_cost_budget_microunits=10000,
            max_request_bytes=65536,
            max_response_bytes=65536,
        )
        embedding_wire = {
            "schema_version": "kg-provider-embedding-wire-v1",
            "request_schema_sha256": "3" * 64,
            "response_schema_sha256": "4" * 64,
            "body_template": {
                "model": {"$ref": "identity.model"},
                "input": {"$ref": "request.items"},
                "input_type": {"$ref": "request.input_type"},
            },
            "vectors_pointer": "/data",
            "values_pointer": "/embedding",
            "match_by": "input_order",
            "id_pointer": None,
        }
        embedding_wire["wire_contract_sha256"] = canonical_sha256(embedding_wire)
        auth = {"header_name": "Authorization", "prefix": "Bearer "}
        meters = {
            "input_meter_id": "unicode_codepoints-v1",
            "output_meter_id": "unicode_codepoints-v1",
            "cost_meter_id": "maximum_request_exposure-v1",
        }
        return {
            "schema_version": "kg-provider-runtime-config-v1",
            "network_mode": "https",
            "approval_binding": {
                "receipt_path": str(self.root / "production-approval.json"),
                "receipt_sha256": "5" * 64,
                "stop_b_request_path": str(self.root / "stop-b-request.json"),
                "stop_b_request_sha256": "6" * 64,
                "contract_materials_path": str(self.root / "contract-materials.json"),
                "contract_materials_sha256": "7" * 64,
                "egress_policy_path": str(self.root / "egress-policy.json"),
                "egress_policy_sha256": "8" * 64,
            },
            "server_answer": {
                "strategy": "single",
                "winner_policy": "ordered_success",
                "total_budget_seconds": 2.0,
                "total_cost_budget_microunits": 100,
                "circuit_breaker_failure_threshold": 2,
                "circuit_breaker_cooldown_seconds": 30.0,
                "channels": [
                    {
                        "channel_id": channel.channel_id,
                        "approval_role_id": "server-answer-1",
                        "provider": channel.provider,
                        "endpoint": channel.base_url,
                        "region": channel.region,
                        "model": channel.model,
                        "model_version": channel.model_version,
                        "api_version": channel.api_version,
                        "identity_sha256": channel.identity_sha256,
                        "secret_ref": "secretref:KG_ANSWER_1_KEY",
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
                ],
            },
            "embedding": {
                "approval_role_id": "embedding-1",
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

    def _align_stop_b_request(
        self,
        request: dict[str, object],
        config: ProviderRuntimeConfig,
    ) -> None:
        answer = config.server_answer
        embedding = config.embedding
        self.assertIsNotNone(answer)
        self.assertIsNotNone(embedding)
        channel = answer.channels[0]
        roles = {role["role_id"]: role for role in request["role_instances"]}
        server = roles[channel.approval_role_id]
        embed = roles[embedding.approval_role_id]
        app = roles["app-host-final-1"]

        def bind_identity(role: dict[str, object], identity: dict[str, object]) -> None:
            role["endpoint_contract"].update(
                {
                    "exact_endpoint": identity["endpoint"],
                    "region": identity["region"],
                    "data_residency": "mainland-china-only",
                    "china_region_default_satisfied": True,
                }
            )
            role["model_contract"].update(
                {
                    "model_id": identity["model"],
                    "model_version": identity["model_version"],
                    "api_version": identity["api_version"],
                    "request_schema_sha256": identity["request_schema_sha256"],
                    "response_schema_sha256": identity["response_schema_sha256"],
                }
            )

        server_identity = {
            "endpoint": channel.endpoint,
            "region": channel.region,
            "model": channel.model,
            "model_version": channel.model_version,
            "api_version": channel.api_version,
            "request_schema_sha256": channel.wire.request_schema_sha256,
            "response_schema_sha256": channel.wire.response_schema_sha256,
        }
        embedding_identity = {
            "endpoint": embedding.identity["base_url"],
            "region": embedding.identity["region"],
            "model": embedding.identity["model"],
            "model_version": embedding.identity["model_version"],
            "api_version": embedding.identity["api_version"],
            "request_schema_sha256": embedding.wire.request_schema_sha256,
            "response_schema_sha256": embedding.wire.response_schema_sha256,
        }
        bind_identity(server, server_identity)
        bind_identity(app, server_identity)
        bind_identity(embed, embedding_identity)
        server["operational_limits"].update(
            {
                "timeout_ms": int(channel.limits["timeout_seconds"] * 1000),
                "max_retries": 0,
                "max_input_units": channel.limits["max_input_units"],
                "max_output_units": channel.limits["max_output_units"],
                "max_request_bytes": channel.limits["max_request_bytes"],
                "max_response_bytes": channel.limits["max_response_bytes"],
            }
        )
        server["commercial_contract"]["budget_per_call_microunits"] = (
            channel.limits["max_cost_microunits"]
        )
        embed["operational_limits"].update(
            {
                "timeout_ms": int(embedding.policy["timeout_seconds"] * 1000),
                "max_retries": embedding.policy["max_retries"],
                "max_input_units": embedding.policy["max_input_units"],
                "max_request_bytes": embedding.policy["max_request_bytes"],
                "max_response_bytes": embedding.policy["max_response_bytes"],
            }
        )
        embed["commercial_contract"]["budget_per_call_microunits"] = embedding.policy[
            "max_cost_microunits_per_request"
        ]

        coordinator = request["server_answer_coordinator"]
        coordinator.update(
            {
                "selected_strategy": answer.strategy,
                "ordered_channel_role_ids": [channel.approval_role_id],
                "winner_policy": answer.winner_policy,
                "global_deadline_ms": int(answer.total_budget_seconds * 1000),
                "parallel_max_started_channels": 1,
                "hedge_delay_ms": 0,
            }
        )
        coordinator["per_channel_limits"] = [
            {
                "role_id": channel.approval_role_id,
                "timeout_ms": int(channel.limits["timeout_seconds"] * 1000),
                "max_retries": 0,
                "max_cost_microunits": channel.limits["max_cost_microunits"],
            }
        ]
        coordinator["aggregate_limits"].update(
            {
                "max_started_calls_per_request": 1,
                "total_cost_budget_microunits": answer.total_cost_budget_microunits,
            }
        )
        coordinator["circuit_breaker"].update(
            {
                "failure_threshold": answer.circuit_breaker_failure_threshold,
                "cooldown_seconds": int(answer.circuit_breaker_cooldown_seconds),
            }
        )
        vector = request["local_vector_contract"]["production"]["vector_identity"]
        vector.update(
            {
                "embedding_identity_sha256": embedding.identity_sha256,
                "dimension": embedding.identity["dimension"],
                "normalization": embedding.identity["normalization"],
            }
        )
        for decision in request["data_class_decisions"]:
            if decision["limits"] is not None:
                decision["limits"]["expires_at"] = "2099-12-31T23:59:59Z"
        role_by_id = {role["role_id"]: role for role in request["role_instances"]}
        for slot in request["provider_specific_wire_compilation"]["role_slots"]:
            slot["exact_endpoint"] = role_by_id[slot["role_id"]]["endpoint_contract"][
                "exact_endpoint"
            ]

    def _materialize_contracts(
        self,
        request: dict[str, object],
        request_schema: Path,
        response_schema: Path,
    ) -> list[dict[str, object]]:
        request_sha = hashlib.sha256(request_schema.read_bytes()).hexdigest()
        response_sha = hashlib.sha256(response_schema.read_bytes()).hexdigest()
        materials: list[dict[str, object]] = []
        fixed_fields = (
            ("training_contract", "evidence_sha256"),
            ("retention_contract", "evidence_sha256"),
            ("deletion_exit_contract", "evidence_sha256"),
            ("meter_contract", "code_sha256"),
            ("meter_contract", "termination_evidence_sha256"),
            ("commercial_contract", "evidence_sha256"),
        )
        for role in request["role_instances"]:
            role_id = role["role_id"]
            prefix = role_id.replace(":", "-")
            role["model_contract"]["request_schema_sha256"] = request_sha
            role["model_contract"]["response_schema_sha256"] = response_sha
            for contract_field, path, sha256 in (
                (
                    "model_contract.request_schema_sha256",
                    request_schema,
                    request_sha,
                ),
                (
                    "model_contract.response_schema_sha256",
                    response_schema,
                    response_sha,
                ),
            ):
                materials.append(
                    {
                        "role_id": role_id,
                        "contract_field": contract_field,
                        "evidence_id": None,
                        "path": str(path),
                        "sha256": sha256,
                    }
                )
            for section, field in fixed_fields:
                contract_field = f"{section}.{field}"
                path = self._write_blob(
                    f"{role_id}:{contract_field}:bound material\n".encode("utf-8"),
                    f"{prefix}-{section}-{field}.txt",
                )
                sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                role[section][field] = sha256
                materials.append(
                    {
                        "role_id": role_id,
                        "contract_field": contract_field,
                        "evidence_id": None,
                        "path": str(path),
                        "sha256": sha256,
                    }
                )
            for evidence in role["evidence_refs"]:
                evidence_id = evidence["evidence_id"]
                path = self._write_blob(
                    f"{role_id}:{evidence_id}:account-bound evidence\n".encode("utf-8"),
                    f"{prefix}-{evidence_id.replace(':', '-')}.txt",
                )
                sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                evidence["sha256"] = sha256
                materials.append(
                    {
                        "role_id": role_id,
                        "contract_field": "evidence_refs.sha256",
                        "evidence_id": evidence_id,
                        "path": str(path),
                        "sha256": sha256,
                    }
                )
        roles = {role["role_id"]: role for role in request["role_instances"]}
        for slot in request["provider_specific_wire_compilation"]["role_slots"]:
            slot["model_identity_sha256"] = canonical_sha256(
                roles[slot["role_id"]]["model_contract"]
            )
        for expectation in request["synthetic_probe"]["expected_outputs"][
            "role_expectations"
        ]:
            expectation["response_schema_sha256"] = roles[expectation["role_id"]][
                "model_contract"
            ]["response_schema_sha256"]
            if roles[expectation["role_id"]]["role_kind"] == "embedding":
                expectation["embedding_dimension"] = request["local_vector_contract"][
                    "production"
                ]["vector_identity"]["dimension"]
        return materials

    def _egress_policy(
        self,
        request: dict[str, object],
        config: ProviderRuntimeConfig,
    ) -> dict[str, object]:
        configured = _configured_role_contracts(config)
        first_runtime = next(iter(configured.values()))
        mappings: list[dict[str, object]] = []
        for role in request["role_instances"]:
            runtime = configured.get(role["role_id"])
            provider = (
                runtime["provider"] if runtime is not None else first_runtime["provider"]
            )
            identity_sha256 = (
                runtime["provider_identity_sha256"]
                if runtime is not None
                else first_runtime["provider_identity_sha256"]
            )
            mappings.append(
                {
                    "role_id": role["role_id"],
                    "role_kind": role["role_kind"],
                    "ordinal": role["ordinal"],
                    "purpose": role["purpose"],
                    "data_class_ids": copy.deepcopy(role["allowed_data_class_ids"]),
                    "provider": provider,
                    "endpoint": role["endpoint_contract"]["exact_endpoint"],
                    "region": role["endpoint_contract"]["region"],
                    "model": role["model_contract"]["model_id"],
                    "model_version": role["model_contract"]["model_version"],
                    "api_version": role["model_contract"]["api_version"],
                    "identity_sha256": identity_sha256,
                }
            )
        return {
            "schema_version": "kg-provider-egress-policy-v3",
            "status": "approved",
            "provider_contract_sha256": config.contract_sha256,
            "stop_b_request_sha256": "0" * 64,
            "allowed_endpoints": sorted({item["endpoint"] for item in mappings}),
            "role_mappings": mappings,
        }

    def _seal_approval(
        self,
        config_value: dict[str, object],
        request: dict[str, object],
        material_entries: list[dict[str, object]],
        egress: dict[str, object],
        suffix: str,
        *,
        expires_at: str = "2099-12-31T23:59:59Z",
    ) -> dict[str, object]:
        preliminary = ProviderRuntimeConfig.load(
            self._write(config_value, f"preliminary-{suffix}.json")
        )
        request_path = self._write(request, f"stop-b-request-{suffix}.json")
        request_sha = hashlib.sha256(request_path.read_bytes()).hexdigest()
        materials = {
            "schema_version": "kg-provider-contract-material-manifest-v1",
            "status": "bound-to-stop-b-request",
            "provider_contract_sha256": preliminary.contract_sha256,
            "stop_b_request_sha256": request_sha,
            "materials": copy.deepcopy(material_entries),
        }
        egress["provider_contract_sha256"] = preliminary.contract_sha256
        egress["stop_b_request_sha256"] = request_sha
        materials_path = self._write(materials, f"contract-materials-{suffix}.json")
        egress_path = self._write(egress, f"egress-{suffix}.json")
        materials_sha = hashlib.sha256(materials_path.read_bytes()).hexdigest()
        egress_sha = hashlib.sha256(egress_path.read_bytes()).hexdigest()
        receipt = {
            "schema_version": "kg-stop-b-production-provider-approval-v3",
            "status": "stop_b_production_provider_approved",
            "approval_id": f"production-approval-{suffix}",
            "approved_by": "CAACYJ authorized approver",
            "approved_at": "2026-09-02T12:00:00Z",
            "expires_at": expires_at,
            "approval_scope": "all_external_processing_roles",
            "regional_policy": "china_only",
            "data_class_policy_version": "kg-stop-b-data-classes-v1",
            "external_role_count": len(request["role_instances"]),
            "provider_contract_sha256": preliminary.contract_sha256,
            "stop_b_request_sha256": request_sha,
            "contract_materials_sha256": materials_sha,
            "egress_policy_sha256": egress_sha,
            "data_class_decisions": [
                {
                    "data_class_id": item["data_class_id"],
                    "decision": (
                        "approved"
                        if item["decision"] == "request_approval"
                        else "denied"
                    ),
                }
                for item in request["data_class_decisions"]
            ],
        }
        receipt_path = self._write(receipt, f"receipt-{suffix}.json")
        receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        config_value["approval_binding"].update(
            {
                "receipt_path": str(receipt_path),
                "receipt_sha256": receipt_sha,
                "stop_b_request_path": str(request_path),
                "stop_b_request_sha256": request_sha,
                "contract_materials_path": str(materials_path),
                "contract_materials_sha256": materials_sha,
                "egress_policy_path": str(egress_path),
                "egress_policy_sha256": egress_sha,
            }
        )
        config = ProviderRuntimeConfig.load(
            self._write(config_value, f"sealed-config-{suffix}.json")
        )
        self.assertEqual(preliminary.contract_sha256, config.contract_sha256)
        return {
            "config": config,
            "environment": {
                APPROVAL_TRUST_ANCHOR_ENVIRONMENT_VARIABLE: receipt_sha
            },
            "config_value": config_value,
            "request": request,
            "materials": materials,
            "material_entries": material_entries,
            "egress": egress,
            "receipt": receipt,
            "receipt_path": receipt_path,
        }

    def _production_approval_fixture(
        self,
        suffix: str = "complete",
        *,
        expires_at: str = "2099-12-31T23:59:59Z",
    ) -> dict[str, object]:
        request_schema = self._write_blob(
            b'{"title":"request-schema"}\n', "request-schema.json"
        )
        response_schema = self._write_blob(
            b'{"title":"response-schema"}\n', "response-schema.json"
        )
        request_sha = hashlib.sha256(request_schema.read_bytes()).hexdigest()
        response_sha = hashlib.sha256(response_schema.read_bytes()).hexdigest()
        config_value = self._https()
        answer_wire = config_value["server_answer"]["channels"][0]["wire"]
        answer_wire["request_schema_sha256"] = request_sha
        answer_wire["response_schema_sha256"] = response_sha
        answer_wire["wire_contract_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in answer_wire.items()
                if key != "wire_contract_sha256"
            }
        )
        embedding_wire = config_value["embedding"]["wire"]
        embedding_wire["request_schema_sha256"] = request_sha
        embedding_wire["response_schema_sha256"] = response_sha
        embedding_wire["wire_contract_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in embedding_wire.items()
                if key != "wire_contract_sha256"
            }
        )
        preliminary = ProviderRuntimeConfig.load(
            self._write(config_value, f"contract-{suffix}.json")
        )
        request = approval_ready_request(
            json.loads(STOP_B_REQUEST_TEMPLATE.read_text(encoding="utf-8"))
        )
        self._align_stop_b_request(request, preliminary)
        material_entries = self._materialize_contracts(
            request, request_schema, response_schema
        )
        egress = self._egress_policy(request, preliminary)
        return self._seal_approval(
            config_value,
            request,
            material_entries,
            egress,
            suffix,
            expires_at=expires_at,
        )

    def _reseal_receipt(
        self,
        fixture: dict[str, object],
        receipt: dict[str, object],
        suffix: str,
    ) -> tuple[ProviderRuntimeConfig, dict[str, str]]:
        receipt_path = self._write(receipt, f"resealed-receipt-{suffix}.json")
        receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        config_value = copy.deepcopy(fixture["config_value"])
        config_value["approval_binding"]["receipt_path"] = str(receipt_path)
        config_value["approval_binding"]["receipt_sha256"] = receipt_sha
        config = ProviderRuntimeConfig.load(
            self._write(config_value, f"resealed-config-{suffix}.json")
        )
        return config, {APPROVAL_TRUST_ANCHOR_ENVIRONMENT_VARIABLE: receipt_sha}

    def test_disabled_config_is_the_only_empty_non_network_state(self) -> None:
        config = ProviderRuntimeConfig.load(self._write(self._disabled()))
        self.assertEqual("disabled", config.network_mode)
        self.assertIsNone(config.server_answer)
        changed = self._disabled()
        changed["embedding"] = {}
        with self.assertRaisesRegex(
            ProviderRuntimeConfigError, "provider runtime bootstrap failed"
        ) as caught:
            ProviderRuntimeConfig.load(self._write(changed, "invalid-disabled.json"))
        self.assertEqual("disabled_provider_config_not_empty", caught.exception.code)

    def test_https_config_binds_answer_embedding_policy_and_wire_hashes(self) -> None:
        config = ProviderRuntimeConfig.load(self._write(self._https()))
        self.assertEqual("https", config.network_mode)
        self.assertEqual(1, len(config.server_answer.channels))
        self.assertEqual(
            config.embedding.identity_sha256,
            self._https()["embedding"]["identity_sha256"],
        )
        self.assertRegex(config.contract_sha256, r"^[0-9a-f]{64}$")

    def test_unknown_template_ref_and_wire_hash_drift_fail_closed(self) -> None:
        unknown = self._https()
        unknown["embedding"]["wire"]["body_template"] = {
            "input": {"$ref": "environment.SECRET"}
        }
        unknown["embedding"]["wire"]["wire_contract_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in unknown["embedding"]["wire"].items()
                if key != "wire_contract_sha256"
            }
        )
        with self.assertRaises(ProviderRuntimeConfigError) as caught:
            ProviderRuntimeConfig.load(self._write(unknown, "unknown-ref.json"))
        self.assertEqual("embedding_config_invalid", caught.exception.code)

        drift = self._https()
        drift["server_answer"]["channels"][0]["wire"]["answer_pointer"] = "/other"
        with self.assertRaises(ProviderRuntimeConfigError) as caught:
            ProviderRuntimeConfig.load(self._write(drift, "wire-drift.json"))
        self.assertEqual("server_answer_wire_hash_mismatch", caught.exception.code)

    def test_answer_and_embedding_template_refs_are_role_specific(self) -> None:
        answer_cross_role = self._https()
        answer_wire = answer_cross_role["server_answer"]["channels"][0]["wire"]
        answer_wire["body_template"] = {
            "items": {"$ref": "request.items"}
        }
        answer_wire["wire_contract_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in answer_wire.items()
                if key != "wire_contract_sha256"
            }
        )
        with self.assertRaises(ProviderRuntimeConfigError) as caught:
            ProviderRuntimeConfig.load(
                self._write(answer_cross_role, "answer-cross-role.json")
            )
        self.assertEqual("server_answer_channel_invalid", caught.exception.code)

        embedding_cross_role = self._https()
        embedding_wire = embedding_cross_role["embedding"]["wire"]
        embedding_wire["body_template"] = {
            "question": {"$ref": "request.question"}
        }
        embedding_wire["wire_contract_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in embedding_wire.items()
                if key != "wire_contract_sha256"
            }
        )
        with self.assertRaises(ProviderRuntimeConfigError) as caught:
            ProviderRuntimeConfig.load(
                self._write(embedding_cross_role, "embedding-cross-role.json")
            )
        self.assertEqual("embedding_config_invalid", caught.exception.code)

    def test_duplicate_json_key_and_plaintext_secret_are_rejected(self) -> None:
        duplicate = self.root / "duplicate.json"
        duplicate.write_text(
            '{"schema_version":"kg-provider-runtime-config-v1",'
            '"schema_version":"kg-provider-runtime-config-v1",'
            '"network_mode":"disabled","approval_binding":null,'
            '"server_answer":null,"embedding":null}',
            encoding="utf-8",
        )
        with self.assertRaises(ProviderRuntimeConfigError) as caught:
            ProviderRuntimeConfig.load(duplicate)
        self.assertEqual("provider_config_invalid_json", caught.exception.code)

        plaintext = self._https()
        plaintext["server_answer"]["channels"][0]["secret_ref"] = "actual-secret"
        with self.assertRaises(ProviderRuntimeConfigError) as caught:
            ProviderRuntimeConfig.load(self._write(plaintext, "plaintext.json"))
        self.assertEqual("server_answer_channel_invalid", caught.exception.code)

    def test_secret_resolver_redacts_repr_and_rejects_header_injection(self) -> None:
        secret = resolve_secret(
            "secretref:KG_ANSWER_1_KEY", {"KG_ANSWER_1_KEY": "top-secret"}
        )
        self.assertNotIn("top-secret", repr(secret))
        header = authorization_header(
            ProviderRuntimeConfig.load(self._write(self._https()))
            .server_answer.channels[0]
            .auth,
            secret,
        )
        self.assertEqual(("Authorization", "Bearer top-secret"), header)
        with self.assertRaises(ProviderSecretError):
            resolve_secret(
                "secretref:KG_ANSWER_1_KEY",
                {"KG_ANSWER_1_KEY": "secret\r\nInjected: true"},
            )

    def test_network_gate_and_approval_fail_before_secret_resolution(self) -> None:
        disabled = ProviderRuntimeConfig.load(self._write(self._disabled()))
        with self.assertRaises(ProviderBootstrapError) as caught:
            require_https_network_mode(disabled, {"KG_PROVIDER_NETWORK_MODE": "https"})
        self.assertEqual("provider_network_disabled", caught.exception.code)

        enabled = ProviderRuntimeConfig.load(self._write(self._https(), "https.json"))
        with self.assertRaises(ProviderBootstrapError) as caught:
            require_https_network_mode(enabled, {})
        self.assertEqual("provider_network_disabled", caught.exception.code)
        with self.assertRaises(ProviderApprovalError):
            validate_production_approval(enabled)

    def test_complete_production_approval_requires_external_trust_anchor(self) -> None:
        fixture = self._production_approval_fixture()
        config = fixture["config"]
        environment = fixture["environment"]
        with self.assertRaises(ProviderApprovalError) as caught:
            validate_production_approval(config, {})
        self.assertEqual(
            "provider_approval_trust_anchor_invalid", caught.exception.code
        )
        validate_production_approval(config, environment)
        endpoints = [
            role["endpoint"] for role in fixture["egress"]["role_mappings"]
        ]
        self.assertLess(len(set(endpoints)), len(endpoints))
        self.assertEqual(
            set(fixture["egress"]["allowed_endpoints"]), set(endpoints)
        )

    def test_approval_counts_and_ordinals_require_strict_json_integers(self) -> None:
        ordinal_fixture = self._production_approval_fixture("ordinal-type-base")
        egress = copy.deepcopy(ordinal_fixture["egress"])
        self.assertEqual(1, egress["role_mappings"][0]["ordinal"])
        egress["role_mappings"][0]["ordinal"] = True
        ordinal_changed = self._seal_approval(
            copy.deepcopy(ordinal_fixture["config_value"]),
            copy.deepcopy(ordinal_fixture["request"]),
            copy.deepcopy(ordinal_fixture["material_entries"]),
            egress,
            "ordinal-type",
        )
        with self.assertRaises(ProviderApprovalError) as caught:
            validate_production_approval(
                ordinal_changed["config"], ordinal_changed["environment"]
            )
        self.assertEqual("provider_egress_policy_invalid", caught.exception.code)

        count_fixture = self._production_approval_fixture("role-count-type-base")
        receipt = copy.deepcopy(count_fixture["receipt"])
        receipt["external_role_count"] = float(receipt["external_role_count"])
        count_config, count_environment = self._reseal_receipt(
            count_fixture, receipt, "role-count-type"
        )
        with self.assertRaises(ProviderApprovalError) as caught:
            validate_production_approval(count_config, count_environment)
        self.assertEqual(
            "provider_approval_receipt_invalid", caught.exception.code
        )

    def test_all_five_data_class_decisions_are_mandatory(self) -> None:
        fixture = self._production_approval_fixture("data-classes-base")
        for suffix, mutate in (
            (
                "missing",
                lambda decisions: decisions.pop(),
            ),
            (
                "unknown",
                lambda decisions: decisions[0].__setitem__(
                    "data_class_id", "unknown-data-class"
                ),
            ),
            (
                "requested-denied",
                lambda decisions: decisions[0].__setitem__("decision", "denied"),
            ),
        ):
            with self.subTest(suffix=suffix):
                receipt = copy.deepcopy(fixture["receipt"])
                mutate(receipt["data_class_decisions"])
                config, environment = self._reseal_receipt(
                    fixture, receipt, f"data-class-{suffix}"
                )
                with self.assertRaises(ProviderApprovalError) as caught:
                    validate_production_approval(config, environment)
                self.assertEqual(
                    "provider_approval_receipt_invalid", caught.exception.code
                )

    def test_unconfigured_provider_role_cannot_be_added_to_approval(self) -> None:
        fixture = self._production_approval_fixture("wrong-role-base")
        config_value = copy.deepcopy(fixture["config_value"])
        config_value["server_answer"]["channels"][0][
            "approval_role_id"
        ] = "server-answer-unconfigured"
        changed = self._seal_approval(
            config_value,
            copy.deepcopy(fixture["request"]),
            copy.deepcopy(fixture["material_entries"]),
            copy.deepcopy(fixture["egress"]),
            "wrong-role",
        )
        with self.assertRaises(ProviderApprovalError) as caught:
            validate_production_approval(changed["config"], changed["environment"])
        self.assertEqual("provider_role_binding_invalid", caught.exception.code)

    def test_runtime_budget_drift_fails_after_resealing(self) -> None:
        fixture = self._production_approval_fixture("budget-base")
        config_value = copy.deepcopy(fixture["config_value"])
        config_value["server_answer"]["total_cost_budget_microunits"] = 99
        changed = self._seal_approval(
            config_value,
            copy.deepcopy(fixture["request"]),
            copy.deepcopy(fixture["material_entries"]),
            copy.deepcopy(fixture["egress"]),
            "budget-drift",
        )
        with self.assertRaises(ProviderApprovalError) as caught:
            validate_production_approval(changed["config"], changed["environment"])
        self.assertEqual("provider_role_binding_invalid", caught.exception.code)

    def test_contract_evidence_bytes_are_verified_after_approval(self) -> None:
        fixture = self._production_approval_fixture("evidence-bytes")
        validate_production_approval(fixture["config"], fixture["environment"])
        evidence_path = Path(fixture["material_entries"][0]["path"])
        evidence_path.write_bytes(b"changed after approval\n")
        with self.assertRaises(ProviderApprovalError) as caught:
            validate_production_approval(
                fixture["config"], fixture["environment"]
            )
        self.assertEqual("provider_contract_materials_invalid", caught.exception.code)

    def test_expired_production_approval_is_rejected(self) -> None:
        fixture = self._production_approval_fixture(
            "expired", expires_at="2026-09-02T12:00:01Z"
        )
        with self.assertRaises(ProviderApprovalError) as caught:
            validate_production_approval(fixture["config"], fixture["environment"])
        self.assertEqual("provider_approval_receipt_invalid", caught.exception.code)

    def test_resealed_self_consistent_bundle_does_not_replace_external_anchor(self) -> None:
        fixture = self._production_approval_fixture("anchor-base")
        receipt = copy.deepcopy(fixture["receipt"])
        receipt["approval_id"] = "production-approval-resealed"
        config, new_environment = self._reseal_receipt(
            fixture, receipt, "self-consistent"
        )
        old_environment = fixture["environment"]
        self.assertNotEqual(old_environment, new_environment)
        with self.assertRaises(ProviderApprovalError) as caught:
            validate_production_approval(config, old_environment)
        self.assertEqual(
            "provider_approval_trust_anchor_invalid", caught.exception.code
        )

    def test_schema_is_valid_json_and_declares_disabled_default_shape(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "deploy/pipeline/provider_runtime_config.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            "kg-provider-runtime-config-v1",
            schema["properties"]["schema_version"]["const"],
        )


if __name__ == "__main__":
    unittest.main()
