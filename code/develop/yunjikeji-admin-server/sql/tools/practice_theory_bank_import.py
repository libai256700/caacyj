#!/usr/bin/env python3
"""Precheck and optionally import practice theory bank markdown files."""

from __future__ import annotations

import argparse
import html
import json
import re
import socket
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


QUESTION_START_RE = re.compile(r"^\s*(\d+)[\.．]\s*(.*)$")
OPTION_MARK_RE = re.compile(r"(?:^|(?<=\s))([A-D])\.\s*")
ANSWER_LINE_RE = re.compile(r"^参考答案[:：]\s*(.+)$")
ANALYSIS_LINE_RE = re.compile(r"^解析[:：]\s*(.*)$")
DEFAULT_LIMITS = {
    "yj_practice_category.category_name": 100,
    "yj_practice_exercises.question_stem": 800,
    "yj_practice_exercises.question_type": 32,
    "yj_practice_exercises.correct_memo": 2000,
    "yj_practice_exercises_answer.question_type": 32,
    "yj_practice_exercises_answer.answer_code": 10,
    "yj_practice_exercises_answer.answer_content": 255,
    "yj_practice_exercises_answer_child.question_type": 32,
    "yj_practice_exercises_answer_child.answer_content": 255,
}
DEFAULT_TARGET_CATEGORY_IDS = tuple(range(1, 12))
TARGET_TABLES = (
    "yj_practice_category",
    "yj_practice_exercises",
    "yj_practice_exercises_answer",
    "yj_practice_exercises_answer_child",
)
SUPPORTED_IMPORT_TABLES = (
    "yj_practice_category",
    "yj_practice_exercises",
    "yj_practice_exercises_answer",
    "yj_practice_exercises_answer_child",
)
APPLY_CONFIRM_TOKEN = "REPLACE_PRACTICE_THEORY_BANK"
NON_PROD_ENVIRONMENTS = {"local", "dev", "test"}
INCOMPLETE_QUESTION_CODES = frozenset({"MISSING_STEM", "MISSING_ANSWER", "DUPLICATE_ANSWER_LINE"})
REQUIRED_CORRECT_MEMO_LENGTH = 761


@dataclass
class Option:
    code: str
    content: str
    line_no: int


@dataclass
class Question:
    number: int
    start_line: int
    stem_parts: list[str] = field(default_factory=list)
    options: dict[str, Option] = field(default_factory=dict)
    option_order: list[str] = field(default_factory=list)
    answer_raw: str | None = None
    answer_code: str | None = None
    answer_line_no: int | None = None
    analysis_parts: list[str] = field(default_factory=list)
    duplicate_answer_lines: list[int] = field(default_factory=list)
    current_option_code: str | None = None

    def stem(self) -> str:
        return join_parts(self.stem_parts)

    def analysis(self) -> str:
        return join_parts(self.analysis_parts)


@dataclass
class CategoryDocument:
    category_name: str
    path: Path
    questions: list[Question] = field(default_factory=list)


@dataclass
class Violation:
    severity: str
    code: str
    message: str
    file: str | None = None
    line: int | None = None
    question_number: int | None = None
    category_name: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.file is not None:
            payload["file"] = self.file
        if self.line is not None:
            payload["line"] = self.line
        if self.question_number is not None:
            payload["questionNumber"] = self.question_number
        if self.category_name is not None:
            payload["categoryName"] = self.category_name
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class ColumnMeta:
    table_name: str
    column_name: str
    data_type: str
    character_maximum_length: int | None
    is_nullable: bool
    column_key: str | None
    extra: str | None


@dataclass
class DatabaseSnapshot:
    connected: bool = False
    host: str | None = None
    port: int | None = None
    database: str | None = None
    metadata_source: str = "fallback"
    column_meta: dict[str, ColumnMeta] = field(default_factory=dict)
    category_rows: list[dict[str, Any]] = field(default_factory=list)
    category_matches: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    answer_child_count: int | None = None
    foreign_keys: list[dict[str, Any]] = field(default_factory=list)
    port_open: bool | None = None


def join_parts(parts: list[str]) -> str:
    return "\n".join(part for part in parts if part).strip()


def normalize_line(text: str) -> str:
    normalized = html.unescape(text.rstrip("\r\n"))
    normalized = normalized.replace("\u00a0", " ").replace("\u3000", " ")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value


def split_option_segments(line: str) -> tuple[str, list[tuple[str, str]]]:
    matches = list(OPTION_MARK_RE.finditer(line))
    if not matches:
        return line, []
    prefix = line[: matches[0].start()].strip()
    segments: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        code = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
        content = line[start:end].strip()
        segments.append((code, content))
    return prefix, segments


def extract_single_answer_code(answer_text: str) -> tuple[str | None, list[str]]:
    codes = re.findall(r"[A-D]", answer_text.upper())
    unique_codes = list(dict.fromkeys(codes))
    return (unique_codes[0] if len(unique_codes) == 1 else None, unique_codes)


