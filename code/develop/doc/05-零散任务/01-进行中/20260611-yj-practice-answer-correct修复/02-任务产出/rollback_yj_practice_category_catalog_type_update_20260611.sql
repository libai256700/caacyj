-- Rollback for yj_practice_category.catalog_type migration.
-- Replace ${BACKUP_TABLE} with the backup table recorded in practice_category_catalog_type_update_result_20260611.json.
-- Example backup table name: yj_practice_category_catalog_type_bak_YYYYMMDDHHMMSS.
-- If this is the first migration run, the backup table will not contain catalog_type, so dropping the added column is the rollback.

SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = '${BACKUP_TABLE}';

SELECT TABLE_NAME, COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME = 'catalog_type'
  AND TABLE_NAME IN ('yj_practice_category', '${BACKUP_TABLE}');

SELECT id, category_name, catalog_type
FROM yj_practice_category
WHERE deleted = b'0'
ORDER BY catalog_type, id;

ALTER TABLE yj_practice_category DROP COLUMN catalog_type;
