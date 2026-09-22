-- Keep the recruitment platform source and the configured collection channel separate.
-- This lets the admin page filter Feishu-collected posts without losing the source
-- identified from the original job detail URL.

SET @schema_name := DATABASE();

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post` ADD COLUMN `collection_channel` varchar(32) DEFAULT NULL COMMENT ''岗位采集渠道'' AFTER `source_code`',
    'SELECT ''yj_post.collection_channel already exists''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'collection_channel'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post_instance` ADD COLUMN `collection_channel` varchar(32) DEFAULT NULL COMMENT ''岗位采集渠道'' AFTER `source_code`',
    'SELECT ''yj_post_instance.collection_channel already exists''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post_instance' AND COLUMN_NAME = 'collection_channel'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post` ADD INDEX `idx_yj_post_collection_channel` (`collection_channel`)',
    'SELECT ''idx_yj_post_collection_channel already exists''')
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post'
    AND INDEX_NAME = 'idx_yj_post_collection_channel'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post_instance` ADD INDEX `idx_yj_post_instance_collection_channel` (`collection_channel`)',
    'SELECT ''idx_yj_post_instance_collection_channel already exists''')
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post_instance'
    AND INDEX_NAME = 'idx_yj_post_instance_collection_channel'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Backfill posts already linked to a Feishu collection audit item.
UPDATE `yj_post` p
JOIN `yj_feishu_post_document_item` i ON i.`target_post_id` = p.`id`
JOIN `yj_feishu_post_collection_run` r ON r.`id` = i.`run_id`
SET p.`collection_channel` = 'feishu_folder'
WHERE p.`deleted` = b'0'
  AND i.`deleted` = b'0'
  AND r.`deleted` = b'0'
  AND (p.`collection_channel` IS NULL OR p.`collection_channel` = '');

-- Backfill collection instances from their task configuration.
UPDATE `yj_post_instance` pi
JOIN `yj_post_collection_task_instance` ti ON ti.`id` = pi.`task_instance_id`
JOIN `yj_post_collection_task` t ON t.`id` = ti.`task_id`
SET pi.`collection_channel` = t.`collection_channel`
WHERE pi.`deleted` = b'0'
  AND ti.`deleted` = b'0'
  AND t.`deleted` = b'0'
  AND (pi.`collection_channel` IS NULL OR pi.`collection_channel` = '');
