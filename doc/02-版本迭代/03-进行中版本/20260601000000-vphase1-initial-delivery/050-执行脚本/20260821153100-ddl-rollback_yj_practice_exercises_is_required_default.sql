-- ============================================
-- 脚本类型：ddl
-- 脚本描述：回滚练习题目必填字段默认值
-- 创建日期：2026-08-21 15:31:00
-- 作者：Codex
-- 影响范围：yj_practice_exercises.is_required
-- 执行环境：测试环境
-- ============================================

-- 说明：仅回滚字段默认值，不回滚已回填的数据。
ALTER TABLE yj_practice_exercises
  MODIFY COLUMN is_required bit(1) NOT NULL COMMENT '是否必填';
