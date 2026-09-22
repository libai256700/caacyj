-- ============================================
-- 脚本类型：dml
-- 脚本描述：将综合考试批次的空 category_id 回填为 10
-- 创建日期：2026-08-27 13:26:29
-- 作者：Codex
-- 影响范围：yj_practice_catalog_batch 中 category_id 为空的综合考试批次
-- 执行环境：测试环境，验证通过后按审批流程执行生产环境
-- ============================================

-- 前置检查：确认分类 10 存在，并统计本次候选数据。
SELECT id, category_name, field_type, category_status, deleted
FROM yj_practice_category
WHERE id = 10;

SELECT COUNT(1) AS candidate_count
FROM yj_practice_catalog_batch
WHERE category_id IS NULL
  AND type = 4
  AND mode = 'COMPREHENSIVE_EXAM'
  AND category_name = '综合考试';

-- 首次执行时保存原始 category_id；重复执行保留首次快照。
CREATE TABLE IF NOT EXISTS bak_20260827_practice_catalog_batch_category_id AS
SELECT id, category_id
FROM yj_practice_catalog_batch
WHERE category_id IS NULL
  AND type = 4
  AND mode = 'COMPREHENSIVE_EXAM'
  AND category_name = '综合考试';

-- 主要变更：仅在分类 10 有效时回填目标批次。
UPDATE yj_practice_catalog_batch batch
INNER JOIN yj_practice_category category
  ON category.id = 10
 AND category.deleted = b'0'
SET batch.category_id = category.id
WHERE batch.category_id IS NULL
  AND batch.type = 4
  AND batch.mode = 'COMPREHENSIVE_EXAM'
  AND batch.category_name = '综合考试';

-- 后置校验：remaining_count 必须为 0，updated_count 应与首次 candidate_count 一致。
SELECT COUNT(1) AS remaining_count
FROM yj_practice_catalog_batch
WHERE category_id IS NULL
  AND type = 4
  AND mode = 'COMPREHENSIVE_EXAM'
  AND category_name = '综合考试';

SELECT COUNT(1) AS updated_count
FROM yj_practice_catalog_batch batch
INNER JOIN bak_20260827_practice_catalog_batch_category_id backup ON backup.id = batch.id
WHERE batch.category_id = 10;

-- 回滚方案：执行 20260827132630-dml-rollback_comprehensive_exam_category_id.sql。
