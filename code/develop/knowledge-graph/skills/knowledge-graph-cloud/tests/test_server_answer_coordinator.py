#!/usr/bin/env python3

from __future__ import annotations

import multiprocessing
import socket
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.server_answer_coordinator import (
    CoordinatorPolicy,
    ServerAnswerCoordinator,
    ServerAnswerUnavailable,
)
from rag_store.server_answer_model import (
    LOCAL_METER_EXECUTION_CONTRACT,
    RESPONSE_SCHEMA_VERSION,
    ServerAnswerChannel,
    ServerAnswerModelAdapter,
    ServerAnswerModelError,
    ServerAnswerRequest,
)


def channel(channel_id: str, *, timeout: float = 0.2, cost: int = 100):
    return ServerAnswerChannel(
        channel_id=channel_id,
        provider=f"fake-provider-{channel_id}",
        base_url=f"https://{channel_id}.invalid/v1/answer",
        region="synthetic-region",
        model=f"fake-model-{channel_id}",
        model_version=f"fake-model-version-{channel_id}",
        api_version="fake-v1",
        timeout_seconds=timeout,
        max_input_units=200,
        max_output_units=80,
        max_cost_microunits=cost,
    )


def response(config: ServerAnswerChannel, answer: str = "受控专业候选"):
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "channel_identity_sha256": config.identity_sha256,
        "answer": answer,
        "usage": {
            "input_units": 12,
            "output_units": 8,
            "cost_microunits": 20,
        },
    }


def request():
    return ServerAnswerRequest(
        request_id="synthetic-request-1",
        question="合成问题",
        evidence=({"evidence_id": "e-1", "text": "合成证据"},),
        input_units=12,
    )


def policy(strategy: str, ids: tuple[str, ...], *, winner: str = "ordered_success"):
    return CoordinatorPolicy(
        strategy=strategy,
        ordered_channel_ids=ids,
        winner_policy=winner,
        total_budget_seconds=0.3,
        total_cost_budget_microunits=100 * len(ids),
        circuit_breaker_failure_threshold=2,
        circuit_breaker_cooldown_seconds=10.0,
    )


def offline_adapter(config, transport, **kwargs):
    with mock.patch(
        "rag_store.server_answer_model._is_sealed_offline_fake_transport",
        return_value=True,
    ):
        return ServerAnswerModelAdapter(
            config,
            transport=transport,
            transport_mode="cooperative",
            **kwargs,
        )


def metered_input(payload):
    return int(payload["input_units"])


def metered_output(answer):
    return len(answer)


def metered_cost(_channel, _input_units, _output_units):
    return 20


class ForeverAnswerTransport:
    def __call__(self, _channel, _payload, _deadline):
        while True:
            time.sleep(1)


class FailSecondSubmitExecutor:
    def __init__(self, *args, **kwargs):
        self._delegate = RealThreadPoolExecutor(*args, **kwargs)
        self._submissions = 0

    def submit(self, *args, **kwargs):
        self._submissions += 1
        if self._submissions == 2:
            raise RuntimeError("SECRET executor failure")
        return self._delegate.submit(*args, **kwargs)

    def shutdown(self, *args, **kwargs):
        return self._delegate.shutdown(*args, **kwargs)


class FailSecondSubmitAfterStartExecutor(FailSecondSubmitExecutor):
    first_started = threading.Event()

    def submit(self, *args, **kwargs):
        self._submissions += 1
        if self._submissions == 2:
            if not self.first_started.wait(timeout=0.2):
                raise AssertionError("first channel did not start")
            raise RuntimeError("SECRET executor failure")
        return self._delegate.submit(*args, **kwargs)


