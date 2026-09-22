-- 用途：将管理平台“知识库管理”菜单切换到专属页面组件。
-- 状态：未执行。
-- 说明：避免在公共 yj/resource/index.vue 中放入知识库专属测试逻辑。

UPDATE system_menu
SET
  component = 'yj/knowledge-base/index.vue',
  component_name = 'YjKnowledgeBase',
  update_time = NOW()
WHERE name = '知识库管理'
  AND deleted = b'0';
