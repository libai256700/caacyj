#!/usr/bin/env python3
"""
知识图谱管理面板 - Flask 后端 API (v2)
审计修复版 — 异常处理 / UUID / 安全 / Cypher查询 / 导出
"""

import json, os, re, sys, uuid, traceback, threading
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, make_response
from flask_cors import CORS
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from werkzeug.utils import secure_filename

# 双RAG 新模块
sys.path.insert(0, str(Path(__file__).parent.parent))
from rag_store.sqlite_store import RagStore
from rag_store.query_rewrite import QueryRewriter
from rag_store.kg_recall import KGRecall
from rag_store.merge_rerank import Merger
from rag_store.context_builder import ContextBuilder
from rag_store.bm25_index import BM25Index
from rag_store.dense_index import DenseIndex
from rag_store.csa_router import CSARouter
from rag_store.query_trace import QueryTraceLogger, source_name
from rag_store.remote_shadow import (
    finish_shadow,
    select_shadow_domain,
    start_shadow,
    summarize_local_result,
)
from rag_store.route_policy import (
    classify_route,
    needs_external_candidate,
)
from rag_store.semantic_schema import build_semantic_plan
from rag_store.request_envelope import (
    ALLOWED_SOURCES,
    RequestEnvelopeError,
    parse_request_envelope,
)
from rag_store.retrieval_planner import build_retrieval_plan
from pipeline.answer_policy import (
    deduplicate_response_sources,
    govern_answer,
    governance_response_fields,
    normalize_response_evidence,
)


SERVICE_RETRIEVAL_SOURCES = frozenset({"csa", "bm25", "dense", "neo4j", "web"})

# ============ 安全配置 ============
BASE_DIR = Path(__file__).parent.parent
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"

PASS_PATH = BASE_DIR / "neo4j" / ".neo4j_pass"
if not PASS_PATH.exists():
    print("❌ 密码文件缺失: "+ str(PASS_PATH))
    exit(1)
NEO4J_PASS = PASS_PATH.read_text().strip()

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

def get_driver():
    """安全获取 Neo4j 驱动，处理断连"""
    global driver
    try:
        driver.verify_connectivity()
    except:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    return driver

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

# ============ 双RAG 新架构初始化 ============
print("🔧 初始化双 RAG 架构组件...")
rag_store = RagStore(str(BASE_DIR / "rag_chunks.db"))
rag_store.init_tables()
print(f"   ✅ SQLite: {rag_store.count_chunks()} chunks / {rag_store.count_docs()} 文档")

query_rewriter = QueryRewriter()
kg_recall = KGRecall(db_path=str(BASE_DIR / "rag_chunks.db"))
merger = Merger(top_k=20)
context_builder = ContextBuilder(max_tokens=2400, db_path=str(BASE_DIR / "rag_chunks.db"))
bm25_index = BM25Index()
dense_index = DenseIndex(db_path=str(BASE_DIR / "rag_chunks.db"))
csa_router = CSARouter()
query_trace = QueryTraceLogger(BASE_DIR / "eval" / "query_traces.jsonl")
remote_shadow_trace = QueryTraceLogger(BASE_DIR / "eval" / "remote_shadow_traces.jsonl")
print("   ✅ Query Rewrite / KG Recall / Merger / Context Builder / BM25 / Dense / CSA 就绪")

# ============ 工具函数 ============
def get_embedding(text: str) -> list:
    """调用本地Ollama获取bge-m3向量"""
    import urllib.request as ureq
    body = json.dumps({"model":"bge-m3","prompt":text}).encode()
    r = ureq.urlopen(ureq.Request("http://127.0.0.1:11434/api/embeddings",
        data=body, headers={"Content-Type":"application/json"}), timeout=15)
    return json.loads(r.read()).get("embedding", [])


MONITOR_INGEST_URL = os.getenv("OPENCLAW_MONITOR_INGEST_URL", "http://127.0.0.1:8787/api/ingest/request")


