#!/usr/bin/env python3
"""Execute the practice question tenant_id repair with before/after checks."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pymysql


TASK_DIR = Path(__file__).resolve().parent
RESULT_PATH = TASK_DIR / "execution_result.json"
ROLLBACK_SQL_PATH = TASK_DIR / "rollback_yj_practice_exercises_tenant_id.sql"

DB_CONFIG = {
    "host": "114.111.30.111",
    "port": 13306,
    "user": "yunjikeji_test",
    "password": "yunjikeji_test8978_",
    "database": "yunjikeji",
    "charset": "utf8mb4",
    "autocommit": False,
}

TARGET_TABLES = (
    "yj_practice_exercises",
    "yj_practice_exercises_answer",
    "yj_practice_exercises_answer_child",
)

REFERENCE_TABLES = (
    "yj_assessment_question",
    "yj_assessment_answer",
)


def quote_identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def fetch_one(cursor, sql: str):
    cursor.execute(sql)
    return cursor.fetchone()


def fetch_all(cursor, sql: str):
    cursor.execute(sql)
    return cursor.fetchall()


def table_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table,),
    )
    return cursor.fetchone()["table_count"] == 1


def collect_counts(cursor, table: str):
    table_sql = quote_identifier(table)
    if not table_exists(cursor, table):
        return {"exists": False}
    return {
        "exists": True,
        "summary": fetch_one(
            cursor,
            f"""
            SELECT
              COUNT(*) AS total_rows,
              SUM(CASE WHEN tenant_id = 1 THEN 1 ELSE 0 END) AS tenant_id_1_rows,
              SUM(CASE WHEN tenant_id <> 1 OR tenant_id IS NULL THEN 1 ELSE 0 END) AS tenant_id_not_1_or_null_rows
            FROM {table_sql}
            """,
        ),
        "distribution": fetch_all(
            cursor,
            f"""
            SELECT tenant_id, deleted, COUNT(*) AS row_count
            FROM {table_sql}
            GROUP BY tenant_id, deleted
            ORDER BY tenant_id, deleted
            """,
        ),
    }


def write_rollback_sql(run_id: str, backup_tables: dict[str, str]) -> None:
    blocks = []
    for table, backup_table in backup_tables.items():
        blocks.append(
            f"""
-- Restore {table}.tenant_id from {backup_table}
SELECT COUNT(*) AS backup_rows FROM {quote_identifier(backup_table)};

UPDATE {quote_identifier(table)} t
JOIN {quote_identifier(backup_table)} b ON b.id = t.id
SET t.tenant_id = b.tenant_id;

SELECT ROW_COUNT() AS restored_rows_for_{table};
"""
        )

    ROLLBACK_SQL_PATH.write_text(
        f"""-- ============================================
-- Script type: DML rollback script
-- Description: restore practice question tenant_id values from backup tables
-- Created at: {datetime.now().isoformat(timespec="seconds")}
-- Author: Codex
-- Scope: yunjikeji practice question tenant_id only
-- Environment: test database only
-- Execution run id: {run_id}
-- ============================================

START TRANSACTION;
{''.join(blocks)}
-- Rollback post-check.
SELECT 'yj_practice_exercises' AS table_name, tenant_id, deleted, COUNT(*) AS row_count
FROM yj_practice_exercises
GROUP BY tenant_id, deleted
UNION ALL
SELECT 'yj_practice_exercises_answer' AS table_name, tenant_id, deleted, COUNT(*) AS row_count
FROM yj_practice_exercises_answer
GROUP BY tenant_id, deleted
UNION ALL
SELECT 'yj_practice_exercises_answer_child' AS table_name, tenant_id, deleted, COUNT(*) AS row_count
FROM yj_practice_exercises_answer_child
GROUP BY tenant_id, deleted;

COMMIT;
""",
        encoding="utf-8",
    )


def main() -> int:
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    result = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "database": f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
        "target_tables": TARGET_TABLES,
        "reference_tables": REFERENCE_TABLES,
        "target_tenant_id": 1,
        "run_id": run_id,
    }

    conn = pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **DB_CONFIG)
    backup_tables: dict[str, str] = {}
    try:
        with conn.cursor() as cursor:
            result["before"] = {table: collect_counts(cursor, table) for table in TARGET_TABLES}
            result["reference_before"] = {table: collect_counts(cursor, table) for table in REFERENCE_TABLES}

            result["backup"] = {}
            result["affected_rows"] = {}
            for table in TARGET_TABLES:
                if not table_exists(cursor, table):
                    raise RuntimeError(f"target table does not exist: {table}")
                backup_table = f"{table}_tenant_bak_{run_id}"
                backup_tables[table] = backup_table
                cursor.execute(
                    f"""
                    CREATE TABLE {quote_identifier(backup_table)} (
                      id BIGINT NOT NULL PRIMARY KEY,
                      tenant_id BIGINT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    INSERT INTO {quote_identifier(backup_table)} (id, tenant_id)
                    SELECT id, tenant_id
                    FROM {quote_identifier(table)}
                    WHERE tenant_id <> 1 OR tenant_id IS NULL
                    """
                )
                result["backup"][table] = {
                    "table": backup_table,
                    "rows": fetch_one(cursor, f"SELECT COUNT(*) AS backup_rows FROM {quote_identifier(backup_table)}"),
                }
                cursor.execute(
                    f"""
                    UPDATE {quote_identifier(table)}
                    SET tenant_id = 1
                    WHERE tenant_id <> 1 OR tenant_id IS NULL
                    """
                )
                result["affected_rows"][table] = cursor.rowcount

            result["after"] = {table: collect_counts(cursor, table) for table in TARGET_TABLES}
            result["reference_after"] = {table: collect_counts(cursor, table) for table in REFERENCE_TABLES}

            failures = []
            for table, counts in result["after"].items():
                remaining = counts["summary"]["tenant_id_not_1_or_null_rows"] or 0
                if remaining != 0:
                    failures.append(f"{table}: remaining non-1/null rows = {remaining}")
            if failures:
                raise RuntimeError("; ".join(failures))

        conn.commit()
        write_rollback_sql(run_id, backup_tables)
        result["rollback_sql"] = str(ROLLBACK_SQL_PATH)
        result["status"] = "committed"
        return 0
    except Exception as exc:
        conn.rollback()
        result["status"] = "rolled_back"
        result["error"] = repr(exc)
        return 1
    finally:
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")
        RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
