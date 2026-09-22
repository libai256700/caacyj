# TASK-008 database assets

## Scope

This asset pack covers the formal practice-page question bank model. It includes:

- question category table
- question main table incremental extension
- question option table
- practice session table
- practice record formal answer field and question snapshot extension
- wrong question book table
- 11 category seeds
- executable question import template

It does not include:

- staging tables or staging CSV contracts
- staging reset, target preclear, or from-staging import route
- full question extraction from source documents
- production execution evidence
- application code changes

## Current execution gate

This round only records the final formal structure boundary. Staging-table assets and their import route are no longer part of the formal structure scope.

## Asset inventory

| Asset | Purpose | File |
| --- | --- | --- |
| `yk_question_category` | Formal category master table for the practice bank. | `20260513220000-ddl-question-bank-schema-v2.sql` |
| `yk_question` extension | Category, code, canonical answer, score, sort, source reference, and `delete_status`. | `20260513220000-ddl-question-bank-schema-v2.sql` |
| `yk_question_option` | Formal option table with separate business status and soft-delete status. | `20260513220000-ddl-question-bank-schema-v2.sql` |
| `yk_practice_session` | Formal session carrier for `sessionId`, category, mode, progress counters, and soft delete. | `20260513220000-ddl-question-bank-schema-v2.sql` |
| `yk_practice_record` extension | Adds `session_id`, `selected_answer`, question snapshots, `status`, and `delete_status`. | `20260513220000-ddl-question-bank-schema-v2.sql` |
| `yk_wrong_question_book` | Formal wrong-question membership and aggregate state table. | `20260513220000-ddl-question-bank-schema-v2.sql` |
| 11 category seeds | Fixed categories requested for the current version. | `20260513221000-dml-question-category-seed-v2.sql` |
| question import template | Formal entry for follow-up question insertion. | `20260513192000-dml-question-import-template.sql` |
| question bank baseline manifest | Historical content baseline reference for later content preparation, not part of the final formal structure. | `20260513222000-question-bank-import-baseline-v2.json` |

## Constraint strategy

This asset pack uses a native-constraint route that is executable under the current account:

- physical foreign keys for parent existence and session-user consistency
- unique indexes for business identity and wrong-book uniqueness
- non-null columns plus data backfill before tightening
- enum-backed value domains for `question_type`, `practice mode`, `practice session status`, and wrong-book membership status
- pre-clean plus verification before `yk_question.question_type` is tightened to the final enum
- compatibility backfill plus sentinel marking before `yk_practice_record.selected_answer` is tightened to the final non-null route

The following rule boundaries remain outside current native enforcement:

- `yk_practice_record.correct_flag` remains `TINYINT(1)`; current write path and validation SQL enforce the expected `0/1` boundary, but MySQL 5.7 `CHECK` is not reliable enough to use as a formal guard.
- Empty-string rejection such as `TRIM(selected_answer) <> ''` cannot be fully enforced without triggers or stricter application writes.
- Legacy `answer_json` payloads that do not follow a stable shape are now marked as `PENDING_MANUAL_CONFIRM`; they still require manual review before being treated as formal historical answers.
- The repository does not currently carry a full 1512-row formal import payload inside `TASK-008`; content preparation remains outside the final formal structure scope of this round.

## Validation SQL

The SQL below is a validation reference for future confirmed execution or read-only review. It is not authorization to run database scripts in this round.

```sql
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
```

Expected result: 6 rows.

```sql
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_question'
  AND COLUMN_NAME IN (
    'category_id',
    'question_code',
    'correct_answer',
    'score',
    'sort_no',
    'source_ref',
    'delete_status'
  )
ORDER BY COLUMN_NAME;
```

Expected result: 7 rows.

```sql
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_practice_record'
  AND COLUMN_NAME IN (
    'session_id',
    'selected_answer',
    'question_code_snapshot',
    'question_type_snapshot',
    'question_stem_snapshot',
    'standard_answer_snapshot',
    'question_analysis_snapshot',
    'category_id_snapshot',
    'category_code_snapshot',
    'category_name_snapshot',
    'options_snapshot_json',
    'status',
    'delete_status'
  )
ORDER BY COLUMN_NAME;
```

Expected result: 13 rows.

