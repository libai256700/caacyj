-- ============================================
-- 脚本类型：dml
-- 脚本描述：回滚默认 OAuth2 客户端访问令牌有效期为 1800 秒
-- 创建日期：2026-08-21 16:01:00
-- 作者：Codex
-- 影响范围：system_oauth2_client.client_id='default'
-- 执行环境：测试环境
-- ============================================

-- 说明：仅回滚默认客户端后续签发 access token 的有效期，不强制缩短已签发且未过期的访问令牌。
UPDATE system_oauth2_client
SET access_token_validity_seconds = 1800,
    updater = 'codex',
    update_time = NOW()
WHERE client_id = 'default'
  AND deleted = b'0';

SELECT
  id,
  client_id,
  access_token_validity_seconds,
  refresh_token_validity_seconds,
  deleted
FROM system_oauth2_client
WHERE client_id = 'default';

-- 生效说明：system_oauth2_client 使用 Spring Cache 缓存，若服务已运行，请重启后端或清理 oauth_client 缓存后生效。
