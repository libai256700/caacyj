#!/usr/bin/env python3
"""Repair discrete/orphan entities introduced by job-report extraction.

Default is DRY-RUN. Use --apply to mutate Neo4j.
Focus:
1) merge same-name different-type entities for known 5 groups
2) quarantine/delete obvious bogus Position nodes without salary
3) add coarse cross-document anchors for useful 05-12/05-13 entities

Usage:
  python3 repair_discrete_entities_20260521.py
  python3 repair_discrete_entities_20260521.py --apply
"""
from __future__ import annotations
import argparse, json, re, datetime
from collections import defaultdict
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "yj123456")
DB = "neo4j"

CANONICAL = {
    "湖北云技科技有限公司": "Company",
    "行业应用培训课程": "Course",
    "CAAC无人机考证培训": "Course",
    "培训": "Position",      # in job reports it is a job category, not an event
    "巡检": "Position",      # in job reports it is a job category, not an event
}

# Conservative: only delete/quarantine when no salary and weakly connected.
BOGUS_POSITION_EXACT = {
    "测试", "工程师", "CAAC优先", "顾问", "总经理", "本科", "学历不限", "中专",
}
BOGUS_POSITION_REGEX = [
    r"^\d+(\.\d+)?[-~—]\d+(\.\d+)?[kK万千元/月薪]*$",  # salary accidentally typed as Position
    r"^[一二三四五六七八九十0-9]+年(以上)?$",             # experience accidentally typed as Position
]

ANCHOR_BY_TYPE = {
    "SalaryRange": "薪资区间",
    "Location": "招聘地域",
    "EducationRequirement": "学历要求",
    "Company": "招聘企业",
    "Position": "无人机岗位",
    "KnowledgePoint": "岗位报告知识点",
    "Course": "培训课程",
    "Organization": "相关机构",
    "Event": "岗位报告事件",
}


def qtype(t: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t):
        raise ValueError(t)
    return f"`{t}`"


def collect_node(session, eid):
    return session.run("""
    MATCH (n) WHERE elementId(n)=$eid
    RETURN elementId(n) AS eid, labels(n) AS labels, properties(n) AS props, count{(n)--()} AS degree
    """, eid=eid).single().data()


def merge_name(session, name: str, canonical_type: str, apply: bool):
    rows = [r.data() for r in session.run("""
    MATCH (n {name:$name})
    RETURN elementId(n) AS eid, labels(n) AS labels, properties(n) AS props, count{(n)--()} AS degree
    ORDER BY CASE WHEN coalesce(n.entityType,n.type,'')=$canonical THEN 0 ELSE 1 END,
             count{(n)--()} DESC
    """, name=name, canonical=canonical_type)]
    if len(rows) <= 1:
        if apply and rows:
            session.run("MATCH (n) WHERE elementId(n)=$eid SET n.entityType=$t, n.type=$t", eid=rows[0]["eid"], t=canonical_type)
        return {"name": name, "found": len(rows), "merged": 0, "canonicalType": canonical_type}
    if not apply:
        return {"name": name, "found": len(rows), "wouldMerge": len(rows)-1, "canonicalType": canonical_type, "nodes": rows}

    survivor = rows[0]["eid"]
    session.run("MATCH (s) WHERE elementId(s)=$sid SET s.entityType=$t, s.type=$t", sid=survivor, t=canonical_type)
    merged = 0
    for dup in rows[1:]:
        did = dup["eid"]
        # Preserve properties as arrays when conflicts exist.
        session.run("""
        MATCH (s),(d) WHERE elementId(s)=$sid AND elementId(d)=$did
        SET s.merged_from = coalesce(s.merged_from, []) + [properties(d)]
        """, sid=survivor, did=did)
        # Copy outgoing rels.
        for r in session.run("MATCH (d)-[rel]->(m) WHERE elementId(d)=$did RETURN type(rel) AS typ, properties(rel) AS props, elementId(m) AS mid", did=did):
            if r["mid"] == survivor: continue
            session.run(f"MATCH (s),(m) WHERE elementId(s)=$sid AND elementId(m)=$mid MERGE (s)-[nr:{qtype(r['typ'])}]->(m) SET nr += $props", sid=survivor, mid=r["mid"], props=r["props"] or {})
        # Copy incoming rels.
        for r in session.run("MATCH (m)-[rel]->(d) WHERE elementId(d)=$did RETURN type(rel) AS typ, properties(rel) AS props, elementId(m) AS mid", did=did):
            if r["mid"] == survivor: continue
            session.run(f"MATCH (m),(s) WHERE elementId(m)=$mid AND elementId(s)=$sid MERGE (m)-[nr:{qtype(r['typ'])}]->(s) SET nr += $props", sid=survivor, mid=r["mid"], props=r["props"] or {})
        session.run("MATCH (d) WHERE elementId(d)=$did DETACH DELETE d", did=did)
        merged += 1
    return {"name": name, "found": len(rows), "merged": merged, "canonicalType": canonical_type}


