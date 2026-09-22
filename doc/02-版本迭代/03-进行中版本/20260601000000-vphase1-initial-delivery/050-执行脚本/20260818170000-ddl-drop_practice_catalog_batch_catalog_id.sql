-- 统一练习批次来源为 yj_practice_category；仅允许在目标列确实存在时执行。
DELIMITER //

CREATE PROCEDURE migrate_practice_catalog_batch_category_source()
BEGIN
    DECLARE catalog_id_column_count INT DEFAULT 0;

    SELECT COUNT(*) INTO catalog_id_column_count
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'yj_practice_catalog_batch'
      AND COLUMN_NAME = 'catalog_id';

    IF catalog_id_column_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'yj_practice_catalog_batch.catalog_id must exist before migration';
    END IF;

    UPDATE yj_practice_catalog_batch
    SET category_id = catalog_id
    WHERE category_id IS NULL
      AND catalog_id IS NOT NULL
      AND type IN (1, 2);

    ALTER TABLE yj_practice_catalog_batch DROP COLUMN catalog_id;
END//

CALL migrate_practice_catalog_batch_category_source()//
DROP PROCEDURE migrate_practice_catalog_batch_category_source//

DELIMITER ;
