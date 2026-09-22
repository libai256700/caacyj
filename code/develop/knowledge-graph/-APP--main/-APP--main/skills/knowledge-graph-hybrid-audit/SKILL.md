---
name: "knowledge-graph-hybrid-audit"
description: "知识图谱混合检索审计：排查 Hybrid RAG、Neo4j、/api/ask、路由、索引新鲜度和评测闸门。"
---

# When To Use

Use this when the task touches the local knowledge base, Hybrid RAG, Neo4j, `/api/ask`, routing policy, graph-first behavior, import quality, index freshness, provenance cleanup, eval gates, or KG/RAG architecture decisions.

Do not use this for generic RAG advice without local project context.

# Real Project First

Always start from the real repo:

`/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph`

Do not mistake Codex scratch directories or analysis folders for the source repo.

# Core Contract

The canonical text contract is:

`chunk_id -> text` lives in SQLite.

BM25, dense vectors, and Neo4j are derived recall/evidence layers. They may return ids, metadata, scores, entities, paths, and source hints, but they do not own the authoritative final text.

# Hybrid RAG Boundary Checklist

Use these checks when retiring duplicate Hybrid RAG guidance or auditing retrieval architecture:

- SQLite `rag_chunks.db` owns full chunk text, `doc_name`, `chunk_index`, checksums or equivalent freshness data, and batch backfill by `chunk_id`.
- Dense retrieval stores embeddings plus `chunk_id`; model or embedding-space changes require a parallel rebuild and explicit cutover.
- BM25 stores searchable fields plus `chunk_id`, and its manifest must include chunk count, text byte count, schema version, and a fingerprint from the canonical store.
- Neo4j stores entities, relationships, source documents, graph paths, and optional lightweight `ChunkRef` nodes; graph paths are evidence, not final answer text.
- The context builder is the final text reader and must backfill answer context by valid `chunk_id`.
- Structured CSV / CSA sits before RAG as a deterministic fast path, returns CSV sources, and does not depend on Dense, BM25, Neo4j, or SQLite chunk indexes.
- Degradation should be explicit: dense failure falls back to BM25 + KG, BM25 stale falls back with a freshness warning, KG unavailable falls back to dense + BM25, and total retrieval failure returns controlled no-context output.
- Fusion should prefer rank-based methods such as RRF; exact-match boosts must be small and visible in traces.

Minimum audit assertions:

- retrievers return valid `chunk_id`, not entity names or graph ids
- final sources resolve to canonical SQLite rows
- structured CSV-sourced business entities (jobs.csv / customers.csv / 价格表.csv …) never resolve to SQLite text chunks by design; `scripts/check_source_doc_aliases.py` counts them under `structured_csv`, so only the text-layer `unresolved` number is a provenance failure signal (a handful of legacy shared hub nodes kept from retired 企业信息 docs are expected to stay listed there)
- API output exposes route, source counts, and degraded status
- BM25 freshness is tied to the canonical-store fingerprint
- KG recall still works without Neo4j full-text `Chunk` ownership
- CSA questions stay `route=csa`, while general product or knowledge questions are not stolen by CSA
- textbook cases keep their per-case governance contract (governance fields present, review/conflict state as declared, deduplicated claims unique and present in the final context, no exercise sources, `public_search_status` as declared, exact graph-evidence origins); rate-only greens do not prove it

# Files To Inspect

Read only the files needed for the task, starting with:

- `pipeline/server.py` (retrieval, parallel recall, context building, response assembly)
- `pipeline/answer_policy.py` (regulation gates, CAAC guards, clause synthesis, hybrid answer merge — split out of server.py 2026-07-02)
- `rag_store/sqlite_store.py`
- `rag_store/route_policy.py`
- `rag_store/context_builder.py`
- `rag_store/merge_rerank.py`
- `rag_store/query_rewrite.py`
- `rag_store/kg_recall.py`
- `rag_store/csa_router.py`
- `rag_store/index_freshness.py`
- `scripts/eval_health_gate.py`
- `scripts/check_index_freshness.py`
- `scripts/build_ingest_manifest.py`
- `csv_query.py`
- `KG_GUIDE.md` when process/handbook rules are involved

# Audit Procedure

Before any command is classified as read-only, inspect its imports and entrypoint. The current live `pipeline/kg_health_check.py` calls `ensure_runtime_secret_files()`, while `scripts/check_source_doc_aliases.py` both persists secret files and calls `RagStore.init_tables()`. Do not run either as a read-only probe until a governed release removes those writes. Read-only SQLite inspection must open an existing database with URI `mode=ro`, enforce `PRAGMA query_only=ON`, and avoid constructors or helpers that create directories, schemas, WAL state, caches, traces, or reports.

An HTTP call to localhost `/api/ask` authorizes only that local request. It does not authorize downstream disclosure of the question, retrieved context, or answer to DeepSeek, Doubao Ark, search services, external reviewers, or any other provider. Before a live ask, confirm a still-valid authorization bound to the disclosed content, providers, purpose, and request cap, or prove that the selected deterministic/local path cannot egress; otherwise fail closed. Pass user questions as one opaque argv element through a `shell=false` executor and never interpolate them into a shell command.

1. Confirm repo path and current git/worktree state.
2. Build the architecture from code and live artifacts, not helper summaries.
3. Check layer alignment when quality/integrity matters:
   - SQLite chunk/doc counts and fingerprints
   - BM25 manifest indexed docs
   - dense index count
   - Neo4j connectivity and graph health
   - source_doc alias coverage
