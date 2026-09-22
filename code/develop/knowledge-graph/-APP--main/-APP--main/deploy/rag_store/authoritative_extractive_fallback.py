#!/usr/bin/env python3
"""Bounded extractive recovery from finalized four-domain SQLite evidence."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

from .cloud_claim_evidence import FAIL_CLOSED_ANSWER


POLICY_VERSION = "authoritative-extractive-fallback-v4"
SQLITE_AUTHORITY_MARKER = "_sqlite_authority_resolved"
ALLOWED_DOC_PREFIXES = (
    "政策法规_",
    "政策法规/",
    "无人机理论书籍_",
    "无人机理论书籍/",
    "地面站考题考试条件/",
)
MAX_EXCERPTS = 4
MAX_EXCERPT_CHARS = 280
MAX_ANSWER_CHARS = 1200
_ANSWER_HEADING = "权威原文摘录："
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_ALNUM_TERM = re.compile(
    r"[a-z][a-z0-9_-]{2,}|\d+(?:\.\d+)+|\d+(?:\.\d+)?[a-z]+",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"[^\r\n。！？!?]+(?:[。！？!?]+|(?=\r?$))", re.MULTILINE)
_QUESTION_BOUNDARIES = (
    "请问", "请介绍", "请说明", "请给出", "请回答", "分别",
    "是什么", "有哪些", "是哪些", "为什么", "怎么样", "怎么", "如何",
    "是否", "应该", "应当", "需要", "可以", "能否", "什么", "哪些",
    "哪一个", "哪个", "哪一", "谁", "何处",
    "介绍", "说明", "给出", "回答", "告诉", "相关", "关于",
)
_GENERIC_QUERY_TERMS = frozenset({
    "无人机", "无人驾驶航空器", "航空器", "民用", "飞行", "相关",
    "规定", "要求", "条件", "内容", "情况", "信息", "资料", "问题",
    "条规定", "本规定", "本规则", "本办法",
})
_GENERIC_DOMAIN_PHRASES = ("民用无人驾驶航空器", "无人驾驶航空器", "航空器", "无人机")
_QUERY_CONJUNCTIONS = ("以及", "还有", "并且", "同时", "和", "与", "及", "、")
_CONDITION_OR_EXCEPTION = re.compile(
    r"但|但是|除非|除.{0,24}外|例外|否则|不适用|"
    r"可以不|可不|无需|豁免|仅当|只有|(?:情况|情形|条件)下"
)


def hydrate_sqlite_authority_sources(
    sources: Iterable[Mapping[str, Any]] | None,
    authority_rows: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return only sources whose exact chunk text resolved through SQLite."""
    by_chunk: dict[str, Mapping[str, Any]] = {}
    for row in authority_rows or ():
        if not isinstance(row, Mapping):
            continue
        chunk_id = row.get("chunk_id")
        text = row.get("text")
        doc_name = row.get("doc_name")
        if all(isinstance(value, str) and value.strip() for value in (chunk_id, text, doc_name)):
            by_chunk.setdefault(str(chunk_id).strip(), row)

    hydrated: list[dict[str, Any]] = []
    for source in sources or ():
        if not isinstance(source, Mapping):
            continue
        chunk_id = str(source.get("chunk_id") or "").strip()
        authority_row = by_chunk.get(chunk_id)
        if authority_row is None:
            continue
        item = dict(source)
        item["chunk_id"] = chunk_id
        item["text"] = str(authority_row["text"])
        item["doc_name"] = str(authority_row["doc_name"])
        item[SQLITE_AUTHORITY_MARKER] = True
        hydrated.append(item)
    return hydrated


def _normalize(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).lower()


