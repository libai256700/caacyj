# TASK-017 database assets

## Scope

This asset pack covers the first backend database baseline for VAPP core pages. It provides table structure only. It does not include seed data, production data changes, or credential records.

## Table inventory

| Table | Purpose | Current script |
| --- | --- | --- |
| `yk_user_account` | Mobile-based user account baseline for login and user profile linkage. | `001-baseline-ddl.sql` |
| `yk_training_course` | Training course display and ordering baseline. | `001-baseline-ddl.sql` |
| `yk_question` | Question bank item baseline for practice and answer pages. | `001-baseline-ddl.sql` |
| `yk_practice_record` | User answer and practice history baseline. | `001-baseline-ddl.sql` |

## Validation SQL

```sql
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'yk_user_account',
    'yk_training_course',
    'yk_question',
    'yk_practice_record'
  )
ORDER BY TABLE_NAME;
```

Expected result: 4 rows.

```sql
SELECT 1 AS database_ready;
```

Expected result: `database_ready = 1`.

## Boundary

- Scripts are idempotent through `CREATE TABLE IF NOT EXISTS`.
- Scripts do not drop or rename tables.
- Production execution must follow backup and approval flow before any write operation.
- Test execution result can be linked with the TASK-017 `mvn test` conclusion, but SQL execution should still be recorded separately when the script is run against a real database.

