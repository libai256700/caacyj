-- 协议类型字典初始化
-- 适用场景：已存在协议管理页面，需要补齐协议类型字典下拉数据
-- 幂等口径：按 system_dict_type.type 与 system_dict_data(dict_type, value) 去重

INSERT INTO `system_dict_type` (`name`, `type`, `status`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `deleted_time`)
SELECT '协议类型', 'yj_agreement_type', 0, '协议管理协议类型：培训协议/管理协议/设备协议/考试协议/训练协议', 'admin', NOW(), 'admin', NOW(), b'0', NULL
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_type` WHERE `type` = 'yj_agreement_type' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 1, '培训协议', '01', 'yj_agreement_type', 0, 'primary', '', '协议管理协议类型：培训协议', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_agreement_type' AND `value` = '01' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 2, '管理协议', '02', 'yj_agreement_type', 0, 'success', '', '协议管理协议类型：管理协议', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_agreement_type' AND `value` = '02' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 3, '设备协议', '03', 'yj_agreement_type', 0, 'warning', '', '协议管理协议类型：设备协议', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_agreement_type' AND `value` = '03' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 4, '考试协议', '04', 'yj_agreement_type', 0, 'info', '', '协议管理协议类型：考试协议', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_agreement_type' AND `value` = '04' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 5, '训练协议', '05', 'yj_agreement_type', 0, 'danger', '', '协议管理协议类型：训练协议', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_agreement_type' AND `value` = '05' AND `deleted` = b'0'
);
