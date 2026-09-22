#!/usr/bin/env python3
"""Evaluate multi-hop business reasoning paths in the live Neo4j graph."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = DEFAULT_PROJECT_ROOT / "eval" / "multihop_business_questions.jsonl"
DEFAULT_OUTPUT = DEFAULT_PROJECT_ROOT / "review_reports" / "multihop_business_eval_report.json"
DEFAULT_SUMMARY = DEFAULT_PROJECT_ROOT / "review_reports" / "multihop_business_eval_summary.md"
VALID_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CHUNK_KEYS = (
    "chunk_id",
    "source_chunk",
    "source_chunk_id",
    "source_chunk_ids",
    "evidence_chunk_id",
    "evidence_chunk_ids",
    "source_chunks",
)

REPAIR_LANES = [
    {
        "phase": 1,
        "name": "第一轮：先让核心经营问题从 0 变成可走通",
        "targets": ["Customer", "Student", "TrainingTrack", "Value"],
        "unlock_questions": [
            "某课程适合哪些客户？依据是什么？",
            "某学员下一步应该推荐什么课程？",
            "某客户如果想做低空业务，应该走什么培训路径？",
            "某价格是否和课程内容、客户类型匹配？",
        ],
    },
    {
        "phase": 2,
        "name": "第二轮：补齐教员、题库、岗位能力、法规和知识点推理",
        "targets": ["Instructor", "QuestionBank", "Position -> Skill", "Course -> Regulation", "Course -> KnowledgePoint"],
        "unlock_questions": [
            "某岗位面试应该考察哪些能力？",
            "某课程涉及哪些法规要求和题库知识点？",
            "某教员能否承担某类培训？",
        ],
    },
]

REPAIR_TARGET_ORDER = {
    target: index
    for index, target in enumerate(target for lane in REPAIR_LANES for target in lane["targets"])
}
REPAIR_TARGET_PHASE = {
    target: lane["phase"]
    for lane in REPAIR_LANES
    for target in lane["targets"]
}
REPAIR_TARGET_DESCRIPTIONS = {
    "Customer": "客户咨询、需求、客户类型到课程的 REFERS_TO 入口",
    "Student": "学员画像、训练进度、下一步推荐到 Skill/Course 的入口",
    "TrainingTrack": "班型、周期、容量、低空培训路径到 Course 的 HAS_CLASS 入口",
    "Value": "价格、周期、容量、内容等课程属性到证据的 HAS_PROPERTY 入口",
    "Instructor": "教员能力、可承担课程、带班关系入口",
    "QuestionBank": "题库与 KnowledgePoint 的 MENTIONS 入口",
    "Position -> Skill": "岗位职责或面试能力到 Skill 的 REQUIRES_SKILL 关系",
    "Course -> Regulation": "课程到法规依据的 REGULATES 关系",
    "Course -> KnowledgePoint": "课程经 Skill/QuestionBank 到 KnowledgePoint 的知识覆盖路径",
}


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_path(path: str) -> tuple[list[str], list[str]]:
    parts = [part.strip() for part in path.split("->") if part.strip()]
    labels = parts[0::2]
    rels = parts[1::2]
    for token in labels + rels:
        if token != "ChunkRef" and not VALID_TOKEN.match(token):
            raise ValueError(f"Unsafe path token: {token}")
    return labels, rels


def infer_repair_targets(expected_path: str) -> list[str]:
    labels, rels = parse_path(expected_path)
    label_set = set(labels)
    rel_set = set(rels)
    targets: list[str] = []
    for label in ("Customer", "Student", "TrainingTrack", "Value", "Instructor", "QuestionBank"):
        if label in label_set:
            targets.append(label)
    if {"Position", "Skill"}.issubset(label_set) and "REQUIRES_SKILL" in rel_set:
        targets.append("Position -> Skill")
    if {"Course", "Regulation"}.issubset(label_set) and "REGULATES" in rel_set:
        targets.append("Course -> Regulation")
    if {"Course", "KnowledgePoint"}.issubset(label_set):
        targets.append("Course -> KnowledgePoint")
    return sorted(set(targets), key=lambda target: REPAIR_TARGET_ORDER.get(target, 999))


def available_labels(session) -> set[str]:
    return {row["label"] for row in session.run("CALL db.labels() YIELD label RETURN label").data()}


def available_rel_types(session) -> set[str]:
    return {
        row["relationshipType"]
        for row in session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType").data()
    }


def chunk_predicate(var_name: str) -> str:
    return (
        f"(any(k IN ['chunk_id','source_chunk','source_chunk_id','evidence_chunk_id'] "
        f"WHERE {var_name}[k] IS NOT NULL AND toString({var_name}[k]) <> '') OR "
        f"any(k IN ['source_chunk_ids','evidence_chunk_ids','source_chunks'] "
        f"WHERE {var_name}[k] IS NOT NULL AND size({var_name}[k]) > 0))"
    )


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def chunk_values(props: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in CHUNK_KEYS:
        for item in as_list(props.get(key)):
            if item is not None and str(item).strip():
                values.append(str(item).strip())
    return values


class ChunkStore:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def fetch(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        ids = []
        seen = set()
        for chunk_id in chunk_ids:
            if chunk_id and chunk_id not in seen:
                ids.append(chunk_id)
                seen.add(chunk_id)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT chunk_id, doc_name, chunk_index, text
            FROM chunks
            WHERE chunk_id IN ({placeholders})
            ORDER BY doc_name, chunk_index
            """,
            ids,
        ).fetchall()
        return [
            {
                "chunk_id": row["chunk_id"],
                "doc_name": row["doc_name"],
                "chunk_index": row["chunk_index"],
                "excerpt": (row["text"] or "")[:260],
            }
            for row in rows
        ]


