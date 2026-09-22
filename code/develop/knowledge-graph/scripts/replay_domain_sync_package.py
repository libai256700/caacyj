#!/usr/bin/env python3
"""Replay domain sync packages in an isolated local directory.

The replay validates that a package can rebuild canonical SQLite chunks, BM25,
dense embeddings, and a Neo4j import payload without reading the source repo's
live derived indexes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from rag_store.bm25_index import BM25Index
from rag_store.dense_index import DenseIndex, ollama_embedding
from rag_store.sqlite_store import RagStore
from rag_store.semantic_schema import SYNC_ELIGIBLE_DOMAINS, relationship_missing_evidence_reason

DEFAULT_PACKAGE_DIR = BASE_DIR / "sync_packages"
DEFAULT_REPLAY_DIR = BASE_DIR / "remote_replay"

PROBE_QUERIES = {
    "regulation": ["民用航空法 施行 日期", "CCAR-92 执照 申请条件"],
    "question_bank": ["低空风切变", "无人机任务规划"],
    "textbook": ["飞行原理", "固定翼结构设计"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def domain_chunk_fingerprint(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    h = hashlib.sha256()
    text_bytes = 0
    for row in chunks:
        text = row.get("text") or ""
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        text_bytes += len(text.encode("utf-8"))
        h.update(
            f"{row['chunk_id']}|{row['doc_name']}|{row['chunk_index']}|{len(text)}|{text_hash}\n".encode("utf-8")
        )
    return {
        "schema": "domain-chunks-v1",
        "chunk_count": len(chunks),
        "doc_count": len({row["doc_name"] for row in chunks}),
        "text_bytes": text_bytes,
        "fingerprint": h.hexdigest(),
    }


def load_replay_chunks(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT chunk_id, doc_name, chunk_index, text, created_at
            FROM chunks
            ORDER BY doc_name, chunk_index
            """
        ).fetchall()
    return [dict(row) for row in rows]


