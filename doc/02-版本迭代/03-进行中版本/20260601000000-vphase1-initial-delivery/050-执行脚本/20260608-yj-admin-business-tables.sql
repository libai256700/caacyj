-- 版本：vphase1-initial-delivery
-- 目标：新增云技科技飞行学院后台管理平台一期业务表
-- 数据库：MySQL 8.x
-- 执行说明：脚本幂等，可重复执行；字段按 doc/数据库表结构说明.md 的补充表结构修正明显录入错误后落库。

CREATE TABLE IF NOT EXISTS `yj_audit_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '企业审核编号',
  `user_id` bigint DEFAULT NULL COMMENT '提交人用户编号',
  `name` varchar(30) NOT NULL COMMENT '企业名称',
  `legal_person` varchar(30) DEFAULT NULL COMMENT '法人姓名',
  `contact_name` varchar(30) NOT NULL COMMENT '联系人',
  `contact_mobile` varchar(30) NOT NULL COMMENT '联系手机',
  `audit_status` tinyint NOT NULL DEFAULT 0 COMMENT '审核状态：0待审核 1审核中 2已通过 3已驳回',
  `audit_reason` varchar(500) DEFAULT NULL COMMENT '驳回原因',
  `audit_time` datetime DEFAULT NULL COMMENT '审核时间',
  `audit_user_id` bigint DEFAULT NULL COMMENT '审核人',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_audit_info_user_id` (`user_id`),
  KEY `idx_yj_audit_info_status` (`audit_status`),
  KEY `idx_yj_audit_info_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='企业注册审核';

CREATE TABLE IF NOT EXISTS `yj_audit_info_attachment` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '存储信息编号',
  `company_id` bigint NOT NULL COMMENT '企业审核编号',
  `user_id` bigint DEFAULT NULL COMMENT '提交人',
  `file_path` varchar(500) NOT NULL COMMENT 'BOS存储路径或令牌',
  `file_name` varchar(255) DEFAULT NULL COMMENT '文件名',
  `file_type` varchar(64) DEFAULT NULL COMMENT '文件类型',
  `tenant_id` bigint DEFAULT NULL COMMENT '租户编号（自测结果共享表可为空）',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_audit_attachment_company_id` (`company_id`),
  KEY `idx_yj_audit_attachment_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='企业注册审核附件';

CREATE TABLE IF NOT EXISTS `yj_student_audit_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '审核信息编号',
  `company_id` bigint NOT NULL COMMENT '企业编号',
  `user_id` bigint NOT NULL COMMENT '学员账号编号',
  `audit_status` tinyint NOT NULL DEFAULT 0 COMMENT '学员账号审核状态：0待审核 1已通过 2已拒绝',
  `audit_reason` varchar(500) DEFAULT NULL COMMENT '审核原因',
  `audit_time` datetime DEFAULT NULL COMMENT '审核时间',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_student_audit_company_id` (`company_id`),
  KEY `idx_yj_student_audit_user_id` (`user_id`),
  KEY `idx_yj_student_audit_status` (`audit_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学员账号审核';

