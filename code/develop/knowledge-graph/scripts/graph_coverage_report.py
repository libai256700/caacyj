#!/usr/bin/env python3
"""Measure graph coverage against business_ontology.yaml."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml
from neo4j import GraphDatabase


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ONTOLOGY = DEFAULT_PROJECT_ROOT / "docs" / "business_ontology.yaml"
DEFAULT_OUTPUT = DEFAULT_PROJECT_ROOT / "review_reports" / "graph_coverage_report.json"

DOMAIN_ALIASES = {
    "hr_policy": "company",
    "price": "course",
    "textbook": "question_bank",
}

DOMAIN_KEYWORDS = {
    "company": ("公司", "云技", "组织", "制度", "员工手册", "入职", "薪酬"),
    "course": ("课程", "培训", "执照", "班型", "价格", "学费", "教员", "垂起"),
    "student": ("学员", "学生", "训练进度", "考试记录"),
    "customer": ("客户", "客资", "咨询", "跟进", "意向"),
    "instructor": ("教员", "讲师", "教练"),
    "job_market": ("岗位", "招聘", "职位", "薪资", "日报"),
    "regulation": ("法规", "民航法", "CCAR", "92部", "条款", "空域", "规章"),
    "question_bank": ("题库", "试题", "答案", "知识点", "教材", "概论", "飞行原理"),
}

ENTITY_TYPE_TO_DOMAIN = {
    "Company": "company",
    "Organization": "company",
    "Policy": "company",
    "Course": "course",
    "Student": "student",
    "Customer": "customer",
    "Instructor": "instructor",
    "Person": "instructor",
    "Position": "job_market",
    "Regulation": "regulation",
    "QuestionBank": "question_bank",
    "KnowledgePoint": "question_bank",
    "Skill": "question_bank",
}

SOURCE_KEYS = (
    "source_doc",
    "_created_by",
    "created_by",
    "source",
    "source_table",
    "source_tables",
    "source_csv",
    "canonical_doc_name",
    "doc_name",
    "document_name",
    "filepath",
    "path",
)

CHUNK_KEYS = (
    "chunk_id",
    "source_chunk",
    "source_chunk_id",
    "source_chunk_ids",
    "evidence_chunk_id",
    "evidence_chunk_ids",
    "source_chunks",
)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(nonempty(item) for item in value)
    return str(value).strip() != ""


def clean_props(props: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in props.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
        elif isinstance(value, list):
            cleaned[key] = value[:20]
        else:
            cleaned[key] = str(value)
    return cleaned


def load_sqlite_chunks(db_path: Path) -> tuple[set[str], set[str]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT chunk_id, doc_name FROM chunks").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}, {row[1] for row in rows}


def candidate_source_docs(props: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("source_doc", "_created_by", "created_by", "canonical_doc_name", "doc_name", "document_name"):
        for item in as_list(props.get(key)):
            if nonempty(item):
                values.append(str(item).strip())
    return values


def source_resolves_to_doc(props: dict[str, Any], doc_names: set[str]) -> bool:
    for source in candidate_source_docs(props):
        if source in doc_names:
            return True
        if source.endswith(".txt") and source in doc_names:
            return True
        if not source.endswith(".txt") and f"{source}.txt" in doc_names:
            return True
        if any(source and (source in doc or doc in source) for doc in doc_names):
            return True
    return False


def chunk_values(props: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in CHUNK_KEYS:
        for item in as_list(props.get(key)):
            if nonempty(item):
                values.append(str(item).strip())
    return values


def has_source_evidence(props: dict[str, Any]) -> bool:
    return any(nonempty(props.get(key)) for key in SOURCE_KEYS)


def has_csv_source(props: dict[str, Any]) -> bool:
    return any(nonempty(props.get(key)) for key in ("source_table", "source_tables", "source_csv", "csv_file"))


def has_doc_source(props: dict[str, Any]) -> bool:
    return any(nonempty(props.get(key)) for key in ("source_doc", "_created_by", "created_by", "canonical_doc_name", "doc_name", "document_name"))


def primary_label(labels: list[str], props: dict[str, Any]) -> str:
    if props.get("type"):
        return str(props["type"])
    for label in labels:
        if label not in {"Entity"}:
            return label
    return labels[0] if labels else "Unknown"


def classify_domain(node: dict[str, Any], ontology_domains: set[str]) -> str:
    props = node["props"]
    explicit = props.get("domain")
    if explicit in ontology_domains:
        return str(explicit)
    if explicit in DOMAIN_ALIASES:
        return DOMAIN_ALIASES[str(explicit)]

    entity_type = primary_label(node["labels"], props)
    if entity_type in ENTITY_TYPE_TO_DOMAIN:
        return ENTITY_TYPE_TO_DOMAIN[entity_type]

    haystack = " ".join(
        str(value or "")
        for value in (
            props.get("name"),
            props.get("canonical_name"),
            props.get("source_doc"),
            props.get("_created_by"),
            props.get("doc_name"),
            props.get("description"),
        )
    )
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if domain in ontology_domains and any(keyword.lower() in haystack.lower() for keyword in keywords):
            return domain
    return "unmapped"


def fetch_nodes(session) -> list[dict[str, Any]]:
    rows = session.run(
        """
        MATCH (n)
        RETURN elementId(n) AS id,
               labels(n) AS labels,
               properties(n) AS props,
               count { (n)--() } AS degree
        ORDER BY coalesce(n.domain, ''), coalesce(n.name, '')
        """
    ).data()
    return [
        {
            "id": row["id"],
            "labels": list(row["labels"] or []),
            "props": dict(row["props"] or {}),
            "degree": int(row["degree"] or 0),
        }
        for row in rows
    ]


def relation_counts(session) -> list[dict[str, Any]]:
    return session.run(
        """
        MATCH ()-[r]->()
        RETURN type(r) AS type, count(r) AS edges
        ORDER BY edges DESC, type
        """
    ).data()


def relation_missing_evidence(session) -> list[dict[str, Any]]:
    return session.run(
        """
        MATCH (a)-[r]->(b)
        WITH a, r, b,
             any(k IN ['source_doc','evidence_doc','source','created_by','_created_by'] WHERE r[k] IS NOT NULL AND toString(r[k]) <> '') AS has_source_prop,
             any(k IN ['source_docs','created_by_docs'] WHERE r[k] IS NOT NULL AND size(r[k]) > 0) AS has_source_list,
             any(k IN ['chunk_id','source_chunk','source_chunk_id','evidence_chunk_id'] WHERE r[k] IS NOT NULL AND toString(r[k]) <> '') AS has_chunk_prop,
             any(k IN ['source_chunk_ids','evidence_chunk_ids','source_chunks'] WHERE r[k] IS NOT NULL AND size(r[k]) > 0) AS has_chunk_list
        WHERE NOT (has_source_prop OR has_source_list OR has_chunk_prop OR has_chunk_list)
        WITH type(r) AS type, count(r) AS missing_edges,
             collect({
               from: coalesce(a.name, a.canonical_name, elementId(a)),
               to: coalesce(b.name, b.canonical_name, elementId(b)),
               from_labels: labels(a),
               to_labels: labels(b)
             })[0..20] AS examples
        RETURN type, missing_edges, examples
        ORDER BY missing_edges DESC, type
        """
    ).data()


def available_labels(session) -> set[str]:
    rows = session.run("CALL db.labels() YIELD label RETURN label").data()
    return {row["label"] for row in rows}


def parse_path(path: str) -> tuple[list[str], list[str]]:
    parts = [part.strip() for part in path.split("->") if part.strip()]
    labels = parts[0::2]
    rels = parts[1::2]
    return labels, rels


def chunk_predicate(var_name: str) -> str:
    return (
        f"(any(k IN ['chunk_id','source_chunk','source_chunk_id','evidence_chunk_id'] "
        f"WHERE {var_name}[k] IS NOT NULL AND toString({var_name}[k]) <> '') OR "
        f"any(k IN ['source_chunk_ids','evidence_chunk_ids','source_chunks'] "
        f"WHERE {var_name}[k] IS NOT NULL AND size({var_name}[k]) > 0))"
    )


def path_exists(session, labels: list[str], rels: list[str], db_labels: set[str]) -> bool:
    if not labels or not rels:
        return False
    missing_labels = [label for label in labels if label != "ChunkRef" and label not in db_labels]
    if missing_labels:
        return False
    terminal_chunk = labels[-1] == "ChunkRef"
    usable_labels = labels[:-1] if terminal_chunk else labels
    usable_rels = rels[:-1] if terminal_chunk else rels
    if len(usable_labels) == 1:
        query = f"MATCH (n0:{usable_labels[0]}) WHERE {chunk_predicate('n0')} RETURN count(n0) > 0 AS ok"
        return bool(session.run(query).single()["ok"])
    pattern = [f"(n0:{usable_labels[0]})"]
    for index, rel in enumerate(usable_rels, start=1):
        pattern.append(f"-[:{rel}]-(n{index}:{usable_labels[index]})")
    where = ""
    if terminal_chunk:
        where = f" WHERE {chunk_predicate(f'n{len(usable_labels) - 1}')}"
    query = "MATCH " + "".join(pattern) + where + " RETURN count(*) > 0 AS ok"
    return bool(session.run(query).single()["ok"])


def longest_prefix(session, labels: list[str], rels: list[str], db_labels: set[str]) -> dict[str, Any]:
    for rel_count in range(len(rels), 0, -1):
        sub_labels = labels[: rel_count + 1]
        sub_rels = rels[:rel_count]
        try:
            if path_exists(session, sub_labels, sub_rels, db_labels):
                return {
                    "matched_hops": rel_count,
                    "matched_path": " -> ".join(
                        item for pair in zip(sub_labels, sub_rels + [""]) for item in pair if item
                    ),
                }
        except Exception as exc:
            return {"matched_hops": 0, "error": f"{type(exc).__name__}: {exc}"}
    return {"matched_hops": 0, "matched_path": ""}


def evaluate_core_questions(session, questions: list[dict[str, Any]], db_labels: set[str]) -> list[dict[str, Any]]:
    results = []
    for case in questions:
        path_results = []
        for expected in case.get("expected_paths") or []:
            labels, rels = parse_path(expected)
            item = {
                "expected_path": expected,
                "ok": False,
                "matched_hops": 0,
                "matched_path": "",
            }
            try:
                missing_labels = [label for label in labels if label != "ChunkRef" and label not in db_labels]
                if missing_labels:
                    item["missing_labels"] = missing_labels
                item["ok"] = path_exists(session, labels, rels, db_labels)
                if not item["ok"]:
                    item.update(longest_prefix(session, labels, rels, db_labels))
                else:
                    item["matched_hops"] = len(rels)
                    item["matched_path"] = expected
            except Exception as exc:
                item["error"] = f"{type(exc).__name__}: {exc}"
            path_results.append(item)
        results.append(
            {
                "id": case.get("id"),
                "question": case.get("question"),
                "expected_domains": case.get("expected_domains") or [],
                "ok": any(item.get("ok") for item in path_results),
                "paths": path_results,
            }
        )
    return results


def summarize_nodes(nodes: list[dict[str, Any]], ontology_domains: set[str], chunk_ids: set[str], doc_names: set[str]) -> dict[str, Any]:
    domain_stats: dict[str, dict[str, Any]] = {
        domain: {
            "entities": 0,
            "with_source_doc_or_csv": 0,
            "with_doc_source": 0,
            "with_csv_source": 0,
            "source_doc_resolves_to_sqlite": 0,
            "with_chunk_id": 0,
            "with_valid_chunk_id": 0,
            "isolated_entities": 0,
            "entity_types": {},
            "isolated_examples": [],
        }
        for domain in sorted(ontology_domains)
    }
    domain_stats["unmapped"] = {
        "entities": 0,
        "with_source_doc_or_csv": 0,
        "with_doc_source": 0,
        "with_csv_source": 0,
        "source_doc_resolves_to_sqlite": 0,
        "with_chunk_id": 0,
        "with_valid_chunk_id": 0,
        "isolated_entities": 0,
        "entity_types": {},
        "isolated_examples": [],
    }

    all_stats = {
        "graph_nodes": len(nodes),
        "entity_nodes_excluding_documents": 0,
        "with_source_doc_or_csv": 0,
        "with_doc_source": 0,
        "with_csv_source": 0,
        "source_doc_resolves_to_sqlite": 0,
        "with_chunk_id": 0,
        "with_valid_chunk_id": 0,
        "isolated_entities": 0,
    }

    for node in nodes:
        is_document = "Document" in node["labels"]
        if is_document:
            continue
        all_stats["entity_nodes_excluding_documents"] += 1
        props = node["props"]
        domain = classify_domain(node, ontology_domains)
        stats = domain_stats.setdefault(domain, defaultdict(int))
        stats["entities"] += 1

        entity_type = primary_label(node["labels"], props)
        stats["entity_types"][entity_type] = stats["entity_types"].get(entity_type, 0) + 1

        source_ok = has_source_evidence(props)
        doc_ok = has_doc_source(props)
        csv_ok = has_csv_source(props)
        doc_resolves = source_resolves_to_doc(props, doc_names)
        chunks = chunk_values(props)
        valid_chunks = [chunk for chunk in chunks if chunk in chunk_ids]
        isolated = int(node["degree"]) == 0

        for key, ok in (
            ("with_source_doc_or_csv", source_ok),
            ("with_doc_source", doc_ok),
            ("with_csv_source", csv_ok),
            ("source_doc_resolves_to_sqlite", doc_resolves),
            ("with_chunk_id", bool(chunks)),
            ("with_valid_chunk_id", bool(valid_chunks)),
            ("isolated_entities", isolated),
        ):
            if ok:
                stats[key] += 1
                all_stats[key] += 1

        if isolated and len(stats["isolated_examples"]) < 20:
            stats["isolated_examples"].append(
                {
                    "id": node["id"],
                    "name": props.get("name") or props.get("canonical_name"),
                    "labels": node["labels"],
                    "type": entity_type,
                    "source_doc": props.get("source_doc") or props.get("_created_by"),
                }
            )

    for stats in domain_stats.values():
        entities = max(int(stats["entities"]), 1)
        for key in (
            "with_source_doc_or_csv",
            "source_doc_resolves_to_sqlite",
            "with_valid_chunk_id",
            "isolated_entities",
        ):
            stats[f"{key}_rate"] = round(int(stats[key]) / entities, 4)
        stats["entity_types"] = dict(sorted(stats["entity_types"].items(), key=lambda item: (-item[1], item[0])))

    entity_total = max(int(all_stats["entity_nodes_excluding_documents"]), 1)
    for key in (
        "with_source_doc_or_csv",
        "source_doc_resolves_to_sqlite",
        "with_valid_chunk_id",
        "isolated_entities",
    ):
        all_stats[f"{key}_rate"] = round(int(all_stats[key]) / entity_total, 4)

    return {"summary": all_stats, "domains": domain_stats}


def load_ontology(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_report(args: argparse.Namespace) -> dict[str, Any]:
    ontology = load_ontology(Path(args.ontology))
    ontology_domains = set((ontology.get("domains") or {}).keys())
    project_root = Path(args.project_root).expanduser()
    chunk_ids, doc_names = load_sqlite_chunks(project_root / "rag_chunks.db")
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        password = (project_root / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, password), connection_timeout=5)
    try:
        with driver.session() as session:
            db_labels = available_labels(session)
            nodes = fetch_nodes(session)
            rel_counts = relation_counts(session)
            missing_rel_evidence = relation_missing_evidence(session)
            core_question_results = evaluate_core_questions(
                session,
                ontology.get("graph_first_candidate_questions") or [],
                db_labels,
            )
    finally:
        driver.close()

    rel_total = sum(int(row["edges"]) for row in rel_counts)
    missing_rel_total = sum(int(row["missing_edges"]) for row in missing_rel_evidence)
    node_report = summarize_nodes(nodes, ontology_domains, chunk_ids, doc_names)
    failed_questions = [item for item in core_question_results if not item["ok"]]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ontology": str(Path(args.ontology).resolve()),
        "project_root": str(project_root),
        "neo4j_uri": args.neo4j_uri,
        "sqlite_evidence_store": {
            "path": str(project_root / "rag_chunks.db"),
            "chunk_count": len(chunk_ids),
            "doc_count": len(doc_names),
        },
        "node_coverage": node_report,
        "relation_coverage": {
            "total_edges": rel_total,
            "relation_type_counts": rel_counts,
            "missing_evidence_edges": missing_rel_total,
            "missing_evidence_edge_rate": round(missing_rel_total / max(rel_total, 1), 4),
            "missing_evidence_by_type": missing_rel_evidence,
        },
        "core_business_path_coverage": {
            "total_questions": len(core_question_results),
            "passed_questions": len(core_question_results) - len(failed_questions),
            "failed_questions": len(failed_questions),
            "failed_question_ids": [item["id"] for item in failed_questions],
            "results": core_question_results,
        },
        "notes": [
            "Domain counts exclude Document nodes and classify legacy hr_policy as company, price as course, textbook as question_bank.",
            "with_valid_chunk_id requires a node chunk property to resolve to an existing SQLite chunk_id.",
            "source_doc_resolves_to_sqlite checks graph source_doc-like fields against SQLite doc_name values.",
            "Core path checks use the expected paths in business_ontology.yaml; ChunkRef is treated as a valid chunk reference on the terminal graph node.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology", default=str(DEFAULT_ONTOLOGY))
    parser.add_argument("--project-root", default=str(DEFAULT_PROJECT_ROOT))
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = make_report(args)
    output = Path(args.output).expanduser()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "domains": {
                    domain: data["entities"]
                    for domain, data in report["node_coverage"]["domains"].items()
                    if domain != "unmapped"
                },
                "relation_types": len(report["relation_coverage"]["relation_type_counts"]),
                "missing_evidence_edges": report["relation_coverage"]["missing_evidence_edges"],
                "isolated_entities": report["node_coverage"]["summary"]["isolated_entities"],
                "failed_core_questions": report["core_business_path_coverage"]["failed_question_ids"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
