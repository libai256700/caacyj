-- Add Feishu folder as the supported recruitment collection source.
-- Idempotent: safe to execute more than once.

INSERT INTO `system_dict_type`
  (`name`, `type`, `status`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `deleted_time`)
SELECT '招聘采集来源', 'yj_recruit_collection_source', 0,
       '招聘信息管理采集配置来源：飞书公开目录及招聘平台', 'admin', NOW(), 'admin', NOW(), b'0', NULL
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_type`
  WHERE `type` = 'yj_recruit_collection_source' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data`
  (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`,
   `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 6, '飞书目录', 'feishu_folder', 'yj_recruit_collection_source', 0, 'success', '',
       '从配置的飞书目录读取岗位文档并进行 AI 结构化采集', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data`
  WHERE `dict_type` = 'yj_recruit_collection_source'
    AND `value` = 'feishu_folder'
    AND `deleted` = b'0'
);
