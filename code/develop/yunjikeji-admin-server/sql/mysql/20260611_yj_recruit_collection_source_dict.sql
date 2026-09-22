-- 招聘采集来源字典初始化
-- 适用场景：已有库补齐招聘信息管理-采集配置-采集来源下拉数据
-- 幂等口径：按 system_dict_type.type 与 system_dict_data(dict_type, value) 判重

INSERT INTO `system_dict_type` (`name`, `type`, `status`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `deleted_time`)
SELECT '招聘采集来源', 'yj_recruit_collection_source', 0, '招聘信息管理采集配置来源：BOSS直聘/猎聘/智联招聘/国聘', 'admin', NOW(), 'admin', NOW(), b'0', NULL
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_type` WHERE `type` = 'yj_recruit_collection_source' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 1, 'BOSS直聘', 'boss_zhipin', 'yj_recruit_collection_source', 0, 'primary', '', '招聘信息采集来源：BOSS直聘', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_recruit_collection_source' AND `value` = 'boss_zhipin' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 2, '猎聘', 'liepin', 'yj_recruit_collection_source', 0, 'success', '', '招聘信息采集来源：猎聘', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_recruit_collection_source' AND `value` = 'liepin' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 3, '智联招聘', 'zhilian', 'yj_recruit_collection_source', 0, 'warning', '', '招聘信息采集来源：智联招聘', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_recruit_collection_source' AND `value` = 'zhilian' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 4, '国聘', 'guopin', 'yj_recruit_collection_source', 0, 'info', '', '招聘信息采集来源：国聘', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_recruit_collection_source' AND `value` = 'guopin' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 5, '前程无忧', '51job', 'yj_recruit_collection_source', 0, 'default', '', '招聘信息采集来源：前程无忧', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_recruit_collection_source' AND `value` = '51job' AND `deleted` = b'0'
);

-- 执行后校验：应返回前程无忧字典项，value 与后端渠道 code 保持一致
SELECT `sort`, `label`, `value`, `dict_type`, `status`
FROM `system_dict_data`
WHERE `dict_type` = 'yj_recruit_collection_source'
  AND `value` = '51job'
  AND `deleted` = b'0';
