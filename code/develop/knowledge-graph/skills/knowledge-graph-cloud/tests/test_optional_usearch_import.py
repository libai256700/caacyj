#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class OptionalUsearchImportTests(unittest.TestCase):
    """The offline contract layer must not require the optional ANN binary."""

    def test_modules_import_and_fail_closed_without_usearch(self) -> None:
        script = textwrap.dedent(
            """
            import importlib.abc
            import json
            import sys
            from pathlib import Path

            class BlockUsearch(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "usearch" or fullname.startswith("usearch."):
                        raise ModuleNotFoundError("usearch intentionally blocked", name="usearch")
                    return None

            sys.meta_path.insert(0, BlockUsearch())
            for name in tuple(sys.modules):
                if name == "usearch" or name.startswith("usearch."):
                    del sys.modules[name]

            repo_root = Path(sys.argv[1])
            sys.path.insert(0, str(repo_root / "deploy"))
            from rag_store.local_vector_store import (
                LocalVectorContract,
                LocalVectorError,
                LocalVectorStoreAdapter,
            )
            from rag_store.runtime_vector_reader import (
                ReadOnlyVectorContract,
                ReadOnlyVectorError,
                ReadOnlyVectorReader,
            )

            root = Path(sys.argv[2]).resolve()
            approved = root / "approved"
            data_root = approved / "vector-data"
            data_root.mkdir(parents=True)
            digest = "a" * 64
            common = {
                "approved_data_parent": approved,
                "data_root": data_root,
                "data_release_id": "offline-release",
                "authority_manifest_sha256": digest,
                "chunking_identity_sha256": "b" * 64,
                "embedding_identity_sha256": "c" * 64,
                "dimension": 3,
                "metric": "cosine",
                "schema_version": "offline-vector-v1",
                "chunk_index_name": "chunk-index",
                "entity_index_name": "entity-index",
                "top_k_max": 5,
                "max_vectors_per_index": 10,
                "metadata_allowlist": {
                    "chunk": ("document_id",),
                    "entity": ("entity_type",),
                },
            }
            local_contract = LocalVectorContract(**common)
            readonly_contract = ReadOnlyVectorContract(**common)

            errors = []
            try:
                LocalVectorStoreAdapter(local_contract)
            except LocalVectorError as exc:
                errors.append(str(exc))
            else:
                raise AssertionError("local adapter unexpectedly accepted missing usearch")
            try:
                ReadOnlyVectorReader(readonly_contract)
            except ReadOnlyVectorError as exc:
                errors.append(str(exc))
            else:
                raise AssertionError("read-only reader unexpectedly accepted missing usearch")

            if len(errors) != 2 or any("USEarch" not in item or "2.26.2" not in item for item in errors):
                raise AssertionError(json.dumps(errors, ensure_ascii=False))
            print(json.dumps({"errors": errors}, ensure_ascii=False))
            """
        )
        with tempfile.TemporaryDirectory(prefix="kg-optional-usearch-") as temporary:
            completed = subprocess.run(
                [sys.executable, "-c", script, str(REPO_ROOT), temporary],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **__import__("os").environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
        self.assertEqual(
            0,
            completed.returncode,
            msg=f"stdout={completed.stdout}\nstderr={completed.stderr}",
        )
        self.assertIn("USEarch", completed.stdout)
        self.assertIn("2.26.2", completed.stdout)


if __name__ == "__main__":
    unittest.main()
