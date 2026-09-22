#!/usr/bin/env python3
"""
任务1: 清理自引用关系 (self-referencing relationships)
任务2: 分析同名但标签不一致的类型冲突

用法: python3 analyze_cleanup_self_refs.py [--dry-run] [--force]
  --dry-run  仅预览，不实际删除
  --force    跳过确认，直接执行
"""
import sys
from neo4j import GraphDatabase

NEO4J_PASS = open("/Users/xiaoji/.openclaw/workspace/projects/knowledge-graph/neo4j/.neo4j_pass").read().strip()
dry_run = "--dry-run" in sys.argv
force = "--force" in sys.argv
drv = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))

mode_label = "🔍 预览" if dry_run else "🗑️ 清理"

def print_sep(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")

def confirm(prompt):
    if force:
        return True
    answer = input(f"\n{prompt} (y/N): ").strip().lower()
    return answer == 'y'

# ============================================================
# 任务1: 自引用关系清理
# ============================================================
print_sep("任务1: 自引用关系清理")

with drv.session() as s:
    result = s.run("""
        MATCH (a)-[r]->(a)
        WITH a.name AS name, type(r) AS rel_type, labels(a) AS labels, count(r) AS cnt
        RETURN name, labels, rel_type, cnt
        ORDER BY cnt DESC
    """)
    self_refs = [record for record in result]

if not self_refs:
    print("\n✅ 未发现自引用关系")
else:
    total_self_refs = sum(r["cnt"] for r in self_refs)
    print(f"\n发现 {total_self_refs} 条自引用关系 (涉及 {len(self_refs)} 种组合):")
    print(f"{'节点名称':<20} {'标签':<30} {'关系类型':<20} {'数量':<6}")
    print("-" * 76)
    for r in self_refs:
        name = r["name"] or "(null)"
        lbls = str(r["labels"])
        print(f"{name:<20} {lbls:<30} {r['rel_type']:<20} {r['cnt']:<6}")

    if not dry_run and confirm("\n确认删除上述自引用关系?"):
        with drv.session() as s:
            total = s.run("MATCH (a)-[r]->(a) RETURN count(r) AS c").single()["c"]
            print(f"\n  将删除 {total} 条自引用关系...")
            for rel_type in set(r["rel_type"] for r in self_refs):
                result = s.run("""
                    MATCH (a)-[r]->(a) WHERE type(r) = $rt
                    DELETE r RETURN count(r) AS c
                """, rt=rel_type)
                c = result.single()["c"]
                print(f"  已删除 {rel_type}: {c} 条")
        print(f"\n✅ 自引用关系清理完成")
        with drv.session() as s:
            remaining = s.run("MATCH (a)-[r]->(a) RETURN count(r) AS c").single()["c"]
            if remaining == 0:
                print("✅ 验证: 已无自引用关系残留")
            else:
                print(f"⚠️ 仍有 {remaining} 条自引用关系残留")
    elif dry_run:
        print(f"\n🔍 Dry-run: 将删除 {total_self_refs} 条自引用关系")
    else:
        print("\n⏭️ 跳过自引用清理")


# ============================================================
# 任务2: 类型冲突分析
# ============================================================
print_sep("任务2: 类型冲突分析 (同名不同标签)")

with drv.session() as s:
    result = s.run("""
        MATCH (n)
        WITH n.name AS name, collect(distinct labels(n)) AS labelSets, collect(n) AS nodes
        WHERE size(labelSets) > 1 AND name IS NOT NULL
        RETURN name, labelSets, [n IN nodes | {labels: labels(n), props: properties(n)}] AS details
        ORDER BY name
    """)
    conflicts = list(result)

if not conflicts:
    print("\n✅ 未发现同名节点类型冲突")
else:
    print(f"\n发现 {len(conflicts)} 组类型冲突:")
    print()

    for i, c in enumerate(conflicts, 1):
        name = c["name"]
        label_sets = c["labelSets"]
        details = c["details"]
        print(f"  [{i}] 名称: {name}")
        for j, lbs in enumerate(label_sets):
            print(f"      标签集 {j+1}: {lbs}")
        print(f"      节点数: {len(details)}")
        for j, det in enumerate(details):
            props_str = ", ".join(f"{k}={v}" for k, v in det["props"].items() if k != "name")
            print(f"        节点{j+1}: 标签={det['labels']}, 属性: {props_str}")
        print()

    print("分析建议:")
    print("-" * 40)
    for c in conflicts:
        name = c["name"]
        label_sets = c["labelSets"]
        details = c["details"]
        all_labels_flat = [lbl for ls in label_sets for lbl in ls]
        if "Entity" in all_labels_flat and len(set(all_labels_flat)) > 1:
            best = max(label_sets, key=len)
            print(f"  {name:<20} 建议保留完整标签: {best}")
            for j, det in enumerate(details):
                if det["labels"] != list(best):
                    matching = [k for k, d2 in enumerate(details) if d2["labels"] == list(best)]
                    if matching:
                        print(f"    → 多余节点可合并到标签 {best} 的节点 (索引 {matching[0]})")
                    else:
                        print(f"    → 节点{j} 标签={det['labels']} 可考虑合并到 {best}")
        else:
            print(f"  {name:<20} 所有标签集不同，建议保留为独立节点")
    print()

drv.close()

print(f"\n{'=' * 60}")
if dry_run:
    print("  🔍 Dry-run 完成 (未做任何修改)")
else:
    print("  ✅ 分析完成")
print(f"{'=' * 60}")
