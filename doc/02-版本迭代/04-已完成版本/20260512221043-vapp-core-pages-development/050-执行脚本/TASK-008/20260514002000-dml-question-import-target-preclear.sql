-- TASK-008 formal preclear before importing the current staged question-bank payload
-- Purpose:
--   1. Delete existing yk_question_option rows for the current staged parsed question set.
--   2. Delete existing yk_question rows for the current staged parsed question set.
-- Preconditions:
--   1. Current-round CSV rows have already been loaded into yk_question_import_staging
--      and yk_question_import_option_staging.
--   2. The staged payload has already been sampled or reviewed.
-- Boundary:
--   1. This script does not clear yk_question_category.
--   2. This script does not clear yk_practice_record, yk_practice_session,
--      or yk_wrong_question_book.
--   3. If linked practice or wrong-book data exists, this script intentionally
--      skips formal deletion to avoid partial data loss.

DROP TEMPORARY TABLE IF EXISTS tmp_task008_target_question;

CREATE TEMPORARY TABLE tmp_task008_target_question (
    question_code VARCHAR(64) NOT NULL,
    category_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (question_code)
) ENGINE=InnoDB
AS
SELECT DISTINCT
    s.question_code,
    s.category_code
FROM yk_question_import_staging s
WHERE s.parse_status = 'parsed'
  AND s.question_code IS NOT NULL
  AND s.question_code <> '';

SET @target_question_count := (
    SELECT COUNT(*)
    FROM tmp_task008_target_question
);

SET @matched_formal_question_count := (
    SELECT COUNT(*)
    FROM yk_question q
    JOIN tmp_task008_target_question t
      ON t.question_code = q.question_code
);

SET @blocked_practice_record_count := (
    SELECT COUNT(*)
    FROM yk_practice_record pr
    JOIN yk_question q
      ON q.id = pr.question_id
    JOIN tmp_task008_target_question t
      ON t.question_code = q.question_code
    WHERE pr.delete_status = 0
);

SET @blocked_wrong_book_count := (
    SELECT COUNT(*)
    FROM yk_wrong_question_book wb
    JOIN yk_question q
      ON q.id = wb.question_id
    JOIN tmp_task008_target_question t
      ON t.question_code = q.question_code
    WHERE wb.delete_status = 0
);

SELECT
    @target_question_count AS target_question_count,
    @matched_formal_question_count AS matched_formal_question_count,
    @blocked_practice_record_count AS blocked_practice_record_count,
    @blocked_wrong_book_count AS blocked_wrong_book_count;

SELECT
    q.id,
    q.question_code,
    q.category_id,
    q.status,
    q.delete_status
FROM yk_question q
JOIN tmp_task008_target_question t
  ON t.question_code = q.question_code
ORDER BY q.id;

SELECT
    pr.id,
    pr.user_id,
    pr.session_id,
    q.question_code,
    pr.status,
    pr.delete_status
FROM yk_practice_record pr
JOIN yk_question q
  ON q.id = pr.question_id
JOIN tmp_task008_target_question t
  ON t.question_code = q.question_code
WHERE pr.delete_status = 0
ORDER BY pr.id
LIMIT 50;

SELECT
    wb.id,
    wb.user_id,
    q.question_code,
    wb.status,
    wb.delete_status
FROM yk_wrong_question_book wb
JOIN yk_question q
  ON q.id = wb.question_id
JOIN tmp_task008_target_question t
  ON t.question_code = q.question_code
WHERE wb.delete_status = 0
ORDER BY wb.id
LIMIT 50;

DELETE qo
FROM yk_question_option qo
JOIN yk_question q
  ON q.id = qo.question_id
JOIN tmp_task008_target_question t
  ON t.question_code = q.question_code
WHERE @target_question_count > 0
  AND @blocked_practice_record_count = 0
  AND @blocked_wrong_book_count = 0;

DELETE q
FROM yk_question q
JOIN tmp_task008_target_question t
  ON t.question_code = q.question_code
WHERE @target_question_count > 0
  AND @blocked_practice_record_count = 0
  AND @blocked_wrong_book_count = 0;

SELECT
    'after_preclear' AS checkpoint,
    @target_question_count AS target_question_count,
    @blocked_practice_record_count AS blocked_practice_record_count,
    @blocked_wrong_book_count AS blocked_wrong_book_count,
    (
        SELECT COUNT(*)
        FROM yk_question q
        JOIN tmp_task008_target_question t
          ON t.question_code = q.question_code
    ) AS remaining_formal_question_count,
    (
        SELECT COUNT(*)
        FROM yk_question_option qo
        JOIN yk_question q
          ON q.id = qo.question_id
        JOIN tmp_task008_target_question t
          ON t.question_code = q.question_code
    ) AS remaining_formal_option_count;

DROP TEMPORARY TABLE IF EXISTS tmp_task008_target_question;
