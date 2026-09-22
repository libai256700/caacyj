#!/usr/bin/env python3
"""Run deterministic route-policy checks without calling the LLM or Neo4j."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = BASE_DIR / "eval" / "route_policy_questions.json"
sys.path.insert(0, str(BASE_DIR))

from rag_store.csa_router import CSARouter
from rag_store.route_policy import classify_route, needs_external_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    args = parser.parse_args()

    router = CSARouter()
    cases = json.loads(args.questions.read_text(encoding="utf-8"))
    failures = []
    for i, case in enumerate(cases, 1):
        question = case["question"]
        csa_result = router.answer(question)
        topic = csa_result.get("stats", {}).get("topic") if csa_result else None
        route = classify_route(question, csa_result)
        external = needs_external_candidate(question, [], csa_result)
        print(f"[{i:02d}/{len(cases):02d}] {case['id']} route={route} topic={topic}")
        if (
            route != case.get("expected_route")
            or topic != case.get("expected_topic")
            or external != case.get("expected_external_candidate")
        ):
            failures.append({
                "id": case["id"],
                "question": question,
                "expected_route": case.get("expected_route"),
                "actual_route": route,
                "expected_topic": case.get("expected_topic"),
                "actual_topic": topic,
                "expected_external_candidate": case.get("expected_external_candidate"),
                "actual_external_candidate": external,
                "answer": (csa_result or {}).get("answer", "")[:160],
            })

    ok = len(cases) - len(failures)
    print("\n=== Route Policy Eval Summary ===")
    print(f"Total: {len(cases)} | OK: {ok} | Failed: {len(failures)}")
    if failures:
        print("\nFailures:")
        for failure in failures:
            print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
