from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from rag_store.query_trace import QueryTraceLogger, TraceIntegrityError, verify_trace_bytes
from scripts import rotate_query_traces


REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_ROOT = REPO_ROOT / "deploy"
ROTATION_SCRIPT = DEPLOY_ROOT / "scripts" / "rotate_query_traces.py"


class RotateQueryTraceIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.eval_dir = self.root / "eval"
        self.archive_dir = self.eval_dir / "trace_archive"
        self.eval_dir.mkdir(mode=0o700)
        self.live = self.eval_dir / "query_traces.jsonl"
        self.previous_enabled = os.environ.get("RAG_TRACE_ENABLED")
        os.environ["RAG_TRACE_ENABLED"] = "1"

    def tearDown(self) -> None:
        if self.previous_enabled is None:
            os.environ.pop("RAG_TRACE_ENABLED", None)
        else:
            os.environ["RAG_TRACE_ENABLED"] = self.previous_enabled
        self.temporary.cleanup()

    def rotate(self, **overrides: object) -> dict[str, object]:
        options: dict[str, object] = {
            "max_mb": 0,
            "keep_lines": 2,
            "keep_archives": 12,
            "dry_run": False,
        }
        options.update(overrides)
        return rotate_query_traces.rotate(
            self.live,
            self.archive_dir,
            **options,
        )

    def test_rotation_archives_exact_bytes_and_writes_a_new_anchor_chain(self) -> None:
        logger = QueryTraceLogger(self.live)
        for index in range(5):
            logger.record({"trace_id": f"trace-{index}", "public_value": index})
        old_bytes = self.live.read_bytes()
        self.archive_dir.mkdir(mode=0o700)
        old_archives = [
            self.archive_dir / "query_traces.jsonl.20200101_000000_000000001.jsonl.gz",
            self.archive_dir / "query_traces.jsonl.20200101_000000_000000002.jsonl.gz",
        ]
        for old_archive in old_archives:
            old_archive.write_bytes(b"old archive")
            old_archive.chmod(0o600)

        result = self.rotate()
        self.assertEqual(result["status"], "rotated")
        self.assertFalse(result["archive_pruning_enabled"])
        self.assertTrue(all(old_archive.exists() for old_archive in old_archives))
        archive = Path(str(result["archive"]))
        archived_bytes = gzip.decompress(archive.read_bytes())
        self.assertEqual(archived_bytes, old_bytes)
        verify_trace_bytes(archived_bytes)

        state = verify_trace_bytes(self.live.read_bytes())
        self.assertEqual(state.line_count, 3)
        self.assertEqual(
            [record["integrity"]["sequence"] for record in state.records],
            [1, 2, 3],
        )
        anchor = state.records[0]
        self.assertEqual(anchor["event_type"], "trace_rotation_anchor")
        self.assertEqual(anchor["archive_name"], archive.name)
        self.assertEqual(anchor["archive_content_sha256"], hashlib.sha256(old_bytes).hexdigest())
        self.assertEqual(anchor["archive_gzip_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(anchor["archived_last_sequence"], 5)
        self.assertEqual(anchor["retained_record_count"], 2)
        self.assertEqual(
            [record["public_value"] for record in state.records[1:]],
            [3, 4],
        )
        self.assertEqual(self.live.stat().st_mode & 0o777, 0o600)
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.live.stat().st_nlink, 1)
        self.assertEqual(archive.stat().st_nlink, 1)

        pruned = self.rotate(
            keep_lines=1,
            keep_archives=1,
            prune_old_archives=True,
        )
        self.assertTrue(pruned["archive_pruning_enabled"])
        archives = [
            path
            for path in self.archive_dir.iterdir()
            if path.name.startswith("query_traces.jsonl.")
            and path.name.endswith(".jsonl.gz")
        ]
        self.assertEqual(len(archives), 1)

    def test_rotation_refuses_corruption_without_replacing_or_archiving(self) -> None:
        QueryTraceLogger(self.live).record({"trace_id": "trace-one", "value": "one"})
        tampered = self.live.read_bytes().replace(b'"value":"one"', b'"value":"ONE"', 1)
        self.live.write_bytes(tampered)
        original_stat = self.live.stat()

        with self.assertRaises(TraceIntegrityError):
            self.rotate(keep_lines=1)
        self.assertEqual(self.live.read_bytes(), tampered)
        self.assertEqual(self.live.stat().st_ino, original_stat.st_ino)
        self.assertFalse(self.archive_dir.exists())

    def test_below_threshold_still_refuses_corruption(self) -> None:
        QueryTraceLogger(self.live).record({"trace_id": "trace-one", "value": "one"})
        tampered = self.live.read_bytes().replace(b'"value":"one"', b'"value":"ONE"', 1)
        self.live.write_bytes(tampered)
        original_stat = self.live.stat()

        with self.assertRaises(TraceIntegrityError):
            self.rotate(max_mb=20, keep_lines=1)
        self.assertEqual(self.live.read_bytes(), tampered)
        self.assertEqual(self.live.stat().st_ino, original_stat.st_ino)
        self.assertFalse(self.archive_dir.exists())

    def test_dry_run_verifies_but_does_not_rotate(self) -> None:
        QueryTraceLogger(self.live).record({"trace_id": "trace-one"})
        original = self.live.read_bytes()
        original_stat = self.live.stat()
        result = self.rotate(keep_lines=1, dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(self.live.read_bytes(), original)
        self.assertEqual(self.live.stat().st_ino, original_stat.st_ino)
        self.assertFalse(self.archive_dir.exists())

    def test_rotation_and_concurrent_process_share_a_lock_without_lost_records(self) -> None:
        logger = QueryTraceLogger(self.live)
        for index in range(8):
            logger.record({"kind": "initial", "record_id": index})

        marker = self.root / "writer-started"
        code = """
import sys
import time
from pathlib import Path
from rag_store.query_trace import QueryTraceLogger
logger = QueryTraceLogger(sys.argv[1])
marker = Path(sys.argv[2])
for index in range(20):
    logger.record({"kind": "concurrent", "record_id": index})
    if index == 0:
        marker.touch()
    time.sleep(0.005)
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = (
            str(DEPLOY_ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
        )
        writer = subprocess.Popen(
            [sys.executable, "-c", code, str(self.live), str(marker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertTrue(marker.exists())
        result = self.rotate(keep_lines=4)
        stdout, stderr = writer.communicate(timeout=30)
        self.assertEqual(writer.returncode, 0, f"stdout={stdout}\nstderr={stderr}")

        archive_state = verify_trace_bytes(
            gzip.decompress(Path(str(result["archive"])).read_bytes())
        )
        live_state = verify_trace_bytes(self.live.read_bytes())
        archived_ids = {
            record["record_id"]
            for record in archive_state.records
            if record.get("kind") == "concurrent"
        }
        live_ids = {
            record["record_id"]
            for record in live_state.records
            if record.get("kind") == "concurrent"
        }
        self.assertEqual(archived_ids | live_ids, set(range(20)))
        self.assertEqual(live_state.records[0]["event_type"], "trace_rotation_anchor")
        self.assertEqual(
            [record["integrity"]["sequence"] for record in live_state.records],
            list(range(1, live_state.line_count + 1)),
        )

    def test_explicit_rotation_migrates_a_strict_legacy_prefix(self) -> None:
        legacy = b'{"trace_id": "legacy-one"}\n{"trace_id": "legacy-two"}\n'
        self.live.write_bytes(legacy)
        self.live.chmod(0o600)
        result = self.rotate(keep_lines=1)
        state = verify_trace_bytes(self.live.read_bytes())
        self.assertEqual(state.records[0]["archived_legacy_count"], 2)
        self.assertEqual(state.records[1]["trace_id"], "legacy-two")
        self.assertEqual(
            gzip.decompress(Path(str(result["archive"])).read_bytes()),
            legacy,
        )

    def test_cli_requires_paths_and_rotates_only_explicit_target(self) -> None:
        missing = subprocess.run(
            [sys.executable, str(ROTATION_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("--trace", missing.stderr)
        self.assertIn("--archive-dir", missing.stderr)

        QueryTraceLogger(self.live).record({"trace_id": "cli-trace"})
        completed = subprocess.run(
            [
                sys.executable,
                str(ROTATION_SCRIPT),
                "--trace",
                str(self.live),
                "--archive-dir",
                str(self.archive_dir),
                "--max-mb",
                "0",
                "--keep-lines",
                "0",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "rotated")
        self.assertEqual(Path(result["trace"]), self.live)
        self.assertEqual(Path(result["archive"]).parent, self.archive_dir)

        noncanonical = subprocess.run(
            [
                sys.executable,
                str(ROTATION_SCRIPT),
                "--trace",
                f"{self.eval_dir}/./{self.live.name}",
                "--archive-dir",
                str(self.archive_dir),
                "--max-mb",
                "0",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(noncanonical.returncode, 2)
        self.assertIn("canonical absolute path", noncanonical.stderr)

    def test_rotation_rejects_symlink_and_hardlink_live_targets(self) -> None:
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind), TemporaryDirectory(dir=self.root) as case_dir:
                case_root = Path(case_dir)
                target = case_root / "target.jsonl"
                live = case_root / "query_traces.jsonl"
                archive_dir = case_root / "archive"
                original = b"target-must-stay-unchanged\n"
                target.write_bytes(original)
                original_mode = target.stat().st_mode
                if kind == "symlink":
                    live.symlink_to(target)
                else:
                    os.link(target, live)

                with self.assertRaises(TraceIntegrityError):
                    rotate_query_traces.rotate(
                        live,
                        archive_dir,
                        max_mb=0,
                        keep_lines=0,
                        keep_archives=1,
                        dry_run=False,
                    )
                self.assertEqual(target.read_bytes(), original)
                self.assertEqual(target.stat().st_mode, original_mode)
                self.assertFalse(archive_dir.exists())

    def test_rotation_rejects_parent_symlinks_for_live_and_archive_paths(self) -> None:
        real_live_parent = self.root / "real-live-parent"
        real_live_parent.mkdir(mode=0o700)
        real_live = real_live_parent / "query_traces.jsonl"
        QueryTraceLogger(real_live).record({"trace_id": "live-parent-check"})
        linked_live_parent = self.root / "linked-live-parent"
        linked_live_parent.symlink_to(real_live_parent, target_is_directory=True)

        with self.assertRaises(TraceIntegrityError):
            rotate_query_traces.rotate(
                linked_live_parent / real_live.name,
                self.archive_dir,
                max_mb=0,
                keep_lines=0,
                keep_archives=1,
                dry_run=False,
            )
        self.assertFalse(self.archive_dir.exists())

        QueryTraceLogger(self.live).record({"trace_id": "archive-parent-check"})
        original_live = self.live.read_bytes()
        real_archive_parent = self.root / "real-archive-parent"
        real_archive_parent.mkdir(mode=0o700)
        linked_archive_parent = self.root / "linked-archive-parent"
        linked_archive_parent.symlink_to(real_archive_parent, target_is_directory=True)

        with self.assertRaises(TraceIntegrityError):
            rotate_query_traces.rotate(
                self.live,
                linked_archive_parent / "archive",
                max_mb=0,
                keep_lines=0,
                keep_archives=1,
                dry_run=False,
            )
        self.assertEqual(self.live.read_bytes(), original_live)
        self.assertEqual(list(real_archive_parent.iterdir()), [])

    def test_rotation_rejects_noncanonical_raw_paths(self) -> None:
        QueryTraceLogger(self.live).record({"trace_id": "canonical-live"})
        original_live = self.live.read_bytes()

        with self.assertRaises(TraceIntegrityError):
            rotate_query_traces.rotate(
                f"{self.eval_dir}/./{self.live.name}",
                self.archive_dir,
                max_mb=0,
                keep_lines=0,
                keep_archives=1,
                dry_run=False,
            )
        with self.assertRaises(TraceIntegrityError):
            rotate_query_traces.rotate(
                self.live,
                f"{self.eval_dir}/./{self.archive_dir.name}",
                max_mb=0,
                keep_lines=0,
                keep_archives=1,
                dry_run=False,
            )
        self.assertEqual(self.live.read_bytes(), original_live)
        self.assertFalse(self.archive_dir.exists())

    def test_rotation_rejects_insecure_live_lock_archive_and_directory_modes(self) -> None:
        QueryTraceLogger(self.live).record({"trace_id": "secure-live"})
        original_live = self.live.read_bytes()

        self.live.chmod(0o660)
        with self.assertRaisesRegex(TraceIntegrityError, "group or other"):
            self.rotate()
        self.assertEqual(self.live.read_bytes(), original_live)
        self.live.chmod(0o600)

        lock_path = Path(f"{self.live}.lock")
        lock_path.chmod(0o666)
        with self.assertRaisesRegex(TraceIntegrityError, "group or other"):
            self.rotate()
        lock_path.chmod(0o600)

        self.archive_dir.mkdir(mode=0o755)
        with self.assertRaisesRegex(TraceIntegrityError, "private directory"):
            self.rotate()
        self.assertEqual(self.live.read_bytes(), original_live)
        self.archive_dir.chmod(0o700)

        insecure_archive = (
            self.archive_dir
            / "query_traces.jsonl.20200101_000000_000000001.jsonl.gz"
        )
        insecure_archive.write_bytes(b"untrusted archive")
        insecure_archive.chmod(0o644)
        with self.assertRaisesRegex(TraceIntegrityError, "group or other"):
            self.rotate()
        self.assertEqual(self.live.read_bytes(), original_live)

    def test_rotation_dirfd_prevents_parent_replacement_redirection(self) -> None:
        QueryTraceLogger(self.live).record({"trace_id": "before-rotation"})
        moved_eval = self.root / "eval-original"
        attacker_eval = self.root / "eval-attacker"
        attacker_eval.mkdir(mode=0o700)
        attacker_live = attacker_eval / self.live.name
        attacker_live.write_bytes(b"")
        attacker_live.chmod(0o600)
        original_atomic_write = rotate_query_traces._atomic_write
        swapped = False

        def swapping_atomic_write(
            parent_fd,
            name,
            data,
            *,
            replace,
            expected_identity=None,
        ):
            nonlocal swapped
            if replace and not swapped:
                self.eval_dir.rename(moved_eval)
                self.eval_dir.symlink_to(attacker_eval, target_is_directory=True)
                swapped = True
            return original_atomic_write(
                parent_fd,
                name,
                data,
                replace=replace,
                expected_identity=expected_identity,
            )

        with mock.patch.object(
            rotate_query_traces,
            "_atomic_write",
            side_effect=swapping_atomic_write,
        ):
            result = self.rotate(keep_lines=0)

        self.assertEqual(result["status"], "rotated")
        moved_live = moved_eval / self.live.name
        state = verify_trace_bytes(moved_live.read_bytes())
        self.assertEqual(state.records[0]["event_type"], "trace_rotation_anchor")
        self.assertEqual(attacker_live.read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