def _normalized_query_content(question: str, *, split_conjunctions: bool) -> str:
    normalized = _normalize(question)
    for boundary in sorted(_QUESTION_BOUNDARIES, key=len, reverse=True):
        normalized = normalized.replace(boundary, " ")
    for generic_phrase in _GENERIC_DOMAIN_PHRASES:
        normalized = normalized.replace(generic_phrase, " ")
    for generic_term in sorted(_GENERIC_QUERY_TERMS, key=len, reverse=True):
        normalized = normalized.replace(generic_term, " ")
    if split_conjunctions:
        for conjunction in _QUERY_CONJUNCTIONS:
            normalized = normalized.replace(conjunction, " ")
    normalized = re.sub(r"[^a-z0-9_\-\.\u3400-\u9fff]+", " ", normalized)
    return normalized


def _query_terms(question: str) -> set[str]:
    """Extract conservative exact-match terms without depending on a tokenizer."""
    normalized = _normalized_query_content(question, split_conjunctions=False)

    terms = {
        match.group(0).lower()
        for match in _ALNUM_TERM.finditer(normalized)
    }
    for run in _CJK_RUN.findall(normalized):
        if 2 <= len(run) <= 12:
            terms.add(run)
        for width in (4, 3, 2):
            if len(run) < width:
                continue
            terms.update(run[index:index + width] for index in range(len(run) - width + 1))
    return {
        term
        for term in terms
        if term not in _GENERIC_QUERY_TERMS
        and not term.isdigit()
        and len(term) >= 2
    }


def _query_anchors(question: str) -> tuple[str, ...]:
    """Return distinguishing concepts that the recovered excerpts must all cover."""
    normalized = _normalized_query_content(question, split_conjunctions=True)
    anchors: list[str] = []
    for token in _ALNUM_TERM.findall(normalized):
        value = token.lower()
        if value not in _GENERIC_QUERY_TERMS and value not in anchors:
            anchors.append(value)
    for run in _CJK_RUN.findall(normalized):
        while len(run) > 2 and run[-1] in "的应需有":
            run = run[:-1]
        if len(run) >= 2 and run not in _GENERIC_QUERY_TERMS and run not in anchors:
            anchors.append(run)
    return tuple(anchors)


def _anchor_matches(anchor: str, normalized_sentence: str) -> bool:
    if anchor in normalized_sentence:
        return True
    if not _CJK_RUN.fullmatch(anchor) or len(anchor) < 5:
        return False
    required = len(anchor) - 1
    return any(
        anchor[index:index + required] in normalized_sentence
        for index in range(len(anchor) - required + 1)
    )


def _best_query_bound_sentence(
    text: str,
    query_terms: set[str],
    query_anchors: tuple[str, ...],
    source_identity: str,
) -> tuple[str, frozenset[str], int]:
    """Select one complete sentence with an explicit deterministic query match."""
    best: tuple[int, int, str, frozenset[str]] | None = None
    matches = list(_SENTENCE.finditer(text))
    for order, match in enumerate(matches):
        base_sentence = match.group(0).strip()
        if (
            not base_sentence
            or base_sentence[-1] not in "。！？!?"
        ):
            continue
        normalized_base = _normalize(base_sentence)
        sentence_anchors = frozenset(
            anchor
            for anchor in query_anchors
            if _anchor_matches(anchor, normalized_base)
        )
        if not sentence_anchors:
            continue
        normalized_identity = _normalize(source_identity)
        matched_anchors = sentence_anchors | frozenset(
            anchor
            for anchor in query_anchors
            if _anchor_matches(anchor, normalized_identity)
        )
        first = order
        last = order
        if order > 0 and _CONDITION_OR_EXCEPTION.search(matches[order - 1].group(0)):
            first -= 1
        while (
            last + 1 < len(matches)
            and _CONDITION_OR_EXCEPTION.search(matches[last + 1].group(0))
        ):
            last += 1
        sentence = text[matches[first].start():matches[last].end()].strip()
        if len(sentence) > MAX_EXCERPT_CHARS:
            continue
        normalized_sentence = _normalize(sentence)
        matched_terms = {term for term in query_terms if term in normalized_sentence}
        score = (
            sum(len(anchor) ** 3 for anchor in matched_anchors)
            + sum(len(term) * len(term) for term in matched_terms)
        )
        candidate = (score, -order, sentence, matched_anchors)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    return (best[2], best[3], best[0]) if best else ("", frozenset(), 0)


