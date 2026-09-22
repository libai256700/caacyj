-- AI model channel configuration by business scene.
-- Model credentials are data owned by the deployment database; this DDL does
-- not copy any credential from application.yaml into source control.

CREATE TABLE IF NOT EXISTS `yj_ai_model_config` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `scene_code` varchar(64) NOT NULL COMMENT '业务场景编码',
  `scene_name` varchar(128) NOT NULL COMMENT '业务场景名称',
  `channel` varchar(32) NOT NULL COMMENT '模型渠道编码',
  `base_url` varchar(512) NOT NULL COMMENT '模型接口地址',
  `api_key` varchar(1024) NOT NULL COMMENT '模型密钥，仅服务端读取',
  `extra_config` json DEFAULT NULL COMMENT '渠道扩展配置，仅服务端读取',
  `model` varchar(128) NOT NULL COMMENT '模型标识',
  `system_prompt` text COMMENT '系统提示词',
  `temperature` decimal(6,3) DEFAULT NULL COMMENT '温度参数',
  `max_tokens` int DEFAULT NULL COMMENT '最大输出 Token 数',
  `timeout_millis` int NOT NULL DEFAULT 300000 COMMENT '请求超时时间（毫秒）',
  `min_report_length` int DEFAULT NULL COMMENT '报告最小长度',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态：0启用，1停用',
  `sort` int NOT NULL DEFAULT 0 COMMENT '排序值',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yj_ai_model_config_scene_code` (`scene_code`),
  KEY `idx_yj_ai_model_config_status_sort` (`status`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 模型场景配置';

-- Initial scene records are intentionally not inserted here. Populate the
-- active rows from the deployment's existing model configuration, then switch
-- the application to database-only mode. This prevents credentials from being
-- duplicated in a migration script.
