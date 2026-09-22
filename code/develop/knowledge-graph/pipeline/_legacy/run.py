#!/usr/bin/env python3
"""
知识图谱抽取 v2.1 — 交叉审查 + 来源追溯版
DeepSeek + GPT 5.5 双模型独立抽取 → 交叉比对 → 一致入库（带原文片段 + 飞书链接）
不一致 → 报告等老文确认
"""

import json, os, re, sys, time, difflib
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    os.system("pip3 install requests"); import requests
try:
    from neo4j import GraphDatabase
except ImportError:
    os.system("pip3 install neo4j"); from neo4j import GraphDatabase

# ============ 配置 ============
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = Path(__file__).parent / "config.json"
NEO4J_PASS_PATH = BASE_DIR / "neo4j" / ".neo4j_pass"
REPORT_DIR = BASE_DIR / "review_reports"
META_DIR = BASE_DIR / "feishu_raw" / "_meta"  # 文件元数据

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = NEO4J_PASS_PATH.read_text().strip() if NEO4J_PASS_PATH.exists() else ""

os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)

EXTRACT_PROMPT = """你是一个知识图谱实体抽取专家。请从以下公司文档中提取实体和关系。

## 实体类型定义
- Organization: 组织/公司/部门
- Person: 角色/岗位
- Policy: 制度/规定/流程
- Product: 产品/服务/课程
- Event: 活动/培训/会议
- Document: 文档/手册

## 关系类型定义（至少使用以下7种）
- belongs_to: 属于（人→部门，制度→公司）
- contains: 包含（手册→章节）
- references: 引用（制度→手册）
- required_by: 要求（制度→岗位）
- manages: 管理（人→部门）
- regulates: 规范（制度→行为）
- provides: 提供（公司→产品）

## 输出格式
返回 JSON 格式，严格如下：
{
  "entities": [
    {"id": "ent_1", "name": "实体名称", "type": "类型", "description": "简短描述"}
  ],
  "relations": [
    {"from_id": "ent_1", "to_id": "ent_2", "type": "关系类型", "description": "关系描述"}
  ]
}

请仔细分析文档，提取所有有意义的实体和关系，尽可能完整。"""


# ============ 工具函数 ============

def load_meta(txt_path: str) -> dict:
    """加载文本文件对应的飞书元数据"""
    name = Path(txt_path).stem
    meta_path = META_DIR / f"{name}.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {"doc_name": name, "doc_url": "", "doc_token": ""}

def extract_source_chunks(text: str, entity_names: list, context_chars: int = 150) -> dict:
    """从原文中提取每个实体名周围的原文片段
    
    返回: { entity_name: "原文片段..." }
    """
    result = {}
    for name in entity_names:
        if not name:
            continue
        # 在原文中找这个名字的出现位置
        idx = text.find(name)
        if idx >= 0:
            start = max(0, idx - context_chars)
            end = min(len(text), idx + len(name) + context_chars)
            chunk = text[start:end]
            # 在前后补齐到句子边界
            chunk = re.sub(r'^[^。；\n]*?。', '', chunk) if start > 0 else chunk
            if len(chunk) > 400:
                # 太长就截断到完整句子
                chunk = chunk[:397] + "..."
            result[name] = chunk.strip()
    return result


# ============ LLM 调用 ============

