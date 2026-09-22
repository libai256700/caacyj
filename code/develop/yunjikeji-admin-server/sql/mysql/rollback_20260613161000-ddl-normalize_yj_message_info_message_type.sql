-- ============================================
-- Script type: ddl
-- Description: Roll back customer service message_type to numeric codes
-- Created at: 2026-06-13 16:10:00
-- Author: Codex
-- Scope: yj_message_info.message_type
-- Environment: test
-- ============================================

-- Pre-check:
SHOW FULL COLUMNS FROM `yj_message_info`;

UPDATE `yj_message_info`
SET `message_type` = CASE `message_type`
    WHEN 'text' THEN '1'
    WHEN 'image' THEN '2'
    WHEN 'video' THEN '3'
    ELSE `message_type`
END
WHERE `message_type` IN ('text', 'image', 'video');

SET @ddl := IF((SELECT COUNT(1)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_message_info'
                  AND COLUMN_NAME = 'message_type') > 0,
  'ALTER TABLE `yj_message_info` MODIFY COLUMN `message_type` tinyint(4) NOT NULL DEFAULT 1 COMMENT ''message type: 1 text 2 image 3 video''',
  'SELECT ''column message_type missing'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Post-check:
SHOW FULL COLUMNS FROM `yj_message_info`;

SELECT `message_type`, COUNT(1) AS message_count
FROM `yj_message_info`
GROUP BY `message_type`;
