-- ============================================
-- Script type: ddl
-- Description: Roll back shared practice index normalization
-- Created at: 2026-08-17 11:31:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_wrong_record_detail, optional yj_assessment_question/yj_assessment_answer
-- Environment: test / production after approval and backup
-- ============================================

SET @idx_exists := (SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
    AND INDEX_NAME = 'uk_yj_wrong_detail_customer_exercises');
SET @ddl := CONCAT('ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ',
  IF(@idx_exists > 0, 'DROP INDEX `uk_yj_wrong_detail_customer_exercises`, ', ''),
  'ADD UNIQUE KEY `uk_yj_wrong_detail_customer_exercises` (`tenant_id`, `customer_account_id`, `exercises`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx_exists := (SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
    AND INDEX_NAME = 'idx_yj_wrong_detail_customer_time');
SET @ddl := CONCAT('ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ',
  IF(@idx_exists > 0, 'DROP INDEX `idx_yj_wrong_detail_customer_time`, ', ''),
  'ADD KEY `idx_yj_wrong_detail_customer_time` (`tenant_id`, `customer_account_id`, `latest_wrong_time`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx_exists := (SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
    AND INDEX_NAME = 'idx_tenant_id');
SET @ddl := IF(@idx_exists = 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ADD KEY `idx_tenant_id` (`tenant_id`)',
  'SELECT ''idx_tenant_id already restored'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Set to 1 only when execution evidence proves the forward script removed compatibility tenant columns.
SET @restore_compat_tenant_columns := 0;

-- Optional compatibility rollback restores the conventional tenant column only when explicitly enabled.
SET @compat_table := 'yj_assessment_question';
SET @compat_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table);
SET @compat_tenant_column := (SELECT COUNT(1) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table AND COLUMN_NAME = 'tenant_id');
SET @ddl := IF(@restore_compat_tenant_columns = 1 AND @compat_exists = 1 AND @compat_tenant_column = 0,
  CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT ''tenant id'', ADD KEY `idx_tenant_id` (`tenant_id`)'),
  'SELECT ''yj_assessment_question absent or tenant column already present'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @compat_table := 'yj_assessment_answer';
SET @compat_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table);
SET @compat_tenant_column := (SELECT COUNT(1) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table AND COLUMN_NAME = 'tenant_id');
SET @ddl := IF(@restore_compat_tenant_columns = 1 AND @compat_exists = 1 AND @compat_tenant_column = 0,
  CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT ''tenant id'', ADD KEY `idx_tenant_id` (`tenant_id`)'),
  'SELECT ''yj_assessment_answer absent or tenant column already present'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Post-check.
SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('yj_user_practice_exercises_wrong_record_detail', 'yj_assessment_question', 'yj_assessment_answer')
GROUP BY TABLE_NAME, INDEX_NAME
ORDER BY TABLE_NAME, INDEX_NAME;