```sql
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'yk_wrong_question_book'
  AND COLUMN_NAME IN (
    'user_id',
    'question_id',
    'latest_practice_record_id',
    'latest_session_id',
    'wrong_count',
    'latest_selected_answer',
    'latest_wrong_answer_json',
    'latest_standard_answer',
    'latest_wrong_at',
    'status',
    'removed_at',
    'delete_status'
  )
ORDER BY COLUMN_NAME;
```

Expected result: 12 rows.

```sql
SELECT category_code, category_name, sort_no
FROM yk_question_category
ORDER BY sort_no;
```

Expected result: 11 rows in the fixed order.

```sql
Current verified evidence:

- `20260513204058-postcheck-results.txt` already shows the 6 key tables are present, 11 category rows are in `yk_question_category`, and the current formal table counts are `yk_question = 1`, `yk_question_option = 4`, `yk_practice_session = 0`, `yk_wrong_question_book = 0`.

```sql
SELECT question_type, COUNT(*) AS question_count
FROM yk_question
GROUP BY question_type
ORDER BY question_type;
```

Expected result: only `single_choice` / `multiple_choice` / `judge`.

Current verified evidence:

- `20260513233000-postcheck-structure-results.txt` shows `invalid_question_type_count = 0`, and `SHOW CREATE TABLE yk_question` confirms `question_type` is already live as `ENUM('single_choice','multiple_choice','judge')`.

```sql
SELECT id, question_type, correct_answer, source_ref
FROM yk_question
WHERE source_ref LIKE '[LEGACY-TYPE-INFERRED]%'
ORDER BY id
LIMIT 50;
```

Expected result: 0 rows is best; if rows exist, they are the inferred legacy set that needs manual sampling review.

Current verified evidence:

- `20260513233000-postcheck-structure-results.txt` shows `legacy_type_inferred_count = 0`.

```sql
SELECT session_id, user_id, category_id, mode, status, delete_status
FROM yk_practice_session
ORDER BY id DESC
LIMIT 5;
```

Expected result: session carrier is available; real rows depend on execution data.

```sql
SELECT user_id, question_id, wrong_count, status, delete_status
FROM yk_wrong_question_book
ORDER BY id DESC
LIMIT 5;
```

Expected result: wrong-book carrier is available; real rows depend on execution data.

Current verified evidence:

- `20260513233000-postcheck-structure-results.txt` shows `SHOW CREATE TABLE yk_wrong_question_book` and `SHOW INDEX FROM yk_wrong_question_book`; the live table already carries the formal wrong-book fields plus the unique key `(user_id, question_id)`.

```sql
SELECT id, session_id, question_id, selected_answer, answer_json
FROM yk_practice_record
WHERE selected_answer = 'PENDING_MANUAL_CONFIRM'
ORDER BY id
LIMIT 50;
```

Expected result: 0 rows is best; if rows exist, they are the historical answer snapshots that the compatibility backfill did not parse automatically.

Current verified evidence:

- `20260513233000-postcheck-structure-results.txt` shows `pending_manual_confirm_count = 0`.

```sql
SELECT id, session_id, question_id, selected_answer
FROM yk_practice_record
WHERE selected_answer REGEXP '(^,|,,|,$)';
```

Expected result: 0 rows.

```sql
SELECT TABLE_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'yk_question',
    'yk_question_option',
    'yk_practice_session',
    'yk_practice_record',
    'yk_wrong_question_book'
  )
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

Expected result: native foreign keys exist for category, question, session user/category, session-user composite consistency, wrong-book user/question, and latest wrong record reference.

## Boundary

- The DDL is idempotent and does not drop or rename any baseline table.
- `yk_question` remains the formal main question table.
- `yk_practice_record` now stores both the formal final answer and the historical submit snapshot.
- `yk_wrong_question_book` is the only formal wrong-question table; it manages in-book membership and aggregate error state.
- Historical `question_type` cleanup is executed before enum tightening, and inferred rows are explicitly marked for sampling review.
- Historical `selected_answer` backfill never leaves empty strings as the only fallback; unresolved rows are explicitly marked as `PENDING_MANUAL_CONFIRM`.
- Production execution must still follow backup and approval flow before any write operation.
- The final formal structure scope keeps only 6 business tables and does not include staging tables.
- `20260513224500-exec-ddl-rerun-output.txt` is only a failed rerun attempt that printed `mysql` help output. It is retained for traceability, but it is not a valid formal landing proof.
