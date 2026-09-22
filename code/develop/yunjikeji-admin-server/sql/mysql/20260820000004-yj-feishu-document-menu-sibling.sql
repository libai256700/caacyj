-- 修正已部署环境中的菜单层级：飞书文档采集与采集配置同级。
UPDATE `system_menu` child_menu
JOIN `system_menu` parent_menu
  ON parent_menu.`name` = '招聘信息管理'
 AND parent_menu.`deleted` = b'0'
SET child_menu.`parent_id` = parent_menu.`id`,
    child_menu.`sort` = 30,
    child_menu.`updater` = 'admin',
    child_menu.`update_time` = NOW()
WHERE child_menu.`path` = 'feishu-document'
  AND child_menu.`deleted` = b'0';
