import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


TOOLS_ROOT = Path(__file__).resolve().parents[3]
MANUAL_ROOT = TOOLS_ROOT / "story052_manual"
QUESTION_FILE = "_".join(["career", "question", "import"]) + ".py"
AGENT_FILE = "_".join(["career", "agent", "init"]) + ".py"


def load_module(file_name: str, module_name: str):
    file_path = MANUAL_ROOT / file_name
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


agent_tool = load_module(AGENT_FILE, "story052_manual_agent_tool")
question_tool = load_module(QUESTION_FILE, "story052_manual_question_tool")


SOURCE_ROOT = Path("D:/飞机") / "-APP--main (4)" / "-APP--main" / "skills" / "-".join(["career", "planning", "coach"])
class Story052CareerManualToolsTest(unittest.TestCase):
    def test_question_rows_match_expected_shape(self) -> None:
        rows = question_tool.build_question_rows(SOURCE_ROOT)

        self.assertEqual(question_tool.EXPECTED_QUESTION_COUNT, len(rows))
        self.assertEqual(question_tool.EXPECTED_ANSWER_COUNT, sum(len(row.options) for row in rows))
        self.assertEqual("name", rows[0].field_key)
        self.assertEqual("values.top3", rows[38].field_key)
        self.assertEqual("weeklyHours", rows[-1].field_key)
        self.assertEqual(["不太想做", "可以尝试", "很想做"], [item.content for item in rows[13].options])
        self.assertEqual(1, [item.question_stem for item in rows].count("姓名"))
        self.assertEqual(
            ["姓名", "年龄段", "最高学历", "专业", "当前岗位", "工作年限", "主要职责"],
            [item.question_stem for item in rows[:7]],
        )
        self.assertEqual(
            [1] * 9 + [2] * 4 + [3] * 13 + [4] * 12 + [5] * 2 + [6] * 7,
            [question_tool.step_sort_no_for_question(item.sort_no) for item in rows],
        )
        self.assertEqual(
            ["基本情况", "经历与成果", "兴趣倾向", "工作风格", "工作价值", "目标计划"],
            [item.step_name for item in question_tool.STEP_ROWS],
        )

    def test_question_default_dry_run_never_connects(self) -> None:
        previous_cwd = Path.cwd()
        try:
            os.chdir(MANUAL_ROOT)
            with patch.object(question_tool, "connect_database", side_effect=AssertionError("must not connect")), \
                    patch.object(question_tool, "load_application_database_credentials", side_effect=AssertionError("must not read credentials")), \
                    redirect_stdout(io.StringIO()):
                result = question_tool.main(["--source-dir", str(SOURCE_ROOT)])
        finally:
            os.chdir(previous_cwd)
        self.assertEqual(0, result)

    def test_question_repair_requires_explicit_apply(self) -> None:
        previous_cwd = Path.cwd()
        try:
            os.chdir(MANUAL_ROOT)
            with self.assertRaisesRegex(RuntimeError, "requires --apply"):
                question_tool.main(["--source-dir", str(SOURCE_ROOT), "--repair-existing"])
        finally:
            os.chdir(previous_cwd)

    def test_question_enabled_status_normalization_is_strict(self) -> None:
        for value in (b"\x01", bytearray(b"\x01"), 1, "1", " 1 "):
            self.assertEqual(1, question_tool.normalize_enabled_status(value))
        for value in (b"\x00", b"2", bytearray(b"\x00"), 0, "disabled"):
            with self.assertRaisesRegex(RuntimeError, "invalid enabled status"):
                question_tool.normalize_enabled_status(value)

    def test_question_apply_connection_uses_config_credentials_without_cli_secrets(self) -> None:
        config_text = """spring:
  datasource:
    url: jdbc:mysql://database.example:13306/yunjikeji?useSSL=false
    username: config-user
    password: config-password
"""

        class FakeDriver:
            class cursors:
                DictCursor = object

            captured: dict = {}

            @classmethod
            def connect(cls, **kwargs):
                cls.captured = kwargs
                return object()

        with tempfile.TemporaryDirectory(prefix="story052-question-config-") as temp_dir:
            config_path = Path(temp_dir) / "application-local.yaml"
            config_path.write_text(config_text, encoding="utf-8")
            args = question_tool.build_parser().parse_args(
                ["--source-dir", str(SOURCE_ROOT), "--app-config", str(config_path), "--apply"]
            )
            target = question_tool.load_application_database_target(config_path)
            with patch.object(question_tool, "load_pymysql", return_value=FakeDriver):
                question_tool.connect_database(target, args)

        self.assertEqual("config-user", FakeDriver.captured["user"])
        self.assertEqual("config-password", FakeDriver.captured["password"])
        self.assertEqual("database.example", FakeDriver.captured["host"])
        self.assertEqual(13306, FakeDriver.captured["port"])
        self.assertEqual("yunjikeji", FakeDriver.captured["database"])
        self.assertNotIn("config-password", json.dumps(target))

    def test_question_cli_user_takes_precedence_over_config_user(self) -> None:
        config_text = """spring:
  datasource:
    url: jdbc:mysql://database.example:13306/yunjikeji
    username: config-user
    password: config-password
"""
        with tempfile.TemporaryDirectory(prefix="story052-question-config-") as temp_dir:
            config_path = Path(temp_dir) / "application-local.yaml"
            config_path.write_text(config_text, encoding="utf-8")
            args = question_tool.build_parser().parse_args(
                [
                    "--source-dir", str(SOURCE_ROOT), "--app-config", str(config_path),
                    "--db-user", "cli-user", "--apply",
                ]
            )
            username, password = question_tool.resolve_database_credentials(args)

        self.assertEqual("cli-user", username)
        self.assertEqual("config-password", password)

    def test_question_credential_errors_do_not_echo_secret_values(self) -> None:
        secret = "not-for-output"
        config_text = f"""spring:
  datasource:
    url: jdbc:mysql://database.example:13306/yunjikeji
    password: {secret}
"""
        with tempfile.TemporaryDirectory(prefix="story052-question-config-") as temp_dir:
            config_path = Path(temp_dir) / "application-local.yaml"
            config_path.write_text(config_text, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "missing database credentials") as error:
                question_tool.load_application_database_credentials(config_path)
        self.assertNotIn(secret, str(error.exception))

    def test_question_cli_database_target_must_be_complete(self) -> None:
        parser = question_tool.build_parser()
        args = parser.parse_args(["--source-dir", str(SOURCE_ROOT), "--db-host", "1.2.3.4"])
        with self.assertRaisesRegex(RuntimeError, "db target requires"):
            question_tool.build_cli_database_target(args)

    def test_question_reports_database_mismatch(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "database mismatch"):
            question_tool.assert_same_application_database(
                {"host": "example.invalid", "port": 3306, "database": "other"},
                {"host": "same", "port": 3306, "database": "same"},
            )

    def test_agent_prompt_extract_and_hash(self) -> None:
        prompt = agent_tool.extract_self_system_prompt("career-core.mjs")
        summary = agent_tool.summarize_prompt(prompt)

        self.assertGreater(summary["characters"], 800)
        self.assertEqual(agent_tool.AGENT_ID, agent_tool.AGENT_ROW["id"])
        self.assertEqual(agent_tool.TENANT_ID, agent_tool.AGENT_ROW["tenant_id"])
        self.assertEqual(agent_tool.EXPECTED_PROMPT_SHA256, summary["sha256"])

    def test_agent_abort_if_exists_raises(self) -> None:
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def execute(self, query, params=None):
                self.query = query

            def fetchall(self):
                if "COLUMN_NAME" in self.query:
                    return [{"COLUMN_NAME": item} for item in agent_tool.REQUIRED_AGENT_COLUMNS]
                if "WHERE id = %s" in self.query:
                    return [{"id": 3}]
                return []

            def close(self):
                return None

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

        with self.assertRaisesRegex(RuntimeError, "id=3"):
            agent_tool.abort_if_exists(FakeConnection(), {"sha256": agent_tool.EXPECTED_PROMPT_SHA256})

    def test_agent_report_writer_emits_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="story052-manual-tools-") as temp_dir:
            path = Path(temp_dir) / "report.json"
            agent_tool.write_json(path, {"mode": "dry-run", "agentId": 3})
            content = path.read_text(encoding="utf-8")

        self.assertIn('"mode": "dry-run"', content)
        self.assertIn('"agentId": 3', content)


if __name__ == "__main__":
    unittest.main()