def call_llm(document_text: str, doc_name: str, level: str, doc_source: str = "") -> dict:
    cfg = CONFIG["models"][level]
    timeout = cfg["timeout"]
    
    src = f"\n## 来源：{doc_source}" if doc_source else ""
    prompt = EXTRACT_PROMPT + f"\n\n## 文档名称：{doc_name}{src}\n\n## 文档内容\n{document_text}"
    
    payload = {
        "model": cfg["name"],
        "messages": [
            {"role": "system", "content": "你是一个知识图谱构建专家。只输出纯JSON，不要markdown格式，不要```代码块标记，不要任何其他文字。"},
            {"role": "user", "content": prompt[:20000]}
        ],
        "temperature": 0.1,
        "max_tokens": cfg.get("max_tokens", 8192)
    }
    if "v4-flash" in cfg["name"]:
        payload["reasoning_effort"] = "low"
    
    # 构建代理列表：full级别支持多中转，其他级别用单地址
    proxies = cfg.get("proxies", [])
    if not proxies:
        proxies = [{"base_url": cfg["base_url"], "api_key": cfg["api_key"]}]
    
    total_start = time.time()
    last_error = ""
    
    for idx, proxy in enumerate(proxies):
        start = time.time()
        base_url = proxy["base_url"]
        api_key = proxy["api_key"]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        proxy_label = proxy.get("description", f"代理{idx+1}")
        proxy_timeout = proxy.get("timeout", timeout)  # 优先使用代理自己的超时
        
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers=headers, json=payload, timeout=(15, proxy_timeout)
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            elapsed = time.time() - start
            # 更健壮的JSON提取：找第一个 { 和最后一个 }
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx > start_idx:
                try:
                    result = json.loads(content[start_idx:end_idx+1])
                    print(f"  ✅ [{level.upper()}] {cfg['name']}({proxy_label}) → {len(result.get('entities',[]))}实体 {len(result.get('relations',[]))}关系 ({elapsed:.1f}s)")
                    return result
                except json.JSONDecodeError as je:
                    print(f"  ⚠️ [{level.upper()}] {proxy_label}: JSON解析异常: {je}")
                    last_error = str(je)
                    continue
            else:
                print(f"  ⚠️ [{level.upper()}] {proxy_label}: 未找到JSON")
                last_error = "未找到JSON"
                continue
        except Exception as e:
            total_used = time.time() - total_start
            print(f"  ❌ [{level.upper()}] {proxy_label}: {e} ({time.time()-start:.0f}s)")
            last_error = str(e)
            # 还有代理就继续重试
            if idx < len(proxies) - 1:
                print(f"     ↳ 切换到下一个代理...")
                continue
            else:
                print(f"  ❌ [{level.upper()}] 全部代理失败 ({total_used:.0f}s)")
                return {"entities": [], "relations": []}
    
    print(f"  ❌ [{level.upper()}] 全部代理失败: {last_error}")
    return {"entities": [], "relations": []}


# ============ 交叉审查 ============

def normalize(name: str) -> str:
    return re.sub(r'\s+', '', name).strip().lower()

def name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()

def cross_review_entities(ds_ents: list, gpt_ents: list):
    confirmed, pending = [], []
    ds_map = {}
    for e in ds_ents:
        n = normalize(e.get("name", ""))
        if n: ds_map[n] = e
    gpt_map = {}
    for e in gpt_ents:
        n = normalize(e.get("name", ""))
        if n: gpt_map[n] = e

    all_names = set(list(ds_map.keys()) + list(gpt_map.keys()))
    
    # 先模糊匹配补充
    matched_gpt = set()
    matched_ds = set()
    for name in sorted(all_names):
        ds_e = ds_map.get(name)
        gpt_e = gpt_map.get(name)
        if ds_e and not gpt_e:
            for gn, ge in gpt_map.items():
                if gn in matched_gpt: continue
                if name_similarity(ds_e.get("name",""), ge.get("name","")) >= 0.65:
                    gpt_map[name] = ge
                    matched_gpt.add(gn)
                    break
        if gpt_e and not ds_e:
            for dn, de in ds_map.items():
                if dn in matched_ds: continue
                if name_similarity(gpt_e.get("name",""), de.get("name","")) >= 0.65:
                    ds_map[name] = de
                    matched_ds.add(dn)
                    break

    # 正式比对
    for name in sorted(set(list(ds_map.keys()) + list(gpt_map.keys()))):
        ds_e = ds_map.get(name)
        gpt_e = gpt_map.get(name)
        if ds_e and gpt_e:
            if ds_e.get("type") == gpt_e.get("type"):
                confirmed.append({
                    "name": ds_e["name"],
                    "type": ds_e["type"],
                    "description": ds_e.get("description","") or gpt_e.get("description",""),
                    "source": "cross_reviewed"
                })
            else:
                pending.append({
                    "type": "entity", "name": ds_e["name"],
                    "issue": "类型不一致",
                    "detail": f"DeepSeek: {ds_e['type']} | GPT: {gpt_e['type']}",
                    "ds": ds_e, "gpt": gpt_e
                })
        elif ds_e and not gpt_e:
            pending.append({
                "type": "entity", "name": ds_e["name"],
                "issue": "仅 DeepSeek", "detail": "GPT 5.5 未提取",
                "ds": ds_e, "gpt": None
            })
        elif not ds_e and gpt_e:
            pending.append({
                "type": "entity", "name": gpt_e["name"],
                "issue": "仅 GPT 5.5", "detail": "DeepSeek 未提取",
                "ds": None, "gpt": gpt_e
            })

    return confirmed, pending


