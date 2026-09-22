-- Rollback for 20260615190000-ddl-add_credit_code_and_legal_person_id_to_yj_audit_info.sql
-- Scope: test database yunjikeji

SET @schema_name := DATABASE();

SET @sql := (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE `yj_audit_info` DROP COLUMN `legal_person_id`',
    'SELECT ''yj_audit_info.legal_person_id already absent''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_audit_info' AND COLUMN_NAME = 'legal_person_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE `yj_audit_info` DROP COLUMN `credit_code`',
    'SELECT ''yj_audit_info.credit_code already absent''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_audit_info' AND COLUMN_NAME = 'credit_code'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
