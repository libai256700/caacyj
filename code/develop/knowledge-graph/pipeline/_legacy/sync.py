#!/usr/bin/env python3
"""
知识图谱增量同步器
每天跑一次，只处理新增/变更的文件，跳过无变化的

工作流程：
  扫描 feishu_raw/*.txt
  → 对比 _meta/{name}.json 的 file_hash
  → 新文件 → 下载？不，feishu_raw 已有 → 直接抽取入库
  → 变更文件 → 清理旧实体 → 重新抽取入库  
  → 无变化 → 跳过
"""

import json, hashlib, sys, time, subprocess, re, os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "feishu_raw"
META_DIR = RAW_DIR / "_meta"
PIPELINE_DIR = Path(__file__).parent

try:
    from neo4j import GraphDatabase
except ImportError:
    import os; os.system("pip3 install neo4j")
    from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS_PATH = BASE_DIR / "neo4j" / ".neo4j_pass"
NEO4J_PASS = NEO4J_PASS_PATH.read_text().strip() if NEO4J_PASS_PATH.exists() else ""

os.makedirs(META_DIR, exist_ok=True)


def file_hash(filepath: str) -> str:
    """计算文件 SHA256 哈希"""
    h = hashlib.sha256()
    h.update(Path(filepath).read_bytes())
    return h.hexdigest()


def load_meta(name: str) -> dict:
    """加载元数据"""
    p = META_DIR / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_meta(name: str, meta: dict):
    """保存元数据"""
    (META_DIR / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def delete_doc_from_neo4j(doc_name: str):
    """删除某个文档关联的实体和关系（v2：修复级联删除bug）
    
    ⚠️ 修复说明：旧版会删实体间的所有关系（PROVIDES/BELONGS_TO/RELATED_TO等），
       导致共享实体（公司、合作方等）及其关系被误删。
    
    新版策略：
    1. 只删 Document→Entity 的 CONTAINS 关系
    2. 保留 Entity 之间的所有关系
    3. 只删文档本身
    4. 只删真正孤立的实体（没有任何关系的）
    """
    if not NEO4J_PASS:
        print("  ⚠️ 无 Neo4j 密码，跳过清理")
        return False

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database="neo4j") as session:
        # 1) 找到该文档关联的所有实体（记录个数，不删）
        entities = session.run(
            "MATCH (d:Document {name: $name}) "
            "MATCH (d)-[:CONTAINS]->(e:Entity) "
            "RETURN e.id AS eid",
            name=doc_name
        ).data()
        eids = [r["eid"] for r in entities]

        # 2) 删除文档→实体关系（只删这个，不动实体间的关系）
        session.run(
            "MATCH (d:Document {name: $name})-[r:CONTAINS]->() DELETE r",
            name=doc_name
        )

        # 3) 删除文档节点
        result = session.run(
            "MATCH (d:Document {name: $name}) DETACH DELETE d "
            "RETURN count(d) AS cnt",
            name=doc_name
        ).data()

        # 4) 只删真正孤立的实体（没有任何关系的，确认不再被其他文档引用）
        truly_orphans = 0
        for eid in eids:
            r = session.run(
                "MATCH (e:Entity {id: $eid}) "
                "WHERE NOT (e)--() "
                "DELETE e RETURN count(e) AS cnt",
                eid=eid
            ).data()
            truly_orphans += r[0]["cnt"] if r else 0

        # 也匹配命名前缀相同但残留的孤立实体
        prefix = doc_name[:6]
        extra_orphans = session.run(
            "MATCH (e:Entity) WHERE e.id STARTS WITH $prefix "
            "AND NOT (e)--() DELETE e RETURN count(e) AS cnt",
            prefix=prefix
        ).data()

    driver.close()
    deleted_doc = result[0]["cnt"] if result else 0
    extra_cnt = extra_orphans[0]["cnt"] if extra_orphans else 0
    print(f"  🗑️ 清理旧数据: {deleted_doc} 文档, 断开{len(eids)}个实体连接, 删除{truly_orphans}个孤立节点")
    return True