def build_pattern(labels: list[str], rels: list[str]) -> tuple[str, str, list[str], list[str]]:
    terminal_chunk = labels[-1] == "ChunkRef"
    usable_labels = labels[:-1] if terminal_chunk else labels
    usable_rels = rels[:-1] if terminal_chunk else rels
    if len(usable_labels) != len(usable_rels) + 1:
        raise ValueError(f"Invalid path shape labels={labels} rels={rels}")
    pattern = [f"(n0:{usable_labels[0]})"]
    for index, rel in enumerate(usable_rels, start=1):
        pattern.append(f"-[r{index - 1}:{rel}]-(n{index}:{usable_labels[index]})")
    terminal_var = f"n{len(usable_labels) - 1}"
    where = f"WHERE {chunk_predicate(terminal_var)}" if terminal_chunk else ""
    return "".join(pattern), where, usable_labels, usable_rels


def path_query(labels: list[str], rels: list[str]) -> str:
    pattern, where, usable_labels, usable_rels = build_pattern(labels, rels)
    node_vars = ", ".join(f"n{i}" for i in range(len(usable_labels)))
    rel_vars = ", ".join(f"r{i}" for i in range(len(usable_rels)))
    return f"""
    MATCH p={pattern}
    {where}
    RETURN
      [n IN [{node_vars}] | {{
        name: coalesce(n.name, n.canonical_name, n.title, n.id),
        labels: labels(n),
        type: n.type,
        domain: n.domain,
        source_doc: coalesce(n.source_doc, n._created_by, n.canonical_doc_name),
        props: properties(n)
      }}] AS node_list,
      [r IN [{rel_vars}] | {{
        type: type(r),
        source_doc: coalesce(r.source_doc, r.evidence_doc, r._created_by),
        props: properties(r)
      }}] AS rel_list
    LIMIT 3
    """


def node_payload(node: dict[str, Any]) -> dict[str, Any]:
    props = dict(node.get("props") or {})
    return {
        "name": node.get("name") or props.get("name") or props.get("canonical_name") or props.get("title") or props.get("id"),
        "labels": list(node.get("labels") or []),
        "type": node.get("type") or props.get("type") or next((label for label in node.get("labels", []) if label != "Entity"), None),
        "domain": node.get("domain") or props.get("domain"),
        "source_doc": node.get("source_doc") or props.get("source_doc") or props.get("_created_by") or props.get("canonical_doc_name"),
        "chunk_ids": chunk_values(props)[:8],
    }


