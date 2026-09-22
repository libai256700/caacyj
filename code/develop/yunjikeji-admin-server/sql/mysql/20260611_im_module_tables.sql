-- IM module table initialization for MySQL.
-- Fixes runtime failures such as: Table 'yunjikeji.im_sensitive_word' doesn't exist.

CREATE TABLE IF NOT EXISTS `im_private_message` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `client_message_id` varchar(64) DEFAULT NULL COMMENT 'Client message ID for idempotency',
  `sender_id` bigint NOT NULL COMMENT 'Sender user ID',
  `receiver_id` bigint NOT NULL COMMENT 'Receiver user ID',
  `type` smallint NOT NULL COMMENT 'Message type',
  `content` varchar(8192) DEFAULT NULL COMMENT 'Message content JSON',
  `status` tinyint NOT NULL COMMENT 'Message status',
  `send_time` datetime NOT NULL COMMENT 'Send time',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_private_message_sender_client` (`sender_id`, `client_message_id`, `tenant_id`),
  KEY `idx_im_private_message_receiver_time` (`receiver_id`, `send_time`),
  KEY `idx_im_private_message_sender_time` (`sender_id`, `send_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM private message';

CREATE TABLE IF NOT EXISTS `im_group_message` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `client_message_id` varchar(64) DEFAULT NULL COMMENT 'Client message ID for idempotency',
  `sender_id` bigint NOT NULL COMMENT 'Sender user ID',
  `group_id` bigint NOT NULL COMMENT 'Group ID',
  `type` smallint NOT NULL COMMENT 'Message type',
  `content` varchar(8192) DEFAULT NULL COMMENT 'Message content JSON',
  `status` tinyint NOT NULL COMMENT 'Message status',
  `send_time` datetime NOT NULL COMMENT 'Send time',
  `receiver_user_ids` varchar(1024) DEFAULT NULL COMMENT 'Target receiver user IDs, comma separated',
  `at_user_ids` varchar(1024) DEFAULT NULL COMMENT 'Mentioned user IDs, comma separated',
  `receipt_status` tinyint NOT NULL DEFAULT 0 COMMENT 'Receipt status',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_group_message_sender_client` (`sender_id`, `client_message_id`, `tenant_id`),
  KEY `idx_im_group_message_group_time` (`group_id`, `send_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM group message';

