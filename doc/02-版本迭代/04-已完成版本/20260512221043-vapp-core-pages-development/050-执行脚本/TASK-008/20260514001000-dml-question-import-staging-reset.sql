-- TASK-008 staging reset before loading the current question-bank payload
-- Purpose:
--   1. Clear previous-round rows from yk_question_import_staging.
--   2. Clear previous-round rows from yk_question_import_option_staging.
-- Execution point:
--   Run this script before loading the current-round CSV files.
-- Boundary:
--   This script clears staging tables only.
--   It does not touch formal question tables, practice records, sessions, or wrong-question data.

SELECT
    'before_reset' AS checkpoint,
    (SELECT COUNT(*) FROM yk_question_import_staging) AS question_staging_rows,
    (SELECT COUNT(*) FROM yk_question_import_option_staging) AS option_staging_rows;

DELETE FROM yk_question_import_option_staging;
DELETE FROM yk_question_import_staging;

SELECT
    'after_reset' AS checkpoint,
    (SELECT COUNT(*) FROM yk_question_import_staging) AS question_staging_rows,
    (SELECT COUNT(*) FROM yk_question_import_option_staging) AS option_staging_rows;
