-- ============================================
-- 脚本类型：ddl
-- 脚本描述：幂等补齐自测报告状态列、执行前快照与后置初始化
-- 创建日期：2026-08-19 12:00:00
-- 作者：Codex
-- 影响范围：yj_assessment_result 及本次状态迁移快照表
-- 执行环境：测试环境 / 生产环境（审批、备份后）
-- ============================================

-- 前置检查：确认目标表与列状态；执行结果需留档。
SELECT
  table_meta.TABLE_NAME AS table_name,
  IF(table_meta.TABLE_NAME IS NULL, 0, 1) AS table_exists,
  IF(report_status_column.COLUMN_NAME IS NULL, 0, 1) AS report_status_exists,
  IF(failure_reason_column.COLUMN_NAME IS NULL, 0, 1) AS failure_reason_exists,
  IF(report_status_index.INDEX_NAME IS NULL, 0, 1) AS report_status_index_exists
FROM information_schema.TABLES table_meta
LEFT JOIN information_schema.COLUMNS report_status_column
  ON report_status_column.TABLE_SCHEMA = DATABASE()
 AND report_status_column.TABLE_NAME = table_meta.TABLE_NAME
 AND report_status_column.COLUMN_NAME = 'report_status'
LEFT JOIN information_schema.COLUMNS failure_reason_column
  ON failure_reason_column.TABLE_SCHEMA = DATABASE()
 AND failure_reason_column.TABLE_NAME = table_meta.TABLE_NAME
 AND failure_reason_column.COLUMN_NAME = 'failure_reason'
LEFT JOIN information_schema.STATISTICS report_status_index
  ON report_status_index.TABLE_SCHEMA = DATABASE()
 AND report_status_index.TABLE_NAME = table_meta.TABLE_NAME
 AND report_status_index.INDEX_NAME = 'idx_yj_assessment_result_report_status'
WHERE table_meta.TABLE_SCHEMA = DATABASE()
  AND table_meta.TABLE_NAME = 'yj_assessment_result';

