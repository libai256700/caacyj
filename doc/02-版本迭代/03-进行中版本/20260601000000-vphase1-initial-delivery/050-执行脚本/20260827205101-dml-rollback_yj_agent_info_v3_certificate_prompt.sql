-- ============================================
-- 脚本类型：dml
-- 脚本描述：精确回滚数据库 V3 system prompt 的泛化证照表述约束
-- 创建日期：2026-08-27 20:51:01
-- 作者：Codex
-- 影响范围：yj_agent_info.id = 2 且 name = '小题' 的 prompt_config
-- 执行环境：Local 正式记录指向的测试库
-- 对应正向脚本：20260827205100-dml-update_yj_agent_info_v3_certificate_prompt.sql
-- ============================================

SET NAMES utf8mb4;

SET @expected_old_char_length = 2284;
SET @expected_old_byte_length = 5809;
SET @expected_old_sha256 = 'd7794b51e039db2ecd7589e60dd593d8f85648c9b774e414768a2539ad3c16ce';
SET @expected_new_char_length = 2440;
SET @expected_new_byte_length = 6243;
SET @expected_new_sha256 = '974ef05f4cda6fe0e07d6076c06e0c87b33986461dcaf2d39feda7c1e2d8d414';
SET @expected_reply_strategy_char_length = 85;
SET @expected_reply_strategy_sha256 = '184baf380d143497d22d042be6b95f2f4c98c558e308945146a5247fba411409';

SET @lf = CONVERT(0x0A USING utf8mb4);
SET @prompt_addendum = CONCAT(
    @lf, @lf,
    '【V3 证照表述规则（最高优先级，违反即不合格）】', @lf,
    '1. 只有【系统事实】明确给出白名单具体证书名称时，才允许使用该具体名称。', @lf,
    '2. 没有白名单具体证书时，必须改写为“已有培训或学习基础”。', @lf,
    '3. 禁止使用“高阶证照”“证照或培训基础”“培训或证照经历”“证照情况”等泛化证照措辞，不得虚构任何其他具体证书。'
);
SET @addendum_definition_ready = IF(
    CHAR_LENGTH(@prompt_addendum) = 156
        AND LENGTH(@prompt_addendum) = 434
        AND SHA2(@prompt_addendum, 256) = '1a1b04f8ffc3da874e119eebcbc190a897a3172af64e36395bb8fded1d2f6883',
    1,
    0
);

START TRANSACTION;

SELECT id,
       name,
       tenant_id,
       status + 0 AS status,
       deleted + 0 AS deleted,
       CHAR_LENGTH(prompt_config) AS prompt_char_length,
       LENGTH(prompt_config) AS prompt_byte_length,
       SHA2(prompt_config, 256) AS prompt_sha256,
       CHAR_LENGTH(reply_strategy) AS reply_strategy_char_length,
       SHA2(COALESCE(reply_strategy, ''), 256) AS reply_strategy_sha256
FROM yj_agent_info
WHERE id = 2
  AND name = '小题'
  AND tenant_id = 1
  AND status = b'1'
  AND deleted = b'0'
FOR UPDATE;

SET @target_count = (
    SELECT COUNT(1)
    FROM yj_agent_info
    WHERE id = 2
      AND name = '小题'
      AND tenant_id = 1
      AND status = b'1'
      AND deleted = b'0'
);
SET @before_is_new = (
    SELECT COUNT(1)
    FROM yj_agent_info
    WHERE id = 2
      AND name = '小题'
      AND tenant_id = 1
      AND status = b'1'
      AND deleted = b'0'
      AND CHAR_LENGTH(prompt_config) = @expected_new_char_length
      AND LENGTH(prompt_config) = @expected_new_byte_length
      AND SHA2(prompt_config, 256) = @expected_new_sha256
      AND RIGHT(prompt_config, CHAR_LENGTH(@prompt_addendum)) = @prompt_addendum
);
SET @before_is_old = (
    SELECT COUNT(1)
    FROM yj_agent_info
    WHERE id = 2
      AND name = '小题'
      AND tenant_id = 1
      AND status = b'1'
      AND deleted = b'0'
      AND CHAR_LENGTH(prompt_config) = @expected_old_char_length
      AND LENGTH(prompt_config) = @expected_old_byte_length
      AND SHA2(prompt_config, 256) = @expected_old_sha256
);
SET @reply_strategy_ready = (
    SELECT COUNT(1)
    FROM yj_agent_info
    WHERE id = 2
      AND name = '小题'
      AND tenant_id = 1
      AND status = b'1'
      AND deleted = b'0'
      AND CHAR_LENGTH(reply_strategy) = @expected_reply_strategy_char_length
      AND SHA2(COALESCE(reply_strategy, ''), 256) = @expected_reply_strategy_sha256
);
SET @ai_config_count_before = (
    SELECT COUNT(1)
    FROM yj_ai_model_config
    WHERE scene_code = 'practice_assessment'
      AND status = 0
      AND deleted = b'0'
);
SET @ai_config_fingerprint_before = (
    SELECT SHA2(CONCAT_WS(0x1F, channel, base_url, model, timeout_millis, SHA2(api_key, 256)), 256)
    FROM yj_ai_model_config
    WHERE scene_code = 'practice_assessment'
      AND status = 0
      AND deleted = b'0'
    LIMIT 1
);

