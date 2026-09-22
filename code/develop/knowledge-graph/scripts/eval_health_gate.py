#!/usr/bin/env python3
"""Run fixed post-import and post-routing health gates for /api/ask."""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = BASE_DIR / "eval" / "health_gate_config.json"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


eval_smoke = load_module(BASE_DIR / "scripts" / "eval_smoke.py", "eval_smoke_module")
eval_csa = load_module(BASE_DIR / "scripts" / "eval_csa.py", "eval_csa_module")


def ask_with_retry(url: str, question: str, timeout: int, retries: int) -> tuple[dict, float, str | None]:
    last = ({}, 0.0, "not_run")
    for attempt in range(retries + 1):
        last = eval_smoke.ask(url, question, timeout)
        if last[2] is None:
            return last
        if attempt < retries:
            time.sleep(min(2 ** attempt, 5))
    return last


def run_retrieval_suite(name: str, config: dict, url: str, timeout: int, retries: int) -> dict:
    questions_path = BASE_DIR / config["questions"]
    questions = eval_smoke.load_questions(questions_path)
    results = []
    started = time.time()
    for i, case in enumerate(questions, 1):
        print(f"[{name} {i:02d}/{len(questions):02d}] {case['id']} ...", flush=True)
        data, elapsed, error = ask_with_retry(url, case["question"], timeout, retries)
        sources = data.get("sources", []) if isinstance(data, dict) else []
        stats = data.get("stats", {}) if isinstance(data, dict) else {}
        top_docs = [eval_smoke.source_doc(src) for src in sources[:10]]
        results.append({
            "id": case["id"],
            "category": case.get("category", "unknown"),
            "question": case["question"],
            "expected_docs": case.get("expected_docs", []),
            "ok": error is None and "error" not in data,
            "error": error or data.get("error"),
            "route": data.get("route"),
            "elapsed_s": round(float(stats.get("elapsed_s") or elapsed), 3),
            "degraded": bool(stats.get("degraded")),
            "degraded_reasons": stats.get("degraded_reasons", []),
            "source_count": len(sources),
            "top_docs": top_docs,
            "expected_doc_hit_at_5": eval_smoke.expected_hit(sources, case.get("expected_docs", []), 5),
            "expected_doc_hit_at_10": eval_smoke.expected_hit(sources, case.get("expected_docs", []), 10),
            "stats": stats,
        })
    summary = eval_smoke.summarize(results)
    failures = retrieval_threshold_failures(summary, config.get("thresholds", {}))
    return {
        "name": name,
        "type": "retrieval",
        "questions": str(questions_path),
        "duration_s": round(time.time() - started, 2),
        "summary": summary,
        "threshold_failures": failures,
        "passed": summary["failed"] == 0 and not failures,
        "results": results,
    }


def run_csa_suite(name: str, config: dict, url: str, timeout: int, retries: int) -> dict:
    questions_path = BASE_DIR / config["questions"]
    questions = eval_csa.load_questions(questions_path)
    results = []
    started = time.time()
    for i, case in enumerate(questions, 1):
        print(f"[{name} {i:02d}/{len(questions):02d}] {case['id']} ...", flush=True)
        data, elapsed, error = ask_with_retry(url, case["question"], timeout, retries)
        stats = data.get("stats", {}) if isinstance(data, dict) else {}
        answer = data.get("answer", "") if isinstance(data, dict) else ""
        sources = eval_csa.source_names(data.get("sources", [])) if isinstance(data, dict) else []
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
    summary = eval_csa.summarize(results)
    failures = csa_threshold_failures(summary, config.get("thresholds", {}))
    return {
        "name": name,
        "type": "csa",
        "questions": str(questions_path),
        "duration_s": round(time.time() - started, 2),
        "summary": summary,
        "threshold_failures": failures,
        "passed": summary["failed"] == 0 and not failures,
        "results": results,
    }