def cross_review_relations(ds_rels: list, gpt_rels: list):
    confirmed, pending = [], []
    def rk(r):
        return (normalize(r.get("from_id","")), normalize(r.get("to_id","")), normalize(r.get("type","")))
    ds_set = {rk(r): r for r in ds_rels}
    gpt_set = {rk(r): r for r in gpt_rels}
    all_keys = set(list(ds_set.keys()) + list(gpt_set.keys()))
    for key in sorted(all_keys):
        ds_r = ds_set.get(key); gpt_r = gpt_set.get(key)
        if ds_r and gpt_r:
            confirmed.append({
                "from_id": ds_r["from_id"], "to_id": ds_r["to_id"],
                "type": ds_r["type"],
                "description": ds_r.get("description","") or gpt_r.get("description",""),
                "source": "cross_reviewed"
            })
        elif ds_r and not gpt_r:
            pending.append({
                "type": "relation", "from_id": ds_r["from_id"], "to_id": ds_r["to_id"],
                "rel_type": ds_r["type"], "issue": "仅 DeepSeek",
                "ds": ds_r, "gpt": None
            })
        elif not ds_r and gpt_r:
            pending.append({
                "type": "relation", "from_id": gpt_r["from_id"], "to_id": gpt_r["to_id"],
                "rel_type": gpt_r["type"], "issue": "仅 GPT 5.5",
                "ds": None, "gpt": gpt_r
            })
    return confirmed, pending


# ============ Neo4j 写入（含来源追溯） ============

def write_confirmed(doc_name: str, confirmed: dict, doc_url: str = "", source_chunks: dict = None):
    """
    写入双方确认的实体和关系到 Neo4j
    每条实体附带: source_chunk, doc_name, doc_url
    """
    entities = confirmed.get("entities", [])
    relations = confirmed.get("relations", [])
    if not entities:
        print("  ℹ️ 无确认实体，跳过写入")
        return

    if source_chunks is None:
        source_chunks = {}

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database="neo4j") as session:
        # 1) 文档节点
        session.run(
            "MERGE (d:Document {name: $name}) "
            "SET d.level = 'cross_reviewed', d.verified = true, "
            "    d.doc_url = $url, "
            "    d.imported_at = datetime()",
            name=doc_name, url=doc_url
        )

        # 2) 实体（带来源片段和文档链接）
        name_to_ent = {}  # 名 → eid 映射
        for i, ent in enumerate(entities):
            eid = f"{doc_name[:6]}_{i+1}"
            ename = ent.get("name", "")
            etype = ent.get("type", "Unknown")
            edesc = ent.get("description", "")
            echunk = source_chunks.get(ename, "")

            session.run(
                "MERGE (e:Entity {id: $eid}) "
                "SET e.name = $name, e.type = $type, "
                "    e.description = $desc, "
                "    e.source_chunk = $chunk, "
                "    e.source_doc = $doc_name, "
                "    e.doc_url = $doc_url, "
                "    e.verified = true, "
                "    e.imported_at = datetime()",
                eid=eid, name=ename, type=etype,
                desc=edesc, chunk=echunk,
                doc_name=doc_name, doc_url=doc_url
            )
            # 文档→实体关联
            session.run(
                "MATCH (d:Document {name: $dn}) "
                "MATCH (e:Entity {id: $eid}) "
                "MERGE (d)-[:CONTAINS]->(e)",
                dn=doc_name, eid=eid
            )
            name_to_ent[ename] = eid

        # 3) 关系
        for rel in relations:
            from_name = rel.get("from_id", "")
            to_name = rel.get("to_id", "")
            from_eid = name_to_ent.get(from_name, from_name)
            to_eid = name_to_ent.get(to_name, to_name)
            rtype = re.sub(r'[^a-zA-Z_]', '_', rel.get("type","RELATED_TO")).upper()
            try:
                session.run(
                    f"MATCH (a:Entity {{id: $fid}}) "
                    f"MATCH (b:Entity {{id: $tid}}) "
                    f"MERGE (a)-[r:{rtype}]->(b) "
                    f"SET r.description = $desc, r.source_doc = $doc_name",
                    fid=from_eid, tid=to_eid,
                    desc=rel.get("description",""), doc_name=doc_name
                )
            except Exception as e:
                print(f"  ⚠️ 关系失败: {from_eid} → {rtype} → {to_eid}: {e}")

    driver.close()
    print(f"  ✅ 入库完成: {len(entities)}实体(含来源) {len(relations)}关系")
    # 打印样本
    if entities:
        s = entities[0]
        chk = source_chunks.get(s.get("name",""), "")
        print(f"     样本: 「{s['name']}」→ {chk[:60]}..." if chk else f"     样本: 「{s['name']}」(无原文)")


# ============ 审查报告 ============

