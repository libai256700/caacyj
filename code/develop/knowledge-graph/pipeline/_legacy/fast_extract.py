#!/usr/bin/env python3
"""快速批量抽取：小名单走DB直写，大文件并行处理"""
import json, sys, time, requests, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from neo4j import GraphDatabase

CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH) as f:
    _cfg = json.load(f)
API_KEY = _cfg["models"]["flash"]["api_key"]
BASE_URL = _cfg["models"]["flash"]["base_url"]
MODEL = _cfg["models"]["flash"]["name"]

RAW_DIR = Path(__file__).parent.parent / "feishu_raw"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = (Path(__file__).parent.parent / "neo4j" / ".neo4j_pass").read_text().strip()

# ============ 直接写库（小文件不走API） ============
def direct_write_person(name, category="咨询客户"):
    """30B的名单直接写库"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        s.run("MERGE (e:Entity {name: $n}) ON CREATE SET e.id = $n, e.type = 'Person', "
              "e.description = $cat, e.category = $cat, e.source_doc = $n",
              n=name, cat=category)
    driver.close()
    return f"  ✅ {name} (Person)"

def direct_write_batch(names, category="咨询客户"):
    """批量写名单"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        for name in names:
            s.run("MERGE (e:Entity {name: $n}) ON CREATE SET e.id = $n, e.type = 'Person', "
                  "e.description = $cat, e.category = $cat, e.source_doc = $n",
                  n=name, cat=category)
    driver.close()
    return f"  ✅ 批量写入 {len(names)} 个客户"

# ============ DeepSeek API 调用 ============
def call_deepseek(filename, text, folder_hint, types):
    prompt = f"""从以下文档提取实体和关系，只输出JSON。

文档：{filename}
来源：{folder_hint}
实体类型：{types}
关系类型：belongs_to | contains | references | required_by | manages | regulates | provides | has_salary | located_in

输出格式：{{"entities":[{{"id":"ent_1","name":"","type":"","description":""}}], "relations":[{{"from_id":"ent_1","to_id":"ent_2","type":"","description":""}}]}}

{text[:8000]}
"""
    r = requests.post(f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": [
            {"role": "system", "content": "只输出JSON，不要markdown代码块"},
            {"role": "user", "content": prompt}
        ], "temperature": 0.1, "max_tokens": 8192},
        timeout=60)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"): content = content.split("\n",1)[1]
    if content.endswith("```"): content = content.rsplit("```",1)[0]
    return json.loads(content)

def write_to_neo4j(doc_name, entities, relations, doc_url=""):
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    name_map = {}
    with d.session() as s:
        s.run("MERGE (d:Document {name: $n}) SET d.name=$n, d.url=$u, d.imported_at=datetime()", n=doc_name, u=doc_url)
        for e in entities:
            eid = e.get("id","")
            ename = e["name"]
            etype = e.get("type","Unknown")
            edesc = e.get("description","")
            r = s.run("MERGE (e:Entity {name: $n}) ON CREATE SET e.id=$id, e.type=$t, e.description=$d, e.source_doc=$doc "
                      "ON MATCH SET e.id=COALESCE(e.id,$id), e.description=COALESCE(e.description,$d) RETURN e.id AS actual_id",
                      n=ename, id=eid, t=etype, d=edesc, doc=doc_name)
            actual_id = r.single()["actual_id"]
            name_map[eid] = actual_id
            s.run("MATCH (d:Document {name:$dn}) MATCH (e:Entity {id:$ei}) MERGE (d)-[:CONTAINS]->(e)", dn=doc_name, ei=actual_id)
        for r in relations:
            fid = name_map.get(r["from_id"])
            tid = name_map.get(r["to_id"])
            if fid and tid:
                try:
                    s.run(f"MATCH (a:Entity {{id:$f}}) MATCH (b:Entity {{id:$t}}) "
                          f"MERGE (a)-[:`{r['type'].upper()}` {{description:$d}}]->(b)",
                          f=fid, t=tid, d=r.get("description",""))
                except: pass
    d.close()
    return len(entities), len(relations)

# ============ 分类 ============
def classify(name):
    if any(k in name for k in ["每日岗位","岗位信息","招聘岗位","岗位周度","低空经济","总经办助理"]):
        return "岗位信息报告", "Position,Company,Location,EducationRequirement,PlatformPresence"
    if any(k in name for k in ["薪酬","员工手册","入职流程","制度","客户管理","跟进制度"]):
        return "制度", "Policy,Position,Event,Person"
    if any(k in name for k in ["培训计划","培训方案","CAAC","长江委","浠水"]):
        return "培训计划", "Course,Event,KnowledgePoint,Person,Organization"
    if any(k in name for k in ["客户","客资","测绘公司","A类","B类","C类"]):
        return "咨询客户", "Person,Organization,Category,Company"
    if any(k in name for k in ["官号","小号","账号登记","运营工作"]):
        return "运营组", "PlatformPresence,SocialContent,Person"
    if any(k in name for k in ["规范","标准","民用"]):
        return "企业信息", "Regulation,Certification,Organization"
    if any(k in name for k in ["学员","模拟机","航空器"]):
        return "学员管理", "Person,Course,Organization"
    return "default", "Organization,Person,Event,Policy"

