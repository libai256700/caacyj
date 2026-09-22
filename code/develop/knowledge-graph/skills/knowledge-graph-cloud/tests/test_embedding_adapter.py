#!/usr/bin/env python3

from __future__ import annotations

import math
import multiprocessing
import socket
import sys
import time
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.embedding_adapter import (
    EMBEDDING_RESPONSE_SCHEMA_VERSION,
    LOCAL_METER_EXECUTION_CONTRACT,
    EmbeddingAdapter,
    EmbeddingError,
    EmbeddingIdentity,
    EmbeddingInput,
    EmbeddingPolicy,
    RetryableEmbeddingTransportError,
)


def identity():
    return EmbeddingIdentity(
        provider="fake-embedding-provider",
        base_url="https://embedding.invalid/v1/embed",
        region="synthetic-region",
        model="fake-embedding-model",
        model_version="fake-model-v1",
        api_version="fake-api-v1",
        dimension=3,
        normalization="l2",
        input_type="document-or-query-text-v1",
    )


def policy(*, batch_size: int = 2, retries: int = 0):
    return EmbeddingPolicy(
        batch_size=batch_size,
        max_input_units=100,
        timeout_seconds=0.2,
        max_retries=retries,
        max_requests_per_operation=20,
        max_cost_microunits_per_request=50,
        total_cost_budget_microunits=1000,
    )


def items():
    return (
        EmbeddingInput("a", "合成文本 A", 4),
        EmbeddingInput("b", "合成文本 B", 4),
    )


def success_response(actual_identity, payload, *, vector=(3.0, 4.0, 0.0)):
    return {
        "schema_version": EMBEDDING_RESPONSE_SCHEMA_VERSION,
        "embedding_identity_sha256": actual_identity.sha256,
        "vectors": [
            {"id": item["id"], "values": list(vector)}
            for item in payload["items"]
        ],
        "failed_ids": [],
        "usage": {
            "input_units": sum(item["input_units"] for item in payload["items"]),
            "cost_microunits": 10,
        },
    }


def offline_adapter(frozen_identity, frozen_policy, transport):
    with mock.patch(
        "rag_store.embedding_adapter._is_sealed_offline_fake_transport",
        return_value=True,
    ):
        return EmbeddingAdapter(
            frozen_identity,
            policy=frozen_policy,
            transport=transport,
            transport_mode="cooperative",
        )


def embedding_input_meter(text):
    return len(text)


class ForeverEmbeddingTransport:
    def __call__(self, _identity, _payload, _deadline):
        while True:
            time.sleep(1)


