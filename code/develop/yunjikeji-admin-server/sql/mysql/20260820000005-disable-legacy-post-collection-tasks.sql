-- Feishu public documents are the only active automatic recruitment source.
-- Keep historical task rows and collector code for audit and rollback, but
-- prevent legacy channels from being scheduled or manually re-enabled.

UPDATE `yj_post_collection_task`
SET `status` = b'0',
    `updater` = 'system',
    `update_time` = NOW()
WHERE `deleted` = b'0'
  AND (`collection_channel` IS NULL OR `collection_channel` <> 'feishu_folder')
  AND `status` = b'1';