def run_semantic_suite(name: str, config: dict, url: str, timeout: int, retries: int) -> dict:
    questions_path = BASE_DIR / config["questions"]
    questions = eval_smoke.load_questions(questions_path)
    results = []
    started = time.time()
    for i, case in enumerate(questions, 1):
        print(f"[{name} {i:02d}/{len(questions):02d}] {case['id']} ...", flush=True)
        data, elapsed, error = ask_with_retry(url, case["question"], timeout, retries)
        plan = data.get("semantic_plan", {}) if isinstance(data, dict) else {}
        domains = set(plan.get("domains", []))
        expected_domains = set(case.get("expected_domains", []))
        graph_paths = data.get("graph_paths", []) if isinstance(data, dict) else []
        evidence_bindings = data.get("evidence_bindings", []) if isinstance(data, dict) else []
        domain_hit = expected_domains.issubset(domains) if expected_domains else True
        route_hit = data.get("route") == case.get("expected_route") if case.get("expected_route") else True
        graph_hit = bool(graph_paths or evidence_bindings) if case.get("must_have_graph") else True
        ok = error is None and "error" not in data and domain_hit and route_hit and graph_hit
        stats = data.get("stats", {}) if isinstance(data, dict) else {}
        results.append({
            "id": case["id"],
            "question": case["question"],
            "ok": ok,
            "error": error or data.get("error"),
            "route": data.get("route"),
            "expected_route": case.get("expected_route"),
            "domains": sorted(domains),
            "expected_domains": sorted(expected_domains),
            "domain_hit": domain_hit,
            "route_hit": route_hit,
            "graph_paths": len(graph_paths),
            "evidence_bindings": len(evidence_bindings),
            "graph_hit": graph_hit,
            "elapsed_s": round(float(stats.get("elapsed_s") or elapsed), 3),
            "degraded": bool(stats.get("degraded")),
            "degraded_reasons": stats.get("degraded_reasons", []),
        })
    summary = summarize_semantic(results)
    failures = semantic_threshold_failures(summary, config.get("thresholds", {}))
    return {
        "name": name,
        "type": "semantic",
        "questions": str(questions_path),
        "duration_s": round(time.time() - started, 2),
        "summary": summary,
        "threshold_failures": failures,
        "passed": summary["failed"] == 0 and not failures,
        "results": results,
    }


def retrieval_threshold_failures(summary: dict, thresholds: dict) -> list[str]:
    checks = [
        ("source-backed", "source_backed_rate", ">=", "min_source_backed_rate"),
        ("expected doc hit@5", "expected_doc_hit_at_5_rate", ">=", "min_expected_doc_hit_at_5_rate"),
        ("degraded", "degraded_rate", "<=", "max_degraded_rate"),
        ("avg latency", "avg_latency_s", "<=", "max_avg_latency_s"),
    ]
    return threshold_failures(summary, thresholds, checks)


def csa_threshold_failures(summary: dict, thresholds: dict) -> list[str]:
    checks = [
        ("CSA route hit", "route_hit_rate", ">=", "min_route_hit_rate"),
        ("CSA topic hit", "topic_hit_rate", ">=", "min_topic_hit_rate"),
        ("CSA degraded", "degraded_rate", "<=", "max_degraded_rate"),
        ("CSA avg latency", "avg_latency_s", "<=", "max_avg_latency_s"),
    ]
    return threshold_failures(summary, thresholds, checks)


def summarize_semantic(results: list[dict]) -> dict:
    total = len(results)
    ok_rows = [row for row in results if row["ok"]]
    avg_latency = sum(row["elapsed_s"] for row in ok_rows) / len(ok_rows) if ok_rows else 0.0
    return {
        "total": total,
        "ok": len(ok_rows),
        "failed": total - len(ok_rows),
        "domain_hit_rate": round(sum(1 for row in results if row["domain_hit"]) / total, 3) if total else 0.0,
        "route_hit_rate": round(sum(1 for row in results if row["route_hit"]) / total, 3) if total else 0.0,
        "graph_hit_rate": round(sum(1 for row in results if row["graph_hit"]) / total, 3) if total else 0.0,
        "degraded_rate": round(sum(1 for row in ok_rows if row["degraded"]) / total, 3) if total else 0.0,
        "avg_latency_s": round(avg_latency, 2),
        "failures": [
            {
                "id": row["id"],
                "question": row["question"],
                "route": row["route"],
                "domains": row["domains"],
                "error": row["error"],
            }
            for row in results
            if not row["ok"]
        ],
    }


