#!/usr/bin/env python3
"""修复GPT-5.5审计发现的4个剩余问题"""

from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "yj123456"))

with driver.session(database="neo4j") as session:
    all_docs = [r["d.name"] for r in session.run("MATCH (d:Document) RETURN d.name")]

    # 1. 补file_token
    print("📌 Step 1: 补写file_token")
    fix_tokens = {
        "综合问答": "OWNJbG04rohTi3xrwsecjLyvnlh",
        "综合问答.txt": "OWNJbG04rohTi3xrwsecjLyvnlh",
        "旋翼无人机": "PtPrbhh1GozODPxm40BcsNhonMf",
        "旋翼无人机.txt": "PtPrbhh1GozODPxm40BcsNhonMf",
        "系统组成及介绍": "EI9HbSTsQosOKdxsDX7cfDqJnVe",
        "系统组成及介绍.txt": "EI9HbSTsQosOKdxsDX7cfDqJnVe",
        "无人机任务规划": "B37vbbMYYoOXpsx4AQEcqkW4nKc",
        "无人机任务规划.txt": "B37vbbMYYoOXpsx4AQEcqkW4nKc",
        "无人机教员题库.docx": "NlGsbmxi7oZ1QIxMC84cCfO4nfW",
        "无人机飞行手册、法律法规及其他": "Q5Xebw0SVoZoVzxQx9McovZQnye",
        "无人机飞行手册、法律法规及其他.txt": "Q5Xebw0SVoZoVzxQx9McovZQnye",
        "无人机操作注意事项": "T9RebmYHJoRuKpx2Utyc5cZNnkd",
        "无人机操作注意事项.txt": "T9RebmYHJoRuKpx2Utyc5cZNnkd",
        "气象": "EJRobhoePo1MCCxjHeRcsvaFnCg",
        "气象.txt": "EJRobhoePo1MCCxjHeRcsvaFnCg",
        "空中交通管制": "Cr6ObOTk7oVRymxTY02ceRWmnsc",
        "空中交通管制.txt": "Cr6ObOTk7oVRymxTY02ceRWmnsc",
        "概述": "DG8EbFAWaojWZcxL0FmckwPwnHd",
        "飞行原理与飞行性能": "KCPRbyOD3oMVSGx3w6EcKXWvnbb",
    }
    for name, token in fix_tokens.items():
        if name in all_docs:
            session.run(
                "MATCH (d:Document {name: $name}) "
                "SET d.file_token = $token, "
                "    d.source_platform = 'feishu', "
                "    d.source_folder = 'AcmEfWkaglzaj2dhS8rctUoAnQd'",
                name=name, token=token
            )
            print(f"  ✅ {name}")
        else:
            print(f"  ⚠️ 不存在: {name}")

    # 2. 合并重复Document
    print("\n📌 Step 2: 合并重复Document")
    pairs = [
        ("综合问答","综合问答.txt"), ("旋翼无人机","旋翼无人机.txt"),
        ("系统组成及介绍","系统组成及介绍.txt"), ("无人机任务规划","无人机任务规划.txt"),
        ("无人机飞行手册、法律法规及其他","无人机飞行手册、法律法规及其他.txt"),
        ("无人机操作注意事项","无人机操作注意事项.txt"), ("气象","气象.txt"),
        ("空中交通管制","空中交通管制.txt")]
    for main, dup in pairs:
        if main in all_docs and dup in all_docs:
            session.run(
                "MATCH (dup:Document {name: $dup})-[r:CONTAINS]->(e) "
                "MATCH (main:Document {name: $main}) "
                "MERGE (main)-[:CONTAINS]->(e) "
                "DELETE r",
                dup=dup, main=main
            )
            session.run("MATCH (d:Document {name: $n}) DELETE d", n=dup)
            print(f"  ✅ {dup} -> 合并到 {main}")

    # 3. 文档关联CAAC理论考试
    print("\n📌 Step 3: 文档关联CAAC理论考试")
    skip_docs = ["云技资料库","培训学员记录"]
    for doc in all_docs:
        if doc in skip_docs:
            continue
        session.run(
            "MATCH (d:Document {name: $dname}) "
            "MATCH (e:Entity {name: 'CAAC理论考试'}) "
            "MERGE (d)-[:CONTAINS]->(e)",
            dname=doc
        )
    print(f"  ✅ {len(all_docs)} 个文档已关联")

    # 4. 清理考试作弊处罚
    print("\n📌 Step 4: 清理冗余")
    session.run("MATCH (e:Entity {name: '考试作弊处罚'})-[r]->() DELETE r")
    session.run("MATCH (e:Entity {name: '考试作弊处罚'}) DELETE e")
    print("  ✅ 考试作弊处罚已删除")

    # 最终验证
    print("\n" + "="*50)
    print("📊 最终验证")
    remaining = [r["d.name"] for r in session.run("MATCH (d:Document) RETURN d.name ORDER BY d.name")]
    print(f"Document节点剩余({len(remaining)}个):")
    for n in remaining:
        row = session.run("MATCH (d:Document {name: $n}) RETURN d.file_token AS tok", n=n).single()
        tok = row["tok"]
        print(f"  {n} | token={'✅' if tok else '❌'}")
    total_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]
    isolated = session.run("MATCH (n:Entity) WHERE NOT (n)-->() AND NOT ()-->(n) RETURN count(n) AS cnt").single()["cnt"]
    cheat_check = list(session.run("MATCH (e:Entity {name: '考试作弊处罚'}) RETURN e"))
    print(f"\n总关系: {total_rels}")
    print(f"完全孤立节点: {isolated}")
    print(f"作弊处罚残留: {len(cheat_check)}")

    # 查考试层级
    print("\n📌 CAAC考试体系:")
    exams = session.run(
        "MATCH (e:Entity {entityType:'Exam'}) "
        "OPTIONAL MATCH (e)-[r:CONTAINS]->(child) "
        "RETURN e.name, count(child) AS children"
    )
    for e in exams:
        print(f"  {e['e.name']}: 包含{e['children']}个子节点")

driver.close()
