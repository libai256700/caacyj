-- ============================================
-- 脚本类型：ddl
-- 脚本描述：只读校验自测报告状态迁移结果
-- 创建日期：2026-08-19 12:02:00
-- 作者：Codex
-- 影响范围：yj_assessment_result 及状态迁移快照表
-- 执行环境：测试环境 / 生产环境（只读）
-- ============================================

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

SET @meta_table_exists := (
  SELECT COUNT(1)
  FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'bak_20260819_yj_assessment_result_status_meta'
);
SET @meta_sql := IF(@meta_table_exists > 0,
  'SELECT `snapshot_label`, CAST(`had_report_status` AS UNSIGNED) AS had_report_status, CAST(`had_failure_reason` AS UNSIGNED) AS had_failure_reason, CAST(`had_report_status_index` AS UNSIGNED) AS had_report_status_index, `snapshot_time` FROM `bak_20260819_yj_assessment_result_status_meta` WHERE `snapshot_label` = ''20260819120000-ddl-add_yj_assessment_result_status'' COLLATE utf8mb4_unicode_ci',
  'SELECT ''backup meta table absent; forward migration not executed in current schema'' AS info'
);
PREPARE stmt FROM @meta_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @status_summary_sql := IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'yj_assessment_result'
      AND COLUMN_NAME = 'report_status'
  ) AND EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'yj_assessment_result'
      AND COLUMN_NAME = 'failure_reason'
  ),
  'SELECT `report_status`, COUNT(1) AS status_count, SUM(CASE WHEN `failure_reason` IS NOT NULL AND `failure_reason` <> '''' THEN 1 ELSE 0 END) AS rows_with_failure_reason FROM `yj_assessment_result` WHERE `deleted` = b''0'' GROUP BY `report_status` ORDER BY `report_status`',
  'SELECT ''report_status/failure_reason missing; forward migration not complete'' AS info'
);
PREPARE stmt FROM @status_summary_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sample_sql := IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'yj_assessment_result'
      AND COLUMN_NAME = 'report_status'
  ) AND EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'yj_assessment_result'
      AND COLUMN_NAME = 'failure_reason'
  ),
  'SELECT `id`, `record_id`, `assessment_time`, `report_status`, `failure_reason`, LEFT(COALESCE(`report_content`, ''''), 80) AS report_preview FROM `yj_assessment_result` WHERE `deleted` = b''0'' ORDER BY `assessment_time` DESC LIMIT 20',
  'SELECT ''sample rows skipped because status columns are absent'' AS info'
);
PREPARE stmt FROM @sample_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
