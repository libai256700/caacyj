#!/usr/bin/env python3
"""Manual Story-052 career-planning question import tool."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[6]
SOURCE_MARKER = "career-planning-coach"
CATEGORY_ID = 14
EXPECTED_QUESTION_COUNT = 47
EXPECTED_ANSWER_COUNT = 111
EXPECTED_CORE_SHA256 = "729A47DDFE55C51B98E1EE921C4B6B35BF0B8BCEF27900D3782E49076377D678"
EXPECTED_SCHEMA_SHA256 = "77FCC8D1C9359D801034AD334C2B81BE08A5EDC694AE63C7DC8811AEA6E769B5"
CANONICAL_APP_CONFIG = (
    "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/"
    "src/main/resources/application-local.yaml"
)
QUESTION_INSERT_SQL = """
INSERT INTO yj_practice_exercises
    (step_id, category_id, question_stem, question_type, question_status, is_required,
     score, sort_no, correct_memo, creator, create_time, updater, update_time, deleted)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, NOW(), b'0')
"""
STEP_INSERT_SQL = """
INSERT INTO yj_practice_step
    (category_id, step_name, step_status, sort_no, creator, create_time, updater, update_time, deleted)
VALUES
    (%s, %s, b'1', %s, %s, NOW(), %s, NOW(), b'0')
"""
STEP_READBACK_SQL = """
SELECT id, category_id, step_name, step_status, sort_no
FROM yj_practice_step
WHERE deleted = b'0' AND category_id = %s
ORDER BY sort_no, id
"""
ANSWER_INSERT_SQL = """
INSERT INTO yj_practice_exercises_answer
    (exercises_id, question_type, answer_code, answer_content, is_correct,
     sort_no, creator, create_time, updater, update_time, deleted)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, NOW(), b'0')
"""
READBACK_SQL = """
SELECT e.id, e.step_id, e.category_id, e.question_stem, e.question_type, e.question_status,
       e.is_required, e.score, e.sort_no, e.correct_memo,
       a.question_type AS answer_question_type, a.answer_code, a.answer_content,
       a.is_correct, a.sort_no AS answer_sort_no
