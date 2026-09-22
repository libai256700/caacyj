from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pymysql


TASK_DIR = Path(__file__).resolve().parent
RESULT_PATH = TASK_DIR / "practice_category_catalog_type_update_result_20260611.json"
BACKUP_SUFFIX = datetime.now().strftime("%Y%m%d%H%M%S")
BACKUP_TABLE = f"yj_practice_category_catalog_type_bak_{BACKUP_SUFFIX}"

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


def column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table, column),
    )
    return cursor.fetchone()["count"] > 0


def main() -> None:
    result = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "database": f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
        "backup_table": BACKUP_TABLE,
        "before": {},
        "actions": [],
        "after": {},
    }
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            result["before"]["columns"] = fetch_all(cursor, "SHOW COLUMNS FROM yj_practice_category")
            result["before"]["category_sample"] = fetch_all(
                cursor,
                """
                SELECT id, category_name, tenant_id, deleted
                FROM yj_practice_category
                WHERE deleted = b'0'
                ORDER BY id
                """,
            )

            cursor.execute(f"CREATE TABLE IF NOT EXISTS `{BACKUP_TABLE}` LIKE yj_practice_category")
            cursor.execute(f"INSERT INTO `{BACKUP_TABLE}` SELECT * FROM yj_practice_category")
            result["actions"].append({"backup": BACKUP_TABLE, "rows": cursor.rowcount})

            if not column_exists(cursor, "yj_practice_category", "catalog_type"):
                cursor.execute(
                    """
                    ALTER TABLE yj_practice_category
                    ADD COLUMN catalog_type int NOT NULL DEFAULT 0 COMMENT '0.练习，1.自测' AFTER field_type
                    """
                )
                result["actions"].append({"add_column": "yj_practice_category.catalog_type"})
            else:
                result["actions"].append({"skip_add_column": "yj_practice_category.catalog_type"})

            cursor.execute(
                """
                UPDATE yj_practice_category
                SET catalog_type = 0
                WHERE deleted = b'0'
                  AND (catalog_type IS NULL OR catalog_type <> 0)
                  AND id <> 13
                """
            )
            result["actions"].append({"set_practice_categories": cursor.rowcount})

            cursor.execute(
                """
                UPDATE yj_practice_category
                SET catalog_type = 1
                WHERE id = 13 AND deleted = b'0'
                """
            )
            result["actions"].append({"set_assessment_category_id_13": cursor.rowcount})

            if not column_exists(cursor, "yj_practice_category", "catalog_type"):
                raise RuntimeError("catalog_type column was not created")

            result["after"]["columns"] = fetch_all(cursor, "SHOW COLUMNS FROM yj_practice_category")
            result["after"]["category_types"] = fetch_all(
                cursor,
                """
                SELECT c.id, c.category_name, c.catalog_type, COUNT(e.id) AS exercise_count
                FROM yj_practice_category c
                LEFT JOIN yj_practice_exercises e ON e.category_id = c.id AND e.deleted = b'0'
                WHERE c.deleted = b'0'
                GROUP BY c.id, c.category_name, c.catalog_type
                ORDER BY c.catalog_type, c.id
                """,
            )
            result["after"]["assessment_question_count"] = fetch_all(
                cursor,
                """
                SELECT COUNT(*) AS count
                FROM yj_practice_exercises e
                JOIN yj_practice_category c ON c.id = e.category_id
                WHERE e.deleted = b'0' AND c.deleted = b'0' AND c.catalog_type = 1
                """,
            )
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