def generate_review_report(doc_name: str, confirmed: dict, pending: dict, 
                           ds_time: float, gpt_time: float) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ce = len(confirmed.get("entities",[]))
    cr = len(confirmed.get("relations",[]))
    pe = len(pending.get("entities",[]))
    pr = len(pending.get("relations",[]))

    lines = [
        f"📋 交叉审查报告 — {doc_name}",
        f"   时间: {now}",
        f"   DeepSeek: {ds_time:.1f}s | GPT 5.5: {gpt_time:.1f}s",
        "",
        f"✅ 自动确认: {ce} 实体, {cr} 关系",
        f"⚠️ 待你确认: {pe} 实体, {pr} 关系",
        "",
    ]
    if pe > 0 or pr > 0:
        lines.append("=" * 50)
        lines.append("⚠️ 以下内容需要你手动确认：")
        lines.append("=" * 50)
        lines.append("")
        for item in pending.get("entities",[]):
            lines.append(f"【实体】{item['name']}")
            lines.append(f"  问题: {item['issue']}")
            lines.append(f"  详情: {item['detail']}")
            if item.get("ds"):
                lines.append(f"  DeepSeek: {item['ds'].get('type','?')} | {item['ds'].get('description','')}")
            if item.get("gpt"):
                lines.append(f"  GPT 5.5: {item['gpt'].get('type','?')} | {item['gpt'].get('description','')}")
            lines.append("")
        for item in pending.get("relations",[]):
            lines.append(f"【关系】{item['from_id']} → [{item['rel_type']}] → {item['to_id']}")
            lines.append(f"  问题: {item['issue']}")
            lines.append("")
        lines.append("=" * 50)
        lines.append("回复格式:")
        lines.append("  [确认] 实体名1, 实体名2")
        lines.append("  [拒绝] 实体名1")
        lines.append("  [修改] 实体名 → Policy")
        lines.append("  [全部确认]")
        lines.append("=" * 50)

    return "\n".join(lines)


# ============ 主流程 ============

def cross_review_extract(file_path: str, doc_name: str = None, doc_source: str = "", doc_url: str = "", fast_mode: bool = True):
    """
    知识图谱抽取
    
    规则（2026-05-18 老文确认）：
    - fast_mode=True（默认/定时任务）: 仅 DeepSeek Pro，自动入库
    - fast_mode=False（手动指定）: DeepSeek Pro + GPT 5.5，结果先确认再入库
    """
    if doc_name is None:
        doc_name = Path(file_path).stem

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 尝试加载元数据（飞书链接等）
    meta = load_meta(file_path)
    if doc_url:
        meta["doc_url"] = doc_url
    if not meta.get("doc_name"):
        meta["doc_name"] = doc_name

    print(f"\n{'='*50}")
    print(f"📄 {doc_name} ({len(content)} 字符)")
    if meta.get("doc_url"):
        print(f"   来源: {meta['doc_url']}")
    print(f"{'='*50}")

    # 1) DeepSeek Pro（始终运行）
    print("┌─ DeepSeek Pro 抽取中 ────────┐")
    t0 = time.time()
    ds_result = call_llm(content, doc_name, "fast", doc_source)
    ds_time = time.time() - t0
    ds_has_data = len(ds_result.get("entities", [])) > 0
    print(f"  DeepSeek: {len(ds_result.get('entities',[]))}实体 {len(ds_result.get('relations',[]))}关系")
    print("└────────────────────────────────┘")

    if fast_mode:
        # 快速模式（默认/定时任务）：仅 DeepSeek Pro，自动入库
        use_model = "DeepSeek Pro"
        entities = ds_result.get("entities", [])
        relations = ds_result.get("relations", [])
        if entities:
            print(f"  ✅ 自动入库: {len(entities)}实体 {len(relations)}关系")
            source_chunks = extract_source_chunks(content, [e["name"] for e in entities])
            write_confirmed(doc_name, {"entities": entities, "relations": relations},
                          doc_url=meta.get("doc_url",""), source_chunks=source_chunks)
            print(f"  ✅ 入库完成 ({use_model})")
        else:
            print("  ⏭️ DeepSeek 无返回")
        return {"entities": entities, "relations": relations}, {}, meta

    # ===== 交叉模式（仅你主动要求时）=====
    # 2) GPT 5.5
    print("┌─ GPT 5.5 抽取中 ─────────────┐")
    t0 = time.time()
    gpt_result = call_llm(content, doc_name, "full", doc_source)
    gpt_time = time.time() - t0
    gpt_has_data = len(gpt_result.get("entities", [])) > 0
    print(f"  GPT: {len(gpt_result.get('entities',[]))}实体 {len(gpt_result.get('relations',[]))}关系")
    print("└────────────────────────────────┘")

    # 3) 选择：GPT优先，失败则用DeepSeek
    print("┌─ 选择结果（需你确认）─────────┐")
    if gpt_has_data:
        use_model = "GPT 5.5"
        entities = gpt_result.get("entities", [])
        relations = gpt_result.get("relations", [])
        print(f"  ✅ GPT正常返回 → 建议以GPT为准 ({len(entities)}实体 {len(relations)}关系)")
    elif ds_has_data:
        use_model = "DeepSeek Pro"
        entities = ds_result.get("entities", [])
        relations = ds_result.get("relations", [])
        print(f"  🔄 GPT无响应 → 建议降级 DeepSeek Pro ({len(entities)}实体 {len(relations)}关系)")
    else:
        print("  ❌ 两个模型均无返回")
        return {}, {}, meta
    
    source_chunks = extract_source_chunks(content, [e["name"] for e in entities])
    print(f"  📎 原文片段: {len(source_chunks)}/{len(entities)} 实体有匹配")
    print("   ⏳ 等待你确认后再入库...")
    print("   输入 [确认] 入库，[拒绝] 放弃")
    print("└────────────────────────────────┘")
    
    # 保存审查报告供查看
    report_path = REPORT_DIR / f"{doc_name}_cross_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_text = f"""文档: {doc_name}
