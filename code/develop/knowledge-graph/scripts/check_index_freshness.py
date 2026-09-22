#!/usr/bin/env python3
"""Check SQLite/BM25/dense freshness after document imports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag_store.index_freshness import check_index_freshness, dumps_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(BASE_DIR / "rag_chunks.db"))
    parser.add_argument("--bm25-dir", default=str(BASE_DIR / "rag_index" / "bm25"))
    parser.add_argument("--dense-path", default=str(BASE_DIR / "rag_index" / "dense_bge_m3.sqlite"))
    parser.add_argument("--auto-rebuild", action="store_true", help="rebuild stale BM25 and dense indexes")
    parser.add_argument("--skip-bm25-rebuild", action="store_true", help="do not rebuild BM25 when --auto-rebuild is set")
    parser.add_argument("--skip-dense-rebuild", action="store_true", help="do not rebuild dense when --auto-rebuild is set")
    args = parser.parse_args()

    report = check_index_freshness(
        db_path=args.db_path,
        bm25_dir=args.bm25_dir,
        dense_path=args.dense_path,
        auto_rebuild=args.auto_rebuild,
        rebuild_bm25=not args.skip_bm25_rebuild,
        rebuild_dense=not args.skip_dense_rebuild,
    )
    print(dumps_report(report))
    return 0 if report["fresh"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
