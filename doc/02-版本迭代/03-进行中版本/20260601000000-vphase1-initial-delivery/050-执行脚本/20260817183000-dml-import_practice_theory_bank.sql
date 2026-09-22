-- DEV-059 理论题库正式替换执行记录 / 命令模板
-- 执行环境：Local（非生产）
-- 目标库：114.111.30.111:13306 / yunjikeji
-- 实际执行时间：2026-08-17 22:32:08 +08:00
-- 实际确认令牌：REPLACE_PRACTICE_THEORY_BANK
-- 实际导入策略：--import-incomplete-questions
-- 保留范围：分类 13 不参与替换，仅替换分类 1..11
-- 实际备份表：
--   yj_practice_category_bak_20260817223208139166
--   yj_practice_exercises_bak_20260817223208139166
--   yj_practice_exercises_answer_bak_20260817223208139166
--   yj_practice_exercises_answer_child_bak_20260817223208139166

-- 一、执行门禁
-- 1. 仅允许在 Local / Dev / Test 环境执行，禁止生产环境执行。
-- 2. 执行前必须先完成 dry-run，并显式携带 --import-incomplete-questions。
-- 3. 必须显式携带 --confirm-apply REPLACE_PRACTICE_THEORY_BANK。
-- 4. 不允许使用 --skip-invalid-questions；本任务约定保留 23 道待维护题导入。

-- 二、建议执行前核对 SQL
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

SELECT COUNT(1) AS answer_child_total_1_to_11
FROM yj_practice_exercises_answer_child child
INNER JOIN yj_practice_exercises_answer answer_item
        ON answer_item.id = child.answer_id
       AND answer_item.deleted = b'0'
INNER JOIN yj_practice_exercises question
        ON question.id = answer_item.exercises_id
       AND question.deleted = b'0'
WHERE child.deleted = b'0'
  AND question.category_id BETWEEN 1 AND 11;

SELECT COUNT(1) AS category_13_question_total
FROM yj_practice_exercises
WHERE deleted = b'0' AND category_id = 13;

-- 三、正式执行命令
-- PowerShell 示例：
-- $env:PRACTICE_DB_PASSWORD = '<从 application-local.yaml 或正式 Local 连接记录读取>'
-- python code/develop/yunjikeji-admin-server/sql/tools/practice_theory_bank_import.py `
--   --source-dir E:/huiyitechworkspace/knowledge-graph/-APP--main/-APP--main/knowledge_base/理论题库 `
--   --report-dir doc/02-版本迭代/03-进行中版本/20260601000000-vphase1-initial-delivery/061-验收标准/03-测试验证/DEV-059 `
--   --db-host 114.111.30.111 --db-port 13306 --db-name yunjikeji `
--   --db-user yunjikeji_test --db-password-env PRACTICE_DB_PASSWORD `
--   --environment local --import-incomplete-questions `
--   --apply --confirm-apply REPLACE_PRACTICE_THEORY_BANK
-- Remove-Item Env:PRACTICE_DB_PASSWORD -ErrorAction SilentlyContinue

-- 四、实际执行后结果口径
-- 1. 备份表实际计数：12 / 1556 / 4731 / 0
-- 2. 分类 1..11 实际替换后：1535 / 4630 / 0
-- 3. 分类 13 保持：21
-- 4. 空题干：22
-- 5. 非唯一正确答案题：1
-- 6. 重复排序：0
-- 7. 题目与答案 tenant_id != 0：均为 0
-- 8. correct_memo 最大长度：761

-- 五、执行后校验 SQL
SELECT COUNT(1) AS empty_stem_questions
FROM yj_practice_exercises
WHERE deleted = b'0'
  AND category_id BETWEEN 1 AND 11
  AND IFNULL(question_stem, '') = '';

SELECT COUNT(1) AS non_standard_correct_questions
FROM (
    SELECT question.id,
           SUM(CASE WHEN answer_item.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
    FROM yj_practice_exercises question
    LEFT JOIN yj_practice_exercises_answer answer_item
           ON answer_item.exercises_id = question.id
          AND answer_item.deleted = b'0'
    WHERE question.deleted = b'0'
      AND question.category_id BETWEEN 1 AND 11
    GROUP BY question.id
    HAVING correct_count <> 1
) t;