4. For routing questions:
   - inspect `rag_store/route_policy.py`
   - preserve fact-dependent generation needs
   - keep pure structured questions on CSA
   - use hybrid for composite structured + knowledge questions
   - keep external completion only when internal evidence is insufficient
5. For import or cleanup:
   - verify source provenance before deleting or rewriting
   - rebuild derived layers when source integrity changes
   - rebuild canonical outputs and ingest manifest when structured/canonical facts are affected
6. For graph governance:
   - keep public UAV knowledge separate from internal company policy semantics
   - merge equivalent public same-name concepts only when evidence supports it
   - require evidence fields for new business relations
7. For remote shadow or staged cutover:
   - keep shadow observe-only unless user explicitly asks for cutover
   - record chunk overlap, KG hit, latency, and evidence completeness
   - keep initial cutover scoped to regulation, question_bank, and textbook domains

# Live Repair Triage

When the task is a live KG failure rather than a broad architecture audit, classify the symptom before editing:

- wrong `route`:
  inspect `rag_store/route_policy.py` and CSA routing boundaries first.
- `route` looks right but sources are off-topic:
  inspect retrieval, merge/rerank, and `top_sources` alignment before changing route logic.
- stale or previously deleted answer keeps appearing:
  check SQLite canonical text, BM25 freshness, dense index freshness, and traces for stale text.
- `/api/ask` fails entirely:
  verify service health and runtime path before touching retrieval logic.
- pure structured question fails:
  inspect `csv_query.py`, `rag_store/csa_router.py`, and CSV freshness path first.
- graph evidence looks wrong or thin:
  inspect Neo4j health, provenance, and `source_doc` alias coverage before changing recall logic.
- generated business artifact misses internal facts:
  inspect query rewrite collapse and whether the original business intent survived routing.

Do not treat all bad answers as route-policy bugs.

# Regression Strategy

Use the standard KG command entrypoints defined in `workspace/skills/knowledge-graph/SKILL.md` for the exact commands and flags. This file owns **which layer to verify first**, while the main KG skill owns the stable command catalog.

Run the smallest useful checks first, typically in this order:

- index freshness checks
- route-policy checks
- CSA checks
- health-gate checks
- textbook gate checks when a book was imported, rechunked, or re-governed
- full KG health checks when graph relationships or provenance changed
- representative `/api/ask` probes for pure CSV, hybrid, KG-heavy, and fallback cases

# Textbook Domain Gate

Textbook question sets are governed differently from regulation or question-bank sets: every case declares per-case assertions instead of relying on suite-level rates. `scripts/eval_health_gate.py` evaluates them only under `"type": "textbook"`, which reuses `eval_smoke.governance_expectation_failures` and adds `min_governance_pass_rate`. A textbook set registered as `"type": "retrieval"` still runs and still reports hit@5, but every governance assertion is silently dropped — a weaker gate that looks identical when green. Unknown suite types now fail closed instead of falling back to retrieval.

Each textbook case must declare `require_expected_doc`, `require_governance_contract`, `require_unique_deduplicated_claims`, `require_no_exercise_sources`, `require_not_degraded`, `expected_review_required`, and `expected_public_search_status`; `require_graph_evidence` is per-case. The gate validates this schema before the first request, so a case that quietly loses an assertion fails at startup rather than passing green.

When a new book lands, add its question set, register it as a textbook suite, and keep expected docs bound to the real `doc_name` in SQLite.

For release or sync work, also use the repo's domain sync and replay acceptance gates when those paths are touched.

For narrow live repairs, close with:

1. the original failing probe
2. one adjacent regression probe
3. the smallest additional gate needed for the changed layer

For each `/api/ask` probe, retain the JSON response and resolve only the exact `stats.trace_id` returned by that response. `kg_explain.py --last` is historical browsing and cannot prove the current probe.

# Common Failure Patterns

- Wrong repo path: relocate to the real knowledge-graph repo before proceeding.
- Healthy source count but wrong answer: retrieved docs may be off-topic; check topical alignment and top sources.
- Bad answer persists verbatim: search exact stale text across SQLite, BM25, dense/canonical outputs, Neo4j, and traces.
- Import finished but retrieval is inconsistent: run freshness checks across SQLite, BM25, and dense.
- Graph source coverage looks low: resolve through `rag_store/source_doc_aliases.json` before declaring unresolved provenance.
- Graph-first routing works but eval fails: business relation evidence is missing; sync evidence-bearing canonical entities before adding router branches.
- Generated business artifact misses key facts: query rewrite likely collapsed the task to keyword lookup; preserve original intent and internal-fact dimensions.

# External Review

If the user asks for Claude or another helper audit:

1. Verify relay/model connectivity with a tiny `OK` probe.
2. Send only the targeted diff or short evidence bundle.
3. Treat the external reviewer as a scoped checker only; final judgment should follow the live local repo, live runtime evidence, and Codex's repair/verification flow.

# Verification Checklist

- Real repo path was used.
- The failing path was captured before repair when this was a live-fix task.
- SQLite remains the canonical chunk-text source.
- Index freshness is checked when imports, migrations, or cleanup changed data.
- Route policy regressions pass for the touched route class.
- Pure CSV stays `route=csa`.
- Composite questions return `route=hybrid` with merged evidence.
- KG health/provenance checks pass when graph data changed.
- Textbook suites ran under `type: textbook` with governance pass rate at the configured floor when textbook data changed.
- Derived canonical outputs and ingest manifest are refreshed when source integrity changed.
- Final report separates current verified architecture from proposed redesign.
