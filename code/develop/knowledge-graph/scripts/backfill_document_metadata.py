#!/usr/bin/env python3
"""Backfill canonical source metadata onto Neo4j Document nodes.

SQLite remains the authoritative chunk text store. This script only annotates
Neo4j Document nodes so health checks can distinguish source files from
chapter/synthetic graph documents.
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
RAG_DB = BASE_DIR / "rag_chunks.db"
RAG_DOCS = BASE_DIR / "rag_docs"
FEISHU_RAW = BASE_DIR / "feishu_raw"
ALIAS_PATH = BASE_DIR / "rag_store" / "source_doc_aliases.json"
REPORT_ROOT = BASE_DIR / "review_reports"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
RUN_ID = f"document_metadata_backfill_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


PREFIXES = ("企业信息", "人事制度", "理论题库", "政策法规", "无人机理论书籍")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def load_sqlite_docs() -> dict[str, dict[str, Any]]:
    with sqlite3.connect(RAG_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT doc_name, doc_path, chunk_count FROM documents ORDER BY doc_name"
        ).fetchall()
    return {row["doc_name"]: dict(row) for row in rows}


def load_aliases() -> dict[str, list[str]]:
    if not ALIAS_PATH.exists():
        return {}
    data = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
    aliases = data.get("aliases", {})
    return {str(key): [str(item) for item in value] for key, value in aliases.items()}


def normalize_doc_name(name: str) -> str:
    return re.sub(r"（文档）$", "", name or "").strip()


def doc_name_candidates(name: str, aliases: dict[str, list[str]]) -> list[str]:
    raw = (name or "").strip()
    core = normalize_doc_name(raw)
    out: list[str] = []

    def add(value: str) -> None:
        if value and value not in out:
            out.append(value)

    for value in (raw, core):
        add(value)
        for alias in aliases.get(value, []):
            add(alias)
        if value and not value.endswith((".txt", ".md")):
            add(f"{value}.txt")
        stripped = re.sub(rf"^({'|'.join(PREFIXES)})_", "", value)
        if stripped != value:
            add(stripped)
            if not stripped.endswith((".txt", ".md")):
                add(f"{stripped}.txt")

        for prefix in PREFIXES:
            add(f"{prefix}_{value}")
            if not value.endswith((".txt", ".md")):
                add(f"{prefix}_{value}.txt")

    return out


def resolve_path(doc_name: str, row: dict[str, Any]) -> str:
    doc_path = row.get("doc_path") or ""
    if doc_path:
        path = Path(doc_path)
        if path.is_absolute() and path.exists():
            return str(path)
        for root in (RAG_DOCS, FEISHU_RAW):
            candidate = root / doc_path
            if candidate.exists():
                return str(candidate)

    for root in (RAG_DOCS, FEISHU_RAW):
        candidate = root / doc_name
        if candidate.exists():
            return str(candidate)

    bare = re.sub(rf"^({'|'.join(PREFIXES)})_", "", doc_name)
    for root in (FEISHU_RAW, RAG_DOCS):
        candidate = root / bare
        if candidate.exists():
            return str(candidate)

    return f"sqlite://{RAG_DB}#documents/{doc_name}"


def classify_kind(node_name: str, canonical_doc_name: str, resolution: str) -> str:
    if resolution == "alias":
        if node_name.startswith(("CCAR-92部_", "教材第", "设计教材·")):
            return "chapter_alias"
        return "document_alias"
    return "source_file"


def fuzzy_match(name: str, sqlite_docs: dict[str, dict[str, Any]]) -> str | None:
    core = normalize_doc_name(name)
    if len(core) < 4:
        return None
    matches = [doc for doc in sqlite_docs if core in doc]
    return matches[0] if len(matches) == 1 else None


def resolve_document(
    node_name: str,
    sqlite_docs: dict[str, dict[str, Any]],
    aliases: dict[str, list[str]],
) -> dict[str, Any]:
    for candidate in doc_name_candidates(node_name, aliases):
        if candidate in sqlite_docs:
            resolution = "exact" if candidate in {node_name, normalize_doc_name(node_name)} else "alias"
            row = sqlite_docs[candidate]
            path = resolve_path(candidate, row)
            kind = classify_kind(node_name, candidate, resolution)
            return {
                "rag_resolved": True,
                "canonical_doc_name": candidate,
                "canonical_doc_path": path,
                "document_kind": kind,
                "source_resolution": resolution,
                "chunk_count": int(row.get("chunk_count") or 0),
                "source": "sqlite_rag",
                "path": path,
                "file_token_status": "not_available",
            }

    fuzzy = fuzzy_match(node_name, sqlite_docs)
    if fuzzy:
        row = sqlite_docs[fuzzy]
        path = resolve_path(fuzzy, row)
        return {
            "rag_resolved": True,
            "canonical_doc_name": fuzzy,
            "canonical_doc_path": path,
            "document_kind": "document_alias",
            "source_resolution": "fuzzy_unique",
            "chunk_count": int(row.get("chunk_count") or 0),
            "source": "sqlite_rag",
            "path": path,
            "file_token_status": "not_available",
        }

    return {
        "rag_resolved": False,
        "canonical_doc_name": None,
        "canonical_doc_path": None,
        "document_kind": "unresolved_document",
        "source_resolution": "unresolved",
        "chunk_count": 0,
        "source": "unresolved",
        "path": None,
        "file_token_status": "missing",
    }


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def property_counts(session) -> dict[str, int]:
    row = session.run(
        """
        MATCH (d:Document)
        RETURN count(d) AS total,
               count(d.source) AS source,
               count(d.path) AS path,
               count(d.fileToken) AS fileToken,
               count(d.canonical_doc_name) AS canonical_doc_name,
               count(d.canonical_doc_path) AS canonical_doc_path,
               count(d.document_kind) AS document_kind,
               count(d.rag_resolved) AS rag_resolved
        """
    ).single()
    return dict(row)


def collect_documents(session) -> list[dict[str, Any]]:
    return session.run(
        """
        MATCH (d:Document)
        RETURN elementId(d) AS id, d.name AS name, keys(d) AS keys, properties(d) AS props
        ORDER BY d.name
        """
    ).data()


def build_plan(session) -> dict[str, Any]:
    sqlite_docs = load_sqlite_docs()
    aliases = load_aliases()
    docs = collect_documents(session)
    items = []
    for doc in docs:
        meta = resolve_document(doc["name"], sqlite_docs, aliases)
        items.append(
            {
                "id": doc["id"],
                "name": doc["name"],
                "before_keys": doc["keys"],
                "metadata": meta,
            }
        )

    by_kind: dict[str, int] = {}
    by_resolution: dict[str, int] = {}
    resolved = 0
    for item in items:
        meta = item["metadata"]
        resolved += 1 if meta["rag_resolved"] else 0
        by_kind[meta["document_kind"]] = by_kind.get(meta["document_kind"], 0) + 1
        by_resolution[meta["source_resolution"]] = by_resolution.get(meta["source_resolution"], 0) + 1

    return {
        "run_id": RUN_ID,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sqlite_doc_count": len(sqlite_docs),
        "document_count": len(items),
        "resolved_count": resolved,
        "unresolved_count": len(items) - resolved,
        "by_kind": by_kind,
        "by_resolution": by_resolution,
        "property_counts_before": property_counts(session),
        "items": items,
    }


def apply_plan(session, plan: dict[str, Any]) -> None:
    for item in plan["items"]:
        meta = item["metadata"]
        patch = {
            "canonical_doc_name": meta["canonical_doc_name"],
            "canonical_doc_path": meta["canonical_doc_path"],
            "document_kind": meta["document_kind"],
            "source_resolution": meta["source_resolution"],
            "rag_resolved": meta["rag_resolved"],
            "rag_chunk_count": meta["chunk_count"],
            "source": meta["source"],
            "path": meta["path"],
            "file_token_status": meta["file_token_status"],
            "metadata_backfilled_by": RUN_ID,
            "metadata_backfilled_at": datetime.now().isoformat(timespec="seconds"),
        }
        session.run(
            """
            MATCH (d:Document) WHERE elementId(d) = $id
            SET d += $patch
            """,
            id=item["id"],
            patch=patch,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="write metadata to Neo4j")
    parser.add_argument("--report-dir", type=Path, help="override report directory")
    args = parser.parse_args()

    report_dir = args.report_dir or (REPORT_ROOT / RUN_ID)
    report_dir.mkdir(parents=True, exist_ok=True)

    driver = connect()
    try:
        with driver.session() as session:
            plan = build_plan(session)
            write_json(report_dir / "plan.json", plan)
            if args.confirm:
                apply_plan(session, plan)
                after = {
                    "run_id": RUN_ID,
                    "property_counts_after": property_counts(session),
                }
                write_json(report_dir / "after.json", after)
                print(f"applied document metadata backfill: {report_dir}")
            else:
                print(f"dry run only: {report_dir}")
            print(
                f"documents={plan['document_count']} resolved={plan['resolved_count']} "
                f"unresolved={plan['unresolved_count']} kinds={plan['by_kind']}"
            )
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
