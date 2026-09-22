#!/usr/bin/env python3
"""Freshness checks for derived RAG indexes.

SQLite is the canonical chunk store. BM25 and dense indexes are fresh only when
their manifests point at the same SQLite fingerprint and their indexed counts
match the canonical chunk count.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

try:
    from .bm25_index import BM25Index
    from .dense_index import DenseIndex
    from .sqlite_store import RagStore
except ImportError:
    from bm25_index import BM25Index
    from dense_index import DenseIndex
    from sqlite_store import RagStore


BASE_DIR = Path(__file__).parent.parent
DEFAULT_DB_PATH = BASE_DIR / "rag_chunks.db"
DEFAULT_BM25_DIR = BASE_DIR / "rag_index" / "bm25"
DEFAULT_DENSE_PATH = BASE_DIR / "rag_index" / "dense_bge_m3.sqlite"


def sqlite_source(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with RagStore(str(db_path)) as store:
        store.init_tables()
        fingerprint = store.fingerprint()
    return {
        "db_path": str(db_path),
        "chunk_count": int(fingerprint.get("chunk_count") or 0),
        "doc_count": int(fingerprint.get("doc_count") or 0),
        "text_bytes": int(fingerprint.get("text_bytes") or 0),
        "max_created_at": fingerprint.get("max_created_at", ""),
        "schema": fingerprint.get("schema", ""),
        "fingerprint": fingerprint.get("fingerprint", ""),
        "raw": fingerprint,
    }


def check_index_freshness(
    db_path: str | Path = DEFAULT_DB_PATH,
    bm25_dir: str | Path = DEFAULT_BM25_DIR,
    dense_path: str | Path = DEFAULT_DENSE_PATH,
    auto_rebuild: bool = False,
    rebuild_bm25: bool = True,
    rebuild_dense: bool = True,
    embed_func: Callable[[str], list[float]] | None = None,
) -> dict[str, Any]:
    """Return a single freshness report and optionally rebuild stale indexes."""
    source = sqlite_source(db_path)
    expected = source["raw"]
    issues: list[dict[str, Any]] = []
    rebuilds: dict[str, Any] = {}

    bm25 = BM25Index(index_dir=str(bm25_dir), db_path=str(db_path))
    bm25_status = _bm25_status(bm25, expected, source["chunk_count"])
    if not bm25_status["fresh"] and auto_rebuild and rebuild_bm25:
        rebuilds["bm25"] = bm25.build(force=True)
        bm25_status = _bm25_status(bm25, expected, source["chunk_count"])

    dense = DenseIndex(index_path=str(dense_path), db_path=str(db_path))
    dense_status = _dense_status(dense, expected, source["chunk_count"])
    if not dense_status["fresh"] and auto_rebuild and rebuild_dense:
        rebuilds["dense"] = dense.build(force=True, embed_func=embed_func)
        dense.close()
        dense = DenseIndex(index_path=str(dense_path), db_path=str(db_path))
        dense_status = _dense_status(dense, expected, source["chunk_count"])

    for name, status in (("bm25", bm25_status), ("dense", dense_status)):
        for reason in status.get("issues", []):
            issues.append({"index": name, **reason})

    return {
        "fresh": not issues,
        "sqlite": source,
        "bm25": bm25_status,
        "dense": dense_status,
        "issues": issues,
        "rebuilds": rebuilds,
        "hint": "" if not issues else _rebuild_hint(issues, rebuild_bm25, rebuild_dense),
    }


def _bm25_status(index: BM25Index, expected: dict[str, Any], expected_chunks: int) -> dict[str, Any]:
    exists = index.exists()
    manifest = index.manifest()
    indexed_docs = int(manifest.get("indexed_docs") or 0)
    issues = []
    if not exists:
        issues.append({"field": "exists", "expected": True, "actual": False})
    if manifest.get("source") != expected:
        issues.append({"field": "fingerprint", "expected": expected, "actual": manifest.get("source")})
    if indexed_docs != expected_chunks:
        issues.append({"field": "indexed_docs", "expected": expected_chunks, "actual": indexed_docs})
    return {
        "fresh": not issues,
        "exists": exists,
        "indexed_docs": indexed_docs,
        "manifest": manifest,
        "issues": issues,
    }


def _dense_status(index: DenseIndex, expected: dict[str, Any], expected_chunks: int) -> dict[str, Any]:
    exists = index.exists()
    manifest = index.manifest()
    stats = _dense_counts(index) if exists else {"indexed_count": 0}
    manifest_count = int(manifest.get("indexed_count") or 0)
    indexed_count = int(stats.get("indexed_count") or 0)
    issues = []
    if not exists:
        issues.append({"field": "exists", "expected": True, "actual": False})
    if manifest.get("source") != expected:
        issues.append({"field": "fingerprint", "expected": expected, "actual": manifest.get("source")})
    if indexed_count != expected_chunks:
        issues.append({"field": "indexed_count", "expected": expected_chunks, "actual": indexed_count})
    if manifest_count != expected_chunks:
        issues.append({"field": "manifest.indexed_count", "expected": expected_chunks, "actual": manifest_count})
    return {
        "fresh": not issues,
        "exists": exists,
        "indexed_count": indexed_count,
        "manifest_indexed_count": manifest_count,
        "manifest": manifest,
        "issues": issues,
    }


def _dense_counts(index: DenseIndex) -> dict[str, int]:
    try:
        conn = index.connect()
        row = conn.execute("SELECT COUNT(*) AS cnt FROM embeddings").fetchone()
        return {"indexed_count": int(row["cnt"] if row else 0)}
    except Exception:
        return {"indexed_count": 0}


def _rebuild_hint(issues: list[dict[str, Any]], rebuild_bm25: bool, rebuild_dense: bool) -> str:
    stale = {issue["index"] for issue in issues}
    commands = []
    if "bm25" in stale and rebuild_bm25:
        commands.append("python3 -m rag_store.bm25_index --rebuild")
    if "dense" in stale and rebuild_dense:
        commands.append("python3 scripts/build_dense_index.py --force")
    if not commands:
        return "Run with --auto-rebuild for enabled indexes, or rebuild the stale indexes manually."
    return "Rebuild stale indexes: " + " && ".join(commands)


def dumps_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
