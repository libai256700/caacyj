-- ============================================
-- Script type: ddl
-- Description: Add credit_code and legal_person_id to enterprise audit table
-- Created at: 2026-06-15 19:00:00
-- Author: Codex
-- Scope: yj_audit_info
-- Environment: test
-- ============================================

SET @schema_name := DATABASE();

-- Pre-check
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = @schema_name
  AND TABLE_NAME = 'yj_audit_info';

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @schema_name
  AND TABLE_NAME = 'yj_audit_info'
  AND COLUMN_NAME IN ('credit_code', 'legal_person_id');

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_audit_info` ADD COLUMN `credit_code` varchar(30) DEFAULT NULL COMMENT ''统一社会信用代码'' AFTER `name`',
    'SELECT ''yj_audit_info.credit_code already exists''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_audit_info' AND COLUMN_NAME = 'credit_code'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_audit_info` ADD COLUMN `legal_person_id` varchar(30) DEFAULT NULL COMMENT ''法人身份证号'' AFTER `legal_person`',
    'SELECT ''yj_audit_info.legal_person_id already exists''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_audit_info' AND COLUMN_NAME = 'legal_person_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Post-check
SHOW FULL COLUMNS FROM `yj_audit_info`;
