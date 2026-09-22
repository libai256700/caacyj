#!/usr/bin/env python3
"""Independent, read-only verification for T0014.

Database credentials are loaded at runtime from the supplied effective profile and
are never included in the result file.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

import pymysql
import yaml


CATEGORY_ID = 13
TENANT_ID = 1
EXPECTED_STEP_NAMES = ["基础画像", "核心量表", "主要顾虑", "报告目标", "补充模块", "确认提交"]
EXPECTED_STEP_COUNTS = [5, 10, 1, 1, 26, 5]
ALLOWED_TABLES = {
    "yj_practice_setp",
    "yj_practice_exercises",
    "yj_practice_exercises_answer",
    "yj_practice_exercises_answer_child",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--implementation-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.self_test:
        missing = [
            name
            for name in ("config", "mapping", "backup", "implementation_dir", "output")
            if getattr(args, name) is None
        ]
        if missing:
            parser.error("the following arguments are required: " + ", ".join(f"--{name.replace('_', '-')}" for name in missing))
    return args


def load_master_config(config_path: Path) -> dict[str, Any]:
    for document in yaml.safe_load_all(config_path.read_text(encoding="utf-8")):
        datasource = (document or {}).get("spring", {}).get("datasource")
        if datasource:
            return datasource["dynamic"]["datasource"]["master"]
    raise RuntimeError("master datasource not found in supplied profile")


def connect_read_only(config_path: Path) -> tuple[pymysql.Connection, dict[str, Any]]:
    master = load_master_config(config_path)
    parsed = urlparse(master["url"].split("?", 1)[0].replace("jdbc:", "", 1))
    connection = pymysql.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=master["username"],
        password=master["password"],
        database=parsed.path.lstrip("/"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    with connection.cursor() as cursor:
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        cursor.execute("START TRANSACTION READ ONLY")
    endpoint = {"host": parsed.hostname, "port": parsed.port, "database": parsed.path.lstrip("/")}
    return connection, endpoint


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


def query(cursor: pymysql.cursors.DictCursor, sql: str, args: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, args)
    return normalize_rows(cursor.fetchall())


def placeholders(values: Sequence[Any]) -> str:
    return ",".join(["%s"] * len(values)) if values else "NULL"


def canonical_hash(rows: Sequence[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def table_columns(cursor: pymysql.cursors.DictCursor, table: str) -> list[str]:
    if table not in ALLOWED_TABLES:
        raise ValueError(f"table not allowed: {table}")
    rows = query(
        cursor,
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
        (table,),
    )
    return [row["COLUMN_NAME"] for row in rows]


def rows_excluding_ids(
    cursor: pymysql.cursors.DictCursor, table: str, excluded_ids: Sequence[int]
) -> list[dict[str, Any]]:
    columns = table_columns(cursor, table)
    selected = ", ".join(f"`{column}`" for column in columns)
    if excluded_ids:
        return query(
            cursor,
            f"SELECT {selected} FROM `{table}` WHERE id NOT IN ({placeholders(excluded_ids)}) ORDER BY id",
            tuple(excluded_ids),
        )
    return query(cursor, f"SELECT {selected} FROM `{table}` ORDER BY id")


def rows_for_ids(cursor: pymysql.cursors.DictCursor, table: str, ids: Sequence[int]) -> list[dict[str, Any]]:
    columns = table_columns(cursor, table)
    selected = ", ".join(f"`{column}`" for column in columns)
    if not ids:
        return []
    return query(
        cursor,
        f"SELECT {selected} FROM `{table}` WHERE id IN ({placeholders(ids)}) ORDER BY id",
        tuple(ids),
    )


class SqlLexicalError(ValueError):
    pass


def append_sql_space(buffer: list[str]) -> None:
    if buffer and buffer[-1] != " ":
        buffer.append(" ")


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
                if next_char == quote:
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
            following = text[index + 2] if index + 2 < len(text) else ""
            if following and ord(following) > 32:
                raise SqlLexicalError("invalid MySQL -- comment marker")
            append_sql_space(buffer)
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            while index < len(text) and text[index] in "\r\n":
                index += 1
            continue
        if char == "#":
            append_sql_space(buffer)
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            while index < len(text) and text[index] in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            marker = text[index + 2] if index + 2 < len(text) else ""
            if marker in {"!", "+"}:
                raise SqlLexicalError("executable comments and optimizer hints are not allowed")
            comment_index = index + 2
            while comment_index + 1 < len(text):
                if text[comment_index] == "*" and text[comment_index + 1] == "/":
                    break
                comment_index += 1
            else:
                raise SqlLexicalError("unterminated block comment")
            append_sql_space(buffer)
            index = comment_index + 2
            continue
        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        elif char.isspace():
            append_sql_space(buffer)
        else:
            buffer.append(char)
        index += 1
    if quote:
        raise SqlLexicalError("unterminated quoted value or identifier")
    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return statements


def statement_type(statement: str) -> str:
    match = re.match(r"\s*([A-Za-z]+)", statement)
    return match.group(1).upper() if match else "UNKNOWN"


def contains_dangerous_read_construct(sql: str) -> bool:
    return bool(
        re.search(
            r"\b(?:INSERT|UPDATE|DELETE|REPLACE|MERGE|CREATE|ALTER|DROP|TRUNCATE|RENAME|"
            r"GRANT|REVOKE|CALL|DO|LOAD|HANDLER|LOCK|UNLOCK|COMMIT)\b|"
            r"\bFOR\s+(?:UPDATE|SHARE)\b|\bLOCK\s+IN\s+SHARE\s+MODE\b|"
            r"\bINTO\s+(?:OUTFILE|DUMPFILE|@)|"
            r"\b(?:GET_LOCK|RELEASE_LOCK|LOAD_FILE|SLEEP|BENCHMARK)\s*\(",
            sql,
        )
    )


def is_normalized_read_only_verification_statement(statement: str) -> bool:
    normalized = statement.upper()
    kind = statement_type(normalized)
    if kind == "SELECT":
        return not contains_dangerous_read_construct(normalized)
    if normalized in {
        "SET SESSION TRANSACTION READ ONLY",
        "START TRANSACTION READ ONLY",
        "ROLLBACK",
        "SET NAMES UTF8MB4",
    }:
        return True
    assignment = re.fullmatch(r"SET\s+@T0014_[A-Z0-9_]+\s*:=\s*(.+)", normalized, flags=re.DOTALL)
    if not assignment:
        return False
    expression = assignment.group(1)
    if ":=" in expression or contains_dangerous_read_construct(expression):
        return False
    return bool(
        re.fullmatch(r"\(\s*SELECT\b.+\)", expression, flags=re.DOTALL)
        or re.fullmatch(r"CASE\b.+\bEND", expression, flags=re.DOTALL)
    )


def is_read_only_verification_statement(statement: str) -> bool:
    try:
        statements = split_sql(statement)
    except SqlLexicalError:
        return False
    return len(statements) == 1 and is_normalized_read_only_verification_statement(statements[0])


def verify_sql_is_read_only(text: str) -> bool:
    try:
        statements = split_sql(text)
    except SqlLexicalError:
        return False
    return bool(statements) and all(is_normalized_read_only_verification_statement(statement) for statement in statements)


def load_classifier_probe_cases() -> list[tuple[str, str, bool]]:
    test_root = Path(__file__).resolve().parent.parent
    probe_path = test_root / "t0014-sql-classifier-probes-final.json"
    payload = json.loads(probe_path.read_text(encoding="utf-8"))
    cases = payload["cases"]
    if payload.get("probeCount") != 62 or len(cases) != 62:
        raise AssertionError(f"expected 62 classifier probes, found {len(cases)}")
    loaded: list[tuple[str, str, bool]] = []
    for case in cases:
        sql = case.get("sql")
        if sql is None:
            sql = (test_root.parent / "实施" / case["sqlFile"]).read_text(encoding="utf-8")
        loaded.append((case["name"], sql, bool(case["expectedReadOnly"])))
    return loaded


def run_classifier_self_tests() -> dict[str, int]:
    positive_cases = [
        "\n-- prepare session\n  SET   SESSION TRANSACTION READ ONLY  ;;; # done\n",
        "/* begin */\n START TRANSACTION   READ ONLY ; -- done\n",
        "# query\n  SELECT 1  ;;; /* done */",
        "/* finish */\n ROLLBACK ; -- done\n",
        "SET NAMES utf8mb4;",
        "SET @t0014_old_active_questions := (SELECT COUNT(*) FROM example WHERE id IN (1, 2));",
        "SET @t0014_new_active_questions := (SELECT COUNT(*) FROM example WHERE id IN (3, 4));",
        "SET @t0014_state := CASE WHEN @t0014_old_active_questions = 2 THEN 'old' ELSE 'final' END;",
        "SELECT category_id, COUNT(*) FROM example WHERE tenant_id = 1 GROUP BY category_id;",
        "SELECT '-- text; # text', '/* text */', `identifier;with-comment-like--text` FROM example;",
        "SELECT 'it''s safe; /* text */', \"a \"\"quoted\"\" value\";",
        "SET SESSION TRANSACTION READ ONLY; START TRANSACTION READ ONLY; SELECT 1; ROLLBACK;",
    ]
    negative_cases = [
        "UPDATE example SET value = 1;",
        "DELETE FROM example;",
        "INSERT INTO example VALUES (1);",
        "COMMIT;",
        "CREATE TABLE example (id INT);",
        "CALL unknown_statement();",
        "SET autocommit = 1;",
        "SET sql_log_bin = 0;",
        "SET @t0014_x := (SELECT id FROM example FOR UPDATE);",
        "SET @t0014_x := (SELECT 'UPDATE');",
        "SET @other_x := (SELECT 1);",
        "SELECT id FROM example FOR UPDATE;",
        "SELECT id FROM example FOR SHARE;",
        "SELECT id FROM example LOCK IN SHARE MODE;",
        "SELECT value FROM example INTO OUTFILE '/tmp/t0014.txt';",
        "SELECT value FROM example INTO DUMPFILE '/tmp/t0014.bin';",
        "SELECT 1 INTO @t0014_x;",
        "SELECT GET_LOCK('t0014', 1);",
        "SELECT LOAD_FILE('/tmp/t0014.txt');",
        "SELECT /*+ MAX_EXECUTION_TIME(1000) */ 1;",
        "SELECT 'unterminated;",
        'SELECT "unterminated;',
        "SELECT `unterminated;",
        "START TRANSACTION;",
        "-- comments only\n",
        "SELECT 1; COMMIT;",
    ]
    failed_positive = [case for case in positive_cases if not verify_sql_is_read_only(case)]
    failed_negative = [case for case in negative_cases if verify_sql_is_read_only(case)]
    probe_cases = load_classifier_probe_cases()
    failed_probes = [
        name for name, sql, expected in probe_cases if verify_sql_is_read_only(sql) != expected
    ]
    if failed_positive or failed_negative or failed_probes:
        raise AssertionError(
            "classifier self-test failed: "
            f"positive={failed_positive!r}, negative={failed_negative!r}, probes={failed_probes!r}"
        )
    probe_positive = sum(expected for _, _, expected in probe_cases)
    return {
        "positive": len(positive_cases) + probe_positive,
        "negative": len(negative_cases) + len(probe_cases) - probe_positive,
        "probeCount": len(probe_cases),
    }


def contains_all_ids(text: str, ids: Sequence[int]) -> bool:
    return all(re.search(rf"(?<!\d){value}(?!\d)", text) for value in ids)


def hardcoded_passwords_in_python(path: Path) -> list[int]:
    hits: list[int] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in {"password", "passwd", "pwd"}:
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                hits.append(node.lineno)
    return hits


def static_sql_review(implementation_dir: Path, backup: dict[str, Any]) -> dict[str, Any]:
    update_path = next(implementation_dir.glob("*-dml-update_category_13_assessment.sql"))
    rollback_path = next(implementation_dir.glob("*-dml-rollback_category_13_assessment.sql"))
    verify_path = implementation_dir / "verify-category-13.sql"
    generator_path = implementation_dir / "generate_and_execute_t0014.py"
    update_text = update_path.read_text(encoding="utf-8")
    rollback_text = rollback_path.read_text(encoding="utf-8")
    verify_text = verify_path.read_text(encoding="utf-8")
    update_statements = split_sql(update_text)
    rollback_statements = split_sql(rollback_text)
    update_writes = [s for s in update_statements if statement_type(s) in {"INSERT", "UPDATE", "DELETE"}]
    rollback_writes = [s for s in rollback_statements if statement_type(s) in {"INSERT", "UPDATE", "DELETE"}]

    def bounded(statement: str, rollback: bool) -> bool:
        kind = statement_type(statement)
        normalized = re.sub(r"\s+", " ", statement).upper()
        table_match = re.match(r"\s*(?:INSERT\s+IGNORE\s+INTO|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([A-Z0-9_]+)", normalized)
        if not table_match:
            return False
        table = table_match.group(1).lower()
        if table not in ALLOWED_TABLES - {"yj_practice_exercises_answer_child"}:
            return False
        if kind == "INSERT":
            return not rollback and "TENANT_ID" in normalized and "VALUES" in normalized and "T0014_V3_20260818" in normalized
        if " WHERE " not in normalized or "TENANT_ID = 1" not in normalized or "ID IN (" not in normalized:
            return False
        if table == "yj_practice_exercises" and "CATEGORY_ID = 13" not in normalized:
            return False
        if table == "yj_practice_exercises_answer" and "EXERCISES_ID IN (" not in normalized:
            return False
        if kind == "DELETE" and "CREATOR = 'T0014_V3_20260818'" not in normalized:
            return False
        return True

    scope = backup["scope"]
    backup_ids_match = (
        sorted(row["id"] for row in backup["tables"]["yj_practice_setp"]) == sorted(scope["oldStepIds"])
        and sorted(row["id"] for row in backup["tables"]["yj_practice_exercises"]) == sorted(scope["oldQuestionIds"])
        and sorted(row["id"] for row in backup["tables"]["yj_practice_exercises_answer"]) == sorted(scope["oldAnswerIds"])
        and sorted(row["id"] for row in backup["tables"]["yj_practice_exercises_answer_child"]) == sorted(scope["oldChildAnswerIds"])
    )
    credential_hits = []
    for path in implementation_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".sql", ".json", ".md", ".py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"jdbc:mysql://|mysql://", text, flags=re.IGNORECASE):
            credential_hits.append(path.name)
    python_password_hits = hardcoded_passwords_in_python(generator_path)
    update_only_soft_deletes = all(
        statement_type(s) != "UPDATE" or re.search(r"\bSET\s+deleted\s*=\s*b?'1'", s, flags=re.IGNORECASE)
        for s in update_writes
    )
    review = {
        "updateFile": update_path.name,
        "rollbackFile": rollback_path.name,
        "verifyFile": verify_path.name,
        "updateWriteStatementCount": len(update_writes),
        "rollbackWriteStatementCount": len(rollback_writes),
        "allUpdateWritesBounded": all(bounded(statement, False) for statement in update_writes),
        "allRollbackWritesBounded": all(bounded(statement, True) for statement in rollback_writes),
        "updateOnlySoftDeletesHistoricalRows": update_only_soft_deletes,
        "updateHasNoDelete": all(statement_type(s) != "DELETE" for s in update_writes),
        "stepReverseReferenceAssertion": "assert_old_steps_not_shared" in update_text
        and "NOT (category_id = 13 AND tenant_id = 1)" in update_text,
        "idempotencyProtection": "@t0014_mode" in update_text
        and update_text.count("INSERT IGNORE INTO") == 3
        and "IF(@t0014_mode = 1" in update_text,
        "backupMatchesRollbackScope": backup_ids_match
        and contains_all_ids(rollback_text, scope["oldStepIds"] + scope["oldQuestionIds"] + scope["oldAnswerIds"])
        and contains_all_ids(rollback_text, scope["newStepIds"] + scope["newQuestionIds"] + scope["newAnswerIds"]),
        "verifyIsReadOnly": verify_sql_is_read_only(verify_text),
        "noFuzzyNameWrite": not any(
            re.search(r"\bWHERE\b[^;]*(?:SET[P]?_NAME|QUESTION_STEM|ANSWER_CONTENT)\s+(?:LIKE|=)", s, flags=re.IGNORECASE | re.DOTALL)
            for s in update_writes + rollback_writes
        ),
        "credentialFiles": credential_hits,
        "hardcodedPythonPasswordLines": python_password_hits,
    }
    review["pass"] = all(
        [
            review["allUpdateWritesBounded"],
            review["allRollbackWritesBounded"],
            review["updateOnlySoftDeletesHistoricalRows"],
            review["updateHasNoDelete"],
            review["stepReverseReferenceAssertion"],
            review["idempotencyProtection"],
            review["backupMatchesRollbackScope"],
            review["verifyIsReadOnly"],
            review["noFuzzyNameWrite"],
            not credential_hits,
            not python_password_hits,
        ]
    )
    return review


def expected_mapping_rows(mapping: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    questions: list[dict[str, Any]] = []
    answers: list[dict[str, Any]] = []
    for item in mapping["questions"]:
        questions.append(
            {
                "id": item["questionId"],
                "step_id": item["stepId"],
                "category_id": CATEGORY_ID,
                "question_stem": item["questionStem"],
                "question_type": item["questionType"],
                "question_status": item["questionStatus"],
                "score": item["score"],
                "sort_no": item["sortNo"],
                "correct_memo": item["correctMemo"],
                "tenant_id": TENANT_ID,
                "deleted": 0,
            }
        )
        for option in item["options"]:
            answers.append(
                {
                    "id": option["answerId"],
                    "exercises_id": item["questionId"],
                    "question_type": option["questionType"],
                    "answer_code": option["answerCode"],
                    "answer_content": option["answerContent"],
                    "is_correct": option["isCorrect"],
                    "sort_no": option["sortNo"],
                    "tenant_id": TENANT_ID,
                    "deleted": 0,
                }
            )
    return questions, answers


def parse_execution_log(implementation_dir: Path) -> dict[str, Any]:
    text = (implementation_dir / "execution-log.md").read_text(encoding="utf-8")
    target_matches = re.findall(r"^- 最终目标哈希：`(\{.*\})`$", text, flags=re.MULTILINE)
    non_target_matches = re.findall(r"^- 非目标零变化：`(\{.*\})`$", text, flags=re.MULTILINE)
    return {
        "targetHashes": json.loads(target_matches[-1]) if target_matches else None,
        "nonTarget": json.loads(non_target_matches[-1]) if non_target_matches else None,
        "workflowEvidencePresent": all(
            marker in text
            for marker in ["第一次更新：成功", "回滚演练：成功", "第二次更新：成功", "幂等重跑：成功"]
        ),
        "failedAttemptRecorded": "执行失败" in text and "Cannot execute statement in a READ ONLY transaction" in text,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    backup = json.loads(args.backup.read_text(encoding="utf-8"))
    expected_questions, expected_answers = expected_mapping_rows(mapping)
    question_ids = [row["id"] for row in expected_questions]
    answer_ids = [row["id"] for row in expected_answers]
    step_ids = [step["stepId"] for step in mapping["steps"]]
    connection, endpoint = connect_read_only(args.config)
    try:
        with connection.cursor() as cursor:
            identity = query(
                cursor,
                "SELECT DATABASE() AS database_name, @@tx_read_only AS transaction_read_only",
            )[0]
            category_rows = query(
                cursor,
                "SELECT id, tenant_id, deleted + 0 AS deleted FROM yj_practice_category "
                "WHERE id = %s AND tenant_id = %s AND deleted = b'0'",
                (CATEGORY_ID, TENANT_ID),
            )
            steps = query(
                cursor,
                "SELECT id, tenant_id, setp_name, setp_status + 0 AS setp_status, sort_no, deleted + 0 AS deleted "
                f"FROM yj_practice_setp WHERE id IN ({placeholders(step_ids)}) AND tenant_id = %s "
                "AND deleted = b'0' ORDER BY sort_no, id",
                (*step_ids, TENANT_ID),
            )
            actual_questions = query(
                cursor,
                "SELECT id, step_id, category_id, question_stem, question_type, question_status + 0 AS question_status, "
                "score, sort_no, correct_memo, tenant_id, deleted + 0 AS deleted "
                "FROM yj_practice_exercises WHERE category_id = %s AND tenant_id = %s AND deleted = b'0' "
                "ORDER BY sort_no, id",
                (CATEGORY_ID, TENANT_ID),
            )
            actual_answers = query(
                cursor,
                "SELECT id, exercises_id, question_type, answer_code, answer_content, is_correct + 0 AS is_correct, "
                "sort_no, tenant_id, deleted + 0 AS deleted FROM yj_practice_exercises_answer "
                f"WHERE exercises_id IN ({placeholders(question_ids)}) AND tenant_id = %s AND deleted = b'0' "
                "ORDER BY exercises_id, sort_no, id",
                (*question_ids, TENANT_ID),
            )
            child_rows = query(
                cursor,
                "SELECT c.id, c.answer_id, c.tenant_id FROM yj_practice_exercises_answer_child c "
                "JOIN yj_practice_exercises_answer a ON a.id = c.answer_id AND a.tenant_id = %s AND a.deleted = b'0' "
                f"WHERE a.id IN ({placeholders(answer_ids)}) AND c.tenant_id = %s AND c.deleted = b'0' ORDER BY c.id",
                (TENANT_ID, *answer_ids, TENANT_ID),
            )
            step_orphans = query(
                cursor,
                "SELECT q.id FROM yj_practice_exercises q LEFT JOIN yj_practice_setp s "
                "ON s.id = q.step_id AND s.tenant_id = q.tenant_id AND s.deleted = b'0' "
                "WHERE q.category_id = %s AND q.tenant_id = %s AND q.deleted = b'0' AND s.id IS NULL ORDER BY q.id",
                (CATEGORY_ID, TENANT_ID),
            )
            answer_orphans = query(
                cursor,
                "SELECT a.id FROM yj_practice_exercises_answer a LEFT JOIN yj_practice_exercises q "
                "ON q.id = a.exercises_id AND q.tenant_id = a.tenant_id AND q.deleted = b'0' "
                f"WHERE a.id IN ({placeholders(answer_ids)}) AND a.tenant_id = %s AND a.deleted = b'0' "
                "AND q.id IS NULL ORDER BY a.id",
                (*answer_ids, TENANT_ID),
            )
            child_orphans = query(
                cursor,
                "SELECT c.id FROM yj_practice_exercises_answer_child c LEFT JOIN yj_practice_exercises_answer a "
                "ON a.id = c.answer_id AND a.tenant_id = c.tenant_id AND a.deleted = b'0' "
                f"WHERE c.answer_id IN ({placeholders(answer_ids)}) AND c.tenant_id = %s AND c.deleted = b'0' "
                "AND a.id IS NULL ORDER BY c.id",
                (*answer_ids, TENANT_ID),
            )

            exclusions = {
                "yj_practice_setp": backup["scope"]["oldStepIds"] + backup["scope"]["newStepIds"],
                "yj_practice_exercises": backup["scope"]["oldQuestionIds"] + backup["scope"]["newQuestionIds"],
                "yj_practice_exercises_answer": backup["scope"]["oldAnswerIds"] + backup["scope"]["newAnswerIds"],
                "yj_practice_exercises_answer_child": backup["scope"]["oldChildAnswerIds"],
            }
            non_target = {}
            for table, ids in exclusions.items():
                rows = rows_excluding_ids(cursor, table, ids)
                non_target[table] = {"rowCount": len(rows), "sha256": canonical_hash(rows)}
            target_hashes = {
                "yj_practice_setp": canonical_hash(rows_for_ids(cursor, "yj_practice_setp", step_ids)),
                "yj_practice_exercises": canonical_hash(rows_for_ids(cursor, "yj_practice_exercises", question_ids)),
                "yj_practice_exercises_answer": canonical_hash(rows_for_ids(cursor, "yj_practice_exercises_answer", answer_ids)),
            }
        connection.rollback()
    finally:
        connection.close()

    step_counts = Counter(row["step_id"] for row in actual_questions)
    actual_step_counts = [step_counts.get(step_id, 0) for step_id in step_ids]
    answer_sorts = {}
    for row in actual_answers:
        answer_sorts.setdefault(row["exercises_id"], []).append(row["sort_no"])
    a3_questions = [item for item in mapping["questions"] if item["sourceParentId"] == "A3"]
    a3_valid = len(a3_questions) == 8 and all(
        len(item["options"]) == 3
        and [option["answerCode"] for option in item["options"]] == ["A", "B", "C"]
        and [option["sortNo"] for option in item["options"]] == [1, 2, 3]
        for item in a3_questions
    )
    expected_non_target = backup["hashes"]["nonTarget"]
    log = parse_execution_log(args.implementation_dir)
    sql_review = static_sql_review(args.implementation_dir, backup)
    checks = {
        "databaseIdentity": identity["database_name"] == "yunjikeji" and int(identity["transaction_read_only"]) == 1,
        "categoryUnique": len(category_rows) == 1,
        "mappingMetadata": mapping["categoryId"] == CATEGORY_ID
        and mapping["tenantId"] == TENANT_ID
        and mapping["questionCount"] == 48
        and mapping["optionCount"] == 243,
        "stepsExact": [row["setp_name"] for row in steps] == EXPECTED_STEP_NAMES
        and [row["sort_no"] for row in steps] == list(range(1, 7))
        and all(row["setp_status"] == 1 and row["tenant_id"] == TENANT_ID for row in steps),
        "stepQuestionCounts": actual_step_counts == EXPECTED_STEP_COUNTS,
        "questionsMatchMapping": actual_questions == expected_questions,
        "answersMatchMapping": actual_answers == expected_answers,
        "a3SplitExact": a3_valid,
        "questionSortContinuous": [row["sort_no"] for row in actual_questions] == list(range(1, 49)),
        "answerSortContinuous": all(
            sorts == list(range(1, len(sorts) + 1)) for sorts in answer_sorts.values()
        ),
        "questionStateAndScore": all(row["question_status"] == 1 and row["score"] == 0 for row in actual_questions),
        "standardAnswersEmpty": all(row["is_correct"] == 0 for row in actual_answers),
        "noActiveChildAnswers": not child_rows,
        "noOrphans": not step_orphans and not answer_orphans and not child_orphans,
        "nonTargetBaselineUnchanged": non_target == expected_non_target,
        "executionLogMatchesCurrentTarget": log["targetHashes"] == target_hashes,
        "executionLogMatchesCurrentNonTarget": log["nonTarget"] == non_target,
        "executionWorkflowEvidence": log["workflowEvidencePresent"] and log["failedAttemptRecorded"],
        "sqlStaticReview": sql_review["pass"],
    }
    return {
        "taskId": "T0014",
        "executedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "read-only",
        "overallPass": all(checks.values()),
        "endpoint": endpoint,
        "checks": checks,
        "statistics": {
            "steps": len(steps),
            "questions": len(actual_questions),
            "answers": len(actual_answers),
            "activeChildAnswers": len(child_rows),
            "stepQuestionCounts": actual_step_counts,
            "questionTypes": dict(sorted(Counter(row["question_type"] for row in actual_questions).items())),
            "stepOrphans": len(step_orphans),
            "answerOrphans": len(answer_orphans),
            "childAnswerOrphans": len(child_orphans),
        },
        "targetHashes": target_hashes,
        "nonTarget": non_target,
        "expectedNonTarget": expected_non_target,
        "sqlReview": sql_review,
        "executionLogReview": log,
    }


def main() -> None:
    args = parse_args()
    if args.self_test:
        counts = run_classifier_self_tests()
        print(json.dumps({"selfTestPass": True, **counts}, ensure_ascii=False))
        return
    result: dict[str, Any]
    try:
        result = run(args)
    except Exception as error:
        result = {
            "taskId": "T0014",
            "executedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "mode": "read-only",
            "overallPass": False,
            "error": {"type": type(error).__name__, "message": str(error)},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"overallPass": result["overallPass"], "output": str(args.output.resolve())}, ensure_ascii=False))
    raise SystemExit(0 if result["overallPass"] else 1)


if __name__ == "__main__":
    main()