def report_request_quality(payload: dict):
    """Best-effort monitor ingest; never block or fail /api/ask."""
    if os.getenv("OPENCLAW_MONITOR_INGEST_DISABLED") == "1":
        return

    def _send():
        try:
            import urllib.request as ureq
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = ureq.Request(
                MONITOR_INGEST_URL,
                data=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with ureq.urlopen(req, timeout=0.8) as resp:
                resp.read()
        except Exception as e:
            print(f"[MONITOR] request quality ingest skipped: {type(e).__name__}: {e}")

    threading.Thread(target=_send, daemon=True).start()


def source_ids_for_monitor(sources: list) -> list[str]:
    ids = []
    for src in sources or []:
        try:
            ids.append(source_name(src))
        except Exception:
                ids.append(str(src)[:120])
    return ids[:20]


CAAC_PRACTICAL_SCORE_CLAIM_TERMS = (
    "起飞10分",
    "悬停20分",
    "航线飞行30分",
    "应急处置20分",
    "降落20分",
)

CAAC_PRACTICAL_SCORE_CLAIM_PATTERNS = (
    r"起飞\s*[:：]?\s*10\s*分?",
    r"悬停\s*[:：]?\s*20\s*分?",
    r"航线(?:飞行)?\s*[:：]?\s*30\s*分?",
    r"应急(?:处置)?\s*[:：]?\s*20\s*分?",
    r"降落\s*[:：]?\s*20\s*分?",
)


def caac_practical_score_claim_hit_count(text: str) -> int:
    value = text or ""
    return sum(1 for pattern in CAAC_PRACTICAL_SCORE_CLAIM_PATTERNS if re.search(pattern, value))


def contains_caac_practical_score_claim(text: str) -> bool:
    return caac_practical_score_claim_hit_count(text) >= 2


def is_caac_practical_score_verification(question: str) -> bool:
    """Detect the known unsupported CAAC practical-score provenance claim."""
    q = question or ""
    if "图谱种子_CAAC实操考试评分标准" in q:
        return True
    if not contains_caac_practical_score_claim(q):
        return False
    verification_markers = (
        "来源",
        "出处",
        "官方",
        "原文",
        "文号",
        "依据",
        "对吗",
        "是否",
        "准确",
        "核实",
        "查过",
        "真假",
    )
    return any(marker in q for marker in verification_markers)


def caac_practical_score_claim_supported(ctx_result: dict) -> bool:
    context = ctx_result.get("context", "") or ""
    if any("图谱种子_" in source_name(src) for src in ctx_result.get("sources", [])):
        return False
    return caac_practical_score_claim_hit_count(context) == len(CAAC_PRACTICAL_SCORE_CLAIM_PATTERNS)


def build_caac_practical_score_guard_answer(question: str, ctx_result: dict) -> str | None:
    if not is_caac_practical_score_verification(question):
        return None
    if caac_practical_score_claim_supported(ctx_result):
        return None
    return (
        "不能把这条分值当成已核实事实。当前知识库没有检索到可支持"
        "“起飞10分、悬停20分、航线飞行30分、应急处置20分、降落20分”"
        "的官方原文、文号或条款。\n\n"
        "`图谱种子_CAAC实操考试评分标准.txt` 这类人工种子摘要不能作为来源；"
        "它已经从当前 RAG/图谱证据路径中清理。现有命中的资料只涉及实操动作、"
        "训练要求或相关法规片段，不足以证明这套评分分布。"
    )


def build_caac_practical_score_output_guard(answer: str, ctx_result: dict) -> str | None:
    """Remove the unsupported practical-score split even for non-verification asks."""
    if not contains_caac_practical_score_claim(answer):
        return None
    if caac_practical_score_claim_supported(ctx_result):
        return None
    return (
        "已删除未证实的实操分值拆分。当前知识库没有检索到可支持"
        "“起飞10分、悬停20分、航线飞行30分、应急处置20分、降落20分”"
        "的官方原文、文号或条款，因此不能把这套分项分值作为考试事实输出。\n\n"
        "当前可依据的内部资料只支持：考试包含理论考试、综合问答、实践飞行；"
        "超视距还涉及地面站预规划、重规划和应急返航。实践飞行应关注对应等级的"
        "飞行模式、悬停、水平360°慢转、水平8字、航向/位移/高度误差和速度要求。"
    )

def merge_hybrid_answer(csa_result: dict, rag_answer: str) -> str:
    csa_answer = (csa_result or {}).get("answer", "").strip()
    rag_answer = (rag_answer or "").strip()
    if csa_answer and rag_answer:
        return f"结构化数据：\n{csa_answer}\n\n知识库补充：\n{rag_answer}"
    return csa_answer or rag_answer


def hybrid_rag_query(question: str) -> str:
    """Keep only the knowledge-oriented part of a hybrid question for RAG."""
    q = question or ""
    from rag_store.route_policy import HYBRID_MARKERS, KNOWLEDGE_TERMS, STRUCTURED_TERMS

    for marker in HYBRID_MARKERS:
        if marker in q:
            tail = q.split(marker, 1)[1].strip(" ，,；;。")
            if any(term in tail for term in KNOWLEDGE_TERMS):
                return tail
    parts = [p.strip() for p in re.split(r"[，,；;。？！!?]", q) if p.strip()]
    knowledge_parts = [
        p for p in parts
        if any(term in p for term in KNOWLEDGE_TERMS)
        and not any(term in p for term in STRUCTURED_TERMS)
    ]
    return "，".join(knowledge_parts) or q


def graph_first_status(kg_result: dict, response_sources: list[dict]) -> dict:
    matched_entities = kg_result.get("matched_entities", []) or []
    paths = kg_result.get("paths", []) or []
    evidence_bindings = kg_result.get("evidence_bindings", []) or []
    if not matched_entities:
        insufficient_step = "graph_first_no_entry_entities"
    elif not paths:
        insufficient_step = "graph_first_no_relation_paths"
    elif not evidence_bindings and not response_sources:
        insufficient_step = "graph_first_no_sqlite_chunk_evidence"
    else:
        insufficient_step = None
    return {
        "enabled": True,
        "ok": insufficient_step is None,
        "used_entities": matched_entities[:10],
        "relation_paths": paths[:10],
        "final_sources": response_sources[:10],
        "evidence_bindings": evidence_bindings[:10],
        "insufficient_step": insufficient_step,
    }

print("[Chunk Init] server 运行时不再创建 Neo4j Chunk；SQLite 是唯一文本回源")

# 允许的关系类型白名单
ALLOWED_REL_TYPES = {
    'BELONGS_TO','CONTAINS','REFERENCES','REQUIRED_BY','MANAGES','REGULATES','PROVIDES',
    'LOCATED_IN','HAS_SALARY','RELATED_TO'  # RELATED_TO = 不安全类型的兜底
}

def safe_rel_type(rtype: str) -> str:
    """净化关系类型，防止 Cypher 注入"""
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', rtype).upper()
    if cleaned not in ALLOWED_REL_TYPES:
        cleaned = 'RELATED_TO'
    return cleaned

def safe_query(data: dict):
    """安全查询包装"""
    d = get_driver()
    with d.session() as s:
        return s

def api_error(e, context="操作失败"):
    print(f"❌ {context}: {traceback.format_exc()}")
    return jsonify({"error": str(e), "context": context}), 500

IMPORT_UPLOAD_DIR = BASE_DIR / "rag_docs" / "_api_uploads"
ALLOWED_IMPORT_SUFFIXES = {".txt", ".md", ".csv", ".json"}


def _json_error(message: str, status_code: int = 400, **extra):
    payload = {"ok": False, "status": "error", "error": message}
    payload.update(extra)
    return jsonify(payload), status_code


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_import_path(raw_path: str) -> Path:
    if not raw_path:
        raise ValueError("file_path is required")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    else:
        path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if not path.is_file():
        raise ValueError(f"path is not a file: {path}")
    if not _is_relative_to(path, BASE_DIR):
        raise ValueError("file_path must be under the project directory")
    if path.suffix.lower() not in ALLOWED_IMPORT_SUFFIXES:
        raise ValueError(f"unsupported file type: {path.suffix or '<none>'}")
    return path


def _save_uploaded_import_file(upload) -> Path:
    if not upload or not upload.filename:
        raise ValueError("multipart field 'file' is required")
    filename = secure_filename(upload.filename)
    if not filename:
        raise ValueError("uploaded filename is invalid")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMPORT_SUFFIXES:
        raise ValueError(f"unsupported file type: {suffix or '<none>'}")
    IMPORT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = IMPORT_UPLOAD_DIR / f"{uuid.uuid4().hex}_{filename}"
    upload.save(target)
    return target


def import_file_to_knowledge_graph(
    file_path: Path,
    *,
    doc_name: str = "",
    folder_hint: str = "",
    types: str = "",
    doc_url: str = "",
    model_key: str = "",
) -> dict:
    from pipeline.extract_one import _DEFAULT_MODEL_KEY, extract

    doc_name = (doc_name or file_path.stem).strip()
    folder_hint = (folder_hint or "default").strip()
    model_key = (model_key or _DEFAULT_MODEL_KEY).strip()
    result = extract(doc_name, str(file_path), folder_hint, types or "", doc_url or "", model_key=model_key)
    if result is None:
        return {
            "ok": False,
            "status": "failed",
            "error": "extract returned no result",
            "doc_name": doc_name,
            "filepath": str(file_path),
        }
    result.setdefault("doc_name", doc_name)
    result.setdefault("filepath", str(file_path))
    result.setdefault("status", "imported" if result.get("ok") else "failed")
    return result

def build_degraded_answer(ctx_result, reason: str) -> str:
    sources = ctx_result.get("sources", []) if ctx_result else []
    if not sources:
        return f"暂时无法生成完整回答（{reason}），且本次没有检索到可引用来源。"
    lines = [f"暂时无法生成完整回答（{reason}），请先参考已检索到的来源："]
    for src in sources[:5]:
        seq = src.get("seq", "?")
        doc_name = src.get("doc_name") or src.get("chunk_id", "未知来源")
        lines.append(f"【来源{seq}】{doc_name}")
    return "\n".join(lines)

def load_secret_env(name: str) -> str:
    """Read OpenClaw local secret env without printing secret values."""
    value = os.environ.get(name)
    if value:
        return value
    secrets_path = Path("/Users/xiaoji/.openclaw/secrets.local.json")
    if not secrets_path.exists():
        return ""
    try:
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    current = data
    for part in ("openclaw", "env", name):
        if not isinstance(current, dict) or part not in current:
            return ""
        current = current[part]
    return str(current or "")


def needs_external_completion(question: str, internal_sources: list[dict], csa_result: dict | None) -> bool:
    """External customer asks must not stop at an empty internal KB result."""
    return needs_external_candidate(question, internal_sources, csa_result)


def external_search_query(question: str) -> str:
    q = (question or "").strip()
    if any(term in q.lower() for term in ("fpv", "穿越机")):
        return f"{q} FPV 穿越机 培训 学费 价格"
    if any(term in q.lower() for term in ("utc", "上门")):
        return f"{q} 无人机 培训 价格"
    return q


def is_fpv_price_question(question: str) -> bool:
    q = (question or "").lower()
    return any(term in q for term in ("fpv", "穿越机")) and any(
        term in question for term in ("价格", "多少钱", "费用", "学费", "收费", "报价")
    )


def run_public_search(question: str, count: int = 10) -> dict:
    """One-round Baidu Qianfan + Serper search. No page fetch, bounded latency."""
    from concurrent.futures import ThreadPoolExecutor

    query = external_search_query(question)
    with ThreadPoolExecutor(max_workers=2) as executor:
        google_future = executor.submit(run_serper_search, query, count)
        baidu_future = executor.submit(run_baidu_search, query, count)
        google_results, google_error = google_future.result()
        baidu_results, baidu_error = baidu_future.result()

    fpv_question = is_fpv_price_question(question)
    seen_urls = set()
    merged = []
    for item in baidu_results + google_results:
        if fpv_question:
            haystack = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
            if not any(term in haystack for term in ("fpv", "穿越机")):
                continue
        url = item.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        merged.append(item)
        if len(merged) >= count:
            break

    errors = [err for err in (baidu_error, google_error) if err]
    status = "ok" if merged else "error" if errors else "empty"
    if merged and errors:
        status = "partial"
    return {
        "query": question,
        "search_query": query,
        "status": status,
        "errors": errors,
        "results": merged,
        "counts": {"baidu": len(baidu_results), "google": len(google_results), "merged": len(merged)},
    }


def run_serper_search(query: str, count: int = 10) -> tuple[list[dict], str | None]:
    import urllib.request as ureq
    api_key = load_secret_env("SERPER_API_KEY")
    if not api_key:
        return [], "missing_serper_api_key"
    try:
        payload = json.dumps({"q": query, "num": count}).encode()
        req = ureq.Request(
            "https://google.serper.dev/search",
            data=payload,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        )
        resp = ureq.urlopen(req, timeout=12)
        data = json.loads(resp.read().decode("utf-8"))
        results = []
        for item in data.get("organic", [])[:count]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "date": item.get("date", ""),
                "source": "google",
            })
        return results, None
    except Exception as e:
        return [], f"serper_error:{type(e).__name__}"


