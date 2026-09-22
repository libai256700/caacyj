#!/usr/bin/env python3
"""Shadow retrieval for remote domain-sync QA.

The shadow path observes remote retrieval quality without changing the answer
returned by /api/ask. It is deliberately best-effort: failures are logged as
shadow diagnostics and never fail the primary local answer path.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any, Optional

from .query_trace import QueryTraceLogger, source_name
from .semantic_schema import SYNC_ELIGIBLE_DOMAINS, infer_domains


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TRACE_PATH = BASE_DIR / "eval" / "remote_shadow_traces.jsonl"
DEFAULT_HTTP_TIMEOUT_S = float(os.getenv("RAG_REMOTE_SHADOW_HTTP_TIMEOUT_S", "20"))
DEFAULT_REPLAY_NEO4J_URI = os.getenv("RAG_REMOTE_REPLAY_NEO4J_URI", "bolt://localhost:7688")
DEFAULT_WORKERS = int(os.getenv("RAG_REMOTE_SHADOW_WORKERS", "2"))

_EXECUTOR = ThreadPoolExecutor(max_workers=max(DEFAULT_WORKERS, 1), thread_name_prefix="remote-shadow")
_REPLAY_MODULE = None
_REPLAY_LOCK = threading.RLock()

SHADOW_DOMAIN_HINTS = {
    "regulation": (
        "民航法", "民用航空法", "CCAR", "92部", "法规", "条款", "管制空域",
        "运营合格证", "适航证书", "经营许可证", "实名登记", "国籍登记", "电子围栏",
        "训练机构规范",
    ),
    "question_bank": (
        "题库", "试题", "参考答案", "GPS", "任务规划", "航线规划", "飞行前检查",
        "多轴", "六轴", "四轴", "螺旋桨", "速度感知", "高海拔", "难离地",
        "空中交通管制", "雷暴", "飞行日志", "夜间飞行",
    ),
    "textbook": (
        "教材", "理论书籍", "固定翼", "升力", "伯努利", "通信链路", "数据链路",
        "导航系统", "发动机", "机翼", "尾翼", "起落架", "无刷电机",
        "电子调速器", "ESC", "飞控系统", "地面站系统", "锂聚合物",
        "复合材料", "任务载荷", "惯性导航", "旋翼飞行器",
    ),
}


def shadow_enabled() -> bool:
    return os.getenv("RAG_REMOTE_SHADOW_ENABLED", "1").lower() not in {"0", "false", "no"}


def shadow_backend() -> str:
    return os.getenv("RAG_REMOTE_SHADOW_BACKEND", "replay").strip().lower() or "replay"


def select_shadow_domain(question: str, semantic_plan: dict[str, Any] | None, intent: str = "") -> str | None:
    if not shadow_enabled():
        return None
    if os.getenv("RAG_REMOTE_SHADOW_ALL", "0").lower() in {"1", "true", "yes"}:
        return "general"

    domains = []
    if semantic_plan:
        domains.extend(semantic_plan.get("domains") or [])
    domains.extend(infer_domains(question or "", intent or ""))
    for domain in domains:
        if domain in SYNC_ELIGIBLE_DOMAINS:
            return domain
    hinted = infer_shadow_domain_from_text(question)
    if hinted:
        return hinted
    return None


def infer_shadow_domain_from_text(question: str) -> str | None:
    q = question or ""
    matched: list[str] = []
    for domain, hints in SHADOW_DOMAIN_HINTS.items():
        if any(hint.lower() in q.lower() for hint in hints):
            matched.append(domain)
    if not matched:
        return None
    if len(matched) == 1:
        return matched[0]
    if "题库" in q or "试题" in q or "参考答案" in q:
        return "question_bank"
    if "教材" in q or "理论书籍" in q:
        return "textbook"
    if any(term in q for term in ("民航法", "CCAR", "92部", "法规", "条款")):
        return "regulation"
    if "固定翼" in q or "伯努利" in q:
        return "textbook"
    if "GPS" in q or "多轴" in q or "任务规划" in q:
        return "question_bank"
    return matched[0]


def _load_replay_harness():
    global _REPLAY_MODULE
    with _REPLAY_LOCK:
        if _REPLAY_MODULE is not None:
            return _REPLAY_MODULE
        path = BASE_DIR / "remote_replay" / "replay_retrieval_harness.py"
        spec = importlib.util.spec_from_file_location("remote_replay_retrieval_harness", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load replay harness: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _REPLAY_MODULE = module
        return module


def start_shadow(query: str, domain: str | None, trace_id: str, semantic_plan: dict[str, Any] | None = None) -> Future | None:
    if not shadow_enabled() or not domain or domain == "general":
        return None
    return _EXECUTOR.submit(run_shadow, query, domain, trace_id, semantic_plan or {})


def run_shadow(query: str, domain: str, trace_id: str, semantic_plan: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    backend = shadow_backend()
    try:
        if backend == "http":
            result = _run_http_shadow(query, domain, trace_id)
        elif backend == "replay":
            result = _run_replay_shadow(query, domain)
        else:
            raise RuntimeError(f"unsupported shadow backend: {backend}")
        status = "ok"
        error = ""
    except Exception as exc:
        result = {}
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = int((time.time() - started) * 1000)
    summary = summarize_remote_result(result)
    return {
        "status": status,
        "error": error,
        "backend": backend,
        "domain": domain,
        "trace_id": trace_id,
        "query": query,
        "semantic_domains": (semantic_plan or {}).get("domains", []),
        "latency_ms": latency_ms,
        "remote": summary,
    }


def _run_http_shadow(query: str, domain: str, trace_id: str) -> dict[str, Any]:
    url = os.getenv("RAG_REMOTE_SHADOW_URL", "").strip()
    if not url:
        raise RuntimeError("RAG_REMOTE_SHADOW_URL is required for http backend")
    params = {"q": query, "domain": domain, "shadow": "1", "trace_id": trace_id}
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(url + sep + urllib.parse.urlencode(params))
    with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run_replay_shadow(query: str, domain: str) -> dict[str, Any]:
    harness = _load_replay_harness()
    args = argparse.Namespace(
        domain=domain,
        query=query,
        base_dir=os.getenv("RAG_REMOTE_REPLAY_BASE_DIR") or str(BASE_DIR / "remote_replay"),
        neo4j_uri=DEFAULT_REPLAY_NEO4J_URI,
        ollama_url=os.getenv("RAG_REMOTE_REPLAY_OLLAMA_URL", harness.DEFAULT_OLLAMA_URL),
        embedding_model=os.getenv("RAG_REMOTE_REPLAY_EMBED_MODEL", harness.DEFAULT_EMBED_MODEL),
        bm25_limit=int(os.getenv("RAG_REMOTE_REPLAY_BM25_LIMIT", "20")),
        dense_limit=int(os.getenv("RAG_REMOTE_REPLAY_DENSE_LIMIT", "20")),
        kg_limit=int(os.getenv("RAG_REMOTE_REPLAY_KG_LIMIT", "20")),
        limit=int(os.getenv("RAG_REMOTE_REPLAY_LIMIT", "8")),
        excerpt_chars=int(os.getenv("RAG_REMOTE_REPLAY_EXCERPT_CHARS", "420")),
    )
    return harness.run(args)


def summarize_remote_result(result: dict[str, Any]) -> dict[str, Any]:
    sources = result.get("sources") or []
    retriever_counts = result.get("retriever_counts") or {}
    kg_evidence = result.get("kg_evidence") or {}
    graph_paths = result.get("graph_paths") or kg_evidence.get("paths") or []
    matched_entities = kg_evidence.get("matched_entities") or []
    source_counts = result.get("source_counts") or {}
    if not retriever_counts and source_counts:
        retriever_counts = {
            "dense": source_counts.get("dense", 0),
            "bm25": source_counts.get("bm25", 0),
            "kg": source_counts.get("kg", 0),
            "merged": source_counts.get("merged", 0),
        }

    sqlite_backed = [
        src for src in sources
        if src.get("text_source") == "replay_sqlite"
        or src.get("sqlite_text_source") == "replay_sqlite"
    ]
    chunk_ids = [src.get("chunk_id") for src in sources if src.get("chunk_id")]
    return {
        "chunk_ids": chunk_ids[:20],
        "top_chunks": chunk_ids[:5],
        "top_sources": [source_name(src) for src in sources[:10]],
        "source_count": len(sources),
        "retriever_counts": retriever_counts,
        "kg_hit": bool(
            (retriever_counts.get("kg") or 0) > 0
            or graph_paths
            or matched_entities
        ),
        "kg_path_count": len(graph_paths),
        "kg_entity_count": len(matched_entities),
        "degraded": bool(result.get("degraded")),
        "degraded_reasons": result.get("degraded_reasons") or [],
        "evidence_completeness": {
            "has_sources": bool(sources),
            "sqlite_backed_sources": len(sqlite_backed),
            "all_sources_sqlite_backed": bool(sources) and len(sqlite_backed) == len(sources),
            "missing_sqlite_chunk_ids": result.get("missing_sqlite_chunk_ids") or [],
        },
    }


def summarize_local_result(
    *,
    response_sources: list[dict[str, Any]],
    kg_result: dict[str, Any],
    elapsed_s: float,
    retriever_counts: dict[str, Any],
    degraded: bool,
    degraded_reasons: list[str],
    answer: str,
) -> dict[str, Any]:
    chunk_ids = [src.get("chunk_id") for src in response_sources or [] if src.get("chunk_id")]
    chunk_sources = [src for src in response_sources or [] if src.get("chunk_id")]
    return {
        "chunk_ids": chunk_ids[:20],
        "top_chunks": chunk_ids[:5],
        "top_sources": [source_name(src) for src in (response_sources or [])[:10]],
        "source_count": len(response_sources or []),
        "retriever_counts": retriever_counts,
        "kg_hit": bool((kg_result or {}).get("total") or (kg_result or {}).get("paths")),
        "kg_path_count": len((kg_result or {}).get("paths") or []),
        "kg_entity_count": len((kg_result or {}).get("matched_entities") or []),
        "latency_ms": int(elapsed_s * 1000),
        "degraded": degraded,
        "degraded_reasons": degraded_reasons,
        "evidence_completeness": {
            "has_sources": bool(response_sources),
            "chunk_sources": len(chunk_sources),
            "chunk_sources_with_doc": sum(1 for src in chunk_sources if src.get("doc_name")),
            "answer_has_citation": bool(response_sources) and (
                "【来源" in (answer or "") or "[来源" in (answer or "") or "来源" in (answer or "")
            ),
        },
    }


def compare_shadow(local: dict[str, Any], shadow: dict[str, Any]) -> dict[str, Any]:
    remote = shadow.get("remote") or {}
    local_chunks = local.get("chunk_ids") or []
    remote_chunks = remote.get("chunk_ids") or []
    local_set = set(local_chunks)
    remote_set = set(remote_chunks)
    overlap = [cid for cid in local_chunks if cid in remote_set]
    return {
        "chunk_overlap": {
            "local_top": local_chunks[:5],
            "remote_top": remote_chunks[:5],
            "overlap_top5": [cid for cid in local_chunks[:5] if cid in set(remote_chunks[:5])],
            "overlap_count": len(overlap),
            "overlap_rate": round(len(overlap) / max(len(set(local_chunks[:10])), 1), 4),
            "remote_only_top5": [cid for cid in remote_chunks[:5] if cid not in local_set],
            "local_only_top5": [cid for cid in local_chunks[:5] if cid not in remote_set],
        },
        "kg_hit": {
            "local": bool(local.get("kg_hit")),
            "remote": bool(remote.get("kg_hit")),
            "diff": bool(local.get("kg_hit")) != bool(remote.get("kg_hit")),
        },
        "latency_ms": {
            "local": local.get("latency_ms"),
            "remote": shadow.get("latency_ms"),
            "delta_remote_minus_local": (
                shadow.get("latency_ms") - local.get("latency_ms")
                if isinstance(shadow.get("latency_ms"), int) and isinstance(local.get("latency_ms"), int)
                else None
            ),
        },
        "evidence_completeness": {
            "local": local.get("evidence_completeness", {}),
            "remote": remote.get("evidence_completeness", {}),
        },
    }


def finish_shadow(
    future: Future | None,
    *,
    trace_id: str,
    query: str,
    route: str,
    domain: str | None,
    local_summary: dict[str, Any],
    trace_logger: QueryTraceLogger | None = None,
) -> None:
    if future is None or not domain:
        return
    logger = trace_logger or QueryTraceLogger(DEFAULT_TRACE_PATH)

    def _finish() -> None:
        try:
            shadow = future.result(timeout=float(os.getenv("RAG_REMOTE_SHADOW_FINISH_TIMEOUT_S", "120")))
        except Exception as exc:
            shadow = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "backend": shadow_backend(),
                "domain": domain,
                "trace_id": trace_id,
                "query": query,
                "latency_ms": None,
                "remote": {},
            }
        payload = {
            "trace_id": trace_id,
            "route": route,
            "domain": domain,
            "query": query,
            "shadow_mode": True,
            "remote_answer_used": False,
            "local": local_summary,
            "shadow": shadow,
            "diff": compare_shadow(local_summary, shadow),
        }
        logger.record(payload)

    threading.Thread(target=_finish, daemon=True).start()
