-- Rollback: restore yj_practice survey import data from backup tables
-- Scope: test database yunjikeji, tenant_id = 1, category_name = '入行专属评估'
-- Backup tables:
--   yj_practice_category_bak_20260611_survey_import
--   yj_practice_exercises_bak_20260611_survey_import
--   yj_practice_exercises_answer_bak_20260611_survey_import
--   yj_practice_exercises_answer_child_bak_20260611_survey_import

START TRANSACTION;

SET @category_name := '入行专属评估';
SET @tenant_id := 1;

DELETE ac
FROM yj_practice_exercises_answer_child ac
JOIN yj_practice_exercises_answer a ON a.id = ac.answer_id
JOIN yj_practice_exercises e ON e.id = a.exercises_id
JOIN yj_practice_category c ON c.id = e.category_id
WHERE c.category_name = @category_name AND c.tenant_id = @tenant_id;

DELETE a
FROM yj_practice_exercises_answer a
JOIN yj_practice_exercises e ON e.id = a.exercises_id
JOIN yj_practice_category c ON c.id = e.category_id
WHERE c.category_name = @category_name AND c.tenant_id = @tenant_id;

DELETE e
FROM yj_practice_exercises e
JOIN yj_practice_category c ON c.id = e.category_id
WHERE c.category_name = @category_name AND c.tenant_id = @tenant_id;

DELETE FROM yj_practice_category
WHERE category_name = @category_name AND tenant_id = @tenant_id;

INSERT INTO yj_practice_category
SELECT * FROM yj_practice_category_bak_20260611_survey_import;

INSERT INTO yj_practice_exercises
SELECT * FROM yj_practice_exercises_bak_20260611_survey_import;

INSERT INTO yj_practice_exercises_answer
SELECT * FROM yj_practice_exercises_answer_bak_20260611_survey_import;

INSERT INTO yj_practice_exercises_answer_child
SELECT * FROM yj_practice_exercises_answer_child_bak_20260611_survey_import;

COMMIT;
