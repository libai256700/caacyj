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
