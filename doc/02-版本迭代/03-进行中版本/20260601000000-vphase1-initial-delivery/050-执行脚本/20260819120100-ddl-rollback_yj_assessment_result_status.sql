-- ============================================
-- 脚本类型：ddl
-- 脚本描述：回滚自测报告状态迁移并按快照恢复执行前状态
-- 创建日期：2026-08-19 12:01:00
-- 作者：Codex
-- 影响范围：yj_assessment_result 及本次状态迁移快照表
-- 执行环境：测试环境 / 生产环境（审批、备份后）
-- ============================================

SET @snapshot_label := CAST('20260819120000-ddl-add_yj_assessment_result_status' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci;
SET @meta_exists := (
  SELECT COUNT(1)
  FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'bak_20260819_yj_assessment_result_status_meta'
);
SET @row_backup_exists := (
  SELECT COUNT(1)
  FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'bak_20260819_yj_assessment_result_status_rows'
);

SET @had_report_status := 1;
SET @had_failure_reason := 1;
SET @had_report_status_index := 1;
SET @meta_sql := IF(@meta_exists > 0,
  CONCAT(
    'SELECT CAST(`had_report_status` AS UNSIGNED), ',
    'CAST(`had_failure_reason` AS UNSIGNED), ',
    'CAST(`had_report_status_index` AS UNSIGNED) ',
    'INTO @had_report_status, @had_failure_reason, @had_report_status_index ',
    'FROM `bak_20260819_yj_assessment_result_status_meta` ',
    'WHERE `snapshot_label` = ''', @snapshot_label, ''' COLLATE utf8mb4_unicode_ci LIMIT 1'
  ),
  'SELECT 1'
);
PREPARE stmt FROM @meta_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

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

SET @restore_sql := IF(@meta_exists > 0 AND @row_backup_exists > 0 AND @had_report_status = 1 AND @had_failure_reason = 1,
  CONCAT(
    'UPDATE `yj_assessment_result` target ',
    'INNER JOIN `bak_20260819_yj_assessment_result_status_rows` backup ',
    'ON backup.`snapshot_label` = ''', @snapshot_label, ''' COLLATE utf8mb4_unicode_ci ',
    'AND backup.`assessment_result_id` = target.`id` ',
    'SET target.`report_status` = backup.`report_status`, ',
    '    target.`failure_reason` = backup.`failure_reason`'
  ),
  'SELECT ''snapshot absent or status columns were originally missing; row restore skipped'' AS info'
);
PREPARE stmt FROM @restore_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl_sql := '';
SET @ddl_sql := IF(@had_report_status_index = 0 AND @report_status_index_exists > 0,
  CONCAT(@ddl_sql, 'DROP INDEX `idx_yj_assessment_result_report_status`'),
  @ddl_sql);
SET @ddl_sql := IF(@had_failure_reason = 0 AND @failure_reason_exists > 0,
  CONCAT(@ddl_sql, IF(@ddl_sql <> '', ', ', ''), 'DROP COLUMN `failure_reason`'),
  @ddl_sql);
SET @ddl_sql := IF(@had_report_status = 0 AND @report_status_exists > 0,
  CONCAT(@ddl_sql, IF(@ddl_sql <> '', ', ', ''), 'DROP COLUMN `report_status`'),
  @ddl_sql);
SET @ddl_sql := IF(@ddl_sql = '',
  'SELECT ''rollback noop: current schema already matches snapshot'' AS info',
  CONCAT('ALTER TABLE `yj_assessment_result` ', @ddl_sql)
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 后置校验：确认列、索引与快照恢复结果。
SELECT
  IF(report_status_column.COLUMN_NAME IS NULL, 0, 1) AS report_status_exists,
  IF(failure_reason_column.COLUMN_NAME IS NULL, 0, 1) AS failure_reason_exists,
  IF(report_status_index.INDEX_NAME IS NULL, 0, 1) AS report_status_index_exists
FROM (SELECT 1 AS anchor) anchor
LEFT JOIN information_schema.COLUMNS report_status_column
  ON report_status_column.TABLE_SCHEMA = DATABASE()
 AND report_status_column.TABLE_NAME = 'yj_assessment_result'
 AND report_status_column.COLUMN_NAME = 'report_status'
LEFT JOIN information_schema.COLUMNS failure_reason_column
  ON failure_reason_column.TABLE_SCHEMA = DATABASE()
 AND failure_reason_column.TABLE_NAME = 'yj_assessment_result'
 AND failure_reason_column.COLUMN_NAME = 'failure_reason'
LEFT JOIN information_schema.STATISTICS report_status_index
  ON report_status_index.TABLE_SCHEMA = DATABASE()
 AND report_status_index.TABLE_NAME = 'yj_assessment_result'
 AND report_status_index.INDEX_NAME = 'idx_yj_assessment_result_report_status';

SET @status_summary_sql := IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'yj_assessment_result'
      AND COLUMN_NAME = 'report_status'
  ),
  'SELECT `report_status`, COUNT(1) AS row_count FROM `yj_assessment_result` WHERE `deleted` = b''0'' GROUP BY `report_status` ORDER BY `report_status`',
  'SELECT ''report_status column absent after rollback'' AS info'
);
PREPARE stmt FROM @status_summary_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