class EmbeddingAdapterTests(unittest.TestCase):
    def test_arbitrary_callable_cannot_force_cooperative_transport(self):
        with self.assertRaisesRegex(ValueError, "sealed offline fake"):
            EmbeddingAdapter(
                identity(),
                policy=policy(),
                transport=lambda *_args: {},
                transport_mode="cooperative",
            )

    def test_explicit_external_transport_does_not_load_the_fake_contract(self):
        with mock.patch(
            "rag_store.embedding_adapter._is_sealed_offline_fake_transport",
            side_effect=AssertionError("fake contract must not load"),
        ):
            adapter = EmbeddingAdapter(
                identity(),
                policy=policy(),
                transport=ForeverEmbeddingTransport(),
                transport_mode="external_process",
                input_unit_meter=embedding_input_meter,
            )
        self.assertEqual("external_process", adapter.transport_mode)

    def test_build_query_and_entity_share_one_identity_and_normalization(self):
        frozen_identity = identity()
        calls = []

        def transport(actual, payload, timeout_seconds):
            calls.append((actual.sha256, payload["purpose"], timeout_seconds))
            return success_response(actual, payload)

        adapter = offline_adapter(frozen_identity, policy(), transport)
        with mock.patch.object(
            socket, "socket", side_effect=AssertionError("network forbidden")
        ):
            build = adapter.embed_build(items())
            query = adapter.embed_query(EmbeddingInput("q", "合成查询", 4))
            entity = adapter.embed_entity(
                (EmbeddingInput("entity-a", "合成实体", 4),)
            )

        self.assertEqual(["build", "query", "entity"], [item[1] for item in calls])
        self.assertEqual({frozen_identity.sha256}, {item[0] for item in calls})
        for result in (build, query, entity):
            self.assertEqual(frozen_identity.sha256, result.identity_sha256)
            for vector in result.vectors:
                self.assertAlmostEqual(
                    1.0,
                    math.sqrt(sum(value * value for value in vector.values)),
                    places=7,
                )
            self.assertTrue(all(item.status == "succeeded" for item in result.ledger))

    def test_partial_second_batch_fails_the_whole_operation_with_checkpoint_ids(self):
        calls = 0

        def transport(actual, payload, _timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                return success_response(actual, payload)
            return {
                "schema_version": EMBEDDING_RESPONSE_SCHEMA_VERSION,
                "embedding_identity_sha256": actual.sha256,
                "vectors": [],
                "failed_ids": [payload["items"][0]["id"]],
                "usage": {"input_units": 4, "cost_microunits": 10},
            }

        adapter = offline_adapter(identity(), policy(batch_size=1), transport)
        with self.assertRaises(EmbeddingError) as caught:
            adapter.embed_build(items())

        self.assertEqual("partial_failure", caught.exception.code)
        self.assertEqual(("a",), caught.exception.completed_ids)
        self.assertEqual(2, len(caught.exception.ledger))
        self.assertEqual(
            ["succeeded", "partial_failure"],
            [item.status for item in caught.exception.ledger],
        )
        self.assertEqual(2, calls)

    def test_retry_is_explicit_bounded_and_fully_ledgered(self):
        calls = 0

        def transport(actual, payload, _timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RetryableEmbeddingTransportError("raw rate limit detail")
            return success_response(actual, payload)

        adapter = offline_adapter(identity(), policy(retries=1), transport)
        result = adapter.embed_query(EmbeddingInput("q", "查询", 2))

        self.assertEqual(2, calls)
        self.assertEqual(
            ["retryable_failure", "succeeded"],
            [item.status for item in result.ledger],
        )
        self.assertNotIn("rate limit", repr(result.ledger))

    def test_retry_exhaustion_and_forged_domain_error_are_sanitized(self):
        def retryable(*_args):
            raise RetryableEmbeddingTransportError("SECRET retry detail")

        retry_adapter = offline_adapter(identity(), policy(retries=1), retryable)
        with self.assertRaises(EmbeddingError) as retry_caught:
            retry_adapter.embed_query(EmbeddingInput("q", "查询", 2))
        self.assertEqual("transport_failure", retry_caught.exception.code)
        self.assertEqual(2, len(retry_caught.exception.ledger))
        self.assertNotIn("SECRET", repr(retry_caught.exception.ledger))

        forged_adapter = offline_adapter(
            identity(),
            policy(),
            lambda *_args: (_ for _ in ()).throw(
                EmbeddingError("SECRET forged domain code")
            ),
        )
        with self.assertRaises(EmbeddingError) as forged_caught:
            forged_adapter.embed_query(EmbeddingInput("q", "查询", 2))
        self.assertEqual("transport_failure", forged_caught.exception.code)
        self.assertNotIn("SECRET", repr(forged_caught.exception.ledger))

    def test_identity_dimension_unknown_and_duplicate_fail_closed(self):
        frozen_identity = identity()

        def wrong_identity(actual, payload, _timeout):
            result = success_response(actual, payload)
            result["embedding_identity_sha256"] = "0" * 64
            return result

        def wrong_dimension(actual, payload, _timeout):
            return success_response(actual, payload, vector=(1.0, 0.0))

        def unknown_id(actual, payload, _timeout):
            result = success_response(actual, payload)
            result["vectors"][0]["id"] = "unknown"
            return result

        for transport in (wrong_identity, wrong_dimension, unknown_id):
            with self.subTest(transport=transport.__name__):
                adapter = offline_adapter(frozen_identity, policy(), transport)
                with self.assertRaises(EmbeddingError) as caught:
                    adapter.embed_query(EmbeddingInput("q", "查询", 2))
                self.assertEqual("invalid_response", caught.exception.code)
                self.assertEqual(1, len(caught.exception.ledger))

        adapter = offline_adapter(
            frozen_identity,
            policy(),
            lambda actual, payload, _timeout: success_response(actual, payload),
        )
        with self.assertRaises(ValueError):
            adapter.embed_build(
                (
                    EmbeddingInput("same", "A", 1),
                    EmbeddingInput("same", "B", 1),
                )
            )

    def test_zero_vector_and_unapproved_purpose_are_rejected(self):
        adapter = offline_adapter(
            identity(),
            policy(),
            lambda actual, payload, _timeout: success_response(
                actual, payload, vector=(0.0, 0.0, 0.0)
            ),
        )
        with self.assertRaises(EmbeddingError):
            adapter.embed_query(EmbeddingInput("q", "查询", 2))
        with self.assertRaises(ValueError):
            adapter.embed("other", (EmbeddingInput("q", "查询", 2),))

    def test_l2_normalization_is_stable_for_extreme_finite_values(self):
        for vector in ((1e308, 1e308, 0.0), (5e-324, 0.0, 0.0)):
            with self.subTest(vector=vector):
                adapter = offline_adapter(
                    identity(),
                    policy(),
                    lambda actual, payload, _deadline, value=vector: success_response(
                        actual, payload, vector=value
                    ),
                )
                result = adapter.embed_query(EmbeddingInput("q", "查询", 2))
                normalized = result.vectors[0].values
                self.assertTrue(all(math.isfinite(value) for value in normalized))
                self.assertAlmostEqual(1.0, math.hypot(*normalized), places=12)

    def test_external_transport_is_killed_at_a_fixed_wall_deadline(self):
        frozen_policy = EmbeddingPolicy(
            batch_size=1,
            max_input_units=100,
            timeout_seconds=0.2,
            max_retries=0,
            max_requests_per_operation=1,
            max_cost_microunits_per_request=50,
            total_cost_budget_microunits=50,
        )

        adapter = EmbeddingAdapter(
            identity(),
            policy=frozen_policy,
            transport=ForeverEmbeddingTransport(),
            transport_mode="external_process",
            input_unit_meter=embedding_input_meter,
        )
        started = time.monotonic()
        with self.assertRaises(EmbeddingError) as caught:
            adapter.embed_query(EmbeddingInput("q", "查询", 2))
        elapsed = time.monotonic() - started

        self.assertEqual("timeout", caught.exception.code)
        self.assertLess(elapsed, 1.0)
        self.assertEqual("timed_out", caught.exception.ledger[0].status)
        self.assertFalse(
            any(
                child.name == "kg-embedding-external-transport"
                for child in multiprocessing.active_children()
            )
        )

    def test_external_transport_requires_a_local_input_meter(self):
        with self.assertRaises(ValueError):
            EmbeddingAdapter(
                identity(),
                policy=policy(),
                transport=ForeverEmbeddingTransport(),
                transport_mode="external_process",
            )

    def test_local_input_meter_consumes_the_first_request_deadline(self):
        class FakeClock:
            value = 0.0

            def __call__(self):
                return self.value

            def advance(self, seconds):
                self.value += seconds

        clock = FakeClock()
        transport = mock.Mock(side_effect=AssertionError("transport must not run"))

        def slow_meter(text):
            clock.advance(0.3)
            return len(text)

        with mock.patch(
            "rag_store.embedding_adapter._is_sealed_offline_fake_transport",
            return_value=True,
        ):
            adapter = EmbeddingAdapter(
                identity(),
                policy=policy(),
                transport=transport,
                transport_mode="cooperative",
                input_unit_meter=slow_meter,
                clock=clock,
            )
        with self.assertRaises(EmbeddingError) as caught:
            adapter.embed_query(EmbeddingInput("q", "查询", 2))

        self.assertEqual("timeout", caught.exception.code)
        self.assertEqual((), caught.exception.ledger)
        transport.assert_not_called()

    def test_policy_manifest_and_hash_bind_every_limit(self):
        baseline = policy()
        same = policy()
        changed = policy(retries=1)
        self.assertEqual(
            LOCAL_METER_EXECUTION_CONTRACT,
            baseline.manifest()["local_meter_execution_contract"],
        )
        self.assertEqual(baseline.manifest(), same.manifest())
        self.assertEqual(baseline.sha256, same.sha256)
        self.assertNotEqual(baseline.sha256, changed.sha256)

    def test_reported_input_usage_must_exactly_match_the_submitted_batch(self):
        def underreported(actual, payload, _deadline):
            value = success_response(actual, payload)
            value["usage"]["input_units"] -= 1
            return value

        adapter = offline_adapter(identity(), policy(), underreported)
        with self.assertRaises(EmbeddingError) as caught:
            adapter.embed_query(EmbeddingInput("q", "查询", 2))
        self.assertEqual("invalid_response", caught.exception.code)

    def test_quota_and_total_budget_are_preflight_gates(self):
        frozen_identity = identity()
        tiny_quota = EmbeddingPolicy(
            batch_size=1,
            max_input_units=100,
            timeout_seconds=1,
            max_retries=1,
            max_requests_per_operation=3,
            max_cost_microunits_per_request=1,
            total_cost_budget_microunits=10,
        )
        adapter = offline_adapter(
            frozen_identity,
            tiny_quota,
            lambda *_args: self.fail("transport must not run"),
        )
        with self.assertRaises(EmbeddingError) as caught:
            adapter.embed_build(items())
        self.assertEqual("quota_exceeded", caught.exception.code)

        tiny_budget = EmbeddingPolicy(
            batch_size=1,
            max_input_units=100,
            timeout_seconds=1,
            max_retries=0,
            max_requests_per_operation=10,
            max_cost_microunits_per_request=10,
            total_cost_budget_microunits=19,
        )
        budget_adapter = offline_adapter(
            frozen_identity,
            tiny_budget,
            lambda *_args: self.fail("transport must not run"),
        )
        with self.assertRaises(EmbeddingError) as budget_caught:
            budget_adapter.embed_build(items())
        self.assertEqual("budget_exceeded", budget_caught.exception.code)


if __name__ == "__main__":
    unittest.main()
