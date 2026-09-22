-- TASK-008 batch import from staging
-- Target database: yunjikeji
-- Preconditions:
--   1. 11 category seeds already exist.
--   2. Question rows are loaded into yk_question_import_staging.
--   3. Option rows are loaded into yk_question_import_option_staging.
--   4. Only parse_status = 'parsed' rows are allowed into formal question tables.

SELECT
    batch_no,
    parse_status,
    COUNT(*) AS question_count
FROM yk_question_import_staging
GROUP BY batch_no, parse_status
ORDER BY batch_no, parse_status;

SELECT
    s.batch_no,
    s.question_code,
    s.category_code,
    s.parse_status,
    s.review_reason
FROM yk_question_import_staging s
LEFT JOIN yk_question_category c
       ON c.category_code = s.category_code
WHERE s.parse_status = 'parsed'
  AND (
      c.id IS NULL
      OR s.question_code = ''
      OR s.stem IS NULL
      OR s.stem = ''
      OR s.correct_answer = ''
      OR s.question_type NOT IN ('single_choice', 'multiple_choice', 'judge')
  )
ORDER BY s.batch_no, s.question_code;

INSERT INTO yk_question (
    course_id,
    category_id,
    question_code,
    question_type,
    stem,
    correct_answer,
    analysis,
    score,
    sort_no,
    source_ref,
    options_json,
    answer_json,
    difficulty,
    status
)
SELECT
    NULL,
    c.id,
    s.question_code,
    s.question_type,
    s.stem,
    s.correct_answer,
    s.analysis,
    CASE WHEN s.score IS NULL OR s.score <= 0 THEN 1 ELSE s.score END,
    CASE WHEN s.sort_no IS NULL OR s.sort_no < 0 THEN 0 ELSE s.sort_no END,
    CASE
        WHEN s.source_ref IS NULL OR s.source_ref = '' THEN CONCAT(s.source_file, '#', s.source_locator)
        ELSE s.source_ref
    END,
    COALESCE(s.options_payload_json, JSON_ARRAY()),
    COALESCE(s.answer_payload_json, JSON_OBJECT('correctAnswer', s.correct_answer)),
    'normal',
    'online'
FROM yk_question_import_staging s
JOIN yk_question_category c
  ON c.category_code = s.category_code
WHERE s.parse_status = 'parsed'
  AND s.question_code <> ''
  AND s.stem IS NOT NULL
  AND s.stem <> ''
  AND s.correct_answer <> ''
  AND s.question_type IN ('single_choice', 'multiple_choice', 'judge')
ON DUPLICATE KEY UPDATE
    category_id = VALUES(category_id),
    question_type = VALUES(question_type),
    stem = VALUES(stem),
    correct_answer = VALUES(correct_answer),
    analysis = VALUES(analysis),
    score = VALUES(score),
    sort_no = VALUES(sort_no),
    source_ref = VALUES(source_ref),
    options_json = VALUES(options_json),
    answer_json = VALUES(answer_json),
    difficulty = VALUES(difficulty),
    status = VALUES(status),
    delete_status = 0;

INSERT INTO yk_question_option (
    question_id,
    option_code,
    option_label,
    option_content,
    is_correct,
    sort_no,
    status,
    delete_status
)
SELECT
    q.id,
    os.option_code,
    os.option_label,
    os.option_content,
    os.is_correct,
    os.sort_no,
    'active',
    0
FROM yk_question_import_option_staging os
JOIN yk_question_import_staging s
  ON s.batch_no = os.batch_no
 AND s.question_code = os.question_code
JOIN yk_question q
  ON q.question_code = os.question_code
WHERE s.parse_status = 'parsed'
  AND os.option_content <> ''
ON DUPLICATE KEY UPDATE
    option_label = VALUES(option_label),
    option_content = VALUES(option_content),
    is_correct = VALUES(is_correct),
    sort_no = VALUES(sort_no),
    status = VALUES(status),
    delete_status = VALUES(delete_status);

UPDATE yk_question_import_staging
SET imported_at = NOW()
WHERE parse_status = 'parsed';

UPDATE yk_question_import_option_staging os
JOIN yk_question_import_staging s
  ON s.batch_no = os.batch_no
 AND s.question_code = os.question_code
SET os.imported_at = NOW()
WHERE s.parse_status = 'parsed';

SELECT
    c.category_code,
    c.category_name,
    COUNT(q.id) AS imported_question_count
FROM yk_question_category c
LEFT JOIN yk_question q
       ON q.category_id = c.id
      AND q.delete_status = 0
GROUP BY c.id, c.category_code, c.category_name
ORDER BY c.sort_no;

SELECT
    category_code,
    parse_status,
    COUNT(*) AS row_count
FROM yk_question_import_staging
WHERE parse_status IN ('needs_manual_review', 'ignored_noise')
GROUP BY category_code, parse_status
ORDER BY category_code, parse_status;
