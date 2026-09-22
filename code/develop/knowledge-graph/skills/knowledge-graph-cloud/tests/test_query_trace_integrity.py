from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import rag_store.query_trace as query_trace
from rag_store.query_trace import (
    MAX_SAFE_SEQUENCE,
    QueryTraceLogger,
    TraceChainState,
    TraceIntegrityError,
    build_trace_line,
    verify_trace_bytes,
    verify_trace_file,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_ROOT = REPO_ROOT / "deploy"


class QueryTraceIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.path = self.root / "query_traces.jsonl"
        self.previous_enabled = os.environ.get("RAG_TRACE_ENABLED")
        os.environ["RAG_TRACE_ENABLED"] = "1"

    def tearDown(self) -> None:
        if self.previous_enabled is None:
            os.environ.pop("RAG_TRACE_ENABLED", None)
        else:
            os.environ["RAG_TRACE_ENABLED"] = self.previous_enabled
        self.temporary.cleanup()

    def test_records_preserve_public_fields_and_form_a_0600_chain(self) -> None:
        logger = QueryTraceLogger(self.path)
        logger.record({"trace_id": "trace-one", "query": "q" * 600, "route": "rag"})
        logger.record({"trace_id": "trace-two", "source_count": 3})

        state = verify_trace_file(self.path)
        self.assertEqual(state.line_count, 2)
        self.assertEqual(state.last_sequence, 2)
        first, second = state.records
        self.assertEqual(first["trace_id"], "trace-one")
        self.assertEqual(first["route"], "rag")
        self.assertEqual(len(first["query"]), 500)
        self.assertEqual(second["source_count"], 3)
        self.assertEqual(first["integrity"]["sequence"], 1)
        self.assertEqual(second["integrity"]["sequence"], 2)
        first_line = self.path.read_bytes().splitlines(keepends=True)[0]
        self.assertEqual(
            second["integrity"]["previous_event_sha256"],
            hashlib.sha256(first_line).hexdigest(),
        )
        lock_path = Path(f"{self.path}.lock")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(lock_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)
        self.assertEqual(lock_path.stat().st_nlink, 1)

    def test_flock_serializes_concurrent_processes(self) -> None:
        code = """
import sys
from rag_store.query_trace import QueryTraceLogger
logger = QueryTraceLogger(sys.argv[1])
worker = int(sys.argv[2])
for index in range(4):
    logger.record({"worker": worker, "index": index})
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = (
            str(DEPLOY_ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
        )
        children = [
            subprocess.Popen(
                [sys.executable, "-c", code, str(self.path), str(worker)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            for worker in range(4)
        ]
        completed = [
            (child, *child.communicate(timeout=30))
            for child in children
        ]
        for child, stdout, stderr in completed:
            self.assertEqual(child.returncode, 0, f"stdout={stdout}\nstderr={stderr}")

        state = verify_trace_file(self.path)
        self.assertEqual(state.line_count, 16)
        self.assertEqual(
            [record["integrity"]["sequence"] for record in state.records],
            list(range(1, 17)),
        )
        self.assertEqual(
            {(record["worker"], record["index"]) for record in state.records},
            {(worker, index) for worker in range(4) for index in range(4)},
        )

    def test_legacy_prefix_is_anchored_once_and_never_allowed_after_chain_start(self) -> None:
        legacy = b'{"trace_id": "legacy-untrusted", "route": "rag"}\n'
        self.path.write_bytes(legacy)
        os.chmod(self.path, 0o600)
        with self.assertRaises(TraceIntegrityError):
            verify_trace_file(self.path)

        QueryTraceLogger(self.path).record({"trace_id": "first-chained"})
        data = self.path.read_bytes()
        state = verify_trace_bytes(data)
        self.assertEqual(state.legacy_count, 1)
        self.assertEqual(state.chained_count, 1)
        anchor = state.records[1]["integrity"]
        self.assertEqual(anchor["sequence"], 1)
        self.assertEqual(anchor["legacy_prefix_sha256"], hashlib.sha256(legacy).hexdigest())
        self.assertEqual(anchor["legacy_prefix_size_bytes"], len(legacy))
        with self.assertRaises(TraceIntegrityError):
            verify_trace_bytes(data + b'{"trace_id":"late-legacy"}\n')

    def test_verifier_rejects_structural_and_hash_chain_failures(self) -> None:
        logger = QueryTraceLogger(self.path)
        for value in ("one", "two", "three"):
            logger.record({"trace_id": value, "value": value})
        data = self.path.read_bytes()
        lines = data.splitlines(keepends=True)
        variants = {
            "tamper": data.replace(b'"value":"one"', b'"value":"ONE"', 1),
            "reorder": lines[1] + lines[0] + lines[2],
            "middle deletion": lines[0] + lines[2],
            "partial": data[:-1],
            "noncanonical": b" " + data,
            "duplicate key": lines[0].replace(b"{", b'{"value":"duplicate",', 1),
            "legacy nonfinite": b'{"value":NaN}\n',
            "legacy overflow": b'{"value":1e400}\n',
        }
        for label, variant in variants.items():
            with self.subTest(label=label), self.assertRaises(TraceIntegrityError):
                verify_trace_bytes(variant, require_chain=label != "legacy nonfinite")

        with mock.patch.object(query_trace, "MAX_TRACE_BYTES", 64):
            with self.assertRaises(TraceIntegrityError) as raised:
                verify_trace_bytes(b"x" * 65)
            self.assertEqual(raised.exception.code, "EFBIG")

    def test_append_refuses_to_create_an_oversized_unverifiable_trace(self) -> None:
        with mock.patch.object(query_trace, "MAX_TRACE_BYTES", 64):
            with self.assertRaises(TraceIntegrityError) as raised:
                QueryTraceLogger(self.path).record({"payload": "x" * 100})
        self.assertEqual(raised.exception.code, "EFBIG")
        self.assertEqual(self.path.read_bytes(), b"")

    def test_append_refuses_an_exhausted_safe_sequence(self) -> None:
        exhausted = TraceChainState(
            records=(),
            line_count=MAX_SAFE_SEQUENCE,
            chained_count=MAX_SAFE_SEQUENCE,
            legacy_count=0,
            last_sequence=MAX_SAFE_SEQUENCE,
            last_raw_line=b"{}\n",
            legacy_prefix=b"",
        )
        with self.assertRaises(TraceIntegrityError):
            build_trace_line({"trace_id": "must-not-overflow"}, exhausted)

    def test_symlink_is_rejected_without_touching_its_target(self) -> None:
        target = self.root / "target.jsonl"
        target.write_text("target-must-stay-unchanged\n", encoding="utf-8")
        original_mode = target.stat().st_mode
        self.path.symlink_to(target)
        with self.assertRaises((OSError, TraceIntegrityError)):
            QueryTraceLogger(self.path).record({"trace_id": "must-not-write"})
        self.assertEqual(target.read_text(encoding="utf-8"), "target-must-stay-unchanged\n")
        self.assertEqual(target.stat().st_mode, original_mode)
        with self.assertRaises((OSError, TraceIntegrityError)):
            verify_trace_file(self.path, require_chain=False)

    def test_parent_symlink_is_rejected_for_append_and_verification(self) -> None:
        real_parent = self.root / "real-parent"
        real_parent.mkdir(mode=0o700)
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        linked_trace = linked_parent / "query_traces.jsonl"

        with self.assertRaises(TraceIntegrityError):
            QueryTraceLogger(linked_trace).record({"trace_id": "must-not-write"})
        self.assertFalse((real_parent / linked_trace.name).exists())
        self.assertFalse((real_parent / f"{linked_trace.name}.lock").exists())

        real_trace = real_parent / "existing.jsonl"
        QueryTraceLogger(real_trace).record({"trace_id": "canonical-write"})
        with self.assertRaises(TraceIntegrityError):
            verify_trace_file(linked_parent / real_trace.name)

    def test_noncanonical_raw_paths_are_rejected_before_writing(self) -> None:
        filename = "noncanonical-query-traces.jsonl"
        raw_paths = (
            f"{self.root}/./{filename}",
            f"{self.root}//{filename}",
            f"{self.root}/missing/../{filename}",
            filename,
        )

        for raw_path in raw_paths:
            with self.subTest(raw_path=raw_path), self.assertRaises(TraceIntegrityError):
                QueryTraceLogger(raw_path).record({"trace_id": "must-not-write"})
        self.assertFalse((self.root / filename).exists())

    def test_trace_hardlink_is_rejected_without_touching_its_target(self) -> None:
        target = self.root / "hardlink-target.jsonl"
        original = b"hardlink-target-must-stay-unchanged\n"
        target.write_bytes(original)
        original_mode = target.stat().st_mode
        os.link(target, self.path)

        with self.assertRaises(TraceIntegrityError):
            QueryTraceLogger(self.path).record({"trace_id": "must-not-write"})
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(target.stat().st_mode, original_mode)
        with self.assertRaises(TraceIntegrityError):
            verify_trace_file(self.path, require_chain=False)

    def test_lock_hardlink_is_rejected_without_touching_its_target(self) -> None:
        target = self.root / "lock-target"
        original = b"lock-target-must-stay-unchanged\n"
        target.write_bytes(original)
        original_mode = target.stat().st_mode
        os.link(target, Path(f"{self.path}.lock"))

        with self.assertRaises(TraceIntegrityError):
            QueryTraceLogger(self.path).record({"trace_id": "must-not-write"})
        self.assertFalse(self.path.exists())
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(target.stat().st_mode, original_mode)

    def test_insecure_trace_lock_and_parent_permissions_fail_closed(self) -> None:
        logger = QueryTraceLogger(self.path)
        logger.record({"trace_id": "secure-baseline"})
        original = self.path.read_bytes()
        os.chmod(self.path, 0o660)
        with self.assertRaisesRegex(TraceIntegrityError, "group or other"):
            logger.record({"trace_id": "must-not-append"})
        with self.assertRaisesRegex(TraceIntegrityError, "group or other"):
            verify_trace_file(self.path)
        self.assertEqual(original, self.path.read_bytes())
        os.chmod(self.path, 0o600)

        lock_path = Path(f"{self.path}.lock")
        os.chmod(lock_path, 0o666)
        with self.assertRaisesRegex(TraceIntegrityError, "group or other"):
            logger.record({"trace_id": "must-not-use-insecure-lock"})

        insecure_parent = self.root / "insecure-parent"
        insecure_parent.mkdir(mode=0o755)
        insecure_trace = insecure_parent / "trace.jsonl"
        with self.assertRaisesRegex(TraceIntegrityError, "private directory"):
            QueryTraceLogger(insecure_trace).record({"trace_id": "must-not-write"})
        self.assertFalse(insecure_trace.exists())

    def test_private_path_gates_reject_a_different_owner(self) -> None:
        QueryTraceLogger(self.path).record({"trace_id": "owner-check"})
        different_uid = os.geteuid() + 1

        with mock.patch.object(query_trace.os, "geteuid", return_value=different_uid):
            with self.assertRaisesRegex(TraceIntegrityError, "current euid"):
                verify_trace_file(self.path)

    def test_held_parent_fd_prevents_parent_symlink_redirection(self) -> None:
        parent = self.root / "held-parent"
        parent.mkdir(mode=0o700)
        trace = parent / "trace.jsonl"
        moved_parent = self.root / "held-parent-original"
        attacker_parent = self.root / "attacker-parent"
        attacker_parent.mkdir(mode=0o700)
        attacker_trace = attacker_parent / trace.name
        attacker_trace.write_bytes(b"")
        os.chmod(attacker_trace, 0o600)
        original_lock = query_trace.trace_file_lock
        swapped = False

        @contextmanager
        def swapping_lock(path, *, create_parent=True):
            nonlocal swapped
            with original_lock(path, create_parent=create_parent) as handle:
                if not swapped:
                    parent.rename(moved_parent)
                    parent.symlink_to(attacker_parent, target_is_directory=True)
                    swapped = True
                yield handle

        with mock.patch.object(query_trace, "trace_file_lock", swapping_lock):
            QueryTraceLogger(trace).record({"trace_id": "dirfd-target"})

        self.assertIn(b"dirfd-target", (moved_parent / trace.name).read_bytes())
        self.assertEqual(attacker_trace.read_bytes(), b"")

    def test_cached_append_reverifies_after_external_tamper(self) -> None:
        logger = QueryTraceLogger(self.path)
        logger.record({"trace_id": "trace-one", "value": "one"})
        original_stat = self.path.stat()
        tampered = self.path.read_bytes().replace(b'"value":"one"', b'"value":"ONE"', 1)
        self.assertNotEqual(tampered, self.path.read_bytes())
        self.path.write_bytes(tampered)
        os.utime(
            self.path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        with self.assertRaises(TraceIntegrityError):
            logger.record({"trace_id": "must-not-append"})
        self.assertNotIn(b"must-not-append", self.path.read_bytes())

    def test_append_detects_leaf_replacement_after_final_prewrite_check(self) -> None:
        logger = QueryTraceLogger(self.path)
        logger.record({"trace_id": "baseline"})
        detached = self.root / "detached.jsonl"
        original_write_all = query_trace._write_all
        swapped = False

        def replace_leaf_then_write(descriptor, data):
            nonlocal swapped
            if not swapped:
                self.path.rename(detached)
                self.path.write_bytes(b'{"forged":true}\n')
                os.chmod(self.path, 0o600)
                swapped = True
            original_write_all(descriptor, data)

        with mock.patch.object(query_trace, "_write_all", replace_leaf_then_write):
            with self.assertRaisesRegex(TraceIntegrityError, "identity changed"):
                logger.record({"trace_id": "must-fail-closed"})

        self.assertEqual(b'{"forged":true}\n', self.path.read_bytes())
        self.assertIn(b"must-fail-closed", detached.read_bytes())

    def test_append_detects_lock_leaf_replacement_while_held(self) -> None:
        logger = QueryTraceLogger(self.path)
        logger.record({"trace_id": "baseline"})
        lock_path = Path(f"{self.path}.lock")
        detached_lock = self.root / "detached.lock"
        original_write_all = query_trace._write_all
        swapped = False

        def replace_lock_then_write(descriptor, data):
            nonlocal swapped
            if not swapped:
                lock_path.rename(detached_lock)
                lock_path.write_bytes(b"")
                os.chmod(lock_path, 0o600)
                swapped = True
            original_write_all(descriptor, data)

        with mock.patch.object(query_trace, "_write_all", replace_lock_then_write):
            with self.assertRaisesRegex(TraceIntegrityError, "lock identity changed"):
                logger.record({"trace_id": "lock-replaced"})

        self.assertIn(b"lock-replaced", self.path.read_bytes())
        self.assertEqual(b"", lock_path.read_bytes())

    def test_canonical_verifier_rejects_noncanonical_but_valid_json(self) -> None:
        QueryTraceLogger(self.path).record({"trace_id": "canonical"})
        record = json.loads(self.path.read_text(encoding="utf-8"))
        noncanonical = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode()
        with self.assertRaises(TraceIntegrityError):
            verify_trace_bytes(noncanonical)


if __name__ == "__main__":
    unittest.main()
