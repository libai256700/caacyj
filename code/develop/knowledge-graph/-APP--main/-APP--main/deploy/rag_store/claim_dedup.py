#!/usr/bin/env python3
"""Claim-level evidence aggregation for retrieval context."""

from __future__ import annotations

import json
import re
from typing import Any

from .knowledge_governance import (
    query_relevance_reviewer_allowed,
    canonical_claim_signature,
    normalize_term,
    stable_conflict_id,
    stable_cross_cluster_claim_key,
)


def _source_identity(source: dict[str, Any]) -> tuple[str, str]:
    return (
        str(source.get("chunk_id") or ""),
        str(source.get("source_doc") or source.get("doc_name") or ""),
    )


def _source_from_claim(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": str(row.get("chunk_id") or ""),
        "doc_name": str(row.get("source_doc") or ""),
        "source_doc": str(row.get("source_doc") or ""),
        "pdf_page_start": row.get("pdf_page_start"),
        "pdf_page_end": row.get("pdf_page_end"),
        "evidence_quote": str(row.get("evidence_quote") or ""),
        "confidence": row.get("source_confidence", row.get("confidence")),
        "content_type": row.get("content_type"),
    }


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for source in sources:
        key = _source_identity(source)
        if not any(key):
            continue
        quote = str(source.get("evidence_quote") or "").strip()
        if key not in by_identity:
            item = dict(source)
            item["evidence_quotes"] = [quote] if quote else []
            by_identity[key] = item
            continue
        existing = by_identity[key]
        if quote and quote not in existing["evidence_quotes"]:
            existing["evidence_quotes"].append(quote)
        for field in (
            "pdf_page_start",
            "pdf_page_end",
            "confidence",
            "content_type",
        ):
            if existing.get(field) is None and source.get(field) is not None:
                existing[field] = source[field]
    return sorted(
        by_identity.values(),
        key=lambda item: (_source_identity(item), item.get("pdf_page_start") or 0),
    )


def _normalized_plain_string_value(row: dict[str, Any]) -> str:
    try:
        value = json.loads(str(row.get("value_json") or '""'))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\W_]+", "", normalize_term(value))


def _normalized_topic_variants(value: Any) -> set[str]:
    normalized = re.sub(r"[\W_]+", "", normalize_term(value))
    variants = {normalized} if normalized else set()
    for prefix in ("民用无人机", "无人机"):
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            variants.add(normalized[len(prefix):])
    return variants


