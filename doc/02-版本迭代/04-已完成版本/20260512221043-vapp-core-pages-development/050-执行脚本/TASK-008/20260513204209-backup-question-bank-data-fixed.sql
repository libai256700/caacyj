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
-- Dumping data for table `yk_question`
--

LOCK TABLES `yk_question` WRITE;
/*!40000 ALTER TABLE `yk_question` DISABLE KEYS */;
INSERT INTO `yk_question` VALUES (1,NULL,1,'Q-OVERVIEW-0001','single_choice','TODO_STEM','A','[{\"optionCode\": \"A\", \"optionContent\": \"Option A\"}, {\"optionCode\": \"B\", \"optionContent\": \"Option B\"}, {\"optionCode\": \"C\", \"optionContent\": \"Option C\"}, {\"optionCode\": \"D\", \"optionContent\": \"Option D\"}]','{\"correctAnswer\": \"A\"}','TODO_ANALYSIS',1,10,'SOURCE_REF','normal','online',0,'2026-05-13 18:40:36','2026-05-13 18:40:36');
/*!40000 ALTER TABLE `yk_question` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `yk_practice_record`
--

LOCK TABLES `yk_practice_record` WRITE;
/*!40000 ALTER TABLE `yk_practice_record` DISABLE KEYS */;
/*!40000 ALTER TABLE `yk_practice_record` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `yk_question_category`
--

LOCK TABLES `yk_question_category` WRITE;
/*!40000 ALTER TABLE `yk_question_category` DISABLE KEYS */;
INSERT INTO `yk_question_category` VALUES (1,'overview','概述',10,'online',0,'builtin category: overview','2026-05-13 18:38:05','2026-05-13 20:41:07'),(2,'system_components','系统组成及介绍',20,'online',0,'builtin category: system_components','2026-05-13 18:39:45','2026-05-13 20:41:07'),(3,'air_traffic_control','空中交通管制',30,'online',0,'builtin category: air_traffic_control','2026-05-13 18:39:45','2026-05-13 20:41:07'),(4,'flight_manual_and_regulations','无人机飞行手册、法律法规及其他',40,'online',0,'builtin category: flight_manual_and_regulations','2026-05-13 18:39:45','2026-05-13 20:41:07'),(5,'operation_precautions','无人机操作注意事项',50,'online',0,'builtin category: operation_precautions','2026-05-13 18:39:45','2026-05-13 20:41:07'),(6,'meteorology','气象',60,'online',0,'builtin category: meteorology','2026-05-13 18:39:45','2026-05-13 20:41:07'),(7,'rotary_uav','旋翼无人机',70,'online',0,'builtin category: rotary_uav','2026-05-13 18:39:45','2026-05-13 20:41:07'),(8,'mission_planning','无人机任务规划',80,'online',0,'builtin category: mission_planning','2026-05-13 18:39:45','2026-05-13 20:41:07'),(9,'flight_principles_and_performance','飞行原理与飞行性能',90,'online',0,'builtin category: flight_principles_and_performance','2026-05-13 18:39:45','2026-05-13 20:41:07'),(10,'comprehensive_qa','综合问答',100,'online',0,'builtin category: comprehensive_qa','2026-05-13 18:39:45','2026-05-13 20:41:07'),(11,'instructor_question_bank','无人机教员题库',110,'online',0,'builtin category: instructor_question_bank','2026-05-13 18:39:45','2026-05-13 20:41:07');
/*!40000 ALTER TABLE `yk_question_category` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `yk_question_option`
--

LOCK TABLES `yk_question_option` WRITE;
/*!40000 ALTER TABLE `yk_question_option` DISABLE KEYS */;
INSERT INTO `yk_question_option` VALUES (1,1,'A','A','Option A',1,10,'active',0,'2026-05-13 18:40:36','2026-05-13 18:40:36'),(2,1,'B','B','Option B',0,20,'active',0,'2026-05-13 18:40:36','2026-05-13 18:40:36'),(3,1,'C','C','Option C',0,30,'active',0,'2026-05-13 18:40:36','2026-05-13 18:40:36'),(4,1,'D','D','Option D',0,40,'active',0,'2026-05-13 18:40:36','2026-05-13 18:40:36');
/*!40000 ALTER TABLE `yk_question_option` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `yk_question_import_staging`
--

LOCK TABLES `yk_question_import_staging` WRITE;
/*!40000 ALTER TABLE `yk_question_import_staging` DISABLE KEYS */;
/*!40000 ALTER TABLE `yk_question_import_staging` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `yk_question_import_option_staging`
--

LOCK TABLES `yk_question_import_option_staging` WRITE;
/*!40000 ALTER TABLE `yk_question_import_option_staging` DISABLE KEYS */;
/*!40000 ALTER TABLE `yk_question_import_option_staging` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `yk_practice_session`
--

LOCK TABLES `yk_practice_session` WRITE;
/*!40000 ALTER TABLE `yk_practice_session` DISABLE KEYS */;
/*!40000 ALTER TABLE `yk_practice_session` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `yk_wrong_question_book`
--

LOCK TABLES `yk_wrong_question_book` WRITE;
/*!40000 ALTER TABLE `yk_wrong_question_book` DISABLE KEYS */;
/*!40000 ALTER TABLE `yk_wrong_question_book` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-13 20:42:13
