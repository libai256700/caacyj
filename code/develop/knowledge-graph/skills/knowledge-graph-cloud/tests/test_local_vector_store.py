#!/usr/bin/env python3

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "deploy"))

from rag_store.local_vector_store import (
    ACTIVE_STATE_SCHEMA_VERSION,
    ENGINE_VERSION,
    INDEX_BUILD_THREADS,
    LocalVectorContract,
    LocalVectorError,
    LocalVectorIntegrityError,
    LocalVectorStoreAdapter,
    VectorRecord,
    _encode_manifest_integer_key,
)


class LocalVectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kg-local-vector-test-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self._restore_write_permissions)

    def _contract(self, root: Path | None = None, **changes):
        values = {
            "approved_data_parent": self.root,
            "data_root": root or self.root / "vector-data",
            "data_release_id": "synthetic-release-a",
            "authority_manifest_sha256": "b" * 64,
            "chunking_identity_sha256": "c" * 64,
            "embedding_identity_sha256": "a" * 64,
            "dimension": 3,
            "metric": "cosine",
            "schema_version": "synthetic-vector-schema-v1",
            "chunk_index_name": "chunk-vectors",
            "entity_index_name": "entity-vectors",
            "top_k_max": 5,
            "max_vectors_per_index": 20,
            "metadata_allowlist": {
                "chunk": ("document_id", "chunk_index"),
                "entity": ("entity_type", "evidence_chunk_ids"),
            },
        }
        values.update(changes)
        return LocalVectorContract(**values)

    @staticmethod
    def _records():
        chunks = (
            VectorRecord(
                "chunk-a",
                (1.0, 0.0, 0.0),
                {"document_id": "doc-a", "chunk_index": 0},
            ),
            VectorRecord(
                "chunk-b",
                (0.0, 1.0, 0.0),
                {"document_id": "doc-b", "chunk_index": 1},
            ),
        )
        entities = (
            VectorRecord(
                "entity-a",
                (0.0, 0.0, 1.0),
                {"entity_type": "synthetic", "evidence_chunk_ids": ["chunk-a"]},
            ),
        )
        return chunks, entities

    def _build(self, contract: LocalVectorContract | None = None):
        frozen = contract or self._contract()
        chunks, entities = self._records()
        receipt = LocalVectorStoreAdapter(frozen).build_candidate(
            chunk_records=chunks,
            entity_records=entities,
            expected_ids={
                "chunk": ("chunk-a", "chunk-b"),
                "entity": ("entity-a",),
            },
        )
        return frozen, receipt

    def _activate_read_only(self, contract, receipt):
        active = contract.active_release_dir
        active.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(receipt.release_dir, active)
        for path in sorted(active.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            path.chmod(0o555 if path.is_dir() else 0o444)
        active.chmod(0o555)
        return active

    def _write_active_state(self, contract, receipt):
        state_path = contract.active_state_path
        state_path.write_text(
            json.dumps(
                {
                    "schema_version": ACTIVE_STATE_SCHEMA_VERSION,
                    "data_release_id": contract.data_release_id,
                    "manifest_sha256": receipt.manifest_sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        state_path.chmod(0o444)
        return state_path

    def _restore_write_permissions(self):
        if not self.root.exists():
            return
        for root, directories, files in os.walk(self.root):
            Path(root).chmod(0o755)
            for name in directories:
                (Path(root) / name).chmod(0o755)
            for name in files:
                (Path(root) / name).chmod(0o644)

    def test_candidate_build_and_active_search_need_no_network(self):
        contract = self._contract()
        with mock.patch.object(
            socket, "socket", side_effect=AssertionError("network forbidden")
        ):
            frozen, receipt = self._build(contract)
        self.assertEqual(2, receipt.chunk_count)
        self.assertEqual(1, receipt.entity_count)
        self.assertTrue((receipt.release_dir / "chunk-vectors/index.usearch").is_file())
        self.assertTrue((receipt.release_dir / "entity-vectors/index.usearch").is_file())
        self.assertFalse(frozen.active_release_dir.exists())

        self._activate_read_only(frozen, receipt)
        with mock.patch.object(
            socket, "socket", side_effect=AssertionError("network forbidden")
        ):
            view = LocalVectorStoreAdapter(frozen).open_active(
                expected_manifest_sha256=receipt.manifest_sha256
            )
            self.addCleanup(view.close)
            chunk_hits = view.query_chunk((1.0, 0.0, 0.0), top_k=1)
            entity_hits = view.query_entity(
                (0.0, 0.0, 1.0),
                top_k=1,
                metadata_filter={"entity_type": "synthetic"},
            )

        self.assertEqual("chunk-a", chunk_hits[0].object_id)
        self.assertEqual("entity-a", entity_hits[0].object_id)
        self.assertEqual("synthetic-release-a", chunk_hits[0].data_release_id)
        self.assertFalse(hasattr(view, "build_candidate"))
        with self.assertRaises(RuntimeError):
            view._indexes["chunk"].add(
                999, np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
            )

    def test_stable_integer_mapping_is_reproducible_and_bound_to_release(self):
        first_contract, first_receipt = self._build()
        second_contract = self._contract(self.root / "second-vector-data")
        _, second_receipt = self._build(second_contract)

        def keys(receipt):
            manifest = json.loads(
                (receipt.release_dir / "local_vector_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            return {
                kind: {
                    item["object_id"]: item["integer_key"]
                    for item in manifest["indexes"][kind]["objects"]
                }
                for kind in ("chunk", "entity")
            }

        self.assertEqual(keys(first_receipt), keys(second_receipt))
        changed = self._contract(
            self.root / "third-vector-data", data_release_id="synthetic-release-b"
        )
        _, changed_receipt = self._build(changed)
        self.assertNotEqual(keys(first_receipt), keys(changed_receipt))
        self.assertEqual(ENGINE_VERSION, first_contract.engine_version)

    def test_manifest_integer_keys_are_canonical_and_dlp_safe(self):
        synthetic_integer = int("110105" + "194912310021")
        encoded = _encode_manifest_integer_key(synthetic_integer)
        self.assertRegex(encoded, r"^u64:[0-9a-f]{16}$")
        self.assertIsNone(
            re.search(
                r"(?<![A-Za-z0-9])[1-8]\d{5}(?:19|20)\d{2}"
                r"(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]"
                r"(?![A-Za-z0-9])",
                encoded,
            )
        )

    def test_single_thread_candidate_bytes_are_reproducible(self):
        first_contract, first_receipt = self._build()
        second_contract = self._contract(self.root / "deterministic-vector-data")
        _, second_receipt = self._build(second_contract)

        self.assertEqual(1, INDEX_BUILD_THREADS)
        self.assertEqual(first_receipt.manifest_sha256, second_receipt.manifest_sha256)
        for relative in (
            "chunk-vectors/index.usearch",
            "entity-vectors/index.usearch",
            "local_vector_manifest.json",
        ):
            self.assertEqual(
                (first_receipt.release_dir / relative).read_bytes(),
                (second_receipt.release_dir / relative).read_bytes(),
            )

    def test_partial_ids_duplicate_ids_dimension_and_metadata_overreach_fail(self):
        adapter = LocalVectorStoreAdapter(self._contract())
        chunks, entities = self._records()
        cases = (
            {
                "chunk_records": chunks[:1],
                "entity_records": entities,
                "expected_ids": {
                    "chunk": ("chunk-a", "chunk-b"),
                    "entity": ("entity-a",),
                },
            },
            {
                "chunk_records": (chunks[0], chunks[0]),
                "entity_records": entities,
                "expected_ids": {
                    "chunk": ("chunk-a",),
                    "entity": ("entity-a",),
                },
            },
            {
                "chunk_records": (
                    VectorRecord("chunk-a", (1.0, 0.0), {"document_id": "doc-a"}),
                ),
                "entity_records": entities,
                "expected_ids": {
                    "chunk": ("chunk-a",),
                    "entity": ("entity-a",),
                },
            },
            {
                "chunk_records": (
                    VectorRecord(
                        "chunk-a",
                        (1.0, 0.0, 0.0),
                        {"document_id": "doc-a", "text": "forbidden"},
                    ),
                ),
                "entity_records": entities,
                "expected_ids": {
                    "chunk": ("chunk-a",),
                    "entity": ("entity-a",),
                },
            },
        )
        for index, case in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(LocalVectorIntegrityError):
                    adapter.build_candidate(**case)
                self.assertFalse(self._contract().candidate_release_dir.exists())

    def test_active_must_be_read_only_and_identity_metric_schema_must_match(self):
        contract, receipt = self._build()
        active = contract.active_release_dir
        active.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(receipt.release_dir, active)
        with self.assertRaises(LocalVectorIntegrityError):
            LocalVectorStoreAdapter(contract).open_active(
                expected_manifest_sha256=receipt.manifest_sha256
            )

        for path in sorted(active.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            path.chmod(0o555 if path.is_dir() else 0o444)
        active.chmod(0o555)
        for changes in (
            {"dimension": 4},
            {"metric": "dot"},
            {"schema_version": "other-schema"},
            {"embedding_identity_sha256": "b" * 64},
        ):
            with self.subTest(changes=changes):
                mismatched = self._contract(**changes)
                with self.assertRaises(LocalVectorIntegrityError):
                    LocalVectorStoreAdapter(mismatched).open_active(
                        expected_manifest_sha256=receipt.manifest_sha256
                    )

    def test_manifest_unknown_or_cross_release_key_is_rejected(self):
        contract, receipt = self._build()
        active = self._activate_read_only(contract, receipt)
        manifest_path = active / "local_vector_manifest.json"
        manifest_path.chmod(0o644)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["indexes"]["chunk"]["objects"][0]["object_id"] = "unknown-object"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        manifest_path.chmod(0o444)

        with self.assertRaises(LocalVectorIntegrityError):
            LocalVectorStoreAdapter(contract).open_active(
                expected_manifest_sha256=receipt.manifest_sha256
            )
        tampered_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        with self.assertRaises(LocalVectorIntegrityError):
            LocalVectorStoreAdapter(contract).open_active(
                expected_manifest_sha256=tampered_sha256
            )

    def test_metadata_filter_is_allowlisted_and_top_k_is_bounded(self):
        contract, receipt = self._build()
        self._activate_read_only(contract, receipt)
        view = LocalVectorStoreAdapter(contract).open_active(
            expected_manifest_sha256=receipt.manifest_sha256
        )
        with self.assertRaises(LocalVectorIntegrityError):
            view.query_chunk(
                (1.0, 0.0, 0.0), top_k=1, metadata_filter={"text": "forbidden"}
            )
        with self.assertRaises(LocalVectorIntegrityError):
            view.query_chunk((1.0, 0.0, 0.0), top_k=6)
        with self.assertRaises(LocalVectorIntegrityError):
            view.query_chunk((1.0, 0.0), top_k=1)

        view.close()
        view.close()
        self.assertTrue(view.closed)
        with self.assertRaisesRegex(LocalVectorIntegrityError, "read view is closed"):
            view.query_chunk((1.0, 0.0, 0.0), top_k=1)

    def test_data_root_must_be_below_an_explicit_approved_parent(self):
        with self.assertRaises(ValueError):
            self._contract(data_root=self.root)
        with self.assertRaises(ValueError):
            self._contract(data_root=self.root.parent / "outside-vector-data")

    def test_allowlist_is_deep_frozen_after_contract_creation(self):
        allowlist = {
            "chunk": ["document_id"],
            "entity": ["entity_type"],
        }
        contract = self._contract(metadata_allowlist=allowlist)
        before = contract.identity_manifest()
        allowlist["chunk"].append("text")

        self.assertEqual(before, contract.identity_manifest())
        self.assertEqual(("document_id",), tuple(contract.metadata_allowlist["chunk"]))

    def test_exact_delete_plan_never_executes_and_refuses_current_active(self):
        contract, receipt = self._build()
        adapter = LocalVectorStoreAdapter(contract)
        plan = adapter.plan_exact_release_delete(
            layout="candidate", data_release_id=contract.data_release_id
        )

        self.assertEqual(receipt.release_dir, plan.release_dir)
        self.assertTrue(plan.release_dir.exists())
        self.assertFalse(plan.as_dict()["execution_authorized"])
        self.assertTrue(plan.entries)
        self.assertTrue(
            all("*" not in str(item.path) and "?" not in str(item.path) for item in plan.entries)
        )

        self._activate_read_only(contract, receipt)
        state_path = self._write_active_state(contract, receipt)
        with self.assertRaises(LocalVectorError):
            adapter.plan_exact_release_delete(
                layout="active",
                data_release_id=contract.data_release_id,
            )

        state_path.chmod(0o644)
        with self.assertRaises(LocalVectorIntegrityError):
            adapter.plan_exact_release_delete(
                layout="active",
                data_release_id=contract.data_release_id,
            )


if __name__ == "__main__":
    unittest.main()
