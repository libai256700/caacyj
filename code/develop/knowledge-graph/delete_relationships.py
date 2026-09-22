#!/usr/bin/env python3
"""
删除两条错误的实体关系：
1. 风→起飞前动力装置检查 的 AFFECTS 关系
2. 地面效应的所有出向关系
"""

from neo4j import GraphDatabase
import sys

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "yj123456"

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

def run_query(tx, cypher, params=None):
    return list(tx.run(cypher, params or {}))

def print_table(rows, headers):
    """简易表格打印"""
    if not rows:
        print("  (无结果)")
        return
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, v in enumerate(row):
            s = str(v)
            if len(s) > col_widths[i]:
                col_widths[i] = min(len(s), 60)
    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_row = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |"
    print(sep)
    print(header_row)
    print(sep.replace("-", "="))
    for row in rows:
        vals = []
        for i, v in enumerate(row):
            s = str(v)
            vals.append(s.ljust(col_widths[i])[:col_widths[i]])
        print("| " + " | ".join(vals) + " |")
        print(sep)

with driver.session(database="neo4j") as session:
    print("=" * 70)
    print("📋 步骤1：预览 — 风→起飞前动力装置检查 的 AFFECTS 关系")
    print("=" * 70)
    result = session.execute_read(run_query,
        "MATCH (a {name:'风'})-[r:AFFECTS]->(b {name:'起飞前动力装置检查'}) "
        "RETURN a.name AS source, type(r) AS rel, b.name AS target, id(r) AS rel_id, "
        "       r.detail AS detail"
    )
    if result:
        print_table([(r['source'], r['rel'], r['target'], r['rel_id'], r.get('detail','')) for r in result],
                     ["Source", "Rel", "Target", "Rel ID", "Detail"])
    else:
        print("  ❓ 未找到该关系")

    print()
    print("=" * 70)
    print("📋 步骤2：预览 — 地面效应 的所有出向关系")
    print("=" * 70)
    result = session.execute_read(run_query,
        "MATCH (n {name:'地面效应'})-[r]->(m) "
        "RETURN type(r) AS rel_type, count(r) AS cnt, "
        "       collect(m.name)[0..10] AS targets "
        "ORDER BY cnt DESC"
    )
    if result:
        print_table([(r['rel_type'], r['cnt'], ", ".join(r['targets'])) for r in result],
                     ["关系类型", "数量", "目标节点"])
    else:
        print("  ❓ 未找到出向关系")

    # 确认
    print()
    print("⚠️  即将执行删除操作。确认继续？(y/N)")
    # 非交互式，直接继续

    # ========== 执行删除 ==========
    print("\n" + "=" * 70)
    print("✂️  执行删除操作 1：删除 风→起飞前动力装置检查 的 AFFECTS 关系")
    print("=" * 70)
    result = session.execute_write(run_query,
        "MATCH (a {name:'风'})-[r:AFFECTS]->(b {name:'起飞前动力装置检查'}) "
        "DELETE r RETURN count(r) AS deleted"
    )
    print(f"  已删除 {result[0]['deleted']} 条关系")

    print()
    print("=" * 70)
    print("✂️  执行删除操作 2：删除 地面效应 的所有出向关系")
    print("=" * 70)
    result = session.execute_write(run_query,
        "MATCH (n {name:'地面效应'})-[r]->() "
        "DELETE r RETURN count(r) AS deleted"
    )
    print(f"  已删除 {result[0]['deleted']} 条关系")

    # ========== 验证 ==========
    print("\n" + "=" * 70)
    print("✅ 验证：删除后检查")
    print("=" * 70)

    # 验证1
    result = session.execute_read(run_query,
        "MATCH (a {name:'风'})-[r:AFFECTS]->(b {name:'起飞前动力装置检查'}) "
        "RETURN count(r) AS c"
    )
    print(f"  验证1 — 风→起飞前动力装置检查 AFFECTS 剩余关系数: {result[0]['c']}")
    assert result[0]['c'] == 0, "❌ 验证失败：风→起飞前动力装置检查 关系未删除干净！"

    # 验证2
    result = session.execute_read(run_query,
        "MATCH (n {name:'地面效应'})-[r]->() "
        "RETURN count(r) AS c"
    )
    print(f"  验证2 — 地面效应 出向剩余关系数: {result[0]['c']}")
    assert result[0]['c'] == 0, "❌ 验证失败：地面效应出向关系未删除干净！"

    # 验证3 - 地面效应实体本身还在
    result = session.execute_read(run_query,
        "MATCH (n {name:'地面效应'}) RETURN count(n) AS c, labels(n) AS labels"
    )
    print(f"  验证3 — 地面效应 实体本身存在: count={result[0]['c']}, labels={result[0]['labels']}")
    assert result[0]['c'] >= 1, "❌ 验证失败：地面效应实体也不见了！"

    print("\n🎉 全部操作完成，验证通过！")

driver.close()
