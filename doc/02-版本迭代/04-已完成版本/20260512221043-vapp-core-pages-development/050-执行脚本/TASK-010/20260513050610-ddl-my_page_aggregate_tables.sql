-- ============================================
-- 脚本类型：ddl
-- 脚本描述：创建我的页聚合所需的资料、学习、简历、投递和面试数据表
-- 创建日期：2026-05-13 05:06:10
-- 作者：Codex
-- 影响范围：yunjikeji 测试库新增我的页聚合表
-- 执行环境：测试环境
-- ============================================

CREATE TABLE IF NOT EXISTS yk_user_profile (
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    avatar_url VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'Avatar URL',
    student_no VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Student number',
    school_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'School name',
    major_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Major name',
    role_label VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Role label',
    training_direction VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Training direction',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (user_id),
    CONSTRAINT fk_yk_user_profile_user FOREIGN KEY (user_id) REFERENCES yk_user_account (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP user profile';

CREATE TABLE IF NOT EXISTS yk_learning_profile (
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    course_total INT NOT NULL DEFAULT 0 COMMENT 'Course total',
    practice_total INT NOT NULL DEFAULT 0 COMMENT 'Practice total',
    learning_progress INT NOT NULL DEFAULT 0 COMMENT 'Learning progress percentage',
    current_course_title VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Current course title',
    current_course_progress INT NOT NULL DEFAULT 0 COMMENT 'Current course progress percentage',
    continue_days INT NOT NULL DEFAULT 0 COMMENT 'Continue learning days',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (user_id),
    CONSTRAINT fk_yk_learning_profile_user FOREIGN KEY (user_id) REFERENCES yk_user_account (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP learning profile';

CREATE TABLE IF NOT EXISTS yk_resume_profile (
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    resume_status VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Resume status',
    completion_percent INT NOT NULL DEFAULT 0 COMMENT 'Resume completion percentage',
    suggestion_count INT NOT NULL DEFAULT 0 COMMENT 'Suggestion count',
    latest_note VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Latest resume note',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (user_id),
    CONSTRAINT fk_yk_resume_profile_user FOREIGN KEY (user_id) REFERENCES yk_user_account (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP resume profile';

CREATE TABLE IF NOT EXISTS yk_job_application_record (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    company_name VARCHAR(128) NOT NULL COMMENT 'Company name',
    position_name VARCHAR(128) NOT NULL COMMENT 'Position name',
    application_status VARCHAR(32) NOT NULL DEFAULT 'applying' COMMENT 'Application status',
    applied_at DATETIME NOT NULL COMMENT 'Applied time',
    note VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Application note',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_yk_job_application_record_unique (user_id, company_name, position_name, applied_at),
    KEY idx_yk_job_application_record_user_status (user_id, application_status),
    KEY idx_yk_job_application_record_user_time (user_id, applied_at),
    CONSTRAINT fk_yk_job_application_record_user FOREIGN KEY (user_id) REFERENCES yk_user_account (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP job application record';

CREATE TABLE IF NOT EXISTS yk_interview_schedule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    company_name VARCHAR(128) NOT NULL COMMENT 'Company name',
    position_name VARCHAR(128) NOT NULL COMMENT 'Position name',
    interview_status VARCHAR(32) NOT NULL DEFAULT 'scheduled' COMMENT 'Interview status',
    interview_time DATETIME NOT NULL COMMENT 'Interview time',
    note VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Interview note',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_yk_interview_schedule_unique (user_id, company_name, position_name, interview_time),
    KEY idx_yk_interview_schedule_user_status (user_id, interview_status),
    KEY idx_yk_interview_schedule_user_time (user_id, interview_time),
    CONSTRAINT fk_yk_interview_schedule_user FOREIGN KEY (user_id) REFERENCES yk_user_account (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP interview schedule';
