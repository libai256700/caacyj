SELECT 'db_version' AS item, VERSION() AS detail
UNION ALL
SELECT 'table', TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'yunjikeji'
  AND TABLE_NAME IN (
    'yk_user_account',
    'yk_question',
    'yk_practice_record',
    'yk_question_category',
    'yk_question_option',
    'yk_question_import_staging',
    'yk_question_import_option_staging',
    'yk_practice_session',
    'yk_wrong_question_book'
  )
ORDER BY item, detail;

SELECT 'yk_question' AS table_name, COUNT(*) AS row_count FROM yk_question
UNION ALL
SELECT 'yk_practice_record', COUNT(*) FROM yk_practice_record
UNION ALL
SELECT 'yk_question_category', COUNT(*) FROM yk_question_category
UNION ALL
SELECT 'yk_question_import_staging', COUNT(*) FROM yk_question_import_staging
UNION ALL
SELECT 'yk_question_import_option_staging', COUNT(*) FROM yk_question_import_option_staging
UNION ALL
SELECT 'yk_practice_session', COUNT(*) FROM yk_practice_session;
