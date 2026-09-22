-- Restore the practice_assessment timeout from the backup captured by
-- 20260822000000-dml-update_yj_ai_model_config_practice_assessment_timeout.sql.

START TRANSACTION;

UPDATE `yj_ai_model_config` target
JOIN `yj_ai_model_config_backup_20260822000000` backup ON backup.`id` = target.`id`
SET target.`timeout_millis` = backup.`timeout_millis`,
    target.`updater` = 'rollback',
    target.`update_time` = NOW()
WHERE target.`scene_code` = 'practice_assessment'
  AND target.`deleted` = b'0';

SELECT `id`, `scene_code`, `base_url`, `model`, `timeout_millis`, `status`, `deleted`
FROM `yj_ai_model_config`
WHERE `scene_code` = 'practice_assessment'
  AND `deleted` = b'0';

COMMIT;