def semantic_threshold_failures(summary: dict, thresholds: dict) -> list[str]:
    checks = [
        ("semantic domain hit", "domain_hit_rate", ">=", "min_domain_hit_rate"),
        ("semantic route hit", "route_hit_rate", ">=", "min_route_hit_rate"),
        ("semantic graph hit", "graph_hit_rate", ">=", "min_graph_hit_rate"),
        ("semantic degraded", "degraded_rate", "<=", "max_degraded_rate"),
        ("semantic avg latency", "avg_latency_s", "<=", "max_avg_latency_s"),
    ]
    return threshold_failures(summary, thresholds, checks)


def threshold_failures(summary: dict, thresholds: dict, checks: list[tuple[str, str, str, str]]) -> list[str]:
    failures = []
    for label, metric_key, op, threshold_key in checks:
        if threshold_key not in thresholds:
            continue
        actual = float(summary.get(metric_key, 0))
        expected = float(thresholds[threshold_key])
        failed = actual < expected if op == ">=" else actual > expected
        if failed:
            if metric_key.endswith("_s"):
                failures.append(f"{label} {actual:.3f}s {op} allowed {expected:.3f}s")
            else:
                failures.append(f"{label} {actual:.1%} {op} required {expected:.1%}")
    return failures


def compact_summary(suite: dict) -> str:
    s = suite["summary"]
    if suite["type"] == "csa":
        return (
            f"{suite['name']}: pass={suite['passed']} ok={s['ok']}/{s['total']} "
            f"route={s['route_hit_rate']:.1%} degraded={s['degraded_rate']:.1%} "
            f"avg={s['avg_latency_s']}s"
        )
    if suite["type"] == "semantic":
        return (
            f"{suite['name']}: pass={suite['passed']} ok={s['ok']}/{s['total']} "
            f"domain={s['domain_hit_rate']:.1%} graph={s['graph_hit_rate']:.1%} "
            f"degraded={s['degraded_rate']:.1%} avg={s['avg_latency_s']}s"
        )
    return (
        f"{suite['name']}: pass={suite['passed']} ok={s['ok']}/{s['total']} "
        f"source={s['source_backed_rate']:.1%} hit@5={s['expected_doc_hit_at_5_rate']:.1%} "
        f"degraded={s['degraded_rate']:.1%} avg={s['avg_latency_s']}s"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--url", help="override /api/ask URL from config")
    parser.add_argument("--timeout", type=int, help="override request timeout seconds")
    parser.add_argument("--suite", action="append", help="suite name to run; can be repeated")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--retries", type=int, default=0, help="retry failed HTTP calls this many times")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    url = args.url or config.get("url", "http://127.0.0.1:5001/api/ask")
    timeout = args.timeout or int(config.get("timeout_s", 120))
    suite_configs = config.get("suites", {})
    selected = args.suite or list(suite_configs.keys())

    suites = []
    started = time.time()
    for name in selected:
        if name not in suite_configs:
            raise ValueError(f"unknown suite: {name}")
        suite_config = suite_configs[name]
        if suite_config.get("type") == "csa":
            suites.append(run_csa_suite(name, suite_config, url, timeout, args.retries))
        elif suite_config.get("type") == "semantic":
            suites.append(run_semantic_suite(name, suite_config, url, timeout, args.retries))
        else:
            suites.append(run_retrieval_suite(name, suite_config, url, timeout, args.retries))

    passed = all(suite["passed"] for suite in suites)
    report = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_s": round(time.time() - started, 2),
        "url": url,
        "config": str(args.config),
        "passed": passed,
        "suites": suites,
    }

    print("\n=== Health Gate Summary ===")
    for suite in suites:
        print(compact_summary(suite))
        for failure in suite["threshold_failures"]:
            print(f"  - {failure}")

    if not args.no_save:
        output = args.output or BASE_DIR / "eval" / f"health_gate_results_{time.strftime('%Y%m%d_%H%M%S')}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved: {output}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