def build_authoritative_extractive_fallback(
    question: str,
    finalized_sources: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Build one claim per accepted excerpt, bound only to its source alias.

    The caller must pass sources produced by ``finalize_internal_sources`` and
    hydrated from authoritative SQLite rows. This function still revalidates
    identity, domain, text, complete-sentence bounds, deterministic question
    relevance, and duplicate aliases before extraction.
    """
    query_terms = _query_terms(question)
    query_anchors = _query_anchors(question)
    if not query_anchors:
        return {
            "answer": FAIL_CLOSED_ANSWER,
            "claim_map": {"claims": []},
            "recovered": False,
            "used_chunk_ids": [],
            "policy_version": POLICY_VERSION,
        }

    candidates: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    seen_aliases: set[str] = set()
    seen_excerpts: set[str] = set()

    for source_index, raw_source in enumerate(finalized_sources or (), start=1):
        if not isinstance(raw_source, Mapping):
            continue

        if raw_source.get(SQLITE_AUTHORITY_MARKER) is not True:
            continue
        chunk_id = raw_source.get("chunk_id")
        doc_name = raw_source.get("doc_name")
        text = raw_source.get("text")
        if not all(isinstance(value, str) and value.strip() for value in (chunk_id, doc_name, text)):
            continue
        chunk_id = chunk_id.strip()
        if not doc_name.startswith(ALLOWED_DOC_PREFIXES) or chunk_id in seen_chunk_ids:
            continue

        alias = f"S{raw_source.get('seq') or source_index}"
        if alias in seen_aliases:
            continue
        excerpt, matched_anchors, score = _best_query_bound_sentence(
            text,
            query_terms,
            query_anchors,
            doc_name,
        )
        if not excerpt or excerpt in seen_excerpts:
            continue
        candidates.append({
            "source_index": source_index,
            "chunk_id": chunk_id,
            "alias": alias,
            "excerpt": excerpt,
            "matched_anchors": matched_anchors,
            "score": score,
        })
        seen_chunk_ids.add(chunk_id)
        seen_aliases.add(alias)
        seen_excerpts.add(excerpt)

    selected: list[dict[str, Any]] = []
    uncovered = set(query_anchors)
    remaining_candidates = list(candidates)
    while uncovered and remaining_candidates and len(selected) < MAX_EXCERPTS:
        best = max(
            remaining_candidates,
            key=lambda item: (
                len(set(item["matched_anchors"]) & uncovered),
                item["score"],
                -item["source_index"],
            ),
        )
        newly_covered = set(best["matched_anchors"]) & uncovered
        if not newly_covered:
            break
        selected.append(best)
        uncovered -= newly_covered
        remaining_candidates.remove(best)

    if uncovered:
        return {
            "answer": FAIL_CLOSED_ANSWER,
            "claim_map": {"claims": []},
            "recovered": False,
            "used_chunk_ids": [],
            "policy_version": POLICY_VERSION,
        }

    selected.sort(key=lambda item: item["source_index"])
    excerpts = [str(item["excerpt"]) for item in selected]
    answer = _ANSWER_HEADING + "\n" + "\n\n".join(excerpts)
    if len(answer) > MAX_ANSWER_CHARS:
        return {
            "answer": FAIL_CLOSED_ANSWER,
            "claim_map": {"claims": []},
            "recovered": False,
            "used_chunk_ids": [],
            "policy_version": POLICY_VERSION,
        }
    claims = [
        {
            "claim_id": f"extractive:{index}",
            "text": item["excerpt"],
            "evidence": [item["alias"]],
            "risk": "high",
        }
        for index, item in enumerate(selected, start=1)
    ]

    return {
        "answer": answer,
        "claim_map": {"claims": claims},
        "recovered": True,
        "used_chunk_ids": [str(item["chunk_id"]) for item in selected],
        "policy_version": POLICY_VERSION,
    }
