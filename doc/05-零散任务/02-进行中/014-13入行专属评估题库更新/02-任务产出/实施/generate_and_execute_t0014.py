#!/usr/bin/env python3
"""Generate, execute, roll back, and verify the T0014 controlled data update."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

import pymysql
import yaml


CATEGORY_ID = 13
TENANT_ID = 1
TASK_MARKER = "t0014_v3_20260818"
STEP_ID_BASE = 132026081800000
QUESTION_ID_BASE = 132026081810000
ANSWER_ID_BASE = 132026081820000
STEP_NAMES = ["基础画像", "核心量表", "主要顾虑", "报告目标", "补充模块", "确认提交"]
TABLES = [
    "yj_practice_setp",
    "yj_practice_exercises",
    "yj_practice_exercises_answer",
    "yj_practice_exercises_answer_child",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--timestamp", required=True)
    workflow = subparsers.add_parser("workflow")
    workflow.add_argument("--config", type=Path, required=True)
    workflow.add_argument("--output", type=Path, required=True)
    workflow.add_argument("--dml", type=Path, required=True)
    workflow.add_argument("--rollback", type=Path, required=True)
    workflow.add_argument("--verify", type=Path, required=True)
    return parser.parse_args()


def load_master_config(config_path: Path) -> dict[str, Any]:
    documents = list(yaml.safe_load_all(config_path.read_text(encoding="utf-8")))
    for document in documents:
        spring = (document or {}).get("spring", {})
        datasource = spring.get("datasource")
        if datasource:
            return datasource["dynamic"]["datasource"]["master"]
    raise RuntimeError("master datasource not found in the supplied profile config")


def connect(config_path: Path) -> pymysql.Connection:
    master = load_master_config(config_path)
    jdbc = master["url"].split("?", 1)[0].replace("jdbc:", "", 1)
    parsed = urlparse(jdbc)
    return pymysql.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=master["username"],
        password=master["password"],
        database=parsed.path.lstrip("/"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def normalize(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return int.from_bytes(value, "big")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return value


def normalize_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: normalize(value) for key, value in row.items()} for row in rows]


def canonical_hash(rows: Sequence[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def query_rows(cursor: pymysql.cursors.DictCursor, sql: str, args: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, args)
    return normalize_rows(cursor.fetchall())


def in_clause(values: Sequence[int]) -> tuple[str, tuple[int, ...]]:
    if not values:
        return "NULL", ()
    return ",".join(["%s"] * len(values)), tuple(values)


def table_columns(cursor: pymysql.cursors.DictCursor, table: str) -> list[str]:
    rows = query_rows(
        cursor,
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
        (table,),
    )
    return [row["COLUMN_NAME"] for row in rows]


def full_table_rows(cursor: pymysql.cursors.DictCursor, table: str) -> list[dict[str, Any]]:
    columns = table_columns(cursor, table)
    selected = ", ".join(f"`{column}`" for column in columns)
    return query_rows(cursor, f"SELECT {selected} FROM `{table}` ORDER BY id")


def filtered_table_rows(
    cursor: pymysql.cursors.DictCursor, table: str, excluded_ids: Sequence[int]
) -> list[dict[str, Any]]:
    if not excluded_ids:
        return full_table_rows(cursor, table)
    columns = table_columns(cursor, table)
    selected = ", ".join(f"`{column}`" for column in columns)
    clause, args = in_clause(excluded_ids)
    return query_rows(cursor, f"SELECT {selected} FROM `{table}` WHERE id NOT IN ({clause}) ORDER BY id", args)


def letter_code(index: int) -> str:
    if index < 1 or index > 26:
        raise ValueError(f"unsupported answer index: {index}")
    return chr(ord("A") + index - 1)


def mapped_step(source_id: str) -> int:
    if re.fullmatch(r"Q[1-5]", source_id):
        return 1
    if re.fullmatch(r"Q(?:[6-9]|1[0-5])", source_id):
        return 2
    if source_id == "Q16":
        return 3
    if source_id == "Q17":
        return 4
    if re.fullmatch(r"[A-E]\d+", source_id):
        return 5
    if re.fullmatch(r"S[1-5]", source_id):
        return 6
    raise ValueError(f"no six-step mapping for source id {source_id}")


def map_question_type(source_type: str) -> str:
    mapping = {
        "single_choice": "single_choice",
        "likert": "single_choice",
        "multiple_choice": "multiple_choice",
        "text": "text",
        "textarea": "text",
    }
    if source_type not in mapping:
        raise ValueError(f"unsupported source type: {source_type}")
    return mapping[source_type]


def build_mapping(source: dict[str, Any], fixed_time: str) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []
    answer_sequence = 0
    for source_question in source["questions"]:
        source_id = source_question["id"]
        expanded = [(source_id, source_question["text"], source_question.get("options", []))]
        if source_id == "A3":
            rows = source_question.get("rules", {}).get("rows", [])
            if len(rows) != 8 or len(source_question.get("options", [])) != 3:
                raise RuntimeError("A3 must contain eight rows and three level options")
            expanded = [
                (f"A3.{index}", f"{source_question['text']}【{row_text}】", source_question["options"])
                for index, row_text in enumerate(rows, 1)
            ]
        for mapped_source_id, stem, options in expanded:
            question_no = len(questions) + 1
            step_no = mapped_step(source_id)
            question_type = "single_choice" if source_id == "A3" else map_question_type(source_question["type"])
            mapped_options = []
            for option_no, content in enumerate(options, 1):
                answer_sequence += 1
                mapped_options.append(
                    {
                        "answerId": ANSWER_ID_BASE + answer_sequence,
                        "answerCode": letter_code(option_no),
                        "answerContent": content,
                        "questionType": question_type,
                        "isCorrect": 0,
                        "sortNo": option_no,
                    }
                )
            questions.append(
                {
                    "sourceId": mapped_source_id,
                    "sourceParentId": source_id,
                    "questionId": QUESTION_ID_BASE + question_no,
                    "stepId": STEP_ID_BASE + step_no,
                    "stepName": STEP_NAMES[step_no - 1],
                    "questionStem": stem,
                    "questionType": question_type,
                    "questionStatus": 1,
                    "score": 0,
                    "sortNo": question_no,
                    "correctMemo": None,
                    "options": mapped_options,
                }
            )
    if len(questions) != 48 or answer_sequence != 243:
        raise RuntimeError(f"unexpected mapping totals: {len(questions)} questions, {answer_sequence} options")
    step_counts = {name: 0 for name in STEP_NAMES}
    for question in questions:
        step_counts[question["stepName"]] += 1
    expected_step_counts = dict(zip(STEP_NAMES, [5, 10, 1, 1, 26, 5]))
    if step_counts != expected_step_counts:
        raise RuntimeError(f"unexpected step distribution: {step_counts}")
    return {
        "taskId": "T0014",
        "sourceUrl": source["sourceUrl"],
        "sourceVersion": source["sourceVersion"],
        "sourceCapturedAt": source["capturedAt"],
        "generatedAt": fixed_time,
        "categoryId": CATEGORY_ID,
        "tenantId": TENANT_ID,
        "taskMarker": TASK_MARKER,
        "questionCount": len(questions),
        "optionCount": answer_sequence,
        "activeChildAnswerCount": 0,
        "stepCounts": step_counts,
        "steps": [
            {"stepId": STEP_ID_BASE + index, "stepName": name, "sortNo": index}
            for index, name in enumerate(STEP_NAMES, 1)
        ],
        "questions": questions,
    }


def capture_backup(cursor: pymysql.cursors.DictCursor, mapping: dict[str, Any]) -> dict[str, Any]:
    category = query_rows(
        cursor,
        "SELECT id, category_name, category_status + 0 AS category_status, field_type, catalog_type, sort_no, "
        "tenant_id, creator, create_time, updater, update_time, deleted + 0 AS deleted "
        "FROM yj_practice_category WHERE id = %s AND tenant_id = %s",
        (CATEGORY_ID, TENANT_ID),
    )
    if len(category) != 1:
        raise RuntimeError("category 13 / tenant 1 is not unique")
    questions = query_rows(
        cursor,
        "SELECT * FROM yj_practice_exercises WHERE category_id = %s AND tenant_id = %s ORDER BY id",
        (CATEGORY_ID, TENANT_ID),
    )
    active_questions = [row for row in questions if row["deleted"] == 0]
    if len(active_questions) != 21:
        raise RuntimeError(f"expected 21 active old questions, found {len(active_questions)}")
    question_ids = [row["id"] for row in questions]
    active_question_ids = [row["id"] for row in active_questions]
    question_clause, question_args = in_clause(question_ids)
    answers = query_rows(
        cursor,
        f"SELECT * FROM yj_practice_exercises_answer WHERE tenant_id = %s "
        f"AND exercises_id IN ({question_clause}) ORDER BY id",
        (TENANT_ID, *question_args),
    )
    active_answers = [row for row in answers if row["deleted"] == 0 and row["exercises_id"] in active_question_ids]
    if len(active_answers) != 101:
        raise RuntimeError(f"expected 101 active old answers, found {len(active_answers)}")
    answer_ids = [row["id"] for row in answers]
    answer_clause, answer_args = in_clause(answer_ids)
    children = query_rows(
        cursor,
        f"SELECT * FROM yj_practice_exercises_answer_child WHERE tenant_id = %s "
        f"AND answer_id IN ({answer_clause}) ORDER BY id",
        (TENANT_ID, *answer_args),
    ) if answer_ids else []
    active_answer_ids = {row["id"] for row in active_answers}
    active_children = [row for row in children if row["deleted"] == 0 and row["answer_id"] in active_answer_ids]
    if active_children:
        raise RuntimeError("expected zero active old child answers")
    active_step_ids = sorted({row["step_id"] for row in active_questions})
    if len(active_step_ids) != 4 or any(value is None for value in active_step_ids):
        raise RuntimeError(f"expected four old step ids, found {active_step_ids}")
    step_clause, step_args = in_clause(active_step_ids)
    steps = query_rows(
        cursor,
        f"SELECT * FROM yj_practice_setp WHERE tenant_id = %s AND id IN ({step_clause}) ORDER BY id",
        (TENANT_ID, *step_args),
    )
    if len(steps) != 4 or any(row["deleted"] != 0 for row in steps):
        raise RuntimeError("old step baseline is incomplete or inactive")
    outside_step_refs = query_rows(
        cursor,
        f"SELECT id FROM yj_practice_exercises WHERE step_id IN ({step_clause}) AND deleted = b'0' "
        "AND NOT (category_id = %s AND tenant_id = %s)",
        (*step_args, CATEGORY_ID, TENANT_ID),
    )
    if outside_step_refs:
        raise RuntimeError("old steps are referenced by non-target active questions")
    target_scope = {
        "oldQuestionIds": question_ids,
        "oldActiveQuestionIds": active_question_ids,
        "oldAnswerIds": answer_ids,
        "oldActiveAnswerIds": [row["id"] for row in active_answers],
        "oldChildAnswerIds": [row["id"] for row in children],
        "oldStepIds": active_step_ids,
        "newQuestionIds": [row["questionId"] for row in mapping["questions"]],
        "newAnswerIds": [option["answerId"] for row in mapping["questions"] for option in row["options"]],
        "newStepIds": [row["stepId"] for row in mapping["steps"]],
    }
    non_target_rows = {
        "yj_practice_setp": filtered_table_rows(cursor, "yj_practice_setp", active_step_ids + target_scope["newStepIds"]),
        "yj_practice_exercises": filtered_table_rows(cursor, "yj_practice_exercises", question_ids + target_scope["newQuestionIds"]),
        "yj_practice_exercises_answer": filtered_table_rows(cursor, "yj_practice_exercises_answer", answer_ids + target_scope["newAnswerIds"]),
        "yj_practice_exercises_answer_child": filtered_table_rows(cursor, "yj_practice_exercises_answer_child", target_scope["oldChildAnswerIds"]),
    }
    schema = {}
    for table in TABLES:
        schema[table] = {
            "columns": query_rows(
                cursor,
                "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY, EXTRA "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                "ORDER BY ORDINAL_POSITION",
                (table,),
            ),
            "indexes": query_rows(
                cursor,
                "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
                "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                "ORDER BY INDEX_NAME, SEQ_IN_INDEX",
                (table,),
            ),
        }
    return {
        "taskId": "T0014",
        "capturedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "connection": {"database": "yunjikeji", "profile": "local", "purpose": "test"},
        "category": category,
        "scope": target_scope,
        "tables": {
            "yj_practice_setp": steps,
            "yj_practice_exercises": questions,
            "yj_practice_exercises_answer": answers,
            "yj_practice_exercises_answer_child": children,
        },
        "hashes": {
            "target": {
                "yj_practice_setp": canonical_hash(steps),
                "yj_practice_exercises": canonical_hash(questions),
                "yj_practice_exercises_answer": canonical_hash(answers),
                "yj_practice_exercises_answer_child": canonical_hash(children),
            },
            "nonTarget": {
                table: {"rowCount": len(rows), "sha256": canonical_hash(rows)}
                for table, rows in non_target_rows.items()
            },
        },
        "schema": schema,
    }


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def sql_ids(values: Sequence[int]) -> str:
    return ", ".join(str(value) for value in values) or "NULL"


def insert_values(rows: Sequence[Sequence[Any]]) -> str:
    return ",\n".join("(" + ", ".join(sql_literal(value) for value in row) + ")" for row in rows)


def exact_question_condition(question: dict[str, Any]) -> str:
    values = [
        ("id", question["questionId"]),
        ("step_id", question["stepId"]),
        ("category_id", CATEGORY_ID),
        ("question_stem", question["questionStem"]),
        ("question_type", question["questionType"]),
        ("question_status + 0", 1),
        ("score", 0),
        ("sort_no", question["sortNo"]),
        ("correct_memo", None),
        ("tenant_id", TENANT_ID),
        ("creator", TASK_MARKER),
        ("updater", TASK_MARKER),
        ("deleted + 0", 0),
    ]
    return "(" + " AND ".join(f"{column} <=> {sql_literal(value)}" for column, value in values) + ")"


def exact_answer_condition(question: dict[str, Any], option: dict[str, Any]) -> str:
    values = [
        ("id", option["answerId"]),
        ("exercises_id", question["questionId"]),
        ("question_type", option["questionType"]),
        ("answer_code", option["answerCode"]),
        ("answer_content", option["answerContent"]),
        ("is_correct + 0", 0),
        ("sort_no", option["sortNo"]),
        ("tenant_id", TENANT_ID),
        ("creator", TASK_MARKER),
        ("updater", TASK_MARKER),
        ("deleted + 0", 0),
    ]
    return "(" + " AND ".join(f"{column} <=> {sql_literal(value)}" for column, value in values) + ")"


def exact_step_condition(step: dict[str, Any]) -> str:
    values = [
        ("id", step["stepId"]),
        ("tenant_id", TENANT_ID),
        ("setp_name", step["stepName"]),
        ("setp_status + 0", 1),
        ("sort_no", step["sortNo"]),
        ("creator", TASK_MARKER),
        ("updater", TASK_MARKER),
        ("deleted + 0", 0),
    ]
    return "(" + " AND ".join(f"{column} <=> {sql_literal(value)}" for column, value in values) + ")"


def exact_sum_assertion(table: str, conditions: Sequence[str], where: str, alias: str, old_state_allowed: bool) -> str:
    condition_sql = " OR\n        ".join(conditions)
    final_assertion = f"COUNT(*) = {len(conditions)} AND SUM(({condition_sql})) = {len(conditions)}"
    prefix = "@t0014_state = 'old' OR " if old_state_allowed else ""
    return f"SELECT ({prefix}({final_assertion})) AS {alias}\nFROM {table}\nWHERE {where};"


def restore_case_sql(table: str, rows: Sequence[dict[str, Any]], boundary: str) -> str:
    ids = [row["id"] for row in rows]
    updater_cases = " ".join(f"WHEN {row['id']} THEN {sql_literal(row['updater'])}" for row in rows)
    time_cases = " ".join(f"WHEN {row['id']} THEN {sql_literal(row['update_time'])}" for row in rows)
    deleted_cases = " ".join(f"WHEN {row['id']} THEN {int(row['deleted'])}" for row in rows)
    return (
        f"UPDATE {table}\nSET updater = CASE id {updater_cases} END,\n"
        f"    update_time = CASE id {time_cases} END,\n"
        f"    deleted = CASE id {deleted_cases} END\n"
        f"WHERE {boundary} AND id IN ({sql_ids(ids)});"
    )


def generate_verify_sql(mapping: dict[str, Any], backup: dict[str, Any], created_date: str) -> str:
    scope = backup["scope"]
    question_conditions = [exact_question_condition(row) for row in mapping["questions"]]
    answer_conditions = [
        exact_answer_condition(question, option)
        for question in mapping["questions"]
        for option in question["options"]
    ]
    step_conditions = [exact_step_condition(row) for row in mapping["steps"]]
    return f"""-- ============================================
