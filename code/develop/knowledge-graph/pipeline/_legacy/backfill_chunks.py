#!/usr/bin/env python3
"""回填缺失的 source_chunk — 在线读取飞书文件原文，匹配实体名"""
import json, requests, os, zipfile, xml.etree.ElementTree as ET, time
from neo4j import GraphDatabase

NEO4J_PASS = open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass").read().strip()
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))

# 飞书
c = json.load(open(os.path.expanduser("~/.openclaw/openclaw.json")))
acct = c["channels"]["feishu"]["accounts"]["default"]
TOKEN = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": acct["appId"], "app_secret": acct["appSecret"]}).json()["tenant_access_token"]
H = {"Authorization": f"Bearer {TOKEN}"}

# 加载本地已缓存的文件
RAW_DIR = "/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/feishu_raw"
local_cache = {}
for fp in os.listdir(RAW_DIR):
    if fp.endswith(".txt") and not fp.startswith("_"):
        try:
            local_cache[fp.replace(".txt","")] = open(f"{RAW_DIR}/{fp}").read()
        except: pass

# 飞书文件 token 映射（从之前扫描获取）
FEISHU_DOCS = {
    "湖北省各县测绘公司名录（完整版）": "XIU6dz3eVoK7ZoxkWpHcBqi8nTd",
    "每日岗位信息报告_2026-05-16": "A23ldubFcomWL4x7QOncufzanUc",
    "每日岗位信息报告_2026-05-15": "HBNkdRT26oxomHxMq0EcdYdUngd",
    "每日岗位信息报告_2026-05-14": "CPX2dRRjUoyV3Hx4cwGcA6rrnKv",
    "每日岗位信息报告_2026-05-13": "Ohnoduta4oECDxxHOoicVNxgn0g",
    "每日岗位信息报告_2026-05-12": "CPZudJrCNot8ulxs3L1chzgKnVd",
    "每日岗位信息报告_2026-05-11": "V1amdk0zAo3PFCxQ063cMcbrnRb",
    "低空经济岗位周度分析报告_2026-05-11~2026-05-16": "BcpCdYvyloXKpLxU4ivcTM6TnBI",
    # 公众号
    "【公众号】低空经济爆发元年已至 — 2026.5.16": "HBNkdRT26oxomHxMq0EcdYdUngd",  # 同一个 token 但不同文件名
}

# 题库文件 token
Q_TOKENS = {
    "飞行原理与飞行性能": "KCPRbyOD3oMVSGx3w6EcKXWvnbb",
    "飞行原理与飞行性能.docx": "KCPRbyOD3oMVSGx3w6EcKXWvnbb",
    "无人机教员题库.docx": "NlGsbmxi7oZ1QIxMC84cCfO4nfW",
    "概述": "DG8EbFAWaojWZcxL0FmckwPwnHd",
    "概述.docx": "DG8EbFAWaojWZcxL0FmckwPwnHd",
}

def read_docx_online(token):
    """在线读取 docx"""
    # raw_content 优先
    r = requests.get(f"https://open.feishu.cn/open-apis/docx/v1/documents/{token}/raw_content", headers=H, timeout=30)
    if r.status_code == 200:
        c = r.json().get("data",{}).get("content","")
        if len(c) > 50: return c
    # download
    r2 = requests.get(f"https://open.feishu.cn/open-apis/drive/v1/files/{token}/download", headers=H, timeout=60)
    if r2.status_code == 200:
        tmp = f"/tmp/_bf_{token}.docx"
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
        return "\n".join(texts)
    return ""

def extract_chunk(text, name, context=120):
    idx = text.find(name)
    if idx < 0: return ""
    s = max(0, idx - context)
    e = min(len(text), idx + len(name) + context)
    chunk = text[s:e].strip()
    return chunk[:300] if len(chunk) > 300 else chunk

stats = 0

# ============ 读本地缓存 + 飞书在线 ============
with driver.session() as s:
    # 按 source_doc 分组
    groups = s.run("""
        MATCH (e:Entity)
        WHERE e.source_chunk IS NULL OR e.source_chunk = ''
        RETURN e.source_doc AS doc, count(*) AS cnt
        ORDER BY cnt DESC
    """).data()
    
    total = sum(g["cnt"] for g in groups)
    print(f"📊 需要回填 {total} 个实体，分布在 {len(groups)} 个文档\n")
    
    for g in groups:
        doc_name = g["doc"] or "(无来源文档)"
        count = g["cnt"]
        print(f"  {doc_name} ({count}个)...", end=" ", flush=True)
        
        # 获取原文
        content = ""
        if doc_name in local_cache:
            content = local_cache[doc_name]
        elif doc_name in FEISHU_DOCS:
            print("在线读取...", end=" ", flush=True)
            content = read_docx_online(FEISHU_DOCS[doc_name])
        elif doc_name in Q_TOKENS:
            print("在线读取题库...", end=" ", flush=True)
            content = read_docx_online(Q_TOKENS[doc_name])
        
        if not content or len(content) < 50:
            # 尝试模糊匹配本地文件
            for k, v in local_cache.items():
                if doc_name and (doc_name[:6] in k or k in doc_name):
                    content = v
                    break
        
        if not content or len(content) < 50:
            print("❌ 无原文")
            continue
        
        print(f"({len(content):,} 字符)...", end=" ", flush=True)
        
        # 匹配实体名
        entities = s.run("""
            MATCH (e:Entity)
            WHERE (e.source_chunk IS NULL OR e.source_chunk = '')
            AND e.source_doc = $doc
            RETURN e.id AS id, e.name AS name
        """, doc=doc_name).data()
        
        filled = 0
        for ent in entities:
            chunk = extract_chunk(content, ent["name"])
            if chunk:
                s.run("MATCH (e:Entity {id:$id}) SET e.source_chunk = $c", id=ent["id"], c=chunk)
                filled += 1
        
        stats += filled
        print(f"✅ {filled}/{count}")
        time.sleep(0.5)

driver.close()

# 最终统计
driver2 = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))
with driver2.session() as s:
    remain = s.run("""
        MATCH (e:Entity) WHERE e.source_chunk IS NULL OR e.source_chunk = ''
        RETURN count(e) AS cnt
    """).data()[0]["cnt"]
    total_e = s.run("MATCH (e:Entity) RETURN count(e) AS c").data()[0]["c"]
print(f"\n{'='*60}")
print(f"✅ 回填完成: {stats} 个")
print(f"   剩余缺来源: {remain}")
print(f"   已有来源: {total_e - remain}/{total_e} ({(total_e-remain)*100//total_e}%)")
driver2.close()