def should_start_question(
    question: Question | None,
    state: str,
    next_number: int,
    allow_number_reset: bool,
) -> bool:
    if question is None:
        return True
    if allow_number_reset and next_number == 1:
        return True
    if state == "analysis":
        return True
    return (
        question.answer_raw is not None
        or (question.options and question.answer_raw is None)
    )


def parse_markdown_file(path: Path) -> tuple[CategoryDocument, list[Violation]]:
    document = CategoryDocument(category_name=path.stem, path=path)
    violations: list[Violation] = []
    current: Question | None = None
    state = "idle"
    allow_number_reset = False

    def finalize_question(question: Question | None) -> None:
        if question is None:
            return
        if not question.stem():
            violations.append(
                Violation(
                    severity="error",
                    code="MISSING_STEM",
                    message="题干缺失，已阻断导入。",
                    file=str(path),
                    line=question.start_line,
                    question_number=question.number,
                    category_name=document.category_name,
                )
            )
        if not question.options:
            violations.append(
                Violation(
                    severity="error",
                    code="MISSING_OPTIONS",
                    message="题目没有解析出任何答案选项。",
                    file=str(path),
                    line=question.start_line,
                    question_number=question.number,
                    category_name=document.category_name,
                )
            )
        if question.answer_raw is None:
            violations.append(
                Violation(
                    severity="error",
                    code="MISSING_ANSWER",
                    message="题目缺少参考答案。",
                    file=str(path),
                    line=question.start_line,
                    question_number=question.number,
                    category_name=document.category_name,
                )
            )
        if question.duplicate_answer_lines:
            violations.append(
                Violation(
                    severity="error",
                    code="DUPLICATE_ANSWER_LINE",
                    message="题目存在多条参考答案记录，已阻断导入。",
                    file=str(path),
                    line=question.duplicate_answer_lines[0],
                    question_number=question.number,
                    category_name=document.category_name,
                    details={"lines": question.duplicate_answer_lines},
                )
            )
        if question.answer_raw is not None:
            answer_code, unique_codes = extract_single_answer_code(question.answer_raw)
            if answer_code is None:
                violations.append(
                    Violation(
                        severity="error",
                        code="INVALID_ANSWER",
                        message="参考答案不是唯一的 A-D 单选答案，已阻断导入。",
                        file=str(path),
                        line=question.answer_line_no,
                        question_number=question.number,
                        category_name=document.category_name,
                        details={"answerRaw": question.answer_raw, "codes": unique_codes},
                    )
                )
            else:
                question.answer_code = answer_code
                if answer_code not in question.options:
                    violations.append(
                        Violation(
                            severity="error",
                            code="ANSWER_OPTION_MISMATCH",
                            message="参考答案未在解析出的选项中出现，已阻断导入。",
                            file=str(path),
                            line=question.answer_line_no,
                            question_number=question.number,
                            category_name=document.category_name,
                            details={"answerCode": answer_code, "optionCodes": question.option_order},
                        )
                    )
        document.questions.append(question)

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = normalize_line(raw_line)
        if not stripped:
            continue
        if "新增真题" in stripped:
            allow_number_reset = True
            continue
        question_start = QUESTION_START_RE.match(stripped)
        if question_start and should_start_question(
            current,
            state,
            int(question_start.group(1)),
            allow_number_reset,
        ):
            finalize_question(current)
            current = Question(number=int(question_start.group(1)), start_line=line_no)
            remainder = question_start.group(2).strip()
            if remainder:
                current.stem_parts.append(remainder)
            state = "stem"
            allow_number_reset = False
            continue

        if current is None:
            continue

        answer_match = ANSWER_LINE_RE.match(stripped)
        if answer_match:
            if current.answer_raw is not None:
                current.duplicate_answer_lines.append(line_no)
            else:
                current.answer_raw = answer_match.group(1).strip()
                current.answer_line_no = line_no
            state = "answer"
            continue

        analysis_match = ANALYSIS_LINE_RE.match(stripped)
        if analysis_match:
            current.analysis_parts.append(analysis_match.group(1).strip())
            state = "analysis"
            continue

        if state == "analysis":
            current.analysis_parts.append(stripped)
            continue

        prefix, segments = split_option_segments(stripped)
        if segments:
            if current.answer_raw is not None or state == "analysis":
                next_number = (current.number + 1) if current else 1
                finalize_question(current)
                current = Question(number=next_number, start_line=line_no)
                state = "options"
            if prefix:
                if current.current_option_code:
                    option = current.options[current.current_option_code]
                    option.content = f"{option.content} {prefix}".strip()
                else:
                    current.stem_parts.append(prefix)
            for code, content in segments:
                if code in current.options:
                    violations.append(
                        Violation(
                            severity="error",
                            code="DUPLICATE_OPTION_CODE",
                            message="同一题目中出现重复的选项编号。",
                            file=str(path),
                            line=line_no,
                            question_number=current.number,
                            category_name=document.category_name,
                            details={"optionCode": code},
                        )
                    )
                    if content:
                        current.options[code].content = f"{current.options[code].content} {content}".strip()
                else:
                    current.options[code] = Option(code=code, content=content, line_no=line_no)
                    current.option_order.append(code)
                current.current_option_code = code
            state = "options"
            continue

        if state == "options" and current.current_option_code:
            option = current.options[current.current_option_code]
            option.content = f"{option.content} {stripped}".strip()
            continue

        current.stem_parts.append(stripped)

    finalize_question(current)
    return document, violations


