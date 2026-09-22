-- ============================================
-- Script type: ddl
-- Description: Create user practice wrong record detail table
-- Created at: 2026-06-13 13:00:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_wrong_record_detail
-- Environment: test
-- ============================================

-- Pre-check:
SELECT COUNT(1) AS existing_table_count
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail';

CREATE TABLE IF NOT EXISTS `yj_user_practice_exercises_wrong_record_detail` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'wrong record id',
  `customer_account_id` bigint NOT NULL COMMENT 'customer account id',
  `record_detail_id` bigint NOT NULL COMMENT 'practice record detail id',
  `exercises` bigint NOT NULL COMMENT 'exercise id',
  `answer_code` varchar(20) DEFAULT NULL COMMENT 'selected answer codes separated by |',
  `correct_answer_code` varchar(20) DEFAULT NULL COMMENT 'correct answer codes separated by |',
  `wrong_count` int NOT NULL DEFAULT 1 COMMENT 'wrong answer count',
  `latest_wrong_time` datetime DEFAULT NULL COMMENT 'latest wrong answer time',
  `creator` varchar(64) DEFAULT '' COMMENT 'creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'tenant id',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yj_wrong_detail_customer_exercises` (`tenant_id`, `customer_account_id`, `exercises`),
  KEY `idx_record_detail_id` (`record_detail_id`),
  KEY `idx_exercises` (`exercises`),
  KEY `idx_yj_wrong_detail_customer_time` (`tenant_id`, `customer_account_id`, `latest_wrong_time`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='user practice wrong record detail';

-- Post-check:
SELECT TABLE_NAME, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_user_practice_exercises_wrong_record_detail';

SHOW FULL COLUMNS FROM `yj_user_practice_exercises_wrong_record_detail`;
