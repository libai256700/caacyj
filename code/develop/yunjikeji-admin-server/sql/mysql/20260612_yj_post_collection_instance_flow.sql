-- Post collection instance flow schema update
-- Scope: test database yunjikeji
-- Idempotency: guarded by information_schema checks where ALTER TABLE is conditional.

SET @schema_name := DATABASE();

SET @sql := (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE `yj_post` DROP COLUMN `tenant_id`',
    'SELECT ''yj_post.tenant_id already absent''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'tenant_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE `yj_post` DROP COLUMN `company_id`',
    'SELECT ''yj_post.company_id already absent''')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post' AND COLUMN_NAME = 'company_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS `yj_post_collection_task_instance` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '任务实例编号',
  `stauts` int DEFAULT 0 COMMENT '任务状态：0保存，1进行中，2成功未合入，3成功已合入，4失败',
  `task_id` bigint NOT NULL COMMENT '对应任务编号',
  `collection_count` int DEFAULT 0 COMMENT '采集条数',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_post_collection_task_instance_task_id` (`task_id`),
  KEY `idx_yj_post_collection_task_instance_stauts` (`stauts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位采集任务实例表';

CREATE TABLE IF NOT EXISTS `yj_post_instance` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '采集岗位实例编号',
  `task_instance_id` bigint NOT NULL COMMENT '岗位采集任务实例ID',
  `name` varchar(100) NOT NULL COMMENT '采集岗位名称',
  `company_name` varchar(100) DEFAULT NULL COMMENT '企业名称',
  `source_code` varchar(20) DEFAULT NULL COMMENT '所属来源',
  `external_post_id` varchar(100) DEFAULT NULL COMMENT '外部岗位标识',
  `salary_range` varchar(100) DEFAULT NULL COMMENT '薪资范围',
  `work_area` varchar(100) DEFAULT NULL COMMENT '工作区域',
  `publish_date` varchar(20) DEFAULT NULL COMMENT '发布时间',
  `detail_url` varchar(500) DEFAULT NULL COMMENT '岗位详情地址',
  `status` bit(1) DEFAULT b'1' COMMENT '是否启用',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_post_instance_task_instance_id` (`task_instance_id`),
  KEY `idx_yj_post_instance_dedupe` (`name`, `company_name`, `salary_range`, `work_area`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位采集表实例';

SET @sql := (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `yj_post` ADD INDEX `idx_yj_post_dedupe` (`name`, `company_name`, `salary_range`, `work_area`)',
    'SELECT ''idx_yj_post_dedupe already exists''')
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'yj_post' AND INDEX_NAME = 'idx_yj_post_dedupe'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
