-- ============================================
-- 脚本类型：ddl
-- 脚本描述：新增消息推送与消息中心四张业务表
-- 创建日期：2026-08-09 12:00:00
-- 作者：Codex
-- 影响范围：yj_push_message、yj_push_recipient、yj_push_device、yj_push_delivery
-- 执行环境：测试环境/生产环境
-- ============================================

-- 前置检查：确认目标表当前是否已存在
SELECT table_name, table_comment
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('yj_push_message', 'yj_push_recipient', 'yj_push_device', 'yj_push_delivery')
ORDER BY table_name;

-- 主要变更 SQL：推送消息主表
CREATE TABLE IF NOT EXISTS `yj_push_message` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '消息ID',
  `message_no` varchar(40) NOT NULL COMMENT '消息业务单号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '创建租户编号',
  `title` varchar(120) NOT NULL COMMENT '消息标题',
  `summary` varchar(255) DEFAULT NULL COMMENT '消息摘要',
  `content` text NOT NULL COMMENT '消息正文',
  `cover_url` varchar(500) DEFAULT NULL COMMENT '封面地址',
  `message_category` varchar(20) NOT NULL DEFAULT 'OPERATION' COMMENT '消息分类：SYSTEM系统/OPERATION运营',
  `send_channel` varchar(20) NOT NULL DEFAULT 'APP_PUSH' COMMENT '发送通道：APP_PUSH仅推送/APP_PUSH_AND_WS推送+站内',
  `target_scope` varchar(20) NOT NULL DEFAULT 'ALL' COMMENT '受众范围：ALL/TENANT/STUDENT/COMPANY/SPECIFIED/TAG',
  `target_snapshot_json` longtext COMMENT '受众快照JSON',
  `route_key` varchar(50) NOT NULL COMMENT '前端路由白名单键',
  `route_params_json` text COMMENT '路由参数JSON',
  `business_type` varchar(50) DEFAULT NULL COMMENT '业务类型',
  `business_id` varchar(64) DEFAULT NULL COMMENT '业务标识',
  `scheduled_time` datetime DEFAULT NULL COMMENT '定时发送时间',
  `published_time` datetime DEFAULT NULL COMMENT '实际发布时间',
  `completed_time` datetime DEFAULT NULL COMMENT '最终完成时间',
  `cancelled_time` datetime DEFAULT NULL COMMENT '取消时间',
  `published_by` varchar(64) DEFAULT '' COMMENT '发布操作人',
  `cancelled_by` varchar(64) DEFAULT '' COMMENT '取消操作人',
  `total_recipient_count` int NOT NULL DEFAULT 0 COMMENT '收件人数',
  `total_device_count` int NOT NULL DEFAULT 0 COMMENT '设备数',
  `accepted_count` int NOT NULL DEFAULT 0 COMMENT '厂商受理数',
  `read_count` int NOT NULL DEFAULT 0 COMMENT '已读人数',
  `open_count` int NOT NULL DEFAULT 0 COMMENT '打开人数',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '消息状态：0草稿/10待发送/20发送中/30全部受理/40部分失败/50失败/60已取消',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_push_message_no` (`message_no`),
  KEY `idx_push_message_tenant_status` (`tenant_id`, `status`),
  KEY `idx_push_message_status_schedule` (`status`, `scheduled_time`),
  KEY `idx_push_message_business` (`business_type`, `business_id`),
  KEY `idx_push_message_published_time` (`published_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='推送消息主表';

-- 主要变更 SQL：消息收件人表
CREATE TABLE IF NOT EXISTS `yj_push_recipient` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '收件记录ID',
  `message_id` bigint NOT NULL COMMENT '消息ID',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '收件账号所属租户',
  `subject_type` varchar(20) NOT NULL COMMENT '主体类型：STUDENT学员/COMPANY企业',
  `subject_id` bigint NOT NULL COMMENT '主体账号ID',
  `display_name` varchar(100) DEFAULT NULL COMMENT '收件人名称快照',
  `mobile_mask` varchar(32) DEFAULT NULL COMMENT '手机号脱敏快照',
  `payload_snapshot_json` text COMMENT '个性化快照JSON',
  `first_accepted_time` datetime DEFAULT NULL COMMENT '首次受理时间',
  `read_time` datetime DEFAULT NULL COMMENT '首次已读时间',
  `open_time` datetime DEFAULT NULL COMMENT '首次打开时间',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '收件状态：0待接收/10已受理/20已读/30已打开/40已撤回',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_push_recipient_message_subject` (`message_id`, `tenant_id`, `subject_type`, `subject_id`),
  KEY `idx_push_recipient_subject` (`tenant_id`, `subject_type`, `subject_id`, `status`),
  KEY `idx_push_recipient_message` (`message_id`),
  KEY `idx_push_recipient_read` (`status`, `read_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息收件人表';

