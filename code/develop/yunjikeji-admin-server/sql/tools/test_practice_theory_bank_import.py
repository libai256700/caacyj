import tempfile
import unittest
from pathlib import Path

from practice_theory_bank_import import (
    APPLY_CONFIRM_TOKEN,
    DatabaseSnapshot,
    Violation,
    allow_incomplete_questions,
    build_parser,
    ensure_apply_guards,
    fetch_post_apply_stats,
    import_payload,
    parse_markdown_file,
    validate_live_schema,
)


class PracticeTheoryBankImportTest(unittest.TestCase):
    def write_markdown(self, content: str) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="theory-bank-import-"))
        path = temp_dir / "样例分类.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_parse_multiline_stem_and_inline_options(self) -> None:
        path = self.write_markdown(
            """
概述

1.第一行题干
继续补充题干
A.选项甲 B.选项乙
C.选项丙
参考答案：B
解析：第一段
继续解析
""".strip()
        )

        document, violations = parse_markdown_file(path)
        self.assertEqual([], [item.code for item in violations])
        self.assertEqual(1, len(document.questions))
        question = document.questions[0]
        self.assertEqual("第一行题干\n继续补充题干", question.stem())
        self.assertEqual(["A", "B", "C"], question.option_order)
        self.assertEqual("选项甲", question.options["A"].content)
        self.assertEqual("选项乙", question.options["B"].content)
        self.assertEqual("B", question.answer_code)
        self.assertEqual("第一段\n继续解析", question.analysis())

    def test_reject_duplicate_answer_lines(self) -> None:
        path = self.write_markdown(
            """
1.重复答案
A.甲
B.乙
参考答案：A
参考答案：B
""".strip()
        )

        _, violations = parse_markdown_file(path)
        self.assertIn("DUPLICATE_ANSWER_LINE", [item.code for item in violations])

    def test_apply_requires_non_prod_and_confirmation(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--apply",
                "--environment",
                "Test",
                "--import-incomplete-questions",
                "--confirm-apply",
                APPLY_CONFIRM_TOKEN,
            ]
        )
        ensure_apply_guards(args, DatabaseSnapshot(connected=True), [])

        bad_args = parser.parse_args(
            [
                "--apply",
                "--environment",
                "Prod",
                "--import-incomplete-questions",
                "--confirm-apply",
                APPLY_CONFIRM_TOKEN,
            ]
        )
        with self.assertRaisesRegex(RuntimeError, "只允许在 Local/Dev/Test 环境执行"):
            ensure_apply_guards(bad_args, DatabaseSnapshot(connected=True), [])

    def test_import_incomplete_questions_keeps_questions_for_later_maintenance(self) -> None:
        path = self.write_markdown(
            """
1.正常题
A.甲
B.乙
参考答案：A

2.
A.甲
B.乙
参考答案：A
""".strip()
        )
        document, violations = parse_markdown_file(path)

        import_documents, remaining_violations, incomplete_questions = allow_incomplete_questions(
            [document],
            violations,
            import_incomplete_questions=True,
        )

        self.assertEqual([], remaining_violations)
        self.assertEqual(2, len(import_documents[0].questions))
        self.assertEqual(1, len(incomplete_questions))
        self.assertEqual(["MISSING_STEM"], incomplete_questions[0]["reasonCodes"])

    def test_incomplete_answer_keys_are_imported_without_a_correct_option(self) -> None:
        path = self.write_markdown(
            """
1.缺少答案
A.甲
B.乙

2.双答案
A.甲
B.乙
参考答案：A
参考答案：B
""".strip()
        )
        document, violations = parse_markdown_file(path)
        import_documents, remaining_violations, _ = allow_incomplete_questions(
            [document], violations, import_incomplete_questions=True
        )
        self.assertEqual([], remaining_violations)
        snapshot = DatabaseSnapshot(
            connected=True,
            category_matches={"样例分类": [{"id": 1, "category_name": "样例分类"}]},
        )
        payload = import_payload(import_documents, snapshot)
        self.assertEqual([0, 0], [item["isCorrect"] for item in payload[0]["options"]])
        self.assertEqual([0, 0], [item["isCorrect"] for item in payload[1]["options"]])

    def test_analysis_numbered_list_does_not_start_new_question(self) -> None:
        path = self.write_markdown(
            """
1.第一题
A.甲
B.乙
参考答案：A
解析：1、第一条
2、第二条
2.第二题
A.丙
B.丁
参考答案：B
""".strip()
        )

        document, violations = parse_markdown_file(path)

        self.assertEqual([], [item.code for item in violations])
        self.assertEqual(2, len(document.questions))
        self.assertEqual("1、第一条\n2、第二条", document.questions[0].analysis())
        self.assertEqual("B", document.questions[1].answer_code)

    def test_new_section_allows_question_number_reset(self) -> None:
        path = self.write_markdown(
            """
1.第一题
A.甲
B.乙
参考答案：A
解析：说明
【2026年新增真题】
1.第二题
A.丙
B.丁
参考答案：B
""".strip()
        )

        document, violations = parse_markdown_file(path)

        self.assertEqual([], [item.code for item in violations])
        self.assertEqual(2, len(document.questions))
        self.assertEqual("A", document.questions[0].answer_code)
        self.assertEqual("B", document.questions[1].answer_code)

    def test_validate_live_schema_blocks_short_correct_memo(self) -> None:
        snapshot = DatabaseSnapshot(
            connected=True,
            column_meta={},
        )
        from practice_theory_bank_import import ColumnMeta

        snapshot.column_meta["yj_practice_exercises.correct_memo"] = ColumnMeta(
            table_name="yj_practice_exercises",
            column_name="correct_memo",
            data_type="varchar",
            character_maximum_length=500,
            is_nullable=True,
            column_key=None,
            extra=None,
        )
        violations: list[Violation] = []

        validate_live_schema(snapshot, violations)

        self.assertEqual(["CORRECT_MEMO_COLUMN_TOO_SHORT"], [item.code for item in violations])

    def test_fetch_post_apply_stats_counts_zero_correct_answers_as_non_standard(self) -> None:
        class FakeCursor:
            def __init__(self) -> None:
                self.queries: list[str] = []
                self._results = [
                    [{"category_id": 1, "total": 2}],
                    [{"category_id": 1, "total": 6}],
                    {"total": 0},
                    {"total": 1},
                    {"total": 21},
                ]

            def __enter__(self) -> "FakeCursor":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def execute(self, query: str, params=None) -> None:
                del params
                self.queries.append(query)

            def fetchall(self):
                return self._results.pop(0)

            def fetchone(self):
                return self._results.pop(0)

        class FakeConnection:
            def __init__(self) -> None:
                self.cursor_instance = FakeCursor()

            def cursor(self) -> FakeCursor:
                return self.cursor_instance

        connection = FakeConnection()

        stats = fetch_post_apply_stats(connection, [1])

        self.assertEqual(1, stats["nonStandardCorrectAnswerQuestions"])
        self.assertIn("LEFT JOIN yj_practice_exercises_answer answer_item", connection.cursor_instance.queries[3])
        self.assertIn("HAVING correct_count <> 1", connection.cursor_instance.queries[3])


if __name__ == "__main__":
    unittest.main()
