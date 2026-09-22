#!/usr/bin/env python3
"""批量抽取：扫描 feishu_raw/ 中所有未入库文件，逐个提取"""
import json, sys, time, requests, os, re
from pathlib import Path
from neo4j import GraphDatabase

# ============ 配置 ============
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

FOLDER_URLS = {
    "制度": "https://zcn5jf36q4fv.feishu.cn/drive/folder/WVOjfu7IolU6U6dmvEZcymQknFf",
    "岗位": "https://zcn5jf36q4fv.feishu.cn/drive/folder/FhmNfRifQlpsZldRXKMcwvKlnCg",
    "客户": "https://zcn5jf36q4fv.feishu.cn/drive/folder/ENHXfWvXrhVHOZxUM4KcNUxhnag",
    "培训": "https://zcn5jf36q4fv.feishu.cn/drive/folder/KuRHfkB1XaJ5VndFTFMcI6tJnCf",
    "运营": "https://zcn5jf36q4fv.feishu.cn/drive/folder/N8kDfuMkXlHi2FdEjoTcT7Lanfc",
    "人事": "https://zcn5jf36q4fv.feishu.cn/drive/folder/Y18ffYhL4L1O28d3IH4cl3qjnrh",
}

# ============ 文件名 → 分类映射 ============
def classify_file(name):
    """根据文件名推断分类和提示词"""
    rules = [
        (["每日岗位", "岗位信息", "招聘岗位", "岗位周度", "低空经济", "总经办助理"], 
         "岗位信息报告", "Position, Company, Location, SalaryRange, EducationRequirement, Platform"),
        (["薪酬", "员工手册", "入职流程", "管理制度", "客户管理与跟进", "制度"], 
         "制度", "Policy, Department, Position, SalaryItem, Event, Person"),
        (["培训计划", "培训方案", "CAAC", "小型视距内", "长江委", "浠水"], 
         "培训计划", "Course, Event, KnowledgePoint, Person, Organization"),
        (["客户", "客资", "测绘公司", "A类", "B类", "C类"], 
         "咨询客户情况", "Person, Organization, Category, Company"),
        (["运管日常工作", "官号", "小号", "账号登记", "运营工作"], 
         "运营组", "PlatformPresence, SocialAccount, Person"),
        (["规范", "标准", "民用中小型"], 
         "企业信息", "Regulation, Certification, Organization"),
        (["学员", "培训记录", "模拟机", "航空器"], 
         "培训学员记录", "Person, Course, Score, Organization"),
    ]
    for keywords, folder, types in rules:
        for kw in keywords:
            if kw in name:
                return folder, types
    # 单人名单 → 咨询客户
    single_names = ["付艳娇","兰海波","刘安权","刘朝凤","华威","华尔丹","卢海","向天宇",
        "吴思雨","吴继安","唐进","康锴斯","张世煜","张君","张留俊","徐彬","曾理想",
        "李嘉昇","李彦杰","李政","李琪","李琪培","李腾达","李龙","杨昱昊","杨杰",
        "杨茂","梅小虎","毛杰","汪武","游希","熊裕凯","王启智","王知春","王锐",
        "田灿穗","程文权","童棋倡","符珉","罗端","罗顺祥","聂菁","肖托","胡继刚",
        "荆志伟","蒋子豪","蔡灿","谭思勤","赵鹏程","邓紫文","郑利","郭宇飞","郭楚璇",
        "陈佑安","雷江月","靖德可","韩松洁","饶兴江","鲁尧","黄理杰",
        "张世煜","刘安权"]
    for sn in single_names:
        if sn in name:
            return "咨询客户情况", "Person, Organization, Category"
    return "default", "Organization, Person, Product, Event, Document, Policy"

# ============ DeepSeek 调用 ============
def call_deepseek(text, doc_name, folder_hint, types, timeout=120):
    prompt = f"""从以下文档中提取实体和关系，只输出JSON。

文档：{doc_name}
来源：{folder_hint}

实体类型（从以下选择）：{types}
关系类型：belongs_to | contains | references | required_by | manages | regulates | provides | has_salary | located_in

输出格式：
{{"entities":[{{"id":"ent_1","name":"名称","type":"类型","description":"描述"}}],
 "relations":[{{"from_id":"ent_1","to_id":"ent_2","type":"关系类型","description":"关系描述"}}]}}

提取要求：
1. 提取所有有意义的实体，不要返回空数组
2. 同名实体只提取一次
3. 薪资带单位（如"6000-8000元"）

文档内容：
{text[:8000]}
"""
    r = requests.post(f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": [
            {"role": "system", "content": "只输出JSON，不要markdown代码块"},
            {"role": "user", "content": prompt}
        ], "temperature": 0.1, "max_tokens": 8192},
        timeout=timeout)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"): content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"): content = content.rsplit("```", 1)[0]
    return json.loads(content)

