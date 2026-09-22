# Unified ingest manifest

`ingest_manifest.json` is the project-level manifest for CSV, document, chunk,
and graph coverage. It is generated from live local state; do not hand-edit it.

Generate or refresh it:

```bash
python3 scripts/build_ingest_manifest.py
```

Print without writing:

```bash
python3 scripts/build_ingest_manifest.py --stdout
```

## What it records

- `csv_sources`: CSV files under `/Users/xiaoji/Downloads/同步空间/openclaw/小技结构化数据`, including row counts, columns, file mtime, size, and SHA-256.
- `document_sources`: local source documents under `rag_docs/` and `feishu_raw/`, including file versions and SQLite chunk coverage.
- `canonical_store`: `rag_chunks.db`, including the canonical chunk fingerprint, document rows, chunk counts, and update times.
- `graph_coverage`: Neo4j node/relationship counts, label/type counts, `Document` node metadata coverage, `source_doc` resolution against SQLite document names, and `source_chunk_ids` coverage.
- `derived_indexes`: BM25 and dense index manifests, checked against the SQLite chunk fingerprint.
- `coverage_summary`: the compact status block to use in audits, backups, and sync checks.
- `domain_asset_map`: per-domain source files, SQLite documents/chunks, Neo4j entity and relationship coverage, canonical tables, and cross-machine sync eligibility.

## Contract

SQLite owns canonical chunk text and the `chunk_id` contract. BM25, dense
embeddings, and Neo4j are derived layers. A fresh manifest should therefore
show:

- BM25 `fresh_against_sqlite: true`
- dense `fresh_against_sqlite: true`
- graph `source_doc_coverage` resolved through direct document names or
  `rag_store/source_doc_aliases.json`

If `sqlite_unresolved_source_docs` is non-zero, either add the missing source
documents/chunks or extend `rag_store/source_doc_aliases.json` when the graph
name is only an alias for an existing SQLite document.

## Domain sync

Check whether sync-eligible domains can be packaged:

```bash
python3 scripts/check_sync_readiness.py
```

Build local package skeletons for the current sync domains:

```bash
python3 scripts/build_domain_sync_package.py
```

Packages are written under `sync_packages/<domain>/` and include:

- `domain_manifest.json`: schema version, source manifest fingerprint, domain fingerprint, graph snapshot, and remote rebuild instructions.
- `chunks.jsonl`: the authoritative chunk subset for the domain.
- `canonical/*.csv`: canonical table subsets needed by that domain.
- `graph_nodes.jsonl` and `graph_relationships.jsonl`: the package's Neo4j subgraph export.
- `README.md`: operator notes for remote rebuild tests.

The remote side should rebuild BM25, dense embeddings, and Neo4j from the
package. It should not treat copied derived indexes or Neo4j database files as
authoritative.

Replay the packages locally in an isolated directory:

```bash
python3 scripts/replay_domain_sync_package.py --dense-mode full --force
```

The replay writes `remote_replay/<domain>/` with:

- a rebuilt `rag_chunks.db`
- rebuilt `rag_index/bm25/`
- rebuilt `rag_index/dense_bge_m3.sqlite`
- `neo4j_import.cypher` generated from the graph JSONL export
- `replay_report.json`

The top-level `remote_replay/replay_summary.json` is the quick pass/fail result
for all sync domains.
