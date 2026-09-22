#!/usr/bin/env python3
"""Manual initializer for Story-052 career assessment Agent row."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path
from decimal import Decimal
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[6]
DEFAULT_SOURCE_FILE = (
    r"D:\飞机\-APP--main (4)\-APP--main\skills\career-planning-coach\scripts\career-core.mjs"
)
EXPECTED_SOURCE_FILE_SHA256 = (
    "729A47DDFE55C51B98E1EE921C4B6B35BF0B8BCEF27900D3782E49076377D678"
)
EXPECTED_PROMPT_SHA256 = (
    "038C28D2600946455E53F15F307ADCC0B739D56AFF31F0B404864DB363FB2F39"
)
AGENT_ID = 3
TENANT_ID = 1
AGENT_NAME = "职业规划评测"
AGENT_TABLE = "yj_agent_info"
REQUIRED_AGENT_FIELDS = (
    "id",
    "name",
    "status",
    "tenant_id",
    "agent_id",
    "knowledge_base_id",
    "reply_strategy",
    "prompt_config",
)
REQUIRED_AGENT_COLUMNS = (
    "id",
    "name",
    "tenant_id",
    "status",
    "agent_id",
    "knowledge_base_id",
    "reply_strategy",
    "prompt_config",
    "deleted",
)


def resolve_workspace_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return WORKSPACE_ROOT / path


def extract_self_system_prompt(source_file: str | Path) -> str:
    source_path = Path(source_file)
    if source_path.name != "career-core.mjs":
        raise RuntimeError("source file must be career-core.mjs")
    if str(source_file) == "career-core.mjs":
        source_path = Path(DEFAULT_SOURCE_FILE)
    text = source_path.read_text(encoding="utf-8")
    start_marker = "const SELF_SYSTEM_PROMPT = `"
    end_marker = "`;\n\nconst HR_SYSTEM_PROMPT = `"
    start_at = text.find(start_marker)
    stop_at = text.find(end_marker)
    if start_at < 0 or stop_at < 0 or stop_at <= start_at:
        raise RuntimeError("SELF_SYSTEM_PROMPT not found in career-core.mjs")
    return text[slice(sum((start_at, len(start_marker))), stop_at)]


SELF_SYSTEM_PROMPT = extract_self_system_prompt("career-core.mjs")
AGENT_ROW = {
    "id": 3,
    "name": "职业规划评测",
    "status": 1,
    "tenant_id": 1,
    "agent_id": None,
    "knowledge_base_id": None,
    "reply_strategy": None,
    "prompt_config": SELF_SYSTEM_PROMPT,
}
INSERT_AGENT_SQL = """
INSERT INTO yj_agent_info (
    id,
    name,
    status,
    tenant_id,
    agent_id,
    knowledge_base_id,
    reply_strategy,
    prompt_config
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
""".strip()
READBACK_AGENT_SQL = """
SELECT
    id,
    name,
    status,
    tenant_id,
    agent_id,
    knowledge_base_id,
    reply_strategy,
    prompt_config
FROM yj_agent_info
WHERE id = %s
LIMIT 1
""".strip()
EXISTS_BY_ID_SQL = """
SELECT
    id
FROM yj_agent_info
WHERE id = %s
LIMIT 1
""".strip()
EXISTS_BY_NAME_SQL = """
SELECT
    id,
    name,
    status,
    tenant_id,
    agent_id,
    knowledge_base_id,
    reply_strategy,
    prompt_config
FROM yj_agent_info
WHERE deleted = b'0' AND name = %s
ORDER BY id ASC
""".strip()
EXISTS_BY_PROMPT_SQL = """
SELECT
    id,
    name,
    status,
    tenant_id,
    agent_id,
    knowledge_base_id,
    reply_strategy,
    prompt_config
FROM yj_agent_info
WHERE deleted = b'0' AND prompt_config = %s
ORDER BY id ASC
""".strip()
AGENT_COLUMNS_SQL = """
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
ORDER BY ORDINAL_POSITION
""".strip()


def load_application_database_target(app_config: str | Path) -> dict[str, Any]:
    matches: list[tuple[str, str, str]] = []
    for raw_line in resolve_workspace_path(app_config).read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "jdbc" not in line or ":mysql://" not in line:
            continue
        match = re.search(
            r"jdbc:mysql://(?P<host>[^/:?#]+):(?P<port>\d+)/(?P<database>[^?\s#]+)",
            line,
        )
        if match:
            matches.append((match.group("host"), match.group("port"), match.group("database")))
    if not matches:
        raise RuntimeError(f"application config missing jdbc:mysql target: {app_config}")
    distinct = {(host, int(port), database) for host, port, database in matches}
    if len(distinct) != 1:
        raise RuntimeError(f"application config exposes multiple database targets: {app_config}")
    host, port, database = next(iter(distinct))
    return {"host": host, "port": port, "database": database}


def assert_same_application_database(target: dict[str, Any], expected: dict[str, Any]) -> None:
    for field in ("host", "port", "database"):
        if target[field] != expected[field]:
            raise RuntimeError(
                f"database target mismatch for {field}: {target[field]!r} != {expected[field]!r}"
            )


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual Story-052 career assessment Agent initializer."
    )
    parser.add_argument(
        "--source-file",
        required=True,
        help="Explicit path to career-core.mjs used for extraction.",
    )
    parser.add_argument(
        "--app-config",
        default=(
            "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/"
            "src/main/resources/application-local.yaml"
        ),
        help="Current application-local.yaml path used for same-database verification.",
    )
    parser.add_argument(
        "--backup-dir",
        default="code/develop/yunjikeji-admin-server/sql/tools/story052_manual/output/backups",
        help="Directory for manual JSON backup files when --apply is used.",
    )
    parser.add_argument(
        "--receipt-dir",
        default="code/develop/yunjikeji-admin-server/sql/tools/story052_manual/output/receipts",
        help="Directory for apply receipts.",
    )
    parser.add_argument(
        "--db-user-env",
        default="YJ_AGENT_INIT_DB_USER",
        help="Environment variable name containing the database username for apply mode.",
    )
    parser.add_argument(
        "--db-password-env",
        default="YJ_AGENT_INIT_DB_PASSWORD",
        help="Environment variable name containing the database password for apply mode.",
    )
    parser.add_argument("--apply", action="store_true", help="Execute the insert after validation.")
    args, extras = parser.parse_known_args(argv)
    args.fixed_id = parse_apply_id(extras, args.apply)
    return args


def parse_apply_id(extras: list[str], write_mode: bool) -> int | None:
    if not extras:
        if write_mode:
            raise RuntimeError("apply requires explicit --id 3")
        return None
    value: str | None = None
    remainder: list[str] = []
    tokens = iter(extras)
    for token in tokens:
        if token == "--id":
            try:
                value = next(tokens)
            except StopIteration:
                raise RuntimeError("--id requires a value")
            continue
        if token.startswith("--id="):
            value = token.split("=", 1)[1]
            continue
        remainder.append(token)
    if remainder:
        raise RuntimeError(f"unsupported arguments: {' '.join(remainder)}")
    if not write_mode:
        raise RuntimeError("--id 3 is only allowed together with --apply")
    if value != "3":
        raise RuntimeError("apply requires exact --id 3")
    return 3


def summarize_prompt(prompt_text: str) -> dict[str, Any]:
    return {
        "characters": len(prompt_text),
        "bytes": len(prompt_text.encode("utf-8")),
        "sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest().upper(),
    }


def summarize_source_file(source_file: str | Path) -> dict[str, Any]:
    source_path = Path(source_file)
    source_text = source_path.read_text(encoding="utf-8")
    return {
        "path": str(source_path),
        "bytes": len(source_text.encode("utf-8")),
        "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest().upper(),
    }


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d%H%M%S")


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dt.time):
        return value.isoformat(timespec="seconds")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(output_path: Path, payload: dict[str, Any]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"{json.dumps(make_json_safe(payload), ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    return output_path


def build_base_receipt(
    args: argparse.Namespace,
    target: dict[str, Any],
    prompt_summary: dict[str, Any],
    source_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mode": "agent_init",
        "apply": bool(args.apply),
        "targetDatabase": {
            "host": target["host"],
            "port": target["port"],
            "database": target["database"],
        },
        "sourceFile": source_summary,
        "promptSummary": prompt_summary,
        "expected": {
            "sourceSha256": EXPECTED_SOURCE_FILE_SHA256,
            "promptSha256": EXPECTED_PROMPT_SHA256,
            "agentRow": copy.deepcopy(AGENT_ROW),
        },
    }


def validate_source_contract(
    prompt_text: str,
    prompt_summary: dict[str, Any],
    source_summary: dict[str, Any],
) -> None:
    if source_summary["sha256"] != EXPECTED_SOURCE_FILE_SHA256:
        raise RuntimeError(
            "career-core.mjs sha256 mismatch: "
            f"{source_summary['sha256']} != {EXPECTED_SOURCE_FILE_SHA256}"
        )
    if prompt_text != SELF_SYSTEM_PROMPT:
        raise RuntimeError("source file SELF_SYSTEM_PROMPT differs from the fixed initialization prompt")
    if prompt_summary["sha256"] != EXPECTED_PROMPT_SHA256:
        raise RuntimeError(
            f"SELF_SYSTEM_PROMPT sha256 mismatch: {prompt_summary['sha256']} != {EXPECTED_PROMPT_SHA256}"
        )


def load_db_credentials(username_env: str, password_env: str) -> tuple[str, str]:
    username = os.environ.get(username_env)
    password = os.environ.get(password_env)
    if not username or not password:
        raise RuntimeError(
            "apply requires database credentials in environment variables "
            f"{username_env} and {password_env}"
        )
    return username, password


def connect_database(
    target: dict[str, Any],
    username: str,
    password: str,
    connector: Any | None = None,
) -> Any:
    driver = connector or importlib.import_module("pymysql")
    return driver.connect(
        host=target["host"],
        port=target["port"],
        database=target["database"],
        user=username,
        password=password,
        charset="utf8mb4",
        cursorclass=getattr(driver.cursors, "DictCursor", None),
        autocommit=True,
    )


def query_rows(connection: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    if rows is None:
        return []
    return [dict(row) for row in rows]


def abort_if_exists(connection: Any, prompt_summary: dict[str, Any]) -> dict[str, Any]:
    columns = query_rows(connection, AGENT_COLUMNS_SQL, (AGENT_TABLE,))
    column_names = [row["COLUMN_NAME"] for row in columns]
    missing_columns = sorted(set(REQUIRED_AGENT_COLUMNS) - set(column_names))
    if missing_columns:
        raise RuntimeError(f"yj_agent_info missing required columns: {', '.join(missing_columns)}")

    fixed_id = 3
    existing_by_id = query_rows(
        connection,
        "SELECT id FROM yj_agent_info WHERE id = %s LIMIT 1",
        (fixed_id,),
    )
    if existing_by_id:
        raise RuntimeError("yj_agent_info.id=3 already exists; apply aborted with zero modifications")

    same_name_rows = query_rows(connection, EXISTS_BY_NAME_SQL, (AGENT_NAME,))
    same_prompt_rows = query_rows(connection, EXISTS_BY_PROMPT_SQL, (SELF_SYSTEM_PROMPT,))
    return {
        "columns": column_names,
        "sameNameRows": same_name_rows,
        "samePromptRows": same_prompt_rows,
        "targetPromptSha256": prompt_summary["sha256"],
    }


def backup_target_rows(
    connection: Any,
    preflight: dict[str, Any],
    backup_dir: str | Path,
    prompt_summary: dict[str, Any],
    source_summary: dict[str, Any],
) -> Path:
    backup_payload = {
        "createdAt": dt.datetime.now().isoformat(timespec="seconds"),
        "table": AGENT_TABLE,
        "fixedId": AGENT_ID,
        "preflight": preflight,
        "sourceFile": source_summary,
        "promptSummary": prompt_summary,
        "database": query_rows(
            connection,
            "SELECT DATABASE() AS database_name, NOW() AS backup_time",
            (),
        ),
    }
    filename = f"career-agent-backup-{now_stamp()}.json"
    return write_json(Path(backup_dir) / filename, backup_payload)


def start_transaction(connection: Any) -> None:
    connection.begin()


def insert_rows(connection: Any, row: dict[str, Any]) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(
            INSERT_AGENT_SQL,
            (
                row["id"],
                row["name"],
                row["status"],
                row["tenant_id"],
                row["agent_id"],
                row["knowledge_base_id"],
                row["reply_strategy"],
                row["prompt_config"],
            ),
        )
    finally:
        cursor.close()


def readback_agent_row(connection: Any) -> dict[str, Any]:
    rows = query_rows(connection, READBACK_AGENT_SQL, (AGENT_ID,))
    if len(rows) != 1:
        raise RuntimeError(f"expected one readback row for id={AGENT_ID}, got {len(rows)}")
    return rows[0]


def normalize_readback_status(value: Any) -> int:
    if isinstance(value, bool):
        raise RuntimeError(f"readback status is not an integer: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if value.is_finite() and value == value.to_integral_value():
            return int(value)
        raise RuntimeError(f"readback status is not an integer: {value!r}")
    if isinstance(value, (bytes, bytearray)):
        raw_value = bytes(value)
        try:
            decoded_value = raw_value.decode("ascii")
        except UnicodeDecodeError:
            if len(raw_value) == 1:
                return raw_value[0]
            raise RuntimeError(f"readback status is not an integer: {value!r}")
        normalized = decoded_value.strip()
        if re.fullmatch(r"[+-]?\d+", normalized):
            return int(normalized)
        if len(raw_value) == 1:
            return raw_value[0]
        raise RuntimeError(f"readback status is not an integer: {value!r}")
    if isinstance(value, str):
        normalized = value.strip()
        if re.fullmatch(r"[+-]?\d+", normalized):
            return int(normalized)
    raise RuntimeError(f"readback status is not an integer: {value!r}")


def verify_after_write(
    readback_row: dict[str, Any],
    prompt_summary: dict[str, Any],
    backup_path: Path,
    receipt_dir: str | Path,
    target: dict[str, Any],
    source_summary: dict[str, Any],
) -> dict[str, Any]:
    for field in REQUIRED_AGENT_FIELDS:
        readback_value = readback_row.get(field)
        if field == "status":
            readback_value = normalize_readback_status(readback_value)
        if readback_value != AGENT_ROW[field]:
            raise RuntimeError(
                f"readback mismatch for {field}: {readback_row.get(field)!r} != {AGENT_ROW[field]!r}"
            )
    readback_prompt_summary = summarize_prompt(str(readback_row["prompt_config"]))
    if readback_prompt_summary["sha256"] != prompt_summary["sha256"]:
        raise RuntimeError(
            "readback prompt hash mismatch: "
            f"{readback_prompt_summary['sha256']} != {prompt_summary['sha256']}"
        )
    receipt = {
        "createdAt": dt.datetime.now().isoformat(timespec="seconds"),
        "table": AGENT_TABLE,
        "database": target,
        "fixedId": AGENT_ID,
        "backupPath": str(backup_path),
        "sourceFile": source_summary,
        "promptSummary": prompt_summary,
        "readback": readback_row,
        "readbackPromptSummary": readback_prompt_summary,
    }
    receipt_path = Path(receipt_dir) / f"career-agent-apply-receipt-{now_stamp()}.json"
    write_json(receipt_path, receipt)
    receipt["receiptPath"] = str(receipt_path)
    return receipt


def print_receipt(receipt: dict[str, Any]) -> None:
    print(json.dumps(make_json_safe(receipt), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = parse_cli_args(argv)
    target = load_application_database_target(args.app_config)
    expected = load_application_database_target(
        "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/"
        "src/main/resources/application-local.yaml"
    )
    assert_same_application_database(target, expected)

    prompt_text = extract_self_system_prompt(args.source_file)
    prompt_summary = summarize_prompt(prompt_text)
    source_summary = summarize_source_file(args.source_file)
    validate_source_contract(prompt_text, prompt_summary, source_summary)

    dry_run_receipt = build_base_receipt(args, target, prompt_summary, source_summary)
    if not args.apply:
        dry_run_receipt["status"] = "dry-run"
        dry_run_receipt["notes"] = [
            "No database connection was opened.",
            "Run again with --apply --id 3 after manual review.",
        ]
        print_receipt(dry_run_receipt)
        return 0

    username, password = load_db_credentials(args.db_user_env, args.db_password_env)
    connection = connect_database(target, username, password)
    try:
        preflight = abort_if_exists(connection, prompt_summary)
        backup_path = backup_target_rows(
            connection,
            preflight,
            args.backup_dir,
            prompt_summary,
            source_summary,
        )
        start_transaction(connection)
        try:
            insert_rows(connection, AGENT_ROW)
            readback_row = readback_agent_row(connection)
            final_receipt = verify_after_write(
                readback_row,
                prompt_summary,
                backup_path,
                args.receipt_dir,
                target,
                source_summary,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    print_receipt(final_receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
