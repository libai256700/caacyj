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
-- Dumping data for table `yk_question_category`
--

LOCK TABLES `yk_question_category` WRITE;
/*!40000 ALTER TABLE `yk_question_category` DISABLE KEYS */;
INSERT INTO `yk_question_category` VALUES (1,'overview','概述',10,'online',0,'builtin category: overview','2026-05-13 18:38:05','2026-05-13 20:41:07'),(2,'system_components','系统组成及介绍',20,'online',0,'builtin category: system_components','2026-05-13 18:39:45','2026-05-13 20:41:07'),(3,'air_traffic_control','空中交通管制',30,'online',0,'builtin category: air_traffic_control','2026-05-13 18:39:45','2026-05-13 20:41:07'),(4,'flight_manual_and_regulations','无人机飞行手册、法律法规及其他',40,'online',0,'builtin category: flight_manual_and_regulations','2026-05-13 18:39:45','2026-05-13 20:41:07'),(5,'operation_precautions','无人机操作注意事项',50,'online',0,'builtin category: operation_precautions','2026-05-13 18:39:45','2026-05-13 20:41:07'),(6,'meteorology','气象',60,'online',0,'builtin category: meteorology','2026-05-13 18:39:45','2026-05-13 20:41:07'),(7,'rotary_uav','旋翼无人机',70,'online',0,'builtin category: rotary_uav','2026-05-13 18:39:45','2026-05-13 20:41:07'),(8,'mission_planning','无人机任务规划',80,'online',0,'builtin category: mission_planning','2026-05-13 18:39:45','2026-05-13 20:41:07'),(9,'flight_principles_and_performance','飞行原理与飞行性能',90,'online',0,'builtin category: flight_principles_and_performance','2026-05-13 18:39:45','2026-05-13 20:41:07'),(10,'comprehensive_qa','综合问答',100,'online',0,'builtin category: comprehensive_qa','2026-05-13 18:39:45','2026-05-13 20:41:07'),(11,'instructor_question_bank','无人机教员题库',110,'online',0,'builtin category: instructor_question_bank','2026-05-13 18:39:45','2026-05-13 20:41:07');
/*!40000 ALTER TABLE `yk_question_category` ENABLE KEYS */;
UNLOCK TABLES;
