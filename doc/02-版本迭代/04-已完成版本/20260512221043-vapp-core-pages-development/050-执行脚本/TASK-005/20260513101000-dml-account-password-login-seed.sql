-- ============================================
-- Script type: dml
-- Script description: Seed TASK-005 test account for mobile-account and password login
-- Created at: 2026-05-13 10:10:00
-- Author: Codex
-- Impact scope: yunjikeji test database yk_user_account
-- Execution environment: test
-- ============================================

-- Pre-check: ensure TASK-005 DDL has been executed
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_user_account'
  AND COLUMN_NAME IN ('password_salt', 'password_hash', 'password_initialized_at')
ORDER BY COLUMN_NAME;

SET @seed_mobile = '13800138000';
SET @seed_nickname = 'Flight Student';
SET @seed_password = 'Yk@20260513';
SET @seed_password_salt = 'TASK005_LOGIN_SALT_V1';
SET @seed_password_hash = SHA2(CONCAT(@seed_password_salt, ':', @seed_password), 256);

UPDATE yk_user_account
   SET nickname = @seed_nickname,
       status = 'active',
       password_salt = @seed_password_salt,
       password_hash = @seed_password_hash,
       password_initialized_at = CURRENT_TIMESTAMP,
       updated_at = CURRENT_TIMESTAMP
 WHERE mobile = @seed_mobile;

INSERT INTO yk_user_account (
    mobile,
    nickname,
    status,
    password_salt,
    password_hash,
    password_initialized_at
)
SELECT
    @seed_mobile,
    @seed_nickname,
    'active',
    @seed_password_salt,
    @seed_password_hash,
    CURRENT_TIMESTAMP
FROM dual
WHERE NOT EXISTS (
    SELECT 1
      FROM yk_user_account
     WHERE mobile = @seed_mobile
);

-- Post-check: confirm the integration account is ready
SELECT id,
       mobile,
       status,
       password_initialized_at,
       last_login_channel,
       last_login_at
FROM yk_user_account
WHERE mobile = @seed_mobile;

-- Rollback reference:
-- UPDATE yk_user_account
--    SET password_salt = '',
--        password_hash = '',
--        password_initialized_at = NULL,
--        updated_at = CURRENT_TIMESTAMP
--  WHERE mobile = @seed_mobile;
