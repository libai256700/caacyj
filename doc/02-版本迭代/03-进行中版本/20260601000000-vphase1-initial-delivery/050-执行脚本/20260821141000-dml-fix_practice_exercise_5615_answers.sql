-- ============================================
-- 脚本类型：dml
-- 脚本描述：修复练习题 5615 题干混入选项且答案选项缺失的问题
-- 创建日期：2026-08-21 14:10:00
-- 作者：Codex
-- 影响范围：yj_practice_exercises.id=5615、yj_practice_exercises_answer、yj_practice_exercises_answer_batch
-- 执行环境：测试环境
-- ============================================

-- 前置检查：确认题目当前存在，且题干包含错误混入的 A/B 选项。
SELECT
  id,
  question_stem,
  question_type,
  score,
  deleted
FROM yj_practice_exercises
WHERE id = 5615;

SELECT
  id,
  exercises_id,
  answer_code,
  answer_content,
  is_correct,
  sort_no,
  deleted
FROM yj_practice_exercises_answer
WHERE exercises_id = 5615
ORDER BY sort_no, id;

-- 主要变更：题干只保留题干内容，A/B 进入答案表，C 保留为正确答案。
UPDATE yj_practice_exercises
SET question_stem = '何种无人机必须安装使用电子围栏',
    updater = 'codex',
    update_time = NOW()
WHERE id = 5615
  AND deleted = b'0';

INSERT INTO yj_practice_exercises_answer
  (exercises_id, question_type, answer_code, answer_content, is_correct, sort_no, creator, updater, deleted)
SELECT
  5615,
  'single_choice',
  'A',
  'II、III、IV、V、VI、VII 类无人机',
  b'0',
  1,
  'codex',
  'codex',
  b'0'
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1
  FROM yj_practice_exercises_answer
  WHERE exercises_id = 5615
    AND answer_code = 'A'
    AND deleted = b'0'
);

INSERT INTO yj_practice_exercises_answer
  (exercises_id, question_type, answer_code, answer_content, is_correct, sort_no, creator, updater, deleted)
SELECT
  5615,
  'single_choice',
  'B',
  'III、IV、VI、VII 类无人机',
  b'0',
  2,
  'codex',
  'codex',
  b'0'
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1
  FROM yj_practice_exercises_answer
  WHERE exercises_id = 5615
    AND answer_code = 'B'
    AND deleted = b'0'
);

UPDATE yj_practice_exercises_answer
SET question_type = 'single_choice',
    answer_code = 'A',
    answer_content = 'II、III、IV、V、VI、VII 类无人机',
    is_correct = b'0',
    sort_no = 1,
    updater = 'codex',
    update_time = NOW()
WHERE exercises_id = 5615
  AND answer_code = 'A'
  AND deleted = b'0';

UPDATE yj_practice_exercises_answer
SET question_type = 'single_choice',
    answer_code = 'B',
    answer_content = 'III、IV、VI、VII 类无人机',
    is_correct = b'0',
    sort_no = 2,
    updater = 'codex',
    update_time = NOW()
WHERE exercises_id = 5615
  AND answer_code = 'B'
  AND deleted = b'0';

UPDATE yj_practice_exercises_answer
SET question_type = 'single_choice',
    answer_code = 'C',
    answer_content = 'III、IV、VI、VII 类无人机及重点地区和机场净空区以下运行的 II、V 类无人机',
    is_correct = b'1',
    sort_no = 3,
    updater = 'codex',
    update_time = NOW()
WHERE exercises_id = 5615
  AND answer_content LIKE '%重点地区和机场净空区以下运行%'
  AND deleted = b'0';

SET @exercise_5615_answer_a_id := (
  SELECT MIN(id)
  FROM yj_practice_exercises_answer
  WHERE exercises_id = 5615
    AND answer_code = 'A'
    AND deleted = b'0'
);
SET @exercise_5615_answer_b_id := (
  SELECT MIN(id)
  FROM yj_practice_exercises_answer
  WHERE exercises_id = 5615
    AND answer_code = 'B'
    AND deleted = b'0'
);
SET @exercise_5615_answer_c_id := (
  SELECT MIN(id)
  FROM yj_practice_exercises_answer
  WHERE exercises_id = 5615
    AND answer_code = 'C'
    AND deleted = b'0'
);

