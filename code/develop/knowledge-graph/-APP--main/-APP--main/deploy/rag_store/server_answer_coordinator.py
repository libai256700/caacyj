#!/usr/bin/env python3
"""Frozen multi-channel orchestration for provider-neutral server answers."""

from __future__ import annotations

import math
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Callable, Sequence

from .server_answer_model import (
    ServerAnswerModelAdapter,
    ServerAnswerModelError,
    ServerAnswerModelResult,
    ServerAnswerRequest,
)


COORDINATOR_SCHEMA_VERSION = "kg-server-answer-coordinator-v1"
_STRATEGIES = frozenset({"single", "sequential_fallback", "parallel_hedge"})
_WINNER_POLICIES = frozenset({"first_success", "ordered_success"})


@dataclass(frozen=True)
class CoordinatorPolicy:
    strategy: str
    ordered_channel_ids: tuple[str, ...]
    winner_policy: str
    total_budget_seconds: float
    total_cost_budget_microunits: int
    circuit_breaker_failure_threshold: int
    circuit_breaker_cooldown_seconds: float

    def __post_init__(self) -> None:
        if self.strategy not in _STRATEGIES:
            raise ValueError("unsupported coordinator strategy")
        if self.winner_policy not in _WINNER_POLICIES:
            raise ValueError("unsupported winner policy")
        if not self.ordered_channel_ids or any(
            not isinstance(item, str) or not item.strip()
            for item in self.ordered_channel_ids
        ):
            raise ValueError("ordered_channel_ids must contain approved ids")
        if len(set(self.ordered_channel_ids)) != len(self.ordered_channel_ids):
            raise ValueError("ordered_channel_ids must be unique")
        if self.strategy == "single" and len(self.ordered_channel_ids) != 1:
            raise ValueError("single strategy requires exactly one channel")
        if self.strategy != "parallel_hedge" and self.winner_policy != "ordered_success":
            raise ValueError("non-parallel strategies require ordered_success")
        if isinstance(self.total_budget_seconds, bool) or not isinstance(
            self.total_budget_seconds, (int, float)
        ):
            raise ValueError("total_budget_seconds must be positive and finite")
        if (
            not math.isfinite(float(self.total_budget_seconds))
            or self.total_budget_seconds <= 0
        ):
            raise ValueError("total_budget_seconds must be positive and finite")
        for value, field in (
            (self.total_cost_budget_microunits, "total_cost_budget_microunits"),
            (
                self.circuit_breaker_failure_threshold,
                "circuit_breaker_failure_threshold",
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field} must be a positive integer")
        if isinstance(self.circuit_breaker_cooldown_seconds, bool) or not isinstance(
            self.circuit_breaker_cooldown_seconds, (int, float)
        ):
            raise ValueError("circuit breaker cooldown must be positive and finite")
        if (
            not math.isfinite(float(self.circuit_breaker_cooldown_seconds))
            or self.circuit_breaker_cooldown_seconds <= 0
        ):
            raise ValueError("circuit breaker cooldown must be positive and finite")


@dataclass(frozen=True)
class DisclosureCostLedgerEntry:
    channel_id: str
    channel_identity_sha256: str
    status: str
    timeout_ms: int
    latency_ms: int
    request_sha256: str
    response_sha256: str | None
    accounted_cost_microunits: int
    cost_basis: str
    disclosed: bool


@dataclass(frozen=True)
class CoordinatorResult:
    answer: str
    winner_channel_id: str
    policy: str
    winner_policy: str
    latency_ms: int
    ledger: tuple[DisclosureCostLedgerEntry, ...]
    skipped_channel_ids: tuple[str, ...]
    schema_version: str = COORDINATOR_SCHEMA_VERSION


class ServerAnswerUnavailable(RuntimeError):
    """Controlled all-channel failure with internal, sanitized accounting only."""

    def __init__(
        self,
        *,
        ledger: Sequence[DisclosureCostLedgerEntry],
        skipped_channel_ids: Sequence[str],
        latency_ms: int,
    ) -> None:
        super().__init__("server answer unavailable")
        self.ledger = tuple(ledger)
        self.skipped_channel_ids = tuple(skipped_channel_ids)
        self.latency_ms = max(0, int(latency_ms))
        self.schema_version = COORDINATOR_SCHEMA_VERSION


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None


class ServerAnswerCoordinator:
    """Run an explicitly ordered and budgeted set of approved adapters once each."""

    def __init__(
        self,
        adapters: Sequence[ServerAnswerModelAdapter],
        *,
        policy: CoordinatorPolicy,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        ordered = tuple(adapters)
        if not ordered:
            raise ValueError("at least one adapter is required")
        actual_ids = tuple(adapter.channel.channel_id for adapter in ordered)
        if actual_ids != policy.ordered_channel_ids:
            raise ValueError("adapter order must exactly match the approved channel order")
        if len(set(actual_ids)) != len(actual_ids):
            raise ValueError("adapter channel ids must be unique")
        maximum_exposure = sum(
            adapter.channel.max_cost_microunits for adapter in ordered
        )
        if maximum_exposure > policy.total_cost_budget_microunits:
            raise ValueError("total cost budget cannot cover the frozen channel set")
        self.adapters = ordered
        self.policy = policy
        self._clock = clock
        self._circuits = {channel_id: _CircuitState() for channel_id in actual_ids}
        self._circuit_lock = threading.Lock()

    def coordinate(self, request: ServerAnswerRequest) -> CoordinatorResult:
        started = self._clock()
        available, skipped = self._available_adapters()
        if not available:
            raise ServerAnswerUnavailable(
                ledger=(),
                skipped_channel_ids=skipped,
                latency_ms=self._latency_ms(started),
            )
        if self.policy.strategy in {"single", "sequential_fallback"}:
            return self._coordinate_sequential(request, available, skipped, started)
        return self._coordinate_parallel(request, available, skipped, started)

    def _coordinate_sequential(
        self,
        request: ServerAnswerRequest,
        available: Sequence[ServerAnswerModelAdapter],
        skipped: tuple[str, ...],
        started: float,
    ) -> CoordinatorResult:
        ledger: list[DisclosureCostLedgerEntry] = []
        skipped_all = list(skipped)
        for position, adapter in enumerate(available):
            remaining = self.policy.total_budget_seconds - (self._clock() - started)
            if remaining <= 0:
                for not_started in available[position:]:
                    ledger.append(
                        self._not_started_entry(
                            not_started, request, "not_started_deadline"
                        )
                    )
                    skipped_all.append(not_started.channel.channel_id)
                break
            timeout = min(float(adapter.channel.timeout_seconds), remaining)
            try:
                result = adapter.invoke(request, timeout_seconds=timeout)
            except ServerAnswerModelError as exc:
                ledger.append(self._failure_entry(adapter, request, timeout, exc))
                if exc.disclosed:
                    self._record_failure(adapter.channel.channel_id)
                continue
            if self._clock() - started > self.policy.total_budget_seconds:
                ledger.append(self._deadline_entry(adapter, request, timeout, result))
                self._record_failure(adapter.channel.channel_id)
                break
            ledger.append(self._success_entry(adapter, timeout, result))
            self._record_success(adapter.channel.channel_id)
            return self._result(result, ledger, tuple(skipped_all), started)

        raise ServerAnswerUnavailable(
            ledger=ledger,
            skipped_channel_ids=tuple(skipped_all),
            latency_ms=self._latency_ms(started),
        )

    def _coordinate_parallel(
        self,
        request: ServerAnswerRequest,
        available: Sequence[ServerAnswerModelAdapter],
        skipped: tuple[str, ...],
        started: float,
    ) -> CoordinatorResult:
        executor: ThreadPoolExecutor | None = None
        futures: dict[Future[ServerAnswerModelResult], ServerAnswerModelAdapter] = {}
        timeouts: dict[str, float] = {}
        cancellations: dict[str, threading.Event] = {}
        outcomes: dict[str, ServerAnswerModelResult | ServerAnswerModelError] = {}
        pending: set[Future[ServerAnswerModelResult]] = set()
        winner: ServerAnswerModelResult | None = None
        deadline_channel_ids: set[str] = set()
        winner_cancelled_ids: set[str] = set()
        try:
            submit_failure_position: int | None = None
            try:
                executor = ThreadPoolExecutor(
                    max_workers=len(available), thread_name_prefix="kg-answer-channel"
                )
                for position, adapter in enumerate(available):
                    timeout = min(
                        float(adapter.channel.timeout_seconds),
                        float(self.policy.total_budget_seconds),
                    )
                    channel_id = adapter.channel.channel_id
                    timeouts[channel_id] = timeout
                    cancellations[channel_id] = threading.Event()
                    future = executor.submit(
                        adapter.invoke,
                        request,
                        timeout_seconds=timeout,
                        cancellation_event=cancellations[channel_id],
                    )
                    futures[future] = adapter
            except Exception:
                submit_failure_position = len(futures)

            if submit_failure_position is not None:
                pending = set(futures)
                for future in pending:
                    channel_id = futures[future].channel.channel_id
                    cancellations[channel_id].set()
                    future.cancel()
                done, pending = wait(
                    pending,
                    timeout=self._parallel_cleanup_timeout(started, timeouts),
                )
                self._collect_outcomes(done, futures, outcomes, request, started)
                self._collect_newly_completed(
                    pending, futures, outcomes, request, started
                )

                ledger: list[DisclosureCostLedgerEntry] = []
                skipped_all = list(skipped)
                for position, adapter in enumerate(available):
                    channel_id = adapter.channel.channel_id
                    if position >= submit_failure_position:
                        ledger.append(
                            self._not_started_entry(
                                adapter, request, "not_started_submit_failure"
                            )
                        )
                        skipped_all.append(channel_id)
                        continue
                    outcome = outcomes.get(channel_id)
                    if isinstance(outcome, ServerAnswerModelResult):
                        ledger.append(
                            self._success_entry(
                                adapter, timeouts[channel_id], outcome
                            )
                        )
                        self._record_success(channel_id)
                    elif isinstance(outcome, ServerAnswerModelError):
                        ledger.append(
                            self._failure_entry(
                                adapter,
                                request,
                                timeouts[channel_id],
                                outcome,
                            )
                        )
                        if outcome.disclosed and outcome.code != "cancelled":
                            self._record_failure(channel_id)
                    else:
                        future = next(
                            item
                            for item, submitted_adapter in futures.items()
                            if submitted_adapter is adapter
                        )
                        if future.cancelled():
                            ledger.append(
                                self._not_started_entry(
                                    adapter, request, "not_started_cancelled"
                                )
                            )
                        else:
                            ledger.append(
                                self._pending_entry(
                                    adapter,
                                    request,
                                    timeouts[channel_id],
                                    None,
                                    started,
                                )
                            )
                raise ServerAnswerUnavailable(
                    ledger=ledger,
                    skipped_channel_ids=tuple(skipped_all),
                    latency_ms=self._latency_ms(started),
                )

            pending = set(futures)
            while pending:
                remaining = self.policy.total_budget_seconds - (self._clock() - started)
                if remaining <= 0:
                    break
                done, pending = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
                if not done:
                    break
                for future in sorted(
                    done,
                    key=lambda item: self.policy.ordered_channel_ids.index(
                        futures[item].channel.channel_id
                    ),
                ):
                    adapter = futures[future]
                    channel_id = adapter.channel.channel_id
                    result = self._future_outcome(future, adapter, request, started)
                    outcomes[channel_id] = result
                    within_deadline = (
                        self._clock() - started
                        <= self.policy.total_budget_seconds
                    )
                    if not within_deadline:
                        deadline_channel_ids.add(channel_id)
                    elif isinstance(result, ServerAnswerModelResult) and winner is None:
                        winner = result
                if winner is not None and self.policy.winner_policy == "first_success":
                    break

            if pending:
                if winner is not None and self.policy.winner_policy == "first_success":
                    cancelled_ids = winner_cancelled_ids
                else:
                    cancelled_ids = deadline_channel_ids
                for future in pending:
                    channel_id = futures[future].channel.channel_id
                    cancelled_ids.add(channel_id)
                    cancellations[channel_id].set()

                done, pending = wait(
                    pending,
                    timeout=self._parallel_cleanup_timeout(started, timeouts),
                )
                self._collect_outcomes(done, futures, outcomes, request, started)
                self._collect_newly_completed(
                    pending, futures, outcomes, request, started
                )

            if self.policy.winner_policy == "ordered_success":
                winner = next(
                    (
                        outcomes[channel_id]
                        for channel_id in self.policy.ordered_channel_ids
                        if channel_id not in deadline_channel_ids
                        if isinstance(outcomes.get(channel_id), ServerAnswerModelResult)
                    ),
                    None,
                )

            ledger: list[DisclosureCostLedgerEntry] = []
            for adapter in available:
                channel_id = adapter.channel.channel_id
                timeout = timeouts[channel_id]
                outcome = outcomes.get(channel_id)
                if isinstance(outcome, ServerAnswerModelResult):
                    if channel_id in deadline_channel_ids:
                        ledger.append(
                            self._deadline_entry(adapter, request, timeout, outcome)
                        )
                        self._record_failure(channel_id)
                    else:
                        ledger.append(self._success_entry(adapter, timeout, outcome))
                        self._record_success(channel_id)
                elif isinstance(outcome, ServerAnswerModelError):
                    ledger.append(
                        self._failure_entry(
                            adapter,
                            request,
                            timeout,
                            outcome,
                            status_override=(
                                "timed_out"
                                if channel_id in deadline_channel_ids
                                else None
                            ),
                        )
                    )
                    if outcome.disclosed and channel_id not in winner_cancelled_ids:
                        self._record_failure(channel_id)
                else:
                    ledger.append(
                        self._pending_entry(
                            adapter, request, timeout, winner, started
                        )
                    )
                    if channel_id in deadline_channel_ids:
                        self._record_failure(channel_id)

            if winner is None:
                raise ServerAnswerUnavailable(
                    ledger=ledger,
                    skipped_channel_ids=skipped,
                    latency_ms=self._latency_ms(started),
                )
            return self._result(winner, ledger, skipped, started)
        finally:
            if executor is not None:
                for cancellation in cancellations.values():
                    cancellation.set()
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    # Executor diagnostics must not cross the sanitized boundary.
                    pass

    def _collect_outcomes(
        self,
        done: Sequence[Future[ServerAnswerModelResult]],
        futures: dict[Future[ServerAnswerModelResult], ServerAnswerModelAdapter],
        outcomes: dict[str, ServerAnswerModelResult | ServerAnswerModelError],
        request: ServerAnswerRequest,
        started: float,
    ) -> None:
        for future in sorted(
            done,
            key=lambda item: self.policy.ordered_channel_ids.index(
                futures[item].channel.channel_id
            ),
        ):
            adapter = futures[future]
            outcomes[adapter.channel.channel_id] = self._future_outcome(
                future, adapter, request, started
            )

    def _collect_newly_completed(
        self,
        pending: set[Future[ServerAnswerModelResult]],
        futures: dict[Future[ServerAnswerModelResult], ServerAnswerModelAdapter],
        outcomes: dict[str, ServerAnswerModelResult | ServerAnswerModelError],
        request: ServerAnswerRequest,
        started: float,
    ) -> None:
        newly_completed = {future for future in pending if future.done()}
        pending.difference_update(newly_completed)
        self._collect_outcomes(
            newly_completed, futures, outcomes, request, started
        )

    def _parallel_cleanup_timeout(
        self,
        started: float,
        timeouts: dict[str, float],
    ) -> float:
        if not timeouts:
            return 0.0
        elapsed = max(0.0, self._clock() - started)
        remaining_adapter_time = max(
            max(timeouts.values()) - elapsed,
            0.0,
        )
        return remaining_adapter_time + min(0.25, max(timeouts.values()))

    def _future_outcome(
        self,
        future: Future[ServerAnswerModelResult],
        adapter: ServerAnswerModelAdapter,
        request: ServerAnswerRequest,
        started: float,
    ) -> ServerAnswerModelResult | ServerAnswerModelError:
        try:
            return future.result()
        except ServerAnswerModelError as exc:
            return exc
        except Exception:
            return ServerAnswerModelError(
                "transport_failure",
                latency_ms=self._latency_ms(started),
                request_sha256=self._safe_request_sha256(adapter, request),
            )

    def _available_adapters(
        self,
    ) -> tuple[tuple[ServerAnswerModelAdapter, ...], tuple[str, ...]]:
        now = self._clock()
        available: list[ServerAnswerModelAdapter] = []
        skipped: list[str] = []
        with self._circuit_lock:
            for adapter in self.adapters:
                state = self._circuits[adapter.channel.channel_id]
                if state.opened_at is not None:
                    if now - state.opened_at < self.policy.circuit_breaker_cooldown_seconds:
                        skipped.append(adapter.channel.channel_id)
                        continue
                    state.failures = 0
                    state.opened_at = None
                available.append(adapter)
        return tuple(available), tuple(skipped)

    def _record_failure(self, channel_id: str) -> None:
        with self._circuit_lock:
            state = self._circuits[channel_id]
            state.failures += 1
            if state.failures >= self.policy.circuit_breaker_failure_threshold:
                state.opened_at = self._clock()

    def _record_success(self, channel_id: str) -> None:
        with self._circuit_lock:
            state = self._circuits[channel_id]
            state.failures = 0
            state.opened_at = None

    def _success_entry(
        self,
        adapter: ServerAnswerModelAdapter,
        timeout: float,
        result: ServerAnswerModelResult,
    ) -> DisclosureCostLedgerEntry:
        return DisclosureCostLedgerEntry(
            channel_id=adapter.channel.channel_id,
            channel_identity_sha256=adapter.channel.identity_sha256,
            status="succeeded",
            timeout_ms=int(timeout * 1000),
            latency_ms=result.latency_ms,
            request_sha256=result.request_sha256,
            response_sha256=result.response_sha256,
            accounted_cost_microunits=result.usage.cost_microunits,
            cost_basis="reported_usage",
            disclosed=True,
        )

    def _failure_entry(
        self,
        adapter: ServerAnswerModelAdapter,
        request: ServerAnswerRequest,
        timeout: float,
        error: ServerAnswerModelError,
        *,
        status_override: str | None = None,
    ) -> DisclosureCostLedgerEntry:
        return DisclosureCostLedgerEntry(
            channel_id=adapter.channel.channel_id,
            channel_identity_sha256=adapter.channel.identity_sha256,
            status=status_override
            or (
                "not_disclosed"
                if not error.disclosed
                else "timed_out"
                if error.code == "timeout"
                else "cancelled"
                if error.code == "cancelled"
                else "failed"
            ),
            timeout_ms=int(timeout * 1000),
            latency_ms=error.latency_ms,
            request_sha256=self._safe_request_sha256(adapter, request),
            response_sha256=error.response_sha256,
            accounted_cost_microunits=(
                adapter.channel.max_cost_microunits if error.disclosed else 0
            ),
            cost_basis=(
                "maximum_request_exposure" if error.disclosed else "not_disclosed"
            ),
            disclosed=error.disclosed,
        )

    def _deadline_entry(
        self,
        adapter: ServerAnswerModelAdapter,
        request: ServerAnswerRequest,
        timeout: float,
        result: ServerAnswerModelResult,
    ) -> DisclosureCostLedgerEntry:
        return DisclosureCostLedgerEntry(
            channel_id=adapter.channel.channel_id,
            channel_identity_sha256=adapter.channel.identity_sha256,
            status="timed_out",
            timeout_ms=int(timeout * 1000),
            latency_ms=result.latency_ms,
            request_sha256=self._safe_request_sha256(adapter, request),
            response_sha256=result.response_sha256,
            accounted_cost_microunits=result.usage.cost_microunits,
            cost_basis="reported_usage_after_deadline",
            disclosed=True,
        )

    def _pending_entry(
        self,
        adapter: ServerAnswerModelAdapter,
        request: ServerAnswerRequest,
        timeout: float,
        winner: ServerAnswerModelResult | None,
        started: float,
    ) -> DisclosureCostLedgerEntry:
        return DisclosureCostLedgerEntry(
            channel_id=adapter.channel.channel_id,
            channel_identity_sha256=adapter.channel.identity_sha256,
            status="cancel_requested" if winner is not None else "timed_out",
            timeout_ms=int(timeout * 1000),
            latency_ms=self._latency_ms(started),
            request_sha256=self._safe_request_sha256(adapter, request),
            response_sha256=None,
            accounted_cost_microunits=adapter.channel.max_cost_microunits,
            cost_basis="maximum_request_exposure",
            disclosed=True,
        )

    def _not_started_entry(
        self,
        adapter: ServerAnswerModelAdapter,
        request: ServerAnswerRequest,
        status: str,
    ) -> DisclosureCostLedgerEntry:
        return DisclosureCostLedgerEntry(
            channel_id=adapter.channel.channel_id,
            channel_identity_sha256=adapter.channel.identity_sha256,
            status=status,
            timeout_ms=0,
            latency_ms=0,
            request_sha256=self._safe_request_sha256(adapter, request),
            response_sha256=None,
            accounted_cost_microunits=0,
            cost_basis="not_disclosed",
            disclosed=False,
        )

    def _result(
        self,
        winner: ServerAnswerModelResult,
        ledger: Sequence[DisclosureCostLedgerEntry],
        skipped: tuple[str, ...],
        started: float,
    ) -> CoordinatorResult:
        accounted = sum(item.accounted_cost_microunits for item in ledger)
        if accounted > self.policy.total_cost_budget_microunits:
            raise ServerAnswerUnavailable(
                ledger=ledger,
                skipped_channel_ids=skipped,
                latency_ms=self._latency_ms(started),
            )
        return CoordinatorResult(
            answer=winner.answer,
            winner_channel_id=winner.channel_id,
            policy=self.policy.strategy,
            winner_policy=self.policy.winner_policy,
            latency_ms=self._latency_ms(started),
            ledger=tuple(ledger),
            skipped_channel_ids=skipped,
        )

    @staticmethod
    def _safe_request_sha256(
        adapter: ServerAnswerModelAdapter,
        request: ServerAnswerRequest,
    ) -> str:
        try:
            return adapter.request_sha256(request)
        except (TypeError, ValueError):
            return ""

    def _latency_ms(self, started: float) -> int:
        return max(0, int((self._clock() - started) * 1000))
