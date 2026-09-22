#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.route_policy import out_of_scope_internal_fact_reason


class RoutePolicyTests(unittest.TestCase):
    def test_cloud_company_names_are_explicitly_out_of_scope(self):
        names = (
            "湖北云技科技有限公司",
            "云技科技",
            "云技科技公司",
            "湖北云技科技",
        )

        for name in names:
            with self.subTest(name=name):
                self.assertEqual(
                    "company_identity",
                    out_of_scope_internal_fact_reason(f"请介绍{name}的业务"),
                )

    def test_similar_company_name_is_not_rejected(self):
        self.assertIsNone(out_of_scope_internal_fact_reason("星云技术公司有哪些业务"))


if __name__ == "__main__":
    unittest.main()