def _compatible_textbook_topics(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if str(left.get("_dedup_entity_type") or "") != str(
        right.get("_dedup_entity_type") or ""
    ):
        return False
    return bool(
        _normalized_topic_variants(left.get("_dedup_canonical_name"))
        & _normalized_topic_variants(right.get("_dedup_canonical_name"))
    )


def _dedupe_equivalent_textbook_fact_results(
    results: list[dict[str, Any]],
    source_groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fold exact cross-book facts after conflict governance has completed."""
    group_by_claim = {
        str(group.get("claim_id") or ""): dict(group)
        for group in source_groups
        if group.get("claim_id")
    }
    ranked = sorted(
        results,
        key=lambda row: (
            -int(row.get("authority_rank") or 0),
            -float(row.get("score") or 0),
            str(row.get("doc_name") or ""),
            str(row.get("chunk_id") or ""),
            str(row.get("claim_id") or ""),
        ),
    )
    retained: list[dict[str, Any]] = []
    retained_groups: list[dict[str, Any]] = []
    candidates_by_signature: dict[tuple[str, str, str, str], list[int]] = {}

    for result in ranked:
        claim_id = str(result.get("claim_id") or "")
        source_group = group_by_claim.get(claim_id)
        value = str(result.get("_dedup_plain_string_value") or "")
        signature = (
            value,
            normalize_term(result.get("_dedup_unit") or ""),
            normalize_term(result.get("_dedup_polarity") or "positive"),
            str(result.get("_dedup_entity_type") or ""),
        )
        is_candidate = bool(
            source_group
            and len(value) >= 12
            and normalize_term(result.get("_dedup_authority") or "") == "textbook"
            and normalize_term(result.get("_dedup_conflict_status") or "clear")
            == "clear"
        )
        duplicate_index = None
        if is_candidate:
            for retained_index in candidates_by_signature.get(signature, []):
                representative = retained[retained_index]
                if str(representative.get("doc_name") or "") == str(
                    result.get("doc_name") or ""
                ):
                    continue
                if _compatible_textbook_topics(representative, result):
                    duplicate_index = retained_index
                    break

        if duplicate_index is None:
            retained_index = len(retained)
            retained.append(result)
            retained_groups.append(source_group or {})
            if is_candidate:
                candidates_by_signature.setdefault(signature, []).append(retained_index)
            continue

        representative = retained[duplicate_index]
        representative_group = retained_groups[duplicate_index]
        supporting_sources = _dedupe_sources([
            *(representative.get("supporting_sources") or []),
            source_group.get("representative_source") or {},
            *(source_group.get("supporting_sources") or []),
        ])
        representative["supporting_sources"] = supporting_sources
        representative_group["supporting_sources"] = supporting_sources
        representative_group["suppressed_count"] = len(supporting_sources)

    private_fields = (
        "_dedup_plain_string_value",
        "_dedup_unit",
        "_dedup_polarity",
        "_dedup_entity_type",
        "_dedup_canonical_name",
        "_dedup_authority",
        "_dedup_conflict_status",
    )
    for result in retained:
        for field in private_fields:
            result.pop(field, None)
    return retained, [group for group in retained_groups if group]


def _claim_signature(row: dict[str, Any]) -> tuple[Any, str, str]:
    value = row.get("value_json")
    if value in (None, ""):
        value = json.dumps(
            row.get("normalized_value") or "",
            ensure_ascii=False,
        )
    return canonical_claim_signature(
        value,
        str(row.get("unit") or ""),
        str(row.get("polarity") or "positive"),
        serialized_value=True,
    )


def _canonical_claim_scope(row: dict[str, Any]) -> str | None:
    return _canonical_scope(row.get("scope_json"))


_QUANTITY_DIMENSION_PATTERNS = (
    (
        "duration",
        re.compile(r"^(?:s|sec|second|seconds|min|minute|minutes|h|hr|hour|hours|秒|分钟|小时)$"),
        re.compile(r"(?:续航|航时|飞行时间|飞行时长|持续时间|能飞多久|多长时间|时间|时长)"),
    ),
    (
        "mass",
        re.compile(r"^(?:mg|g|kg|t|ton|tons|lb|lbs|毫克|克|千克|公斤|吨)$"),
        re.compile(r"(?:质量|重量|全重|载重|载荷|空机质量|起飞重量)"),
    ),
    (
        "speed",
        re.compile(r"^(?:m/s|km/h|kmh|kph|kt|kts|knot|knots|米/秒|千米/小时|节)$"),
        re.compile(r"(?:速度|航速|飞行速率|上升率|下降率)"),
    ),
    (
        "area",
        re.compile(r"^(?:mm2|cm2|m2|km2|mm²|cm²|m²|km²|平方毫米|平方厘米|平方米|平方千米)$"),
        re.compile(r"(?:面积|翼面积|旋翼盘面积)"),
    ),
    (
        "temperature",
        re.compile(r"^(?:c|°c|℃|k|开尔文|摄氏度)$"),
        re.compile(r"(?:温度|摄氏|开尔文)"),
    ),
    (
        "cost",
        re.compile(r"^(?:cny|rmb|usd|eur|元|人民币|美元|欧元)$"),
        re.compile(r"(?:价格|费用|收费|成本|学费|金额)"),
    ),
    (
        "length_or_altitude",
        re.compile(r"^(?:mm|cm|m|km|ft|feet|毫米|厘米|米|千米|英尺)$"),
        re.compile(r"(?:高度|长度|距离|航程|翼展|升限|半径)"),
    ),
)


def _claim_quantity_dimensions(row: dict[str, Any]) -> set[str]:
    unit = re.sub(r"\s+", "", normalize_term(row.get("unit") or ""))
    searchable = normalize_term(
        " ".join(
            str(row.get(field) or "")
            for field in (
                "canonical_name",
                "normalized_value",
                "evidence_quote",
                "predicate",
            )
        )
    )
    dimensions: set[str] = set()
    for dimension, unit_pattern, cue_pattern in _QUANTITY_DIMENSION_PATTERNS:
        if (unit and unit_pattern.search(unit)) or cue_pattern.search(searchable):
            dimensions.add(dimension)
    return dimensions


def _claims_share_hard_topic(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    """Return topic overlap that an alias contract is not allowed to override."""
    left_cluster = str(left.get("concept_cluster_id") or "")
    right_cluster = str(right.get("concept_cluster_id") or "")
    if left_cluster and left_cluster == right_cluster:
        return True
    left_subject = str(left.get("subject_key") or "")
    right_subject = str(right.get("subject_key") or "")
    if left_subject and left_subject == right_subject:
        return True
    if _claim_quantity_dimensions(left) & _claim_quantity_dimensions(right):
        return True
    left_name = normalize_term(left.get("canonical_name") or "")
    right_name = normalize_term(right.get("canonical_name") or "")
    return bool(
        left_name
        and left_name == right_name
        and str(left.get("predicate") or "").upper().strip()
        == str(right.get("predicate") or "").upper().strip()
        and _canonical_claim_scope(left) is not None
        and _canonical_claim_scope(left) == _canonical_claim_scope(right)
    )


def _claim_query_score(
    row: dict[str, Any],
    query: str,
    keywords: list[str],
) -> int:
    """Return a conservative lexical relevance score for one governed claim."""
    query_text = re.sub(r"\s+", "", str(query or "")).lower()
    canonical_name = re.sub(
        r"\s+", "", str(row.get("canonical_name") or "")
    ).lower()
    normalized_value = re.sub(
        r"\s+", "", str(row.get("normalized_value") or "")
    ).lower()
    evidence_quote = re.sub(
        r"\s+", "", str(row.get("evidence_quote") or "")
    ).lower()
    searchable = " ".join((canonical_name, normalized_value, evidence_quote))

    score = 0
    if len(canonical_name) >= 2 and canonical_name in query_text:
        score += 100 + len(canonical_name)
    if len(normalized_value) >= 2 and normalized_value in query_text:
        score += 80 + len(normalized_value)
    if len(query_text) >= 4 and query_text in evidence_quote:
        score += 60 + len(query_text)

    seen = set()
    for raw_term in keywords:
        term = re.sub(r"\s+", "", str(raw_term or "")).lower()
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        if term in searchable:
            score += 10 + len(term)
    return score


def _canonical_scope(value: Any) -> str | None:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return json.dumps(
        parsed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_relevance_term(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).lower()


def _validated_query_aliases(row: dict[str, Any]) -> tuple[str, ...] | None:
    """Validate one human-reviewed query-relevance contract.

    A lexical miss is not evidence of irrelevance.  This contract is the only
    mechanism allowed to declare an exhaustive alias set for the exact claim,
    predicate, and scope being quarantined.
    """
    contract = row.get("query_relevance_contract")
    if not isinstance(contract, dict):
        return None
    if contract.get("review_status") != "approved":
        return None
    if not str(contract.get("decision_id") or "").strip():
        return None
    reviewed_by = str(contract.get("reviewed_by") or "").strip()
    if not reviewed_by or not query_relevance_reviewer_allowed(contract, reviewed_by):
        return None
    if not str(contract.get("reviewed_at") or "").strip():
        return None
    if contract.get("aliases_complete") is not True:
        return None

    claim_id = str(row.get("claim_id") or "")
    if not claim_id or str(contract.get("claim_id") or "") != claim_id:
        return None
    predicate = str(row.get("predicate") or "").upper().strip()
    contract_predicate = str(contract.get("predicate") or "").upper().strip()
    if not predicate or contract_predicate != predicate:
        return None
    row_scope = _canonical_scope(row.get("scope_json"))
    contract_scope = _canonical_scope(contract.get("scope_json"))
    if row_scope is None or contract_scope != row_scope:
        return None

    raw_aliases = contract.get("query_aliases")
    if not isinstance(raw_aliases, list) or not raw_aliases:
        return None
    if any(not isinstance(alias, str) or not alias.strip() for alias in raw_aliases):
        return None
    aliases = tuple(_normalize_relevance_term(alias) for alias in raw_aliases)
    if any(len(alias) < 2 for alias in aliases):
        return None
    return tuple(dict.fromkeys(aliases))


def _reviewed_contract_proves_query_irrelevant(
    candidate: dict[str, Any],
    query: str,
    keywords: list[str],
) -> bool:
    """Return true only when complete reviewed contracts exclude this query."""
    claim_ids = {
        str(claim_id)
        for claim_id in candidate.get("claim_ids") or []
        if claim_id
    }
    if not claim_ids:
        return False
    expected_claim_counts = candidate.get("expected_claim_counts") or set()
    if len(expected_claim_counts) != 1:
        return False
    expected_claim_count = next(iter(expected_claim_counts))
    complete_visible_set = len(claim_ids) == expected_claim_count

    aliases_by_claim: dict[str, tuple[str, ...]] = {}
    for row in candidate.get("rows") or []:
        claim_id = str(row.get("claim_id") or "")
        aliases = _validated_query_aliases(row)
        if claim_id in claim_ids and aliases is not None:
            aliases_by_claim[claim_id] = aliases
    if set(aliases_by_claim) != claim_ids:
        return False

    if not complete_visible_set:
        return False

    query_terms = [_normalize_relevance_term(query)]
    query_terms.extend(_normalize_relevance_term(term) for term in keywords)
    query_terms = [term for term in dict.fromkeys(query_terms) if len(term) >= 2]
    for aliases in aliases_by_claim.values():
        if any(
            alias in term or term in alias
            for alias in aliases
            for term in query_terms
        ):
            return False
    return True


def aggregate_claim_evidence(
    enriched_results: list[dict[str, Any]],
    governance: dict[str, Any],
    *,
    query: str = "",
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate governed claims and preserve legacy chunks unchanged.

    A governed chunk is rendered as one virtual evidence item per claim.  This
    avoids reintroducing duplicate prose from a chunk containing several facts.
    Claims are merged only when their value, unit, and polarity signatures are
    exactly equal.  Divergent signatures are quarantined as a conflict.
    """
    keywords = keywords or []
    by_chunk = governance.get("by_chunk") or {}
    provenance = governance.get("provenance") or {}
    supporting_by_claim = governance.get("supporting_sources") or {}
    unresolved = governance.get("unresolved_conflicts") or {}

    explicit_conflicts_by_claim_key: dict[str, set[str]] = {}
    blocked_claim_keys: set[str] = set()
    conflict_candidates: dict[str, dict[str, Any]] = {}
    for chunk_id, rows in unresolved.items():
        if (provenance.get(chunk_id) or {}).get("content_type") == "exercise":
            continue
        for row in rows:
            if row.get("conflict_id"):
                conflict_id = str(row["conflict_id"])
                conflict_claim_key = str(
                    row.get("conflict_claim_key") or row.get("claim_key") or ""
                )
                candidate = conflict_candidates.setdefault(conflict_id, {
                    "conflict_id": conflict_id,
                    "concept_cluster_id": str(
                        row.get("conflict_concept_cluster_id")
                        or row.get("concept_cluster_id")
                        or ""
                    ),
                    "claim_key": conflict_claim_key,
                    "claim_ids": set(),
                    "chunk_ids": set(),
                    "rows": [],
                    "expected_claim_counts": set(),
                    "persisted": True,
                    "cross_cluster": conflict_claim_key.startswith(
                        "claim-cross-slot:"
                    ),
                })
                candidate["chunk_ids"].add(str(chunk_id))
                if row.get("claim_id"):
                    candidate["claim_ids"].add(str(row["claim_id"]))
                try:
                    conflict_claim_count = int(row.get("conflict_claim_count") or 0)
                except (TypeError, ValueError):
                    conflict_claim_count = 0
                if conflict_claim_count > 0:
                    candidate["expected_claim_counts"].add(conflict_claim_count)
                candidate["rows"].append(row)
                if row.get("claim_key"):
                    explicit_conflicts_by_claim_key.setdefault(
                        str(row["claim_key"]), set()
                    ).add(conflict_id)
            if row.get("claim_key"):
                blocked_claim_keys.add(str(row["claim_key"]))
    for rows in by_chunk.values():
        for row in rows:
            if normalize_term(row.get("conflict_status") or "") in {
                "blocking",
                "pending",
                "in_review",
                "unresolved",
            } and row.get("claim_key"):
                blocked_claim_keys.add(str(row["claim_key"]))

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    legacy_results: list[dict[str, Any]] = []
    excluded_exercise_ids: list[str] = []
    quarantined_conflict_chunk_ids: list[str] = []

    for result in enriched_results:
        chunk_id = str(result.get("chunk_id") or "")
        chunk_provenance = provenance.get(chunk_id) or {}
        if chunk_provenance.get("content_type") == "exercise":
            excluded_exercise_ids.append(chunk_id)
            continue

        retrieval_result = dict(result)
        if chunk_provenance.get("content_type"):
            retrieval_result["content_type"] = chunk_provenance["content_type"]

        claims = by_chunk.get(chunk_id) or []
        if not claims:
            if unresolved.get(chunk_id):
                # A pending/unapproved claim can be absent from ``by_chunk``.
                # Never fall back to rendering the whole legacy chunk in that
                # case, because it would re-expose the quarantined statement.
                quarantined_conflict_chunk_ids.append(chunk_id)
                continue
            legacy = retrieval_result
            legacy["governed_claim"] = False
            legacy_results.append(legacy)
            continue

        for claim in claims:
            row = {**claim, "retrieval": retrieval_result}
            claim_key = str(claim["claim_key"])
            if normalize_term(claim.get("conflict_status") or "") == "resolved":
                claim_key += "\x00resolved\x00" + str(claim.get("claim_id") or "")
            key = (str(claim["concept_cluster_id"]), claim_key)
            groups.setdefault(key, []).append(row)

    governed_results: list[dict[str, Any]] = []
    deduplicated_sources: list[dict[str, Any]] = []
    safe_claim_rows: list[dict[str, Any]] = []
    runtime_conflicts: list[dict[str, Any]] = []

    # A concept extraction split can leave the same named subject in multiple
    # clusters (for example KnowledgePoint vs AircraftType).  Compare those
    # slots before rendering either version as governed evidence.
    cross_topics: dict[
        tuple[str, str, str],
        list[tuple[tuple[str, str], dict[str, Any]]],
    ] = {}
    for group_key, rows in groups.items():
        for row in rows:
            canonical_name = normalize_term(row.get("canonical_name") or "")
            predicate = str(row.get("predicate") or "").upper().strip()
            scope = _canonical_claim_scope(row)
            if canonical_name and predicate and scope is not None:
                cross_topics.setdefault(
                    (canonical_name, predicate, scope), []
                ).append((group_key, row))

    cross_blocked_groups: set[tuple[str, str]] = set()
    equivalent_cross_groups: dict[
        tuple[str, str], list[tuple[str, str]]
    ] = {}
    for (canonical_name, predicate, scope), members in sorted(cross_topics.items()):
        rows_by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for group_key, row in members:
            rows_by_group.setdefault(group_key, []).append(row)
        cluster_ids = {group_key[0] for group_key in rows_by_group}
        group_signatures = {
            group_key: {_claim_signature(row) for row in topic_rows}
            for group_key, topic_rows in rows_by_group.items()
        }
        if len(cluster_ids) < 2 or any(
            len(signatures) != 1 for signatures in group_signatures.values()
        ):
            continue
        distinct_signatures = {
            next(iter(signatures)) for signatures in group_signatures.values()
        }
        if len(distinct_signatures) == 1:
            ordered_group_keys = sorted(rows_by_group)
            if any(group_key[1] in blocked_claim_keys for group_key in ordered_group_keys):
                cross_blocked_groups.update(ordered_group_keys)
            else:
                equivalent_cross_groups[ordered_group_keys[0]] = ordered_group_keys[1:]
            continue
        cross_claim_key = stable_cross_cluster_claim_key(
            canonical_name,
            predicate,
            json.loads(scope),
        )
        conflict_id = stable_conflict_id(cross_claim_key)
        topic_rows = [row for rows in rows_by_group.values() for row in rows]
        candidate = conflict_candidates.get(conflict_id)
        if candidate is None:
            candidate = {
                "conflict_id": conflict_id,
                "concept_cluster_id": sorted(cluster_ids)[0],
                "claim_key": cross_claim_key,
                "claim_ids": set(),
                "chunk_ids": set(),
                "rows": [],
                "expected_claim_counts": set(),
                "persisted": False,
                "cross_cluster": True,
            }
            conflict_candidates[conflict_id] = candidate
        candidate["claim_ids"].update(
            str(row.get("claim_id")) for row in topic_rows if row.get("claim_id")
        )
        candidate["chunk_ids"].update(
            str(row.get("chunk_id")) for row in topic_rows if row.get("chunk_id")
        )
        candidate["rows"].extend(topic_rows)
        candidate["cross_cluster"] = True
        cross_blocked_groups.update(rows_by_group)

    for primary_group, duplicate_groups in equivalent_cross_groups.items():
        for duplicate_group in duplicate_groups:
            groups[primary_group].extend(groups.pop(duplicate_group, []))

    for (cluster_id, claim_key), rows in sorted(groups.items()):
        if (cluster_id, claim_key) in cross_blocked_groups:
            continue
        source_claim_key = str(rows[0].get("claim_key") or claim_key)
        signatures = {_claim_signature(row) for row in rows}
        if source_claim_key in blocked_claim_keys or len(signatures) != 1:
            explicit_ids = explicit_conflicts_by_claim_key.get(source_claim_key) or set()
            conflict_ids = explicit_ids or {stable_conflict_id(source_claim_key)}
            for conflict_id in conflict_ids:
                candidate = conflict_candidates.setdefault(conflict_id, {
                    "conflict_id": conflict_id,
                    "concept_cluster_id": cluster_id,
                    "claim_key": source_claim_key,
                    "claim_ids": set(),
                    "chunk_ids": set(),
                    "rows": [],
                    "expected_claim_counts": set(),
                    "persisted": bool(explicit_ids),
                })
                candidate["claim_ids"].update(
                    str(row.get("claim_id")) for row in rows if row.get("claim_id")
                )
                candidate["chunk_ids"].update(
                    str(row.get("chunk_id")) for row in rows if row.get("chunk_id")
                )
                candidate["rows"].extend(rows)
            continue

        ranked = sorted(
            rows,
            key=lambda row: (
                -int(row.get("authority_rank") or 0),
                -float((row.get("retrieval") or {}).get("score") or 0),
                str(row.get("source_doc") or ""),
                str(row.get("chunk_id") or ""),
                str(row.get("claim_id") or ""),
            ),
        )
        representative = ranked[0]
        retrieval = dict(representative["retrieval"])
        representative_source = _source_from_claim(representative)

        all_sources = [_source_from_claim(row) for row in rows]
        for row in rows:
            for source in supporting_by_claim.get(str(row.get("claim_id") or ""), []):
                all_sources.append({
                    "chunk_id": str(source.get("chunk_id") or ""),
                    "doc_name": str(source.get("source_doc") or ""),
                    "source_doc": str(source.get("source_doc") or ""),
                    "pdf_page_start": source.get("pdf_page_start"),
                    "pdf_page_end": source.get("pdf_page_end"),
                    "evidence_quote": str(source.get("evidence_quote") or ""),
                    "confidence": source.get("confidence"),
                    "content_type": source.get("content_type"),
                })
        all_sources = _dedupe_sources(all_sources)
        supporting_sources = [
            source
            for source in all_sources
            if _source_identity(source) != _source_identity(representative_source)
        ]

        evidence_quote = str(representative.get("evidence_quote") or "").strip()
        if not evidence_quote:
            try:
                value = json.loads(str(representative.get("value_json") or '""'))
            except (TypeError, ValueError, json.JSONDecodeError):
                value = representative.get("normalized_value") or ""
            evidence_quote = f"{representative.get('canonical_name', '')}: {value}"

        retrieval.update({
            "chunk_id": representative_source["chunk_id"],
            "doc_name": representative_source["doc_name"],
            "text": evidence_quote,
            "expanded_text": evidence_quote,
            "expanded_chunk_ids": [representative_source["chunk_id"]],
            "governed_claim": True,
            "concept_cluster_id": cluster_id,
            "claim_key": source_claim_key,
            "claim_id": representative.get("claim_id"),
            "authority": representative.get("authority"),
            "supporting_sources": supporting_sources,
            "source_pages": [
                representative_source.get("pdf_page_start"),
                representative_source.get("pdf_page_end"),
            ],
            "_dedup_plain_string_value": _normalized_plain_string_value(
                representative
            ),
            "_dedup_unit": representative.get("unit"),
            "_dedup_polarity": representative.get("polarity"),
            "_dedup_entity_type": representative.get("entity_type"),
            "_dedup_canonical_name": representative.get("canonical_name"),
            "_dedup_authority": representative.get("authority"),
            "_dedup_conflict_status": representative.get("conflict_status"),
        })
        governed_results.append(retrieval)
        safe_claim_rows.extend(rows)
        deduplicated_sources.append({
            "concept_cluster_id": cluster_id,
            "claim_key": source_claim_key,
            "claim_id": representative.get("claim_id"),
            "representative_source": representative_source,
            "supporting_sources": supporting_sources,
            "suppressed_count": len(supporting_sources),
        })

    governed_results, deduplicated_sources = _dedupe_equivalent_textbook_fact_results(
        governed_results,
        deduplicated_sources,
    )

    combined = [*governed_results, *legacy_results]
    combined.sort(
        key=lambda row: (
            -float(row.get("score") or 0),
            0 if row.get("governed_claim") else 1,
            str(row.get("concept_cluster_id") or ""),
            str(row.get("claim_key") or row.get("chunk_id") or ""),
        )
    )
    best_safe_score = max(
        (_claim_query_score(row, query, keywords) for row in safe_claim_rows),
        default=0,
    )
    blocking_conflict_ids = []
    isolated_conflict_ids = []
    for conflict_id, candidate in sorted(conflict_candidates.items()):
        conflict_score = max(
            (
                _claim_query_score(row, query, keywords)
                for row in candidate.get("rows") or []
            ),
            default=0,
        )
        # Conflicting evidence is always quarantined.  A lexical zero is
        # unknown, not proof of irrelevance: only a complete, human-reviewed
        # contract may isolate a conflict from a clearly matched safe claim.
        hard_topic_overlap = any(
            _claims_share_hard_topic(safe_row, conflict_row)
            for safe_row in safe_claim_rows
            for conflict_row in candidate.get("rows") or []
        )
        reviewed_irrelevant = _reviewed_contract_proves_query_irrelevant(
            candidate,
            query,
            keywords,
        )
        if (
            best_safe_score <= 0
            or hard_topic_overlap
            or not reviewed_irrelevant
        ):
            blocking_conflict_ids.append(conflict_id)
        else:
            isolated_conflict_ids.append(conflict_id)
        quarantined_conflict_chunk_ids.extend(candidate.get("chunk_ids") or [])
        if not candidate.get("persisted"):
            runtime_conflicts.append({
                "conflict_id": conflict_id,
                "concept_cluster_id": candidate.get("concept_cluster_id"),
                "claim_key": candidate.get("claim_key"),
                "claim_ids": sorted(candidate.get("claim_ids") or []),
                "cross_cluster": bool(candidate.get("cross_cluster")),
            })

    return {
        "results": combined,
        "deduplicated_sources": deduplicated_sources,
        "conflict_ids": blocking_conflict_ids,
        "isolated_conflict_ids": isolated_conflict_ids,
        "review_required": bool(blocking_conflict_ids),
        "runtime_conflicts": runtime_conflicts,
        "excluded_exercise_chunk_ids": sorted(set(excluded_exercise_ids)),
        "quarantined_conflict_chunk_ids": sorted(
            set(quarantined_conflict_chunk_ids)
        ),
    }
