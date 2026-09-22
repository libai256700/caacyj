#!/usr/bin/env python3
"""Deduplicate low-risk Neo4j relationships.

Actions with --confirm:
- merge duplicate relationships with the same start node, end node, and type
- convert legacy HAS_SALARY course-price edges to HAS_PROPERTY

The script writes a JSON report before mutation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_ROOT = BASE_DIR / "review_reports"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
RUN_ID = f"kg_relationship_dedupe_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LIST_PROPS = {"source_chunk_ids", "source_docs", "evidence_chunk_ids"}


def json_default(value: Any) -> str:
    return str(value)


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def counts(session) -> dict[str, int]:
    return {
        "nodes": session.run("MATCH (n) RETURN count(n) AS c").single()["c"],
        "relationships": session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"],
        "duplicate_groups": session.run(
            """
            MATCH (a)-[r]->(b)
            WITH elementId(a) AS start_id, elementId(b) AS end_id, type(r) AS rel_type, count(r) AS c
            WHERE c > 1
            RETURN count(*) AS c
            """
        ).single()["c"],
        "duplicate_relationships": session.run(
            """
            MATCH (a)-[r]->(b)
            WITH elementId(a) AS start_id, elementId(b) AS end_id, type(r) AS rel_type, count(r) AS c
            WHERE c > 1
            RETURN coalesce(sum(c - 1), 0) AS c
            """
        ).single()["c"],
        "has_salary": session.run("MATCH ()-[r:HAS_SALARY]->() RETURN count(r) AS c").single()["c"],
    }


def export_preview(session, report_dir: Path) -> dict[str, Any]:
    groups = session.run(
        """
        MATCH (a)-[r]->(b)
        WITH a, b, type(r) AS rel_type, count(r) AS c
        WHERE c > 1
        RETURN rel_type, a.name AS start_name, labels(a) AS start_labels,
               b.name AS end_name, labels(b) AS end_labels, c
        ORDER BY c DESC, rel_type, start_name, end_name
        LIMIT 100
        """
    ).data()
    bad_salary = session.run(
        """
        MATCH (a)-[r:HAS_SALARY]->(b)
        RETURN a.name AS start_name, labels(a) AS start_labels,
               b.name AS end_name, labels(b) AS end_labels, properties(r) AS props
        LIMIT 20
        """
    ).data()
    summary = {
        "run_id": RUN_ID,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "before": counts(session),
        "sample_duplicate_groups": groups,
        "has_salary_edges": bad_salary,
    }
    write_json(report_dir / "relationship_dedupe_preview.json", summary)
    return summary


def merge_props(rows: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for row in rows:
        props = row.get("props") or {}
        for key, value in props.items():
            if value in (None, "", []):
                continue
            if key in LIST_PROPS or isinstance(value, list):
                current = merged.setdefault(key, [])
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if item not in current:
                        current.append(item)
            elif key not in merged:
                merged[key] = value
    return merged


def dedupe_group(session, rel_ids: list[str]) -> int:
    if len(rel_ids) <= 1:
        return 0
    rows = session.run(
        """
        MATCH ()-[r]->()
        WHERE elementId(r) IN $rel_ids
        RETURN elementId(r) AS id, properties(r) AS props
        """,
        rel_ids=rel_ids,
    ).data()
    keep = rel_ids[0]
    delete_ids = rel_ids[1:]
    props = merge_props(rows)
    props["deduped_by"] = RUN_ID
    props["deduped_at"] = datetime.now().isoformat(timespec="seconds")
    props["deduped_count"] = len(delete_ids)
    session.run(
        """
        MATCH ()-[r]->()
        WHERE elementId(r) = $keep
        SET r += $props
        WITH r
        MATCH ()-[dup]->()
        WHERE elementId(dup) IN $delete_ids
        DELETE dup
        RETURN count(dup) AS deleted
        """,
        keep=keep,
        delete_ids=delete_ids,
        props=props,
    ).consume()
    return len(delete_ids)


def dedupe_relationships(session, batch_size: int) -> dict[str, int]:
    total_deleted = 0
    total_groups = 0
    while True:
        groups = session.run(
            """
            MATCH (a)-[r]->(b)
            WITH elementId(a) AS start_id, elementId(b) AS end_id, type(r) AS rel_type,
                 collect(elementId(r)) AS rel_ids, count(r) AS c
            WHERE c > 1
            RETURN rel_ids
            LIMIT $limit
            """,
            limit=batch_size,
        ).data()
        if not groups:
            break
        for group in groups:
            total_deleted += dedupe_group(session, group["rel_ids"])
            total_groups += 1
    return {"groups_merged": total_groups, "relationships_deleted": total_deleted}


def convert_has_salary(session) -> int:
    converted = session.run(
        """
        MATCH (a)-[r:HAS_SALARY]->(b)
        MERGE (a)-[new:HAS_PROPERTY]->(b)
        SET new += properties(r),
            new.property_name = coalesce(r.description, '价格'),
            new.legacy_type = 'HAS_SALARY',
            new.converted_by = $run_id,
            new.converted_at = datetime()
        DELETE r
        RETURN count(new) AS c
        """,
        run_id=RUN_ID,
    ).single()["c"]
    session.run(
        """
        MATCH (a)-[new:HAS_PROPERTY]->(b)
        MATCH (a)-[old:OFFERS]->(b)
        WHERE old.legacy_type = 'HAS_SALARY'
          AND coalesce(old.description, '') = coalesce(new.description, '')
        DELETE old
        """
    ).consume()
    return converted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="apply changes")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    report_dir = REPORT_ROOT / RUN_ID
    driver = connect()
    try:
        with driver.session() as session:
            preview = export_preview(session, report_dir)
            print(json.dumps(preview, ensure_ascii=False, indent=2, default=json_default))
            if not args.confirm:
                print(f"Dry run only. Report written to {report_dir}")
                return 0
            actions = {
                "dedupe": dedupe_relationships(session, args.batch_size),
                "has_salary_converted": convert_has_salary(session),
            }
            result = {
                "run_id": RUN_ID,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "actions": actions,
                "after": counts(session),
            }
            write_json(report_dir / "relationship_dedupe_after.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=json_default))
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
