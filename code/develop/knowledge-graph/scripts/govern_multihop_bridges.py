#!/usr/bin/env python3
"""Govern evidence-backed bridge paths for multi-hop business graph evals.

Dry-run by default. With --confirm this script:
- rewrites legacy node source_chunk_ids such as doc.txt_0 to canonical SQLite chunk_ids
- creates evidence-backed KnowledgePoint bridge nodes for business-linked Skill nodes
- links those Skill nodes to bridge KnowledgePoint nodes with MENTIONS relations

It never writes chunk text and only uses chunk_ids that already exist in rag_chunks.db.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_ROOT = BASE_DIR / "review_reports"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
RUN_ID = f"multihop_bridge_governance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
MAX_NODE_CHUNKS = 120
MAX_REL_CHUNKS = 20


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def clean(value: Any) -> str:
    return str(value or "").strip()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


class ChunkIndex:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT chunk_id, doc_name, chunk_index, text FROM chunks"
        ).fetchall()
        self.valid_ids = {row["chunk_id"] for row in rows}
        self.by_doc_index: dict[tuple[str, int], str] = {}
        self.doc_by_chunk: dict[str, str] = {}
        self.text_by_chunk: dict[str, str] = {}
        for row in rows:
            chunk_id = row["chunk_id"]
            doc_name = row["doc_name"] or ""
            self.doc_by_chunk[chunk_id] = doc_name
            self.text_by_chunk[chunk_id] = row["text"] or ""
            self.by_doc_index[(doc_name, int(row["chunk_index"]))] = chunk_id

    def close(self) -> None:
        self.conn.close()

    def translate(self, chunk_id: Any) -> str | None:
        value = clean(chunk_id)
        if not value:
            return None
        if value in self.valid_ids:
            return value
        match = re.match(r"^(.+)_(\d+)$", value)
        if not match:
            return None
        doc_name = match.group(1)
        index = int(match.group(2))
        candidates = [doc_name]
        if not doc_name.endswith(".txt"):
            candidates.append(f"{doc_name}.txt")
        for candidate in candidates:
            found = self.by_doc_index.get((candidate, index))
            if found:
                return found
        return None

    def translate_many(self, values: Any, limit: int | None = MAX_NODE_CHUNKS) -> list[str]:
        out: list[str] = []
        seen = set()
        for value in as_list(values):
            translated = self.translate(value)
            if translated and translated not in seen:
                out.append(translated)
                seen.add(translated)
            if limit is not None and len(out) >= limit:
                break
        return out

    def search(self, terms: list[str], limit: int = MAX_NODE_CHUNKS) -> list[str]:
        terms = [term for term in terms if len(term) >= 2]
        if not terms:
            return []
        clauses = []
        params: list[str] = []
        for term in terms[:6]:
            clauses.append("(doc_name LIKE ? OR text LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%"])
        rows = self.conn.execute(
            f"""
            SELECT chunk_id, doc_name, chunk_index, text
            FROM chunks
            WHERE {" OR ".join(clauses)}
            LIMIT 400
            """,
            params,
        ).fetchall()
        scored: list[tuple[int, str]] = []
        for row in rows:
            haystack = f"{row['doc_name']}\n{row['text'] or ''}"
            score = sum(1 for term in terms if term in haystack)
            doc_name = row["doc_name"] or ""
            if any(token in doc_name for token in ("理论题库", "无人机理论书籍", "政策法规")):
                score += 2
            elif "企业信息" in doc_name:
                score += 1
            scored.append((-score, row["chunk_id"]))
        scored.sort()
        out: list[str] = []
        seen = set()
        for _, chunk_id in scored:
            if chunk_id not in seen:
                out.append(chunk_id)
                seen.add(chunk_id)
            if len(out) >= limit:
                break
        return out


def skill_terms(name: str) -> list[str]:
    terms = [name]
    rules = [
        ("CAAC执照培训", ["CAAC", "执照", "考证", "视距内", "超视距"]),
        ("超视距", ["超视距", "地面站", "飞行计划", "执照"]),
        ("视距内", ["视距内", "执照", "飞行"]),
        ("教员", ["教员", "教学", "口试", "安全与应急教学能力"]),
        ("多旋翼", ["多旋翼", "旋翼", "飞行原理"]),
        ("垂直起降", ["垂直起降", "固定翼", "垂起"]),
        ("地面站", ["地面站", "任务规划", "预规划"]),
        ("飞行原理", ["飞行原理", "升力", "阻力"]),
        ("法规", ["法律法规", "CCAR", "训练机构", "运行安全"]),
        ("合规", ["法律法规", "合规", "CCAR"]),
        ("维修", ["维修", "装配", "持续适航"]),
        ("装调", ["维修", "装配", "动力系统", "飞控"]),
        ("市场", ["市场", "客户", "经营"]),
        ("销售", ["销售", "客户", "咨询"]),
        ("客户", ["客户", "跟进", "咨询"]),
        ("无人机综合", ["无人机", "飞行", "执照", "题库"]),
    ]
    for trigger, values in rules:
        if trigger in name:
            terms.extend(values)
    seen = set()
    return [term for term in terms if term and not (term in seen or seen.add(term))]


def domain_for_doc(doc_name: str) -> str:
    if "政策法规" in doc_name or "CCAR" in doc_name:
        return "regulation"
    if "理论题库" in doc_name:
        return "question_bank"
    if "无人机理论书籍" in doc_name or "教材" in doc_name:
        return "textbook"
    if "企业信息" in doc_name:
        return "course"
    if "人事制度" in doc_name:
        return "company"
    return "general"


def generic_skill_source(source_doc: str) -> bool:
    source_doc = clean(source_doc)
    return source_doc in {
        "",
        "question_banks.csv",
        "canonical_skill_rules",
        "canonical_knowledge_point_rules",
    }


def normalize_node_chunks(session, chunks: ChunkIndex, confirm: bool) -> dict[str, Any]:
    rows = session.run(
        """
        MATCH (n)
        WHERE n.source_chunk_ids IS NOT NULL AND size(n.source_chunk_ids) > 0
        RETURN elementId(n) AS id,
               coalesce(n.name, n.canonical_name, n.title, n.entity_id, elementId(n)) AS name,
               labels(n) AS labels,
               n.source_chunk_ids AS source_chunk_ids
        """
    ).data()
    updates: list[dict[str, Any]] = []
    for row in rows:
        original = [clean(item) for item in as_list(row.get("source_chunk_ids")) if clean(item)]
        translated = chunks.translate_many(original, limit=None)
        if not translated or translated == original:
            continue
        updates.append(
            {
                "id": row["id"],
                "name": row["name"],
                "labels": row["labels"],
                "old_count": len(original),
                "new_count": len(translated),
                "old_sample": original[:8],
                "new_sample": translated[:8],
            }
        )
        if confirm:
            session.run(
                """
                MATCH (n) WHERE elementId(n) = $id
                SET n.legacy_source_chunk_ids = coalesce(n.legacy_source_chunk_ids, n.source_chunk_ids),
                    n.source_chunk_ids = $source_chunk_ids,
                    n.source_chunk_ids_normalized_by = $run_id,
                    n.source_chunk_ids_normalized_at = datetime()
                """,
                id=row["id"],
                source_chunk_ids=translated,
                run_id=RUN_ID,
            ).consume()
    return {
        "scanned_nodes_with_chunks": len(rows),
        "planned_or_applied_node_chunk_updates": len(updates),
        "updates": updates,
        "by_primary_label": dict(Counter((item["labels"][-1] if item["labels"] else "unknown") for item in updates)),
    }


def fetch_business_skills(session) -> list[dict[str, Any]]:
    return session.run(
        """
        MATCH (entry)-[er]-(s:Skill)
        WHERE (entry:Course AND type(er) = 'REQUIRES')
           OR (entry:Student AND type(er) = 'REQUIRES')
           OR (entry:Position AND type(er) = 'REQUIRES_SKILL')
           OR (entry:Instructor AND type(er) = 'REQUIRES_SKILL')
        OPTIONAL MATCH (s)-[:MENTIONS]-(kp:KnowledgePoint)
        RETURN elementId(s) AS skill_id,
               coalesce(s.skill_name, s.canonical_name, s.name, s.entity_id) AS name,
               labels(s) AS labels,
               s.source_doc AS source_doc,
               s.source_chunk_ids AS source_chunk_ids,
               collect({
                 id: elementId(kp),
                 name: kp.name,
                 source_chunk_ids: kp.source_chunk_ids
               }) AS mentioned_kps,
               count(DISTINCT entry) AS entry_count
        ORDER BY entry_count DESC, name
        """
    ).data()


def has_valid_mentioned_kp(row: dict[str, Any], chunks: ChunkIndex) -> bool:
    for kp in row.get("mentioned_kps") or []:
        if not kp.get("id"):
            continue
        if chunks.translate_many(kp.get("source_chunk_ids"), limit=1):
            return True
    return False


def build_bridge_plan(session, chunks: ChunkIndex) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for row in fetch_business_skills(session):
        name = clean(row.get("name"))
        if not name or has_valid_mentioned_kp(row, chunks):
            continue
        source_chunks = chunks.translate_many(row.get("source_chunk_ids"), limit=MAX_NODE_CHUNKS)
        searched_chunks = chunks.search(skill_terms(name), limit=MAX_NODE_CHUNKS)
        if searched_chunks and (not source_chunks or generic_skill_source(row.get("source_doc") or "")):
            source_chunks = searched_chunks
        if not source_chunks:
            source_chunks = searched_chunks
        if not source_chunks:
            continue
        first_doc = chunks.doc_by_chunk.get(source_chunks[0], row.get("source_doc") or "rag_chunks.db")
        bridge_name = f"{name}（知识点证据）"
        bridge_id = stable_id("kp", bridge_name)
        rel_chunks = source_chunks[:MAX_REL_CHUNKS]
        plan.append(
            {
                "skill_id": row["skill_id"],
                "skill_name": name,
                "skill_labels": row.get("labels") or [],
                "entry_count": row.get("entry_count", 0),
                "bridge_entity_id": bridge_id,
                "bridge_name": bridge_name,
                "domain": domain_for_doc(first_doc),
                "source_doc": first_doc,
                "source_chunk_ids": source_chunks[:MAX_NODE_CHUNKS],
                "rel_source_chunk_ids": rel_chunks,
                "sync_key": stable_id("bridge_rel", row["skill_id"], bridge_id, "MENTIONS"),
            }
        )
    return plan


def apply_bridge_plan(session, plan: list[dict[str, Any]], confirm: bool) -> dict[str, int]:
    stats = {"planned": len(plan), "nodes_merged": 0, "relationships_merged": 0}
    if not confirm:
        return stats
    for item in plan:
        session.run(
            """
            MERGE (kp:Entity:KnowledgePoint {entity_id: $entity_id})
            ON CREATE SET kp._multihop_bridge_created_by = $run_id,
                          kp._multihop_bridge_created_at = datetime()
            SET kp.name = $name,
                kp.canonical_name = $name,
                kp.domain = $domain,
                kp.type = 'KnowledgePoint',
                kp.source_doc = $source_doc,
                kp.source_table = 'multihop_bridge_governance',
                kp.source_chunk_ids = $source_chunk_ids,
                kp.evidence_contract = 'source_doc_and_source_chunk_ids_to_sqlite',
                kp.bridge_for_skill = $skill_name,
                kp.sync_source = 'multihop_bridge_governance',
                kp.sync_run_id = $run_id,
                kp.schema_version = 'semantic-graph-v2',
                kp._multihop_bridge_last_run_id = $run_id,
                kp._multihop_bridge_updated_at = datetime()
            """,
            entity_id=item["bridge_entity_id"],
            name=item["bridge_name"],
            domain=item["domain"],
            source_doc=item["source_doc"],
            source_chunk_ids=item["source_chunk_ids"],
            skill_name=item["skill_name"],
            run_id=RUN_ID,
        ).consume()
        stats["nodes_merged"] += 1
        session.run(
            """
            MATCH (s) WHERE elementId(s) = $skill_id
            MATCH (kp:KnowledgePoint {entity_id: $bridge_entity_id})
            MERGE (s)-[r:MENTIONS {sync_key: $sync_key}]->(kp)
            ON CREATE SET r._multihop_bridge_created_by = $run_id,
                          r._multihop_bridge_created_at = datetime()
            SET r.source_doc = $source_doc,
                r.source_table = 'multihop_bridge_governance',
                r.source_chunk_ids = $source_chunk_ids,
                r.evidence_contract = 'source_doc_and_source_chunk_ids_to_sqlite',
                r.bridge_reason = 'business_entry_skill_to_evidence_backed_knowledge_point',
                r.sync_source = 'multihop_bridge_governance',
                r.sync_run_id = $run_id,
                r.schema_version = 'semantic-graph-v2',
                r._multihop_bridge_last_run_id = $run_id,
                r._multihop_bridge_updated_at = datetime()
            """,
            skill_id=item["skill_id"],
            bridge_entity_id=item["bridge_entity_id"],
            sync_key=item["sync_key"],
            source_doc=item["source_doc"],
            source_chunk_ids=item["rel_source_chunk_ids"],
            run_id=RUN_ID,
        ).consume()
        stats["relationships_merged"] += 1
    return stats


def backfill_bridge_audit(session, confirm: bool) -> dict[str, int]:
    count_query = """
    MATCH (:Skill)-[r:MENTIONS]->(kp:KnowledgePoint)
    WHERE kp.source_table = 'multihop_bridge_governance'
      AND r.source_table = 'multihop_bridge_governance'
      AND kp.name ENDS WITH '（知识点证据）'
      AND (
        kp.sync_source IS NULL OR kp.sync_run_id IS NULL OR
        r.sync_source IS NULL OR r.sync_run_id IS NULL
      )
    RETURN count(DISTINCT kp) AS nodes, count(r) AS relationships
    """
    row = session.run(count_query).single()
    stats = {
        "planned_node_updates": int(row["nodes"]),
        "planned_relationship_updates": int(row["relationships"]),
        "nodes_updated": 0,
        "relationships_updated": 0,
    }
    if not confirm or (not stats["planned_node_updates"] and not stats["planned_relationship_updates"]):
        return stats
    result = session.run(
        """
        MATCH (:Skill)-[r:MENTIONS]->(kp:KnowledgePoint)
        WHERE kp.source_table = 'multihop_bridge_governance'
          AND r.source_table = 'multihop_bridge_governance'
          AND kp.name ENDS WITH '（知识点证据）'
          AND (
            kp.sync_source IS NULL OR kp.sync_run_id IS NULL OR
            r.sync_source IS NULL OR r.sync_run_id IS NULL
          )
        SET kp.sync_source = 'multihop_bridge_governance',
            kp.sync_run_id = $run_id,
            r.sync_source = 'multihop_bridge_governance',
            r.sync_run_id = $run_id
        RETURN count(DISTINCT kp) AS nodes, count(r) AS relationships
        """,
        run_id=RUN_ID,
    ).single()
    stats["nodes_updated"] = int(result["nodes"])
    stats["relationships_updated"] = int(result["relationships"])
    return stats


def collect_counts(session) -> dict[str, int]:
    queries = {
        "course_requires_skill_mentions_kp": "MATCH (:Course)-[:REQUIRES]-(:Skill)-[:MENTIONS]-(:KnowledgePoint) RETURN count(*) AS c",
        "student_requires_skill_mentions_kp": "MATCH (:Student)-[:REQUIRES]-(:Skill)-[:MENTIONS]-(:KnowledgePoint) RETURN count(*) AS c",
        "position_requires_skill_mentions_kp": "MATCH (:Position)-[:REQUIRES_SKILL]-(:Skill)-[:MENTIONS]-(:KnowledgePoint) RETURN count(*) AS c",
        "instructor_requires_skill_mentions_kp": "MATCH (:Instructor)-[:REQUIRES_SKILL]-(:Skill)-[:MENTIONS]-(:KnowledgePoint) RETURN count(*) AS c",
    }
    return {name: int(session.run(query).single()["c"]) for name, query in queries.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    report_dir = REPORT_ROOT / RUN_ID
    chunk_index = ChunkIndex(BASE_DIR / "rag_chunks.db")
    driver = connect()
    try:
        with driver.session() as session:
            before_counts = collect_counts(session)
            node_result = normalize_node_chunks(session, chunk_index, args.confirm)
            bridge_plan = build_bridge_plan(session, chunk_index)
            bridge_result = apply_bridge_plan(session, bridge_plan, args.confirm)
            bridge_audit_backfill = backfill_bridge_audit(session, args.confirm)
            after_counts = collect_counts(session)
            append_jsonl(report_dir / "node_chunk_updates.jsonl", node_result["updates"])
            append_jsonl(report_dir / "bridge_plan.jsonl", bridge_plan)
            summary = {
                "run_id": RUN_ID,
                "dry_run": not args.confirm,
                "report_dir": str(report_dir),
                "before_counts": before_counts,
                "after_counts": after_counts,
                "node_chunk_normalization": {
                    key: value for key, value in node_result.items() if key != "updates"
                },
                "bridge_result": bridge_result,
                "bridge_audit_backfill": bridge_audit_backfill,
                "bridge_plan_by_domain": dict(Counter(item["domain"] for item in bridge_plan)),
            }
            write_json(report_dir / "summary.json", summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        driver.close()
        chunk_index.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
