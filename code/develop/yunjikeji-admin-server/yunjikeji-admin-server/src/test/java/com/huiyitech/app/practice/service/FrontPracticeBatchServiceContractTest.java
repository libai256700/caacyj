package com.huiyitech.app.practice.service;

import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import com.baomidou.mybatisplus.core.conditions.AbstractWrapper;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerCardRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitReqVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeCatalogBatchDetailRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordAnswerRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeStartRespVO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCatalogBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCategoryDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesDO;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDO;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDetailDO;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesWrongRecordDetailDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeCatalogBatchMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeCategoryMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesAnswerBatchMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesAnswerChildMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesAnswerMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesBatchMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordDetailMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesWrongRecordDetailMapper;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.ArrayList;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FrontPracticeBatchServiceContractTest {

    @Test
    void startPracticeMode_shouldUseCatalogJoinAndKeepOriginalAnswerOrder() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(2001L, "法规", "law");
        fixture.registerExerciseWithAnswers(2001L, 101L, "法规题", Arrays.asList("X", "Y"), 0);
        fixture.prepareSelectObjsSequence(2001L);

        AppPracticeStartRespVO response = fixture.service.startPracticeMode(fixture.loginUser(), "uav-basic-001", "law");
        AppPracticeCatalogBatchDetailRespVO detail = fixture.service.getCatalogBatchDetail(9001L, fixture.catalogBatch.getId());
        AppPracticeQuestionRespVO question = fixture.service.getQuestion(9001L, response.getSessionId(), 0);

        assertEquals("PRACTICE", response.getMode());
        assertEquals(Long.valueOf(2001L), fixture.catalogBatch.getCategoryId());
        assertEquals(Arrays.asList("X", "Y"), fixture.answerBatchesForExercise(0).stream()
                .map(PracticeExercisesAnswerBatchDO::getAnswerCode)
                .collect(Collectors.toList()));
        assertEquals(Long.valueOf(2001L), detail.getCategoryId());
        assertEquals("法规", detail.getCategoryName());
        assertEquals(Integer.valueOf(1), detail.getTotal());
        assertEquals(Integer.valueOf(1), question.getTotalQuestions());
        assertEquals("PRACTICE", question.getMode());
        verify(fixture.exercisesBatchMapper).insertBatchByExerciseIds(anyLong(), anyLong(), anyList(), anyString(), any());
        verify(fixture.answerBatchMapper).insertBatchByCatalogBatchId(anyLong(), anyString(), any());
        verify(fixture.exercisesBatchMapper, never()).insert(any(PracticeExercisesBatchDO.class));
        verify(fixture.answerBatchMapper, never()).insert(any(PracticeExercisesAnswerBatchDO.class));
    }

    @Test
    void startPracticeMode_shouldFailWhenTopicDoesNotMatchCategory() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(2001L, "法规", "law");

        ServiceException exception = assertThrows(ServiceException.class,
                () -> fixture.service.startPracticeMode(fixture.loginUser(), "uav-basic-001", "9999"));

        assertTrue(exception.getMessage().contains("练习分类不存在"));
    }

    @Test
    void startAssessment_shouldUseEnabledAssessmentCatalogTypeWithoutTopicMatching() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(13L, "入行专属评估", "entry", 1);
        fixture.registerExercises(13L, 2, "自测题");
        fixture.exerciseStore.values().forEach(exercise -> exercise.setIsRequired(Boolean.FALSE));
        fixture.prepareSelectObjsSequence(13L);

        AppPracticeStartRespVO response = fixture.service.startAssessment(
                fixture.loginUser(), "uav-basic-001", "assessment");
        AppPracticeCatalogBatchDetailRespVO detail = fixture.service.getCatalogBatchDetail(9001L, fixture.catalogBatch.getId());
        AppPracticeQuestionRespVO question = fixture.service.getQuestion(9001L, response.getSessionId(), 0);

        assertEquals("ASSESSMENT", response.getMode());
        assertEquals(Long.valueOf(13L), fixture.catalogBatch.getCategoryId());
        assertEquals("入行专属评估", fixture.catalogBatch.getCategoryName());
        assertEquals("assessment", fixture.record.getFieldType());
        assertEquals(Long.valueOf(13L), detail.getCategoryId());
        assertEquals("入行专属评估", detail.getCategoryName());
        assertEquals(Integer.valueOf(2), detail.getTotal());
        assertEquals("ASSESSMENT", question.getMode());
        assertEquals(Boolean.FALSE, question.getQuestion().getIsRequired());
        AppPracticeAnswerSubmitReqVO optionalSubmit = new AppPracticeAnswerSubmitReqVO();
        optionalSubmit.setCurrentIndex(0);
        AppPracticeAnswerSubmitRespVO optionalResponse = fixture.service.submitAnswer(
                9001L, response.getSessionId(), optionalSubmit);
        assertEquals(Collections.emptyList(), optionalResponse.getSelectedOptionIds());
        assertEquals("", fixture.recordDetails.get(0).getAnswerCode());
        assertFalse(optionalResponse.getCorrect());
        verify(fixture.exercisesBatchMapper).insertBatchByExerciseIds(anyLong(), anyLong(), anyList(), anyString(), any());
        verify(fixture.answerBatchMapper).insertBatchByCatalogBatchId(anyLong(), anyString(), any());
    }

    @Test
    void startAssessment_shouldFailWhenOnlyPracticeCatalogExists() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(13L, "入行专属评估", "entry", 0);
        fixture.registerExercises(13L, 2, "自测题");

        ServiceException exception = assertThrows(ServiceException.class,
                () -> fixture.service.startAssessment(fixture.loginUser(), "uav-basic-001", "assessment"));

        assertTrue(exception.getMessage().contains("自测分类不存在"));
        assertNull(fixture.catalogBatch);
        assertTrue(fixture.exerciseBatches.isEmpty());
    }

    @Test
    void submitAnswer_shouldRejectEmptyAnswerOutsideOptionalAssessment() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(2001L, "法规", "law");
        fixture.registerExercises(2001L, 1, "法规题");
        fixture.prepareSelectObjsSequence(2001L);
        AppPracticeStartRespVO start = fixture.service.startPracticeMode(
                fixture.loginUser(), "uav-basic-001", "law");

        ServiceException exception = assertThrows(ServiceException.class,
                () -> fixture.service.submitAnswer(9001L, start.getSessionId(), new AppPracticeAnswerSubmitReqVO()));

        assertTrue(exception.getMessage().contains("答案不能为空"));
        assertTrue(fixture.recordDetails.isEmpty());
    }

    @Test
    void startPracticeMode_shouldResumeLatestIncompleteBatchForTheSameUserCatalogAndMode() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(2001L, "法规", "law");
        fixture.registerExercises(2001L, 2, "法规题");
        fixture.prepareSelectObjsSequence(2001L);

        AppPracticeStartRespVO first = fixture.service.startPracticeMode(fixture.loginUser(), "uav-basic-001", "law");
        int exerciseBatchCount = fixture.exerciseBatches.size();
        AppPracticeStartRespVO resumed = fixture.service.startPracticeMode(fixture.loginUser(), "uav-basic-001", "law");

        assertEquals(first.getCatalogBatchId(), resumed.getCatalogBatchId());
        assertEquals(first.getSessionId(), resumed.getSessionId());
        assertEquals(first.getRecordId(), resumed.getRecordId());
        assertEquals(Integer.valueOf(0), resumed.getResumeQuestionIndex());
        assertEquals(exerciseBatchCount, fixture.exerciseBatches.size());
    }

    @Test
    void startPracticeMode_shouldCreateNewBatchWhenLatestBatchIsCompleted() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(2001L, "法规", "law");
        fixture.registerExercises(2001L, 1, "法规题");
        fixture.prepareSelectObjsSequence(2001L);

        AppPracticeStartRespVO earlierIncomplete = fixture.service.startPracticeMode(
                fixture.loginUser(), "uav-basic-001", "law");
        fixture.catalogBatches.add(PracticeCatalogBatchDO.builder()
                .id(9999L)
                .customerAccountId(9001L)
                .categoryId(2001L)
                .mode("PRACTICE")
                .completed(Boolean.TRUE)
                .build());

        AppPracticeStartRespVO created = fixture.service.startPracticeMode(
                fixture.loginUser(), "uav-basic-001", "law");

        assertFalse(earlierIncomplete.getCatalogBatchId().equals(created.getCatalogBatchId()));
        assertEquals(3, fixture.catalogBatches.size());
        assertEquals(2, fixture.exerciseBatches.size());
    }

    @Test
    void getLatestCatalogBatchDetail_shouldMatchTypeAndModeOnly() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(2001L, "法规", "law");
        fixture.registerExercises(2001L, 1, "法规题");
        fixture.prepareSelectObjsSequence(2001L);

        fixture.catalogBatches.add(PracticeCatalogBatchDO.builder()
                .id(8001L)
                .customerAccountId(9001L)
                .type(1)
                .mode("ASSESSMENT")
                .completed(Boolean.FALSE)
                .build());
        fixture.catalogBatches.add(PracticeCatalogBatchDO.builder()
                .id(8002L)
                .customerAccountId(9001L)
                .type(1)
                .mode("PRACTICE")
                .completed(Boolean.FALSE)
                .build());

        AppPracticeCatalogBatchDetailRespVO detail = fixture.service.getLatestCatalogBatchDetail(9001L, 1, "practice");

        assertEquals(Long.valueOf(8002L), detail.getCatalogBatchId());
        assertEquals("PRACTICE", fixture.catalogBatches.get(1).getMode());
    }

    @Test
    void startChapterTest_shouldRelabelBatchAnswersAndJudgeByBatchSnapshot() {
        BatchFixture fixture = new BatchFixture();
        fixture.service.setPracticeRandom(new Random(7L));
        fixture.registerCategory(2002L, "章节练习", "chapter");
        fixture.registerExerciseWithAnswers(2002L, 201L, "章节题", Arrays.asList("X", "Y", "Z"), 1);
        fixture.prepareSelectObjsSequence(2002L);

        AppPracticeStartRespVO start = fixture.service.startChapterTest(fixture.loginUser(), "uav-basic-001", "chapter");
        AppPracticeCatalogBatchDetailRespVO detail = fixture.service.getCatalogBatchDetail(9001L, fixture.catalogBatch.getId());
        AppPracticeQuestionRespVO question = fixture.service.getQuestion(9001L, start.getSessionId(), 0);
        List<PracticeExercisesAnswerBatchDO> batchAnswers = fixture.answerBatchesForExercise(0);
        PracticeExercisesAnswerBatchDO correctAnswer = batchAnswers.stream()
                .filter(answer -> Boolean.TRUE.equals(answer.getCorrect()))
                .findFirst()
                .orElseThrow(AssertionError::new);
        PracticeExercisesAnswerBatchDO wrongAnswer = batchAnswers.stream()
                .filter(answer -> !Boolean.TRUE.equals(answer.getCorrect()))
                .findFirst()
                .orElseThrow(AssertionError::new);

        assertEquals(Arrays.asList("A", "B", "C"), batchAnswers.stream()
                .map(PracticeExercisesAnswerBatchDO::getAnswerCode)
                .collect(Collectors.toList()));
        assertEquals(Arrays.asList(20101L, 20102L, 20103L), batchAnswers.stream()
                .map(PracticeExercisesAnswerBatchDO::getAnswerId)
                .sorted()
                .collect(Collectors.toList()));
        assertEquals(Long.valueOf(20102L), correctAnswer.getAnswerId());
        assertEquals(Arrays.asList("A", "B", "C"), question.getQuestion().getOptions().stream()
                .map(option -> option.getLabel())
                .collect(Collectors.toList()));
        assertEquals(Long.valueOf(2002L), detail.getCategoryId());
        assertEquals("章节练习", detail.getCategoryName());
        assertEquals(Integer.valueOf(1), detail.getTotal());

        AppPracticeAnswerSubmitReqVO submitReq = new AppPracticeAnswerSubmitReqVO();
        submitReq.setCurrentIndex(0);
        submitReq.setSelectedOptionIds(Collections.singletonList(String.valueOf(wrongAnswer.getId())));
        AppPracticeAnswerSubmitRespVO submitResp = fixture.service.submitAnswer(9001L, start.getSessionId(), submitReq);

        assertFalse(submitResp.getCorrect());
        assertEquals(Collections.singletonList(String.valueOf(correctAnswer.getId())), submitResp.getCorrectOptionIds());
        assertEquals(fixture.catalogBatch.getId(), fixture.record.getCategoryId());
        assertEquals(fixture.exerciseBatches.get(0).getId(), fixture.recordDetails.get(0).getExercisesId());
        assertEquals(wrongAnswer.getAnswerCode(), fixture.recordDetails.get(0).getAnswerCode());
        assertEquals(correctAnswer.getAnswerCode(), fixture.recordDetails.get(0).getCorrectAnswerCode());
        assertEquals(1, fixture.wrongRecordDetails.size());
        assertEquals(fixture.exerciseBatches.get(0).getExercisesId(), fixture.wrongRecordDetails.get(0).getExercisesId());
        assertEquals(wrongAnswer.getAnswerCode(), fixture.wrongRecordDetails.get(0).getAnswerCode());
        assertEquals(correctAnswer.getAnswerCode(), fixture.wrongRecordDetails.get(0).getCorrectAnswerCode());
        assertTrue(fixture.catalogBatch.getCompleted());

        verify(fixture.exercisesBatchMapper).insertBatchByExerciseIds(anyLong(), anyLong(), anyList(), anyString(), any());
        verify(fixture.answerBatchMapper).insertBatch(anyList(), anyString(), any());

        List<AppPracticeRecordAnswerRespVO> recordAnswers = fixture.service.buildRecordAnswers(fixture.record);
        assertEquals(Collections.singletonList(wrongAnswer.getAnswerCode()), recordAnswers.get(0).getSelectedOptionIds());
        assertEquals("选项" + wrongAnswer.getAnswerId(), recordAnswers.get(0).getAnswer());
        assertEquals("选项" + correctAnswer.getAnswerId(), recordAnswers.get(0).getCorrect());

        AppPracticeAnswerCardRespVO answerCard = fixture.service.buildAnswerCard(fixture.record);
        assertTrue(answerCard.getDetail().get(0).getIsCompleted());
    }

    @Test
    void startChapterTest_shouldRepairStaleCompletedFlagBeforeResuming() {
        BatchFixture fixture = new BatchFixture();
        fixture.service.setPracticeRandom(new Random(7L));
        fixture.registerCategory(2002L, "章节练习", "chapter");
        fixture.registerExerciseWithAnswers(2002L, 201L, "章节题", Arrays.asList("X", "Y", "Z"), 1);
        fixture.prepareSelectObjsSequence(2002L);

        AppPracticeStartRespVO start = fixture.service.startChapterTest(fixture.loginUser(), "uav-basic-001", "chapter");
        PracticeExercisesAnswerBatchDO wrongAnswer = fixture.answerBatchesForExercise(0).stream()
                .filter(answer -> !Boolean.TRUE.equals(answer.getCorrect()))
                .findFirst()
                .orElseThrow(AssertionError::new);
        AppPracticeAnswerSubmitReqVO submitReq = new AppPracticeAnswerSubmitReqVO();
        submitReq.setCurrentIndex(0);
        submitReq.setSelectedOptionIds(Collections.singletonList(String.valueOf(wrongAnswer.getId())));
        fixture.service.submitAnswer(9001L, start.getSessionId(), submitReq);

        fixture.catalogBatch.setCompleted(Boolean.FALSE);

        AppPracticeCatalogBatchDetailRespVO repairedDetail =
                fixture.service.getLatestCatalogBatchDetail(9001L, 2, "chapter-test");
        AppPracticeStartRespVO nextStart = fixture.service.startChapterTest(fixture.loginUser(), "uav-basic-001", "chapter");

        assertTrue(repairedDetail.getCompleted());
        assertFalse(start.getCatalogBatchId().equals(nextStart.getCatalogBatchId()));
    }

    @Test
    void startChapterTest_shouldResumeUnfinishedBatchAtNextUnansweredQuestion() {
        BatchFixture fixture = new BatchFixture();
        fixture.service.setPracticeRandom(new Random(7L));
        fixture.registerCategory(2002L, "章节练习", "chapter");
        fixture.registerExercises(2002L, 3, "章节题");
        fixture.prepareSelectObjsSequence(2002L, 2002L);

        AppPracticeStartRespVO firstStart = fixture.service.startChapterTest(
                fixture.loginUser(), "uav-basic-001", "chapter");
        int originalCatalogBatchCount = fixture.catalogBatches.size();
        int originalExerciseBatchCount = fixture.exerciseBatches.size();
        PracticeExercisesAnswerBatchDO firstAnswer = fixture.answerBatchesForExercise(0).get(0);
        AppPracticeAnswerSubmitReqVO firstSubmit = new AppPracticeAnswerSubmitReqVO();
        firstSubmit.setCurrentIndex(0);
        firstSubmit.setSelectedOptionIds(Collections.singletonList(String.valueOf(firstAnswer.getId())));

        AppPracticeAnswerSubmitRespVO submitResp =
                fixture.service.submitAnswer(9001L, firstStart.getSessionId(), firstSubmit);
        AppPracticeStartRespVO resumed = fixture.service.startChapterTest(
                fixture.loginUser(), "uav-basic-001", "chapter");

        assertFalse(submitResp.getCompleted());
        assertEquals(firstStart.getCatalogBatchId(), resumed.getCatalogBatchId());
        assertEquals(firstStart.getSessionId(), resumed.getSessionId());
        assertEquals(firstStart.getRecordId(), resumed.getRecordId());
        assertEquals(Integer.valueOf(1), resumed.getResumeQuestionIndex());
        assertEquals(originalCatalogBatchCount, fixture.catalogBatches.size());
        assertEquals(originalExerciseBatchCount, fixture.exerciseBatches.size());
        assertFalse(fixture.catalogBatch.getCompleted());
    }

    @Test
    void startTheoryExam_shouldPersistNullCatalogIdAndBatchSelfDetail() {
        BatchFixture fixture = new BatchFixture();
        fixture.service.setPracticeRandom(new Random(3L));
        fixture.registerCategory(10L, "理论分类", "theory");
        fixture.registerExercises(10L, 12, "理论题");
        fixture.prepareSelectObjsSequence(10L);

        AppPracticeStartRespVO start = fixture.service.startTheoryExam(fixture.loginUser(), "uav-basic-001");
        AppPracticeCatalogBatchDetailRespVO detail = fixture.service.getCatalogBatchDetail(9001L, fixture.catalogBatch.getId());
        AppPracticeQuestionRespVO question = fixture.service.getQuestion(9001L, start.getSessionId(), 0);

        assertEquals(Long.valueOf(10L), fixture.catalogBatch.getCategoryId());
        assertEquals("理论分类", fixture.catalogBatch.getCategoryName());
        assertEquals(Integer.valueOf(3), fixture.catalogBatch.getType());
        assertEquals("理论分类", detail.getCategoryName());
        assertEquals(Integer.valueOf(10), detail.getTotal());
        assertEquals("THEORY_EXAM", question.getMode());
        assertEquals(Integer.valueOf(10), question.getTotalQuestions());
    }

    @Test
    void startWrongReviewPractice_shouldCreateBatchFromSourceExerciseIds() {
        BatchFixture fixture = new BatchFixture();
        fixture.service.setPracticeRandom(new Random(7L));
        fixture.registerCategory(2002L, "章节练习", "chapter");
        fixture.registerExerciseWithAnswers(2002L, 201L, "章节题", Arrays.asList("X", "Y", "Z"), 1);
        fixture.prepareSelectObjsSequence(2002L);

        AppPracticeStartRespVO start = fixture.service.startChapterTest(fixture.loginUser(), "uav-basic-001", "chapter");
        PracticeExercisesAnswerBatchDO wrongAnswer = fixture.answerBatchesForExercise(0).stream()
                .filter(answer -> !Boolean.TRUE.equals(answer.getCorrect()))
                .findFirst()
                .orElseThrow(AssertionError::new);
        AppPracticeAnswerSubmitReqVO submitReq = new AppPracticeAnswerSubmitReqVO();
        submitReq.setCurrentIndex(0);
        submitReq.setSelectedOptionIds(Collections.singletonList(String.valueOf(wrongAnswer.getId())));
        fixture.service.submitAnswer(9001L, start.getSessionId(), submitReq);

        Long wrongSourceExerciseId = fixture.exerciseBatches.get(0).getExercisesId();
        int originalExerciseBatchCount = fixture.exerciseBatches.size();

        AppPracticeStartRespVO wrongReview = fixture.service.startWrongReviewPractice(fixture.loginUser(), "uav-basic-001", "chapter");
        AppPracticeCatalogBatchDetailRespVO detail = fixture.service.getCatalogBatchDetail(9001L, fixture.catalogBatch.getId());
        AppPracticeQuestionRespVO question = fixture.service.getQuestion(9001L, wrongReview.getSessionId(), 0);
        AppPracticeAnswerCardRespVO answerCard = fixture.service.buildAnswerCard(fixture.record);

        assertEquals("wrongReview", wrongReview.getMode());
        assertEquals(Integer.valueOf(1), detail.getTotal());
        assertEquals(originalExerciseBatchCount + 1, fixture.exerciseBatches.size());
        PracticeExercisesBatchDO reviewBatch = fixture.exerciseBatches.stream()
                .filter(batch -> String.valueOf(batch.getId()).equals(question.getQuestion().getId()))
                .findFirst()
                .orElseThrow(AssertionError::new);
        assertEquals(wrongSourceExerciseId, reviewBatch.getExercisesId());
        assertEquals(String.valueOf(reviewBatch.getId()), question.getQuestion().getId());
        assertFalse(answerCard.getDetail().isEmpty());
    }

    @Test
    void startComprehensiveExam_shouldUseConfiguredQuotasAndCategoryIdTen() {
        BatchFixture fixture = new BatchFixture();
        fixture.service.setPracticeRandom(new Random(11L));
        Map<Long, Integer> quotas = new LinkedHashMap<Long, Integer>();
        quotas.put(1L, 5);
        quotas.put(2L, 13);
        quotas.put(3L, 3);
        quotas.put(4L, 11);
        quotas.put(5L, 7);
        quotas.put(6L, 22);
        quotas.put(7L, 7);
        quotas.put(8L, 6);
        quotas.put(9L, 26);
        for (Map.Entry<Long, Integer> entry : quotas.entrySet()) {
            fixture.registerCategory(entry.getKey(), "分类" + entry.getKey(), "cat-" + entry.getKey());
            fixture.registerExercises(entry.getKey(), entry.getValue() + 2, "综合题-" + entry.getKey());
        }
        fixture.prepareSelectObjsSequence(1L, 2L, 3L, 4L, 5L, 6L, 7L, 8L, 9L);

        AppPracticeStartRespVO start = fixture.service.startComprehensiveExam(fixture.loginUser(), "uav-basic-001");
        AppPracticeCatalogBatchDetailRespVO detail = fixture.service.getCatalogBatchDetail(9001L, fixture.catalogBatch.getId());
        AppPracticeQuestionRespVO question = fixture.service.getQuestion(9001L, start.getSessionId(), 0);

        assertEquals(Long.valueOf(10L), fixture.catalogBatch.getCategoryId());
        assertEquals("综合考试", fixture.catalogBatch.getCategoryName());
        assertEquals(Integer.valueOf(4), fixture.catalogBatch.getType());
        assertEquals(100, fixture.exerciseBatches.size());
        assertEquals("comprehens", fixture.record.getFieldType());
        assertTrue(fixture.record.getFieldType().length() <= 10);
        assertEquals("综合考试", detail.getCategoryName());
        assertEquals(Integer.valueOf(100), detail.getTotal());
        assertEquals("COMPREHENSIVE_EXAM", question.getMode());
        assertEquals(Integer.valueOf(100), question.getTotalQuestions());
        Map<Long, Long> counts = fixture.exerciseBatches.stream()
                .collect(Collectors.groupingBy(
                        batch -> Objects.requireNonNull(fixture.exerciseStore.get(batch.getExercisesId())).getCategoryId(),
                        LinkedHashMap::new,
                        Collectors.counting()));
        assertEquals(Long.valueOf(5L), counts.get(1L));
        assertEquals(Long.valueOf(13L), counts.get(2L));
        assertEquals(Long.valueOf(3L), counts.get(3L));
        assertEquals(Long.valueOf(11L), counts.get(4L));
        assertEquals(Long.valueOf(7L), counts.get(5L));
        assertEquals(Long.valueOf(22L), counts.get(6L));
        assertEquals(Long.valueOf(7L), counts.get(7L));
        assertEquals(Long.valueOf(6L), counts.get(8L));
        assertEquals(Long.valueOf(26L), counts.get(9L));
    }

    @Test
    void startInstructorExam_shouldPersistNullCatalogIdAndBatchSelfDetail() {
        BatchFixture fixture = new BatchFixture();
        fixture.service.setPracticeRandom(new Random(13L));
        fixture.registerCategory(11L, "教员分类", "instructor");
        fixture.registerExercises(11L, 110, "教员题");
        fixture.prepareSelectObjsSequence(11L);

        AppPracticeStartRespVO start = fixture.service.startInstructorExam(fixture.loginUser(), "uav-basic-001");
        AppPracticeCatalogBatchDetailRespVO detail = fixture.service.getCatalogBatchDetail(9001L, fixture.catalogBatch.getId());
        AppPracticeQuestionRespVO question = fixture.service.getQuestion(9001L, start.getSessionId(), 0);

        assertEquals(Long.valueOf(11L), fixture.catalogBatch.getCategoryId());
        assertEquals(Long.valueOf(11L), fixture.catalogBatch.getCategoryId());
        assertEquals("教员分类", detail.getCategoryName());
        assertEquals(Integer.valueOf(100), detail.getTotal());
        assertEquals(Integer.valueOf(5), fixture.catalogBatch.getType());
        assertEquals("INSTRUCTOR_EXAM", question.getMode());
        assertEquals(Integer.valueOf(100), question.getTotalQuestions());
    }

    @Test
    void startTheoryExam_shouldFailWhenQuestionsInsufficient() {
        BatchFixture fixture = new BatchFixture();
        fixture.registerCategory(10L, "理论分类", "theory");
        fixture.registerExercises(10L, 9, "理论题");

        assertThrows(ServiceException.class, () -> fixture.service.startTheoryExam(fixture.loginUser(), "uav-basic-001"));
        assertNull(fixture.catalogBatch);
        assertTrue(fixture.exerciseBatches.isEmpty());
    }

    private static final class BatchFixture {
        private final FrontPracticeBatchService service = new FrontPracticeBatchService();
        private final PracticeCategoryMapper categoryMapper = mock(PracticeCategoryMapper.class);
        private final PracticeExercisesMapper exercisesMapper = mock(PracticeExercisesMapper.class);
        private final PracticeExercisesAnswerMapper answerMapper = mock(PracticeExercisesAnswerMapper.class);
        private final PracticeExercisesAnswerChildMapper answerChildMapper = mock(PracticeExercisesAnswerChildMapper.class);
        private final PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        private final PracticeExercisesBatchMapper exercisesBatchMapper = mock(PracticeExercisesBatchMapper.class);
        private final PracticeExercisesAnswerBatchMapper answerBatchMapper = mock(PracticeExercisesAnswerBatchMapper.class);
        private final UserPracticeExercisesRecordMapper recordMapper = mock(UserPracticeExercisesRecordMapper.class);
        private final UserPracticeExercisesRecordDetailMapper recordDetailMapper = mock(UserPracticeExercisesRecordDetailMapper.class);
        private final UserPracticeExercisesWrongRecordDetailMapper wrongRecordDetailMapper = mock(UserPracticeExercisesWrongRecordDetailMapper.class);

        private final Map<Long, PracticeCategoryDO> categories = new LinkedHashMap<>();
        private final Map<Long, PracticeExercisesDO> exerciseStore = new LinkedHashMap<>();
        private final Map<Long, List<Long>> exerciseIdsByCategory = new LinkedHashMap<>();
        private final Map<Long, List<PracticeExercisesAnswerDO>> answersByExerciseId = new LinkedHashMap<>();
        private final List<PracticeCatalogBatchDO> catalogBatches = new ArrayList<>();
        private final List<PracticeExercisesBatchDO> exerciseBatches = new ArrayList<>();
        private final List<PracticeExercisesAnswerBatchDO> answerBatches = new ArrayList<>();
        private final List<UserPracticeExercisesRecordDetailDO> recordDetails = new ArrayList<>();
        private final List<UserPracticeExercisesWrongRecordDetailDO> wrongRecordDetails = new ArrayList<>();
        private final Deque<List<Long>> selectObjsQueue = new ArrayDeque<List<Long>>();
        private final Deque<Long> pendingAnswerExerciseIds = new ArrayDeque<Long>();
        private PracticeCatalogBatchDO catalogBatch;
        private UserPracticeExercisesRecordDO record;
        private int selectObjsFallbackIndex;

        private BatchFixture() {
            inject();
            stubBaseMappers();
            stubInserts();
        }

        private LoginUser loginUser() {
            LoginUser loginUser = new LoginUser();
            loginUser.setId(9001L);
            loginUser.setTenantId(8L);
            return loginUser;
        }

        private void prepareSelectObjsSequence(Long... categoryIds) {
            selectObjsQueue.clear();
            selectObjsFallbackIndex = 0;
            for (Long categoryId : categoryIds) {
                selectObjsQueue.addLast(new ArrayList<Long>(exerciseIdsByCategory.getOrDefault(categoryId, Collections.<Long>emptyList())));
            }
        }

        private void registerCategory(Long categoryId, String categoryName, String fieldType) {
            registerCategory(categoryId, categoryName, fieldType, 0);
        }

        private void registerCategory(Long categoryId, String categoryName, String fieldType, int catalogType) {
            categories.put(categoryId, PracticeCategoryDO.builder()
                    .id(categoryId)
                    .categoryName(categoryName)
                    .fieldType(fieldType)
                    .catalogType(catalogType)
                    .categoryStatus(Boolean.TRUE)
                    .sortNo(categoryId.intValue())
                    .build());
        }

        private void registerExercises(Long categoryId, int count, String stemPrefix) {
            for (int index = 1; index <= count; index++) {
                long exerciseId = categoryId * 1000 + index;
                registerExerciseWithAnswers(categoryId, exerciseId, stemPrefix + "-" + index, Arrays.asList("A", "B"), 0);
            }
        }

        private void registerExerciseWithAnswers(Long categoryId, Long exerciseId, String stem,
                                                 List<String> sourceCodes, int correctIndex) {
            exerciseStore.put(exerciseId, PracticeExercisesDO.builder()
                    .id(exerciseId)
                    .categoryId(categoryId)
                    .stepId(categoryId)
                    .questionStem(stem)
                    .questionType("single_choice")
                    .questionStatus(Boolean.TRUE)
                    .score(2)
                    .sortNo(exerciseIdsByCategory.computeIfAbsent(categoryId, ignored -> new ArrayList<>()).size() + 1)
                    .correctMemo("解析-" + exerciseId)
                    .build());
            exerciseIdsByCategory.get(categoryId).add(exerciseId);
            List<PracticeExercisesAnswerDO> answers = new ArrayList<>();
            for (int index = 0; index < sourceCodes.size(); index++) {
                long answerId = exerciseId * 100 + index + 1;
                answers.add(PracticeExercisesAnswerDO.builder()
                        .id(answerId)
                        .exercisesId(exerciseId)
                        .questionType("single_choice")
                        .answerCode(sourceCodes.get(index))
                        .answerContent("选项" + answerId)
                        .correct(index == correctIndex)
                        .sortNo(index + 1)
                        .build());
            }
            answersByExerciseId.put(exerciseId, answers);
        }

        private List<PracticeExercisesAnswerBatchDO> answerBatchesForExercise(int exerciseIndex) {
            Long exercisesBatchId = exerciseBatches.get(exerciseIndex).getId();
            return answerBatches.stream()
                    .filter(answer -> Objects.equals(answer.getExercisesBatchId(), exercisesBatchId))
                    .sorted(Comparator.comparing(PracticeExercisesAnswerBatchDO::getSortNo))
                    .collect(Collectors.toList());
        }

        private void inject() {
            ReflectionTestUtils.setField(service, "practiceCategoryMapper", categoryMapper);
            ReflectionTestUtils.setField(service, "practiceExercisesMapper", exercisesMapper);
            ReflectionTestUtils.setField(service, "practiceExercisesAnswerMapper", answerMapper);
            ReflectionTestUtils.setField(service, "practiceExercisesAnswerChildMapper", answerChildMapper);
            ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);
            ReflectionTestUtils.setField(service, "practiceExercisesBatchMapper", exercisesBatchMapper);
            ReflectionTestUtils.setField(service, "practiceExercisesAnswerBatchMapper", answerBatchMapper);
            ReflectionTestUtils.setField(service, "userPracticeExercisesRecordMapper", recordMapper);
            ReflectionTestUtils.setField(service, "userPracticeExercisesRecordDetailMapper", recordDetailMapper);
            ReflectionTestUtils.setField(service, "userPracticeExercisesWrongRecordDetailMapper", wrongRecordDetailMapper);
            ReflectionTestUtils.setField(service, "theoryExamCategoryId", 10L);
            ReflectionTestUtils.setField(service, "instructorExamCategoryId", 11L);
        }

        private void stubBaseMappers() {
            when(categoryMapper.selectById(anyLong())).thenAnswer(invocation -> categories.get(invocation.getArgument(0)));
            when(categoryMapper.selectList(any())).thenAnswer(invocation -> {
                Object wrapper = invocation.getArgument(0);
                List<Long> values = wrapperLongValues(wrapper);
                String wrapperText = String.valueOf(wrapper);
                boolean queryMode = wrapper != null && "QueryWrapper".equals(wrapper.getClass().getSimpleName());
                Collection<?> paramValues = wrapper instanceof AbstractWrapper
                        ? ((AbstractWrapper<?, ?, ?>) wrapper).getParamNameValuePairs().values()
                        : Collections.emptyList();
                boolean hasCategoryId = categories.keySet().stream().anyMatch(values::contains);
                List<PracticeCategoryDO> matchedCategories = categories.values().stream()
                        .filter(category -> values.contains(category.getId())
                                || paramValues.contains(category.getId())
                                || paramValues.contains(category.getCategoryName())
                                || paramValues.contains(category.getFieldType())
                                || wrapperText.contains(category.getCategoryName())
                                || wrapperText.contains(category.getFieldType()))
                        .sorted(Comparator.comparing(PracticeCategoryDO::getSortNo))
                        .collect(Collectors.toList());
                if (!matchedCategories.isEmpty()) {
                    return matchedCategories;
                }
                if (queryMode) {
                    return Collections.emptyList();
                }
                if (values.isEmpty() || !hasCategoryId) {
                    return categories.values().stream()
                            .sorted(Comparator.comparing(PracticeCategoryDO::getSortNo))
                            .collect(Collectors.toList());
                }
                return matchedCategories;
            });
            when(exercisesMapper.selectObjs(any())).thenAnswer(invocation -> {
                if (!selectObjsQueue.isEmpty()) {
                    return new ArrayList<Long>(selectObjsQueue.removeFirst());
                }
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                Long categoryId = values.stream()
                        .filter(exerciseIdsByCategory::containsKey)
                        .findFirst()
                        .orElse(null);
                if (categoryId == null && !exerciseIdsByCategory.isEmpty()) {
                    List<Long> categoryOrder = new ArrayList<Long>(exerciseIdsByCategory.keySet());
                    Collections.sort(categoryOrder);
                    categoryId = categoryOrder.get(Math.min(selectObjsFallbackIndex, categoryOrder.size() - 1));
                    selectObjsFallbackIndex++;
                }
                return new ArrayList<>(exerciseIdsByCategory.getOrDefault(categoryId, Collections.emptyList()));
            });
            when(exercisesMapper.selectById(anyLong())).thenAnswer(invocation -> exerciseStore.get(invocation.getArgument(0)));
            when(exercisesMapper.selectBatchIds(any())).thenAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                Collection<Long> ids = invocation.getArgument(0, Collection.class);
                if (ids == null) {
                    return Collections.emptyList();
                }
                return ids.stream().map(exerciseStore::get).filter(Objects::nonNull).collect(Collectors.toList());
            });
            when(answerMapper.selectList(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                if (!values.isEmpty()) {
                    List<PracticeExercisesAnswerDO> result = new ArrayList<>();
                    for (Long exerciseId : values) {
                        result.addAll(answersByExerciseId.getOrDefault(exerciseId, Collections.emptyList()));
                    }
                    if (!result.isEmpty()) {
                        return result;
                    }
                }
                Long exerciseId = pendingAnswerExerciseIds.isEmpty() ? null : pendingAnswerExerciseIds.removeFirst();
                if (exerciseId == null) {
                    exerciseId = values.stream()
                            .filter(answersByExerciseId::containsKey)
                            .findFirst()
                            .orElse(null);
                }
                if (exerciseId != null) {
                    return new ArrayList<>(answersByExerciseId.getOrDefault(exerciseId, Collections.emptyList()));
                }
                return answersByExerciseId.values().stream()
                        .flatMap(List::stream)
                        .collect(Collectors.toList());
            });
            when(answerChildMapper.selectList(any())).thenReturn(Collections.emptyList());

            when(catalogBatchMapper.selectById(anyLong())).thenAnswer(invocation ->
                    catalogBatches.stream()
                            .filter(batch -> Objects.equals(batch.getId(), invocation.getArgument(0)))
                            .reduce((first, second) -> second)
                            .orElse(null));
            when(catalogBatchMapper.selectOne(any())).thenAnswer(invocation -> {
                if (catalogBatches.isEmpty()) {
                    return null;
                }
                return catalogBatches.stream()
                        .reduce((first, second) -> second)
                        .orElse(null);
            });
            when(catalogBatchMapper.selectLatestByUserCategoryAndMode(anyLong(), anyLong(), anyString()))
                    .thenAnswer(invocation -> catalogBatches.stream()
                            .filter(batch -> Objects.equals(batch.getCustomerAccountId(), invocation.getArgument(0))
                                    && Objects.equals(batch.getCategoryId(), invocation.getArgument(1))
                                    && Objects.equals(batch.getMode(), invocation.getArgument(2)))
                            .max(Comparator.comparing(PracticeCatalogBatchDO::getId))
                            .orElse(null));
            when(catalogBatchMapper.selectLatestByCustomerAccountIdAndTypeAndMode(anyLong(), anyLong(), anyString()))
                    .thenAnswer(invocation -> catalogBatches.stream()
                            .filter(batch -> Objects.equals(batch.getCustomerAccountId(), invocation.getArgument(0))
                                    && Objects.equals(batch.getType() == null ? null : batch.getType().longValue(),
                                    invocation.getArgument(1))
                                    && Objects.equals(batch.getMode(), invocation.getArgument(2)))
                            .max(Comparator.comparing(PracticeCatalogBatchDO::getId))
                            .orElse(null));

            when(exercisesBatchMapper.selectById(anyLong())).thenAnswer(invocation ->
                    exerciseBatches.stream()
                            .filter(batch -> Objects.equals(batch.getId(), invocation.getArgument(0)))
                            .findFirst()
                            .orElse(null));
            when(exercisesBatchMapper.selectList(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                Set<Long> knownCatalogBatchIds = exerciseBatches.stream()
                        .map(PracticeExercisesBatchDO::getCatalogBatchId)
                        .filter(Objects::nonNull)
                        .collect(Collectors.toCollection(LinkedHashSet::new));
                Set<Long> matchedCatalogBatchIds = values.stream()
                        .filter(knownCatalogBatchIds::contains)
                        .collect(Collectors.toCollection(LinkedHashSet::new));
                if (matchedCatalogBatchIds.isEmpty()) {
                    if (catalogBatch != null && catalogBatch.getId() != null) {
                        matchedCatalogBatchIds.add(catalogBatch.getId());
                    }
                }
                if (matchedCatalogBatchIds.isEmpty()) {
                    return exerciseBatches.stream()
                            .sorted(Comparator.comparing(PracticeExercisesBatchDO::getSortNo))
                            .collect(Collectors.toList());
                }
                return exerciseBatches.stream()
                        .filter(batch -> matchedCatalogBatchIds.contains(batch.getCatalogBatchId()))
                        .sorted(Comparator.comparing(PracticeExercisesBatchDO::getSortNo))
                        .collect(Collectors.toList());
            });
            when(exercisesBatchMapper.selectOne(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                return exerciseBatches.stream()
                        .filter(batch -> values.contains(batch.getCatalogBatchId()) && values.contains(batch.getExercisesId()))
                        .findFirst()
                        .orElse(null);
            });

            when(answerBatchMapper.selectList(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                Set<Long> knownBatchIds = answerBatches.stream()
                        .map(PracticeExercisesAnswerBatchDO::getExercisesBatchId)
                        .filter(Objects::nonNull)
                        .collect(Collectors.toCollection(LinkedHashSet::new));
                Set<Long> ids = values.stream()
                        .filter(knownBatchIds::contains)
                        .collect(Collectors.toCollection(LinkedHashSet::new));
                return answerBatches.stream()
                        .filter(answer -> ids.isEmpty() || ids.contains(answer.getExercisesBatchId()))
                        .sorted(Comparator.comparing(PracticeExercisesAnswerBatchDO::getSortNo))
                        .collect(Collectors.toList());
            });

            when(recordMapper.selectById(anyLong())).thenAnswer(invocation ->
                    record != null && Objects.equals(record.getId(), invocation.getArgument(0)) ? record : null);
            when(recordMapper.selectOne(any())).thenAnswer(invocation -> record);
            when(recordMapper.selectList(any())).thenAnswer(invocation ->
                    record == null ? Collections.emptyList() : Collections.singletonList(record));

            when(recordDetailMapper.selectOne(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                return recordDetails.stream()
                        .filter(detail -> detail.getRecordId() != null
                                && detail.getExercisesId() != null
                                && values.contains(detail.getRecordId())
                                && values.contains(detail.getExercisesId()))
                        .findFirst()
                        .orElse(null);
            });
            when(recordDetailMapper.selectList(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                if (values.isEmpty()) {
                    return new ArrayList<>(recordDetails);
                }
                Long recordId = recordDetails.stream()
                        .map(UserPracticeExercisesRecordDetailDO::getRecordId)
                        .filter(Objects::nonNull)
                        .filter(values::contains)
                        .findFirst()
                        .orElse(null);
                if (recordId == null && record != null) {
                    recordId = record.getId();
                }
                if (recordId == null) {
                    return Collections.emptyList();
                }
                final Long targetRecordId = recordId;
                return recordDetails.stream()
                        .filter(detail -> Objects.equals(detail.getRecordId(), targetRecordId))
                        .sorted(Comparator.comparing(UserPracticeExercisesRecordDetailDO::getId))
                        .collect(Collectors.toList());
            });

            when(wrongRecordDetailMapper.selectOne(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                return wrongRecordDetails.stream()
                        .filter(detail -> detail.getCustomerAccountId() != null
                                && detail.getExercisesId() != null
                                && values.contains(detail.getCustomerAccountId())
                                && values.contains(detail.getExercisesId()))
                        .findFirst()
                        .orElse(null);
            });
            when(wrongRecordDetailMapper.selectList(any())).thenAnswer(invocation -> new ArrayList<>(wrongRecordDetails));
            when(wrongRecordDetailMapper.deleteById(anyLong())).thenAnswer(invocation -> {
                Long id = invocation.getArgument(0);
                wrongRecordDetails.removeIf(detail -> Objects.equals(detail.getId(), id));
                return 1;
            });
        }

        private void stubInserts() {
            AtomicLong catalogId = new AtomicLong(5000L);
            AtomicLong exerciseBatchId = new AtomicLong(6000L);
            AtomicLong answerBatchId = new AtomicLong(7000L);
            AtomicLong recordId = new AtomicLong(8000L);
            AtomicLong recordDetailId = new AtomicLong(9000L);
            AtomicLong wrongRecordId = new AtomicLong(9500L);

            doAnswer(invocation -> {
                catalogBatch = invocation.getArgument(0);
                catalogBatch.setId(catalogId.incrementAndGet());
                catalogBatches.add(catalogBatch);
                return 1;
            }).when(catalogBatchMapper).insert(any(PracticeCatalogBatchDO.class));
            doAnswer(invocation -> {
                PracticeCatalogBatchDO update = invocation.getArgument(0);
                for (PracticeCatalogBatchDO existing : catalogBatches) {
                    if (Objects.equals(existing.getId(), update.getId())) {
                        if (update.getRecordId() != null) {
                            existing.setRecordId(update.getRecordId());
                        }
                        if (update.getCurrentExercisesNo() != null) {
                            existing.setCurrentExercisesNo(update.getCurrentExercisesNo());
                        }
                        if (update.getCompleted() != null) {
                            existing.setCompleted(update.getCompleted());
                        }
                        if (catalogBatch != null && Objects.equals(catalogBatch.getId(), existing.getId())) {
                            catalogBatch = existing;
                        }
                    }
                }
                return 1;
            }).when(catalogBatchMapper).updateById(any(PracticeCatalogBatchDO.class));

            doAnswer(invocation -> {
                PracticeExercisesBatchDO batch = invocation.getArgument(0);
                batch.setId(exerciseBatchId.incrementAndGet());
                exerciseBatches.add(batch);
                if (batch.getExercisesId() != null) {
                    pendingAnswerExerciseIds.addLast(batch.getExercisesId());
                }
                return 1;
            }).when(exercisesBatchMapper).insert(any(PracticeExercisesBatchDO.class));
            doAnswer(invocation -> {
                Long customerAccountId = invocation.getArgument(0);
                Long catalogBatchId = invocation.getArgument(1);
                @SuppressWarnings("unchecked")
                List<Long> exerciseIds = invocation.getArgument(2, List.class);
                for (int index = 0; index < exerciseIds.size(); index++) {
                    PracticeExercisesBatchDO batch = PracticeExercisesBatchDO.builder()
                            .id(exerciseBatchId.incrementAndGet())
                            .customerAccountId(customerAccountId)
                            .catalogBatchId(catalogBatchId)
                            .exercisesId(exerciseIds.get(index))
                            .sortNo(index + 1)
                            .build();
                    exerciseBatches.add(batch);
                }
                return exerciseIds.size();
            }).when(exercisesBatchMapper).insertBatchByExerciseIds(anyLong(), anyLong(), anyList(), anyString(), any());

            doAnswer(invocation -> {
                PracticeExercisesAnswerBatchDO batch = invocation.getArgument(0);
                batch.setId(answerBatchId.incrementAndGet());
                answerBatches.add(batch);
                return 1;
            }).when(answerBatchMapper).insert(any(PracticeExercisesAnswerBatchDO.class));
            doAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                List<PracticeExercisesAnswerBatchDO> batches = invocation.getArgument(0, List.class);
                for (PracticeExercisesAnswerBatchDO batch : batches) {
                    batch.setId(answerBatchId.incrementAndGet());
                    answerBatches.add(batch);
                }
                return batches == null ? 0 : batches.size();
            }).when(answerBatchMapper).insertBatch(anyList(), anyString(), any());
            doAnswer(invocation -> {
                Long catalogBatchId = invocation.getArgument(0);
                int inserted = 0;
                List<PracticeExercisesBatchDO> matchedBatches = exerciseBatches.stream()
                        .filter(batch -> Objects.equals(batch.getCatalogBatchId(), catalogBatchId))
                        .sorted(Comparator.comparing(PracticeExercisesBatchDO::getSortNo))
                        .collect(Collectors.toList());
                for (PracticeExercisesBatchDO batch : matchedBatches) {
                    List<PracticeExercisesAnswerDO> answers = answersByExerciseId.getOrDefault(
                            batch.getExercisesId(), Collections.emptyList());
                    for (int answerIndex = 0; answerIndex < answers.size(); answerIndex++) {
                        PracticeExercisesAnswerDO answer = answers.get(answerIndex);
                        PracticeExercisesAnswerBatchDO answerBatch = PracticeExercisesAnswerBatchDO.builder()
                                .id(answerBatchId.incrementAndGet())
                                .exercisesBatchId(batch.getId())
                                .answerId(answer.getId())
                                .questionType(answer.getQuestionType())
                                .answerCode(answer.getAnswerCode())
                                .answerContent(answer.getAnswerContent())
                                .correct(answer.getCorrect())
                                .sortNo(answer.getSortNo() == null ? answerIndex + 1 : answer.getSortNo())
                                .build();
                        answerBatches.add(answerBatch);
                        inserted++;
                    }
                }
                return inserted;
            }).when(answerBatchMapper).insertBatchByCatalogBatchId(anyLong(), anyString(), any());

            doAnswer(invocation -> {
                record = invocation.getArgument(0);
                record.setId(recordId.incrementAndGet());
                return 1;
            }).when(recordMapper).insert(any(UserPracticeExercisesRecordDO.class));
            doAnswer(invocation -> {
                UserPracticeExercisesRecordDO update = invocation.getArgument(0);
                if (record != null && Objects.equals(record.getId(), update.getId())) {
                    if (update.getCategoryId() != null) {
                        record.setCategoryId(update.getCategoryId());
                    }
                    if (update.getTotalScore() != null) {
                        record.setTotalScore(update.getTotalScore());
                    }
                    if (update.getCorrectCount() != null) {
                        record.setCorrectCount(update.getCorrectCount());
                    }
                    if (update.getWrongCount() != null) {
                        record.setWrongCount(update.getWrongCount());
                    }
                }
                return 1;
            }).when(recordMapper).updateById(any(UserPracticeExercisesRecordDO.class));

            doAnswer(invocation -> {
                UserPracticeExercisesRecordDetailDO detail = invocation.getArgument(0);
                detail.setId(recordDetailId.incrementAndGet());
                recordDetails.add(detail);
                return 1;
            }).when(recordDetailMapper).insert(any(UserPracticeExercisesRecordDetailDO.class));
            doAnswer(invocation -> {
                UserPracticeExercisesRecordDetailDO update = invocation.getArgument(0);
                recordDetails.removeIf(detail -> Objects.equals(detail.getId(), update.getId()));
                recordDetails.add(update);
                return 1;
            }).when(recordDetailMapper).updateById(any(UserPracticeExercisesRecordDetailDO.class));

            doAnswer(invocation -> {
                UserPracticeExercisesWrongRecordDetailDO detail = invocation.getArgument(0);
                detail.setId(wrongRecordId.incrementAndGet());
                wrongRecordDetails.add(detail);
                return 1;
            }).when(wrongRecordDetailMapper).insert(any(UserPracticeExercisesWrongRecordDetailDO.class));
            doAnswer(invocation -> {
                UserPracticeExercisesWrongRecordDetailDO update = invocation.getArgument(0);
                wrongRecordDetails.removeIf(detail -> Objects.equals(detail.getId(), update.getId()));
                wrongRecordDetails.add(update);
                return 1;
            }).when(wrongRecordDetailMapper).updateById(any(UserPracticeExercisesWrongRecordDetailDO.class));
            doAnswer(invocation -> {
                Long customerAccountId = invocation.getArgument(0);
                Long exercisesId = invocation.getArgument(1);
                wrongRecordDetails.removeIf(detail -> Objects.equals(detail.getCustomerAccountId(), customerAccountId)
                        && Objects.equals(detail.getExercisesId(), exercisesId));
                return 1;
            }).when(wrongRecordDetailMapper).deleteByCustomerAccountIdAndExercisesId(anyLong(), anyLong());
        }

        private List<Long> wrapperLongValues(Object wrapper) {
            List<Long> values = new ArrayList<>();
            if (wrapper instanceof AbstractWrapper) {
                ((AbstractWrapper<?, ?, ?>) wrapper).getParamNameValuePairs().values().stream()
                        .forEach(value -> {
                            if (value instanceof Number) {
                                values.add(((Number) value).longValue());
                                return;
                            }
                            if (value instanceof Collection) {
                                ((Collection<?>) value).forEach(item -> {
                                    if (item instanceof Number) {
                                        values.add(((Number) item).longValue());
                                    }
                                });
                                return;
                            }
                            if (value instanceof String && ((String) value).chars().allMatch(Character::isDigit)) {
                                values.add(Long.valueOf((String) value));
                            }
                        });
            }
            return values;
        }
    }
}
