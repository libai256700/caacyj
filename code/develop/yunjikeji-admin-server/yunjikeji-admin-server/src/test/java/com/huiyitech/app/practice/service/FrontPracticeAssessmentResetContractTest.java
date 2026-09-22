package com.huiyitech.app.practice.service;

import cn.iocoder.yudao.framework.security.core.LoginUser;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.huiyitech.aiconfig.AiSceneCodes;
import com.huiyitech.aiconfig.dal.dataobject.AiModelConfigDO;
import com.huiyitech.aiconfig.service.AiModelConfigService;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCatalogBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesBatchDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeCatalogBatchMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesAnswerBatchMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesBatchMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordDetailMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordMapper;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.MockedStatic;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.mockStatic;

class FrontPracticeAssessmentResetContractTest {

    @Test
    void resetCompletedAssessmentResult_shouldOnlyDeleteCurrentUsersAssessmentData() {
        FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        UserPracticeExercisesRecordMapper recordMapper = mock(UserPracticeExercisesRecordMapper.class);
        UserPracticeExercisesRecordDetailMapper recordDetailMapper = mock(UserPracticeExercisesRecordDetailMapper.class);
        JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
        FrontPracticeBatchService batchService = mock(FrontPracticeBatchService.class);
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordMapper", recordMapper);
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordDetailMapper", recordDetailMapper);
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplate);
        ReflectionTestUtils.setField(service, "frontPracticeBatchService", batchService);
        when(catalogBatchMapper.selectList(any())).thenReturn(Collections.singletonList(PracticeCatalogBatchDO.builder()
                .id(101L).customerAccountId(9001L).categoryId(13L).recordId(201L)
                .mode("ASSESSMENT").completed(Boolean.TRUE).build()));
        when(recordMapper.selectAssessmentRecordIdsForPhysicalDelete(eq(9001L), eq("assessment"),
                eq(Collections.singletonList(101L)))).thenReturn(Collections.singletonList(201L));
        Map<String, Object> completedReport = new HashMap<>();
        completedReport.put("record_id", 201L);
        completedReport.put("report_status", "SUCCESS");
        completedReport.put("report_content", completeReportContent());
        assertTrue(isCompleteReportForTest((String) completedReport.get("report_content")));
        when(jdbcTemplate.queryForList(anyString(), eq(9001L), eq(9001L)))
                .thenReturn(Collections.singletonList(completedReport));
        when(jdbcTemplate.update(anyString(), any(Object[].class))).thenReturn(1);

        assertTrue(withLogin(() -> service.resetCompletedAssessmentResult()));

