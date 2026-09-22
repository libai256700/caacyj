-- TASK-008 practice page question bank schema
-- Incremental DDL for category, question option, practice session,
-- wrong-question book, yk_question extension,
-- and yk_practice_record answer plus snapshot support.
-- Target database: yunjikeji

CREATE TABLE IF NOT EXISTS yk_question_category (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    category_code VARCHAR(64) NOT NULL COMMENT 'Category code',
    category_name VARCHAR(128) NOT NULL COMMENT 'Category name',
    sort_no INT NOT NULL DEFAULT 0 COMMENT 'Display order',
    status VARCHAR(32) NOT NULL DEFAULT 'online' COMMENT 'Category status: draft, online, offline',
    delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted',
    description VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Category description',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_yk_question_category_code (category_code),
    KEY idx_yk_question_category_status_sort (status, sort_no, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP question bank category';

CREATE TABLE IF NOT EXISTS yk_question_option (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    question_id BIGINT UNSIGNED NOT NULL COMMENT 'Question ID',
    option_code VARCHAR(16) NOT NULL COMMENT 'Option code',
    option_label VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'Option display label',
    option_content VARCHAR(512) NOT NULL COMMENT 'Option content',
    is_correct TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether this option is correct',
    sort_no INT NOT NULL DEFAULT 0 COMMENT 'Display order',
    status VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT 'Option status: active, invalid',
    delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_yk_question_option_question_code (question_id, option_code),
    KEY idx_yk_question_option_question_sort (question_id, sort_no, id),
    CONSTRAINT fk_yk_question_option_question
        FOREIGN KEY (question_id) REFERENCES yk_question(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP question option';

-- Historical staging tables are no longer part of the final formal schema.
-- The final formal structure in this round keeps only business tables.

CREATE TABLE IF NOT EXISTS yk_practice_session (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    session_id VARCHAR(64) NOT NULL COMMENT 'Practice session ID',
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    practice_code VARCHAR(64) NOT NULL DEFAULT 'practice-default' COMMENT 'Practice instance code',
    category_id BIGINT UNSIGNED NOT NULL COMMENT 'Question category ID',
    mode ENUM('standard', 'wrongReview') NOT NULL DEFAULT 'standard' COMMENT 'Practice mode: standard, wrongReview',
    question_count INT NOT NULL DEFAULT 0 COMMENT 'Total question count',
    answered_count INT NOT NULL DEFAULT 0 COMMENT 'Answered question count',
    correct_count INT NOT NULL DEFAULT 0 COMMENT 'Correct answer count',
    wrong_count INT NOT NULL DEFAULT 0 COMMENT 'Wrong answer count',
    status ENUM('in_progress', 'completed', 'abandoned') NOT NULL DEFAULT 'in_progress' COMMENT 'Session status: in_progress, completed, abandoned',
    delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted',
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Started time',
    completed_at DATETIME NULL COMMENT 'Completed time',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_yk_practice_session_session_id (session_id),
    UNIQUE KEY uk_yk_practice_session_session_user (session_id, user_id),
    KEY idx_yk_practice_session_user_status (user_id, status, updated_at),
    KEY idx_yk_practice_session_category_status (category_id, status, updated_at),
    CONSTRAINT fk_yk_practice_session_user
        FOREIGN KEY (user_id) REFERENCES yk_user_account(id),
    CONSTRAINT fk_yk_practice_session_category
        FOREIGN KEY (category_id) REFERENCES yk_question_category(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP practice session';

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question_category'
              AND COLUMN_NAME = 'status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question_category ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT ''online'' COMMENT ''Category status: draft, online, offline'''
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question_category'
              AND COLUMN_NAME = 'delete_status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question_category ADD COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''Soft delete status: 0-normal, 1-deleted'''
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question_category'
              AND COLUMN_NAME = 'description'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question_category ADD COLUMN description VARCHAR(255) NOT NULL DEFAULT '''' COMMENT ''Category description'''
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

INSERT INTO yk_question_category (
    category_code,
    category_name,
    sort_no,
    status,
    delete_status,
    description
)
SELECT 'overview', '概述', 10, 'online', 0, 'TASK-008 bootstrap category'
WHERE NOT EXISTS (
    SELECT 1 FROM yk_question_category WHERE category_code = 'overview'
);

SET @bootstrap_category_id = (
    SELECT id
    FROM yk_question_category
    WHERE category_code = 'overview'
    ORDER BY id
    LIMIT 1
);

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND COLUMN_NAME = 'category_id'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD COLUMN category_id BIGINT UNSIGNED NULL COMMENT ''Question category ID'' AFTER course_id'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND COLUMN_NAME = 'question_code'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD COLUMN question_code VARCHAR(64) NULL COMMENT ''Question code'' AFTER category_id'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND COLUMN_NAME = 'correct_answer'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD COLUMN correct_answer VARCHAR(128) NULL COMMENT ''Canonical correct answer'' AFTER stem'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND COLUMN_NAME = 'score'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD COLUMN score INT NOT NULL DEFAULT 1 COMMENT ''Question score'' AFTER analysis'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND COLUMN_NAME = 'sort_no'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD COLUMN sort_no INT NOT NULL DEFAULT 0 COMMENT ''Question sort order'' AFTER score'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND COLUMN_NAME = 'source_ref'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD COLUMN source_ref VARCHAR(255) NOT NULL DEFAULT '''' COMMENT ''Source reference'' AFTER sort_no'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND COLUMN_NAME = 'delete_status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''Soft delete status: 0-normal, 1-deleted'' AFTER status'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question_option'
              AND COLUMN_NAME = 'status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question_option ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT ''active'' COMMENT ''Option status: active, invalid'' AFTER sort_no'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question_option'
              AND COLUMN_NAME = 'delete_status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question_option ADD COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''Soft delete status: 0-normal, 1-deleted'' AFTER status'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_session'
              AND COLUMN_NAME = 'delete_status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_session ADD COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''Soft delete status: 0-normal, 1-deleted'' AFTER status'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'session_id'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN session_id VARCHAR(64) NULL COMMENT ''Practice session ID'' AFTER course_id'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'selected_answer'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN selected_answer VARCHAR(128) NOT NULL DEFAULT '''' COMMENT ''Canonical selected answer'' AFTER question_id'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'question_code_snapshot'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN question_code_snapshot VARCHAR(64) NOT NULL DEFAULT '''' COMMENT ''Question code snapshot'' AFTER answer_json'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'question_type_snapshot'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN question_type_snapshot VARCHAR(32) NOT NULL DEFAULT '''' COMMENT ''Question type snapshot'' AFTER question_code_snapshot'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'question_stem_snapshot'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN question_stem_snapshot TEXT NULL COMMENT ''Question stem snapshot'' AFTER question_type_snapshot'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'standard_answer_snapshot'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN standard_answer_snapshot VARCHAR(128) NOT NULL DEFAULT '''' COMMENT ''Standard answer snapshot'' AFTER question_stem_snapshot'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'question_analysis_snapshot'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN question_analysis_snapshot TEXT NULL COMMENT ''Question analysis snapshot'' AFTER standard_answer_snapshot'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'category_id_snapshot'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN category_id_snapshot BIGINT UNSIGNED NULL COMMENT ''Category ID snapshot'' AFTER question_analysis_snapshot'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'category_code_snapshot'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN category_code_snapshot VARCHAR(64) NOT NULL DEFAULT '''' COMMENT ''Category code snapshot'' AFTER category_id_snapshot'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'category_name_snapshot'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN category_name_snapshot VARCHAR(128) NOT NULL DEFAULT '''' COMMENT ''Category name snapshot'' AFTER category_code_snapshot'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'options_snapshot_json'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN options_snapshot_json JSON NULL COMMENT ''Question options snapshot'' AFTER category_name_snapshot'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT ''active'' COMMENT ''Record status: active, invalid'' AFTER correct_flag'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND COLUMN_NAME = 'delete_status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''Soft delete status: 0-normal, 1-deleted'' AFTER status'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE yk_question
SET category_id = CASE
        WHEN category_id IS NULL OR category_id = 0 THEN @bootstrap_category_id
        ELSE category_id
    END,
    question_code = CASE
        WHEN question_code IS NULL OR question_code = '' THEN CONCAT('LEGACY-Q-', LPAD(id, 10, '0'))
        ELSE question_code
    END,
    correct_answer = CASE
        WHEN correct_answer IS NOT NULL AND correct_answer <> '' THEN correct_answer
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.correctAnswer')), '') <> ''
            THEN JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.correctAnswer'))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$')) = 'ARRAY'
            THEN REPLACE(REPLACE(REPLACE(REPLACE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$')), '[', ''), ']', ''), '\"', ''), ' ', '')
        ELSE 'PENDING'
    END,
    score = CASE
        WHEN score IS NULL OR score <= 0 THEN 1
        ELSE score
    END,
    sort_no = CASE
        WHEN sort_no IS NULL OR sort_no < 0 THEN 0
        ELSE sort_no
    END,
    source_ref = COALESCE(source_ref, ''),
    delete_status = CASE
        WHEN delete_status IS NULL THEN 0
        ELSE delete_status
    END
WHERE category_id IS NULL
   OR category_id = 0
   OR question_code IS NULL
   OR question_code = ''
   OR correct_answer IS NULL
   OR correct_answer = ''
   OR score IS NULL
   OR score <= 0
   OR sort_no IS NULL
   OR sort_no < 0
   OR source_ref IS NULL
   OR delete_status IS NULL;

SELECT id, question_type, correct_answer, source_ref
FROM yk_question
WHERE question_type IS NULL
   OR TRIM(question_type) = ''
   OR question_type NOT IN ('single_choice', 'multiple_choice', 'judge')
ORDER BY id
LIMIT 100;

UPDATE yk_question
SET question_type = CASE
        WHEN LOWER(REPLACE(REPLACE(TRIM(COALESCE(question_type, '')), '-', '_'), ' ', '')) IN (
            'single_choice', 'singlechoice', 'single', 'single_select', 'radio', 'danxuan', '单选', '单选题'
        ) THEN 'single_choice'
        WHEN LOWER(REPLACE(REPLACE(TRIM(COALESCE(question_type, '')), '-', '_'), ' ', '')) IN (
            'multiple_choice', 'multiplechoice', 'multiple', 'multiple_select', 'multi', 'duoxuan', '多选', '多选题'
        ) THEN 'multiple_choice'
        WHEN LOWER(REPLACE(REPLACE(TRIM(COALESCE(question_type, '')), '-', '_'), ' ', '')) IN (
            'judge', 'judgement', 'judgment', 'true_false', 'truefalse', 'panduan', '判断', '判断题'
        ) THEN 'judge'
        WHEN COALESCE(correct_answer, '') REGEXP '[,，]' THEN 'multiple_choice'
        WHEN UPPER(TRIM(COALESCE(correct_answer, ''))) IN ('T', 'F', 'TRUE', 'FALSE', 'Y', 'N')
             OR TRIM(COALESCE(correct_answer, '')) IN ('正确', '错误') THEN 'judge'
        ELSE 'single_choice'
    END,
    source_ref = CASE
        WHEN question_type IN ('single_choice', 'multiple_choice', 'judge') THEN COALESCE(source_ref, '')
        WHEN LOWER(REPLACE(REPLACE(TRIM(COALESCE(question_type, '')), '-', '_'), ' ', '')) IN (
            'single_choice', 'singlechoice', 'single', 'single_select', 'radio', 'danxuan', '单选', '单选题',
            'multiple_choice', 'multiplechoice', 'multiple', 'multiple_select', 'multi', 'duoxuan', '多选', '多选题',
            'judge', 'judgement', 'judgment', 'true_false', 'truefalse', 'panduan', '判断', '判断题'
        ) THEN COALESCE(source_ref, '')
        WHEN COALESCE(source_ref, '') LIKE '[LEGACY-TYPE-INFERRED]%' THEN COALESCE(source_ref, '')
        ELSE CONCAT(
            '[LEGACY-TYPE-INFERRED]',
            LEFT(COALESCE(source_ref, ''), 255 - CHAR_LENGTH('[LEGACY-TYPE-INFERRED]'))
        )
    END
WHERE question_type IS NULL
   OR TRIM(question_type) = ''
   OR question_type NOT IN ('single_choice', 'multiple_choice', 'judge');

SELECT question_type, COUNT(*) AS question_count
FROM yk_question
GROUP BY question_type
ORDER BY question_type;

SELECT id, question_type, correct_answer, source_ref
FROM yk_question
WHERE source_ref LIKE '[LEGACY-TYPE-INFERRED]%'
ORDER BY id
LIMIT 100;

UPDATE yk_practice_record
SET session_id = CASE
        WHEN session_id IS NULL OR session_id = '' THEN CONCAT('LEGACY-S-', LPAD(id, 10, '0'))
        ELSE session_id
    END,
    selected_answer = CASE
        WHEN selected_answer IS NOT NULL
             AND TRIM(selected_answer) <> ''
             AND selected_answer <> 'PENDING_MANUAL_CONFIRM'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(selected_answer), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '\"', ''))
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selectedAnswer')), '') <> ''
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selectedAnswer'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '\"', ''))
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selected_answer')), '') <> ''
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selected_answer'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '\"', ''))
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.answer')), '') <> ''
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.answer'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '\"', ''))
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.submitAnswer')), '') <> ''
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.submitAnswer'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '\"', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.selectedOptionCodes')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selectedOptionCodes'))), '[', ''), ']', ''), '\"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.selected_option_codes')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selected_option_codes'))), '[', ''), ']', ''), '\"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.optionCodes')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.optionCodes'))), '[', ''), ']', ''), '\"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.option_codes')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.option_codes'))), '[', ''), ']', ''), '\"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.answers')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.answers'))), '[', ''), ']', ''), '\"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.answerList')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.answerList'))), '[', ''), ']', ''), '\"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.options')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.options'))), '[', ''), ']', ''), '\"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$'))), '[', ''), ']', ''), '\"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$')) = 'STRING'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '\"', ''))
        ELSE 'PENDING_MANUAL_CONFIRM'
    END,
    status = CASE
        WHEN status IS NULL OR status = '' THEN 'active'
        ELSE status
    END,
    delete_status = CASE
        WHEN delete_status IS NULL THEN 0
        ELSE delete_status
    END
WHERE session_id IS NULL
   OR session_id = ''
   OR selected_answer IS NULL
   OR TRIM(selected_answer) = ''
   OR selected_answer = 'PENDING_MANUAL_CONFIRM'
   OR status IS NULL
   OR status = ''
   OR delete_status IS NULL;

SELECT id, session_id, question_id, selected_answer, answer_json
FROM yk_practice_record
WHERE selected_answer = 'PENDING_MANUAL_CONFIRM'
ORDER BY id
LIMIT 100;

SELECT id, session_id, question_id, selected_answer
FROM yk_practice_record
WHERE selected_answer REGEXP '(^,|,,|,$)'
ORDER BY id
LIMIT 100;

UPDATE yk_practice_record pr
LEFT JOIN yk_question q
       ON q.id = pr.question_id
LEFT JOIN yk_question_category qc
       ON qc.id = q.category_id
SET pr.question_code_snapshot = CASE
        WHEN pr.question_code_snapshot IS NULL OR pr.question_code_snapshot = ''
            THEN COALESCE(q.question_code, CONCAT('LEGACY-Q-', LPAD(pr.question_id, 10, '0')))
        ELSE pr.question_code_snapshot
    END,
    pr.question_type_snapshot = CASE
        WHEN pr.question_type_snapshot IS NULL OR pr.question_type_snapshot = ''
            THEN COALESCE(q.question_type, '')
        ELSE pr.question_type_snapshot
    END,
    pr.question_stem_snapshot = CASE
        WHEN pr.question_stem_snapshot IS NULL OR pr.question_stem_snapshot = ''
            THEN q.stem
        ELSE pr.question_stem_snapshot
    END,
    pr.standard_answer_snapshot = CASE
        WHEN pr.standard_answer_snapshot IS NULL OR pr.standard_answer_snapshot = ''
            THEN COALESCE(q.correct_answer, '')
        ELSE pr.standard_answer_snapshot
    END,
    pr.question_analysis_snapshot = CASE
        WHEN pr.question_analysis_snapshot IS NULL OR pr.question_analysis_snapshot = ''
            THEN q.analysis
        ELSE pr.question_analysis_snapshot
    END,
    pr.category_id_snapshot = CASE
        WHEN pr.category_id_snapshot IS NULL THEN q.category_id
        ELSE pr.category_id_snapshot
    END,
    pr.category_code_snapshot = CASE
        WHEN pr.category_code_snapshot IS NULL OR pr.category_code_snapshot = ''
            THEN COALESCE(qc.category_code, '')
        ELSE pr.category_code_snapshot
    END,
    pr.category_name_snapshot = CASE
        WHEN pr.category_name_snapshot IS NULL OR pr.category_name_snapshot = ''
            THEN COALESCE(qc.category_name, '')
        ELSE pr.category_name_snapshot
    END,
    pr.options_snapshot_json = CASE
        WHEN pr.options_snapshot_json IS NULL THEN q.options_json
        ELSE pr.options_snapshot_json
    END
WHERE pr.question_code_snapshot IS NULL
   OR pr.question_code_snapshot = ''
   OR pr.question_type_snapshot IS NULL
   OR pr.question_type_snapshot = ''
   OR pr.question_stem_snapshot IS NULL
   OR pr.question_stem_snapshot = ''
   OR pr.standard_answer_snapshot IS NULL
   OR pr.standard_answer_snapshot = ''
   OR pr.question_analysis_snapshot IS NULL
   OR pr.question_analysis_snapshot = ''
   OR pr.category_id_snapshot IS NULL
   OR pr.category_code_snapshot IS NULL
   OR pr.category_code_snapshot = ''
   OR pr.category_name_snapshot IS NULL
   OR pr.category_name_snapshot = ''
   OR pr.options_snapshot_json IS NULL;

INSERT INTO yk_practice_session (
    session_id,
    user_id,
    practice_code,
    category_id,
    mode,
    question_count,
    answered_count,
    correct_count,
    wrong_count,
    status,
    delete_status,
    started_at,
    completed_at
)
SELECT agg.session_id,
       agg.user_id,
       'legacy-import',
       agg.category_id,
       'standard',
       agg.question_count,
       agg.answered_count,
       agg.correct_count,
       agg.wrong_count,
       'completed',
       0,
       agg.started_at,
       agg.completed_at
FROM (
    SELECT pr.session_id,
           pr.user_id,
           COALESCE(MIN(q.category_id), @bootstrap_category_id) AS category_id,
           COUNT(*) AS question_count,
           COUNT(*) AS answered_count,
           SUM(CASE WHEN pr.correct_flag = 1 THEN 1 ELSE 0 END) AS correct_count,
           SUM(CASE WHEN pr.correct_flag = 1 THEN 0 ELSE 1 END) AS wrong_count,
           MIN(COALESCE(pr.answered_at, pr.created_at)) AS started_at,
           MAX(COALESCE(pr.answered_at, pr.created_at)) AS completed_at
    FROM yk_practice_record pr
    LEFT JOIN yk_question q
           ON q.id = pr.question_id
    GROUP BY pr.session_id, pr.user_id
) agg
WHERE NOT EXISTS (
    SELECT 1
    FROM yk_practice_session ps
    WHERE ps.session_id = agg.session_id
      AND ps.user_id = agg.user_id
);

CREATE TABLE IF NOT EXISTS yk_wrong_question_book (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    question_id BIGINT UNSIGNED NOT NULL COMMENT 'Question ID',
    latest_practice_record_id BIGINT UNSIGNED NULL COMMENT 'Latest wrong practice record ID',
    latest_session_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Latest wrong session ID',
    wrong_count INT NOT NULL DEFAULT 0 COMMENT 'Accumulated wrong answer count',
    latest_selected_answer VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Latest wrong selected answer',
    latest_wrong_answer_json JSON NULL COMMENT 'Latest wrong raw answer snapshot',
    latest_standard_answer VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Latest wrong standard answer snapshot',
    latest_wrong_at DATETIME NULL COMMENT 'Latest wrong answered time',
    status ENUM('active', 'removed') NOT NULL DEFAULT 'active' COMMENT 'Wrong question status: active, removed',
    removed_at DATETIME NULL COMMENT 'Removed time',
    delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_yk_wrong_question_book_user_question (user_id, question_id),
    KEY idx_yk_wrong_question_book_user_status (user_id, status, updated_at),
    KEY idx_yk_wrong_question_book_question_status (question_id, status, updated_at),
    CONSTRAINT fk_yk_wrong_question_book_user
        FOREIGN KEY (user_id) REFERENCES yk_user_account(id),
    CONSTRAINT fk_yk_wrong_question_book_question
        FOREIGN KEY (question_id) REFERENCES yk_question(id),
    CONSTRAINT fk_yk_wrong_question_book_record
        FOREIGN KEY (latest_practice_record_id) REFERENCES yk_practice_record(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP wrong question book';

INSERT INTO yk_wrong_question_book (
    user_id,
    question_id,
    latest_practice_record_id,
    latest_session_id,
    wrong_count,
    latest_selected_answer,
    latest_wrong_answer_json,
    latest_standard_answer,
    latest_wrong_at,
    status,
    removed_at,
    delete_status
)
SELECT agg.user_id,
       agg.question_id,
       agg.latest_record_id,
       COALESCE(pr.session_id, ''),
       agg.wrong_count,
       COALESCE(pr.selected_answer, ''),
       pr.answer_json,
       COALESCE(pr.standard_answer_snapshot, q.correct_answer, ''),
       pr.answered_at,
       'active',
       NULL,
       0
FROM (
    SELECT user_id,
           question_id,
           MAX(id) AS latest_record_id,
           COUNT(*) AS wrong_count
    FROM yk_practice_record
    WHERE correct_flag = 0
      AND delete_status = 0
      AND status = 'active'
    GROUP BY user_id, question_id
) agg
JOIN yk_practice_record pr
  ON pr.id = agg.latest_record_id
LEFT JOIN yk_question q
  ON q.id = agg.question_id
WHERE NOT EXISTS (
    SELECT 1
    FROM yk_wrong_question_book wb
    WHERE wb.user_id = agg.user_id
      AND wb.question_id = agg.question_id
);

ALTER TABLE yk_question_category
    MODIFY COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted';

ALTER TABLE yk_question
    MODIFY COLUMN question_type ENUM('single_choice', 'multiple_choice', 'judge') NOT NULL COMMENT 'Question type',
    MODIFY COLUMN category_id BIGINT UNSIGNED NOT NULL COMMENT 'Question category ID',
    MODIFY COLUMN question_code VARCHAR(64) NOT NULL COMMENT 'Question code',
    MODIFY COLUMN correct_answer VARCHAR(128) NOT NULL COMMENT 'Canonical correct answer',
    MODIFY COLUMN score INT NOT NULL DEFAULT 1 COMMENT 'Question score',
    MODIFY COLUMN sort_no INT NOT NULL DEFAULT 0 COMMENT 'Question sort order',
    MODIFY COLUMN source_ref VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Source reference',
    MODIFY COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted';

ALTER TABLE yk_question_option
    MODIFY COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT 'Option status: active, invalid',
    MODIFY COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted';

ALTER TABLE yk_practice_session
    MODIFY COLUMN mode ENUM('standard', 'wrongReview') NOT NULL DEFAULT 'standard' COMMENT 'Practice mode: standard, wrongReview',
    MODIFY COLUMN status ENUM('in_progress', 'completed', 'abandoned') NOT NULL DEFAULT 'in_progress' COMMENT 'Session status: in_progress, completed, abandoned',
    MODIFY COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted';

ALTER TABLE yk_practice_record
    MODIFY COLUMN session_id VARCHAR(64) NOT NULL COMMENT 'Practice session ID',
    MODIFY COLUMN selected_answer VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Canonical selected answer',
    MODIFY COLUMN question_code_snapshot VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Question code snapshot',
    MODIFY COLUMN question_type_snapshot VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'Question type snapshot',
    MODIFY COLUMN standard_answer_snapshot VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Standard answer snapshot',
    MODIFY COLUMN category_code_snapshot VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Category code snapshot',
    MODIFY COLUMN category_name_snapshot VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Category name snapshot',
    MODIFY COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT 'Record status: active, invalid',
    MODIFY COLUMN delete_status TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete status: 0-normal, 1-deleted';

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND INDEX_NAME = 'uk_yk_question_code'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD UNIQUE KEY uk_yk_question_code (question_code)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND INDEX_NAME = 'idx_yk_question_category_status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD KEY idx_yk_question_category_status (category_id, status, sort_no, id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND INDEX_NAME = 'uk_yk_practice_record_session_question'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD UNIQUE KEY uk_yk_practice_record_session_question (session_id, question_id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND INDEX_NAME = 'idx_yk_practice_record_session_time'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD KEY idx_yk_practice_record_session_time (session_id, answered_at)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND INDEX_NAME = 'idx_yk_practice_record_user_status'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD KEY idx_yk_practice_record_user_status (user_id, status, delete_status, answered_at)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_wrong_question_book'
              AND INDEX_NAME = 'uk_yk_wrong_question_book_user_question'
        ),
        'SELECT 1',
        'ALTER TABLE yk_wrong_question_book ADD UNIQUE KEY uk_yk_wrong_question_book_user_question (user_id, question_id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND CONSTRAINT_NAME = 'fk_tmp_yk_question_category'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'ALTER TABLE yk_question DROP FOREIGN KEY fk_tmp_yk_question_category',
        'SELECT 1'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT id, question_type
FROM yk_question
WHERE question_type NOT IN ('single_choice', 'multiple_choice', 'judge')
ORDER BY id
LIMIT 20;

SELECT id, session_id, question_id, selected_answer
FROM yk_practice_record
WHERE selected_answer = 'PENDING_MANUAL_CONFIRM'
ORDER BY id
LIMIT 20;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question'
              AND CONSTRAINT_NAME = 'fk_yk_question_category'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question ADD CONSTRAINT fk_yk_question_category FOREIGN KEY (category_id) REFERENCES yk_question_category(id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_question_option'
              AND CONSTRAINT_NAME = 'fk_yk_question_option_question'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_question_option ADD CONSTRAINT fk_yk_question_option_question FOREIGN KEY (question_id) REFERENCES yk_question(id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_session'
              AND CONSTRAINT_NAME = 'fk_yk_practice_session_user'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_session ADD CONSTRAINT fk_yk_practice_session_user FOREIGN KEY (user_id) REFERENCES yk_user_account(id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_session'
              AND CONSTRAINT_NAME = 'fk_yk_practice_session_category'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_session ADD CONSTRAINT fk_yk_practice_session_category FOREIGN KEY (category_id) REFERENCES yk_question_category(id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_session'
              AND INDEX_NAME = 'uk_yk_practice_session_session_user'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_session ADD UNIQUE KEY uk_yk_practice_session_session_user (session_id, user_id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND CONSTRAINT_NAME = 'fk_yk_practice_record_question'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD CONSTRAINT fk_yk_practice_record_question FOREIGN KEY (question_id) REFERENCES yk_question(id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_practice_record'
              AND CONSTRAINT_NAME = 'fk_yk_practice_record_session_user'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_practice_record ADD CONSTRAINT fk_yk_practice_record_session_user FOREIGN KEY (session_id, user_id) REFERENCES yk_practice_session(session_id, user_id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_wrong_question_book'
              AND CONSTRAINT_NAME = 'fk_yk_wrong_question_book_user'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_wrong_question_book ADD CONSTRAINT fk_yk_wrong_question_book_user FOREIGN KEY (user_id) REFERENCES yk_user_account(id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_wrong_question_book'
              AND CONSTRAINT_NAME = 'fk_yk_wrong_question_book_question'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_wrong_question_book ADD CONSTRAINT fk_yk_wrong_question_book_question FOREIGN KEY (question_id) REFERENCES yk_question(id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'yk_wrong_question_book'
              AND CONSTRAINT_NAME = 'fk_yk_wrong_question_book_record'
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        ),
        'SELECT 1',
        'ALTER TABLE yk_wrong_question_book ADD CONSTRAINT fk_yk_wrong_question_book_record FOREIGN KEY (latest_practice_record_id) REFERENCES yk_practice_record(id)'
    )
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