-- 主要变更 SQL：推送设备表
CREATE TABLE IF NOT EXISTS `yj_push_device` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '设备记录ID',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '当前绑定租户',
  `subject_type` varchar(20) NOT NULL COMMENT '主体类型：STUDENT学员/COMPANY企业',
  `subject_id` bigint NOT NULL COMMENT '主体账号ID',
  `client_id` varchar(100) NOT NULL COMMENT '推送客户端标识（clientId）',
  `push_token` varchar(255) DEFAULT NULL COMMENT '厂商 push token 或通道 token',
  `platform` varchar(20) NOT NULL COMMENT '平台：android/ios',
  `manufacturer` varchar(50) DEFAULT NULL COMMENT '厂商名称',
  `device_model` varchar(100) DEFAULT NULL COMMENT '设备型号',
  `app_id` varchar(100) DEFAULT NULL COMMENT '应用标识',
  `app_version` varchar(30) DEFAULT NULL COMMENT 'App版本',
  `os_version` varchar(30) DEFAULT NULL COMMENT '系统版本',
  `rom_channel` varchar(30) DEFAULT NULL COMMENT '厂商通道标识',
  `last_active_time` datetime DEFAULT NULL COMMENT '最近活跃时间',
  `bind_time` datetime DEFAULT NULL COMMENT '首次绑定时间',
  `unbind_time` datetime DEFAULT NULL COMMENT '最近解绑时间',
  `invalid_time` datetime DEFAULT NULL COMMENT '标记失效时间',
  `invalid_reason` varchar(255) DEFAULT NULL COMMENT '失效原因',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '设备状态：0启用/10已解绑/20失效',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_push_device_client_id` (`client_id`),
  KEY `idx_push_device_subject` (`tenant_id`, `subject_type`, `subject_id`, `status`),
  KEY `idx_push_device_status_active` (`status`, `last_active_time`),
  KEY `idx_push_device_platform_status` (`platform`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='推送设备表';

-- 主要变更 SQL：逐设备投递表
CREATE TABLE IF NOT EXISTS `yj_push_delivery` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '投递记录ID',
  `message_id` bigint NOT NULL COMMENT '消息ID',
  `recipient_id` bigint NOT NULL COMMENT '收件记录ID',
  `device_id` bigint NOT NULL COMMENT '设备ID',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `subject_type` varchar(20) NOT NULL COMMENT '主体类型：STUDENT学员/COMPANY企业',
  `subject_id` bigint NOT NULL COMMENT '主体账号ID',
  `provider_code` varchar(30) NOT NULL DEFAULT 'noop' COMMENT '推送通道：noop/mock/unicloud-http',
  `provider_message_id` varchar(100) DEFAULT NULL COMMENT '云函数返回的 push 任务标识或厂商消息ID',
  `provider_request_id` varchar(100) DEFAULT NULL COMMENT 'Java 调云函数请求追踪ID',
  `payload_snapshot_json` text COMMENT '下发payload快照JSON',
  `attempt_log_json` longtext COMMENT '每次投递尝试审计日志JSON，至少记录 attemptNo/providerCode/providerRequestId/requestTime/responseTime/resultStatus/failureCode/failureMessage',
  `attempt_count` int NOT NULL DEFAULT 0 COMMENT '已尝试次数',
  `max_attempt_count` int NOT NULL DEFAULT 3 COMMENT '最大重试次数',
  `next_retry_time` datetime DEFAULT NULL COMMENT '下次重试时间',
  `last_attempt_time` datetime DEFAULT NULL COMMENT '最近尝试时间',
  `accepted_time` datetime DEFAULT NULL COMMENT '厂商受理时间',
  `delivered_time` datetime DEFAULT NULL COMMENT '厂商送达回执时间',
  `failure_code` varchar(64) DEFAULT NULL COMMENT '厂商失败码；Noop 固定为 NOOP_PROVIDER_DISABLED',
  `failure_message` varchar(255) DEFAULT NULL COMMENT '厂商失败描述；Noop 写明缺失配置项',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '投递状态：0待投递/10投递中/20已受理/30已送达回执/40失败/50已取消',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_push_delivery_message_device` (`message_id`, `device_id`),
  KEY `idx_push_delivery_status_retry` (`status`, `next_retry_time`),
  KEY `idx_push_delivery_recipient` (`recipient_id`, `status`),
  KEY `idx_push_delivery_provider` (`provider_code`, `provider_request_id`),
  KEY `idx_push_delivery_message` (`message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='逐设备投递表';

-- 幂等补齐：已存在旧表时，同步字段定义、注释与新增字段
ALTER TABLE `yj_push_device`
  MODIFY COLUMN `client_id` varchar(100) NOT NULL COMMENT '推送客户端标识（clientId）',
  MODIFY COLUMN `push_token` varchar(255) DEFAULT NULL COMMENT '厂商 push token 或通道 token';

ALTER TABLE `yj_push_delivery`
  MODIFY COLUMN `provider_code` varchar(30) NOT NULL DEFAULT 'noop' COMMENT '推送通道：noop/mock/unicloud-http',
  MODIFY COLUMN `provider_message_id` varchar(100) DEFAULT NULL COMMENT '云函数返回的 push 任务标识或厂商消息ID',
  MODIFY COLUMN `provider_request_id` varchar(100) DEFAULT NULL COMMENT 'Java 调云函数请求追踪ID',
  MODIFY COLUMN `failure_code` varchar(64) DEFAULT NULL COMMENT '厂商失败码；Noop 固定为 NOOP_PROVIDER_DISABLED',
  MODIFY COLUMN `failure_message` varchar(255) DEFAULT NULL COMMENT '厂商失败描述；Noop 写明缺失配置项';

DROP PROCEDURE IF EXISTS `add_notification_index_if_missing`;
DROP PROCEDURE IF EXISTS `add_notification_column_if_missing`;
DELIMITER $$
CREATE PROCEDURE `add_notification_index_if_missing`(
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
CREATE PROCEDURE `add_notification_column_if_missing`(
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

CALL add_notification_column_if_missing(
  'yj_push_delivery',
  'attempt_log_json',
  '`attempt_log_json` longtext COMMENT ''每次投递尝试审计日志JSON，至少记录 attemptNo/providerCode/providerRequestId/requestTime/responseTime/resultStatus/failureCode/failureMessage'' AFTER `payload_snapshot_json`'
);

CALL add_notification_index_if_missing(
  'yj_push_message',
  'uk_push_message_no',
  'UNIQUE KEY `uk_push_message_no` (`message_no`)'
);
CALL add_notification_index_if_missing(
  'yj_push_message',
  'idx_push_message_tenant_status',
  'KEY `idx_push_message_tenant_status` (`tenant_id`, `status`)'
);
CALL add_notification_index_if_missing(
  'yj_push_message',
  'idx_push_message_status_schedule',
  'KEY `idx_push_message_status_schedule` (`status`, `scheduled_time`)'
);
CALL add_notification_index_if_missing(
  'yj_push_message',
  'idx_push_message_business',
  'KEY `idx_push_message_business` (`business_type`, `business_id`)'
);
CALL add_notification_index_if_missing(
  'yj_push_message',
  'idx_push_message_published_time',
  'KEY `idx_push_message_published_time` (`published_time`)'
);

CALL add_notification_index_if_missing(
  'yj_push_recipient',
  'uk_push_recipient_message_subject',
  'UNIQUE KEY `uk_push_recipient_message_subject` (`message_id`, `tenant_id`, `subject_type`, `subject_id`)'
);
CALL add_notification_index_if_missing(
  'yj_push_recipient',
  'idx_push_recipient_subject',
  'KEY `idx_push_recipient_subject` (`tenant_id`, `subject_type`, `subject_id`, `status`)'
);
CALL add_notification_index_if_missing(
  'yj_push_recipient',
  'idx_push_recipient_message',
  'KEY `idx_push_recipient_message` (`message_id`)'
);
CALL add_notification_index_if_missing(
  'yj_push_recipient',
  'idx_push_recipient_read',
  'KEY `idx_push_recipient_read` (`status`, `read_time`)'
);

CALL add_notification_index_if_missing(
  'yj_push_device',
  'uk_push_device_client_id',
  'UNIQUE KEY `uk_push_device_client_id` (`client_id`)'
);
CALL add_notification_index_if_missing(
  'yj_push_device',
  'idx_push_device_subject',
  'KEY `idx_push_device_subject` (`tenant_id`, `subject_type`, `subject_id`, `status`)'
);
CALL add_notification_index_if_missing(
  'yj_push_device',
  'idx_push_device_status_active',
  'KEY `idx_push_device_status_active` (`status`, `last_active_time`)'
);
CALL add_notification_index_if_missing(
  'yj_push_device',
  'idx_push_device_platform_status',
  'KEY `idx_push_device_platform_status` (`platform`, `status`)'
);

CALL add_notification_index_if_missing(
  'yj_push_delivery',
  'uk_push_delivery_message_device',
  'UNIQUE KEY `uk_push_delivery_message_device` (`message_id`, `device_id`)'
);
CALL add_notification_index_if_missing(
  'yj_push_delivery',
  'idx_push_delivery_status_retry',
  'KEY `idx_push_delivery_status_retry` (`status`, `next_retry_time`)'
);
CALL add_notification_index_if_missing(
  'yj_push_delivery',
  'idx_push_delivery_recipient',
  'KEY `idx_push_delivery_recipient` (`recipient_id`, `status`)'
);
CALL add_notification_index_if_missing(
  'yj_push_delivery',
  'idx_push_delivery_provider',
  'KEY `idx_push_delivery_provider` (`provider_code`, `provider_request_id`)'
);
CALL add_notification_index_if_missing(
  'yj_push_delivery',
  'idx_push_delivery_message',
  'KEY `idx_push_delivery_message` (`message_id`)'
);

DROP PROCEDURE IF EXISTS `add_notification_index_if_missing`;
DROP PROCEDURE IF EXISTS `add_notification_column_if_missing`;

-- 后置校验：目标表、关键字段、关键索引必须存在
SELECT table_name, table_comment
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('yj_push_message', 'yj_push_recipient', 'yj_push_device', 'yj_push_delivery')
ORDER BY table_name;

SELECT table_name, column_name, column_type, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name IN ('yj_push_message', 'yj_push_recipient', 'yj_push_device', 'yj_push_delivery')
ORDER BY table_name, ordinal_position;

SELECT table_name, column_name, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND (
    (table_name = 'yj_push_device' AND column_name IN ('client_id', 'push_token'))
    OR
    (table_name = 'yj_push_delivery' AND column_name IN ('provider_code', 'provider_message_id', 'provider_request_id', 'attempt_log_json', 'failure_code', 'failure_message'))
  )
ORDER BY table_name, ordinal_position;

SELECT table_name, index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN ('yj_push_message', 'yj_push_recipient', 'yj_push_device', 'yj_push_delivery')
GROUP BY table_name, index_name
ORDER BY table_name, index_name;

-- 回滚方案
-- 1. 若四张表尚未产生正式业务数据，可按依赖顺序执行：
--    DROP TABLE IF EXISTS `yj_push_delivery`;
--    DROP TABLE IF EXISTS `yj_push_device`;
--    DROP TABLE IF EXISTS `yj_push_recipient`;
--    DROP TABLE IF EXISTS `yj_push_message`;
-- 2. 若仅需回退本次字段补齐且表已存在历史数据，可先备份后执行：
--    ALTER TABLE `yj_push_delivery` DROP COLUMN `attempt_log_json`;
--    ALTER TABLE `yj_push_delivery`
--      MODIFY COLUMN `provider_code` varchar(30) NOT NULL DEFAULT 'noop' COMMENT '推送通道：noop/mock/unipush',
--      MODIFY COLUMN `provider_message_id` varchar(100) DEFAULT NULL COMMENT '厂商消息ID',
--      MODIFY COLUMN `provider_request_id` varchar(100) DEFAULT NULL COMMENT '厂商请求追踪ID',
--      MODIFY COLUMN `failure_code` varchar(64) DEFAULT NULL COMMENT '厂商失败码',
--      MODIFY COLUMN `failure_message` varchar(255) DEFAULT NULL COMMENT '厂商失败描述';
--    ALTER TABLE `yj_push_device`
--      MODIFY COLUMN `client_id` varchar(100) NOT NULL COMMENT 'UniPush客户端标识',
--      MODIFY COLUMN `push_token` varchar(255) DEFAULT NULL COMMENT '厂商或UniPush token';
-- 3. 若已产生测试或正式数据，回滚前先导出四张表快照，再评估 message_no 与 route_key 相关业务是否已被前端引用。
