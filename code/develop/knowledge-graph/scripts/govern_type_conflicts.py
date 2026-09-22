#!/usr/bin/env python3
"""Govern same-name Neo4j type conflicts with conservative rules.

Actions with --confirm:
- merge duplicate Skill/KnowledgePoint concept nodes into one multi-label node
- merge Entity-only duplicates into the typed counterpart
- quarantine obvious jobs.csv pseudo-Company nodes that duplicate Position names
- rename job-market Position nodes only when they collide with non-position concepts

All changes are reported under review_reports/<run_id>/.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_ROOT = BASE_DIR / "review_reports"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
RUN_ID = f"type_conflict_governance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

MERGEABLE_TYPE_SETS = (
    frozenset({"Skill", "KnowledgePoint"}),
    frozenset({"Entity", "Course"}),
)


def json_default(value: Any) -> str:
    return str(value)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def primary_type(labels: list[str], props: dict[str, Any]) -> str:
    for label in labels:
        if label != "Entity":
            return label
    prop_type = props.get("type")
    return str(prop_type) if prop_type else "Entity"


def safe_props(props: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in props.items():
        if key == "embedding":
            out[key] = "<omitted:embedding>"
        elif isinstance(value, list) and len(value) > 25:
            out[key] = value[:25] + [f"<omitted:{len(value)-25}>"]
        else:
            out[key] = value
    return out


def prop_writable(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(isinstance(item, (str, int, float, bool)) for item in value)
    return False


def fetch_conflict_groups(session) -> list[dict[str, Any]]:
    groups = session.run(
        """
        MATCH (n)
        WHERE NOT n:Document
          AND n.name IS NOT NULL
          AND coalesce(n.quarantined, false) = false
        WITH n.name AS name,
             collect({
               id: elementId(n),
               labels: labels(n),
               props: properties(n),
               degree: count { (n)--() },
               out_degree: count { (n)-[]->() },
               in_degree: count { ()-->(n) }
             }) AS nodes,
             collect(DISTINCT coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity')) AS types
        WHERE size(types) > 1
        RETURN name, types, nodes ORDER BY name
        """
    ).data()
    for group in groups:
        for node in group["nodes"]:
            node["primary_type"] = primary_type(node["labels"], node["props"])
            node["props"] = dict(node["props"] or {})
    return groups


def export_snapshot(groups: list[dict[str, Any]], report_dir: Path) -> None:
    snapshot = []
    for group in groups:
        item = {**group, "nodes": [{**node, "props": safe_props(node["props"])} for node in group["nodes"]]}
        snapshot.append(item)
    write_json(report_dir / "type_conflicts_before.json", snapshot)


def classify_group(group: dict[str, Any]) -> tuple[str, str]:
    types = set(group["types"])
    if types in MERGEABLE_TYPE_SETS:
        return "merge", "mergeable_type_set"
    if "Position" in types and "Company" in types:
        companies = [node for node in group["nodes"] if node["primary_type"] == "Company"]
        if companies and all(node["props"].get("source_doc") == "jobs.csv" and node["degree"] <= 2 for node in companies):
            return "quarantine_company", "jobs_csv_pseudo_company"
    if "Position" in types and types - {"Position"}:
        return "rename_positions", "position_name_collision"
    if "QuestionBank" in types and "KnowledgePoint" in types:
        return "rename_knowledge_point", "question_bank_title_collision"
    return "review", "manual_review_required"


def source_values(props: dict[str, Any]) -> list[str]:
    values = []
    for key in ("source_doc", "_created_by", "created_by", "canonical_doc_name", "doc_name"):
        value = props.get(key)
        if isinstance(value, list):
            values.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            values.append(str(value).strip())
    return values


def chunk_values(props: dict[str, Any]) -> list[str]:
    values = []
    for key in ("source_chunk_ids", "evidence_chunk_ids", "source_chunks", "chunk_id"):
        value = props.get(key)
        if isinstance(value, list):
            values.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            values.append(str(value).strip())
    return values


def select_keeper(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    def score(node: dict[str, Any]) -> tuple[int, int, int, str]:
        labels = set(node["labels"])
        has_chunks = 1 if chunk_values(node["props"]) else 0
        has_source = 1 if source_values(node["props"]) else 0
        label_score = 2 if "KnowledgePoint" in labels else 1 if "Course" in labels else 0
        return (node["degree"], has_chunks, has_source + label_score, node["id"])

    return sorted(nodes, key=score, reverse=True)[0]


def merge_relationships(session, source_id: str, target_id: str, group_ids: set[str]) -> int:
    moved = 0
    outgoing = session.run(
        """
        MATCH (n)-[r]->(m) WHERE elementId(n)=$source_id
        RETURN elementId(m) AS other_id, type(r) AS rel_type, properties(r) AS props
        """,
        source_id=source_id,
    ).data()
    incoming = session.run(
        """
        MATCH (m)-[r]->(n) WHERE elementId(n)=$source_id
        RETURN elementId(m) AS other_id, type(r) AS rel_type, properties(r) AS props
        """,
        source_id=source_id,
    ).data()
    for row in outgoing:
        if row["other_id"] in group_ids:
            continue
        props = {k: v for k, v in dict(row["props"] or {}).items() if prop_writable(v)}
        session.run(
            f"""
            MATCH (a) WHERE elementId(a)=$target_id
            MATCH (b) WHERE elementId(b)=$other_id
            MERGE (a)-[r:`{row['rel_type']}`]->(b)
            SET r += $props
            """,
            target_id=target_id,
            other_id=row["other_id"],
            props=props,
        ).consume()
        moved += 1
    for row in incoming:
        if row["other_id"] in group_ids:
            continue
        props = {k: v for k, v in dict(row["props"] or {}).items() if prop_writable(v)}
        session.run(
            f"""
            MATCH (a) WHERE elementId(a)=$other_id
            MATCH (b) WHERE elementId(b)=$target_id
            MERGE (a)-[r:`{row['rel_type']}`]->(b)
            SET r += $props
            """,
            other_id=row["other_id"],
            target_id=target_id,
            props=props,
        ).consume()
        moved += 1
    return moved


def merge_group(session, group: dict[str, Any]) -> dict[str, Any]:
    keeper = select_keeper(group["nodes"])
    group_ids = {node["id"] for node in group["nodes"]}
    labels = sorted({label for node in group["nodes"] for label in node["labels"] if label != "Entity"})
    all_types = sorted({node["primary_type"] for node in group["nodes"]})
    sources = sorted({source for node in group["nodes"] for source in source_values(node["props"])})
    chunks = sorted({chunk for node in group["nodes"] for chunk in chunk_values(node["props"])})
    aliases = sorted({node["props"].get("entity_id") for node in group["nodes"] if node["props"].get("entity_id")})
    patch = {
        "type": keeper["primary_type"],
        "canonical_entity_types": all_types,
        "source_docs": sources,
        "source_chunk_ids": chunks[:120] or keeper["props"].get("source_chunk_ids"),
        "merged_entity_ids": aliases,
        "type_conflict_resolved_by": RUN_ID,
        "type_conflict_resolved_at": datetime.now().isoformat(timespec="seconds"),
        "type_conflict_resolution": "merged_same_concept",
    }
    for label in labels:
        session.run(f"MATCH (n) WHERE elementId(n)=$id SET n:`{label}`", id=keeper["id"]).consume()
    session.run("MATCH (n) WHERE elementId(n)=$id SET n += $patch", id=keeper["id"], patch=patch).consume()

    moved = 0
    deleted = 0
    for node in group["nodes"]:
        if node["id"] == keeper["id"]:
            continue
        moved += merge_relationships(session, node["id"], keeper["id"], group_ids)
        session.run("MATCH (n) WHERE elementId(n)=$id DETACH DELETE n", id=node["id"]).consume()
        deleted += 1
    return {"name": group["name"], "action": "merge", "keeper": keeper["id"], "deleted": deleted, "relationships_moved": moved}


def quarantine_jobs_company(session, group: dict[str, Any]) -> dict[str, Any]:
    companies = [node for node in group["nodes"] if node["primary_type"] == "Company"]
    changed = 0
    for node in companies:
        session.run(
            """
            MATCH (n) WHERE elementId(n)=$id
            SET n.quarantined = true,
                n.quarantine_reason = 'jobs_csv_pseudo_company_name_collision',
                n.type_conflict_resolved_by = $run_id,
                n.type_conflict_resolved_at = datetime(),
                n.type_conflict_resolution = 'quarantine_pseudo_company',
                n.legacy_type = coalesce(n.legacy_type, n.type),
                n.type = 'RejectedCompany'
            REMOVE n:Company
            SET n:Entity:RejectedEntity
            """,
            id=node["id"],
            run_id=RUN_ID,
        ).consume()
        changed += 1
    return {"name": group["name"], "action": "quarantine_company", "changed": changed}


def rename_positions(session, group: dict[str, Any]) -> dict[str, Any]:
    changed = 0
    for node in group["nodes"]:
        if node["primary_type"] != "Position":
            continue
        company = str(node["props"].get("company") or "").strip()
        entity_id = str(node["props"].get("entity_id") or node["id"]).replace(":", "_")
        suffix = company or entity_id[-10:]
        new_name = f"{group['name']}（岗位:{suffix}）"
        session.run(
            """
            MATCH (n) WHERE elementId(n)=$id
            SET n.original_name = coalesce(n.original_name, n.name),
                n.name = $new_name,
                n.canonical_name = coalesce(n.canonical_name, $old_name),
                n.type_conflict_resolved_by = $run_id,
                n.type_conflict_resolved_at = datetime(),
                n.type_conflict_resolution = 'renamed_position_disambiguation'
            """,
            id=node["id"],
            new_name=new_name,
            old_name=group["name"],
            run_id=RUN_ID,
        ).consume()
        changed += 1
    return {"name": group["name"], "action": "rename_positions", "changed": changed}


def rename_knowledge_points(session, group: dict[str, Any]) -> dict[str, Any]:
    changed = 0
    for node in group["nodes"]:
        if node["primary_type"] != "KnowledgePoint":
            continue
        source = str(node["props"].get("source_doc") or "知识点").replace(".txt", "")
        new_name = f"{group['name']}（知识点:{source}）"
        session.run(
            """
            MATCH (n) WHERE elementId(n)=$id
            SET n.original_name = coalesce(n.original_name, n.name),
                n.name = $new_name,
                n.canonical_name = coalesce(n.canonical_name, $old_name),
                n.type_conflict_resolved_by = $run_id,
                n.type_conflict_resolved_at = datetime(),
                n.type_conflict_resolution = 'renamed_knowledge_point_disambiguation'
            """,
            id=node["id"],
            new_name=new_name,
            old_name=group["name"],
            run_id=RUN_ID,
        ).consume()
        changed += 1
    return {"name": group["name"], "action": "rename_knowledge_point", "changed": changed}


def plan_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = []
    for group in groups:
        action, reason = classify_group(group)
        plan.append(
            {
                "name": group["name"],
                "types": group["types"],
                "action": action,
                "reason": reason,
                "nodes": [
                    {
                        "id": node["id"],
                        "labels": node["labels"],
                        "primary_type": node["primary_type"],
                        "degree": node["degree"],
                        "source_doc": node["props"].get("source_doc"),
                        "source_table": node["props"].get("source_table"),
                        "entity_id": node["props"].get("entity_id"),
                        "company": node["props"].get("company"),
                    }
                    for node in group["nodes"]
                ],
            }
        )
    return plan


def apply_plan(session, groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for group in groups:
        action, _ = classify_group(group)
        if action == "merge":
            results.append(merge_group(session, group))
        elif action == "quarantine_company":
            results.append(quarantine_jobs_company(session, group))
        elif action == "rename_positions":
            results.append(rename_positions(session, group))
        elif action == "rename_knowledge_point":
            results.append(rename_knowledge_points(session, group))
        else:
            results.append({"name": group["name"], "action": "review"})
    return results


def conflict_count(session) -> int:
    return session.run(
        """
        MATCH (n)
        WHERE NOT n:Document
          AND n.name IS NOT NULL
          AND coalesce(n.quarantined, false) = false
        WITH n.name AS name,
             collect(DISTINCT coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity')) AS types
        WHERE size(types) > 1
        RETURN count(*) AS c
        """
    ).single()["c"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    report_dir = REPORT_ROOT / RUN_ID
    driver = connect()
    try:
        with driver.session() as session:
            groups = fetch_conflict_groups(session)
            export_snapshot(groups, report_dir)
            plan = plan_groups(groups)
            write_json(report_dir / "type_conflict_plan.json", plan)
            results = []
            if args.confirm:
                results = apply_plan(session, groups)
            after_count = conflict_count(session)
            summary = {
                "run_id": RUN_ID,
                "dry_run": not args.confirm,
                "before_conflict_groups": len(groups),
                "planned_actions": dict(Counter(item["action"] for item in plan)),
                "results": results,
                "after_conflict_groups": after_count,
                "report_dir": str(report_dir),
            }
            write_json(report_dir / "summary.json", summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2, default=json_default))
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
