#!/usr/bin/env python3
"""Govern remaining low-risk KG health issues.

Actions with --confirm:
- add the generic :Entity label to all non-Document nodes
- merge exact same-name nodes into one multi-label canonical node
- backfill missing Document-[:CONTAINS]->Entity provenance edges from safe source_doc matches
- report isolated Neo4j-only knowledge descriptions without turning them into sources

The script writes a JSON backup report before mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
SQLITE_DB = BASE_DIR / "rag_chunks.db"
REPORT_ROOT = BASE_DIR / "review_reports"

WHITELIST_LABELS = {
    "Company", "Organization", "PlatformPresence", "Event", "Course", "Exam",
    "Certification", "KnowledgePoint", "Category", "Student", "Teacher", "Person",
    "Policy", "Regulation", "SocialContent", "Skill", "EducationRequirement",
    "AircraftType", "LicenseLevel", "WeightClass", "Location", "Position",
    "Chapter", "Section", "Scenario", "DesignTool", "FabricationStep",
    "Document", "Entity",
}

SKIP_PROP_KEYS = {"embedding"}
RUN_ID = f"kg_health_governance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def json_default(value: Any) -> str:
    return str(value)


def safe_props(props: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in props.items():
        if key in SKIP_PROP_KEYS:
            result[key] = f"<omitted:{key}>"
        elif isinstance(value, list) and len(value) > 30:
            result[key] = f"<omitted:list:{len(value)}>"
        else:
            result[key] = value
    return result


def prop_is_writable(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(isinstance(v, (str, int, float, bool)) for v in value)
    return False


def escape_ident(value: str) -> str:
    return value.replace("`", "``")


def business_labels(labels: list[str]) -> list[str]:
    return [label for label in labels if label not in {"Entity", "Document"}]


def source_doc_values(props: dict[str, Any]) -> set[str]:
    values = set()
    for key in ("source_doc", "_created_by", "created_by"):
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            values.add(value.strip())
    for key in ("source_docs", "created_by_docs"):
        value = props.get(key)
        if isinstance(value, list):
            values.update(str(item).strip() for item in value if str(item).strip())
    return values


def node_type_values(labels: list[str], props: dict[str, Any]) -> set[str]:
    values = set(business_labels(labels))
    prop_type = props.get("type")
    if isinstance(prop_type, str) and prop_type in WHITELIST_LABELS:
        values.add(prop_type)
    return values


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def sqlite_fingerprint() -> dict[str, Any]:
    with sqlite3.connect(SQLITE_DB) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS chunk_count, COUNT(DISTINCT doc_name) AS doc_count, "
            "COALESCE(SUM(LENGTH(text)), 0) AS text_bytes FROM chunks"
        ).fetchone()
    return {"chunk_count": row[0], "doc_count": row[1], "text_bytes": row[2]}


def health_counts(session) -> dict[str, int]:
    conflict_count = session.run(
        """
        MATCH (n) WHERE NOT n:Document AND n.name IS NOT NULL
        WITH n.name AS nm,
             collect(DISTINCT coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity')) AS types
        WHERE size(types) > 1
        RETURN count(*) AS c
        """
    ).single()["c"]
    return {
        "type_conflicts": conflict_count,
        "docs_without_contains": session.run(
            "MATCH (d:Document) WHERE NOT (d)-[:CONTAINS]->() RETURN count(d) AS c"
        ).single()["c"],
        "isolated_nodes": session.run(
            "MATCH (n) WHERE NOT (n)--() AND NOT n:Document RETURN count(n) AS c"
        ).single()["c"],
        "missing_entity_label": session.run(
            "MATCH (n) WHERE NOT n:Document AND NOT n:Entity RETURN count(n) AS c"
        ).single()["c"],
    }


def export_snapshot(session, report_dir: Path) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)

    conflicts = session.run(
        """
        MATCH (n) WHERE NOT n:Document AND n.name IS NOT NULL
        WITH n, coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity') AS primary_type,
             COUNT { (n)--() } AS degree
        WITH n.name AS name,
             collect({
               id: elementId(n),
               labels: labels(n),
               primary_type: primary_type,
               degree: degree,
               props: properties(n)
             }) AS nodes,
             collect(DISTINCT primary_type) AS types
        WHERE size(types) > 1
        RETURN name, types, nodes ORDER BY name
        """
    ).data()
    for row in conflicts:
        for node in row["nodes"]:
            node["props"] = safe_props(node["props"])
    write_json(report_dir / "type_conflicts.json", conflicts)

    docs = session.run(
        """
        MATCH (d:Document) WHERE NOT (d)-[:CONTAINS]->()
        OPTIONAL MATCH (d)-[r]-()
        WITH d, collect(DISTINCT type(r)) AS rel_types, COUNT { (d)--() } AS degree
        RETURN elementId(d) AS id, d.name AS name, labels(d) AS labels,
               properties(d) AS props, rel_types, degree
        ORDER BY d.name
        """
    ).data()
    for row in docs:
        row["props"] = safe_props(row["props"])
    write_json(report_dir / "docs_without_contains.json", docs)

    isolated = session.run(
        """
        MATCH (n) WHERE NOT (n)--() AND NOT n:Document
        RETURN elementId(n) AS id, labels(n) AS labels, n.name AS name,
               properties(n) AS props
        ORDER BY n.name
        """
    ).data()
    for row in isolated:
        row["props"] = safe_props(row["props"])
    write_json(report_dir / "isolated_nodes.json", isolated)

    missing_entity = session.run(
        """
        MATCH (n) WHERE NOT n:Document AND NOT n:Entity
        RETURN elementId(n) AS id, labels(n) AS labels, n.name AS name,
               properties(n) AS props
        ORDER BY coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity'), n.name
        """
    ).data()
    for row in missing_entity:
        row["props"] = safe_props(row["props"])
    write_json(report_dir / "missing_entity_label.json", missing_entity)

    summary = {
        "run_id": RUN_ID,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sqlite_before": sqlite_fingerprint(),
        "health_before": health_counts(session),
        "backup_files": [
            "type_conflicts.json",
            "docs_without_contains.json",
            "isolated_nodes.json",
            "missing_entity_label.json",
        ],
    }
    write_json(report_dir / "summary_before.json", summary)
    return summary


def add_entity_label(session) -> int:
    return session.run(
        """
        MATCH (n) WHERE NOT n:Document AND NOT n:Entity
        SET n:Entity
        RETURN count(n) AS c
        """
    ).single()["c"]


def create_relationship(session, start_id: str, end_id: str, rel_type: str, props: dict[str, Any]) -> None:
    rel = escape_ident(rel_type)
    clean_props = {k: v for k, v in props.items() if prop_is_writable(v)}
    session.run(
        f"""
        MATCH (a) WHERE elementId(a) = $start_id
        MATCH (b) WHERE elementId(b) = $end_id
        MERGE (a)-[r:`{rel}`]->(b)
        SET r += $props
        """,
        start_id=start_id,
        end_id=end_id,
        props=clean_props,
    )


def set_node_labels(session, node_id: str, labels: set[str]) -> None:
    for label in sorted(labels):
        if label == "Document" or label not in WHITELIST_LABELS:
            continue
        session.run(
            f"MATCH (n) WHERE elementId(n) = $id SET n:`{escape_ident(label)}`",
            id=node_id,
        )


def merge_node_group(session, group: dict[str, Any]) -> dict[str, Any]:
    nodes = sorted(group["nodes"], key=lambda n: (n["degree"], len(n["labels"])), reverse=True)
    keeper = nodes[0]
    keeper_id = keeper["id"]
    group_ids = {node["id"] for node in nodes}

    all_labels: set[str] = set()
    all_source_docs: set[str] = set()
    all_types: set[str] = set()
    all_chunk_ids: set[str] = set()
    patch: dict[str, Any] = {}
    merged_ids = []
    converted_contains = 0

    for node in nodes:
        props = node["props"]
        all_labels.update(node["labels"])
        all_source_docs.update(source_doc_values(props))
        all_types.update(node_type_values(node["labels"], props))
        chunk_id = props.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id:
            all_chunk_ids.add(chunk_id)
        if node["id"] != keeper_id:
            merged_ids.append(node["id"])

    keeper_props = session.run(
        "MATCH (n) WHERE elementId(n) = $id RETURN properties(n) AS props",
        id=keeper_id,
    ).single()["props"]
    for node in nodes[1:]:
        for key, value in node["props"].items():
            if key in SKIP_PROP_KEYS or not prop_is_writable(value):
                continue
            if key not in keeper_props or keeper_props.get(key) in (None, "", []):
                patch[key] = value

    descriptions = [
        node["props"].get("description")
        for node in nodes
        if isinstance(node["props"].get("description"), str) and node["props"].get("description").strip()
    ]
    if descriptions and not keeper_props.get("description"):
        patch["description"] = max(descriptions, key=len)

    set_node_labels(session, keeper_id, all_labels)
    if all_types:
        patch.setdefault("type", sorted(all_types)[0])
    patch["types"] = sorted(all_types)
    patch["source_docs"] = sorted(all_source_docs)
    if all_chunk_ids:
        patch["chunk_ids"] = sorted(all_chunk_ids)
        patch.setdefault("chunk_id", sorted(all_chunk_ids)[0])
    patch["merged_from_element_ids"] = sorted(set(keeper_props.get("merged_from_element_ids", [])) | set(merged_ids))
    patch["merged_at"] = datetime.now().isoformat(timespec="seconds")
    patch["merged_by"] = RUN_ID
    session.run("MATCH (n) WHERE elementId(n) = $id SET n += $patch", id=keeper_id, patch=patch)

    for node in nodes[1:]:
        dup_id = node["id"]
        outgoing = session.run(
            """
            MATCH (n)-[r]->(m) WHERE elementId(n) = $id
            RETURN elementId(m) AS other_id, labels(m) AS other_labels, m.name AS other_name,
                   type(r) AS rel_type, properties(r) AS props
            """,
            id=dup_id,
        ).data()
        incoming = session.run(
            """
            MATCH (m)-[r]->(n) WHERE elementId(n) = $id
            RETURN elementId(m) AS other_id, labels(m) AS other_labels, m.name AS other_name,
                   type(r) AS rel_type, properties(r) AS props
            """,
            id=dup_id,
        ).data()

        for rel in outgoing:
            if rel["other_id"] in group_ids:
                continue
            create_relationship(session, keeper_id, rel["other_id"], rel["rel_type"], rel["props"])

        for rel in incoming:
            if rel["other_id"] in group_ids:
                continue
            rel_type = rel["rel_type"]
            props = rel["props"]
            if "Document" in rel["other_labels"] and rel_type == "CONTAINS":
                rel_type = "DESCRIBES"
                props = {**props, "legacy_type": "CONTAINS", "converted_by": RUN_ID}
                converted_contains += 1
            create_relationship(session, rel["other_id"], keeper_id, rel_type, props)

        session.run("MATCH (n) WHERE elementId(n) = $id DETACH DELETE n", id=dup_id)

    return {
        "name": group["name"],
        "keeper": keeper_id,
        "merged": len(nodes) - 1,
        "converted_document_contains": converted_contains,
    }


def merge_type_conflicts(session) -> list[dict[str, Any]]:
    groups = session.run(
        """
        MATCH (n) WHERE NOT n:Document AND n.name IS NOT NULL
        WITH n, coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity') AS primary_type,
             COUNT { (n)--() } AS degree
        WITH n.name AS name,
             collect({
               id: elementId(n),
               labels: labels(n),
               props: properties(n),
               degree: degree,
               primary_type: primary_type
             }) AS nodes,
             collect(DISTINCT primary_type) AS types
        WHERE size(types) > 1
        RETURN name, types, nodes ORDER BY name
        """
    ).data()
    return [merge_node_group(session, group) for group in groups if len(group["nodes"]) > 1]


def normalize_doc_name(name: str) -> str:
    return re.sub(r"（文档）$", "", name or "").strip()


def backfill_document_contains(session) -> list[dict[str, Any]]:
    docs = session.run(
        """
        MATCH (d:Document) WHERE NOT (d)-[:CONTAINS]->()
        RETURN elementId(d) AS id, d.name AS name
        ORDER BY d.name
        """
    ).data()
    results = []
    for doc in docs:
        name = doc["name"]
        core = normalize_doc_name(name)
        count = session.run(
            """
            MATCH (d:Document) WHERE elementId(d) = $doc_id
            MATCH (d)-[:DESCRIBES]->(e)
            WHERE NOT e:Document
              AND (
                e._created_by IN $names
                OR e.source_doc IN $names
                OR (
                  e.source_doc IS NOT NULL
                  AND size(toString(e.source_doc)) >= 4
                  AND ($doc_name CONTAINS toString(e.source_doc)
                       OR $core CONTAINS toString(e.source_doc))
                )
              )
            MERGE (d)-[r:CONTAINS]->(e)
            ON CREATE SET r.created_by = $run_id, r.created_at = datetime()
            RETURN count(r) AS c
            """,
            doc_id=doc["id"],
            names=[name, core],
            doc_name=name,
            core=core,
            run_id=RUN_ID,
        ).single()["c"]
        results.append({"document": name, "contains_edges": count})
    return results


def refresh_documents_table(conn: sqlite3.Connection, doc_names: set[str]) -> None:
    for doc_name in doc_names:
        count = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_name = ?", (doc_name,)).fetchone()[0]
        conn.execute(
            """
            INSERT INTO documents (doc_name, doc_path, chunk_count, updated_at)
            VALUES (?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(doc_name) DO UPDATE SET
                chunk_count = excluded.chunk_count,
                updated_at = excluded.updated_at
            """,
            (doc_name, doc_name, count),
        )


def report_unsupported_isolated_nodes(session) -> list[dict[str, Any]]:
    """Return isolated graph-only nodes that still need source-backed ingestion or deletion.

    These nodes are not promoted into SQLite chunks. Canonical answer sources must come
    from imported documents, not from graph-only descriptions.
    """
    rows = session.run(
        """
        MATCH (n) WHERE NOT (n)--() AND NOT n:Document
        RETURN elementId(n) AS id, labels(n) AS labels, n.name AS name, properties(n) AS props
        ORDER BY coalesce(n.source_doc, ''), n.name
        """
    ).data()
    return [
        {
            "id": row["id"],
            "labels": row["labels"],
            "name": row["name"],
            "props": safe_props(row["props"]),
            "action": "not_promoted_to_source",
        }
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="apply changes; otherwise only writes backup")
    args = parser.parse_args()

    report_dir = REPORT_ROOT / RUN_ID
    driver = connect()
    try:
        with driver.session() as session:
            summary = export_snapshot(session, report_dir)
            print(json.dumps(summary, ensure_ascii=False, indent=2, default=json_default))
            if not args.confirm:
                print(f"Dry run only. Backup written to {report_dir}")
                return 0

            actions = {
                "entity_labels_added": add_entity_label(session),
                "type_conflict_merges": merge_type_conflicts(session),
                "document_contains_backfill": backfill_document_contains(session),
                "unsupported_isolated_nodes": report_unsupported_isolated_nodes(session),
            }
            post = {
                "run_id": RUN_ID,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "actions": actions,
                "health_after": health_counts(session),
                "sqlite_after": sqlite_fingerprint(),
            }
            write_json(report_dir / "summary_after.json", post)
            print(json.dumps(post, ensure_ascii=False, indent=2, default=json_default))
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