def init_meta():
    """初始化/更新所有文件的元数据（不触发抽取）"""
    txt_files = sorted(RAW_DIR.glob("*.txt"))
    txt_files = [f for f in txt_files if not f.name.endswith("_result.json") and not f.name.startswith("_")]
    new_count, update_count = 0, 0
    for fp in txt_files:
        name = fp.stem
        meta = load_meta(name)
        fhash = file_hash(str(fp))
        if meta:
            if meta.get("file_hash") == fhash:
                print(f"⏭️  {name} — 无变化")
                continue
            else:
                print(f"✏️  {name} — 哈希变化，更新元数据")
                update_count += 1
        else:
            print(f"✅  {name} — 新建元数据")
            new_count += 1
        save_meta(name, {
            "file_hash": fhash,
            "last_imported": datetime.now().isoformat(),
            "doc_name": name,
            "doc_url": "",
            "file_size": fp.stat().st_size,
            "init": True
        })
    print(f"\n初始化完成: 新建{new_count}, 更新{update_count} 个元数据")
    print("下次运行 --scan 将跳过无变化的文件")


def sync():
    """增量同步主流程"""
    txt_files = sorted(RAW_DIR.glob("*.txt"))
    txt_files = [f for f in txt_files if not f.name.endswith("_result.json") and not f.name.startswith("_")]

    if not txt_files:
        print("📭 feishu_raw/ 为空，无事可做")
        return

    print(f"📊 feishu_raw/ 共 {len(txt_files)} 个文件")
    print(f"{'='*60}")
    print(f"{'文件':<30} {'状态':<12} {'上次导入':<16}")
    print(f"{'='*60}")

    stats = {"new": 0, "changed": 0, "skipped": 0, "failed": 0}
    total_entities, total_relations = 0, 0

    for fp in txt_files:
        name = fp.stem
        fhash = file_hash(str(fp))
        meta = load_meta(name)

        # 状态判断
        if not meta:
            status = "🆕 新增"
            stats["new"] += 1
        elif meta.get("file_hash") != fhash:
            status = "✏️ 变更"
            stats["changed"] += 1
        else:
            status = "⏭️ 跳过"
            stats["skipped"] += 1
            print(f"{name:<30} {status:<12} {meta.get('last_imported','未知')[:16]:<16}")
            continue

        print(f"{name:<30} {status:<12}", end="", flush=True)

        # 如果是变更，先删旧数据
        if status.startswith("✏️"):
            print(f"\n{'':>30} 清理旧数据中...")
            delete_doc_from_neo4j(name)

        # 调用 run.py 抽取
        print(f"\n{'':>30} 开始抽取...")
        try:
            script = PIPELINE_DIR / "online_extract.py"
            doc_url = meta.get("doc_url", "")
            result = subprocess.run(
                [sys.executable, str(script), str(fp), name, doc_url],
                capture_output=True, text=True, timeout=600
            )
            output = result.stdout + result.stderr

            # 统计实体数
            import_count = 0
            for line in output.split("\n"):
                if "入库完成" in line:
                    m = re.search(r'(\d+)实体', line)
                    if m:
                        total_entities += int(m.group(1))
                    m = re.search(r'(\d+)关系', line)
                    if m:
                        total_relations += int(m.group(1))
                    import_count += 1

            # 更新元数据
            save_meta(name, {
                "file_hash": fhash,
                "last_imported": datetime.now().isoformat(),
                "doc_name": name,
                "doc_url": doc_url or meta.get("doc_url", ""),
                "file_size": fp.stat().st_size,
                "entities": int(import_count)
            })

            print(f"{'':>30} ✅ 完成")
        except subprocess.TimeoutExpired:
            print(f"{'':>30} ❌ 超时(600s)")
            stats["failed"] += 1
        except Exception as e:
            print(f"{'':>30} ❌ 异常: {e}")
            stats["failed"] += 1

    # 汇总
    print(f"\n{'='*60}")
    print(f"📊 增量同步完成")
    print(f"   🆕 新增: {stats['new']}  |  ✏️ 变更: {stats['changed']}")
    print(f"   ⏭️ 跳过: {stats['skipped']}  |  ❌ 失败: {stats['failed']}")
    print(f"   📥 本次导入约: {total_entities} 实体, {total_relations} 关系")
    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--init", "-i"):
        init_meta()
    else:
        sync()
