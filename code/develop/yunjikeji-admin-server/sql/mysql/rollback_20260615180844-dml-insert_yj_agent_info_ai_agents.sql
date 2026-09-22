-- ============================================
-- Script type: dml rollback
-- Description: remove AI agent management seed records inserted by 20260615180844-dml-insert_yj_agent_info_ai_agents.sql
-- Created at: 2026-06-15 18:08:44
-- Author: Codex
-- Impact scope: yj_agent_info delete 2 rows by fixed names and prompt contents
-- Environment: test
-- ============================================

START TRANSACTION;

-- Pre-check: target rows before rollback.
SELECT id, name, knowledge_base_id, prompt_config, reply_strategy, status + 0 AS status,
       remark, tenant_id, deleted + 0 AS deleted
FROM yj_agent_info
WHERE name IN ('小搜', '小题');

DELETE FROM yj_agent_info
WHERE name = '小搜'
  AND tenant_id = 1
  AND prompt_config = '你是一个专业的岗位搜索专家，负责理解用户的岗位诉求，检索并筛选匹配岗位，提炼岗位职责、任职要求、薪资地点等关键信息，并给出清晰可执行的岗位搜索建议。'
  AND remark = '岗位搜索专家，负责岗位检索、岗位匹配和招聘信息要点提炼。';

DELETE FROM yj_agent_info
WHERE name = '小题'
  AND tenant_id = 1
  AND prompt_config = '你是一个知识渊博的无人机考题专家，负责围绕无人机基础知识、飞行安全、法规规范、设备操作、维护保养和应用场景生成、解析与校验相关考题，并输出准确、清晰、适合学习训练的答案说明。'
  AND remark = '无人机考题专家，负责无人机相关试题生成、解析和知识点校验。';

-- Post-check: target rows after rollback.
SELECT id, name, knowledge_base_id, prompt_config, reply_strategy, status + 0 AS status,
       remark, tenant_id, deleted + 0 AS deleted
FROM yj_agent_info
WHERE name IN ('小搜', '小题')
ORDER BY name;

COMMIT;
