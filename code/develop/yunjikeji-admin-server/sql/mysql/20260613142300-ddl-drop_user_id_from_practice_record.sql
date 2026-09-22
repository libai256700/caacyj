-- ============================================
-- Script type: ddl
-- Description: Drop legacy user id from practice record
-- Created at: 2026-06-13 14:23:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_record
-- Environment: test
-- ============================================

-- Pre-check:
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_user_practice_exercises_record'
  AND COLUMN_NAME IN ('user_id', 'customer_account_id')
ORDER BY ORDINAL_POSITION;

SET @drop_record_user_id = (
  SELECT IF(
    COUNT(1) > 0,
    'ALTER TABLE `yj_user_practice_exercises_record` DROP COLUMN `user_id`',
    'SELECT ''yj_user_practice_exercises_record.user_id not exists'' AS message'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'yj_user_practice_exercises_record'
    AND COLUMN_NAME = 'user_id'
);
PREPARE stmt FROM @drop_record_user_id;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Post-check:
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_user_practice_exercises_record'
  AND COLUMN_NAME IN ('user_id', 'customer_account_id')
ORDER BY ORDINAL_POSITION;
