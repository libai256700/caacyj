-- Reuse the active GPT connection for the dedicated Feishu job-extraction scene.
-- No secret is duplicated in source control; credentials are copied inside the database.

INSERT INTO `yj_ai_model_config` (
    `scene_code`, `scene_name`, `channel`, `base_url`, `api_key`, `extra_config`,
    `model`, `system_prompt`, `temperature`, `max_tokens`, `timeout_millis`,
    `min_report_length`, `status`, `sort`, `remark`, `creator`, `create_time`,
    `updater`, `update_time`, `deleted`
)
SELECT
    'job_extraction', '飞书岗位提取', source.`channel`, source.`base_url`, source.`api_key`,
    source.`extra_config`, source.`model`, NULL, 0.1, 12000,
    GREATEST(COALESCE(source.`timeout_millis`, 300000), 300000), NULL, 0, 10,
    '飞书新增岗位章节定位与结构化提取', 'system', NOW(), 'system', NOW(), b'0'
FROM `yj_ai_model_config` source
WHERE source.`scene_code` = 'knowledge_chat'
  AND source.`status` = 0
  AND source.`deleted` = b'0'
  AND NOT EXISTS (
      SELECT 1
      FROM `yj_ai_model_config` target
      WHERE target.`scene_code` = 'job_extraction'
        AND target.`deleted` = b'0'
  )
ORDER BY source.`sort`, source.`id`
LIMIT 1;
