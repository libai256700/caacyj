-- ============================================
-- Script type: DML execution script
-- Description: update practice question tenant_id values to 1
-- Created at: 2026-06-11 00:00:00
-- Author: Codex
-- Scope: yunjikeji practice question tenant_id only
-- Environment: test database only
-- Rollback script: rollback_yj_practice_exercises_tenant_id.sql
-- ============================================

-- Preferred execution entry:
--   python execute_yj_practice_exercises_tenant_id_update.py
--
-- The Python entry creates timestamped backup tables before DML using explicit
-- CREATE TABLE plus INSERT SELECT, then rewrites the rollback SQL with the
-- actual backup table names for the current run.

START TRANSACTION;

-- Pre-check: target table distributions.
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

-- DML is intentionally kept explicit. Use timestamped backup tables before
-- running these statements manually.
UPDATE yj_practice_exercises
SET tenant_id = 1
WHERE tenant_id <> 1 OR tenant_id IS NULL;

UPDATE yj_practice_exercises_answer
SET tenant_id = 1
WHERE tenant_id <> 1 OR tenant_id IS NULL;

UPDATE yj_practice_exercises_answer_child
SET tenant_id = 1
WHERE tenant_id <> 1 OR tenant_id IS NULL;

-- Post-check: each target table should have zero non-1/null rows.
SELECT 'yj_practice_exercises' AS table_name,
       COUNT(*) AS total_rows,
       SUM(CASE WHEN tenant_id = 1 THEN 1 ELSE 0 END) AS tenant_id_1_rows,
       SUM(CASE WHEN tenant_id <> 1 OR tenant_id IS NULL THEN 1 ELSE 0 END) AS tenant_id_not_1_or_null_rows
FROM yj_practice_exercises
UNION ALL
SELECT 'yj_practice_exercises_answer' AS table_name,
       COUNT(*) AS total_rows,
       SUM(CASE WHEN tenant_id = 1 THEN 1 ELSE 0 END) AS tenant_id_1_rows,
       SUM(CASE WHEN tenant_id <> 1 OR tenant_id IS NULL THEN 1 ELSE 0 END) AS tenant_id_not_1_or_null_rows
FROM yj_practice_exercises_answer
UNION ALL
SELECT 'yj_practice_exercises_answer_child' AS table_name,
       COUNT(*) AS total_rows,
       SUM(CASE WHEN tenant_id = 1 THEN 1 ELSE 0 END) AS tenant_id_1_rows,
       SUM(CASE WHEN tenant_id <> 1 OR tenant_id IS NULL THEN 1 ELSE 0 END) AS tenant_id_not_1_or_null_rows
FROM yj_practice_exercises_answer_child;

COMMIT;
