#!/usr/bin/env python3
"""
回溯已有知识图谱数据：补填 source_chunk / source_doc / doc_url
对已入库但缺少来源信息的实体，从 feishu_raw 中找回原文片段补上
"""

import json, re, sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
NEO4J_PASS_PATH = BASE_DIR / "neo4j" / ".neo4j_pass"
RAW_DIR = BASE_DIR / "feishu_raw"
META_DIR = RAW_DIR / "_meta"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = NEO4J_PASS_PATH.read_text().strip() if NEO4J_PASS_PATH.exists() else ""

try:
    from neo4j import GraphDatabase
except ImportError:
    import os; os.system("pip3 install neo4j")
    from neo4j import GraphDatabase


def extract_chunk(text: str, name: str, context: int = 120) -> str:
    """从原文中提取实体名周围的片段"""
    idx = text.find(name)
    if idx < 0:
        return ""
    start = max(0, idx - context)
    end = min(len(text), idx + len(name) + context)
    chunk = text[start:end]
    if len(chunk) > 350:
        chunk = chunk[:347] + "..."
    return chunk.strip()


def backfill():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    updated_entities = 0

    with driver.session(database="neo4j") as session:
        # 找所有没有 source_chunk 的实体
        rows = session.run(
            "MATCH (e:Entity) "
            "WHERE e.source_chunk IS NULL OR e.source_chunk = '' "
            "RETURN e.id AS id, e.name AS name, e.source_doc AS doc "
            "LIMIT 500"
        )
        entities = [{"id": r["id"], "name": r["name"], "doc": r["doc"]} for r in rows]
        print(f"📊 找到 {len(entities)} 个缺少来源的实体")

        for ent in entities:
            name = ent.get("name", "")
            doc_name = ent.get("doc", "")
            if not name:
                continue

            chunk = ""
            doc_url = ""

            # 1) 从 feishu_raw/ 中查找来源文档
            if doc_name:
                raw_paths = [
                    RAW_DIR / f"{doc_name}.txt",
                    RAW_DIR / f"{doc_name.replace('/', '_').replace(' ', '_')}.txt",
                ]
                for rp in raw_paths:
                    if rp.exists():
                        text = rp.read_text(encoding="utf-8")
                        chunk = extract_chunk(text, name)
                        # 加载元数据
                        meta_path = META_DIR / f"{doc_name}.json"
                        if meta_path.exists():
                            meta = json.loads(meta_path.read_text())
                            doc_url = meta.get("doc_url", "")
                        break

            # 2) 如果上面没找到，全局搜索所有 txt
            if not chunk:
                for txt_file in sorted(RAW_DIR.glob("*.txt")):
                    if txt_file.stem.startswith("_"):
                        continue
                    text = txt_file.read_text(encoding="utf-8")
                    chunk = extract_chunk(text, name)
                    if chunk:
                        doc_name = txt_file.stem
                        meta_path = META_DIR / f"{doc_name}.json"
                        if meta_path.exists():
                            meta = json.loads(meta_path.read_text())
                            doc_url = meta.get("doc_url", "")
                        break

            # 3) 更新 Neo4j
            if chunk:
                session.run(
                    "MATCH (e:Entity {id: $eid}) "
                    "SET e.source_chunk = $chunk, "
                    "    e.source_doc = $doc, "
                    "    e.doc_url = $url",
                    eid=ent["id"], chunk=chunk,
                    doc=doc_name or "", url=doc_url
                )
                updated_entities += 1
                if updated_entities <= 5:
                    print(f"  ✅ {ent['id']}: 「{name}」→ {chunk[:50]}...")
            else:
                # 在原文没找到 → 把 doc_name 和 doc_url 至少填上
                if doc_name:
                    session.run(
                        "MATCH (e:Entity {id: $eid}) "
                        "SET e.source_doc = $doc, e.doc_url = $url",
                        eid=ent["id"], doc=doc_name, url=doc_url
                    )
                    updated_entities += 1

    driver.close()
    print(f"\n✅ 回溯完成: 更新了 {updated_entities} 个实体")
    if updated_entities < len(entities):
        print(f"⚠️ 仍有 {len(entities) - updated_entities} 个实体未找到原文匹配")


if __name__ == "__main__":
    backfill()
