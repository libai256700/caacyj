-- 用途：为管理平台“知识库管理”页面补齐两条测试入口数据。
-- 目标表：yj_knowledge_base。
-- 状态：未执行。
-- 安全门禁：执行前必须确认目标环境不是生产库，并替换 @tenant_id。
-- @tenant_id 保持 NULL 时，临时表 NOT NULL 写入会先失败，避免误写 yj_knowledge_base。

SET @tenant_id = NULL;

CREATE TEMPORARY TABLE IF NOT EXISTS _yj_kb_tenant_guard (
  tenant_id BIGINT NOT NULL
);
INSERT INTO _yj_kb_tenant_guard (tenant_id) VALUES (@tenant_id);
DROP TEMPORARY TABLE _yj_kb_tenant_guard;

INSERT INTO yj_knowledge_base (
  name,
  item_count,
  status,
  tenant_id,
  deleted,
  create_time,
  update_time
)
SELECT
  '云技科技原知识库',
  0,
  b'1',
  @tenant_id,
  b'0',
  NOW(),
  NOW()
WHERE NOT EXISTS (
  SELECT 1
  FROM yj_knowledge_base
  WHERE name = '云技科技原知识库'
    AND tenant_id = @tenant_id
    AND deleted = b'0'
);

UPDATE yj_knowledge_base
SET
  item_count = COALESCE(item_count, 0),
  status = b'1',
  update_time = NOW()
WHERE name = '云技科技原知识库'
  AND tenant_id = @tenant_id
  AND deleted = b'0';

INSERT INTO yj_knowledge_base (
  name,
  item_count,
  status,
  tenant_id,
  deleted,
  create_time,
  update_time
)
SELECT
  '考试知识库',
  0,
  b'1',
  @tenant_id,
  b'0',
  NOW(),
  NOW()
WHERE NOT EXISTS (
  SELECT 1
  FROM yj_knowledge_base
  WHERE name = '考试知识库'
    AND tenant_id = @tenant_id
    AND deleted = b'0'
);

UPDATE yj_knowledge_base
SET
  item_count = COALESCE(item_count, 0),
  status = b'1',
  update_time = NOW()
WHERE name = '考试知识库'
  AND tenant_id = @tenant_id
  AND deleted = b'0';
