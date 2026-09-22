package com.huiyitech.practice;

import com.huiyitech.practice.service.UserPracticeExercisesRecordServiceImpl;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UserPracticeExercisesRecordSqlContractTest {

    @Test
    void categoryNameExpression_shouldUseExplicitUnicodeCollation() {
        String categoryNameSql = (String) ReflectionTestUtils.getField(
                UserPracticeExercisesRecordServiceImpl.class, "CATEGORY_NAME_SQL");

        assertEquals("(COALESCE(NULLIF(pcb.category_name, ''), NULLIF(pc.category_name, ''), '') "
                + "COLLATE utf8mb4_unicode_ci)", categoryNameSql);
    }

    @Test
    void practiceRecordDisplayExpression_shouldFormatPracticeTimeAndCategoryName() {
        String practiceRecordDisplaySql = (String) ReflectionTestUtils.getField(
                UserPracticeExercisesRecordServiceImpl.class, "PRACTICE_RECORD_DISPLAY_SQL");

        assertEquals("CONCAT(DATE_FORMAT(r.create_time, '%Y-%m-%d %H:%i:%s'), ' + ', "
                + "(COALESCE(NULLIF(pcb.category_name, ''), NULLIF(pc.category_name, ''), '') "
                + "COLLATE utf8mb4_unicode_ci))", practiceRecordDisplaySql);
    }

    @Test
    void questionStemExpression_shouldUseExplicitUnicodeCollation() {
        String questionStemSql = (String) ReflectionTestUtils.getField(
                UserPracticeExercisesRecordServiceImpl.class, "QUESTION_STEM_SQL");

        assertEquals("(COALESCE(NULLIF(pe.question_stem, ''), '') COLLATE utf8mb4_unicode_ci)", questionStemSql);
    }

    @Test
    void wrongDetailFromSql_shouldJoinCategoryAndQuestionTables() {
        String fromSql = (String) ReflectionTestUtils.getField(
                UserPracticeExercisesRecordServiceImpl.class, "PRACTICE_WRONG_DETAIL_FROM_SQL");

        assertTrue(fromSql.contains("LEFT JOIN yj_practice_catalog_batch pcb ON pcb.id = r.category_id"));
        assertTrue(fromSql.contains("LEFT JOIN yj_practice_category pc ON pc.id = pcb.category_id"));
        assertTrue(fromSql.contains("LEFT JOIN yj_practice_exercises_batch peb ON peb.id = d.exercises_id"));
        assertTrue(fromSql.contains("LEFT JOIN yj_practice_exercises pe ON pe.id = peb.exercises_id"));
    }

    @Test
    void wrongDetailWhere_shouldFilterCategoryQuestionAndBooleanWhenProvided() {
        UserPracticeExercisesRecordServiceImpl service = new UserPracticeExercisesRecordServiceImpl();
        Map<String, String> params = new LinkedHashMap<>();
        params.put("category_name", "概述");
        params.put("question_keyword", "题干");
        params.put("is_correct", "false");

        Object sqlBuilder = ReflectionTestUtils.invokeMethod(service, "buildPracticeWrongDetailWhere", params);
        String whereSql = getWhereSql(sqlBuilder);
        List<?> args = getArgs(sqlBuilder);

        assertTrue(whereSql.contains("WHERE d.deleted = b'0' AND r.deleted = b'0'"));
        assertTrue(whereSql.contains("AND (COALESCE(NULLIF(pcb.category_name, ''), NULLIF(pc.category_name, ''), '') "
                + "COLLATE utf8mb4_unicode_ci) LIKE ?"));
        assertTrue(whereSql.contains("AND (COALESCE(NULLIF(pe.question_stem, ''), '') COLLATE utf8mb4_unicode_ci) LIKE ?"));
        assertTrue(whereSql.contains("AND d.is_correct = ?"));
        assertIterableEquals(Arrays.asList("%概述%", "%题干%", false), args);
    }

    @Test
    void wrongDetailWhere_shouldNotAppendBooleanFilterWhenIsCorrectIsBlank() {
        UserPracticeExercisesRecordServiceImpl service = new UserPracticeExercisesRecordServiceImpl();
        Map<String, String> params = new LinkedHashMap<>();
        params.put("is_correct", "");

        Object sqlBuilder = ReflectionTestUtils.invokeMethod(service, "buildPracticeWrongDetailWhere", params);
        String whereSql = getWhereSql(sqlBuilder);
        List<?> args = getArgs(sqlBuilder);

        assertFalse(whereSql.contains("d.is_correct = ?"));
        assertTrue(args.isEmpty());
    }

    private static String getWhereSql(Object sqlBuilder) {
        return ((StringBuilder) ReflectionTestUtils.getField(sqlBuilder, "whereSql")).toString();
    }

    @SuppressWarnings("unchecked")
    private static List<Object> getArgs(Object sqlBuilder) {
        return (List<Object>) ReflectionTestUtils.getField(sqlBuilder, "args");
    }
}
