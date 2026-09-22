# TASK-017 database script entry

This directory is the formal database asset entry for TASK-017 backend and database baseline.

## Files

- `001-baseline-ddl.sql`: first idempotent DDL batch for the current VAPP core pages baseline.
- `database-assets.md`: table inventory, ownership boundary, and validation checklist.

## Execution order

1. Review `database-assets.md`.
2. Execute `001-baseline-ddl.sql` against the target `yunjikeji` database.
3. Run the validation SQL in `database-assets.md`.
4. Keep the actual execution result in the version acceptance record. Do not write production credentials into this directory.

## Command template

```powershell
mysql --default-character-set=utf8mb4 -h <host> -P <port> -u <user> -p yunjikeji < .\001-baseline-ddl.sql
```

