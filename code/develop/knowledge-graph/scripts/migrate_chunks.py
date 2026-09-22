#!/usr/bin/env python3
"""
一次性迁移脚本：将 Neo4j 中的 Chunk 节点迁移到 SQLite

流程：
1. 从 Neo4j 读取所有 Chunk 节点 (chunk_id, text, doc_name, chunk_index)
2. 批量写入 SQLite
3. 校验数量一致
4. 确认后：删除 Neo4j 中的 Chunk 节点 + 删除 chunk_embedding 向量索引
"""

import sys, time, json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from neo4j import GraphDatabase
from rag_store.sqlite_store import RagStore
from rag_store.index_freshness import check_index_freshness, dumps_report

# ============ 配置 ============
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text().strip()

DB_PATH = str(BASE_DIR / "rag_chunks.db")

BATCH_SIZE = 500    # 每批写入 SQLite 条数
STREAM_BATCH = 200  # 从 Neo4j 流式读取的批次大小


def get_neo4j_chunks():
    """流式读取 Neo4j 中所有 Chunk 节点"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        total = s.run("MATCH (c:Chunk) RETURN count(c) AS cnt").single()["cnt"]
        print(f"📦 Neo4j 中共 {total} 个 Chunk 节点")
        
        skip = 0
        while skip < total:
            rows = s.run(
                "MATCH (c:Chunk) RETURN c.chunk_id AS chunk_id, "
                "c.text AS text, c.doc_name AS doc_name, "
                "c.chunk_index AS chunk_index "
                "ORDER BY c.chunk_id SKIP $skip LIMIT $limit",
                skip=skip, limit=STREAM_BATCH
            ).data()
            if not rows:
                break
            for r in rows:
                yield {
                    "chunk_id": r["chunk_id"],
                    "text": r.get("text") or "",
                    "doc_name": r.get("doc_name") or "",
                    "chunk_index": r.get("chunk_index") or 0,
                }
            skip += len(rows)
            print(f"  🔄 已读取 {skip}/{total}", end="\r")
    print()
    driver.close()


def migrate(confirm: bool = False):
    """执行迁移"""
    t0 = time.time()
    
    # 1. 初始化 SQLite
    print("🔧 初始化 SQLite...")
    store = RagStore(DB_PATH)
    store.init_tables()
    print(f"   ✅ SQLite 就绪: {DB_PATH}")
    
    # 2. 流式迁移
    print("📖 从 Neo4j 流式读取 Chunk 节点...")
    batch = []
    migrated = 0
    for chunk in get_neo4j_chunks():
        batch.append(chunk)
        if len(batch) >= BATCH_SIZE:
            store.store_chunks_batch(batch)
            migrated += len(batch)
            print(f"   ✅ 已迁移 {migrated} 条", end="\r")
            batch = []
    
    if batch:
        store.store_chunks_batch(batch)
        migrated += len(batch)
    
    print(f"\n   ✅ 全部迁移完成: {migrated} 条耗时 {time.time()-t0:.1f}s")
    
    # 3. 校验
    print("\n🔍 校验...")
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with neo4j_driver.session() as s:
        neo4j_count = s.run("MATCH (c:Chunk) RETURN count(c) AS cnt").single()["cnt"]
    sqlite_count = store.count_chunks()
    
    print(f"   Neo4j: {neo4j_count}  →  SQLite: {sqlite_count}")
    
    if neo4j_count != sqlite_count:
        print(f"❌ 数量不匹配！操作终止，数据未清理")
        print(f"   SQLite 数据保留在: {DB_PATH}")
        neo4j_driver.close()
        store.close()
        return False
    
    print(f"✅ 校验通过！所有 Chunk 数据已安全迁移到 SQLite")
    
    # 4. 确认后清理 Neo4j
    if confirm:
        print("\n⚠️  将在 3 秒后删除 Neo4j 中的 Chunk 节点和 chunk_embedding 索引...")
        print("   按 Ctrl+C 取消，或等 3 秒自动执行")
        time.sleep(3)
        
        with neo4j_driver.session() as s:
            # 先删索引
            try:
                s.run("DROP INDEX chunk_embedding IF EXISTS")
                print("   ✅ 已删除 chunk_embedding 索引")
            except Exception as e:
                print(f"   ⚠️  删除索引时出错 (可能不存在): {e}")
            
            # 再删节点。先计数再删除，避免 DELETE 后 RETURN count(*) 语义不可靠。
            deleted = s.run("MATCH (c:Chunk) RETURN count(c) AS cnt").single()["cnt"]
            s.run("MATCH (c:Chunk) DETACH DELETE c").consume()
            print(f"   ✅ 已从 Neo4j 删除 {deleted} 个 Chunk 节点")
        
        print("\n🎉 迁移+清理完成！")
    else:
        print("\nℹ️  Neo4j 中的 Chunk 节点和索引已保留（未传 --confirm）")
        print(f"   如需清理，执行: python3 scripts/migrate_chunks.py --confirm")
    
    print(f"\n📊 SQLite 统计: {json.dumps(store.stats(), ensure_ascii=False)}")
    
    neo4j_driver.close()
    store.close()
    return True


if __name__ == "__main__":
    confirm = "--confirm" in sys.argv
    check_indexes = "--check-indexes" in sys.argv
    auto_rebuild_indexes = "--auto-rebuild-indexes" in sys.argv
    if not confirm:
        print("=" * 50)
        print("🔔 注意：这是 DRY-RUN 模式，不会删除 Neo4j 数据")
        print("   确认迁移+清理请加 --confirm 参数")
        print("=" * 50)
    
    success = migrate(confirm=confirm)
    if success and check_indexes:
        report = check_index_freshness(auto_rebuild=auto_rebuild_indexes)
        print("\n🔍 索引新鲜度自检:")
        print(dumps_report(report))
        success = report["fresh"]
    sys.exit(0 if success else 1)
