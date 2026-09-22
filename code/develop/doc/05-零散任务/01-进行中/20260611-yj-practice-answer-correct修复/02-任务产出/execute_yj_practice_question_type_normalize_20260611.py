from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pymysql


TASK_DIR = Path(__file__).resolve().parent
RESULT_PATH = TASK_DIR / "practice_question_type_normalize_result_20260611.json"
ROLLBACK_SQL_PATH = TASK_DIR / "rollback_yj_practice_question_type_normalize_20260611.sql"
BACKUP_SUFFIX = datetime.now().strftime("%Y%m%d%H%M%S")

TENANT_ID = 1
LEGACY_TYPE = "2"
NORMALIZED_TYPE = "single_choice"
OPERATOR = "codex_20260611"

BACKUP_TABLES = {
    "yj_practice_exercises": f"yj_practice_exercises_qtype_bak_{BACKUP_SUFFIX}",
    "yj_practice_exercises_answer": f"yj_practice_answer_qtype_bak_{BACKUP_SUFFIX}",
    "yj_practice_exercises_answer_child": f"yj_practice_answer_child_qtype_bak_{BACKUP_SUFFIX}",
}

DB_CONFIG = {
    "host": "114.111.30.111",
    "port": 13306,
    "user": "yunjikeji_test",
    "password": "yunjikeji_test8978_",
    "database": "yunjikeji",
    "charset": "utf8mb4",
    "use_unicode": True,
    "cursorclass": pymysql.cursors.DictCursor,
}


def fetch_all(cursor, sql: str, args: tuple = ()) -> list[dict]:
    cursor.execute(sql, args)
    return list(cursor.fetchall())


def count_legacy_rows(cursor, table: str) -> int:
    cursor.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM `{table}`
        WHERE tenant_id = %s
          AND deleted = b'0'
          AND question_type = %s
        """,
        (TENANT_ID, LEGACY_TYPE),
    )
    return int(cursor.fetchone()["count"])


def get_type_distribution(cursor, table: str) -> list[dict]:
    return fetch_all(
        cursor,
        f"""
        SELECT question_type, COUNT(*) AS count
        FROM `{table}`
        WHERE tenant_id = %s
          AND deleted = b'0'
        GROUP BY question_type
        ORDER BY count DESC, question_type ASC
        """,
        (TENANT_ID,),
    )


def backup_table(cursor, table: str, backup_table: str) -> int:
    cursor.execute(f"CREATE TABLE IF NOT EXISTS `{backup_table}` LIKE `{table}`")
    cursor.execute(f"DELETE FROM `{backup_table}`")
    cursor.execute(
        f"""
        INSERT INTO `{backup_table}`
        SELECT *
        FROM `{table}`
        WHERE tenant_id = %s
          AND deleted = b'0'
          AND question_type = %s
        """,
        (TENANT_ID, LEGACY_TYPE),
    )
    return int(cursor.rowcount)


def update_legacy_rows(cursor, table: str) -> int:
    cursor.execute(
        f"""
        UPDATE `{table}`
        SET question_type = %s,
            updater = %s,
            update_time = NOW()
        WHERE tenant_id = %s
          AND deleted = b'0'
          AND question_type = %s
        """,
        (NORMALIZED_TYPE, OPERATOR, TENANT_ID, LEGACY_TYPE),
    )
    return int(cursor.rowcount)


def write_rollback_sql() -> None:
    exercise_backup = BACKUP_TABLES["yj_practice_exercises"]
    answer_backup = BACKUP_TABLES["yj_practice_exercises_answer"]
    answer_child_backup = BACKUP_TABLES["yj_practice_exercises_answer_child"]
    ROLLBACK_SQL_PATH.write_text(
        f"""-- Rollback for execute_yj_practice_question_type_normalize_20260611.py
-- Generated at: {datetime.now().isoformat(timespec="seconds")}
-- Legacy question_type '{LEGACY_TYPE}' was normalized to '{NORMALIZED_TYPE}'.
-- Backup tables:
--   {exercise_backup}
--   {answer_backup}
--   {answer_child_backup}

START TRANSACTION;

UPDATE yj_practice_exercises t
JOIN `{exercise_backup}` b ON b.id = t.id
SET t.question_type = b.question_type,
    t.updater = b.updater,
    t.update_time = b.update_time
WHERE t.tenant_id = {TENANT_ID}
  AND t.deleted = b'0';

UPDATE yj_practice_exercises_answer t
JOIN `{answer_backup}` b ON b.id = t.id
SET t.question_type = b.question_type,
    t.updater = b.updater,
    t.update_time = b.update_time
WHERE t.tenant_id = {TENANT_ID}
  AND t.deleted = b'0';

UPDATE yj_practice_exercises_answer_child t
JOIN `{answer_child_backup}` b ON b.id = t.id
SET t.question_type = b.question_type,
    t.updater = b.updater,
    t.update_time = b.update_time
WHERE t.tenant_id = {TENANT_ID}
  AND t.deleted = b'0';

COMMIT;

-- Verification after rollback:
-- SELECT question_type, COUNT(*) FROM yj_practice_exercises WHERE tenant_id = {TENANT_ID} AND deleted = b'0' GROUP BY question_type;
-- SELECT question_type, COUNT(*) FROM yj_practice_exercises_answer WHERE tenant_id = {TENANT_ID} AND deleted = b'0' GROUP BY question_type;
-- SELECT question_type, COUNT(*) FROM yj_practice_exercises_answer_child WHERE tenant_id = {TENANT_ID} AND deleted = b'0' GROUP BY question_type;
""",
        encoding="utf-8",
    )


def main() -> None:
    result: dict = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "database": f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
        "tenant_id": TENANT_ID,
        "legacy_type": LEGACY_TYPE,
        "normalized_type": NORMALIZED_TYPE,
        "backup_tables": BACKUP_TABLES,
        "before": {},
        "actions": [],
        "after": {},
    }

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            tables = list(BACKUP_TABLES)
            result["before"]["type_distribution"] = {
                table: get_type_distribution(cursor, table) for table in tables
            }
            result["before"]["legacy_counts"] = {
                table: count_legacy_rows(cursor, table) for table in tables
            }

            for table, backup in BACKUP_TABLES.items():
                backup_rows = backup_table(cursor, table, backup)
                result["actions"].append({"backup": backup, "source_table": table, "rows": backup_rows})

            for table in tables:
                updated_rows = update_legacy_rows(cursor, table)
                result["actions"].append({"normalize_table": table, "rows": updated_rows})

            result["after"]["type_distribution"] = {
                table: get_type_distribution(cursor, table) for table in tables
            }
            result["after"]["legacy_counts"] = {
                table: count_legacy_rows(cursor, table) for table in tables
            }

            remaining = {
                table: count
                for table, count in result["after"]["legacy_counts"].items()
                if count != 0
            }
            if remaining:
                raise RuntimeError(f"Legacy question_type remains after normalize: {remaining}")

            write_rollback_sql()

        conn.commit()
        result["status"] = "committed"
    except Exception as exc:
        conn.rollback()
        result["status"] = "rolled_back"
        result["error"] = repr(exc)
        raise
    finally:
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")
        RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        conn.close()


if __name__ == "__main__":
    main()
