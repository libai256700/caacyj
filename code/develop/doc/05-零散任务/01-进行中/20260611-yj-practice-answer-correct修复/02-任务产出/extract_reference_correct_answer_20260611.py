import argparse
import json
import os
from datetime import datetime

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


def choose_option_content(options_json, correct_answer):
    if not options_json:
        return None
    values = []
    for item in json.loads(options_json):
        code = (
            item.get("optionCode")
            or item.get("option_code")
            or item.get("id")
            or item.get("label")
            or ""
        ).strip()
        if code.upper() != correct_answer.upper():
            continue
        content = (
            item.get("optionContent")
            or item.get("option_content")
            or item.get("content")
            or item.get("text")
            or item.get("value")
            or ""
        ).strip()
        if content:
            values.append(content)
    if not values:
        return None
    return sorted(values, key=lambda value: (len(value), value))[0]


def fetch_candidates(cursor):
    cursor.execute(
        """
        SELECT
          e.id AS exercises_id,
          e.category_id,
          e.question_type,
          e.question_stem,
          e.tenant_id,
          q.id AS yk_question_id,
          q.question_code,
          q.correct_answer,
          q.options_json,
          COALESCE(MAX(a.sort_no), 0) AS max_sort_no,
          SUM(CASE WHEN a.is_correct = b'1' THEN 1 ELSE 0 END) AS yj_correct_count,
          SUM(CASE WHEN a.answer_code = q.correct_answer AND a.deleted = b'0' THEN 1 ELSE 0 END) AS yj_correct_code_count
        FROM yj_practice_exercises e
        JOIN yk_question q
          ON q.id = e.id
         AND q.category_id = e.category_id
         AND TRIM(q.stem) = TRIM(e.question_stem)
         AND q.status = 'online'
         AND q.delete_status = 0
         AND COALESCE(q.correct_answer, '') <> ''
        JOIN yj_practice_exercises_answer a
          ON a.exercises_id = e.id
         AND a.deleted = b'0'
        WHERE e.deleted = b'0'
          AND e.tenant_id = 1
        GROUP BY
          e.id,
          e.category_id,
          e.question_type,
          e.question_stem,
          e.tenant_id,
          q.id,
          q.question_code,
          q.correct_answer,
          q.options_json
        HAVING yj_correct_count = 0
        ORDER BY e.id
        """
    )
    candidates = []
    for row in cursor.fetchall():
        content = choose_option_content(row["options_json"], row["correct_answer"])
        if content:
            row["answer_content"] = content
            candidates.append(row)
    return candidates


def ensure_backup_table(cursor):
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} LIKE yj_practice_exercises_answer
        """
    )
    cursor.execute(f"SHOW COLUMNS FROM {BACKUP_TABLE} LIKE 'backup_reason'")
    if not cursor.fetchone():
        cursor.execute(
            f"""
            ALTER TABLE {BACKUP_TABLE}
              ADD COLUMN backup_reason varchar(128) NOT NULL DEFAULT '',
              ADD COLUMN backup_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
            """
        )


def backup_existing_rows(cursor, exercise_ids):
    if not exercise_ids:
        return
    placeholders = ",".join(["%s"] * len(exercise_ids))
    cursor.execute(
        f"""
        INSERT INTO {BACKUP_TABLE}
        SELECT src.*, %s AS backup_reason, NOW() AS backup_time
        FROM yj_practice_exercises_answer src
        WHERE src.exercises_id IN ({placeholders})
          AND NOT EXISTS (
            SELECT 1
            FROM {BACKUP_TABLE} bak
            WHERE bak.id = src.id
              AND bak.backup_reason = %s
          )
        """,
        [REASON] + exercise_ids + [REASON],
    )


def apply_candidates(cursor, candidates):
    for row in candidates:
        cursor.execute(
            """
            SELECT id
            FROM yj_practice_exercises_answer
            WHERE exercises_id = %s
              AND answer_code = %s
              AND deleted = b'0'
            ORDER BY id ASC
            LIMIT 1
            """,
            (row["exercises_id"], row["correct_answer"]),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE yj_practice_exercises_answer
                SET answer_content = %s,
                    is_correct = b'1',
                    tenant_id = %s,
                    updater = 'codex',
                    update_time = NOW()
                WHERE id = %s
                """,
                (row["answer_content"], row["tenant_id"], existing["id"]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO yj_practice_exercises_answer
                  (exercises_id, question_type, answer_code, answer_content, is_correct,
                   sort_no, tenant_id, creator, create_time, updater, update_time, deleted)
                VALUES
                  (%s, %s, %s, %s, b'1',
                   %s, %s, 'codex', NOW(), 'codex', NOW(), b'0')
                """,
                (
                    row["exercises_id"],
                    row["question_type"],
                    row["correct_answer"],
                    row["answer_content"],
                    int(row["max_sort_no"] or 0) + 10,
                    row["tenant_id"],
                ),
            )


def verify(cursor):
    cursor.execute(
        """
        SELECT
          e.id AS exercises_id,
          q.correct_answer,
          GROUP_CONCAT(CASE WHEN a.is_correct = b'1' THEN a.answer_code END ORDER BY a.answer_code SEPARATOR ',') AS yj_correct_codes,
          COUNT(a.id) AS option_count
        FROM yj_practice_exercises e
        JOIN yk_question q
          ON q.id = e.id
         AND q.category_id = e.category_id
         AND TRIM(q.stem) = TRIM(e.question_stem)
         AND q.status = 'online'
         AND q.delete_status = 0
         AND COALESCE(q.correct_answer, '') <> ''
        JOIN yj_practice_exercises_answer a
          ON a.exercises_id = e.id
         AND a.deleted = b'0'
        WHERE e.deleted = b'0'
          AND e.tenant_id = 1
        GROUP BY e.id, q.correct_answer
        HAVING COALESCE(yj_correct_codes, '') <> q.correct_answer
        ORDER BY e.id
        """
    )
    return cursor.fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Execute DML. Without this flag the script only previews.")
    args = parser.parse_args()

    with connect() as conn:
        try:
            with conn.cursor() as cursor:
                candidates = fetch_candidates(cursor)
                print(
                    json.dumps(
                        {
                            "mode": "apply" if args.apply else "dry-run",
                            "backup_table": BACKUP_TABLE,
                            "candidate_count": len(candidates),
                            "candidates": [
                                {
                                    "exercises_id": row["exercises_id"],
                                    "question_code": row["question_code"],
                                    "correct_answer": row["correct_answer"],
                                    "answer_content": row["answer_content"],
                                }
                                for row in candidates
                            ],
                            "checked_at": datetime.now().isoformat(timespec="seconds"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                if not args.apply:
                    conn.rollback()
                    return

                ensure_backup_table(cursor)
                backup_existing_rows(cursor, [row["exercises_id"] for row in candidates])
                apply_candidates(cursor, candidates)
                mismatches = verify(cursor)
                if mismatches:
                    conn.rollback()
                    raise RuntimeError("Verification failed: " + json.dumps(mismatches, ensure_ascii=False, default=str))
                conn.commit()
                print(json.dumps({"status": "committed", "mismatch_count": 0}, ensure_ascii=False))
        except Exception:
            conn.rollback()
            raise


if __name__ == "__main__":
    main()
