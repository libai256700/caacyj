-- ============================================
-- Script type: ddl
-- Description: add agent id for yj_agent_info synchronization
-- Created at: 2026-07-02 14:30:00
-- Author: Codex
-- Impact scope: yj_agent_info add agent_id column and index
-- Environment: test, production
-- ============================================

-- Pre-check: current column and index state.
SELECT column_name, column_type, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'yj_agent_info'
  AND column_name = 'agent_id';

SELECT index_name, column_name
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'yj_agent_info'
  AND index_name = 'idx_yj_agent_info_agent_id';

DROP PROCEDURE IF EXISTS `add_yj_agent_info_agent_id_if_missing`;
DELIMITER $$
CREATE PROCEDURE `add_yj_agent_info_agent_id_if_missing`()
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'yj_agent_info'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'yj_agent_info'
      AND column_name = 'agent_id'
  ) THEN
    ALTER TABLE `yj_agent_info`
      ADD COLUMN `agent_id` varchar(128) DEFAULT NULL COMMENT 'QwenPaw agent id' AFTER `id`;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'yj_agent_info'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'yj_agent_info'
      AND index_name = 'idx_yj_agent_info_agent_id'
  ) THEN
    ALTER TABLE `yj_agent_info`
      ADD KEY `idx_yj_agent_info_agent_id` (`agent_id`);
  END IF;
END$$
DELIMITER ;

CALL `add_yj_agent_info_agent_id_if_missing`();

DROP PROCEDURE IF EXISTS `add_yj_agent_info_agent_id_if_missing`;

-- Post-check: column and index after execution.
SELECT column_name, column_type, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'yj_agent_info'
  AND column_name = 'agent_id';

SELECT index_name, column_name
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'yj_agent_info'
  AND index_name = 'idx_yj_agent_info_agent_id';
