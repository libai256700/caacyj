#!/usr/bin/env python3
"""Fail-closed source authority and supersession rules for the r9 cloud corpus."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any


REGULATION = "regulation"
COMPANY_POLICY = "company_policy"
TEXTBOOK = "textbook"
QUESTION_BANK = "question_bank"
UNKNOWN = "unknown"

TIER_RANK = {
    REGULATION: 100,
    COMPANY_POLICY: 80,
    TEXTBOOK: 60,
    QUESTION_BANK: 50,
    UNKNOWN: 0,
}
TIER_LABEL = {
    REGULATION: "法规",
    COMPANY_POLICY: "公司制度",
    TEXTBOOK: "教材",
    QUESTION_BANK: "题库",
    UNKNOWN: "其他资料",
}

TIMELINE_SCHEMA_VERSION = "cloud-v2-regulation-timeline-r9-v1"
SUPERSEDED_SCHEMA_VERSION = "cloud-v2-superseded-passages-r9-v1"
R9_REGULATION_DOCUMENT_COUNT = 7
FROZEN_R9_SOURCE_SCOPE = MappingProxyType(
    {
        "schema_version": "cloud-v2-source-scope-v1",
        "candidate_id": "revision-a-r9",
        "source_count": 35,
        "source_manifest_sha256": (
            "9e0f9018c9a72f2a99c19a7c6b2362cb49154233b770c8f7c41af0b48a3aa8fe"
        ),
        "allowlist_sha256": (
            "a5efe7537d9ab9de1624bf40e5cb944f95c35fb0252c04927f73886c1bb5d64f"
        ),
        "stop_a_receipt_sha256": (
            "4515475c1e89b85aea91eb912d238d0eb63776f82b75468ac4aecd8206c4ab6c"
        ),
        "source_dlp_receipt_sha256": (
            "ee460cfd8d35a6ace33d87c6f2f313e68e1ef6b5c5ceaa8b29fcb70950219123"
        ),
        "unchanged_source_count": 28,
        "approved_redacted_source_count": 7,
    }
)

_DOC_PREFIX_TIERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("政策法规_", "政策法规/", "法规_"), REGULATION),
    (("无人机理论书籍_", "无人机理论书籍/", "教材_", "理论书籍_"), TEXTBOOK),
    (
        (
            "理论题库_",
            "理论题库/",
            "实操题库_",
            "实操题库/",
            "题库_",
            "题库/",
        ),
        QUESTION_BANK,
    ),
)
_CHUNK_PREFIX_TIERS: tuple[tuple[str, str], ...] = (
    ("regulation:", REGULATION),
    ("textbook:", TEXTBOOK),
    ("question_bank:", QUESTION_BANK),
)
_STATUS_SORT = {"current": 0, "partially_superseded": 1, "superseded": 2}
_STATUS_LABEL = {
    "current": "现行",
    "partially_superseded": "部分被取代",
    "superseded": "已被取代",
}

REGULATION_TIMELINE_PATH = Path(__file__).with_name("regulation_timeline.json")
SUPERSEDED_PASSAGES_PATH = Path(__file__).with_name("superseded_passages.json")

_timeline_cache: dict[str, dict[str, Any]] | None = None
_passages_cache: list[dict[str, Any]] | None = None


class SourceAuthorityError(RuntimeError):
    """The frozen authority registry is missing, ambiguous, or unbound."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def governance_file_hashes() -> dict[str, str]:
    return {
        "timeline_sha256": _sha256_file(REGULATION_TIMELINE_PATH),
        "superseded_sha256": _sha256_file(SUPERSEDED_PASSAGES_PATH),
    }


