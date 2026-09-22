---
name: "structured-data-sync-csa"
description: "结构化数据与 CSA 同步：处理 CSV/XLSX/飞书表格、canonical 数据、缓存校验和事实路由。"
---

# When To Use

Use this when the user asks about structured business data, CSV/XLSX/Feishu Sheet sync, CSA route behavior, price/student/course/instructor/job facts, canonical tables, or the SQLite CSA cache.

Typical prompts:

- 同步一下结构化数据
- 价格表和学员进度有没有更新
- 这个问题应该只查 CSV 还是 CSV+RAG
- CSA 为什么慢或回答不对
- 把结构化数据接入图谱或缓存

# Source Of Truth

Treat source data and derived caches separately:

- Source folder: `/Users/xiaoji/Downloads/同步空间/openclaw/小技结构化数据`
- Knowledge repo: `/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph`
- Canonical data: `/Users/xiaoji/Documents/知识库分析/data/canonical/`
- CSA router: `rag_store/csa_router.py`
- CSA cache: `rag_index/csa_cache.sqlite`
- CSA evals: `scripts/eval_csa.py`, `eval/csa_questions.json`
- Business graph sync checks: `scripts/check_sync_readiness.py`, `scripts/run_business_graph_sync_gate.sh`
- Ingest manifest: `scripts/build_ingest_manifest.py`, `ingest_manifest.json`
- Customer canonical currently merges `客资表.csv` with `客资信息_客资表.csv`; the latter comes from the live Feishu folder `客资信息` base `客资表`, not from the old deleted 汪金钨 sheet.

# Procedure

1. Determine whether the user wants sync, audit, router repair, cache validation, or graph projection.
2. Inspect the real source folder and newest file timestamps before trusting cached outputs.
3. For sync:
   - identify CSV, XLSX, and Feishu-exported text inputs
   - when `客资信息` changes, inspect the live folder/base first and verify whether the source is a sheet or a bitable before touching the parser
   - run the established sync script or OpenClaw cron job when appropriate
   - report table counts and failures
4. For parser issues:
   - inspect the generator script for the affected output, such as `sync_consult.py` for `价格表.csv`
   - fix source parsing rather than patching the final CSV by hand
   - verify expected rows and aliases
5. For CSA cache:
   - check whether `rag_store/csa_router.py` uses `rag_index/csa_cache.sqlite`
   - verify cache freshness against source fingerprints or row counts
   - keep source CSV/canonical files as truth and SQLite cache as performance layer
6. For route behavior:
   - pure structured facts should stay on `route=csa`
   - composite questions should use `route=hybrid` and preserve both structured and RAG/KG sources
   - unsupported specialty course questions should fall through to RAG/public search rather than generic price-table answers
7. For canonical/governance work:
   - inspect `/Users/xiaoji/Documents/知识库分析/data/canonical/`
   - run `scripts/check_sync_readiness.py`
   - rebuild ingest manifest
   - run `scripts/run_business_graph_sync_gate.sh` when projecting business entities
   - only project to Neo4j when cross-entity reasoning needs it

# Write Safety

- Bind every production change to the exact release id and manifest SHA-256.
- Capture a pre-write checkpoint or backup for every authority or derived layer that can change.
- Show the exact write scope and obtain approval for that exact scope before applying it.
- Never patch generated CSV; fix the source parser or canonical build and regenerate it.
- Never grant a model or general-purpose tool arbitrary SQL/Cypher access.
- For a read-only CSA/cache audit, open only an existing SQLite file with URI `mode=ro`, enforce `PRAGMA query_only=ON`, and never call `CSARouter.connect()`, schema initialization, cache refresh, or any helper that creates a directory, database, table, WAL state, trace, or report.
- A command named `check`, `health`, `stats`, or `dry-run` is not presumed read-only. Inspect its imports and entrypoint first; if it persists secrets or initializes SQLite, classify it as a write-capable operation and require the corresponding staging/approval boundary.

# Route Boundaries

Prefer CSV/CSA for:

- exact price, student, course, instructor, customer, training progress, attendance, or job facts
- counts and table-backed facts

Prefer hybrid CSV + RAG/KG for:

- questions combining structured facts with policies, regulations, training design, or explanation
- business recommendations requiring both current data and internal knowledge

Prefer RAG/search fallback for:

- topics not represented in current structured data
- specialty offerings that the price table should not answer generically

# Common Failure Patterns

- A final CSV looks wrong: fix the parser/generator and rerun sync.
- `openclaw cron list` says no jobs: check legacy JSON state and SQLite state before concluding sync automation is missing.
- CSA is slow: router may be reparsing files instead of using SQLite cache.
- Route-policy eval fails after data refresh: live data may have changed; verify current row counts before changing router logic.
- Bad evidence still appears after cleanup: rebuild canonical outputs and ingest manifest, not just the main RAG DB.

# Verification Checklist

- Source folder and current file timestamps were checked.
- Sync result reports successful, failed, and skipped tables.
- Important row counts are reported for affected tables.
- CSA cache freshness is checked when cache behavior is involved.
- Pure structured regression stays `route=csa`.
- Composite regression returns `route=hybrid` with merged evidence.
- Canonical outputs and ingest manifest are rebuilt when source integrity changed.