# 已知的单人名单（跳过API，直接写库）
SINGLE_NAMES = {"付艳娇","兰海波","刘安权","刘朝凤","华威","华尔丹","卢海","向天宇",
    "吴思雨","吴继安","唐进","康锴斯","张世煜","张君（机长）","张留俊","徐彬","曾理想",
    "李嘉昇","李彦杰","李政","李琪","李琪培","李腾达","李龙","杨昱昊","杨杰","杨茂",
    "梅小虎","毛杰","汪武","游希","熊裕凯","王启智","王知春","王锐","田灿穗",
    "程文权","童棋倡","符珉","罗端","罗顺祥","聂菁","肖托","胡继刚","荆志伟",
    "蒋子豪","蔡灿","谭思勤","赵鹏程","邓紫文","郑利","郭宇飞","郭楚璇","陈佑安",
    "雷江月","靖德可","韩松洁","饶兴江","鲁尧","黄理杰","张世煜","刘安权"}

def process_file(fp):
    """处理单个文件：小名单直接写库，大文件走API"""
    name = fp.stem
    
    # 已知单人名单 → 直接写库
    if name in SINGLE_NAMES:
        return direct_write_person(name)
    
    # 读取文件
    try:
        with open(fp, "rb") as f:
            raw = f.read()
        if len(raw) < 20:
            # 极短文件→尝试当名字处理
            text = raw.decode("utf-8", errors="replace").strip()
            if text and len(text) < 30 and not any(c in text for c in "《 《「【\n\t"):
                return direct_write_person(text)
            return f"  ⏭️ {name}: 内容过短"
        
        text = raw.decode("utf-8", errors="replace")[:8000]
    except Exception as e:
        return f"  ⏭️ {name}: 读取失败({e})"
    
    if len(text.strip()) < 20:
        return f"  ⏭️ {name}: 无有效内容"
    
    # 走API
    folder, types = classify(name)
    try:
        t0 = time.time()
        data = call_deepseek(name, text, folder, types)
        elapsed = time.time() - t0
        entities = data.get("entities", [])
        relations = data.get("relations", [])
        if entities:
            ec, rc = write_to_neo4j(name, entities, relations, "")
            return f"  ✅ [{folder}] {name}: {ec}实体 {rc}关系 ({elapsed:.1f}s)"
        else:
            return f"  ⚠️ [{folder}] {name}: 无实体 ({elapsed:.1f}s)"
    except Exception as e:
        return f"  ❌ [{folder}] {name}: {e}"

# ============ 主流程 ============
def main():
    # 获取已入库文档
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        imported = set(r["name"] for r in s.run("MATCH (d:Document) RETURN d.name AS name").data())
    driver.close()
    print(f"📊 已入库: {len(imported)} 文档")
    
    files = sorted(RAW_DIR.glob("*.txt"))
    to_process = []
    for fp in files:
        name = fp.stem
        if "【调试】" in name or "测试块" in name: continue
        if name in imported: continue
        to_process.append(fp)
    
    print(f"📁 待处理: {len(to_process)} 文件\n")
    
    # 先快速批量写单人名单（秒级完成）
    single_files = [fp for fp in to_process if fp.stem in SINGLE_NAMES]
    if single_files:
        names = [fp.stem for fp in single_files]
        print(direct_write_batch(names))
        to_process = [fp for fp in to_process if fp not in single_files]
    
    # 极短文件也直接写
    tiny = []
    rest = []
    for fp in to_process:
        if os.path.getsize(fp) < 50:
            tiny.append(fp)
        else:
            rest.append(fp)
    
    if tiny:
        for fp in tiny:
            print(process_file(fp))
    
    # 剩下的文件走API（并行3个）
    if rest:
        print(f"\n📡 开始API抽取 ({len(rest)} 文件, 并行3个)...")
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(process_file, fp): fp for fp in rest}
            done = 0
            for f in as_completed(futures):
                done += 1
                try:
                    print(f.result(), flush=True)
                except Exception as e:
                    print(f"  ❌ 异常: {e}", flush=True)
    
    # 最终统计
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        nb = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        docs = s.run("MATCH (d:Document) RETURN count(d) AS c").single()["c"]
    driver.close()
    print(f"\n{'='*50}")
    print(f"📊 最终: {nb} 节点, {rels} 关系, {docs} 文档")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
