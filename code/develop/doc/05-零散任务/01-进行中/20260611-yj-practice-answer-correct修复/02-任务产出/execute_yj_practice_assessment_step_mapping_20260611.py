from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pymysql


TASK_DIR = Path(__file__).resolve().parent
RESULT_PATH = TASK_DIR / "practice_assessment_step_mapping_result_20260611.json"
ROLLBACK_SQL_PATH = TASK_DIR / "rollback_yj_practice_assessment_step_mapping_20260611.sql"
BACKUP_SUFFIX = datetime.now().strftime("%Y%m%d%H%M%S")
STEP_BACKUP_TABLE = f"yj_practice_assessment_step_bak_{BACKUP_SUFFIX}"
EXERCISE_BACKUP_TABLE = f"yj_practice_assessment_exercise_bak_{BACKUP_SUFFIX}"

TENANT_ID = 1
ASSESSMENT_CATEGORY_ID = 13
EXPECTED_ASSESSMENT_COUNT = 21
OPERATOR = "codex_20260611"

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

STEP_DEFINITIONS = [
    {
        "sort_no": 1,
        "setp_name": "第一部分：您的基本信息",
        "exercise_sort_min": 1,
        "exercise_sort_max": 7,
        "expected_ids": list(range(2749, 2756)),
    },
    {
        "sort_no": 2,
        "setp_name": "第二部分：入行动机与自身优势",
        "exercise_sort_min": 8,
        "exercise_sort_max": 13,
        "expected_ids": list(range(2756, 2762)),
    },
    {
        "sort_no": 3,
        "setp_name": "第三部分：行业方向与学习条件",
        "exercise_sort_min": 14,
        "exercise_sort_max": 19,
        "expected_ids": list(range(2762, 2768)),
    },
    {
        "sort_no": 4,
        "setp_name": "第四部分：最终确认",
        "exercise_sort_min": 20,
        "exercise_sort_max": 21,
        "expected_ids": list(range(2768, 2770)),
    },
]


def fetch_all(cursor, sql: str, args: tuple = ()) -> list[dict]:
    cursor.execute(sql, args)
    return list(cursor.fetchall())


def fetch_one(cursor, sql: str, args: tuple = ()) -> dict:
    cursor.execute(sql, args)
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Expected one row, got none")
    return row


def assert_preconditions(cursor) -> dict:
    category_rows = fetch_all(
        cursor,
        """
        SELECT id, category_name, catalog_type, tenant_id, HEX(deleted) AS deleted_hex
        FROM yj_practice_category
        WHERE tenant_id = %s
          AND deleted = b'0'
          AND catalog_type = 1
        ORDER BY id
        """,
        (TENANT_ID,),
    )
    if len(category_rows) != 1 or category_rows[0]["id"] != ASSESSMENT_CATEGORY_ID:
        raise RuntimeError(f"Unexpected assessment category rows: {category_rows}")

    assessment_rows = fetch_all(
        cursor,
        """
        SELECT e.id, e.sort_no, e.step_id, e.category_id, LEFT(e.question_stem, 120) AS question_stem
        FROM yj_practice_exercises e
        JOIN yj_practice_category c ON c.id = e.category_id
        WHERE e.tenant_id = %s
          AND e.deleted = b'0'
          AND c.tenant_id = %s
          AND c.deleted = b'0'
          AND c.catalog_type = 1
        ORDER BY e.sort_no ASC, e.id ASC
        """,
        (TENANT_ID, TENANT_ID),
    )
    if len(assessment_rows) != EXPECTED_ASSESSMENT_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_ASSESSMENT_COUNT} assessment exercises, got {len(assessment_rows)}")

    actual_ids = [row["id"] for row in assessment_rows]
    expected_ids = [exercise_id for step in STEP_DEFINITIONS for exercise_id in step["expected_ids"]]
    if actual_ids != expected_ids:
        raise RuntimeError(f"Unexpected assessment exercise ids: {actual_ids}")

    actual_sort_numbers = [row["sort_no"] for row in assessment_rows]
    if actual_sort_numbers != list(range(1, EXPECTED_ASSESSMENT_COUNT + 1)):
        raise RuntimeError(f"Unexpected assessment sort_no sequence: {actual_sort_numbers}")

    return {
        "assessment_category": category_rows,
        "assessment_exercises": assessment_rows,
        "catalog_type_0_step_id_summary": fetch_all(
            cursor,
            """
            SELECT COUNT(*) AS total_count,
                   SUM(CASE WHEN e.step_id IS NULL THEN 1 ELSE 0 END) AS null_step_count,
                   SUM(CASE WHEN e.step_id IS NOT NULL THEN 1 ELSE 0 END) AS non_null_step_count
            FROM yj_practice_exercises e
            JOIN yj_practice_category c ON c.id = e.category_id
            WHERE e.tenant_id = %s
              AND e.deleted = b'0'
              AND c.tenant_id = %s
              AND c.deleted = b'0'
              AND c.catalog_type = 0
            """,
            (TENANT_ID, TENANT_ID),
        ),
        "existing_steps": fetch_all(
            cursor,
            """
            SELECT id, tenant_id, setp_name, sort_no, HEX(deleted) AS deleted_hex
            FROM yj_practice_setp
            WHERE tenant_id = %s AND deleted = b'0'
            ORDER BY sort_no ASC, id ASC
            """,
            (TENANT_ID,),
        ),
    }