# ============ Neo4j 写入 ============
def write_to_neo4j(doc_name, entities, relations, doc_url):
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    name_map = {}
    with d.session() as s:
        s.run("MERGE (d:Document {name: $n}) SET d.name=$n, d.url=$u, d.imported_at=datetime()", n=doc_name, u=doc_url)
        for e in entities:
            eid = e.get("id", f"ent_{entities.index(e)}")
            ename = e["name"]
            etype = e.get("type", "Unknown")
            edesc = e.get("description", "")
            result = s.run(
                "MERGE (e:Entity {name: $n}) "
                "ON CREATE SET e.id = $id, e.type = $t, e.description = $d, e.source_doc = $doc "
                "ON MATCH SET e.id = COALESCE(e.id, $id), e.description = COALESCE(e.description, $d), "
                "  e.source_doc = COALESCE(e.source_doc, $doc) "
                "RETURN e.id AS actual_id",
                n=ename, id=eid, t=etype, d=edesc, doc=doc_name)
            actual_id = result.single()["actual_id"]
            name_map[eid] = actual_id
            s.run("MATCH (d:Document {name:$dn}) MATCH (e:Entity {id:$ei}) "
                  "MERGE (d)-[:CONTAINS]->(e)", dn=doc_name, ei=actual_id)
        rel_count = 0
        for r in relations:
            fid = name_map.get(r["from_id"])
            tid = name_map.get(r["to_id"])
            if fid and tid:
                try:
                    s.run(
                        f"MATCH (a:Entity {{id:$f}}) MATCH (b:Entity {{id:$t}}) "
                        f"MERGE (a)-[:`{r['type'].upper()}` {{description: $d}}]->(b)",
                        f=fid, t=tid, d=r.get("description",""))
                    rel_count += 1
                except: pass
    d.close()
    return len(entities), rel_count

# ============ 获取已入库文档 ============
def get_imported_docs():
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with d.session() as s:
        rows = s.run("MATCH (d:Document) RETURN d.name AS name").data()
    d.close()
    return set(r["name"] for r in rows)

# ============ 主流程 ============
def main():
    imported = get_imported_docs()
    print(f"📊 已入库文档: {len(imported)}")
    
    # 扫描 feishu_raw 下的所有 .txt 文件
    files = sorted(RAW_DIR.glob("*.txt"))
    total = len(files)
    print(f"📁 feishu_raw 文件总数: {total}")
    
    # 排除调试文件
    skip_patterns = ["【调试】", "测试块"]
    
    processed = 0
    skipped = 0
    failed = 0
    
    for fp in files:
        name = fp.stem  # 不含扩展名的文件名
        
        # 跳过已入库的
        if name in imported:
            skipped += 1
            continue
        
        # 跳过调试文件
        if any(p in name for p in skip_patterns):
            skipped += 1
            continue
        
        # 分类 + 提取
        folder, types = classify_file(name)
        doc_url = FOLDER_URLS.get(folder.split()[0] if " " in folder else folder, "")
        
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()[:8000]
            if len(text.strip()) < 10:
                print(f"  ⏭️  {name}: 内容过短,跳过")
                skipped += 1
                continue
            
            print(f"\n📄 [{folder}] {name}...", end=" ", flush=True)
            t0 = time.time()
            data = call_deepseek(text, name, folder, types)
            elapsed = time.time() - t0
            entities = data.get("entities", [])
            relations = data.get("relations", [])
            
            if entities:
                ec, rc = write_to_neo4j(name, entities, relations, doc_url)
                print(f"⚡ {elapsed:.1f}s → {ec}实体 {rc}关系 ✅", flush=True)
                processed += 1
            else:
                print(f"⚡ {elapsed:.1f}s → 无实体 ⚠️", flush=True)
                # 写个空文档标记已处理，防止反复试
                d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
                with d.session() as s:
                    s.run("MERGE (d:Document {name:$n}) SET d.name=$n, d.empty=true, d.imported_at=datetime()", n=name)
                d.close()
                skipped += 1
        except Exception as e:
            print(f"❌ 错误: {e}", flush=True)
            failed += 1
            if failed > 5:
                print("\n⚠️ 连续失败超过5次，暂停")
                break
    
    # 最终统计
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with d.session() as s:
        nb = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        docs = s.run("MATCH (d:Document) RETURN count(d) AS c").single()["c"]
    d.close()
    
    print(f"\n{'='*50}")
    print(f"本轮: 处理{processed}个 | 跳过{skipped}个 | 失败{failed}个")
    print(f"总计: {nb} 节点, {rels} 关系, {docs} 文档")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
