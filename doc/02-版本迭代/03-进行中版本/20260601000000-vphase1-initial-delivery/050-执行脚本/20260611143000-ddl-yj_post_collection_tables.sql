-- ============================================
-- 脚本类型：ddl
-- 脚本描述：补齐招聘岗位 yj_post 与岗位采集任务 yj_post_collection_task 表结构
-- 创建日期：2026-06-11 14:30:00
-- 作者：Codex
-- 影响范围：yj_post、yj_post_collection_task；兼容历史 yj_collection_task 数据迁移
-- 执行环境：测试环境/生产环境
-- ============================================

-- 前置检查：确认当前库中招聘岗位与采集任务表状态
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('yj_post', 'yj_post_collection_task', 'yj_collection_task');

-- 主要变更 SQL：岗位表
CREATE TABLE IF NOT EXISTS `yj_post` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '采集岗位编号',
  `name` varchar(100) NOT NULL COMMENT '采集岗位名称',
  `company_id` bigint DEFAULT NULL COMMENT '所属企业编号',
  `company_name` varchar(100) DEFAULT NULL COMMENT '企业名称',
  `source_code` varchar(20) DEFAULT NULL COMMENT '所属来源',
  `external_post_id` varchar(100) DEFAULT NULL COMMENT '外部岗位标识',
  `salary_range` varchar(100) DEFAULT NULL COMMENT '薪资范围',
  `work_area` varchar(100) DEFAULT NULL COMMENT '工作区域',
  `publish_date` varchar(20) DEFAULT NULL COMMENT '发布时间',
  `detail_url` varchar(500) DEFAULT NULL COMMENT '岗位详情地址',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '是否启用',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  KEY `idx_yj_post_name` (`name`),
  KEY `idx_yj_post_company_id` (`company_id`),
  KEY `idx_yj_post_source_external` (`source_code`, `external_post_id`),
  KEY `idx_yj_post_fallback_dedup` (`source_code`, `name`, `company_name`, `work_area`),
  KEY `idx_yj_post_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位采集表';

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'company_name') = 0,
  'ALTER TABLE `yj_post` ADD COLUMN `company_name` varchar(100) DEFAULT NULL COMMENT ''企业名称'' AFTER `company_id`',
  'SELECT ''skip yj_post.company_name''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'external_post_id') = 0,
  'ALTER TABLE `yj_post` ADD COLUMN `external_post_id` varchar(100) DEFAULT NULL COMMENT ''外部岗位标识'' AFTER `source_code`',
  'SELECT ''skip yj_post.external_post_id''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'detail_url') = 0,
  'ALTER TABLE `yj_post` ADD COLUMN `detail_url` varchar(500) DEFAULT NULL COMMENT ''岗位详情地址'' AFTER `publish_date`',
  'SELECT ''skip yj_post.detail_url''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'deleted_time') = 0,
  'ALTER TABLE `yj_post` ADD COLUMN `deleted_time` datetime DEFAULT NULL COMMENT ''删除时间'' AFTER `deleted`',
  'SELECT ''skip yj_post.deleted_time''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post' AND INDEX_NAME = 'idx_yj_post_source_external') = 0,
  'ALTER TABLE `yj_post` ADD INDEX `idx_yj_post_source_external` (`source_code`, `external_post_id`)',
  'SELECT ''skip idx_yj_post_source_external''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post' AND INDEX_NAME = 'idx_yj_post_fallback_dedup') = 0,
  'ALTER TABLE `yj_post` ADD INDEX `idx_yj_post_fallback_dedup` (`source_code`, `name`, `company_name`, `work_area`)',
  'SELECT ''skip idx_yj_post_fallback_dedup''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 主要变更 SQL：采集任务表，统一使用 yj_post_collection_task
CREATE TABLE IF NOT EXISTS `yj_post_collection_task` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '采集任务编号',
  `name` varchar(255) NOT NULL COMMENT '任务名称',
  `collection_channel` varchar(20) DEFAULT NULL COMMENT '采集渠道',
  `collection_time` datetime DEFAULT NULL COMMENT '采集时间，频次规则按其中的日期/星期/时间解释',
  `collection_count_rule` int DEFAULT NULL COMMENT '采集频次：1每天、2每周、3每月',
  `collection_key` varchar(100) DEFAULT NULL COMMENT '采集关键词',
  `collection_num` int NOT NULL DEFAULT 0 COMMENT '采集量级',
  `last_execute_time` datetime DEFAULT NULL COMMENT '最近执行时间',
  `last_execute_result` varchar(500) DEFAULT NULL COMMENT '最近执行结果',
  `last_execute_status` tinyint DEFAULT NULL COMMENT '最近执行状态：1成功、2失败',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '是否启用',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  KEY `idx_yj_post_collection_task_name` (`name`),
  KEY `idx_yj_post_collection_task_channel` (`collection_channel`),
  KEY `idx_yj_post_collection_task_due` (`status`, `collection_count_rule`, `collection_time`, `last_execute_time`),
  KEY `idx_yj_post_collection_task_tenant` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位采集任务表';

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post_collection_task' AND COLUMN_NAME = 'last_execute_status') = 0,
  'ALTER TABLE `yj_post_collection_task` ADD COLUMN `last_execute_status` tinyint DEFAULT NULL COMMENT ''最近执行状态：1成功、2失败'' AFTER `last_execute_result`',
  'SELECT ''skip yj_post_collection_task.last_execute_status''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post_collection_task' AND COLUMN_NAME = 'deleted_time') = 0,
  'ALTER TABLE `yj_post_collection_task` ADD COLUMN `deleted_time` datetime DEFAULT NULL COMMENT ''删除时间'' AFTER `deleted`',
  'SELECT ''skip yj_post_collection_task.deleted_time''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post_collection_task' AND COLUMN_NAME = 'collection_time') = 'date',
  'ALTER TABLE `yj_post_collection_task` MODIFY COLUMN `collection_time` datetime DEFAULT NULL COMMENT ''采集时间，频次规则按其中的日期/星期/时间解释''',
  'SELECT ''skip yj_post_collection_task.collection_time type''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF((SELECT COUNT(1) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_post_collection_task' AND INDEX_NAME = 'idx_yj_post_collection_task_due') = 0,
  'ALTER TABLE `yj_post_collection_task` ADD INDEX `idx_yj_post_collection_task_due` (`status`, `collection_count_rule`, `collection_time`, `last_execute_time`)',
  'SELECT ''skip idx_yj_post_collection_task_due''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 兼容迁移：如果历史库已存在 yj_collection_task，则复制到新表；新代码不再访问旧表。
SET @ddl := IF((SELECT COUNT(1) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'yj_collection_task') > 0,
  'INSERT INTO `yj_post_collection_task` (`id`, `name`, `collection_channel`, `collection_time`, `collection_count_rule`, `collection_key`, `collection_num`, `last_execute_time`, `last_execute_result`, `status`, `tenant_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`) SELECT `id`, `name`, `collection_channel`, CAST(`collection_time` AS datetime), `collection_count_rule`, `collection_key`, `collection_num`, `last_execute_time`, `last_execute_result`, `status`, `tenant_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted` FROM `yj_collection_task` old_task WHERE NOT EXISTS (SELECT 1 FROM `yj_post_collection_task` new_task WHERE new_task.id = old_task.id)',
  'SELECT ''skip yj_collection_task migration''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 后置校验：两张目标表必须存在，关键列与索引必须存在。
SELECT TABLE_NAME, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('yj_post', 'yj_post_collection_task');

SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('yj_post', 'yj_post_collection_task')
  AND COLUMN_NAME IN ('company_name', 'external_post_id', 'detail_url', 'collection_time', 'last_execute_status')
ORDER BY TABLE_NAME, COLUMN_NAME;

SELECT TABLE_NAME, INDEX_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('yj_post', 'yj_post_collection_task')
  AND INDEX_NAME IN ('idx_yj_post_source_external', 'idx_yj_post_fallback_dedup', 'idx_yj_post_collection_task_due')
GROUP BY TABLE_NAME, INDEX_NAME;

-- 回滚方案：
-- 1. 如本脚本尚未进入正式使用，可执行 DROP TABLE IF EXISTS `yj_post_collection_task`;
-- 2. yj_post 已有业务数据时不建议直接删表；如需回滚新增字段，应先确认字段数据未被使用，再按字段逐一 DROP COLUMN；
-- 3. 历史 yj_collection_task 未被删除，必要时可临时把应用配置回旧版本后继续读取旧表。