def apply_length_checks(
    documents: list[CategoryDocument], limits: dict[str, int], violations: list[Violation]
) -> None:
    for document in documents:
        category_limit = limits.get("yj_practice_category.category_name")
        if category_limit and len(document.category_name) > category_limit:
            violations.append(
                Violation(
                    severity="error",
                    code="CATEGORY_NAME_TOO_LONG",
                    message="分类名称超出目标字段长度，已阻断导入。",
                    file=str(document.path),
                    line=1,
                    category_name=document.category_name,
                    details={"length": len(document.category_name), "limit": category_limit},
                )
            )
        for question in document.questions:
            field_lengths = {
                "yj_practice_exercises.question_stem": len(question.stem()),
                "yj_practice_exercises.correct_memo": len(question.analysis()),
                "yj_practice_exercises.question_type": len("single_choice"),
            }
            for field_name, value_length in field_lengths.items():
                limit = limits.get(field_name)
                if limit is not None and value_length > limit:
                    violations.append(
                        Violation(
                            severity="error",
                            code="FIELD_TOO_LONG",
                            message="字段长度超限，已阻断导入。",
                            file=str(document.path),
                            line=question.start_line,
                            question_number=question.number,
                            category_name=document.category_name,
                            details={"field": field_name, "length": value_length, "limit": limit},
                        )
                    )
            for code in question.option_order:
                option = question.options[code]
                answer_limit = limits.get("yj_practice_exercises_answer.answer_content")
                if answer_limit is not None and len(option.content) > answer_limit:
                    violations.append(
                        Violation(
                            severity="error",
                            code="FIELD_TOO_LONG",
                            message="答案内容超出目标字段长度，已阻断导入。",
                            file=str(document.path),
                            line=option.line_no,
                            question_number=question.number,
                            category_name=document.category_name,
                            details={
                                "field": "yj_practice_exercises_answer.answer_content",
                                "answerCode": code,
                                "length": len(option.content),
                                "limit": answer_limit,
                            },
                        )
                    )


def summarize_documents(documents: list[CategoryDocument]) -> dict[str, Any]:
    answer_distribution = Counter()
    option_distribution = Counter()
    question_total = 0
    option_total = 0
    for document in documents:
        question_total += len(document.questions)
        for question in document.questions:
            if question.answer_code:
                answer_distribution[question.answer_code] += 1
            option_total += len(question.option_order)
            option_distribution[str(len(question.option_order))] += 1
    return {
        "files": len(documents),
        "categories": len(documents),
        "questions": question_total,
        "options": option_total,
        "answerDistribution": dict(answer_distribution),
        "optionCountDistribution": dict(option_distribution),
    }


def get_workspace_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("workspace root not found from script path")


def default_source_dir(workspace_root: Path) -> Path:
    return (
        workspace_root.parent
        / "knowledge-graph"
        / "-APP--main"
        / "-APP--main"
        / "knowledge_base"
        / "理论题库"
    )