CREATE TABLE IF NOT EXISTS `bak_20260819_yj_assessment_result_status_meta` (
  `snapshot_label` varchar(64) NOT NULL COMMENT '脚本快照标签',
  `had_report_status` bit(1) NOT NULL DEFAULT b'0' COMMENT '执行前是否存在 report_status',
  `had_failure_reason` bit(1) NOT NULL DEFAULT b'0' COMMENT '执行前是否存在 failure_reason',
  `had_report_status_index` bit(1) NOT NULL DEFAULT b'0' COMMENT '执行前是否存在状态索引',
  `snapshot_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '快照时间',
  PRIMARY KEY (`snapshot_label`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自测报告状态迁移元数据快照';

CREATE TABLE IF NOT EXISTS `bak_20260819_yj_assessment_result_status_rows` (
  `snapshot_label` varchar(64) NOT NULL COMMENT '脚本快照标签',
  `assessment_result_id` bigint NOT NULL COMMENT '自测结果编号',
  `report_status` varchar(32) DEFAULT NULL COMMENT '执行前报告状态',
  `failure_reason` varchar(255) DEFAULT NULL COMMENT '执行前失败原因',
  `snapshot_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '快照时间',
  PRIMARY KEY (`snapshot_label`, `assessment_result_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自测报告状态迁移行级快照';

SET @snapshot_label := CAST('20260819120000-ddl-add_yj_assessment_result_status' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci;
SET @report_status_exists := (
  SELECT COUNT(1)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'yj_assessment_result'
    AND COLUMN_NAME = 'report_status'
);
SET @failure_reason_exists := (
  SELECT COUNT(1)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'yj_assessment_result'
    AND COLUMN_NAME = 'failure_reason'
);
SET @report_status_index_exists := (
  SELECT COUNT(1)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'yj_assessment_result'
    AND INDEX_NAME = 'idx_yj_assessment_result_report_status'
);

INSERT INTO `bak_20260819_yj_assessment_result_status_meta` (
  `snapshot_label`,
  `had_report_status`,
  `had_failure_reason`,
  `had_report_status_index`
)
SELECT
  @snapshot_label,
  IF(@report_status_exists > 0, b'1', b'0'),
  IF(@failure_reason_exists > 0, b'1', b'0'),
  IF(@report_status_index_exists > 0, b'1', b'0')
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1
  FROM `bak_20260819_yj_assessment_result_status_meta`
  WHERE `snapshot_label` = @snapshot_label
);

SET @backup_sql := IF(@report_status_exists > 0 AND @failure_reason_exists > 0,
  CONCAT(
    'INSERT INTO `bak_20260819_yj_assessment_result_status_rows` ',
    '(`snapshot_label`, `assessment_result_id`, `report_status`, `failure_reason`) ',
    'SELECT ''', @snapshot_label, ''' COLLATE utf8mb4_unicode_ci, src.`id`, src.`report_status`, src.`failure_reason` ',
    'FROM `yj_assessment_result` src ',
    'WHERE NOT EXISTS (',
    '  SELECT 1 FROM `bak_20260819_yj_assessment_result_status_rows` backup ',
    '  WHERE backup.`snapshot_label` = ''', @snapshot_label, ''' COLLATE utf8mb4_unicode_ci ',
    '    AND backup.`assessment_result_id` = src.`id`',
    ')'
  ),
  'SELECT ''report_status/failure_reason absent before migration; row backup skipped'' AS info'
);
PREPARE stmt FROM @backup_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql := IF(@report_status_exists = 0,
  'ALTER TABLE `yj_assessment_result` ADD COLUMN `report_status` varchar(32) NOT NULL DEFAULT ''SUCCESS'' COMMENT ''报告状态：PENDING/SUCCESS/FAILED'' AFTER `report_content`',
  'SELECT ''report_status already exists'' AS info'
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql := IF(@failure_reason_exists = 0,
  'ALTER TABLE `yj_assessment_result` ADD COLUMN `failure_reason` varchar(255) DEFAULT NULL COMMENT ''报告失败原因'' AFTER `report_status`',
  'SELECT ''failure_reason already exists'' AS info'
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql := IF(@report_status_index_exists = 0,
  'ALTER TABLE `yj_assessment_result` ADD KEY `idx_yj_assessment_result_report_status` (`report_status`)',
  'SELECT ''idx_yj_assessment_result_report_status already exists'' AS info'
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `yj_assessment_result`
SET `report_status` = CASE
      WHEN `report_content` IS NOT NULL AND LENGTH(TRIM(`report_content`)) > 0 THEN 'SUCCESS'
      ELSE 'FAILED'
    END,
    `failure_reason` = CASE
      WHEN `report_content` IS NOT NULL AND LENGTH(TRIM(`report_content`)) > 0 THEN NULL
      ELSE '历史记录缺少完整报告内容'
    END
WHERE `deleted` = b'0'
  AND (
    `report_status` IS NULL
    OR `report_status` = ''
    OR (
      `report_status` = 'SUCCESS'
      AND LENGTH(TRIM(COALESCE(`report_content`, ''))) = 0
      AND (`failure_reason` IS NULL OR `failure_reason` = '' OR `failure_reason` = '历史记录缺少完整报告内容')
    )
  );

-- 后置校验：确认列、索引与历史数据初始化结果。
SELECT
  column_name,
  column_type,
  is_nullable,
  column_default
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_assessment_result'
  AND column_name IN ('report_status', 'failure_reason')
ORDER BY field(column_name, 'report_status', 'failure_reason');

SELECT
  INDEX_NAME,
  GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_assessment_result'
  AND INDEX_NAME = 'idx_yj_assessment_result_report_status'
GROUP BY INDEX_NAME;

SELECT
  `report_status`,
  COUNT(1) AS row_count,
  SUM(CASE WHEN `failure_reason` IS NOT NULL AND `failure_reason` <> '' THEN 1 ELSE 0 END) AS rows_with_failure_reason
FROM `yj_assessment_result`
WHERE `deleted` = b'0'
GROUP BY `report_status`
ORDER BY `report_status`;
