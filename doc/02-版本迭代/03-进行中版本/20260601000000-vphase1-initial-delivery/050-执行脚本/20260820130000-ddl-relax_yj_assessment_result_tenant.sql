-- ============================================
-- 脚本类型：ddl
-- 脚本描述：放宽共享自测结果表租户字段可空约束
-- 创建日期：2026-08-20 13:00:00
-- 作者：Codex
-- 影响范围：yj_assessment_result.tenant_id
-- 执行环境：测试环境 / 生产环境（审批、备份后）
-- ============================================

ALTER TABLE `yj_assessment_result`
  MODIFY COLUMN `tenant_id` bigint DEFAULT NULL COMMENT '租户编号（自测结果共享表可为空）';

-- 后置校验
SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yj_assessment_result'
  AND COLUMN_NAME = 'tenant_id';

-- 回滚：恢复为原有非空默认 0 约束（执行前必须确认不存在 tenant_id IS NULL 数据）
-- ALTER TABLE `yj_assessment_result`
--   MODIFY COLUMN `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号';
