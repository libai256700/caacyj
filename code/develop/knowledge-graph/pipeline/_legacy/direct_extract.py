#!/usr/bin/env python3
"""直接抽取：DeepSeek API → Neo4j，跳过pipeline中间层"""
import json, sys, time, requests
from neo4j import GraphDatabase

CONFIG_PATH = "/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/pipeline/config.json"
with open(CONFIG_PATH) as f:
    _cfg = json.load(f)
API_KEY = _cfg["models"]["flash"]["api_key"]
BASE_URL = _cfg["models"]["flash"]["base_url"]
MODEL = _cfg["models"]["flash"]["name"]
print(f"🔑 Key: {API_KEY[:12]}...{API_KEY[-4:]} Model: {MODEL} ")

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass").read().strip()

TYPE_COLORS = {
    "Organization": "#29b6f6", "Person": "#ab47bc", "Policy": "#ef5350",
    "Department": "#26c6da", "SalaryItem": "#9ccc65", "Position": "#ff7043",
    "Event": "#ffa726", "Document": "#78909c", "Product": "#66bb6a",
    "Category": "#ffa726", "Location": "#8d6e63"
}

def call_deepseek(prompt, timeout=120):
    r = requests.post(f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": [
            {"role": "system", "content": "只输出JSON，不要markdown代码块"},
            {"role": "user", "content": prompt}
        ], "temperature": 0.1, "max_tokens": 8192},
        timeout=timeout)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    # 清理可能的markdown标记
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    return json.loads(content)

def write_neo4j(doc_name, entities, relations, doc_url):
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with d.session() as s:
        # 创建文档节点
        s.run("MERGE (d:Document {name: $n}) SET d.name=$n, d.url=$u, d.imported_at=datetime()",
              n=doc_name, u=doc_url)
        
        # 创建实体节点（按name MERGE）
        name_map = {}
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
            # 关联到文档
            s.run("MATCH (d:Document {name:$dn}) MATCH (e:Entity {id:$ei}) "
                  "MERGE (d)-[:CONTAINS]->(e)", dn=doc_name, ei=actual_id)
        
        print(f"  ✅ 写入 {len(entities)} 实体")
        
        # 创建关系
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
                except Exception as ex:
                    print(f"  ⚠️ 关系写入失败: {ex}")
        
        print(f"  ✅ 写入 {rel_count} 关系")
    d.close()
    return name_map

def extract_file(filepath, doc_name, doc_url, folder_hint="制度"):
    print(f"\n📄 {doc_name}...", end=" ", flush=True)
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()[:8000]
    
    prompt = f"""从以下文档中提取实体和关系，只输出JSON。

文档：{doc_name}
来源：{folder_hint}

实体类型（选择匹配的）：
- Organization: 公司/组织/部门
- Person: 人员
- Policy: 制度/规定/流程
- Department: 部门
- SalaryItem: 薪资项目/补贴/奖金
- Position: 岗位/职位
- Event: 培训/活动/会议
- Location: 地点

关系类型：belongs_to | contains | manages | regulates | provides | has_salary

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
    try:
        t0 = time.time()
        data = call_deepseek(prompt)
        elapsed = time.time() - t0
        entities = data.get("entities", [])
        relations = data.get("relations", [])
        print(f"⚡ {elapsed:.1f}s → {len(entities)}实体 {len(relations)}关系", flush=True)
        
        if entities:
            write_neo4j(doc_name, entities, relations, doc_url)
        else:
            print("  ⚠️ 无实体")
    except Exception as e:
        print(f"\n  ❌ 错误: {e}", flush=True)

if __name__ == "__main__":
    folder_url = "https://zcn5jf36q4fv.feishu.cn/drive/folder/WVOjfu7IolU6U6dmvEZcymQknFf"
    base = "/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/feishu_raw"
    
    files = [
        ("云技科技员工手册", f"{base}/云技科技员工手册.txt"),
        ("湖北云技科技有限公司薪酬体系", f"{base}/湖北云技科技有限公司薪酬体系.txt"),
        ("湖北云技科技有限公司无人机执照培训项目客户管理与跟进制度", f"{base}/湖北云技科技有限公司无人机执照培训项目客户管理与跟进制度.txt"),
        ("湖北云技科技新员工面试及入职流程", f"{base}/湖北云技科技新员工面试及入职流程.txt"),
    ]
    
    # 跳过已处理的（云技科技员工手册已有46节点）
    for name, path in files:
        extract_file(path, name, folder_url)
    
    # 最终统计
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with d.session() as s:
        nb = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        docs = s.run("MATCH (d:Document) RETURN d.name AS name").data()
        print(f"\n=== 最终: {nb} 节点, {rels} 关系, {len(docs)} 文档 ===")
        for doc in docs:
            ec = s.run("MATCH (d:Document {name:$n})-[c:CONTAINS]->(e) RETURN count(e) AS c", n=doc["name"]).single()["c"]
            print(f"  📄 {doc['name']}: {ec} 实体")
    d.close()
