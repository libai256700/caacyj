#!/usr/bin/env python3
"""Fail when business graph multi-hop or bridge governance reports drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MULTIHOP_REPORT = BASE_DIR / "review_reports" / "multihop_business_eval_report.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_bridge_report() -> Path:
    reports = sorted(
        BASE_DIR.glob("review_reports/multihop_bridge_governance_*/summary.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError("No multihop bridge governance summary found")
    return reports[0]


def latest_type_conflict_report() -> Path:
    reports = sorted(
        BASE_DIR.glob("review_reports/type_conflict_governance_*/summary.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError("No type conflict governance summary found")
    return reports[0]


def latest_job_company_report() -> Path:
    reports = sorted(
        BASE_DIR.glob("review_reports/job_company_dedup_governance_*/summary.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError("No job company dedup governance summary found")
    return reports[0]


def bridge_pending(summary: dict[str, Any]) -> dict[str, int]:
    normalization = summary.get("node_chunk_normalization") or {}
    bridge_result = summary.get("bridge_result") or {}
    audit = summary.get("bridge_audit_backfill") or {}
    return {
        "node_chunk_updates": int(normalization.get("planned_or_applied_node_chunk_updates") or 0),
        "bridge_plans": int(bridge_result.get("planned") or 0),
        "bridge_audit_node_updates": int(audit.get("planned_node_updates") or 0),
        "bridge_audit_relationship_updates": int(audit.get("planned_relationship_updates") or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--multihop-report", type=Path, default=DEFAULT_MULTIHOP_REPORT)
    parser.add_argument("--bridge-summary", type=Path)
    parser.add_argument("--type-conflict-summary", type=Path)
    parser.add_argument("--job-company-summary", type=Path)
    args = parser.parse_args()

    multihop_report = args.multihop_report
    bridge_summary = args.bridge_summary or latest_bridge_report()
    type_conflict_summary = args.type_conflict_summary or latest_type_conflict_report()
    job_company_summary = args.job_company_summary or latest_job_company_report()
    failures: list[dict[str, Any]] = []

    multihop = read_json(multihop_report)
    multihop_summary = multihop.get("summary") or {}
    if int(multihop_summary.get("failed") or 0) != 0:
        failures.append(
            {
                "gate": "multihop_business_eval",
                "reason": "failed_cases",
                "count": int(multihop_summary.get("failed") or 0),
                "report": str(multihop_report),
            }
        )
    failed_paths = int((multihop_summary.get("repair_priority") or {}).get("total_failed_paths") or 0)
    if failed_paths != 0:
        failures.append(
            {
                "gate": "multihop_business_eval",
                "reason": "failed_expected_paths",
                "count": failed_paths,
                "report": str(multihop_report),
            }
        )

    bridge = read_json(bridge_summary)
    if not bridge.get("dry_run"):
        failures.append(
            {
                "gate": "multihop_bridge_governance",
                "reason": "bridge_summary_is_not_dry_run",
                "report": str(bridge_summary),
            }
        )
    pending = bridge_pending(bridge)
    for key, count in pending.items():
        if count:
            failures.append(
                {
                    "gate": "multihop_bridge_governance",
                    "reason": key,
                    "count": count,
                    "report": str(bridge_summary),
                }
            )

    type_conflicts = read_json(type_conflict_summary)
    if not type_conflicts.get("dry_run"):
        failures.append(
            {
                "gate": "type_conflict_governance",
                "reason": "type_conflict_summary_is_not_dry_run",
                "report": str(type_conflict_summary),
            }
        )
    before_conflicts = int(type_conflicts.get("before_conflict_groups") or 0)
    after_conflicts = int(type_conflicts.get("after_conflict_groups") or 0)
    if before_conflicts or after_conflicts:
        failures.append(
            {
                "gate": "type_conflict_governance",
                "reason": "same_name_type_conflicts",
                "before_conflict_groups": before_conflicts,
                "after_conflict_groups": after_conflicts,
                "report": str(type_conflict_summary),
            }
        )

    job_companies = read_json(job_company_summary)
    if not job_companies.get("dry_run"):
        failures.append(
            {
                "gate": "job_company_dedup_governance",
                "reason": "job_company_summary_is_not_dry_run",
                "report": str(job_company_summary),
            }
        )
    planned_job_company_duplicates = int(job_companies.get("planned_duplicates") or 0)
    if planned_job_company_duplicates:
        failures.append(
            {
                "gate": "job_company_dedup_governance",
                "reason": "job_company_duplicates",
                "count": planned_job_company_duplicates,
                "report": str(job_company_summary),
            }
        )

    report = {
        "passed": not failures,
        "multihop_report": str(multihop_report),
        "bridge_summary": str(bridge_summary),
        "type_conflict_summary": str(type_conflict_summary),
        "job_company_summary": str(job_company_summary),
        "multihop": {
            "total": int(multihop_summary.get("total") or 0),
            "passed": int(multihop_summary.get("passed") or 0),
            "failed": int(multihop_summary.get("failed") or 0),
            "failed_paths": failed_paths,
        },
        "bridge_pending": pending,
        "type_conflicts": {
            "before_conflict_groups": before_conflicts,
            "after_conflict_groups": after_conflicts,
        },
        "job_company_duplicates": planned_job_company_duplicates,
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
