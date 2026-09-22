#!/usr/bin/env python3
"""批量删除知识图谱中不合理的 USES 和 INCLUDES 关系"""
import sys
from neo4j import GraphDatabase

PASS = open("projects/knowledge-graph/neo4j/.neo4j_pass").read().strip()
URI = "bolt://localhost:7687"
driver = GraphDatabase.driver(URI, auth=("neo4j", PASS))


def query(tx, cypher):
    result = tx.run(cypher)
    return [r.data() for r in result]


def main():
    with driver.session(database="neo4j") as session:
        # === 0. 初始统计 ===
        init_nodes = session.execute_read(query, "MATCH (n) RETURN count(n) AS c")[0]["c"]
        init_rels = session.execute_read(query, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        init_uses = session.execute_read(query, "MATCH ()-[r:USES]->() RETURN count(r) AS c")[0]["c"]
        init_includes = session.execute_read(query, "MATCH ()-[r:INCLUDES]->() RETURN count(r) AS c")[0]["c"]
        print(f"【初始】节点={init_nodes}  关系={init_rels}  USES={init_uses}  INCLUDES={init_includes}")
        print()

        # === 第一步：删除 USES ===
        print(f"▶ 第一步：删除 USES（共 {init_uses} 条）")
        if init_uses > 0:
            result = session.execute_write(query, "MATCH ()-[r:USES]->() DELETE r RETURN count(r) AS c")
            deleted = result[0]["c"]
            remaining = session.execute_read(query, "MATCH ()-[r:USES]->() RETURN count(r) AS c")[0]["c"]
            print(f"   删除={deleted}  剩余 USES={remaining}")
        else:
            print(f"   无需删除，USES 已为 0")
        print()

        # === 第二步：删除 INCLUDES ===
        print(f"▶ 第二步：删除 INCLUDES（共 {init_includes} 条）")
        if init_includes > 0:
            result = session.execute_write(query, "MATCH ()-[r:INCLUDES]->() DELETE r RETURN count(r) AS c")
            deleted = result[0]["c"]
            remaining = session.execute_read(query, "MATCH ()-[r:INCLUDES]->() RETURN count(r) AS c")[0]["c"]
            print(f"   删除={deleted}  剩余 INCLUDES={remaining}")
        else:
            print(f"   无需删除，INCLUDES 已为 0")
        print()

        # === 第三步：最终验证 ===
        final_nodes = session.execute_read(query, "MATCH (n) RETURN count(n) AS c")[0]["c"]
        final_rels = session.execute_read(query, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        final_uses = session.execute_read(query, "MATCH ()-[r:USES]->() RETURN count(r) AS c")[0]["c"]
        final_includes = session.execute_read(query, "MATCH ()-[r:INCLUDES]->() RETURN count(r) AS c")[0]["c"]

        print("=" * 50)
        print("✅ 验证结果")
        print(f"   节点数:      {init_nodes} → {final_nodes} (不变)")
        print(f"   关系总数:    {init_rels} → {final_rels} (减少 {init_rels - final_rels})")
        print(f"   USES:        {init_uses} → {final_uses}")
        print(f"   INCLUDES:    {init_includes} → {final_includes}")
        print()

        if final_uses == 0 and final_includes == 0:
            print("✅ USES 和 INCLUDES 均已清零，清理完成。")
        else:
            print(f"⚠️  异常：USES={final_uses}  INCLUDES={final_includes}，操作可能不完整。")

    driver.close()


if __name__ == "__main__":
    main()
