#!/usr/bin/env python3
"""
云技知识库统一查询脚本
用法: 
  python3 kg_query.py "无人机大风天能飞么"          → 自然语言回答（纯文本）
  python3 kg_query.py --json "无人机分类"           → JSON 结构化输出
  python3 kg_query.py --json "无人机分类" > out.json → 保存到文件
  from kg_query import query                        → Python 模块导入
  RAG_URL=http://x:5001/api/ask python3 kg_query.py → 跨机器调用

输出: 自然语言回答 + 来源 > stdout
退出码: 0=成功, 1=失败
"""

import sys, json, os, time, urllib.request, urllib.parse, urllib.error, logging

# --- 配置（环境变量覆盖） ---
RAG_URL = os.environ.get("RAG_URL", "http://localhost:5001/api/ask")
RAG_TIMEOUT = int(os.environ.get("RAG_TIMEOUT", "60"))
RAG_RETRIES = int(os.environ.get("RAG_RETRIES", "2"))
RAG_MAX_QUERY_LEN = int(os.environ.get("RAG_MAX_QUERY_LEN", "2000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("kg_query")


def classify_service_error(err: Exception) -> tuple[str, bool]:
    """Classify transport failures without treating outages as empty results."""
    if isinstance(err, urllib.error.HTTPError):
        return f"HTTP {err.code}: {err.reason}", err.code in {502, 503, 504}
    if isinstance(err, urllib.error.URLError):
        reason = err.reason
        detail = str(reason or err)
        if isinstance(reason, (ConnectionRefusedError, TimeoutError)):
            return detail, True
        markers = (
            "connection refused",
            "failed to establish a new connection",
            "timed out",
            "bad gateway",
            "service unavailable",
        )
        return detail, any(marker in detail.lower() for marker in markers)
    return str(err), False


def source_name(source: dict) -> str:
    """Return the best display name for RAG or CSA sources."""
    return (
        source.get("name")
        or source.get("doc_name")
        or source.get("source_doc")
        or source.get("doc")
        or source.get("file")
        or source.get("chunk_id")
        or "unknown"
    )


def source_type(source: dict) -> str:
    explicit = source.get("type") or source.get("source")
    if explicit:
        return explicit
    name = source_name(source)
    chunk_id = str(source.get("chunk_id") or "").lower()
    if name.endswith(".csv"):
        return "StructuredData"
    if name.startswith("政策法规_") or chunk_id.startswith("regulation:"):
        return "Regulation"
    if name.startswith("理论题库_"):
        return "QuestionBank"
    if name.startswith("无人机理论书籍_") or chunk_id.startswith("textbook:"):
        return "Textbook"
    return "Document"


def source_score(source: dict) -> float:
    for key in ("score", "final_score", "rrf_score"):
        value = source.get(key)
        if isinstance(value, (int, float)):
            return round(float(value), 3)
    return 0.0


def governance_fields(data: dict) -> dict:
    """Project the backward-compatible governance response contract."""
    return {
        "review_required": bool(data.get("review_required")),
        "conflict_ids": data.get("conflict_ids", []),
        "deduplicated_sources": data.get("deduplicated_sources", []),
        "governance_degraded": bool(data.get("governance_degraded")),
    }


def response_status_fields(data: dict) -> dict:
    """Prefer top-level degradation fields and support legacy stats responses."""
    data = data if isinstance(data, dict) else {}
    stats = data.get("stats", {}) if isinstance(data.get("stats"), dict) else {}
    degraded_value = data.get("degraded")
    degraded = degraded_value if isinstance(degraded_value, bool) else bool(stats.get("degraded"))
    reasons = data.get("degraded_reasons")
    if not isinstance(reasons, list):
        reasons = stats.get("degraded_reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    return {"degraded": degraded, "degraded_reasons": reasons, "stats": stats}


def open_ask_response(question: str):
    """Prefer POST and fall back to legacy GET only when POST is unsupported."""
    body = json.dumps({"user_query": question}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        RAG_URL,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        return urllib.request.urlopen(request, timeout=RAG_TIMEOUT)
    except urllib.error.HTTPError as exc:
        if exc.code != 405:
            raise
        log.warning("POST /api/ask is unavailable; using one legacy GET request")
        query_string = urllib.parse.urlencode({"q": question})
        return urllib.request.urlopen(f"{RAG_URL}?{query_string}", timeout=RAG_TIMEOUT)


def query(question: str) -> dict:
    """查询统一 /api/ask，返回双RAG或CSA结构化结果。
    
    Returns:
        {"ok": True, "question": str, "answer": str, "sources": [{"name","type","score"}], "source_count": int}
        或 {"ok": False, "error": str}
    """
    question = question.strip()
    if not question:
        return {"ok": False, "error": "question is empty"}
    if len(question) > RAG_MAX_QUERY_LEN:
        return {"ok": False, "error": f"question exceeds {RAG_MAX_QUERY_LEN} chars"}
    
    last_error = ""
    last_error_service_unavailable = False
    last_error_payload = {}
    for attempt in range(1, RAG_RETRIES + 1):
        last_error_payload = {}
        last_error_service_unavailable = False
        try:
            t0 = time.time()
            r = open_ask_response(question)
            data = json.loads(r.read())
            elapsed = time.time() - t0
            
            # 安全取值
            answer = data.get("answer", "")
            raw_sources = data.get("sources", [])
            status_fields = response_status_fields(data)
            sources = [
                {
                    "name": source_name(s),
                    "type": source_type(s),
                    "score": source_score(s)
                }
                for s in raw_sources
            ]
            
            log.info(
                f"QUERY OK | q={question[:40]} | "
                f"sources={len(sources)} | time={elapsed:.1f}s"
            )
            
            return {
                "ok": True,
                "question": data.get("query", question),
                "answer": answer,
                "sources": sources,
                "source_count": len(sources),
                "route": data.get("route") or "rag",
                "intent": data.get("intent"),
                "degraded": status_fields["degraded"],
                "degraded_reasons": status_fields["degraded_reasons"],
                **governance_fields(data),
                "stats": status_fields["stats"],
                "elapsed": round(elapsed, 2)
            }
        except urllib.error.HTTPError as e:
            detail, service_unavailable = classify_service_error(e)
            try:
                payload = json.loads(e.read())
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                payload = {}
            if isinstance(payload, dict):
                last_error_payload = payload
                if payload.get("error"):
                    detail = f"{detail}: {payload['error']}"
            last_error = f"network error (attempt {attempt}/{RAG_RETRIES}): {detail}"
            last_error_service_unavailable = service_unavailable
            log.warning(last_error)
        except urllib.error.URLError as e:
            detail, service_unavailable = classify_service_error(e)
            last_error = f"network error (attempt {attempt}/{RAG_RETRIES}): {detail}"
            last_error_service_unavailable = service_unavailable
            log.warning(last_error)
        except json.JSONDecodeError as e:
            last_error = f"invalid response (attempt {attempt}/{RAG_RETRIES}): {e}"
            log.warning(last_error)
        except Exception as e:
            last_error = str(e)
            log.warning(f"QUERY FAIL (attempt {attempt}/{RAG_RETRIES}): {last_error}")
        
        if attempt < RAG_RETRIES:
            time.sleep(min(2 ** attempt, 8))  # 指数退避: 2s, 4s
    
    log.error(f"QUERY EXHAUSTED | q={question[:40]} | error={last_error}")
    if last_error_service_unavailable:
        result = {
            "ok": False,
            "error": (
                f"当前知识库问答服务不可用（RAG_URL={RAG_URL}）。"
                f"这不是“知识库无结果”，原始错误: {last_error}"
            ),
            "error_type": "service_unavailable",
            "service_url": RAG_URL,
            "degraded": True,
            "degraded_reasons": ["service_unavailable"],
            "stats": {},
        }
    else:
        result = {
            "ok": False,
            "error": f"知识库查询失败: {last_error}",
            "error_type": "query_failed",
            "service_url": RAG_URL,
            "degraded": True,
            "degraded_reasons": ["query_failed"],
            "stats": {},
        }
    if last_error_payload:
        result.update({
            "answer": last_error_payload.get("answer", ""),
            "route": last_error_payload.get("route") or "error",
            "request_rejected": bool(last_error_payload.get("request_rejected")),
            **governance_fields(last_error_payload),
            **response_status_fields(last_error_payload),
        })
    return result


# --- CLI ---
if __name__ == "__main__":
    use_json = False
    args = sys.argv[1:]
    
    if "--json" in args:
        use_json = True
        args.remove("--json")
    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)
    
    question = args[0] if args else "无人机分类有哪些"
    result = query(question)
    
    if result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["answer"])
            print(f"\n📚 来源: {result['source_count']} 个")
            for s in result["sources"]:
                print(f"  · {s['name']} ({s['type']}, 相关度 {s['score']})")
        sys.exit(0)
    else:
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"❌ {result['error']}", file=sys.stderr)
        sys.exit(1)
