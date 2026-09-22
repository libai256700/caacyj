#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.merge_rerank import Merger
from rag_store.source_identity import document_key


class SourceIdentityTests(unittest.TestCase):
    def test_document_key_prefers_document_identity_over_legacy_chunk_id(self):
        first = {
            "source_id": "doc:weather",
            "doc_name": "理论题库_气象.txt",
            "chunk_id": "legacy-chunk:aaa",
        }
        second = {
            "source_id": "doc:weather",
            "doc_name": "理论题库_气象",
            "chunk_id": "legacy-chunk:bbb",
        }

        self.assertEqual(document_key(first), document_key(second))

    def test_document_name_normalization_handles_optional_txt_suffix(self):
        first = {"doc_name": "理论题库_气象.txt", "chunk_id": "legacy-chunk:a"}
        second = {"source_doc": "理论题库_气象", "chunk_id": "legacy-chunk:b"}

        self.assertEqual(document_key(first), document_key(second))

    def test_same_basename_in_different_source_paths_remains_distinct(self):
        first = {"source_doc": "法规/概述.txt", "chunk_id": "legacy-chunk:a"}
        second = {"source_doc": "题库/概述.txt", "chunk_id": "legacy-chunk:b"}

        self.assertNotEqual(document_key(first), document_key(second))

    def test_merger_caps_distinct_legacy_chunks_from_the_same_document(self):
        items = [
            {
                "chunk_id": f"legacy-chunk:weather-{index}",
                "doc_name": "理论题库_气象.txt",
                "score": 1.0 - index / 100,
            }
            for index in range(4)
        ]
        items.extend([
            {"chunk_id": "legacy-chunk:flight", "doc_name": "理论题库_飞行原理与飞行性能.txt", "score": 0.90},
            {"chunk_id": "legacy-chunk:law", "doc_name": "政策法规_CCAR-92部.txt", "score": 0.89},
            {"chunk_id": "legacy-chunk:system", "doc_name": "理论题库_系统组成及介绍.txt", "score": 0.88},
        ])

        result = Merger(top_k=5, doc_cap=2).merge(vector_results=items)

        weather = [item for item in result if item.get("doc_name") == "理论题库_气象.txt"]
        self.assertEqual(2, len(weather))
        self.assertEqual(5, len(result))


if __name__ == "__main__":
    unittest.main()
