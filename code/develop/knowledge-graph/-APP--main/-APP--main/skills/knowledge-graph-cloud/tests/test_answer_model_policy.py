#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.answer_model_policy import (
    AnswerModelUnavailable,
    DEFAULT_FALLBACK_MODEL,
    POLICY_VERSION,
    PRIMARY_MODEL,
    build_answer_model_telemetry,
    recovery_status_after_finalizer,
    run_answer_model,
)


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def config(include_mini=True):
    models = {
        "flash": {
            "name": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key": "secretref:PRIMARY_TEST_KEY",
        },
        "doubao": {
            "name": "doubao-seed-2-1-pro-260628",
            "base_url": "https://ark.example/v3",
            "api_key": "secretref:PRO_TEST_KEY",
        },
    }
    if include_mini:
        models["doubao_mini"] = {
            "name": "doubao-seed-2-0-mini-260428",
            "base_url": "https://ark.example/v3",
            "api_key": "secretref:MINI_TEST_KEY",
        }
    return {"models": models}


class AnswerModelPolicyTests(unittest.TestCase):
    def test_primary_is_attempted_once_then_mini_fallback_runs(self):
        clock = FakeClock()
        calls = []

        def transport(url, payload, headers, timeout_s):
            calls.append((url, dict(payload), timeout_s))
            clock.advance(0.1)
            if len(calls) == 1:
                raise TimeoutError("primary timeout")
            return {"choices": [{"message": {"content": "有证据的回答"}}]}

        result = run_answer_model(
            {"messages": [], "max_tokens": 200},
            config=config(),
            transport=transport,
            clock=clock,
        )

        self.assertEqual(2, len(calls))
        self.assertEqual("deepseek-v4-flash", calls[0][1]["model"])
        self.assertEqual("doubao-seed-2-0-mini-260428", calls[1][1]["model"])
        self.assertTrue(all(call[1]["thinking"] == {"type": "disabled"} for call in calls))
        self.assertEqual(POLICY_VERSION, result["policy_version"])
        self.assertEqual(["failed", "succeeded"], [item["status"] for item in result["attempts"]])

    def test_extraction_pro_model_is_never_used_as_answer_fallback(self):
        calls = []

        def transport(url, payload, headers, timeout_s):
            calls.append(payload["model"])
            raise RuntimeError("unavailable")

        with self.assertRaises(AnswerModelUnavailable) as caught:
            run_answer_model(
                {"messages": [], "max_tokens": 200},
                config=config(include_mini=False),
                transport=transport,
            )

        self.assertEqual(["deepseek-v4-flash"], calls)
        self.assertEqual(1, len(caught.exception.attempts))

    def test_attempt_timeouts_share_one_total_budget(self):
        clock = FakeClock()
        timeouts = []

        def transport(url, payload, headers, timeout_s):
            timeouts.append(timeout_s)
            clock.advance(timeout_s)
            raise TimeoutError("deadline")

        with self.assertRaises(AnswerModelUnavailable) as caught:
            run_answer_model(
                {"messages": [], "max_tokens": 200},
                config=config(),
                transport=transport,
                clock=clock,
            )

        self.assertLessEqual(sum(timeouts), 5.2)
        self.assertLessEqual(caught.exception.latency_ms, 5200)
        self.assertEqual(2, len({item["model"] for item in caught.exception.attempts}))

    def test_pro_model_cannot_be_smuggled_into_mini_slot(self):
        bad_config = config()
        bad_config["models"]["doubao_mini"]["name"] = "doubao-seed-2-1-pro-260628"

        with self.assertRaises(ValueError):
            run_answer_model(
                {"messages": [], "max_tokens": 200},
                config=bad_config,
                transport=lambda *_args: self.fail("transport must not run"),
            )

    def test_recovery_telemetry_distinguishes_model_and_extractive_outcomes(self):
        attempts = [
            {
                "model": PRIMARY_MODEL,
                "status": "failed",
                "error_type": "TimeoutError",
            },
            {
                "model": DEFAULT_FALLBACK_MODEL,
                "status": "failed",
                "error_type": "RuntimeError",
            },
        ]
        recovered = build_answer_model_telemetry(
            attempts=attempts,
            selected_model="authoritative_extractive_fallback",
            latency_ms=5200,
            recovery_status="extractive_fallback_succeeded",
            extractive_fallback_used=True,
            extractive_fallback_recovered=True,
            extractive_policy_version="extractive-v1",
            answer_method="authoritative_extractive",
            answer_status="recovered",
        )

        self.assertTrue(recovered["primary_failed"])
        self.assertTrue(recovered["primary_timed_out"])
        self.assertTrue(recovered["model_fallback_attempted"])
        self.assertFalse(recovered["model_fallback_succeeded"])
        self.assertTrue(recovered["extractive_fallback_used"])
        self.assertTrue(recovered["extractive_fallback_recovered"])
        self.assertTrue(recovered["fallback_recovered_answer"])
        self.assertFalse(recovered["unrecovered_model_failure"])

        blocked = build_answer_model_telemetry(
            attempts=attempts,
            selected_model=None,
            latency_ms=5200,
            recovery_status="unrecovered",
            extractive_fallback_used=True,
            extractive_fallback_recovered=True,
            extractive_policy_version="extractive-v1",
            answer_method="safe_refusal",
            answer_status="safe_refusal",
        )
        self.assertFalse(blocked["fallback_recovered_answer"])
        self.assertTrue(blocked["unrecovered_model_failure"])

        pipeline_error = build_answer_model_telemetry(
            attempts=attempts,
            selected_model=None,
            latency_ms=5200,
            recovery_status="pipeline_error",
            extractive_fallback_used=True,
            extractive_fallback_recovered=False,
            extractive_policy_version="extractive-v1",
            answer_method="safe_refusal",
            answer_status="safe_refusal",
        )
        self.assertTrue(pipeline_error["unrecovered_model_failure"])

    def test_model_fallback_success_is_an_explicit_recovered_answer(self):
        telemetry = build_answer_model_telemetry(
            attempts=[
                {
                    "model": PRIMARY_MODEL,
                    "status": "failed",
                    "error_type": "TimeoutError",
                },
                {
                    "model": DEFAULT_FALLBACK_MODEL,
                    "status": "succeeded",
                    "error_type": None,
                },
            ],
            selected_model=DEFAULT_FALLBACK_MODEL,
            latency_ms=3000,
            recovery_status="model_fallback_succeeded",
            extractive_fallback_used=False,
            extractive_fallback_recovered=False,
            extractive_policy_version="extractive-v1",
            answer_method="model_fallback",
            answer_status="recovered",
        )

        self.assertEqual("timed_out", telemetry["primary_status"])
        self.assertEqual("succeeded", telemetry["model_fallback_status"])
        self.assertTrue(telemetry["fallback_recovered_answer"])
        self.assertEqual("model_fallback", telemetry["answer_method"])

    def test_finalizer_block_revokes_both_fallback_recovery_states(self):
        for recovery_status in (
            "model_fallback_succeeded",
            "extractive_fallback_succeeded",
        ):
            with self.subTest(recovery_status=recovery_status):
                self.assertEqual(
                    "unrecovered",
                    recovery_status_after_finalizer(recovery_status, "blocked"),
                )
                self.assertEqual(
                    recovery_status,
                    recovery_status_after_finalizer(recovery_status, "passed"),
                )

        attempts = [
            {"model": PRIMARY_MODEL, "status": "failed", "error_type": "TimeoutError"},
            {"model": DEFAULT_FALLBACK_MODEL, "status": "succeeded", "error_type": None},
        ]
        telemetry = build_answer_model_telemetry(
            attempts=attempts,
            selected_model=DEFAULT_FALLBACK_MODEL,
            latency_ms=3000,
            recovery_status=recovery_status_after_finalizer(
                "model_fallback_succeeded", "blocked"
            ),
            extractive_fallback_used=False,
            extractive_fallback_recovered=False,
            extractive_policy_version="extractive-v1",
            answer_method="safe_refusal",
            answer_status="safe_refusal",
        )
        self.assertTrue(telemetry["model_fallback_succeeded"])
        self.assertFalse(telemetry["fallback_recovered_answer"])
        self.assertTrue(telemetry["unrecovered_model_failure"])


if __name__ == "__main__":
    unittest.main()
