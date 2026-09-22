-- TASK-008 practice page question import template
-- Replace only the sample business values before execution.
-- Target database: yunjikeji

SET @category_code = 'overview';
SET @question_code = 'Q-OVERVIEW-0001';
SET @question_type = 'single_choice';
SET @correct_answer = 'A';
SET @source_ref = 'SOURCE_REF';
SET @category_id = (
    SELECT id
    FROM yk_question_category
    WHERE category_code = @category_code
    LIMIT 1
);

INSERT INTO yk_question (
    course_id,
    category_id,
    question_code,
    question_type,
    stem,
    correct_answer,
    analysis,
    score,
    sort_no,
    source_ref,
    options_json,
    answer_json,
    difficulty,
    status
) VALUES (
    NULL,
    @category_id,
    @question_code,
    @question_type,
    'TODO_STEM',
    @correct_answer,
    'TODO_ANALYSIS',
    1,
    10,
    @source_ref,
    JSON_ARRAY(
        JSON_OBJECT('optionCode', 'A', 'optionContent', 'Option A'),
        JSON_OBJECT('optionCode', 'B', 'optionContent', 'Option B'),
        JSON_OBJECT('optionCode', 'C', 'optionContent', 'Option C'),
        JSON_OBJECT('optionCode', 'D', 'optionContent', 'Option D')
    ),
    JSON_OBJECT('correctAnswer', @correct_answer),
    'normal',
    'online'
) ON DUPLICATE KEY UPDATE
    category_id = VALUES(category_id),
    question_type = VALUES(question_type),
    stem = VALUES(stem),
    correct_answer = VALUES(correct_answer),
    analysis = VALUES(analysis),
    score = VALUES(score),
    sort_no = VALUES(sort_no),
    source_ref = VALUES(source_ref),
    options_json = VALUES(options_json),
    answer_json = VALUES(answer_json),
    difficulty = VALUES(difficulty),
    status = VALUES(status);

SET @question_id = (
    SELECT id
    FROM yk_question
    WHERE question_code = @question_code
    LIMIT 1
);

INSERT INTO yk_question_option (
    question_id,
    option_code,
    option_label,
    option_content,
    is_correct,
    sort_no
) VALUES
    (@question_id, 'A', 'A', 'Option A', 1, 10),
    (@question_id, 'B', 'B', 'Option B', 0, 20),
    (@question_id, 'C', 'C', 'Option C', 0, 30),
    (@question_id, 'D', 'D', 'Option D', 0, 40)
ON DUPLICATE KEY UPDATE
    option_label = VALUES(option_label),
    option_content = VALUES(option_content),
    is_correct = VALUES(is_correct),
    sort_no = VALUES(sort_no);

-- Multiple choice rule:
--   question_type = 'multiple_choice'
--   correct_answer = 'A,C'
--   set is_correct = 1 on option A and option C

-- Judge rule:
--   question_type = 'judge'
--   keep two option rows only:
--     ('T', 'TRUE')
--     ('F', 'FALSE')
--   correct_answer = 'T' or 'F'

SELECT q.id,
       q.question_code,
       q.question_type,
       q.correct_answer,
       COUNT(o.id) AS option_count
FROM yk_question q
LEFT JOIN yk_question_option o
       ON o.question_id = q.id
WHERE q.question_code = @question_code
GROUP BY q.id, q.question_code, q.question_type, q.correct_answer;
