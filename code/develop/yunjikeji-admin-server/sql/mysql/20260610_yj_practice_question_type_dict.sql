-- 练习题题型字典初始化
-- 适用场景：已有库补齐练习题目管理题型下拉数据
-- 幂等口径：按 system_dict_type.type 与 system_dict_data(dict_type, value) 判重

ALTER TABLE `yj_practice_exercises`
  MODIFY COLUMN `question_type` varchar(32) NULL COMMENT '题型（字典表 yj_practice_question_type）';

ALTER TABLE `yj_practice_exercises_answer`
  MODIFY COLUMN `question_type` varchar(32) NULL COMMENT '题型（字典表 yj_practice_question_type）';

ALTER TABLE `yj_practice_exercises_answer_child`
  MODIFY COLUMN `question_type` varchar(32) NULL COMMENT '题型（字典表 yj_practice_question_type）';

INSERT INTO `system_dict_type` (`name`, `type`, `status`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `deleted_time`)
SELECT '练习题题型', 'yj_practice_question_type', 0, '练习题目管理题型：单选题/多选题/判断题', 'admin', NOW(), 'admin', NOW(), b'0', NULL
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_type` WHERE `type` = 'yj_practice_question_type' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 1, '单选题', 'single_choice', 'yj_practice_question_type', 0, 'primary', '', '参考 yunjikeji-server 练习题型 single_choice', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_practice_question_type' AND `value` = 'single_choice' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 2, '多选题', 'multiple_choice', 'yj_practice_question_type', 0, 'success', '', '参考 yunjikeji-server 练习题型 multiple_choice', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_practice_question_type' AND `value` = 'multiple_choice' AND `deleted` = b'0'
);

INSERT INTO `system_dict_data` (`sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 3, '判断题', 'judge', 'yj_practice_question_type', 0, 'warning', '', '参考 yunjikeji-server 练习题型 judge', 'admin', NOW(), 'admin', NOW(), b'0'
WHERE NOT EXISTS (
  SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'yj_practice_question_type' AND `value` = 'judge' AND `deleted` = b'0'
);

UPDATE `yj_practice_exercises`
SET `question_type` = CASE `question_type`
  WHEN 'single' THEN 'single_choice'
  WHEN '2' THEN 'single_choice'
  WHEN 'multi' THEN 'multiple_choice'
  WHEN 'multiple' THEN 'multiple_choice'
  WHEN '3' THEN 'multiple_choice'
  WHEN '4' THEN 'judge'
  ELSE `question_type`
END
WHERE `question_type` IN ('single', '2', 'multi', 'multiple', '3', '4');

UPDATE `yj_practice_exercises_answer`
SET `question_type` = CASE `question_type`
  WHEN 'single' THEN 'single_choice'
  WHEN '2' THEN 'single_choice'
  WHEN 'multi' THEN 'multiple_choice'
  WHEN 'multiple' THEN 'multiple_choice'
  WHEN '3' THEN 'multiple_choice'
  WHEN '4' THEN 'judge'
  ELSE `question_type`
END
WHERE `question_type` IN ('single', '2', 'multi', 'multiple', '3', '4');

UPDATE `yj_practice_exercises_answer_child`
SET `question_type` = CASE `question_type`
  WHEN 'single' THEN 'single_choice'
  WHEN '2' THEN 'single_choice'
  WHEN 'multi' THEN 'multiple_choice'
  WHEN 'multiple' THEN 'multiple_choice'
  WHEN '3' THEN 'multiple_choice'
  WHEN '4' THEN 'judge'
  ELSE `question_type`
END
WHERE `question_type` IN ('single', '2', 'multi', 'multiple', '3', '4');
