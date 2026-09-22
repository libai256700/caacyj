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
    """Normalize transport errors so callers can distinguish outage vs no-hit."""
    if isinstance(err, urllib.error.HTTPError):
        detail = f"HTTP {err.code}: {err.reason}"
        return detail, err.code in {502, 503, 504}

    if isinstance(err, urllib.error.URLError):
        reason = err.reason
        detail = str(reason or err)
        service_unavailable = False
        if isinstance(reason, ConnectionRefusedError):
            service_unavailable = True
        elif isinstance(reason, TimeoutError):
            service_unavailable = True
        else:
            low = detail.lower()
            service_unavailable = any(
                marker in low
                for marker in (
                    "connection refused",
                    "failed to establish a new connection",
                    "timed out",
                    "bad gateway",
                    "service unavailable",
                )
            )
        return detail, service_unavailable

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
    if name.startswith("政策法规_") or chunk_id.startswith("regulation:") or "ccar_92" in chunk_id:
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
    """Project the backward-compatible governance contract from /api/ask."""
    return {
        "review_required": bool(data.get("review_required")),
        "conflict_ids": data.get("conflict_ids", []),
        "deduplicated_sources": data.get("deduplicated_sources", []),
        "governance_degraded": bool(data.get("governance_degraded")),
    }


def response_status_fields(data: dict) -> dict:
    """Project the canonical degraded contract with a legacy stats fallback."""
    data = data if isinstance(data, dict) else {}
    stats = data.get("stats", {}) if isinstance(data.get("stats"), dict) else {}
    degraded_value = data.get("degraded")
    degraded = degraded_value if isinstance(degraded_value, bool) else bool(stats.get("degraded", False))
    degraded_reasons = data.get("degraded_reasons")
    if not isinstance(degraded_reasons, list):
        degraded_reasons = stats.get("degraded_reasons", [])
    if not isinstance(degraded_reasons, list):
        degraded_reasons = []
    return {
        "degraded": degraded,
        "degraded_reasons": degraded_reasons,
        "stats": stats,
    }


def open_ask_response(question: str):
    """Prefer the envelope POST contract, with a narrow pre-restart GET fallback."""
    body = json.dumps({"user_query": question}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        RAG_URL,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        return urllib.request.urlopen(req, timeout=RAG_TIMEOUT)
    except urllib.error.HTTPError as exc:
        if exc.code != 405:
            raise
        log.warning("RAG server has not reloaded POST /api/ask; using legacy GET once")
        qs = urllib.parse.urlencode({"q": question})
        return urllib.request.urlopen(f"{RAG_URL}?{qs}", timeout=RAG_TIMEOUT)


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
                # 命中题库文档 ≠ 命中原题。只有 exact 为真才允许输出题库关联栏目。
                "question_bank_hit": bool(data.get("question_bank_hit")),
                "question_bank_exact_hit": bool(data.get("question_bank_exact_hit")),
                "question_bank_matched_question": data.get("question_bank_matched_question"),
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
                server_error = str(payload.get("error") or "").strip()
                if server_error:
                    detail = f"{detail}: {server_error}"
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
                f"这不是“知识库无结果”，而是服务未连通或上游返回错误。原始错误: {last_error}"
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
            "error_type": last_error_payload.get("error_type")
            or (
                "governance_unavailable"
                if last_error_payload.get("governance_degraded")
                else result["error_type"]
            ),
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
