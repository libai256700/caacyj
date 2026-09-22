SET NAMES utf8mb4;
DROP TEMPORARY TABLE IF EXISTS tmp_task008_post_question;
DROP TEMPORARY TABLE IF EXISTS tmp_task008_post_option;
DROP TEMPORARY TABLE IF EXISTS tmp_task008_post_excluded_question;
DROP TEMPORARY TABLE IF EXISTS tmp_task008_post_duplicate_option_key;

CREATE TEMPORARY TABLE tmp_task008_post_question (
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
    KEY idx_tmp_task008_post_question_code (question_code),
    KEY idx_tmp_task008_post_category_code (category_code),
    KEY idx_tmp_task008_post_parse_status (parse_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TEMPORARY TABLE tmp_task008_post_option (
    batch_no VARCHAR(64) NOT NULL,
    question_code VARCHAR(64) NOT NULL,
    option_code VARCHAR(16) NOT NULL,
    option_label VARCHAR(16) NOT NULL,
    option_content VARCHAR(512) NOT NULL,
    is_correct TINYINT(1) NOT NULL,
    sort_no INT NOT NULL,
    KEY idx_tmp_task008_post_option_question (question_code),
    KEY idx_tmp_task008_post_option_key (question_code, option_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

LOAD DATA LOCAL INFILE 'D:/ProjPort/Work/feixingxueyuan/tmp/task008-direct-import-run/question-import-staging-real.tsv'
INTO TABLE tmp_task008_post_question
CHARACTER SET utf8mb4
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n' IGNORE 1 LINES
(batch_no,source_file,source_locator,category_code,question_code,question_type,stem,correct_answer,analysis,score,sort_no,source_ref,parse_status,review_reason,options_payload_json,answer_payload_json,raw_payload_json);

LOAD DATA LOCAL INFILE 'D:/ProjPort/Work/feixingxueyuan/tmp/task008-direct-import-run/question-import-option-staging-real.tsv'
INTO TABLE tmp_task008_post_option
CHARACTER SET utf8mb4
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n' IGNORE 1 LINES
(batch_no,question_code,option_code,option_label,option_content,is_correct,sort_no);

CREATE TEMPORARY TABLE tmp_task008_post_duplicate_option_key AS
SELECT question_code, option_code, COUNT(*) duplicate_row_count
FROM tmp_task008_post_option
GROUP BY question_code, option_code
HAVING COUNT(*) > 1;

CREATE TEMPORARY TABLE tmp_task008_post_excluded_question AS
SELECT q.question_code, q.category_code, q.parse_status, q.review_reason
FROM tmp_task008_post_question q
LEFT JOIN tmp_task008_post_option o ON o.question_code = q.question_code
WHERE q.parse_status = 'needs_manual_review'
GROUP BY q.question_code, q.category_code, q.parse_status, q.review_reason
HAVING COUNT(o.question_code) = 0;

SELECT 'final_category_count' metric, COUNT(*) metric_value FROM yk_question_category WHERE delete_status = 0;
SELECT 'final_active_question_count' metric, COUNT(*) metric_value FROM yk_question WHERE delete_status = 0;
SELECT 'final_active_option_count' metric, COUNT(*) metric_value FROM yk_question_option WHERE delete_status = 0;
SELECT 'source_question_rows' metric, COUNT(*) metric_value FROM tmp_task008_post_question;
SELECT 'source_option_rows' metric, COUNT(*) metric_value FROM tmp_task008_post_option;
SELECT 'excluded_needs_manual_without_option' metric, COUNT(*) metric_value FROM tmp_task008_post_excluded_question;
SELECT 'duplicate_option_key_groups' metric, COUNT(*) metric_value FROM tmp_task008_post_duplicate_option_key;
SELECT 'active_excluded_question_rows' metric, COUNT(*) metric_value FROM yk_question q JOIN tmp_task008_post_excluded_question x ON x.question_code = q.question_code WHERE q.delete_status = 0;
SELECT 'active_duplicate_option_rows' metric, COUNT(*) metric_value FROM yk_question_option qo JOIN yk_question q ON q.id = qo.question_id JOIN tmp_task008_post_duplicate_option_key d ON d.question_code = q.question_code AND d.option_code = qo.option_code WHERE q.delete_status = 0 AND qo.delete_status = 0;
SELECT 'missing_category_mapping_rows' metric, COUNT(*) metric_value FROM yk_question q LEFT JOIN yk_question_category c ON c.id = q.category_id AND c.delete_status = 0 WHERE q.delete_status = 0 AND c.id IS NULL;
SELECT 'missing_option_question_mapping_rows' metric, COUNT(*) metric_value FROM yk_question_option qo LEFT JOIN yk_question q ON q.id = qo.question_id AND q.delete_status = 0 WHERE qo.delete_status = 0 AND q.id IS NULL;
SELECT 'questions_without_options_active' metric, COUNT(*) metric_value FROM yk_question q LEFT JOIN yk_question_option qo ON qo.question_id = q.id AND qo.delete_status = 0 WHERE q.delete_status = 0 GROUP BY q.id HAVING COUNT(qo.id) = 0 LIMIT 20;
SELECT c.category_code, c.category_name, COUNT(q.id) final_question_count FROM yk_question_category c LEFT JOIN yk_question q ON q.category_id = c.id AND q.delete_status = 0 GROUP BY c.id, c.category_code, c.category_name, c.sort_no ORDER BY c.sort_no, c.id;
SELECT d.question_code, d.option_code, d.duplicate_row_count FROM tmp_task008_post_duplicate_option_key d ORDER BY d.question_code, d.option_code;
SELECT x.question_code, x.category_code, x.parse_status, x.review_reason FROM tmp_task008_post_excluded_question x ORDER BY x.question_code LIMIT 400;
