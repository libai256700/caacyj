-- ============================================
-- 脚本类型：ddl
-- 脚本描述：幂等补齐评测批次保存状态字段并回填历史完成批次
-- 创建日期：2026-08-31 10:30:00
-- 作者：Codex
-- 影响范围：yj_practice_catalog_batch.status 及本次迁移快照表
-- 执行环境：测试环境 / 生产环境（审批、备份后）
-- 字段边界：本脚本只新增、规范、回填或回滚status；is_completed仅用于只读快照、筛选和校验，绝不更新。
-- ============================================

-- 前置检查：确认目标表、人工已建字段定义和现有状态分布；结果必须留档。
SELECT
  table_meta.TABLE_NAME AS table_name,
  status_column.COLUMN_NAME AS status_column,
  status_column.COLUMN_TYPE AS status_column_type,
  status_column.IS_NULLABLE AS status_is_nullable,
  status_column.COLUMN_DEFAULT AS status_default,
  status_column.COLUMN_COMMENT AS status_comment
FROM information_schema.TABLES table_meta
LEFT JOIN information_schema.COLUMNS status_column
  ON status_column.TABLE_SCHEMA = table_meta.TABLE_SCHEMA
 AND status_column.TABLE_NAME = table_meta.TABLE_NAME
 AND status_column.COLUMN_NAME = 'status'
WHERE table_meta.TABLE_SCHEMA = DATABASE()
  AND table_meta.TABLE_NAME = 'yj_practice_catalog_batch';

SET @snapshot_label := '20260831103000-ddl-add_yj_practice_catalog_batch_status';
SET @status_exists_before := (
  SELECT COUNT(1)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'yj_practice_catalog_batch'
    AND COLUMN_NAME = 'status'
);