-- 同步现有练习批次答案快照，避免已经生成的批次仍只显示一个选项。
UPDATE yj_practice_exercises_answer_batch answer_batch
INNER JOIN yj_practice_exercises_batch exercise_batch ON exercise_batch.id = answer_batch.exercises_batch_id
SET answer_batch.answer_id = @exercise_5615_answer_c_id,
    answer_batch.question_type = 'single_choice',
    answer_batch.answer_code = 'C',
    answer_batch.answer_content = 'III、IV、VI、VII 类无人机及重点地区和机场净空区以下运行的 II、V 类无人机',
    answer_batch.is_correct = b'1',
    answer_batch.sort_no = 3,
    answer_batch.updater = 'codex',
    answer_batch.update_time = NOW()
WHERE exercise_batch.exercises_id = 5615
  AND answer_batch.deleted = b'0'
  AND answer_batch.answer_content LIKE '%重点地区和机场净空区以下运行%';

INSERT INTO yj_practice_exercises_answer_batch
  (exercises_batch_id, answer_id, question_type, answer_code, answer_content, is_correct, sort_no, creator, updater, deleted)
SELECT
  exercise_batch.id,
  @exercise_5615_answer_a_id,
  'single_choice',
  'A',
  'II、III、IV、V、VI、VII 类无人机',
  b'0',
  1,
  'codex',
  'codex',
  b'0'
FROM yj_practice_exercises_batch exercise_batch
WHERE exercise_batch.exercises_id = 5615
  AND exercise_batch.deleted = b'0'
  AND @exercise_5615_answer_a_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM yj_practice_exercises_answer_batch existing_answer
    WHERE existing_answer.exercises_batch_id = exercise_batch.id
      AND existing_answer.answer_code = 'A'
      AND existing_answer.deleted = b'0'
  );

INSERT INTO yj_practice_exercises_answer_batch
  (exercises_batch_id, answer_id, question_type, answer_code, answer_content, is_correct, sort_no, creator, updater, deleted)
SELECT
  exercise_batch.id,
  @exercise_5615_answer_b_id,
  'single_choice',
  'B',
  'III、IV、VI、VII 类无人机',
  b'0',
  2,
  'codex',
  'codex',
  b'0'
FROM yj_practice_exercises_batch exercise_batch
WHERE exercise_batch.exercises_id = 5615
  AND exercise_batch.deleted = b'0'
  AND @exercise_5615_answer_b_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM yj_practice_exercises_answer_batch existing_answer
    WHERE existing_answer.exercises_batch_id = exercise_batch.id
      AND existing_answer.answer_code = 'B'
      AND existing_answer.deleted = b'0'
  );

-- 后置校验：预期题干不含选项，源答案 A/B/C 各一条，批次快照每个批次都有 A/B/C。
SELECT
  id,
  question_stem,
  question_type,
  score,
  deleted
FROM yj_practice_exercises
WHERE id = 5615;

SELECT
  id,
  exercises_id,
  answer_code,
  answer_content,
  is_correct,
  sort_no,
  deleted
FROM yj_practice_exercises_answer
WHERE exercises_id = 5615
ORDER BY sort_no, id;

SELECT
  exercise_batch.id AS exercises_batch_id,
  COUNT(answer_batch.id) AS answer_count,
  GROUP_CONCAT(answer_batch.answer_code ORDER BY answer_batch.sort_no, answer_batch.id SEPARATOR ',') AS answer_codes
FROM yj_practice_exercises_batch exercise_batch
LEFT JOIN yj_practice_exercises_answer_batch answer_batch
  ON answer_batch.exercises_batch_id = exercise_batch.id
  AND answer_batch.deleted = b'0'
WHERE exercise_batch.exercises_id = 5615
  AND exercise_batch.deleted = b'0'
GROUP BY exercise_batch.id
ORDER BY exercise_batch.id;

-- 回滚方案：如需回滚，可将 question_stem 恢复为原始混入选项文本，删除本脚本新增的 A/B 源答案及 A/B 批次快照，
-- 并将 C 选项 sort_no 恢复为 1。由于本次修复是纠错数据，正常不建议回滚到错误题库状态。
