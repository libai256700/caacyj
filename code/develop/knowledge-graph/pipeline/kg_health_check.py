#!/usr/bin/env python3
"""kg_health_check.py v2 — 知识图谱健康检查（适配多标签模型）
用法: python3 kg_health_check.py [--full]
"""
import sys
from neo4j import GraphDatabase

NEO4J_PASS = open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass").read().strip()
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))
full = "--full" in sys.argv
stats_only = "--stats-only" in sys.argv

# 类型白名单 — 对齐 extract_one.py（含 Entity 通用标签）
WHITELIST = {
    'Company','Organization','PlatformPresence','Event','Course','Exam',
    'Certification','KnowledgePoint','Category','Student','Customer','Teacher','Instructor','Person',
    'Policy','Regulation','SocialContent','Skill','EducationRequirement',
    'AircraftType','LicenseLevel','WeightClass','Location','Position',
    'Chapter','Section','Scenario','DesignTool','FabricationStep',
    'QuestionBank','TrainingTrack','Value','ChunkRef','RejectedEntity',
    'Document',  # 文档节点
    'Entity',    # 所有节点的通用标签
}

# 关系白名单 — 对齐 extract_one.py REL_WHITELIST
ALLOWED_RELS = {
    'DESCRIBES','OFFERS','INCLUDES','AWARDS','REQUIRES','USES',
    'ISSUED_BY','LOCATED_AT','REGULATES','BELONGS_TO','MENTIONS',
    'HAS_CLASS','HAS_LEVEL','REFERS_TO','REQUIRES_SKILL','HAS_PROPERTY',
    'SUBCLASS_OF','PART_OF','DEFINED_BY',
    'CONTAINS',  # Document→Entity 所属关系
    'AFFECTS',   # 风→飞行操作 影响关系
}

SAMPLE_LIMIT = 20
issues = []

