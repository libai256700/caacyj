#!/usr/bin/env python3
"""Check whether domain sync packages are allowed to leave the local master."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from rag_store.semantic_schema import SCHEMA_VERSION, SYNC_ELIGIBLE_DOMAINS

DEFAULT_MANIFEST = BASE_DIR / "ingest_manifest.json"


def check_domain(manifest: dict[str, Any], domain: str, min_chunk_coverage: float) -> dict[str, Any]:
    domain_map = manifest.get("domain_asset_map", {}).get(domain, {})
    sync_set = manifest.get("sync_sets", {}).get(domain, {})
    sqlite = domain_map.get("sqlite", {})
    neo4j = domain_map.get("neo4j", {})
    canonical_store = manifest.get("canonical_store", {})
    fingerprint = canonical_store.get("fingerprint", {})
    indexes = manifest.get("derived_indexes", {})

    checks = {
        "manifest_schema": manifest.get("schema_version") == "ingest-manifest-v2",
        "sqlite_fingerprint": bool(fingerprint.get("fingerprint"))
        and fingerprint.get("schema") == "chunks-v1"
        and int(fingerprint.get("chunk_count") or 0) > 0,
        "domain_sync_eligible": bool(sync_set.get("eligible")) and domain in SYNC_ELIGIBLE_DOMAINS,
        "domain_has_chunks": int(sqlite.get("chunk_count") or 0) > 0,
        "source_doc_resolved": not neo4j.get("unresolved_source_docs"),
        "source_doc_coverage": float(neo4j.get("source_doc_coverage_rate") or 0) >= 1.0,
        "source_chunk_evidence": float(neo4j.get("source_chunk_id_coverage_rate") or 0) >= min_chunk_coverage,
        "schema_version": float(neo4j.get("schema_version_coverage_rate") or 0) >= 1.0
        and manifest.get("semantic_schema", {}).get("version") == SCHEMA_VERSION,
        "bm25_fresh": bool(indexes.get("bm25", {}).get("fresh_against_sqlite")),
        "dense_fresh": bool(indexes.get("dense", {}).get("fresh_against_sqlite")),
    }
    if domain == "regulation":
        required_tables = {"regulations", "documents", "document_chunks"}
    elif domain == "question_bank":
        required_tables = {"question_banks", "documents", "document_chunks"}
    elif domain == "textbook":
        required_tables = {"documents", "document_chunks"}
    else:
        required_tables = {"documents", "document_chunks"}
    present_tables = {row.get("table") for row in domain_map.get("canonical_tables", []) if row.get("exists")}
    checks["canonical_tables"] = required_tables.issubset(present_tables)

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "domain": domain,
        "ready": not failed,
        "failed_checks": failed,
        "checks": checks,
        "metrics": {
            "sqlite_chunks": int(sqlite.get("chunk_count") or 0),
            "sqlite_documents": int(sqlite.get("document_count") or 0),
            "neo4j_entities": int(neo4j.get("entity_count") or 0),
            "neo4j_relationships": int(neo4j.get("relationship_count") or 0),
            "source_chunk_id_coverage_rate": float(neo4j.get("source_chunk_id_coverage_rate") or 0),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--domain", action="append", choices=sorted(SYNC_ELIGIBLE_DOMAINS))
    parser.add_argument("--min-chunk-coverage", type=float, default=0.70)
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest).expanduser()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    domains = args.domain or list(SYNC_ELIGIBLE_DOMAINS)
    results = [check_domain(manifest, domain, args.min_chunk_coverage) for domain in domains]
    output = {
        "manifest": str(manifest_path),
        "min_chunk_coverage": args.min_chunk_coverage,
        "ready": all(item["ready"] for item in results),
        "domains": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
