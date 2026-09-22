-- Rollback for execute_yj_practice_question_type_normalize_20260611.py
-- Generated at: 2026-06-11T18:50:27
-- Legacy question_type '2' was normalized to 'single_choice'.
-- Backup tables:
--   yj_practice_exercises_qtype_bak_20260611185026
--   yj_practice_answer_qtype_bak_20260611185026
--   yj_practice_answer_child_qtype_bak_20260611185026

START TRANSACTION;

UPDATE yj_practice_exercises t
JOIN `yj_practice_exercises_qtype_bak_20260611185026` b ON b.id = t.id
SET t.question_type = b.question_type,
    t.updater = b.updater,
    t.update_time = b.update_time
WHERE t.tenant_id = 1
  AND t.deleted = b'0';

UPDATE yj_practice_exercises_answer t
JOIN `yj_practice_answer_qtype_bak_20260611185026` b ON b.id = t.id
SET t.question_type = b.question_type,
    t.updater = b.updater,
    t.update_time = b.update_time
WHERE t.tenant_id = 1
  AND t.deleted = b'0';

UPDATE yj_practice_exercises_answer_child t
JOIN `yj_practice_answer_child_qtype_bak_20260611185026` b ON b.id = t.id
SET t.question_type = b.question_type,
    t.updater = b.updater,
    t.update_time = b.update_time
WHERE t.tenant_id = 1
  AND t.deleted = b'0';

COMMIT;

-- Verification after rollback:
-- SELECT question_type, COUNT(*) FROM yj_practice_exercises WHERE tenant_id = 1 AND deleted = b'0' GROUP BY question_type;
-- SELECT question_type, COUNT(*) FROM yj_practice_exercises_answer WHERE tenant_id = 1 AND deleted = b'0' GROUP BY question_type;
-- SELECT question_type, COUNT(*) FROM yj_practice_exercises_answer_child WHERE tenant_id = 1 AND deleted = b'0' GROUP BY question_type;
