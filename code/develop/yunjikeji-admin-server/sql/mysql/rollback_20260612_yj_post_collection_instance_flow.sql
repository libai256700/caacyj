-- Rollback for 20260612_yj_post_collection_instance_flow.sql
-- Scope: test database yunjikeji

SET @schema_name := DATABASE();

DROP TABLE IF EXISTS `yj_post_instance`;
DROP TABLE IF EXISTS `yj_post_collection_task_instance`;

SET @sql := (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE `yj_post` DROP INDEX `idx_yj_post_dedupe`',
    'SELECT ''idx_yj_post_dedupe already absent''')
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post' AND INDEX_NAME = 'idx_yj_post_dedupe'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post` ADD COLUMN `tenant_id` bigint DEFAULT 0 COMMENT ''租户编号''',
    'SELECT ''yj_post.tenant_id already exists''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'tenant_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post` ADD COLUMN `company_id` bigint DEFAULT NULL COMMENT ''企业编号'' AFTER `name`',
    'SELECT ''yj_post.company_id already exists''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'company_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
