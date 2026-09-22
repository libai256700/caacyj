-- ============================================
-- 脚本类型：dml
-- 脚本描述：将 practice_assessment 切换到 DeepSeek Anthropic 兼容配置
-- 创建日期：2026-08-27 19:05:00
-- 作者：Codex
-- 影响范围：yj_ai_model_config 中唯一启用的 practice_assessment 配置
-- 执行环境：Local 正式记录指向的测试库
-- ============================================

-- 安全变量门禁：执行器必须在同一数据库会话中通过参数绑定设置
-- @practice_assessment_api_key。本脚本禁止写入、回显或持久化密钥明文。
SET @target_scene_code = 'practice_assessment';
SET @target_channel = 'ANTHROPIC';
SET @target_base_url = 'https://api.deepseek.com/anthropic';
SET @target_model = 'deepseek-v4-pro';
SET @expected_timeout_millis = 120000;
SET @expected_agent_prompt_sha256_v3 = 'd7794b51e039db2ecd7589e60dd593d8f85648c9b774e414768a2539ad3c16ce';
SET @expected_agent_prompt_sha256_v3_certificate = '974ef05f4cda6fe0e07d6076c06e0c87b33986461dcaf2d39feda7c1e2d8d414';

SET @active_count = (
    SELECT COUNT(1)
    FROM yj_ai_model_config
    WHERE scene_code = @target_scene_code
      AND status = 0
      AND deleted = b'0'
);
SET @target_config_id = (
    SELECT MIN(id)
    FROM yj_ai_model_config
    WHERE scene_code = @target_scene_code
      AND status = 0
      AND deleted = b'0'
);
SET @api_key_ready = IF(
    @practice_assessment_api_key IS NOT NULL
        AND CHAR_LENGTH(@practice_assessment_api_key) >= 20,
    1,
    0
);
SET @prompt_unchanged_before = (
    SELECT COUNT(1)
    FROM yj_agent_info
    WHERE id = 2
      AND deleted = b'0'
      AND SHA2(prompt_config, 256) IN (
          @expected_agent_prompt_sha256_v3,
          @expected_agent_prompt_sha256_v3_certificate
      )
);

-- 前置检查：active_count、api_key_ready、prompt_unchanged_before 必须均为 1。
-- 只输出密钥哈希，不输出密钥明文。
SELECT @active_count AS active_count,
       @target_config_id AS target_config_id,
       @api_key_ready AS api_key_ready,
       SHA2(@practice_assessment_api_key, 256) AS target_api_key_sha256,
       @prompt_unchanged_before AS prompt_unchanged_before;

SELECT id, scene_code, channel, base_url, model, timeout_millis, status,
       SHA2(api_key, 256) AS current_api_key_sha256
FROM yj_ai_model_config
WHERE scene_code = @target_scene_code
  AND status = 0
  AND deleted = b'0';

START TRANSACTION;

-- 主要变更：仅允许从已核验旧结构或本脚本目标结构切换，timeout 与提示词均不修改。
UPDATE yj_ai_model_config
SET channel = @target_channel,
    base_url = @target_base_url,
    model = @target_model,
    api_key = @practice_assessment_api_key,
    updater = 'codex-config-change',
    update_time = NOW()
WHERE id = @target_config_id
  AND @active_count = 1
  AND @api_key_ready = 1
  AND @prompt_unchanged_before = 1
  AND scene_code = @target_scene_code
  AND status = 0
  AND deleted = b'0'
  AND timeout_millis = @expected_timeout_millis
  AND (
      (channel = 'OPENAI_COMPATIBLE'
       AND base_url = 'https://techyuan.net'
       AND model = 'gpt-5.5')
      OR
      (channel = @target_channel
       AND base_url = @target_base_url
       AND model = @target_model)
  );

SET @updated_rows = ROW_COUNT();
SET @postcheck_count = (
    SELECT COUNT(1)
    FROM yj_ai_model_config
    WHERE id = @target_config_id
      AND scene_code = @target_scene_code
      AND status = 0
      AND deleted = b'0'
      AND channel = @target_channel
      AND base_url = @target_base_url
      AND model = @target_model
      AND timeout_millis = @expected_timeout_millis
      AND SHA2(api_key, 256) = SHA2(@practice_assessment_api_key, 256)
);
SET @prompt_unchanged_after = (
    SELECT COUNT(1)
    FROM yj_agent_info
    WHERE id = 2
      AND deleted = b'0'
      AND SHA2(prompt_config, 256) IN (
          @expected_agent_prompt_sha256_v3,
          @expected_agent_prompt_sha256_v3_certificate
      )
);
SET @execution_pass = IF(
    @active_count = 1
        AND @api_key_ready = 1
        AND @updated_rows = 1
        AND @postcheck_count = 1
        AND @prompt_unchanged_after = 1,
    1,
    0
);

-- 后置校验：execution_result 必须为 PASS；只输出非敏感字段与密钥哈希。
SELECT @updated_rows AS updated_rows,
       @postcheck_count AS postcheck_count,
       @prompt_unchanged_after AS prompt_unchanged_after,
       IF(@execution_pass = 1, 'PASS', 'FAIL') AS execution_result;

SELECT id, scene_code, channel, base_url, model, timeout_millis, status,
       SHA2(api_key, 256) AS api_key_sha256
FROM yj_ai_model_config
WHERE id = @target_config_id;

SELECT id,
       CHAR_LENGTH(prompt_config) AS prompt_char_length,
       LENGTH(prompt_config) AS prompt_byte_length,
       SHA2(prompt_config, 256) AS prompt_sha256
FROM yj_agent_info
WHERE id = 2
  AND deleted = b'0';

-- 提交门禁：执行器仅在 @execution_pass = 1 时 COMMIT，否则必须 ROLLBACK。
-- 回滚方案：执行 20260827190501-dml-rollback_practice_assessment_anthropic_config.sql，
-- 并从仓外受限备份安全绑定 @practice_assessment_rollback_api_key。
