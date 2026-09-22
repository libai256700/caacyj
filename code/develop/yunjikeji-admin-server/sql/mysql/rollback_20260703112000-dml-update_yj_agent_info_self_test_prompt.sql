-- ============================================
-- 脚本类型：dml
-- 脚本描述：回滚小题智能体自测 AI 报告 HTML 生成提示词
-- 创建日期：2026-07-03 11:20:00
-- 作者：Codex
-- 影响范围：yj_agent_info.id = 2 且 name = '小题'
-- 执行环境：测试环境
-- ============================================

START TRANSACTION;

-- 前置检查：确认当前目标记录。
SELECT id, name, CHAR_LENGTH(prompt_config) AS prompt_length, reply_strategy, remark,
       tenant_id, deleted + 0 AS deleted
FROM yj_agent_info
WHERE id = 2 OR name = '小题';

UPDATE yj_agent_info
SET prompt_config = '你是一个知识渊博的无人机考题专家，负责围绕无人机基础知识、飞行安全、法规规范、设备操作、维护保养和应用场景生成、解析与校验相关考题，并输出准确、清晰、适合学习训练的答案说明。',
    reply_strategy = '无人机考题生成、试题解析、知识点校验',
    remark = '无人机考题专家，负责无人机相关试题生成、解析和知识点校验。',
    updater = '1',
    update_time = NOW()
WHERE id = 2
  AND name = '小题'
  AND deleted = b'0';

-- 后置校验。
SELECT id, name, prompt_config, reply_strategy, remark,
       update_time, tenant_id, deleted + 0 AS deleted
FROM yj_agent_info
WHERE id = 2 OR name = '小题';

COMMIT;
