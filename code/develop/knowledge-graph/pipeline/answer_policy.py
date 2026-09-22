"""Small, dependency-free response governance used by the local APP server."""

from __future__ import annotations

from typing import Any


EVIDENCE_BLOCKED_ANSWER = (
    "当前检索结果没有提供足够的可核对证据，系统已停止生成事实性答案。"
    "请补充问题范围或在数据与索引恢复后重试。"
)


def deduplicate_response_sources(sources: list[dict] | None) -> list[dict]:
    """Expose each SQLite-backed chunk once without changing stored data."""
    result = []
    seen_chunk_ids = set()
    for source in sources or []:
        if not isinstance(source, dict):
            result.append(source)
            continue
        chunk_id = str(source.get("chunk_id") or "")
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        result.append(source)
    return result


def normalize_response_evidence(
    evidence: list[dict] | None,
    sources: list[dict] | None,
) -> list[dict]:
    """Remove duplicate or orphan document evidence from the public response."""
    allowed_chunk_ids = {
        str(source.get("chunk_id") or "")
        for source in sources or []
        if isinstance(source, dict) and source.get("chunk_id")
    }
    result = []
    seen = set()
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or "")
        if item.get("type") == "document" and chunk_id not in allowed_chunk_ids:
            continue
        marker = (str(item.get("type") or ""), chunk_id, str(item.get("source_num") or ""))
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def govern_answer(
    answer: str,
    *,
    sources: list[dict] | None,
    evidence: list[dict] | None,
    risk_level: str,
) -> tuple[str, list[str]]:
    """Fail closed when a factual answer has no retrievable support."""
    reasons = []
    if not sources:
        reasons.append("answer_without_sources_blocked")
    elif risk_level in {"high", "critical"} and not evidence:
        reasons.append("high_risk_answer_without_evidence_blocked")
    if reasons:
        return EVIDENCE_BLOCKED_ANSWER, reasons
    return answer, reasons


def governance_response_fields(
    ctx_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize backward-compatible governance fields for API consumers."""
    ctx_result = ctx_result or {}
    conflict_ids = sorted({
        str(conflict_id)
        for conflict_id in ctx_result.get("conflict_ids", [])
        if conflict_id
    })
    deduplicated_sources = ctx_result.get("deduplicated_sources") or []
    if not isinstance(deduplicated_sources, list):
        deduplicated_sources = []
    return {
        "review_required": bool(conflict_ids),
        "conflict_ids": conflict_ids,
        "deduplicated_sources": deduplicated_sources,
        "governance_degraded": False,
    }
