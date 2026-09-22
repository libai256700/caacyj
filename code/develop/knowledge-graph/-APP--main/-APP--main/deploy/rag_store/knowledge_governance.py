#!/usr/bin/env python3
"""Canonical concept, claim, conflict, and provenance contracts.

The existing ``chunks`` table remains the only owner of chunk text.  These
tables are sidecars joined by ``chunk_id`` so governance can be introduced
without changing retrieval or index contracts for legacy documents.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any, Iterable


GOVERNANCE_SCHEMA_VERSION = "knowledge-governance-v1"
QUERY_RELEVANCE_CONTRACT_VERSION = "query-relevance-v2"
# v2 相对 v1 增加 reviewer_type='human' 强制声明：v1 只校验 decided_by 非空，
# 任何机器署名都能解除冲突拒答。表结构无 actor 字段，故该声明放在合同 payload 里。
HUMAN_REVIEWER_TYPE = "human"
# decided_by 里出现这些记号即判为自动化来源，不能充当人工批准。
MACHINE_REVIEWER_MARKERS = (
    "llm", "gpt", "claude", "deepseek", "doubao", "bot", "auto", "script",
    "backfill", "migration", "cron", "system", "agent", "pipeline", "codex",
)
PREPARED_BUNDLE_SCHEMA_VERSION = "textbook-prepared-bundle-v1"
TEXTBOOK_SEMANTIC_SCHEMA_VERSION = "textbook-semantic-v1"
TEXTBOOK_SYNC_SOURCE = "textbook_semantic_v1"

GOVERNANCE_TABLE_NAMES = frozenset({
    "document_sources",
    "chunk_provenance",
    "concept_clusters",
    "concept_members",
    "knowledge_claims",
    "claim_sources",
    "knowledge_conflicts",
    "conflict_claims",
    "review_decisions",
})

CORE_RAG_TABLE_NAMES = frozenset({"chunks", "documents"})


CORE_RAG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    doc_name TEXT NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_name);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_idx ON chunks(doc_name, chunk_index);

CREATE TABLE IF NOT EXISTS documents (
    doc_name TEXT PRIMARY KEY,
    doc_path TEXT,
    chunk_count INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
"""

REVIEW_APPROVED = ("approved", "auto_approved")
UNRESOLVED_CONFLICT_STATUSES = ("pending", "in_review")

AUTHORITY_RANK = {
    "regulation": 100,
    "company_policy": 80,
    "textbook": 60,
    "question_bank": 50,
    "unknown": 0,
}


