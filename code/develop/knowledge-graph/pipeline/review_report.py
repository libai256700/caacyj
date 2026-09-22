#!/usr/bin/env python3
"""review_report.py v2 — 单文件复盘（适配多标签模型）
用法: python3 review_report.py <文档名>
示例: python3 review_report.py 价格表
"""
import sys
from neo4j import GraphDatabase

NEO4J_PASS = open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass").read().strip()
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))

doc = sys.argv[1] if len(sys.argv) > 1 else None
if not doc:
    print("用法: python3 review_report.py <文档名>")
    sys.exit(1)

with driver.session() as s:
    # 1. 自有实体
    r = s.run("""
        MATCH (d:Document {name:$doc})-[:DESCRIBES]->(e)
        RETURN count(e) AS c
    """, doc=doc)
    own = r.single()["c"]

    # 2. Top5 实体
    r = s.run("""
        MATCH (d:Document {name:$doc})-[:DESCRIBES]->(e)
        RETURN labels(e)[0] AS t, e.name AS nm
        LIMIT 5
    """, doc=doc)
    top5 = [(row['t'], row['nm']) for row in r]

    # 3. 类型分布
    r = s.run("""
        MATCH (d:Document {name:$doc})-[:DESCRIBES]->(e)
        RETURN labels(e)[0] AS t, count(*) AS c
        ORDER BY c DESC
    """, doc=doc)
    type_dist = {row['t']: row['c'] for row in r}

    # 4. 关联关系（实体与外部实体之间的连接）
    r = s.run("""
        MATCH (d:Document {name:$doc})-[:DESCRIBES]->(e)
        MATCH (e)-[rel]->(other)
        WHERE NOT (d)-[:DESCRIBES]->(other) AND NOT other:Document
        RETURN DISTINCT labels(e)[0] AS et, e.name AS en,
               type(rel) AS rt, labels(other)[0] AS ot, other.name AS on
        LIMIT 15
    """, doc=doc)
    linked = [(row['et'], row['en'], row['rt'], row['ot'], row['on']) for row in r]

    # 5. 跨文件污染（同一实体被多个文档DESCRIBES）
    r = s.run("""
        MATCH (d1:Document {name:$doc})-[:DESCRIBES]->(e)
        MATCH (d2:Document)-[:DESCRIBES]->(e)
        WHERE d2.name <> $doc
        RETURN e.name AS nm, labels(e)[0] AS t, collect(d2.name) AS others
        LIMIT 10
    """, doc=doc)
    cross = [(row['nm'], row['t'], row['others']) for row in r]

driver.close()

report = f"""
📊 复盘报告 — {doc}

▶ 自有实体: {own} 个
▶ 类型分布: {type_dist}

前5实体:
""" + "\n".join(f"  • [{t}] {n}" for t, n in top5)

if linked:
    report += "\n\n关联关系:\n" + "\n".join(
        f"  [{et}]{en} →[{rt}]→ [{ot}]{on}" for et, en, rt, ot, on in linked
    )

if cross:
    report += "\n\n跨文件共享实体:\n" + "\n".join(
        f"  [{t}] {nm} (也属: {', '.join(others)})" for nm, t, others in cross
    )

# 异常检测
alerts = []
try:
    fpath = f"/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/feishu_raw/{doc}.txt"
    total_chars = len(open(fpath).read())
    expected = max(1, int(total_chars / 1000 * 3))
    if own < expected * 0.5:
        alerts.append(f"⚠️  实体数({own})远低于预期(~{expected})，可能抽取不完整")
except:
    pass

if own == 0:
    alerts.append("⚠️  无自有实体，请检查抽取是否成功")

if alerts:
    report += "\n\n⚠️  异常:\n" + "\n".join(f"  • {a}" for a in alerts)
else:
    report += "\n\n✅ 未检测到异常"

print(report)