-- 脚本类型：verify
-- 脚本描述：T0014 分类13题库及六步骤状态校验
-- 创建日期：{created_date}
-- 作者：Codex
-- 影响范围：只读 yj_practice_setp 及题库三表
-- 执行环境：local profile 实际连接的 yunjikeji 测试库
-- ============================================
SET NAMES utf8mb4;
START TRANSACTION READ ONLY;
SET @t0014_old_active_questions := (SELECT COUNT(*) FROM yj_practice_exercises WHERE id IN ({sql_ids(scope['oldActiveQuestionIds'])}) AND category_id = 13 AND tenant_id = 1 AND deleted = b'0');
SET @t0014_new_active_questions := (SELECT COUNT(*) FROM yj_practice_exercises WHERE id IN ({sql_ids(scope['newQuestionIds'])}) AND category_id = 13 AND tenant_id = 1 AND deleted = b'0');
SET @t0014_state := CASE WHEN @t0014_old_active_questions = 21 AND @t0014_new_active_questions = 0 THEN 'old' WHEN @t0014_old_active_questions = 0 AND @t0014_new_active_questions = 48 THEN 'final' ELSE 'invalid' END;
SELECT DATABASE() = 'yunjikeji' AS assert_database;
SELECT COUNT(*) = 1 AS assert_category_unique FROM yj_practice_category WHERE id = 13 AND tenant_id = 1 AND deleted = b'0';
SELECT @t0014_state IN ('old', 'final') AS assert_supported_state;
SELECT @t0014_state AS verification_state;
SELECT (@t0014_state = 'final' OR COUNT(*) = 101) AS assert_old_answers FROM yj_practice_exercises_answer WHERE id IN ({sql_ids(scope['oldActiveAnswerIds'])}) AND tenant_id = 1 AND deleted = b'0';
SELECT (@t0014_state = 'final' OR COUNT(*) = 4) AS assert_old_steps FROM yj_practice_setp WHERE id IN ({sql_ids(scope['oldStepIds'])}) AND tenant_id = 1 AND deleted = b'0';
{exact_sum_assertion('yj_practice_setp', step_conditions, f"tenant_id = 1 AND id IN ({sql_ids(scope['newStepIds'])}) AND deleted = b'0'", 'assert_final_steps_exact', True)}
{exact_sum_assertion('yj_practice_exercises', question_conditions, 'category_id = 13 AND tenant_id = 1 AND deleted = b\'0\'', 'assert_final_questions_exact', True)}
{exact_sum_assertion('yj_practice_exercises_answer', answer_conditions, f"tenant_id = 1 AND exercises_id IN ({sql_ids(scope['newQuestionIds'])}) AND deleted = b'0'", 'assert_final_answers_exact', True)}
SELECT (@t0014_state = 'old' OR COUNT(*) = 0) AS assert_final_children_zero
FROM yj_practice_exercises_answer_child c
JOIN yj_practice_exercises_answer a ON a.id = c.answer_id
WHERE a.exercises_id IN ({sql_ids(scope['newQuestionIds'])}) AND a.tenant_id = 1 AND c.tenant_id = 1 AND c.deleted = b'0';
SELECT (@t0014_state = 'old' OR (COUNT(*) = 48 AND MIN(sort_no) = 1 AND MAX(sort_no) = 48 AND COUNT(DISTINCT sort_no) = 48)) AS assert_question_sort_continuous
FROM yj_practice_exercises WHERE category_id = 13 AND tenant_id = 1 AND deleted = b'0';
SELECT (@t0014_state = 'old' OR COUNT(*) = 0) AS assert_no_active_orphan_answers
FROM yj_practice_exercises_answer a LEFT JOIN yj_practice_exercises e ON e.id = a.exercises_id AND e.deleted = b'0'
WHERE a.id IN ({sql_ids(scope['newAnswerIds'])}) AND a.exercises_id IN ({sql_ids(scope['newQuestionIds'])})
  AND a.tenant_id = 1 AND a.deleted = b'0' AND e.id IS NULL;
