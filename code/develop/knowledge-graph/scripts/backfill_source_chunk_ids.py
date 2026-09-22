#!/usr/bin/env python3
"""Backfill Neo4j source_chunk_ids from resolved SQLite source documents.

This is a bounded evidence repair: SQLite remains the canonical chunk text
store, and Neo4j only receives chunk ids that can be tied to local chunks.
Dry-run by default; pass --confirm to write.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Query

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from rag_store.semantic_schema import SCHEMA_VERSION, SYNC_ELIGIBLE_DOMAINS, domain_for_doc_name

RAG_DB = BASE_DIR / "rag_chunks.db"
ALIAS_PATH = BASE_DIR / "rag_store" / "source_doc_aliases.json"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
TYPE_EXPR = "coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity')"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_doc_name(value: str) -> str:
    name = (value or "").strip()
    for suffix in (".txt", ".md"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    for prefix in ("企业信息_", "人事制度_", "理论题库_", "政策法规_", "无人机理论书籍_"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    return name


def load_doc_resolver() -> dict[str, str]:
    with sqlite3.connect(RAG_DB) as conn:
        docs = [row[0] for row in conn.execute("SELECT doc_name FROM documents ORDER BY doc_name")]
    doc_names = set(docs)
    resolver: dict[str, str] = {}
    for doc_name in docs:
        candidates = {doc_name, normalize_doc_name(doc_name)}
        if doc_name.endswith((".txt", ".md")):
            candidates.add(doc_name.rsplit(".", 1)[0])
        for candidate in candidates:
            if candidate:
                resolver.setdefault(candidate, doc_name)

    aliases = read_json(ALIAS_PATH).get("aliases", {})
    if isinstance(aliases, dict):
        for alias, targets in aliases.items():
            if isinstance(targets, str):
                targets = [targets]
            target = next((item for item in targets if item in doc_names), None)
            if target:
                resolver[str(alias)] = target
                resolver.setdefault(normalize_doc_name(str(alias)), target)
    return resolver


def load_chunks_by_doc() -> dict[str, list[dict[str, Any]]]:
    with sqlite3.connect(RAG_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT chunk_id, doc_name, chunk_index, text
            FROM chunks
            ORDER BY doc_name, chunk_index
            """
        ).fetchall()
    chunks: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        chunks[item["doc_name"]].append(item)
    return dict(chunks)


def compact_text(value: str) -> str:
    return re.sub(r"[\s　,，.。:：;；、()（）《》<>【】\\[\\]\"'“”‘’_-]+", "", (value or "").lower())


def split_terms(*values: str) -> list[str]:
    terms: list[str] = []

    def add(value: str) -> None:
        value = (value or "").strip()
        if len(value) >= 2 and value not in terms:
            terms.append(value)

    for value in values:
        raw = (value or "").strip()
        add(raw)
        add(normalize_doc_name(raw))
        for part in re.split(r"[/／|,，、;；:：()（）《》<>【】\\[\\]\\s]+", raw):
            add(part)
        for article in re.findall(r"第[一二三四五六七八九十百千万零〇两\\d]+条(?:之[一二三四五六七八九十百千万零〇两\\d]+)?", raw):
            add(article)
        for code in re.findall(r"[A-Za-z]{2,}-?\\d+(?:部|章|条)?", raw):
            add(code)
    return terms[:24]


def score_chunk(chunk: dict[str, Any], terms: list[str]) -> int:
    text = chunk.get("text") or ""
    doc_name = chunk.get("doc_name") or ""
    compact = compact_text(text)
    score = 0
    for term in terms:
        if term in text:
            score += 12 + min(len(term), 12)
        term_compact = compact_text(term)
        if len(term_compact) >= 2 and term_compact in compact:
            score += 8 + min(len(term_compact), 10)
        if term in doc_name or term_compact in compact_text(doc_name):
            score += 4
        if len(term_compact) >= 4:
            chars = [ch for ch in term_compact if "\\u4e00" <= ch <= "\\u9fff"]
            if chars:
                hit_rate = sum(1 for ch in set(chars) if ch in compact) / len(set(chars))
                if hit_rate >= 0.85:
                    score += 6
    return score


def choose_chunks(node: dict[str, Any], chunks_by_doc: dict[str, list[dict[str, Any]]], resolver: dict[str, str]) -> tuple[list[str], str]:
    source_doc = (node.get("source_doc") or node.get("created_by") or "").strip()
    canonical_doc = resolver.get(source_doc) or resolver.get(normalize_doc_name(source_doc))
    if not canonical_doc:
        return [], "unresolved_source_doc"

    chunks = chunks_by_doc.get(canonical_doc, [])
    terms = split_terms(
        node.get("name") or "",
        node.get("canonical_name") or "",
        node.get("description") or "",
        source_doc,
    )
    scored = [
        (score_chunk(chunk, terms), int(chunk.get("chunk_index") or 0), chunk["chunk_id"])
        for chunk in chunks
    ]
    strong = [(score, index, chunk_id) for score, index, chunk_id in scored if score >= 14]
    if strong:
        selected = [chunk_id for score, index, chunk_id in sorted(strong, key=lambda item: (-item[0], item[1]))[:5]]
        return selected, "term_match"

    source_terms = split_terms(source_doc)
    source_scored = [
        (score_chunk(chunk, source_terms), int(chunk.get("chunk_index") or 0), chunk["chunk_id"])
        for chunk in chunks
    ]
    source_strong = [(score, index, chunk_id) for score, index, chunk_id in source_scored if score >= 12]
    if source_strong:
        selected = [chunk_id for score, index, chunk_id in sorted(source_strong, key=lambda item: (-item[0], item[1]))[:3]]
        return selected, "source_doc_match"

    return [], "no_text_match"


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS), connection_timeout=2)


