-- TASK-008 direct import into final question bank tables
-- Target database: yunjikeji test database only.
-- Persistent write scope: yk_question, yk_question_option.
-- Preconditions:
--   1. 20260513221000-dml-question-category-seed-v2.sql has been executed.
--   2. The two real CSV files remain in this TASK-008 asset directory.
--   3. Run with mysql --local-infile=1 and --default-character-set=utf8mb4.

SET NAMES utf8mb4;
SET SESSION sql_safe_updates = 0;

DROP TEMPORARY TABLE IF EXISTS tmp_task008_direct_question_import;
DROP TEMPORARY TABLE IF EXISTS tmp_task008_direct_option_import;
DROP TEMPORARY TABLE IF EXISTS tmp_task008_excluded_question;
DROP TEMPORARY TABLE IF EXISTS tmp_task008_duplicate_option_key;
DROP TEMPORARY TABLE IF EXISTS tmp_task008_importable_question;

CREATE TEMPORARY TABLE tmp_task008_direct_question_import (
    batch_no VARCHAR(64) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    source_locator VARCHAR(128) NOT NULL,
    category_code VARCHAR(64) NOT NULL,
    question_code VARCHAR(64) NOT NULL,
    question_type VARCHAR(32) NOT NULL,
    stem MEDIUMTEXT NOT NULL,
    correct_answer VARCHAR(128) NOT NULL,
    analysis MEDIUMTEXT NULL,
    score INT NULL,
    sort_no INT NULL,
    source_ref VARCHAR(255) NULL,
    parse_status VARCHAR(64) NOT NULL,
    review_reason VARCHAR(255) NULL,
    options_payload_json MEDIUMTEXT NULL,
    answer_payload_json MEDIUMTEXT NULL,
    raw_payload_json MEDIUMTEXT NULL,
    KEY idx_tmp_task008_direct_question_code (question_code),
    KEY idx_tmp_task008_direct_category_code (category_code),
    KEY idx_tmp_task008_direct_parse_status (parse_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TEMPORARY TABLE tmp_task008_direct_option_import (
    batch_no VARCHAR(64) NOT NULL,
    question_code VARCHAR(64) NOT NULL,
    option_code VARCHAR(16) NOT NULL,
    option_label VARCHAR(16) NOT NULL,
    option_content VARCHAR(512) NOT NULL,
    is_correct TINYINT(1) NOT NULL,
    sort_no INT NOT NULL,
    KEY idx_tmp_task008_direct_option_question (question_code),
    KEY idx_tmp_task008_direct_option_key (question_code, option_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

LOAD DATA LOCAL INFILE 'D:/ProjPort/Work/feixingxueyuan/doc/02-版本迭代/03-进行中版本/20260512221043-vapp-core-pages-development/050-执行脚本/TASK-008/20260513233500-question-import-staging-real.csv'
INTO TABLE tmp_task008_direct_question_import
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n' IGNORE 1 LINES
(batch_no,source_file,source_locator,category_code,question_code,question_type,stem,correct_answer,analysis,score,sort_no,source_ref,parse_status,review_reason,options_payload_json,answer_payload_json,raw_payload_json);

LOAD DATA LOCAL INFILE 'D:/ProjPort/Work/feixingxueyuan/doc/02-版本迭代/03-进行中版本/20260512221043-vapp-core-pages-development/050-执行脚本/TASK-008/20260513233600-question-import-option-staging-real.csv'
INTO TABLE tmp_task008_direct_option_import
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n' IGNORE 1 LINES
(batch_no,question_code,option_code,option_label,option_content,is_correct,sort_no);

CREATE TEMPORARY TABLE tmp_task008_duplicate_option_key AS
SELECT
    question_code,
    option_code,
    COUNT(*) AS duplicate_row_count
FROM tmp_task008_direct_option_import
GROUP BY question_code, option_code
HAVING COUNT(*) > 1;

CREATE TEMPORARY TABLE tmp_task008_excluded_question AS
SELECT
    q.question_code,
    q.category_code,
    q.parse_status,
    q.review_reason,
    'needs_manual_review_without_option' AS exclude_reason
FROM tmp_task008_direct_question_import q
LEFT JOIN tmp_task008_direct_option_import o
       ON o.question_code = q.question_code
WHERE q.parse_status = 'needs_manual_review'
GROUP BY q.question_code, q.category_code, q.parse_status, q.review_reason
HAVING COUNT(o.question_code) = 0;

CREATE TEMPORARY TABLE tmp_task008_importable_question AS
SELECT q.*
FROM tmp_task008_direct_question_import q
JOIN yk_question_category c
  ON c.category_code = q.category_code
 AND c.delete_status = 0
LEFT JOIN tmp_task008_excluded_question x
       ON x.question_code = q.question_code
WHERE x.question_code IS NULL
  AND q.question_code <> ''
  AND q.stem <> ''
  AND q.correct_answer <> ''
  AND q.question_type IN ('single_choice', 'multiple_choice', 'judge')
  AND JSON_VALID(q.options_payload_json)
  AND JSON_VALID(q.answer_payload_json);

SELECT 'loaded_question_csv_rows' AS metric, COUNT(*) AS metric_value
FROM tmp_task008_direct_question_import
UNION ALL
SELECT 'loaded_option_csv_rows', COUNT(*)
FROM tmp_task008_direct_option_import
UNION ALL
SELECT 'duplicate_question_codes', COUNT(*)
FROM (
    SELECT question_code
    FROM tmp_task008_direct_question_import
    GROUP BY question_code
    HAVING COUNT(*) > 1
) d
UNION ALL
SELECT 'duplicate_option_keys', COUNT(*)
FROM tmp_task008_duplicate_option_key
UNION ALL
SELECT 'excluded_questions_needs_manual_review_without_option', COUNT(*)
FROM tmp_task008_excluded_question
UNION ALL
SELECT 'importable_questions', COUNT(*)
FROM tmp_task008_importable_question
UNION ALL
SELECT 'importable_options_after_duplicate_key_exclusion', COUNT(*)
FROM tmp_task008_direct_option_import o
JOIN tmp_task008_importable_question q
  ON q.question_code = o.question_code
LEFT JOIN tmp_task008_duplicate_option_key d
       ON d.question_code = o.question_code
      AND d.option_code = o.option_code
WHERE d.question_code IS NULL;

SELECT
    'pre_cleanup_non_batch_active_question_count' AS metric,
    COUNT(*) AS metric_value
FROM yk_question q
WHERE q.delete_status = 0
  AND NOT EXISTS (
      SELECT 1
      FROM tmp_task008_direct_question_import src
      WHERE src.question_code = q.question_code
  );

SELECT
    d.question_code,
    d.option_code,
    d.duplicate_row_count
FROM tmp_task008_duplicate_option_key d
ORDER BY d.question_code, d.option_code;

SELECT
    x.question_code,
    x.category_code,
    x.parse_status,
    x.exclude_reason,
    x.review_reason
FROM tmp_task008_excluded_question x
ORDER BY x.question_code;

SELECT
    'missing_category_or_invalid_question_rows' AS check_name,
    q.question_code,
    q.category_code,
    q.question_type,
    q.parse_status,
    CASE
        WHEN c.id IS NULL THEN 'missing_category'
        WHEN q.question_code = '' THEN 'missing_question_code'
        WHEN q.stem = '' THEN 'missing_stem'
        WHEN q.correct_answer = '' THEN 'missing_correct_answer'
        WHEN q.question_type NOT IN ('single_choice', 'multiple_choice', 'judge') THEN 'invalid_question_type'
        WHEN NOT JSON_VALID(q.options_payload_json) THEN 'invalid_options_json'
        WHEN NOT JSON_VALID(q.answer_payload_json) THEN 'invalid_answer_json'
        ELSE 'unknown'
    END AS block_reason
FROM tmp_task008_direct_question_import q
LEFT JOIN yk_question_category c
       ON c.category_code = q.category_code
      AND c.delete_status = 0
LEFT JOIN tmp_task008_excluded_question x
       ON x.question_code = q.question_code
WHERE x.question_code IS NULL
  AND (
      c.id IS NULL
      OR q.question_code = ''
      OR q.stem = ''
      OR q.correct_answer = ''
      OR q.question_type NOT IN ('single_choice', 'multiple_choice', 'judge')
      OR NOT JSON_VALID(q.options_payload_json)
      OR NOT JSON_VALID(q.answer_payload_json)
  )
ORDER BY q.question_code;

START TRANSACTION;

DELETE qo
FROM yk_question_option qo
JOIN yk_question q
  ON q.id = qo.question_id
JOIN tmp_task008_direct_question_import src
  ON src.question_code = q.question_code;

DELETE qo
FROM yk_question_option qo
JOIN yk_question q
  ON q.id = qo.question_id
WHERE NOT EXISTS (
    SELECT 1
    FROM tmp_task008_direct_question_import src
    WHERE src.question_code = q.question_code
);

SELECT ROW_COUNT() AS non_batch_option_deleted_rows;

UPDATE yk_question q
JOIN tmp_task008_direct_question_import src
  ON src.question_code = q.question_code
SET q.delete_status = 1,
    q.status = 'offline'
WHERE NOT EXISTS (
    SELECT 1
    FROM tmp_task008_importable_question iq
    WHERE iq.question_code = q.question_code
);

UPDATE yk_question q
SET q.delete_status = 1,
    q.status = 'offline'
WHERE NOT EXISTS (
    SELECT 1
    FROM tmp_task008_direct_question_import src
    WHERE src.question_code = q.question_code
);

SELECT ROW_COUNT() AS non_batch_question_soft_deleted_rows;

INSERT INTO yk_question (
    course_id,
    category_id,
    question_code,
    question_type,
    stem,
    correct_answer,
    options_json,
    answer_json,
    analysis,
    score,
    sort_no,
    source_ref,
    difficulty,
    status,
    delete_status
)
SELECT
    NULL,
    c.id,
    q.question_code,
    q.question_type,
    q.stem,
    q.correct_answer,
    NULLIF(q.options_payload_json, ''),
    NULLIF(q.answer_payload_json, ''),
    NULLIF(q.analysis, ''),
    CASE WHEN q.score IS NULL OR q.score <= 0 THEN 1 ELSE q.score END,
    CASE WHEN q.sort_no IS NULL OR q.sort_no < 0 THEN 0 ELSE q.sort_no END,
    CASE
        WHEN q.source_ref IS NULL OR q.source_ref = '' THEN CONCAT(q.source_file, '#', q.source_locator)
        ELSE q.source_ref
    END,
    'normal',
    'online',
    0
FROM tmp_task008_importable_question q
JOIN yk_question_category c
  ON c.category_code = q.category_code
 AND c.delete_status = 0
ON DUPLICATE KEY UPDATE
    category_id = VALUES(category_id),
    question_type = VALUES(question_type),
    stem = VALUES(stem),
    correct_answer = VALUES(correct_answer),
    options_json = VALUES(options_json),
    answer_json = VALUES(answer_json),
    analysis = VALUES(analysis),
    score = VALUES(score),
    sort_no = VALUES(sort_no),
    source_ref = VALUES(source_ref),
    difficulty = VALUES(difficulty),
    status = VALUES(status),
    delete_status = VALUES(delete_status);

SELECT ROW_COUNT() AS question_upsert_affected_rows;

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
    o.option_code,
    o.option_label,
    o.option_content,
    o.is_correct,
    o.sort_no,
    'active',
    0
FROM tmp_task008_direct_option_import o
JOIN tmp_task008_importable_question iq
  ON iq.question_code = o.question_code
JOIN yk_question q
  ON q.question_code = o.question_code
 AND q.delete_status = 0
LEFT JOIN tmp_task008_duplicate_option_key d
       ON d.question_code = o.question_code
      AND d.option_code = o.option_code
WHERE d.question_code IS NULL
  AND o.option_content <> ''
ON DUPLICATE KEY UPDATE
    option_label = VALUES(option_label),
    option_content = VALUES(option_content),
    is_correct = VALUES(is_correct),
    sort_no = VALUES(sort_no),
    status = VALUES(status),
    delete_status = VALUES(delete_status);

SELECT ROW_COUNT() AS option_upsert_affected_rows;

SELECT
    'final_category_count' AS metric,
    COUNT(*) AS metric_value
FROM yk_question_category
WHERE delete_status = 0
UNION ALL
SELECT 'final_import_batch_question_count', COUNT(*)
FROM yk_question q
JOIN tmp_task008_direct_question_import src
  ON src.question_code = q.question_code
WHERE q.delete_status = 0
UNION ALL
SELECT 'final_total_question_count', COUNT(*)
FROM yk_question
WHERE delete_status = 0
UNION ALL
SELECT 'final_import_batch_option_count', COUNT(*)
FROM yk_question_option qo
JOIN yk_question q
  ON q.id = qo.question_id
JOIN tmp_task008_direct_question_import src
  ON src.question_code = q.question_code
WHERE qo.delete_status = 0
UNION ALL
SELECT 'final_total_option_count', COUNT(*)
FROM yk_question_option
WHERE delete_status = 0
UNION ALL
SELECT 'final_excluded_question_count', COUNT(*)
FROM tmp_task008_excluded_question
UNION ALL
SELECT 'final_duplicate_option_key_count', COUNT(*)
FROM tmp_task008_duplicate_option_key;

SELECT
    c.category_code,
    c.category_name,
    COUNT(q.id) AS final_question_count
FROM yk_question_category c
LEFT JOIN yk_question q
       ON q.category_id = c.id
      AND q.delete_status = 0
GROUP BY c.id, c.category_code, c.category_name, c.sort_no
ORDER BY c.sort_no, c.id;

COMMIT;
