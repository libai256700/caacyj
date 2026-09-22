-- TASK-017 backend and database baseline
-- First idempotent DDL batch for VAPP core pages.
-- Target database: yunjikeji

CREATE TABLE IF NOT EXISTS yk_user_account (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    mobile VARCHAR(32) NOT NULL COMMENT 'User mobile number',
    nickname VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Display nickname',
    avatar_url VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'Avatar URL',
    status VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT 'Account status: active, disabled',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_yk_user_account_mobile (mobile),
    KEY idx_yk_user_account_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP user account';

CREATE TABLE IF NOT EXISTS yk_training_course (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    course_type VARCHAR(32) NOT NULL COMMENT 'Course type',
    title VARCHAR(128) NOT NULL COMMENT 'Course title',
    cover_url VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'Course cover URL',
    summary VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'Course summary',
    sort_no INT NOT NULL DEFAULT 0 COMMENT 'Display order',
    status VARCHAR(32) NOT NULL DEFAULT 'draft' COMMENT 'Course status: draft, online, offline',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    KEY idx_yk_training_course_type_status (course_type, status),
    KEY idx_yk_training_course_sort (sort_no, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP training course';

CREATE TABLE IF NOT EXISTS yk_question (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    course_id BIGINT UNSIGNED NULL COMMENT 'Related course ID',
    question_type VARCHAR(32) NOT NULL COMMENT 'Question type',
    stem TEXT NOT NULL COMMENT 'Question stem',
    options_json JSON NULL COMMENT 'Question options JSON',
    answer_json JSON NULL COMMENT 'Question answer JSON',
    analysis TEXT NULL COMMENT 'Answer analysis',
    difficulty VARCHAR(32) NOT NULL DEFAULT 'normal' COMMENT 'Question difficulty',
    status VARCHAR(32) NOT NULL DEFAULT 'draft' COMMENT 'Question status: draft, online, offline',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    KEY idx_yk_question_course_status (course_id, status),
    KEY idx_yk_question_type_status (question_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP question bank item';

CREATE TABLE IF NOT EXISTS yk_practice_record (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    course_id BIGINT UNSIGNED NULL COMMENT 'Course ID',
    question_id BIGINT UNSIGNED NOT NULL COMMENT 'Question ID',
    answer_json JSON NULL COMMENT 'Submitted answer JSON',
    correct_flag TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether answer is correct',
    answered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Answered time',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    PRIMARY KEY (id),
    KEY idx_yk_practice_record_user_time (user_id, answered_at),
    KEY idx_yk_practice_record_question (question_id),
    KEY idx_yk_practice_record_course (course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP practice answer record';

