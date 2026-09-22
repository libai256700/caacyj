#!/usr/bin/env python3
"""知识图谱优化：去重 + 补描述 + 回填来源"""
import re, json
from collections import defaultdict
from neo4j import GraphDatabase

NEO4J_PASS = open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass").read().strip()
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))

def normalize(name):
    return re.sub(r'\s+', '', name).strip().lower()

stats = {"merged": 0, "entities_deleted": 0, "relations_rewired": 0, "desc_filled": 0, "chunk_filled": 0}

with driver.session() as s:
    print("=" * 60)
    print("🔧 开始知识图谱优化")
    print("=" * 60)

    # ============ 1. 去重 ============
    print("\n📦 第1步：去重合并...")
    
    # 找所有重复组
    dups = s.run("""
        MATCH (e:Entity)
        WITH e.name AS name, e.type AS type, collect(e.id) AS ids, 
             collect(e.source_doc) AS docs, count(*) AS cnt
        WHERE cnt > 1
        RETURN name, type, ids, docs, cnt
        ORDER BY cnt DESC
    """).data()
    
    for group in dups:
        ids = group["ids"]
        name = group["name"]
        etype = group["type"]
        
        # 选保留哪个：有最多关系的那个
        best_id = None
        best_deg = -1
        for eid in ids:
            deg = s.run("MATCH (e:Entity {id:$id}) RETURN count{(e)--()} AS deg", id=eid).data()[0]["deg"]
            if deg > best_deg:
                best_deg = deg
                best_id = eid
        
        for eid in ids:
            if eid == best_id:
                continue
            
            # 转移所有关系到 best_id
            # 入边
            in_rels = s.run("""
                MATCH (a)-[r]->(e:Entity {id:$eid})
                RETURN a.id AS from_id, type(r) AS rtype, r.description AS desc
            """, eid=eid).data()
            for rel in in_rels:
                try:
                    rtype = re.sub(r'[^a-zA-Z_]', '_', rel["rtype"]).upper()
                    s.run(f"MATCH (a:Entity {{id:$fid}}) MATCH (b:Entity {{id:$tid}}) "
                          f"MERGE (a)-[rr:{rtype}]->(b) SET rr.description=$d",
                          fid=rel["from_id"], tid=best_id, d=rel.get("desc",""))
                    stats["relations_rewired"] += 1
                except: pass
            
            # 出边
            out_rels = s.run("""
                MATCH (e:Entity {id:$eid})-[r]->(b)
                RETURN b.id AS to_id, type(r) AS rtype, r.description AS desc
            """, eid=eid).data()
            for rel in out_rels:
                try:
                    rtype = re.sub(r'[^a-zA-Z_]', '_', rel["rtype"]).upper()
                    s.run(f"MATCH (a:Entity {{id:$fid}}) MATCH (b:Entity {{id:$tid}}) "
                          f"MERGE (a)-[rr:{rtype}]->(b) SET rr.description=$d",
                          fid=best_id, tid=rel["to_id"], d=rel.get("desc",""))
                    stats["relations_rewired"] += 1
                except: pass
            
            # 转移 CONTAINS 关系
            s.run("""
                MATCH (d:Document)-[r:CONTAINS]->(e:Entity {id:$old_id})
                MATCH (target:Entity {id:$new_id})
                MERGE (d)-[:CONTAINS]->(target)
                DELETE r
            """, old_id=eid, new_id=best_id)
            
            # 删除重复实体及其所有关系
            s.run("MATCH (e:Entity {id:$id}) DETACH DELETE e", id=eid)
            stats["entities_deleted"] += 1
        
        if len(ids) > 1:
            print(f"  ✅ 「{name}」({etype}) ×{len(ids)} → 合并为 1")
            stats["merged"] += 1
    
    print(f"  合并 {stats['merged']} 组 → 删 {stats['entities_deleted']} 重复实体")

    # ============ 2. 补空描述 ============
    print("\n📝 第2步：补空描述...")
    
    empties = s.run("""
        MATCH (e:Entity)
        WHERE e.description IS NULL OR e.description = ''
        RETURN e.id AS id, e.name AS name, e.type AS type, e.source_doc AS doc
        LIMIT 30
    """).data()
    
    for ent in empties:
        # 从 source_chunk 自动提取描述
        chunk = s.run("MATCH (e:Entity {id:$id}) RETURN e.source_chunk AS c", id=ent["id"]).data()[0].get("c","")
        if chunk:
            desc = chunk[:200] if len(chunk) > 200 else chunk
            s.run("MATCH (e:Entity {id:$id}) SET e.description = $d", id=ent["id"], d=desc)
            stats["desc_filled"] += 1
        elif ent.get("doc"):
            # 用来源文档名 + 类型生成简要描述
            desc = f"来自「{ent['doc']}」的{ent['type']}类实体"
            s.run("MATCH (e:Entity {id:$id}) SET e.description = $d", id=ent["id"], d=desc)
            stats["desc_filled"] += 1
    
    print(f"  补了 {stats['desc_filled']} 个空描述")

    # ============ 3. 回填 source_chunk ============
    print("\n📎 第3步：回填来源片段...")
    
    # 从 feishu_raw/ 读原文，匹配实体名
    import os
    raw_dir = "/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/feishu_raw"
    
    missing = s.run("""
        MATCH (e:Entity) 
        WHERE (e.source_chunk IS NULL OR e.source_chunk = '')
        RETURN e.id AS id, e.name AS name, e.source_doc AS doc
        LIMIT 500
    """).data()
    
    print(f"  缺来源: {len(missing)} 个实体")
    
    # 预加载所有本地文本文件
    corpus = {}
    for fp in os.listdir(raw_dir):
        if fp.endswith(".txt") and not fp.startswith("_"):
            try:
                corpus[fp.replace(".txt","")] = open(f"{raw_dir}/{fp}").read()
            except: pass
    
    for ent in missing[:100]:  # 批量 100 个
        name = ent["name"]
        doc = ent.get("doc","")
        
        chunk = ""
        # 先搜对应文档
        if doc and doc in corpus:
            text = corpus[doc]
            idx = text.find(name)
            if idx >= 0:
                s_idx = max(0, idx - 120)
                e_idx = min(len(text), idx + len(name) + 120)
                chunk = text[s_idx:e_idx].strip()
        
        # 全局搜
        if not chunk:
            for doc_name, text in corpus.items():
                idx = text.find(name)
                if idx >= 0:
                    s_idx = max(0, idx - 120)
                    e_idx = min(len(text), idx + len(name) + 120)
                    chunk = text[s_idx:e_idx].strip()
                    break
        
        if chunk:
            chunk = chunk[:300]
            s.run("MATCH (e:Entity {id:$id}) SET e.source_chunk = $c", id=ent["id"], c=chunk)
            stats["chunk_filled"] += 1
    
    print(f"  回填 {stats['chunk_filled']} 个来源片段")

    # ============ 最终统计 ============
    e2 = s.run("MATCH (e:Entity) RETURN count(e) AS c").data()[0]['c']
    r2 = s.run("MATCH ()-[r]->() RETURN count(r) AS c").data()[0]['c']
    d2 = s.run("MATCH (d:Document) RETURN count(d) AS c").data()[0]['c']
    
    empty_desc2 = s.run("""
        MATCH (e:Entity) WHERE e.description IS NULL OR e.description = ''
        RETURN count(e) AS c
    """).data()[0]['c']
    
    dups2 = s.run("""
        MATCH (e:Entity)
        WITH e.name AS name, e.type AS type, count(*) AS cnt WHERE cnt > 1
        RETURN count(*) AS c
    """).data()[0]['c']
    
    orphans2 = s.run("MATCH (e:Entity) WHERE NOT (e)--() RETURN count(e) AS c").data()[0]['c']

driver.close()

print(f"\n{'='*60}")
print(f"🏁 优化完成")
print(f"{'='*60}")
print(f"""
📊 优化前后对比:
                优化前  →  优化后
  实体          584    →  {e2}     (-{stats['entities_deleted']})
  关系          1,530  →  {r2}
  重复组        15     →  {dups2}
  空描述        20     →  {empty_desc2}
  孤立实体      0      →  {orphans2}
  source_chunk  28%    →  回填 +{stats['chunk_filled']}
""")