def run(session: Any, statement: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in session.run(Query(statement, timeout=5), **params)]


def domain_stats(session: Any, domains: list[str]) -> dict[str, dict[str, Any]]:
    rows = run(
        session,
        """
        MATCH (n)
        WHERE NOT n:Document AND n.domain IN $domains
        RETURN n.domain AS domain,
               count(n) AS total,
               count(n.source_chunk_ids) AS with_source_chunk_ids,
               count(n.source_doc) AS with_source_doc,
               count(CASE WHEN n.schema_version = $schema_version THEN 1 END) AS with_schema_version
        ORDER BY domain
        """,
        domains=domains,
        schema_version=SCHEMA_VERSION,
    )
    return {
        row["domain"]: {
            "total": int(row["total"]),
            "with_source_chunk_ids": int(row["with_source_chunk_ids"]),
            "with_source_doc": int(row["with_source_doc"]),
            "with_schema_version": int(row["with_schema_version"]),
            "source_chunk_id_coverage_rate": round(int(row["with_source_chunk_ids"]) / max(int(row["total"]), 1), 4),
        }
        for row in rows
    }


def collect_candidates(session: Any, domains: list[str], limit: int) -> list[dict[str, Any]]:
    return run(
        session,
        f"""
        MATCH (n)
        WHERE NOT n:Document
          AND n.domain IN $domains
          AND (n.source_chunk_ids IS NULL OR size(n.source_chunk_ids) = 0)
          AND n.source_doc IS NOT NULL
        RETURN elementId(n) AS id,
               coalesce(n.name, "") AS name,
               {TYPE_EXPR} AS type,
               n.domain AS domain,
               n.canonical_name AS canonical_name,
               n.description AS description,
               n.source_doc AS source_doc,
               n._created_by AS created_by
        ORDER BY n.domain, n.source_doc, n.name
        LIMIT $limit
        """,
        domains=domains,
        limit=limit,
    )


def build_plan(session: Any, domains: list[str], limit: int) -> dict[str, Any]:
    resolver = load_doc_resolver()
    chunks_by_doc = load_chunks_by_doc()
    before = domain_stats(session, domains)
    candidates = collect_candidates(session, domains, limit)
    items = []
    by_reason: defaultdict[str, int] = defaultdict(int)
    by_domain_bound: defaultdict[str, int] = defaultdict(int)

    for node in candidates:
        chunk_ids, reason = choose_chunks(node, chunks_by_doc, resolver)
        by_reason[reason] += 1
        if chunk_ids:
            by_domain_bound[node["domain"]] += 1
            items.append(
                {
                    "id": node["id"],
                    "name": node["name"],
                    "type": node["type"],
                    "domain": node["domain"],
                    "source_doc": node["source_doc"],
                    "source_chunk_ids": chunk_ids,
                    "match_reason": reason,
                }
            )

    projected = json.loads(json.dumps(before, ensure_ascii=False))
    for domain, add_count in by_domain_bound.items():
        if domain in projected:
            projected[domain]["with_source_chunk_ids"] += add_count
            projected[domain]["source_chunk_id_coverage_rate"] = round(
                projected[domain]["with_source_chunk_ids"] / max(projected[domain]["total"], 1),
                4,
            )

    return {
        "created_at": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "domains": domains,
        "before": before,
        "candidate_count": len(candidates),
        "bindable_count": len(items),
        "match_reasons": dict(sorted(by_reason.items())),
        "projected_after": projected,
        "items": items,
    }


def apply_plan(session: Any, plan: dict[str, Any]) -> int:
    count = 0
    for item in plan["items"]:
        result = session.run(
            Query(
                """
                MATCH (n)
                WHERE elementId(n) = $id
                  AND (n.source_chunk_ids IS NULL OR size(n.source_chunk_ids) = 0)
                SET n.source_chunk_ids = $source_chunk_ids,
                    n.evidence_contract = "source_doc_and_source_chunk_ids_to_sqlite",
                    n.source_chunk_binding = $match_reason,
                    n.source_chunk_bound_at = datetime()
                RETURN count(n) AS count
                """,
                timeout=5,
            ),
            id=item["id"],
            source_chunk_ids=item["source_chunk_ids"],
            match_reason=item["match_reason"],
        )
        count += int(result.single()["count"])
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", action="append", choices=sorted(SYNC_ELIGIBLE_DOMAINS))
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)

    domains = args.domain or list(SYNC_ELIGIBLE_DOMAINS)
    driver = connect()
    try:
        with driver.session() as session:
            plan = build_plan(session, domains, args.limit)
            if not args.confirm:
                public = {key: value for key, value in plan.items() if key != "items"}
                public["examples"] = plan["items"][:20]
                print(json.dumps({"dry_run": True, **public}, ensure_ascii=False, indent=2))
                return 0

            applied = apply_plan(session, plan)
            after = domain_stats(session, domains)
            print(json.dumps({"dry_run": False, "planned": len(plan["items"]), "applied": applied, "after": after}, ensure_ascii=False, indent=2))
            return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
