-- DEV-059 理论题库正式替换回滚脚本
-- 仅用于回滚 2026-08-17 22:32:08 +08:00 这次替换
-- 目标库：114.111.30.111:13306 / yunjikeji
-- 作用范围：只恢复分类 1..11，分类 13 保持不变
-- 备份表：
--   yj_practice_category_bak_20260817223208139166
--   yj_practice_exercises_bak_20260817223208139166
--   yj_practice_exercises_answer_bak_20260817223208139166
--   yj_practice_exercises_answer_child_bak_20260817223208139166

START TRANSACTION;

-- 一、删除当前分类 1..11 下的题目、答案、子答案
DELETE child
FROM yj_practice_exercises_answer_child child
INNER JOIN yj_practice_exercises_answer answer_item
        ON answer_item.id = child.answer_id
INNER JOIN yj_practice_exercises question
        ON question.id = answer_item.exercises_id
WHERE question.category_id BETWEEN 1 AND 11;

DELETE answer_item
FROM yj_practice_exercises_answer answer_item
INNER JOIN yj_practice_exercises question
        ON question.id = answer_item.exercises_id
WHERE question.category_id BETWEEN 1 AND 11;

DELETE FROM yj_practice_exercises
WHERE category_id BETWEEN 1 AND 11;

-- 二、仅从备份恢复分类 1..11 的题目
INSERT INTO yj_practice_exercises
SELECT question_bak.*
FROM yj_practice_exercises_bak_20260817223208139166 question_bak
WHERE question_bak.category_id BETWEEN 1 AND 11;

-- 三、仅恢复这些备份题目关联的答案，避免把分类 13 等其他历史答案一并恢复
INSERT INTO yj_practice_exercises_answer
SELECT answer_bak.*
FROM yj_practice_exercises_answer_bak_20260817223208139166 answer_bak
INNER JOIN yj_practice_exercises_bak_20260817223208139166 question_bak
        ON question_bak.id = answer_bak.exercises_id
WHERE question_bak.category_id BETWEEN 1 AND 11;

-- 四、仅恢复这些备份答案关联的子答案
INSERT INTO yj_practice_exercises_answer_child
SELECT child_bak.*
FROM yj_practice_exercises_answer_child_bak_20260817223208139166 child_bak
INNER JOIN yj_practice_exercises_answer_bak_20260817223208139166 answer_bak
        ON answer_bak.id = child_bak.answer_id
INNER JOIN yj_practice_exercises_bak_20260817223208139166 question_bak
        ON question_bak.id = answer_bak.exercises_id
WHERE question_bak.category_id BETWEEN 1 AND 11;

COMMIT;

-- 五、回滚后校验
SELECT COUNT(1) AS question_total_1_to_11
FROM yj_practice_exercises
WHERE deleted = b'0' AND category_id BETWEEN 1 AND 11;

SELECT COUNT(1) AS answer_total_1_to_11
FROM yj_practice_exercises_answer answer_item
INNER JOIN yj_practice_exercises question
        ON question.id = answer_item.exercises_id
       AND question.deleted = b'0'
WHERE answer_item.deleted = b'0'
  AND question.category_id BETWEEN 1 AND 11;

SELECT COUNT(1) AS category_13_question_total
FROM yj_practice_exercises
WHERE deleted = b'0' AND category_id = 13;
