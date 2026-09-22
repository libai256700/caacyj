-- Purpose: upsert test knowledge base rows for the admin knowledge-base page.
-- Target table: yj_knowledge_base.
-- Status: not executed.
-- Safety gate: keep @tenant_id as NULL until the Dev/Test tenant_id is confirmed.
-- If @tenant_id is not replaced, the NOT NULL temporary table insert fails before any write to yj_knowledge_base.

SET @tenant_id = /* TODO: replace with confirmed Dev/Test tenant_id before execution */ NULL;
SET @operator = '1';
SET @now = NOW();

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
  creator,
  create_time,
  updater,
  update_time,
  deleted
)
SELECT '云技科技原知识库', 0, b'1', @tenant_id, @operator, @now, @operator, @now, b'0'
WHERE NOT EXISTS (
  SELECT 1
  FROM yj_knowledge_base
  WHERE name = '云技科技原知识库'
    AND tenant_id = @tenant_id
    AND deleted = b'0'
);

UPDATE yj_knowledge_base
SET status = b'1',
    updater = @operator,
    update_time = @now
WHERE name = '云技科技原知识库'
  AND tenant_id = @tenant_id
  AND deleted = b'0';

INSERT INTO yj_knowledge_base (
  name,
  item_count,
  status,
  tenant_id,
  creator,
  create_time,
  updater,
  update_time,
  deleted
)
SELECT '考试知识库', 0, b'1', @tenant_id, @operator, @now, @operator, @now, b'0'
WHERE NOT EXISTS (
  SELECT 1
  FROM yj_knowledge_base
  WHERE name = '考试知识库'
    AND tenant_id = @tenant_id
    AND deleted = b'0'
);

UPDATE yj_knowledge_base
SET status = b'1',
    updater = @operator,
    update_time = @now
WHERE name = '考试知识库'
  AND tenant_id = @tenant_id
  AND deleted = b'0';

SELECT id, name, item_count, status, tenant_id, deleted
FROM yj_knowledge_base
WHERE name IN ('云技科技原知识库', '考试知识库')
  AND tenant_id = @tenant_id
  AND deleted = b'0'
ORDER BY FIELD(name, '云技科技原知识库', '考试知识库');
