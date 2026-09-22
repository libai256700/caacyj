-- ============================================
-- Script type: ddl
-- Description: Roll back wrong detail normalization columns and indexes
-- Created at: 2026-06-13 14:30:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_wrong_record_detail
-- Environment: test
-- ============================================

-- Pre-check:
SHOW FULL COLUMNS FROM `yj_user_practice_exercises_wrong_record_detail`;
SHOW INDEX FROM `yj_user_practice_exercises_wrong_record_detail`;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND INDEX_NAME = 'uk_yj_wrong_detail_customer_exercises') > 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` DROP INDEX `uk_yj_wrong_detail_customer_exercises`',
  'SELECT ''index uk_yj_wrong_detail_customer_exercises missing'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND INDEX_NAME = 'idx_yj_wrong_detail_customer_time') > 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` DROP INDEX `idx_yj_wrong_detail_customer_time`',
  'SELECT ''index idx_yj_wrong_detail_customer_time missing'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND COLUMN_NAME = 'latest_wrong_time') > 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` DROP COLUMN `latest_wrong_time`',
  'SELECT ''column latest_wrong_time missing'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND COLUMN_NAME = 'wrong_count') > 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` DROP COLUMN `wrong_count`',
  'SELECT ''column wrong_count missing'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail'
                  AND COLUMN_NAME = 'customer_account_id'
                  AND IS_NULLABLE = 'YES') > 0,
  'ALTER TABLE `yj_user_practice_exercises_wrong_record_detail` DROP COLUMN `customer_account_id`',
  'SELECT ''column customer_account_id missing or is original NOT NULL column'' AS info');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Post-check:
SHOW FULL COLUMNS FROM `yj_user_practice_exercises_wrong_record_detail`;
SHOW INDEX FROM `yj_user_practice_exercises_wrong_record_detail`;
