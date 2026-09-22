-- Rollback script for practice step schema update on test database.
-- Backup table created by execute_yj_practice_step_schema_update_20260611.py:
--   yj_practice_exercises_schema_bak_20260611172443
--
-- Execute only after confirming no new business data depends on yj_practice_exercises.step_id
-- or yj_practice_setp.

SELECT COUNT(*) AS backup_rows
FROM `yj_practice_exercises_schema_bak_20260611172443`;

ALTER TABLE `yj_practice_exercises`
DROP COLUMN `step_id`;

DROP TABLE IF EXISTS `yj_practice_setp`;

SHOW COLUMNS FROM `yj_practice_exercises` LIKE 'step_id';
SHOW TABLES LIKE 'yj_practice_setp';