def _strict_json_object_payload(payload: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise SourceAuthorityError(f"duplicate JSON key in {label}")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        raise SourceAuthorityError(f"non-finite JSON value in {label}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except SourceAuthorityError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceAuthorityError(f"invalid JSON in {label}") from exc
    if not isinstance(value, dict):
        raise SourceAuthorityError(f"{label} must contain an object")
    return value


def _strict_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise SourceAuthorityError(f"invalid JSON in {label}") from exc
    return _strict_json_object_payload(payload, label)


def _exact_mapping(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise SourceAuthorityError(f"{label} fields do not match the frozen schema")
    return dict(value)


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SourceAuthorityError(f"{label} must be non-empty text")
    return value


def _required_sha256(value: Any, label: str) -> str:
    normalized = _required_text(value, label)
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        raise SourceAuthorityError(f"{label} must be a lowercase SHA-256")
    return normalized


def _required_chunk_id(value: Any, label: str) -> str:
    normalized = _required_text(value, label)
    if re.fullmatch(r"chunk:[0-9a-f]{40}", normalized) is None:
        raise SourceAuthorityError(f"{label} must be an authority chunk id")
    return normalized


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SourceAuthorityError(f"{label} must be a positive integer")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label)


def _iso_date(value: Any, label: str, *, optional: bool = False) -> str | None:
    normalized = _optional_text(value, label) if optional else _required_text(value, label)
    if normalized is None:
        return None
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise SourceAuthorityError(f"{label} must be an ISO calendar date") from exc
    return normalized


def _text_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise SourceAuthorityError(f"{label} must be a text list")
    items = [_required_text(item, label) for item in value]
    if len(items) != len(set(items)):
        raise SourceAuthorityError(f"{label} contains duplicates")
    return items


def _validate_source_scope(value: Any, label: str) -> dict[str, Any]:
    scope = _exact_mapping(value, set(FROZEN_R9_SOURCE_SCOPE), label)
    if scope != dict(FROZEN_R9_SOURCE_SCOPE):
        raise SourceAuthorityError(f"{label} does not match revision-a-r9")
    return scope


def _registry_authority(
    value: Any, label: str, *, require_regulation_count: bool
) -> dict[str, Any]:
    fields = {"release_id", "database_sha256"}
    if require_regulation_count:
        fields.add("regulation_document_count")
    authority = _exact_mapping(value, fields, label)
    authority["release_id"] = _required_text(
        authority["release_id"], f"{label}.release_id"
    )
    if (
        re.fullmatch(
            r"rag-authority:revision-a-r9:[0-9a-f]{16}", authority["release_id"]
        )
        is None
    ):
        raise SourceAuthorityError(f"{label}.release_id is not revision-a-r9")
    authority["database_sha256"] = _required_sha256(
        authority["database_sha256"], f"{label}.database_sha256"
    )
    if require_regulation_count:
        authority["regulation_document_count"] = _positive_int(
            authority["regulation_document_count"],
            f"{label}.regulation_document_count",
        )
        if authority["regulation_document_count"] != R9_REGULATION_DOCUMENT_COUNT:
            raise SourceAuthorityError("regulation document count does not match r9")
    return authority


def _evidence_binding(value: Any, label: str, *, with_proofs: bool) -> dict[str, Any]:
    fields = {"chunk_id", "text_sha256"}
    if with_proofs:
        fields.update({"proofs", "required_markers"})
    evidence = _exact_mapping(value, fields, label)
    evidence["chunk_id"] = _required_chunk_id(
        evidence["chunk_id"], f"{label}.chunk_id"
    )
    evidence["text_sha256"] = _required_sha256(
        evidence["text_sha256"], f"{label}.text_sha256"
    )
    if with_proofs:
        evidence["proofs"] = _text_list(evidence["proofs"], f"{label}.proofs")
        if not set(evidence["proofs"]).issubset({"number", "effective_date"}):
            raise SourceAuthorityError(f"{label}.proofs contains an unsupported proof")
        evidence["required_markers"] = _text_list(
            evidence["required_markers"], f"{label}.required_markers"
        )
    return evidence


def _load_timeline_root(path: Path, *, payload: bytes | None = None) -> dict[str, Any]:
    root = _exact_mapping(
        (
            _strict_json_object(path, "regulation timeline")
            if payload is None
            else _strict_json_object_payload(payload, "regulation timeline")
        ),
        {"schema_version", "authority", "documents"},
        "regulation timeline",
    )
    if root["schema_version"] != TIMELINE_SCHEMA_VERSION:
        raise SourceAuthorityError("regulation timeline schema mismatch")
    root["authority"] = _registry_authority(
        root["authority"], "regulation timeline authority", require_regulation_count=True
    )
    documents = root["documents"]
    if not isinstance(documents, list) or len(documents) != R9_REGULATION_DOCUMENT_COUNT:
        raise SourceAuthorityError("regulation timeline must contain the seven r9 documents")
    normalized: dict[str, dict[str, Any]] = {}
    fields = {
        "doc_name",
        "short_name",
        "doc_type",
        "authority_rank",
        "number",
        "effective_date",
        "status",
        "evidence",
    }
    seen_evidence_chunks: set[str] = set()
    for raw_meta in documents:
        meta = _exact_mapping(raw_meta, fields, "regulation timeline document")
        name = _required_text(meta.pop("doc_name"), "regulation document name")
        if not name.startswith("政策法规/") or name in normalized:
            raise SourceAuthorityError("regulation document name is invalid")
        meta["short_name"] = _required_text(meta["short_name"], f"{name}.short_name")
        meta["doc_type"] = _required_text(meta["doc_type"], f"{name}.doc_type")
        meta["authority_rank"] = _positive_int(
            meta["authority_rank"], f"{name}.authority_rank"
        )
        meta["number"] = _required_text(meta["number"], f"{name}.number")
        meta["effective_date"] = _iso_date(meta["effective_date"], f"{name}.effective_date")
        meta["status"] = _required_text(meta["status"], f"{name}.status")
        if meta["status"] not in _STATUS_SORT:
            raise SourceAuthorityError(f"{name}.status is unsupported")
        if not isinstance(meta["evidence"], list) or not meta["evidence"]:
            raise SourceAuthorityError(f"{name}.evidence is absent")
        evidence = [
            _evidence_binding(item, f"{name}.evidence", with_proofs=True)
            for item in meta["evidence"]
        ]
        chunk_ids = {item["chunk_id"] for item in evidence}
        if len(chunk_ids) != len(evidence) or seen_evidence_chunks.intersection(chunk_ids):
            raise SourceAuthorityError("regulation evidence chunk id is duplicated")
        seen_evidence_chunks.update(chunk_ids)
        if {proof for item in evidence for proof in item["proofs"]} != {
            "number",
            "effective_date",
        }:
            raise SourceAuthorityError(
                f"{name}.evidence must bind both number and effective_date"
            )
        meta["evidence"] = evidence
        normalized[name] = meta
    root["documents"] = normalized
    return root


def _load_superseded_root(path: Path, *, payload: bytes | None = None) -> dict[str, Any]:
    root = _exact_mapping(
        (
            _strict_json_object(path, "superseded passages")
            if payload is None
            else _strict_json_object_payload(payload, "superseded passages")
        ),
        {"schema_version", "authority", "passages"},
        "superseded passages",
    )
    if root["schema_version"] != SUPERSEDED_SCHEMA_VERSION:
        raise SourceAuthorityError("superseded passage schema mismatch")
    root["authority"] = _registry_authority(
        root["authority"], "superseded passages authority", require_regulation_count=False
    )
    passages = root["passages"]
    if not isinstance(passages, list) or not passages:
        raise SourceAuthorityError("superseded passage registry is absent")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_chunk_ids: set[str] = set()
    fields = {
        "id",
        "doc_name",
        "chunks",
        "topic",
        "topic_markers",
        "keep_when_exact_question_match",
        "superseded_by",
        "reason_code",
    }
    for raw in passages:
        item = _exact_mapping(raw, fields, "superseded passage")
        item["id"] = _required_text(item["id"], "superseded passage id")
        if item["id"] in seen_ids:
            raise SourceAuthorityError("superseded passage id is duplicated")
        seen_ids.add(item["id"])
        item["doc_name"] = _required_text(item["doc_name"], f"{item['id']}.doc_name")
        declared_doc_names = [
            _required_text(name, f"{item['id']}.doc_name")
            for name in item["doc_name"].split(" and ")
        ]
        if (
            len(declared_doc_names) != len(set(declared_doc_names))
            or any("/" not in name for name in declared_doc_names)
        ):
            raise SourceAuthorityError(f"{item['id']}.doc_name is invalid")
        if not isinstance(item["chunks"], list) or not item["chunks"]:
            raise SourceAuthorityError(f"{item['id']}.chunks is absent")
        item["chunks"] = [
            _evidence_binding(chunk, f"{item['id']}.chunks", with_proofs=False)
            for chunk in item["chunks"]
        ]
        chunk_ids = [chunk["chunk_id"] for chunk in item["chunks"]]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise SourceAuthorityError("superseded chunk id is duplicated")
        if seen_chunk_ids.intersection(chunk_ids):
            raise SourceAuthorityError("superseded chunk id is registered twice")
        seen_chunk_ids.update(chunk_ids)
        item["topic"] = _required_text(item["topic"], f"{item['id']}.topic")
        item["topic_markers"] = _text_list(
            item["topic_markers"], f"{item['id']}.topic_markers"
        )
        if not isinstance(item["keep_when_exact_question_match"], bool):
            raise SourceAuthorityError(
                f"{item['id']}.keep_when_exact_question_match must be boolean"
            )
        if not isinstance(item["superseded_by"], list) or not item["superseded_by"]:
            raise SourceAuthorityError(f"{item['id']}.superseded_by is absent")
        targets: list[dict[str, Any]] = []
        seen_targets: set[tuple[str, str]] = set()
        for target in item["superseded_by"]:
            target_mapping = _exact_mapping(
                target,
                {"doc_name", "chunk_id", "text_sha256"},
                f"{item['id']}.superseded_by",
            )
            bound = _evidence_binding(
                {
                    "chunk_id": target_mapping["chunk_id"],
                    "text_sha256": target_mapping["text_sha256"],
                },
                f"{item['id']}.superseded_by",
                with_proofs=False,
            )
            bound["doc_name"] = _required_text(
                target_mapping["doc_name"],
                f"{item['id']}.superseded_by.doc_name",
            )
            target_key = (bound["doc_name"], bound["chunk_id"])
            if target_key in seen_targets:
                raise SourceAuthorityError("superseding evidence is duplicated")
            seen_targets.add(target_key)
            targets.append(bound)
        item["superseded_by"] = targets
        item["reason_code"] = _required_text(
            item["reason_code"], f"{item['id']}.reason_code"
        )
        item["declared_doc_names"] = declared_doc_names
        normalized.append(item)
    root["passages"] = normalized
    return root


def load_regulation_timeline(path: Path | None = None) -> dict[str, dict[str, Any]]:
    global _timeline_cache
    if path is None and _timeline_cache is not None:
        return _timeline_cache
    documents = _load_timeline_root(path or REGULATION_TIMELINE_PATH)["documents"]
    if path is None:
        _timeline_cache = documents
    return documents


def _project_superseded_passages(
    raw_passages: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "doc_name": item["doc_name"],
            "chunk_ids": [chunk["chunk_id"] for chunk in item["chunks"]],
            "topic": item["topic"],
            "topic_markers": list(item["topic_markers"]),
            "keep_when_exact_question_match": item["keep_when_exact_question_match"],
            "superseded_by": [target["doc_name"] for target in item["superseded_by"]],
            "reason": item["reason_code"],
        }
        for item in raw_passages
    ]


def load_superseded_passages(path: Path | None = None) -> list[dict[str, Any]]:
    global _passages_cache
    if path is None and _passages_cache is not None:
        return _passages_cache
    raw_passages = _load_superseded_root(path or SUPERSEDED_PASSAGES_PATH)["passages"]
    passages = _project_superseded_passages(raw_passages)
    if path is None:
        _passages_cache = passages
    return passages


def _validate_and_load_regulation_governance(
    authority_manifest: Mapping[str, Any],
    authority_rows: Sequence[Mapping[str, Any]],
    *,
    timeline_path: Path = REGULATION_TIMELINE_PATH,
    superseded_path: Path = SUPERSEDED_PASSAGES_PATH,
    timeline_payload: bytes | None = None,
    superseded_payload: bytes | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Bind both governance registries to the opened r9 SQLite authority rows."""

    source_scope = _validate_source_scope(
        authority_manifest.get("source_scope"), "authority source_scope"
    )
    if (timeline_payload is None) != (superseded_payload is None):
        raise SourceAuthorityError("regulation governance payload set is incomplete")
    timeline = _load_timeline_root(timeline_path, payload=timeline_payload)
    superseded = _load_superseded_root(
        superseded_path,
        payload=superseded_payload,
    )
    database = authority_manifest.get("database")
    if not isinstance(database, Mapping):
        raise SourceAuthorityError("authority database binding is absent")
    authority_binding = {
        "release_id": _required_text(
            authority_manifest.get("release_id"), "authority release_id"
        ),
        "database_sha256": _required_sha256(
            database.get("sha256"), "authority database sha256"
        ),
    }
    if (
        timeline["authority"]["release_id"] != authority_binding["release_id"]
        or timeline["authority"]["database_sha256"]
        != authority_binding["database_sha256"]
        or superseded["authority"] != authority_binding
    ):
        raise SourceAuthorityError("governance registry authority binding mismatch")
    rows_by_id: dict[str, Mapping[str, Any]] = {}
    regulation_documents: set[str] = set()
    for row in authority_rows:
        chunk_id = _required_text(row.get("chunk_id"), "authority chunk_id")
        doc_name = _required_text(row.get("doc_name"), "authority doc_name")
        raw_text = row.get("text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise SourceAuthorityError("authority text must be non-empty text")
        text = raw_text
        if chunk_id in rows_by_id:
            raise SourceAuthorityError("authority chunk id is duplicated")
        rows_by_id[chunk_id] = {
            "chunk_id": chunk_id,
            "doc_name": doc_name,
            "text": text,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
        if doc_name.startswith("政策法规/"):
            regulation_documents.add(doc_name)

    documents = timeline["documents"]
    if set(documents) != regulation_documents:
        raise SourceAuthorityError("regulation timeline does not exactly cover r9 documents")
    for doc_name, meta in documents.items():
        for evidence in meta["evidence"]:
            row = rows_by_id.get(evidence["chunk_id"])
            if (
                row is None
                or row["doc_name"] != doc_name
                or row["text_sha256"] != evidence["text_sha256"]
            ):
                raise SourceAuthorityError("regulation timeline evidence binding mismatch")
            if any(marker not in row["text"] for marker in evidence["required_markers"]):
                raise SourceAuthorityError("regulation timeline evidence text mismatch")

    for passage in superseded["passages"]:
        observed_doc_names: set[str] = set()
        for evidence in passage["chunks"]:
            row = rows_by_id.get(evidence["chunk_id"])
            if (
                row is None
                or row["doc_name"] not in passage["declared_doc_names"]
                or row["text_sha256"] != evidence["text_sha256"]
            ):
                raise SourceAuthorityError("superseded passage evidence binding mismatch")
            observed_doc_names.add(str(row["doc_name"]))
        if observed_doc_names != set(passage["declared_doc_names"]):
            raise SourceAuthorityError("superseded passage document coverage mismatch")
        for target in passage["superseded_by"]:
            row = rows_by_id.get(target["chunk_id"])
            if (
                target["doc_name"] not in documents
                or row is None
                or row["doc_name"] != target["doc_name"]
                or row["text_sha256"] != target["text_sha256"]
            ):
                raise SourceAuthorityError("superseding regulation evidence mismatch")
    validation = {
        "schema_version": "cloud-regulation-governance-validation-v1",
        "status": "passed",
        "source_scope": source_scope,
        "authority": authority_binding,
        "timeline_sha256": (
            _sha256_file(timeline_path)
            if timeline_payload is None
            else hashlib.sha256(timeline_payload).hexdigest()
        ),
        "superseded_sha256": (
            _sha256_file(superseded_path)
            if superseded_payload is None
            else hashlib.sha256(superseded_payload).hexdigest()
        ),
        "regulation_document_count": len(documents),
        "superseded_passage_count": len(superseded["passages"]),
        "superseded_chunk_count": sum(
            len(item["chunks"]) for item in superseded["passages"]
        ),
    }
    runtime_timeline = {
        doc_name: {
            key: value
            for key, value in meta.items()
            if key != "evidence"
        }
        for doc_name, meta in documents.items()
    }
    runtime_passages = _project_superseded_passages(superseded["passages"])
    return validation, runtime_timeline, runtime_passages


def load_bound_regulation_governance(
    authority_manifest: Mapping[str, Any],
    authority_rows: Sequence[Mapping[str, Any]],
    *,
    timeline_path: Path = REGULATION_TIMELINE_PATH,
    superseded_path: Path = SUPERSEDED_PASSAGES_PATH,
    timeline_payload: bytes | None = None,
    superseded_payload: bytes | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Validate once and return the exact normalized registries used at runtime."""

    return _validate_and_load_regulation_governance(
        authority_manifest,
        authority_rows,
        timeline_path=timeline_path,
        superseded_path=superseded_path,
        timeline_payload=timeline_payload,
        superseded_payload=superseded_payload,
    )


def validate_regulation_governance(
    authority_manifest: Mapping[str, Any],
    authority_rows: Sequence[Mapping[str, Any]],
    *,
    timeline_path: Path = REGULATION_TIMELINE_PATH,
    superseded_path: Path = SUPERSEDED_PASSAGES_PATH,
) -> dict[str, Any]:
    validation, _timeline, _passages = load_bound_regulation_governance(
        authority_manifest,
        authority_rows,
        timeline_path=timeline_path,
        superseded_path=superseded_path,
    )
    return validation


def regulation_meta(
    doc_name: Any, *, timeline: Mapping[str, Mapping[str, Any]] | None = None
) -> dict[str, Any] | None:
    registry = load_regulation_timeline() if timeline is None else timeline
    meta = registry.get(str(doc_name or ""))
    return dict(meta) if meta else None


def source_tier(doc_name: Any = "", chunk_id: Any = "") -> dict[str, Any]:
    doc = str(doc_name or "")
    cid = str(chunk_id or "")
    for prefixes, tier in _DOC_PREFIX_TIERS:
        if doc.startswith(prefixes):
            return {"tier": tier, "rank": TIER_RANK[tier], "label": TIER_LABEL[tier]}
    for prefix, tier in _CHUNK_PREFIX_TIERS:
        if cid.startswith(prefix):
            return {"tier": tier, "rank": TIER_RANK[tier], "label": TIER_LABEL[tier]}
    return {"tier": UNKNOWN, "rank": TIER_RANK[UNKNOWN], "label": TIER_LABEL[UNKNOWN]}


def source_priority_key(
    source: Mapping[str, Any],
    *,
    timeline: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[int, int, int, int, float, str]:
    """Rank by tier, status, legal authority, effective date, then score."""

    doc_name = str(source.get("doc_name") or "")
    chunk_id = str(source.get("chunk_id") or "")
    tier = source_tier(doc_name, chunk_id)
    meta = (
        regulation_meta(doc_name, timeline=timeline)
        if tier["tier"] == REGULATION
        else None
    )
    status_rank = _STATUS_SORT.get(str((meta or {}).get("status") or "current"), 99)
    authority_rank = int((meta or {}).get("authority_rank") or 0)
    authority_date = str(
        (meta or {}).get("effective_date")
        or (meta or {}).get("issued_date")
        or "0001-01-01"
    )
    try:
        date_rank = date.fromisoformat(authority_date).toordinal()
    except ValueError:
        date_rank = 0
    try:
        score = float(source.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    if not math.isfinite(score):
        score = 0.0
    return (
        -int(tier["rank"]),
        status_rank,
        -authority_rank,
        -date_rank,
        -score,
        chunk_id,
    )


def authority_priority_rule() -> str:
    return (
        "来源效力层级：法规 > 公司制度 > 教材 > 题库。"
        "同一事项上教材、题库与法规冲突时，一律以已绑定的现行法规原文为准；"
        "已登记为部分或全部被取代的段落不得作为现行依据。"
        "法规元数据中的编号、施行日期和状态只可来自已绑定的r9 SQLite证据。"
    )


def source_annotation(
    doc_name: Any = "",
    chunk_id: Any = "",
    *,
    timeline: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    tier = source_tier(doc_name, chunk_id)
    if tier["tier"] != REGULATION:
        return str(tier["label"])
    meta = regulation_meta(doc_name, timeline=timeline)
    if meta is None:
        raise SourceAuthorityError("regulation source is missing timeline metadata")
    parts = [str(tier["label"])]
    number = meta.get("number")
    if number:
        parts.append(str(number))
    effective = meta.get("effective_date")
    if effective:
        parts.append(f"{effective}施行")
    else:
        parts.append(f"{meta['issued_date']}下发")
    parts.append(_STATUS_LABEL[str(meta["status"])])
    return "·".join(parts)


def superseded_passage_for_chunk(chunk_id: Any) -> dict[str, Any] | None:
    return _passage_for_chunk(str(chunk_id or ""), load_superseded_passages())


def _passage_for_chunk(
    chunk_id: str, passages: Iterable[Mapping[str, Any]]
) -> dict[str, Any] | None:
    for passage in passages:
        if chunk_id in passage.get("chunk_ids", []):
            return dict(passage)
    return None


def _query_hits_topic(query: str, passage: Mapping[str, Any]) -> bool:
    return any(str(marker) in query for marker in passage.get("topic_markers", []) if marker)


def filter_superseded(
    query: str,
    results: Sequence[Mapping[str, Any]],
    *,
    passages: Sequence[Mapping[str, Any]] | None = None,
    exact_question_match: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry = load_superseded_passages() if passages is None else [dict(x) for x in passages]
    question = str(query or "")
    kept: list[dict[str, Any]] = []
    yielded: list[dict[str, Any]] = []
    for raw in results:
        result = dict(raw)
        chunk_id = str(result.get("chunk_id") or "")
        passage = _passage_for_chunk(chunk_id, registry)
        if (
            passage
            and exact_question_match
            and passage["keep_when_exact_question_match"]
        ):
            passage = None
        if passage and _query_hits_topic(question, passage):
            yielded.append(
                {
                    "chunk_id": chunk_id,
                    "doc_name": str(result.get("doc_name") or passage["doc_name"]),
                    "passage_id": passage["id"],
                    "topic": passage["topic"],
                    "superseded_by": list(passage["superseded_by"]),
                    "reason": passage["reason"],
                }
            )
            continue
        kept.append(result)
    return kept, yielded


__all__ = [
    "FROZEN_R9_SOURCE_SCOPE",
    "REGULATION_TIMELINE_PATH",
    "SUPERSEDED_PASSAGES_PATH",
    "SourceAuthorityError",
    "authority_priority_rule",
    "filter_superseded",
    "governance_file_hashes",
    "load_bound_regulation_governance",
    "load_regulation_timeline",
    "load_superseded_passages",
    "regulation_meta",
    "source_annotation",
    "source_priority_key",
    "source_tier",
    "superseded_passage_for_chunk",
    "validate_regulation_governance",
]