ROLLBACK;
"""


def generate_dml_sql(mapping: dict[str, Any], backup: dict[str, Any], created_date: str) -> str:
    scope = backup["scope"]
    fixed_time = mapping["generatedAt"][:19].replace("T", " ")
    step_rows = [
        (row["stepId"], TENANT_ID, row["stepName"], 1, row["sortNo"], TASK_MARKER, fixed_time, TASK_MARKER, fixed_time, 0)
        for row in mapping["steps"]
    ]
    question_rows = [
        (row["questionId"], row["stepId"], CATEGORY_ID, row["questionStem"], row["questionType"], 1, 0, row["sortNo"], None, TENANT_ID, TASK_MARKER, fixed_time, TASK_MARKER, fixed_time, 0)
        for row in mapping["questions"]
    ]
    answer_rows = [
        (option["answerId"], question["questionId"], option["questionType"], option["answerCode"], option["answerContent"], 0, option["sortNo"], TENANT_ID, TASK_MARKER, fixed_time, TASK_MARKER, fixed_time, 0)
        for question in mapping["questions"] for option in question["options"]
    ]
    return f"""-- ============================================
-- 脚本类型：dml
-- 脚本描述：T0014 分类13 V3题库及六步骤受控更新
-- 创建日期：{created_date}
-- 作者：Codex
-- 影响范围：tenant_id=1、category_id=13 的精确旧主键集合及任务专属新主键集合
-- 执行环境：local profile 实际连接的 yunjikeji 测试库
-- 回滚方案：执行对应 rollback SQL
-- ============================================
SET NAMES utf8mb4;
START TRANSACTION;
SET @t0014_old_active_questions := (SELECT COUNT(*) FROM yj_practice_exercises WHERE id IN ({sql_ids(scope['oldActiveQuestionIds'])}) AND category_id = 13 AND tenant_id = 1 AND deleted = b'0');
SET @t0014_new_active_questions := (SELECT COUNT(*) FROM yj_practice_exercises WHERE id IN ({sql_ids(scope['newQuestionIds'])}) AND category_id = 13 AND tenant_id = 1 AND deleted = b'0');
SET @t0014_mode := CASE WHEN @t0014_old_active_questions = 21 AND @t0014_new_active_questions = 0 THEN 1 WHEN @t0014_old_active_questions = 0 AND @t0014_new_active_questions = 48 THEN 2 ELSE 0 END;
SELECT DATABASE() = 'yunjikeji' AS assert_database;
SELECT COUNT(*) = 1 AS assert_category_unique FROM yj_practice_category WHERE id = 13 AND tenant_id = 1 AND deleted = b'0';
SELECT @t0014_mode IN (1, 2) AS assert_supported_state;
SELECT (@t0014_mode = 2 OR COUNT(*) = 101) AS assert_old_answers FROM yj_practice_exercises_answer WHERE id IN ({sql_ids(scope['oldActiveAnswerIds'])}) AND tenant_id = 1 AND deleted = b'0';
SELECT COUNT(*) = 0 AS assert_old_children FROM yj_practice_exercises_answer_child WHERE id IN ({sql_ids(scope['oldChildAnswerIds'])}) AND tenant_id = 1 AND deleted = b'0';
SELECT (@t0014_mode = 2 OR COUNT(*) = 4) AS assert_old_steps FROM yj_practice_setp WHERE id IN ({sql_ids(scope['oldStepIds'])}) AND tenant_id = 1 AND deleted = b'0';
SELECT (@t0014_mode = 2 OR COUNT(*) = 0) AS assert_old_steps_not_shared
FROM yj_practice_exercises WHERE step_id IN ({sql_ids(scope['oldStepIds'])}) AND deleted = b'0' AND NOT (category_id = 13 AND tenant_id = 1);
SELECT (@t0014_mode = 2 OR COUNT(*) = 0) AS assert_new_step_ids_free FROM yj_practice_setp WHERE id IN ({sql_ids(scope['newStepIds'])});
SELECT (@t0014_mode = 2 OR COUNT(*) = 0) AS assert_new_question_ids_free FROM yj_practice_exercises WHERE id IN ({sql_ids(scope['newQuestionIds'])});
SELECT (@t0014_mode = 2 OR COUNT(*) = 0) AS assert_new_answer_ids_free FROM yj_practice_exercises_answer WHERE id IN ({sql_ids(scope['newAnswerIds'])});
UPDATE yj_practice_exercises_answer SET deleted = b'1', updater = '{TASK_MARKER}', update_time = NOW()
WHERE tenant_id = 1 AND deleted = b'0' AND id IN ({sql_ids(scope['oldActiveAnswerIds'])}) AND exercises_id IN ({sql_ids(scope['oldActiveQuestionIds'])});
SELECT ROW_COUNT() = IF(@t0014_mode = 1, 101, 0) AS assert_old_answers_soft_deleted;
UPDATE yj_practice_exercises SET deleted = b'1', updater = '{TASK_MARKER}', update_time = NOW()
WHERE category_id = 13 AND tenant_id = 1 AND deleted = b'0' AND id IN ({sql_ids(scope['oldActiveQuestionIds'])});
SELECT ROW_COUNT() = IF(@t0014_mode = 1, 21, 0) AS assert_old_questions_soft_deleted;
UPDATE yj_practice_setp SET deleted = b'1', updater = '{TASK_MARKER}', update_time = NOW()
WHERE tenant_id = 1 AND deleted = b'0' AND id IN ({sql_ids(scope['oldStepIds'])});
SELECT ROW_COUNT() = IF(@t0014_mode = 1, 4, 0) AS assert_old_steps_soft_deleted;
INSERT IGNORE INTO yj_practice_setp (id, tenant_id, setp_name, setp_status, sort_no, creator, create_time, updater, update_time, deleted) VALUES
{insert_values(step_rows)};
SELECT ROW_COUNT() = IF(@t0014_mode = 1, 6, 0) AS assert_new_steps_inserted;
INSERT IGNORE INTO yj_practice_exercises (id, step_id, category_id, question_stem, question_type, question_status, score, sort_no, correct_memo, tenant_id, creator, create_time, updater, update_time, deleted) VALUES
{insert_values(question_rows)};
SELECT ROW_COUNT() = IF(@t0014_mode = 1, 48, 0) AS assert_new_questions_inserted;
INSERT IGNORE INTO yj_practice_exercises_answer (id, exercises_id, question_type, answer_code, answer_content, is_correct, sort_no, tenant_id, creator, create_time, updater, update_time, deleted) VALUES
{insert_values(answer_rows)};
SELECT ROW_COUNT() = IF(@t0014_mode = 1, 243, 0) AS assert_new_answers_inserted;
SELECT COUNT(*) = 48 AS assert_final_question_count FROM yj_practice_exercises WHERE category_id = 13 AND tenant_id = 1 AND deleted = b'0';
SELECT COUNT(*) = 243 AS assert_final_answer_count FROM yj_practice_exercises_answer WHERE exercises_id IN ({sql_ids(scope['newQuestionIds'])}) AND tenant_id = 1 AND deleted = b'0';
SELECT COUNT(*) = 0 AS assert_final_correct_answers FROM yj_practice_exercises_answer WHERE exercises_id IN ({sql_ids(scope['newQuestionIds'])}) AND tenant_id = 1 AND deleted = b'0' AND is_correct <> b'0';
SELECT COUNT(*) = 0 AS assert_final_child_answers FROM yj_practice_exercises_answer_child c JOIN yj_practice_exercises_answer a ON a.id = c.answer_id WHERE a.exercises_id IN ({sql_ids(scope['newQuestionIds'])}) AND c.tenant_id = 1 AND c.deleted = b'0';
COMMIT;
"""


def generate_rollback_sql(mapping: dict[str, Any], backup: dict[str, Any], created_date: str) -> str:
    scope = backup["scope"]
    old_steps = backup["tables"]["yj_practice_setp"]
    old_questions = [row for row in backup["tables"]["yj_practice_exercises"] if row["id"] in scope["oldActiveQuestionIds"]]
    old_answers = [row for row in backup["tables"]["yj_practice_exercises_answer"] if row["id"] in scope["oldActiveAnswerIds"]]
    return f"""-- ============================================
