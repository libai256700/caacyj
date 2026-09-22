-- Rollback for yj_ai_center history table index.
-- Do not drop yj_ai_center: this is an existing AI conversation table.

SET @idx_exists := (
  SELECT COUNT(1)
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'yj_ai_center'
    AND index_name = 'idx_yj_ai_center_account_name_id'
);
SET @idx_sql := IF(
  @idx_exists > 0,
  'ALTER TABLE `yj_ai_center` DROP INDEX `idx_yj_ai_center_account_name_id`',
  'SELECT 1'
);
PREPARE stmt FROM @idx_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
