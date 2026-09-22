#!/usr/bin/env python3
"""Run a small retrieval QA smoke evaluation against /api/ask."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = BASE_DIR / "eval" / "smoke_questions.json"


def load_questions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("question file must contain a JSON array")
    return data


def ask(url: str, question: str, timeout: int) -> tuple[dict, float, str | None]:
    query = urllib.parse.urlencode({"q": question})
    sep = "&" if "?" in url else "?"
    req_url = f"{url}{sep}{query}"
    started = time.time()
    try:
        with urllib.request.urlopen(req_url, timeout=timeout) as resp:
            body = resp.read()
        elapsed = time.time() - started
        return json.loads(body.decode("utf-8")), elapsed, None
    except urllib.error.HTTPError as e:
        elapsed = time.time() - started
        body = e.read().decode("utf-8", errors="replace")
        return {}, elapsed, f"HTTP {e.code}: {body[:200]}"
    except Exception as e:
        elapsed = time.time() - started
        return {}, elapsed, f"{type(e).__name__}: {e}"


def source_doc(source: dict) -> str:
    return str(source.get("doc_name") or source.get("doc") or source.get("source_doc") or source.get("file") or "")


def expected_hit(sources: list[dict], expected_docs: list[str], top_k: int) -> bool:
    if not expected_docs:
        return False
    docs = [source_doc(src) for src in sources[:top_k]]
    return any(expected in doc for expected in expected_docs for doc in docs)


def summarize(results: list[dict]) -> dict:
    total = len(results)
    ok = [r for r in results if r["ok"]]
    backed = [r for r in ok if r["source_count"] > 0]
    hit5 = [r for r in ok if r["expected_doc_hit_at_5"]]
    hit10 = [r for r in ok if r["expected_doc_hit_at_10"]]
    degraded = [r for r in ok if r["degraded"]]
    avg_latency = sum(r["elapsed_s"] for r in ok) / len(ok) if ok else 0.0

    by_category: dict[str, dict] = {}
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        buckets[r["category"]].append(r)
    for category, rows in sorted(buckets.items()):
        ok_rows = [r for r in rows if r["ok"]]
        by_category[category] = {
            "total": len(rows),
            "ok": len(ok_rows),
            "expected_doc_hit_at_5": sum(1 for r in ok_rows if r["expected_doc_hit_at_5"]),
            "source_backed": sum(1 for r in ok_rows if r["source_count"] > 0),
            "avg_latency_s": round(sum(r["elapsed_s"] for r in ok_rows) / len(ok_rows), 2) if ok_rows else 0.0,
        }

    return {
        "total": total,
        "ok": len(ok),
        "failed": total - len(ok),
        "source_backed": len(backed),
        "source_backed_rate": round(len(backed) / total, 3) if total else 0.0,
        "expected_doc_hit_at_5": len(hit5),
        "expected_doc_hit_at_5_rate": round(len(hit5) / total, 3) if total else 0.0,
        "expected_doc_hit_at_10": len(hit10),
        "expected_doc_hit_at_10_rate": round(len(hit10) / total, 3) if total else 0.0,
        "degraded": len(degraded),
        "degraded_rate": round(len(degraded) / total, 3) if total else 0.0,
        "avg_latency_s": round(avg_latency, 2),
        "by_category": by_category,
        "failures": [
            {
                "id": r["id"],
                "category": r["category"],
                "question": r["question"],
                "error": r["error"],
            }
            for r in results
            if not r["ok"]
        ],
        "misses_at_5": [
            {
                "id": r["id"],
                "category": r["category"],
                "question": r["question"],
                "expected_docs": r["expected_docs"],
                "top_docs": r["top_docs"][:5],
            }
            for r in results
            if r["ok"] and not r["expected_doc_hit_at_5"]
        ],
    }


def print_summary(summary: dict) -> None:
    print("\n=== Smoke Eval Summary ===")
    print(f"Total: {summary['total']} | OK: {summary['ok']} | Failed: {summary['failed']}")
    print(
        "Source-backed: "
        f"{summary['source_backed']}/{summary['total']} ({summary['source_backed_rate']:.1%})"
    )
    print(
        "Expected doc hit@5: "
        f"{summary['expected_doc_hit_at_5']}/{summary['total']} ({summary['expected_doc_hit_at_5_rate']:.1%})"
    )
    print(
        "Expected doc hit@10: "
        f"{summary['expected_doc_hit_at_10']}/{summary['total']} ({summary['expected_doc_hit_at_10_rate']:.1%})"
    )
    print(f"Degraded: {summary['degraded']}/{summary['total']} ({summary['degraded_rate']:.1%})")
    print(f"Avg latency: {summary['avg_latency_s']}s")

    print("\nBy category:")
    for category, row in summary["by_category"].items():
        print(
            f"- {category}: ok={row['ok']}/{row['total']}, "
            f"hit@5={row['expected_doc_hit_at_5']}/{row['total']}, "
            f"source={row['source_backed']}/{row['total']}, "
            f"avg={row['avg_latency_s']}s"
        )

    if summary["misses_at_5"]:
        print("\nMisses at 5:")
        for miss in summary["misses_at_5"]:
            print(f"- {miss['id']}: expected={miss['expected_docs']} top={miss['top_docs']}")
    if summary["failures"]:
        print("\nFailures:")
        for failure in summary["failures"]:
            print(f"- {failure['id']}: {failure['error']}")


def threshold_failures(summary: dict, args: argparse.Namespace) -> list[str]:
    failures = []
    if args.min_hit5_rate is not None and summary["expected_doc_hit_at_5_rate"] < args.min_hit5_rate:
        failures.append(
            f"hit@5 {summary['expected_doc_hit_at_5_rate']:.1%} < required {args.min_hit5_rate:.1%}"
        )
    if args.min_source_rate is not None and summary["source_backed_rate"] < args.min_source_rate:
        failures.append(
            f"source-backed {summary['source_backed_rate']:.1%} < required {args.min_source_rate:.1%}"
        )
    if args.max_degraded_rate is not None and summary["degraded_rate"] > args.max_degraded_rate:
        failures.append(
            f"degraded {summary['degraded_rate']:.1%} > allowed {args.max_degraded_rate:.1%}"
        )
    if args.max_avg_latency_s is not None and summary["avg_latency_s"] > args.max_avg_latency_s:
        failures.append(
            f"avg latency {summary['avg_latency_s']}s > allowed {args.max_avg_latency_s}s"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5001/api/ask")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--min-hit5-rate", type=float, help="fail if expected doc hit@5 is below this rate")
    parser.add_argument("--min-source-rate", type=float, help="fail if source-backed rate is below this rate")
    parser.add_argument("--max-degraded-rate", type=float, help="fail if degraded rate is above this rate")
    parser.add_argument("--max-avg-latency-s", type=float, help="fail if average latency is above this many seconds")
    args = parser.parse_args()

    questions = load_questions(args.questions)
    results = []
    started = time.time()

    for i, case in enumerate(questions, 1):
        q = case["question"]
        print(f"[{i:02d}/{len(questions):02d}] {case['id']} ...", flush=True)
        data, elapsed, error = ask(args.url, q, args.timeout)
        sources = data.get("sources", []) if isinstance(data, dict) else []
        stats = data.get("stats", {}) if isinstance(data, dict) else {}
        top_docs = [source_doc(src) for src in sources[:10]]
        result = {
            "id": case["id"],
            "category": case.get("category", "unknown"),
            "question": q,
            "expected_docs": case.get("expected_docs", []),
            "ok": error is None and "error" not in data,
            "error": error or data.get("error"),
            "elapsed_s": round(float(stats.get("elapsed_s") or elapsed), 2),
            "degraded": bool(stats.get("degraded")),
            "degraded_reasons": stats.get("degraded_reasons", []),
            "source_count": len(sources),
            "top_docs": top_docs,
            "expected_doc_hit_at_5": expected_hit(sources, case.get("expected_docs", []), 5),
            "expected_doc_hit_at_10": expected_hit(sources, case.get("expected_docs", []), 10),
            "stats": stats,
        }
        results.append(result)

    summary = summarize(results)
    report = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_s": round(time.time() - started, 2),
        "url": args.url,
        "questions": str(args.questions),
        "summary": summary,
        "results": results,
    }

    print_summary(summary)
    quality_failures = threshold_failures(summary, args)
    if quality_failures:
        print("\nQuality threshold failures:")
        for failure in quality_failures:
            print(f"- {failure}")

    if not args.no_save:
        output = args.output or BASE_DIR / "eval" / f"smoke_results_{time.strftime('%Y%m%d_%H%M%S')}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nSaved: {output}")

    return 0 if summary["failed"] == 0 and not quality_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
