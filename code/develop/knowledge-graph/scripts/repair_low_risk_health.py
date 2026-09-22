#!/usr/bin/env python3
"""Repair low-risk KG/RAG metadata drift.

Dry-run by default. With --confirm this script only performs bounded repairs:
- backfill missing Entity.type from existing business labels
- link source_doc-backed orphan entities to existing Document nodes
- synchronize SQLite documents metadata from the canonical chunks table

It intentionally does not merge nodes, delete data, or create synthetic documents.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_DB = BASE_DIR / "rag_chunks.db"
REPORT_ROOT = BASE_DIR / "review_reports"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
RUN_ID = f"low_risk_health_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

IGNORED_LABELS = {"Entity", "Document"}
TYPE_PRIORITY = [
    "Company",
    "Organization",
    "PlatformPresence",
    "Event",
    "Course",
    "Exam",
    "Certification",
    "KnowledgePoint",
    "Category",
    "Student",
    "Teacher",
    "Person",
    "Policy",
    "Regulation",
    "SocialContent",
    "Skill",
    "EducationRequirement",
    "AircraftType",
    "LicenseLevel",
    "WeightClass",
    "Location",
    "Position",
    "Chapter",
    "Section",
    "Scenario",
    "DesignTool",
    "FabricationStep",
]


def json_default(value: Any) -> str:
    return str(value)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def primary_type(labels: list[str]) -> str | None:
    for label in TYPE_PRIORITY:
        if label in labels:
            return label
    for label in labels:
        if label not in IGNORED_LABELS:
            return label
    return None


def connect_neo4j():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def get_missing_types(session) -> list[dict[str, Any]]:
    rows = session.run(
        """
        MATCH (e:Entity)
        WHERE e.type IS NULL OR trim(toString(e.type)) = ''
        RETURN elementId(e) AS id, e.name AS name, labels(e) AS labels,
               e.source_doc AS source_doc, e._created_by AS created_by
        ORDER BY coalesce(e.name, '')
        """
    ).data()
    planned = []
    for row in rows:
        chosen = primary_type(row["labels"])
        if chosen:
            row["chosen_type"] = chosen
            planned.append(row)
    return planned


def get_document_names(session) -> list[str]:
    rows = session.run(
        """
        MATCH (d:Document)
        WHERE d.name IS NOT NULL AND trim(toString(d.name)) <> ''
        RETURN d.name AS name
        ORDER BY d.name
        """
    ).data()
    return [row["name"] for row in rows]


def resolve_document_name(source_doc: str, document_names: list[str]) -> tuple[str | None, str]:
    source = (source_doc or "").strip()
    if not source:
        return None, "missing_source_doc"

    exact = [name for name in document_names if name == source]
    if len(exact) == 1:
        return exact[0], "exact"
    if len(exact) > 1:
        return None, "ambiguous_exact"

    contains = [name for name in document_names if source in name]
    if len(contains) == 1:
        return contains[0], "document_contains_source"
    if len(contains) > 1:
        return None, "ambiguous_contains"

    return None, "no_document_match"


def get_orphan_entities(session, document_names: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = session.run(
        """
        MATCH (e:Entity)
        WHERE NOT (:Document)-[:CONTAINS]->(e)
        RETURN elementId(e) AS id, e.name AS name, labels(e) AS labels,
               e.source_doc AS source_doc, e._created_by AS created_by
        ORDER BY coalesce(e.source_doc, ''), coalesce(e.name, '')
        """
    ).data()

    resolvable: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for row in rows:
        source_doc = (row.get("source_doc") or row.get("created_by") or "").strip()
        doc_name, reason = resolve_document_name(source_doc, document_names)
        row["resolution_reason"] = reason
        row["resolved_document"] = doc_name
        if not doc_name:
            unresolved.append(row)
            continue

        created_by = (row.get("created_by") or "").strip()
        if created_by and created_by not in {doc_name, source_doc}:
            row["resolution_reason"] = f"created_by_conflict:{created_by}"
            row["resolved_document"] = None
            unresolved.append(row)
            continue

        resolvable.append(row)

    return resolvable, unresolved


def sqlite_doc_drift() -> dict[str, Any]:
    with sqlite3.connect(SQLITE_DB) as conn:
        conn.row_factory = sqlite3.Row
        chunk_docs = {
            row["doc_name"]: row["chunk_count"]
            for row in conn.execute(
                "SELECT doc_name, COUNT(*) AS chunk_count FROM chunks GROUP BY doc_name ORDER BY doc_name"
            ).fetchall()
        }
        table_docs = {
            row["doc_name"]: row["chunk_count"]
            for row in conn.execute(
                "SELECT doc_name, chunk_count FROM documents ORDER BY doc_name"
            ).fetchall()
        }

    missing = [
        {"doc_name": doc_name, "chunk_count": chunk_docs[doc_name]}
        for doc_name in sorted(set(chunk_docs) - set(table_docs))
    ]
    stale = [
        {
            "doc_name": doc_name,
            "table_chunk_count": table_docs[doc_name],
            "actual_chunk_count": chunk_docs[doc_name],
        }
        for doc_name in sorted(set(chunk_docs) & set(table_docs))
        if table_docs[doc_name] != chunk_docs[doc_name]
    ]
    extra = [
        {"doc_name": doc_name, "table_chunk_count": table_docs[doc_name]}
        for doc_name in sorted(set(table_docs) - set(chunk_docs))
    ]
    return {
        "chunks_distinct_docs": len(chunk_docs),
        "documents_table_docs": len(table_docs),
        "missing_in_documents_table": missing,
        "stale_chunk_counts": stale,
        "extra_documents_without_chunks": extra,
    }


def health_counts(session) -> dict[str, int]:
    return {
        "entity_missing_type": session.run(
            "MATCH (e:Entity) WHERE e.type IS NULL OR trim(toString(e.type)) = '' RETURN count(e) AS c"
        ).single()["c"],
        "orphan_entities": session.run(
            "MATCH (e:Entity) WHERE NOT (:Document)-[:CONTAINS]->(e) RETURN count(e) AS c"
        ).single()["c"],
        "cross_pollution": session.run(
            """
            MATCH (d:Document)-[:CONTAINS]->(e:Entity)
            WHERE e._created_by IS NOT NULL AND e._created_by <> d.name
            RETURN count(*) AS c
            """
        ).single()["c"],
        "chunk_nodes": session.run("MATCH (c:Chunk) RETURN count(c) AS c").single()["c"],
    }


def backfill_types(session, planned: list[dict[str, Any]]) -> int:
    count = 0
    for item in planned:
        result = session.run(
            """
            MATCH (e)
            WHERE elementId(e) = $id
            SET e.type = $type,
                e.type_backfilled_by = $run_id,
                e.type_backfilled_at = datetime()
            RETURN count(e) AS c
            """,
            id=item["id"],
            type=item["chosen_type"],
            run_id=RUN_ID,
        ).single()["c"]
        count += result
    return count


def link_orphans(session, resolvable: list[dict[str, Any]]) -> int:
    count = 0
    for item in resolvable:
        result = session.run(
            """
            MATCH (d:Document {name: $doc_name})
            MATCH (e)
            WHERE elementId(e) = $entity_id
            SET e._created_by = CASE
                    WHEN e._created_by IS NULL OR trim(toString(e._created_by)) = ''
                    THEN $doc_name ELSE e._created_by
                END,
                e.source_doc_resolved_doc = $doc_name,
                e.provenance_repaired_by = $run_id,
                e.provenance_repaired_at = datetime()
            MERGE (d)-[r:CONTAINS]->(e)
            ON CREATE SET r.created_by = $run_id, r.created_at = datetime()
            ON MATCH SET r.checked_by = $run_id, r.checked_at = datetime()
            RETURN count(r) AS c
            """,
            doc_name=item["resolved_document"],
            entity_id=item["id"],
            run_id=RUN_ID,
        ).single()["c"]
        count += result
    return count


def sync_sqlite_documents() -> dict[str, int]:
    with sqlite3.connect(SQLITE_DB) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        rows = conn.execute(
            "SELECT doc_name, COUNT(*) AS chunk_count FROM chunks GROUP BY doc_name ORDER BY doc_name"
        ).fetchall()
        before = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        for row in rows:
            conn.execute(
                """
                INSERT INTO documents (doc_name, doc_path, chunk_count, updated_at)
                VALUES (?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(doc_name) DO UPDATE SET
                    doc_path = COALESCE(NULLIF(documents.doc_path, ''), excluded.doc_path),
                    chunk_count = excluded.chunk_count,
                    updated_at = excluded.updated_at
                """,
                (row["doc_name"], row["doc_name"], row["chunk_count"]),
            )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
    return {"documents_before": before, "documents_after": after, "chunk_doc_count": len(rows)}


def build_plan(report_dir: Path, session) -> dict[str, Any]:
    document_names = get_document_names(session)
    missing_types = get_missing_types(session)
    resolvable_orphans, unresolved_orphans = get_orphan_entities(session, document_names)
    drift = sqlite_doc_drift()
    plan = {
        "run_id": RUN_ID,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "confirm_required": True,
        "health_before": health_counts(session),
        "planned": {
            "type_backfills": len(missing_types),
            "source_doc_orphans_to_link": len(resolvable_orphans),
            "orphan_entities_left_unresolved": len(unresolved_orphans),
            "sqlite_documents_missing": len(drift["missing_in_documents_table"]),
            "sqlite_documents_stale_counts": len(drift["stale_chunk_counts"]),
            "sqlite_documents_extra_without_chunks": len(drift["extra_documents_without_chunks"]),
        },
        "details": {
            "type_backfills": missing_types,
            "source_doc_orphans_to_link": resolvable_orphans,
            "orphan_entities_left_unresolved": unresolved_orphans,
            "sqlite_document_drift": drift,
        },
    }
    write_json(report_dir / "plan.json", plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="apply the planned low-risk repairs")
    parser.add_argument(
        "--max-orphans-to-link",
        type=int,
        default=100,
        help="safety guard for the number of orphan entities to link in one run",
    )
    parser.add_argument("--report-dir", type=Path, help="override report directory")
    args = parser.parse_args()

    report_dir = args.report_dir or (REPORT_ROOT / RUN_ID)
    report_dir.mkdir(parents=True, exist_ok=True)

    driver = connect_neo4j()
    try:
        with driver.session() as session:
            plan = build_plan(report_dir, session)
            planned = plan["planned"]
            print(
                "plan: "
                f"type_backfills={planned['type_backfills']}, "
                f"orphans_to_link={planned['source_doc_orphans_to_link']}, "
                f"orphans_unresolved={planned['orphan_entities_left_unresolved']}, "
                f"sqlite_docs_missing={planned['sqlite_documents_missing']}, "
                f"sqlite_docs_stale={planned['sqlite_documents_stale_counts']}"
            )
            print(f"report: {report_dir}")

            if planned["source_doc_orphans_to_link"] > args.max_orphans_to_link:
                print(
                    "abort: planned orphan links exceed --max-orphans-to-link "
                    f"({planned['source_doc_orphans_to_link']} > {args.max_orphans_to_link})"
                )
                return 2

            if not args.confirm:
                print("dry-run only; rerun with --confirm to apply")
                return 0

            type_count = backfill_types(session, plan["details"]["type_backfills"])
            orphan_count = link_orphans(session, plan["details"]["source_doc_orphans_to_link"])
            sqlite_sync = sync_sqlite_documents()
            after = {
                "run_id": RUN_ID,
                "applied_at": datetime.now().isoformat(timespec="seconds"),
                "applied": {
                    "type_backfilled": type_count,
                    "source_doc_orphans_linked": orphan_count,
                    "sqlite_sync": sqlite_sync,
                },
                "health_after": health_counts(session),
                "sqlite_drift_after": sqlite_doc_drift(),
            }
            write_json(report_dir / "after.json", after)
            print(
                "applied: "
                f"type_backfilled={type_count}, "
                f"orphans_linked={orphan_count}, "
                f"sqlite_documents={sqlite_sync['documents_before']}->{sqlite_sync['documents_after']}"
            )
            print(
                "after: "
                f"missing_type={after['health_after']['entity_missing_type']}, "
                f"orphans={after['health_after']['orphan_entities']}, "
                f"cross_pollution={after['health_after']['cross_pollution']}, "
                f"chunk_nodes={after['health_after']['chunk_nodes']}"
            )
            return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
