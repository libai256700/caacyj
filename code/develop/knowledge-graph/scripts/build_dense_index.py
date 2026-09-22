#!/usr/bin/env python3
"""Build the local bge-m3 dense chunk index from canonical SQLite chunks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag_store.dense_index import DenseIndex


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild the index from scratch")
    parser.add_argument("--index-path", default=str(BASE_DIR / "rag_index" / "dense_bge_m3.sqlite"))
    parser.add_argument("--db-path", default=str(BASE_DIR / "rag_chunks.db"))
    args = parser.parse_args()

    idx = DenseIndex(index_path=args.index_path, db_path=args.db_path)
    if idx.is_fresh() and not args.force:
        print(json.dumps({"fresh": True, "stats": idx.stats()}, ensure_ascii=False, indent=2))
        return 0

    stat = idx.build(force=args.force)
    print()
    print(json.dumps({"fresh": idx.is_fresh(), "build": stat, "stats": idx.stats()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
