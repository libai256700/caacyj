# TASK-008 question bank database assets

This directory is the formal SQL asset entry for TASK-008 practice-page question bank design.

## Current execution gate

This round records only the final formal structure. The staging-table route is no longer part of the formal structure scope in this directory.

## Files

- `20260513220000-ddl-question-bank-schema-v2.sql`: current formal executable DDL route for test DB landing. Use this as the primary execution entry.
- `20260513221000-dml-question-category-seed-v2.sql`: current formal 11-category seed route. Use this as the primary category seed entry.
- `20260513190000-ddl-question-bank-schema.sql`: historical draft DDL asset retained for traceability; not the preferred execution entry after the 2026-05-13 v2 correction.
- `20260513191000-dml-question-category-seed.sql`: historical draft seed asset retained for traceability; not the preferred execution entry after the 2026-05-13 v2 correction.
- `20260513192000-dml-question-import-template.sql`: executable template for follow-up question import.
- `20260513222000-question-bank-import-baseline-v2.json`: current-round readable baseline after the 2026-05-13 v2 correction.
- `20260513200000-question-bank-import-baseline.json`: historical draft baseline retained for traceability.
- `database-assets.md`: inventory, execution order, validation checklist, and constraint summary.

## Execution order

The order below is the final formal structure route only. It is not authorization to run scripts in this round.

1. Execute `..\TASK-017\001-baseline-ddl.sql` if the baseline has not been applied.
2. Execute `20260513220000-ddl-question-bank-schema-v2.sql`. This is the current formal executable route for test DB landing.
3. Review the result sets returned by step 2:
   - `source_ref LIKE '[LEGACY-TYPE-INFERRED]%'` means the row was inferred before enum tightening and should be sampled manually.
   - `selected_answer = 'PENDING_MANUAL_CONFIRM'` means historical `answer_json` was not parsed by the compatibility rules and needs manual correction.
4. Execute `20260513221000-dml-question-category-seed-v2.sql`.
5. Use `20260513222000-question-bank-import-baseline-v2.json` only as a reference baseline for later content preparation. It is not part of the final formal structure.
6. Use `20260513192000-dml-question-import-template.sql` only as a single-question fallback or patch template.
7. Run the validation SQL in `database-assets.md`.

## Current verified landing evidence

- Formal DDL success evidence: `20260513195800-exec-ddl-native-constraints-output.txt`.
- Formal data/status postcheck evidence: `20260513204058-postcheck-results.txt`.
- Formal structure/constraint postcheck evidence: `20260513233000-postcheck-structure-results.txt`.
- `20260513224500-exec-ddl-rerun-output.txt` is not valid success evidence. That file is a `mysql` help output caused by a command misuse, so the current-round landing conclusion must be based on the live postcheck result files above instead of that rerun attempt.

Current verified result:

- The 6 key tables are present in the current test DB: `yk_question_category`, `yk_question`, `yk_question_option`, `yk_practice_session`, `yk_practice_record`, `yk_wrong_question_book`.
- `yk_question.question_type` is live as `ENUM('single_choice','multiple_choice','judge')`.
- `yk_practice_session.mode` is live as `ENUM('standard','wrongReview')`, and `status` is live as `ENUM('in_progress','completed','abandoned')`.
- `yk_practice_record` already carries the formal answer field plus the required snapshot fields.
- `yk_wrong_question_book` already carries the formal wrong-book fields and the unique key `(user_id, question_id)`.
- Current live counts are `invalid_question_type_count = 0`, `legacy_type_inferred_count = 0`, and `pending_manual_confirm_count = 0`.
- The final formal structure scope is limited to 6 business tables only and does not include any staging table.

## Current constraint route

The formal executable route uses only native constraints that the current account can apply:

- physical foreign keys
- unique indexes
- non-null columns
- enum-backed value domains where the current MySQL version supports them reliably

This directory no longer depends on trigger creation for formal execution.

Current residual boundary:

- `question_type` legacy dirty values are cleaned before enum tightening. The current live test DB postcheck shows `legacy_type_inferred_count = 0`, but this check must still be rerun after any future data reload.
- `selected_answer` backfill now covers common scalar and array payload shapes. The current live test DB postcheck shows `pending_manual_confirm_count = 0`, but this check must still be rerun after any future historical data replay.
- `correct_flag` remains `TINYINT(1)` on the current baseline; MySQL 5.7 `CHECK` is not a reliable formal guard, so the `0/1` boundary stays under template and application write-path control.
- The current repository does not contain a full 1512-row formal question payload inside `TASK-008`; content preparation is outside the final formal structure scope of this round.

## Command template

Command templates are retained only for future confirmed execution. Do not run them in this round.

```powershell
mysql --default-character-set=utf8mb4 -h <host> -P <port> -u <user> -p yunjikeji < .\20260513220000-ddl-question-bank-schema-v2.sql
mysql --default-character-set=utf8mb4 -h <host> -P <port> -u <user> -p yunjikeji < .\20260513221000-dml-question-category-seed-v2.sql
```

Keep real execution results in the formal acceptance record. Do not write production credentials into this directory.