with driver.session() as s:
    print("=" * 55)
    print("📊 知识图谱健康检查 v2 (多标签模型)")
    print("=" * 55)

    # §6.1 覆盖率
    nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    docs = s.run("MATCH (d:Document) RETURN count(d) AS c").single()["c"]
    
    # 实体数 = 非Document节点
    entities = nodes - docs if nodes > docs else nodes
    print(f"§6.1 覆盖率: {nodes}节点 {rels}关系 {docs}文档 {entities}实体")
    
    if stats_only:
        driver.close()
        sys.exit(0)
    
    if entities == 0:
        print("  ⚠️  图谱为空")
        issues.append("图谱为空，暂无数据")

    # §6.2 类型合规（多标签模型）
    r = s.run("""
        MATCH (n) WHERE NOT n:Document AND coalesce(n.quarantined, false) = false
        WITH coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity') AS lt, count(*) AS c
        WHERE NOT lt IN $wl
        RETURN lt, c ORDER BY c DESC
    """, wl=list(WHITELIST))
    bad_types = [(row['lt'], row['c']) for row in r]
    bad_total = sum(c for _, c in bad_types)
    print(f"\n§6.2 类型合规: {bad_total}/{entities} 节点使用了白名单外类型")
    if bad_types:
        issues.append(f"类型不合规: {bad_total} 个节点")
        for lt, c in bad_types:
            print(f"  ❌ {lt}: {c}")

    # §6.3 关系合规
    r = s.run("""
        MATCH ()-[r]->() WHERE NOT type(r) IN $ar
        RETURN type(r) AS rt, count(*) AS c ORDER BY c DESC
    """, ar=list(ALLOWED_RELS))
    bad_rels = [(row['rt'], row['c']) for row in r]
    total_bad = sum(c for _, c in bad_rels)
    print(f"\n§6.3 关系合规: {total_bad}/{rels} 关系不匹配白名单")
    if bad_rels:
        issues.append(f"关系不合规: {total_bad} 条")
        for rt, c in bad_rels:
            print(f"  ❌ {rt}: {c}")

    # §6.4 悬挂引用
    # 起点不存在
    r = s.run("""
        MATCH (a)-[r]->(b) 
        WHERE a IS NULL
        RETURN count(*) AS c
    """)
    print(f"\n§6.4 悬挂引用 (起点不存在): (N/A — Neo4j 自动保证)")

    # 自引用
    r = s.run("MATCH (n)-[r]->(n) RETURN type(r) AS rt, n.name AS nm")
    self_refs = [(row['rt'], row['nm']) for row in r]
    print(f"  自引用: {len(self_refs)} 条")
    if self_refs:
        issues.append(f"自引用: {len(self_refs)} 条")
        for rt, nm in self_refs:
            print(f"  ⚠️  {nm} →[{rt}]→ 自身")

    # 类型冲突（同名不同类）
    r = s.run("""
        MATCH (n) WHERE NOT n:Document
          AND n.name IS NOT NULL
          AND coalesce(n.quarantined, false) = false
        WITH n.name AS nm,
             collect(DISTINCT coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity')) AS types
        WHERE size(types) > 1
        RETURN nm, types ORDER BY nm
    """)
    conflicts = [(row['nm'], row['types']) for row in r]
    print(f"\n§6.4 类型冲突 (同名不同类): {len(conflicts)} 组")
    if conflicts:
        issues.append(f"类型冲突: {len(conflicts)} 组同名节点类型不一致")
        for nm, types in conflicts[:SAMPLE_LIMIT]:
            print(f"  ⚠️  '{nm}': {types}")
        if len(conflicts) > SAMPLE_LIMIT:
            print(f"  ... 另有 {len(conflicts) - SAMPLE_LIMIT} 组未显示")

    # §6.5 文档检查
    if docs > 0:
        orphan_docs = s.run("""
            MATCH (d:Document) WHERE NOT (d)-[:CONTAINS]->()
            RETURN count(d) AS c
        """).single()["c"]
        print(f"\n§6.5 文档检查: {orphan_docs}/{docs} 文档无CONTAINS关系")
        if orphan_docs > 0:
            issues.append(f"文档孤儿: {orphan_docs} 个文档无CONTAINS关联实体")

    # §6.6 无关系孤岛
    orphan_total = s.run("""
        MATCH (n)
        WHERE NOT (n)--()
          AND NOT n:Document
          AND coalesce(n.quarantined, false) = false
        RETURN count(n) AS c
    """).single()["c"]
    r = s.run("""
        MATCH (n)
        WHERE NOT (n)--()
          AND NOT n:Document
          AND coalesce(n.quarantined, false) = false
        RETURN coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity') AS t, n.name AS nm
        ORDER BY t, coalesce(n.name, '')
        LIMIT $limit
    """, limit=SAMPLE_LIMIT)
    orphans = [(row['t'], row['nm']) for row in r]
    print(f"\n§6.6 孤立节点: {orphan_total} 个")
    if orphan_total:
        issues.append(f"孤立节点: {orphan_total} 个实体无任何关系")
        for t, nm in orphans:
            print(f"  ⚠️  [{t}] {nm}")
        if orphan_total > len(orphans):
            print(f"  ... 另有 {orphan_total - len(orphans)} 个未显示")

    # §6.7 节点类型分布
    if full:
        print(f"\n§6.7 节点类型分布:")
        r = s.run("""
            MATCH (n) WHERE NOT n:Document AND coalesce(n.quarantined, false) = false
            RETURN coalesce([label IN labels(n) WHERE label <> 'Entity'][0], 'Entity') AS t, count(*) AS c ORDER BY c DESC
        """)
        for row in r:
            bar = "█" * (row['c'] // 2)
            print(f"  {row['t']:<20} {row['c']:>4} {bar}")

    print(f"\n§6.8 状态: {'✅ 通过' if not issues else '⚠️  有问题'}")

driver.close()

if issues:
    print(f"\n🚨 发现 {len(issues)} 个问题:")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
else:
    print("\n✅ 健康检查全部通过")
