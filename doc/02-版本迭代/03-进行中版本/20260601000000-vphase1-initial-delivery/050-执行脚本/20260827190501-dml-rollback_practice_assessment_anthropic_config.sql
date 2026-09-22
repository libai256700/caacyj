-- ============================================
-- 脚本类型：dml
-- 脚本描述：回滚 practice_assessment 的 DeepSeek Anthropic 兼容配置
-- 创建日期：2026-08-27 19:05:01
-- 作者：Codex
-- 影响范围：yj_ai_model_config 中唯一启用的 practice_assessment 配置
-- 执行环境：Local 正式记录指向的测试库
-- ============================================

-- 安全变量门禁：执行器必须从仓外受限备份读取原密钥，并在同一数据库会话中
-- 通过参数绑定设置 @practice_assessment_rollback_api_key。本脚本不保存密钥明文。
SET @target_scene_code = 'practice_assessment';
SET @rollback_channel = 'OPENAI_COMPATIBLE';
SET @rollback_base_url = 'https://techyuan.net';
SET @rollback_model = 'gpt-5.5';
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
SET @rollback_api_key_ready = IF(
    @practice_assessment_rollback_api_key IS NOT NULL
        AND CHAR_LENGTH(@practice_assessment_rollback_api_key) >= 20,
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

-- 前置检查：唯一 active 行必须仍为本次目标结构，且安全回滚密钥已绑定。
SELECT @active_count AS active_count,
       @target_config_id AS target_config_id,
       @rollback_api_key_ready AS rollback_api_key_ready,
       SHA2(@practice_assessment_rollback_api_key, 256) AS rollback_api_key_sha256,
       @prompt_unchanged_before AS prompt_unchanged_before;

SELECT id, scene_code, channel, base_url, model, timeout_millis, status,
       SHA2(api_key, 256) AS current_api_key_sha256
FROM yj_ai_model_config
WHERE scene_code = @target_scene_code
  AND status = 0
  AND deleted = b'0';

START TRANSACTION;

-- 主要变更：仅从本次目标结构回滚，timeout 与提示词均不修改。
UPDATE yj_ai_model_config
SET channel = @rollback_channel,
    base_url = @rollback_base_url,
    model = @rollback_model,
    api_key = @practice_assessment_rollback_api_key,
    updater = 'codex-config-rollback',
    update_time = NOW()
WHERE id = @target_config_id
  AND @active_count = 1
  AND @rollback_api_key_ready = 1
  AND @prompt_unchanged_before = 1
  AND scene_code = @target_scene_code
  AND status = 0
  AND deleted = b'0'
  AND channel = 'ANTHROPIC'
  AND base_url = 'https://api.deepseek.com/anthropic'
  AND model = 'deepseek-v4-pro'
  AND timeout_millis = @expected_timeout_millis;

SET @updated_rows = ROW_COUNT();
SET @postcheck_count = (
    SELECT COUNT(1)
    FROM yj_ai_model_config
    WHERE id = @target_config_id
      AND scene_code = @target_scene_code
      AND status = 0
      AND deleted = b'0'
      AND channel = @rollback_channel
      AND base_url = @rollback_base_url
      AND model = @rollback_model
      AND timeout_millis = @expected_timeout_millis
      AND SHA2(api_key, 256) = SHA2(@practice_assessment_rollback_api_key, 256)
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
        AND @rollback_api_key_ready = 1
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
