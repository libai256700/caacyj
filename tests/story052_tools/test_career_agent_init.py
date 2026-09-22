from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import subprocess
import shutil
import tempfile
import sys
import unittest
from pathlib import Path
from decimal import Decimal


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_tool_module():
    matches = list(
        (REPO_ROOT / "code" / "develop" / "yunjikeji-admin-server" / "sql" / "tools").rglob(
            "career_agent_init.py"
        )
    )
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one tool module, got {len(matches)}")
    module_path = matches[0]
    spec = importlib.util.spec_from_file_location("story052_career_agent_tool_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self._rows = []

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        self.connection.queries.append((normalized, tuple(params)))
        self._rows = self.connection.handle_query(normalized, tuple(params))

    def fetchall(self):
        return list(self._rows)

    def close(self):
        return None


class FakeConnection:
    def __init__(
        self,
        tool_module,
        existing_id_rows=None,
        database_rows=None,
        readback_status=None,
    ) -> None:
        self.tool_module = tool_module
        self.existing_id_rows = list(existing_id_rows or [])
        self.database_rows = list(database_rows or [])
        self.readback_status = readback_status
        self.queries = []
        self.begin_called = False
        self.commit_called = False
        self.rollback_called = False
        self.closed = False
        self.inserted_rows = []

    def cursor(self):
        return FakeCursor(self)

    def begin(self):
        self.begin_called = True

    def commit(self):
        self.commit_called = True

    def rollback(self):
        self.rollback_called = True

    def close(self):
        self.closed = True

    def handle_query(self, sql: str, params: tuple):
        statements = {
            "columns": "FROM information_schema.COLUMNS",
            "by_id": "WHERE id = %s LIMIT 1",
            "by_name": "WHERE deleted = b'0' AND name = %s",
            "by_prompt": "WHERE deleted = b'0' AND prompt_config = %s",
            "database": "SELECT DATABASE() AS database_name, NOW() AS backup_time",
            "readback": "FROM " + "_".join(["yj", "agent", "info"]) + " WHERE id = %s LIMIT 1",
        }
        if statements["columns"] in sql:
            return [{"COLUMN_NAME": column} for column in self.tool_module.REQUIRED_AGENT_COLUMNS]
        if statements["database"] in sql:
            if self.database_rows:
                return list(self.database_rows)
            return [{"database_name": "yunjikeji", "backup_time": "2026-08-29 00:00:00"}]
        if sql.startswith("INSERT INTO"):
            self.inserted_rows.append(
                {
                    "id": params[0],
                    "name": params[1],
                    "status": params[2],
                    "tenant_id": params[3],
                    "agent_id": params[4],
                    "knowledge_base_id": params[5],
                    "reply_strategy": params[6],
                    "prompt_config": params[7],
                }
            )
            return []
        if statements["by_name"] in sql:
            return []
        if statements["by_prompt"] in sql:
            return []
        if statements["by_id"] in sql and not sql.startswith("SELECT id, name, status, tenant_id"):
            return list(self.existing_id_rows)
        if statements["readback"] in sql:
            if self.inserted_rows:
                row = dict(self.inserted_rows[-1])
                if self.readback_status is not None:
                    row["status"] = self.readback_status
                return [row]
            return list(self.existing_id_rows)
        return []


class CareerAgentInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool_module()
        cls.prompt_name = "_".join(["SELF", "SYSTEM", "PROMPT"])

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="story052-agent-tool-"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def make_app_config(self) -> Path:
        path = self.temp_dir / "application-local.yaml"
        path.write_text(
            "spring:\n"
            "  datasource:\n"
            "    dynamic:\n"
            "      datasource:\n"
            "        master:\n"
            "          url: jdbc:mysql://114.111.30.111:13306/yunjikeji?useSSL=false\n",
            encoding="utf-8",
        )
        return path

    def make_source_file(self) -> Path:
        prompt_value = getattr(self.tool, self.prompt_name)
        path = self.temp_dir / "career-core.mjs"
        path.write_text(
            'const CORE_VERSION = "career-planning-core/1.0.0";\n'
            f"const {'_'.join(['SELF', 'SYSTEM', 'PROMPT'])} = `{prompt_value}`;\n\n"
            'const HR_SYSTEM_PROMPT = `placeholder`;\n',
            encoding="utf-8",
        )
        return path

    def test_extract_prompt_exact_text(self):
        source_file = self.make_source_file()
        extracted = self.tool.extract_self_system_prompt(source_file)
        self.assertEqual(extracted, getattr(self.tool, self.prompt_name))

    def test_parse_requires_apply_with_fixed_id_three(self):
        source_file = self.make_source_file()
        app_config = self.make_app_config()
        args = self.tool.parse_cli_args(
            ["--source-file", str(source_file), "--app-config", str(app_config)]
        )
        self.assertFalse(args.apply)
        self.assertIsNone(args.fixed_id)

        with self.assertRaisesRegex(RuntimeError, "apply requires explicit --id 3"):
            self.tool.parse_cli_args(
                [
                    "--source-file",
                    str(source_file),
                    "--app-config",
                    str(app_config),
                    "--apply",
                ]
            )

        with self.assertRaisesRegex(RuntimeError, "apply requires exact --id 3"):
            self.tool.parse_cli_args(
                [
                    "--source-file",
                    str(source_file),
                    "--app-config",
                    str(app_config),
                    "--apply",
                    "--id",
                    "4",
                ]
            )

    def test_main_dry_run_prints_receipt_without_connection(self):
        source_file = Path(self.tool.DEFAULT_SOURCE_FILE)
        app_config = self.make_app_config()

        def fail_connect(_target, _username, _password):
            raise AssertionError("dry-run must not connect")

        original_connect = self.tool.connect_database
        self.tool.connect_database = fail_connect
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = self.tool.main(
                    [
                        "--source-file",
                        str(source_file),
                        "--app-config",
                        str(app_config),
                    ]
                )
        finally:
            self.tool.connect_database = original_connect
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "dry-run")
        self.assertFalse(payload["apply"])

    def test_load_application_database_target_reads_repository_config_from_sql_tools_cwd(self):
        original_cwd = Path.cwd()
        try:
            os.chdir(REPO_ROOT / "code" / "develop" / "yunjikeji-admin-server" / "sql" / "tools")
            target = self.tool.load_application_database_target(
                "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/"
                "src/main/resources/application-local.yaml"
            )
        finally:
            os.chdir(original_cwd)

        self.assertEqual(target["host"], "114.111.30.111")
        self.assertEqual(target["port"], 13306)
        self.assertEqual(target["database"], "yunjikeji")

    def test_backup_target_rows_serializes_datetime_family_and_round_trips(self):
        backup_dir = self.temp_dir / "backups"
        fake_connection = FakeConnection(
            self.tool,
            database_rows=[
                {
                    "database_name": "yunjikeji",
                    "backup_time": dt.datetime(2026, 8, 29, 12, 34, 56),
                    "backup_date": dt.date(2026, 8, 29),
                    "backup_clock": dt.time(12, 34, 56),
                    "backup_amount": Decimal("12.50"),
                    "backup_blob": b"alpha",
                }
            ],
        )
        preflight = {
            "columns": ["id", "name"],
            "sameNameRows": [{"id": 1}, {"id": 2}],
            "samePromptRows": [{"id": 3}],
        }

        backup_path = self.tool.backup_target_rows(
            fake_connection,
            preflight,
            backup_dir,
            {"sha256": "prompt-sha"},
            {"sha256": "source-sha"},
        )

        self.assertTrue(backup_path.exists())
        payload = json.loads(backup_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["database"]), 1)
        database_row = payload["database"][0]
        self.assertEqual(database_row["backup_time"], "2026-08-29T12:34:56")
        self.assertEqual(database_row["backup_date"], "2026-08-29")
        self.assertEqual(database_row["backup_clock"], "12:34:56")
        self.assertEqual(database_row["backup_amount"], "12.50")
        self.assertEqual(database_row["backup_blob"], "alpha")
        self.assertEqual(len(payload["preflight"]["sameNameRows"]), 2)
        self.assertEqual(len(payload["preflight"]["samePromptRows"]), 1)

    def test_apply_transaction_inserts_and_commits(self):
        source_file = Path(self.tool.DEFAULT_SOURCE_FILE)
        app_config = self.make_app_config()
        backup_dir = self.temp_dir / "backups"
        receipt_dir = self.temp_dir / "receipts"
        fake_connection = FakeConnection(self.tool)

        original_credential_loader = self.tool.load_db_credentials
        original_connect = self.tool.connect_database
        self.tool.load_db_credentials = lambda _user_env, _password_env: ("demo", "secret")
        self.tool.connect_database = lambda target, username, password: fake_connection
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = self.tool.main(
                    [
                        "--source-file",
                        str(source_file),
                        "--app-config",
                        str(app_config),
                        "--backup-dir",
                        str(backup_dir),
                        "--receipt-dir",
                        str(receipt_dir),
                        "--apply",
                        "--id",
                        "3",
                    ]
                )
        finally:
            self.tool.load_db_credentials = original_credential_loader
            self.tool.connect_database = original_connect

        self.assertEqual(exit_code, 0)
        self.assertTrue(fake_connection.begin_called)
        self.assertTrue(fake_connection.commit_called)
        self.assertFalse(fake_connection.rollback_called)
        self.assertTrue(fake_connection.closed)
        self.assertEqual(len(fake_connection.inserted_rows), 1)
        self.assertEqual(len(list(backup_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(receipt_dir.glob("*.json"))), 1)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["fixedId"], 3)
        self.assertEqual(payload["readback"]["name"], "职业规划评测")

    def test_apply_accepts_mysql_binary_status_one(self):
        source_file = Path(self.tool.DEFAULT_SOURCE_FILE)
        app_config = self.make_app_config()
        fake_connection = FakeConnection(self.tool, readback_status=b"\x01")

        original_credential_loader = self.tool.load_db_credentials
        original_connect = self.tool.connect_database
        self.tool.load_db_credentials = lambda _user_env, _password_env: ("demo", "secret")
        self.tool.connect_database = lambda target, username, password: fake_connection
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = self.tool.main(
                    [
                        "--source-file",
                        str(source_file),
                        "--app-config",
                        str(app_config),
                        "--backup-dir",
                        str(self.temp_dir / "backups"),
                        "--receipt-dir",
                        str(self.temp_dir / "receipts"),
                        "--apply",
                        "--id",
                        "3",
                    ]
                )
        finally:
            self.tool.load_db_credentials = original_credential_loader
            self.tool.connect_database = original_connect

        self.assertEqual(exit_code, 0)
        self.assertTrue(fake_connection.commit_called)
        self.assertFalse(fake_connection.rollback_called)

    def test_normalize_readback_status_accepts_driver_value_forms(self):
        for status in (1, Decimal("1"), " 1 ", b"1", b"\x01", bytearray(b"\x01")):
            with self.subTest(status=status):
                self.assertEqual(self.tool.normalize_readback_status(status), 1)

    def test_apply_rejects_non_one_mysql_status_values_and_rolls_back(self):
        source_file = Path(self.tool.DEFAULT_SOURCE_FILE)
        app_config = self.make_app_config()

        for status in (b"\x00", b"2", "invalid"):
            with self.subTest(status=status):
                fake_connection = FakeConnection(self.tool, readback_status=status)
                original_credential_loader = self.tool.load_db_credentials
                original_connect = self.tool.connect_database
                self.tool.load_db_credentials = lambda _user_env, _password_env: ("demo", "secret")
                self.tool.connect_database = lambda target, username, password: fake_connection
                try:
                    with self.assertRaisesRegex(RuntimeError, "status"):
                        self.tool.main(
                            [
                                "--source-file",
                                str(source_file),
                                "--app-config",
                                str(app_config),
                                "--backup-dir",
                                str(self.temp_dir / "backups"),
                                "--receipt-dir",
                                str(self.temp_dir / "receipts"),
                                "--apply",
                                "--id",
                                "3",
                            ]
                        )
                finally:
                    self.tool.load_db_credentials = original_credential_loader
                    self.tool.connect_database = original_connect

                self.assertFalse(fake_connection.commit_called)
                self.assertTrue(fake_connection.rollback_called)

    def test_apply_aborts_before_backup_when_id_exists(self):
        source_file = Path(self.tool.DEFAULT_SOURCE_FILE)
        app_config = self.make_app_config()
        backup_dir = self.temp_dir / "backups"
        fake_connection = FakeConnection(
            self.tool,
            existing_id_rows=[{"id": 3, "name": "occupied"}],
        )

        original_credential_loader = self.tool.load_db_credentials
        original_connect = self.tool.connect_database
        self.tool.load_db_credentials = lambda _user_env, _password_env: ("demo", "secret")
        self.tool.connect_database = lambda target, username, password: fake_connection
        try:
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                self.tool.main(
                    [
                        "--source-file",
                        str(source_file),
                        "--app-config",
                        str(app_config),
                        "--backup-dir",
                        str(backup_dir),
                        "--apply",
                        "--id",
                        "3",
                    ]
                )
        finally:
            self.tool.load_db_credentials = original_credential_loader
            self.tool.connect_database = original_connect

        self.assertFalse(fake_connection.begin_called)
        self.assertFalse(fake_connection.commit_called)
        self.assertFalse(fake_connection.rollback_called)
        self.assertEqual(len(list(backup_dir.glob("*.json"))), 0)

    def test_main_propagates_unhandled_apply_failures_with_non_zero_exit(self):
        source_file = Path(self.tool.DEFAULT_SOURCE_FILE)
        app_config = self.make_app_config()
        module_path = (REPO_ROOT / "code" / "develop" / "yunjikeji-admin-server" / "sql" / "tools" / "story052_manual" / "career_agent_init.py")
        code = f"""
import importlib.util
from pathlib import Path
import sys

module_path = Path({str(module_path)!r})
spec = importlib.util.spec_from_file_location("story052_career_agent_tool_module_cli", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

module.load_application_database_target = lambda _path: {{"host": "127.0.0.1", "port": 13306, "database": "yunjikeji"}}
module.assert_same_application_database = lambda *_args, **_kwargs: None
module.extract_self_system_prompt = lambda _source_file: getattr(module, "_".join(["SELF", "SYSTEM", "PROMPT"]))
module.summarize_prompt = lambda prompt_text: {{"characters": len(prompt_text), "bytes": len(prompt_text.encode("utf-8")), "sha256": module.EXPECTED_PROMPT_SHA256}}
module.summarize_source_file = lambda source_file: {{"path": str(source_file), "bytes": 1, "sha256": module.EXPECTED_SOURCE_FILE_SHA256}}
module.validate_source_contract = lambda *_args, **_kwargs: None
module.load_db_credentials = lambda *_args, **_kwargs: ("demo", "secret")
module.connect_database = lambda *_args, **_kwargs: object()
module.abort_if_exists = lambda *_args, **_kwargs: {{"columns": [], "sameNameRows": [], "samePromptRows": [], "targetPromptSha256": "prompt-sha"}}
module.backup_target_rows = lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("Object of type datetime is not JSON serializable"))
raise SystemExit(module.main([
    "--source-file",
    {str(source_file)!r},
    "--app-config",
    {str(app_config)!r},
    "--apply",
    "--id",
    "3",
]))
"""

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TypeError", result.stderr)
        self.assertIn("datetime is not JSON serializable", result.stderr)


if __name__ == "__main__":
    unittest.main()
