#!/usr/bin/env python3
"""Import the 2025-revised PRC Civil Aviation Law into the local KG/RAG stack.

The law text is imported deterministically into the canonical SQLite chunk store.
Doubao Seed 2.0 Pro is used only for high-level KG extraction, never to rewrite
or paraphrase legal text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from neo4j import GraphDatabase

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from rag_store.semantic_schema import relationship_missing_evidence_reason

RAG_DB = PROJECT_DIR / "rag_chunks.db"
RAG_DOCS = PROJECT_DIR / "rag_docs"
REPORTS = PROJECT_DIR / "review_reports"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
NEO4J_PASS_FILE = PROJECT_DIR / "neo4j" / ".neo4j_pass"

SOURCE_DOCX = Path("/Users/xiaoji/Downloads/同步空间/openclaw/knowledge_base/政策法规/中华人民共和国民用航空法.docx")
DOC_NAME = "政策法规_中华人民共和国民用航空法_2025修订_2026-07-01施行.txt"
DOC_ID = "regulation:cn_civil_aviation_law_2025"
LAW_ENTITY = "中华人民共和国民用航空法（2025修订）"
DOMAIN = "政策法规"
STATUS = "promulgated_not_yet_effective"
EFFECTIVE_FROM = "2026-07-01"
PROMULGATED_AT = "2025-12-27"

REL_WHITELIST = {
    "DESCRIBES",
    "OFFERS",
    "AWARDS",
    "REQUIRES",
    "ISSUED_BY",
    "LOCATED_AT",
    "REGULATES",
    "BELONGS_TO",
    "MENTIONS",
    "HAS_CLASS",
    "HAS_LEVEL",
    "REFERS_TO",
    "REQUIRES_SKILL",
    "HAS_PROPERTY",
    "SUBCLASS_OF",
    "PART_OF",
    "DEFINED_BY",
}

TYPE_WHITELIST = {
    "Location",
    "Position",
    "Company",
    "Organization",
    "PlatformPresence",
    "Event",
    "Course",
    "Exam",
    "Certification",
    "KnowledgePoint",
    "Category",
    "Student",
    "Teacher",
    "Person",
    "Policy",
    "Regulation",
    "SocialContent",
    "Skill",
    "EducationRequirement",
    "AircraftType",
    "LicenseLevel",
    "WeightClass",
    "Chapter",
    "Section",
    "Scenario",
    "DesignTool",
    "FabricationStep",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


CN_NUM = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def chinese_number_to_int(value: str) -> int:
    section = 0
    number = 0
    for char in value:
        if char in CN_NUM:
            number = CN_NUM[char]
        elif char in CN_UNIT:
            unit = CN_UNIT[char]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
    return section + number


def article_number(text: str) -> int | None:
    match = re.match(r"^第(.+?)条", text)
    if not match:
        return None
    return chinese_number_to_int(match.group(1))


def expand_structural_paragraphs(paragraphs: list[str]) -> list[str]:
    marker = re.compile(
        r"(?<!^)(第[一二三四五六七八九十百零〇两]+章[\s　]|第[一二三四五六七八九十]+节[\s　]|第[一二三四五六七八九十百零〇两]+条[\s　])"
    )
    expanded: list[str] = []
    for text in paragraphs:
        expanded_text = marker.sub(r"\n\1", text)
        expanded.extend(part.strip() for part in expanded_text.splitlines() if part.strip())
    return expanded


def read_docx_paragraphs(path: Path) -> tuple[dict[str, str], list[str]]:
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    }
    with ZipFile(path) as zf:
        core: dict[str, str] = {}
        if "docProps/core.xml" in zf.namelist():
            root = ET.fromstring(zf.read("docProps/core.xml"))
            for child in root:
                core[child.tag.split("}", 1)[-1]] = child.text or ""
        doc = ET.fromstring(zf.read("word/document.xml"))
        paragraphs = []
        for para in doc.findall(".//w:p", ns):
            text = "".join(t.text or "" for t in para.findall(".//w:t", ns)).strip()
            if text:
                paragraphs.append(text)
    return core, paragraphs


def parse_articles(paragraphs: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    paragraphs = expand_structural_paragraphs(paragraphs)
    first_article_idx = next(i for i, text in enumerate(paragraphs) if article_number(text) == 1)
    start_idx = 0
    for i in range(first_article_idx, -1, -1):
        if re.match(r"^第一章", paragraphs[i]):
            start_idx = i
            break

    preface = paragraphs[:start_idx]
    current_chapter = ""
    current_section = ""
    current_article: dict[str, Any] | None = None
    articles: list[dict[str, Any]] = []

    def close_article() -> None:
        nonlocal current_article
        if current_article:
            current_article["text"] = "\n".join(current_article.pop("_parts")).strip()
            current_article["chunk_id"] = f"{DOC_ID}:art_{current_article['article_no']:03d}"
            articles.append(current_article)
            current_article = None

    for raw in paragraphs[start_idx:]:
        text = raw.strip()
        if not text:
            continue
        if re.match(r"^第[一二三四五六七八九十百]+章", text):
            close_article()
            current_chapter = normalize_space(text)
            current_section = ""
            continue
        if re.match(r"^第[一二三四五六七八九十]+节", text):
            close_article()
            current_section = normalize_space(text)
            continue
        art_no = article_number(text)
        if art_no is not None:
            close_article()
            current_article = {
                "article_no": art_no,
                "chapter": current_chapter,
                "section": current_section,
                "_parts": [text],
            }
            continue
        if current_article is not None:
            current_article["_parts"].append(text)

    close_article()
    return articles, preface


def chunk_text(article: dict[str, Any]) -> str:
    meta = [
        f"文档：{DOC_NAME}",
        f"法规：{LAW_ENTITY}",
        f"状态：已颁布，{EFFECTIVE_FROM}起施行",
        f"知识域：{DOMAIN}",
        f"章节：{article['chapter']}",
    ]
    if article.get("section"):
        meta.append(f"节：{article['section']}")
    return "\n".join(meta) + "\n\n" + article["text"]


def write_rag_doc(preface: list[str], articles: list[dict[str, Any]]) -> Path:
    RAG_DOCS.mkdir(parents=True, exist_ok=True)
    out = RAG_DOCS / DOC_NAME
    body = [
        f"文档：{DOC_NAME}",
        f"原始文件：{SOURCE_DOCX}",
        f"法规实体：{LAW_ENTITY}",
        f"状态：已颁布，{EFFECTIVE_FROM}起施行",
        f"颁布/修订日期：{PROMULGATED_AT}",
        "",
        *preface,
        "",
    ]
    body.extend(article["text"] for article in articles)
    out.write_text("\n".join(body).strip() + "\n", encoding="utf-8")
    return out


def backup_sqlite(report_dir: Path) -> Path:
    backup_path = report_dir / f"rag_chunks.before_civil_aviation_law.{timestamp()}.db"
    src = sqlite3.connect(RAG_DB)
    dst = sqlite3.connect(backup_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def import_chunks(articles: list[dict[str, Any]], rag_doc_path: Path) -> dict[str, Any]:
    rows = [
        {
            "chunk_id": article["chunk_id"],
            "text": chunk_text(article),
            "doc_name": DOC_NAME,
            "chunk_index": idx,
        }
        for idx, article in enumerate(articles)
    ]
    conn = sqlite3.connect(RAG_DB)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("DELETE FROM chunks WHERE doc_name = ?", (DOC_NAME,))
        conn.execute("DELETE FROM documents WHERE doc_name = ?", (DOC_NAME,))
        conn.executemany(
            """
            INSERT OR REPLACE INTO chunks (chunk_id, text, doc_name, chunk_index)
            VALUES (:chunk_id, :text, :doc_name, :chunk_index)
            """,
            rows,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO documents (doc_name, doc_path, chunk_count, updated_at)
            VALUES (?, ?, ?, datetime('now','localtime'))
            """,
            (DOC_NAME, str(rag_doc_path), len(rows)),
        )
        conn.commit()
        total_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        conn.close()
    return {
        "doc_name": DOC_NAME,
        "inserted_chunks": len(rows),
        "total_docs": total_docs,
        "total_chunks": total_chunks,
    }


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_doubao_config() -> dict[str, Any]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    model_cfg = cfg["models"]["doubao"]
    return {
        "model": model_cfg["name"],
        "base_url": model_cfg["base_url"].rstrip("/"),
        "api_key": model_cfg["api_key"],
        "timeout": int(model_cfg.get("timeout", 180)),
    }


