# Chunker v2

`rag_store/chunker_v2.py` provides structure-aware chunking for RAG migrations
and import flows. It does not write SQLite by itself; writes go through
`scripts/apply_rechunk_v2.py` so the canonical store can be previewed, backed
up, and rebuilt in one controlled pass.

## Policy

- `理论题库_*`: one question per chunk. Keep question, choices, answer, and
  explanation together.
- `政策法规_*`: one article per chunk. Split only when a single article is too
  long.
- `无人机理论书籍_*`: pack by section or paragraph, target about 900 characters,
  with punctuation-aware fallback splitting.
- `企业信息_*` and `人事制度_*`: pack by headings and numbered policy sections,
  target about 650 characters.

## Preview

Run a read-only preview before any migration:

```bash
python3 scripts/preview_rechunk_v2.py \
  --domain regulation \
  --domain question_bank \
  --domain textbook \
  --write-json review_reports/chunker_v2_preview.json
```

The preview compares current SQLite chunk counts with v2 chunk counts and writes
sample v2 chunk ids when `--sample` is used.

## Apply

Apply v2 chunking to the canonical SQLite store only after the preview looks
reasonable. This rewrites chunk ids for the selected domains, so every derived
retrieval and sync artifact must be rebuilt before release:

```bash
python3 scripts/apply_rechunk_v2.py --apply
python3 - <<'PY'
from rag_store.bm25_index import BM25Index
print(BM25Index().build(force=True))
PY
python3 scripts/build_dense_index.py --force
python3 scripts/check_index_freshness.py
```

Then refresh the downstream inventory and sync packages:

```bash
python3 /Users/xiaoji/Documents/知识库分析/scripts/build_canonical_entities.py
python3 /Users/xiaoji/Documents/知识库分析/scripts/validate_canonical_entities.py
python3 scripts/build_ingest_manifest.py
python3 scripts/build_domain_sync_package.py --domain regulation --domain question_bank --domain textbook
make domain-sync-gate-fast
```

`apply_rechunk_v2.py --apply` creates a timestamped backup under
`backups/rechunk_v2/` before replacing chunks for the selected domains.

## Runtime Mitigation

`ContextBuilder` expands each retrieved chunk with adjacent chunks from the same
document during final context assembly. This keeps answers readable when a
source boundary is narrow and works with the new v2 canonical chunk ids after
SQLite, BM25, dense indexes, manifests, and remote sync packages are rebuilt.
