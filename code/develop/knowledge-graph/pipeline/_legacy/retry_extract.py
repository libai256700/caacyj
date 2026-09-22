#!/usr/bin/env python3
"""补抽失败的文档 — 用修正后的参数"""
import json, requests, re, time, os, sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG = json.load(open(Path(__file__).parent / "config.json"))

# Neo4j
from neo4j import GraphDatabase
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text().strip()
N4J = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))

# 飞书
c = json.load(open(os.path.expanduser("~/.openclaw/openclaw.json")))
acct = c["channels"]["feishu"]["accounts"]["default"]
TOKEN = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": acct["appId"], "app_secret": acct["appSecret"]}).json()["tenant_access_token"]
H = {"Authorization": f"Bearer {TOKEN}"}

EXTRACT_PROMPT = """你是一个知识图谱实体抽取专家。请从以下文档中提取实体和关系。

## 实体类型
Organization | Person | Policy | Product | Event | Document

## 关系类型
belongs_to | contains | references | required_by | manages | regulates | provides

## 输出格式
{"entities":[{"id":"ent_1","name":"名称","type":"类型","description":"描述"}],
"relations":[{"from_id":"ent_1","to_id":"ent_2","type":"关系类型","description":"关系描述"}]}

仔细提取所有有意义的实体和关系。"""

def try_parse(text):
    clean = re.sub(r'^```(?:json)?\s*', '', text.strip())
    clean = re.sub(r'\s*```$', '', clean)
    s = clean.find('{'); e = clean.rfind('}')
    if s<0 or e<=s: return None
    cand = clean[s:e+1]
    cand = re.sub(r',(\s*[}\]])', r'\1', cand)
    try: return json.loads(cand)
    except: pass
    try:
        cand2 = re.sub(r',\s*}', '}', cand)
        cand2 = re.sub(r',\s*\]', ']', cand2)
        return json.loads(cand2)
    except: return None

def call_llm(text, doc_name, level="fast", source=""):
    cfg = CONFIG["models"][level]
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    src = f"\n## 来源：{source}" if source else ""
    prompt = EXTRACT_PROMPT + f"\n\n## 文档：{doc_name}{src}\n\n{text[:8000]}"
    
    payload = {
        "model": cfg["name"],
        "messages": [
            {"role":"system","content":"只输出JSON，不要markdown代码块，不要任何其他文字"},
            {"role":"user","content":prompt}
        ],
        "temperature": 0.1, "max_tokens": 8192
    }
    
    start = time.time()
    try:
        r = requests.post(f"{cfg['base_url']}/chat/completions", headers=headers, json=payload, timeout=cfg["timeout"])
        r.raise_for_status()
        c = r.json()["choices"][0]["message"]["content"]
        elapsed = time.time() - start
        result = try_parse(c)
        if result:
            print(f"  ✅ [{level.upper()}] {len(result.get('entities',[]))}实体 {len(result.get('relations',[]))}关系 ({elapsed:.1f}s)")
            return result
        print(f"  ❌ [{level.upper()}] JSON解析失败，原始输出前100: {c[:100]}")
        return {"entities":[],"relations":[]}
    except Exception as e:
        print(f"  ❌ [{level.upper()}] 失败: {e}")
        return {"entities":[],"relations":[]}

def process_text(text, doc_name, source="", force_gpt=False):
    if force_gpt:
        return call_llm(text, doc_name, "full", source)
    result = call_llm(text, doc_name, "fast", source)
    if not result.get("entities"):
        print(f"  ⚠️ DeepSeek 失败，切 GPT 5.5...")
        result = call_llm(text, doc_name, "full", source)
    return result

def write_neo4j(doc_name, entities, relations, doc_url=""):
    if not entities: return
    with N4J.session() as s:
        s.run("MERGE (d:Document {name:$n}) SET d.doc_url=$u, d.imported_at=datetime()", n=doc_name, u=doc_url)
        name_map = {}
        for i,e in enumerate(entities):
            eid = f"{doc_name[:6]}_{i+1}"
            s.run("MERGE (e:Entity {id:$eid}) SET e.name=$n, e.type=$t, e.description=$d, e.source_doc=$sn, e.doc_url=$u, e.imported_at=datetime()",
                  eid=eid, n=e.get("name",""), t=e.get("type","Unknown"), d=e.get("description",""), sn=doc_name, u=doc_url)
            s.run("MATCH (d:Document {name:$dn}) MATCH (e:Entity {id:$eid}) MERGE (d)-[:CONTAINS]->(e)", dn=doc_name, eid=eid)
            name_map[e.get("name","")] = eid
        for rel in relations:
            fid = name_map.get(rel.get("from_id",""), rel.get("from_id",""))
            tid = name_map.get(rel.get("to_id",""), rel.get("to_id",""))
            rt = re.sub(r'[^a-zA-Z_]', '_', rel.get("type","RELATED_TO")).upper()
            try:
                s.run(f"MATCH (a:Entity {{id:$fid}}) MATCH (b:Entity {{id:$tid}}) MERGE (a)-[r:{rt}]->(b) SET r.description=$d",
                      fid=fid, tid=tid, d=rel.get("description",""))
            except: pass
    print(f"  ✅ 入库: {len(entities)}实体 {len(relations)}关系")

# -------------------------------------------------

