# Semantic graph v2

This project now treats Neo4j as the semantic planning and reasoning layer, while SQLite remains the canonical evidence store for answer text.

## Contract

- `rag_chunks.db` owns `chunk_id -> text`.
- BM25, dense vectors, and Neo4j are derived layers that must be rebuildable from local source state.
- Neo4j nodes carry semantic governance fields: `entity_id`, `domain`, `canonical_name`, `source_doc`, `source_chunk_ids`, and `schema_version`.
- The active graph schema version is `semantic-graph-v2`.
- `chunk_id` is never reused as a semantic entity id.

## Domains

The first governed domains are:

- `company`
- `hr_policy`
- `course`
- `price`
- `regulation`
- `question_bank`
- `textbook`
- `job_market`
- `customer`

The first cross-machine sync domains are `regulation`, `question_bank`, and `textbook`. The local Mac remains the authoritative source; remote machines receive sync packages and rebuild BM25, dense, and Neo4j locally.

## Ingest And Validation Flow

New content should follow this sequence:

1. Store source files locally.
2. Generate stable document and chunk ids.
3. Write canonical chunks to SQLite.
4. Rebuild or refresh BM25.
5. Rebuild or refresh dense embeddings.
6. Extract graph entities and relationships into a staging set.
7. Bind graph nodes to `source_doc` and `source_chunk_ids`.
8. Merge only after freshness, graph health, route policy, and answer-quality gates pass.

## Standard Checks

Run these after semantic graph or ingest changes:

```bash
python3 scripts/check_index_freshness.py
python3 pipeline/kg_health_check.py
python3 scripts/eval_route_policy.py
python3 scripts/build_ingest_manifest.py
python3 scripts/eval_health_gate.py --suite smoke --suite quality --suite csa
python3 scripts/eval_health_gate.py --suite semantic
```

For graph governance repairs:

```bash
python3 scripts/repair_semantic_graph.py
python3 scripts/repair_semantic_graph.py --confirm
```
