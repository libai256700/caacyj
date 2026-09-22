-- ============================================
-- Script type: dml
-- Description: Roll back backfilled user practice wrong record details
-- Created at: 2026-06-13 13:10:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_wrong_record_detail
-- Environment: test
-- ============================================

DELETE w
FROM `yj_user_practice_exercises_wrong_record_detail` w
INNER JOIN `yj_user_practice_exercises_record_detail` d ON d.`id` = w.`record_detail_id`
INNER JOIN `yj_user_practice_exercises_record` r ON r.`id` = d.`record_id`
WHERE d.`is_correct` = b'0'
  AND d.`deleted` = b'0'
  AND r.`deleted` = b'0'
  AND r.`customer_account_id` = w.`customer_account_id`
  AND d.`exercises_id` = w.`exercises`;

-- Post-check:
SELECT COUNT(1) AS remaining_backfilled_wrong_detail_count
FROM `yj_user_practice_exercises_wrong_record_detail` w
INNER JOIN `yj_user_practice_exercises_record_detail` d ON d.`id` = w.`record_detail_id`
INNER JOIN `yj_user_practice_exercises_record` r ON r.`id` = d.`record_id`
WHERE d.`is_correct` = b'0'
  AND d.`deleted` = b'0'
  AND r.`deleted` = b'0'
  AND r.`customer_account_id` = w.`customer_account_id`
  AND d.`exercises_id` = w.`exercises`;