FROM yj_practice_exercises e
LEFT JOIN yj_practice_exercises_answer a ON a.exercises_id = e.id AND a.deleted = b'0'
WHERE e.deleted = b'0' AND e.category_id = %s
ORDER BY e.sort_no, e.id, a.sort_no, a.id
"""


@dataclass(frozen=True)
class OptionRow:
    code: str
    content: str
    sort_no: int


@dataclass(frozen=True)
class QuestionRow:
    sort_no: int
    field_key: str
    question_stem: str
    question_type: str
    is_required: bool
    correct_memo: str
    options: tuple[OptionRow, ...]


@dataclass(frozen=True)
class StepRow:
    sort_no: int
    step_name: str
    first_question_sort_no: int
    last_question_sort_no: int


STEP_ROWS = (
    StepRow(1, "基本情况", 1, 9),
    StepRow(2, "经历与成果", 10, 13),
    StepRow(3, "兴趣倾向", 14, 26),
    StepRow(4, "工作风格", 27, 38),
    StepRow(5, "工作价值", 39, 40),
    StepRow(6, "目标计划", 41, 47),
)


def resolve_workspace_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return WORKSPACE_ROOT / path


def load_application_database_target(app_config: str | Path) -> dict[str, Any]:
    text = resolve_workspace_path(app_config).read_text(encoding="utf-8-sig")
    match = re.search(r"jdbc:mysql://(?P<host>[^/:?#]+):(?P<port>\d+)/(?P<database>[^?\s#]+)", text)
    if not match:
        raise RuntimeError("invalid application database config")
    return {
        "host": match.group("host"),
        "port": int(match.group("port")),
        "database": match.group("database"),
    }


def parse_yaml_scalar(value: str) -> str:
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] in "\"'" and normalized[-1] == normalized[0]:
        return normalized[1:-1]
    return normalized.split(" #", 1)[0].strip()


def iter_yaml_scalars(app_config: str | Path):
    stack: list[tuple[int, str]] = []
    with resolve_workspace_path(app_config).open(encoding="utf-8-sig") as config_file:
        for raw_line in config_file:
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            match = re.match(r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_.-]+):(?:[ \t]+(?P<value>.*))?$", raw_line.rstrip())
            if not match:
                continue
            indent = len(match.group("indent").expandtabs(2))
            while stack and indent <= stack[-1][0]:
                stack.pop()
            key = match.group("key")
            if match.group("value") is None:
                stack.append((indent, key))
                continue
            yield tuple(item[1] for item in stack) + (key,), parse_yaml_scalar(match.group("value"))
            stack.append((indent, key))


def load_application_database_credentials(app_config: str | Path) -> dict[str, str]:
    target = load_application_database_target(app_config)
    candidates: dict[tuple[str, ...], dict[str, str]] = {}
    for path, value in iter_yaml_scalars(app_config):
        key = path[-1].replace("-", "_").lower()
        if key in {"url", "jdbc_url"} and "jdbc:mysql://" in value:
            candidates.setdefault(path[:-1], {})["url"] = value
        elif key in {"username", "user", "user_name"}:
            candidates.setdefault(path[:-1], {})["username"] = value
        elif key == "password":
            candidates.setdefault(path[:-1], {})["password"] = value
    matching: list[dict[str, str]] = []
    for values in candidates.values():
        url = values.get("url")
        if not url or "username" not in values or "password" not in values:
            continue
        match = re.search(r"jdbc:mysql://(?P<host>[^/:?#]+):(?P<port>\d+)/(?P<database>[^?\s#]+)", url)
        if not match:
            continue
        if (
            match.group("host") == target["host"]
            and int(match.group("port")) == target["port"]
            and match.group("database") == target["database"]
        ):
            matching.append({"username": values["username"], "password": values["password"]})
    if not matching:
        raise RuntimeError("application config missing database credentials for jdbc target")
    if len({(item["username"], item["password"]) for item in matching}) != 1:
        raise RuntimeError("application config has ambiguous database credentials for jdbc target")
    return matching[0]


def assert_same_application_database(target: dict[str, Any], expected: dict[str, Any]) -> None:
    for field in ("host", "port", "database"):
        if target[field] != expected[field]:
            raise RuntimeError(f"database mismatch: {field}")


def build_cli_database_target(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.db_host is None and args.db_port is None and args.db_name is None:
        return None
    if not args.db_host or args.db_port is None or not args.db_name:
        raise RuntimeError("db target requires --db-host --db-port --db-name together")
    return {"host": args.db_host, "port": args.db_port, "database": args.db_name}


def resolve_db_password(args: argparse.Namespace) -> str | None:
    if args.db_password_env:
        password = os.getenv(args.db_password_env)
        if password is None:
            raise RuntimeError(f"environment variable {args.db_password_env} is not set")
        return password
    return None


def resolve_database_credentials(args: argparse.Namespace) -> tuple[str, str]:
    cli_password = resolve_db_password(args)
    if args.db_user and cli_password is not None:
        return args.db_user, cli_password
    configured = load_application_database_credentials(args.app_config)
    username = args.db_user or configured["username"]
    password = cli_password if cli_password is not None else configured["password"]
    if not username or not password:
        raise RuntimeError("database credentials are unavailable in application config")
    return username, password


def load_pymysql():
    try:
        import pymysql  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("missing pymysql dependency") from exc
    return pymysql


def bit_value_to_int(value: Any) -> int:
    if isinstance(value, (bytes, bytearray)):
        return int.from_bytes(value, byteorder="big", signed=False)
    if isinstance(value, bool):
        return int(value)
    if value is None:
        return 0
    return int(value)


def normalize_enabled_status(value: Any) -> int:
    """Normalize a database status value and accept only the enabled value 1."""
    if isinstance(value, bool):
        raise RuntimeError(f"invalid enabled status: {value!r}")
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, (bytes, bytearray)):
        raw_value = bytes(value)
        if raw_value == b"\x01":
            return 1
        try:
            normalized = int(raw_value.decode("ascii").strip())
        except (UnicodeDecodeError, ValueError):
            raise RuntimeError(f"invalid enabled status: {value!r}") from None
    elif isinstance(value, str):
        try:
            normalized = int(value.strip())
        except ValueError:
            raise RuntimeError(f"invalid enabled status: {value!r}") from None
    else:
        raise RuntimeError(f"invalid enabled status: {value!r}")
    if normalized != 1:
        raise RuntimeError(f"invalid enabled status: {value!r}")
    return 1


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return bit_value_to_int(value)
    return value


def connect_database(target: dict[str, Any], args: argparse.Namespace):
    username, password = resolve_database_credentials(args)
    pymysql = load_pymysql()
    return pymysql.connect(
        host=target["host"],
        port=target["port"],
        user=username,
        password=password,
        database=target["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).replace("*", "").strip()


def extract_field_label(index_html: str, field_name: str) -> str:
    # Match one label element at a time.  The earlier cross-label expression
    # could pair the first "姓名" span with a later field's name attribute.
    for match in re.finditer(r"<label\b(?P<attrs>[^>]*)>(?P<body>.*?)</label>", index_html, re.S):
        attrs = match.group("attrs")
        body = match.group("body")
        if "field" not in attrs or not re.search(rf'name="{re.escape(field_name)}"', body):
            continue
        label_match = re.search(r"<span>(?P<label>.*?)</span>", body, re.S)
        if label_match:
            return strip_tags(label_match.group("label"))
    raise RuntimeError(f"field label not found: {field_name}")


def extract_select_options(index_html: str, field_name: str) -> list[str]:
    match = re.search(
        rf'<select name="{re.escape(field_name)}">(?P<body>.*?)</select>',
        index_html,
        re.S,
    )
    if not match:
        raise RuntimeError(f"select not found: {field_name}")
    options = []
    for attrs, body in re.findall(r"<option(?P<attrs>[^>]*)>(?P<body>.*?)</option>", match.group("body"), re.S):
        text = strip_tags(body)
        value_match = re.search(r'value="([^"]*)"', attrs)
        option_value = value_match.group(1) if value_match else None
        if not text or option_value == "" or text == "请选择":
            continue
        options.append(text)
    return options


def extract_checkbox_question(index_html: str, field_name: str) -> tuple[str, list[str]]:
    for match in re.finditer(r"<fieldset[^>]*>(?P<body>.*?)</fieldset>", index_html, re.S):
        body = match.group("body")
        if f'name="{field_name}"' not in body:
            continue
        legend_match = re.search(r"<legend>(.*?)</legend>", body, re.S)
        if not legend_match:
            break
        label = strip_tags(legend_match.group(1))
        options = [strip_tags(item) for item in re.findall(
            rf'<input[^>]+name="{re.escape(field_name)}"[^>]+value="([^"]+)"',
            body,
            re.S,
        )]
        return label, [item for item in options if item]
    raise RuntimeError(f"checkbox question not found: {field_name}")


def extract_string_array(core_text: str, constant_name: str) -> list[str]:
    match = re.search(
        rf"const {re.escape(constant_name)} = Object\.freeze\(\[(?P<body>[\s\S]*?)\]\);",
        core_text,
    )
    if not match:
        raise RuntimeError(f"constant not found: {constant_name}")
    return re.findall(r'"([^"]+)"', match.group("body"))


def extract_riasec_questions(core_text: str) -> list[str]:
    match = re.search(r"const RIASEC_QUESTIONS = Object\.freeze\(\[(?P<body>[\s\S]*?)\]\);", core_text)
    if not match:
        raise RuntimeError("RIASEC_QUESTIONS not found")
    return re.findall(r'text:\s*"([^"]+)"', match.group("body"))


def extract_style_questions(core_text: str) -> list[dict[str, str]]:
    match = re.search(r"const STYLE_QUESTIONS = Object\.freeze\(\[(?P<body>[\s\S]*?)\]\);", core_text)
    if not match:
        raise RuntimeError("STYLE_QUESTIONS not found")
    pattern = re.compile(r'\{[^{}]*text:\s*"([^"]+)"[^{}]*a:\s*"([^"]+)"[^{}]*b:\s*"([^"]+)"[^{}]*\}')
    return [{"text": text, "a": left, "b": right} for text, left, right in pattern.findall(match.group("body"))]


def answer_code(index: int) -> str:
    return chr(ord("A") + index)


def build_options(values: list[str]) -> tuple[OptionRow, ...]:
    return tuple(OptionRow(code=answer_code(index), content=value, sort_no=index + 1) for index, value in enumerate(values))


def build_meta(field_key: str, question_type: str, is_required: bool, extra: dict[str, Any] | None = None) -> str:
    payload = {
        "field": field_key,
        "type": question_type,
        "required": is_required,
        "source": SOURCE_MARKER,
    }
    if extra:
        payload.update(extra)
    value = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(value) > 500:
        raise RuntimeError(f"correct_memo overflow for {field_key}")
    return value


def text_question(sort_no: int, field_key: str, label: str, required: bool, extra: dict[str, Any] | None = None) -> QuestionRow:
    return QuestionRow(sort_no, field_key, label, "text", required, build_meta(field_key, "text", required, extra), ())


def single_choice_question(
    sort_no: int,
    field_key: str,
    label: str,
    required: bool,
    option_values: list[str],
    extra: dict[str, Any] | None = None,
) -> QuestionRow:
    return QuestionRow(
        sort_no,
        field_key,
        label,
        "single_choice",
        required,
        build_meta(field_key, "single_choice", required, extra),
        build_options(option_values),
    )


def multiple_choice_question(
    sort_no: int,
    field_key: str,
    label: str,
    required: bool,
    option_values: list[str],
    extra: dict[str, Any] | None = None,
) -> QuestionRow:
    return QuestionRow(
        sort_no,
        field_key,
        label,
        "multiple_choice",
        required,
        build_meta(field_key, "multiple_choice", required, extra),
        build_options(option_values),
    )


def load_source_package(source_dir: Path) -> dict[str, Any]:
    if not source_dir.exists():
        raise RuntimeError(f"source-dir does not exist: {source_dir}")
    core_path = source_dir / "scripts" / "career-core.mjs"
    schema_path = source_dir / "references" / "self-assessment.schema.json"
    index_path = source_dir / "web" / "index.html"
    for required in (core_path, schema_path, index_path):
        if not required.exists():
            raise RuntimeError(f"required source file missing: {required}")
    core_sha256 = sha256_file(core_path)
    schema_sha256 = sha256_file(schema_path)
    if core_sha256 != EXPECTED_CORE_SHA256:
        raise RuntimeError("career-core.mjs hash mismatch")
    if schema_sha256 != EXPECTED_SCHEMA_SHA256:
        raise RuntimeError("self-assessment.schema.json hash mismatch")
    return {
        "coreText": core_path.read_text(encoding="utf-8"),
        "indexText": index_path.read_text(encoding="utf-8"),
    }


def build_question_rows(source_dir: Path) -> list[QuestionRow]:
    source = load_source_package(source_dir)
    core_text = source["coreText"]
    index_html = source["indexText"]
    age_options = extract_select_options(index_html, "age")
    education_options = extract_select_options(index_html, "education")
    year_options = extract_select_options(index_html, "years")
    weekly_hours_options = extract_select_options(index_html, "weeklyHours")
    track_options = extract_select_options(index_html, "trackPreference")
    cert_label, cert_options = extract_checkbox_question(index_html, "certsList")
    direction_label, direction_options = extract_checkbox_question(index_html, "interestDirections")
    value_options = extract_string_array(core_text, "VALUE_OPTIONS")
    riasec_questions = extract_riasec_questions(core_text)
    style_questions = extract_style_questions(core_text)
    if len(riasec_questions) != 12 or len(style_questions) != 12 or len(value_options) != 8:
        raise RuntimeError("source question bank shape mismatch")
    rows: list[QuestionRow] = [
        text_question(1, "name", extract_field_label(index_html, "name"), True),
        single_choice_question(2, "age", extract_field_label(index_html, "age"), False, age_options),
        single_choice_question(3, "education", extract_field_label(index_html, "education"), False, education_options),
        text_question(4, "major", extract_field_label(index_html, "major"), False),
        text_question(5, "currentRole", extract_field_label(index_html, "currentRole"), False),
        single_choice_question(6, "years", extract_field_label(index_html, "years"), False, year_options),
        text_question(7, "duties", extract_field_label(index_html, "duties"), False),
        multiple_choice_question(8, "certsList", cert_label, False, cert_options, {"exclusive": "暂无，在学/备考"}),
        text_question(9, "certsOther", extract_field_label(index_html, "certsOther"), False),
        text_question(10, "experience", extract_field_label(index_html, "experience"), False),
        text_question(11, "achievements", extract_field_label(index_html, "achievements"), True),
        text_question(12, "interests", extract_field_label(index_html, "interests"), False),
        text_question(13, "dislikes", extract_field_label(index_html, "dislikes"), False),
    ]
    riasec_options = ["不太想做", "可以尝试", "很想做"]
    for index, question_text in enumerate(riasec_questions, start=14):
        rows.append(single_choice_question(
            index,
            f"riasecAnswers[{index - 14}]",
            question_text,
            True,
            riasec_options,
            {"scoreValues": [0, 1, 2]},
        ))
    rows.append(multiple_choice_question(26, "interestDirections", direction_label, False, direction_options))
    for index, question in enumerate(style_questions, start=27):
        rows.append(single_choice_question(
            index,
            f"style.answers[{index - 27}]",
            question["text"],
            False,
            [question["a"], question["b"]],
            {"skipGroup": "style.source=skip"},
        ))
    rows.append(multiple_choice_question(
        39,
        "values.top3",
        "最看重的 3 项",
        True,
        value_options,
        {"minSelections": 3, "maxSelections": 3},
    ))
    rows.append(single_choice_question(
        40,
        "values.least",
        "相对最不看重的一项",
        False,
        value_options,
        {"excludeField": "values.top3"},
    ))
    rows.extend(
        [
            text_question(41, "goal3y", extract_field_label(index_html, "goal3y"), False),
            single_choice_question(42, "trackPreference", extract_field_label(index_html, "trackPreference"), False, track_options),
            text_question(43, "targetJob", extract_field_label(index_html, "targetJob"), False),
            text_question(44, "targetJD", extract_field_label(index_html, "targetJD"), False),
            text_question(45, "obstacle", extract_field_label(index_html, "obstacle"), False),
            text_question(46, "firstStep", extract_field_label(index_html, "firstStep"), False),
            single_choice_question(47, "weeklyHours", extract_field_label(index_html, "weeklyHours"), False, weekly_hours_options),
        ]
    )
    validate_target(CATEGORY_ID, rows, [option for row in rows for option in row.options])
    validate_question_step_mapping(rows, STEP_ROWS)
    return rows


def validate_question_step_mapping(questions: list[QuestionRow], steps: tuple[StepRow, ...]) -> None:
    if len(steps) != 6:
        raise RuntimeError("wrong step count")
    if [step.sort_no for step in steps] != list(range(1, 7)):
        raise RuntimeError("wrong step ordering")
    if [step.step_name for step in steps] != [
        "基本情况", "经历与成果", "兴趣倾向", "工作风格", "工作价值", "目标计划",
    ]:
        raise RuntimeError("wrong step names")
    if len({question.question_stem for question in questions}) != len(questions):
        raise RuntimeError("duplicate question stem in source")
    for question in questions:
        step_sort_no_for_question(question.sort_no, steps)


def step_sort_no_for_question(sort_no: int, steps: tuple[StepRow, ...] = STEP_ROWS) -> int:
    for step in steps:
        if step.first_question_sort_no <= sort_no <= step.last_question_sort_no:
            return step.sort_no
    raise RuntimeError(f"question sort has no step: {sort_no}")


def validate_target(category_id: int, questions: list[QuestionRow], answers: list[OptionRow]) -> None:
    if category_id != CATEGORY_ID:
        raise RuntimeError("wrong category")
    if len(questions) != EXPECTED_QUESTION_COUNT:
        raise RuntimeError("wrong question count")
    if len(answers) != EXPECTED_ANSWER_COUNT:
        raise RuntimeError("wrong answer count")


def ensure_empty_target(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, category_name, category_status, field_type, catalog_type, sort_no
            FROM yj_practice_category
            WHERE id = %s AND deleted = b'0'
            """,
            (CATEGORY_ID,),
        )
        category_row = cursor.fetchone()
        if not category_row:
            raise RuntimeError("category 14 does not exist")
        cursor.execute(
            "SELECT COUNT(1) AS total FROM yj_practice_exercises WHERE deleted = b'0' AND category_id = %s",
            (CATEGORY_ID,),
        )
        question_total = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT COUNT(1) AS total
            FROM yj_practice_exercises_answer answer_item
            INNER JOIN yj_practice_exercises question
                    ON question.id = answer_item.exercises_id
                   AND question.deleted = b'0'
            WHERE answer_item.deleted = b'0' AND question.category_id = %s
            """,
            (CATEGORY_ID,),
        )
        answer_total = int(cursor.fetchone()["total"])
    if question_total or answer_total:
        raise RuntimeError("category 14 target already contains data")
    return {"category": category_row, "questionCount": question_total, "answerCount": answer_total}


def ensure_repair_target(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM yj_practice_category WHERE id = %s AND deleted = b'0'",
            (CATEGORY_ID,),
        )
        if not cursor.fetchone():
            raise RuntimeError("category 14 does not exist")
        cursor.execute(
            "SELECT id, sort_no FROM yj_practice_exercises "
            "WHERE deleted = b'0' AND category_id = %s ORDER BY sort_no, id",
            (CATEGORY_ID,),
        )
        questions = cursor.fetchall()
        cursor.execute(
            "SELECT COUNT(1) AS total FROM yj_practice_exercises_answer a "
            "INNER JOIN yj_practice_exercises e ON e.id = a.exercises_id AND e.deleted = b'0' "
            "WHERE a.deleted = b'0' AND e.category_id = %s",
            (CATEGORY_ID,),
        )
        answer_total = int(cursor.fetchone()["total"])
    sorts = [item["sort_no"] for item in questions]
    if sorts != list(range(1, EXPECTED_QUESTION_COUNT + 1)):
        raise RuntimeError("category 14 repair requires exactly one question for every source sort")
    if answer_total != EXPECTED_ANSWER_COUNT:
        raise RuntimeError("category 14 repair requires the expected answer count")
    return {"questionCount": len(questions), "answerCount": answer_total}


def backup_target_rows(connection: Any) -> dict[str, str]:
    suffix = datetime.now().strftime("%Y%m%d%H%M%S%f")
    exercise_backup = f"yj_practice_exercises_bak_{suffix}"
    answer_backup = f"yj_practice_exercises_answer_bak_{suffix}"
    step_backup = f"yj_practice_step_bak_{suffix}"
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE `{exercise_backup}` LIKE `yj_practice_exercises`")
        cursor.execute(
            f"INSERT INTO `{exercise_backup}` SELECT * FROM yj_practice_exercises WHERE category_id = %s",
            (CATEGORY_ID,),
        )
        cursor.execute(f"CREATE TABLE `{answer_backup}` LIKE `yj_practice_exercises_answer`")
        cursor.execute(
            f"""
            INSERT INTO `{answer_backup}`
            SELECT answer_item.*
            FROM yj_practice_exercises_answer answer_item
            INNER JOIN yj_practice_exercises question
                    ON question.id = answer_item.exercises_id
            WHERE question.category_id = %s
            """,
            (CATEGORY_ID,),
        )
        cursor.execute(f"CREATE TABLE `{step_backup}` LIKE `yj_practice_step`")
        cursor.execute(
            f"INSERT INTO `{step_backup}` SELECT * FROM yj_practice_step WHERE category_id = %s",
            (CATEGORY_ID,),
        )
    return {"questions": exercise_backup, "answers": answer_backup, "steps": step_backup}


def ensure_steps(connection: Any, creator: str) -> dict[int, int]:
    with connection.cursor() as cursor:
        cursor.execute(STEP_READBACK_SQL, (CATEGORY_ID,))
        existing = cursor.fetchall()
        by_sort: dict[int, dict[str, Any]] = {}
        for item in existing:
            sort_no = item["sort_no"]
            if sort_no in by_sort or sort_no not in range(1, len(STEP_ROWS) + 1):
                raise RuntimeError("category 14 has ambiguous existing steps")
            by_sort[sort_no] = item
        for step in STEP_ROWS:
            row = by_sort.get(step.sort_no)
            if row is None:
                cursor.execute(
                    STEP_INSERT_SQL,
                    (CATEGORY_ID, step.step_name, step.sort_no, creator, creator),
                )
            else:
                cursor.execute(
                    "UPDATE yj_practice_step SET step_name = %s, step_status = b'1', "
                    "sort_no = %s, updater = %s, update_time = NOW() WHERE id = %s AND category_id = %s",
                    (step.step_name, step.sort_no, creator, row["id"], CATEGORY_ID),
                )
        cursor.execute(STEP_READBACK_SQL, (CATEGORY_ID,))
        current = cursor.fetchall()
    if len(current) != len(STEP_ROWS):
        raise RuntimeError("step readback count mismatch")
    step_ids: dict[int, int] = {}
    for actual, expected in zip(current, STEP_ROWS):
        if (
            actual["category_id"] != CATEGORY_ID
            or actual["sort_no"] != expected.sort_no
            or actual["step_name"] != expected.step_name
            or normalize_enabled_status(actual["step_status"]) != 1
        ):
            raise RuntimeError("step readback mismatch")
        step_ids[expected.sort_no] = actual["id"]
    return step_ids


def insert_rows(connection: Any, questions: list[QuestionRow], step_ids: dict[int, int], creator: str) -> None:
    with connection.cursor() as cursor:
        cursor.executemany(
            QUESTION_INSERT_SQL,
            [
                (
                    step_ids[step_sort_no_for_question(question.sort_no)],
                    CATEGORY_ID,
                    question.question_stem,
                    question.question_type,
                    1,
                    1 if question.is_required else 0,
                    1,
                    question.sort_no,
                    question.correct_memo,
                    creator,
                    creator,
                )
                for question in questions
            ],
        )
        cursor.execute(
            """
            SELECT id, sort_no
            FROM yj_practice_exercises
            WHERE deleted = b'0' AND category_id = %s AND creator = %s
            ORDER BY sort_no, id
            """,
            (CATEGORY_ID, creator),
        )
        inserted = cursor.fetchall()
        if len(inserted) != len(questions):
            raise RuntimeError("unable to re-read inserted questions")
        answer_parameters = []
        for inserted_row, question in zip(inserted, questions):
            for option in question.options:
                answer_parameters.append(
                    (
                        inserted_row["id"],
                        question.question_type,
                        option.code,
                        option.content,
                        0,
                        option.sort_no,
                        creator,
                        creator,
                    )
                )
        cursor.executemany(ANSWER_INSERT_SQL, answer_parameters)


def repair_existing_rows(connection: Any, questions: list[QuestionRow], step_ids: dict[int, int], creator: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, sort_no FROM yj_practice_exercises "
            "WHERE deleted = b'0' AND category_id = %s ORDER BY sort_no, id",
            (CATEGORY_ID,),
        )
        existing = cursor.fetchall()
        if [item["sort_no"] for item in existing] != list(range(1, EXPECTED_QUESTION_COUNT + 1)):
            raise RuntimeError("category 14 repair question ordering changed")
        cursor.executemany(
            "UPDATE yj_practice_exercises SET step_id = %s, question_stem = %s, question_type = %s, "
            "question_status = 1, is_required = %s, score = 1, sort_no = %s, correct_memo = %s, "
            "updater = %s, update_time = NOW() WHERE id = %s AND category_id = %s AND deleted = b'0'",
            [
                (
                    step_ids[step_sort_no_for_question(question.sort_no)],
                    question.question_stem,
                    question.question_type,
                    1 if question.is_required else 0,
                    question.sort_no,
                    question.correct_memo,
                    creator,
                    existing[index]["id"],
                    CATEGORY_ID,
                )
                for index, question in enumerate(questions)
            ],
        )


def verify_readback(
    connection: Any, expected_questions: list[QuestionRow], step_ids: dict[int, int]
) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(READBACK_SQL, (CATEGORY_ID,))
        rows = cursor.fetchall()
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        item = grouped.setdefault(
            row["id"],
            {
                "category_id": row["category_id"],
                "step_id": row["step_id"],
                "question_stem": row["question_stem"],
                "question_type": row["question_type"],
                "question_status": row["question_status"],
                "is_required": row["is_required"],
                "score": row["score"],
                "sort_no": row["sort_no"],
                "correct_memo": row["correct_memo"],
                "options": [],
            },
        )
        if row["answer_code"] is not None:
            item["options"].append(
                {
                    "question_type": row["answer_question_type"],
                    "answer_code": row["answer_code"],
                    "answer_content": row["answer_content"],
                    "is_correct": row["is_correct"],
                    "sort_no": row["answer_sort_no"],
                }
            )
    actual_questions = sorted(grouped.values(), key=lambda item: item["sort_no"])
    if len(actual_questions) != EXPECTED_QUESTION_COUNT:
        raise RuntimeError("question readback count mismatch")
    answer_count = sum(len(item["options"]) for item in actual_questions)
    if answer_count != EXPECTED_ANSWER_COUNT:
        raise RuntimeError("answer readback count mismatch")
    for actual, expected in zip(actual_questions, expected_questions):
        if actual["category_id"] != CATEGORY_ID:
            raise RuntimeError("readback category mismatch")
        if actual["step_id"] != step_ids[step_sort_no_for_question(expected.sort_no)]:
            raise RuntimeError(f"readback step mismatch: {expected.field_key}")
        if actual["question_stem"] != expected.question_stem:
            raise RuntimeError(f"readback question mismatch: {expected.field_key}")
        if actual["question_type"] != expected.question_type:
            raise RuntimeError(f"readback question type mismatch: {expected.field_key}")
        if normalize_enabled_status(actual["question_status"]) != 1:
            raise RuntimeError(f"readback question status mismatch: {expected.field_key}")
        if bit_value_to_int(actual["is_required"]) != int(expected.is_required):
            raise RuntimeError(f"readback required mismatch: {expected.field_key}")
        if actual["score"] != 1:
            raise RuntimeError(f"readback score mismatch: {expected.field_key}")
        if actual["sort_no"] != expected.sort_no:
            raise RuntimeError(f"readback sort mismatch: {expected.field_key}")
        if actual["correct_memo"] != expected.correct_memo:
            raise RuntimeError(f"readback meta mismatch: {expected.field_key}")
        if len(actual["options"]) != len(expected.options):
            raise RuntimeError(f"readback option count mismatch: {expected.field_key}")
        for actual_option, expected_option in zip(actual["options"], expected.options):
            if actual_option["question_type"] != expected.question_type:
                raise RuntimeError(f"readback answer type mismatch: {expected.field_key}")
            if actual_option["answer_code"] != expected_option.code:
                raise RuntimeError(f"readback answer code mismatch: {expected.field_key}")
            if actual_option["answer_content"] != expected_option.content:
                raise RuntimeError(f"readback answer content mismatch: {expected.field_key}")
            if bit_value_to_int(actual_option["is_correct"]) != 0:
                raise RuntimeError(f"readback answer correctness mismatch: {expected.field_key}")
            if actual_option["sort_no"] != expected_option.sort_no:
                raise RuntimeError(f"readback answer sort mismatch: {expected.field_key}")
    return {"questionCount": len(actual_questions), "answerCount": answer_count}


def write_report(report_path: Path | None, payload: dict[str, Any]) -> None:
    if report_path is None:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(make_json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual Story-052 career-planning question import tool.")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument(
        "--app-config",
        default="code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/resources/application-local.yaml",
    )
    parser.add_argument("--db-host")
    parser.add_argument("--db-port", type=int)
    parser.add_argument("--db-name")
    parser.add_argument("--db-user")
    parser.add_argument("--db-password-env")
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--repair-existing",
        action="store_true",
        help="explicitly repair the existing category 14 rows; requires --apply",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    parsed_target = load_application_database_target(args.app_config)
    canonical_target = load_application_database_target(
        "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/resources/application-local.yaml"
    )
    assert_same_application_database(parsed_target, canonical_target)
    cli_target = build_cli_database_target(args)
    if cli_target is not None:
        assert_same_application_database(cli_target, canonical_target)
    if args.repair_existing and not args.apply:
        raise RuntimeError("--repair-existing requires --apply")
    questions = build_question_rows(args.source_dir)
    payload = {
        "mode": "dry-run",
        "categoryId": CATEGORY_ID,
        "sourceDir": str(args.source_dir),
        "questionCount": len(questions),
        "answerCount": sum(len(question.options) for question in questions),
        "stepCount": len(STEP_ROWS),
        "steps": [
            {
                "sortNo": step.sort_no,
                "stepName": step.step_name,
                "questionRange": [step.first_question_sort_no, step.last_question_sort_no],
            }
            for step in STEP_ROWS
        ],
        "coreSha256": EXPECTED_CORE_SHA256,
        "schemaSha256": EXPECTED_SCHEMA_SHA256,
    }
    if not args.apply:
        write_report(args.report_json, payload)
        print(json.dumps(make_json_safe(payload), ensure_ascii=False))
        return 0
    creator = f"story052-career-question-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    connection = connect_database(parsed_target, args)
    try:
        conflict = ensure_repair_target(connection) if args.repair_existing else ensure_empty_target(connection)
        backup_tables = backup_target_rows(connection)
        connection.begin()
        try:
            step_ids = ensure_steps(connection, creator)
            if args.repair_existing:
                repair_existing_rows(connection, questions, step_ids, creator)
            else:
                insert_rows(connection, questions, step_ids, creator)
            readback = verify_readback(connection, questions, step_ids)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        connection.close()
    payload["mode"] = "repair-existing" if args.repair_existing else "apply"
    payload["applyResult"] = {
        "conflict": conflict,
        "backupTables": backup_tables,
        "stepIds": step_ids,
        "readback": readback,
    }
    write_report(args.report_json, payload)
    print(json.dumps(make_json_safe(payload), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
