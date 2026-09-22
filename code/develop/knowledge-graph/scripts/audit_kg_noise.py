#!/usr/bin/env python3
"""Read-only KG relationship noise audit.

The report highlights graph-density risks before changing recall weights or
deleting edges. It does not mutate Neo4j.
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

DEFAULT_REL_TYPES = ["REQUIRES", "PART_OF", "REGULATES", "REFERS_TO", "SUBCLASS_OF", "DEFINED_BY"]


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def connect_neo4j():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def collect(session, rel_types: list[str], sample_limit: int) -> dict[str, Any]:
    stats = dict(session.run(
        """
        MATCH (n)
        WITH count(n) AS nodes
        MATCH ()-[r]->()
        WITH nodes, count(r) AS rels
        RETURN nodes, rels,
               COUNT { MATCH (e:Entity) RETURN e } AS entities,
               COUNT { MATCH (d:Document) RETURN d } AS documents,
               COUNT { MATCH (c:Chunk) RETURN c } AS chunk_nodes
        """
    ).single())
    stats["rels_per_entity"] = round(stats["rels"] / max(stats["entities"], 1), 2)
    stats["rels_per_node"] = round(stats["rels"] / max(stats["nodes"], 1), 2)

    rel_distribution = session.run(
        """
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(r) AS count
        ORDER BY count DESC
        """
    ).data()

    high_degree_nodes = session.run(
        """
        MATCH (n)
        WHERE NOT n:Document
        WITH n, COUNT { (n)--() } AS degree
        RETURN n.name AS name,
               labels(n) AS labels,
               n.type AS type,
               n.source_doc AS source_doc,
               degree
        ORDER BY degree DESC
        LIMIT 50
        """
    ).data()

    self_loops = session.run(
        """
        MATCH (n)-[r]->(n)
        RETURN n.name AS name, labels(n) AS labels, type(r) AS rel_type, count(r) AS count
        ORDER BY count DESC, name
        LIMIT 50
        """
    ).data()

    duplicate_edges = session.run(
        """
        MATCH (a)-[r]->(b)
        WITH coalesce(a.name, elementId(a)) AS from_name,
             coalesce(b.name, elementId(b)) AS to_name,
             type(r) AS rel_type,
             count(r) AS count
        WHERE count > 1
        RETURN from_name, rel_type, to_name, count
        ORDER BY count DESC
        LIMIT 50
        """
    ).data()

    relation_samples = {}
    for rel_type in rel_types:
        relation_samples[rel_type] = session.run(
            f"""
            MATCH (a)-[r:{rel_type}]->(b)
            WITH a, b, COUNT {{ (a)--() }} AS a_degree, COUNT {{ (b)--() }} AS b_degree
            RETURN a.name AS from_name,
                   labels(a) AS from_labels,
                   a.type AS from_type,
                   a.source_doc AS from_source_doc,
                   b.name AS to_name,
                   labels(b) AS to_labels,
                   b.type AS to_type,
                   b.source_doc AS to_source_doc,
                   a_degree,
                   b_degree
            ORDER BY a_degree + b_degree DESC
            LIMIT $limit
            """,
            limit=sample_limit,
        ).data()

    document_contains = session.run(
        """
        MATCH (d:Document)-[:CONTAINS]->(e)
        RETURN d.name AS document, count(e) AS contains_count
        ORDER BY contains_count DESC
        LIMIT 50
        """
    ).data()

    recommendations = []
    if stats["rels_per_entity"] > 100:
        recommendations.append("关系密度很高；KG recall 应按关系类型加权并限制每个实体的一跳/二跳扩展数量。")
    if any(row["rel_type"] == "REQUIRES" and row["count"] > 50000 for row in rel_distribution):
        recommendations.append("REQUIRES 数量极大；抽样审计是否存在通用实体或课程/法规节点过连。")
    if self_loops:
        recommendations.append("存在 self-loop；建议逐条确认是否为抽取噪声。")
    if duplicate_edges:
        recommendations.append("存在重复同类型边；可做去重脚本，但先确认关系属性是否有业务差异。")
    recommendations.append("先把本报告纳入评测观察，不建议直接删边；下一步优先在 KG recall 层做 relation cap/weight。")

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stats": stats,
        "rel_distribution": rel_distribution,
        "high_degree_nodes": high_degree_nodes,
        "self_loops": self_loops,
        "duplicate_edges": duplicate_edges,
        "document_contains": document_contains,
        "relation_samples": relation_samples,
        "recommendations": recommendations,
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# KG Noise Audit",
        "",
        f"- Created: {report['created_at']}",
        f"- Nodes: {report['stats']['nodes']}",
        f"- Entities: {report['stats']['entities']}",
        f"- Relationships: {report['stats']['rels']}",
        f"- Relationships per entity: {report['stats']['rels_per_entity']}",
        f"- Chunk nodes: {report['stats']['chunk_nodes']}",
        "",
        "## Recommendations",
        *[f"- {item}" for item in report["recommendations"]],
        "",
        "## Top Relationship Types",
    ]
    for row in report["rel_distribution"][:20]:
        lines.append(f"- {row['rel_type']}: {row['count']}")

    lines.extend(["", "## High-Degree Nodes"])
    for row in report["high_degree_nodes"][:20]:
        lines.append(f"- {row.get('name')} | degree={row.get('degree')} | type={row.get('type')} | source={row.get('source_doc')}")

    lines.extend(["", "## Self-Loops"])
    if report["self_loops"]:
        for row in report["self_loops"][:20]:
            lines.append(f"- {row.get('name')} -[{row.get('rel_type')}]-> self | count={row.get('count')}")
    else:
        lines.append("- none")

    lines.extend(["", "## Duplicate Edges"])
    if report["duplicate_edges"]:
        for row in report["duplicate_edges"][:20]:
            lines.append(f"- {row.get('from_name')} -[{row.get('rel_type')}]-> {row.get('to_name')} | count={row.get('count')}")
    else:
        lines.append("- none")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rel-type", action="append", dest="rel_types", help="relationship type to sample")
    parser.add_argument("--sample-limit", type=int, default=25)
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()

    rel_types = args.rel_types or DEFAULT_REL_TYPES
    report_dir = args.report_dir or REPORT_ROOT / f"kg_noise_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    report_dir.mkdir(parents=True, exist_ok=True)

    driver = connect_neo4j()
    try:
        with driver.session() as session:
            report = collect(session, rel_types, args.sample_limit)
    finally:
        driver.close()

    write_json(report_dir / "kg_noise_audit.json", report)
    write_markdown(report_dir / "kg_noise_audit.md", report)

    print(f"report: {report_dir}")
    print(
        "summary: "
        f"rels={report['stats']['rels']}, "
        f"rels_per_entity={report['stats']['rels_per_entity']}, "
        f"self_loops={len(report['self_loops'])}, "
        f"duplicate_edge_groups={len(report['duplicate_edges'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