def run_baidu_search(query: str, count: int = 10) -> tuple[list[dict], str | None]:
    import urllib.request as ureq
    token = load_secret_env("BAIDU_QIANFAN_SEARCH_TOKEN")
    if not token:
        return [], "missing_baidu_qianfan_search_token"
    try:
        payload = json.dumps({
            "messages": [{"content": query, "role": "user"}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": count}],
        }).encode()
        req = ureq.Request(
            "https://qianfan.baidubce.com/v2/ai_search/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        resp = ureq.urlopen(req, timeout=12)
        data = json.loads(resp.read().decode("utf-8"))
        results = []
        for ref in data.get("references", [])[:count]:
            results.append({
                "title": ref.get("title", ""),
                "url": ref.get("url", ""),
                "snippet": ref.get("snippet") or ref.get("content", "")[:300],
                "date": ref.get("date", ""),
                "source": "baidu",
            })
        return results, None
    except Exception as e:
        return [], f"baidu_error:{type(e).__name__}"


def build_public_search_context(search_result: dict, start_seq: int) -> tuple[str, list[dict], list[dict]]:
    results = (search_result or {}).get("results", [])
    if not results:
        return "", [], []
    lines = ["【公开搜索补充】"]
    sources = []
    evidence = []
    for offset, item in enumerate(results[:5]):
        seq = start_seq + offset
        title = item.get("title") or "公开搜索结果"
        snippet = item.get("snippet") or ""
        url = item.get("url") or ""
        date = item.get("date") or ""
        suffix = f"（{date}）" if date else ""
        lines.append(f"【来源{seq}】{title}{suffix}\n{snippet}\n{url}".strip())
        sources.append({
            "type": "web",
            "doc_name": title,
            "url": url,
            "snippet": snippet,
            "date": date,
            "seq": seq,
        })
        evidence.append({
            "type": "public_search",
            "source_num": seq,
            "title": title,
            "url": url,
            "preview": snippet[:100],
        })
    return "\n\n".join(lines), sources, evidence

def primary_label_from_labels(node_labels):
    labels_list = list(node_labels or [])
    for label in labels_list:
        if label not in {"Entity", "Document"}:
            return label
    return labels_list[0] if labels_list else "Entity"

def node_primary_type(node):
    prop_type = node.get("type", "") if hasattr(node, "get") else ""
    if isinstance(prop_type, str) and prop_type and prop_type != "Entity":
        return prop_type
    return primary_label_from_labels(getattr(node, "labels", []))

# ============ API ============

@app.route("/")
def index():
    resp = make_response(send_from_directory(app.static_folder, "index.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.route("/api/health")
def health():
    try:
        d = get_driver()
        d.verify_connectivity()
        return jsonify({"status": "ok", "neo4j": "connected"})
    except Exception as e:
        return jsonify({"status": "error", "neo4j": str(e)}), 503


@app.route("/api/files", methods=["POST"])
@app.route("/api/import/file", methods=["POST"])
def import_file():
    try:
        if "file" in request.files:
            file_path = _save_uploaded_import_file(request.files["file"])
            values = request.form
        else:
            values = request.get_json(silent=True) or {}
            raw_path = values.get("file_path") or values.get("path")
            file_path = _safe_import_path(raw_path)
    except (FileNotFoundError, ValueError) as e:
        return _json_error(str(e), 400)

    try:
        result = import_file_to_knowledge_graph(
            file_path,
            doc_name=(values.get("doc_name") or values.get("name") or ""),
            folder_hint=(values.get("folder_hint") or values.get("category") or "default"),
            types=(values.get("types") or ""),
            doc_url=(values.get("doc_url") or ""),
            model_key=(values.get("model_key") or ""),
        )
    except Exception as e:
        print(f"❌ import_file: {traceback.format_exc()}")
        return _json_error(str(e), 500)

    ok = bool(result.get("ok"))
    return jsonify({
        "ok": ok,
        "job": {"mode": "sync", "status": result.get("status", "unknown")},
        "status": result.get("status", "unknown"),
        "result": result if ok else None,
        "error": None if ok else result.get("error", "import failed"),
    }), 201 if ok else 502

@app.route("/api/stats")
def stats():
    try:
        d = get_driver()
        with d.session() as s:
            nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = s.run("MATCH ()-->() RETURN count(*) AS c").single()["c"]
            docs = s.run("MATCH (d:Document) RETURN count(d) AS c").single()["c"]
            types = s.run(
                "MATCH (n) WHERE NOT n:Document "
                "RETURN coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity') AS t, "
                "count(*) AS c ORDER BY c DESC"
            ).data()
            rel_types = s.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType").data()
        return jsonify({
            "entities": nodes - docs, "relations": rels, "documents": docs,
            "types": [{"name": t["t"], "count": t["c"]} for t in types],
            "relationshipTypes": [r["relationshipType"] for r in rel_types],
        })
    except Exception as e:
        return api_error(e, "stats")

@app.route("/api/graph")
def graph():
    """返回所有节点和关系（兼容旧版vis-network + 新版多标签模型）"""
    try:
        d = get_driver()
        with d.session() as s:
            # 所有非Document节点
            enodes = s.run(
                "MATCH (n) WHERE NOT n:Document "
                "RETURN n.name AS id, n.name AS name, "
                "coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity') AS type "
                "ORDER BY type LIMIT 2000"
            ).data()
            # Document 节点
            dnodes = s.run(
                "MATCH (d:Document) RETURN d.name AS id, d.name AS name, "
                "'Document' AS type LIMIT 200"
            ).data()
            # 所有关系
            erels = s.run(
                "MATCH (a)-[r]->(b) "
                "RETURN COALESCE(a.name, a.id) AS source, COALESCE(b.name, b.id) AS target, type(r) AS type "
                "LIMIT 30000"
            ).data()
        return jsonify({
            "nodes": [{"id": n["id"], "label": n["name"], "type": n["type"]} for n in enodes + dnodes],
            "edges": [{"from": r["source"], "to": r["target"], "label": r["type"]} for r in erels if r.get("source") and r.get("target")]
        })
    except Exception as e:
        return api_error(e, "graph")


@app.route("/search")
def search_page():
    return app.send_static_file("search.html")
@app.route("/api/search")
def search():
    """语义搜索：Ollama bge-m3 向量化 + Neo4j 向量检索"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    try:
        import urllib.request as ureq
        body = json.dumps({"model":"bge-m3","prompt":q}).encode()
        r = ureq.urlopen(ureq.Request("http://127.0.0.1:11434/api/embeddings",
            data=body, headers={"Content-Type":"application/json"}), timeout=15)
        q_emb = json.loads(r.read()).get("embedding", [])
        if not q_emb:
            return jsonify([])
        d = get_driver()
        with d.session() as s:
            rows = s.run("""CALL db.index.vector.queryNodes('entity_embedding', 10, $e)
                YIELD node, score WHERE node.source_doc IS NOT NULL
                RETURN node.name AS name, node.type AS type,
                       node.description AS description, score ORDER BY score DESC""",
                e=q_emb).data()
        return jsonify([{
            "name":r["name"], "type":r["type"],
            "description":(r.get("description")or"")[:120],
            "score":round(r["score"],4)
        } for r in rows])
    except Exception as e:
        return api_error(e, "search")


@app.route("/api/ask", methods=["GET", "POST"])
def ask():
    """
    双RAG + Neo4j 图谱 混合检索问答
    
    流程：Query Rewrite → Dense RAG → Neo4j KG → Merge → Context Builder → LLM Answer
    """
    trace_id = str(uuid.uuid4())
    try:
        if request.method == "POST":
            if not request.is_json:
                raise RequestEnvelopeError(
                    "invalid_content_type",
                    "POST /api/ask requires application/json",
                )
            payload = request.get_json(silent=True)
            if payload is None:
                raise RequestEnvelopeError("invalid_json", "request body is not valid JSON")
            envelope = parse_request_envelope(method="POST", json_body=payload)
        else:
            envelope = parse_request_envelope(
                method="GET",
                query_args={
                    key: values if len(values) != 1 else values[0]
                    for key, values in request.args.lists()
                },
            )
    except RequestEnvelopeError as exc:
        return jsonify({
            "error": exc.code,
            "message": str(exc),
            "request_rejected": True,
            "degraded": False,
            "degraded_reasons": [],
            "stats": {"trace_id": trace_id},
        }), 400

    q = envelope.user_query
    request_contract = envelope.to_dict(include_query=False)
    configured_sources = {
        source.strip().lower()
        for source in os.getenv(
            "RAG_ALLOWED_RETRIEVAL_SOURCES",
            ",".join(SERVICE_RETRIEVAL_SOURCES),
        ).split(",")
        if source.strip().lower() in SERVICE_RETRIEVAL_SOURCES
    }
    effective_sources = tuple(
        source
        for source in ALLOWED_SOURCES
        if source in envelope.allowed_sources and source in configured_sources
    )
    if not effective_sources:
        return jsonify({
            "error": "source_policy_empty",
            "message": "no requested retrieval source is enabled by the service",
            "request_rejected": True,
            "degraded": False,
            "degraded_reasons": [],
            "stats": {"trace_id": trace_id},
        }), 403
    request_contract["requested_sources"] = list(envelope.allowed_sources)
    request_contract["allowed_sources"] = list(effective_sources)
    request_contract["source_policy_enforced"] = True
    allowed_sources = set(effective_sources)
    embed_mode = "bge_m3"
    
    try:
        import urllib.request as ureq
        import time as _time
        t0 = _time.time()
        degraded = False
        degraded_reasons = []
        requested_embedding = envelope.isolation.get("requested_embedding", "")
        if requested_embedding == "unsupported":
            degraded = True
            degraded_reasons.append("embedding_param_ignored:bge_m3_only")

        # ====== Step 0: CSA 结构化 CSV 路由 ======
        csa_result = csa_router.answer(q) if "csa" in allowed_sources else None
        route_decision = classify_route(q, csa_result)
        hybrid_mode = route_decision == "hybrid"
        graph_first_mode = route_decision == "graph_first"
        if csa_result and route_decision == "csa":
            semantic_plan = build_semantic_plan(
                q,
                route_decision=route_decision,
                rag_query=q,
                intent=csa_result.get("intent", "structured_csv"),
                keywords=[],
                entities=[],
                csa_topic=csa_result.get("stats", {}).get("topic"),
            )
            retrieval_plan = build_retrieval_plan(
                envelope,
                route_decision=route_decision,
                semantic_plan=semantic_plan,
                intent=csa_result.get("intent", "structured_csv"),
                csa_topic=csa_result.get("stats", {}).get("topic"),
                effective_sources=effective_sources,
            )
            elapsed = _time.time() - t0
            csa_result.setdefault("stats", {})
            csa_sources = deduplicate_response_sources(csa_result.get("sources", []))
            csa_result["sources"] = csa_sources
            source_counts = {
                "structured": len(csa_sources),
                "dense": 0,
                "bm25": 0,
                "kg": 0,
                "merged": 0,
                "total": len(csa_sources),
            }
            csa_result["semantic_plan"] = semantic_plan
            csa_result["source_counts"] = source_counts
            csa_result["graph_paths"] = []
            csa_result["evidence_bindings"] = []
            csa_result["request_envelope"] = request_contract
            csa_result["retrieval_plan"] = retrieval_plan.to_dict()
            csa_result["degraded"] = degraded
            csa_result["degraded_reasons"] = degraded_reasons
            csa_result.update(governance_response_fields())
            csa_result["stats"].update({
                "trace_id": trace_id,
                "request_envelope": request_contract,
                "retrieval_plan": retrieval_plan.to_dict(),
                "embed_mode": None,
                "degraded": degraded,
                "degraded_reasons": degraded_reasons,
                "route_decision": route_decision,
                "semantic_domains": semantic_plan.get("domains", []),
                "source_counts": source_counts,
                "elapsed_s": round(elapsed, 3),
            })
            query_trace.record({
                "trace_id": trace_id,
                "route": "csa",
                "route_decision": route_decision,
                "semantic_plan": semantic_plan,
                "query": q,
                "intent": csa_result.get("intent", "structured_csv"),
                "topic": csa_result["stats"].get("topic"),
                "elapsed_s": round(elapsed, 3),
                "degraded": degraded,
                "degraded_reasons": degraded_reasons,
                "source_count": len(csa_result.get("sources", [])),
                "top_sources": [source_name(src) for src in csa_result.get("sources", [])[:10]],
                "retriever_counts": {"dense": 0, "bm25": 0, "kg": 0, "merged": 0},
            })
            report_request_quality({
                "request_id": trace_id,
                "user_id": "openclaw_kg",
                "channel": "knowledge_graph_api",
                "question": q,
                "domain": csa_result.get("intent", "structured_csv"),
                "answer_preview": (csa_result.get("answer") or "")[:240],
                "source_count": len(csa_result.get("sources", [])),
                "source_doc_ids": source_ids_for_monitor(csa_result.get("sources", [])),
                "answer_has_citation": bool(csa_result.get("sources")),
                "degraded": degraded,
                "degraded_reasons": degraded_reasons,
                "latency_ms": int(elapsed * 1000),
                "model": "csa_router",
                "retrievers": {"dense_count": 0, "bm25_count": 0, "kg_count": 0},
            })
            print(f"[ASK] CSA hit | topic={csa_result['stats'].get('topic')} | 耗时 {elapsed:.3f}s")
            return jsonify(csa_result)
        if csa_result and hybrid_mode:
            print(f"[ASK] CSA partial hit | topic={csa_result['stats'].get('topic')} | continue RAG")
        if graph_first_mode:
            print("[ASK] Graph-first route | run KG paths before text retrieval")
            if "neo4j" not in allowed_sources:
                degraded = True
                degraded_reasons.append("graph_source_not_allowed")
        
        # ====== Step 1: Query Rewrite ======
        rag_q = hybrid_rag_query(q) if hybrid_mode else q
        rewrite_result = query_rewriter.rewrite(rag_q, use_llm=False)  # 先用规则模式，快速
        rewritten_q = rewrite_result.get("rewritten", rag_q)
        entities = rewrite_result.get("entities", [])
        keywords = rewrite_result.get("keywords", [])
        intent = rewrite_result.get("intent", "general")
        need_kg = rewrite_result.get("need_kg", False)
        semantic_plan = build_semantic_plan(
            q,
            route_decision=route_decision,
            rag_query=rag_q,
            intent="hybrid" if hybrid_mode else intent,
            keywords=keywords,
            entities=entities,
            csa_topic=csa_result.get("stats", {}).get("topic") if csa_result else None,
        )
        retrieval_plan = build_retrieval_plan(
            envelope,
            route_decision=route_decision,
            semantic_plan=semantic_plan,
            intent="hybrid" if hybrid_mode else intent,
            csa_topic=csa_result.get("stats", {}).get("topic") if csa_result else None,
            effective_sources=effective_sources,
        )
        need_kg = bool(
            (need_kg or semantic_plan.get("needs", {}).get("graph_reasoning"))
            and "neo4j" in allowed_sources
        )
        shadow_domain = select_shadow_domain(rag_q, semantic_plan, intent)
        shadow_future = start_shadow(rag_q, shadow_domain, trace_id, semantic_plan)
        
        print(f"[ASK] q='{rag_q[:40]}...' intent={intent} domains={semantic_plan.get('domains')} embed={embed_mode} entities={[e['name'] for e in entities]} need_kg={need_kg}")

        # ====== Step 2a: Graph-first KG Recall（先找实体/路径/chunk 证据，可降级） ======
        kg_result = {"chunk_ids": [], "paths": [], "matched_entities": [], "evidence_bindings": [], "total": 0}
        if graph_first_mode and "neo4j" in allowed_sources:
            try:
                kg_result = kg_recall.recall(entities, "graph_first", keywords, rewritten_q, semantic_plan=semantic_plan)
                print(f"[ASK] Graph-first KG: {kg_result.get('total', 0)} chunk_ids, {len(kg_result.get('paths', []))} 条路径")
                if not kg_result.get("paths"):
                    degraded = True
                    degraded_reasons.append("graph_first_no_relation_paths")
                elif not kg_result.get("chunk_ids"):
                    degraded = True
                    degraded_reasons.append("graph_first_no_sqlite_chunk_evidence")
            except Exception as e:
                degraded = True
                degraded_reasons.append(f"graph_first_kg_failed:{type(e).__name__}")
                print(f"[ASK] graph-first KG degraded: {e}")
        
        # ====== Step 2: Dense RAG (向量检索，可降级) ======
        q_emb = []
        if "dense" in allowed_sources or (
            "neo4j" in allowed_sources and not graph_first_mode
        ):
            try:
                q_emb = get_embedding(rewritten_q)
                if not q_emb:
                    raise RuntimeError("empty embedding")
            except Exception as e:
                degraded = True
                degraded_reasons.append(f"embedding_failed:{type(e).__name__}")
                print(f"[ASK] embedding degraded: {e}")

        vector_results = []
        entity_evidence = []
        dense_status = {"fresh": False, "rebuilt": False}
        if q_emb:
            if "dense" in allowed_sources:
                try:
                    dense_status = dense_index.ensure_fresh(auto_rebuild=False)
                    if not dense_status.get("fresh"):
                        degraded = True
                        degraded_reasons.append("dense_index_stale_or_missing")
                    elif dense_index.exists():
                        vector_results = dense_index.search_by_embedding(q_emb, limit=10)
                except Exception as e:
                    degraded = True
                    degraded_reasons.append(f"dense_index_failed:{type(e).__name__}")
                    print(f"[ASK] dense index degraded: {e}")

            if graph_first_mode or "neo4j" not in allowed_sources:
                entity_rows = []
            else:
                try:
                    d = get_driver()
                    with d.session() as s:
                        # 实体向量检索只作为图谱证据和 source_doc 线索，不伪装成 chunk_id
                        entity_rows = s.run("""
                            CALL db.index.vector.queryNodes('entity_embedding', 10, $e)
                            YIELD node, score WHERE node.source_doc IS NOT NULL
                            RETURN node.name AS name,
                                   coalesce([label IN labels(node) WHERE label <> 'Entity'][0], 'Entity') AS type,
                                   node.description AS description,
                                   node.source_doc AS source_doc,
                                   score
                            ORDER BY score DESC""", e=q_emb).data()
                except Exception as e:
                    degraded = True
                    degraded_reasons.append(f"entity_vector_failed:{type(e).__name__}")
                    print(f"[ASK] entity vector degraded: {e}")
                    entity_rows = []
            entity_evidence = [{
                "name": row.get("name", ""),
                "type": row.get("type", ""),
                "description": row.get("description", ""),
                "source_doc": row.get("source_doc", ""),
                "score": float(row.get("score", 0)),
            } for row in entity_rows if row.get("name")]
        
        print(f"[ASK] Dense RAG: {len(vector_results)} chunks, entity evidence={len(entity_evidence)}")
        
        # ====== Step 3: Neo4j KG Recall（按需） ======
        try:
            if need_kg and not graph_first_mode:
                kg_result = kg_recall.recall(entities, intent, keywords, rewritten_q, semantic_plan=semantic_plan)
                print(f"[ASK] KG Recall: {kg_result['total']} chunk_ids, {len(kg_result['paths'])} 条路径")
        except Exception as e:
            degraded = True
            degraded_reasons.append(f"kg_failed:{type(e).__name__}")
            print(f"[ASK] KG degraded: {e}")
        if entity_evidence:
            kg_result.setdefault("matched_entities", [])
            existing_names = {e.get("name") for e in kg_result["matched_entities"]}
            for entity in entity_evidence[:5]:
                if entity.get("name") not in existing_names:
                    kg_result["matched_entities"].append(entity)
                    existing_names.add(entity.get("name"))

        # ====== Step 3b: BM25 稀疏检索（Whoosh） ======
        sparse_results = []
        bm25_status = {"fresh": False, "rebuilt": False}
        if "bm25" in allowed_sources:
            try:
                bm25_status = bm25_index.ensure_fresh(auto_rebuild=True)
                if bm25_index.exists():
                    bm25_q = " ".join(keywords) if keywords else rewritten_q
                    sparse_results = bm25_index.search(bm25_q, limit=15)
            except Exception as e:
                degraded = True
                degraded_reasons.append(f"bm25_failed:{type(e).__name__}")
                print(f"[ASK] BM25 error: {e}")
        print(f"[ASK] BM25 sparse: {len(sparse_results)} 条")
        
        # ====== Step 4: Merge 三路融合 ======
        merged = merger.merge(
            vector_results=vector_results,
            sparse_results=sparse_results,
            kg_results=kg_result,
            keywords=keywords,
            entities=entities,
        )
        print(f"[ASK] Merge: {len(merged)} 条 (去重后)")
        
        # ====== Step 5: Context Builder ======
        ctx_result = context_builder.build(
            merged_results=merged,
            kg_paths=kg_result.get("paths", []),
            matched_entities=kg_result.get("matched_entities", []),
            query=rag_q,
            intent=intent,
            keywords=keywords,
        )

        external_search = {"status": "skipped", "errors": [], "results": []}
        external_sources = []
        external_evidence = []
        external_context = ""
        if (
            "web" in allowed_sources
            and needs_external_completion(q, ctx_result.get("sources", []), csa_result)
        ):
            external_search = run_public_search(q, count=10)
            if external_search.get("results"):
                start_seq = len(ctx_result.get("sources", [])) + 1
                external_context, external_sources, external_evidence = build_public_search_context(external_search, start_seq)
                ctx_result["context"] = f"{ctx_result['context']}\n\n{external_context}"
                ctx_result.setdefault("sources", []).extend(external_sources)
                ctx_result.setdefault("evidence", []).extend(external_evidence)
                degraded_reasons.append("internal_kb_insufficient_public_search_used")
            else:
                degraded_reasons.append("internal_kb_insufficient_public_search_empty")
            degraded = True
        
        guard_answer = build_caac_practical_score_guard_answer(q, ctx_result)
        answer_guardrail = ""
        if guard_answer:
            answer_guardrail = "unsupported_caac_practical_score_claim"
            degraded = True
            degraded_reasons.append(answer_guardrail)

        # ====== Step 6: LLM Answer ======
        if guard_answer:
            answer = guard_answer
        else:
            try:
                # 读取 API key
                with open(os.path.join(os.path.dirname(__file__), 'config.json')) as cf:
                    cfg = json.load(cf)
                    ds_key = cfg['models']['flash']['api_key']

                answer_prompt = context_builder.build_answer_prompt(
                    context=ctx_result["context"],
                    query=rag_q,
                    intent=intent,
                    evidence=ctx_result.get("evidence", []),
                    sources=ctx_result.get("sources", []),
                )
                if external_search.get("status") != "skipped":
                    answer_prompt += """

外部客户补全规则：
- 内部知识库/CSV没有充分命中时，禁止只回答“知识库没有查到”。
- 已有公开搜索结果时，先说明“内部知识库未找到明确价格”，再基于公开搜索结果补全，并用【来源N】标注。
- 公开搜索仍没有明确价格时，可用大模型行业常识给出谨慎判断或建议咨询确认，但必须明确标注“模型常识推断，非内部知识库定价”。
- 对价格、报价、上门培训等问题，回答要直接给客户可用的信息，不要把搜索任务再交还给客户。
- 禁止把现有 CAAC、多旋翼、超视距、教员、装调检修等课程价格套用到用户问的专项课程上；只有内部来源或公开搜索明确说同一课程时，才可建立价格关联。
- 如果问题是 FPV/穿越机价格，必须明确说明“内部价格表暂无单独 FPV/穿越机专项价格”；禁止说 FPV 通常属于超视距或教员级别，除非来源明确支持。"""

                body2 = json.dumps({
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "你是CAAC无人机培训知识助手。结合知识库、公开搜索和自身专业知识回答。内部来源不足时必须补全并标注来源，不能只说知识库未查到。200字左右。用【来源N】标注引用。"},
                        {"role": "user", "content": answer_prompt}
                    ],
                    "max_tokens": 600,
                    "temperature": 0.3
                }).encode()

                r2 = ureq.urlopen(ureq.Request(
                    "https://api.deepseek.com/chat/completions",
                    data=body2,
                    headers={
                        "Authorization": f"Bearer {ds_key}",
                        "Content-Type": "application/json"
                    }
                ), timeout=60)
                resp = json.loads(r2.read())
                answer = resp["choices"][0]["message"]["content"]
            except Exception as e:
                degraded = True
                reason = f"llm_failed:{type(e).__name__}"
                degraded_reasons.append(reason)
                print(f"[ASK] LLM degraded: {e}")
                answer = build_degraded_answer(ctx_result, reason)
        if hybrid_mode and csa_result:
            answer = merge_hybrid_answer(csa_result, answer)

        output_guard_answer = build_caac_practical_score_output_guard(answer, ctx_result)
        if output_guard_answer:
            answer = output_guard_answer
            answer_guardrail = "unsupported_caac_practical_score_claim"
            degraded = True
            if answer_guardrail not in degraded_reasons:
                degraded_reasons.append(answer_guardrail)
        
        elapsed = _time.time() - t0
        print(f"[ASK] ✅ 完成 | 耗时 {elapsed:.1f}s | intent={intent} | 来源={len(ctx_result.get('sources',[]))}")
        
        response_sources = ctx_result.get("sources", [])
        if hybrid_mode and csa_result:
            response_sources = csa_result.get("sources", []) + response_sources
        if guard_answer or output_guard_answer:
            response_sources = csa_result.get("sources", []) if hybrid_mode and csa_result else []
        response_sources = deduplicate_response_sources(response_sources)
        response_evidence = normalize_response_evidence(
            ctx_result.get("evidence", []),
            response_sources,
        )
        if not (guard_answer or output_guard_answer):
            answer, governance_reasons = govern_answer(
                answer,
                sources=response_sources,
                evidence=response_evidence,
                risk_level=envelope.risk_level,
            )
            if governance_reasons:
                degraded = True
                degraded_reasons.extend(
                    reason for reason in governance_reasons
                    if reason not in degraded_reasons
                )
        governance_fields = governance_response_fields(ctx_result)
        source_counts = {
            "structured": len(csa_result.get("sources", [])) if csa_result else 0,
            "dense": len(vector_results),
            "bm25": len(sparse_results),
            "kg": kg_result.get("total", 0),
            "merged": len(merged),
            "total": len(response_sources),
        }
        graph_first = graph_first_status(kg_result, response_sources) if graph_first_mode else {"enabled": False}

        response = {
            "query": q,
            "rag_query": rag_q,
            "rewritten": rewritten_q,
            "intent": "graph_first" if graph_first_mode else "hybrid" if hybrid_mode else intent,
            "route": "graph_first" if graph_first_mode else "hybrid" if hybrid_mode else "rag",
            "route_decision": route_decision,
            "request_envelope": request_contract,
            "retrieval_plan": retrieval_plan.to_dict(),
            "semantic_plan": semantic_plan,
            "graph_first": graph_first,
            "graph_paths": kg_result.get("paths", [])[:10],
            "evidence_bindings": kg_result.get("evidence_bindings", [])[:10],
            "source_counts": source_counts,
            "answer": answer,
            "sources": response_sources,
            "evidence": response_evidence[:5],
            "degraded": degraded,
            "degraded_reasons": degraded_reasons,
            **governance_fields,
                "stats": {
                    "trace_id": trace_id,
                    "request_envelope": request_contract,
                    "retrieval_plan": retrieval_plan.to_dict(),
                    "embed_mode": embed_mode,
                    "degraded": degraded,
                    "degraded_reasons": degraded_reasons,
                "external_completion": external_search.get("status") != "skipped",
                "public_search_status": external_search.get("status"),
                "public_search_results": len(external_search.get("results", [])),
                "public_search_errors": external_search.get("errors", []),
                "answer_guardrail": answer_guardrail,
                    "remote_shadow": {
                        "enabled": bool(shadow_future),
                        "domain": shadow_domain,
                        "answer_used": False,
                    },
                    "csa_hit": bool(csa_result),
                    "csa_topic": csa_result.get("stats", {}).get("topic") if csa_result else None,
                    "hybrid": bool(hybrid_mode),
                    "graph_first": bool(graph_first_mode),
                    "graph_first_ok": graph_first.get("ok") if graph_first_mode else False,
                    "graph_first_insufficient_step": graph_first.get("insufficient_step") if graph_first_mode else None,
                    "route_decision": route_decision,
                    "semantic_domains": semantic_plan.get("domains", []),
                    "source_counts": source_counts,
                    "dense_fresh": dense_status.get("fresh", False),
                "dense_rebuilt": dense_status.get("rebuilt", False),
                "bm25_fresh": bm25_status.get("fresh", False),
                "bm25_rebuilt": bm25_status.get("rebuilt", False),
                "elapsed_s": round(elapsed, 1),
                "vector_results": len(vector_results),
                "entity_evidence": len(entity_evidence),
                "sparse_results": len(sparse_results),
                "kg_results": kg_result.get("total", 0),
                "merged_results": len(merged),
                "token_estimate": ctx_result.get("token_estimate", 0),
            }
        }
        query_trace.record({
            "trace_id": trace_id,
            "route": "graph_first" if graph_first_mode else "hybrid" if hybrid_mode else "rag",
            "query": q,
            "rag_query": rag_q,
            "rewritten": rewritten_q,
            "intent": "graph_first" if graph_first_mode else "hybrid" if hybrid_mode else intent,
            "route_decision": route_decision,
            "semantic_plan": semantic_plan,
            "graph_first": graph_first,
            "keywords": keywords,
            "entities": [entity.get("name") for entity in entities],
            "need_kg": need_kg,
            "csa_topic": csa_result.get("stats", {}).get("topic") if csa_result else None,
            "elapsed_s": round(elapsed, 3),
                "degraded": degraded,
                "degraded_reasons": degraded_reasons,
                "source_count": len(response_sources),
                "top_sources": [source_name(src) for src in response_sources[:10]],
                "external_completion": external_search.get("status") != "skipped",
                "public_search_status": external_search.get("status"),
                "public_search_results": len(external_search.get("results", [])),
                "source_counts": source_counts,
                "graph_paths": kg_result.get("paths", [])[:10],
                "evidence_bindings": kg_result.get("evidence_bindings", [])[:10],
                "retriever_counts": {
                    "dense": len(vector_results),
                    "entity_evidence": len(entity_evidence),
                    "bm25": len(sparse_results),
                    "kg": kg_result.get("total", 0),
                "merged": len(merged),
            },
            "freshness": {
                "dense": dense_status.get("fresh", False),
                "bm25": bm25_status.get("fresh", False),
            },
            "remote_shadow": {
                "enabled": bool(shadow_future),
                "domain": shadow_domain,
                "answer_used": False,
            },
            "token_estimate": ctx_result.get("token_estimate", 0),
        })
        report_request_quality({
            "request_id": trace_id,
            "user_id": "openclaw_kg",
            "channel": "knowledge_graph_api",
            "question": q,
            "domain": "graph_first" if graph_first_mode else "hybrid" if hybrid_mode else intent,
            "answer_preview": answer[:240],
            "source_count": len(response_sources),
            "source_doc_ids": source_ids_for_monitor(response_sources),
            "answer_has_citation": bool(response_sources) and ("【来源" in answer or "[来源" in answer or "来源" in answer),
            "degraded": degraded,
            "degraded_reasons": degraded_reasons,
            "latency_ms": int(elapsed * 1000),
            "model": "deepseek-chat",
            "retrievers": {
                "dense_count": len(vector_results),
                "bm25_count": len(sparse_results),
                "kg_count": kg_result.get("total", 0),
            },
        })
        local_shadow_summary = summarize_local_result(
            response_sources=response_sources,
            kg_result=kg_result,
            elapsed_s=elapsed,
            retriever_counts={
                "dense": len(vector_results),
                "entity_evidence": len(entity_evidence),
                "bm25": len(sparse_results),
                "kg": kg_result.get("total", 0),
                "merged": len(merged),
            },
            degraded=degraded,
            degraded_reasons=degraded_reasons,
            answer=answer,
        )
        finish_shadow(
            shadow_future,
            trace_id=trace_id,
            query=rag_q,
            route="graph_first" if graph_first_mode else "hybrid" if hybrid_mode else "rag",
            domain=shadow_domain,
            local_summary=local_shadow_summary,
            trace_logger=remote_shadow_trace,
        )
        return jsonify(response)
    except Exception as e:
        report_request_quality({
            "request_id": trace_id,
            "user_id": "openclaw_kg",
            "channel": "knowledge_graph_api",
            "question": q,
            "domain": "error",
            "source_count": 0,
            "answer_has_citation": False,
            "degraded": True,
            "degraded_reasons": locals().get("degraded_reasons", []) + [f"ask_failed:{type(e).__name__}"],
            "latency_ms": 0,
            "model": "knowledge_graph_api",
            "error": f"{type(e).__name__}: {e}",
        })
        try:
            query_trace.record({
                "trace_id": trace_id,
                "route": "error",
                "query": q,
                "degraded": locals().get("degraded", False),
                "degraded_reasons": locals().get("degraded_reasons", []),
                "error": f"{type(e).__name__}: {e}",
            })
        except Exception:
            pass
        reason = f"ask_failed:{type(e).__name__}"
        reasons = list(locals().get("degraded_reasons", []))
        if reason not in reasons:
            reasons.append(reason)
        print(f"❌ ask: {traceback.format_exc()}")
        return jsonify({
            "query": q,
            "route": "error",
            "answer": "",
            "sources": [],
            "evidence": [],
            "error": str(e),
            "error_type": "query_failed",
            "degraded": True,
            "degraded_reasons": reasons,
            "request_envelope": request_contract,
            "stats": {
                "trace_id": trace_id,
                "degraded": True,
                "degraded_reasons": reasons,
                "request_envelope": request_contract,
            },
        }), 500

@app.route("/api/entity/<entity_id>")
def entity_detail(entity_id):
    try:
        d = get_driver()
        with d.session() as s:
            entity = s.run(
                "MATCH (n {name: $id}) RETURN n", id=entity_id
            ).data()
            if not entity:
                return jsonify({"error": "not found"}), 404
            e = entity[0]["n"]
            # 查找所有关联（不限标签）
            relations = s.run(
                "MATCH (a {name: $id})-[r]->(b) WHERE NOT b:Document "
                "RETURN b.name AS id, b.name AS name, "
                "coalesce([label IN labels(b) WHERE label <> 'Entity'][0], 'Entity') AS type, "
                "type(r) AS relation, r.description AS description LIMIT 30",
                id=entity_id
            ).data()
            incoming = s.run(
                "MATCH (s)-[r]->(a {name: $id}) WHERE NOT s:Document "
                "RETURN s.name AS id, s.name AS name, "
                "coalesce([label IN labels(s) WHERE label <> 'Entity'][0], 'Entity') AS type, "
                "type(r) AS relation, r.description AS description LIMIT 30",
                id=entity_id
            ).data()
        return jsonify({
            "entity": {"id": entity_id, "name": e.get("name",""), "type": node_primary_type(e),
                       "description": e.get("description","")},
            "outgoing": relations, "incoming": incoming
        })
    except Exception as e:
        return api_error(e, "entity_detail")

@app.route("/api/presentation/<route_name>")
def presentation_route(route_name):
    routes = {
        "company": {
            "name": "公司实力展示",
            "steps": [
                {"query": "云技科技", "label": "公司简介"},
                {"query": "甲级|资质|中国民航局|考点|民航", "label": "资质证书"},
                {"query": "武汉大学|华中师范|硚口|政府|城运|交管局|外企", "label": "合作机构"},
                {"query": "培训|实训|模拟|技能|教学", "label": "培训基地"},
                {"query": "就业|人才|北京外企|城运|企业", "label": "就业合作"},
                {"query": "价格表|兴趣爱好班|飞手考证班|精英教员就业班", "label": "课程与定价"}
            ]
        },
        "caac_theory": {
            "name": "CAAC理论知识",
            "steps": [
                {"query": "CAAC理论考试", "label": "考试总览"},
                {"query": "气象|大气|风|能见度|云|露点", "label": "气象知识"},
                {"query": "无人机飞行手册|法律法规|法规|空域|管理|飞行管理|飞行暂行条例", "label": "法规与手册"},
                {"query": "系统组成|电机|电调|电池|螺旋桨|传感器|飞控|IMU|GPS|陀螺仪|地面站", "label": "系统组成"},
                {"query": "自由度|前飞|悬停|偏航|转弯|俯仰|航向|反扭矩", "label": "旋翼无人机特性"},
                {"query": "飞行原理|升力|阻力|配平|动力|桨叶|翼", "label": "飞行原理"},
                {"query": "任务规划|航线|规划|载荷", "label": "任务规划"},
                {"query": "操作规范|操作注意事项|飞行安全|应急|失控保护|校准", "label": "操作规范"},
                {"query": "空中交通|管制|进离场|净空|高度层|防撞灯", "label": "空中交通管制"},
                {"query": "CAAC实操考试|悬停|八字|电子桩|360°自旋", "label": "实操考试"},
                {"query": "教员考点|教学|授课|教案|训练|模拟器|测评|学员", "label": "教员知识"}
            ]
        },
        "products": {
            "name": "产品服务展示",
            "steps": [
                {"query": "兴趣爱好班|飞手考证班|CAAC无人机考证培训|CAAC无人机执照|执照培训|考证", "label": "核心培训"},
                {"query": "设备维修进阶班|植保吊运班|智慧城市班|装调检修班|实训|多行业|航拍|植保|吊运|幕墙|软件工程", "label": "实训课程"},
                {"query": "双机长专业能力进阶班|多旋翼教员考证班|垂起教员考证班|精英教员就业班|SkillMatrix|教学平台|智能", "label": "教学与教员"},
                {"query": "就业指导|就业服务|一对一|价格表", "label": "就业服务与定价"}
            ]
        }
    }
    if route_name not in routes:
        return jsonify({"error": "route not found"}), 404
    route = routes[route_name]
    try:
        d = get_driver()
        with d.session() as s:
            for step in route["steps"]:
                terms = [t.strip() for t in step["query"].split("|") if t.strip()]
                if not terms:
                    step["results"] = []
                    continue
                # 公司路线优先精确匹配公司主体，避免 CONTAINS "云技科技" 命中过多无关实体；其余步骤按名称去重。
                if route_name == "company" and step["label"] == "公司简介":
                    results = s.run(
                        "MATCH (e:Entity) WHERE e.name IN ['湖北云技科技有限公司', '云技科技'] "
                        "OR e.name STARTS WITH '湖北云技科技有限公司' "
                        "WITH e.name AS name, collect(e)[0] AS e "
                        "RETURN e.id AS id, name, e.type AS type, "
                        "e.description AS description LIMIT 8"
                    ).data()
                else:
                    conditions = " OR ".join([f"e.name CONTAINS $t{i}" for i in range(len(terms))])
                    params = {f"t{i}": terms[i] for i in range(len(terms))}
                    results = s.run(
                        f"MATCH (e:Entity) WHERE {conditions} "
                        "WITH e.name AS name, collect(e)[0] AS e "
                        "RETURN e.id AS id, name, e.type AS type, "
                        "e.description AS description LIMIT 8",
                        **params
                    ).data()
                step["results"] = results
        return jsonify(route)
    except Exception as e:
        return api_error(e, "presentation")

@app.route("/api/cypher", methods=["POST"])
def run_cypher():
    """Neo4j Browser 风格的 Cypher 直接查询（只读）"""
    data = request.json or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "query required"}), 400
    if not re.match(r'^\s*(MATCH|CALL|SHOW|RETURN|EXPLAIN|PROFILE)', query, re.IGNORECASE):
        return jsonify({"error": "仅支持只读查询（MATCH/CALL/SHOW/RETURN）"}), 403
    try:
        d = get_driver()
        with d.session() as s:
            results = s.run(query).data()
        return jsonify({"columns": list(results[0].keys()) if results else [],
                        "data": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/entity", methods=["POST"])
def create_entity():
    data = request.json or {}
    if not data.get("name"):
        return jsonify({"error": "name required"}), 400
    eid = f"manual_{uuid.uuid4().hex[:12]}"
    try:
        d = get_driver()
        with d.session() as s:
            s.run(
                "CREATE (e:Entity {id: $id, name: $name, type: $type, "
                "description: $desc, level: 'manual', imported_at: datetime()})",
                id=eid, name=data["name"], type=data.get("type", "Unknown"),
                desc=data.get("description", "")
            )
        return jsonify({"id": eid, "name": data["name"]}), 201
    except Exception as e:
        return api_error(e, "create_entity")

@app.route("/api/entity/<entity_id>", methods=["PUT"])
def update_entity(entity_id):
    data = request.json or {}
    sets = []
    params = {"id": entity_id}
    for field in ["name", "type", "description"]:
        if field in data:
            sets.append(f"e.{field} = ${field}")
            params[field] = data[field]
    if not sets:
        return jsonify({"error": "no fields to update"}), 400
    try:
        d = get_driver()
        with d.session() as s:
            s.run(f"MATCH (e:Entity {{id: $id}}) SET {', '.join(sets)}", **params)
        return jsonify({"status": "ok"})
    except Exception as e:
        return api_error(e, "update_entity")

@app.route("/api/entity/<entity_id>", methods=["DELETE"])
def delete_entity(entity_id):
    try:
        d = get_driver()
        with d.session() as s:
            # 先按id匹配（任意标签，不限制:Entity）
            result = s.run("MATCH (e {id: $id}) DETACH DELETE e RETURN count(*) as cnt", id=entity_id)
            cnt = result.single()["cnt"]
            if cnt == 0:
                # 用name兜底（任意标签）
                result = s.run("MATCH (e {name: $name}) DETACH DELETE e RETURN count(*) as cnt", name=entity_id)
                cnt = result.single()["cnt"]
            return jsonify({"status": "ok", "deleted": cnt})
    except Exception as e:
        return api_error(e, "delete_entity")

@app.route("/api/edge", methods=["POST"])
def create_edge():
    data = request.json or {}
    if not data.get("from_id") or not data.get("to_id") or not data.get("type"):
        return jsonify({"error": "from_id, to_id, type required"}), 400
    rtype = safe_rel_type(data["type"])
    try:
        d = get_driver()
        with d.session() as s:
            s.run(
                f"MATCH (a:Entity {{id: $from_id}}) MATCH (b:Entity {{id: $to_id}}) "
                f"MERGE (a)-[:{rtype} {{description: $desc}}]->(b)",
                from_id=data["from_id"], to_id=data["to_id"], desc=data.get("description", "")
            )
        return jsonify({"status": "ok", "type": rtype}), 201
    except Exception as e:
        return api_error(e, "create_edge")

@app.route("/api/edge", methods=["DELETE"])
def delete_edge():
    data = request.json or {}
    if not data.get("from_id") or not data.get("to_id") or not data.get("type"):
        return jsonify({"error": "from_id, to_id, type required"}), 400
    rtype = safe_rel_type(data["type"])
    try:
        d = get_driver()
        with d.session() as s:
            s.run(
                f"MATCH (a {{id: $from_id}})-[r:{rtype}]->(b {{id: $to_id}}) DELETE r",
                from_id=data["from_id"], to_id=data["to_id"]
            )
        return jsonify({"status": "ok"})
    except Exception as e:
        return api_error(e, "delete_edge")

@app.route("/api/export")
def export_data():
    """导出图谱为 JSON"""
    try:
        d = get_driver()
        with d.session() as s:
            nodes = s.run("MATCH (e:Entity) RETURN e").data()
            rels = s.run("MATCH (a:Entity)-[r]->(b:Entity) RETURN a.id AS from, b.id AS to, type(r) AS type").data()
        return jsonify({
            "exported_at": str(__import__('datetime').datetime.now()),
            "nodes": [dict(n["e"]) for n in nodes],
            "edges": rels,
        })
    except Exception as e:
        return api_error(e, "export")

# ============ 3D 知识图谱 API ============

@app.route("/api/graph-3d")
def graph_3d():
    """返回所有节点和关系，用于 3D 可视化"""
    try:
        d = get_driver()
        with d.session() as s:
            # 批量查询所有节点（排除 embedding 大字段）
            all_nodes = s.run(
                "MATCH (n) WHERE NOT n:Document OR n.embedding IS NOT NULL "
                "RETURN coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity') AS label, "
                "coalesce(n.name, n.id, toString(id(n))) AS uid, "
                "n.name AS name, n.price AS price, n.duration AS duration, "
                "n.description AS description, n.content AS content, "
                "n.source_doc AS source_doc, n.category AS category"
            ).data()

            # 查询所有关系（直接用 name 关联）
            all_edges = s.run(
                "MATCH (a)-[r]->(b) "
                "RETURN coalesce(a.id, a.name) AS from_uid, coalesce(b.id, b.name) AS to_uid, "
                "type(r) AS rel_type, r.description AS rel_desc"
            ).data()

        # 标签颜色方案
        color_palette = [
            "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
            "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
            "#469990", "#dcbeff", "#9A6324", "#fffac8", "#800000",
            "#aaffc3", "#808000", "#ffd8b1", "#000075", "#a9a9a9"
        ]
        type_colors = {}
        seen_types = set()
        for row in all_nodes:
            seen_types.add(row["label"])
        all_labels = sorted(seen_types)
        for i, lbl in enumerate(all_labels):
            type_colors[lbl] = color_palette[i % len(color_palette)]

        seen_ids = set()
        nodes_out = []
        for row in all_nodes:
            uid = row["uid"]
            if not uid or uid in seen_ids:
                continue
            seen_ids.add(uid)
            lbl = row["label"]
            props = {}
            for k in ['price','duration','description','content','source_doc','category']:
                if row.get(k):
                    props[k] = row[k]
            nodes_out.append({
                "id": uid,
                "label": row.get("name") or uid,
                "type": lbl,
                "color": type_colors.get(lbl, "#cccccc"),
                "properties": props
            })

        edges_out = []
        seen_edges = set()
        for row in all_edges:
            from_uid = row.get("from_uid", "")
            to_uid = row.get("to_uid", "")
            if not from_uid or not to_uid:
                continue
            edge_key = f"{from_uid}|{to_uid}|{row['rel_type']}"
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges_out.append({
                "from": from_uid,
                "to": to_uid,
                "label": row["rel_type"]
            })

        return jsonify({
            "nodes": nodes_out,
            "edges": edges_out
        })
    except Exception as e:
        return api_error(e, "graph_3d")


@app.route("/api/node", methods=["POST"])
def create_node_3d():
    """创建节点（任意标签）"""
    data = request.json or {}
    name = data.get("name", "").strip()
    label = data.get("type", "Unknown").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', label):
        return jsonify({"error": "invalid label name"}), 400

    # 清理属性，只保留安全字段
    props = data.get("properties", {})
    safe_props = {"name": name}
    for k, v in props.items():
        k_clean = re.sub(r'[^a-zA-Z0-9_]', '_', k)
        if k_clean and isinstance(v, (str, int, float, bool)):
            safe_props[k_clean] = str(v)

    try:
        d = get_driver()
        with d.session() as s:
            s.run(
                f"CREATE (n:{label} {{name: $name}})", name=name
            )
            # 设置额外属性
            for k, v in safe_props.items():
                if k != "name":
                    s.run(f"MATCH (n:{label} {{name: $name}}) SET n.{k} = $v", name=name, v=v)
        return jsonify({"id": name, "name": name, "type": label}), 201
    except Exception as e:
        return api_error(e, "create_node_3d")


@app.route("/api/node/<node_id>", methods=["PUT"])
def update_node_3d(node_id):
    """更新任意标签的节点属性"""
    data = request.json or {}
    sets = []
    params = {"id": node_id}
    for field in ["name", "description"]:
        if field in data:
            sets.append(f"n.{field} = ${field}")
            params[field] = data[field]
    # 支持更新 properties 字典中的字段
    if "properties" in data:
        for k, v in data["properties"].items():
            k_clean = re.sub(r'[^a-zA-Z0-9_]', '_', k)
            if k_clean and k_clean not in ("id",):
                sets.append(f"n.{k_clean} = ${k_clean}")
                params[k_clean] = str(v) if not isinstance(v, (int, float, bool)) else v
    if not sets:
        return jsonify({"error": "no fields to update"}), 400
    try:
        d = get_driver()
        with d.session() as s:
            s.run(f"MATCH (n {{name: $name}}) SET {', '.join(sets)}", **params, name=node_id)
        return jsonify({"status": "ok"})
    except Exception as e:
        return api_error(e, "update_node_3d")


@app.route("/api/node/<node_id>", methods=["DELETE"])
def delete_node_3d(node_id):
    """删除任意标签的节点"""
    try:
        d = get_driver()
        with d.session() as s:
            result = s.run("MATCH (n {name: $name}) DETACH DELETE n RETURN count(*) as cnt", name=node_id)
            cnt = result.single()["cnt"]
            return jsonify({"status": "ok", "deleted": cnt})
    except Exception as e:
        return api_error(e, "delete_node_3d")


@app.route("/api/edge-3d", methods=["POST"])
def create_edge_3d():
    """创建关系（任意标签节点间）"""
    data = request.json or {}
    from_id = data.get("from", "").strip()
    to_id = data.get("to", "").strip()
    rel_type = data.get("label", "").strip().upper()
    if not from_id or not to_id or not rel_type:
        return jsonify({"error": "from, to, label required"}), 400
    # 净化关系类型
    rel_type = re.sub(r'[^a-zA-Z0-9_]', '_', rel_type).upper()
    if not rel_type:
        return jsonify({"error": "invalid relationship type"}), 400
    try:
        d = get_driver()
        with d.session() as s:
            # 尝试用 id 匹配
            summary = s.run(
                f"MATCH (a {{id: $fid}}) MATCH (b {{id: $tid}}) "
                f"MERGE (a)-[:{rel_type}]->(b)",
                fid=from_id, tid=to_id
            ).consume()
            # 检查是否创建了关系（计数器 > 0 表示 MATCH 成功）
            if summary.counters.contains_updates == False:
                # 用 name 兜底
                s.run(
                    f"MATCH (a {{name: $fid}}) MATCH (b {{name: $tid}}) "
                    f"MERGE (a)-[:{rel_type}]->(b)",
                    fid=from_id, tid=to_id
                )
        return jsonify({"status": "ok", "type": rel_type}), 201
    except Exception as e:
        return api_error(e, "create_edge_3d")


@app.route("/api/edge-3d", methods=["DELETE"])
def delete_edge_3d():
    """删除关系"""
    data = request.json or {}
    from_id = data.get("from", "").strip()
    to_id = data.get("to", "").strip()
    rel_type = data.get("label", "").strip().upper()
    if not from_id or not to_id or not rel_type:
        return jsonify({"error": "from, to, label required"}), 400
    rel_type = re.sub(r'[^a-zA-Z0-9_]', '_', rel_type).upper()
    try:
        d = get_driver()
        with d.session() as s:
            summary = s.run(
                f"MATCH (a {{name: $fid}})-[r:{rel_type}]->(b {{name: $tid}}) DELETE r RETURN count(r) AS cnt",
                fid=from_id, tid=to_id
            )
            cnt = summary.single()["cnt"]
            return jsonify({"status": "ok", "deleted": cnt})
    except Exception as e:
        return api_error(e, "delete_edge_3d")


# ============ 语义搜索 API (RAG) ============


# ============ 启动 ============
if __name__ == "__main__":
    print("🚀 云技知识图谱面板 v2 启动")
    print("   展示: http://localhost:5001")
    print("   API:  http://localhost:5001/api/health")
    app.run(host="0.0.0.0", port=5001, debug=False)