def refresh_documents_table(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM documents")
    rows = conn.execute(
        """
        SELECT doc_name, COUNT(*) AS chunk_count
        FROM chunks
        GROUP BY doc_name
        ORDER BY doc_name
        """
    ).fetchall()
    conn.executemany(
        "INSERT INTO documents (doc_name, doc_path, chunk_count) VALUES (?, ?, ?)",
        [(row[0], row[0], row[1]) for row in rows],
    )


def create_replay_sqlite(db_path: Path, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE chunks (
                chunk_id   TEXT PRIMARY KEY,
                text       TEXT NOT NULL,
                doc_name   TEXT NOT NULL,
                chunk_index INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX idx_chunks_doc ON chunks(doc_name);
            CREATE INDEX idx_chunks_doc_idx ON chunks(doc_name, chunk_index);

            CREATE TABLE documents (
                doc_name    TEXT PRIMARY KEY,
                doc_path    TEXT,
                chunk_count INTEGER DEFAULT 0,
                updated_at  TEXT DEFAULT (datetime('now','localtime'))
            );
            """
        )
        conn.executemany(
            """
            INSERT INTO chunks (chunk_id, text, doc_name, chunk_index, created_at)
            VALUES (:chunk_id, :text, :doc_name, :chunk_index, :created_at)
            """,
            chunks,
        )
        refresh_documents_table(conn)
        conn.commit()
    finally:
        conn.close()

    with RagStore(str(db_path)) as store:
        store.init_tables()
        return store.fingerprint()


def apply_incremental_sqlite(
    db_path: Path,
    package_dir: Path,
    manifest: dict[str, Any],
    target_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    incremental = manifest.get("incremental") or {}
    if not incremental.get("can_apply_incrementally"):
        raise RuntimeError("package has no previous snapshot for incremental replay")
    if not db_path.exists():
        raise RuntimeError(f"remote replay sqlite does not exist: {db_path}")

    base_fingerprint = incremental.get("base_fingerprint")
    target_fingerprint = incremental.get("target_fingerprint") or manifest.get("domain_fingerprint")
    current_chunks = load_replay_chunks(db_path)
    current_fingerprint = domain_chunk_fingerprint(current_chunks)
    if current_fingerprint != base_fingerprint:
        raise RuntimeError(
            "remote replay base fingerprint mismatch; "
            f"expected {base_fingerprint}, got {current_fingerprint}"
        )

    changed = read_jsonl(package_dir / incremental.get("changed_chunks_file", "changed_chunks.jsonl"))
    deleted = read_jsonl(package_dir / incremental.get("deleted_chunks_file", "deleted_chunks.jsonl"))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN")
        for item in deleted:
            conn.execute("DELETE FROM chunks WHERE chunk_id = ?", (item["chunk_id"],))
        for item in changed:
            row = item["chunk"]
            conn.execute(
                """
                INSERT INTO chunks (chunk_id, text, doc_name, chunk_index, created_at)
                VALUES (:chunk_id, :text, :doc_name, :chunk_index, :created_at)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    text = excluded.text,
                    doc_name = excluded.doc_name,
                    chunk_index = excluded.chunk_index,
                    created_at = excluded.created_at
                """,
                row,
            )
        refresh_documents_table(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    replayed_chunks = load_replay_chunks(db_path)
    replayed_fingerprint = domain_chunk_fingerprint(replayed_chunks)
    if replayed_fingerprint != target_fingerprint:
        raise RuntimeError(
            "incremental replay target fingerprint mismatch; "
            f"expected {target_fingerprint}, got {replayed_fingerprint}"
        )
    if domain_chunk_fingerprint(target_chunks) != replayed_fingerprint:
        raise RuntimeError("incremental replay does not match package chunks.jsonl")

    with RagStore(str(db_path)) as store:
        store.init_tables()
        sqlite_source = store.fingerprint()
    return {
        "mode": "incremental",
        "changed_chunks": len(changed),
        "deleted_chunks": len(deleted),
        "sqlite_source_fingerprint": sqlite_source,
        "replayed_fingerprint": replayed_fingerprint,
    }


def copy_canonical(package_dir: Path, replay_dir: Path) -> dict[str, Any]:
    src = package_dir / "canonical"
    dst = replay_dir / "canonical"
    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.copytree(src, dst)
    tables = []
    for path in sorted(dst.glob("*.csv")) if dst.exists() else []:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            rows = sum(1 for row in reader if any(cell.strip() for cell in row))
        tables.append({"table": path.stem, "path": str(path), "columns": header, "row_count": rows})
    return {"path": str(dst), "tables": tables}


def build_bm25(replay_dir: Path, db_path: Path, expected_chunks: int) -> dict[str, Any]:
    index_dir = replay_dir / "rag_index" / "bm25"
    idx = BM25Index(index_dir=str(index_dir), db_path=str(db_path))
    stat = idx.build(force=True)
    manifest = idx.manifest()
    fresh = idx.is_fresh()
    idx.close()
    return {
        "index_dir": str(index_dir),
        "build": stat,
        "manifest": manifest,
        "fresh": fresh,
        "indexed_docs_match": int(manifest.get("indexed_docs") or 0) == expected_chunks,
    }


def build_dense(replay_dir: Path, db_path: Path, mode: str, sample: int) -> dict[str, Any]:
    if mode == "skip":
        return {"mode": mode, "fresh": False, "skipped": True}

    dense_db_path = db_path
    source_note = "full"
    if mode == "sample":
        dense_db_path = replay_dir / "rag_chunks_dense_sample.db"
        with sqlite3.connect(db_path) as src, sqlite3.connect(dense_db_path) as dst:
            src.row_factory = sqlite3.Row
            rows = src.execute(
                "SELECT chunk_id, text, doc_name, chunk_index, created_at FROM chunks ORDER BY doc_name, chunk_index LIMIT ?",
                (sample,),
            ).fetchall()
            fp = create_replay_sqlite(dense_db_path, [dict(row) for row in rows])
        source_note = f"sample:{sample}"

    index_path = replay_dir / "rag_index" / "dense_bge_m3.sqlite"
    idx = DenseIndex(index_path=str(index_path), db_path=str(dense_db_path))
    try:
        stat = idx.build(force=True, embed_func=ollama_embedding)
        stats = idx.stats()
        return {
            "mode": mode,
            "source": source_note,
            "index_path": str(index_path),
            "build": stat,
            "stats": stats,
            "fresh": bool(stats.get("fresh")),
        }
    except Exception as exc:
        return {"mode": mode, "source": source_note, "fresh": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        idx.close()


def cypher_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def cypher_key(value: str) -> str:
    return "`" + str(value).replace("`", "``") + "`"


def cypher_properties(props: dict[str, Any]) -> str:
    items = ", ".join(f"{cypher_key(key)}: {cypher_value(value)}" for key, value in sorted(props.items()))
    return "{" + items + "}"


def rel_type(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch == "_")
    return cleaned or "RELATED_TO"


def write_neo4j_import(package_dir: Path, replay_dir: Path) -> dict[str, Any]:
    nodes = read_jsonl(package_dir / "graph_nodes.jsonl")
    relationships = read_jsonl(package_dir / "graph_relationships.jsonl")
    cypher_path = replay_dir / "neo4j_import.cypher"
    lines = [
        "// Generated by scripts/replay_domain_sync_package.py",
        "CREATE CONSTRAINT replay_node_key IF NOT EXISTS FOR (n:ReplayNode) REQUIRE n.replay_key IS UNIQUE;",
    ]
    for node in nodes:
        labels = ":".join(["ReplayNode", *[label for label in node.get("labels", []) if label != "ReplayNode"]])
        props = dict(node.get("properties") or {})
        props["replay_key"] = node["key"]
        lines.append(f"MERGE (n:{labels} {{replay_key: {cypher_value(node['key'])}}}) SET n += {cypher_properties(props)};")
    for rel in relationships:
        props = rel.get("properties") or {}
        if relationship_missing_evidence_reason(rel.get("type") or "", props):
            continue
        lines.append(
            "MATCH (a:ReplayNode {replay_key: "
            + cypher_value(rel["start_key"])
            + "}), (b:ReplayNode {replay_key: "
            + cypher_value(rel["end_key"])
            + f"}}) MERGE (a)-[r:{rel_type(rel.get('type') or '')}]->(b) SET r += {cypher_properties(props)};"
        )
    cypher_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "mode": "import_payload",
        "nodes": len(nodes),
        "relationships": len(relationships),
        "cypher": str(cypher_path),
        "applied_to_neo4j": False,
    }


def run_probes(domain: str, db_path: Path, bm25_dir: Path, dense_report: dict[str, Any]) -> list[dict[str, Any]]:
    probes = []
    bm25 = BM25Index(index_dir=str(bm25_dir), db_path=str(db_path))
    dense = None
    if dense_report.get("fresh") and dense_report.get("mode") == "full":
        dense = DenseIndex(index_path=dense_report["index_path"], db_path=str(db_path))
    try:
        with RagStore(str(db_path)) as store:
            store.init_tables()
            for query in PROBE_QUERIES.get(domain, [domain]):
                bm25_results = bm25.search(query, limit=3)
                dense_results = []
                if dense:
                    dense_results = dense.search_by_embedding(ollama_embedding(query), limit=3)
                top_ids = [item["chunk_id"] for item in bm25_results[:1] + dense_results[:1]]
                resolved = store.get_chunks_batch(top_ids)
                probes.append(
                    {
                        "query": query,
                        "bm25_top": bm25_results[:3],
                        "dense_top": dense_results[:3],
                        "resolved_chunk_ids": [row["chunk_id"] for row in resolved],
                        "resolved_all": len(resolved) == len(set(top_ids)),
                    }
                )
    finally:
        bm25.close()
        if dense:
            dense.close()
    return probes


def replay_domain(package_root: Path, replay_root: Path, domain: str, dense_mode: str, dense_sample: int, force: bool) -> dict[str, Any]:
    package_dir = package_root / domain
    manifest = read_json(package_dir / "domain_manifest.json")
    replay_dir = replay_root / domain
    if force and replay_dir.exists():
        shutil.rmtree(replay_dir)
    replay_dir.mkdir(parents=True, exist_ok=True)

    chunks = read_jsonl(package_dir / manifest["chunks_file"])
    package_fp = manifest["domain_fingerprint"]
    replay_fp = domain_chunk_fingerprint(chunks)
    db_path = replay_dir / "rag_chunks.db"
    fallback_reason = None
    try:
        if force:
            raise RuntimeError("force requested full rebuild")
        incremental_result = apply_incremental_sqlite(db_path, package_dir, manifest, chunks)
        replay_mode = "incremental"
        sqlite_source = incremental_result["sqlite_source_fingerprint"]
    except Exception as exc:
        fallback_reason = f"{type(exc).__name__}: {exc}"
        sqlite_source = create_replay_sqlite(db_path, chunks)
        incremental_result = None
        replay_mode = "full_rebuild_after_incremental_fallback" if not force else "full_rebuild_forced"
    canonical = copy_canonical(package_dir, replay_dir)
    bm25 = build_bm25(replay_dir, db_path, expected_chunks=len(chunks))
    dense = build_dense(replay_dir, db_path, dense_mode, dense_sample)
    neo4j = write_neo4j_import(package_dir, replay_dir)
    probes = run_probes(domain, db_path, replay_dir / "rag_index" / "bm25", dense)

    checks = {
        "domain_fingerprint_match": replay_fp == package_fp,
        "sqlite_chunk_count_match": int(sqlite_source.get("chunk_count") or 0) == len(chunks),
        "bm25_fresh": bool(bm25.get("fresh")),
        "bm25_indexed_docs_match": bool(bm25.get("indexed_docs_match")),
        "dense_fresh": dense_mode == "skip" or bool(dense.get("fresh")),
        "neo4j_payload_available": neo4j["nodes"] > 0 and neo4j["relationships"] >= 0,
        "probes_resolve": all(item["resolved_all"] for item in probes),
    }
    report = {
        "domain": domain,
        "package_dir": str(package_dir),
        "replay_dir": str(replay_dir),
        "generated_at": utc_now(),
        "replay_mode": replay_mode,
        "incremental": {
            "attempted": not force,
            "applied": incremental_result is not None,
            "fallback_reason": fallback_reason,
            "result": incremental_result,
            "package": manifest.get("incremental") or {},
        },
        "package_fingerprint": package_fp,
        "replayed_fingerprint": replay_fp,
        "sqlite_source_fingerprint": sqlite_source,
        "canonical": canonical,
        "bm25": bm25,
        "dense": dense,
        "neo4j": neo4j,
        "probes": probes,
        "checks": checks,
        "ready": all(checks.values()),
    }
    write_json(replay_dir / "replay_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", default=str(DEFAULT_PACKAGE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPLAY_DIR))
    parser.add_argument("--domain", action="append", choices=sorted(SYNC_ELIGIBLE_DOMAINS))
    parser.add_argument("--dense-mode", choices=("full", "sample", "skip"), default="full")
    parser.add_argument("--dense-sample", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    package_root = Path(args.package_dir).expanduser()
    replay_root = Path(args.output_dir).expanduser()
    domains = args.domain or list(SYNC_ELIGIBLE_DOMAINS)
    reports = [replay_domain(package_root, replay_root, domain, args.dense_mode, args.dense_sample, args.force) for domain in domains]
    summary = {
        "generated_at": utc_now(),
        "package_root": str(package_root),
        "replay_root": str(replay_root),
        "dense_mode": args.dense_mode,
        "ready": all(item["ready"] for item in reports),
        "domains": [
            {
                "domain": item["domain"],
                "ready": item["ready"],
                "replay_mode": item["replay_mode"],
                "incremental_applied": item["incremental"]["applied"],
                "incremental_fallback_reason": item["incremental"]["fallback_reason"],
                "checks": item["checks"],
                "replay_dir": item["replay_dir"],
                "bm25_indexed_docs": item["bm25"].get("manifest", {}).get("indexed_docs"),
                "dense_indexed": item["dense"].get("build", {}).get("indexed"),
                "neo4j_nodes": item["neo4j"].get("nodes"),
                "neo4j_relationships": item["neo4j"].get("relationships"),
            }
            for item in reports
        ],
    }
    write_json(replay_root / "replay_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