CREATE TABLE IF NOT EXISTS `im_group` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(64) NOT NULL COMMENT 'Group name',
  `owner_user_id` bigint NOT NULL COMMENT 'Owner user ID',
  `avatar` varchar(512) DEFAULT NULL COMMENT 'Group avatar',
  `notice` varchar(2048) DEFAULT NULL COMMENT 'Group notice',
  `join_approval` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Join approval required',
  `banned` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Banned flag',
  `banned_reason` varchar(512) DEFAULT NULL COMMENT 'Banned reason',
  `banned_time` datetime DEFAULT NULL COMMENT 'Banned time',
  `status` tinyint NOT NULL COMMENT 'Group status',
  `dissolved_time` datetime DEFAULT NULL COMMENT 'Dissolved time',
  `muted_all` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Mute all flag',
  `pinned_message_ids` varchar(128) DEFAULT NULL COMMENT 'Pinned message IDs, comma separated',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  KEY `idx_im_group_owner` (`owner_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM group';

CREATE TABLE IF NOT EXISTS `im_group_member` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `group_id` bigint NOT NULL COMMENT 'Group ID',
  `user_id` bigint NOT NULL COMMENT 'User ID',
  `display_user_name` varchar(64) DEFAULT NULL COMMENT 'Display name in group',
  `group_remark` varchar(64) DEFAULT NULL COMMENT 'Group remark',
  `silent` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Silent flag',
  `status` tinyint NOT NULL COMMENT 'Member status',
  `role` tinyint NOT NULL DEFAULT 3 COMMENT 'Member role',
  `join_time` datetime DEFAULT NULL COMMENT 'Join time',
  `add_source` tinyint DEFAULT NULL COMMENT 'Add source',
  `inviter_user_id` bigint DEFAULT NULL COMMENT 'Inviter user ID',
  `quit_time` datetime DEFAULT NULL COMMENT 'Quit time',
  `mute_end_time` datetime DEFAULT NULL COMMENT 'Mute end time',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_group_member` (`group_id`, `user_id`, `tenant_id`),
  KEY `idx_im_group_member_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM group member';

CREATE TABLE IF NOT EXISTS `im_friend` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `user_id` bigint NOT NULL COMMENT 'User ID',
  `friend_user_id` bigint NOT NULL COMMENT 'Friend user ID',
  `silent` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Silent flag',
  `display_name` varchar(64) NOT NULL DEFAULT '' COMMENT 'Display name',
  `add_source` tinyint DEFAULT NULL COMMENT 'Add source',
  `pinned` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Pinned flag',
  `blocked` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Blocked flag',
  `status` tinyint NOT NULL COMMENT 'Friend status',
  `add_time` datetime DEFAULT NULL COMMENT 'Add time',
  `delete_time` datetime DEFAULT NULL COMMENT 'Delete time',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_friend` (`user_id`, `friend_user_id`, `tenant_id`),
  KEY `idx_im_friend_friend_user` (`friend_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM friend';

CREATE TABLE IF NOT EXISTS `im_friend_request` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `from_user_id` bigint NOT NULL COMMENT 'Requester user ID',
  `to_user_id` bigint NOT NULL COMMENT 'Target user ID',
  `apply_content` varchar(255) DEFAULT NULL COMMENT 'Apply content',
  `display_name` varchar(64) DEFAULT NULL COMMENT 'Display name',
  `add_source` tinyint DEFAULT NULL COMMENT 'Add source',
  `handle_result` tinyint NOT NULL DEFAULT 0 COMMENT 'Handle result',
  `handle_content` varchar(255) DEFAULT NULL COMMENT 'Handle content',
  `handle_time` datetime DEFAULT NULL COMMENT 'Handle time',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_friend_request` (`from_user_id`, `to_user_id`, `tenant_id`),
  KEY `idx_im_friend_request_to_user` (`to_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM friend request';

CREATE TABLE IF NOT EXISTS `im_group_request` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `group_id` bigint NOT NULL COMMENT 'Group ID',
  `user_id` bigint NOT NULL COMMENT 'Applicant or invited user ID',
  `inviter_user_id` bigint DEFAULT NULL COMMENT 'Inviter user ID',
  `apply_content` varchar(255) DEFAULT NULL COMMENT 'Apply content',
  `add_source` tinyint DEFAULT NULL COMMENT 'Add source',
  `handle_result` tinyint NOT NULL DEFAULT 0 COMMENT 'Handle result',
  `handle_user_id` bigint DEFAULT NULL COMMENT 'Handler user ID',
  `handle_content` varchar(255) DEFAULT NULL COMMENT 'Handle content',
  `handle_time` datetime DEFAULT NULL COMMENT 'Handle time',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_group_request` (`group_id`, `user_id`, `tenant_id`),
  KEY `idx_im_group_request_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM group request';

CREATE TABLE IF NOT EXISTS `im_face_pack` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(64) NOT NULL COMMENT 'Face pack name',
  `icon` varchar(512) DEFAULT NULL COMMENT 'Face pack icon',
  `sort` int NOT NULL DEFAULT 0 COMMENT 'Sort',
  `status` tinyint NOT NULL COMMENT 'Status',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM face pack';

CREATE TABLE IF NOT EXISTS `im_face_pack_item` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `pack_id` bigint NOT NULL COMMENT 'Face pack ID',
  `url` varchar(512) NOT NULL COMMENT 'Face URL',
  `name` varchar(64) DEFAULT NULL COMMENT 'Face name',
  `width` int NOT NULL DEFAULT 0 COMMENT 'Width',
  `height` int NOT NULL DEFAULT 0 COMMENT 'Height',
  `sort` int NOT NULL DEFAULT 0 COMMENT 'Sort',
  `status` tinyint NOT NULL COMMENT 'Status',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  KEY `idx_im_face_pack_item_pack` (`pack_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM face pack item';

CREATE TABLE IF NOT EXISTS `im_face_user_item` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `user_id` bigint NOT NULL COMMENT 'User ID',
  `url` varchar(512) NOT NULL COMMENT 'Face URL',
  `name` varchar(64) DEFAULT NULL COMMENT 'Face name',
  `width` int NOT NULL DEFAULT 0 COMMENT 'Width',
  `height` int NOT NULL DEFAULT 0 COMMENT 'Height',
  `sort` int NOT NULL DEFAULT 0 COMMENT 'Sort',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_face_user_item_user_url_deleted` (`user_id`, `url`, `deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM user face item';

CREATE TABLE IF NOT EXISTS `im_rtc_call` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `room` varchar(64) NOT NULL COMMENT 'Business room ID',
  `conversation_type` tinyint NOT NULL COMMENT 'Conversation type',
  `media_type` tinyint NOT NULL COMMENT 'Media type',
  `inviter_user_id` bigint NOT NULL COMMENT 'Inviter user ID',
  `group_id` bigint DEFAULT NULL COMMENT 'Group ID',
  `status` tinyint NOT NULL COMMENT 'Call status',
  `end_reason` tinyint DEFAULT NULL COMMENT 'End reason',
  `start_time` datetime NOT NULL COMMENT 'Start time',
  `accept_time` datetime DEFAULT NULL COMMENT 'Accept time',
  `end_time` datetime DEFAULT NULL COMMENT 'End time',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  KEY `idx_im_rtc_call_room` (`room`),
  KEY `idx_im_rtc_call_inviter` (`inviter_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM RTC call';

CREATE TABLE IF NOT EXISTS `im_rtc_participant` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `call_id` bigint NOT NULL COMMENT 'Call ID',
  `room` varchar(64) NOT NULL COMMENT 'Business room ID',
  `user_id` bigint NOT NULL COMMENT 'User ID',
  `role` tinyint NOT NULL COMMENT 'Participant role',
  `status` tinyint NOT NULL COMMENT 'Participant status',
  `invite_time` datetime NOT NULL COMMENT 'Invite time',
  `accept_time` datetime DEFAULT NULL COMMENT 'Accept time',
  `leave_time` datetime DEFAULT NULL COMMENT 'Leave time',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_rtc_participant_room_user` (`room`, `user_id`, `tenant_id`),
  KEY `idx_im_rtc_participant_call` (`call_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM RTC participant';

CREATE TABLE IF NOT EXISTS `im_channel` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) NOT NULL COMMENT 'Channel code',
  `name` varchar(64) NOT NULL COMMENT 'Channel name',
  `avatar` varchar(512) DEFAULT NULL COMMENT 'Channel avatar',
  `sort` int NOT NULL DEFAULT 0 COMMENT 'Sort',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT 'Status',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_channel_code_tenant` (`code`, `tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM channel';

CREATE TABLE IF NOT EXISTS `im_channel_material` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `channel_id` bigint NOT NULL COMMENT 'Channel ID',
  `type` tinyint NOT NULL COMMENT 'Material type',
  `title` varchar(128) NOT NULL COMMENT 'Title',
  `cover_url` varchar(512) DEFAULT NULL COMMENT 'Cover URL',
  `summary` varchar(255) DEFAULT NULL COMMENT 'Summary',
  `content` mediumtext DEFAULT NULL COMMENT 'Rich text HTML',
  `url` varchar(512) DEFAULT NULL COMMENT 'External URL',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  KEY `idx_im_channel_material_channel` (`channel_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM channel material';

CREATE TABLE IF NOT EXISTS `im_channel_message` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `channel_id` bigint NOT NULL COMMENT 'Channel ID',
  `material_id` bigint NOT NULL COMMENT 'Material ID',
  `type` smallint NOT NULL COMMENT 'Message type',
  `content` varchar(8192) DEFAULT NULL COMMENT 'Message content JSON',
  `receiver_user_ids` varchar(1024) DEFAULT NULL COMMENT 'Receiver user IDs, comma separated',
  `send_time` datetime NOT NULL COMMENT 'Send time',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  KEY `idx_im_channel_message_channel_time` (`channel_id`, `send_time`),
  KEY `idx_im_channel_message_material` (`material_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM channel message';

CREATE TABLE IF NOT EXISTS `im_sensitive_word` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `word` varchar(128) NOT NULL COMMENT 'Sensitive word',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT 'Status',
  `creator` varchar(64) DEFAULT '' COMMENT 'Creator',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `updater` varchar(64) DEFAULT '' COMMENT 'Updater',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT 'Deleted flag',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT 'Tenant ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_im_sensitive_word` (`word`, `tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM sensitive word';
