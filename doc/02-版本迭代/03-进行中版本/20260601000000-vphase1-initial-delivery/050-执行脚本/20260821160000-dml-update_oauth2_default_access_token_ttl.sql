-- ============================================
-- 脚本类型：dml
-- 脚本描述：将默认 OAuth2 客户端访问令牌有效期调整为 3 天
-- 创建日期：2026-08-21 16:00:00
-- 作者：Codex
-- 影响范围：system_oauth2_client.client_id='default'、未过期的 default 访问令牌
-- 执行环境：测试环境
-- ============================================

SET @target_access_token_ttl_seconds := 3 * 24 * 60 * 60;
SET @target_access_token_expires_time := DATE_ADD(NOW(), INTERVAL @target_access_token_ttl_seconds SECOND);

-- 前置检查：确认默认客户端当前有效期，以及当前未过期访问令牌数量。
SELECT
  id,
  client_id,
  access_token_validity_seconds,
  refresh_token_validity_seconds,
  deleted
FROM system_oauth2_client
WHERE client_id = 'default';

SELECT
  COUNT(1) AS active_default_access_token_count
FROM system_oauth2_access_token
WHERE client_id = 'default'
  AND expires_time > NOW();

-- 主要变更：后续登录/刷新签发的 access token 有效期改为 259200 秒（3 天）。
UPDATE system_oauth2_client
SET access_token_validity_seconds = @target_access_token_ttl_seconds,
    updater = 'codex',
    update_time = NOW()
WHERE client_id = 'default'
  AND deleted = b'0';

-- 兼容当前仍未过期的会话：把它们延长到从执行时刻起 3 天，避免用户短时间内继续掉线。
UPDATE system_oauth2_access_token
SET expires_time = @target_access_token_expires_time,
    updater = 'codex',
    update_time = NOW()
WHERE client_id = 'default'
  AND expires_time > NOW()
  AND expires_time < @target_access_token_expires_time;

-- 后置校验：默认客户端 access token 有效期应为 259200 秒。
SELECT
  id,
  client_id,
  access_token_validity_seconds,
  refresh_token_validity_seconds,
  deleted
FROM system_oauth2_client
WHERE client_id = 'default';

SELECT
  COUNT(1) AS active_default_access_token_count,
  MIN(expires_time) AS min_active_expires_time,
  MAX(expires_time) AS max_active_expires_time
FROM system_oauth2_access_token
WHERE client_id = 'default'
  AND expires_time > NOW();

-- 生效说明：system_oauth2_client 使用 Spring Cache 缓存，若服务已运行，请重启后端或清理 oauth_client 缓存后生效。
