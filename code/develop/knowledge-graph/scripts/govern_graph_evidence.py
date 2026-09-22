#!/usr/bin/env python3
"""Govern Neo4j relationship evidence and Position tier fields.

Actions with --confirm:
- backfill own relationship source_doc/source_chunk_ids for selected relation
  types when evidence can be inferred from relation, endpoint, or SQLite docs
- normalize Position nodes whose type/category/entityType was used as a tier

The script writes a JSON summary plus JSONL evidence plans before mutation.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_ROOT = BASE_DIR / "review_reports"
SQLITE_DB = BASE_DIR / "rag_chunks.db"
ALIAS_PATH = BASE_DIR / "rag_store" / "source_doc_aliases.json"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()

RUN_ID = f"graph_evidence_governance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
DEFAULT_REL_TYPES = (
    "REQUIRES",
    "REGULATES",
    "REFERS_TO",
    "HAS_PROPERTY",
    "REQUIRES_SKILL",
    "HAS_CLASS",
)
TIER_VALUES = {"管理", "基层"}
SOURCE_DOC_KEYS = ("source_doc", "_created_by", "created_by", "canonical_doc_name", "doc_name", "document_name")
SOURCE_TABLE_KEYS = ("source_table", "source_csv")
CHUNK_KEYS = ("source_chunk_ids", "evidence_chunk_ids", "source_chunks", "chunk_id", "source_chunk_id")


def json_default(value: Any) -> str:
    return str(value)


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=json_default) + "\n")


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(nonempty(item) for item in value)
    return str(value).strip() != ""


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def unique_strings(values: list[Any], limit: int | None = None) -> list[str]:
    result: list[str] = []
    for value in values:
        for item in as_list(value):
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
                if limit and len(result) >= limit:
                    return result
    return result


def first_text(props: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = props.get(key)
        if isinstance(value, list):
            values = unique_strings(value, limit=1)
            if values:
                return values[0]
        elif nonempty(value):
            return str(value).strip()
    return ""


class ChunkResolver:
    def __init__(self, db_path: Path, alias_path: Path, max_chunks: int):
        self.max_chunks = max_chunks
        self.by_doc = self._load_chunks(db_path)
        self.aliases = self._load_aliases(alias_path)
        self.normalized_docs = {self._normalize(name): name for name in self.by_doc}

    @staticmethod
    def _normalize(value: str) -> str:
        text = str(value or "").strip()
        for suffix in (".txt", ".md", ".docx", ".pdf", ".csv"):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                break
        return text.lower()

    def _load_chunks(self, db_path: Path) -> dict[str, list[str]]:
        by_doc: dict[str, list[str]] = {}
        with sqlite3.connect(db_path) as conn:
            for doc_name, chunk_id in conn.execute(
                "SELECT doc_name, chunk_id FROM chunks ORDER BY doc_name, chunk_id"
            ):
                by_doc.setdefault(str(doc_name), []).append(str(chunk_id))
        return by_doc

    def _load_aliases(self, alias_path: Path) -> dict[str, list[str]]:
        if not alias_path.exists():
            return {}
        raw = json.loads(alias_path.read_text(encoding="utf-8"))
        aliases = raw.get("aliases") if isinstance(raw, dict) else raw
        if not isinstance(aliases, dict):
            return {}
        return {
            str(alias).strip(): [str(item).strip() for item in as_list(targets) if str(item).strip()]
            for alias, targets in aliases.items()
        }

    def source_candidates(self, source_doc: str) -> list[str]:
        source = str(source_doc or "").strip()
        if not source:
            return []
        candidates = [source]
        candidates.extend(self.aliases.get(source, []))
        if not source.endswith(".txt"):
            candidates.append(f"{source}.txt")
        normalized = self._normalize(source)
        if normalized in self.normalized_docs:
            candidates.append(self.normalized_docs[normalized])
        for doc_name in self.by_doc:
            if source and (source in doc_name or doc_name in source):
                candidates.append(doc_name)
        return unique_strings(candidates)

    def chunks_for_source(self, source_doc: str) -> list[str]:
        chunks: list[str] = []
        for doc_name in self.source_candidates(source_doc):
            for chunk_id in self.by_doc.get(doc_name, []):
                if chunk_id not in chunks:
                    chunks.append(chunk_id)
                    if len(chunks) >= self.max_chunks:
                        return chunks
        return chunks


def source_values(props: dict[str, Any], include_tables: bool = False) -> list[str]:
    keys = SOURCE_DOC_KEYS + (SOURCE_TABLE_KEYS if include_tables else ())
    return unique_strings([props.get(key) for key in keys])


def chunk_values(props: dict[str, Any], limit: int) -> list[str]:
    return unique_strings([props.get(key) for key in CHUNK_KEYS], limit=limit)


def choose_source_doc(
    rel_props: dict[str, Any],
    a_props: dict[str, Any],
    b_props: dict[str, Any],
    resolver: ChunkResolver,
) -> tuple[str, list[str]]:
    current = first_text(rel_props, ("source_doc",))
    if current:
        return current, ["relationship.source_doc"]

    a_sources = source_values(a_props)
    b_sources = source_values(b_props)
    for source in a_sources:
        if source in b_sources:
            return source, ["endpoint.shared_source_doc"]
    for source in a_sources:
        a_candidates = set(resolver.source_candidates(source))
        if any(a_candidates.intersection(resolver.source_candidates(other)) for other in b_sources):
            return source, ["endpoint.shared_canonical_source_doc"]

    table_sources = source_values(rel_props, include_tables=True)
    if table_sources:
        return table_sources[0], ["relationship.source_table"]
    return "", []


def infer_evidence(row: dict[str, Any], resolver: ChunkResolver, max_chunks: int) -> dict[str, Any]:
    rel_props = dict(row.get("rel_props") or {})
    a_props = dict(row.get("a_props") or {})
    b_props = dict(row.get("b_props") or {})

    current_doc = first_text(rel_props, ("source_doc",))
    current_chunks = chunk_values(rel_props, max_chunks)
    source_doc, reasons = choose_source_doc(rel_props, a_props, b_props, resolver)

    chunks = current_chunks
    chunk_reasons: list[str] = []
    if chunks:
        chunk_reasons.append("relationship.source_chunk_ids")
    else:
        a_chunks = chunk_values(a_props, max_chunks)
        b_chunks = chunk_values(b_props, max_chunks)
        endpoint_chunks = unique_strings(a_chunks + b_chunks, limit=max_chunks)
        if source_doc and endpoint_chunks:
            chunks = endpoint_chunks
            chunk_reasons.append("endpoint.source_chunk_ids_for_inferred_source")
        elif source_doc:
            chunks = resolver.chunks_for_source(source_doc)
            if chunks:
                chunk_reasons.append("sqlite.chunks_by_source_doc")

    update: dict[str, Any] = {
        "rel_id": row["rel_id"],
        "rel_type": row["rel_type"],
        "start_name": row.get("start_name"),
        "end_name": row.get("end_name"),
        "old_source_doc": current_doc,
        "old_source_chunk_ids": current_chunks,
        "new_source_doc": "" if current_doc else source_doc,
        "new_source_chunk_ids": [] if current_chunks else chunks,
        "inference_reasons": unique_strings(reasons + chunk_reasons),
    }
    update["will_update_source_doc"] = not current_doc and bool(source_doc)
    update["will_update_source_chunk_ids"] = not current_chunks and bool(chunks)
    update["will_update"] = update["will_update_source_doc"] or update["will_update_source_chunk_ids"]
    update["will_have_both"] = bool(current_doc or source_doc) and bool(current_chunks or chunks)
    return update


def evidence_counts(session, rel_types: list[str]) -> list[dict[str, Any]]:
    return session.run(
        """
        MATCH ()-[r]->()
        WHERE type(r) IN $rel_types
        WITH type(r) AS rel_type,
             count(r) AS total,
             count(CASE WHEN r.source_doc IS NOT NULL AND trim(toString(r.source_doc)) <> '' THEN 1 END) AS with_doc,
             count(CASE WHEN r.source_chunk_ids IS NOT NULL AND size(r.source_chunk_ids) > 0 THEN 1 END) AS with_chunks,
             count(CASE WHEN (r.source_doc IS NULL OR trim(toString(r.source_doc)) = '')
                          OR (r.source_chunk_ids IS NULL OR size(r.source_chunk_ids) = 0) THEN 1 END) AS missing_either,
             count(CASE WHEN (r.source_doc IS NULL OR trim(toString(r.source_doc)) = '')
                          AND (r.source_chunk_ids IS NULL OR size(r.source_chunk_ids) = 0) THEN 1 END) AS missing_both
        RETURN rel_type, total, with_doc, with_chunks, missing_either, missing_both
        ORDER BY missing_either DESC, rel_type
        """,
        rel_types=rel_types,
    ).data()


def position_counts(session) -> dict[str, Any]:
    total = session.run(
        """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN $tiers)
           OR n.type IN $tiers
           OR n.entityType IN $tiers
           OR n.category IN $tiers
        RETURN count(n) AS c
        """,
        tiers=sorted(TIER_VALUES),
    ).single()["c"]
    by_value = session.run(
        """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN $tiers)
           OR n.type IN $tiers
           OR n.entityType IN $tiers
           OR n.category IN $tiers
        WITH coalesce(
               CASE WHEN n.type IN $tiers THEN n.type END,
               CASE WHEN n.entityType IN $tiers THEN n.entityType END,
               CASE WHEN n.category IN $tiers THEN n.category END,
               head([label IN labels(n) WHERE label IN $tiers])
             ) AS tier,
             count(n) AS count
        RETURN tier, count
        ORDER BY tier
        """,
        tiers=sorted(TIER_VALUES),
    ).data()
    return {"total": int(total), "by_value": by_value}


def fetch_missing_evidence_batch(session, rel_types: list[str], limit: int, run_id: str) -> list[dict[str, Any]]:
    return session.run(
        """
        MATCH (a)-[r]->(b)
        WHERE type(r) IN $rel_types
          AND (
            (r.source_doc IS NULL OR trim(toString(r.source_doc)) = '')
            OR (r.source_chunk_ids IS NULL OR size(r.source_chunk_ids) = 0)
          )
          AND r.evidence_backfilled_by IS NULL
          AND (r.evidence_governance_checked_by IS NULL OR r.evidence_governance_checked_by <> $run_id)
        RETURN elementId(r) AS rel_id,
               type(r) AS rel_type,
               a.name AS start_name,
               b.name AS end_name,
               properties(r) AS rel_props,
               properties(a) AS a_props,
               properties(b) AS b_props
        LIMIT $limit
        """,
        rel_types=rel_types,
        limit=limit,
        run_id=run_id,
    ).data()


def apply_evidence_updates(session, updates: list[dict[str, Any]], run_id: str) -> int:
    rows = [
        {
            "rel_id": update["rel_id"],
            "source_doc": update["new_source_doc"] or None,
            "source_chunk_ids": update["new_source_chunk_ids"] or None,
            "evidence_inferred_from": update["inference_reasons"],
        }
        for update in updates
        if update["will_update"]
    ]
    if not rows:
        return 0
    return session.run(
        """
        UNWIND $rows AS row
        MATCH ()-[r]->()
        WHERE elementId(r) = row.rel_id
        SET r.source_doc = CASE
              WHEN row.source_doc IS NULL THEN r.source_doc
              ELSE row.source_doc
            END,
            r.source_chunk_ids = CASE
              WHEN row.source_chunk_ids IS NULL THEN r.source_chunk_ids
              ELSE row.source_chunk_ids
            END,
            r.evidence_backfilled_by = $run_id,
            r.evidence_backfilled_at = datetime(),
            r.evidence_inferred_from = row.evidence_inferred_from,
            r.evidence_contract = coalesce(r.evidence_contract, 'source_doc_and_source_chunk_ids_to_sqlite'),
            r.evidence_governance_checked_by = $run_id,
            r.evidence_governance_checked_at = datetime(),
            r.evidence_governance_status = 'backfilled'
        RETURN count(r) AS c
        """,
        rows=rows,
        run_id=run_id,
    ).single()["c"]


def mark_scanned_unresolved(session, updates: list[dict[str, Any]], run_id: str) -> int:
    rows = [
        {
            "rel_id": update["rel_id"],
            "status": "planned_backfill" if update["will_update"] else "unresolved",
            "inference_reasons": update["inference_reasons"],
        }
        for update in updates
    ]
    if not rows:
        return 0
    return session.run(
        """
        UNWIND $rows AS row
        MATCH ()-[r]->()
        WHERE elementId(r) = row.rel_id
        SET r.evidence_governance_checked_by = $run_id,
            r.evidence_governance_checked_at = datetime(),
            r.evidence_governance_status = row.status,
            r.evidence_inference_attempted_from = row.inference_reasons
        RETURN count(r) AS c
        """,
        rows=rows,
        run_id=run_id,
    ).single()["c"]


def normalize_positions(session, run_id: str) -> int:
    return session.run(
        """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN $tiers)
           OR n.type IN $tiers
           OR n.entityType IN $tiers
           OR n.category IN $tiers
        WITH n, coalesce(
               CASE WHEN n.type IN $tiers THEN n.type END,
               CASE WHEN n.entityType IN $tiers THEN n.entityType END,
               CASE WHEN n.category IN $tiers THEN n.category END,
               head([label IN labels(n) WHERE label IN $tiers])
             ) AS tier
        SET n:Entity:Position,
            n.type = 'Position',
            n.position_tier = coalesce(n.position_tier, tier),
            n.management_level = coalesce(n.management_level, tier),
            n.legacy_type = coalesce(n.legacy_type, tier),
            n.type_normalized_by = $run_id,
            n.type_normalized_at = datetime()
        FOREACH (_ IN CASE WHEN n.entityType IN $tiers THEN [1] ELSE [] END |
            SET n.legacy_entityType = coalesce(n.legacy_entityType, n.entityType),
                n.entityType = 'Position'
        )
        REMOVE n:`管理`, n:`基层`
        RETURN count(n) AS c
        """,
        tiers=sorted(TIER_VALUES),
        run_id=run_id,
    ).single()["c"]


def plan_and_apply_evidence(
    session,
    resolver: ChunkResolver,
    rel_types: list[str],
    report_dir: Path,
    batch_size: int,
    max_batches: int | None,
    confirm: bool,
) -> dict[str, Any]:
    plan_path = report_dir / "relationship_evidence_plan.jsonl"
    unresolved_path = report_dir / "relationship_evidence_unresolved.jsonl"
    totals = Counter()
    by_rel_type: dict[str, Counter] = {}
    applied = 0
    batches = 0

    while True:
        if max_batches is not None and batches >= max_batches:
            break
        rows = fetch_missing_evidence_batch(session, rel_types, batch_size, RUN_ID)
        if not rows:
            break
        batches += 1
        updates = [infer_evidence(row, resolver, resolver.max_chunks) for row in rows]
        plan_rows = [update for update in updates if update["will_update"]]
        unresolved = [update for update in updates if not update["will_have_both"]]
        append_jsonl(plan_path, plan_rows)
        append_jsonl(unresolved_path, unresolved)

        for update in updates:
            rel_counter = by_rel_type.setdefault(update["rel_type"], Counter())
            rel_counter["scanned"] += 1
            totals["scanned"] += 1
            if update["will_update"]:
                rel_counter["planned_updates"] += 1
                totals["planned_updates"] += 1
            if update["will_update_source_doc"]:
                rel_counter["source_doc_updates"] += 1
                totals["source_doc_updates"] += 1
            if update["will_update_source_chunk_ids"]:
                rel_counter["source_chunk_id_updates"] += 1
                totals["source_chunk_id_updates"] += 1
            if update["will_have_both"]:
                rel_counter["will_have_both"] += 1
                totals["will_have_both"] += 1
            else:
                rel_counter["unresolved_after_inference"] += 1
                totals["unresolved_after_inference"] += 1

        if confirm:
            mark_scanned_unresolved(session, updates, RUN_ID)
            applied += apply_evidence_updates(session, plan_rows, RUN_ID)
        else:
            break

    return {
        "batches": batches,
        "totals": dict(totals),
        "by_rel_type": {rel_type: dict(counter) for rel_type, counter in sorted(by_rel_type.items())},
        "applied_updates": applied,
        "plan_path": str(plan_path),
        "unresolved_path": str(unresolved_path),
        "stopped_after_max_batches": max_batches is not None and batches >= max_batches,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="apply changes")
    parser.add_argument("--rel-type", action="append", choices=DEFAULT_REL_TYPES, help="target relation type; repeatable")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--max-batches", type=int, default=None, help="limit batches for preview/debug")
    parser.add_argument("--max-rel-chunks", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rel_types = args.rel_type or list(DEFAULT_REL_TYPES)
    report_dir = REPORT_ROOT / RUN_ID
    resolver = ChunkResolver(SQLITE_DB, ALIAS_PATH, args.max_rel_chunks)
    driver = connect()
    try:
        with driver.session() as session:
            before = {
                "relationship_evidence": evidence_counts(session, rel_types),
                "position_pollution": position_counts(session),
            }
            write_json(report_dir / "before.json", before)
            evidence_result = plan_and_apply_evidence(
                session=session,
                resolver=resolver,
                rel_types=rel_types,
                report_dir=report_dir,
                batch_size=args.batch_size,
                max_batches=args.max_batches,
                confirm=args.confirm,
            )
            position_normalized = 0
            if args.confirm:
                position_normalized = normalize_positions(session, RUN_ID)
            after = {
                "relationship_evidence": evidence_counts(session, rel_types),
                "position_pollution": position_counts(session),
            }
            result = {
                "run_id": RUN_ID,
                "created_at": now_text(),
                "dry_run": not args.confirm,
                "rel_types": rel_types,
                "report_dir": str(report_dir),
                "before": before,
                "evidence_result": evidence_result,
                "position_normalized": position_normalized,
                "after": after,
            }
            write_json(report_dir / "summary.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=json_default))
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
