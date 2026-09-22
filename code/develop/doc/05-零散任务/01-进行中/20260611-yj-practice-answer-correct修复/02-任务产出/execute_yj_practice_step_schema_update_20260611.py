from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pymysql


TASK_DIR = Path(__file__).resolve().parent
RESULT_PATH = TASK_DIR / "practice_step_schema_update_result_20260611.json"
BACKUP_SUFFIX = datetime.now().strftime("%Y%m%d%H%M%S")
BACKUP_TABLE = f"yj_practice_exercises_schema_bak_{BACKUP_SUFFIX}"

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


def table_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table,),
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
            result["before"]["practice_exercises_columns"] = fetch_all(cursor, "SHOW COLUMNS FROM yj_practice_exercises")
            result["before"]["practice_setp_exists"] = table_exists(cursor, "yj_practice_setp")
            result["before"]["assessment_order_sample"] = fetch_all(
                cursor,
                """
                SELECT id, sort_no, question_stem
                FROM yj_practice_exercises
                WHERE category_id = 13 AND tenant_id = 1 AND deleted = b'0'
                ORDER BY sort_no ASC, id ASC
                LIMIT 5
                """,
            )

            cursor.execute(f"CREATE TABLE IF NOT EXISTS `{BACKUP_TABLE}` LIKE yj_practice_exercises")
            cursor.execute(f"INSERT INTO `{BACKUP_TABLE}` SELECT * FROM yj_practice_exercises")
            result["actions"].append({"backup": BACKUP_TABLE, "rows": cursor.rowcount})

            if not table_exists(cursor, "yj_practice_setp"):
                cursor.execute(
                    """
                    CREATE TABLE yj_practice_setp (
                      id bigint NOT NULL AUTO_INCREMENT COMMENT '步骤编号',
                      tenant_id bigint NOT NULL DEFAULT 0 COMMENT '所属公司（租户）',
                      setp_name varchar(100) NOT NULL COMMENT '步骤名称',
                      setp_status bit(1) NOT NULL DEFAULT b'1' COMMENT '步骤状态',
                      sort_no int NOT NULL DEFAULT 0 COMMENT '排序号',
                      creator varchar(64) DEFAULT '' COMMENT '创建者',
                      create_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                      updater varchar(64) DEFAULT '' COMMENT '更新者',
                      update_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                      deleted bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
                      PRIMARY KEY (id),
                      KEY idx_tenant_sort (tenant_id, sort_no),
                      KEY idx_status (setp_status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自测题库分步骤表'
                    """
                )
                result["actions"].append({"create_table": "yj_practice_setp"})
            else:
                result["actions"].append({"skip_create_table": "yj_practice_setp"})

            if not column_exists(cursor, "yj_practice_exercises", "step_id"):
                cursor.execute(
                    """
                    ALTER TABLE yj_practice_exercises
                    ADD COLUMN step_id bigint NULL COMMENT '所属步骤，对应 yj_practice_setp.id' AFTER id
                    """
                )
                result["actions"].append({"add_column": "yj_practice_exercises.step_id"})
            else:
                result["actions"].append({"skip_add_column": "yj_practice_exercises.step_id"})

            if not column_exists(cursor, "yj_practice_exercises", "step_id"):
                raise RuntimeError("step_id column was not created")
            if not table_exists(cursor, "yj_practice_setp"):
                raise RuntimeError("yj_practice_setp table was not created")

            result["after"]["practice_exercises_columns"] = fetch_all(cursor, "SHOW COLUMNS FROM yj_practice_exercises")
            result["after"]["practice_setp_columns"] = fetch_all(cursor, "SHOW COLUMNS FROM yj_practice_setp")
            result["after"]["assessment_order_sample"] = fetch_all(
                cursor,
                """
                SELECT id, sort_no, question_stem
                FROM yj_practice_exercises
                WHERE category_id = 13 AND tenant_id = 1 AND deleted = b'0'
                ORDER BY sort_no ASC, id ASC
                LIMIT 5
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
        RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        conn.close()


if __name__ == "__main__":
    main()
