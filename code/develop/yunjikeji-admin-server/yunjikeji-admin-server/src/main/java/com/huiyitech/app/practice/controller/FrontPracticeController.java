package com.huiyitech.app.practice.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.app.practice.controller.vo.AppAssessmentResultStatusRespVO;
import com.huiyitech.app.practice.controller.vo.AppAssessmentReportRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitReqVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerCardRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeCatalogBatchDetailRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordDetailRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeStatisticsRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeStartRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeTopicRespVO;
import com.huiyitech.app.practice.service.FrontPracticeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.List;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "APP 练习")
@RestController
@Validated
@TenantIgnore
public class FrontPracticeController {

    @Resource
    private FrontPracticeService frontPracticeService;

    @Resource
    private com.huiyitech.app.practice.service.PracticeQuestionVideoService videoService;

    @GetMapping("/app-api/yj/practices/current")
    @Operation(summary = "练习 Tab 页面查询当前练习")
    @Parameter(name = "mode", description = "练习模式", example = "standard")
    public CommonResult<List<AppPracticeTopicRespVO>> getCurrentPractice(
            @RequestParam(value = "topicId", defaultValue = "") String topicId,
            @RequestParam(value = "mode", defaultValue = "standard") String mode) {
        return success(frontPracticeService.getCurrentPractice(topicId, mode));
    }

    @GetMapping("/app-api/yj/practices/statistics")
    @Operation(summary = "APP get practice statistics")
    public CommonResult<AppPracticeStatisticsRespVO> getStatistics() {
        return success(frontPracticeService.getStatistics());
    }

    @GetMapping("/app-api/yj/practices/records")
    @Operation(summary = "APP get practice records")
    public CommonResult<List<AppPracticeRecordRespVO>> getRecords() {
        return success(frontPracticeService.getRecords());
    }

    @GetMapping("/app-api/yj/practices/records/{recordId}")
    @Operation(summary = "APP get practice record detail")
    public CommonResult<AppPracticeRecordDetailRespVO> getRecordDetail(@PathVariable("recordId") String recordId) {
        return success(frontPracticeService.getRecordDetail(recordId));
    }

    @GetMapping("/app-api/yj/practices/records/{recordId}/answer-card")
    @Operation(summary = "APP get practice answer card")
    public CommonResult<AppPracticeAnswerCardRespVO> getAnswerCard(@PathVariable("recordId") String recordId) {
        return success(frontPracticeService.getAnswerCard(recordId));
    }

    @GetMapping("/app-api/yj/practices/catalog-batches/{catalogBatchId}")
    @Operation(summary = "APP get practice catalog batch detail")
    public CommonResult<AppPracticeCatalogBatchDetailRespVO> getCatalogBatchDetail(
            @PathVariable("catalogBatchId") Long catalogBatchId) {
        return success(frontPracticeService.getCatalogBatchDetail(catalogBatchId));
    }

    @GetMapping("/app-api/yj/practices/catalog-batches/latest")
    @Operation(summary = "APP get latest practice catalog batch detail")
    @Parameter(name = "type", description = "练习批次类型", example = "1")
    @Parameter(name = "mode", description = "练习模式", example = "practice")
    public CommonResult<AppPracticeCatalogBatchDetailRespVO> getLatestCatalogBatchDetail(
            @RequestParam("type") Integer type,
            @RequestParam("mode") String mode) {
        return success(frontPracticeService.getLatestCatalogBatchDetail(type, mode));
    }

    @PostMapping("/app-api/yj/practices/exam-batches/close-incomplete")
    @Operation(summary = "APP close incomplete theory/comprehensive/instructor exam batches")
    public CommonResult<Integer> closeIncompleteExamBatches() {
        return success(frontPracticeService.closeIncompleteExamBatches());
    }

    @GetMapping("/app-api/yj/practices/assessment-result/completed")
    @Operation(summary = "APP check current student assessment result exists")
    public CommonResult<Boolean> hasCompletedAssessmentResult() {
        return success(frontPracticeService.hasCompletedAssessmentResult());
    }

    @GetMapping("/app-api/yj/practices/assessment-result/latest-status")
    @Operation(summary = "APP get latest assessment result entry status")
    public CommonResult<AppAssessmentResultStatusRespVO> getLatestAssessmentResultStatus() {
        return success(frontPracticeService.getLatestAssessmentResultStatus());
    }

    @PostMapping("/app-api/yj/practices/assessment-result/reset")
    @Operation(summary = "APP reset current student completed assessment")
    public CommonResult<Boolean> resetCompletedAssessmentResult() {
        return success(frontPracticeService.resetCompletedAssessmentResult());
    }

    @PostMapping("/app-api/yj/practices/assessment-result/{recordId}/regenerate")
    @Operation(summary = "APP regenerate current student failed assessment report")
    public CommonResult<AppPracticeAnswerSubmitRespVO> regenerateAssessmentReport(
            @PathVariable("recordId") Long recordId) {
        return success(frontPracticeService.regenerateAssessmentReport(recordId));
    }

    @GetMapping("/app-api/yj/practices/assessment-result/self/{recordId}")
    @Operation(summary = "APP get current student self assessment report")
    public CommonResult<AppAssessmentReportRespVO> getSelfAssessmentReport(
            @PathVariable("recordId") Long recordId) {
        return success(frontPracticeService.getSelfAssessmentReport(recordId));
    }

