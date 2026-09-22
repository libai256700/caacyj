-- 版本：vphase1-initial-delivery
-- 目标：新增 APP 学员端独立账号体系表，并补齐学员业务记录到学员账号表的关联字段
-- 数据库：MySQL 8.x
-- 执行说明：脚本幂等，可重复执行；只创建/补充 APP 学员账号相关结构，不复用后台管理用户表。

CREATE TABLE IF NOT EXISTS `yj_customer_account` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '学员账号编号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `username` varchar(100) NOT NULL COMMENT '用户名',
  `mobile` varchar(30) NOT NULL COMMENT '手机号码',
  `password_salt` varchar(64) NOT NULL DEFAULT '' COMMENT '密码盐',
  `password` varchar(100) NOT NULL COMMENT '密码摘要',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '是否启用',
  `audit_status` bit(1) NOT NULL DEFAULT b'1' COMMENT '是否通过审核',
  `password_initialized_at` datetime DEFAULT NULL COMMENT '密码初始化时间',
  `last_login_at` datetime DEFAULT NULL COMMENT '最近登录时间',
  `last_login_channel` varchar(32) DEFAULT NULL COMMENT '最近登录渠道',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yj_customer_account_mobile` (`mobile`, `deleted`),
  KEY `idx_yj_customer_account_username` (`username`),
  KEY `idx_yj_customer_account_tenant_id` (`tenant_id`),
  KEY `idx_yj_customer_account_status` (`status`, `audit_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='APP学员登录账号';

CREATE TABLE IF NOT EXISTS `yj_customer_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '学员信息编号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `customer_account_id` bigint NOT NULL COMMENT '学员账号编号',
  `nick_name` varchar(100) NOT NULL DEFAULT '' COMMENT '学员昵称',
  `real_name` varchar(100) DEFAULT NULL COMMENT '学员姓名',
  `sex` varchar(10) DEFAULT NULL COMMENT '性别',
  `mobile_phone` varchar(30) DEFAULT NULL COMMENT '手机号码',
  `email` varchar(100) DEFAULT NULL COMMENT '邮箱',
  `avatar_url` varchar(500) DEFAULT NULL COMMENT '头像地址',
  `student_no` varchar(64) DEFAULT NULL COMMENT '学员编号',
  `school_name` varchar(100) DEFAULT NULL COMMENT '学校名称',
  `major_name` varchar(100) DEFAULT NULL COMMENT '专业名称',
  `role_label` varchar(64) DEFAULT NULL COMMENT '角色标签',
  `training_direction` varchar(100) DEFAULT NULL COMMENT '训练方向',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yj_customer_info_account` (`customer_account_id`, `deleted`),
  KEY `idx_yj_customer_info_mobile` (`mobile_phone`),
  KEY `idx_yj_customer_info_student_no` (`student_no`),
  KEY `idx_yj_customer_info_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='APP学员基础信息';

CREATE TABLE IF NOT EXISTS `yj_company_account_front` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '组织前端编号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '所属公司租户编号',
  `username` varchar(100) NOT NULL COMMENT '用户名',
  `password` varchar(100) NOT NULL COMMENT '密码摘要',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '是否启用',
  `audit_status` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否通过审核',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yj_company_account_front_username` (`username`, `deleted`),
  KEY `idx_yj_company_account_front_tenant_id` (`tenant_id`),
  KEY `idx_yj_company_account_front_status` (`status`, `audit_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='APP组织前端登录账号';

DROP PROCEDURE IF EXISTS `add_yj_customer_column_if_missing`;
DELIMITER $$
CREATE PROCEDURE `add_yj_customer_column_if_missing`(
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

DROP PROCEDURE IF EXISTS `add_yj_customer_index_if_missing`;
DELIMITER $$
CREATE PROCEDURE `add_yj_customer_index_if_missing`(
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

CALL add_yj_customer_column_if_missing('yj_student_audit_info', 'customer_account_id', '`customer_account_id` bigint DEFAULT NULL COMMENT ''学员账号编号'' AFTER `user_id`');
CALL add_yj_customer_index_if_missing('yj_student_audit_info', 'idx_yj_student_audit_customer_account_id', 'KEY `idx_yj_student_audit_customer_account_id` (`customer_account_id`)');

CALL add_yj_customer_column_if_missing('yj_audit_info_attachment', 'company_account_front_id', '`company_account_front_id` bigint DEFAULT NULL COMMENT ''企业前端登录账号ID'' AFTER `user_id`');
CALL add_yj_customer_index_if_missing('yj_audit_info_attachment', 'idx_yj_audit_attachment_company_account_front_id', 'KEY `idx_yj_audit_attachment_company_account_front_id` (`company_account_front_id`)');

CALL add_yj_customer_column_if_missing('yj_user_practice_exercises_record', 'customer_account_id', '`customer_account_id` bigint DEFAULT NULL COMMENT ''学员账号编号'' AFTER `user_id`');
CALL add_yj_customer_index_if_missing('yj_user_practice_exercises_record', 'idx_yj_practice_record_customer_account_id', 'KEY `idx_yj_practice_record_customer_account_id` (`customer_account_id`)');

CALL add_yj_customer_column_if_missing('yj_assessment_result', 'customer_account_id', '`customer_account_id` bigint DEFAULT NULL COMMENT ''学员账号编号'' AFTER `user_id`');
CALL add_yj_customer_index_if_missing('yj_assessment_result', 'idx_yj_assessment_result_customer_account_id', 'KEY `idx_yj_assessment_result_customer_account_id` (`customer_account_id`)');

DROP PROCEDURE IF EXISTS `add_yj_customer_column_if_missing`;
DROP PROCEDURE IF EXISTS `add_yj_customer_index_if_missing`;
