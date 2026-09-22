-- ============================================
-- Script type: DML rollback script
-- Description: restore practice question tenant_id values from backup tables
-- Created at: 2026-06-11T15:33:48
-- Author: Codex
-- Scope: yunjikeji practice question tenant_id only
-- Environment: test database only
-- Execution run id: 20260611153346
-- ============================================

START TRANSACTION;

-- Restore yj_practice_exercises.tenant_id from yj_practice_exercises_tenant_bak_20260611153346
SELECT COUNT(*) AS backup_rows FROM `yj_practice_exercises_tenant_bak_20260611153346`;

UPDATE `yj_practice_exercises` t
JOIN `yj_practice_exercises_tenant_bak_20260611153346` b ON b.id = t.id
SET t.tenant_id = b.tenant_id;

SELECT ROW_COUNT() AS restored_rows_for_yj_practice_exercises;

-- Restore yj_practice_exercises_answer.tenant_id from yj_practice_exercises_answer_tenant_bak_20260611153346
SELECT COUNT(*) AS backup_rows FROM `yj_practice_exercises_answer_tenant_bak_20260611153346`;

UPDATE `yj_practice_exercises_answer` t
JOIN `yj_practice_exercises_answer_tenant_bak_20260611153346` b ON b.id = t.id
SET t.tenant_id = b.tenant_id;

SELECT ROW_COUNT() AS restored_rows_for_yj_practice_exercises_answer;

-- Restore yj_practice_exercises_answer_child.tenant_id from yj_practice_exercises_answer_child_tenant_bak_20260611153346
SELECT COUNT(*) AS backup_rows FROM `yj_practice_exercises_answer_child_tenant_bak_20260611153346`;

UPDATE `yj_practice_exercises_answer_child` t
JOIN `yj_practice_exercises_answer_child_tenant_bak_20260611153346` b ON b.id = t.id
SET t.tenant_id = b.tenant_id;

SELECT ROW_COUNT() AS restored_rows_for_yj_practice_exercises_answer_child;

-- Rollback post-check.
SELECT 'yj_practice_exercises' AS table_name, tenant_id, deleted, COUNT(*) AS row_count
FROM yj_practice_exercises
GROUP BY tenant_id, deleted
UNION ALL
SELECT 'yj_practice_exercises_answer' AS table_name, tenant_id, deleted, COUNT(*) AS row_count
FROM yj_practice_exercises_answer
GROUP BY tenant_id, deleted
UNION ALL
SELECT 'yj_practice_exercises_answer_child' AS table_name, tenant_id, deleted, COUNT(*) AS row_count
FROM yj_practice_exercises_answer_child
GROUP BY tenant_id, deleted;

COMMIT;
