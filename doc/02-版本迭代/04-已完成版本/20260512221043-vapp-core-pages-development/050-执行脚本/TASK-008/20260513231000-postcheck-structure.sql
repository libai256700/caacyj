SELECT 'TABLES' AS section;
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'yk_question_category',
    'yk_question',
    'yk_question_option',
    'yk_practice_session',
    'yk_practice_record',
    'yk_wrong_question_book'
  )
ORDER BY TABLE_NAME;

SELECT 'KEY_COLUMNS' AS section;
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
    (TABLE_NAME = 'yk_question' AND COLUMN_NAME IN ('question_type', 'delete_status', 'source_ref'))
    OR (TABLE_NAME = 'yk_question_category' AND COLUMN_NAME IN ('status', 'delete_status'))
    OR (TABLE_NAME = 'yk_question_option' AND COLUMN_NAME IN ('status', 'delete_status'))
    OR (TABLE_NAME = 'yk_practice_session' AND COLUMN_NAME IN ('session_id','mode','status','delete_status'))
    OR (TABLE_NAME = 'yk_practice_record' AND COLUMN_NAME IN (
      'session_id','selected_answer','question_code_snapshot','question_type_snapshot',
      'question_stem_snapshot','standard_answer_snapshot','question_analysis_snapshot',
      'category_id_snapshot','category_code_snapshot','category_name_snapshot',
      'options_snapshot_json','status','delete_status'
    ))
    OR (TABLE_NAME = 'yk_wrong_question_book' AND COLUMN_NAME IN (
      'user_id','question_id','latest_practice_record_id','latest_session_id',
      'latest_selected_answer','wrong_count','status','delete_status'
    ))
  )
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT 'SHOW_CREATE_YK_QUESTION' AS section;
SHOW CREATE TABLE yk_question;
SELECT 'SHOW_CREATE_YK_PRACTICE_SESSION' AS section;
SHOW CREATE TABLE yk_practice_session;
SELECT 'SHOW_CREATE_YK_WRONG_QUESTION_BOOK' AS section;
SHOW CREATE TABLE yk_wrong_question_book;

SELECT 'INVALID_QUESTION_TYPE_COUNT' AS section;
SELECT COUNT(*) AS invalid_question_type_count
FROM yk_question
WHERE question_type NOT IN ('single_choice', 'multiple_choice', 'judge');

SELECT 'LEGACY_TYPE_INFERRED_COUNT' AS section;
SELECT COUNT(*) AS legacy_type_inferred_count
FROM yk_question
WHERE source_ref LIKE '[LEGACY-TYPE-INFERRED]%';

SELECT 'PENDING_MANUAL_CONFIRM_COUNT' AS section;
SELECT COUNT(*) AS pending_manual_confirm_count
FROM yk_practice_record
WHERE selected_answer = 'PENDING_MANUAL_CONFIRM';

SELECT 'WRONG_BOOK_INDEX' AS section;
SHOW INDEX FROM yk_wrong_question_book;
