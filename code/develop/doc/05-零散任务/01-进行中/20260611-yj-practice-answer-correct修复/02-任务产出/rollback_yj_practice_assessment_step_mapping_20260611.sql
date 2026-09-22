-- Rollback for execute_yj_practice_assessment_step_mapping_20260611.py
-- Generated at: 2026-06-11T18:37:41
-- Backup tables:
--   yj_practice_assessment_step_bak_20260611183740
--   yj_practice_assessment_exercise_bak_20260611183740

START TRANSACTION;

UPDATE yj_practice_exercises e
JOIN `yj_practice_assessment_exercise_bak_20260611183740` b ON b.id = e.id
SET e.step_id = b.step_id,
    e.updater = b.updater,
    e.update_time = b.update_time
WHERE e.tenant_id = 1
  AND e.deleted = b'0';

DELETE s
FROM yj_practice_setp s
LEFT JOIN `yj_practice_assessment_step_bak_20260611183740` b ON b.id = s.id
WHERE s.tenant_id = 1
  AND s.deleted = b'0'
  AND b.id IS NULL;

UPDATE yj_practice_setp s
JOIN `yj_practice_assessment_step_bak_20260611183740` b ON b.id = s.id
SET s.tenant_id = b.tenant_id,
    s.setp_name = b.setp_name,
    s.setp_status = b.setp_status,
    s.sort_no = b.sort_no,
    s.creator = b.creator,
    s.create_time = b.create_time,
    s.updater = b.updater,
    s.update_time = b.update_time,
    s.deleted = b.deleted;

COMMIT;

-- Verification after rollback:
-- SELECT id, tenant_id, setp_name, sort_no, HEX(deleted) FROM yj_practice_setp WHERE tenant_id = 1 ORDER BY sort_no, id;
-- SELECT e.id, e.sort_no, e.step_id FROM yj_practice_exercises e JOIN yj_practice_category c ON c.id = e.category_id WHERE e.tenant_id = 1 AND e.deleted = b'0' AND c.tenant_id = 1 AND c.deleted = b'0' AND c.catalog_type = 1 ORDER BY e.sort_no, e.id;
