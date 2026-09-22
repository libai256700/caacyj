-- ============================================
-- Script type: ddl
-- Description: Recreate legacy user id on practice record
-- Created at: 2026-06-13 14:23:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_record
-- Environment: test
-- ============================================

SET @add_record_user_id = (
  SELECT IF(
    COUNT(1) = 0,
    'ALTER TABLE `yj_user_practice_exercises_record` ADD COLUMN `user_id` bigint NOT NULL COMMENT ''所属学员'' AFTER `id`',
    'SELECT ''yj_user_practice_exercises_record.user_id exists'' AS message'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'yj_user_practice_exercises_record'
    AND COLUMN_NAME = 'user_id'
);
PREPARE stmt FROM @add_record_user_id;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `yj_user_practice_exercises_record`
SET `user_id` = `customer_account_id`
WHERE `user_id` = 0
   OR `user_id` IS NULL;
