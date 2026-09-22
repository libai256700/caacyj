#!/usr/bin/env python3
"""Quality repair for the 2025 Civil Aviation Law import.

This script only touches Neo4j nodes/relationships created for the imported
Civil Aviation Law document. RAG chunks remain the canonical text source.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from neo4j import GraphDatabase

import import_civil_aviation_law as civil


PROJECT_DIR = Path(__file__).resolve().parent.parent
RAG_DB = PROJECT_DIR / "rag_chunks.db"
DOC_NAME = civil.DOC_NAME
LAW_ENTITY = civil.LAW_ENTITY
STATUS = civil.STATUS
EFFECTIVE_FROM = civil.EFFECTIVE_FROM


def chunk_id(article_no: int) -> str:
    return f"{civil.DOC_ID}:art_{article_no:03d}"


def chapter_first_chunks() -> dict[str, str]:
    conn = sqlite3.connect(RAG_DB)
    try:
        rows = conn.execute(
            "SELECT chunk_id, text FROM chunks WHERE doc_name = ? ORDER BY chunk_index",
            (DOC_NAME,),
        ).fetchall()
    finally:
        conn.close()

    first_chunks: dict[str, str] = {}
    for cid, text in rows:
        match = re.search(r"^章节：(.+)$", text, flags=re.MULTILINE)
        if not match:
            continue
        chapter = match.group(1).strip()
        first_chunks.setdefault(chapter, cid)
    return first_chunks


def normalize_chapter_name(name: str) -> str:
    return re.sub(r"\s+", "", name.replace(LAW_ENTITY, ""))


def sha_id(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def repair_chapters(session) -> dict[str, int]:
    first_chunks = chapter_first_chunks()
    full_rows = session.run(
        """
        MATCH (c:Chapter:Entity {_created_by:$doc})
        WHERE c.name STARTS WITH $law
        RETURN c.name AS name, c.description AS description,
               c.source_chunk_ids AS source_chunk_ids, c.aliases AS aliases
        """,
        doc=DOC_NAME,
        law=LAW_ENTITY,
    ).data()
    short_rows = session.run(
        """
        MATCH (c:Chapter:Entity {_created_by:$doc})
        WHERE NOT c.name STARTS WITH $law
        RETURN c.name AS name, c.description AS description,
               c.source_chunk_ids AS source_chunk_ids, c.aliases AS aliases
        """,
        doc=DOC_NAME,
        law=LAW_ENTITY,
    ).data()

    full_by_norm = {normalize_chapter_name(row["name"]): row for row in full_rows}
    merged = 0
    for short in short_rows:
        full = full_by_norm.get(normalize_chapter_name(short["name"]))
        if not full:
            continue
        aliases = list(full.get("aliases") or [])
        if short["name"] not in aliases:
            aliases.append(short["name"])
        desc = full.get("description") or short.get("description")
        chunks = full.get("source_chunk_ids") or short.get("source_chunk_ids") or []
        session.run(
            """
            MATCH (full:Chapter:Entity {name:$full_name})
            MATCH (short:Chapter:Entity {name:$short_name})
            SET full.description = $description,
                full.source_doc = $doc,
                full.source_chunk_ids = $chunks,
                full.aliases = $aliases
            WITH full, short
            OPTIONAL MATCH (short)-[sr:PART_OF]->(law:Entity {name:$law})
            OPTIONAL MATCH (full)-[fr:PART_OF]->(law)
            SET fr.description = coalesce(fr.description, sr.description),
                fr.source_doc = coalesce(fr.source_doc, $doc),
                fr.source_chunk_ids = coalesce(fr.source_chunk_ids, sr.source_chunk_ids, $chunks)
            DETACH DELETE short
            """,
            full_name=full["name"],
            short_name=short["name"],
            description=desc,
            chunks=chunks,
            aliases=aliases,
            doc=DOC_NAME,
            law=LAW_ENTITY,
        )
        merged += 1

    updated = 0
    for chapter, cid in first_chunks.items():
        full_name = f"{LAW_ENTITY}{chapter}"
        session.run(
            """
            MERGE (c:Chapter:Entity {name:$name})
            ON CREATE SET c.id=$id, c.type='Chapter', c._created_by=$doc,
                          c.imported_at=datetime()
            SET c.source_doc=$doc,
                c.source_chunk_ids=coalesce(c.source_chunk_ids, [$chunk_id]),
                c.description=coalesce(c.description, $description)
            WITH c
            MATCH (law:Entity {name:$law})
            MERGE (c)-[r:PART_OF]->(law)
            SET r.description=coalesce(r.description, '章节属于民用航空法'),
                r.source_doc=coalesce(r.source_doc, $doc),
                r.source_chunk_ids=coalesce(r.source_chunk_ids, [$chunk_id])
            WITH c
            MATCH (d:Document {name:$doc})
            MERGE (d)-[:CONTAINS]->(c)
            """,
            name=full_name,
            id=f"civil_law_chapter_{sha_id(full_name)[:10]}",
            doc=DOC_NAME,
            chunk_id=cid,
            description=f"本法{chapter}章节",
            law=LAW_ENTITY,
        )
        updated += 1
    return {"merged_short_chapters": merged, "chapter_nodes_updated": updated}


def repair_anchors(session) -> dict[str, int]:
    session.run(
        """
        MATCH (date:Entity {name:'2026-07-01'})
        WHERE date._created_by = $doc
        SET date.description='本法正式施行日期',
            date.source_doc=$doc,
            date.source_chunk_ids=[$effective_chunk]
        WITH date
        MATCH (law:Entity {name:$law})-[r:HAS_PROPERTY]->(date)
        SET r.description='第二百六十二条规定本法自2026年7月1日起施行',
            r.source_doc=$doc,
            r.source_chunk_ids=[$effective_chunk]
        """,
        doc=DOC_NAME,
        law=LAW_ENTITY,
        effective_chunk=chunk_id(262),
    )

    session.run(
        """
        MATCH (n:Entity {_created_by:$doc})
        WHERE n.description CONTAINS '本发'
        SET n.description = replace(n.description, '本发', '本法')
        """,
        doc=DOC_NAME,
    )

    session.run(
        """
        MATCH (uav:Entity {name:'无人驾驶航空器'})
        WHERE uav._created_by = $doc
        MATCH (cert:Entity {name:'民用航空器适航证书'})
        OPTIONAL MATCH (uav)-[old:REQUIRES]->(cert)
        WHERE old.source_doc = $doc
        DELETE old
        WITH uav
        MERGE (permit:Certification:Entity {name:'民用无人驾驶航空器适航许可'})
        ON CREATE SET permit.id=$permit_id,
                      permit.type='Certification',
                      permit._created_by=$doc,
                      permit.imported_at=datetime()
        SET permit.description='从事民用无人驾驶航空器设计、生产、进口、维修和飞行活动应按规定申请取得的适航许可',
            permit.source_doc=$doc,
            permit.source_chunk_ids=[$uav_chunk],
            permit.status=$status,
            permit.effective_from=$effective_from
        MERGE (uav)-[r:REQUIRES]->(permit)
        SET r.description='第三十四条规定相关活动应按规定申请取得适航许可，另有免许可规定的除外',
            r.source_doc=$doc,
            r.source_chunk_ids=[$uav_chunk],
            r.imported_at=datetime()
        WITH permit
        MATCH (d:Document {name:$doc})
        MERGE (d)-[:CONTAINS]->(permit)
        """,
        doc=DOC_NAME,
        permit_id=f"civil_law_{sha_id('民用无人驾驶航空器适航许可')}",
        uav_chunk=chunk_id(34),
        status=STATUS,
        effective_from=EFFECTIVE_FROM,
    )

    return {"anchors_repaired": 3}


def quality_summary(session) -> dict[str, int]:
    row = session.run(
        """
        MATCH (n:Entity {_created_by:$doc})
        WITH collect(n) AS nodes
        OPTIONAL MATCH (a:Entity {_created_by:$doc})-[r]->(b:Entity {_created_by:$doc})
        RETURN size(nodes) AS nodes,
               count(r) AS relations,
               size([n IN nodes WHERE n.description IS NULL OR n.description='']) AS nodes_missing_description,
               size([n IN nodes WHERE n.source_chunk_ids IS NULL OR size(n.source_chunk_ids)=0]) AS nodes_missing_chunks,
               count(CASE WHEN r.source_chunk_ids IS NULL OR size(r.source_chunk_ids)=0 THEN 1 END) AS relations_missing_chunks
        """,
        doc=DOC_NAME,
    ).single()
    return dict(row) if row else {}


def main() -> None:
    password = civil.NEO4J_PASS_FILE.read_text().strip()
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    try:
        with driver.session() as session:
            before = quality_summary(session)
            chapter_stats = repair_chapters(session)
            anchor_stats = repair_anchors(session)
            after = quality_summary(session)
    finally:
        driver.close()

    print({"before": before, "chapter_stats": chapter_stats, "anchor_stats": anchor_stats, "after": after})


if __name__ == "__main__":
    main()
