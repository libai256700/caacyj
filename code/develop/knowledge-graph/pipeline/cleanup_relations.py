#!/usr/bin/env python3
"""抽取后自动清理违规关系：双保险
用法: python3 cleanup_relations.py [--dry-run]
  --dry-run  仅预览要清理的内容，不实际删除
"""
import sys
from neo4j import GraphDatabase

NEO4J_PASS = open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass").read().strip()
dry_run = "--dry-run" in sys.argv
d = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))

# 清理前统计
with d.session() as s:
    pre_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    pre_rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

mode_label = "🔍 预览" if dry_run else "🗑️ 清理"
print(f"\n📊 清理前: {pre_nodes}节点 {pre_rels}关系  | 模式: {mode_label}")

total_deleted = 0

def do_delete(cql, label):
    """执行删除或预览，返回计数"""
    with d.session() as s:
        if dry_run:
            count_cql = cql.replace("DELETE r RETURN count(r) AS c", "RETURN count(r) AS c")
            r = s.run(count_cql)
            c = r.single()["c"]
        else:
            r = s.run(cql)
            c = r.single()["c"]
    print(f"  {mode_label} {label}: {c}")
    return c

# 1. SalaryItem 所有外出关系
c1 = do_delete("MATCH (e:Entity {type:'SalaryItem'})-[r]->() DELETE r RETURN count(r) AS c",
               "SalaryItem外出关系")
if not dry_run: total_deleted += c1
else: print(f'  (将删除 {c1} 条)')

# 2. SalaryRange 所有外出关系
c2 = do_delete("MATCH (e:Entity {type:'SalaryRange'})-[r]->() DELETE r RETURN count(r) AS c",
               "SalaryRange外出关系")
if not dry_run: total_deleted += c2
else: print(f'  (将删除 {c2} 条)')

# 3. LOCATED_IN 指向非Location
c3 = do_delete("""
    MATCH (a)-[r:LOCATED_IN]->(b)
    WHERE b.type <> 'Location' OR b.type IS NULL
    DELETE r RETURN count(r) AS c
""", "LOCATED_IN→非Location")
if not dry_run: total_deleted += c3
else: print(f'  (将删除 {c3} 条)')

# 4. MANAGES/REGULATES 主体违规
c4 = do_delete("""
    MATCH (a)-[r:MANAGES|REGULATES]->(b)
    WHERE a.type IN ['SalaryItem','Product','Event','SalaryRange']
    DELETE r RETURN count(r) AS c
""", "违规MANAGES/REGULATES主体")
if not dry_run: total_deleted += c4
else: print(f'  (将删除 {c4} 条)')

# 5. BELONGS_TO 源头违规
c5 = do_delete("""
    MATCH (a)-[r:BELONGS_TO]->(b)
    WHERE a.type IN ['SalaryItem','SalaryRange']
    DELETE r RETURN count(r) AS c
""", "违规BELONGS_TO源头")
if not dry_run: total_deleted += c5
else: print(f'  (将删除 {c5} 条)')

# 清理后统计
with d.session() as s:
    nb = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

d.close()

print(f"📊 清理后: {nb}节点 {rels}关系")
if dry_run:
    print(f"🔍 预览: 将删除 {total_deleted} 条违规关系")
else:
    print(f"🗑️ 共删除: {total_deleted} 条违规关系")