def probe_port(host: str, port: int, timeout_seconds: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def load_pymysql():
    try:
        import pymysql  # type: ignore

        return pymysql
    except ImportError as exc:
        raise RuntimeError("缺少 pymysql，无法执行数据库元数据预检或导入。") from exc


def fetch_database_snapshot(args: argparse.Namespace, documents: list[CategoryDocument]) -> DatabaseSnapshot:
    snapshot = DatabaseSnapshot(
        connected=False,
        host=args.db_host,
        port=args.db_port,
        database=args.db_name,
        port_open=probe_port(args.db_host, args.db_port) if args.db_host and args.db_port else None,
    )
    if not args.db_host:
        return snapshot

    pymysql = load_pymysql()
    password = resolve_db_password(args)
    connection = pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=password,
        database=args.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        snapshot.connected = True
        snapshot.metadata_source = "database"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name, column_name, data_type, character_maximum_length,
                       is_nullable, column_key, extra
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name IN (%s, %s, %s, %s)
                """,
                (args.db_name, *TARGET_TABLES),
            )
            for row in cursor.fetchall():
                key = f"{row['table_name']}.{row['column_name']}"
                snapshot.column_meta[key] = ColumnMeta(
                    table_name=row["table_name"],
                    column_name=row["column_name"],
                    data_type=row["data_type"],
                    character_maximum_length=row["character_maximum_length"],
                    is_nullable=row["is_nullable"] == "YES",
                    column_key=row.get("column_key"),
                    extra=row.get("extra"),
                )
            cursor.execute(
                """
                SELECT kcu.table_name, kcu.column_name, kcu.referenced_table_name,
                       kcu.referenced_column_name
                FROM information_schema.key_column_usage kcu
                WHERE kcu.table_schema = %s
                  AND kcu.table_name IN (%s, %s, %s, %s)
                  AND kcu.referenced_table_name IS NOT NULL
                ORDER BY kcu.table_name, kcu.column_name
                """,
                (args.db_name, *TARGET_TABLES),
            )
            snapshot.foreign_keys = list(cursor.fetchall())
            category_names = [document.category_name for document in documents]
            placeholders = ", ".join(["%s"] * len(category_names))
            cursor.execute(
                f"""
                SELECT id, category_name, category_status, field_type, catalog_type, sort_no
                FROM yj_practice_category
                WHERE deleted = b'0'
                  AND category_name IN ({placeholders})
                ORDER BY category_name, id
                """,
                category_names,
            )
            snapshot.category_rows = list(cursor.fetchall())
            matches: dict[str, list[dict[str, Any]]] = {name: [] for name in category_names}
            for row in snapshot.category_rows:
                matches.setdefault(row["category_name"], []).append(row)
            snapshot.category_matches = matches
            if snapshot.category_rows:
                category_ids = [row["id"] for row in snapshot.category_rows]
                placeholders = ", ".join(["%s"] * len(category_ids))
                cursor.execute(
                    f"""
                    SELECT COUNT(1) AS total
                    FROM yj_practice_exercises_answer_child child
                    INNER JOIN yj_practice_exercises_answer answer_item
                            ON answer_item.id = child.answer_id
                           AND answer_item.deleted = b'0'
                    INNER JOIN yj_practice_exercises question
                            ON question.id = answer_item.exercises_id
                           AND question.deleted = b'0'
                    WHERE child.deleted = b'0'
                      AND question.category_id IN ({placeholders})
                    """,
                    category_ids,
                )
                snapshot.answer_child_count = int(cursor.fetchone()["total"])
            else:
                snapshot.answer_child_count = 0
    finally:
        connection.close()
    return snapshot


def resolve_db_password(args: argparse.Namespace) -> str:
    if args.db_password:
        return args.db_password
    if args.db_password_env:
        import os

        value = os.getenv(args.db_password_env)
        if not value:
            raise RuntimeError(f"环境变量 {args.db_password_env} 未设置，无法连接数据库。")
        return value
    raise RuntimeError("缺少数据库密码；请提供 --db-password 或 --db-password-env。")


def build_effective_limits(args: argparse.Namespace, snapshot: DatabaseSnapshot) -> dict[str, int]:
    limits = dict(DEFAULT_LIMITS)
    if args.correct_memo_limit is not None:
        limits["yj_practice_exercises.correct_memo"] = args.correct_memo_limit
    for key, meta in snapshot.column_meta.items():
        if meta.character_maximum_length is not None:
            limits[key] = meta.character_maximum_length
    return limits


def validate_category_mapping(
    documents: list[CategoryDocument],
    snapshot: DatabaseSnapshot,
    violations: list[Violation],
    target_category_ids: set[int],
) -> None:
    if not snapshot.connected:
        return
    for document in documents:
        rows = snapshot.category_matches.get(document.category_name, [])
        if not rows:
            violations.append(
                Violation(
                    severity="error",
                    code="CATEGORY_NOT_FOUND",
                    message="没有找到与文件名完全匹配的分类，已阻断导入。",
                    file=str(document.path),
                    category_name=document.category_name,
                )
            )
        elif len(rows) > 1:
            violations.append(
                Violation(
                    severity="error",
                    code="CATEGORY_DUPLICATED",
                    message="匹配到多个同名分类，已阻断导入。",
                    file=str(document.path),
                    category_name=document.category_name,
                    details={"matchedIds": [row["id"] for row in rows]},
                )
            )
        elif rows[0]["id"] not in target_category_ids:
            violations.append(
                Violation(
                    severity="error",
                    code="CATEGORY_ID_OUT_OF_SCOPE",
                    message="分类命中结果不在允许导入的分类 ID 范围内，已阻断导入。",
                    file=str(document.path),
                    category_name=document.category_name,
                    details={"matchedId": rows[0]["id"], "targetCategoryIds": sorted(target_category_ids)},
                )
            )
    if snapshot.answer_child_count not in (None, 0):
        violations.append(
            Violation(
                severity="error",
                code="ANSWER_CHILD_NOT_EMPTY",
                message="目标分类下存在二级答案数据，当前题库导入不支持该数据形态，已阻断导入。",
                details={"answerChildCount": snapshot.answer_child_count},
            )
        )


def validate_live_schema(snapshot: DatabaseSnapshot, violations: list[Violation]) -> None:
    if not snapshot.connected:
        return
    correct_memo_meta = snapshot.column_meta.get("yj_practice_exercises.correct_memo")
    if correct_memo_meta is None:
        violations.append(
            Violation(
                severity="error",
                code="MISSING_TARGET_COLUMN",
                message="未读取到 yj_practice_exercises.correct_memo 字段元数据，已阻断导入。",
            )
        )
    elif (
        correct_memo_meta.character_maximum_length is not None
        and correct_memo_meta.character_maximum_length < REQUIRED_CORRECT_MEMO_LENGTH
    ):
        violations.append(
            Violation(
                severity="error",
                code="CORRECT_MEMO_COLUMN_TOO_SHORT",
                message="correct_memo 字段不足以保留理论题库最长解析，已阻断导入。",
                details={
                    "length": correct_memo_meta.character_maximum_length,
                    "requiredLength": REQUIRED_CORRECT_MEMO_LENGTH,
                },
            )
        )


def allow_incomplete_questions(
    documents: list[CategoryDocument],
    violations: list[Violation],
    import_incomplete_questions: bool,
) -> tuple[list[CategoryDocument], list[Violation], list[dict[str, Any]]]:
    if not import_incomplete_questions:
        return documents, violations, []

    incomplete_questions: list[dict[str, Any]] = []
    allowed_violation_ids: set[int] = set()
    for document in documents:
        for index, question in enumerate(document.questions):
            next_start_line = (
                document.questions[index + 1].start_line if index + 1 < len(document.questions) else sys.maxsize
            )
            skip_items = [
                violation
                for violation in violations
                if violation.file == str(document.path)
                and violation.question_number == question.number
                and violation.line is not None
                and question.start_line <= violation.line < next_start_line
            ]
            codes = {item.code for item in skip_items}
            is_incomplete = bool(skip_items) and codes.issubset(INCOMPLETE_QUESTION_CODES)
            if is_incomplete:
                allowed_violation_ids.update(id(item) for item in skip_items)
                incomplete_questions.append(
                    {
                        "file": str(document.path),
                        "line": min(item.line or question.start_line for item in skip_items),
                        "questionNumber": question.number,
                        "categoryName": document.category_name,
                        "reasonCodes": [item.code for item in skip_items],
                        "reasonMessages": [item.message for item in skip_items],
                    }
                )
    remaining_violations = [violation for violation in violations if id(violation) not in allowed_violation_ids]
    return documents, remaining_violations, incomplete_questions


def parse_documents(source_dir: Path) -> tuple[list[CategoryDocument], list[Violation]]:
    if not source_dir.exists():
        raise RuntimeError(f"题库目录不存在：{source_dir}")
    documents: list[CategoryDocument] = []
    violations: list[Violation] = []
    for path in sorted(source_dir.glob("*.md")):
        document, parse_violations = parse_markdown_file(path)
        documents.append(document)
        violations.extend(parse_violations)
    if not documents:
        raise RuntimeError(f"题库目录中没有找到 Markdown 文件：{source_dir}")
    return documents, violations


def violation_counts(violations: list[Violation]) -> dict[str, int]:
    counter = Counter(violation.code for violation in violations)
    return dict(counter)


def build_report(
    args: argparse.Namespace,
    source_dir: Path,
    source_documents: list[CategoryDocument],
    import_documents: list[CategoryDocument],
    violations: list[Violation],
    incomplete_questions: list[dict[str, Any]],
    snapshot: DatabaseSnapshot,
    limits: dict[str, int],
) -> dict[str, Any]:
    source_summary = summarize_documents(source_documents)
    import_summary = summarize_documents(import_documents)
    report = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sourceDir": str(source_dir),
        "mode": "apply" if args.apply else "dry-run",
        "targetCategoryIds": list(args.target_category_ids),
        "database": {
            "connected": snapshot.connected,
            "host": snapshot.host,
            "port": snapshot.port,
            "database": snapshot.database,
            "portOpen": snapshot.port_open,
            "metadataSource": snapshot.metadata_source,
            "answerChildCount": snapshot.answer_child_count,
            "foreignKeys": json_safe(snapshot.foreign_keys),
        },
        "summary": {
            "sourceFiles": source_summary["files"],
            "sourceCategories": source_summary["categories"],
            "sourceQuestions": source_summary["questions"],
            "sourceOptions": source_summary["options"],
            "importQuestions": import_summary["questions"],
            "importOptions": import_summary["options"],
            "incompleteQuestions": len(incomplete_questions),
            "answerDistribution": import_summary["answerDistribution"],
            "optionCountDistribution": import_summary["optionCountDistribution"],
        },
        "limits": {
            "source": snapshot.metadata_source,
            "values": limits,
        },
        "categoryMappings": [
            {
                "categoryName": document.category_name,
                "file": str(document.path),
                "matchedRows": json_safe(snapshot.category_matches.get(document.category_name, [])),
            }
            for document in import_documents
        ],
        "incompleteQuestions": incomplete_questions,
        "violations": json_safe([violation.to_dict() for violation in violations]),
        "violationCounts": violation_counts(violations),
        "canApply": not violations,
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# 理论题库预检报告",
        "",
        f"- 生成时间：`{report['generatedAt']}`",
        f"- 运行模式：`{report['mode']}`",
        f"- 题库目录：`{report['sourceDir']}`",
        "",
        "## 摘要",
        "",
        f"- Markdown 文件数：`{report['summary']['sourceFiles']}`",
        f"- 分类数：`{report['summary']['sourceCategories']}`",
        f"- 源题目数：`{report['summary']['sourceQuestions']}`",
        f"- 导入题目数：`{report['summary']['importQuestions']}`",
        f"- 待维护题目数：`{report['summary']['incompleteQuestions']}`",
        f"- 导入选项数：`{report['summary']['importOptions']}`",
        f"- 正确答案分布：`{json.dumps(report['summary']['answerDistribution'], ensure_ascii=False)}`",
        f"- 选项数量分布：`{json.dumps(report['summary']['optionCountDistribution'], ensure_ascii=False)}`",
        "",
        "## 数据库",
        "",
        f"- 已连接：`{report['database']['connected']}`",
        f"- 端口可达：`{report['database']['portOpen']}`",
        f"- 元数据来源：`{report['database']['metadataSource']}`",
        f"- answer_child 数量：`{report['database']['answerChildCount']}`",
        "",
        "## 阻断结果",
        "",
        f"- 可执行导入：`{report['canApply']}`",
        f"- 违规统计：`{json.dumps(report['violationCounts'], ensure_ascii=False)}`",
        "",
    ]
    if report["incompleteQuestions"]:
        lines.extend(["## 待维护题目", ""])
        for skipped in report["incompleteQuestions"]:
            lines.append(
                "- "
                f"`{','.join(skipped['reasonCodes'])}`："
                f"file=`{skipped['file']}`，line=`{skipped['line']}`，"
                f"question=`{skipped['questionNumber']}`，category=`{skipped['categoryName']}`"
            )
        lines.append("")
    if report["violations"]:
        lines.extend(["## 违规明细", ""])
        for violation in report["violations"]:
            line_parts = [
                f"- `{violation['severity']}` `{violation['code']}`：{violation['message']}",
            ]
            metadata = []
            if violation.get("file"):
                metadata.append(f"file=`{violation['file']}`")
            if violation.get("line") is not None:
                metadata.append(f"line=`{violation['line']}`")
            if violation.get("questionNumber") is not None:
                metadata.append(f"question=`{violation['questionNumber']}`")
            if violation.get("categoryName"):
                metadata.append(f"category=`{violation['categoryName']}`")
            if violation.get("details"):
                metadata.append(f"details=`{json.dumps(violation['details'], ensure_ascii=False)}`")
            if metadata:
                line_parts.append("，".join(metadata))
            lines.append(" ".join(line_parts))
    else:
        lines.extend(["## 违规明细", "", "- 无阻断项。"])
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], json_path: Path | None, markdown_path: Path | None) -> None:
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown_report(report) + "\n", encoding="utf-8")


def ensure_apply_guards(args: argparse.Namespace, snapshot: DatabaseSnapshot, violations: list[Violation]) -> None:
    if not args.apply:
        return
    environment = (args.environment or "").strip().lower()
    if environment not in NON_PROD_ENVIRONMENTS:
        raise RuntimeError("`--apply` 只允许在 Local/Dev/Test 环境执行。")
    if not args.import_incomplete_questions:
        raise RuntimeError("`--apply` 需要同时提供 --import-incomplete-questions。")
    if args.confirm_apply != APPLY_CONFIRM_TOKEN:
        raise RuntimeError(f"`--apply` 需要同时提供 --confirm-apply {APPLY_CONFIRM_TOKEN}")
    if not snapshot.connected:
        raise RuntimeError("`--apply` 需要先成功连接数据库并完成只读预检。")
    if violations:
        raise RuntimeError("当前预检存在阻断项，禁止执行导入。")


def import_payload(documents: list[CategoryDocument], snapshot: DatabaseSnapshot) -> list[dict[str, Any]]:
    category_map = {
        rows[0]["category_name"]: rows[0]["id"]
        for rows in snapshot.category_matches.values()
        if len(rows) == 1
    }
    payload: list[dict[str, Any]] = []
    for document in documents:
        category_id = category_map[document.category_name]
        for sort_no, question in enumerate(document.questions, start=1):
            payload.append(
                {
                    "categoryId": category_id,
                    "questionStem": question.stem(),
                    "questionType": "single_choice",
                    "questionStatus": 1,
                    "score": 1,
                    "sortNo": sort_no,
                    "correctMemo": question.analysis(),
                    "options": [
                        {
                            "questionType": "single_choice",
                            "answerCode": code,
                            "answerContent": question.options[code].content,
                            # Missing or conflicting answer keys remain intentionally unmarked for later maintenance.
                            "isCorrect": 1
                            if question.answer_code == code
                            and question.answer_raw is not None
                            and not question.duplicate_answer_lines
                            else 0,
                            "sortNo": option_sort,
                        }
                        for option_sort, code in enumerate(question.option_order, start=1)
                    ],
                }
            )
    return payload


def fetch_post_apply_stats(connection: Any, category_ids: list[int]) -> dict[str, Any]:
    placeholders = ", ".join(["%s"] * len(category_ids))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT category_id, COUNT(1) AS total
            FROM yj_practice_exercises
            WHERE deleted = b'0'
              AND category_id IN ({placeholders})
            GROUP BY category_id
            ORDER BY category_id
            """,
            category_ids,
        )
        question_counts = list(cursor.fetchall())
        cursor.execute(
            f"""
            SELECT question.category_id, COUNT(1) AS total
            FROM yj_practice_exercises_answer answer_item
            INNER JOIN yj_practice_exercises question
                    ON question.id = answer_item.exercises_id
                   AND question.deleted = b'0'
            WHERE answer_item.deleted = b'0'
              AND question.category_id IN ({placeholders})
            GROUP BY question.category_id
            ORDER BY question.category_id
            """,
            category_ids,
        )
        answer_counts = list(cursor.fetchall())
        cursor.execute(
            f"""
            SELECT COUNT(1) AS total
            FROM yj_practice_exercises_answer_child child
            INNER JOIN yj_practice_exercises_answer answer_item
                    ON answer_item.id = child.answer_id
                   AND answer_item.deleted = b'0'
            INNER JOIN yj_practice_exercises question
                    ON question.id = answer_item.exercises_id
                   AND question.deleted = b'0'
            WHERE child.deleted = b'0'
              AND question.category_id IN ({placeholders})
            """,
            category_ids,
        )
        answer_child_count = int(cursor.fetchone()["total"])
        cursor.execute(
            f"""
            SELECT COUNT(1) AS total
            FROM (
                SELECT question.id,
                       SUM(CASE WHEN answer_item.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
                FROM yj_practice_exercises question
                LEFT JOIN yj_practice_exercises_answer answer_item
                       ON answer_item.exercises_id = question.id
                      AND answer_item.deleted = b'0'
                WHERE question.deleted = b'0'
                  AND question.category_id IN ({placeholders})
                GROUP BY question.id
                HAVING correct_count <> 1
            ) t
            """,
            category_ids,
        )
        invalid_correct_answer_questions = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT COUNT(1) AS total
            FROM yj_practice_exercises
            WHERE deleted = b'0' AND category_id = 13
            """
        )
        category_13_question_count = int(cursor.fetchone()["total"])
    return {
        "questionCounts": question_counts,
        "answerCounts": answer_counts,
        "answerChildCount": answer_child_count,
        "nonStandardCorrectAnswerQuestions": invalid_correct_answer_questions,
        "category13QuestionCount": category_13_question_count,
    }


def execute_apply(
    args: argparse.Namespace,
    snapshot: DatabaseSnapshot,
    documents: list[CategoryDocument],
) -> dict[str, Any]:
    pymysql = load_pymysql()
    payload = import_payload(documents, snapshot)
    password = resolve_db_password(args)
    connection = pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=password,
        database=args.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    backup_suffix = datetime.now().strftime("%Y%m%d%H%M%S%f")
    backup_tables = {table: f"{table}_bak_{backup_suffix}" for table in SUPPORTED_IMPORT_TABLES}
    category_ids = [rows[0]["id"] for rows in snapshot.category_matches.values()]
    import_creator = f"theory-import-{backup_suffix}"
    try:
        with connection.cursor() as cursor:
            for table_name, backup_name in backup_tables.items():
                cursor.execute(f"CREATE TABLE `{backup_name}` LIKE `{table_name}`")
                cursor.execute(f"INSERT INTO `{backup_name}` SELECT * FROM `{table_name}`")
            placeholders = ", ".join(["%s"] * len(category_ids))
            cursor.execute(
                f"""
                DELETE child
                FROM yj_practice_exercises_answer_child child
                INNER JOIN yj_practice_exercises_answer answer_item
                        ON answer_item.id = child.answer_id
                INNER JOIN yj_practice_exercises question
                        ON question.id = answer_item.exercises_id
                WHERE question.category_id IN ({placeholders})
                """,
                category_ids,
            )
            cursor.execute(
                f"""
                DELETE answer_item
                FROM yj_practice_exercises_answer answer_item
                INNER JOIN yj_practice_exercises question
                        ON question.id = answer_item.exercises_id
                WHERE question.category_id IN ({placeholders})
                """,
                category_ids,
            )
            cursor.execute(
                f"DELETE FROM yj_practice_exercises WHERE category_id IN ({placeholders})",
                category_ids,
            )
            payload_by_category: dict[int, list[dict[str, Any]]] = {}
            for item in payload:
                payload_by_category.setdefault(item["categoryId"], []).append(item)
            answer_rows: list[tuple[Any, ...]] = []
            inserted_question_count = 0
            for category_id, category_payload in payload_by_category.items():
                cursor.executemany(
                    """
                    INSERT INTO yj_practice_exercises
                        (step_id, category_id, question_stem, question_type, question_status,
                         score, sort_no, correct_memo, creator, create_time, updater, update_time, deleted)
                    VALUES
                        (NULL, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, NOW(), b'0')
                    """,
                    [
                        (
                            item["categoryId"],
                            item["questionStem"],
                            item["questionType"],
                            item["questionStatus"],
                            item["score"],
                            item["sortNo"],
                            item["correctMemo"],
                            import_creator,
                            import_creator,
                        )
                        for item in category_payload
                    ],
                )
                cursor.execute(
                    """
                    SELECT id
                    FROM yj_practice_exercises
                    WHERE category_id = %s AND creator = %s AND deleted = b'0'
                    ORDER BY sort_no, id
                    """,
                    (category_id, import_creator),
                )
                exercises_ids = [row["id"] for row in cursor.fetchall()]
                if len(exercises_ids) != len(category_payload):
                    raise RuntimeError("批量插入题目后无法精确回查主键，已停止导入。")
                inserted_question_count += len(exercises_ids)
                for item, exercises_id in zip(category_payload, exercises_ids):
                    answer_rows.extend(
                        (
                            exercises_id,
                            option["questionType"],
                            option["answerCode"],
                            option["answerContent"],
                            option["isCorrect"],
                            option["sortNo"],
                            import_creator,
                            import_creator,
                        )
                        for option in item["options"]
                    )
            cursor.executemany(
                """
                INSERT INTO yj_practice_exercises_answer
                    (exercises_id, question_type, answer_code, answer_content, is_correct,
                     sort_no, creator, create_time, updater, update_time, deleted)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, NOW(), b'0')
                """,
                answer_rows,
            )
            inserted_answer_count = len(answer_rows)
        connection.commit()
        post_apply_stats = fetch_post_apply_stats(connection, category_ids)
        return {
            "applied": True,
            "backupTables": backup_tables,
            "backupNote": "MySQL CREATE TABLE / INSERT ... SELECT 备份已先落库，若后续 DML 失败将仅回滚删除与插入，不回滚备份表。",
            "insertedQuestions": inserted_question_count,
            "insertedAnswers": inserted_answer_count,
            "postApplyStats": post_apply_stats,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Precheck or import practice theory bank markdown files.")
    parser.add_argument("--source-dir", type=Path, help="Directory containing theory bank markdown files.")
    parser.add_argument("--report-dir", type=Path, help="Write precheck JSON/Markdown reports into this directory.")
    parser.add_argument("--report-json", type=Path, help="Write JSON report to this path.")
    parser.add_argument("--report-markdown", type=Path, help="Write markdown report to this path.")
    parser.add_argument("--db-host", default=None)
    parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-name", default="yunjikeji")
    parser.add_argument("--db-user", default=None)
    parser.add_argument("--db-password", default=None)
    parser.add_argument("--db-password-env", default=None)
    parser.add_argument("--environment", default=None, help="Local, Dev, or Test when using --apply.")
    parser.add_argument(
        "--target-category-ids",
        type=lambda value: [int(item) for item in value.split(",") if item.strip()],
        default=list(DEFAULT_TARGET_CATEGORY_IDS),
        help="Comma separated category ids allowed for delete/import. Default: 1..11.",
    )
    parser.add_argument(
        "--import-incomplete-questions",
        action="store_true",
        help="Import questions with missing stems or unresolved answer keys as explicit maintenance records.",
    )
    parser.add_argument(
        "--correct-memo-limit",
        type=int,
        default=None,
        help="Override fallback correct_memo length when dry-run does not load live schema metadata.",
    )
    parser.add_argument("--apply", action="store_true", help="Execute backup, delete, and import in one transaction.")
    parser.add_argument("--confirm-apply", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace_root = get_workspace_root(Path(__file__).resolve())
    source_dir = args.source_dir or default_source_dir(workspace_root)
    source_documents, violations = parse_documents(source_dir)
    snapshot = DatabaseSnapshot()
    if args.db_host:
        if not args.db_user:
            raise RuntimeError("提供 --db-host 时必须同时提供 --db-user。")
        snapshot = fetch_database_snapshot(args, source_documents)
    limits = build_effective_limits(args, snapshot)
    apply_length_checks(source_documents, limits, violations)
    validate_live_schema(snapshot, violations)
    import_documents, violations, incomplete_questions = allow_incomplete_questions(
        source_documents,
        violations,
        args.import_incomplete_questions,
    )
    validate_category_mapping(import_documents, snapshot, violations, set(args.target_category_ids))
    report = build_report(
        args,
        source_dir,
        source_documents,
        import_documents,
        violations,
        incomplete_questions,
        snapshot,
        limits,
    )
    apply_result: dict[str, Any] | None = None
    if args.apply:
        ensure_apply_guards(args, snapshot, violations)
        apply_result = execute_apply(args, snapshot, import_documents)
        report["applyResult"] = apply_result
        report["canApply"] = True
    if args.report_dir:
        args.report_json = args.report_json or args.report_dir / "precheck-report.json"
        args.report_markdown = args.report_markdown or args.report_dir / "precheck-report.md"
    write_report(report, args.report_json, args.report_markdown)
    print(json.dumps(report["summary"], ensure_ascii=False))
    if violations:
        print(f"precheck blocked: {len(violations)} violation(s)", file=sys.stderr)
        return 1
    if apply_result:
        print(json.dumps(apply_result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