SELECT @target_count AS target_count,
       @addendum_definition_ready AS addendum_definition_ready,
       @reply_strategy_ready AS reply_strategy_ready,
       @ai_config_count_before AS ai_config_count_before,
       CASE
           WHEN @target_count <> 1 THEN 'STOP_TARGET_NOT_UNIQUE'
           WHEN @addendum_definition_ready <> 1 THEN 'STOP_ADDENDUM_DEFINITION_MISMATCH'
           WHEN @reply_strategy_ready <> 1 THEN 'STOP_REPLY_STRATEGY_MISMATCH'
           WHEN @ai_config_count_before <> 1 THEN 'STOP_AI_CONFIG_NOT_UNIQUE'
           WHEN @before_is_new = 1 THEN 'READY'
           WHEN @before_is_old = 1 THEN 'ALREADY_ROLLED_BACK'
           ELSE 'STOP_UNEXPECTED_PROMPT'
       END AS precheck_result;

-- 仅删除已核验的精确尾部规则；已是旧值时不更新，重复执行保持幂等。
UPDATE yj_agent_info
SET prompt_config = LEFT(prompt_config, CHAR_LENGTH(prompt_config) - CHAR_LENGTH(@prompt_addendum)),
    updater = '1',
    update_time = NOW()
WHERE id = 2
  AND name = '小题'
  AND tenant_id = 1
  AND status = b'1'
  AND deleted = b'0'
  AND @target_count = 1
  AND @addendum_definition_ready = 1
  AND @reply_strategy_ready = 1
  AND @ai_config_count_before = 1
  AND CHAR_LENGTH(prompt_config) = @expected_new_char_length
  AND LENGTH(prompt_config) = @expected_new_byte_length
  AND SHA2(prompt_config, 256) = @expected_new_sha256
  AND RIGHT(prompt_config, CHAR_LENGTH(@prompt_addendum)) = @prompt_addendum;

SET @updated_rows = ROW_COUNT();
SET @postcheck_count = (
    SELECT COUNT(1)
    FROM yj_agent_info
    WHERE id = 2
      AND name = '小题'
      AND tenant_id = 1
      AND status = b'1'
      AND deleted = b'0'
      AND CHAR_LENGTH(prompt_config) = @expected_old_char_length
      AND LENGTH(prompt_config) = @expected_old_byte_length
      AND SHA2(prompt_config, 256) = @expected_old_sha256
      AND INSTR(prompt_config, '【V3 证照表述规则（最高优先级，违反即不合格）】') = 0
);
SET @reply_strategy_unchanged = (
    SELECT COUNT(1)
    FROM yj_agent_info
    WHERE id = 2
      AND name = '小题'
      AND tenant_id = 1
      AND status = b'1'
      AND deleted = b'0'
      AND CHAR_LENGTH(reply_strategy) = @expected_reply_strategy_char_length
      AND SHA2(COALESCE(reply_strategy, ''), 256) = @expected_reply_strategy_sha256
);
SET @ai_config_count_after = (
    SELECT COUNT(1)
    FROM yj_ai_model_config
    WHERE scene_code = 'practice_assessment'
      AND status = 0
      AND deleted = b'0'
);
SET @ai_config_fingerprint_after = (
    SELECT SHA2(CONCAT_WS(0x1F, channel, base_url, model, timeout_millis, SHA2(api_key, 256)), 256)
    FROM yj_ai_model_config
    WHERE scene_code = 'practice_assessment'
      AND status = 0
      AND deleted = b'0'
    LIMIT 1
);
SET @ai_config_unchanged = IF(
    @ai_config_count_before = 1
        AND @ai_config_count_after = 1
        AND @ai_config_fingerprint_before = @ai_config_fingerprint_after,
    1,
    0
);
SET @execution_pass = IF(
    @target_count = 1
        AND @addendum_definition_ready = 1
        AND @reply_strategy_unchanged = 1
        AND @ai_config_unchanged = 1
        AND @postcheck_count = 1
        AND (
            (@before_is_new = 1 AND @updated_rows = 1)
            OR (@before_is_old = 1 AND @updated_rows = 0)
        ),
    1,
    0
);

SELECT @updated_rows AS updated_rows,
       @postcheck_count AS postcheck_count,
       @reply_strategy_unchanged AS reply_strategy_unchanged,
       @ai_config_unchanged AS ai_config_unchanged,
       IF(@execution_pass = 1, 'PASS', 'FAIL_MANUAL_REVIEW_REQUIRED') AS execution_result;

SELECT id,
       CHAR_LENGTH(prompt_config) AS prompt_char_length,
       LENGTH(prompt_config) AS prompt_byte_length,
       SHA2(prompt_config, 256) AS prompt_sha256,
       CHAR_LENGTH(reply_strategy) AS reply_strategy_char_length,
       SHA2(COALESCE(reply_strategy, ''), 256) AS reply_strategy_sha256
FROM yj_agent_info
WHERE id = 2
  AND name = '小题'
  AND tenant_id = 1
  AND status = b'1'
  AND deleted = b'0';

COMMIT;

-- 执行器必须确认 execution_result = PASS；否则停止并进行人工复核。