    @GetMapping("/app-api/yj/practices/assessment-result/career/report-entry")
    @Operation(summary = "APP get current student latest completed career assessment report entry")
    public CommonResult<AppAssessmentResultStatusRespVO> getLatestCareerAssessmentReportEntry() {
        return success(frontPracticeService.getLatestCareerAssessmentReportEntry());
    }

    @GetMapping("/app-api/yj/practices/assessment-result/career/latest-status")
    @Operation(summary = "APP get latest career assessment save status")
    public CommonResult<AppAssessmentResultStatusRespVO> getLatestCareerAssessmentStatus() {
        return success(frontPracticeService.getLatestCareerAssessmentStatus());
    }

    @GetMapping("/app-api/yj/practices/assessment-result/career/completed")
    @Operation(summary = "APP check current student career assessment result exists")
    public CommonResult<Boolean> hasCompletedCareerAssessmentResult() {
        return success(frontPracticeService.hasCompletedCareerAssessmentResult());
    }

    @PostMapping("/app-api/yj/practices/assessment-result/career/{recordId}/regenerate")
    @Operation(summary = "APP regenerate current student failed career assessment report")
    public CommonResult<AppPracticeAnswerSubmitRespVO> regenerateCareerAssessmentReport(
            @PathVariable("recordId") Long recordId) {
        return success(frontPracticeService.regenerateCareerAssessmentReport(recordId));
    }

    @GetMapping("/app-api/yj/practices/assessment-result/career/{recordId}")
    @Operation(summary = "APP get current student career assessment report")
    public CommonResult<AppAssessmentReportRespVO> getCareerAssessmentReport(
            @PathVariable("recordId") Long recordId) {
        return success(frontPracticeService.getCareerAssessmentReport(recordId));
    }

    @PostMapping("/app-api/yj/practices/{practiceId}/start")
    @Operation(summary = "APP start practice")
    public CommonResult<AppPracticeStartRespVO> startPractice(
            @PathVariable("practiceId") String practiceId,
            @RequestParam(value = "topicId", defaultValue = "") String topicId,
            @RequestParam(value = "mode", defaultValue = "standard") String mode) {
        return success(frontPracticeService.startPractice(practiceId, topicId, mode));
    }

    @PostMapping("/app-api/yj/practices/{practiceId}/start/career-assessment")
    @Operation(summary = "APP start career planning assessment")
    public CommonResult<AppPracticeStartRespVO> startCareerAssessment(
            @PathVariable("practiceId") String practiceId) {
        return success(frontPracticeService.startCareerAssessment(practiceId));
    }

    @PostMapping("/app-api/yj/practices/{practiceId}/start/practice")
    @Operation(summary = "APP start practice mode")
    public CommonResult<AppPracticeStartRespVO> startPracticeMode(
            @PathVariable("practiceId") String practiceId,
            @RequestParam("topicId") String topicId) {
        return success(frontPracticeService.startPracticeMode(practiceId, topicId));
    }

    @PostMapping("/app-api/yj/practices/{practiceId}/start/chapter-test")
    @Operation(summary = "APP start chapter test mode")
    public CommonResult<AppPracticeStartRespVO> startChapterTest(
            @PathVariable("practiceId") String practiceId,
            @RequestParam("topicId") String topicId) {
        return success(frontPracticeService.startChapterTest(practiceId, topicId));
    }

    @PostMapping("/app-api/yj/practices/{practiceId}/start/theory-exam")
    @Operation(summary = "APP start theory exam mode")
    public CommonResult<AppPracticeStartRespVO> startTheoryExam(@PathVariable("practiceId") String practiceId) {
        return success(frontPracticeService.startTheoryExam(practiceId));
    }

    @PostMapping("/app-api/yj/practices/{practiceId}/start/comprehensive-exam")
    @Operation(summary = "APP start comprehensive exam mode")
    public CommonResult<AppPracticeStartRespVO> startComprehensiveExam(@PathVariable("practiceId") String practiceId) {
        return success(frontPracticeService.startComprehensiveExam(practiceId));
    }

    @PostMapping("/app-api/yj/practices/{practiceId}/start/instructor-exam")
    @Operation(summary = "APP start instructor exam mode")
    public CommonResult<AppPracticeStartRespVO> startInstructorExam(@PathVariable("practiceId") String practiceId) {
        return success(frontPracticeService.startInstructorExam(practiceId));
    }

    @GetMapping("/app-api/yj/practices/{practiceId}/sessions/{sessionId}/question")
    @Operation(summary = "APP get practice question")
    public CommonResult<AppPracticeQuestionRespVO> getQuestion(
            @PathVariable("practiceId") String practiceId,
            @PathVariable("sessionId") String sessionId,
            @RequestParam(value = "mode", defaultValue = "standard") String mode,
            @RequestParam(value = "index", defaultValue = "0") Integer index) {
        AppPracticeQuestionRespVO result = frontPracticeService.getQuestion(practiceId, sessionId, mode, index);
        videoService.enrich(result.getQuestion());
        return success(result);
    }

    @PostMapping("/app-api/yj/practices/{practiceId}/sessions/{sessionId}/answers")
    @Operation(summary = "APP submit practice answer")
    public CommonResult<AppPracticeAnswerSubmitRespVO> submitAnswer(
            @PathVariable("practiceId") String practiceId,
            @PathVariable("sessionId") String sessionId,
            @RequestBody AppPracticeAnswerSubmitReqVO reqVO) {
        return success(frontPracticeService.submitAnswer(practiceId, sessionId, reqVO));
    }
}
