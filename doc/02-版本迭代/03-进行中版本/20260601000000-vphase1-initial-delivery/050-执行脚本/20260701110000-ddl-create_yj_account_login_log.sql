-- ============================================
-- 脚本类型：ddl
-- 脚本描述：新增学员账号登录与知识图谱调用日志表
-- 创建日期：2026-07-01 11:00:00
-- 作者：Codex
-- 影响范围：yj_account_login_log
-- 执行环境：测试环境/生产环境
-- ============================================

-- 前置检查
SELECT COUNT(1) AS before_table_count
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'yj_account_login_log';

-- 主要变更 SQL
CREATE TABLE IF NOT EXISTS `yj_account_login_log` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '日志编号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `customer_account_id` bigint NOT NULL COMMENT '学员账号编号',
  `type` int NOT NULL COMMENT '日志类型：0登录/10知识图谱调用',
  `operator_time` varchar(30) NOT NULL COMMENT '操作时间，格式 yyyy-MM-dd HH:mm:ss',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_customer_account_type_time` (`customer_account_id`, `type`, `operator_time`),
  KEY `idx_type_operator_time` (`type`, `operator_time`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学员账号登录与调用日志';

DROP PROCEDURE IF EXISTS `add_yj_account_login_log_index_if_missing`;
DELIMITER $$
CREATE PROCEDURE `add_yj_account_login_log_index_if_missing`(
  IN p_index_name varchar(64),
  IN p_index_definition varchar(1000)
)
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'yj_account_login_log'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'yj_account_login_log'
      AND index_name = p_index_name
  ) THEN
    SET @ddl_sql = CONCAT('ALTER TABLE `yj_account_login_log` ADD ', p_index_definition);
    PREPARE ddl_stmt FROM @ddl_sql;
    EXECUTE ddl_stmt;
    DEALLOCATE PREPARE ddl_stmt;
  END IF;
END$$
DELIMITER ;

CALL add_yj_account_login_log_index_if_missing(
  'idx_customer_account_type_time',
  'KEY `idx_customer_account_type_time` (`customer_account_id`, `type`, `operator_time`)'
);

CALL add_yj_account_login_log_index_if_missing(
  'idx_type_operator_time',
  'KEY `idx_type_operator_time` (`type`, `operator_time`)'
);

CALL add_yj_account_login_log_index_if_missing(
  'idx_tenant_id',
  'KEY `idx_tenant_id` (`tenant_id`)'
);

DROP PROCEDURE IF EXISTS `add_yj_account_login_log_index_if_missing`;

-- 后置校验
SELECT table_name, table_comment
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'yj_account_login_log';

SELECT column_name, column_type, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'yj_account_login_log'
ORDER BY ordinal_position;

SELECT index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'yj_account_login_log'
GROUP BY index_name
ORDER BY index_name;

-- 回滚方案
-- DROP TABLE IF EXISTS `yj_account_login_log`;