-- 脚本类型：dml
-- 脚本描述：回滚 T0014 分类13 V3题库及六步骤更新
-- 创建日期：{created_date}
-- 作者：Codex
-- 影响范围：tenant_id=1、category_id=13 的精确旧主键集合及任务专属新主键集合
-- 执行环境：local profile 实际连接的 yunjikeji 测试库
-- 说明：仅硬删除本任务新建且带任务标记的行；历史旧行全部原值恢复
-- ============================================
SET NAMES utf8mb4;
START TRANSACTION;
SELECT DATABASE() = 'yunjikeji' AS assert_database;
SELECT COUNT(*) = 48 AS assert_new_questions FROM yj_practice_exercises WHERE id IN ({sql_ids(scope['newQuestionIds'])}) AND category_id = 13 AND tenant_id = 1 AND creator = '{TASK_MARKER}' AND deleted = b'0';
SELECT COUNT(*) = 243 AS assert_new_answers FROM yj_practice_exercises_answer WHERE id IN ({sql_ids(scope['newAnswerIds'])}) AND exercises_id IN ({sql_ids(scope['newQuestionIds'])}) AND tenant_id = 1 AND creator = '{TASK_MARKER}' AND deleted = b'0';
SELECT COUNT(*) = 6 AS assert_new_steps FROM yj_practice_setp WHERE id IN ({sql_ids(scope['newStepIds'])}) AND tenant_id = 1 AND creator = '{TASK_MARKER}' AND deleted = b'0';
SELECT COUNT(*) = 0 AS assert_new_children FROM yj_practice_exercises_answer_child c JOIN yj_practice_exercises_answer a ON a.id = c.answer_id WHERE a.exercises_id IN ({sql_ids(scope['newQuestionIds'])}) AND c.tenant_id = 1 AND c.deleted = b'0';
DELETE FROM yj_practice_exercises_answer WHERE id IN ({sql_ids(scope['newAnswerIds'])}) AND exercises_id IN ({sql_ids(scope['newQuestionIds'])}) AND tenant_id = 1 AND creator = '{TASK_MARKER}';
SELECT ROW_COUNT() = 243 AS assert_new_answers_removed;
DELETE FROM yj_practice_exercises WHERE id IN ({sql_ids(scope['newQuestionIds'])}) AND category_id = 13 AND tenant_id = 1 AND creator = '{TASK_MARKER}';
SELECT ROW_COUNT() = 48 AS assert_new_questions_removed;
DELETE FROM yj_practice_setp WHERE id IN ({sql_ids(scope['newStepIds'])}) AND tenant_id = 1 AND creator = '{TASK_MARKER}';
SELECT ROW_COUNT() = 6 AS assert_new_steps_removed;
{restore_case_sql('yj_practice_setp', old_steps, 'tenant_id = 1')}
SELECT ROW_COUNT() = 4 AS assert_old_steps_restored;
{restore_case_sql('yj_practice_exercises', old_questions, 'category_id = 13 AND tenant_id = 1')}
SELECT ROW_COUNT() = 21 AS assert_old_questions_restored;
{restore_case_sql('yj_practice_exercises_answer', old_answers, f"tenant_id = 1 AND exercises_id IN ({sql_ids(scope['oldActiveQuestionIds'])})")}
SELECT ROW_COUNT() = 101 AS assert_old_answers_restored;
SELECT COUNT(*) = 21 AS assert_old_question_count FROM yj_practice_exercises WHERE id IN ({sql_ids(scope['oldActiveQuestionIds'])}) AND category_id = 13 AND tenant_id = 1 AND deleted = b'0';
SELECT COUNT(*) = 101 AS assert_old_answer_count FROM yj_practice_exercises_answer WHERE id IN ({sql_ids(scope['oldActiveAnswerIds'])}) AND tenant_id = 1 AND deleted = b'0';
SELECT COUNT(*) = 4 AS assert_old_step_count FROM yj_practice_setp WHERE id IN ({sql_ids(scope['oldStepIds'])}) AND tenant_id = 1 AND deleted = b'0';
COMMIT;
"""


def split_sql(text: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if quote:
            buffer.append(char)
            if char == "\\" and index + 1 < len(text):
                index += 1
                buffer.append(text[index])
            elif char == quote:
                if next_char == quote and quote in ("'", '"'):
                    index += 1
                    buffer.append(text[index])
                else:
                    quote = None
            index += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
            buffer.append(char)
            index += 1
            continue
        if char == "-" and next_char == "-":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "#":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue
        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(char)
        index += 1
    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return statements


def execute_sql_file(connection: pymysql.Connection, path: Path, read_only: bool = False) -> dict[str, Any]:
    statements = split_sql(path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {"file": str(path.resolve()), "statementCount": len(statements), "assertions": 0, "verificationState": None}
    try:
        for statement in statements:
            normalized = re.sub(r"\s+", " ", statement).strip().upper()
            if normalized in {"START TRANSACTION", "START TRANSACTION READ ONLY"}:
                if normalized == "START TRANSACTION READ ONLY":
                    with connection.cursor() as cursor:
                        cursor.execute("START TRANSACTION READ ONLY")
                else:
                    connection.begin()
                continue
            if normalized == "COMMIT":
                connection.commit()
                continue
            if normalized == "ROLLBACK":
                connection.rollback()
                continue
            with connection.cursor() as cursor:
                cursor.execute(statement)
                if cursor.description:
                    row = cursor.fetchone()
                    if row:
                        for key, value in row.items():
                            if key.startswith("assert_"):
                                result["assertions"] += 1
                                if int(value) != 1:
                                    raise RuntimeError(f"{path.name}: assertion failed: {key}")
                            elif key == "verification_state":
                                result["verificationState"] = value
        return result
    except Exception:
        connection.rollback()
        raise


def current_scope_hashes(cursor: pymysql.cursors.DictCursor, backup: dict[str, Any]) -> dict[str, str]:
    scope = backup["scope"]
    result = {}
    for table, key in [
        ("yj_practice_setp", "oldStepIds"),
        ("yj_practice_exercises", "oldQuestionIds"),
        ("yj_practice_exercises_answer", "oldAnswerIds"),
        ("yj_practice_exercises_answer_child", "oldChildAnswerIds"),
    ]:
        values = scope[key]
        clause, args = in_clause(values)
        rows = query_rows(cursor, f"SELECT * FROM {table} WHERE id IN ({clause}) ORDER BY id", args) if values else []
        result[table] = canonical_hash(rows)
    return result


def non_target_hashes(cursor: pymysql.cursors.DictCursor, backup: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scope = backup["scope"]
    exclusions = {
        "yj_practice_setp": scope["oldStepIds"] + scope["newStepIds"],
        "yj_practice_exercises": scope["oldQuestionIds"] + scope["newQuestionIds"],
        "yj_practice_exercises_answer": scope["oldAnswerIds"] + scope["newAnswerIds"],
        "yj_practice_exercises_answer_child": scope["oldChildAnswerIds"],
    }
    output = {}
    for table, ids in exclusions.items():
        rows = filtered_table_rows(cursor, table, ids)
        output[table] = {"rowCount": len(rows), "sha256": canonical_hash(rows)}
    return output


def assert_old_state(cursor: pymysql.cursors.DictCursor, backup: dict[str, Any]) -> None:
    actual = current_scope_hashes(cursor, backup)
    expected = backup["hashes"]["target"]
    if actual != expected:
        raise RuntimeError(f"old target baseline hash mismatch: {actual}")


def assert_non_target(cursor: pymysql.cursors.DictCursor, backup: dict[str, Any]) -> dict[str, dict[str, Any]]:
    actual = non_target_hashes(cursor, backup)
    expected = backup["hashes"]["nonTarget"]
    if actual != expected:
        raise RuntimeError(f"non-target baseline changed: {actual}")
    return actual


def final_content_hashes(cursor: pymysql.cursors.DictCursor, backup: dict[str, Any]) -> dict[str, str]:
    scope = backup["scope"]
    result = {}
    for table, ids in [
        ("yj_practice_setp", scope["newStepIds"]),
        ("yj_practice_exercises", scope["newQuestionIds"]),
        ("yj_practice_exercises_answer", scope["newAnswerIds"]),
    ]:
        clause, args = in_clause(ids)
        rows = query_rows(cursor, f"SELECT * FROM {table} WHERE id IN ({clause}) ORDER BY id", args)
        result[table] = canonical_hash(rows)
    return result


def append_log(path: Path, lines: Sequence[str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else "# T0014 实施执行日志\n\n"
    content = existing + "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8", newline="\n")


def prepare_assets(args: argparse.Namespace) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    fixed_time = datetime.strptime(args.timestamp, "%Y%m%d%H%M%S").astimezone().isoformat(timespec="seconds")
    source = json.loads(args.source.read_text(encoding="utf-8"))
    mapping = build_mapping(source, fixed_time)
    connection = connect(args.config)
    try:
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            backup = capture_backup(cursor, mapping)
            connection.rollback()
    finally:
        connection.close()
    mapping_path = args.output / "mapping-48.json"
    backup_path = args.output / "backup-before.json"
    dml_path = args.output / f"{args.timestamp}-dml-update_category_13_assessment.sql"
    rollback_path = args.output / f"{int(args.timestamp) + 1:014d}-dml-rollback_category_13_assessment.sql"
    verify_path = args.output / "verify-category-13.sql"
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    created_date = fixed_time[:19].replace("T", " ")
    dml_path.write_text(generate_dml_sql(mapping, backup, created_date), encoding="utf-8", newline="\n")
    rollback_path.write_text(generate_rollback_sql(mapping, backup, created_date), encoding="utf-8", newline="\n")
    verify_path.write_text(generate_verify_sql(mapping, backup, created_date), encoding="utf-8", newline="\n")
    append_log(
        args.output / "execution-log.md",
        [
            f"## {datetime.now().astimezone().isoformat(timespec='seconds')} 资产准备",
            "",
            f"- 命令：`python generate_and_execute_t0014.py prepare --config <application-local.yaml> --source <source-questions.json> --output <实施目录> --timestamp {args.timestamp}`",
            "- 连接确认：运行中程序默认 `local` profile；生效库 `yunjikeji`；正式用途为测试库。",
            "- 旧基线：21 道活动题、101 个活动选项、0 个活动子答案、4 个仅供目标分类使用的活动步骤。",
            "- 新映射：48 道题、243 个选项、6 个步骤；步骤题量 5/10/1/1/26/5。",
            f"- 目标基线哈希：`{json.dumps(backup['hashes']['target'], ensure_ascii=False, sort_keys=True)}`",
            f"- 非目标基线：`{json.dumps(backup['hashes']['nonTarget'], ensure_ascii=False, sort_keys=True)}`",
            "- 凭据：仅由运行时读取生效配置，未写入任何产出。",
            "",
        ],
    )
    print(json.dumps({"mapping": str(mapping_path.resolve()), "backup": str(backup_path.resolve()), "dml": str(dml_path.resolve()), "rollback": str(rollback_path.resolve()), "verify": str(verify_path.resolve())}, ensure_ascii=False, indent=2))


def run_workflow(args: argparse.Namespace) -> None:
    backup = json.loads((args.output / "backup-before.json").read_text(encoding="utf-8"))
    log_path = args.output / "execution-log.md"
    connection = connect(args.config)
    phases = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            assert_old_state(cursor, backup)
            assert_non_target(cursor, backup)
            connection.rollback()
        verify_before = execute_sql_file(connection, args.verify, read_only=True)
        if verify_before["verificationState"] != "old":
            raise RuntimeError("pre-update verify did not detect the old state")
        phases.append(verify_before)
        phases.append(execute_sql_file(connection, args.dml))
        verify_first = execute_sql_file(connection, args.verify, read_only=True)
        if verify_first["verificationState"] != "final":
            raise RuntimeError("first update did not reach final state")
        phases.append(verify_first)
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            final_first = final_content_hashes(cursor, backup)
            assert_non_target(cursor, backup)
            connection.rollback()
        phases.append(execute_sql_file(connection, args.rollback))
        verify_rollback = execute_sql_file(connection, args.verify, read_only=True)
        if verify_rollback["verificationState"] != "old":
            raise RuntimeError("rollback did not restore old state")
        phases.append(verify_rollback)
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            assert_old_state(cursor, backup)
            assert_non_target(cursor, backup)
            connection.rollback()
        phases.append(execute_sql_file(connection, args.dml))
        verify_final = execute_sql_file(connection, args.verify, read_only=True)
        if verify_final["verificationState"] != "final":
            raise RuntimeError("second update did not reach final state")
        phases.append(verify_final)
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            final_second = final_content_hashes(cursor, backup)
            assert_non_target(cursor, backup)
            connection.rollback()
        if final_first != final_second:
            raise RuntimeError("final data hash differs after rollback rehearsal and re-update")
        phases.append(execute_sql_file(connection, args.dml))
        verify_idempotent = execute_sql_file(connection, args.verify, read_only=True)
        if verify_idempotent["verificationState"] != "final":
            raise RuntimeError("idempotent rerun changed final state")
        phases.append(verify_idempotent)
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION READ ONLY")
            final_third = final_content_hashes(cursor, backup)
            final_non_target = assert_non_target(cursor, backup)
            connection.rollback()
        if final_second != final_third:
            raise RuntimeError("idempotent rerun changed target final hash")
    except Exception as error:
        recovery = "not-needed"
        try:
            with connection.cursor() as cursor:
                active_new = query_rows(
                    cursor,
                    "SELECT COUNT(*) AS row_count FROM yj_practice_exercises "
                    "WHERE id IN (" + ",".join(["%s"] * len(backup["scope"]["newQuestionIds"])) + ") "
                    "AND category_id = %s AND tenant_id = %s AND deleted = b'0'",
                    (*backup["scope"]["newQuestionIds"], CATEGORY_ID, TENANT_ID),
                )[0]["row_count"]
            if active_new == 48:
                execute_sql_file(connection, args.rollback)
                recovery = "rollback-restored-old-state"
        except Exception as recovery_error:
            recovery = f"rollback-failed: {type(recovery_error).__name__}: {recovery_error}"
        append_log(
            log_path,
            [
                f"## {datetime.now().astimezone().isoformat(timespec='seconds')} 执行失败",
                "",
                f"- 失败：`{type(error).__name__}: {error}`",
                f"- 自动恢复：`{recovery}`",
                "- 结论：停止后续动作，未宣称验收通过。",
                "",
            ],
        )
        raise
    finally:
        connection.close()
    append_log(
        log_path,
        [
            f"## {datetime.now().astimezone().isoformat(timespec='seconds')} 执行、回滚演练与最终恢复",
            "",
            "- 命令：`python generate_and_execute_t0014.py workflow --config <application-local.yaml> --output <实施目录> --dml <更新SQL> --rollback <回滚SQL> --verify <校验SQL>`",
            "- 第一次更新：成功；verify 检测状态 `final`。",
            "- 回滚演练：成功；verify 检测状态 `old`；旧目标全字段哈希恢复。",
            "- 第二次更新：成功；verify 检测状态 `final`；与第一次最终哈希一致。",
            "- 幂等重跑：成功；更新 SQL 再执行无新增变化，目标最终哈希不变。",
            "- 最终统计：48 道活动题、243 个活动选项、0 个活动子答案、6 个活动步骤。",
            "- 标准答案：243 个活动选项 `is_correct=0`；题目 `score=0`、`question_status=1`。",
            f"- 最终目标哈希：`{json.dumps(final_third, ensure_ascii=False, sort_keys=True)}`",
            f"- 非目标零变化：`{json.dumps(final_non_target, ensure_ascii=False, sort_keys=True)}`",
            f"- SQL 断言摘要：`{json.dumps(phases, ensure_ascii=False, sort_keys=True)}`",
            "- 凭据：未写入日志或产出。",
            "- 结论：仅为实施自检，不能替代独立验收。",
            "",
        ],
    )
    print(json.dumps({"status": "DONE", "phases": phases, "targetHashes": final_third, "nonTarget": final_non_target}, ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()
    if args.command == "prepare":
        prepare_assets(args)
    else:
        run_workflow(args)


if __name__ == "__main__":
    main()
