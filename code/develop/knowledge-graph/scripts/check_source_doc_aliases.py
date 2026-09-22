#!/usr/bin/env python3
"""Check Neo4j source_doc values resolve to canonical SQLite chunks."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(BASE_DIR))

from rag_store.sqlite_store import RagStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-unresolved", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()

    password = (BASE_DIR / "neo4j" / ".neo4j_pass").read_text(encoding="utf-8").strip()
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    store = RagStore(str(BASE_DIR / "rag_chunks.db"))
    store.init_tables()

    with driver.session() as session:
        nodes = session.run(
            """
            MATCH (n) WHERE NOT n:Document
            RETURN n.name AS name, labels(n) AS labels, n.chunk_id AS chunk_id,
                   n.source_doc AS source_doc, n._created_by AS created_by
            ORDER BY n.name
            """
        ).data()

    summary: dict[str, Any] = {
        "total_entities": len(nodes),
        "chunk_id_resolves": 0,
        "source_doc_resolves": 0,
        "unresolved": 0,
        "unresolved_examples": [],
        "unresolved_sources": {},
    }
    unresolved_sources: Counter[str] = Counter()

    for node in nodes:
        chunk_id = node.get("chunk_id")
        if chunk_id and store.get_chunk_text(chunk_id):
            summary["chunk_id_resolves"] += 1
            continue

        source_names = [name for name in (node.get("source_doc"), node.get("created_by")) if name]
        if source_names and store.find_chunks_by_doc_names(source_names, limit_per_doc=1):
            summary["source_doc_resolves"] += 1
            continue

        summary["unresolved"] += 1
        for source in source_names or ["<missing source_doc>"]:
            unresolved_sources[source] += 1
        if len(summary["unresolved_examples"]) < 20:
            summary["unresolved_examples"].append({
                "name": node.get("name"),
                "labels": node.get("labels"),
                "source_doc": node.get("source_doc"),
                "created_by": node.get("created_by"),
            })

    summary["resolved_total"] = summary["chunk_id_resolves"] + summary["source_doc_resolves"]
    summary["resolved_rate"] = round(summary["resolved_total"] / max(summary["total_entities"], 1), 4)
    summary["unresolved_sources"] = dict(unresolved_sources.most_common(20))

    store.close()
    driver.close()

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"source_doc alias coverage: {summary['resolved_total']}/{summary['total_entities']} "
            f"({summary['resolved_rate']:.2%}); unresolved={summary['unresolved']}"
        )
        if summary["unresolved_examples"]:
            print("unresolved examples:")
            for item in summary["unresolved_examples"]:
                print(f"- {item['name']} | source_doc={item.get('source_doc')}")

    return 0 if summary["unresolved"] <= args.max_unresolved else 1


if __name__ == "__main__":
    raise SystemExit(main())