def call_doubao_for_kg(articles: list[dict[str, Any]], report_dir: Path) -> dict[str, Any]:
    cfg = load_doubao_config()
    overview = build_kg_prompt_text(articles)
    prompt = f"""
你是企业知识图谱抽取器。请从《中华人民共和国民用航空法（2025修订，2026-07-01施行）》中抽取高价值图谱实体和关系。

只输出 JSON，不要 Markdown。不要改写法条原文，不要输出完整法条。

实体类型只能使用：
{", ".join(sorted(TYPE_WHITELIST))}

关系类型只能使用：
{", ".join(sorted(REL_WHITELIST))}

输出格式：
{{
  "entities": [
    {{
      "id": "e1",
      "name": "实体名",
      "type": "Regulation|Organization|KnowledgePoint|Category|Chapter|Section|Event",
      "properties": {{
        "description": "一句话说明",
        "source_articles": [1, 2, 3]
      }}
    }}
  ],
  "relations": [
    {{
      "from_id": "e1",
      "to_id": "e2",
      "type": "REGULATES|PART_OF|DEFINED_BY|ISSUED_BY|REFERS_TO|MENTIONS|HAS_PROPERTY",
      "properties": {{
        "description": "关系依据",
        "source_articles": [1, 2, 3]
      }}
    }}
  ]
}}

硬性规则：
- 必须包含法规实体“{LAW_ENTITY}”。
- 必须包含颁布/修订机构、生效日期、民用航空、通用航空、公共航空运输、民用机场、航空人员、无人驾驶航空器、安全保卫、搜寻援救、事故调查、法律责任等核心概念。
- 不要把 262 条法条逐条建成实体。
- 关系必须能被下方材料直接支持。
- source_articles 只能使用下方出现的条号数字。
- 实体总数控制在 18 到 30 个，关系总数控制在 20 到 45 条。
- description 最多 24 个汉字，避免长解释。

材料：
{overview}
""".strip()

    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": "只输出严格 JSON，不要 Markdown。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    print("🚀 doubao seed 2.0 pro 抽取知识图谱...", flush=True)
    req = urllib.request.Request(
        f"{cfg['base_url']}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"].strip()
    (report_dir / "doubao_kg_raw_response.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "doubao_kg_raw_content.txt").write_text(content, encoding="utf-8")
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()
    if not content.startswith("{") and "{" in content:
        content = content[content.find("{") :]
    if not content.endswith("}") and "}" in content:
        content = content[: content.rfind("}") + 1]
    result = json.loads(content)
    (report_dir / "doubao_kg.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def build_kg_prompt_text(articles: list[dict[str, Any]]) -> str:
    """Compress the law for KG extraction while preserving article anchors."""
    selected = []
    for article in articles:
        no = article["article_no"]
        text = article["text"]
        if (
            no <= 20
            or no >= 220
            or any(
                term in text
                for term in (
                    "无人驾驶航空器",
                    "通用航空",
                    "公共航空运输",
                    "民用机场",
                    "航空人员",
                    "安全保卫",
                    "搜寻援救",
                    "事故调查",
                    "国务院民用航空主管部门",
                    "法律责任",
                    "空域",
                    "飞行管理",
                    "适航",
                    "保险",
                    "航班延误",
                )
            )
        ):
            selected.append(
                f"第{no}条｜{article['chapter']}｜{article.get('section') or ''}\n{text[:260]}"
            )
    return "\n\n".join(selected[:80])


def article_chunk_ids(source_articles: Any) -> list[str]:
    ids = []
    if not isinstance(source_articles, list):
        return ids
    for item in source_articles:
        try:
            no = int(item)
        except Exception:
            continue
        if 1 <= no <= 262:
            ids.append(f"{DOC_ID}:art_{no:03d}")
    return sorted(set(ids))


def write_neo4j(kg: dict[str, Any], articles: list[dict[str, Any]]) -> dict[str, int]:
    password = NEO4J_PASS_FILE.read_text().strip()
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    id_to_name: dict[str, str] = {}
    created_names: set[str] = set()
    entity_count = 0
    relation_count = 0

    with driver.session() as session:
        session.run(
            """
            MERGE (d:Document {name: $name})
            SET d.doc_name = $name,
                d.domain = $domain,
                d.source_file = $source_file,
                d.status = $status,
                d.effective_from = $effective_from,
                d.promulgated_at = $promulgated_at,
                d.imported_at = datetime()
            """,
            name=DOC_NAME,
            domain=DOMAIN,
            source_file=str(SOURCE_DOCX),
            status=STATUS,
            effective_from=EFFECTIVE_FROM,
            promulgated_at=PROMULGATED_AT,
        )

        mandatory = {
            "entities": [
                {
                    "id": "mandatory_law",
                    "name": LAW_ENTITY,
                    "type": "Regulation",
                    "properties": {
                        "description": "2025年修订、2026年7月1日起施行的中华人民共和国民用航空法",
                        "source_articles": [1, 262],
                    },
                },
                {
                    "id": "mandatory_authority",
                    "name": "全国人民代表大会常务委员会",
                    "type": "Organization",
                    "properties": {"description": "本法修订通过机关", "source_articles": []},
                },
                {
                    "id": "mandatory_effective_event",
                    "name": "中华人民共和国民用航空法2026年7月1日起施行",
                    "type": "Event",
                    "properties": {"description": "本法施行日期", "source_articles": [262]},
                },
            ],
            "relations": [
                {
                    "from_id": "mandatory_law",
                    "to_id": "mandatory_authority",
                    "type": "ISSUED_BY",
                    "properties": {"description": "2025年12月27日第十四届全国人大常委会第十九次会议修订", "source_articles": []},
                },
                {
                    "from_id": "mandatory_law",
                    "to_id": "mandatory_effective_event",
                    "type": "HAS_PROPERTY",
                    "properties": {"description": "第二百六十二条规定本法自2026年7月1日起施行", "source_articles": [262]},
                },
            ],
        }

        entities = [*mandatory["entities"], *kg.get("entities", [])]
        relations = [*mandatory["relations"], *kg.get("relations", [])]

        for entity in entities:
            name = str(entity.get("name", "")).strip()
            etype = str(entity.get("type", "KnowledgePoint")).strip()
            if not name or etype not in TYPE_WHITELIST:
                continue
            props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
            description = str(props.get("description", "")).strip()
            source_articles = props.get("source_articles", [])
            chunk_ids = article_chunk_ids(source_articles)
            label = etype
            row = session.run(
                f"""
                MERGE (e:{label}:Entity {{name: $name}})
                ON CREATE SET e.id = $id,
                              e.type = $type,
                              e.description = $description,
                              e._created_by = $doc_name,
                              e.source_doc = $doc_name,
                              e.source_chunk_ids = $chunk_ids,
                              e.status = $status,
                              e.effective_from = $effective_from,
                              e.imported_at = datetime()
                ON MATCH SET e.description = CASE
                                  WHEN (e.description IS NULL OR e.description = '') AND $description <> ''
                                  THEN $description ELSE e.description END,
                              e.source_chunk_ids = CASE
                                  WHEN e.source_chunk_ids IS NULL OR size(e.source_chunk_ids) = 0
                                  THEN $chunk_ids ELSE e.source_chunk_ids END
                RETURN e.id AS id, e._created_by AS created_by
                """,
                id=f"civil_law_{hashlib.sha1(name.encode('utf-8')).hexdigest()[:12]}",
                name=name,
                type=etype,
                description=description,
                doc_name=DOC_NAME,
                chunk_ids=chunk_ids,
                status=STATUS,
                effective_from=EFFECTIVE_FROM,
            ).single()
            id_to_name[str(entity.get("id"))] = name
            if row and row["created_by"] == DOC_NAME:
                created_names.add(name)
                session.run(
                    "MATCH (d:Document {name:$doc}) MATCH (e:Entity {name:$name}) MERGE (d)-[:CONTAINS]->(e)",
                    doc=DOC_NAME,
                    name=name,
                )
            entity_count += 1

        for article in articles:
            chapter_name = f"{LAW_ENTITY}{article['chapter']}"
            if chapter_name in created_names:
                continue
            row = session.run(
                """
                MATCH (law:Entity {name:$law})
                MERGE (c:Chapter:Entity {name:$chapter})
                ON CREATE SET c.id=$id, c.type='Chapter', c._created_by=$doc_name,
                              c.source_doc=$doc_name, c.imported_at=datetime()
                MERGE (c)-[:PART_OF {description:'章节属于民用航空法'}]->(law)
                WITH c
                MATCH (d:Document {name:$doc_name})
                MERGE (d)-[:CONTAINS]->(c)
                RETURN c.name AS name
                """,
                law=LAW_ENTITY,
                chapter=chapter_name,
                id=f"civil_law_chapter_{hashlib.sha1(chapter_name.encode('utf-8')).hexdigest()[:10]}",
                doc_name=DOC_NAME,
            ).single()
            if row:
                created_names.add(chapter_name)

        for rel in relations:
            from_name = id_to_name.get(str(rel.get("from_id")))
            to_name = id_to_name.get(str(rel.get("to_id")))
            rel_type = str(rel.get("type", "")).upper().strip()
            if not from_name or not to_name or rel_type not in REL_WHITELIST:
                continue
            if from_name not in created_names or to_name not in created_names:
                continue
            props = rel.get("properties") if isinstance(rel.get("properties"), dict) else {}
            description = str(props.get("description", "")).strip()
            chunk_ids = article_chunk_ids(props.get("source_articles", []))
            evidence_props = {
                "description": description,
                "source_doc": DOC_NAME,
                "source_chunk_ids": chunk_ids,
                "evidence_contract": "source_doc_and_source_chunk_ids_to_sqlite",
            }
            reason = relationship_missing_evidence_reason(rel_type, evidence_props)
            if reason:
                print(f"Skip relation without required evidence: {from_name} -[{rel_type}]-> {to_name} ({reason})")
                continue
            session.run(
                f"""
                MATCH (a:Entity {{name:$from_name}})
                MATCH (b:Entity {{name:$to_name}})
                MERGE (a)-[r:`{rel_type}`]->(b)
                SET r += $evidence_props,
                    r.imported_at = datetime()
                """,
                from_name=from_name,
                to_name=to_name,
                evidence_props=evidence_props,
            )
            relation_count += 1

        stats = session.run(
            """
            MATCH (d:Document {name:$doc})
            OPTIONAL MATCH (d)-[:CONTAINS]->(e)
            WITH d, count(e) AS contains_count
            OPTIONAL MATCH (n:Entity {_created_by:$doc})
            WITH contains_count, count(n) AS created_entities
            OPTIONAL MATCH (:Entity {_created_by:$doc})-[r]->(:Entity {_created_by:$doc})
            RETURN contains_count, created_entities, count(r) AS created_relations
            """,
            doc=DOC_NAME,
        ).single()
    driver.close()
    return {
        "kg_entities_seen": entity_count,
        "kg_relations_seen": relation_count,
        "document_contains": stats["contains_count"] if stats else 0,
        "created_entities": stats["created_entities"] if stats else 0,
        "created_relations": stats["created_relations"] if stats else 0,
    }


def rebuild_bm25() -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(PROJECT_DIR / "rag_store"))
    from bm25_index import BM25Index

    return BM25Index().build(force=True)


def rebuild_dense() -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(PROJECT_DIR / "rag_store"))
    from dense_index import DenseIndex

    return DenseIndex().build(force=True)


