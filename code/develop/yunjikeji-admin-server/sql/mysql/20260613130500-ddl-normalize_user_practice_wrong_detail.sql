-- ============================================
-- Script type: ddl
-- Description: Normalize user practice wrong detail table for per-customer current wrong book state
-- Created at: 2026-06-13 13:05:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_wrong_record_detail
-- Environment: test
-- ============================================

-- Pre-check:
SELECT COUNT(1) AS existing_table_count
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail';

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND COLUMN_NAME = 'customer_account_id') = 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ADD COLUMN `customer_account_id` bigint DEFAULT NULL COMMENT ''customer account id'' AFTER `id`',
  'SELECT ''column customer_account_id already exists'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND COLUMN_NAME = 'wrong_count') = 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ADD COLUMN `wrong_count` int NOT NULL DEFAULT 1 COMMENT ''wrong answer count'' AFTER `correct_answer_code`',
  'SELECT ''column wrong_count already exists'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND COLUMN_NAME = 'latest_wrong_time') = 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ADD COLUMN `latest_wrong_time` datetime DEFAULT NULL COMMENT ''latest wrong answer time'' AFTER `wrong_count`',
  'SELECT ''column latest_wrong_time already exists'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `yj_user_practice_exercises_wrong_record_detail` w
INNER JOIN `yj_user_practice_exercises_record_detail` d ON d.`id` = w.`record_detail_id`
INNER JOIN `yj_user_practice_exercises_record` r ON r.`id` = d.`record_id`
SET w.`customer_account_id` = COALESCE(w.`customer_account_id`, r.`customer_account_id`),
    w.`wrong_count` = GREATEST(IFNULL(w.`wrong_count`, 1), 1),
    w.`latest_wrong_time` = COALESCE(w.`latest_wrong_time`, d.`create_time`, w.`create_time`)
WHERE r.`customer_account_id` IS NOT NULL;

UPDATE `yj_user_practice_exercises_wrong_record_detail`
SET `latest_wrong_time` = COALESCE(`latest_wrong_time`, `create_time`)
WHERE `latest_wrong_time` IS NULL;

DELETE FROM `yj_user_practice_exercises_wrong_record_detail`
WHERE `deleted` = b'1'
  AND `customer_account_id` IS NOT NULL;

DELETE w1
FROM `yj_user_practice_exercises_wrong_record_detail` w1
INNER JOIN `yj_user_practice_exercises_wrong_record_detail` w2
  ON w2.`tenant_id` = w1.`tenant_id`
 AND w2.`customer_account_id` = w1.`customer_account_id`
 AND w2.`exercises` = w1.`exercises`
 AND w2.`deleted` = b'0'
 AND (
   COALESCE(w2.`latest_wrong_time`, w2.`create_time`) > COALESCE(w1.`latest_wrong_time`, w1.`create_time`)
   OR (
     COALESCE(w2.`latest_wrong_time`, w2.`create_time`) = COALESCE(w1.`latest_wrong_time`, w1.`create_time`)
     AND w2.`id` > w1.`id`
   )
 )
WHERE w1.`deleted` = b'0'
  AND w1.`customer_account_id` IS NOT NULL;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND COLUMN_NAME = 'customer_account_id'
                  AND IS_NULLABLE = 'YES') = 1
  AND (SELECT COUNT(1) FROM `yj_user_practice_exercises_wrong_record_detail`
       WHERE `customer_account_id` IS NULL AND `deleted` = b'0') = 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` MODIFY COLUMN `customer_account_id` bigint NOT NULL COMMENT ''customer account id''',
  'SELECT ''skip customer_account_id not null because nullable column missing or null rows remain'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND INDEX_NAME = 'uk_yj_wrong_detail_customer_exercises') = 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ADD UNIQUE KEY `uk_yj_wrong_detail_customer_exercises` (`tenant_id`, `customer_account_id`, `exercises`)',
  'SELECT ''index uk_yj_wrong_detail_customer_exercises already exists'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND INDEX_NAME = 'idx_yj_wrong_detail_customer_time') = 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` ADD KEY `idx_yj_wrong_detail_customer_time` (`tenant_id`, `customer_account_id`, `latest_wrong_time`)',
  'SELECT ''index idx_yj_wrong_detail_customer_time already exists'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Post-check:
SHOW FULL COLUMNS FROM `yj_user_practice_exercises_wrong_record_detail`;

SHOW INDEX FROM `yj_user_practice_exercises_wrong_record_detail`;

SELECT `tenant_id`, `customer_account_id`, `exercises`, COUNT(1) AS duplicate_count
FROM `yj_user_practice_exercises_wrong_record_detail`
WHERE `deleted` = b'0'
GROUP BY `tenant_id`, `customer_account_id`, `exercises`
HAVING COUNT(1) > 1;