# 待补抽的文件（在线读取）
RETRY_FILES = [
    ("BcpCdYT4AoDVhFxYbVTcP3BITnBI", "低空经济岗位周度分析报告_2026-05-11~2026-05-16", "docx"),
    ("CPZudJ7UAlf7mqx7E4hcJR6uKnVd", "每日岗位信息报告_2026-05-12", "docx"),
    ("OhnoduH8DodJtpxI2ahch1t7gn0g", "每日岗位信息报告_2026-05-13", "docx"),
    ("CPX2dRqslqyZ1OxTNgmcEtT7rnKv", "每日岗位信息报告_2026-05-14", "docx"),
    ("V1amdk4m2o3eMYxRPmXc3FP5rnRb", "每日岗位信息报告_2026-05-11", "docx"),
    ("HBNkdRGLU4X0Y7xAI3acKNkRUngd", "每日岗位信息报告_2026-05-15", "docx"),
    ("A23ldu81Xot6dIxc3JHcCxTr3anUc", "每日岗位信息报告_2026-05-16", "docx"),
]

# 本地文件补抽（之前在线失败的）
LOCAL_FILES = [
    ("feishu_raw/湖北云技科技企业介绍.txt", "湖北云技科技企业介绍(PPT全量)", ""),
    ("feishu_raw/湖北云技科技企业介绍.txt", "湖北云技科技企业介绍(PPT-GPT)", "full"),
]

print("="*60)
print("🔧 补抽失败文档（修正参数版）")
print("="*60)

# 1) 在线文档补抽（先删旧数据再重抽）
print("\n📡 在线文档补抽:")
for token, name, dtype in RETRY_FILES:
    print(f"\n📄 {name}")
    
    # 读内容（通过 raw_content + download 双保险）
    content = ""
    r = requests.get(f"https://open.feishu.cn/open-apis/docx/v1/documents/{token}/raw_content", headers=H, timeout=30)
    if r.status_code == 200:
        content = r.json().get("data",{}).get("content","")
    if not content or len(content) < 50:
        r2 = requests.get(f"https://open.feishu.cn/open-apis/drive/v1/files/{token}/download", headers=H, timeout=30)
        if r2.status_code == 200:
            import zipfile, xml.etree.ElementTree as ET
            tmp = f"/tmp/_retry_{token}.docx"
            open(tmp, "wb").write(r2.content)
            z = zipfile.ZipFile(tmp)
            texts = []
            for zn in z.namelist():
                if zn.startswith("word/document"):
                    tree = ET.fromstring(z.read(zn))
                    for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                        t = "".join(t.text or "" for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
                        if t.strip(): texts.append(t.strip())
            os.remove(tmp)
            content = "\n".join(texts)
    
    if not content or len(content) < 50:
        print(f"   ⏭️ 无法读取内容")
        continue
    
    print(f"   内容: {len(content):,} 字符")
    
    # 删旧数据
    with N4J.session() as s:
        ents = s.run("MATCH (d:Document {name:$n})-[:CONTAINS]->(e:Entity) RETURN e.id AS eid", n=name).data()
        for e in ents: s.run("MATCH (e:Entity {id:$id})-[r]-() DELETE r", id=e["eid"])
        s.run("MATCH (d:Document {name:$n})-[r:CONTAINS]->() DELETE r", n=name)
        for e in ents: s.run("MATCH (e:Entity {id:$id}) DELETE e", id=e["eid"])
        s.run("MATCH (d:Document {name:$n}) DELETE d", n=name)
    
    # 抽取 + 入库
    result = process_text(content, name, "岗位信息报告")
    if result.get("entities"):
        write_neo4j(name, result["entities"], result["relations"])
    else:
        print(f"   ⏭️ 抽取为空")

# 2) 本地文件补抽
print("\n\n📁 本地文件补抽:")
for path, name, force_level in LOCAL_FILES:
    full_path = BASE_DIR / path
    if not full_path.exists():
        print(f"  ⏭️ {name} — 文件不存在"); continue
    
    content = full_path.read_text(encoding="utf-8")
    print(f"\n📄 {name} ({len(content):,} 字符)")
    
    # 删旧数据
    with N4J.session() as s:
        ents = s.run("MATCH (d:Document {name:$n})-[:CONTAINS]->(e:Entity) RETURN e.id AS eid", n=name).data()
        for e in ents: s.run("MATCH (e:Entity {id:$id})-[r]-() DELETE r", id=e["eid"])
        s.run("MATCH (d:Document {name:$n})-[r:CONTAINS]->() DELETE r", n=name)
        for e in ents: s.run("MATCH (e:Entity {id:$id}) DELETE e", id=e["eid"])
        s.run("MATCH (d:Document {name:$n}) DELETE d", n=name)
    
    if force_level == "full":
        result = call_llm(content, name, "full", "企业文化")
    else:
        result = process_text(content, name, "企业文化")
    
    if result.get("entities"):
        write_neo4j(name, result["entities"], result["relations"])
    else:
        print(f"   ⏭️ 抽取为空")

# 统计
with N4J.session() as s:
    e = s.run("MATCH (e:Entity) RETURN count(e) AS c").data()[0]["c"]
    r = s.run("MATCH ()-[r]->() RETURN count(r) AS c").data()[0]["c"]
    d = s.run("MATCH (d:Document) RETURN count(d) AS c").data()[0]["c"]

print(f"\n{'='*60}")
print(f"📊 补抽完成: {d} 文档, {e} 实体, {r} 关系")
print(f"{'='*60}")
N4J.close()