def check_indexes(auto_rebuild: bool, rebuild_bm25_enabled: bool, rebuild_dense_enabled: bool) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(PROJECT_DIR))
    from rag_store.index_freshness import check_index_freshness

    return check_index_freshness(
        db_path=RAG_DB,
        auto_rebuild=auto_rebuild,
        rebuild_bm25=rebuild_bm25_enabled,
        rebuild_dense=rebuild_dense_enabled,
    )


def verify_import() -> dict[str, Any]:
    conn = sqlite3.connect(RAG_DB)
    conn.row_factory = sqlite3.Row
    try:
        doc = conn.execute(
            "SELECT doc_name, doc_path, chunk_count, updated_at FROM documents WHERE doc_name = ?",
            (DOC_NAME,),
        ).fetchone()
        chunks = conn.execute(
            "SELECT COUNT(*) AS c FROM chunks WHERE doc_name = ?",
            (DOC_NAME,),
        ).fetchone()["c"]
        total_docs = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        total_chunks = conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"]
    finally:
        conn.close()
    password = NEO4J_PASS_FILE.read_text().strip()
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    with driver.session() as session:
        kg = session.run(
            """
            MATCH (d:Document {name:$doc})
            OPTIONAL MATCH (d)-[:CONTAINS]->(e)
            WITH count(e) AS contains_count
            OPTIONAL MATCH (n:Entity {_created_by:$doc})
            WITH contains_count, count(n) AS created_entities
            OPTIONAL MATCH (:Entity {_created_by:$doc})-[r]->(:Entity {_created_by:$doc})
            RETURN contains_count, created_entities, count(r) AS created_relations
            """,
            doc=DOC_NAME,
        ).single()
    driver.close()
    return {
        "document": dict(doc) if doc else None,
        "doc_chunks": chunks,
        "total_docs": total_docs,
        "total_chunks": total_chunks,
        "neo4j": dict(kg) if kg else {},
    }


