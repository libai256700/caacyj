package com.huiyitech.app.practice.service;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CareerAssessmentIsolationContractTest {

    @Test
    void careerAssessment_shouldExposeOnlyParallelEndpointsAndKeepLegacyAssessmentStartUntouched() throws Exception {
        String controller = source("src/main/java/com/huiyitech/app/practice/controller/FrontPracticeController.java");
        assertTrue(controller.contains("/assessment-result/career/report-entry"));
        assertTrue(controller.contains("/assessment-result/career/completed"));
        assertTrue(controller.contains("/assessment-result/career/{recordId}/regenerate"));
        assertTrue(controller.contains("/start/career-assessment"));
        assertTrue(controller.contains("/app-api/yj/practices/{practiceId}/start"));
        assertTrue(controller.contains("/assessment-result/latest-status"));
        assertTrue(controller.contains("/assessment-result/reset"));

        String service = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        int legacyStart = service.indexOf("public AppPracticeStartRespVO startPractice(String practiceId, String topicId, String mode)");
        int careerStart = service.indexOf("public AppPracticeStartRespVO startCareerAssessment(String practiceId)");
        assertTrue(legacyStart >= 0 && careerStart > legacyStart);
        assertTrue(service.substring(legacyStart, careerStart).contains("frontPracticeBatchService.startAssessment(loginUser, practiceId, topicId)"));
        assertTrue(service.contains("frontPracticeBatchService.startCareerAssessment("));
        assertTrue(service.contains("resetCareerAssessmentHistory(loginUser.getId())"));
        assertTrue(service.contains("getLatestCareerAssessmentReportEntry"));
        assertFalse(service.contains("resetCompletedCareerAssessmentResult"));
        assertFalse(controller.contains("/assessment-result/career/reset"));
    }

    @Test
    void careerAssessment_shouldRouteByCatalogBatchCategoryAndUseFixedAgentThree() throws Exception {
        String service = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        assertTrue(service.contains("private static final Long CAREER_ASSESSMENT_CATEGORY_ID = 14L"));
        assertTrue(service.contains("private static final Long CAREER_ASSESSMENT_AGENT_INFO_ID = 3L"));
        assertTrue(service.contains("findCareerAssessmentAgentConfig"));
        assertTrue(service.contains("findAssessmentAgentConfig(tenantId, CAREER_ASSESSMENT_AGENT_INFO_ID"));
        assertTrue(service.contains("requireCompletedCareerAssessmentBatch"));
        assertTrue(service.contains("!CAREER_ASSESSMENT_CATEGORY_ID.equals(batch.getCategoryId())"));
        assertTrue(service.contains("assessmentSession.categoryId = assessmentCategoryId"));
        assertTrue(service.contains("CAREER_ASSESSMENT_CATEGORY_ID.equals(session == null ? null : session.categoryId)"));
    }

    @Test
    void careerAssessment_shouldKeepAllCategory14StagesObservableWithPromptAndRawResultLogs() throws Exception {
        String service = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        assertTrue(service.contains("stage=submit_received"));
        assertTrue(service.contains("stage=answer_validate status=STARTED"));
        assertTrue(service.contains("stage=answer_validate status=SUCCESS"));
        assertTrue(service.contains("stage=answer_validate status=FAILED"));
        assertTrue(service.contains("stage=result_pending status=CREATED"));
        assertTrue(service.contains("stage=async_enqueue status=QUEUED"));
        assertTrue(service.contains("stage=async_enqueue status=FAILED"));
        assertTrue(service.contains("stage=async_execute status=STARTED"));
        assertTrue(service.contains("stage=async_execute status=SUCCESS"));
        assertTrue(service.contains("stage=async_execute status=FAILED"));
        assertTrue(service.contains("stage=async_execute status=FINISHED"));
        assertTrue(service.contains("stage=agent_resolve status=STARTED"));
        assertTrue(service.contains("stage=agent_resolve status=SUCCESS"));
        assertTrue(service.contains("stage=agent_resolve status=FAILED"));
        assertTrue(service.contains("stage=request_prepare status=STARTED"));
        assertTrue(service.contains("stage=request_prepare status=READY"));
        assertTrue(service.contains("stage=request_prepare status=FAILED"));
        assertTrue(service.contains("stage=model_request status=STARTED"));
        assertTrue(service.contains("stage=model_response status=RECEIVED"));
        assertTrue(service.contains("Career assessment DeepSeek AI invocation params recordId={} sceneCode={} systemPrompt={} userPrompt={} fallback={}"));
        assertTrue(service.contains("Career assessment DeepSeek AI invocation result recordId={} rawResult={}"));
        assertTrue(service.contains("stage=report_clean status=SUCCESS"));
        assertTrue(service.contains("stage=report_clean status=FAILED"));
        assertTrue(service.contains("stage=report_validate status=SUCCESS"));
        assertTrue(service.contains("stage=report_validate status=FAILED"));
        assertTrue(service.contains("stage=state_transition status=PENDING_TO_SUCCESS"));
        assertTrue(service.contains("stage=state_transition status=PENDING_TO_FAILED"));
        assertTrue(service.contains("stage=report_poll status=RESULT"));
        assertFalse(service.contains("Career assessment AI stage=submit_received status=RECEIVED reqVO="));
        assertFalse(service.contains("Career assessment AI stage=model_request status=STARTED apiKey="));
        assertFalse(service.contains("Career assessment AI stage=model_request status=STARTED secret="));
    }

    @Test
    void careerStart_shouldRequireSameCategoryStepMappingsBeforeCreatingSession() throws Exception {
        String batchService = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeBatchService.java");
        assertTrue(batchService.contains("private static final Long CAREER_ASSESSMENT_CATEGORY_ID = 14L"));
        assertTrue(batchService.contains("public AppPracticeStartRespVO startCareerAssessment"));
        assertTrue(batchService.contains("validateCareerAssessmentStepMappings(category.getId(), exerciseIds)"));
        assertTrue(batchService.contains("findPracticeStep(exercise.getStepId(), categoryId) == null"));
        assertTrue(batchService.contains("if (!isCareerAssessmentPlan(plan))"));
    }

    @Test
    void careerFreshStart_shouldDeleteOnlyItsRunDataIncludingSnapshotsAndProtectTemplates() throws Exception {
        String service = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        int cleanupStart = service.indexOf("private void resetCareerAssessmentHistory(Long customerAccountId)");
        int cleanupEnd = service.indexOf("    private void lockCustomerAccountOrThrow", cleanupStart);
        assertTrue(cleanupStart >= 0 && cleanupEnd > cleanupStart);
        String cleanup = service.substring(cleanupStart, cleanupEnd);
        assertTrue(cleanup.contains("lockCustomerAccountOrThrow(customerAccountId)"));
        assertTrue(cleanup.contains("eq(PracticeCatalogBatchDO::getCustomerAccountId, customerAccountId)"));
        assertTrue(cleanup.contains("eq(PracticeCatalogBatchDO::getCategoryId, CAREER_ASSESSMENT_CATEGORY_ID)"));
        assertTrue(cleanup.contains("eq(PracticeCatalogBatchDO::getMode, ASSESSMENT_MODE)"));
        assertTrue(cleanup.contains("selectAssessmentRecordIdsForPhysicalDelete"));
        assertTrue(cleanup.contains("deleteAssessmentResultsByRecordIds"));
        assertTrue(cleanup.contains("physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds"));
        assertTrue(cleanup.contains("deleteCareerAssessmentBatches"));

        int lockStart = service.indexOf("private void lockCustomerAccountOrThrow(Long customerAccountId)");
        int lockEnd = service.indexOf("    private void deleteAssessmentResultsByRecordIds", lockStart);
        assertTrue(lockStart >= 0 && lockEnd > lockStart);
        String lockBlock = service.substring(lockStart, lockEnd);
        assertTrue(lockBlock.contains("SELECT id FROM yj_customer_account WHERE id = ? AND deleted = b'0' FOR UPDATE"));
        assertTrue(lockBlock.contains("职业规划评测用户不存在"));

        int deleteStart = service.indexOf("private void deleteAssessmentResultsByRecordIds(Long customerAccountId, List<Long> recordIds)");
        int deleteEnd = service.indexOf("    private PracticeCatalogBatchDO requireCompletedCareerAssessmentBatch", deleteStart);
        assertTrue(deleteStart >= 0 && deleteEnd > deleteStart);
        String deleteBlock = service.substring(deleteStart, deleteEnd);
        assertTrue(deleteBlock.contains("DELETE FROM yj_assessment_result"));
        assertTrue(deleteBlock.contains("WHERE (customer_account_id = ? OR user_id = ?)"));
        assertTrue(deleteBlock.contains("record_id IN"));

        String batchService = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeBatchService.java");
        int catalogDeleteStart = batchService.indexOf("public AppPracticeStartRespVO startCareerAssessment(LoginUser loginUser, String practiceId, Runnable cleanupAction)");
        int catalogDeleteEnd = batchService.indexOf("    public void deleteCareerAssessmentBatches", catalogDeleteStart);
        assertTrue(catalogDeleteStart >= 0 && catalogDeleteEnd > catalogDeleteStart);
        String startBlock = batchService.substring(catalogDeleteStart, catalogDeleteEnd);
        assertTrue(startBlock.contains("Objects.requireNonNull(cleanupAction, \"cleanupAction\").run()"));
        assertTrue(startBlock.contains("return startCareerAssessmentUnlocked(loginUser, practiceId);"));
        assertFalse(startBlock.contains("resumeLatestIncompleteCareerAssessmentBatch"));

        catalogDeleteStart = batchService.indexOf("public void deleteCareerAssessmentBatches");
        int deleteBatchesEnd = batchService.indexOf("    public AppPracticeAnswerCardRespVO", catalogDeleteStart);
        assertTrue(catalogDeleteStart >= 0 && deleteBatchesEnd > catalogDeleteStart);
        String catalogDelete = batchService.substring(catalogDeleteStart, deleteBatchesEnd);
        assertTrue(catalogDelete.contains("practiceExercisesAnswerBatchMapper.physicalDeleteByCustomerAccountIdAndCatalogBatchIds"));
        assertTrue(catalogDelete.contains("practiceExercisesBatchMapper.physicalDeleteByCustomerAccountIdAndCatalogBatchIds"));
        assertTrue(catalogDelete.contains("physicalDeleteByCustomerAccountIdAndModeAndIds"));
        assertTrue(catalogDelete.contains("runtimeSessions.entrySet().removeIf"));
        assertTrue(catalogDelete.contains("CAREER_ASSESSMENT_CATEGORY_ID.equals(entry.getValue().assessmentCategoryId)"));
        assertTrue(catalogDelete.contains("batchIds.contains(entry.getValue().catalogBatchId)"));
        assertTrue(catalogDelete.indexOf("practiceExercisesAnswerBatchMapper.physicalDelete")
                < catalogDelete.indexOf("practiceExercisesBatchMapper.physicalDelete"));
        assertTrue(catalogDelete.indexOf("practiceExercisesBatchMapper.physicalDelete")
                < catalogDelete.indexOf("physicalDeleteByCustomerAccountIdAndModeAndIds"));
        assertFalse(catalogDelete.contains("practiceExercisesMapper.delete"));
        assertFalse(catalogDelete.contains("practiceExercisesAnswerMapper.delete"));
        assertFalse(catalogDelete.contains("practiceId"));
    }

    @Test
    void careerService_shouldNotExposeResetOrResumeCompatibility() throws Exception {
        String controller = source("src/main/java/com/huiyitech/app/practice/controller/FrontPracticeController.java");
        assertFalse(controller.contains("/assessment-result/career/reset"));

        String service = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        assertFalse(service.contains("resetCompletedCareerAssessmentResult"));
        assertFalse(service.contains("resumeLatestIncompleteCareerAssessmentBatch"));

        String batchService = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeBatchService.java");
        assertFalse(batchService.contains("resumeLatestIncompleteCareerAssessmentBatch"));
    }

    private String source(String relativePath) throws Exception {
        Path path = Paths.get(relativePath);
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }
}
