SELECT 'active_category_count' AS metric, COUNT(*) AS metric_value FROM yk_question_category WHERE delete_status = 0;
SELECT 'active_question_count' AS metric, COUNT(*) AS metric_value FROM yk_question WHERE delete_status = 0;
SELECT 'active_option_count' AS metric, COUNT(*) AS metric_value FROM yk_question_option WHERE delete_status = 0;
SELECT 'active_q_cqa_question_count' AS metric, COUNT(*) AS metric_value FROM yk_question WHERE delete_status = 0 AND question_code LIKE 'Q-CQA-%';
SELECT 'active_q_cqa_option_count' AS metric, COUNT(*) AS metric_value FROM yk_question_option qo JOIN yk_question q ON q.id = qo.question_id WHERE qo.delete_status = 0 AND q.delete_status = 0 AND q.question_code LIKE 'Q-CQA-%';