def create_backups(cursor) -> dict:
    cursor.execute(f"CREATE TABLE IF NOT EXISTS `{STEP_BACKUP_TABLE}` LIKE yj_practice_setp")
    cursor.execute(f"DELETE FROM `{STEP_BACKUP_TABLE}`")
    cursor.execute(
        f"""
        INSERT INTO `{STEP_BACKUP_TABLE}`
        SELECT *
        FROM yj_practice_setp
        WHERE tenant_id = %s
          AND deleted = b'0'
        """,
        (TENANT_ID,),
    )
    step_backup_rows = cursor.rowcount

    cursor.execute(f"CREATE TABLE IF NOT EXISTS `{EXERCISE_BACKUP_TABLE}` LIKE yj_practice_exercises")
    cursor.execute(f"DELETE FROM `{EXERCISE_BACKUP_TABLE}`")
    cursor.execute(
        f"""
        INSERT INTO `{EXERCISE_BACKUP_TABLE}`
        SELECT e.*
        FROM yj_practice_exercises e
        JOIN yj_practice_category c ON c.id = e.category_id
        WHERE e.tenant_id = %s
          AND e.deleted = b'0'
          AND c.tenant_id = %s
          AND c.deleted = b'0'
          AND c.catalog_type = 1
        """,
        (TENANT_ID, TENANT_ID),
    )
    exercise_backup_rows = cursor.rowcount
    if exercise_backup_rows != EXPECTED_ASSESSMENT_COUNT:
        raise RuntimeError(f"Expected to back up 21 assessment exercises, got {exercise_backup_rows}")

    return {
        "step_backup_table": STEP_BACKUP_TABLE,
        "step_backup_rows": step_backup_rows,
        "exercise_backup_table": EXERCISE_BACKUP_TABLE,
        "exercise_backup_rows": exercise_backup_rows,
    }


def upsert_steps_and_map_exercises(cursor) -> dict:
    step_ids_by_sort_no: dict[int, int] = {}
    actions: list[dict] = []

    for step in STEP_DEFINITIONS:
        existing = fetch_all(
            cursor,
            """
            SELECT id
            FROM yj_practice_setp
            WHERE tenant_id = %s
              AND deleted = b'0'
              AND sort_no = %s
              AND setp_name = %s
            ORDER BY id ASC
            LIMIT 1
            """,
            (TENANT_ID, step["sort_no"], step["setp_name"]),
        )
        if existing:
            step_id = existing[0]["id"]
            cursor.execute(
                """
                UPDATE yj_practice_setp
                SET updater = %s, update_time = NOW()
                WHERE id = %s
                """,
                (OPERATOR, step_id),
            )
            actions.append({"reuse_step": step["setp_name"], "step_id": step_id})
        else:
            cursor.execute(
                """
                INSERT INTO yj_practice_setp
                    (tenant_id, setp_name, setp_status, sort_no, creator, create_time, updater, update_time, deleted)
                VALUES
                    (%s, %s, b'1', %s, %s, NOW(), %s, NOW(), b'0')
                """,
                (TENANT_ID, step["setp_name"], step["sort_no"], OPERATOR, OPERATOR),
            )
            step_id = cursor.lastrowid
            actions.append({"insert_step": step["setp_name"], "step_id": step_id})
        step_ids_by_sort_no[step["sort_no"]] = step_id

        cursor.execute(
            """
            UPDATE yj_practice_exercises e
            JOIN yj_practice_category c ON c.id = e.category_id
            SET e.step_id = %s,
                e.updater = %s,
                e.update_time = NOW()
            WHERE e.tenant_id = %s
              AND e.deleted = b'0'
              AND c.tenant_id = %s
              AND c.deleted = b'0'
              AND c.catalog_type = 1
              AND e.sort_no BETWEEN %s AND %s
            """,
            (
                step_id,
                OPERATOR,
                TENANT_ID,
                TENANT_ID,
                step["exercise_sort_min"],
                step["exercise_sort_max"],
            ),
        )
        actions.append(
            {
                "map_exercises": step["setp_name"],
                "step_id": step_id,
                "sort_range": [step["exercise_sort_min"], step["exercise_sort_max"]],
                "rows": cursor.rowcount,
            }
        )

    return {"step_ids_by_sort_no": step_ids_by_sort_no, "actions": actions}


