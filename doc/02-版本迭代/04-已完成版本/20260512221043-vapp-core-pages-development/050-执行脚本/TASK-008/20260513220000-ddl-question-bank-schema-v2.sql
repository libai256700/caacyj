-- TASK-008 practice page question bank schema v2
-- Formal executable route for current baseline and test DB landing.
-- Target database: yunjikeji

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

UPDATE yk_question
SET delete_status = 0
WHERE delete_status IS NULL;

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

UPDATE yk_practice_record
SET selected_answer = CASE
        WHEN selected_answer IS NOT NULL
             AND TRIM(selected_answer) <> ''
             AND selected_answer <> 'PENDING_MANUAL_CONFIRM'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(selected_answer), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '"', ''))
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selectedAnswer')), '') <> ''
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selectedAnswer'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '"', ''))
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selected_answer')), '') <> ''
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selected_answer'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '"', ''))
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.answer')), '') <> ''
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.answer'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '"', ''))
        WHEN JSON_VALID(answer_json)
             AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.submitAnswer')), '') <> ''
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.submitAnswer'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '"', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.selectedOptionCodes')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selectedOptionCodes'))), '[', ''), ']', ''), '"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.selected_option_codes')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.selected_option_codes'))), '[', ''), ']', ''), '"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.optionCodes')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.optionCodes'))), '[', ''), ']', ''), '"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.option_codes')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.option_codes'))), '[', ''), ']', ''), '"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.answers')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.answers'))), '[', ''), ']', ''), '"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.answerList')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.answerList'))), '[', ''), ']', ''), '"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$.options')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$.options'))), '[', ''), ']', ''), '"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$')) = 'ARRAY'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$'))), '[', ''), ']', ''), '"', ''), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''))
        WHEN JSON_VALID(answer_json)
             AND JSON_TYPE(JSON_EXTRACT(answer_json, '$')) = 'STRING'
            THEN TRIM(BOTH ',' FROM REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(JSON_UNQUOTE(JSON_EXTRACT(answer_json, '$'))), '，', ','), '、', ','), ';', ','), '|', ','), ' ', ''), '"', ''))
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
WHERE selected_answer IS NULL
   OR TRIM(selected_answer) = ''
   OR selected_answer = 'PENDING_MANUAL_CONFIRM'
   OR status IS NULL
   OR status = ''
   OR delete_status IS NULL;

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
        WHEN pr.options_snapshot_json IS NULL
            THEN q.options_json
        ELSE pr.options_snapshot_json
    END
WHERE pr.question_code_snapshot IS NULL
   OR pr.question_code_snapshot = ''
   OR pr.question_type_snapshot IS NULL
   OR pr.question_type_snapshot = ''
   OR pr.standard_answer_snapshot IS NULL
   OR pr.standard_answer_snapshot = ''
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
       'practice-default',
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
           COALESCE(MIN(q.category_id), 1) AS category_id,
           COUNT(*) AS question_count,
           COUNT(*) AS answered_count,
           SUM(CASE WHEN pr.correct_flag = 1 THEN 1 ELSE 0 END) AS correct_count,
           SUM(CASE WHEN pr.correct_flag = 1 THEN 0 ELSE 1 END) AS wrong_count,
           MIN(COALESCE(pr.answered_at, pr.created_at)) AS started_at,
           MAX(COALESCE(pr.answered_at, pr.created_at)) AS completed_at
    FROM yk_practice_record pr
    LEFT JOIN yk_question q
           ON q.id = pr.question_id
    WHERE pr.session_id IS NOT NULL
      AND pr.session_id <> ''
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

SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'yk_question_category',
    'yk_question',
    'yk_question_option',
    'yk_practice_session',
    'yk_practice_record',
    'yk_wrong_question_book',
    'yk_question_import_staging',
    'yk_question_import_option_staging'
  )
ORDER BY TABLE_NAME;

SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_practice_record'
  AND COLUMN_NAME IN (
    'session_id',
    'selected_answer',
    'question_code_snapshot',
    'question_type_snapshot',
    'question_stem_snapshot',
    'standard_answer_snapshot',
    'question_analysis_snapshot',
    'category_id_snapshot',
    'category_code_snapshot',
    'category_name_snapshot',
    'options_snapshot_json',
    'status',
    'delete_status'
  )
ORDER BY COLUMN_NAME;

SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_question'
  AND COLUMN_NAME IN (
    'category_id',
    'question_code',
    'question_type',
    'correct_answer',
    'score',
    'sort_no',
    'source_ref',
    'status',
    'delete_status'
  )
ORDER BY COLUMN_NAME;

SELECT id, session_id, question_id, selected_answer
FROM yk_practice_record
WHERE selected_answer = 'PENDING_MANUAL_CONFIRM'
ORDER BY id
LIMIT 20;