CREATE TABLE IF NOT EXISTS `yj_practice_category` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '分类信息编号',
  `category_name` varchar(100) NOT NULL COMMENT '分类名称',
  `category_status` bit(1) NOT NULL DEFAULT b'1' COMMENT '分类状态',
  `field_type` varchar(10) DEFAULT NULL COMMENT '所属领域',
  `sort_no` int NOT NULL DEFAULT 0 COMMENT '排序号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_practice_category_name` (`category_name`),
  KEY `idx_yj_practice_category_status` (`category_status`),
  KEY `idx_yj_practice_category_sort` (`sort_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='练习分类管理';

CREATE TABLE IF NOT EXISTS `yj_practice_exercises` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '习题编号',
  `category_id` bigint NOT NULL COMMENT '所属分类',
  `question_stem` varchar(800) NOT NULL COMMENT '题干摘要',
  `question_type` varchar(2) NOT NULL COMMENT '题型',
  `question_status` bit(1) NOT NULL DEFAULT b'1' COMMENT '状态',
  `score` int NOT NULL DEFAULT 0 COMMENT '分值',
  `sort_no` int NOT NULL DEFAULT 0 COMMENT '排序号',
  `correct_memo` varchar(500) DEFAULT NULL COMMENT '正确解析',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_practice_exercises_category_id` (`category_id`),
  KEY `idx_yj_practice_exercises_type` (`question_type`),
  KEY `idx_yj_practice_exercises_status` (`question_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='练习题目管理';

CREATE TABLE IF NOT EXISTS `yj_practice_exercises_answer` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '答案编号',
  `exercises_id` bigint NOT NULL COMMENT '所属题目',
  `question_type` varchar(2) NOT NULL COMMENT '题型',
  `answer_code` varchar(10) DEFAULT NULL COMMENT '答案编号',
  `answer_content` varchar(255) NOT NULL COMMENT '答案正文',
  `is_correct` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否正确答案',
  `sort_no` int NOT NULL DEFAULT 0 COMMENT '排序号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_practice_answer_exercises_id` (`exercises_id`),
  KEY `idx_yj_practice_answer_code` (`answer_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='练习答案管理';

CREATE TABLE IF NOT EXISTS `yj_practice_exercises_answer_child` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '二级答案编号',
  `answer_id` bigint NOT NULL COMMENT '答案编号',
  `question_type` varchar(2) NOT NULL COMMENT '题型',
  `answer_content` varchar(255) NOT NULL COMMENT '答案正文',
  `is_correct` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否正确答案',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_practice_answer_child_answer_id` (`answer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='练习二级答案管理';

CREATE TABLE IF NOT EXISTS `yj_user_practice_exercises_record` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '记录编号',
  `user_id` bigint NOT NULL COMMENT '所属学员',
  `category_id` bigint NOT NULL COMMENT '分类编号',
  `total_score` int NOT NULL DEFAULT 0 COMMENT '总分',
  `correct_count` int NOT NULL DEFAULT 0 COMMENT '对题数',
  `wrong_count` int NOT NULL DEFAULT 0 COMMENT '错题数',
  `field_type` varchar(10) DEFAULT NULL COMMENT '所属领域',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_practice_record_user_id` (`user_id`),
  KEY `idx_yj_practice_record_category_id` (`category_id`),
  KEY `idx_yj_practice_record_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='练习记录表';

CREATE TABLE IF NOT EXISTS `yj_user_practice_exercises_record_detail` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '详情编号',
  `record_id` bigint NOT NULL COMMENT '记录编号',
  `exercises_id` bigint NOT NULL COMMENT '题目编号',
  `answer_code` varchar(20) DEFAULT NULL COMMENT '所选答案',
  `correct_answer_code` varchar(20) DEFAULT NULL COMMENT '正确答案',
  `is_correct` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否做对',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_practice_record_detail_record_id` (`record_id`),
  KEY `idx_yj_practice_record_detail_exercises_id` (`exercises_id`),
  KEY `idx_yj_practice_record_detail_correct` (`is_correct`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='练习记录详情表';

CREATE TABLE IF NOT EXISTS `yj_post` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '采集岗位编号',
  `name` varchar(100) NOT NULL COMMENT '采集岗位名称',
  `company_id` bigint DEFAULT NULL COMMENT '所属企业',
  `source_code` varchar(10) DEFAULT NULL COMMENT '所属来源',
  `salary_range` varchar(100) DEFAULT NULL COMMENT '薪资范围',
  `work_area` varchar(100) DEFAULT NULL COMMENT '工作区域',
  `publish_date` varchar(10) DEFAULT NULL COMMENT '发布时间',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '是否启用',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_post_name` (`name`),
  KEY `idx_yj_post_company_id` (`company_id`),
  KEY `idx_yj_post_source_code` (`source_code`),
  KEY `idx_yj_post_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位采集表';

CREATE TABLE IF NOT EXISTS `yj_post_collection_task` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '采集任务编号',
  `name` varchar(255) NOT NULL COMMENT '任务名称',
  `collection_channel` varchar(20) DEFAULT NULL COMMENT '采集渠道',
  `collection_time` date DEFAULT NULL COMMENT '采集时间',
  `collection_count_rule` int DEFAULT NULL COMMENT '采集频次',
  `collection_key` varchar(100) DEFAULT NULL COMMENT '采集关键词',
  `collection_num` int NOT NULL DEFAULT 0 COMMENT '采集量级',
  `last_execute_time` datetime DEFAULT NULL COMMENT '最近执行时间',
  `last_execute_result` varchar(255) DEFAULT NULL COMMENT '最近执行结果',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '是否启用',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_post_collection_task_name` (`name`),
  KEY `idx_yj_post_collection_task_channel` (`collection_channel`),
  KEY `idx_yj_post_collection_task_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采集任务管理';

CREATE TABLE IF NOT EXISTS `yj_agreement_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '协议编号',
  `name` varchar(255) NOT NULL COMMENT '协议名称',
  `type` varchar(20) NOT NULL COMMENT '协议类型',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '是否启用',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_agreement_info_type` (`type`),
  KEY `idx_yj_agreement_info_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='协议表';

CREATE TABLE IF NOT EXISTS `yj_agreement_detail_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '协议详情编号',
  `agreement_info_id` bigint NOT NULL COMMENT '协议编号',
  `version` varchar(20) NOT NULL COMMENT '版本号',
  `content` mediumtext COMMENT '正文',
  `publish_status` tinyint NOT NULL DEFAULT 0 COMMENT '发布状态：0草稿 1已发布 2已撤回',
  `publish_time` datetime DEFAULT NULL COMMENT '发布时间',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_agreement_detail_info_id` (`agreement_info_id`),
  KEY `idx_yj_agreement_detail_publish_status` (`publish_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='协议详情表';

CREATE TABLE IF NOT EXISTS `yj_session_message` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '会话编号',
  `session_from` bigint NOT NULL COMMENT '发起人编号',
  `session_to` bigint NOT NULL COMMENT '接收人编号',
  `last_message_content` varchar(500) DEFAULT NULL COMMENT '最近消息摘要',
  `last_message_time` datetime DEFAULT NULL COMMENT '最近消息时间',
  `unread_count` int NOT NULL DEFAULT 0 COMMENT '未读数量',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_session_message_from` (`session_from`),
  KEY `idx_yj_session_message_to` (`session_to`),
  KEY `idx_yj_session_message_last_time` (`last_message_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话消息表';

CREATE TABLE IF NOT EXISTS `yj_message_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '消息编号',
  `session_id` bigint NOT NULL COMMENT '会话编号',
  `session_from` bigint NOT NULL COMMENT '发起人编号',
  `session_to` bigint NOT NULL COMMENT '接收人编号',
  `message_type` tinyint NOT NULL DEFAULT 1 COMMENT '消息类型：1文本 2图片 3视频',
  `content` varchar(4000) DEFAULT NULL COMMENT '正文',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_message_info_session_id` (`session_id`),
  KEY `idx_yj_message_info_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户消息表';

CREATE TABLE IF NOT EXISTS `yj_collection_task_log` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '采集任务日志编号',
  `task_id` bigint NOT NULL COMMENT '采集任务编号',
  `execute_time` datetime NOT NULL COMMENT '执行时间',
  `execute_result` varchar(255) DEFAULT NULL COMMENT '执行结果',
  `success_count` int NOT NULL DEFAULT 0 COMMENT '成功采集数量',
  `fail_reason` varchar(500) DEFAULT NULL COMMENT '失败原因',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_collection_task_log_task_id` (`task_id`),
  KEY `idx_yj_collection_task_log_execute_time` (`execute_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采集任务执行日志';

CREATE TABLE IF NOT EXISTS `yj_assessment_question` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '自测题目编号',
  `title` varchar(255) NOT NULL COMMENT '题目标题',
  `question_type` varchar(2) NOT NULL COMMENT '题目类型',
  `question_content` varchar(1000) DEFAULT NULL COMMENT '题目内容',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '状态',
  `sort_no` int NOT NULL DEFAULT 0 COMMENT '排序号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_assessment_question_title` (`title`),
  KEY `idx_yj_assessment_question_type` (`question_type`),
  KEY `idx_yj_assessment_question_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自测题库题目';

CREATE TABLE IF NOT EXISTS `yj_assessment_answer` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '自测答案编号',
  `question_id` bigint NOT NULL COMMENT '自测题目编号',
  `answer_code` varchar(10) DEFAULT NULL COMMENT '答案编号',
  `answer_content` varchar(255) NOT NULL COMMENT '答案正文',
  `is_correct` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否标准答案',
  `sort_no` int NOT NULL DEFAULT 0 COMMENT '排序号',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_assessment_answer_question_id` (`question_id`),
  KEY `idx_yj_assessment_answer_code` (`answer_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自测题库答案';

CREATE TABLE IF NOT EXISTS `yj_assessment_result` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '自测结果编号',
  `user_id` bigint NOT NULL COMMENT '学员编号',
  `assessment_time` datetime NOT NULL COMMENT '自测时间',
  `result_summary` varchar(500) DEFAULT NULL COMMENT '结果摘要',
  `recommend_direction` varchar(255) DEFAULT NULL COMMENT '推荐方向',
  `report_content` mediumtext COMMENT 'AI评估报告',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_assessment_result_user_id` (`user_id`),
  KEY `idx_yj_assessment_result_time` (`assessment_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自测结果管理';

CREATE TABLE IF NOT EXISTS `yj_knowledge_base` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '知识库编号',
  `name` varchar(255) NOT NULL COMMENT '知识库名称',
  `item_count` int NOT NULL DEFAULT 0 COMMENT '条目数量',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '状态',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_knowledge_base_name` (`name`),
  KEY `idx_yj_knowledge_base_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库管理';

CREATE TABLE IF NOT EXISTS `yj_knowledge_item` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '知识条目编号',
  `knowledge_base_id` bigint NOT NULL COMMENT '知识库编号',
  `title` varchar(255) NOT NULL COMMENT '条目标题',
  `content_type` varchar(20) NOT NULL COMMENT '内容类型：text/pdf/video/audio',
  `content_url` varchar(500) DEFAULT NULL COMMENT '内容文件地址',
  `content_text` mediumtext COMMENT '文本内容',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '状态',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_knowledge_item_base_id` (`knowledge_base_id`),
  KEY `idx_yj_knowledge_item_title` (`title`),
  KEY `idx_yj_knowledge_item_type` (`content_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库条目';

CREATE TABLE IF NOT EXISTS `yj_agent_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '智能体编号',
  `agent_id` varchar(128) DEFAULT NULL COMMENT 'QwenPaw agent id',
  `name` varchar(255) NOT NULL COMMENT '智能体名称',
  `knowledge_base_id` bigint DEFAULT NULL COMMENT '关联知识库',
  `prompt_config` mediumtext COMMENT '提示词配置',
  `reply_strategy` varchar(500) DEFAULT NULL COMMENT '回复策略',
  `status` bit(1) NOT NULL DEFAULT b'1' COMMENT '启用状态',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`),
  KEY `idx_yj_agent_info_agent_id` (`agent_id`),
  KEY `idx_yj_agent_info_name` (`name`),
  KEY `idx_yj_agent_info_knowledge_base_id` (`knowledge_base_id`),
  KEY `idx_yj_agent_info_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能体管理';
