-- ============================================
-- Script type: ddl
-- Description: Normalize shared practice indexes and optional compatibility tables
-- Created at: 2026-08-17 11:30:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_wrong_record_detail, optional yj_assessment_question/yj_assessment_answer
-- Environment: test / production after approval and backup
-- ============================================

-- Pre-check: a non-zero result blocks the wrong-record index change and requires reviewed data migration.
SELECT customer_account_id, exercises, COUNT(1) AS duplicate_count
FROM yj_user_practice_exercises_wrong_record_detail
GROUP BY customer_account_id, exercises
HAVING COUNT(1) > 1;

SET @wrong_duplicate_count := (
  SELECT COUNT(1)
  FROM (
    SELECT customer_account_id, exercises
    FROM yj_user_practice_exercises_wrong_record_detail
    GROUP BY customer_account_id, exercises
    HAVING COUNT(1) > 1
  ) duplicate_rows
);

SET @wrong_unique_exists := (SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
    AND INDEX_NAME = 'uk_yj_wrong_detail_customer_exercises');
SET @ddl := IF(@wrong_duplicate_count > 0,
  'SELECT ''blocked: cross-tenant wrong-record duplicates exist'' AS info',
  CONCAT('ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ',
    IF(@wrong_unique_exists > 0, 'DROP INDEX `uk_yj_wrong_detail_customer_exercises`, ', ''),
    'ADD UNIQUE KEY `uk_yj_wrong_detail_customer_exercises` (`customer_account_id`, `exercises`)'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @wrong_time_exists := (SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
    AND INDEX_NAME = 'idx_yj_wrong_detail_customer_time');
SET @ddl := IF(@wrong_duplicate_count > 0,
  'SELECT ''blocked: wrong-record query index unchanged'' AS info',
  CONCAT('ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ',
    IF(@wrong_time_exists > 0, 'DROP INDEX `idx_yj_wrong_detail_customer_time`, ', ''),
    'ADD KEY `idx_yj_wrong_detail_customer_time` (`customer_account_id`, `latest_wrong_time`)'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @wrong_tenant_index_exists := (SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
    AND INDEX_NAME = 'idx_tenant_id');
SET @ddl := IF(@wrong_duplicate_count = 0 AND @wrong_tenant_index_exists > 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` DROP INDEX `idx_tenant_id`',
  'SELECT ''idx_tenant_id absent or duplicate gate blocked'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Compatibility tables are optional. Unknown tenant composite indexes block automatic column removal.
SET @compat_table := 'yj_assessment_question';
SET @compat_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table);
SET @compat_tenant_column := (SELECT COUNT(1) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table AND COLUMN_NAME = 'tenant_id');
SET @compat_other_indexes := (SELECT COUNT(DISTINCT INDEX_NAME) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table AND COLUMN_NAME = 'tenant_id'
    AND INDEX_NAME <> 'idx_tenant_id');
SET @compat_tenant_index := (SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table AND INDEX_NAME = 'idx_tenant_id');
SET @ddl := IF(@compat_exists = 1 AND @compat_tenant_column = 1 AND @compat_other_indexes = 0
    AND @compat_tenant_index <= 1,
  CONCAT('ALTER TABLE `', @compat_table, '` ', IF(@compat_tenant_index > 0, 'DROP INDEX `idx_tenant_id`, ', ''),
    'DROP COLUMN `tenant_id`'),
  'SELECT ''yj_assessment_question absent/already shared/or requires index review'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @compat_table := 'yj_assessment_answer';
SET @compat_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table);
SET @compat_tenant_column := (SELECT COUNT(1) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table AND COLUMN_NAME = 'tenant_id');
SET @compat_other_indexes := (SELECT COUNT(DISTINCT INDEX_NAME) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table AND COLUMN_NAME = 'tenant_id'
    AND INDEX_NAME <> 'idx_tenant_id');
SET @compat_tenant_index := (SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @compat_table AND INDEX_NAME = 'idx_tenant_id');
SET @ddl := IF(@compat_exists = 1 AND @compat_tenant_column = 1 AND @compat_other_indexes = 0
    AND @compat_tenant_index <= 1,
  CONCAT('ALTER TABLE `', @compat_table, '` ', IF(@compat_tenant_index > 0, 'DROP INDEX `idx_tenant_id`, ', ''),
    'DROP COLUMN `tenant_id`'),
  'SELECT ''yj_assessment_answer absent/already shared/or requires index review'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Post-check.
SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('yj_user_practice_exercises_wrong_record_detail', 'yj_assessment_question', 'yj_assessment_answer')
GROUP BY TABLE_NAME, INDEX_NAME
ORDER BY TABLE_NAME, INDEX_NAME;

-- Compatibility-column status must be reviewed directly, not inferred from indexes alone.
SELECT expected.table_name,
       IF(table_meta.TABLE_NAME IS NULL, 0, 1) AS table_exists,
       IF(tenant_column.COLUMN_NAME IS NULL, 0, 1) AS tenant_id_exists,
       CASE
         WHEN table_meta.TABLE_NAME IS NULL THEN 'OPTIONAL_TABLE_ABSENT'
         WHEN tenant_column.COLUMN_NAME IS NULL THEN 'TENANT_ID_REMOVED'
         WHEN EXISTS (
           SELECT 1
           FROM information_schema.STATISTICS tenant_index
           WHERE tenant_index.TABLE_SCHEMA = DATABASE()
             AND tenant_index.TABLE_NAME = expected.table_name
             AND tenant_index.COLUMN_NAME = 'tenant_id'
             AND tenant_index.INDEX_NAME <> 'idx_tenant_id'
         ) OR (
           SELECT COUNT(1)
           FROM information_schema.STATISTICS named_index_column
           WHERE named_index_column.TABLE_SCHEMA = DATABASE()
             AND named_index_column.TABLE_NAME = expected.table_name
             AND named_index_column.INDEX_NAME = 'idx_tenant_id'
         ) > 1 THEN 'TENANT_ID_RETAINED_REQUIRES_INDEX_REVIEW'
         ELSE 'TENANT_ID_PRESENT_UNEXPECTED'
       END AS tenant_policy_status
FROM (
  SELECT 'yj_assessment_question' AS table_name
  UNION ALL
  SELECT 'yj_assessment_answer'
) expected
LEFT JOIN information_schema.TABLES table_meta
  ON table_meta.TABLE_SCHEMA = DATABASE() AND table_meta.TABLE_NAME = expected.table_name
LEFT JOIN information_schema.COLUMNS tenant_column
  ON tenant_column.TABLE_SCHEMA = DATABASE()
 AND tenant_column.TABLE_NAME = expected.table_name
 AND tenant_column.COLUMN_NAME = 'tenant_id'
ORDER BY expected.table_name;
