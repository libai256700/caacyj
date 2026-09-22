-- ============================================
-- Script type: ddl
-- Script description: Extend account table and login audit table for mobile-account and password login
-- Created at: 2026-05-13 09:30:00
-- Author: Codex
-- Impact scope: yunjikeji test database login-related tables
-- Execution environment: test
-- ============================================

-- Pre-check: ensure yk_user_account baseline table already exists
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_user_account';

SET @ddl := IF(
    EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'yk_user_account'
          AND COLUMN_NAME = 'password_salt'
    ),
    'SELECT ''skip add password_salt''',
    'ALTER TABLE yk_user_account ADD COLUMN password_salt VARCHAR(64) NOT NULL DEFAULT '''' COMMENT ''Password salt'' AFTER status'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'yk_user_account'
          AND COLUMN_NAME = 'password_hash'
    ),
    'SELECT ''skip add password_hash''',
    'ALTER TABLE yk_user_account ADD COLUMN password_hash VARCHAR(128) NOT NULL DEFAULT '''' COMMENT ''Password hash'' AFTER password_salt'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'yk_user_account'
          AND COLUMN_NAME = 'password_initialized_at'
    ),
    'SELECT ''skip add password_initialized_at''',
    'ALTER TABLE yk_user_account ADD COLUMN password_initialized_at DATETIME NULL COMMENT ''Password initialized time'' AFTER password_hash'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'yk_user_account'
          AND COLUMN_NAME = 'last_login_at'
    ),
    'SELECT ''skip add last_login_at''',
    'ALTER TABLE yk_user_account ADD COLUMN last_login_at DATETIME NULL COMMENT ''Latest login time'' AFTER password_initialized_at'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'yk_user_account'
          AND COLUMN_NAME = 'last_login_channel'
    ),
    'SELECT ''skip add last_login_channel''',
    'ALTER TABLE yk_user_account ADD COLUMN last_login_channel VARCHAR(32) NOT NULL DEFAULT '''' COMMENT ''Latest login channel'' AFTER last_login_at'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS yk_login_audit (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'User account ID',
    mobile VARCHAR(32) NOT NULL COMMENT 'Login mobile number',
    login_channel VARCHAR(32) NOT NULL DEFAULT 'password' COMMENT 'Login channel',
    login_result VARCHAR(32) NOT NULL DEFAULT 'success' COMMENT 'Login result',
    password_match_flag TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether password matched',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
    is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Logical delete flag',
    PRIMARY KEY (id),
    KEY idx_yk_login_audit_user_time (user_id, created_at),
    KEY idx_yk_login_audit_mobile_time (mobile, created_at),
    CONSTRAINT fk_yk_login_audit_user FOREIGN KEY (user_id) REFERENCES yk_user_account (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP login audit';

SET @ddl := IF(
    EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'yk_login_audit'
          AND COLUMN_NAME = 'login_result'
    ),
    'SELECT ''skip add yk_login_audit.login_result''',
    'ALTER TABLE yk_login_audit ADD COLUMN login_result VARCHAR(32) NOT NULL DEFAULT ''success'' COMMENT ''Login result'' AFTER login_channel'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'yk_login_audit'
          AND COLUMN_NAME = 'password_match_flag'
    ),
    'SELECT ''skip add yk_login_audit.password_match_flag''',
    'ALTER TABLE yk_login_audit ADD COLUMN password_match_flag TINYINT(1) NOT NULL DEFAULT 1 COMMENT ''Whether password matched'' AFTER login_result'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Post-check: confirm required account and audit fields exist
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_user_account'
  AND COLUMN_NAME IN (
    'password_salt',
    'password_hash',
    'password_initialized_at',
    'last_login_at',
    'last_login_channel'
  )
ORDER BY COLUMN_NAME;

SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_login_audit'
  AND COLUMN_NAME IN ('login_channel', 'login_result', 'password_match_flag')
ORDER BY COLUMN_NAME;

-- Rollback reference:
-- 1. DROP TABLE yk_login_audit;
-- 2. ALTER TABLE yk_user_account
--       DROP COLUMN last_login_channel,
--       DROP COLUMN last_login_at,
--       DROP COLUMN password_initialized_at,
--       DROP COLUMN password_hash,
--       DROP COLUMN password_salt;
