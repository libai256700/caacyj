-- 在“招聘信息管理”下增加飞书文档采集概览菜单，与“采集配置”保持同级。
-- 使用父菜单名称定位，避免依赖不同环境中的自增菜单 ID；重复执行不会重复创建。
INSERT INTO `system_menu`
(`name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT '飞书文档采集', '', 2, 30, parent_menu.id, 'feishu-document', 'ep:document',
       'yj/feishu-document/index', 'YjFeishuDocument', 0, b'1', b'1', b'1', 'admin', NOW(), 'admin', NOW(), b'0'
FROM `system_menu` parent_menu
WHERE parent_menu.`name` = '招聘信息管理'
  AND parent_menu.`deleted` = b'0'
  AND NOT EXISTS (
      SELECT 1
      FROM `system_menu` existing_menu
      WHERE existing_menu.`path` = 'feishu-document'
        AND existing_menu.`deleted` = b'0'
  )
LIMIT 1;
