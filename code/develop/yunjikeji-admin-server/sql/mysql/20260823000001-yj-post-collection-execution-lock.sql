-- Prevent concurrent processes from running the same Feishu collection task.
-- The statements are idempotent for existing test environments.

SET @schema_name := DATABASE();

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post_collection_task` ADD COLUMN `collection_lock_owner` varchar(128) DEFAULT NULL COMMENT ''采集执行锁持有者'' AFTER `last_execute_status`',
    'SELECT ''collection_lock_owner already exists''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'yj_post_collection_task'
    AND COLUMN_NAME = 'collection_lock_owner'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post_collection_task` ADD COLUMN `collection_lock_until` datetime DEFAULT NULL COMMENT ''采集执行锁过期时间'' AFTER `collection_lock_owner`',
    'SELECT ''collection_lock_until already exists''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'yj_post_collection_task'
    AND COLUMN_NAME = 'collection_lock_until'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post_collection_task` ADD KEY `idx_yj_post_collection_task_lock_until` (`collection_lock_until`)',
    'SELECT ''idx_yj_post_collection_task_lock_until already exists''')
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'yj_post_collection_task'
    AND INDEX_NAME = 'idx_yj_post_collection_task_lock_until'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
