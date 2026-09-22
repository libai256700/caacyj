-- ============================================
-- Script type: dml
-- Description: Import shared practice data without tenant fields
-- Created at: 2026-06-10 00:00:00
-- Author: Codex
-- Scope: shared practice category, exercises, answers, records and record details
-- Environment: test / production after approval and backup
-- ============================================

-- Pre-check: execute after 20260608-yj-admin-business-tables.sql.
-- This migration is insert-only. The immutable candidate-id snapshots below record exactly which rows are
-- absent before the first execution; reruns preserve the original snapshots for deterministic rollback.

SET @backup_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bak_20260610_practice_category_ids');
SET @ddl := IF(@backup_exists = 0,
  'CREATE TABLE `bak_20260610_practice_category_ids` AS SELECT qc.id FROM `yk_question_category` qc LEFT JOIN `yj_practice_category` target ON target.id = qc.id WHERE target.id IS NULL',
  'SELECT ''bak_20260610_practice_category_ids already exists; original snapshot preserved'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @backup_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bak_20260610_practice_exercises_ids');
SET @ddl := IF(@backup_exists = 0,
  'CREATE TABLE `bak_20260610_practice_exercises_ids` AS SELECT q.id FROM `yk_question` q LEFT JOIN `yj_practice_exercises` target ON target.id = q.id WHERE target.id IS NULL',
  'SELECT ''bak_20260610_practice_exercises_ids already exists; original snapshot preserved'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @backup_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bak_20260610_practice_answer_ids');
SET @ddl := IF(@backup_exists = 0,
  'CREATE TABLE `bak_20260610_practice_answer_ids` AS SELECT qo.id FROM `yk_question_option` qo LEFT JOIN `yj_practice_exercises_answer` target ON target.id = qo.id WHERE target.id IS NULL',
  'SELECT ''bak_20260610_practice_answer_ids already exists; original snapshot preserved'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @backup_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bak_20260610_practice_record_ids');
SET @ddl := IF(@backup_exists = 0,
  'CREATE TABLE `bak_20260610_practice_record_ids` AS SELECT ps.id FROM `yk_practice_session` ps LEFT JOIN `yj_user_practice_exercises_record` target ON target.id = ps.id WHERE target.id IS NULL',
  'SELECT ''bak_20260610_practice_record_ids already exists; original snapshot preserved'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @backup_exists := (SELECT COUNT(1) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bak_20260610_practice_detail_ids');
SET @ddl := IF(@backup_exists = 0,
  'CREATE TABLE `bak_20260610_practice_detail_ids` AS SELECT pr.id FROM `yk_practice_record` pr LEFT JOIN `yj_user_practice_exercises_record_detail` target ON target.id = pr.id WHERE target.id IS NULL',
  'SELECT ''bak_20260610_practice_detail_ids already exists; original snapshot preserved'' AS info');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Existing ids are retained so category, question, option, session and record relationships stay stable.

INSERT INTO yj_practice_category (
    id, category_name, category_status, field_type, sort_no,
    creator, create_time, updater, update_time, deleted
)
SELECT
    qc.id,
    qc.category_name,
    CASE WHEN qc.status = 'online' THEN b'1' ELSE b'0' END,
    LEFT(qc.category_code, 10),
    COALESCE(qc.sort_no, 0),
    '',
    COALESCE(qc.created_at, CURRENT_TIMESTAMP),
    '',
    COALESCE(qc.updated_at, qc.created_at, CURRENT_TIMESTAMP),
    CASE WHEN COALESCE(qc.delete_status, 0) = 1 THEN b'1' ELSE b'0' END
FROM yk_question_category qc
INNER JOIN bak_20260610_practice_category_ids migration_scope ON migration_scope.id = qc.id
WHERE NOT EXISTS (
    SELECT 1 FROM yj_practice_category target WHERE target.id = qc.id
);

INSERT INTO yj_practice_exercises (
    id, category_id, question_stem, question_type, question_status, score, sort_no,
    correct_memo, creator, create_time, updater, update_time, deleted
)
SELECT
    q.id,
    q.category_id,
    LEFT(q.stem, 800),
    CASE q.question_type
        WHEN 'single_choice' THEN '2'
        WHEN 'multiple_choice' THEN '3'
        WHEN 'judge' THEN '4'
        ELSE COALESCE(q.question_type, '1')
    END,
    CASE WHEN q.status = 'online' THEN b'1' ELSE b'0' END,
    COALESCE(q.score, 0),
    COALESCE(q.sort_no, 0),
    LEFT(q.analysis, 500),
    '',
    COALESCE(q.created_at, CURRENT_TIMESTAMP),
    '',
    COALESCE(q.updated_at, q.created_at, CURRENT_TIMESTAMP),
    CASE WHEN COALESCE(q.delete_status, 0) = 1 THEN b'1' ELSE b'0' END
FROM yk_question q
INNER JOIN bak_20260610_practice_exercises_ids migration_scope ON migration_scope.id = q.id
WHERE NOT EXISTS (
    SELECT 1 FROM yj_practice_exercises target WHERE target.id = q.id
);

INSERT INTO yj_practice_exercises_answer (
    id, exercises_id, question_type, answer_code, answer_content, is_correct, sort_no,
    creator, create_time, updater, update_time, deleted
)
SELECT
    qo.id,
    qo.question_id,
    CASE q.question_type
        WHEN 'single_choice' THEN '2'
        WHEN 'multiple_choice' THEN '3'
        WHEN 'judge' THEN '4'
        ELSE COALESCE(q.question_type, '1')
    END,
    qo.option_code,
    LEFT(qo.option_content, 255),
    CASE WHEN COALESCE(qo.is_correct, 0) = 1 THEN b'1' ELSE b'0' END,
    COALESCE(qo.sort_no, 0),
    '',
    CURRENT_TIMESTAMP,
    '',
    CURRENT_TIMESTAMP,
    CASE WHEN COALESCE(qo.delete_status, 0) = 1 THEN b'1' ELSE b'0' END
FROM yk_question_option qo
INNER JOIN bak_20260610_practice_answer_ids migration_scope ON migration_scope.id = qo.id
JOIN yk_question q ON q.id = qo.question_id
WHERE NOT EXISTS (
    SELECT 1 FROM yj_practice_exercises_answer target WHERE target.id = qo.id
);

INSERT INTO yj_user_practice_exercises_record (
    id, user_id, category_id, total_score, correct_count, wrong_count, field_type,
    creator, create_time, updater, update_time, deleted
)
SELECT
    ps.id,
    ps.user_id,
    ps.category_id,
    COALESCE(SUM(CASE WHEN pr.correct_flag = 1 THEN q.score ELSE 0 END), 0),
    COALESCE(ps.correct_count, 0),
    COALESCE(ps.wrong_count, 0),
    LEFT(qc.category_code, 10),
    '',
    COALESCE(ps.started_at, ps.created_at, CURRENT_TIMESTAMP),
    '',
    COALESCE(ps.updated_at, ps.completed_at, ps.created_at, CURRENT_TIMESTAMP),
    CASE WHEN COALESCE(ps.delete_status, 0) = 1 THEN b'1' ELSE b'0' END
FROM yk_practice_session ps
INNER JOIN bak_20260610_practice_record_ids migration_scope ON migration_scope.id = ps.id
LEFT JOIN yk_question_category qc ON qc.id = ps.category_id
LEFT JOIN yk_practice_record pr
       ON pr.session_id = ps.session_id
      AND pr.user_id = ps.user_id
      AND COALESCE(pr.delete_status, 0) = 0
LEFT JOIN yk_question q ON q.id = pr.question_id
WHERE NOT EXISTS (
    SELECT 1 FROM yj_user_practice_exercises_record target WHERE target.id = ps.id
)
GROUP BY ps.id, ps.user_id, ps.category_id, ps.correct_count, ps.wrong_count, qc.category_code,
         ps.started_at, ps.created_at, ps.updated_at, ps.completed_at, ps.delete_status;

INSERT INTO yj_user_practice_exercises_record_detail (
    id, record_id, exercises_id, answer_code, correct_answer_code, is_correct,
    creator, create_time, updater, update_time, deleted
)
SELECT
    pr.id,
    ps.id,
    pr.question_id,
    pr.selected_answer,
    pr.standard_answer_snapshot,
    CASE WHEN COALESCE(pr.correct_flag, 0) = 1 THEN b'1' ELSE b'0' END,
    '',
    COALESCE(pr.answered_at, pr.created_at, CURRENT_TIMESTAMP),
    '',
    COALESCE(pr.answered_at, pr.created_at, CURRENT_TIMESTAMP),
    CASE WHEN COALESCE(pr.delete_status, 0) = 1 THEN b'1' ELSE b'0' END
FROM yk_practice_record pr
INNER JOIN bak_20260610_practice_detail_ids migration_scope ON migration_scope.id = pr.id
JOIN yk_practice_session ps
  ON ps.session_id = pr.session_id
 AND ps.user_id = pr.user_id
WHERE NOT EXISTS (
    SELECT 1 FROM yj_user_practice_exercises_record_detail target WHERE target.id = pr.id
);

-- Post-check: target insert column lists must not contain tenant_id.
SELECT 'yj_practice_category' AS table_name, COUNT(1) AS row_count FROM yj_practice_category
UNION ALL
SELECT 'yj_practice_exercises', COUNT(1) FROM yj_practice_exercises
UNION ALL
SELECT 'yj_practice_exercises_answer', COUNT(1) FROM yj_practice_exercises_answer
UNION ALL
SELECT 'yj_user_practice_exercises_record', COUNT(1) FROM yj_user_practice_exercises_record
UNION ALL
SELECT 'yj_user_practice_exercises_record_detail', COUNT(1) FROM yj_user_practice_exercises_record_detail;

-- Snapshot verification. Each count is the maximum number of rows the paired rollback may remove.
SELECT 'bak_20260610_practice_category_ids' AS backup_table, COUNT(1) AS candidate_count
FROM bak_20260610_practice_category_ids
UNION ALL
SELECT 'bak_20260610_practice_exercises_ids', COUNT(1) FROM bak_20260610_practice_exercises_ids
UNION ALL
SELECT 'bak_20260610_practice_answer_ids', COUNT(1) FROM bak_20260610_practice_answer_ids
UNION ALL
SELECT 'bak_20260610_practice_record_ids', COUNT(1) FROM bak_20260610_practice_record_ids
UNION ALL
SELECT 'bak_20260610_practice_detail_ids', COUNT(1) FROM bak_20260610_practice_detail_ids;

-- Paired rollback: 20260817113200-dml-rollback_yj_practice_data_migration.sql.
