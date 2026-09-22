# question_bank sync package

This package is a local skeleton for cross-machine sync tests.
The remote side should import `chunks.jsonl`, read canonical CSV subsets,
then rebuild BM25, dense_bge_m3, and the Neo4j subgraph as derived layers.

Run readiness before shipping:

```bash
python3 scripts/check_sync_readiness.py --domain question_bank
```