SET @precheck_sql := IF(
  @status_exists_before > 0,
  'SELECT `status`, `is_completed`, COUNT(1) AS row_count FROM `yj_practice_catalog_batch` GROUP BY `status`, `is_completed` ORDER BY `status`, `is_completed`',
  'SELECT ''status column absent; data distribution check skipped'' AS info'
);
PREPARE stmt FROM @precheck_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 快照：记录字段原始存在性，并在字段可读后保存每个批次的原状态。
CREATE TABLE IF NOT EXISTS `bak_20260831_yj_practice_catalog_batch_status_meta` (
  `snapshot_label` varchar(80) NOT NULL COMMENT '脚本快照标签',
  `had_status_column` tinyint NOT NULL DEFAULT 0 COMMENT '执行前是否存在status字段：0否/1是',
  `snapshot_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '快照时间',
  PRIMARY KEY (`snapshot_label`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='评测批次保存状态迁移元数据快照';

CREATE TABLE IF NOT EXISTS `bak_20260831_yj_practice_catalog_batch_status_rows` (
  `snapshot_label` varchar(80) NOT NULL COMMENT '脚本快照标签',
  `batch_id` bigint NOT NULL COMMENT '评测批次ID',
  `status` tinyint DEFAULT NULL COMMENT '执行前保存状态；人工字段原值可为空',
  `is_completed` tinyint NOT NULL DEFAULT 0 COMMENT '执行前是否完成',
  `snapshot_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '快照时间',
  PRIMARY KEY (`snapshot_label`, `batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='评测批次保存状态迁移行级快照';

INSERT INTO `bak_20260831_yj_practice_catalog_batch_status_meta` (
  `snapshot_label`,
  `had_status_column`
)
SELECT @snapshot_label, IF(@status_exists_before > 0, 1, 0)
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1
  FROM `bak_20260831_yj_practice_catalog_batch_status_meta`
  WHERE `snapshot_label` = @snapshot_label
);

SET @backup_existing_status_sql := IF(
  @status_exists_before > 0,
  CONCAT(
    'INSERT INTO `bak_20260831_yj_practice_catalog_batch_status_rows` ',
    '(`snapshot_label`, `batch_id`, `status`, `is_completed`) ',
    'SELECT ''', @snapshot_label, ''', source_row.`id`, source_row.`status`, source_row.`is_completed` ',
    'FROM `yj_practice_catalog_batch` source_row ',
    'WHERE NOT EXISTS (',
    '  SELECT 1 FROM `bak_20260831_yj_practice_catalog_batch_status_rows` backup_row ',
    '  WHERE backup_row.`snapshot_label` = ''', @snapshot_label, ''' ',
    '    AND backup_row.`batch_id` = source_row.`id`',
    ')'
  ),
  'SELECT ''status column absent before migration; pre-change row snapshot deferred'' AS info'
);
PREPARE stmt FROM @backup_existing_status_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 主要变更：兼容字段已由人工创建的现场；不存在时新增，存在时继续规范定义。
SET @ddl_sql := IF(
  @status_exists_before = 0,
  'ALTER TABLE `yj_practice_catalog_batch` ADD COLUMN `status` TINYINT NOT NULL DEFAULT 0 COMMENT ''评测保存状态：0未开始、1写入中、2写入结束''',
  'SELECT ''status column already exists; normalize definition'' AS info'
);
PREPARE stmt FROM @ddl_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 先消除人工字段可能存在的NULL，再统一类型、默认值和注释。
UPDATE `yj_practice_catalog_batch`
SET `status` = 0
WHERE `status` IS NULL
   OR `status` NOT IN (0, 1, 2);

ALTER TABLE `yj_practice_catalog_batch`
  MODIFY COLUMN `status` TINYINT NOT NULL DEFAULT 0 COMMENT '评测保存状态：0未开始、1写入中、2写入结束';

INSERT INTO `bak_20260831_yj_practice_catalog_batch_status_rows` (
  `snapshot_label`,
  `batch_id`,
  `status`,
  `is_completed`
)
SELECT
  @snapshot_label,
  source_row.`id`,
  source_row.`status`,
  source_row.`is_completed`
FROM `yj_practice_catalog_batch` source_row
WHERE NOT EXISTS (
  SELECT 1
  FROM `bak_20260831_yj_practice_catalog_batch_status_rows` backup_row
  WHERE backup_row.`snapshot_label` = @snapshot_label
    AND backup_row.`batch_id` = source_row.`id`
);

-- 历史回填：is_completed仅作为只读筛选条件，只更新status；重复执行结果不变。
UPDATE `yj_practice_catalog_batch`
SET `status` = 2
WHERE `is_completed` = 1
  AND `status` <> 2;

-- 后置校验：字段定义准确、状态仅为0/1/2，并只读核对历史完成批次回填结果。
SELECT
  COLUMN_NAME,
  COLUMN_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT,
  COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_practice_catalog_batch'
  AND COLUMN_NAME = 'status';

SELECT
  `status`,
  `is_completed`,
  COUNT(1) AS row_count
FROM `yj_practice_catalog_batch`
GROUP BY `status`, `is_completed`
ORDER BY `status`, `is_completed`;

SELECT
  SUM(CASE WHEN `status` NOT IN (0, 1, 2) THEN 1 ELSE 0 END) AS invalid_status_count,
  SUM(CASE WHEN `is_completed` = 1 AND `status` <> 2 THEN 1 ELSE 0 END) AS completed_not_status_2_count
FROM `yj_practice_catalog_batch`;

-- 索引说明：status仅3个低区分度取值，latest-status沿用现有用户/分类/批次时序
-- 定位唯一最新批次后读取本字段，本次不新增status单列或联合索引。

-- 回滚口径（必须审批后单独执行，不得与主变更同次执行）：
-- 1. 先校验快照标签、had_status_column、执行前information_schema留档和批次数量。
-- 2. 若meta.had_status_column=1，先按执行前留档恢复字段可空性/类型/默认值/注释，
--    再按batch_id恢复执行前status（避免原值NULL时被当前NOT NULL定义阻断）：
--    UPDATE `yj_practice_catalog_batch` target
--    JOIN `bak_20260831_yj_practice_catalog_batch_status_rows` backup
--      ON backup.`snapshot_label` = '20260831103000-ddl-add_yj_practice_catalog_batch_status'
--     AND backup.`batch_id` = target.`id`
--    SET target.`status` = backup.`status`;
-- 3. 若meta.had_status_column=0，确认应用已回退后执行：
--    ALTER TABLE `yj_practice_catalog_batch` DROP COLUMN `status`;
-- 4. 回滚验证通过且确认不再需要二次回滚后，方可清理两个bak_20260831快照表。