GOVERNANCE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document_sources (
    document_source_id TEXT PRIMARY KEY,
    doc_name TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_page_count INTEGER,
    authority TEXT NOT NULL,
    published_at TEXT,
    ocr_engine TEXT,
    ocr_version TEXT,
    ocr_backend TEXT,
    ocr_language TEXT,
    extractor_version TEXT,
    import_run_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_document_sources_sha
ON document_sources(source_sha256);

CREATE INDEX IF NOT EXISTS idx_document_sources_run
ON document_sources(import_run_id);

CREATE TABLE IF NOT EXISTS chunk_provenance (
    chunk_id TEXT PRIMARY KEY,
    document_source_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    pdf_page_start INTEGER NOT NULL,
    pdf_page_end INTEGER NOT NULL,
    printed_page_start INTEGER,
    printed_page_end INTEGER,
    chapter_id TEXT,
    chapter_title TEXT,
    section_id TEXT,
    section_title TEXT,
    content_type TEXT NOT NULL,
    confidence REAL,
    review_status TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    FOREIGN KEY(document_source_id) REFERENCES document_sources(document_source_id)
);

CREATE INDEX IF NOT EXISTS idx_chunk_provenance_scope
ON chunk_provenance(source_sha256, import_run_id);

CREATE INDEX IF NOT EXISTS idx_chunk_provenance_section
ON chunk_provenance(section_id, content_type);

CREATE TABLE IF NOT EXISTS concept_clusters (
    concept_cluster_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    review_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_concept_clusters_name
ON concept_clusters(entity_type, normalized_name);

CREATE TABLE IF NOT EXISTS concept_members (
    concept_member_id TEXT PRIMARY KEY,
    concept_cluster_id TEXT NOT NULL,
    semantic_key TEXT NOT NULL UNIQUE,
    source_doc TEXT NOT NULL,
    source_chunk_id TEXT,
    member_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    match_method TEXT NOT NULL,
    similarity REAL,
    review_status TEXT NOT NULL,
    import_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(concept_cluster_id) REFERENCES concept_clusters(concept_cluster_id),
    UNIQUE(concept_cluster_id, semantic_key, source_chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_concept_members_chunk
ON concept_members(source_chunk_id);

CREATE TABLE IF NOT EXISTS knowledge_claims (
    claim_id TEXT PRIMARY KEY,
    concept_cluster_id TEXT NOT NULL,
    claim_key TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    predicate TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}',
    value_json TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    polarity TEXT NOT NULL DEFAULT 'positive',
    authority TEXT NOT NULL,
    review_status TEXT NOT NULL,
    conflict_status TEXT NOT NULL DEFAULT 'clear',
    import_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(concept_cluster_id) REFERENCES concept_clusters(concept_cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_claims_key
ON knowledge_claims(concept_cluster_id, claim_key);

CREATE TABLE IF NOT EXISTS claim_sources (
    claim_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    source_doc TEXT NOT NULL,
    pdf_page_start INTEGER,
    pdf_page_end INTEGER,
    evidence_quote TEXT NOT NULL,
    confidence REAL,
    review_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY(claim_id, chunk_id, evidence_quote),
    FOREIGN KEY(claim_id) REFERENCES knowledge_claims(claim_id) ON DELETE CASCADE,
    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_claim_sources_chunk
ON claim_sources(chunk_id);

CREATE TABLE IF NOT EXISTS knowledge_conflicts (
    conflict_id TEXT PRIMARY KEY,
    conflict_key TEXT NOT NULL UNIQUE,
    concept_cluster_id TEXT NOT NULL,
    claim_key TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'blocking',
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    suggested_action TEXT,
    resolution_action TEXT,
    resolution_notes TEXT,
    decided_by TEXT,
    decided_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(concept_cluster_id) REFERENCES concept_clusters(concept_cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_conflicts_status
ON knowledge_conflicts(status, severity);

CREATE TABLE IF NOT EXISTS conflict_claims (
    conflict_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    PRIMARY KEY(conflict_id, claim_id),
    FOREIGN KEY(conflict_id) REFERENCES knowledge_conflicts(conflict_id) ON DELETE CASCADE,
    FOREIGN KEY(claim_id) REFERENCES knowledge_claims(claim_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    action TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    notes TEXT,
    decided_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_review_decisions_target
ON review_decisions(target_type, target_id);
"""


def ensure_governance_tables(conn: sqlite3.Connection) -> None:
    """Create governance sidecars without modifying the chunks text contract."""
    statement = ""
    for line in GOVERNANCE_SCHEMA_SQL.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            sql = statement.strip()
            if sql:
                conn.execute(sql)
            statement = ""
    if statement.strip():
        raise ValueError("incomplete governance schema statement")


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _schema_contract(conn: sqlite3.Connection, table_name: str) -> dict[str, Any]:
    """Read the structural contract SQLite enforces for one table."""
    quoted_table = _quoted_identifier(table_name)
    columns = tuple(
        (
            str(row[1]),
            str(row[2] or "").upper(),
            int(row[3]),
            None if row[4] is None else str(row[4]),
            int(row[5]),
            int(row[6]),
        )
        for row in conn.execute(f"PRAGMA table_xinfo({quoted_table})").fetchall()
    )

    foreign_keys = tuple(sorted(
        (
            int(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]).upper(),
            str(row[6]).upper(),
            str(row[7]).upper(),
        )
        for row in conn.execute(f"PRAGMA foreign_key_list({quoted_table})").fetchall()
    ))

    unique_constraints = []
    named_indexes: dict[str, tuple[int, int, tuple[str | None, ...]]] = {}
    for row in conn.execute(f"PRAGMA index_list({quoted_table})").fetchall():
        index_name = str(row[1])
        is_unique = int(row[2])
        origin = str(row[3])
        is_partial = int(row[4])
        quoted_index = _quoted_identifier(index_name)
        index_columns = tuple(
            None if item[2] is None else str(item[2])
            for item in conn.execute(f"PRAGMA index_info({quoted_index})").fetchall()
        )
        if is_unique:
            unique_constraints.append((origin, is_partial, index_columns))
        if origin == "c":
            named_indexes[index_name] = (is_unique, is_partial, index_columns)

    return {
        "columns": columns,
        "foreign_keys": foreign_keys,
        "unique_constraints": tuple(sorted(unique_constraints, key=repr)),
        "named_indexes": named_indexes,
    }


@lru_cache(maxsize=1)
def _expected_schema_contracts() -> dict[str, dict[str, Any]]:
    reference = sqlite3.connect(":memory:")
    try:
        reference.execute("PRAGMA foreign_keys=ON")
        reference.executescript(CORE_RAG_SCHEMA_SQL)
        ensure_governance_tables(reference)
        return {
            table_name: _schema_contract(reference, table_name)
            for table_name in sorted(CORE_RAG_TABLE_NAMES | GOVERNANCE_TABLE_NAMES)
        }
    finally:
        reference.close()


def _matches_schema_contract(
    conn: sqlite3.Connection,
    table_name: str,
    expected: dict[str, Any],
) -> bool:
    actual = _schema_contract(conn, table_name)
    if actual["columns"] != expected["columns"]:
        return False
    if actual["foreign_keys"] != expected["foreign_keys"]:
        return False
    if actual["unique_constraints"] != expected["unique_constraints"]:
        return False
    return all(
        actual["named_indexes"].get(index_name) == index_contract
        for index_name, index_contract in expected["named_indexes"].items()
    )


def governance_schema_state(conn: sqlite3.Connection) -> str:
    """Classify the core and v1 governance schema without applying DDL.

    ``legacy`` is reserved for an intact legacy RAG schema with no governance
    tables. A partial sidecar is distinguished from a fully present but damaged
    schema so callers can fail closed in both cases.
    """
    expected = _expected_schema_contracts()
    relevant_names = CORE_RAG_TABLE_NAMES | GOVERNANCE_TABLE_NAMES
    placeholders = ",".join("?" for _ in relevant_names)
    rows = conn.execute(
        f"SELECT name, type FROM sqlite_master "
        f"WHERE lower(name) IN ({placeholders})",
        sorted(relevant_names),
    ).fetchall()
    objects = {
        str(row[0]).lower(): (str(row[0]), str(row[1]))
        for row in rows
    }

    if any(
        table_name not in objects
        or objects[table_name] != (table_name, "table")
        for table_name in CORE_RAG_TABLE_NAMES
    ):
        return "invalid"
    if any(
        not _matches_schema_contract(conn, table_name, expected[table_name])
        for table_name in CORE_RAG_TABLE_NAMES
    ):
        return "invalid"

    governance_objects = {
        table_name for table_name in GOVERNANCE_TABLE_NAMES if table_name in objects
    }
    if not governance_objects:
        return "legacy"
    if any(
        objects[table_name] != (table_name, "table")
        for table_name in governance_objects
    ):
        return "invalid"
    if governance_objects != GOVERNANCE_TABLE_NAMES:
        return "partial"
    if any(
        not _matches_schema_contract(conn, table_name, expected[table_name])
        for table_name in GOVERNANCE_TABLE_NAMES
    ):
        return "invalid"
    return "ready"


def normalize_term(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_claim_number(value: Decimal) -> str:
    if not value.is_finite():
        raise InvalidOperation
    if value == 0:
        return "0"
    normalized = value.normalize()
    sign, digits, exponent = normalized.as_tuple()
    return f"{sign}:{''.join(str(digit) for digit in digits)}:{exponent}"


def _canonical_claim_value(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, Decimal):
        return ("number", _canonical_claim_number(value))
    if isinstance(value, int):
        return ("number", _canonical_claim_number(Decimal(value)))
    if isinstance(value, float):
        return ("number", _canonical_claim_number(Decimal(str(value))))
    if isinstance(value, str):
        return ("string", unicodedata.normalize("NFC", value))
    if isinstance(value, list):
        # Array order can encode an ordered classification or procedure.
        return ("list", tuple(_canonical_claim_value(item) for item in value))
    if isinstance(value, dict):
        return (
            "object",
            tuple(
                sorted(
                    (
                        unicodedata.normalize("NFC", str(key)),
                        _canonical_claim_value(item),
                    )
                    for key, item in value.items()
                )
            ),
        )
    return ("unsupported", type(value).__name__, str(value))


def canonical_claim_signature(
    value: Any,
    unit: str = "",
    polarity: str = "positive",
    *,
    serialized_value: bool = False,
) -> tuple[Any, str, str]:
    """Canonical fact signature shared by staging and retrieval governance.

    JSON numbers such as ``30`` and ``30.0`` compare equal, while text values
    retain compatibility characters so ``10²`` cannot collapse into ``102``.
    List order remains significant. Unit and polarity use the existing term
    normalization contract but no unit conversion is attempted.
    """
    try:
        if serialized_value:
            raw = str(value if value is not None else "")
            parsed = json.loads(
                raw,
                parse_int=Decimal,
                parse_float=Decimal,
                parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
            )
            canonical_value = _canonical_claim_value(parsed)
        else:
            canonical_value = _canonical_claim_value(value)
    except (InvalidOperation, TypeError, ValueError, json.JSONDecodeError):
        canonical_value = (
            "invalid-json" if serialized_value else "invalid-value",
            unicodedata.normalize("NFC", str(value if value is not None else "")),
        )
    return (
        canonical_value,
        normalize_term(unit),
        normalize_term(polarity or "positive"),
    )


def _digest(*parts: Any, length: int = 20) -> str:
    payload = "|".join(normalize_term(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _exact_digest(*parts: Any, length: int = 20) -> str:
    """Hash stored claim identity without compatibility or case folding.

    NFKC is appropriate for names used during candidate matching, but it is not
    safe for fact values: for example ``10²`` and ``102`` are different values.
    Exact member-claim ids deliberately remain distinct; read-time aggregation
    decides whether two member claims carry equivalent canonical evidence.
    """
    payload = "|".join(
        unicodedata.normalize("NFC", str(part if part is not None else ""))
        for part in parts
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def stable_semantic_key(
    import_scope: str,
    entity_type: str,
    structural_path: str,
    canonical_name: str,
) -> str:
    digest = _digest(import_scope, entity_type, structural_path, canonical_name)
    return f"textbook:{entity_type}:{digest}"


def stable_relationship_key(
    import_scope: str,
    start_key: str,
    relation_type: str,
    end_key: str,
    claim_key: str = "",
) -> str:
    digest = _digest(import_scope, start_key, relation_type, end_key, claim_key, length=24)
    return f"textbook:rel:{digest}"


def stable_concept_cluster_id(entity_type: str, canonical_name: str, sense: str = "") -> str:
    return f"concept:{entity_type}:{_digest(entity_type, canonical_name, sense)}"


def stable_claim_key(subject_key: str, predicate: str, scope: Any = None) -> str:
    """Key the proposition slot, deliberately excluding value/unit/polarity.

    Different values for the same subject/predicate/scope therefore collide in
    one slot and can be escalated as a conflict instead of silently coexisting.
    """
    return f"claim-slot:{_digest(subject_key, predicate, canonical_json(scope), length=24)}"


def stable_claim_id(
    claim_key: str,
    value: Any,
    unit: str = "",
    polarity: str = "positive",
) -> str:
    return f"claim:{_exact_digest(claim_key, canonical_json(value), unit, polarity, length=24)}"


def stable_cross_cluster_claim_key(
    canonical_name: str,
    predicate: str,
    scope: Any = None,
) -> str:
    """Return a review slot for contradictory claims split across concepts."""
    subject = f"cross-cluster:{normalize_term(canonical_name)}"
    digest = _digest(subject, predicate, canonical_json(scope), length=24)
    return f"claim-cross-slot:{digest}"


def stable_conflict_id(claim_key: str) -> str:
    return f"conflict:{_digest(claim_key, length=24)}"


def authority_rank(authority: str) -> int:
    return AUTHORITY_RANK.get(normalize_term(authority), AUTHORITY_RANK["unknown"])


def _batched(values: list[str], size: int = 400) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _looks_like_machine_reviewer(decided_by: str) -> bool:
    """Reject automation-signed approvals from standing in for a human decision."""
    token = re.sub(r"[\s_\-.]+", "", decided_by).lower()
    return any(marker in token for marker in MACHINE_REVIEWER_MARKERS)


def query_relevance_reviewer_allowed(payload: dict[str, Any], decided_by: str) -> bool:
    """Allow only an explicitly human-approved query-relevance contract."""
    return (
        payload.get("version") == QUERY_RELEVANCE_CONTRACT_VERSION
        and payload.get("reviewer_type") == HUMAN_REVIEWER_TYPE
        and not _looks_like_machine_reviewer(decided_by)
    )


def _reviewed_query_relevance_contracts(
    conn: sqlite3.Connection,
    claim_slots: dict[str, tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    """Return only each claim's latest, complete human-approved query contract."""
    contracts: dict[str, dict[str, Any]] = {}
    for batch in _batched(sorted(claim_slots)):
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"""
            SELECT decision_id, target_id, action, decided_by, notes, decided_at,
                   julianday(decision.decided_at) AS decided_julian_day,
                   CASE
                       WHEN julianday(decision.decided_at) IS NULL
                         OR (
                             decision.decided_at NOT GLOB '????-??-?? ??:??:??*'
                             AND decision.decided_at NOT GLOB '????-??-??T??:??:??*'
                         )
                       THEN 1 ELSE 0
                   END AS decision_timestamp_invalid
            FROM review_decisions AS decision
            WHERE decision.target_type = 'claim_query_relevance'
              AND decision.target_id IN ({placeholders})
              AND decision.rowid = (
                  SELECT newer.rowid
                  FROM review_decisions AS newer
                  WHERE newer.target_type = decision.target_type
                    AND newer.target_id = decision.target_id
                  ORDER BY
                      CASE
                          WHEN julianday(newer.decided_at) IS NULL
                            OR (
                                newer.decided_at NOT GLOB '????-??-?? ??:??:??*'
                                AND newer.decided_at NOT GLOB '????-??-??T??:??:??*'
                            )
                          THEN 1 ELSE 0
                      END DESC,
                      julianday(newer.decided_at) DESC,
                      newer.rowid DESC
                  LIMIT 1
              )
            """,
            batch,
        ).fetchall()
        for raw_row in rows:
            row = dict(raw_row)
            claim_id = str(row.get("target_id") or "")
            if row.get("decision_timestamp_invalid") or row.get(
                "decided_julian_day"
            ) is None:
                # One malformed timestamp makes decision recency unknowable. The
                # invalid row sorts first so this target fails closed instead of
                # reviving an older approval.
                continue
            if str(row.get("action") or "") != "approve":
                continue
            try:
                payload = json.loads(str(row.get("notes") or ""))
                expected_predicate, expected_scope = claim_slots[claim_id]
                payload_scope_value = json.loads(payload["scope_json"])
                stored_scope_value = json.loads(expected_scope)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(payload_scope_value, dict) or not isinstance(
                stored_scope_value, dict
            ):
                continue
            payload_scope = canonical_json(payload_scope_value)
            stored_scope = canonical_json(stored_scope_value)
            aliases = payload.get("query_aliases")
            if (
                not isinstance(payload, dict)
                or payload.get("claim_id") != claim_id
                or payload.get("predicate") != expected_predicate
                or payload_scope != stored_scope
                or payload.get("aliases_complete") is not True
                or not isinstance(aliases, list)
                or not aliases
                or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
                or not str(row.get("decision_id") or "")
                or not str(row.get("decided_by") or "")
                or not str(row.get("decided_at") or "")
                or not query_relevance_reviewer_allowed(
                    payload, str(row.get("decided_by") or "")
                )
            ):
                continue
            contracts[claim_id] = {
                **payload,
                "decision_id": str(row["decision_id"]),
                "review_status": "approved",
                "reviewed_by": str(row["decided_by"]),
                "reviewed_at": str(row["decided_at"]),
            }
    return contracts


def fetch_chunk_governance(
    conn: sqlite3.Connection,
    chunk_ids: list[str],
) -> dict[str, Any]:
    """Return approved claim membership plus unresolved conflicts by chunk."""
    ordered_ids = list(dict.fromkeys(chunk_id for chunk_id in chunk_ids if chunk_id))
    result: dict[str, Any] = {
        "by_chunk": {chunk_id: [] for chunk_id in ordered_ids},
        "supporting_sources": {},
        "unresolved_conflicts": {chunk_id: [] for chunk_id in ordered_ids},
        "provenance": {},
    }
    if not ordered_ids:
        return result

    for batch in _batched(ordered_ids):
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"""
            SELECT chunk_id, source_sha256, import_run_id, pdf_page_start,
                   pdf_page_end, printed_page_start, printed_page_end,
                   chapter_id, chapter_title, section_id, section_title,
                   content_type, confidence, review_status
            FROM chunk_provenance
            WHERE chunk_id IN ({placeholders})
            """,
            batch,
        ).fetchall()
        for raw_row in rows:
            row = dict(raw_row)
            result["provenance"][str(row["chunk_id"])] = row

    claim_ids: set[str] = set()
    for batch in _batched(ordered_ids):
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"""
            SELECT cs.chunk_id,
                   cs.claim_id,
                   cs.source_doc,
                   cs.pdf_page_start,
                   cs.pdf_page_end,
                   cs.evidence_quote,
                   cs.confidence AS source_confidence,
                   cs.review_status AS source_review_status,
                   cp.content_type,
                   kc.concept_cluster_id,
                   kc.claim_key,
                   kc.subject_key,
                   kc.predicate,
                   kc.scope_json,
                   kc.value_json,
                   kc.normalized_value,
                   kc.unit,
                   kc.polarity,
                   kc.authority,
                   kc.review_status AS claim_review_status,
                   kc.conflict_status,
                   cc.canonical_name,
                   cc.entity_type
            FROM claim_sources cs
            LEFT JOIN chunk_provenance cp ON cp.chunk_id = cs.chunk_id
            JOIN knowledge_claims kc ON kc.claim_id = cs.claim_id
            JOIN concept_clusters cc ON cc.concept_cluster_id = kc.concept_cluster_id
            WHERE cs.chunk_id IN ({placeholders})
              AND cs.review_status IN ('approved', 'auto_approved')
              AND kc.review_status IN ('approved', 'auto_approved')
              AND cc.review_status IN ('approved', 'auto_approved')
            ORDER BY cs.chunk_id, kc.claim_key, cs.claim_id
            """,
            batch,
        ).fetchall()
        for raw_row in rows:
            row = dict(raw_row)
            claim_ids.add(str(row["claim_id"]))
            row["authority_rank"] = authority_rank(str(row.get("authority") or ""))
            result["by_chunk"].setdefault(str(row["chunk_id"]), []).append(row)

    if claim_ids:
        for batch in _batched(sorted(claim_ids)):
            placeholders = ",".join("?" for _ in batch)
            rows = conn.execute(
                f"""
                SELECT cs.claim_id, cs.chunk_id, cs.source_doc,
                       cs.pdf_page_start, cs.pdf_page_end, cs.evidence_quote,
                       cs.confidence, cs.review_status,
                       coalesce(cp.content_type, 'body') AS content_type
                FROM claim_sources cs
                LEFT JOIN chunk_provenance cp ON cp.chunk_id = cs.chunk_id
                WHERE cs.claim_id IN ({placeholders})
                  AND cs.review_status IN ('approved', 'auto_approved')
                  AND coalesce(cp.content_type, 'body') <> 'exercise'
                ORDER BY cs.claim_id, cs.source_doc, cs.chunk_id
                """,
                batch,
            ).fetchall()
            for raw_row in rows:
                row = dict(raw_row)
                result["supporting_sources"].setdefault(str(row["claim_id"]), []).append(row)

    for batch in _batched(ordered_ids):
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"""
            SELECT DISTINCT cs.chunk_id,
                   cs.source_doc,
                   cs.pdf_page_start,
                   cs.pdf_page_end,
                   cs.evidence_quote,
                   cs.confidence AS source_confidence,
                   kc.claim_id,
                   kc.concept_cluster_id,
                   kc.claim_key,
                   kc.subject_key,
                   kc.predicate,
                   kc.scope_json,
                   kc.value_json,
                   kc.normalized_value,
                   kc.unit,
                   kc.polarity,
                   kc.authority,
                   kc.conflict_status,
                   cc.canonical_name,
                   cc.entity_type,
                   kf.conflict_id,
                   kf.concept_cluster_id AS conflict_concept_cluster_id,
                   kf.claim_key AS conflict_claim_key,
                   kf.severity,
                   kf.reason,
                   kf.status,
                   kf.suggested_action,
                   (
                       SELECT count(*)
                       FROM conflict_claims AS all_conflict_claims
                       WHERE all_conflict_claims.conflict_id = kf.conflict_id
                   ) AS conflict_claim_count
            FROM claim_sources cs
            JOIN knowledge_claims kc ON kc.claim_id = cs.claim_id
            JOIN concept_clusters cc ON cc.concept_cluster_id = kc.concept_cluster_id
            JOIN knowledge_conflicts kf ON (
                   (
                       kf.concept_cluster_id = kc.concept_cluster_id
                       AND kf.claim_key = kc.claim_key
                   )
                   OR EXISTS (
                       SELECT 1
                       FROM conflict_claims AS direct_link
                       WHERE direct_link.conflict_id = kf.conflict_id
                         AND direct_link.claim_id = kc.claim_id
                   )
                   OR EXISTS (
                       SELECT 1
                       FROM conflict_claims AS topic_link
                       JOIN knowledge_claims AS linked_claim
                         ON linked_claim.claim_id = topic_link.claim_id
                       JOIN concept_clusters AS linked_cluster
                         ON linked_cluster.concept_cluster_id =
                            linked_claim.concept_cluster_id
                       WHERE topic_link.conflict_id = kf.conflict_id
                         AND linked_cluster.normalized_name = cc.normalized_name
                         AND linked_claim.predicate = kc.predicate
                         AND linked_claim.scope_json = kc.scope_json
                   )
               )
            WHERE cs.chunk_id IN ({placeholders})
              AND kf.status IN ('pending', 'in_review')
            ORDER BY kf.conflict_id, cs.chunk_id
            """,
            batch,
        ).fetchall()
        relevance_contracts = _reviewed_query_relevance_contracts(
            conn,
            {
                str(row["claim_id"]): (
                    str(row["predicate"] or ""),
                    str(row["scope_json"] or ""),
                )
                for row in rows
            },
        )
        for raw_row in rows:
            row = dict(raw_row)
            relevance_contract = relevance_contracts.get(str(row["claim_id"]))
            if relevance_contract is not None:
                row["query_relevance_contract"] = relevance_contract
            result["unresolved_conflicts"].setdefault(str(row["chunk_id"]), []).append(row)

    return result


def governance_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "document_sources",
        "chunk_provenance",
        "concept_clusters",
        "concept_members",
        "knowledge_claims",
        "claim_sources",
        "knowledge_conflicts",
        "conflict_claims",
        "review_decisions",
    )
    counts: dict[str, int] = {}
    for table in tables:
        counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts
