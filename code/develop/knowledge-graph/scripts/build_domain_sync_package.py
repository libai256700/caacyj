#!/usr/bin/env python3
"""Build local domain sync package skeletons for remote derived-layer rebuilds."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Query

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from rag_store.semantic_schema import SCHEMA_VERSION, SYNC_ELIGIBLE_DOMAINS, relationship_missing_evidence_reason

DEFAULT_MANIFEST = BASE_DIR / "ingest_manifest.json"
DEFAULT_OUTPUT_DIR = BASE_DIR / "sync_packages"
DEFAULT_NEO4J_PASS_FILE = BASE_DIR / "neo4j" / ".neo4j_pass"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def load_chunks(doc_names: set[str]) -> list[dict[str, Any]]:
    with sqlite3.connect(BASE_DIR / "rag_chunks.db") as conn:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in doc_names)
        rows = conn.execute(
            f"""
            SELECT chunk_id, doc_name, chunk_index, text, created_at
            FROM chunks
            WHERE doc_name IN ({placeholders})
            ORDER BY doc_name, chunk_index
            """,
            sorted(doc_names),
        ).fetchall()
    return [dict(row) for row in rows]


def fingerprint_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
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


def write_chunks_jsonl(path: Path, chunks: list[dict[str, Any]]) -> None:
    write_jsonl(path, chunks)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def chunk_fingerprint(domain: str, row: dict[str, Any]) -> dict[str, Any]:
    text = row.get("text") or ""
    payload = {
        "domain": domain,
        "doc_name": row.get("doc_name"),
        "chunk_id": row.get("chunk_id"),
        "chunk_index": int(row.get("chunk_index") or 0),
        "text_hash": text_hash(text),
        "text_bytes": len(text.encode("utf-8")),
    }
    fp_source = "|".join(str(payload[key]) for key in ("domain", "doc_name", "chunk_id", "chunk_index", "text_hash"))
    payload["fingerprint"] = hashlib.sha256(fp_source.encode("utf-8")).hexdigest()
    return payload


def fingerprint_maps(domain: str, chunks: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    chunk_map = {row["chunk_id"]: chunk_fingerprint(domain, row) for row in chunks}
    doc_groups: dict[str, list[dict[str, Any]]] = {}
    for item in chunk_map.values():
        doc_groups.setdefault(str(item["doc_name"]), []).append(item)

    doc_map = {}
    for doc_name, items in doc_groups.items():
        h = hashlib.sha256()
        text_bytes = 0
        for item in sorted(items, key=lambda value: (int(value["chunk_index"]), str(value["chunk_id"]))):
            text_bytes += int(item["text_bytes"])
            h.update(
                f"{domain}|{doc_name}|{item['chunk_id']}|{item['chunk_index']}|{item['fingerprint']}\n".encode(
                    "utf-8"
                )
            )
        doc_map[doc_name] = {
            "domain": domain,
            "doc_name": doc_name,
            "chunk_count": len(items),
            "text_bytes": text_bytes,
            "fingerprint": h.hexdigest(),
        }
    return chunk_map, doc_map


def load_previous_chunks(package_dir: Path) -> list[dict[str, Any]]:
    return read_jsonl(package_dir / "chunks.jsonl")


def build_delta(
    domain: str,
    previous_chunks: list[dict[str, Any]],
    current_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_by_id = {row["chunk_id"]: row for row in previous_chunks}
    current_by_id = {row["chunk_id"]: row for row in current_chunks}
    previous_chunk_fp, previous_doc_fp = fingerprint_maps(domain, previous_chunks)
    current_chunk_fp, current_doc_fp = fingerprint_maps(domain, current_chunks)

    changed_chunks = []
    for chunk_id, row in current_by_id.items():
        current_fp = current_chunk_fp[chunk_id]
        previous_fp = previous_chunk_fp.get(chunk_id)
        if previous_fp == current_fp:
            continue
        changed_chunks.append(
            {
                "change_type": "added" if previous_fp is None else "modified",
                "domain": domain,
                "chunk_id": chunk_id,
                "doc_name": row.get("doc_name"),
                "chunk_index": int(row.get("chunk_index") or 0),
                "fingerprint": current_fp,
                "previous_fingerprint": previous_fp,
                "chunk": row,
            }
        )

    deleted_chunks = []
    tombstoned_at = utc_now()
    for chunk_id, row in previous_by_id.items():
        if chunk_id in current_by_id:
            continue
        previous_fp = previous_chunk_fp[chunk_id]
        deleted_chunks.append(
            {
                "change_type": "deleted",
                "domain": domain,
                "chunk_id": chunk_id,
                "doc_name": row.get("doc_name"),
                "chunk_index": int(row.get("chunk_index") or 0),
                "fingerprint": previous_fp,
                "tombstoned_at": tombstoned_at,
                "reason": "missing_from_current_domain_snapshot",
            }
        )

    doc_changes = []
    for doc_name, current_fp in current_doc_fp.items():
        previous_fp = previous_doc_fp.get(doc_name)
        if previous_fp == current_fp:
            continue
        doc_changes.append(
            {
                "change_type": "added" if previous_fp is None else "modified",
                "domain": domain,
                "doc_name": doc_name,
                "fingerprint": current_fp,
                "previous_fingerprint": previous_fp,
            }
        )
    for doc_name, previous_fp in previous_doc_fp.items():
        if doc_name not in current_doc_fp:
            doc_changes.append(
                {
                    "change_type": "deleted",
                    "domain": domain,
                    "doc_name": doc_name,
                    "fingerprint": previous_fp,
                    "tombstoned_at": tombstoned_at,
                    "reason": "missing_from_current_domain_snapshot",
                }
            )

    return {
        "schema": "domain-sync-delta-v1",
        "has_previous_snapshot": bool(previous_chunks),
        "changed_chunks": changed_chunks,
        "deleted_chunks": deleted_chunks,
        "tombstones": deleted_chunks,
        "chunk_fingerprints": current_chunk_fp,
        "doc_fingerprints": current_doc_fp,
        "doc_changes": doc_changes,
        "counts": {
            "previous_chunks": len(previous_chunks),
            "current_chunks": len(current_chunks),
            "changed_chunks": len(changed_chunks),
            "deleted_chunks": len(deleted_chunks),
            "tombstones": len(deleted_chunks),
            "changed_docs": len(doc_changes),
        },
    }


def should_keep_row(table: str, row: dict[str, str], domain: str, doc_names: set[str]) -> bool:
    if "doc_name" in row:
        return row.get("doc_name") in doc_names
    return row.get("domain") == domain


def write_canonical_subsets(package_dir: Path, canonical_tables: list[dict[str, Any]], domain: str, doc_names: set[str]) -> list[dict[str, Any]]:
    out_dir = package_dir / "canonical"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for table in canonical_tables:
        path = Path(str(table.get("path") or ""))
        if not table.get("exists") or not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as src:
            reader = csv.DictReader(src)
            rows = [row for row in reader if should_keep_row(str(table.get("table")), row, domain, doc_names)]
            fieldnames = reader.fieldnames or []
        if not rows:
            continue
        out_path = out_dir / path.name
        with out_path.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        written.append(
            {
                "table": table.get("table"),
                "path": str(out_path),
                "row_count": len(rows),
                "source_path": str(path),
            }
        )
    return written


def neo4j_password(pass_file: Path) -> str:
    if pass_file.exists():
        return pass_file.read_text(encoding="utf-8").strip()
    return ""


def node_key(labels: list[str], props: dict[str, Any]) -> str:
    if props.get("entity_id"):
        return str(props["entity_id"])
    if "Document" in labels:
        return f"Document:{props.get('canonical_doc_name') or props.get('name')}"
    return f"{next((label for label in labels if label != 'Entity'), 'Entity')}:{props.get('name')}"


def export_graph(package_dir: Path, domain: str, doc_names: set[str], pass_file: Path) -> dict[str, Any]:
    password = neo4j_password(pass_file)
    if not password:
        return {"available": False, "error": "Neo4j password is not configured"}

    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password), connection_timeout=2)
    try:
        with driver.session() as session:
            node_rows = [
                dict(row)
                for row in session.run(
                    Query(
                        """
                        MATCH (n)
                        WHERE (NOT n:Document AND n.domain = $domain)
                           OR (n:Document AND (n.canonical_doc_name IN $doc_names OR n.name IN $doc_names))
                        RETURN elementId(n) AS element_id,
                               labels(n) AS labels,
                               properties(n) AS properties
                        ORDER BY coalesce(n.domain, ""), coalesce(n.canonical_doc_name, n.name, "")
                        """,
                        timeout=10,
                    ),
                    domain=domain,
                    doc_names=sorted(doc_names),
                )
            ]
            id_to_key = {}
            nodes = []
            for row in node_rows:
                props = dict(row["properties"] or {})
                labels = list(row["labels"] or [])
                key = node_key(labels, props)
                id_to_key[row["element_id"]] = key
                nodes.append({"key": key, "labels": labels, "properties": props})

            rel_rows = [
                dict(row)
                for row in session.run(
                    Query(
                        """
                        MATCH (a)-[r]->(b)
                        WHERE elementId(a) IN $ids AND elementId(b) IN $ids
                        RETURN elementId(a) AS start_id,
                               elementId(b) AS end_id,
                               type(r) AS type,
                               properties(r) AS properties
                        ORDER BY type(r), elementId(a), elementId(b)
                        """,
                        timeout=20,
                    ),
                    ids=list(id_to_key),
                )
            ]
    finally:
        driver.close()

    relationships = []
    rejected_relationships = []
    for row in rel_rows:
        if row["start_id"] not in id_to_key or row["end_id"] not in id_to_key:
            continue
        props = dict(row.get("properties") or {})
        reason = relationship_missing_evidence_reason(row["type"], props)
        if reason:
            rejected_relationships.append(
                {
                    "start_key": id_to_key[row["start_id"]],
                    "end_key": id_to_key[row["end_id"]],
                    "type": row["type"],
                    "reason": reason,
                    "properties": props,
                }
            )
            continue
        relationships.append(
            {
                "start_key": id_to_key[row["start_id"]],
                "end_key": id_to_key[row["end_id"]],
                "type": row["type"],
                "properties": props,
            }
        )
    write_jsonl(package_dir / "graph_nodes.jsonl", nodes)
    write_jsonl(package_dir / "graph_relationships.jsonl", relationships)
    write_jsonl(package_dir / "graph_relationships_rejected.jsonl", rejected_relationships)
    return {
        "available": True,
        "nodes_file": "graph_nodes.jsonl",
        "relationships_file": "graph_relationships.jsonl",
        "rejected_relationships_file": "graph_relationships_rejected.jsonl",
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "rejected_relationship_count": len(rejected_relationships),
    }


def package_domain(manifest: dict[str, Any], domain: str, output_dir: Path, neo4j_pass_file: Path) -> dict[str, Any]:
    sync_set = manifest.get("sync_sets", {}).get(domain, {})
    if not sync_set.get("eligible"):
        raise ValueError(f"{domain} is not sync eligible in manifest")

    package_dir = output_dir / domain
    package_dir.mkdir(parents=True, exist_ok=True)
    previous_chunks = load_previous_chunks(package_dir)
    doc_names = set(sync_set.get("sqlite_documents", []))
    chunks = load_chunks(doc_names)
    chunk_fp = fingerprint_chunks(chunks)
    previous_domain_fp = fingerprint_chunks(previous_chunks) if previous_chunks else None
    delta = build_delta(domain, previous_chunks, chunks)
    canonical_tables = write_canonical_subsets(
        package_dir,
        manifest.get("domain_asset_map", {}).get(domain, {}).get("canonical_tables", []),
        domain,
        doc_names,
    )
    graph_export = export_graph(package_dir, domain, doc_names, neo4j_pass_file)
    write_chunks_jsonl(package_dir / "chunks.jsonl", chunks)
    write_jsonl(package_dir / "changed_chunks.jsonl", delta["changed_chunks"])
    write_jsonl(package_dir / "deleted_chunks.jsonl", delta["deleted_chunks"])
    write_jsonl(package_dir / "tombstones.jsonl", delta["tombstones"])
    write_json(package_dir / "chunk_fingerprints.json", delta["chunk_fingerprints"])
    write_json(package_dir / "doc_fingerprints.json", delta["doc_fingerprints"])
    write_jsonl(package_dir / "doc_changes.jsonl", delta["doc_changes"])
    write_json(package_dir / "documents.json", sorted(doc_names))

    domain_manifest = {
        "schema_version": "domain-sync-package-v2",
        "built_at": utc_now(),
        "domain": domain,
        "semantic_schema_version": SCHEMA_VERSION,
        "source_manifest": {
            "schema_version": manifest.get("schema_version"),
            "generated_at": manifest.get("generated_at"),
            "sqlite_fingerprint": manifest.get("canonical_store", {}).get("fingerprint", {}),
        },
        "domain_fingerprint": chunk_fp,
        "previous_domain_fingerprint": previous_domain_fp,
        "documents": sorted(doc_names),
        "chunks_file": "chunks.jsonl",
        "incremental": {
            "schema": delta["schema"],
            "base_fingerprint": previous_domain_fp,
            "target_fingerprint": chunk_fp,
            "can_apply_incrementally": bool(previous_chunks),
            "changed_chunks_file": "changed_chunks.jsonl",
            "deleted_chunks_file": "deleted_chunks.jsonl",
            "tombstones_file": "tombstones.jsonl",
            "chunk_fingerprints_file": "chunk_fingerprints.json",
            "doc_fingerprints_file": "doc_fingerprints.json",
            "doc_changes_file": "doc_changes.jsonl",
            "counts": delta["counts"],
        },
        "canonical_tables": canonical_tables,
        "graph_export": graph_export,
        "graph_snapshot": manifest.get("domain_asset_map", {}).get(domain, {}).get("neo4j", {}),
        "remote_rebuild": {
            "authority": "Use chunks.jsonl, canonical subsets, and graph export files as package inputs; rebuild derived layers remotely.",
            "layers": ["bm25", "dense_bge_m3", "neo4j_subgraph"],
            "do_not_sync_as_authority": ["bm25 index files", "dense sqlite index", "neo4j database files"],
        },
    }
    write_json(package_dir / "domain_manifest.json", domain_manifest)
    (package_dir / "README.md").write_text(
        "\n".join(
            [
                f"# {domain} sync package",
                "",
                "This package is a local skeleton for cross-machine sync tests.",
                "The remote side should import `chunks.jsonl`, read canonical CSV subsets,",
                "then rebuild BM25, dense_bge_m3, and the Neo4j subgraph as derived layers.",
                "",
                "Run readiness before shipping:",
                "",
                f"```bash\npython3 scripts/check_sync_readiness.py --domain {domain}\n```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "domain": domain,
        "package_dir": str(package_dir),
        "domain_fingerprint": chunk_fp,
        "incremental": {
            "base_fingerprint": previous_domain_fp,
            "target_fingerprint": chunk_fp,
            "counts": delta["counts"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--domain", action="append", choices=sorted(SYNC_ELIGIBLE_DOMAINS))
    parser.add_argument("--neo4j-pass-file", default=str(DEFAULT_NEO4J_PASS_FILE))
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).expanduser().read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir).expanduser()
    domains = args.domain or list(SYNC_ELIGIBLE_DOMAINS)
    neo4j_pass_file = Path(args.neo4j_pass_file).expanduser()
    results = [package_domain(manifest, domain, output_dir, neo4j_pass_file) for domain in domains]
    write_json(output_dir / "index.json", {"built_at": utc_now(), "packages": results})
    print(json.dumps({"output_dir": str(output_dir), "packages": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
