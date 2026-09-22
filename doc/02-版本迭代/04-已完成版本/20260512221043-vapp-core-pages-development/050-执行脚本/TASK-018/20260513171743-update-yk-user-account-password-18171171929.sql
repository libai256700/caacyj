-- ============================================
-- Script type: dml
-- Script description: Reset test account 18171171929 password to wan123456 using AuthService hash rule
-- Created at: 2026-05-13 17:17:43
-- Author: Codex
-- Impact scope: yunjikeji test database yk_user_account
-- Execution environment: test
-- ============================================

SET @target_id = 4;
SET @target_mobile = '18171171929';
SET @target_password = 'wan123456';
SET @target_password_salt = 'TASK018_RESET_18171171929_V1';
SET @target_password_hash = SHA2(CONCAT(@target_password_salt, ':', @target_password), 256);

SELECT id,
       mobile,
       status,
       password_salt,
       password_hash,
       password_initialized_at
FROM yk_user_account
WHERE id = @target_id
  AND mobile = @target_mobile;

UPDATE yk_user_account
   SET password_salt = @target_password_salt,
       password_hash = @target_password_hash,
       password_initialized_at = CURRENT_TIMESTAMP,
       updated_at = CURRENT_TIMESTAMP
 WHERE id = @target_id
   AND mobile = @target_mobile;

SELECT id,
       mobile,
       status,
       password_salt,
       password_hash,
       password_initialized_at
FROM yk_user_account
WHERE id = @target_id
  AND mobile = @target_mobile;
