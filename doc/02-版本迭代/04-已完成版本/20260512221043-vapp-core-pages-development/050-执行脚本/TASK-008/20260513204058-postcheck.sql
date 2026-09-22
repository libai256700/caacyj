SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'yk_question_category',
    'yk_question',
    'yk_question_option',
    'yk_practice_session',
    'yk_practice_record',
    'yk_wrong_question_book',
    'yk_question_import_staging',
    'yk_question_import_option_staging'
  )
ORDER BY TABLE_NAME;

SELECT category_code, category_name, sort_no
FROM yk_question_category
ORDER BY sort_no;

SELECT parse_status, COUNT(*) AS row_count
FROM yk_question_import_staging
GROUP BY parse_status
ORDER BY parse_status;

SELECT COUNT(*) AS formal_question_count FROM yk_question;
SELECT COUNT(*) AS formal_option_count FROM yk_question_option;
SELECT COUNT(*) AS practice_session_count FROM yk_practice_session;
SELECT COUNT(*) AS wrong_book_count FROM yk_wrong_question_book;

SELECT category_code, COUNT(*) AS question_count
FROM yk_question_import_staging
WHERE parse_status IN ('parsed', 'needs_manual_review')
GROUP BY category_code
ORDER BY category_code;
