#!/usr/bin/env python3
"""Merge jobs.csv Company nodes that were split by job-row identity."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CANONICAL_DIR = Path("/Users/xiaoji/Documents/知识库分析/data/canonical")
REPORT_ROOT = BASE_DIR / "review_reports"
NEO4J_PASS = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
RUN_ID = f"job_company_dedup_governance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
VALID_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def prop_writable(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(isinstance(item, (str, int, float, bool)) for item in value)
    return False


def connect():
    return GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", NEO4J_PASS))


def expected_company(row: dict[str, Any], job_titles: set[str]) -> tuple[str, str]:
    company_name = clean(row.get("company_name"))
    position_name = clean(row.get("position_original_name")) or clean(row.get("position_name"))
    position_id = clean(row.get("position_entity_id"))
    if company_name in job_titles:
        good_name = f"未标注招聘公司（{position_name[:28]}）"
        return good_name, stable_id("company_unknown", good_name, position_id)
    return company_name, stable_id("company", company_name)


def load_plan(session, job_titles: set[str]) -> list[dict[str, Any]]:
    rows = session.run(
        """
        MATCH (p:Position)-[:BELONGS_TO]->(c:Company)
        WHERE c.domain = 'job_market'
          AND c.source_table = 'jobs.csv'
          AND coalesce(c.company_name_disambiguated, false) = false
        RETURN elementId(c) AS company_id,
               c.entity_id AS company_entity_id,
               c.name AS company_name,
               c.source_doc AS source_doc,
               c.source_table AS source_table,
               c.source_csv AS source_csv,
               c.source_row_id AS source_row_id,
               c.source_chunk_ids AS source_chunk_ids,
               p.entity_id AS position_entity_id,
               p.name AS position_name,
               coalesce(p.original_name, p.canonical_name, p.name) AS position_original_name
        ORDER BY c.name, p.entity_id
        """
    ).data()
    plan = []
    seen_bad = set()
    for row in rows:
        good_name, good_entity_id = expected_company(row, job_titles)
        if row["company_entity_id"] == good_entity_id or row["company_id"] in seen_bad:
            continue
        seen_bad.add(row["company_id"])
        plan.append(
            {
                "bad_company_id": row["company_id"],
                "bad_entity_id": row["company_entity_id"],
                "bad_name": row["company_name"],
                "good_entity_id": good_entity_id,
                "good_name": good_name,
                "position_entity_id": row["position_entity_id"],
                "source_doc": row.get("source_doc") or "jobs.csv",
                "source_table": row.get("source_table") or "jobs.csv",
                "source_csv": row.get("source_csv") or "jobs.csv",
                "source_row_id": row.get("source_row_id"),
                "source_chunk_ids": row.get("source_chunk_ids") or [],
            }
        )
    return plan


def merge_relationships(session, bad_id: str, good_entity_id: str) -> int:
    moved = 0
    outgoing = session.run(
        """
        MATCH (bad)-[r]->(other) WHERE elementId(bad) = $bad_id
        RETURN elementId(other) AS other_id, type(r) AS rel_type, properties(r) AS props
        """,
        bad_id=bad_id,
    ).data()
    incoming = session.run(
        """
        MATCH (other)-[r]->(bad) WHERE elementId(bad) = $bad_id
        RETURN elementId(other) AS other_id, type(r) AS rel_type, properties(r) AS props
        """,
        bad_id=bad_id,
    ).data()
    for row in outgoing:
        if not VALID_TOKEN.match(row["rel_type"]):
            continue
        props = {key: value for key, value in dict(row.get("props") or {}).items() if prop_writable(value)}
        session.run(
            f"""
            MATCH (good:Company {{entity_id: $good_entity_id}})
            MATCH (other) WHERE elementId(other) = $other_id
            MERGE (good)-[r:`{row['rel_type']}`]->(other)
            SET r += $props
            """,
            good_entity_id=good_entity_id,
            other_id=row["other_id"],
            props=props,
        ).consume()
        moved += 1
    for row in incoming:
        if not VALID_TOKEN.match(row["rel_type"]):
            continue
        props = {key: value for key, value in dict(row.get("props") or {}).items() if prop_writable(value)}
        session.run(
            f"""
            MATCH (other) WHERE elementId(other) = $other_id
            MATCH (good:Company {{entity_id: $good_entity_id}})
            MERGE (other)-[r:`{row['rel_type']}`]->(good)
            SET r += $props
            """,
            other_id=row["other_id"],
            good_entity_id=good_entity_id,
            props=props,
        ).consume()
        moved += 1
    return moved


def apply_plan(session, plan: list[dict[str, Any]]) -> dict[str, int]:
    stats = {"companies_merged": 0, "relationships_moved": 0}
    for item in plan:
        session.run(
            """
            MERGE (good:Entity:Company {entity_id: $entity_id})
            SET good.name = $name,
                good.canonical_name = $name,
                good.domain = 'job_market',
                good.type = 'Company',
                good.source_doc = $source_doc,
                good.source_table = $source_table,
                good.source_csv = $source_csv,
                good.source_row_id = $source_row_id,
                good.source_chunk_ids = $source_chunk_ids,
                good.evidence_contract = 'canonical_csv_source_row',
                good.schema_version = 'semantic-graph-v2',
                good.sync_source = 'canonical_business_entities',
                good.job_company_dedup_last_run_id = $run_id,
                good.job_company_dedup_updated_at = datetime()
            """,
            entity_id=item["good_entity_id"],
            name=item["good_name"],
            source_doc=item["source_doc"],
            source_table=item["source_table"],
            source_csv=item["source_csv"],
            source_row_id=item.get("source_row_id"),
            source_chunk_ids=item.get("source_chunk_ids") or [],
            run_id=RUN_ID,
        ).consume()
        stats["relationships_moved"] += merge_relationships(session, item["bad_company_id"], item["good_entity_id"])
        session.run("MATCH (bad) WHERE elementId(bad) = $bad_id DETACH DELETE bad", bad_id=item["bad_company_id"]).consume()
        stats["companies_merged"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--canonical-dir", type=Path, default=DEFAULT_CANONICAL_DIR)
    args = parser.parse_args()

    jobs = read_csv(args.canonical_dir / "jobs.csv")
    job_titles = {clean(row.get("job_title")) for row in jobs if clean(row.get("job_title"))}
    report_dir = REPORT_ROOT / RUN_ID
    driver = connect()
    try:
        with driver.session() as session:
            plan = load_plan(session, job_titles)
            results = apply_plan(session, plan) if args.confirm else {"companies_merged": 0, "relationships_moved": 0}
            summary = {
                "run_id": RUN_ID,
                "dry_run": not args.confirm,
                "planned_duplicates": len(plan),
                "results": results,
                "sample": plan[:20],
                "report_dir": str(report_dir),
            }
            write_json(report_dir / "summary.json", summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
