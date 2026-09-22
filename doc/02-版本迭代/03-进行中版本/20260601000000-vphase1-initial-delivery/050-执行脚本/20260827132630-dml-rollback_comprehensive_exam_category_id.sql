-- ============================================
-- 脚本类型：dml
-- 脚本描述：按原值快照回滚综合考试批次 category_id
-- 创建日期：2026-08-27 13:26:30
-- 作者：Codex
-- 影响范围：bak_20260827_practice_catalog_batch_category_id 中记录的批次
-- 执行环境：测试环境，验证通过后按审批流程执行生产环境
-- ============================================

-- 前置检查：确认备份范围及当前待回滚数量。
SELECT COUNT(1) AS backup_count
FROM bak_20260827_practice_catalog_batch_category_id;

SELECT COUNT(1) AS rollback_candidate_count
FROM yj_practice_catalog_batch batch
INNER JOIN bak_20260827_practice_catalog_batch_category_id backup ON backup.id = batch.id
WHERE batch.category_id = 10;

-- 主要变更：仅回滚仍为本次目标值 10 的快照记录，避免覆盖后续人工修改。
UPDATE yj_practice_catalog_batch batch
INNER JOIN bak_20260827_practice_catalog_batch_category_id backup ON backup.id = batch.id
SET batch.category_id = backup.category_id
WHERE batch.category_id = 10;

-- 后置校验：remaining_count 必须为 0。
SELECT COUNT(1) AS remaining_count
FROM yj_practice_catalog_batch batch
INNER JOIN bak_20260827_practice_catalog_batch_category_id backup ON backup.id = batch.id
WHERE NOT (batch.category_id <=> backup.category_id);
