#!/usr/bin/env python3
"""Apply bounded semantic-graph v2 repairs.

Dry-run by default. With --confirm this script:
- normalizes deprecated HAS_SALARY relations to HAS_PROPERTY
- backfills deterministic entity_id/domain/canonical_name/schema_version
- backfills Document domain/schema_version and evidence flags

It does not delete nodes, merge names, or modify SQLite chunk text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from rag_store.semantic_schema import SCHEMA_VERSION, domain_for_doc_name, stable_entity_id
from rag_store.sqlite_store import RagStore


NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
TYPE_EXPR = "coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity')"
RAG_STORE = RagStore(str(BASE_DIR / "rag_chunks.db"))


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def collect_plan(session) -> dict[str, Any]:
    legacy_salary = session.run(
        """
        MATCH (a)-[r:HAS_SALARY]->(b)
        RETURN elementId(r) AS rel_id,
               a.name AS from_name,
               labels(a) AS from_labels,
               b.name AS to_name,
               labels(b) AS to_labels,
               properties(r) AS properties
        ORDER BY from_name, to_name
        LIMIT 100
        """
    ).data()
    missing_entity_props = session.run(
        """
        MATCH (n)
        WHERE NOT n:Document
          AND (n.entity_id IS NULL OR n.domain IS NULL OR n.canonical_name IS NULL OR n.schema_version <> $schema_version)
        RETURN count(n) AS count
        """,
        schema_version=SCHEMA_VERSION,
    ).single()["count"]
    missing_doc_props = session.run(
        """
        MATCH (d:Document)
        WHERE d.domain IS NULL OR d.schema_version <> $schema_version OR d.rag_resolved IS NULL
        RETURN count(d) AS count
        """,
        schema_version=SCHEMA_VERSION,
    ).single()["count"]
    return {
        "schema_version": SCHEMA_VERSION,
        "legacy_has_salary": legacy_salary,
        "missing_entity_semantic_props": int(missing_entity_props),
        "missing_document_semantic_props": int(missing_doc_props),
    }


def normalize_has_salary(session) -> int:
    result = session.run(
        """
        MATCH (a)-[r:HAS_SALARY]->(b)
        WITH a, r, b, properties(r) AS props
        MERGE (a)-[nr:HAS_PROPERTY]->(b)
        SET nr += props,
            nr.description = coalesce(props.description, "价格"),
            nr.property_name = coalesce(props.property_name, props.description, "价格"),
            nr.legacy_type = "HAS_SALARY",
            nr.schema_version = $schema_version,
            nr.migrated_at = datetime()
        DELETE r
        RETURN count(nr) AS count
        """,
        schema_version=SCHEMA_VERSION,
    )
    return int(result.single()["count"])


def backfill_documents(session) -> int:
    rows = session.run(
        """
        MATCH (d:Document)
        RETURN elementId(d) AS id,
               coalesce(d.canonical_doc_name, d.name, d.source_doc, d.path, "") AS doc_name,
               d.source_chunk_ids AS source_chunk_ids
        """
    ).data()
    count = 0
    for row in rows:
        doc_name = row.get("doc_name") or ""
        result = session.run(
            """
            MATCH (d)
            WHERE elementId(d) = $id
            SET d.domain = coalesce(d.domain, $domain),
                d.canonical_name = coalesce(d.canonical_name, $doc_name),
                d.schema_version = $schema_version,
                d.rag_resolved = coalesce(d.rag_resolved, d.canonical_doc_name IS NOT NULL OR d.source_doc IS NOT NULL),
                d.evidence_contract = "sqlite_chunk_text"
            RETURN count(d) AS count
            """,
            id=row["id"],
            domain=domain_for_doc_name(doc_name),
            doc_name=doc_name,
            schema_version=SCHEMA_VERSION,
        )
        count += int(result.single()["count"])
    return count


def exact_source_chunk_ids(name: str, source_doc: str) -> list[str]:
    name = (name or "").strip()
    source_doc = (source_doc or "").strip()
    if len(name) < 2 or not source_doc:
        return []
    chunks = RAG_STORE.find_chunks_by_doc_names([source_doc], limit_per_doc=40)
    matched = [
        row["chunk_id"]
        for row in chunks
        if name in (row.get("text") or "") or name in (row.get("doc_name") or "")
    ]
    return matched[:5]


def backfill_entities(session) -> dict[str, int]:
    rows = session.run(
        """
        MATCH (n)
        WHERE NOT n:Document
        RETURN elementId(n) AS id,
               coalesce(n.name, "") AS name,
               """ + TYPE_EXPR + """ AS type,
               coalesce(n.source_doc, n._created_by, "") AS source_doc,
               n.source_chunk_ids AS source_chunk_ids
        """
    ).data()
    count = 0
    chunk_bound = 0
    for row in rows:
        name = row.get("name") or ""
        entity_type = row.get("type") or "Entity"
        source_doc = row.get("source_doc") or name
        domain = domain_for_doc_name(source_doc or name)
        entity_id = stable_entity_id(domain, entity_type, name or row["id"])
        source_chunk_ids = row.get("source_chunk_ids") or exact_source_chunk_ids(name, source_doc)
        if source_chunk_ids and not row.get("source_chunk_ids"):
            chunk_bound += 1
        result = session.run(
            """
            MATCH (n)
            WHERE elementId(n) = $id
            SET n.entity_id = coalesce(n.entity_id, $entity_id),
                n.domain = coalesce(n.domain, $domain),
                n.canonical_name = coalesce(n.canonical_name, $canonical_name),
                n.schema_version = $schema_version,
                n.evidence_contract = "source_doc_or_source_chunk_ids_to_sqlite",
                n.source_chunk_ids = CASE
                    WHEN n.source_chunk_ids IS NULL AND size($source_chunk_ids) > 0 THEN $source_chunk_ids
                    ELSE n.source_chunk_ids
                END
            RETURN count(n) AS count
            """,
            id=row["id"],
            entity_id=entity_id,
            domain=domain,
            canonical_name=name,
            schema_version=SCHEMA_VERSION,
            source_chunk_ids=source_chunk_ids,
        )
        count += int(result.single()["count"])
    return {"entities_backfilled": count, "entities_bound_to_exact_chunks": chunk_bound}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="apply repairs")
    args = parser.parse_args()

    driver = connect()
    try:
        with driver.session() as session:
            plan = collect_plan(session)
            if not args.confirm:
                print(json.dumps({"dry_run": True, "plan": plan}, ensure_ascii=False, indent=2))
                return 0

            applied = {
                "normalized_has_salary": normalize_has_salary(session),
                "documents_backfilled": backfill_documents(session),
                **backfill_entities(session),
            }
            after = collect_plan(session)
            print(json.dumps({"dry_run": False, "applied": applied, "after": after}, ensure_ascii=False, indent=2))
            return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
