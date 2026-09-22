-- ============================================
-- Script type: backup
-- Script description: Backup yk_user_account record for mobile 18171171929 before password reset
-- Created at: 2026-05-13 17:17:43
-- Author: Codex
-- Impact scope: yunjikeji test database yk_user_account
-- Execution environment: test
-- ============================================

SELECT id,
       mobile,
       nickname,
       status,
       password_salt,
       password_hash,
       password_initialized_at,
       updated_at
FROM yk_user_account
WHERE id = 4
  AND mobile = '18171171929';
