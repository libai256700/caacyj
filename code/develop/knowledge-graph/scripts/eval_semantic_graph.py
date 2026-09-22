#!/usr/bin/env python3
"""Evaluate semantic-plan fields exposed by /api/ask."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "scripts"))

import eval_smoke


DEFAULT_QUESTIONS = BASE_DIR / "eval" / "semantic_graph_questions.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5001/api/ask")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    questions = eval_smoke.load_questions(args.questions)
    results = []
    for i, case in enumerate(questions, 1):
        print(f"[{i:02d}/{len(questions):02d}] {case['id']} ...", flush=True)
        data, elapsed, error = eval_smoke.ask(args.url, case["question"], args.timeout)
        plan = data.get("semantic_plan", {}) if isinstance(data, dict) else {}
        domains = set(plan.get("domains", []))
        expected_domains = set(case.get("expected_domains", []))
        graph_paths = data.get("graph_paths", []) if isinstance(data, dict) else []
        evidence_bindings = data.get("evidence_bindings", []) if isinstance(data, dict) else []
        domain_hit = expected_domains.issubset(domains) if expected_domains else True
        route_hit = data.get("route") == case.get("expected_route") if case.get("expected_route") else True
        graph_hit = bool(graph_paths or evidence_bindings) if case.get("must_have_graph") else True
        ok = error is None and "error" not in data and domain_hit and route_hit and graph_hit
        results.append({
            "id": case["id"],
            "question": case["question"],
            "ok": ok,
            "error": error or data.get("error"),
            "elapsed_s": round(elapsed, 3),
            "route": data.get("route"),
            "expected_route": case.get("expected_route"),
            "domains": sorted(domains),
            "expected_domains": sorted(expected_domains),
            "domain_hit": domain_hit,
            "route_hit": route_hit,
            "graph_paths": len(graph_paths),
            "evidence_bindings": len(evidence_bindings),
            "graph_hit": graph_hit,
            "degraded": bool(data.get("stats", {}).get("degraded")) if isinstance(data, dict) else False,
        })

    summary = {
        "total": len(results),
        "ok": sum(1 for row in results if row["ok"]),
        "failed": sum(1 for row in results if not row["ok"]),
    }
    report = {"summary": summary, "results": results}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.no_save:
        output = BASE_DIR / "eval" / "semantic_graph_results.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output)}, ensure_ascii=False))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