def bogus_position_candidates(session):
    rows = []
    for r in session.run("""
    MATCH (p)
    WHERE coalesce(p.entityType,p.type, CASE WHEN 'Position' IN labels(p) THEN 'Position' ELSE '' END)='Position'
      AND NOT (p)-[:HAS_SALARY]-()
    RETURN elementId(p) AS eid, p.name AS name, labels(p) AS labels,
           coalesce(p.source_doc,p.source,'') AS source, count{(p)--()} AS degree, properties(p) AS props
    ORDER BY degree ASC, name
    """):
        name = r["name"] or ""
        exact = name in BOGUS_POSITION_EXACT
        regex = any(re.search(pat, name) for pat in BOGUS_POSITION_REGEX)
        too_generic = len(name) <= 2 and name not in {"巡检", "培训"}
        if (exact or regex or too_generic) and r["degree"] <= 2:
            rows.append(r.data())
    return rows


def clean_bogus_positions(session, apply: bool):
    rows = bogus_position_candidates(session)
    if apply:
        for r in rows:
            session.run("MATCH (p) WHERE elementId(p)=$eid SET p.quarantined=true, p.quarantine_reason='bogus Position without HAS_SALARY', p.entityType='RejectedPosition', p.type='RejectedPosition' REMOVE p:Position", eid=r["eid"])
    return {"candidates": len(rows), "items": rows[:100], "action": "quarantine+retype" if apply else "dry-run"}


def add_anchor_links(session, apply: bool):
    cy = """
    MATCH (n)
    WHERE (coalesce(n.source_doc,n.source,'') CONTAINS '05-12' OR coalesce(n.source_doc,n.source,'') CONTAINS '05-13')
    WITH n, coalesce(n.entityType,n.type,head(labels(n))) AS typ,
         count{(n)--(m) WHERE NOT (coalesce(m.source_doc,m.source,'') CONTAINS '05-12' OR coalesce(m.source_doc,m.source,'') CONTAINS '05-13')} AS cross,
         count{(n)--()} AS degree
    WHERE cross=0 AND degree <= 2 AND typ IN $types
    RETURN elementId(n) AS eid, n.name AS name, typ AS type, degree
    ORDER BY type, name
    """
    candidates = [r.data() for r in session.run(cy, types=list(ANCHOR_BY_TYPE))]
    if apply:
        for r in candidates:
            anchor = ANCHOR_BY_TYPE[r["type"]]
            session.run("""
            MERGE (a:Entity {name:$anchor})
            SET a.entityType='Category', a.type='Category', a.generated_by='repair_discrete_entities_20260521'
            WITH a
            MATCH (n) WHERE elementId(n)=$eid
            MERGE (n)-[:BELONGS_TO]->(a)
            """, anchor=anchor, eid=r["eid"])
    return {"candidates": len(candidates), "items": candidates[:200], "action": "BELONGS_TO anchors" if apply else "dry-run"}


def audit(session):
    return {
        "nodes": session.run("MATCH (n) RETURN count(n) AS c").single()["c"],
        "rels": session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"],
        "sameNameDiffTypes": [r.data() for r in session.run("""
            MATCH (n) WHERE n.name IS NOT NULL
            WITH n.name AS name, collect(DISTINCT coalesce(n.entityType,n.type,head(labels(n)))) AS types, count(n) AS c
            WHERE size(types)>1
            RETURN name, types, c ORDER BY c DESC, name LIMIT 100
        """)],
        "leafByType": [r.data() for r in session.run("""
            MATCH (n) WITH n, count{(n)--()} AS degree
            WHERE degree <= 2
            RETURN coalesce(n.entityType,n.type,head(labels(n))) AS type, count(*) AS c ORDER BY c DESC LIMIT 20
        """)],
        "noSalaryPositions": session.run("""
            MATCH (p)
            WHERE coalesce(p.entityType,p.type, CASE WHEN 'Position' IN labels(p) THEN 'Position' ELSE '' END)='Position'
              AND NOT (p)-[:HAS_SALARY]-()
            RETURN count(p) AS c
        """).single()["c"],
        "newNoCross": [r.data() for r in session.run("""
            MATCH (n)
            WHERE coalesce(n.source_doc,n.source,'') CONTAINS '05-12' OR coalesce(n.source_doc,n.source,'') CONTAINS '05-13'
            WITH n, count{(n)--(m) WHERE NOT (coalesce(m.source_doc,m.source,'') CONTAINS '05-12' OR coalesce(m.source_doc,m.source,'') CONTAINS '05-13')} AS cross
            WHERE cross=0
            RETURN coalesce(n.source_doc,n.source,'') AS source, coalesce(n.entityType,n.type,head(labels(n))) AS type, count(*) AS c
            ORDER BY source,type
        """)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    report = {"apply": args.apply, "startedAt": datetime.datetime.now().isoformat()}
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session(database=DB) as session:
            report["before"] = audit(session)
            report["merge"] = [merge_name(session, n, t, args.apply) for n,t in CANONICAL.items()]
            report["bogusPositions"] = clean_bogus_positions(session, args.apply)
            report["anchorLinks"] = add_anchor_links(session, args.apply)
            report["after"] = audit(session)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

if __name__ == "__main__":
    main()
