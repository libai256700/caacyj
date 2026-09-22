-- ============================================
-- Script type: dml
-- Description: Roll back rows inserted by 20260610-yj-practice-data-migration.sql
-- Created at: 2026-08-17 11:32:00
-- Author: Codex
-- Scope: shared practice category, exercises, answers, records and record details
-- Environment: test / production after approval and backup verification
-- ============================================

-- Pre-check: all five immutable candidate-id snapshots must exist before any delete starts.
SELECT expected.table_name,
       IF(snapshot.TABLE_NAME IS NULL, 'MISSING', 'READY') AS snapshot_status
FROM (
  SELECT 'bak_20260610_practice_category_ids' AS table_name
  UNION ALL SELECT 'bak_20260610_practice_exercises_ids'
  UNION ALL SELECT 'bak_20260610_practice_answer_ids'
  UNION ALL SELECT 'bak_20260610_practice_record_ids'
  UNION ALL SELECT 'bak_20260610_practice_detail_ids'
) expected
LEFT JOIN information_schema.TABLES snapshot
  ON snapshot.TABLE_SCHEMA = DATABASE() AND snapshot.TABLE_NAME = expected.table_name
ORDER BY expected.table_name;

SET @practice_backup_count := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME IN (
      'bak_20260610_practice_category_ids',
      'bak_20260610_practice_exercises_ids',
      'bak_20260610_practice_answer_ids',
      'bak_20260610_practice_record_ids',
      'bak_20260610_practice_detail_ids'
    ));
SET @rollback_gate := IF(@practice_backup_count = 5,
  'SELECT ''practice migration snapshots ready'' AS info',
  'SELECT * FROM `rollback_blocked_missing_practice_migration_snapshot`');
PREPARE stmt FROM @rollback_gate; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- The forward migration is insert-only. Deleting only snapshot candidate ids restores the exact pre-run set
-- without overwriting rows that existed before the migration or unrelated rows created later.
START TRANSACTION;

DELETE target FROM `yj_user_practice_exercises_record_detail` target
JOIN `bak_20260610_practice_detail_ids` backup ON backup.id = target.id;

DELETE target FROM `yj_user_practice_exercises_record` target
JOIN `bak_20260610_practice_record_ids` backup ON backup.id = target.id;

DELETE target FROM `yj_practice_exercises_answer` target
JOIN `bak_20260610_practice_answer_ids` backup ON backup.id = target.id;

DELETE target FROM `yj_practice_exercises` target
JOIN `bak_20260610_practice_exercises_ids` backup ON backup.id = target.id;

DELETE target FROM `yj_practice_category` target
JOIN `bak_20260610_practice_category_ids` backup ON backup.id = target.id;

COMMIT;

-- Post-check: every remaining count must be zero.
SELECT 'yj_practice_category' AS table_name, COUNT(1) AS remaining_migrated_rows
FROM yj_practice_category target
JOIN bak_20260610_practice_category_ids backup ON backup.id = target.id
UNION ALL
SELECT 'yj_practice_exercises', COUNT(1)
FROM yj_practice_exercises target
JOIN bak_20260610_practice_exercises_ids backup ON backup.id = target.id
UNION ALL
SELECT 'yj_practice_exercises_answer', COUNT(1)
FROM yj_practice_exercises_answer target
JOIN bak_20260610_practice_answer_ids backup ON backup.id = target.id
UNION ALL
SELECT 'yj_user_practice_exercises_record', COUNT(1)
FROM yj_user_practice_exercises_record target
JOIN bak_20260610_practice_record_ids backup ON backup.id = target.id
UNION ALL
SELECT 'yj_user_practice_exercises_record_detail', COUNT(1)
FROM yj_user_practice_exercises_record_detail target
JOIN bak_20260610_practice_detail_ids backup ON backup.id = target.id;

-- Keep the snapshot tables for audit and repeatable rollback evidence. Drop them only through a separately
-- reviewed cleanup script after the release rollback window closes.
