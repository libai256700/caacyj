#!/usr/bin/env python3
"""Run deterministic CSA CSV routing checks against /api/ask."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = BASE_DIR / "eval" / "csa_questions.json"


def ask(url: str, question: str, timeout: int) -> tuple[dict, float, str | None]:
    query = urllib.parse.urlencode({"q": question})
    sep = "&" if "?" in url else "?"
    req_url = f"{url}{sep}{query}"
    started = time.time()
    try:
        with urllib.request.urlopen(req_url, timeout=timeout) as resp:
            body = resp.read()
        return json.loads(body.decode("utf-8")), time.time() - started, None
    except Exception as e:
        return {}, time.time() - started, f"{type(e).__name__}: {e}"


def source_names(sources: list[dict]) -> list[str]:
    return [
        str(src.get("doc_name") or src.get("source_doc") or src.get("file") or "")
        for src in sources
    ]


def load_questions(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("question file must contain a JSON array")
    return data


def summarize(results: list[dict]) -> dict:
    total = len(results)
    ok = [r for r in results if r["ok"]]
    route_hits = [r for r in results if r["route_hit"]]
    topic_hits = [r for r in results if r["topic_hit"]]
    source_hits = [r for r in results if r["source_hit"]]
    degraded = [r for r in results if r["degraded"]]
    route_counts = Counter(r.get("route") or "missing" for r in results)
    avg_latency = sum(r["elapsed_s"] for r in results) / total if total else 0.0
    return {
        "total": total,
        "ok": len(ok),
        "failed": total - len(ok),
        "route_hit": len(route_hits),
        "route_hit_rate": round(len(route_hits) / total, 3) if total else 0.0,
        "topic_hit": len(topic_hits),
        "topic_hit_rate": round(len(topic_hits) / total, 3) if total else 0.0,
        "source_hit": len(source_hits),
        "source_hit_rate": round(len(source_hits) / total, 3) if total else 0.0,
        "degraded": len(degraded),
        "degraded_rate": round(len(degraded) / total, 3) if total else 0.0,
        "avg_latency_s": round(avg_latency, 3),
        "route_counts": dict(sorted(route_counts.items())),
        "failures": [
            {
                "id": r["id"],
                "question": r["question"],
                "error": r["error"],
                "route": r["route"],
                "expected_route": r["expected_route"],
                "topic": r["topic"],
                "expected_topic": r["expected_topic"],
                "sources": r["sources"],
                "answer_preview": r["answer_preview"],
            }
            for r in results
            if not r["ok"]
        ],
    }


def threshold_failures(summary: dict, args: argparse.Namespace) -> list[str]:
    failures = []
    if args.min_route_hit_rate is not None and summary["route_hit_rate"] < args.min_route_hit_rate:
        failures.append(
            f"CSA route hit {summary['route_hit_rate']:.1%} < required {args.min_route_hit_rate:.1%}"
        )
    if args.min_topic_hit_rate is not None and summary["topic_hit_rate"] < args.min_topic_hit_rate:
        failures.append(
            f"CSA topic hit {summary['topic_hit_rate']:.1%} < required {args.min_topic_hit_rate:.1%}"
        )
    if args.max_degraded_rate is not None and summary["degraded_rate"] > args.max_degraded_rate:
        failures.append(
            f"CSA degraded {summary['degraded_rate']:.1%} > allowed {args.max_degraded_rate:.1%}"
        )
    if args.max_avg_latency_s is not None and summary["avg_latency_s"] > args.max_avg_latency_s:
        failures.append(
            f"CSA avg latency {summary['avg_latency_s']}s > allowed {args.max_avg_latency_s}s"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5001/api/ask")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--min-route-hit-rate", type=float, help="fail if CSA route hit rate is below this rate")
    parser.add_argument("--min-topic-hit-rate", type=float, help="fail if CSA topic hit rate is below this rate")
    parser.add_argument("--max-degraded-rate", type=float, help="fail if degraded rate is above this rate")
    parser.add_argument("--max-avg-latency-s", type=float, help="fail if average latency is above this many seconds")
    args = parser.parse_args()

    cases = load_questions(args.questions)
    results = []
    started = time.time()
    for i, case in enumerate(cases, 1):
        print(f"[{i:02d}/{len(cases):02d}] {case['id']} ...", flush=True)
        data, elapsed, error = ask(args.url, case["question"], args.timeout)
        stats = data.get("stats", {}) if isinstance(data, dict) else {}
        answer = data.get("answer", "") if isinstance(data, dict) else ""
        sources = source_names(data.get("sources", [])) if isinstance(data, dict) else []
        route_hit = data.get("route") == case.get("expected_route")
        topic_hit = stats.get("topic") == case.get("expected_topic")
        source_hit = any(case.get("expected_source", "") in src for src in sources)
        content_hit = all(text in answer for text in case.get("must_contain", []))
        ok = error is None and route_hit and topic_hit and source_hit and content_hit
        results.append({
            "id": case["id"],
            "question": case["question"],
            "expected_route": case.get("expected_route"),
            "expected_topic": case.get("expected_topic"),
            "expected_source": case.get("expected_source"),
            "ok": ok,
            "error": error,
            "route": data.get("route"),
            "topic": stats.get("topic"),
            "sources": sources,
            "answer_preview": answer[:200],
            "elapsed_s": round(float(stats.get("elapsed_s") or elapsed), 3),
            "degraded": bool(stats.get("degraded")),
            "degraded_reasons": stats.get("degraded_reasons", []),
            "route_hit": route_hit,
            "topic_hit": topic_hit,
            "source_hit": source_hit,
            "content_hit": content_hit,
        })

    summary = summarize(results)
    report = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_s": round(time.time() - started, 2),
        "url": args.url,
        "questions": str(args.questions),
        "summary": summary,
        "results": results,
    }

    print("\n=== CSA Eval Summary ===")
    print(f"Total: {summary['total']} | OK: {summary['ok']} | Failed: {summary['failed']}")
    print(f"CSA route hit: {summary['route_hit']}/{summary['total']} ({summary['route_hit_rate']:.1%})")
    print(f"CSA topic hit: {summary['topic_hit']}/{summary['total']} ({summary['topic_hit_rate']:.1%})")
    print(f"Degraded: {summary['degraded']}/{summary['total']} ({summary['degraded_rate']:.1%})")
    print(f"Avg latency: {summary['avg_latency_s']}s")

    quality_failures = threshold_failures(summary, args)
    if quality_failures:
        print("\nQuality threshold failures:")
        for failure in quality_failures:
            print(f"- {failure}")

    if summary["failures"]:
        print("\nFailures:")
        for failure in summary["failures"]:
            print(json.dumps(failure, ensure_ascii=False, indent=2))

    if not args.no_save:
        output = args.output or BASE_DIR / "eval" / f"csa_results_{time.strftime('%Y%m%d_%H%M%S')}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved: {output}")

    return 0 if summary["failed"] == 0 and not quality_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
