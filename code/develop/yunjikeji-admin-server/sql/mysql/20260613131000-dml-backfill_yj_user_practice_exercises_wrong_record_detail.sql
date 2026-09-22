-- ============================================
-- Script type: dml
-- Description: Backfill user practice wrong record detail table from existing practice record details
-- Created at: 2026-06-13 13:10:00
-- Author: Codex
-- Scope: yj_user_practice_exercises_wrong_record_detail
-- Environment: test
-- ============================================

-- Pre-check:
SELECT COUNT(1) AS source_wrong_detail_count
FROM `yj_user_practice_exercises_record_detail` d
INNER JOIN `yj_user_practice_exercises_record` r ON r.`id` = d.`record_id`
WHERE d.`is_correct` = b'0'
  AND d.`deleted` = b'0'
  AND r.`deleted` = b'0'
  AND r.`customer_account_id` IS NOT NULL;

INSERT INTO `yj_user_practice_exercises_wrong_record_detail` (
  `customer_account_id`,
  `record_detail_id`,
  `exercises`,
  `answer_code`,
  `correct_answer_code`,
  `wrong_count`,
  `latest_wrong_time`,
  `creator`,
  `create_time`,
  `updater`,
  `update_time`,
  `deleted`,
  `tenant_id`
)
SELECT
  r.`customer_account_id`,
  d.`id`,
  d.`exercises_id`,
  REPLACE(d.`answer_code`, ',', '|'),
  REPLACE(d.`correct_answer_code`, ',', '|'),
  cnt.`wrong_count`,
  COALESCE(d.`create_time`, d.`update_time`),
  d.`creator`,
  d.`create_time`,
  d.`updater`,
  d.`update_time`,
  d.`deleted`,
  r.`tenant_id`
FROM `yj_user_practice_exercises_record_detail` d
INNER JOIN `yj_user_practice_exercises_record` r ON r.`id` = d.`record_id`
INNER JOIN (
  SELECT
    r2.`tenant_id`,
    r2.`customer_account_id`,
    d2.`exercises_id`,
    COUNT(1) AS `wrong_count`
  FROM `yj_user_practice_exercises_record_detail` d2
  INNER JOIN `yj_user_practice_exercises_record` r2 ON r2.`id` = d2.`record_id`
  WHERE d2.`is_correct` = b'0'
    AND d2.`deleted` = b'0'
    AND r2.`deleted` = b'0'
    AND r2.`customer_account_id` IS NOT NULL
  GROUP BY r2.`tenant_id`, r2.`customer_account_id`, d2.`exercises_id`
) cnt ON cnt.`tenant_id` = r.`tenant_id`
     AND cnt.`customer_account_id` = r.`customer_account_id`
     AND cnt.`exercises_id` = d.`exercises_id`
WHERE d.`is_correct` = b'0'
  AND d.`deleted` = b'0'
  AND r.`deleted` = b'0'
  AND r.`customer_account_id` IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM `yj_user_practice_exercises_record_detail` newer
    INNER JOIN `yj_user_practice_exercises_record` newer_record ON newer_record.`id` = newer.`record_id`
    WHERE newer.`is_correct` = b'0'
      AND newer.`deleted` = b'0'
      AND newer_record.`deleted` = b'0'
      AND newer_record.`tenant_id` = r.`tenant_id`
      AND newer_record.`customer_account_id` = r.`customer_account_id`
      AND newer.`exercises_id` = d.`exercises_id`
      AND (
        COALESCE(newer.`create_time`, newer.`update_time`) > COALESCE(d.`create_time`, d.`update_time`)
        OR (
          COALESCE(newer.`create_time`, newer.`update_time`) = COALESCE(d.`create_time`, d.`update_time`)
          AND newer.`id` > d.`id`
        )
      )
  )
ON DUPLICATE KEY UPDATE
  `record_detail_id` = VALUES(`record_detail_id`),
  `answer_code` = VALUES(`answer_code`),
  `correct_answer_code` = VALUES(`correct_answer_code`),
  `wrong_count` = VALUES(`wrong_count`),
  `latest_wrong_time` = VALUES(`latest_wrong_time`),
  `updater` = VALUES(`updater`),
  `update_time` = VALUES(`update_time`),
  `deleted` = b'0';

-- Post-check:
SELECT COUNT(1) AS target_wrong_detail_count
FROM `yj_user_practice_exercises_wrong_record_detail`
WHERE `deleted` = b'0';

SELECT `tenant_id`, `customer_account_id`, `exercises`, COUNT(1) AS duplicate_count
FROM `yj_user_practice_exercises_wrong_record_detail`
WHERE `deleted` = b'0'
GROUP BY `tenant_id`, `customer_account_id`, `exercises`
HAVING COUNT(1) > 1;