        verify(jdbcTemplate).update(org.mockito.ArgumentMatchers.contains("record_id IN"),
                eq(9001L), eq(9001L), eq(201L));
        verify(recordDetailMapper).physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(eq(9001L),
                eq("assessment"), eq(Collections.singletonList(101L)));
        verify(recordMapper).physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(eq(9001L),
                eq("assessment"), eq(Collections.singletonList(101L)));
        verify(batchService).deleteAssessmentBatches(eq(9001L), eq(Collections.singletonList(101L)));
        verify(batchService, never()).deleteAssessmentBatches(eq(9002L), any());
    }

    @Test
    void deleteAssessmentBatches_shouldDeleteOptionsBeforeExercisesAndCatalogForOneUser() {
        FrontPracticeBatchService service = new FrontPracticeBatchService();
        PracticeExercisesBatchMapper exerciseBatchMapper = mock(PracticeExercisesBatchMapper.class);
        PracticeExercisesAnswerBatchMapper answerBatchMapper = mock(PracticeExercisesAnswerBatchMapper.class);
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        ReflectionTestUtils.setField(service, "practiceExercisesBatchMapper", exerciseBatchMapper);
        ReflectionTestUtils.setField(service, "practiceExercisesAnswerBatchMapper", answerBatchMapper);
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);
        when(exerciseBatchMapper.selectList(any())).thenReturn(Collections.singletonList(PracticeExercisesBatchDO.builder()
                .id(301L).customerAccountId(9001L).catalogBatchId(101L).build()));

        service.deleteAssessmentBatches(9001L, Collections.singletonList(101L));

        org.mockito.InOrder order = org.mockito.Mockito.inOrder(answerBatchMapper, exerciseBatchMapper, catalogBatchMapper);
        order.verify(answerBatchMapper).physicalDeleteByCustomerAccountIdAndCatalogBatchIds(eq(9001L),
                eq(Collections.singletonList(101L)));
        order.verify(exerciseBatchMapper).physicalDeleteByCustomerAccountIdAndCatalogBatchIds(eq(9001L),
                eq(Collections.singletonList(101L)));
        order.verify(catalogBatchMapper).physicalDeleteByCustomerAccountIdAndModeAndIds(eq(9001L),
                eq("ASSESSMENT"), eq(Collections.singletonList(101L)));
    }

    @Test
    void resetCompletedAssessmentResult_shouldBeTransactional() throws Exception {
        assertTrue(FrontPracticeServiceImpl.class
                .getMethod("resetCompletedAssessmentResult")
                .isAnnotationPresent(Transactional.class));
    }

    @Test
    void resetCompletedAssessmentResult_shouldNotDeleteUnfinishedAssessment() {
        FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
        JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        UserPracticeExercisesRecordMapper recordMapper = mock(UserPracticeExercisesRecordMapper.class);
        UserPracticeExercisesRecordDetailMapper recordDetailMapper = mock(UserPracticeExercisesRecordDetailMapper.class);
        FrontPracticeBatchService batchService = mock(FrontPracticeBatchService.class);
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplate);
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordMapper", recordMapper);
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordDetailMapper", recordDetailMapper);
        ReflectionTestUtils.setField(service, "frontPracticeBatchService", batchService);
        when(catalogBatchMapper.selectList(any())).thenReturn(Collections.emptyList());
        Map<String, Object> pendingReport = new HashMap<>();
        pendingReport.put("record_id", 201L);
        pendingReport.put("report_status", "PENDING");
        pendingReport.put("report_content", "");
        when(jdbcTemplate.queryForList(anyString(), eq(9001L), eq(9001L)))
                .thenReturn(Collections.singletonList(pendingReport));
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), ""),
                PracticeCatalogBatchDO.class);

        assertFalse(withLogin(() -> service.resetCompletedAssessmentResult()));

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Wrapper> wrapperCaptor = ArgumentCaptor.forClass(Wrapper.class);
        verify(catalogBatchMapper).selectList(wrapperCaptor.capture());
        Wrapper<?> wrapper = wrapperCaptor.getValue();
        assertTrue(wrapper.getSqlSegment().replace("_", "").toLowerCase().contains("completed"));
        @SuppressWarnings("unchecked")
        Map<String, Object> parameters = (Map<String, Object>) ReflectionTestUtils.getField(
                wrapper, "paramNameValuePairs");
        assertTrue(parameters.containsValue(Boolean.TRUE));
        verify(recordMapper, never()).selectAssessmentRecordIdsForPhysicalDelete(anyLong(), anyString(), any());
        verify(recordDetailMapper, never()).physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(
                anyLong(), anyString(), any());
        verify(batchService, never()).deleteAssessmentBatches(anyLong(), any());
        verify(jdbcTemplate, never()).update(anyString(), any(Object[].class));
    }

    @Test
    void hasCompletedAssessmentResult_shouldUseCompletedAssessmentBatchEvenWithoutReport() {
        FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);
        when(catalogBatchMapper.selectList(any())).thenReturn(Collections.singletonList(PracticeCatalogBatchDO.builder()
                .id(101L).customerAccountId(9001L).categoryId(13L).mode("ASSESSMENT")
                .completed(Boolean.TRUE).build()));

        assertTrue(withLogin(() -> service.hasCompletedAssessmentResult()));
    }

    @Test
    void hasCompletedAssessmentResult_shouldIgnoreCompletedOrdinaryBatch() {
        FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);
        when(catalogBatchMapper.selectList(any())).thenReturn(Collections.emptyList());
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), ""),
                PracticeCatalogBatchDO.class);

        assertFalse(withLogin(() -> service.hasCompletedAssessmentResult()));

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Wrapper> wrapperCaptor = ArgumentCaptor.forClass(Wrapper.class);
        verify(catalogBatchMapper).selectList(wrapperCaptor.capture());
        Wrapper<?> wrapper = wrapperCaptor.getValue();
        String normalizedSqlSegment = wrapper.getSqlSegment().replace("_", "").toLowerCase();
        assertTrue(normalizedSqlSegment.contains("customaccountid"));
        assertTrue(normalizedSqlSegment.contains("categoryid"));
        assertTrue(normalizedSqlSegment.contains("mode"));
        assertTrue(normalizedSqlSegment.contains("completed"));
        @SuppressWarnings("unchecked")
        Map<String, Object> parameters = (Map<String, Object>) ReflectionTestUtils.getField(
                wrapper, "paramNameValuePairs");
        assertTrue(parameters.containsValue(9001L));
        assertTrue(parameters.containsValue(13L));
        assertTrue(parameters.containsValue("ASSESSMENT"));
        assertTrue(parameters.containsValue(Boolean.TRUE));
    }

    @Test
    void resetCompletedAssessmentResult_shouldDeletePendingAssessmentReport() {
        assertResetForReportStatus("PENDING");
    }

    @Test
    void resetCompletedAssessmentResult_shouldDeleteFailedAssessmentReport() {
        assertResetForReportStatus("FAILED");
    }

    @Test
    void resetCompletedAssessmentResult_shouldNotDeleteMispointedPracticeRecord() {
        FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
        JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        UserPracticeExercisesRecordMapper recordMapper = mock(UserPracticeExercisesRecordMapper.class);
        UserPracticeExercisesRecordDetailMapper recordDetailMapper = mock(UserPracticeExercisesRecordDetailMapper.class);
        FrontPracticeBatchService batchService = mock(FrontPracticeBatchService.class);
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplate);
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordMapper", recordMapper);
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordDetailMapper", recordDetailMapper);
        ReflectionTestUtils.setField(service, "frontPracticeBatchService", batchService);
        when(catalogBatchMapper.selectList(any())).thenReturn(Collections.singletonList(PracticeCatalogBatchDO.builder()
                .id(101L).customerAccountId(9001L).categoryId(13L).recordId(301L)
                .mode("ASSESSMENT").completed(Boolean.TRUE).build()));
        when(recordMapper.selectAssessmentRecordIdsForPhysicalDelete(eq(9001L), eq("assessment"),
                eq(Collections.singletonList(101L)))).thenReturn(Collections.emptyList());

        assertTrue(withLogin(() -> service.resetCompletedAssessmentResult()));

        verify(jdbcTemplate, never()).update(anyString(), any(Object[].class));
        verify(recordDetailMapper, never()).physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(
                anyLong(), anyString(), any());
        verify(recordMapper, never()).physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(
                anyLong(), anyString(), any());
        verify(batchService).deleteAssessmentBatches(eq(9001L), eq(Collections.singletonList(101L)));
    }

    private void assertResetForReportStatus(String reportStatus) {
        FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
        JdbcTemplate jdbcTemplate = mock(JdbcTemplate.class);
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        UserPracticeExercisesRecordMapper recordMapper = mock(UserPracticeExercisesRecordMapper.class);
        UserPracticeExercisesRecordDetailMapper recordDetailMapper = mock(UserPracticeExercisesRecordDetailMapper.class);
        FrontPracticeBatchService batchService = mock(FrontPracticeBatchService.class);
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplate);
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordMapper", recordMapper);
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordDetailMapper", recordDetailMapper);
        ReflectionTestUtils.setField(service, "frontPracticeBatchService", batchService);
        when(catalogBatchMapper.selectList(any())).thenReturn(Collections.singletonList(PracticeCatalogBatchDO.builder()
                .id(101L).customerAccountId(9001L).categoryId(13L).recordId(201L)
                .mode("ASSESSMENT").completed(Boolean.TRUE).build()));
        when(recordMapper.selectAssessmentRecordIdsForPhysicalDelete(eq(9001L), eq("assessment"),
                eq(Collections.singletonList(101L)))).thenReturn(Collections.singletonList(201L));
        Map<String, Object> report = new HashMap<>();
        report.put("record_id", 201L);
        report.put("report_status", reportStatus);
        report.put("report_content", "");
        when(jdbcTemplate.queryForList(anyString(), eq(9001L), eq(9001L)))
                .thenReturn(Collections.singletonList(report));
        when(jdbcTemplate.update(anyString(), any(Object[].class))).thenReturn(1);

        assertTrue(withLogin(() -> service.resetCompletedAssessmentResult()));

        verify(batchService).deleteAssessmentBatches(eq(9001L), eq(Collections.singletonList(101L)));
        verify(recordDetailMapper).physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(eq(9001L),
                eq("assessment"), eq(Collections.singletonList(101L)));
        verify(recordMapper).physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(eq(9001L),
                eq("assessment"), eq(Collections.singletonList(101L)));
    }

    private <T> T withLogin(java.util.function.Supplier<T> action) {
        LoginUser loginUser = new LoginUser();
        loginUser.setId(9001L);
        try (MockedStatic<com.huiyitech.framework.security.AppMobileAuthUtils> authMock =
                     mockStatic(com.huiyitech.framework.security.AppMobileAuthUtils.class)) {
            authMock.when(com.huiyitech.framework.security.AppMobileAuthUtils::requireStudentLoginUser)
                    .thenReturn(loginUser);
            return action.get();
        }
    }

    private static String completeReportContent() {
        String brandContent;
        try {
            String source = new String(java.nio.file.Files.readAllBytes(
                    java.nio.file.Paths.get("E:/huiyitechworkspace/feixingxueyuan/eval_ai_transform_redacted.mjs")),
                    java.nio.charset.StandardCharsets.UTF_8);
            java.util.regex.Matcher matcher = java.util.regex.Pattern
                    .compile("const BRAND_CONTENT = `([\\s\\S]*?)`;").matcher(source);
            if (!matcher.find()) {
                throw new AssertionError("brand content fixture missing");
            }
            brandContent = matcher.group(1);
        } catch (java.io.IOException exception) {
            throw new AssertionError(exception);
        }
        return "<section><h1>基础信息概览</h1><p>aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</p>"
                + "<h2>核心适配度评估</h2><p>bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb</p>"
                + "<h2>课程推荐</h2><p>cccccccccccccccccccccccccccccccccccccccc</p>"
                + "<h2>入行规划</h2><p>dddddddddddddddddddddddddddddddddddddddd</p>"
                + "<h2>行业资讯</h2><p>eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee</p>"
                + "<h2>评估结论</h2><p>ffffffffffffffffffffffffffffffffffffffff</p></section>"
                + brandContent;
    }

    private static boolean isCompleteReportForTest(String content) {
        try {
            FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
            AiModelConfigService aiModelConfigService = mock(AiModelConfigService.class);
            when(aiModelConfigService.getRequiredActiveBySceneCode(AiSceneCodes.PRACTICE_ASSESSMENT))
                    .thenReturn(AiModelConfigDO.builder().minReportLength(200).build());
            ReflectionTestUtils.setField(service, "aiModelConfigService", aiModelConfigService);
            java.lang.reflect.Method method = FrontPracticeServiceImpl.class
                    .getDeclaredMethod("isCompleteAssessmentReport", String.class);
            method.setAccessible(true);
            return (Boolean) method.invoke(service, content);
        } catch (ReflectiveOperationException exception) {
            throw new AssertionError(exception);
        }
    }
}
