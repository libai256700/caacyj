-- 版本：vphase1-initial-delivery
-- 目标：补齐企业审核主表与企业前端登录账号的关联字段
-- 数据库：MySQL 8.x
-- 执行说明：脚本幂等，可重复执行

DROP PROCEDURE IF EXISTS `add_yj_audit_column_if_missing`;
DELIMITER $$
CREATE PROCEDURE `add_yj_audit_column_if_missing`(
  IN p_table_name varchar(64),
  IN p_column_name varchar(64),
  IN p_column_definition varchar(1000)
)
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = p_table_name
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = p_table_name
      AND column_name = p_column_name
  ) THEN
    SET @ddl_sql = CONCAT('ALTER TABLE `', p_table_name, '` ADD COLUMN ', p_column_definition);
    PREPARE ddl_stmt FROM @ddl_sql;
    EXECUTE ddl_stmt;
    DEALLOCATE PREPARE ddl_stmt;
  END IF;
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS `add_yj_audit_index_if_missing`;
DELIMITER $$
CREATE PROCEDURE `add_yj_audit_index_if_missing`(
  IN p_table_name varchar(64),
  IN p_index_name varchar(64),
  IN p_index_definition varchar(1000)
)
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = p_table_name
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = p_table_name
      AND index_name = p_index_name
  ) THEN
    SET @ddl_sql = CONCAT('ALTER TABLE `', p_table_name, '` ADD ', p_index_definition);
    PREPARE ddl_stmt FROM @ddl_sql;
    EXECUTE ddl_stmt;
    DEALLOCATE PREPARE ddl_stmt;
  END IF;
END$$
DELIMITER ;

CALL add_yj_audit_column_if_missing(
  'yj_audit_info',
  'company_account_front_id',
  '`company_account_front_id` bigint DEFAULT NULL COMMENT ''企业前端登录账号ID'' AFTER `user_id`'
);

CALL add_yj_audit_index_if_missing(
  'yj_audit_info',
  'idx_yj_audit_info_company_account_front_id',
  'KEY `idx_yj_audit_info_company_account_front_id` (`company_account_front_id`)'
);

DROP PROCEDURE IF EXISTS `add_yj_audit_column_if_missing`;
DROP PROCEDURE IF EXISTS `add_yj_audit_index_if_missing`;