def verify_after(cursor) -> dict:
    steps = fetch_all(
        cursor,
        """
        SELECT id, tenant_id, setp_name, sort_no, HEX(deleted) AS deleted_hex
        FROM yj_practice_setp
        WHERE tenant_id = %s AND deleted = b'0'
        ORDER BY sort_no ASC, id ASC
        """,
        (TENANT_ID,),
    )
    assessment_mapping = fetch_all(
        cursor,
        """
        SELECT s.id AS step_id,
               s.setp_name,
               s.sort_no AS step_sort_no,
               COUNT(e.id) AS exercise_count,
               MIN(e.sort_no) AS min_exercise_sort_no,
               MAX(e.sort_no) AS max_exercise_sort_no,
               GROUP_CONCAT(e.id ORDER BY e.sort_no ASC, e.id ASC) AS exercise_ids
        FROM yj_practice_setp s
        LEFT JOIN yj_practice_exercises e
               ON e.step_id = s.id
              AND e.tenant_id = %s
              AND e.deleted = b'0'
        LEFT JOIN yj_practice_category c ON c.id = e.category_id
        WHERE s.tenant_id = %s
          AND s.deleted = b'0'
          AND (c.id IS NULL OR (c.tenant_id = %s AND c.deleted = b'0' AND c.catalog_type = 1))
        GROUP BY s.id, s.setp_name, s.sort_no
        ORDER BY s.sort_no ASC, s.id ASC
        """,
        (TENANT_ID, TENANT_ID, TENANT_ID),
    )
    assessment_unmapped = fetch_one(
        cursor,
        """
        SELECT COUNT(*) AS count
        FROM yj_practice_exercises e
        JOIN yj_practice_category c ON c.id = e.category_id
        WHERE e.tenant_id = %s
          AND e.deleted = b'0'
          AND c.tenant_id = %s
          AND c.deleted = b'0'
          AND c.catalog_type = 1
          AND e.step_id IS NULL
        """,
        (TENANT_ID, TENANT_ID),
    )["count"]
    catalog_type_0_summary = fetch_all(
        cursor,
        """
        SELECT COUNT(*) AS total_count,
               SUM(CASE WHEN e.step_id IS NULL THEN 1 ELSE 0 END) AS null_step_count,
               SUM(CASE WHEN e.step_id IS NOT NULL THEN 1 ELSE 0 END) AS non_null_step_count
        FROM yj_practice_exercises e
        JOIN yj_practice_category c ON c.id = e.category_id
        WHERE e.tenant_id = %s
          AND e.deleted = b'0'
          AND c.tenant_id = %s
          AND c.deleted = b'0'
          AND c.catalog_type = 0
        """,
        (TENANT_ID, TENANT_ID),
    )
    exercise_detail = fetch_all(
        cursor,
        """
        SELECT e.id, e.sort_no, e.step_id, s.setp_name, c.catalog_type, LEFT(e.question_stem, 120) AS question_stem
        FROM yj_practice_exercises e
        JOIN yj_practice_category c ON c.id = e.category_id
        LEFT JOIN yj_practice_setp s ON s.id = e.step_id
        WHERE e.tenant_id = %s
          AND e.deleted = b'0'
          AND c.tenant_id = %s
          AND c.deleted = b'0'
          AND c.catalog_type = 1
        ORDER BY e.sort_no ASC, e.id ASC
        """,
        (TENANT_ID, TENANT_ID),
    )

    expected_names = [step["setp_name"] for step in STEP_DEFINITIONS]
    expected_step_sort_numbers = [step["sort_no"] for step in STEP_DEFINITIONS]
    if [row["setp_name"] for row in steps] != expected_names:
        raise RuntimeError(f"Unexpected step names after update: {steps}")
    if [row["sort_no"] for row in steps] != expected_step_sort_numbers:
        raise RuntimeError(f"Unexpected step sort_no after update: {steps}")
    if assessment_unmapped != 0:
        raise RuntimeError(f"Assessment exercises still unmapped: {assessment_unmapped}")
    if len(exercise_detail) != EXPECTED_ASSESSMENT_COUNT:
        raise RuntimeError(f"Expected 21 mapped exercises after update, got {len(exercise_detail)}")

    return {
        "steps": steps,
        "assessment_mapping": assessment_mapping,
        "assessment_unmapped_count": assessment_unmapped,
        "catalog_type_0_step_id_summary": catalog_type_0_summary,
        "exercise_detail": exercise_detail,
    }


