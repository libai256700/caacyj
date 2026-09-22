---
name: "query-trace-quality-dashboard"
description: "问答质量追踪看板：分析 query_traces、路由、外部补全率、来源、延迟和 dashboard 质量遥测。"
---

# When To Use

Use this when the user asks to inspect answer quality, query traces, route behavior, external-completion rate, source usage, latency, degraded answers, KG overfetch, or the local dashboard quality tab.

Typical prompts:

- 看看 query_traces 质量如何
- 哪些问题外部补全最多
- 哪些来源最常被引用
- 哪些 intent 延迟最高
- 哪些 query KG 召回太多但答案贡献低
- 更新或验证 127.0.0.1:8787/dashboard 的质量监控

# Source Of Truth

Prefer the existing local sources before inventing a new telemetry path:

- `/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/eval/query_traces.jsonl`
- `/Users/xiaoji/Documents/监控平台/app.py`
- `http://127.0.0.1:8787/dashboard`
- `GET http://127.0.0.1:8787/api/summary`
- `GET http://127.0.0.1:8787/api/quality/traces`
- `POST http://127.0.0.1:8787/api/ingest/request`
- `pipeline/server.py` quality-report hook when validating live ingestion

# Procedure

1. Confirm whether the user wants an analysis report, a dashboard change, or a live verification.
2. Locate the current trace file and dashboard service.
3. For dashboard work, check the service first:
   - `launchctl print gui/$(id -u)/com.openclaw.monitor`
   - `lsof -nP -iTCP:8787 -sTCP:LISTEN`
   - `curl -s http://127.0.0.1:8787/api/summary`
   - `curl -s http://127.0.0.1:8787/api/quality/traces`
4. Resolve the answer-path evidence before aggregating metrics:
   - for a current ask, retain its JSON response and read `stats.trace_id`
   - run `kg_explain.py --trace-id <trace_id>` only with that exact response trace id
   - `kg_explain.py --last` is historical browsing only and cannot prove the current ask
   - a missing label file is an input error, not an empty or successful evaluation
5. For trace analysis, compute at least:
   - total trace count
   - external completion count and rate
   - top cited source kinds/docs
   - per-intent average and p95 latency
   - degraded reason distribution
   - KG overfetch with low final-source contribution
6. For live ingestion checks:
   - verify `pipeline/server.py` reports request quality to `/api/ingest/request`
   - keep telemetry failure non-blocking for `/api/ask`
   - run one real ask only when downstream provider disclosure is separately authorized, or use a proven no-egress local smoke path
   - pass the question as one opaque argv element with `shell=false`; never interpolate user text into a shell command
7. For UI/API changes:
   - keep total backend graph stats separate from display-sample stats
   - verify both API JSON and the rendered dashboard, not just the source diff

# Quality Heuristics

Flag queries for review when:

- answer is degraded or citation-free for an internal-fact question
- route is external-only when internal evidence should exist
- KG recalled many entities/paths but none appear in final sources
- latency is high for a simple CSA/CSV question
- source kinds are dominated by fallback search for business facts
- route metadata is missing or inconsistent with answer content

# Dashboard Constraints

- Keep the dashboard read-only for quality monitoring unless the user explicitly asks for admin controls.
- A local dashboard GET or `/api/ask` call does not itself authorize provider egress. Bind any disclosure of questions or retrieved context to an explicit provider/content/purpose/request-cap authorization.
- Treat a script as read-only only after source inspection proves that it does not persist secrets, initialize or refresh SQLite, write trace/report files, or trigger provider/network side effects.
- Do not mix placeholder data with live OpenClaw/KG metrics.
- Expose the source path or active DB path when it helps diagnose drift.
- Ignore `BrokenPipeError` if it only reflects disconnected clients during long JSON/graph responses.

# Verification Checklist

- Trace source path was confirmed.
- Dashboard API responds when dashboard work is involved.
- Metrics include external completion, top sources, latency by intent, degraded reasons, and KG low-contribution candidates.
- Live ingestion, if touched, remains non-blocking.
- Browser/API verification was performed for visible dashboard changes.
- Final report names the exact trace count and the most important bottleneck or risk.
