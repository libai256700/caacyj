SELECT 'staging_question_rows' AS item, COUNT(*) AS row_count FROM yk_question_import_staging
UNION ALL
SELECT 'staging_option_rows', COUNT(*) FROM yk_question_import_option_staging
UNION ALL
SELECT 'formal_question_rows', COUNT(*) FROM yk_question
UNION ALL
SELECT 'formal_option_rows', COUNT(*) FROM yk_question_option
UNION ALL
SELECT 'category_rows', COUNT(*) FROM yk_question_category
UNION ALL
SELECT 'wrong_book_rows', COUNT(*) FROM yk_wrong_question_book;

SELECT parse_status, COUNT(*) AS row_count
FROM yk_question_import_staging
GROUP BY parse_status
ORDER BY parse_status;

SELECT category_code, COUNT(*) AS imported_question_count
FROM yk_question
GROUP BY category_code
ORDER BY category_code;

SELECT id, category_code, question_code, question_type, status, delete_status
FROM yk_question
ORDER BY id
LIMIT 20;
