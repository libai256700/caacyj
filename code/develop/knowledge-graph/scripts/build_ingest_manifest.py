#!/usr/bin/env python3
"""Build a unified ingest manifest for CSV, document, and graph coverage.

SQLite remains the canonical chunk text store. BM25, dense vectors, and Neo4j
are recorded as derived coverage layers so drift can be detected from one file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from neo4j import GraphDatabase, Query
except Exception:  # pragma: no cover - optional runtime dependency
    GraphDatabase = None
    Query = None


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_DIR / "rag_chunks.db"
DEFAULT_OUTPUT = PROJECT_DIR / "ingest_manifest.json"
DEFAULT_CSV_DIR = Path("/Users/xiaoji/Downloads/同步空间/openclaw/小技结构化数据")
DEFAULT_DOC_DIRS = (PROJECT_DIR / "rag_docs", PROJECT_DIR / "feishu_raw")
DEFAULT_BM25_MANIFEST = PROJECT_DIR / "rag_index" / "bm25" / "manifest.json"
DEFAULT_DENSE_PATH = PROJECT_DIR / "rag_index" / "dense_bge_m3.sqlite"
DEFAULT_NEO4J_PASS_FILE = PROJECT_DIR / "neo4j" / ".neo4j_pass"
DEFAULT_SOURCE_DOC_ALIASES = PROJECT_DIR / "rag_store" / "source_doc_aliases.json"
DEFAULT_CANONICAL_DIR = Path("/Users/xiaoji/Documents/知识库分析/data/canonical")

sys.path.insert(0, str(PROJECT_DIR))
from rag_store.semantic_schema import (  # noqa: E402
    CANONICAL_TABLES,
    SCHEMA_VERSION as SEMANTIC_SCHEMA_VERSION,
    SYNC_ELIGIBLE_DOMAINS,
    canonical_table_report,
    domain_for_doc_name,
    semantic_schema_manifest,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_version(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        "sha256": file_sha256(path),
    }


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": str(exc)}


def sqlite_report(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        chunks = conn.execute(
            """
            SELECT COUNT(*) AS chunk_count,
                   COUNT(DISTINCT doc_name) AS doc_count,
                   COALESCE(SUM(LENGTH(text)), 0) AS text_bytes,
                   COALESCE(MAX(created_at), '') AS max_created_at
            FROM chunks
            """
        ).fetchone()
        rows = conn.execute(
            """
            SELECT chunk_id, doc_name, chunk_index, LENGTH(text) AS text_len
            FROM chunks
            ORDER BY chunk_id
            """
        ).fetchall()
        docs = conn.execute(
            """
            SELECT d.doc_name,
                   d.doc_path,
                   d.chunk_count AS recorded_chunk_count,
                   d.updated_at,
                   COUNT(c.chunk_id) AS actual_chunk_count,
                   COALESCE(SUM(LENGTH(c.text)), 0) AS text_bytes,
                   MIN(c.chunk_index) AS min_chunk_index,
                   MAX(c.chunk_index) AS max_chunk_index
            FROM documents d
            LEFT JOIN chunks c ON c.doc_name = d.doc_name
            GROUP BY d.doc_name
            ORDER BY d.doc_name
            """
        ).fetchall()
        h = hashlib.sha256()
        for row in rows:
            h.update(
                f"{row['chunk_id']}|{row['doc_name']}|{row['chunk_index']}|{row['text_len']}\n".encode("utf-8")
            )
        fingerprint = {
            "chunk_count": int(chunks["chunk_count"]),
            "doc_count": int(chunks["doc_count"]),
            "text_bytes": int(chunks["text_bytes"]),
            "max_created_at": chunks["max_created_at"],
            "schema": "chunks-v1",
            "fingerprint": h.hexdigest(),
        }
        return {
            "db_path": str(db_path),
            "version": file_version(db_path) if db_path.exists() else {},
            "fingerprint": fingerprint,
            "documents": [dict(row) for row in docs],
        }
    finally:
        conn.close()


def count_csv_rows(path: Path) -> tuple[int, list[str], str | None]:
    encodings = ("utf-8-sig", "utf-8", "gb18030")
    last_error = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.reader(f)
                header = next(reader, [])
                rows = sum(1 for row in reader if any(cell.strip() for cell in row))
            return rows, header, encoding
        except Exception as exc:
            last_error = str(exc)
    return 0, [], f"unreadable: {last_error}"


def csv_sources(csv_dir: Path) -> dict[str, Any]:
    if not csv_dir.exists():
        return {"root": str(csv_dir), "exists": False, "files": [], "totals": {"files": 0, "rows": 0}}
    files = []
    for path in sorted(csv_dir.glob("*.csv")):
        rows, header, encoding = count_csv_rows(path)
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "format": "csv",
                "row_count": rows,
                "columns": header,
                "column_count": len(header),
                "encoding": encoding,
                "version": file_version(path),
            }
        )
    dictionary = csv_dir / "_数据字典.json"
    return {
        "root": str(csv_dir),
        "exists": True,
        "data_dictionary": {
            "path": str(dictionary),
            "exists": dictionary.exists(),
            "version": file_version(dictionary) if dictionary.exists() else {},
        },
        "files": files,
        "totals": {
            "files": len(files),
            "rows": sum(int(item["row_count"]) for item in files),
        },
    }


def doc_sources(doc_dirs: list[Path], sqlite_docs: list[dict[str, Any]]) -> dict[str, Any]:
    by_doc_name = {doc["doc_name"]: doc for doc in sqlite_docs}
    by_path = {
        str(Path(doc["doc_path"]).resolve()): doc
        for doc in sqlite_docs
        if doc.get("doc_path")
    }
    files = []
    suffixes = {".txt", ".md", ".docx", ".pdf", ".csv"}
    for root in doc_dirs:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes):
            resolved = str(path.resolve())
            sqlite_doc = by_path.get(resolved) or by_doc_name.get(path.name)
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "format": path.suffix.lower().lstrip(".") or "unknown",
                    "source_root": str(root),
                    "version": file_version(path),
                    "chunk_coverage": {
                        "in_sqlite": sqlite_doc is not None,
                        "doc_name": sqlite_doc.get("doc_name") if sqlite_doc else None,
                        "chunk_count": int(sqlite_doc.get("actual_chunk_count") or 0) if sqlite_doc else 0,
                        "recorded_chunk_count": int(sqlite_doc.get("recorded_chunk_count") or 0) if sqlite_doc else 0,
                        "updated_at": sqlite_doc.get("updated_at") if sqlite_doc else None,
                    },
                }
            )
    covered = sum(1 for item in files if item["chunk_coverage"]["in_sqlite"])
    return {
        "roots": [str(path) for path in doc_dirs],
        "files": files,
        "totals": {
            "files": len(files),
            "sqlite_covered_files": covered,
            "sqlite_uncovered_files": len(files) - covered,
            "sqlite_covered_chunks": sum(int(item["chunk_coverage"]["chunk_count"]) for item in files),
        },
    }


def dense_index_report(path: Path) -> dict[str, Any]:
    report = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return report
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM embeddings").fetchone()["c"]
        dims = conn.execute("SELECT dim, model, COUNT(*) AS c FROM embeddings GROUP BY dim, model").fetchall()
        manifest_rows = conn.execute("SELECT key, value FROM manifest").fetchall()
        manifest = {row["key"]: json.loads(row["value"]) for row in manifest_rows}
        report.update(
            {
                "version": file_version(path),
                "indexed_count": int(count),
                "dimensions": [dict(row) for row in dims],
                "manifest": manifest,
            }
        )
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        conn.close()
    return report


def derived_indexes(db_fingerprint: dict[str, Any], bm25_manifest: Path, dense_path: Path) -> dict[str, Any]:
    bm25 = read_json(bm25_manifest)
    dense = dense_index_report(dense_path)
    expected_chunks = int(db_fingerprint.get("chunk_count") or 0)
    return {
        "bm25": {
            "manifest_path": str(bm25_manifest),
            "exists": bm25_manifest.exists(),
            "manifest": bm25,
            "fresh_against_sqlite": bm25.get("source") == db_fingerprint
            and int(bm25.get("indexed_docs") or 0) == expected_chunks,
        },
        "dense": {
            **dense,
            "fresh_against_sqlite": dense.get("manifest", {}).get("source") == db_fingerprint
            and int(dense.get("indexed_count") or 0) == expected_chunks,
        },
    }


def neo4j_password(pass_file: Path) -> str:
    if pass_file.exists():
        return pass_file.read_text(encoding="utf-8").strip()
    return os.environ.get("NEO4J_PASS", "")


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


def build_source_doc_resolver(sqlite_doc_names: set[str], alias_path: Path) -> dict[str, str]:
    resolver: dict[str, str] = {}
    for doc_name in sqlite_doc_names:
        candidates = {doc_name, normalize_doc_name(doc_name)}
        if doc_name.endswith(".txt"):
            candidates.add(doc_name[:-4])
        if doc_name.endswith(".md"):
            candidates.add(doc_name[:-3])
        for candidate in candidates:
            if candidate:
                resolver.setdefault(candidate, doc_name)

    aliases = read_json(alias_path).get("aliases", {})
    if isinstance(aliases, dict):
        for source_doc, targets in aliases.items():
            if isinstance(targets, str):
                targets = [targets]
            target = next((item for item in targets if item in sqlite_doc_names), None)
            if target:
                resolver[source_doc] = target
                resolver.setdefault(normalize_doc_name(source_doc), target)
    return resolver


def run_neo4j(session: Any, statement: str, **params: Any) -> list[dict[str, Any]]:
    query = Query(statement, timeout=float(os.environ.get("NEO4J_TIMEOUT", "2"))) if Query else statement
    return [dict(row) for row in session.run(query, **params)]


def graph_coverage(sqlite_doc_names: set[str], pass_file: Path, alias_path: Path) -> dict[str, Any]:
    if GraphDatabase is None:
        return {"available": False, "error": "neo4j python package is not importable"}
    password = neo4j_password(pass_file)
    if not password:
        return {"available": False, "error": "Neo4j password is not configured"}

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=2)
    try:
        with driver.session() as session:
            labels = run_neo4j(
                session,
                """
                MATCH (n)
                UNWIND labels(n) AS label
                RETURN label, count(*) AS count
                ORDER BY count DESC, label
                """,
            )
            rel_types = run_neo4j(
                session,
                """
                MATCH ()-[r]->()
                RETURN type(r) AS type, count(*) AS count
                ORDER BY count DESC, type
                """,
            )
            totals = run_neo4j(
                session,
                """
                MATCH (n)
                WITH count(n) AS nodes
                MATCH ()-[r]->()
                RETURN nodes, count(r) AS relationships
                """,
            )[0]
            documents = run_neo4j(
                session,
                """
                MATCH (d:Document)
                RETURN count(d) AS count,
                       count(d.canonical_doc_name) AS canonical_doc_names,
                       count(d.path) AS paths,
                       count(d.rag_resolved) AS rag_resolved_flags
                """,
            )[0]
            source_docs = run_neo4j(
                session,
                """
                MATCH (n)
                WHERE n.source_doc IS NOT NULL
                RETURN n.source_doc AS source_doc, count(n) AS entity_count
                ORDER BY entity_count DESC, source_doc
                LIMIT 5000
                """,
            )
            chunk_linked = run_neo4j(
                session,
                """
                MATCH (n)
                WHERE n.source_chunk_ids IS NOT NULL
                RETURN count(n) AS nodes_with_source_chunk_ids
                """,
            )[0]
            semantic_props = run_neo4j(
                session,
                """
                MATCH (n)
                WHERE NOT n:Document
                RETURN count(n) AS total_entities,
                       count(n.entity_id) AS with_entity_id,
                       count(n.domain) AS with_domain,
                       count(n.canonical_name) AS with_canonical_name,
                       count(n.source_doc) AS with_source_doc,
                       count(n.source_chunk_ids) AS with_source_chunk_ids,
                       count(CASE WHEN n.schema_version = $schema_version THEN 1 END) AS with_schema_version
                """,
                schema_version=SEMANTIC_SCHEMA_VERSION,
            )[0]
            document_semantic_props = run_neo4j(
                session,
                """
                MATCH (d:Document)
                RETURN count(d) AS total_documents,
                       count(d.domain) AS with_domain,
                       count(d.canonical_name) AS with_canonical_name,
                       count(d.canonical_doc_name) AS with_canonical_doc_name,
                       count(d.rag_resolved) AS with_rag_resolved,
                       count(CASE WHEN d.schema_version = $schema_version THEN 1 END) AS with_schema_version
                """,
                schema_version=SEMANTIC_SCHEMA_VERSION,
            )[0]
            domain_counts = run_neo4j(
                session,
                """
                MATCH (n)
                RETURN coalesce(n.domain, "unknown") AS domain, count(n) AS count
                ORDER BY count DESC, domain
                """,
            )
            domain_evidence = run_neo4j(
                session,
                """
                MATCH (n)
                WHERE NOT n:Document
                RETURN coalesce(n.domain, "unknown") AS domain,
                       count(n) AS total_entities,
                       count(n.source_doc) AS with_source_doc,
                       count(n.source_chunk_ids) AS with_source_chunk_ids,
                       count(CASE WHEN n.schema_version = $schema_version THEN 1 END) AS with_schema_version
                ORDER BY domain
                """,
                schema_version=SEMANTIC_SCHEMA_VERSION,
            )
            domain_relationship_types = run_neo4j(
                session,
                """
                MATCH (a)-[r]->(b)
                RETURN coalesce(a.domain, b.domain, "unknown") AS domain,
                       type(r) AS type,
                       count(r) AS count
                ORDER BY domain, type
                """,
            )
            domain_source_docs = run_neo4j(
                session,
                """
                MATCH (n)
                WHERE NOT n:Document AND n.source_doc IS NOT NULL
                RETURN coalesce(n.domain, "unknown") AS domain,
                       n.source_doc AS source_doc,
                       count(n) AS entity_count,
                       count(n.source_chunk_ids) AS with_source_chunk_ids
                ORDER BY domain, entity_count DESC, source_doc
                LIMIT 5000
                """,
            )
            deprecated_rels = run_neo4j(
                session,
                """
                MATCH ()-[r]->()
                WHERE type(r) IN ["HAS_SALARY"]
                RETURN type(r) AS type, count(r) AS count
                ORDER BY count DESC
                """,
            )
    except Exception as exc:
        return {"available": False, "uri": uri, "error": str(exc)}
    finally:
        driver.close()

    source_doc_counts = {row["source_doc"]: int(row["entity_count"]) for row in source_docs if row.get("source_doc")}
    resolver = build_source_doc_resolver(sqlite_doc_names, alias_path)
    resolved_map = {
        name: resolver[name] for name in source_doc_counts if name in resolver
    }
    unresolved = sorted(name for name in source_doc_counts if name not in resolved_map)
    canonical_entity_counts: defaultdict[str, int] = defaultdict(int)
    for source_doc, canonical_doc in resolved_map.items():
        canonical_entity_counts[canonical_doc] += source_doc_counts[source_doc]
    relationship_by_domain: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {"relationship_count": 0, "types": []}
    )
    for row in domain_relationship_types:
        domain = row.get("domain") or "unknown"
        count = int(row.get("count") or 0)
        relationship_by_domain[domain]["relationship_count"] += count
        relationship_by_domain[domain]["types"].append({"type": row.get("type"), "count": count})
    source_docs_by_domain: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in domain_source_docs:
        source_doc = row.get("source_doc") or ""
        source_docs_by_domain[row.get("domain") or "unknown"].append(
            {
                "source_doc": source_doc,
                "sqlite_doc_name": resolved_map.get(source_doc),
                "resolved": source_doc in resolved_map,
                "entity_count": int(row.get("entity_count") or 0),
                "with_source_chunk_ids": int(row.get("with_source_chunk_ids") or 0),
            }
        )
    return {
        "available": True,
        "uri": uri,
        "totals": {key: int(value) for key, value in totals.items()},
        "labels": [{row["label"]: int(row["count"])} for row in labels],
        "relationship_types": [{row["type"]: int(row["count"])} for row in rel_types],
        "documents": {key: int(value) for key, value in documents.items()},
        "source_doc_coverage": {
            "source_docs": len(source_doc_counts),
            "sqlite_resolved_source_docs": len(resolved_map),
            "sqlite_unresolved_source_docs": len(unresolved),
            "resolved": [
                {"source_doc": source_doc, "sqlite_doc_name": resolved_map[source_doc]}
                for source_doc in sorted(resolved_map)
            ],
            "unresolved": unresolved[:200],
            "top_entity_sources": [
                {"source_doc": name, "entity_count": count}
                for name, count in sorted(source_doc_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
            ],
            "top_canonical_sqlite_docs": [
                {"doc_name": name, "entity_count": count}
                for name, count in sorted(canonical_entity_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
            ],
        },
        "chunk_coverage": {key: int(value) for key, value in chunk_linked.items()},
        "semantic_props": {key: int(value) for key, value in semantic_props.items()},
        "document_semantic_props": {key: int(value) for key, value in document_semantic_props.items()},
        "domain_counts": [
            {"domain": row["domain"], "count": int(row["count"])} for row in domain_counts
        ],
        "domain_evidence": [
            {
                "domain": row["domain"],
                "total_entities": int(row["total_entities"]),
                "with_source_doc": int(row["with_source_doc"]),
                "with_source_chunk_ids": int(row["with_source_chunk_ids"]),
                "with_schema_version": int(row["with_schema_version"]),
                "source_doc_coverage_rate": round(int(row["with_source_doc"]) / max(int(row["total_entities"]), 1), 4),
                "source_chunk_id_coverage_rate": round(
                    int(row["with_source_chunk_ids"]) / max(int(row["total_entities"]), 1), 4
                ),
                "schema_version_coverage_rate": round(
                    int(row["with_schema_version"]) / max(int(row["total_entities"]), 1), 4
                ),
            }
            for row in domain_evidence
        ],
        "domain_relationships": [
            {"domain": domain, **data} for domain, data in sorted(relationship_by_domain.items())
        ],
        "domain_source_docs": [
            {"domain": domain, "source_docs": rows} for domain, rows in sorted(source_docs_by_domain.items())
        ],
        "deprecated_relationships": [
            {"type": row["type"], "count": int(row["count"])} for row in deprecated_rels
        ],
    }


def build_domain_coverage(
    canonical: dict[str, Any],
    csv_report: dict[str, Any],
    doc_report: dict[str, Any],
    graph_report: dict[str, Any],
) -> dict[str, Any]:
    coverage: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"sqlite_documents": 0, "sqlite_chunks": 0, "document_files": 0, "csv_files": 0, "graph_nodes": 0}
    )
    for doc in canonical.get("documents", []):
        domain = domain_for_doc_name(str(doc.get("doc_name") or ""))
        coverage[domain]["sqlite_documents"] += 1
        coverage[domain]["sqlite_chunks"] += int(doc.get("actual_chunk_count") or 0)
    for item in doc_report.get("files", []):
        domain = domain_for_doc_name(str(item.get("name") or ""))
        coverage[domain]["document_files"] += 1
    for item in csv_report.get("files", []):
        domain = domain_for_doc_name(str(item.get("name") or ""))
        coverage[domain]["csv_files"] += 1
    for row in graph_report.get("domain_counts", []):
        domain = row.get("domain") or "unknown"
        coverage[domain]["graph_nodes"] += int(row.get("count") or 0)
    return dict(sorted(coverage.items()))


def build_graph_quality(graph_report: dict[str, Any]) -> dict[str, Any]:
    deprecated = graph_report.get("deprecated_relationships", [])
    semantic = graph_report.get("semantic_props", {})
    total_entities = int(semantic.get("total_entities") or 0)
    with_entity_id = int(semantic.get("with_entity_id") or 0)
    with_domain = int(semantic.get("with_domain") or 0)
    with_schema = int(semantic.get("with_schema_version") or 0)
    return {
        "semantic_schema_version": SEMANTIC_SCHEMA_VERSION,
        "deprecated_relationship_count": sum(int(item.get("count") or 0) for item in deprecated),
        "deprecated_relationships": deprecated,
        "entity_id_coverage_rate": round(with_entity_id / total_entities, 4) if total_entities else 0.0,
        "domain_coverage_rate": round(with_domain / total_entities, 4) if total_entities else 0.0,
        "schema_version_coverage_rate": round(with_schema / total_entities, 4) if total_entities else 0.0,
        "source_doc_unresolved": int(
            graph_report.get("source_doc_coverage", {}).get("sqlite_unresolved_source_docs") or 0
        ),
    }


def build_evidence_coverage(graph_report: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    semantic = graph_report.get("semantic_props", {})
    docs = graph_report.get("documents", {})
    total_entities = int(semantic.get("total_entities") or 0)
    with_source_doc = int(semantic.get("with_source_doc") or 0)
    with_source_chunk_ids = int(semantic.get("with_source_chunk_ids") or 0)
    total_docs = int(docs.get("count") or 0)
    return {
        "canonical_text_owner": "sqlite:rag_chunks.db",
        "chunk_id_contract": canonical.get("fingerprint", {}),
        "entity_source_doc_coverage_rate": round(with_source_doc / total_entities, 4) if total_entities else 0.0,
        "entity_source_chunk_id_coverage_rate": round(with_source_chunk_ids / total_entities, 4) if total_entities else 0.0,
        "document_rag_resolved_coverage_rate": round(
            int(docs.get("rag_resolved_flags") or 0) / total_docs, 4
        )
        if total_docs
        else 0.0,
        "nodes_with_source_chunk_ids": int(graph_report.get("chunk_coverage", {}).get("nodes_with_source_chunk_ids") or 0),
    }


def build_sync_sets(domain_coverage: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    documents_by_domain: defaultdict[str, list[str]] = defaultdict(list)
    chunk_counts_by_domain: defaultdict[str, int] = defaultdict(int)
    for doc in canonical.get("documents", []):
        domain = domain_for_doc_name(str(doc.get("doc_name") or ""))
        documents_by_domain[domain].append(doc["doc_name"])
        chunk_counts_by_domain[domain] += int(doc.get("actual_chunk_count") or 0)
    return {
        domain: {
            "eligible": domain in SYNC_ELIGIBLE_DOMAINS,
            "sqlite_documents": sorted(documents_by_domain.get(domain, [])),
            "sqlite_chunks": chunk_counts_by_domain.get(domain, 0),
            "rebuild_remote_layers": ["bm25", "dense_bge_m3", "neo4j"] if domain in SYNC_ELIGIBLE_DOMAINS else [],
        }
        for domain in sorted(domain_coverage)
    }


def build_domain_asset_map(
    canonical: dict[str, Any],
    csv_report: dict[str, Any],
    doc_report: dict[str, Any],
    graph_report: dict[str, Any],
    canonical_tables: dict[str, Any],
    domain_coverage: dict[str, Any],
) -> dict[str, Any]:
    evidence_by_domain = {row["domain"]: row for row in graph_report.get("domain_evidence", [])}
    relationships_by_domain = {row["domain"]: row for row in graph_report.get("domain_relationships", [])}
    source_docs_by_domain = {row["domain"]: row["source_docs"] for row in graph_report.get("domain_source_docs", [])}
    canonical_table_rows = canonical_tables.get("tables", [])

    docs_by_domain: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in canonical.get("documents", []):
        docs_by_domain[domain_for_doc_name(str(doc.get("doc_name") or ""))].append(
            {
                "doc_name": doc.get("doc_name"),
                "doc_path": doc.get("doc_path"),
                "chunk_count": int(doc.get("actual_chunk_count") or 0),
                "text_bytes": int(doc.get("text_bytes") or 0),
                "updated_at": doc.get("updated_at"),
            }
        )

    source_files_by_domain: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in doc_report.get("files", []):
        coverage = item.get("chunk_coverage", {})
        domain = domain_for_doc_name(str(coverage.get("doc_name") or item.get("name") or ""))
        source_files_by_domain[domain].append(
            {
                "name": item.get("name"),
                "path": item.get("path"),
                "format": item.get("format"),
                "in_sqlite": bool(coverage.get("in_sqlite")),
                "sqlite_doc_name": coverage.get("doc_name"),
                "chunk_count": int(coverage.get("chunk_count") or 0),
            }
        )
    for item in csv_report.get("files", []):
        domain = domain_for_doc_name(str(item.get("name") or ""))
        source_files_by_domain[domain].append(
            {
                "name": item.get("name"),
                "path": item.get("path"),
                "format": "csv",
                "row_count": int(item.get("row_count") or 0),
            }
        )

    table_names_by_domain: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    domain_specific_tables = {domain: table for table, domain in CANONICAL_TABLES.items()}
    for table in canonical_table_rows:
        table_name = table.get("table")
        table_domain = table.get("domain")
        if table_domain in domain_coverage:
            table_names_by_domain[table_domain].append(table)
        if table_name in {"documents", "document_chunks"}:
            for domain, docs in docs_by_domain.items():
                if docs:
                    table_names_by_domain[domain].append(table)
    for domain, table_name in domain_specific_tables.items():
        if domain in domain_coverage:
            table = next((row for row in canonical_table_rows if row.get("table") == table_name), None)
            if table and table not in table_names_by_domain[domain]:
                table_names_by_domain[domain].append(table)

    out: dict[str, Any] = {}
    for domain in sorted(domain_coverage):
        evidence = evidence_by_domain.get(domain, {})
        rels = relationships_by_domain.get(domain, {"relationship_count": 0, "types": []})
        domain_tables = table_names_by_domain.get(domain, [])
        source_docs = mark_canonical_source_docs(source_docs_by_domain.get(domain, []), domain_tables)
        out[domain] = {
            "sync_eligible": domain in SYNC_ELIGIBLE_DOMAINS,
            "source_files": sorted(source_files_by_domain.get(domain, []), key=lambda item: str(item.get("name"))),
            "sqlite": {
                "documents": sorted(docs_by_domain.get(domain, []), key=lambda item: str(item.get("doc_name"))),
                "document_count": len(docs_by_domain.get(domain, [])),
                "chunk_count": sum(int(item.get("chunk_count") or 0) for item in docs_by_domain.get(domain, [])),
            },
            "neo4j": {
                "entity_count": int(evidence.get("total_entities") or 0),
                "relationship_count": int(rels.get("relationship_count") or 0),
                "relationship_types": rels.get("types", []),
                "source_doc_coverage_rate": evidence.get("source_doc_coverage_rate", 0.0),
                "source_chunk_id_coverage_rate": evidence.get("source_chunk_id_coverage_rate", 0.0),
                "schema_version_coverage_rate": evidence.get("schema_version_coverage_rate", 0.0),
                "unresolved_source_docs": [item for item in source_docs if not item.get("resolved")],
                "source_docs": source_docs,
            },
            "canonical_tables": [
                {
                    "table": table.get("table"),
                    "domain": table.get("domain"),
                    "path": table.get("path"),
                    "exists": table.get("exists"),
                    "row_count": table.get("row_count", 0),
                }
                for table in domain_tables
            ],
            "cross_machine_sync": {
                "allowed_domain": domain in SYNC_ELIGIBLE_DOMAINS,
                "remote_rebuild_layers": ["bm25", "dense_bge_m3", "neo4j"] if domain in SYNC_ELIGIBLE_DOMAINS else [],
                "authority": "local sqlite chunks plus domain manifest",
            },
        }
    return out


def canonical_source_doc_map(tables: list[dict[str, Any]]) -> dict[str, str]:
    """Map canonical CSV provenance names to table names.

    Some semantic nodes are derived from canonical CSV rows. Their final answer
    evidence must still resolve through source_chunk_ids, but the source_doc
    itself should be allowed to identify the canonical table instead of a
    SQLite text document.
    """
    names: dict[str, str] = {}
    for table in tables:
        if not table.get("exists"):
            continue
        table_name = str(table.get("table") or "").strip()
        if not table_name:
            continue
        names.setdefault(table_name, table_name)
        names.setdefault(f"{table_name}.csv", table_name)
        path_name = Path(str(table.get("path") or "")).name
        if path_name:
            names.setdefault(path_name, table_name)
    return names


def mark_canonical_source_docs(
    source_docs: list[dict[str, Any]],
    canonical_tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    canonical_sources = canonical_source_doc_map(canonical_tables)
    marked = []
    for item in source_docs:
        source_doc = str(item.get("source_doc") or "")
        out = dict(item)
        if not out.get("resolved") and source_doc in canonical_sources:
            out["resolved"] = True
            out["source_type"] = "canonical_table"
            out["canonical_table"] = canonical_sources[source_doc]
        elif out.get("resolved"):
            out["source_type"] = "sqlite_document"
        marked.append(out)
    return marked


def coverage_summary(
    canonical: dict[str, Any],
    csv_report: dict[str, Any],
    doc_report: dict[str, Any],
    graph_report: dict[str, Any],
    indexes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "csv_files": csv_report["totals"]["files"],
        "csv_rows": csv_report["totals"]["rows"],
        "document_files": doc_report["totals"]["files"],
        "document_files_with_chunks": doc_report["totals"]["sqlite_covered_files"],
        "sqlite_documents": canonical["fingerprint"]["doc_count"],
        "sqlite_chunks": canonical["fingerprint"]["chunk_count"],
        "graph_available": bool(graph_report.get("available")),
        "graph_nodes": int(graph_report.get("totals", {}).get("nodes", 0)),
        "graph_relationships": int(graph_report.get("totals", {}).get("relationships", 0)),
        "bm25_fresh": bool(indexes["bm25"]["fresh_against_sqlite"]),
        "dense_fresh": bool(indexes["dense"]["fresh_against_sqlite"]),
    }


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db_path).expanduser()
    csv_dir = Path(args.csv_dir).expanduser()
    doc_dirs = [Path(item).expanduser() for item in args.doc_dir]
    canonical = sqlite_report(db_path)
    csv_report = csv_sources(csv_dir)
    doc_report = doc_sources(doc_dirs, canonical["documents"])
    indexes = derived_indexes(canonical["fingerprint"], Path(args.bm25_manifest), Path(args.dense_path))
    sqlite_doc_names = {doc["doc_name"] for doc in canonical["documents"]}
    graph_report = graph_coverage(sqlite_doc_names, Path(args.neo4j_pass_file), Path(args.source_doc_aliases))
    canonical_tables = canonical_table_report(Path(args.canonical_dir).expanduser())
    domain_report = build_domain_coverage(canonical, csv_report, doc_report, graph_report)
    manifest = {
        "schema_version": "ingest-manifest-v2",
        "generated_at": utc_now(),
        "project": {
            "name": "knowledge-graph",
            "root": str(PROJECT_DIR),
        },
        "source_contract": {
            "canonical_chunk_store": "sqlite:rag_chunks.db",
            "derived_layers": ["bm25", "dense_bge_m3", "neo4j"],
            "join_key": "chunk_id",
        },
        "canonical_store": canonical,
        "csv_sources": csv_report,
        "document_sources": doc_report,
        "graph_coverage": graph_report,
        "derived_indexes": indexes,
        "semantic_schema": semantic_schema_manifest(),
        "canonical_tables": canonical_tables,
        "domain_coverage": domain_report,
        "domain_asset_map": build_domain_asset_map(
            canonical,
            csv_report,
            doc_report,
            graph_report,
            canonical_tables,
            domain_report,
        ),
        "graph_quality": build_graph_quality(graph_report),
        "evidence_coverage": build_evidence_coverage(graph_report, canonical),
        "sync_sets": build_sync_sets(domain_report, canonical),
    }
    manifest["coverage_summary"] = coverage_summary(canonical, csv_report, doc_report, graph_report, indexes)
    return manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--csv-dir", default=str(DEFAULT_CSV_DIR))
    parser.add_argument("--doc-dir", action="append", default=[str(path) for path in DEFAULT_DOC_DIRS])
    parser.add_argument("--bm25-manifest", default=str(DEFAULT_BM25_MANIFEST))
    parser.add_argument("--dense-path", default=str(DEFAULT_DENSE_PATH))
    parser.add_argument("--neo4j-pass-file", default=str(DEFAULT_NEO4J_PASS_FILE))
    parser.add_argument("--source-doc-aliases", default=str(DEFAULT_SOURCE_DOC_ALIASES))
    parser.add_argument("--canonical-dir", default=str(DEFAULT_CANONICAL_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--stdout", action="store_true", help="print manifest instead of writing --output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    manifest = build_manifest(args)
    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.stdout:
        print(text)
    else:
        output = Path(args.output).expanduser()
        output.write_text(text + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), "coverage_summary": manifest["coverage_summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