def run_health_gate(url: str, timeout: int) -> dict[str, Any]:
    output = REPORTS / f"import_civil_aviation_law_health_gate_{timestamp()}.json"
    cmd = [
        sys.executable,
        str(PROJECT_DIR / "scripts" / "eval_health_gate.py"),
        "--url",
        url,
        "--timeout",
        str(timeout),
        "--output",
        str(output),
    ]
    started = time.time()
    proc = subprocess.run(cmd, cwd=PROJECT_DIR, text=True, capture_output=True)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "duration_s": round(time.time() - started, 2),
        "output": str(output),
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "passed": proc.returncode == 0,
    }


def main() -> None:
    global SOURCE_DOCX
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_DOCX)
    parser.add_argument("--skip-doubao", action="store_true")
    parser.add_argument("--skip-bm25", action="store_true")
    parser.add_argument("--skip-dense", action="store_true")
    parser.add_argument(
        "--auto-rebuild-stale-indexes",
        action="store_true",
        help="after import, rebuild stale indexes that were skipped or drifted",
    )
    parser.add_argument("--skip-health-gate", action="store_true")
    parser.add_argument("--health-gate-url", default=os.getenv("KG_HEALTH_GATE_URL", "http://127.0.0.1:5001/api/ask"))
    parser.add_argument("--health-gate-timeout", type=int, default=120)
    args = parser.parse_args()

    SOURCE_DOCX = args.source.expanduser()
    if not SOURCE_DOCX.exists():
        raise FileNotFoundError(SOURCE_DOCX)

    report_dir = REPORTS / f"import_civil_aviation_law_{timestamp()}"
    report_dir.mkdir(parents=True, exist_ok=True)

    core, paragraphs = read_docx_paragraphs(SOURCE_DOCX)
    articles, preface = parse_articles(paragraphs)
    if len(articles) != 262:
        raise RuntimeError(f"expected 262 articles, got {len(articles)}")

    shutil.copy2(SOURCE_DOCX, report_dir / SOURCE_DOCX.name)
    backup_path = backup_sqlite(report_dir)
    rag_doc = write_rag_doc(preface, articles)
    import_stat = import_chunks(articles, rag_doc)

    doubao_result: dict[str, Any] = {"entities": [], "relations": []}
    if not args.skip_doubao:
        doubao_result = call_doubao_for_kg(articles, report_dir)
    kg_stat = write_neo4j(doubao_result, articles)

    bm25_stat = None if args.skip_bm25 else rebuild_bm25()
    dense_stat = None if args.skip_dense else rebuild_dense()
    index_freshness = check_indexes(
        auto_rebuild=args.auto_rebuild_stale_indexes,
        rebuild_bm25_enabled=True,
        rebuild_dense_enabled=True,
    )
    if not index_freshness.get("fresh"):
        print("⚠️  导入后索引自检发现不一致：", flush=True)
        for issue in index_freshness.get("issues", []):
            print(
                f"   - {issue.get('index')}.{issue.get('field')}: "
                f"expected={issue.get('expected')} actual={issue.get('actual')}",
                flush=True,
            )
        print(f"   {index_freshness.get('hint')}", flush=True)
    verify = verify_import()
    health_gate = None if args.skip_health_gate else run_health_gate(args.health_gate_url, args.health_gate_timeout)

    manifest = {
        "source_file": str(SOURCE_DOCX),
        "source_sha256": sha256_file(SOURCE_DOCX),
        "core_properties": core,
        "doc_name": DOC_NAME,
        "domain": DOMAIN,
        "status": STATUS,
        "effective_from": EFFECTIVE_FROM,
        "promulgated_at": PROMULGATED_AT,
        "articles": len(articles),
        "sqlite_backup": str(backup_path),
        "rag_doc": str(rag_doc),
        "import": import_stat,
        "kg": kg_stat,
        "bm25": bm25_stat,
        "dense": dense_stat,
        "index_freshness": index_freshness,
        "verify": verify,
        "health_gate": health_gate,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    (report_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if health_gate and not health_gate["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
