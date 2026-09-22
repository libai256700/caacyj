#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import unittest
from shutil import copy2
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from verify_package import (
    FIXED_EVAL_ARTIFACTS,
    canonical_relative_path,
    scan_forbidden_text,
    verify_eval_artifacts,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


class PackageVerifierTests(unittest.TestCase):
    def test_manifest_paths_must_be_canonical_and_relative(self):
        self.assertEqual("deploy/pipeline/server.py", canonical_relative_path("deploy/pipeline/server.py"))
        for invalid in ("/tmp/server.py", "../server.py", "deploy//server.py", "deploy\\server.py"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    canonical_relative_path(invalid)

    def test_host_paths_and_literal_credentials_are_rejected(self):
        host_path = "path = '/" + "Users/name/data'"
        self.assertTrue(scan_forbidden_text("deploy/a.py", host_path))
        key_field = '"api_' + 'key"'
        literal_config = key_field + ': "not-a-secretref"'
        self.assertTrue(scan_forbidden_text("deploy/a.json", literal_config))
        self.assertEqual([], scan_forbidden_text("deploy/a.json", '"api_key": "secretref:KG_KEY"'))

    def test_eval_directory_allows_only_fixed_pending_gold_artifacts(self):
        with TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            (root / "eval").mkdir()
            for relative in FIXED_EVAL_ARTIFACTS:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                copy2(REPO_ROOT / relative, destination)

            self.assertEqual([], verify_eval_artifacts(root))

            (root / "eval" / "results.json").write_text("{}\n", encoding="utf-8")
            self.assertIn(
                "unexpected_eval_artifact:eval/results.json",
                verify_eval_artifacts(root),
            )

    def test_reviewed_gold_cannot_be_checked_into_the_portable_package(self):
        with TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            (root / "eval").mkdir()
            for relative in FIXED_EVAL_ARTIFACTS:
                copy2(REPO_ROOT / relative, root / relative)
            gold_path = root / "eval" / "cloud80_gold_standard_v1.json"
            gold = json.loads(gold_path.read_text(encoding="utf-8"))
            gold["review_policy"]["status"] = "reviewed-pending-signature"
            gold_path.write_text(
                json.dumps(gold, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            errors = verify_eval_artifacts(root)
            self.assertIn(
                "checked_in_gold_must_be_80_case_pending_template",
                errors,
            )
            self.assertIn(
                "fixed_eval_artifact_hash_mismatch:eval/cloud80_gold_standard_v1.json",
                errors,
            )

            gold["review_policy"] = []
            gold_path.write_text(json.dumps(gold) + "\n", encoding="utf-8")
            self.assertIn(
                "checked_in_gold_must_be_80_case_pending_template",
                verify_eval_artifacts(root),
            )


if __name__ == "__main__":
    unittest.main()
