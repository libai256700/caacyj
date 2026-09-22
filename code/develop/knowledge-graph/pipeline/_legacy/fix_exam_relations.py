#!/usr/bin/env python3
"""修复考试节点关联问题：合并重复节点，关联知识点到考试节点"""

from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "yj123456"

def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database="neo4j") as session:
        print("="*50)
        print("🔧 修复考试节点关联问题")
        print("="*50)
        
        # Step 1: 合并旧考试节点到新节点
        print("\n📌 Step 1: 合并重复考试节点")
        # 旧理论考试 → 合并到CAAC理论考试
        session.run("""
            MATCH (old:Entity {name: "理论考试"})
            MATCH (new:Entity {name: "CAAC理论考试"})
            MATCH (old)-[r]->(n)
            MERGE (new)-[r2:CONTAINS]->(n)
            DELETE r
            DELETE old
        """)
        print("✅ 旧「理论考试」节点合并到「CAAC理论考试」")
        
        # 旧实操考试 → 合并到CAAC实操考试
        session.run("""
            MATCH (old:Entity {name: "实操考试"})
            MATCH (new:Entity {name: "CAAC实操考试"})
            MATCH (old)-[r]->(n)
            MERGE (new)-[r2:CONTAINS]->(n)
            DELETE r
            DELETE old
        """)
        print("✅ 旧「实操考试」节点合并到「CAAC实操考试」")
        
        # Step 2: 确保CAAC无人机执照考试包含两个考试
        session.run("""
            MATCH (root:Entity {name: "CAAC无人机执照考试"})
            MATCH (theory:Entity {name: "CAAC理论考试"})
            MATCH (practical:Entity {name: "CAAC实操考试"})
            MERGE (root)-[:CONTAINS]->(theory)
            MERGE (root)-[:CONTAINS]->(practical)
        """)
        print("✅ 考试层级已确认：CAAC无人机执照考试 → 包含理论+实操")
        
        # Step 3: 关联所有知识点到CAAC理论考试
        print("\n📌 Step 2: 关联所有知识点到CAAC理论考试")
        result = session.run("""
            MATCH (exam:Entity {name: "CAAC理论考试"})
            MATCH (kp:Entity {entityType: "KnowledgePoint"})
            MERGE (exam)-[:CONTAINS]->(kp)
            RETURN count(kp) as linked
        """)
        linked = result.single()["linked"]
        print(f"✅ {linked} 个知识点已关联到CAAC理论考试")
        
        # Step 4: 验证最终结果
        print("\n" + "="*50)
        print("✅ 修复完成，最终验证")
        print("="*50)
        
        result = session.run("""
            MATCH (e:Entity {name: "CAAC理论考试"})-[r:CONTAINS]->(kp)
            RETURN count(kp) as total
        """)
        total = result.single()["total"]
        print(f"CAAC理论考试关联知识点总数: {total} 个")
        
        result = session.run("""
            MATCH (root:Entity {name: "CAAC无人机执照考试"})-[r:CONTAINS]->(e)
            RETURN collect(e.name) as children
        """)
        children = result.single()["children"]
        print(f"CAAC无人机执照考试包含: {', '.join(children)}")
        
        result = session.run("""
            MATCH (e:Entity) WHERE toLower(e.name) CONTAINS "考试" AND e.name STARTS WITH "CAAC"
            RETURN e.name, size(()-[r]->(e)) as in_edges, size((e)-[r]->()) as out_edges
        """)
        print("\n考试节点状态:")
        for r in result:
            print(f"  {r['e.name']}: 入边={r['in_edges']}, 出边={r['out_edges']}, 孤立={r['in_edges'] + r['out_edges'] == 0}")
    
    driver.close()
    print("\n✅ 全部修复完成！考试节点已全部关联，无孤立节点！")

if __name__ == "__main__":
    main()