class ServerAnswerCoordinatorTests(unittest.TestCase):
    def test_arbitrary_callable_cannot_force_cooperative_transport(self):
        with self.assertRaisesRegex(ValueError, "sealed offline fake"):
            ServerAnswerModelAdapter(
                channel("one"),
                transport=lambda *_args: {},
                transport_mode="cooperative",
            )

    def test_explicit_external_transport_does_not_load_the_fake_contract(self):
        with mock.patch(
            "rag_store.server_answer_model._is_sealed_offline_fake_transport",
            side_effect=AssertionError("fake contract must not load"),
        ):
            adapter = ServerAnswerModelAdapter(
                channel("one"),
                transport=ForeverAnswerTransport(),
                transport_mode="external_process",
                input_unit_meter=metered_input,
                output_unit_meter=metered_output,
                cost_meter=metered_cost,
            )
        self.assertEqual("external_process", adapter.transport_mode)

    def test_single_runs_with_process_level_network_blocked(self):
        config = channel("one")
        calls = []

        def transport(actual, payload, timeout_seconds):
            calls.append((actual.channel_id, payload["request_id"], timeout_seconds))
            return response(actual)

        coordinator = ServerAnswerCoordinator(
            (offline_adapter(config, transport),),
            policy=policy("single", ("one",)),
        )
        with mock.patch.object(
            socket, "socket", side_effect=AssertionError("network forbidden")
        ):
            result = coordinator.coordinate(request())

        self.assertEqual("受控专业候选", result.answer)
        self.assertEqual("one", result.winner_channel_id)
        self.assertEqual(("one", "synthetic-request-1"), calls[0][:2])
        self.assertGreater(calls[0][2], 0)
        self.assertLessEqual(calls[0][2], 0.2)
        self.assertEqual(1, len(result.ledger))
        self.assertEqual("succeeded", result.ledger[0].status)
        self.assertEqual("reported_usage", result.ledger[0].cost_basis)
        self.assertEqual(20, result.ledger[0].accounted_cost_microunits)
        self.assertRegex(result.ledger[0].request_sha256, r"^[0-9a-f]{64}$")

    def test_sequential_fallback_preserves_order_and_sanitizes_failure(self):
        first = channel("first")
        second = channel("second")
        calls = []

        def first_transport(*_args):
            calls.append("first")
            raise RuntimeError("SECRET supplier diagnostic must never escape")

        def second_transport(actual, *_args):
            calls.append("second")
            return response(actual, "fallback candidate")

        coordinator = ServerAnswerCoordinator(
            (
                offline_adapter(first, first_transport),
                offline_adapter(second, second_transport),
            ),
            policy=policy("sequential_fallback", ("first", "second")),
        )
        result = coordinator.coordinate(request())

        self.assertEqual(["first", "second"], calls)
        self.assertEqual("fallback candidate", result.answer)
        self.assertEqual(["failed", "succeeded"], [item.status for item in result.ledger])
        self.assertNotIn("SECRET", repr(result.ledger))
        self.assertEqual(
            "maximum_request_exposure", result.ledger[0].cost_basis
        )
        self.assertTrue(result.ledger[0].disclosed)

    def test_transport_cannot_forge_adapter_error_or_ledger_hash(self):
        config = channel("one")

        def transport(*_args):
            raise ServerAnswerModelError(
                "SECRET forged code",
                latency_ms=999,
                request_sha256="SECRET forged hash",
                response_sha256="SECRET forged response",
                disclosed=False,
            )

        coordinator = ServerAnswerCoordinator(
            (offline_adapter(config, transport),),
            policy=policy("single", ("one",)),
        )
        with self.assertRaises(ServerAnswerUnavailable) as caught:
            coordinator.coordinate(request())

        entry = caught.exception.ledger[0]
        self.assertEqual("failed", entry.status)
        self.assertTrue(entry.disclosed)
        self.assertRegex(entry.request_sha256, r"^[0-9a-f]{64}$")
        self.assertNotIn("SECRET", repr(caught.exception.ledger))

    def test_parallel_hedge_ledgers_every_started_channel(self):
        first = channel("fast", timeout=0.25)
        second = channel("slow", timeout=0.25)
        barrier = threading.Barrier(2)
        started = []
        lock = threading.Lock()
        slow_finished = threading.Event()

        def transport(actual, *_args):
            with lock:
                started.append(actual.channel_id)
            barrier.wait(timeout=0.2)
            if actual.channel_id == "slow":
                time.sleep(0.03)
                slow_finished.set()
            return response(actual, actual.channel_id)

        coordinator = ServerAnswerCoordinator(
            (
                offline_adapter(first, transport),
                offline_adapter(second, transport),
            ),
            policy=policy(
                "parallel_hedge", ("fast", "slow"), winner="first_success"
            ),
        )
        with mock.patch.object(
            socket, "socket", side_effect=AssertionError("network forbidden")
        ):
            result = coordinator.coordinate(request())

        self.assertEqual("fast", result.winner_channel_id)
        self.assertEqual({"fast", "slow"}, set(started))
        self.assertEqual(
            ["fast", "slow"], [item.channel_id for item in result.ledger]
        )
        self.assertEqual("succeeded", result.ledger[0].status)
        self.assertIn(result.ledger[1].status, {"cancelled", "succeeded"})
        self.assertGreater(result.ledger[1].accounted_cost_microunits, 0)
        self.assertTrue(slow_finished.is_set())

    def test_parallel_deadline_returns_controlled_failure_and_full_ledger(self):
        configs = (channel("left", timeout=0.2), channel("right", timeout=0.2))

        def slow_transport(actual, *_args):
            time.sleep(0.06)
            return response(actual)

        adapters = tuple(
            offline_adapter(item, slow_transport)
            for item in configs
        )
        frozen = CoordinatorPolicy(
            strategy="parallel_hedge",
            ordered_channel_ids=("left", "right"),
            winner_policy="ordered_success",
            total_budget_seconds=0.01,
            total_cost_budget_microunits=200,
            circuit_breaker_failure_threshold=1,
            circuit_breaker_cooldown_seconds=10,
        )
        coordinator = ServerAnswerCoordinator(adapters, policy=frozen)

        with self.assertRaises(ServerAnswerUnavailable) as caught:
            coordinator.coordinate(request())

        self.assertEqual("server answer unavailable", str(caught.exception))
        self.assertEqual(2, len(caught.exception.ledger))
        self.assertEqual(
            {"timed_out"}, {item.status for item in caught.exception.ledger}
        )
        self.assertNotIn("provider", str(caught.exception).lower())

    def test_parallel_ordered_success_chooses_approved_order_not_fastest(self):
        first = channel("first")
        second = channel("second")
        barrier = threading.Barrier(2)

        def transport(actual, *_args):
            barrier.wait(timeout=0.2)
            if actual.channel_id == "first":
                time.sleep(0.03)
            return response(actual, actual.channel_id)

        coordinator = ServerAnswerCoordinator(
            (
                offline_adapter(first, transport),
                offline_adapter(second, transport),
            ),
            policy=policy(
                "parallel_hedge", ("first", "second"), winner="ordered_success"
            ),
        )
        result = coordinator.coordinate(request())

        self.assertEqual("first", result.winner_channel_id)
        self.assertEqual(
            ["succeeded", "succeeded"], [item.status for item in result.ledger]
        )

    def test_empty_response_and_identity_drift_are_controlled(self):
        config = channel("one")
        bad_responses = (
            {**response(config), "answer": "  "},
            {**response(config), "channel_identity_sha256": "0" * 64},
        )
        expected_codes = ("empty_response", "identity_mismatch")
        for bad, expected in zip(bad_responses, expected_codes):
            with self.subTest(expected=expected):
                adapter = offline_adapter(
                    config, lambda *_args, value=bad: value
                )
                with self.assertRaises(ServerAnswerModelError) as caught:
                    adapter.invoke(request())
                self.assertEqual(expected, caught.exception.code)
                self.assertEqual("server answer channel failed", str(caught.exception))
                self.assertRegex(caught.exception.response_sha256 or "", r"^[0-9a-f]{64}$")

    def test_external_transport_is_killed_at_a_fixed_wall_deadline(self):
        config = channel("slow", timeout=0.2)
        adapter = ServerAnswerModelAdapter(
            config,
            transport=ForeverAnswerTransport(),
            transport_mode="external_process",
            input_unit_meter=metered_input,
            output_unit_meter=metered_output,
            cost_meter=metered_cost,
        )
        started = time.monotonic()
        with self.assertRaises(ServerAnswerModelError) as caught:
            adapter.invoke(request())
        elapsed = time.monotonic() - started

        self.assertEqual("timeout", caught.exception.code)
        self.assertLess(elapsed, 1.0)
        self.assertFalse(
            any(
                child.name.startswith("kg-answer-transport-")
                for child in multiprocessing.active_children()
            )
        )

    def test_external_transport_requires_local_usage_and_cost_meters(self):
        with self.assertRaises(ValueError):
            ServerAnswerModelAdapter(
                channel("one"),
                transport=ForeverAnswerTransport(),
                transport_mode="external_process",
            )

    def test_response_usage_bytes_and_cost_are_locally_verified(self):
        config = channel("one")
        cases = (
            (
                {**response(config), "usage": {**response(config)["usage"], "input_units": 11}},
                "usage_mismatch",
            ),
            (
                {
                    **response(config, "abcd"),
                    "usage": {"input_units": 12, "output_units": 1, "cost_microunits": 20},
                },
                "usage_mismatch",
            ),
            (
                {
                    **response(config, "abcd"),
                    "usage": {"input_units": 12, "output_units": 4, "cost_microunits": 1},
                },
                "cost_mismatch",
            ),
        )
        for payload, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                adapter = offline_adapter(
                    config,
                    lambda *_args, value=payload: value,
                    input_unit_meter=metered_input,
                    output_unit_meter=metered_output,
                    cost_meter=metered_cost,
                )
                with self.assertRaises(ServerAnswerModelError) as caught:
                    adapter.invoke(request())
                self.assertEqual(expected_code, caught.exception.code)

        tiny = ServerAnswerChannel(
            **{
                **config.__dict__,
                "max_response_bytes": 256,
            }
        )
        oversized = response(tiny, "x" * 1000)
        adapter = offline_adapter(tiny, lambda *_args: oversized)
        with self.assertRaises(ServerAnswerModelError) as caught:
            adapter.invoke(request())
        self.assertEqual("response_too_large", caught.exception.code)

    def test_local_meters_cannot_disclose_or_succeed_after_the_deadline(self):
        class FakeClock:
            value = 0.0

            def __call__(self):
                return self.value

            def advance(self, seconds):
                self.value += seconds

        config = channel("one", timeout=0.2)
        input_clock = FakeClock()
        transport = mock.Mock(side_effect=AssertionError("transport must not run"))

        def slow_input_meter(payload):
            input_clock.advance(0.3)
            return payload["input_units"]

        input_adapter = offline_adapter(
            config,
            transport,
            input_unit_meter=slow_input_meter,
            clock=input_clock,
        )
        with self.assertRaises(ServerAnswerModelError) as input_caught:
            input_adapter.invoke(request())
        self.assertEqual("timeout", input_caught.exception.code)
        self.assertFalse(input_caught.exception.disclosed)
        transport.assert_not_called()

        output_clock = FakeClock()

        def slow_output_meter(answer):
            output_clock.advance(0.3)
            return len(answer)

        output_adapter = offline_adapter(
            config,
            lambda *_args: {
                **response(config, "abcd"),
                "usage": {
                    "input_units": 12,
                    "output_units": 4,
                    "cost_microunits": 20,
                },
            },
            output_unit_meter=slow_output_meter,
            clock=output_clock,
        )
        with self.assertRaises(ServerAnswerModelError) as output_caught:
            output_adapter.invoke(request())
        self.assertEqual("timeout", output_caught.exception.code)
        self.assertTrue(output_caught.exception.disclosed)
        self.assertRegex(output_caught.exception.response_sha256 or "", r"^[0-9a-f]{64}$")

    def test_parallel_submit_failure_is_sanitized_and_fully_ledgered(self):
        first = channel("first")
        second = channel("second")

        def first_transport(actual, _payload, deadline):
            deadline.cancellation_event.wait(timeout=0.2)
            return response(actual)

        coordinator = ServerAnswerCoordinator(
            (
                offline_adapter(first, first_transport),
                offline_adapter(second, lambda actual, *_args: response(actual)),
            ),
            policy=policy("parallel_hedge", ("first", "second")),
        )
        with mock.patch(
            "rag_store.server_answer_coordinator.ThreadPoolExecutor",
            FailSecondSubmitExecutor,
        ):
            with self.assertRaises(ServerAnswerUnavailable) as caught:
                coordinator.coordinate(request())

        self.assertEqual("server answer unavailable", str(caught.exception))
        self.assertNotIn("SECRET", repr(caught.exception.ledger))
        self.assertEqual(["first", "second"], [item.channel_id for item in caught.exception.ledger])
        self.assertEqual("not_started_submit_failure", caught.exception.ledger[1].status)
        self.assertFalse(caught.exception.ledger[1].disclosed)

    def test_submit_failure_records_a_disclosed_channel_failure_in_its_circuit(self):
        first = channel("first")
        second = channel("second")
        first_started = threading.Event()
        FailSecondSubmitAfterStartExecutor.first_started = first_started

        def first_transport(*_args):
            first_started.set()
            raise RuntimeError("SECRET provider failure")

        frozen = CoordinatorPolicy(
            strategy="parallel_hedge",
            ordered_channel_ids=("first", "second"),
            winner_policy="ordered_success",
            total_budget_seconds=0.3,
            total_cost_budget_microunits=200,
            circuit_breaker_failure_threshold=1,
            circuit_breaker_cooldown_seconds=10,
        )
        coordinator = ServerAnswerCoordinator(
            (
                offline_adapter(first, first_transport),
                offline_adapter(second, lambda actual, *_args: response(actual)),
            ),
            policy=frozen,
        )
        with mock.patch(
            "rag_store.server_answer_coordinator.ThreadPoolExecutor",
            FailSecondSubmitAfterStartExecutor,
        ):
            with self.assertRaises(ServerAnswerUnavailable) as caught:
                coordinator.coordinate(request())

        self.assertEqual("failed", caught.exception.ledger[0].status)
        self.assertTrue(caught.exception.ledger[0].disclosed)
        result = coordinator.coordinate(request())
        self.assertEqual("second", result.winner_channel_id)
        self.assertEqual(("first",), result.skipped_channel_ids)

    def test_circuit_breaker_skips_without_creating_a_disclosure_entry(self):
        config = channel("one")
        frozen = CoordinatorPolicy(
            strategy="single",
            ordered_channel_ids=("one",),
            winner_policy="ordered_success",
            total_budget_seconds=0.1,
            total_cost_budget_microunits=100,
            circuit_breaker_failure_threshold=1,
            circuit_breaker_cooldown_seconds=60,
        )
        coordinator = ServerAnswerCoordinator(
            (
                offline_adapter(
                    config, lambda *_args: (_ for _ in ()).throw(TimeoutError())
                ),
            ),
            policy=frozen,
        )
        with self.assertRaises(ServerAnswerUnavailable) as first:
            coordinator.coordinate(request())
        with self.assertRaises(ServerAnswerUnavailable) as second:
            coordinator.coordinate(request())

        self.assertEqual(1, len(first.exception.ledger))
        self.assertEqual((), second.exception.ledger)
        self.assertEqual(("one",), second.exception.skipped_channel_ids)

    def test_invalid_request_is_zero_cost_and_does_not_open_circuits(self):
        config = channel("one")
        transport = mock.Mock(side_effect=AssertionError("transport must not run"))
        frozen = CoordinatorPolicy(
            strategy="single",
            ordered_channel_ids=("one",),
            winner_policy="ordered_success",
            total_budget_seconds=0.1,
            total_cost_budget_microunits=100,
            circuit_breaker_failure_threshold=1,
            circuit_breaker_cooldown_seconds=60,
        )
        coordinator = ServerAnswerCoordinator(
            (offline_adapter(config, transport),), policy=frozen
        )
        invalid = ServerAnswerRequest(
            request_id="synthetic-invalid",
            question="合成问题",
            evidence=({"evidence_id": "e", "text": "证据"},),
            input_units=0,
        )
        for _ in range(2):
            with self.assertRaises(ServerAnswerUnavailable) as caught:
                coordinator.coordinate(invalid)
            entry = caught.exception.ledger[0]
            self.assertEqual("not_disclosed", entry.status)
            self.assertFalse(entry.disclosed)
            self.assertEqual(0, entry.accounted_cost_microunits)
            self.assertEqual((), caught.exception.skipped_channel_ids)
        transport.assert_not_called()

    def test_deadline_skipped_fallback_is_explicit_zero_cost(self):
        class FakeClock:
            value = 0.0

            def __call__(self):
                return self.value

            def advance(self, seconds):
                self.value += seconds

        clock = FakeClock()
        first = channel("first")
        second = channel("second")

        def first_transport(*_args):
            clock.advance(1.0)
            raise TimeoutError("synthetic")

        coordinator = ServerAnswerCoordinator(
            (
                offline_adapter(first, first_transport, clock=clock),
                offline_adapter(
                    second,
                    lambda *_args: self.fail("fallback must not start"),
                    clock=clock,
                ),
            ),
            policy=policy("sequential_fallback", ("first", "second")),
            clock=clock,
        )
        with self.assertRaises(ServerAnswerUnavailable) as caught:
            coordinator.coordinate(request())

        self.assertEqual(
            ["timed_out", "not_started_deadline"],
            [item.status for item in caught.exception.ledger],
        )
        self.assertTrue(caught.exception.ledger[0].disclosed)
        self.assertFalse(caught.exception.ledger[1].disclosed)
        self.assertEqual(0, caught.exception.ledger[1].accounted_cost_microunits)
        self.assertEqual(("second",), caught.exception.skipped_channel_ids)

    def test_order_and_maximum_cost_exposure_are_configuration_gates(self):
        one = offline_adapter(
            channel("one"), lambda actual, *_args: response(actual)
        )
        two = offline_adapter(
            channel("two"), lambda actual, *_args: response(actual)
        )
        with self.assertRaises(ValueError):
            ServerAnswerCoordinator(
                (two, one),
                policy=policy("sequential_fallback", ("one", "two")),
            )
        underfunded = CoordinatorPolicy(
            strategy="sequential_fallback",
            ordered_channel_ids=("one", "two"),
            winner_policy="ordered_success",
            total_budget_seconds=1,
            total_cost_budget_microunits=199,
            circuit_breaker_failure_threshold=1,
            circuit_breaker_cooldown_seconds=1,
        )
        with self.assertRaises(ValueError):
            ServerAnswerCoordinator((one, two), policy=underfunded)

    def test_channel_identity_binds_timeout_limits_and_cost(self):
        baseline = channel("one")
        changed = channel("one", timeout=0.3, cost=101)
        self.assertEqual(
            LOCAL_METER_EXECUTION_CONTRACT,
            baseline.identity()["local_meter_execution_contract"],
        )
        self.assertNotEqual(baseline.identity_sha256, changed.identity_sha256)


if __name__ == "__main__":
    unittest.main()
