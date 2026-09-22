#!/usr/bin/env python3
"""Acceptance gate for offline remote_replay retrieval packages."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import replay_retrieval_harness as harness


DEFAULT_FIXTURE = Path(__file__).with_name("acceptance_60_retrieval_questions.jsonl")


def load_cases(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, dict):
        return list(data.get("cases") or data.get("records") or [])
    return list(data)


def case_args(args: argparse.Namespace, case: Dict[str, Any]) -> argparse.Namespace:
    return argparse.Namespace(
        domain=case["domain"],
        query=case["query"],
        base_dir=args.base_dir,
        neo4j_uri=args.neo4j_uri,
        ollama_url=args.ollama_url,
        embedding_model=args.embedding_model,
        bm25_limit=args.bm25_limit,
        dense_limit=args.dense_limit,
        kg_limit=args.kg_limit,
        limit=args.limit,
        excerpt_chars=args.excerpt_chars,
    )


def assert_fixture_shape(cases: Sequence[Dict[str, Any]], expected_per_domain: int) -> List[str]:
    failures = []
    counts = Counter(case.get("domain") for case in cases)
    for domain in harness.DOMAINS:
        if counts.get(domain, 0) != expected_per_domain:
            failures.append(f"{domain}: expected {expected_per_domain} cases, got {counts.get(domain, 0)}")
    unknown = sorted(domain for domain in counts if domain not in harness.DOMAINS)
    if unknown:
        failures.append(f"unknown domains: {', '.join(unknown)}")
    return failures


def fetch_sqlite_rows(base_dir: Optional[str], domain: str, chunk_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    base = harness.resolve_replay_base(base_dir)
    root = harness.domain_dir(base, domain)
    store = harness.ReplaySQLite(root / "rag_chunks.db")
    try:
        return store.fetch_chunks(chunk_ids)
    finally:
        store.close()


def source_is_sqlite_backed(base_dir: Optional[str], domain: str, source: Dict[str, Any]) -> bool:
    if source.get("text_source") != "replay_sqlite":
        return False
    rows = fetch_sqlite_rows(base_dir, domain, [source.get("chunk_id")])
    row = rows.get(source.get("chunk_id"))
    if not row:
        return False
    return (
        source.get("text") == row.get("text")
        and source.get("doc_name") == row.get("doc_name")
        and source.get("chunk_index") == row.get("chunk_index")
    )


def contains_any(value: str, needles: Sequence[str]) -> bool:
    return any(needle in value for needle in needles)


def evaluate_case(args: argparse.Namespace, case: Dict[str, Any]) -> Dict[str, Any]:
    result = harness.run(case_args(args, case))
    sources = result.get("sources") or []
    top = sources[0] if sources else {}
    failures = []

    if not sources:
        failures.append("no sources returned")
    if result.get("missing_sqlite_chunk_ids"):
        failures.append(f"missing sqlite chunks: {result['missing_sqlite_chunk_ids']}")

    sqlite_backed = [source_is_sqlite_backed(args.base_dir, case["domain"], source) for source in sources]
    if not all(sqlite_backed):
        bad = [source.get("chunk_id") for source, ok in zip(sources, sqlite_backed) if not ok]
        failures.append(f"non-sqlite-backed sources: {bad}")

    expected_chunks = case.get("top_chunk_ids") or []
    if expected_chunks and top.get("chunk_id") not in expected_chunks:
        failures.append(f"top chunk {top.get('chunk_id')} not in expected {expected_chunks}")

    expected_doc_substrings = case.get("top_doc_any") or []
    if expected_doc_substrings and not contains_any(top.get("doc_name") or "", expected_doc_substrings):
        failures.append(f"top doc {top.get('doc_name')} does not match {expected_doc_substrings}")

    haystack = "\n".join(
        str(part or "")
        for part in (top.get("doc_name"), top.get("chunk_id"), top.get("text"), top.get("excerpt"))
    )
    missing_terms = [term for term in case.get("top_text_all") or [] if term not in haystack]
    if missing_terms:
        failures.append(f"top source missing required terms: {missing_terms}")

    any_terms = case.get("top_text_any") or []
    if any_terms and not contains_any(haystack, any_terms):
        failures.append(f"top source missing any of: {any_terms}")

    return {
        "id": case.get("id"),
        "domain": case.get("domain"),
        "query": case.get("query"),
        "ok": not failures,
        "failures": failures,
        "top": {
            "chunk_id": top.get("chunk_id"),
            "doc_name": top.get("doc_name"),
            "chunk_index": top.get("chunk_index"),
            "retrievers": top.get("retrievers"),
            "text_source": top.get("text_source"),
        },
        "retriever_counts": result.get("retriever_counts"),
        "degraded": result.get("degraded"),
        "degraded_reasons": result.get("degraded_reasons"),
        "source_count": len(sources),
    }


def summarize(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_domain: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in results:
        by_domain[item["domain"]].append(item)
    return {
        "total": len(results),
        "passed": sum(1 for item in results if item["ok"]),
        "failed": sum(1 for item in results if not item["ok"]),
        "domains": {
            domain: {
                "total": len(items),
                "passed": sum(1 for item in items if item["ok"]),
                "failed": sum(1 for item in items if not item["ok"]),
            }
            for domain, items in sorted(by_domain.items())
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 60-case remote_replay acceptance gate.")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--base-dir", help="Path containing regulation/question_bank/textbook replay packages.")
    parser.add_argument("--neo4j-uri", default=harness.DEFAULT_NEO4J_URI)
    parser.add_argument("--ollama-url", default=harness.DEFAULT_OLLAMA_URL)
    parser.add_argument("--embedding-model", default=harness.DEFAULT_EMBED_MODEL)
    parser.add_argument("--bm25-limit", type=int, default=20)
    parser.add_argument("--dense-limit", type=int, default=20)
    parser.add_argument("--kg-limit", type=int, default=20)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--excerpt-chars", type=int, default=420)
    parser.add_argument("--expected-per-domain", type=int, default=20)
    parser.add_argument("--output", help="Optional JSON report path.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    fixture = Path(args.fixture).expanduser()
    cases = load_cases(fixture)
    shape_failures = assert_fixture_shape(cases, args.expected_per_domain)

    results = [evaluate_case(args, case) for case in cases]
    report = {
        "fixture": str(fixture),
        "base_dir": str(harness.resolve_replay_base(args.base_dir)),
        "shape_failures": shape_failures,
        "summary": summarize(results),
        "results": results,
    }

    if args.output:
        Path(args.output).expanduser().write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"shape_failures": shape_failures, "summary": report["summary"]}, ensure_ascii=False, indent=2))
    failed = [item for item in results if not item["ok"]]
    if failed:
        print("\nFailures:", file=sys.stderr)
        for item in failed:
            print(
                f"- {item['id']} {item['domain']} {item['query']}: {'; '.join(item['failures'])}",
                file=sys.stderr,
            )
    return 1 if shape_failures or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
