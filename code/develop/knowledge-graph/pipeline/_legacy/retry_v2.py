#!/usr/bin/env python3
"""补抽失败文档 v2 — 使用完整 token"""
import requests, json, re, time, os, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).parent.parent
CONFIG = json.load(open(Path(__file__).parent / "config.json"))
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text().strip()
N4J = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))

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
"relations":[{"from_id":"ent_1","to_id":"ent_2","type":"关系类型","description":"关系描述"}]}"""

def try_parse(text):
    clean = re.sub(r'^```(?:json)?\s*', '', text.strip())
    clean = re.sub(r'\s*```$', '', clean)
    s = clean.find('{'); e = clean.rfind('}')
    if s<0 or e<=s: return None
    cand = clean[s:e+1]
    cand = re.sub(r',(\s*[}\]])', r'\1', cand)
    try: return json.loads(cand)
    except:
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
        "messages": [{"role":"system","content":"只输出JSON，不要markdown代码块"}, {"role":"user","content":prompt}],
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
        print(f"  ❌ [{level.upper()}] JSON失败")
        if level == "fast":
            print(f"  ⚠️ 转 GPT 5.5 补抽...")
            return call_llm(text, doc_name, "full", source)
        return {"entities":[],"relations":[]}
    except Exception as e:
        print(f"  ❌ [{level.upper()}] 失败: {e}")
        return {"entities":[],"relations":[]}

def write_neo4j(doc_name, entities, relations, doc_url=""):
    if not entities: return
    with N4J.session() as s:
        s.run("MERGE (d:Document {name:$n}) SET d.doc_url=$u, d.imported_at=datetime()", n=doc_name, u=doc_url)
        name_map = {}
        for i,e in enumerate(entities):
            eid = f"{doc_name[:6]}_{i+1}"
            cat = '就业' if '岗位信息报告' in (f.get('path','') or '') else ''
            if cat: s.run("MATCH (e:Entity {id:$eid}) SET e.category=$cat", eid=eid, cat=cat)
            s.run("MERGE (e:Entity {id:$eid}) SET e.name=$n, e.type=$t, e.description=$d, e.source_doc=$sn, e.doc_url=$u, e.source_chunk=$ch, e.imported_at=datetime()",
                  eid=eid, n=e.get("name",""), t=e.get("type","Unknown"), d=e.get("description",""), sn=doc_name, u=doc_url, ch=e.get("source_chunk",""))
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

# ============ 获取完整文件清单（不截断 token） ============
def get_all_files():
    """递归扫描文件夹，获取完整文件信息"""
    files = []
    def scan(ft, path):
        r = requests.get(f"https://open.feishu.cn/open-apis/drive/v1/files?page_size=50&folder_token={ft}", headers=H, timeout=30)
        for f in r.json().get("data",{}).get("files",[]):
            if f["type"] == "folder":
                scan(f["token"], path + [f["name"]])
            else:
                files.append({"token": f["token"], "name": f["name"], "type": f["type"],
                             "path": "/".join(path), "url": f.get("url","")})
    scan("X9pZftImzlgO1HdIo7Xct1CXn5b", ["云技资料库"])
    return files

all_files = get_all_files()
print(f"📊 云技资料库共 {len(all_files)} 个文件")

# 筛选出未入库的 docx 文件（不包括之前已成功的）
with N4J.session() as s:
    existing = {r["name"] for r in s.run("MATCH (d:Document) RETURN d.name AS name").data()}

to_process = [f for f in all_files 
              if f["type"] == "docx" 
              and f["name"] not in existing]
# 按路径排序
to_process.sort(key=lambda x: x["path"] + "/" + x["name"])

print(f"📋 待处理: {len(to_process)} 个 docx 文件")
for f in to_process:
    print(f"  📝 {f['path']}/{f['name']}  token={f['token']}")

# ============ 逐份处理 ============
total_e, total_r, ok = 0, 0, 0
for f in to_process:
    print(f"\n{'='*50}")
    print(f"📄 {f['name']}")
    print(f"   路径: {f['path']}")
    
    # 读内容
    r = requests.get(f"https://open.feishu.cn/open-apis/docx/v1/documents/{f['token']}/raw_content", headers=H, timeout=30)
    content = r.json().get("data",{}).get("content","") if r.status_code==200 else ""
    
    if not content or len(content) < 50:
        # 尝试下载
        r2 = requests.get(f"https://open.feishu.cn/open-apis/drive/v1/files/{f['token']}/download", headers=H, timeout=30)
        if r2.status_code == 200:
            tmp = f"/tmp/_v2_{f['token']}.docx"
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
    
    # 抽取
    result = call_llm(content, f["name"], "fast", f["path"])
    
    # GPT 5.5 补抽
    if not result.get("entities"):
        result = call_llm(content, f["name"], "full", f["path"])
    
    if result.get("entities"):
        write_neo4j(f["name"], result["entities"], result["relations"], f.get("url",""))
        total_e += len(result["entities"])
        total_r += len(result["relations"])
        ok += 1
    else:
        print(f"   ❌ 完全失败")

N4J.close()
print(f"\n{'='*50}")
print(f"📊 完成: 成功 {ok}/{len(to_process)} 个文件, {total_e} 实体, {total_r} 关系")
print(f"{'='*50}")