def write_rollback_sql(result: dict) -> None:
    rollback_sql = f"""-- Rollback for execute_yj_practice_assessment_step_mapping_20260611.py
-- Generated at: {datetime.now().isoformat(timespec="seconds")}
-- Backup tables:
--   {STEP_BACKUP_TABLE}
--   {EXERCISE_BACKUP_TABLE}

START TRANSACTION;

UPDATE yj_practice_exercises e
JOIN `{EXERCISE_BACKUP_TABLE}` b ON b.id = e.id
SET e.step_id = b.step_id,
    e.updater = b.updater,
    e.update_time = b.update_time
WHERE e.tenant_id = {TENANT_ID}
  AND e.deleted = b'0';

DELETE s
FROM yj_practice_setp s
LEFT JOIN `{STEP_BACKUP_TABLE}` b ON b.id = s.id
WHERE s.tenant_id = {TENANT_ID}
  AND s.deleted = b'0'
  AND b.id IS NULL;

UPDATE yj_practice_setp s
JOIN `{STEP_BACKUP_TABLE}` b ON b.id = s.id
SET s.tenant_id = b.tenant_id,
    s.setp_name = b.setp_name,
    s.setp_status = b.setp_status,
    s.sort_no = b.sort_no,
    s.creator = b.creator,
    s.create_time = b.create_time,
    s.updater = b.updater,
    s.update_time = b.update_time,
    s.deleted = b.deleted;

COMMIT;

-- Verification after rollback:
-- SELECT id, tenant_id, setp_name, sort_no, HEX(deleted) FROM yj_practice_setp WHERE tenant_id = {TENANT_ID} ORDER BY sort_no, id;
-- SELECT e.id, e.sort_no, e.step_id FROM yj_practice_exercises e JOIN yj_practice_category c ON c.id = e.category_id WHERE e.tenant_id = {TENANT_ID} AND e.deleted = b'0' AND c.tenant_id = {TENANT_ID} AND c.deleted = b'0' AND c.catalog_type = 1 ORDER BY e.sort_no, e.id;
"""
    ROLLBACK_SQL_PATH.write_text(rollback_sql, encoding="utf-8")
    result["rollback_sql_path"] = str(ROLLBACK_SQL_PATH)


def main() -> None:
    result: dict = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "database": f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
        "tenant_id": TENANT_ID,
        "assessment_category_id": ASSESSMENT_CATEGORY_ID,
        "backup_tables": {
            "yj_practice_setp": STEP_BACKUP_TABLE,
            "yj_practice_exercises": EXERCISE_BACKUP_TABLE,
        },
        "before": {},
        "actions": [],
        "after": {},
    }
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            result["before"] = assert_preconditions(cursor)
            backup_result = create_backups(cursor)
            result["actions"].append({"backup": backup_result})
        conn.commit()

        with conn.cursor() as cursor:
            mapping_result = upsert_steps_and_map_exercises(cursor)
            result["actions"].extend(mapping_result["actions"])
            result["after"] = verify_after(cursor)
        conn.commit()
        result["status"] = "committed"
    except Exception as exc:
        conn.rollback()
        result["status"] = "rolled_back"
        result["error"] = repr(exc)
        raise
    finally:
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")
        write_rollback_sql(result)
        RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        conn.close()


if __name__ == "__main__":
    main()
