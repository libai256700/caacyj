import argparse
import os

import pymysql


BACKUP_TABLE = "yj_practice_exercises_answer_bak_20260611_correct_extract"
REASON = "20260611_extract_reference_correct_answer"


def connect():
    return pymysql.connect(
        host=os.getenv("YUNJI_DB_HOST", "114.111.30.111"),
        port=int(os.getenv("YUNJI_DB_PORT", "13306")),
        user=os.getenv("YUNJI_DB_USER", "yunji_test"),
        password=os.getenv("YUNJI_DB_PASSWORD", "yunji8978_"),
        database=os.getenv("YUNJI_DB_NAME", "yunjikeji"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def ensure_backup_exists(cursor):
    cursor.execute("SHOW TABLES LIKE %s", (BACKUP_TABLE,))
    if not cursor.fetchone():
        raise RuntimeError(f"Backup table not found: {BACKUP_TABLE}")


def preview(cursor):
    cursor.execute(
        f"""
        SELECT exercises_id, COUNT(*) AS backup_rows
        FROM {BACKUP_TABLE}
        WHERE backup_reason = %s
        GROUP BY exercises_id
        ORDER BY exercises_id
        """,
        (REASON,),
    )
    return cursor.fetchall()


def rollback(cursor):
    cursor.execute(
        f"""
        DELETE target
        FROM yj_practice_exercises_answer target
        JOIN (
          SELECT DISTINCT exercises_id
          FROM {BACKUP_TABLE}
          WHERE backup_reason = %s
        ) scope ON scope.exercises_id = target.exercises_id
        WHERE NOT EXISTS (
          SELECT 1
          FROM {BACKUP_TABLE} bak
          WHERE bak.backup_reason = %s
            AND bak.id = target.id
        )
        """,
        (REASON, REASON),
    )
    deleted_inserted_rows = cursor.rowcount

    cursor.execute(
        f"""
        UPDATE yj_practice_exercises_answer target
        JOIN {BACKUP_TABLE} bak
          ON bak.id = target.id
         AND bak.backup_reason = %s
        SET
          target.exercises_id = bak.exercises_id,
          target.question_type = bak.question_type,
          target.answer_code = bak.answer_code,
          target.answer_content = bak.answer_content,
          target.is_correct = bak.is_correct,
          target.sort_no = bak.sort_no,
          target.tenant_id = bak.tenant_id,
          target.creator = bak.creator,
          target.create_time = bak.create_time,
          target.updater = bak.updater,
          target.update_time = bak.update_time,
          target.deleted = bak.deleted
        """,
        (REASON,),
    )
    restored_rows = cursor.rowcount
    return deleted_inserted_rows, restored_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Execute rollback. Without this flag the script only previews.")
    args = parser.parse_args()

    with connect() as conn:
        try:
            with conn.cursor() as cursor:
                ensure_backup_exists(cursor)
                rows = preview(cursor)
                print({"mode": "apply" if args.apply else "dry-run", "backup_rows": rows})
                if not args.apply:
                    conn.rollback()
                    return
                deleted_inserted_rows, restored_rows = rollback(cursor)
                conn.commit()
                print({"status": "committed", "deleted_inserted_rows": deleted_inserted_rows, "restored_rows": restored_rows})
        except Exception:
            conn.rollback()
            raise


if __name__ == "__main__":
    main()
