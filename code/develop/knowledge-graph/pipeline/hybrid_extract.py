#!/usr/bin/env python3
"""
混合抽取脚本：图谱实体抽取 + 向量嵌入
用法: python3 hybrid_extract.py <文件路径或目录>
"""
import json, sys, os, re, time, requests
from pathlib import Path
from neo4j import GraphDatabase

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rag_store.semantic_schema import relationship_missing_evidence_reason

# ── 配置 ──
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
NEO4J_PASS_FILE = os.path.expanduser("~/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass")

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

# ── 模型：按 KG_GUIDE.md §3.5，主抽取用 GPT-5.5（中转站）──
GPT_MODEL = cfg['models']['full']['name']           # gpt-5.5
GPT_PROXIES = cfg['models']['full']['proxies']       # 中转站列表
GPT_TIMEOUT = cfg['models']['full']['timeout']       # 180s
NEO4J_PASS = open(NEO4J_PASS_FILE).read().strip()

# entity types from KG_GUIDE.md whitelist + 企业信息新增
ENTITY_TYPES = [
    "Company", "Organization", "Course", "Certification", "Policy", "Regulation",
    "KnowledgePoint", "Skill", "Location", "Event", "Category", "Person",
    "AircraftType", "LicenseLevel", "WeightClass"  # 企业信息细粒度
]

RELATION_TYPES = [
    "OFFERS", "INCLUDES", "AWARDS", "REQUIRES", "USES", "ISSUED_BY",
    "LOCATED_AT", "REGULATES", "DESCRIBES", "BELONGS_TO", "MENTIONS",
    "HAS_CLASS", "HAS_LEVEL"
]

OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings"
OLLAMA_MODEL = "bge-m3"

# ── Neo4j driver ──
def get_driver():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))

# ── Embedding ──
def get_embedding(text):
    """bge-m3 向量化"""
    try:
        r = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": text[:8000]}, timeout=30)
        return r.json().get("embedding", [])
    except Exception as e:
        print(f"  ⚠️ embedding 失败: {e}")
        return None

