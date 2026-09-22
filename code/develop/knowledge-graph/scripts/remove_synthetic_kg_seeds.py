#!/usr/bin/env python3
"""Remove synthetic KG seed sources from the canonical RAG path.

Synthetic seeds were graph-only descriptions that had been promoted into
SQLite chunks as ``图谱种子_*.txt`` / ``kg_seed_*``. They are not imported
source documents, so they must not be answer evidence.
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

from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_DB = BASE_DIR / "rag_chunks.db"
DENSE_DB = BASE_DIR / "rag_index" / "dense_bge_m3.sqlite"
REPORT_ROOT = BASE_DIR / "review_reports"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
RUN_ID = f"remove_synthetic_kg_seeds_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

sys.path.insert(0, str(BASE_DIR))
from rag_store.sqlite_store import RagStore  # noqa: E402


def json_default(value: Any) -> str:
    return str(value)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def connect_neo4j():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def sqlite_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def collect_sqlite_seed_rows() -> dict[str, Any]:
    with sqlite3.connect(SQLITE_DB) as conn:
        conn.row_factory = sqlite3.Row
        chunks = sqlite_rows(
            conn,
            """
            SELECT chunk_id, doc_name, chunk_index, created_at, text
            FROM chunks
            WHERE doc_name LIKE '图谱种子_%' OR chunk_id LIKE 'kg_seed_%'
            ORDER BY doc_name, chunk_index, chunk_id
            """,
        )
        docs = sqlite_rows(
            conn,
            """
            SELECT doc_name, doc_path, chunk_count, updated_at
            FROM documents
            WHERE doc_name LIKE '图谱种子_%'
            ORDER BY doc_name
            """,
        )
        totals = {
            "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        }
    return {"chunks": chunks, "documents": docs, "totals": totals}


def collect_dense_seed_rows() -> dict[str, Any]:
    if not DENSE_DB.exists():
        return {"exists": False, "rows": [], "totals": {}}
    with sqlite3.connect(DENSE_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = sqlite_rows(
            conn,
            """
            SELECT chunk_id, doc_name, chunk_index, model, dim, updated_at
            FROM embeddings
            WHERE doc_name LIKE '图谱种子_%' OR chunk_id LIKE 'kg_seed_%'
            ORDER BY doc_name, chunk_index, chunk_id
            """,
        )
        totals = {
            "embeddings": conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0],
        }
    return {"exists": True, "rows": rows, "totals": totals}


def collect_neo4j_seed_rows(session) -> dict[str, Any]:
    docs = session.run(
        """
        MATCH (d:Document)
        WHERE d.synthetic = true
           OR d.document_kind = 'synthetic_seed'
           OR toString(d.seed_doc_name) STARTS WITH '图谱种子_'
           OR toString(d.canonical_doc_name) STARTS WITH '图谱种子_'
        RETURN elementId(d) AS id, labels(d) AS labels, properties(d) AS props
        ORDER BY coalesce(d.canonical_doc_name, d.seed_doc_name, d.name)
        """
    ).data()
    entities = session.run(
        """
        MATCH (n)
        WHERE NOT n:Document
          AND (
            toString(n.chunk_id) STARTS WITH 'kg_seed_'
            OR any(x IN coalesce(n.source_chunk_ids, []) WHERE toString(x) STARTS WITH 'kg_seed_')
          )
        RETURN elementId(n) AS id, labels(n) AS labels, n.name AS name, properties(n) AS props
        ORDER BY coalesce(n.source_doc, ''), n.name
        """
    ).data()
    relations = session.run(
        """
        MATCH ()-[r]-()
        WHERE any(x IN coalesce(r.source_chunk_ids, []) WHERE toString(x) STARTS WITH 'kg_seed_')
        RETURN elementId(r) AS id, type(r) AS type, properties(r) AS props
        ORDER BY type(r)
        """
    ).data()
    return {"documents": docs, "entities": entities, "relations": relations}


def backup_db(path: Path, report_dir: Path) -> str | None:
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.DatabaseError:
        pass
    target = report_dir / f"{path.name}.before_{RUN_ID}"
    shutil.copy2(path, target)
    return str(target)


def delete_sqlite_seeds(seed_chunk_ids: list[str], seed_doc_names: list[str]) -> dict[str, Any]:
    with sqlite3.connect(SQLITE_DB) as conn:
        if seed_chunk_ids:
            placeholders = ",".join("?" for _ in seed_chunk_ids)
            deleted_chunks = conn.execute(
                f"DELETE FROM chunks WHERE chunk_id IN ({placeholders})",
                seed_chunk_ids,
            ).rowcount
        else:
            deleted_chunks = 0
        if seed_doc_names:
            placeholders = ",".join("?" for _ in seed_doc_names)
            deleted_docs = conn.execute(
                f"DELETE FROM documents WHERE doc_name IN ({placeholders})",
                seed_doc_names,
            ).rowcount
        else:
            deleted_docs = 0
        conn.commit()
        remaining = {
            "seed_chunks": conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE doc_name LIKE '图谱种子_%' OR chunk_id LIKE 'kg_seed_%'"
            ).fetchone()[0],
            "seed_documents": conn.execute(
                "SELECT COUNT(*) FROM documents WHERE doc_name LIKE '图谱种子_%'"
            ).fetchone()[0],
            "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        }
    return {"deleted_chunks": deleted_chunks, "deleted_documents": deleted_docs, "remaining": remaining}


def refresh_dense_manifest(conn: sqlite3.Connection) -> None:
    with RagStore(str(SQLITE_DB)) as store:
        store.init_tables()
        source = store.fingerprint()
    indexed_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    manifest = {
        "source": source,
        "indexed_count": indexed_count,
        "skipped_count": 0,
        "error_count": 0,
        "cleaned_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    for key, value in manifest.items():
        conn.execute(
            "INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def delete_dense_seeds(seed_chunk_ids: list[str]) -> dict[str, Any]:
    if not DENSE_DB.exists():
        return {"exists": False, "deleted_embeddings": 0, "remaining": {}}
    with sqlite3.connect(DENSE_DB) as conn:
        if seed_chunk_ids:
            placeholders = ",".join("?" for _ in seed_chunk_ids)
            deleted = conn.execute(
                f"DELETE FROM embeddings WHERE chunk_id IN ({placeholders}) OR doc_name LIKE '图谱种子_%'",
                seed_chunk_ids,
            ).rowcount
        else:
            deleted = conn.execute("DELETE FROM embeddings WHERE doc_name LIKE '图谱种子_%'").rowcount
        refresh_dense_manifest(conn)
        conn.commit()
        remaining = {
            "seed_embeddings": conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE doc_name LIKE '图谱种子_%' OR chunk_id LIKE 'kg_seed_%'"
            ).fetchone()[0],
            "embeddings": conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0],
        }
    return {"exists": True, "deleted_embeddings": deleted, "remaining": remaining}


def delete_neo4j_seeds(session) -> dict[str, int]:
    deleted_entities = session.run(
        """
        MATCH (n)
        WHERE NOT n:Document
          AND (
            toString(n.chunk_id) STARTS WITH 'kg_seed_'
            OR any(x IN coalesce(n.source_chunk_ids, []) WHERE toString(x) STARTS WITH 'kg_seed_')
          )
        WITH collect(n) AS nodes, count(n) AS deleted
        FOREACH (n IN nodes | DETACH DELETE n)
        RETURN deleted
        """
    ).single()["deleted"]
    deleted_docs = session.run(
        """
        MATCH (d:Document)
        WHERE d.synthetic = true
           OR d.document_kind = 'synthetic_seed'
           OR toString(d.seed_doc_name) STARTS WITH '图谱种子_'
           OR toString(d.canonical_doc_name) STARTS WITH '图谱种子_'
        WITH collect(d) AS docs, count(d) AS deleted
        FOREACH (d IN docs | DETACH DELETE d)
        RETURN deleted
        """
    ).single()["deleted"]
    remaining_docs = session.run(
        """
        MATCH (d:Document)
        WHERE d.synthetic = true
           OR d.document_kind = 'synthetic_seed'
           OR toString(d.seed_doc_name) STARTS WITH '图谱种子_'
           OR toString(d.canonical_doc_name) STARTS WITH '图谱种子_'
        RETURN count(d) AS c
        """
    ).single()["c"]
    remaining_entities = session.run(
        """
        MATCH (n)
        WHERE NOT n:Document
          AND (
            toString(n.chunk_id) STARTS WITH 'kg_seed_'
            OR any(x IN coalesce(n.source_chunk_ids, []) WHERE toString(x) STARTS WITH 'kg_seed_')
          )
        RETURN count(n) AS c
        """
    ).single()["c"]
    return {
        "deleted_entities": deleted_entities,
        "deleted_documents": deleted_docs,
        "remaining_seed_entities": remaining_entities,
        "remaining_synthetic_documents": remaining_docs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="apply deletions; otherwise write an audit report only")
    args = parser.parse_args()

    report_dir = REPORT_ROOT / RUN_ID
    report_dir.mkdir(parents=True, exist_ok=True)

    sqlite_before = collect_sqlite_seed_rows()
    dense_before = collect_dense_seed_rows()
    driver = connect_neo4j()
    try:
        with driver.session() as session:
            neo4j_before = collect_neo4j_seed_rows(session)
            report: dict[str, Any] = {
                "run_id": RUN_ID,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "confirmed": args.confirm,
                "sqlite_before": sqlite_before,
                "dense_before": dense_before,
                "neo4j_before": neo4j_before,
            }
            write_json(report_dir / "audit_before.json", report)

            if not args.confirm:
                print(json.dumps({"dry_run": True, "report_dir": str(report_dir)}, ensure_ascii=False, indent=2))
                return 0

            backups = {
                "rag_chunks_db": backup_db(SQLITE_DB, report_dir),
                "dense_db": backup_db(DENSE_DB, report_dir),
            }
            seed_chunk_ids = [row["chunk_id"] for row in sqlite_before["chunks"]]
            seed_doc_names = [row["doc_name"] for row in sqlite_before["documents"]]
            actions = {
                "sqlite": delete_sqlite_seeds(seed_chunk_ids, seed_doc_names),
                "dense": delete_dense_seeds(seed_chunk_ids),
                "neo4j": delete_neo4j_seeds(session),
            }
            after = {
                "sqlite": collect_sqlite_seed_rows(),
                "dense": collect_dense_seed_rows(),
                "neo4j": collect_neo4j_seed_rows(session),
            }
            summary = {
                "run_id": RUN_ID,
                "report_dir": str(report_dir),
                "backups": backups,
                "actions": actions,
                "after_counts": {
                    "sqlite_seed_chunks": len(after["sqlite"]["chunks"]),
                    "sqlite_seed_documents": len(after["sqlite"]["documents"]),
                    "dense_seed_embeddings": len(after["dense"]["rows"]),
                    "neo4j_synthetic_documents": len(after["neo4j"]["documents"]),
                    "neo4j_seed_entities": len(after["neo4j"]["entities"]),
                    "neo4j_seed_relations": len(after["neo4j"]["relations"]),
                },
            }
            write_json(report_dir / "summary_after.json", summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
