-- ============================================
-- 脚本类型：ddl
-- 脚本描述：补齐练习题目必填字段默认值并回填历史数据
-- 创建日期：2026-08-21 15:30:00
-- 作者：Codex
-- 影响范围：yj_practice_exercises.is_required
-- 执行环境：测试环境
-- ============================================

-- 前置检查：确认字段已存在，且统计当前默认值与历史数据分布。
SHOW COLUMNS FROM yj_practice_exercises LIKE 'is_required';

SELECT
  COUNT(1) AS total,
  SUM(CASE WHEN is_required IS NULL THEN 1 ELSE 0 END) AS null_cnt,
  SUM(CASE WHEN is_required = b'1' THEN 1 ELSE 0 END) AS one_cnt,
  SUM(CASE WHEN is_required = b'0' THEN 1 ELSE 0 END) AS zero_cnt
FROM yj_practice_exercises;

-- 主要变更：将字段默认值设为 1，并确保历史数据全部为 1。
ALTER TABLE yj_practice_exercises
  MODIFY COLUMN is_required bit(1) NOT NULL DEFAULT b'1' COMMENT '是否必填';

UPDATE yj_practice_exercises
SET is_required = b'1'
WHERE is_required IS NULL
   OR is_required = b'0';

-- 后置校验：默认值为 1，历史数据全部回填为 1。
SHOW COLUMNS FROM yj_practice_exercises LIKE 'is_required';

SELECT
  COUNT(1) AS total,
  SUM(CASE WHEN is_required IS NULL THEN 1 ELSE 0 END) AS null_cnt,
  SUM(CASE WHEN is_required = b'1' THEN 1 ELSE 0 END) AS one_cnt,
  SUM(CASE WHEN is_required = b'0' THEN 1 ELSE 0 END) AS zero_cnt
FROM yj_practice_exercises;