# ── DeepSeek 抽取 ──
def extract_entities(text, doc_name, doc_type, extra_prompt=""):
    """调用 DeepSeek 抽取实体和关系"""
    prompt = f"""从以下文档提取实体和关系，只输出纯JSON（不要markdown包裹）。

文档名：{doc_name}
文档类型：{doc_type}
{extra_prompt}

实体类型（必须选一个）：{', '.join(ENTITY_TYPES)}
关系类型：{', '.join(RELATION_TYPES)}

输出格式：
{{
  "entities": [
    {{"name": "实体名", "type": "类型", "properties": {{"key": "value"}} }}
  ],
  "relations": [
    {{"from": "实体A名", "to": "实体B名", "type": "关系名"}}
  ]
}}

⚠️ 规则：
- name 必须使用完整全称（公司名用全称，地名用完整地址）
- 同名同类型实体只出现一次
- 仅提取有实际意义的实体，忽略表格表头、编号等

⚠️ 新增实体类型分类指南：
- AircraftType: 无人机机型，如 多旋翼/单旋翼/垂直起降固定翼/固定翼/直升机
- LicenseLevel: 执照等级，如 视距内驾驶员/超视距驾驶员/教员/动力升空器
- WeightClass: 重量分类，如 微型/轻型/小型/中型/大型/农用
- 关系 HAS_CLASS: AircraftType→WeightClass，HAS_LEVEL: Certification→LicenseLevel
- 关系 USES: Course→AircraftType，REQUIRES: Course→LicenseLevel

文档内容：
{text[:12000]}
"""
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": GPT_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个实体关系抽取专家。只输出JSON，不要markdown代码块。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 8192
    }
    
    # ── 中转站轮询：按序尝试，3次重试 ──
    for proxy in GPT_PROXIES:
        proxy_url = f"{proxy['base_url']}/chat/completions"
        headers["Authorization"] = f"Bearer {proxy['api_key']}"
        print(f"     → 中转站: {proxy['base_url'][:30]}...")
        
        for attempt in range(3):
            try:
                resp = requests.post(proxy_url, json=payload, headers=headers, timeout=GPT_TIMEOUT)
                if resp.status_code != 200:
                    print(f"     ⚠️  HTTP {resp.status_code}")
                    if attempt < 2: time.sleep(3); continue
                    else: break
                content = resp.json()["choices"][0]["message"]["content"]
                content = re.sub(r'^```json\s*', '', content.strip())
                content = re.sub(r'^```\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                return json.loads(content)
            except Exception as e:
                if attempt < 2:
                    print(f"     ⚠️  重试 {attempt+1}/3: {str(e)[:50]}")
                    time.sleep(3)
                else:
                    print(f"     ❌ 中转站 {proxy['base_url'][:30]} 失败: {str(e)[:50]}")
                    break  # 换下一个中转站
    
    # ── 降级：按 §3.5.1，所有中转站失败后，停下来问老文 ──
    print(f"  ❌ 所有中转站均失败！按KG_GUIDE §3.5.1，需老文确认后降级到Doubao")
    return None

# ── Neo4j 写入 ──
def write_to_neo4j(driver, doc_name, file_path, entities, relations):
    """写入实体、关系、文档节点"""
    with driver.session() as session:
        # 创建 Document 节点
        doc_node_name = doc_name.replace(".txt", "")
        session.run("""
            MERGE (d:Document {name: $name})
            SET d.filepath = $filepath, d.updated_at = datetime()
        """, name=doc_node_name, filepath=file_path)
        
        # 写入实体
        entity_count = 0
        for e in entities:
            props = e.get('properties', {}) or {}
            props['name'] = e['name']
            props['source_doc'] = doc_node_name
            try:
                session.run(f"""
                    MERGE (n:{e['type']} {{name: $name}})
                    SET n += $props
                """, name=e['name'], props=props)
                entity_count += 1
            except Exception as ex:
                print(f"  ⚠️ 实体写入失败: {e['name']} - {ex}")
        
        # 写入关系
        rel_count = 0
        for r in relations:
            rel_type = str(r.get("type") or "").upper().strip()
            if not re.match(r"^[A-Z_][A-Z0-9_]*$", rel_type):
                print(f"  🚫 跳过非法关系类型: {r.get('from')} -[{rel_type}]-> {r.get('to')}")
                continue
            props = {
                "source_doc": doc_node_name,
                "source_chunk_ids": [],
                "evidence_contract": "legacy_hybrid_extract_missing_chunk_ids",
            }
            reason = relationship_missing_evidence_reason(rel_type, props)
            if reason:
                print(f"  🚫 跳过缺证据关键关系: {r.get('from')} -[{rel_type}]-> {r.get('to')} ({reason})")
                continue
            try:
                session.run(f"""
                    MATCH (a {{name: $from}}), (b {{name: $to}})
                    MERGE (a)-[rel:{rel_type}]->(b)
                    SET rel += $props
                """, **{"from": r.get("from"), "to": r.get("to"), "props": props})
                rel_count += 1
            except Exception as ex:
                print(f"  ⚠️ 关系写入失败: {r.get('from')} -[{rel_type}]-> {r.get('to')} - {ex}")
        
        # 创建 Document -> Entity 的 DESCRIBES 关系
        for e in entities:
            try:
                session.run(f"""
                    MATCH (d:Document {{name: $doc}}), (n:{e['type']} {{name: $name}})
                    MERGE (d)-[:DESCRIBES]->(n)
                """, doc=doc_node_name, name=e['name'])
            except:
                pass
        
        return entity_count, rel_count

# ── Vector embedding for Document ──
def embed_and_store(driver, doc_name, text):
    """给文档全文生成向量并存储"""
    embedding = get_embedding(text[:6000])  # 截断到6000字符
    if not embedding:
        return False
    
    doc_node_name = doc_name.replace(".txt", "")
    with driver.session() as session:
        # 先创建向量索引（如果不存在）
        try:
            session.run("""
                CREATE VECTOR INDEX doc_embedding IF NOT EXISTS
                FOR (d:Document) ON (d.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 1024,
                    `vector.similarity_function`: 'cosine'
                }}
            """)
        except:
            pass
        
        # 存储向量
        session.run("""
            MATCH (d:Document {name: $name})
            SET d.embedding = $embedding, d.content = $content
        """, name=doc_node_name, embedding=embedding, content=text[:6000])
    
    return True

# ── 主流程 ──
def process_file(filepath):
    """处理单个文件"""
    name = os.path.basename(filepath)
    print(f"\n{'='*60}")
    print(f"📄 {name}")
    print(f"{'='*60}")
    
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    print(f"  文件大小: {len(text)} 字符")
    
    # 判断文档类型
    if "公司介绍" in name and "产品" not in name:
        doc_type = "企业介绍"
    elif "产品" in name:
        doc_type = "产品介绍"
    elif "价格" in name:
        doc_type = "价格表"
    elif "培训" in name:
        doc_type = "培训资料"
    elif "规范" in name or "标准" in name:
        doc_type = "行业规范"
    elif "员工手册" in name or "面试" in name or "入职" in name or "薪酬" in name or "客户管理" in name or "制度" in name:
        doc_type = "人事制度"
    else:
        doc_type = "企业信息"
    
    # 人事制度需要更深入的抽取
    if doc_type == "人事制度":
        extra_prompt = "\n⚠️ 人事制度抽取要求：不仅要抽章节标题，必须深入每个条款具体内容，提取具体的政策、规则、流程节点。例如：\"迟到按考勤制度处理\"→Policy考勤管理制度 + Event迟到处理；\"年假病假按国家规定\"→Policy年假制度+Policy病假制度。\n"
    else:
        extra_prompt = ""
    
    print(f"  文档类型: {doc_type}")
    
    # Step 1: 实体抽取
    print(f"  🧠 DeepSeek 抽取中...")
    result = extract_entities(text, name, doc_type, extra_prompt)
    
    if not result:
        print("  ❌ 抽取失败，跳过")
        return
    
    entities = result.get("entities", [])
    relations = result.get("relations", [])
    print(f"  ✅ 实体: {len(entities)} 个, 关系: {len(relations)} 条")
    
    for e in entities:
        print(f"     • [{e['type']}] {e['name']}")
    
    # Step 2: 写入 Neo4j
    print(f"  💾 写入 Neo4j...")
    driver = get_driver()
    try:
        e_cnt, r_cnt = write_to_neo4j(driver, name, filepath, entities, relations)
        print(f"  ✅ 写入完成: {e_cnt} 实体, {r_cnt} 关系")
    finally:
        driver.close()
    
    # Step 3: 向量嵌入
    print(f"  🔢 生成向量嵌入...")
    driver2 = get_driver()
    try:
        ok = embed_and_store(driver2, name, text)
        if ok:
            print(f"  ✅ 向量嵌入完成 (1024维)")
        else:
            print(f"  ⚠️ 向量嵌入失败")
    finally:
        driver2.close()

def show_stats():
    """展示当前数据库统计"""
    driver = get_driver()
    try:
        with driver.session() as s:
            r = s.run("MATCH (n) RETURN labels(n)[0] as type, count(*) as cnt ORDER BY cnt DESC")
            print("\n📊 数据库统计:")
            for row in r:
                print(f"  {row['type']}: {row['cnt']}")
    finally:
        driver.close()

# ── 入口 ──
if __name__ == "__main__":
    args = sys.argv[1:] if len(sys.argv) > 1 else ["."]
    
    print("=" * 60)
    print("🚀 混合抽取流水线：图谱 + 向量")
    print("=" * 60)
    
    # 收集文件
    for target in args:
        p = Path(target)
        if p.is_dir():
            files = sorted(p.glob("*.txt"))
        else:
            files = [p]
        for f in files:
            process_file(str(f))
    
    show_stats()
    print("\n✅ 全部完成!")