模型: {use_model}
实体数: {len(entities)}
关系数: {len(relations)}

请确认是否入库：
- 输入 [确认] → 入库
- 输入 [拒绝] → 放弃
"""
    report_path.write_text(report_text, encoding="utf-8")
    print(f"  报告: {report_path}")
    
    return {"entities": entities, "relations": relations, "pending_confirm": True}, {}, meta


def scan_and_process():
    """批量处理 feishu_raw/"""
    raw_dir = BASE_DIR / "feishu_raw"
    if not raw_dir.exists():
        print(f"❌ 未找到: {raw_dir}"); return

    files = sorted(raw_dir.glob("*.txt"))
    files = [f for f in files if not f.name.endswith("_result.json") and f.parent.name != "_meta"]
    
    if not files:
        print("📭 无待处理文档"); return

    print(f"📊 发现 {len(files)} 份文档")
    for fp in files:
        cross_review_extract(str(fp))
        print()


# ============ 查询助手 ============

def query_with_source(query: str) -> dict:
    """
    知识图谱查询 + 来源追溯
    返回: {"answer": "回答", "source_chunks": [...], "source_docs": [...]}
    
    用在问答场景：先查 Neo4j，有 source_chunk 就直接回答，
    不够的可以去飞书搜原文。
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    results = []
    with driver.session(database="neo4j") as session:
        # 模糊搜索实体名
        rows = session.run(
            "MATCH (e:Entity) "
            "WHERE e.name CONTAINS $q "
            "RETURN e.name AS name, e.type AS type, "
            "       e.description AS desc, "
            "       e.source_chunk AS chunk, "
            "       e.source_doc AS doc, e.doc_url AS url "
            "LIMIT 10",
            q=query
        )
        for r in rows:
            results.append({
                "name": r["name"], "type": r["type"],
                "description": r["desc"],
                "source_chunk": r["chunk"],
                "source_doc": r["doc"],
                "doc_url": r["url"]
            })
    driver.close()
    return results


# ============ 主入口 ============
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ("--scan", "-s"):
            scan_and_process()
        elif cmd == "--query":
            q = sys.argv[2] if len(sys.argv) > 2 else ""
            if q:
                res = query_with_source(q)
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print("用法: python3 run.py --query <关键词>")
        elif cmd == "--cross":
            file_path = sys.argv[2] if len(sys.argv) > 2 else ""
            src = sys.argv[3] if len(sys.argv) > 3 else ""
            url = sys.argv[4] if len(sys.argv) > 4 else ""
            if file_path:
                cross_review_extract(file_path, doc_source=src, doc_url=url, fast_mode=False)
            else:
                print("用法: python3 run.py --cross <文件路径> [来源] [文档]")
        else:
            file_path = cmd
            src = sys.argv[2] if len(sys.argv) > 2 else ""
            url = sys.argv[3] if len(sys.argv) > 3 else ""
            cross_review_extract(file_path, doc_source=src, doc_url=url, fast_mode=True)
    else:
        print("用法:")
        print("  python3 run.py <文件路径> [来源] [文档链接]   # 单个文件")
        print("  python3 run.py --scan                        # 批量")
        print("  python3 run.py --query <关键词>               # 查询（含来源）")
