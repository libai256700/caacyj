-- Increase the active self-assessment model call timeout to five minutes.
-- Credentials stay inside the deployment database and are not copied into source control.
-- Run in the test environment first, after the normal database backup procedure.

START TRANSACTION;

CREATE TABLE IF NOT EXISTS `yj_ai_model_config_backup_20260822000000` LIKE `yj_ai_model_config`;

INSERT INTO `yj_ai_model_config_backup_20260822000000`
SELECT source.*
FROM `yj_ai_model_config` source
WHERE source.`scene_code` = 'practice_assessment'
  AND source.`deleted` = b'0'
  AND NOT EXISTS (
      SELECT 1
      FROM `yj_ai_model_config_backup_20260822000000` backup
      WHERE backup.`id` = source.`id`
  );

UPDATE `yj_ai_model_config`
SET `timeout_millis` = GREATEST(COALESCE(`timeout_millis`, 0), 300000),
    `updater` = 'system',
    `update_time` = NOW()
WHERE `scene_code` = 'practice_assessment'
  AND `status` = 0
  AND `deleted` = b'0';

SELECT `id`, `scene_code`, `base_url`, `model`, `timeout_millis`, `status`, `deleted`
FROM `yj_ai_model_config`
WHERE `scene_code` = 'practice_assessment'
  AND `deleted` = b'0';

COMMIT;