def rel_payload(rel: dict[str, Any]) -> dict[str, Any]:
    props = dict(rel.get("props") or {})
    return {
        "type": rel.get("type"),
        "source_doc": rel.get("source_doc") or props.get("source_doc") or props.get("evidence_doc") or props.get("_created_by"),
        "chunk_ids": chunk_values(props)[:8],
    }


def sample_label_entities(session, label: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = session.run(
        f"""
        MATCH (n:{label})
        RETURN coalesce(n.name, n.canonical_name, n.title, n.id) AS name,
               labels(n) AS labels,
               n.domain AS domain,
               n.source_doc AS source_doc
        ORDER BY name
        LIMIT $limit
        """,
        limit=limit,
    ).data()
    return rows


def evaluate_path(
    session,
    store: ChunkStore,
    expected_path: str,
    db_labels: set[str],
    db_rels: set[str],
) -> dict[str, Any]:
    labels, rels = parse_path(expected_path)
    concrete_labels = [label for label in labels if label != "ChunkRef"]
    missing_labels = [label for label in concrete_labels if label not in db_labels]
    missing_rels = [rel for rel in rels if rel not in db_rels and not (labels[-1] == "ChunkRef" and rel == rels[-1])]
    result: dict[str, Any] = {
        "expected_path": expected_path,
        "path_labels": labels,
        "path_relations": rels,
        "repair_targets": infer_repair_targets(expected_path),
        "ok": False,
        "path_found": False,
        "has_final_sources": False,
        "used_entities": [],
        "relation_paths": [],
        "final_sources": [],
        "insufficient_step": None,
        "missing_labels": missing_labels,
        "missing_relation_types": missing_rels,
    }
    if missing_labels or missing_rels:
        result["insufficient_step"] = "missing_label_or_relation_type"
        return result

    rows = session.run(path_query(labels, rels)).data()
    if not rows:
        result["insufficient_step"] = "expected_relation_path_not_found"
        result["available_entry_entities"] = sample_label_entities(session, concrete_labels[0]) if concrete_labels else []
        return result

    result["path_found"] = True
    all_chunk_ids: list[str] = []
    for row in rows:
        nodes = [node_payload(node) for node in row["node_list"]]
        rel_payloads = [rel_payload(rel) for rel in row["rel_list"] if rel is not None]
        all_chunk_ids.extend(chunk_id for node in nodes for chunk_id in node["chunk_ids"])
        all_chunk_ids.extend(chunk_id for rel in rel_payloads for chunk_id in rel["chunk_ids"])
        result["relation_paths"].append(
            {
                "entities": nodes,
                "relations": rel_payloads,
            }
        )

    result["used_entities"] = result["relation_paths"][0]["entities"] if result["relation_paths"] else []
    result["final_sources"] = store.fetch(all_chunk_ids)[:8]
    result["has_final_sources"] = bool(result["final_sources"])
    result["ok"] = result["path_found"] and result["has_final_sources"]
    if not result["ok"]:
        result["insufficient_step"] = "path_found_but_no_sqlite_chunk_source"
    return result


def evaluate_case(session, store: ChunkStore, case: dict[str, Any], db_labels: set[str], db_rels: set[str]) -> dict[str, Any]:
    path_results = [
        evaluate_path(session, store, expected_path, db_labels, db_rels)
        for expected_path in case.get("expected_paths", [])
    ]
    passing = [item for item in path_results if item["ok"]]
    best = passing[0] if passing else next((item for item in path_results if item["path_found"]), None)
    if best is None and path_results:
        best = path_results[0]
    insufficient = []
    for item in path_results:
        if not item["ok"]:
            insufficient.append(
                {
                    "expected_path": item["expected_path"],
                    "step": item.get("insufficient_step"),
                    "missing_labels": item.get("missing_labels") or [],
                    "missing_relation_types": item.get("missing_relation_types") or [],
                }
            )
    return {
        "id": case["id"],
        "category": case.get("category"),
        "question": case["question"],
        "expected_domains": case.get("expected_domains", []),
        "ok": bool(passing),
        "path_results": path_results,
        "used_entities": (best or {}).get("used_entities", []),
        "relation_paths": (best or {}).get("relation_paths", []),
        "final_sources": (best or {}).get("final_sources", []),
        "insufficient_steps": insufficient,
    }


def build_repair_priority(results: list[dict[str, Any]]) -> dict[str, Any]:
    target_stats: dict[str, dict[str, Any]] = {}
    for lane in REPAIR_LANES:
        for target in lane["targets"]:
            target_stats[target] = {
                "target": target,
                "phase": lane["phase"],
                "description": REPAIR_TARGET_DESCRIPTIONS[target],
                "failed_questions": set(),
                "failed_paths": 0,
                "insufficient_steps": Counter(),
                "missing_labels": Counter(),
                "missing_relation_types": Counter(),
                "examples": [],
            }

    total_failed_paths = 0
    for item in results:
        for path_result in item.get("path_results", []):
            if path_result.get("ok"):
                continue
            total_failed_paths += 1
            step = path_result.get("insufficient_step") or "unknown"
            targets = path_result.get("repair_targets") or infer_repair_targets(path_result.get("expected_path", ""))
            for target in targets:
                if target not in target_stats:
                    continue
                stats = target_stats[target]
                stats["failed_questions"].add(item["id"])
                stats["failed_paths"] += 1
                stats["insufficient_steps"][step] += 1
                stats["missing_labels"].update(path_result.get("missing_labels") or [])
                stats["missing_relation_types"].update(path_result.get("missing_relation_types") or [])
                if len(stats["examples"]) < 5:
                    stats["examples"].append(
                        {
                            "id": item["id"],
                            "question": item["question"],
                            "expected_path": path_result.get("expected_path"),
                            "step": step,
                        }
                    )

    ordered_targets = []
    for target, stats in target_stats.items():
        ordered_targets.append(
            {
                "target": target,
                "phase": stats["phase"],
                "description": stats["description"],
                "failed_question_count": len(stats["failed_questions"]),
                "failed_questions": sorted(stats["failed_questions"]),
                "failed_paths": stats["failed_paths"],
                "insufficient_steps": dict(stats["insufficient_steps"].most_common()),
                "missing_labels": dict(stats["missing_labels"].most_common()),
                "missing_relation_types": dict(stats["missing_relation_types"].most_common()),
                "examples": stats["examples"],
            }
        )
    ordered_targets.sort(
        key=lambda item: (
            item["phase"],
            -item["failed_question_count"],
            -item["failed_paths"],
            REPAIR_TARGET_ORDER.get(item["target"], 999),
        )
    )

    lanes = []
    for lane in REPAIR_LANES:
        lane_targets = [item for item in ordered_targets if item["phase"] == lane["phase"]]
        lanes.append(
            {
                "phase": lane["phase"],
                "name": lane["name"],
                "unlock_questions": lane["unlock_questions"],
                "targets": lane_targets,
                "active_blockers": [item for item in lane_targets if item["failed_paths"] > 0],
            }
        )

    return {
        "basis": "failed expected paths; a case can pass through one path while another path still contributes a repair signal",
        "total_failed_paths": total_failed_paths,
        "lanes": lanes,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    missing_labels = Counter()
    missing_rels = Counter()
    insufficient_steps = Counter()
    categories = Counter()
    for item in results:
        categories[item["category"]] += 1
        for step in item["insufficient_steps"]:
            insufficient_steps[step.get("step") or "unknown"] += 1
            missing_labels.update(step.get("missing_labels") or [])
            missing_rels.update(step.get("missing_relation_types") or [])
    repair_priority = build_repair_priority(results)
    return {
        "total": len(results),
        "passed": sum(1 for item in results if item["ok"]),
        "failed": sum(1 for item in results if not item["ok"]),
        "missing_labels": dict(missing_labels.most_common()),
        "missing_relation_types": dict(missing_rels.most_common()),
        "insufficient_steps": dict(insufficient_steps.most_common()),
        "categories": dict(categories),
        "repair_priority": repair_priority,
    }


def write_summary(path: Path, report: dict[str, Any]) -> None:
    repair_priority = report["summary"].get("repair_priority") or {}
    lines = [
        "# 多跳业务图谱 Eval 摘要",
        "",
        f"生成时间：{report['generated_at']}",
        "",
        "## 总览",
        "",
        f"- 评测问题：{report['summary']['total']}",
        f"- 通过：{report['summary']['passed']}",
        f"- 未通过：{report['summary']['failed']}",
        f"- 缺失标签：{json.dumps(report['summary']['missing_labels'], ensure_ascii=False)}",
        f"- 缺失关系类型：{json.dumps(report['summary']['missing_relation_types'], ensure_ascii=False)}",
        f"- 断点类型：{json.dumps(report['summary']['insufficient_steps'], ensure_ascii=False)}",
        "",
        "## Eval 反推补图顺序",
        "",
        f"- 统计口径：{repair_priority.get('basis', '')}",
        f"- 未通过路径：{repair_priority.get('total_failed_paths', 0)}",
        "",
    ]
    for lane in repair_priority.get("lanes", []):
        lines.extend(
            [
                f"### Phase {lane['phase']}：{lane['name']}",
                "",
                "解锁问题：",
            ]
        )
        for question in lane.get("unlock_questions", []):
            lines.append(f"- {question}")
        lines.extend(
            [
                "",
                "| 补图目标 | 失败问题数 | 失败路径数 | 当前断点 | 说明 |",
                "| --- | ---: | ---: | --- | --- |",
            ]
        )
        for target in lane.get("targets", []):
            steps = json.dumps(target["insufficient_steps"], ensure_ascii=False)
            lines.append(
                f"| `{target['target']}` | {target['failed_question_count']} | {target['failed_paths']} | {steps} | {target['description']} |"
            )
        if not lane.get("active_blockers"):
            lines.append("")
            lines.append("当前 eval 没有在这一轮目标上发现未通过路径。")
        lines.append("")
    lines.extend(
        [
        "## 逐题结果",
        "",
        ]
    )
    for item in report["results"]:
        status = "通过" if item["ok"] else "未通过"
        lines.extend(
            [
                f"### {item['id']} {status}",
                "",
                f"问题：{item['question']}",
                "",
                f"- 用到实体：{json.dumps(item['used_entities'][:6], ensure_ascii=False)}",
                f"- 最终来源：{json.dumps(item['final_sources'][:3], ensure_ascii=False)}",
                f"- 证据不足：{json.dumps(item['insufficient_steps'], ensure_ascii=False)}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--project-root", default=str(DEFAULT_PROJECT_ROOT))
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).expanduser()
    password = os.environ.get("NEO4J_PASSWORD") or (project_root / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
    cases = load_cases(Path(args.fixture))
    store = ChunkStore(project_root / "rag_chunks.db")
    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, password), connection_timeout=5)
    try:
        with driver.session() as session:
            db_labels = available_labels(session)
            db_rels = available_rel_types(session)
            results = [evaluate_case(session, store, case, db_labels, db_rels) for case in cases]
    finally:
        driver.close()
        store.close()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fixture": str(Path(args.fixture).resolve()),
        "project_root": str(project_root),
        "neo4j_uri": args.neo4j_uri,
        "summary": summarize(results),
        "results": results,
        "required_output_contract": ["used_entities", "relation_paths", "final_sources", "insufficient_steps"],
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(Path(args.summary), report)
    print(json.dumps({"output": str(output), "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
