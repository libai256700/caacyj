#!/usr/bin/env python3
"""Bounded retrieval plans for deterministic execution and shadow comparison."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from rag_store.request_envelope import ALLOWED_SOURCES, RequestEnvelope


PLAN_SCHEMA_VERSION = "retrieval-plan-v1"
TOOL_ORDER = ALLOWED_SOURCES
TOOL_BUDGETS: dict[str, dict[str, int]] = {
    "csa": {"top_k": 1, "timeout_ms": 2500, "max_calls": 1},
    "sqlite_exact": {"top_k": 5, "timeout_ms": 1200, "max_calls": 1},
    "bm25": {"top_k": 15, "timeout_ms": 2500, "max_calls": 1},
    "dense": {"top_k": 10, "timeout_ms": 7000, "max_calls": 1},
    "neo4j": {"top_k": 20, "timeout_ms": 5000, "max_calls": 1},
    "official_api": {"top_k": 8, "timeout_ms": 8000, "max_calls": 1},
    "web": {"top_k": 10, "timeout_ms": 10000, "max_calls": 1},
}

_RELATION_PATTERN = re.compile(
    r"关系|关联|对应|隶属|路径|多跳|上下游|影响链|引用哪些|依据什么|"
    r"适合哪些|匹配|推荐给|由谁|谁负责|哪些人同时|兼任"
)
_LEXICAL_PATTERN = re.compile(
    r"CCAR[-－]?\d+|第\s*\d+(?:\.\d+)*\s*条|题号|原题|正确答案|"
    r"参考答案|制度原文|法规原文|条款|文件名"
)
_COMPOUND_PATTERN = re.compile(r"同时|另外|并且|以及|结合|分别|对比|比较|；|;")


@dataclass(frozen=True)
class RetrievalPlan:
    plan_id: str
    mode: str
    route_decision: str
    expected_tools: tuple[str, ...]
    conditional_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    denied_by_envelope: tuple[str, ...]
    budgets: Mapping[str, Mapping[str, int]]
    max_rounds: int
    minimum_evidence: int
    stop_conditions: tuple[str, ...]
    needs: Mapping[str, bool]
    reasons: tuple[str, ...]
    shadow_eligible: bool
    schema_version: str = PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "mode": self.mode,
            "route_decision": self.route_decision,
            "expected_tools": list(self.expected_tools),
            "conditional_tools": list(self.conditional_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "denied_by_envelope": list(self.denied_by_envelope),
            "budgets": {name: dict(value) for name, value in self.budgets.items()},
            "max_rounds": self.max_rounds,
            "minimum_evidence": self.minimum_evidence,
            "stop_conditions": list(self.stop_conditions),
            "needs": dict(self.needs),
            "reasons": list(self.reasons),
            "shadow_eligible": self.shadow_eligible,
        }


def _ordered(values: set[str] | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    selected = set(values)
    return tuple(tool for tool in TOOL_ORDER if tool in selected)


def _append_tool(target: list[str], tool: str, allowed: set[str]) -> None:
    if tool in allowed and tool not in target:
        target.append(tool)


def build_retrieval_plan(
    envelope: RequestEnvelope,
    *,
    route_decision: str,
    semantic_plan: Mapping[str, Any] | None = None,
    intent: str = "general",
    csa_topic: str | None = None,
    effective_sources: tuple[str, ...] | list[str] | None = None,
) -> RetrievalPlan:
    """Create a typed, deterministic plan without executing retrieval tools."""
    semantic_plan = semantic_plan or {}
    question = envelope.user_query
    domains = [
        str(domain)
        for domain in semantic_plan.get("domains", [])
        if domain and domain != "general"
    ]
    allowed = set(effective_sources if effective_sources is not None else envelope.allowed_sources)
    denied = set(TOOL_ORDER) - allowed
    expected: list[str] = []
    conditional: list[str] = []
    reasons: list[str] = []

    lexical_anchor = bool(_LEXICAL_PATTERN.search(question))
    relation_intent = route_decision == "graph_first" or bool(_RELATION_PATTERN.search(question))
    multi_domain = len(set(domains)) >= 2
    compound = route_decision == "hybrid" or bool(_COMPOUND_PATTERN.search(question))
    complex_request = relation_intent or multi_domain or compound
    graph_required = route_decision == "graph_first" or (
        relation_intent and (multi_domain or bool(semantic_plan.get("graph_query_plan", {}).get("path_required")))
    )
    graph_conditional = not graph_required and (relation_intent or multi_domain)

    if route_decision == "csa":
        _append_tool(expected, "csa", allowed)
        reasons.append("deterministic_structured_route")
    else:
        if route_decision == "hybrid" or csa_topic:
            _append_tool(expected, "csa", allowed)
            reasons.append("structured_partial_answer")

        _append_tool(expected, "bm25", allowed)
        if lexical_anchor:
            _append_tool(conditional, "sqlite_exact", allowed)
            _append_tool(conditional, "dense", allowed)
            reasons.append("lexical_anchor_prefers_exact_and_sparse")
        else:
            _append_tool(expected, "dense", allowed)
            reasons.append("semantic_text_retrieval")

        if graph_required:
            _append_tool(expected, "neo4j", allowed)
            reasons.append("relationship_path_required")
        elif graph_conditional:
            _append_tool(conditional, "neo4j", allowed)
            reasons.append("graph_only_if_text_evidence_is_insufficient")

        if route_decision == "rag_external_candidate":
            _append_tool(conditional, "official_api", allowed)
            _append_tool(conditional, "web", allowed)
            reasons.append("external_completion_only_after_internal_shortfall")

    expected_set = set(expected)
    conditional = [tool for tool in conditional if tool not in expected_set]
    selected_or_conditional = expected_set | set(conditional)
    forbidden = set(TOOL_ORDER) - selected_or_conditional
    minimum_evidence = 4 if envelope.risk_level in {"high", "critical"} else 3
    max_rounds = 2 if complex_request else 1
    needs = {
        "structured": "csa" in selected_or_conditional,
        "lexical": "bm25" in selected_or_conditional,
        "semantic": "dense" in selected_or_conditional,
        "graph_recall": graph_required and "neo4j" in allowed,
        "graph_recall_conditional": graph_conditional and "neo4j" in allowed,
        "graph_binding": (graph_required or graph_conditional) and "neo4j" in allowed,
        "entity_vector": (
            (graph_required or graph_conditional)
            and route_decision != "graph_first"
            and "neo4j" in allowed
        ),
        "external_completion": bool({"official_api", "web"} & selected_or_conditional),
    }
    if graph_required and "neo4j" not in allowed:
        reasons.append("required_graph_tool_denied_by_request_envelope")
    if route_decision == "csa" and "csa" not in allowed:
        reasons.append("required_structured_tool_denied_by_request_envelope")

    budgets = {
        tool: MappingProxyType(dict(TOOL_BUDGETS[tool]))
        for tool in _ordered(selected_or_conditional)
    }
    stop_conditions = (
        f"minimum_evidence:{minimum_evidence}",
        "all_required_relationships_bound" if graph_required else "internal_evidence_sufficient",
        f"max_rounds:{max_rounds}",
        "budget_exhausted",
    )
    stable_payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "request_fingerprint": envelope.fingerprint,
        "route_decision": route_decision,
        "expected_tools": list(_ordered(expected)),
        "conditional_tools": list(_ordered(conditional)),
        "max_rounds": max_rounds,
        "minimum_evidence": minimum_evidence,
        "needs": needs,
    }
    plan_id = hashlib.sha256(
        json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    return RetrievalPlan(
        plan_id=plan_id,
        mode="planner" if complex_request else "deterministic",
        route_decision=route_decision,
        expected_tools=_ordered(expected),
        conditional_tools=_ordered(conditional),
        forbidden_tools=_ordered(forbidden),
        denied_by_envelope=_ordered(denied),
        budgets=MappingProxyType(budgets),
        max_rounds=max_rounds,
        minimum_evidence=minimum_evidence,
        stop_conditions=stop_conditions,
        needs=MappingProxyType(needs),
        reasons=tuple(dict.fromkeys(reasons)),
        shadow_eligible=route_decision != "csa",
    )


def resolve_shadow_tools(
    plan: RetrievalPlan,
    *,
    candidate_counts: Mapping[str, int],
    unique_text_candidates: int,
) -> dict[str, Any]:
    """Resolve conditional tools against A's observed candidate pool only."""
    selected = list(plan.expected_tools)
    activated: list[str] = []
    unresolved: list[str] = []
    evidence_count = max(0, int(unique_text_candidates))

    for tool in plan.conditional_tools:
        activate = False
        if tool == "sqlite_exact":
            activate = int(candidate_counts.get(tool, 0)) > 0
        elif tool == "dense":
            activate = evidence_count < plan.minimum_evidence
        elif tool == "neo4j":
            activate = bool(plan.needs.get("graph_recall")) or evidence_count < plan.minimum_evidence
        elif tool in {"official_api", "web"}:
            activate = evidence_count < plan.minimum_evidence
            if activate and int(candidate_counts.get(tool, 0)) <= 0:
                unresolved.append(tool)
                continue

        if activate:
            selected.append(tool)
            activated.append(tool)
            if tool in {"bm25", "dense", "sqlite_exact"}:
                evidence_count = max(evidence_count, int(candidate_counts.get(tool, 0)))

    selected_tools = _ordered(selected)
    if plan.route_decision == "csa" and "csa" in selected_tools:
        stop_reason = "direct_structured_answer"
    elif plan.needs.get("graph_recall") and "neo4j" in selected_tools:
        stop_reason = "required_graph_round_complete"
    elif evidence_count >= plan.minimum_evidence:
        stop_reason = "sufficient_internal_evidence"
    elif unresolved:
        stop_reason = "conditional_tool_unavailable_in_shadow_pool"
    else:
        stop_reason = "candidate_pool_exhausted"

    return {
        "selected_tools": list(selected_tools),
        "activated_conditional_tools": list(_ordered(activated)),
        "unresolved_conditional_tools": list(_ordered(unresolved)),
        "rounds_used": min(1 + int(bool(activated or unresolved)), plan.max_rounds),
        "evidence_count": evidence_count,
        "stop_reason": stop_reason,
    }
