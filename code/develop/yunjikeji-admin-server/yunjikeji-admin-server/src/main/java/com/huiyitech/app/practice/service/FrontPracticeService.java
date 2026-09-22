package com.huiyitech.app.practice.service;

import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitReqVO;
import com.huiyitech.app.practice.controller.vo.AppAssessmentReportRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerCardRespVO;
import com.huiyitech.app.practice.controller.vo.AppAssessmentResultStatusRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeCatalogBatchDetailRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordDetailRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeStatisticsRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeTopicRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeStartRespVO;

import java.util.List;

public interface FrontPracticeService {

    List<AppPracticeTopicRespVO> getCurrentPractice(String topicId, String mode);

    AppPracticeStatisticsRespVO getStatistics();

    List<AppPracticeRecordRespVO> getRecords();

    AppPracticeRecordDetailRespVO getRecordDetail(String recordId);

    Boolean hasCompletedAssessmentResult();

    AppAssessmentResultStatusRespVO getLatestAssessmentResultStatus();

    Boolean resetCompletedAssessmentResult();

    AppPracticeAnswerSubmitRespVO regenerateAssessmentReport(Long recordId);

    AppAssessmentReportRespVO getSelfAssessmentReport(Long recordId);

    AppAssessmentResultStatusRespVO getLatestCareerAssessmentReportEntry();

    AppAssessmentResultStatusRespVO getLatestCareerAssessmentStatus();

    Boolean hasCompletedCareerAssessmentResult();

    AppPracticeAnswerSubmitRespVO regenerateCareerAssessmentReport(Long recordId);

    AppAssessmentReportRespVO getCareerAssessmentReport(Long recordId);

    AppPracticeStartRespVO startPractice(String practiceId, String topicId, String mode);

    AppPracticeStartRespVO startCareerAssessment(String practiceId);

    AppPracticeStartRespVO startPracticeMode(String practiceId, String topicId);

    AppPracticeStartRespVO startChapterTest(String practiceId, String topicId);

    AppPracticeStartRespVO startTheoryExam(String practiceId);

    AppPracticeStartRespVO startComprehensiveExam(String practiceId);

    AppPracticeStartRespVO startInstructorExam(String practiceId);

    AppPracticeAnswerCardRespVO getAnswerCard(String recordId);

    AppPracticeCatalogBatchDetailRespVO getCatalogBatchDetail(Long catalogBatchId);

    AppPracticeCatalogBatchDetailRespVO getLatestCatalogBatchDetail(Integer type, String mode);

    Integer closeIncompleteExamBatches();

    AppPracticeQuestionRespVO getQuestion(String practiceId, String sessionId, String mode, Integer index);

    AppPracticeAnswerSubmitRespVO submitAnswer(String practiceId, String sessionId, AppPracticeAnswerSubmitReqVO reqVO);
}
