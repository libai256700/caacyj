-- ============================================
-- Script type: ddl
-- Description: Normalize customer service message_type to string codes
-- Created at: 2026-06-13 16:10:00
-- Author: Codex
-- Scope: yj_message_info.message_type
-- Environment: test
-- ============================================

-- Pre-check:
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_message_info';

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_message_info'
  AND COLUMN_NAME = 'message_type';

SET @ddl := IF((SELECT COUNT(1)
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_message_info') = 0,
  'CREATE TABLE `yj_message_info` (
     `id` bigint NOT NULL AUTO_INCREMENT COMMENT ''message id'',
     `session_id` bigint NOT NULL COMMENT ''session id'',
     `message_type` varchar(10) NOT NULL DEFAULT ''text'' COMMENT ''message type: text image video'',
     `session_from` bigint NOT NULL COMMENT ''sender id'',
     `session_to` bigint NOT NULL COMMENT ''receiver id'',
     `content` varchar(4000) NOT NULL DEFAULT '''' COMMENT ''content'',
     `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT ''tenant id'',
     `creator` varchar(64) DEFAULT '''' COMMENT ''creator'',
     `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT ''create time'',
     `updater` varchar(64) DEFAULT '''' COMMENT ''updater'',
     `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT ''update time'',
     `deleted` bit(1) NOT NULL DEFAULT b''0'' COMMENT ''deleted'',
     PRIMARY KEY (`id`),
     KEY `idx_yj_message_info_session` (`tenant_id`, `session_id`, `create_time`),
     KEY `idx_yj_message_info_sender` (`tenant_id`, `session_from`, `create_time`)
   ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT=''customer service messages''',
  'SELECT ''table yj_message_info already exists'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_message_info'
                  AND COLUMN_NAME = 'message_type') = 0,
  'ALTER TABLE `yj_message_info` ADD COLUMN `message_type` varchar(10) NOT NULL DEFAULT ''text'' COMMENT ''message type: text image video'' AFTER `session_id`',
  'SELECT ''column message_type already exists'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_message_info'
                  AND COLUMN_NAME = 'message_type'
                  AND DATA_TYPE = 'varchar'
                  AND CHARACTER_MAXIMUM_LENGTH = 10) = 0,
  'ALTER TABLE `yj_message_info` MODIFY COLUMN `message_type` varchar(10) NOT NULL DEFAULT ''text'' COMMENT ''message type: text image video''',
  'SELECT ''column message_type already normalized'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `yj_message_info`
SET `message_type` = CASE `message_type`
    WHEN '1' THEN 'text'
    WHEN '2' THEN 'image'
    WHEN '3' THEN 'video'
    ELSE `message_type`
END
WHERE `message_type` IN ('1', '2', '3');

UPDATE `yj_message_info`
SET `message_type` = 'text'
WHERE `message_type` IS NULL OR `message_type` = '';

-- Post-check:
SHOW FULL COLUMNS FROM `yj_message_info`;

SELECT `message_type`, COUNT(1) AS message_count
FROM `yj_message_info`
GROUP BY `message_type`;
