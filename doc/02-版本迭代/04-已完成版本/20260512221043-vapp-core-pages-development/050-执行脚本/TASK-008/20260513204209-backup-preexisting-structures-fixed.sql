-- MySQL dump 10.13  Distrib 8.0.24, for Win64 (x86_64)
--
-- Host: 114.111.30.111    Database: yunjikeji
-- ------------------------------------------------------
-- Server version	5.7.44-7.0.1.5-log

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `yk_user_account`
--

DROP TABLE IF EXISTS `yk_user_account`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_user_account` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `mobile` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'User mobile number',
  `nickname` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Display nickname',
  `avatar_url` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Avatar URL',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT 'Account status: active, disabled',
  `password_salt` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Password salt',
  `password_hash` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Password hash',
  `password_initialized_at` datetime DEFAULT NULL COMMENT 'Password initialized time',
  `last_login_at` datetime DEFAULT NULL COMMENT 'Latest login time',
  `last_login_channel` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Latest login channel',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_user_account_mobile` (`mobile`),
  KEY `idx_yk_user_account_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP user account';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `yk_question`
--

DROP TABLE IF EXISTS `yk_question`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_question` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `course_id` bigint(20) unsigned DEFAULT NULL COMMENT 'Related course ID',
  `category_id` bigint(20) unsigned NOT NULL COMMENT 'Question category ID',
  `question_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Question code',
  `question_type` enum('single_choice','multiple_choice','judge') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Question type',
  `stem` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Question stem',
  `correct_answer` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Canonical correct answer',
  `options_json` json DEFAULT NULL COMMENT 'Question options JSON',
  `answer_json` json DEFAULT NULL COMMENT 'Question answer JSON',
  `analysis` text COLLATE utf8mb4_unicode_ci COMMENT 'Answer analysis',
  `score` int(11) NOT NULL DEFAULT '1' COMMENT 'Question score',
  `sort_no` int(11) NOT NULL DEFAULT '0' COMMENT 'Question sort order',
  `source_ref` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Source reference',
  `difficulty` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'normal' COMMENT 'Question difficulty',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft' COMMENT 'Question status: draft, online, offline',
  `delete_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete status: 0-normal, 1-deleted',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_question_code` (`question_code`),
  KEY `idx_yk_question_course_status` (`course_id`,`status`),
  KEY `idx_yk_question_type_status` (`question_type`,`status`),
  KEY `idx_yk_question_category_status` (`category_id`,`status`,`sort_no`,`id`),
  CONSTRAINT `fk_yk_question_category` FOREIGN KEY (`category_id`) REFERENCES `yk_question_category` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP question bank item';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `yk_practice_record`
--

DROP TABLE IF EXISTS `yk_practice_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_practice_record` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `user_id` bigint(20) unsigned NOT NULL COMMENT 'User account ID',
  `course_id` bigint(20) unsigned DEFAULT NULL COMMENT 'Course ID',
  `session_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Practice session ID',
  `question_id` bigint(20) unsigned NOT NULL COMMENT 'Question ID',
  `selected_answer` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Canonical selected answer',
  `answer_json` json DEFAULT NULL COMMENT 'Submitted answer JSON',
  `question_code_snapshot` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Question code snapshot',
  `question_type_snapshot` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Question type snapshot',
  `question_stem_snapshot` text COLLATE utf8mb4_unicode_ci COMMENT 'Question stem snapshot',
  `standard_answer_snapshot` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Standard answer snapshot',
  `question_analysis_snapshot` text COLLATE utf8mb4_unicode_ci COMMENT 'Question analysis snapshot',
  `category_id_snapshot` bigint(20) unsigned DEFAULT NULL COMMENT 'Category ID snapshot',
  `category_code_snapshot` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Category code snapshot',
  `category_name_snapshot` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Category name snapshot',
  `options_snapshot_json` json DEFAULT NULL COMMENT 'Question options snapshot',
  `correct_flag` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Whether answer is correct',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT 'Record status: active, invalid',
  `delete_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete status: 0-normal, 1-deleted',
  `answered_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Answered time',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_practice_record_session_question` (`session_id`,`question_id`),
  KEY `idx_yk_practice_record_user_time` (`user_id`,`answered_at`),
  KEY `idx_yk_practice_record_question` (`question_id`),
  KEY `idx_yk_practice_record_course` (`course_id`),
  KEY `idx_yk_practice_record_session_time` (`session_id`,`answered_at`),
  KEY `fk_yk_practice_record_session_user` (`session_id`,`user_id`),
  KEY `idx_yk_practice_record_user_status` (`user_id`,`status`,`delete_status`,`answered_at`),
  CONSTRAINT `fk_yk_practice_record_question` FOREIGN KEY (`question_id`) REFERENCES `yk_question` (`id`),
  CONSTRAINT `fk_yk_practice_record_session_user` FOREIGN KEY (`session_id`, `user_id`) REFERENCES `yk_practice_session` (`session_id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP practice answer record';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `yk_question_category`
--

DROP TABLE IF EXISTS `yk_question_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_question_category` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `category_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Category code',
  `category_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Category name',
  `sort_no` int(11) NOT NULL DEFAULT '0' COMMENT 'Display order',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'online' COMMENT 'Category status: online, offline',
  `delete_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete status: 0-normal, 1-deleted',
  `description` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Category description',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_question_category_code` (`category_code`),
  KEY `idx_yk_question_category_status_sort` (`status`,`sort_no`,`id`)
) ENGINE=InnoDB AUTO_INCREMENT=35 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP question bank category';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `yk_question_option`
--

