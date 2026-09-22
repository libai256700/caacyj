-- ============================================
-- Script type: dml
-- Description: insert AI agent management seed records for job search and UAV exam roles
-- Created at: 2026-06-15 18:08:44
-- Author: Codex
-- Impact scope: yj_agent_info insert 2 rows when names do not already exist
-- Environment: test
-- Rollback: rollback_20260615180844-dml-insert_yj_agent_info_ai_agents.sql
-- ============================================

START TRANSACTION;

-- Pre-check: target rows before execution.
SELECT id, name, knowledge_base_id, prompt_config, reply_strategy, status + 0 AS status,
       remark, tenant_id, deleted + 0 AS deleted
FROM yj_agent_info
WHERE name IN ('小搜', '小题');

INSERT INTO yj_agent_info (
    name, knowledge_base_id, prompt_config, reply_strategy, status, remark,
    tenant_id, creator, create_time, updater, update_time, deleted
)
SELECT '小搜',
       NULL,
       '你是一个专业的岗位搜索专家，负责理解用户的岗位诉求，检索并筛选匹配岗位，提炼岗位职责、任职要求、薪资地点等关键信息，并给出清晰可执行的岗位搜索建议。',
       '岗位搜索、岗位匹配、招聘信息解析',
       b'1',
       '岗位搜索专家，负责岗位检索、岗位匹配和招聘信息要点提炼。',
       1,
       '1',
       NOW(),
       '1',
       NOW(),
       b'0'
WHERE NOT EXISTS (
    SELECT 1 FROM yj_agent_info WHERE name = '小搜'
);

INSERT INTO yj_agent_info (
    name, knowledge_base_id, prompt_config, reply_strategy, status, remark,
    tenant_id, creator, create_time, updater, update_time, deleted
)
SELECT '小题',
       NULL,
       '你是一个知识渊博的无人机考题专家，负责围绕无人机基础知识、飞行安全、法规规范、设备操作、维护保养和应用场景生成、解析与校验相关考题，并输出准确、清晰、适合学习训练的答案说明。',
       '无人机考题生成、试题解析、知识点校验',
       b'1',
       '无人机考题专家，负责无人机相关试题生成、解析和知识点校验。',
       1,
       '1',
       NOW(),
       '1',
       NOW(),
       b'0'
WHERE NOT EXISTS (
    SELECT 1 FROM yj_agent_info WHERE name = '小题'
);

-- Post-check: target rows after execution.
SELECT id, name, knowledge_base_id, prompt_config, reply_strategy, status + 0 AS status,
       remark, tenant_id, deleted + 0 AS deleted
FROM yj_agent_info
WHERE name IN ('小搜', '小题')
ORDER BY name;

COMMIT;
