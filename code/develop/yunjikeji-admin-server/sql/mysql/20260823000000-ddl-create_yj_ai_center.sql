-- AI assistant conversation history for the center page.
-- This table only stores readable chat history and does not change the existing
-- knowledge-answering flow.

CREATE TABLE IF NOT EXISTS `yj_ai_center` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `name` varchar(255) DEFAULT NULL COMMENT '对话名称',
  `custom_account_id` bigint DEFAULT NULL COMMENT '客户账号编号',
  `from_type` int DEFAULT 1 COMMENT '消息来源：1用户，2AI',
  `content` varchar(5000) DEFAULT NULL COMMENT '消息内容',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_ai_center_account_name_id` (`custom_account_id`, `name`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 中心对话历史';

ALTER TABLE `yj_ai_center`
  MODIFY COLUMN `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键';

SET @idx_exists := (
  SELECT COUNT(1)
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'yj_ai_center'
    AND index_name = 'idx_yj_ai_center_account_name_id'
);
SET @idx_sql := IF(
  @idx_exists = 0,
  'ALTER TABLE `yj_ai_center` ADD KEY `idx_yj_ai_center_account_name_id` (`custom_account_id`, `name`, `id`)',
  'SELECT 1'
);
PREPARE stmt FROM @idx_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
