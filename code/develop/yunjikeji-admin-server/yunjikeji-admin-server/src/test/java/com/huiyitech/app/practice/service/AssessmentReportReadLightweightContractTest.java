package com.huiyitech.app.practice.service;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AssessmentReportReadLightweightContractTest {

    @Test
    void reportEndpoints_shouldExposeDedicatedLightweightResponses() throws Exception {
        String controller = source("src/main/java/com/huiyitech/app/practice/controller/FrontPracticeController.java");

        assertTrue(controller.contains("/assessment-result/self/{recordId}"));
        assertTrue(controller.contains("CommonResult<AppAssessmentReportRespVO> getSelfAssessmentReport"));
        assertTrue(controller.contains("CommonResult<AppAssessmentReportRespVO> getCareerAssessmentReport"));
    }

    @Test
    void lightweightReportMethods_shouldNotBuildRecordDetailsOrAnswers() throws Exception {
        String service = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        String selfReport = methodBlock(service, "public AppAssessmentReportRespVO getSelfAssessmentReport(Long recordId)");
        String careerReport = methodBlock(service, "public AppAssessmentReportRespVO getCareerAssessmentReport(Long recordId)");

        assertLightweight(selfReport);
        assertLightweight(careerReport);
        assertTrue(selfReport.contains("requireCompletedAssessmentBatch"));
        assertTrue(careerReport.contains("requireCompletedCareerAssessmentBatch"));
    }

    @Test
    void genericRecordDetail_shouldKeepAnswerDetailContract() throws Exception {
        String service = source("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        String detail = methodBlock(service, "public AppPracticeRecordDetailRespVO getRecordDetail(String recordId)");
        String detailVo = source("src/main/java/com/huiyitech/app/practice/controller/vo/AppPracticeRecordDetailRespVO.java");

        assertTrue(detail.contains("listExerciseStatsForCategoryPage()"));
        assertTrue(detail.contains("frontPracticeBatchService.buildRecordAnswers(record)"));
        assertTrue(detail.contains(".answers(answers)"));
        assertTrue(detailVo.contains("private List<AppPracticeRecordAnswerRespVO> answers;"));
    }

    @Test
    void lightweightResponse_shouldContainOnlyReportFields() throws Exception {
        String response = source("src/main/java/com/huiyitech/app/practice/controller/vo/AppAssessmentReportRespVO.java");

        assertTrue(response.contains("private String id;"));
        assertTrue(response.contains("private String assessmentTime;"));
        assertTrue(response.contains("private String assessmentReportStatus;"));
        assertTrue(response.contains("private String assessmentReportFailureReason;"));
        assertTrue(response.contains("private String selfReportContent;"));
        assertFalse(response.contains("answers"));
        assertFalse(response.contains("score"));
        assertFalse(response.contains("category"));
    }

    private void assertLightweight(String method) {
        assertTrue(method.contains("buildAssessmentReportResponse"));
        assertFalse(method.contains("getRecordDetail("));
        assertFalse(method.contains("listExerciseStatsForCategoryPage("));
        assertFalse(method.contains("buildRecordAnswers("));
    }

    private String methodBlock(String source, String signature) {
        int start = source.indexOf(signature);
        assertTrue(start >= 0, "Missing method: " + signature);
        int end = source.indexOf("\n    @Override", start + signature.length());
        assertTrue(end > start, "Missing method boundary: " + signature);
        return source.substring(start, end);
    }

    private String source(String relativePath) throws Exception {
        Path path = Paths.get(relativePath);
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }
}
