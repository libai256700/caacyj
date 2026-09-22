#!/usr/bin/env python3
"""Preview structure-aware chunking against the current canonical SQLite store."""

from __future__ import annotations

import argparse
import fnmatch
import json
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag_store.chunker_v2 import chunk_document, infer_profile, summarize_chunks


RAG_DOCS = BASE_DIR / "rag_docs"
RAG_DB = BASE_DIR / "rag_chunks.db"


def old_stats(conn: sqlite3.Connection, doc_name: str) -> dict:
    rows = conn.execute(
        "SELECT LENGTH(text) AS chars FROM chunks WHERE doc_name = ? ORDER BY chunk_index",
        (doc_name,),
    ).fetchall()
    lengths = [int(row["chars"] or 0) for row in rows]
    return {
        "chunk_count": len(lengths),
        "min_chars": min(lengths) if lengths else 0,
        "avg_chars": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "max_chars": max(lengths) if lengths else 0,
    }


def list_doc_paths(patterns: list[str], domains: set[str]) -> list[Path]:
    paths = sorted(RAG_DOCS.glob("*.txt"))
    if patterns:
        paths = [
            path for path in paths
            if any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns)
        ]
    if domains:
        paths = [
            path for path in paths
            if infer_profile(path.name).domain in domains
        ]
    return paths


def preview_doc(conn: sqlite3.Connection, path: Path, sample: int) -> dict:
    text = path.read_text(encoding="utf-8")
    chunks = chunk_document(path.name, text)
    profile = infer_profile(path.name)
    old = old_stats(conn, path.name)
    new = summarize_chunks(chunks)
    report = {
        "doc_name": path.name,
        "domain": profile.domain,
        "mode": profile.mode,
        "old": old,
        "new": new,
        "delta_chunks": new["chunk_count"] - old["chunk_count"],
    }
    if sample > 0:
        report["samples"] = [
            {
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "chars": len(chunk.text),
                "preview": chunk.text.replace("\n", " ")[:220],
            }
            for chunk in chunks[:sample]
        ]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doc-glob", action="append", default=[], help="fnmatch pattern, e.g. '理论题库_*'")
    parser.add_argument("--domain", action="append", choices=("question_bank", "regulation", "textbook", "company_policy", "general"))
    parser.add_argument("--sample", type=int, default=0, help="include the first N v2 chunks per doc")
    parser.add_argument("--write-json", type=Path, help="write the full report to JSON")
    args = parser.parse_args()

    domains = set(args.domain or [])
    paths = list_doc_paths(args.doc_glob, domains)
    if not paths:
        print(json.dumps({"error": "no rag_docs matched"}, ensure_ascii=False, indent=2))
        return 2

    conn = sqlite3.connect(RAG_DB)
    conn.row_factory = sqlite3.Row
    try:
        docs = [preview_doc(conn, path, args.sample) for path in paths]
    finally:
        conn.close()

    total_old = sum(doc["old"]["chunk_count"] for doc in docs)
    total_new = sum(doc["new"]["chunk_count"] for doc in docs)
    report = {
        "schema": "chunker_v2_preview",
        "rag_docs": str(RAG_DOCS),
        "rag_db": str(RAG_DB),
        "doc_count": len(docs),
        "old_chunk_count": total_old,
        "new_chunk_count": total_new,
        "delta_chunks": total_new - total_old,
        "docs": docs,
    }

    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        key: report[key]
        for key in ("schema", "doc_count", "old_chunk_count", "new_chunk_count", "delta_chunks")
    }
    summary["largest_deltas"] = sorted(
        (
            {
                "doc_name": doc["doc_name"],
                "domain": doc["domain"],
                "old": doc["old"]["chunk_count"],
                "new": doc["new"]["chunk_count"],
                "delta": doc["delta_chunks"],
            }
            for doc in docs
        ),
        key=lambda item: abs(item["delta"]),
        reverse=True,
    )[:10]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
