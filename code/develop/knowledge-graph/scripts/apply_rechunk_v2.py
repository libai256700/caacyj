#!/usr/bin/env python3
"""Apply structure-aware chunking to selected canonical RAG domains.

SQLite remains the authoritative chunk text store. BM25, dense, Neo4j, and
sync packages must be rebuilt after this script changes chunk ids.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag_store.chunker_v2 import chunk_document, infer_profile, summarize_chunks


RAG_DOCS = BASE_DIR / "rag_docs"
RAG_DB = BASE_DIR / "rag_chunks.db"
DEFAULT_DOMAINS = ("regulation", "question_bank", "textbook")


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def old_stats(conn: sqlite3.Connection, doc_name: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT chunk_id, LENGTH(text) AS chars FROM chunks WHERE doc_name = ? ORDER BY chunk_index",
        (doc_name,),
    ).fetchall()
    lengths = [int(row["chars"] or 0) for row in rows]
    return {
        "chunk_count": len(lengths),
        "min_chars": min(lengths) if lengths else 0,
        "avg_chars": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "max_chars": max(lengths) if lengths else 0,
        "chunk_ids": [row["chunk_id"] for row in rows],
    }


def selected_doc_paths(domains: set[str]) -> list[Path]:
    paths = []
    for path in sorted(RAG_DOCS.glob("*.txt")):
        if infer_profile(path.name).domain in domains:
            paths.append(path)
    return paths


def build_plan(conn: sqlite3.Connection, paths: list[Path]) -> dict[str, Any]:
    docs = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        profile = infer_profile(path.name)
        chunks = chunk_document(path.name, text, profile)
        old = old_stats(conn, path.name)
        new = summarize_chunks(chunks)
        docs.append(
            {
                "doc_name": path.name,
                "domain": profile.domain,
                "mode": profile.mode,
                "old": {key: value for key, value in old.items() if key != "chunk_ids"},
                "new": new,
                "delta_chunks": new["chunk_count"] - old["chunk_count"],
                "new_chunk_ids": [chunk.chunk_id for chunk in chunks],
            }
        )
    return {
        "schema": "apply_rechunk_v2_plan",
        "rag_docs": str(RAG_DOCS),
        "rag_db": str(RAG_DB),
        "doc_count": len(docs),
        "old_chunk_count": sum(doc["old"]["chunk_count"] for doc in docs),
        "new_chunk_count": sum(doc["new"]["chunk_count"] for doc in docs),
        "docs": docs,
    }


def ensure_unique_chunk_ids(plan: dict[str, Any]) -> None:
    seen: dict[str, str] = {}
    duplicates = []
    for doc in plan["docs"]:
        for chunk_id in doc["new_chunk_ids"]:
            previous_doc = seen.get(chunk_id)
            if previous_doc is not None:
                duplicates.append({"chunk_id": chunk_id, "docs": [previous_doc, doc["doc_name"]]})
                continue
            seen[chunk_id] = doc["doc_name"]
    if duplicates:
        raise RuntimeError(f"duplicate v2 chunk ids: {duplicates[:5]}")


def backup_db() -> Path:
    backup_dir = BASE_DIR / "backups" / "rechunk_v2"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"rag_chunks.{now_tag()}.db"
    shutil.copy2(RAG_DB, backup_path)
    for suffix in ("-wal", "-shm"):
        extra = RAG_DB.with_name(RAG_DB.name + suffix)
        if extra.exists():
            shutil.copy2(extra, backup_path.with_name(backup_path.name + suffix))
    return backup_path


def apply_plan(conn: sqlite3.Connection, paths: list[Path]) -> dict[str, Any]:
    applied = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        for path in paths:
            profile = infer_profile(path.name)
            chunks = chunk_document(path.name, path.read_text(encoding="utf-8"), profile)
            conn.execute("DELETE FROM chunks WHERE doc_name = ?", (path.name,))
            conn.executemany(
                """
                INSERT INTO chunks (chunk_id, text, doc_name, chunk_index)
                VALUES (?, ?, ?, ?)
                """,
                [(chunk.chunk_id, chunk.text, chunk.doc_name, chunk.chunk_index) for chunk in chunks],
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (doc_name, doc_path, chunk_count, updated_at)
                VALUES (?, ?, ?, datetime('now','localtime'))
                """,
                (path.name, str(path), len(chunks)),
            )
            applied.append({"doc_name": path.name, "chunk_count": len(chunks), "domain": profile.domain})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"applied_docs": applied, "applied_chunk_count": sum(item["chunk_count"] for item in applied)}


def sqlite_totals(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        "SELECT COUNT(*) AS chunks, COUNT(DISTINCT doc_name) AS documents FROM chunks"
    ).fetchone()
    return {"chunks": int(row["chunks"]), "documents": int(row["documents"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", action="append", choices=DEFAULT_DOMAINS, help="domain to rechunk; defaults to all sync domains")
    parser.add_argument("--apply", action="store_true", help="write v2 chunks into canonical SQLite")
    parser.add_argument("--report", type=Path, default=BASE_DIR / "review_reports" / "apply_rechunk_v2_report.json")
    args = parser.parse_args(argv)

    domains = set(args.domain or DEFAULT_DOMAINS)
    paths = selected_doc_paths(domains)
    if not paths:
        print(json.dumps({"error": "no selected rag_docs"}, ensure_ascii=False, indent=2))
        return 2

    conn = sqlite3.connect(RAG_DB)
    conn.row_factory = sqlite3.Row
    try:
        before_totals = sqlite_totals(conn)
        plan = build_plan(conn, paths)
        ensure_unique_chunk_ids(plan)
        report: dict[str, Any] = {
            **plan,
            "apply": bool(args.apply),
            "before_totals": before_totals,
            "delta_chunks": plan["new_chunk_count"] - plan["old_chunk_count"],
        }
        if args.apply:
            backup_path = backup_db()
            result = apply_plan(conn, paths)
            report["backup_db"] = str(backup_path)
            report["result"] = result
            report["after_totals"] = sqlite_totals(conn)
        write_json(args.report, report)
    finally:
        conn.close()

    summary = {
        "apply": bool(args.apply),
        "doc_count": plan["doc_count"],
        "old_chunk_count": plan["old_chunk_count"],
        "new_chunk_count": plan["new_chunk_count"],
        "delta_chunks": plan["new_chunk_count"] - plan["old_chunk_count"],
        "report": str(args.report),
    }
    if args.apply:
        summary["backup_db"] = report["backup_db"]
        summary["after_totals"] = report["after_totals"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
