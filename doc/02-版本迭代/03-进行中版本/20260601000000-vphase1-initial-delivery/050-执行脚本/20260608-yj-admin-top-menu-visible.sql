-- 版本：vphase1-initial-delivery
-- 目标：后台管理平台顶级菜单只保留首页、系统管理、云技业务、IM 即时通讯
-- 执行说明：
-- 1. 首页为前端固定路由，不在 system_menu 动态菜单表中。
-- 2. 本脚本只调整 parent_id = 0 的顶级动态菜单 visible 字段。
-- 3. 保留菜单：系统管理(id=1)、云技业务(id=900000)、IM 即时通讯(id=6500)。
-- 4. 不修改系统自带租户、组织、用户、角色、权限页面。

UPDATE `system_menu`
SET `visible` = CASE
    WHEN `id` IN (1, 900000, 6500) THEN b'1'
    ELSE b'0'
  END,
  `updater` = 'admin',
  `update_time` = NOW()
WHERE `parent_id` = 0
  AND `deleted` = b'0';

SELECT `id`, `name`, `path`, `visible`
FROM `system_menu`
WHERE `parent_id` = 0
  AND `deleted` = b'0'
ORDER BY `sort`, `id`;
