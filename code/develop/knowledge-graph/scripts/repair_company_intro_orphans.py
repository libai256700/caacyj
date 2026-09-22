#!/usr/bin/env python3
"""Repair company-introduction orphan concept nodes.

Dry-run by default. With --confirm this script:
- attaches 9 source-less company introduction concept nodes to Document("公司介绍")
- sets source_doc/_created_by/chunk_id to the canonical SQLite chunk
- adds conservative business relations supported by the source chunk

It does not delete or merge nodes.
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
RUN_ID = f"company_intro_orphans_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

DOC_NAME = "公司介绍"
CHUNK_ID = "企业信息_公司介绍.txt_0"
TARGET_TERMS = [
    "人才培养闭环",
    "实训教学",
    "岗位标准",
    "新质生产力",
    "考核认证",
    "能力诊断",
    "行业知识",
    "课程建设",
    "过程评价",
]

RELATIONS = [
    # Broad category from: "聚焦人工智能与职业教育培训深度融合" and
    # "公司围绕职业教育培训中的..."
    *[
        {"from": name, "type": "BELONGS_TO", "to": "职业教育培训", "evidence": "公司围绕职业教育培训中的关键环节"}
        for name in TARGET_TERMS
    ],
    # Key links from: "打造面向职业能力提升的智能培训解决方案" and
    # "公司围绕职业教育培训中的课程建设、实训教学、过程评价、能力诊断、...、考核认证与人才培养闭环等关键环节"
    *[
        {"from": name, "type": "PART_OF", "to": "智能培训解决方案", "evidence": "职业教育培训关键环节构成智能培训解决方案"}
        for name in ["课程建设", "实训教学", "过程评价", "能力诊断", "考核认证", "人才培养闭环"]
    ],
    # From: "大模型驱动+智能体协同+行业知识融合" and
    # "通过将行业知识、岗位标准与真实训练场景深度融合..."
    {"from": "行业知识", "type": "PART_OF", "to": "AI智学体系", "evidence": "大模型驱动+智能体协同+行业知识融合"},
    {"from": "岗位标准", "type": "PART_OF", "to": "AI智学体系", "evidence": "将行业知识、岗位标准与真实训练场景深度融合"},
    # From: "面向国家新质生产力发展与高技能人才培养需求"
    {"from": "新质生产力", "type": "AFFECTS", "to": "职业教育培训", "evidence": "面向国家新质生产力发展与高技能人才培养需求"},
]


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def connect_neo4j():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def get_chunk_text() -> str:
    with sqlite3.connect(SQLITE_DB) as conn:
        row = conn.execute("SELECT text FROM chunks WHERE chunk_id = ?", (CHUNK_ID,)).fetchone()
    if not row:
        raise RuntimeError(f"canonical chunk not found: {CHUNK_ID}")
    return row[0]


def health_counts(session) -> dict[str, int]:
    return {
        "orphan_entities": session.run(
            "MATCH (e:Entity) WHERE NOT (:Document)-[:CONTAINS]->(e) RETURN count(e) AS c"
        ).single()["c"],
        "source_doc_unresolved": session.run(
            """
            MATCH (e:Entity)
            WHERE (e.source_doc IS NULL OR trim(toString(e.source_doc)) = '')
              AND (e.chunk_id IS NULL OR trim(toString(e.chunk_id)) = '')
            RETURN count(e) AS c
            """
        ).single()["c"],
        "cross_pollution": session.run(
            """
            MATCH (d:Document)-[:CONTAINS]->(e:Entity)
            WHERE e._created_by IS NOT NULL AND e._created_by <> d.name
            RETURN count(*) AS c
            """
        ).single()["c"],
    }


def build_plan(session, chunk_text: str) -> dict[str, Any]:
    targets = session.run(
        """
        UNWIND $names AS name
        OPTIONAL MATCH (e:Entity {name: name})
        RETURN name,
               elementId(e) AS id,
               labels(e) AS labels,
               e.type AS type,
               e.source_doc AS source_doc,
               e._created_by AS created_by,
               e.chunk_id AS chunk_id,
               COUNT { (e)--() } AS degree,
               COUNT { (:Document)-[:CONTAINS]->(e) } AS contains_count
        ORDER BY name
        """,
        names=TARGET_TERMS,
    ).data()
    anchors = session.run(
        """
        UNWIND $names AS name
        OPTIONAL MATCH (e:Entity {name: name})
        RETURN name, elementId(e) AS id, labels(e) AS labels, e.type AS type
        ORDER BY name
        """,
        names=sorted({item["to"] for item in RELATIONS}),
    ).data()

    missing_targets = [row["name"] for row in targets if not row["id"]]
    missing_anchors = [row["name"] for row in anchors if not row["id"]]
    missing_terms = [term for term in TARGET_TERMS if term not in chunk_text]

    rel_existing = session.run(
        """
        UNWIND $relations AS rel
        MATCH (from:Entity {name: rel.from})
        MATCH (to:Entity {name: rel.to})
        RETURN rel.from AS from, rel.type AS type, rel.to AS to,
               COUNT { (from)-[r]->(to) WHERE type(r) = rel.type } AS existing
        ORDER BY from, type, to
        """,
        relations=RELATIONS,
    ).data()

    return {
        "run_id": RUN_ID,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "doc_name": DOC_NAME,
        "chunk_id": CHUNK_ID,
        "health_before": health_counts(session),
        "targets": targets,
        "anchors": anchors,
        "relations": RELATIONS,
        "relation_existing": rel_existing,
        "checks": {
            "missing_targets": missing_targets,
            "missing_anchors": missing_anchors,
            "terms_missing_from_chunk": missing_terms,
        },
        "planned": {
            "target_count": len(TARGET_TERMS),
            "contains_links": len([row for row in targets if row["id"] and row["contains_count"] == 0]),
            "relations_total": len(RELATIONS),
            "relations_new": len([row for row in rel_existing if row["existing"] == 0]),
        },
    }


def assert_plan_safe(plan: dict[str, Any]) -> None:
    checks = plan["checks"]
    problems = []
    if checks["missing_targets"]:
        problems.append(f"missing target nodes: {checks['missing_targets']}")
    if checks["missing_anchors"]:
        problems.append(f"missing anchor nodes: {checks['missing_anchors']}")
    if checks["terms_missing_from_chunk"]:
        problems.append(f"terms missing from chunk: {checks['terms_missing_from_chunk']}")
    if problems:
        raise RuntimeError("; ".join(problems))


def apply_repair(session) -> dict[str, int]:
    source_result = session.run(
        """
        MATCH (d:Document {name: $doc_name})
        WITH d
        UNWIND $names AS name
        MATCH (e:Entity {name: name})
        SET e.source_doc = $doc_name,
            e._created_by = $doc_name,
            e.chunk_id = $chunk_id,
            e.provenance_repaired_by = $run_id,
            e.provenance_repaired_at = datetime()
        MERGE (d)-[r:CONTAINS]->(e)
        ON CREATE SET r.created_by = $run_id, r.created_at = datetime()
        ON MATCH SET r.checked_by = $run_id, r.checked_at = datetime()
        RETURN count(e) AS nodes, count(r) AS contains_links
        """,
        doc_name=DOC_NAME,
        chunk_id=CHUNK_ID,
        names=TARGET_TERMS,
        run_id=RUN_ID,
    ).single()

    rel_count = 0
    for rel in RELATIONS:
        row = session.run(
            f"""
            MATCH (from:Entity {{name: $from_name}})
            MATCH (to:Entity {{name: $to_name}})
            MERGE (from)-[r:{rel['type']}]->(to)
            ON CREATE SET r.created_by = $run_id,
                          r.created_at = datetime(),
                          r.evidence_chunk_id = $chunk_id,
                          r.evidence_doc = $doc_name,
                          r.evidence = $evidence
            ON MATCH SET r.checked_by = $run_id,
                         r.checked_at = datetime(),
                         r.evidence_chunk_id = coalesce(r.evidence_chunk_id, $chunk_id),
                         r.evidence_doc = coalesce(r.evidence_doc, $doc_name),
                         r.evidence = coalesce(r.evidence, $evidence)
            RETURN count(r) AS c
            """,
            from_name=rel["from"],
            to_name=rel["to"],
            run_id=RUN_ID,
            chunk_id=CHUNK_ID,
            doc_name=DOC_NAME,
            evidence=rel["evidence"],
        ).single()["c"]
        rel_count += row

    return {
        "source_nodes": source_result["nodes"],
        "contains_links": source_result["contains_links"],
        "business_relations": rel_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="apply the planned repair")
    parser.add_argument("--report-dir", type=Path, help="override report directory")
    args = parser.parse_args()

    report_dir = args.report_dir or (REPORT_ROOT / RUN_ID)
    report_dir.mkdir(parents=True, exist_ok=True)

    chunk_text = get_chunk_text()
    driver = connect_neo4j()
    try:
        with driver.session() as session:
            plan = build_plan(session, chunk_text)
            write_json(report_dir / "plan.json", plan)
            print(
                "plan: "
                f"targets={plan['planned']['target_count']}, "
                f"contains_links={plan['planned']['contains_links']}, "
                f"relations_total={plan['planned']['relations_total']}, "
                f"relations_new={plan['planned']['relations_new']}"
            )
            print(f"report: {report_dir}")
            assert_plan_safe(plan)

            if not args.confirm:
                print("dry-run only; rerun with --confirm to apply")
                return 0

            applied = apply_repair(session)
            after = {
                "run_id": RUN_ID,
                "applied_at": datetime.now().isoformat(timespec="seconds"),
                "applied": applied,
                "health_after": health_counts(session),
            }
            write_json(report_dir / "after.json", after)
            print(
                "applied: "
                f"source_nodes={applied['source_nodes']}, "
                f"contains_links={applied['contains_links']}, "
                f"business_relations={applied['business_relations']}"
            )
            print(
                "after: "
                f"orphans={after['health_after']['orphan_entities']}, "
                f"source_doc_unresolved={after['health_after']['source_doc_unresolved']}, "
                f"cross_pollution={after['health_after']['cross_pollution']}"
            )
            return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