DROP TABLE IF EXISTS `yk_question_option`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_question_option` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `question_id` bigint(20) unsigned NOT NULL COMMENT 'Question ID',
  `option_code` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Option code',
  `option_label` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Option display label',
  `option_content` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Option content',
  `is_correct` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Whether this option is correct',
  `sort_no` int(11) NOT NULL DEFAULT '0' COMMENT 'Display order',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT 'Option status: active, invalid',
  `delete_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete status: 0-normal, 1-deleted',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_question_option_question_code` (`question_id`,`option_code`),
  KEY `idx_yk_question_option_question_sort` (`question_id`,`sort_no`,`id`),
  CONSTRAINT `fk_yk_question_option_question` FOREIGN KEY (`question_id`) REFERENCES `yk_question` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP question option';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `yk_question_import_staging`
--

DROP TABLE IF EXISTS `yk_question_import_staging`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_question_import_staging` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `batch_no` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Import batch number',
  `source_file` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Source file path or logical file',
  `source_locator` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Source row or question locator',
  `category_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Target category code',
  `question_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Target question code',
  `question_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'single_choice' COMMENT 'Normalized question type',
  `stem` text COLLATE utf8mb4_unicode_ci COMMENT 'Normalized question stem',
  `correct_answer` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Normalized correct answer',
  `analysis` text COLLATE utf8mb4_unicode_ci COMMENT 'Normalized answer analysis',
  `score` int(11) NOT NULL DEFAULT '1' COMMENT 'Question score',
  `sort_no` int(11) NOT NULL DEFAULT '0' COMMENT 'Display order inside category',
  `source_ref` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Formal source reference',
  `parse_status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'parsed' COMMENT 'parsed, needs_manual_review, ignored_noise',
  `review_reason` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Reason for manual review or ignored noise',
  `options_payload_json` json DEFAULT NULL COMMENT 'Compatibility options snapshot payload',
  `answer_payload_json` json DEFAULT NULL COMMENT 'Compatibility answer snapshot payload',
  `raw_payload_json` json DEFAULT NULL COMMENT 'Raw extracted payload snapshot',
  `imported_at` datetime DEFAULT NULL COMMENT 'Formal import time',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_question_import_staging_question_code` (`question_code`),
  KEY `idx_yk_question_import_staging_batch_status` (`batch_no`,`parse_status`,`category_code`,`sort_no`),
  KEY `idx_yk_question_import_staging_source` (`source_file`,`source_locator`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='TASK-008 question import staging';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `yk_question_import_option_staging`
--

DROP TABLE IF EXISTS `yk_question_import_option_staging`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_question_import_option_staging` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `batch_no` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Import batch number',
  `question_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Target question code',
  `option_code` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Option code',
  `option_label` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Option display label',
  `option_content` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Option content',
  `is_correct` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Whether this option is correct',
  `sort_no` int(11) NOT NULL DEFAULT '0' COMMENT 'Display order',
  `imported_at` datetime DEFAULT NULL COMMENT 'Formal import time',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_question_import_option_staging_question_option` (`question_code`,`option_code`),
  KEY `idx_yk_question_import_option_staging_batch_question` (`batch_no`,`question_code`,`sort_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='TASK-008 question option import staging';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `yk_practice_session`
--

DROP TABLE IF EXISTS `yk_practice_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_practice_session` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `session_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Practice session ID',
  `user_id` bigint(20) unsigned NOT NULL COMMENT 'User account ID',
  `practice_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'practice-default' COMMENT 'Practice instance code',
  `category_id` bigint(20) unsigned NOT NULL COMMENT 'Question category ID',
  `mode` enum('standard','wrongReview') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'standard' COMMENT 'Practice mode: standard, wrongReview',
  `question_count` int(11) NOT NULL DEFAULT '0' COMMENT 'Total question count',
  `answered_count` int(11) NOT NULL DEFAULT '0' COMMENT 'Answered question count',
  `correct_count` int(11) NOT NULL DEFAULT '0' COMMENT 'Correct answer count',
  `wrong_count` int(11) NOT NULL DEFAULT '0' COMMENT 'Wrong answer count',
  `status` enum('in_progress','completed','abandoned') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'in_progress' COMMENT 'Session status: in_progress, completed, abandoned',
  `delete_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete status: 0-normal, 1-deleted',
  `started_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Started time',
  `completed_at` datetime DEFAULT NULL COMMENT 'Completed time',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_practice_session_session_id` (`session_id`),
  UNIQUE KEY `uk_yk_practice_session_session_user` (`session_id`,`user_id`),
  KEY `idx_yk_practice_session_user_status` (`user_id`,`status`,`updated_at`),
  KEY `idx_yk_practice_session_category_status` (`category_id`,`status`,`updated_at`),
  CONSTRAINT `fk_yk_practice_session_category` FOREIGN KEY (`category_id`) REFERENCES `yk_question_category` (`id`),
  CONSTRAINT `fk_yk_practice_session_user` FOREIGN KEY (`user_id`) REFERENCES `yk_user_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP practice session';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `yk_wrong_question_book`
--

DROP TABLE IF EXISTS `yk_wrong_question_book`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `yk_wrong_question_book` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `user_id` bigint(20) unsigned NOT NULL COMMENT 'User account ID',
  `question_id` bigint(20) unsigned NOT NULL COMMENT 'Question ID',
  `latest_practice_record_id` bigint(20) unsigned DEFAULT NULL COMMENT 'Latest wrong practice record ID',
  `latest_session_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Latest wrong session ID',
  `wrong_count` int(11) NOT NULL DEFAULT '0' COMMENT 'Accumulated wrong answer count',
  `latest_selected_answer` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Latest wrong selected answer',
  `latest_wrong_answer_json` json DEFAULT NULL COMMENT 'Latest wrong raw answer snapshot',
  `latest_standard_answer` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Latest wrong standard answer snapshot',
  `latest_wrong_at` datetime DEFAULT NULL COMMENT 'Latest wrong answered time',
  `status` enum('active','removed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT 'Wrong question status: active, removed',
  `removed_at` datetime DEFAULT NULL COMMENT 'Removed time',
  `delete_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete status: 0-normal, 1-deleted',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_yk_wrong_question_book_user_question` (`user_id`,`question_id`),
  KEY `idx_yk_wrong_question_book_user_status` (`user_id`,`status`,`updated_at`),
  KEY `idx_yk_wrong_question_book_question_status` (`question_id`,`status`,`updated_at`),
  KEY `fk_yk_wrong_question_book_record` (`latest_practice_record_id`),
  CONSTRAINT `fk_yk_wrong_question_book_question` FOREIGN KEY (`question_id`) REFERENCES `yk_question` (`id`),
  CONSTRAINT `fk_yk_wrong_question_book_record` FOREIGN KEY (`latest_practice_record_id`) REFERENCES `yk_practice_record` (`id`),
  CONSTRAINT `fk_yk_wrong_question_book_user` FOREIGN KEY (`user_id`) REFERENCES `yk_user_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='VAPP wrong question book';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-13 20:42:11
