package com.huiyitech.app.practice.service;

import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerCardRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitReqVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeCatalogBatchDetailRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionItemRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionOptionRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordAnswerRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeStartRespVO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCatalogBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCategoryDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeStepDO;
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
import com.huiyitech.practice.dal.mysql.practice.PracticeStepMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordDetailMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesWrongRecordDetailMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;
import java.time.Instant;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
public class FrontPracticeBatchService {

    private static final Logger log = LoggerFactory.getLogger(FrontPracticeBatchService.class);

    static final String DEFAULT_PRACTICE_ID = "uav-basic-001";
    static final String PRACTICE_MODE = "PRACTICE";
    static final String CHAPTER_TEST_MODE = "CHAPTER_TEST";
    static final String THEORY_EXAM_MODE = "THEORY_EXAM";
    static final String COMPREHENSIVE_EXAM_MODE = "COMPREHENSIVE_EXAM";
    static final String INSTRUCTOR_EXAM_MODE = "INSTRUCTOR_EXAM";
    static final String ASSESSMENT_MODE = "ASSESSMENT";
    static final String RANDOM_EXAM_MODE = "RANDOM_EXAM";
    static final String WRONG_REVIEW_MODE = "wrongReview";
    static final String ASSESSMENT_TOPIC_ID = "assessment";
    private static final Long SELF_ASSESSMENT_CATEGORY_ID = 13L;
    private static final Long CAREER_ASSESSMENT_CATEGORY_ID = 14L;
    static final String PRACTICE_ANSWER_PAGE = "/pages/practice/answer";
    private static final int ASSESSMENT_CATALOG_TYPE = 1;
    private static final String COMPREHENSIVE_EXAM_FIELD_TYPE = "comprehens";
    private static final Long DEFAULT_THEORY_EXAM_CATEGORY_ID = 10L;
    private static final Long DEFAULT_INSTRUCTOR_EXAM_CATEGORY_ID = 11L;
    private static final int THEORY_EXAM_QUESTION_COUNT = 10;
    private static final int INSTRUCTOR_EXAM_QUESTION_COUNT = 100;
    private static final Map<Long, Integer> COMPREHENSIVE_EXAM_CATEGORY_QUOTAS =
            FrontPracticeBatchUtils.buildComprehensiveExamCategoryQuotas();
    private static final Map<String, String> TOPIC_CATEGORY_CODE_MAP =
            FrontPracticeBatchUtils.buildTopicCategoryCodeMap();

    @Value("${huiyitech.practice.fixed-category.theory:10}")
    private Long theoryExamCategoryId = DEFAULT_THEORY_EXAM_CATEGORY_ID;
    @Value("${huiyitech.practice.fixed-category.instructor:11}")
    private Long instructorExamCategoryId = DEFAULT_INSTRUCTOR_EXAM_CATEGORY_ID;
    @Value("${huiyitech.practice.exam-time-limit.theory:45}")
    private Integer theoryExamTimeLimitMinutes = 45;
    @Value("${huiyitech.practice.exam-time-limit.comprehensive:45}")
    private Integer comprehensiveExamTimeLimitMinutes = 45;
    @Value("${huiyitech.practice.exam-time-limit.instructor:60}")
    private Integer instructorExamTimeLimitMinutes = 60;

    @Resource
    private PracticeCategoryMapper practiceCategoryMapper;
    @Resource
    private PracticeExercisesMapper practiceExercisesMapper;
    @Resource
    private PracticeExercisesAnswerMapper practiceExercisesAnswerMapper;
    @Resource
    private PracticeExercisesAnswerChildMapper practiceExercisesAnswerChildMapper;
    @Resource
    private PracticeCatalogBatchMapper practiceCatalogBatchMapper;
    @Resource
    private PracticeExercisesBatchMapper practiceExercisesBatchMapper;
    @Resource
    private PracticeExercisesAnswerBatchMapper practiceExercisesAnswerBatchMapper;
    @Resource
    private PracticeStepMapper practiceStepMapper;
    @Resource
    private UserPracticeExercisesRecordMapper userPracticeExercisesRecordMapper;
    @Resource
    private UserPracticeExercisesRecordDetailMapper userPracticeExercisesRecordDetailMapper;
    @Resource
    private UserPracticeExercisesWrongRecordDetailMapper userPracticeExercisesWrongRecordDetailMapper;
    @Resource
    private TransactionTemplate transactionTemplate;
    @Resource
    private AssessmentBatchSaveStatusTransactionService assessmentBatchSaveStatusTransactionService;
    private final Map<String, PracticeRuntimeSession> runtimeSessions = new ConcurrentHashMap<>();
    private final Map<Long, Object> careerAssessmentStartLocks = new ConcurrentHashMap<>();
    private Random practiceRandom = new Random();

    public AppPracticeStartRespVO startPracticeMode(LoginUser loginUser, String practiceId, String topicId) {
        PracticeCategoryDO category = resolveSelectedPracticeCategory(FrontPracticeBatchUtils.requireTopicId(topicId));
        CategoryReference categoryReference = resolveCategoryReference(category);
        return startBatch(loginUser, FrontPracticeBatchUtils.normalizePracticeId(practiceId, DEFAULT_PRACTICE_ID), BatchStartPlan.builder()
                .mode(PRACTICE_MODE)
                .type(1)
                .category(category)
                .categoryReference(categoryReference)
                .exerciseIds(listCategoryExerciseIds(category.getId()))
                .shuffleQuestions(false)
                .shuffleAnswers(false)
                .build());
    }

    public AppPracticeStartRespVO startChapterTest(LoginUser loginUser, String practiceId, String topicId) {
        PracticeCategoryDO category = resolveSelectedPracticeCategory(FrontPracticeBatchUtils.requireTopicId(topicId));
        CategoryReference categoryReference = resolveCategoryReference(category);
        return startBatch(loginUser, FrontPracticeBatchUtils.normalizePracticeId(practiceId, DEFAULT_PRACTICE_ID), BatchStartPlan.builder()
                .mode(CHAPTER_TEST_MODE)
                .type(2)
                .category(category)
                .categoryReference(categoryReference)
                .exerciseIds(listCategoryExerciseIds(category.getId()))
                .shuffleQuestions(true)
                .shuffleAnswers(true)
                .build());
    }

    public AppPracticeStartRespVO startTheoryExam(LoginUser loginUser, String practiceId) {
        PracticeCategoryDO category = requirePracticeCategory(theoryExamCategoryId);
        CategoryReference categoryReference = resolveCategoryReference(category);
        return startBatch(loginUser, FrontPracticeBatchUtils.normalizePracticeId(practiceId, DEFAULT_PRACTICE_ID), BatchStartPlan.builder()
                .mode(THEORY_EXAM_MODE)
                .type(3)
                .category(category)
                .categoryReference(categoryReference)
                .exerciseIds(FrontPracticeBatchUtils.pickRandomExerciseIds(category.getId(), THEORY_EXAM_QUESTION_COUNT,
                        "理论考试", this::listCategoryExerciseIds, practiceRandom))
                .shuffleQuestions(true)
                .shuffleAnswers(true)
                .build());
    }

    public AppPracticeStartRespVO startComprehensiveExam(LoginUser loginUser, String practiceId) {
        return startBatch(loginUser, FrontPracticeBatchUtils.normalizePracticeId(practiceId, DEFAULT_PRACTICE_ID), BatchStartPlan.builder()
                .mode(COMPREHENSIVE_EXAM_MODE)
                .type(4)
                .category(PracticeCategoryDO.builder()
                        .categoryName("综合考试")
                        .fieldType(COMPREHENSIVE_EXAM_FIELD_TYPE)
                        .categoryStatus(Boolean.TRUE)
                        .build())
                .categoryReference(CategoryReference.builder()
                        .categoryId(theoryExamCategoryId)
                        .categoryName("综合考试")
                        .fieldType(COMPREHENSIVE_EXAM_FIELD_TYPE)
                        .build())
                .exerciseIds(FrontPracticeBatchUtils.pickComprehensiveExamExerciseIds(
                        COMPREHENSIVE_EXAM_CATEGORY_QUOTAS, this::listCategoryExerciseIds, practiceRandom))
                .shuffleQuestions(true)
                .shuffleAnswers(true)
                .build());
    }

    public AppPracticeStartRespVO startInstructorExam(LoginUser loginUser, String practiceId) {
        PracticeCategoryDO category = requirePracticeCategory(instructorExamCategoryId);
        CategoryReference categoryReference = resolveCategoryReference(category);
        return startBatch(loginUser, FrontPracticeBatchUtils.normalizePracticeId(practiceId, DEFAULT_PRACTICE_ID), BatchStartPlan.builder()
                .mode(INSTRUCTOR_EXAM_MODE)
                .type(5)
                .category(category)
                .categoryReference(categoryReference)
                .exerciseIds(FrontPracticeBatchUtils.pickRandomExerciseIds(category.getId(), INSTRUCTOR_EXAM_QUESTION_COUNT,
                        "教员考试", this::listCategoryExerciseIds, practiceRandom))
                .shuffleQuestions(true)
                .shuffleAnswers(true)
                .build());
    }

    public AppPracticeStartRespVO startWrongReviewPractice(LoginUser loginUser, String practiceId, String topicId) {
        PracticeCategoryDO category = resolveSelectedPracticeCategory(topicId);
        CategoryReference categoryReference = resolveCategoryReference(category);
        return startBatch(loginUser, FrontPracticeBatchUtils.normalizePracticeId(practiceId, DEFAULT_PRACTICE_ID), BatchStartPlan.builder()
                .mode(WRONG_REVIEW_MODE)
                .type(1)
                .category(category)
                .categoryReference(categoryReference)
                .exerciseIds(listWrongExerciseIds(loginUser.getId(), topicId))
                .shuffleQuestions(false)
                .shuffleAnswers(false)
                .build());
    }

    public AppPracticeStartRespVO startAssessment(LoginUser loginUser, String practiceId, String topicId) {
        PracticeCategoryDO category = resolveSelectedAssessmentCategory();
        CategoryReference categoryReference = CategoryReference.builder()
                .categoryId(category.getId())
                .categoryName(category.getCategoryName())
                .fieldType(ASSESSMENT_TOPIC_ID)
                .build();
        return startBatch(loginUser, FrontPracticeBatchUtils.normalizePracticeId(practiceId, DEFAULT_PRACTICE_ID), BatchStartPlan.builder()
                .mode(ASSESSMENT_MODE)
                .type(1)
                .category(category)
                .categoryReference(categoryReference)
                .exerciseIds(listCategoryExerciseIds(category.getId()))
                .shuffleQuestions(false)
                .shuffleAnswers(false)
                .build());
    }

    /**
     * Category 14 is intentionally selected by its fixed business id. It must not
     * participate in the legacy catalog-type lookup used by self assessment.
     */
    public AppPracticeStartRespVO startCareerAssessment(LoginUser loginUser, String practiceId, Runnable cleanupAction) {
        if (loginUser == null || loginUser.getId() == null) {
            throw invalidParamException("登录用户不存在");
        }
        synchronized (careerAssessmentStartLock(loginUser.getId())) {
            Objects.requireNonNull(cleanupAction, "cleanupAction").run();
            return startCareerAssessmentUnlocked(loginUser, practiceId);
        }
    }

    private AppPracticeStartRespVO startCareerAssessmentUnlocked(LoginUser loginUser, String practiceId) {
        PracticeCategoryDO category = requireCareerAssessmentCategory();
        List<Long> exerciseIds = listCategoryExerciseIds(category.getId());
        validateCareerAssessmentStepMappings(category.getId(), exerciseIds);
        CategoryReference categoryReference = CategoryReference.builder()
                .categoryId(category.getId())
                .categoryName(category.getCategoryName())
                .fieldType(ASSESSMENT_TOPIC_ID)
                .build();
        return startBatch(loginUser, FrontPracticeBatchUtils.normalizePracticeId(practiceId, DEFAULT_PRACTICE_ID), BatchStartPlan.builder()
                .mode(ASSESSMENT_MODE)
                .type(1)
                .category(category)
                .categoryReference(categoryReference)
                .exerciseIds(exerciseIds)
                .shuffleQuestions(false)
                .shuffleAnswers(false)
                .build());
    }

    private Object careerAssessmentStartLock(Long userId) {
        return careerAssessmentStartLocks.computeIfAbsent(userId, ignored -> new Object());
    }

    /**
     * Removes only the persisted and in-memory batches belonging to one student's assessment sessions.
     * The caller owns the surrounding transaction because related answer records and reports are removed there.
     */
    public void deleteAssessmentBatches(Long customerAccountId, Collection<Long> catalogBatchIds) {
        if (customerAccountId == null) {
            return;
        }
        List<Long> batchIds = catalogBatchIds == null ? Collections.emptyList() : catalogBatchIds.stream()
                .filter(Objects::nonNull)
                .distinct()
                .collect(Collectors.toList());
        if (!batchIds.isEmpty()) {
            practiceExercisesAnswerBatchMapper.physicalDeleteByCustomerAccountIdAndCatalogBatchIds(customerAccountId, batchIds);
            practiceExercisesBatchMapper.physicalDeleteByCustomerAccountIdAndCatalogBatchIds(customerAccountId, batchIds);
            practiceCatalogBatchMapper.physicalDeleteByCustomerAccountIdAndModeAndIds(customerAccountId,
                    ASSESSMENT_MODE, batchIds);
        }
        runtimeSessions.entrySet().removeIf(entry -> customerAccountId.equals(entry.getValue().userId)
                && ASSESSMENT_MODE.equals(entry.getValue().mode));
    }

    public int closeIncompleteExamBatches(Long userId) {
        if (userId == null) {
            return 0;
        }
        List<PracticeCatalogBatchDO> batches = practiceCatalogBatchMapper.selectList(new LambdaQueryWrapperX<PracticeCatalogBatchDO>()
                .eq(PracticeCatalogBatchDO::getCustomerAccountId, userId)
                .in(PracticeCatalogBatchDO::getMode, examModes()));
        List<PracticeCatalogBatchDO> closedBatches = new ArrayList<>();
        for (PracticeCatalogBatchDO batch : batches) {
            if (Boolean.TRUE.equals(batch.getCompleted())) {
                continue;
            }
            batch.setCompleted(Boolean.TRUE);
            practiceCatalogBatchMapper.updateById(batch);
            closedBatches.add(batch);
        }
        if (!closedBatches.isEmpty()) {
            Set<Long> closedIds = closedBatches.stream().map(PracticeCatalogBatchDO::getId).collect(Collectors.toSet());
            runtimeSessions.entrySet().removeIf(entry -> userId.equals(entry.getValue().userId)
                    && closedIds.contains(entry.getValue().catalogBatchId));
        }
        return closedBatches.size();
    }

    @Scheduled(fixedDelayString = "${huiyitech.practice.exam-expiry-scan-ms:60000}")
    public void completeExpiredExamBatches() {
        List<PracticeCatalogBatchDO> batches = practiceCatalogBatchMapper.selectList(new LambdaQueryWrapperX<PracticeCatalogBatchDO>()
                .in(PracticeCatalogBatchDO::getMode, examModes()));
        for (PracticeCatalogBatchDO batch : batches) {
            if (!Boolean.TRUE.equals(batch.getCompleted())) {
                expireExamBatchIfNeeded(batch);
            }
        }
    }

    private Set<String> examModes() {
        return new LinkedHashSet<>(java.util.Arrays.asList(THEORY_EXAM_MODE, COMPREHENSIVE_EXAM_MODE, INSTRUCTOR_EXAM_MODE));
    }

    private boolean isExamMode(String mode) {
        return THEORY_EXAM_MODE.equals(mode) || COMPREHENSIVE_EXAM_MODE.equals(mode) || INSTRUCTOR_EXAM_MODE.equals(mode);
    }

    private Integer getExamTimeLimitMinutes(String mode) {
        if (THEORY_EXAM_MODE.equals(mode)) return Math.max(theoryExamTimeLimitMinutes, 1);
        if (COMPREHENSIVE_EXAM_MODE.equals(mode)) return Math.max(comprehensiveExamTimeLimitMinutes, 1);
        if (INSTRUCTOR_EXAM_MODE.equals(mode)) return Math.max(instructorExamTimeLimitMinutes, 1);
        return null;
    }

    private long getRemainingExamSeconds(PracticeCatalogBatchDO batch) {
        Integer minutes = getExamTimeLimitMinutes(batch.getMode());
        if (minutes == null || batch.getCreateTime() == null || Boolean.TRUE.equals(batch.getCompleted())) {
            return Boolean.TRUE.equals(batch.getCompleted()) ? 0L : 0L;
        }
        long remaining = Duration.between(LocalDateTime.now(), batch.getCreateTime().plusMinutes(minutes)).getSeconds();
        return Math.max(remaining, 0L);
    }

    private void expireExamBatchIfNeeded(PracticeCatalogBatchDO batch) {
        if (batch == null || !isExamMode(batch.getMode()) || Boolean.TRUE.equals(batch.getCompleted())) {
            return;
        }
        Integer minutes = getExamTimeLimitMinutes(batch.getMode());
        if (minutes != null && batch.getCreateTime() != null
                && !LocalDateTime.now().isBefore(batch.getCreateTime().plusMinutes(minutes))) {
            batch.setCompleted(Boolean.TRUE);
            practiceCatalogBatchMapper.updateById(batch);
            runtimeSessions.entrySet().removeIf(entry -> Objects.equals(entry.getValue().catalogBatchId, batch.getId()));
        }
    }

    private void ensureExamSessionActive(PracticeRuntimeSession session) {
        if (!isExamMode(session.mode) || session.catalogBatchId == null) {
            return;
        }
        PracticeCatalogBatchDO batch = requireCatalogBatch(session.catalogBatchId, session.userId);
        expireExamBatchIfNeeded(batch);
        if (Boolean.TRUE.equals(batch.getCompleted())) {
            throw invalidParamException("考试已结束，无法继续答题");
        }
    }

    public AppPracticeCatalogBatchDetailRespVO getCatalogBatchDetail(Long userId, Long catalogBatchId) {
        PracticeCatalogBatchDO catalogBatch = requireCatalogBatch(catalogBatchId, userId);
        expireExamBatchIfNeeded(catalogBatch);
        List<PracticeExercisesBatchDO> exerciseBatches = resolveCatalogExerciseBatches(catalogBatch);
        Map<Long, PracticeExercisesDO> exerciseMap = listExerciseMap(exerciseBatches.stream()
                .map(PracticeExercisesBatchDO::getExercisesId)
                .collect(Collectors.toList()));
        Integer total = catalogBatch.getTotal();
        if (total == null || total <= 0) {
            total = exerciseBatches.size();
        }
        Long recordId = resolveRecordIdForBatch(catalogBatch);
        Integer resumeQuestionIndex = null;
        Boolean pendingSubmit = Boolean.FALSE;
        if (!Boolean.TRUE.equals(catalogBatch.getCompleted()) && recordId != null) {
            resumeQuestionIndex = resolveResumeQuestionIndex(catalogBatch.getId(), recordId);
            pendingSubmit = PRACTICE_MODE.equals(catalogBatch.getMode())
                    && isCatalogBatchFullyAnswered(catalogBatch.getId(), recordId);
        }
        return AppPracticeCatalogBatchDetailRespVO.builder()
                .practiceId(StringUtils.hasText(catalogBatch.getPracticeId()) ? catalogBatch.getPracticeId() : DEFAULT_PRACTICE_ID)
                .catalogBatchId(catalogBatch.getId())
                .recordId(recordId)
                .sessionId(resolveSessionId(catalogBatch))
                .type(catalogBatch.getType())
                .categoryId(catalogBatch.getCategoryId())
                .categoryName(resolveCategoryName(catalogBatch))
                .total(total)
                .timeLimitMinutes(getExamTimeLimitMinutes(catalogBatch.getMode()))
                .remainingSeconds(getRemainingExamSeconds(catalogBatch))
                .completed(Boolean.TRUE.equals(catalogBatch.getCompleted()))
                .pendingSubmit(pendingSubmit)
                .resumeQuestionIndex(resumeQuestionIndex)
                .nextPage(StringUtils.hasText(catalogBatch.getNextPage()) ? catalogBatch.getNextPage() : PRACTICE_ANSWER_PAGE)
                .questionTypeStats(FrontPracticeBatchUtils.buildQuestionTypeStats(exerciseBatches, exerciseMap))
                .build();
    }

    public AppPracticeCatalogBatchDetailRespVO getLatestCatalogBatchDetail(Long userId, Integer type, String mode) {
        if (userId == null || type == null || !StringUtils.hasText(mode)) {
            throw invalidParamException("练习批次不存在");
        }
        String normalizedMode = normalizeCatalogBatchMode(mode);
        PracticeCatalogBatchDO latest = practiceCatalogBatchMapper.selectLatestByCustomerAccountIdAndTypeAndMode(
                userId, type.longValue(), normalizedMode);
        if (latest == null) {
            return null;
        }
        if (CHAPTER_TEST_MODE.equals(normalizedMode) && !Boolean.TRUE.equals(latest.getCompleted())
                && latest.getRecordId() != null && isCatalogBatchFullyAnswered(latest.getId(), latest.getRecordId())) {
            completeCatalogBatch(latest);
        }
        return getCatalogBatchDetail(userId, latest.getId());
    }

    private String normalizeCatalogBatchMode(String mode) {
        if ("practice".equalsIgnoreCase(mode)) {
            return PRACTICE_MODE;
        }
        if ("chapter-test".equalsIgnoreCase(mode)) {
            return CHAPTER_TEST_MODE;
        }
        throw invalidParamException("练习批次不存在");
    }

    public AppPracticeQuestionRespVO getQuestion(Long userId, String sessionId, Integer index) {
        PracticeRuntimeSession session = requireSession(sessionId, userId);
        ensureExamSessionActive(session);
        int currentIndex = FrontPracticeBatchUtils.normalizeIndex(index, session.exerciseBatchIds.size());
        PracticeExercisesBatchDO exerciseBatch = requireExerciseBatch(session.exerciseBatchIds.get(currentIndex));
        PracticeExercisesDO exercise = requireExercise(session, exerciseBatch.getExercisesId());
        PracticeStepDO step = findPracticeStep(exercise.getStepId(), exercise.getCategoryId());
        List<AppPracticeQuestionOptionRespVO> options = listBatchOptions(session, exerciseBatch.getId()).stream()
                .map(option -> AppPracticeQuestionOptionRespVO.builder()
                        .id(option.getId())
                        .label(option.getLabel())
                        .content(option.getContent())
                        .build())
                .collect(Collectors.toList());
        return AppPracticeQuestionRespVO.builder()
                .practiceId(session.practiceId)
                .sessionId(sessionId)
                .mode(session.mode)
                .currentIndex(currentIndex)
                .totalQuestions(session.exerciseBatchIds.size())
                .answeredCount(session.answeredCount)
                .correctCount(session.correctCount)
                .progressPercent(FrontPracticeBatchUtils.progressPercent(session.answeredCount, session.exerciseBatchIds.size()))
                .question(AppPracticeQuestionItemRespVO.builder()
                        .id(String.valueOf(exerciseBatch.getId()))
                        .exerciseId(exercise.getId())
                        .type(FrontPracticeBatchUtils.toDisplayQuestionType(exercise.getQuestionType()))
                        .title("第 " + (currentIndex + 1) + " 题")
                        .stem(exercise.getQuestionStem())
                        .score(exercise.getScore())
                        .isRequired(exercise.getIsRequired())
                        .stepName(step == null ? null : step.getStepName())
                        .stepStatus(step == null ? null : step.getStepStatus())
                        .options(options)
                        .build())
                .build();
    }

    public AppPracticeAnswerSubmitRespVO submitAnswer(Long userId, String sessionId, AppPracticeAnswerSubmitReqVO reqVO) {
        PracticeRuntimeSession session = requireSession(sessionId, userId);
        try {
            if (transactionTemplate == null) {
                return submitAnswerInTransaction(userId, sessionId, reqVO, session);
            }
            return transactionTemplate.execute(status -> submitAnswerInTransaction(userId, sessionId, reqVO, session));
        } catch (RuntimeException exception) {
            if (isAssessmentSession(session) && assessmentBatchSaveStatusTransactionService != null) {
                try {
                    assessmentBatchSaveStatusTransactionService.finishAssessmentBatchAfterFailure(
                            session.catalogBatchId, userId);
                } catch (RuntimeException compensationException) {
                    exception.addSuppressed(compensationException);
                    log.error("Failed to finish assessment batch save status after answer rollback catalogBatchId={} userId={}",
                            session.catalogBatchId, userId, compensationException);
                }
            }
            throw exception;
        }
    }

    private AppPracticeAnswerSubmitRespVO submitAnswerInTransaction(Long userId, String sessionId,
                                                                     AppPracticeAnswerSubmitReqVO reqVO,
                                                                     PracticeRuntimeSession session) {
        long totalStart = System.nanoTime();
        ensureExamSessionActive(session);
        long prepareStart = System.nanoTime();
        int currentIndex = FrontPracticeBatchUtils.normalizeIndex(reqVO == null ? null : reqVO.getCurrentIndex(),
                session.exerciseBatchIds.size());
        PracticeExercisesBatchDO exerciseBatch = requireExerciseBatch(session.exerciseBatchIds.get(currentIndex));
        PracticeExercisesDO exercise = requireExercise(session, exerciseBatch.getExercisesId());
        boolean textQuestion = FrontPracticeBatchUtils.isTextQuestion(exercise.getQuestionType());
        List<OptionSnapshot> options = textQuestion ? Collections.emptyList() : listBatchOptions(session, exerciseBatch.getId());
        List<String> correctOptionIds = options.stream()
                .filter(OptionSnapshot::isCorrect)
                .map(OptionSnapshot::getId)
                .collect(Collectors.toList());
        List<String> selectedOptionIds = FrontPracticeBatchUtils.normalizeSelectedOptionIds(reqVO);
        boolean optionalAssessmentQuestion = isOptionalAssessmentQuestion(session, exercise);
        if (selectedOptionIds.isEmpty() && !optionalAssessmentQuestion) {
            throw invalidParamException("答案不能为空");
        }
        boolean correct = textQuestion || correctOptionIds.isEmpty()
                || FrontPracticeBatchUtils.sameOptions(selectedOptionIds, correctOptionIds);
        List<String> storedSelectedAnswers = textQuestion
                ? selectedOptionIds
                : FrontPracticeBatchUtils.resolveOptionCodes(options, selectedOptionIds);
        List<String> storedCorrectAnswers = textQuestion
                ? Collections.emptyList()
                : FrontPracticeBatchUtils.resolveOptionCodes(options, correctOptionIds);
        session.answer(currentIndex, exerciseBatch.getId(), exerciseBatch.getExercisesId(), exercise,
                storedSelectedAnswers, storedCorrectAnswers, correct);
        long prepareCostMs = elapsedMillis(prepareStart);
        long persistStart = System.nanoTime();
        persistProgress(session, currentIndex);
        long persistCostMs = elapsedMillis(persistStart);
        boolean completed = session.answeredIndexes.size() >= session.exerciseBatchIds.size();
        int nextQuestionIndex = completed ? currentIndex : FrontPracticeBatchUtils.nextIndex(session, currentIndex);
        log.info("practice.submitAnswer costMs total={} prepare={} persist={} userId={} sessionId={} currentIndex={} completed={}",
                elapsedMillis(totalStart), prepareCostMs, persistCostMs, userId, sessionId, currentIndex, completed);
        return AppPracticeAnswerSubmitRespVO.builder()
                .questionId(String.valueOf(exerciseBatch.getId()))
                .selectedOptionId(String.join(",", selectedOptionIds))
                .selectedOptionIds(selectedOptionIds)
                .correctOptionId(String.join(",", correctOptionIds))
                .correctOptionIds(correctOptionIds)
                .correct(correct)
                .explanation(StringUtils.hasText(exercise.getCorrectMemo()) ? exercise.getCorrectMemo() : "暂无标准解析。")
                .currentIndex(currentIndex)
                .nextQuestionIndex(nextQuestionIndex)
                .totalQuestions(session.exerciseBatchIds.size())
                .answeredCount(session.answeredCount)
                .correctCount(session.correctCount)
                .progressPercent(FrontPracticeBatchUtils.progressPercent(session.answeredCount, session.exerciseBatchIds.size()))
                .completed(completed)
                .recordId(String.valueOf(session.recordId))
                .build();
    }

    private boolean isOptionalAssessmentQuestion(PracticeRuntimeSession session, PracticeExercisesDO exercise) {
        return session != null
                && ASSESSMENT_MODE.equals(session.mode)
                && exercise != null
                && (SELF_ASSESSMENT_CATEGORY_ID.equals(exercise.getCategoryId())
                || CAREER_ASSESSMENT_CATEGORY_ID.equals(exercise.getCategoryId()))
                && Boolean.FALSE.equals(exercise.getIsRequired());
    }

    /**
     * Removes only one student's category-14 run snapshots, catalog rows, and
     * runtime sessions selected by the caller. The IDs are catalog batch IDs;
     * question and answer templates are never part of this deletion chain.
     */
    public void deleteCareerAssessmentBatches(Long customerAccountId, Collection<Long> catalogBatchIds) {
        if (customerAccountId == null) {
            return;
        }
        List<Long> batchIds = catalogBatchIds == null ? Collections.emptyList() : catalogBatchIds.stream()
                .filter(Objects::nonNull)
                .distinct()
                .collect(Collectors.toList());
        if (batchIds.isEmpty()) {
            return;
        }
        practiceExercisesAnswerBatchMapper.physicalDeleteByCustomerAccountIdAndCatalogBatchIds(customerAccountId, batchIds);
        practiceExercisesBatchMapper.physicalDeleteByCustomerAccountIdAndCatalogBatchIds(customerAccountId, batchIds);
        practiceCatalogBatchMapper.physicalDeleteByCustomerAccountIdAndModeAndIds(customerAccountId,
                ASSESSMENT_MODE, batchIds);
        runtimeSessions.entrySet().removeIf(entry -> customerAccountId.equals(entry.getValue().userId)
                && CAREER_ASSESSMENT_CATEGORY_ID.equals(entry.getValue().assessmentCategoryId)
                && batchIds.contains(entry.getValue().catalogBatchId));
    }

    public AppPracticeAnswerCardRespVO buildAnswerCard(UserPracticeExercisesRecordDO record) {
        Long catalogBatchId = resolveRecordCatalogBatchId(record);
        if (record == null || catalogBatchId == null) {
            throw invalidParamException("当前练习记录暂不支持答题卡");
        }
        PracticeCatalogBatchDO catalogBatch = practiceCatalogBatchMapper.selectById(catalogBatchId);
        List<PracticeExercisesBatchDO> exerciseBatches = catalogBatch == null
                ? Collections.emptyList()
                : resolveCatalogExerciseBatches(catalogBatch);
        Set<Long> completedBatchIds = userPracticeExercisesRecordDetailMapper.selectList(
                        new LambdaQueryWrapperX<UserPracticeExercisesRecordDetailDO>()
                                .eq(UserPracticeExercisesRecordDetailDO::getRecordId, record.getId())
                                .orderByAsc(UserPracticeExercisesRecordDetailDO::getId))
                .stream()
                .map(UserPracticeExercisesRecordDetailDO::getExercisesId)
                .filter(id -> id != null)
                .collect(Collectors.toCollection(LinkedHashSet::new));
        List<AppPracticeAnswerCardRespVO.AnswerCardDetailItem> detail = exerciseBatches.stream()
                .map(batch -> AppPracticeAnswerCardRespVO.AnswerCardDetailItem.builder()
                        .exercisesBatchId(batch.getId())
                        .isCompleted(completedBatchIds.contains(batch.getId()))
                        .sortNo(batch.getSortNo())
                        .build())
                .collect(Collectors.toList());
        return AppPracticeAnswerCardRespVO.builder()
                .total(detail.size())
                .catalogBatchId(catalogBatchId)
                .detail(detail)
                .build();
    }

    public List<AppPracticeRecordAnswerRespVO> buildRecordAnswers(UserPracticeExercisesRecordDO record) {
        if (record == null || record.getId() == null) {
            return Collections.emptyList();
        }
        List<UserPracticeExercisesRecordDetailDO> details = userPracticeExercisesRecordDetailMapper.selectList(
                new LambdaQueryWrapperX<UserPracticeExercisesRecordDetailDO>()
                        .eq(UserPracticeExercisesRecordDetailDO::getRecordId, record.getId())
                        .orderByAsc(UserPracticeExercisesRecordDetailDO::getId));
        List<AppPracticeRecordAnswerRespVO> answers = new ArrayList<>();
        for (UserPracticeExercisesRecordDetailDO detail : details) {
            PracticeExercisesBatchDO batch = resolveRecordExerciseBatch(record, detail);
            if (batch == null || batch.getExercisesId() == null) {
                throw invalidParamException("练习记录关联题目批次不存在");
            }
            PracticeExercisesDO exercise = requireExercise(batch.getExercisesId());
            PracticeStepDO step = findPracticeStep(exercise.getStepId(), exercise.getCategoryId());
            List<OptionSnapshot> options = listBatchOptions(null, batch.getId());
            boolean textQuestion = FrontPracticeBatchUtils.isTextQuestion(exercise.getQuestionType());
            List<String> selectedOptionIds = textQuestion
                    ? FrontPracticeBatchUtils.singletonTextAnswer(detail.getAnswerCode())
                    : FrontPracticeBatchUtils.splitOptionIds(detail.getAnswerCode());
            List<String> correctOptionIds = textQuestion
                    ? Collections.emptyList()
                    : FrontPracticeBatchUtils.splitOptionIds(detail.getCorrectAnswerCode());
            String explanation = StringUtils.hasText(exercise.getCorrectMemo()) ? exercise.getCorrectMemo() : "暂无标准解析。";
            answers.add(AppPracticeRecordAnswerRespVO.builder()
                    .no(answers.size() + 1)
                    .questionId(String.valueOf(batch == null ? exercise.getId() : batch.getId()))
                    .type(FrontPracticeBatchUtils.toDisplayQuestionType(exercise.getQuestionType()))
                    .question(exercise.getQuestionStem())
                    .selectedOptionIds(selectedOptionIds)
                    .answer(textQuestion
                            ? FrontPracticeBatchUtils.textAnswerContent(detail.getAnswerCode())
                            : FrontPracticeBatchUtils.optionContents(options, selectedOptionIds))
                    .correctOptionIds(correctOptionIds)
                    .correct(textQuestion
                            ? FrontPracticeBatchUtils.textCorrectContent(explanation)
                            : FrontPracticeBatchUtils.optionContents(options, correctOptionIds))
                    .correctFlag(Boolean.TRUE.equals(detail.getCorrect()))
                    .explanation(explanation)
                    .stepName(step == null ? null : step.getStepName())
                    .stepStatus(step == null ? null : step.getStepStatus())
                    .build());
        }
        return answers;
    }

    public Map<Long, Integer> listWrongCountStats(Long userId) {
        List<UserPracticeExercisesWrongRecordDetailDO> wrongRecords = listUserWrongRecords(userId);
        if (wrongRecords.isEmpty()) {
            return Collections.emptyMap();
        }
        return wrongRecords.stream()
                .map(this::resolveWrongRecordCategoryId)
                .filter(categoryId -> categoryId != null)
                .collect(Collectors.toMap(categoryId -> categoryId, categoryId -> 1, Integer::sum, LinkedHashMap::new));
    }

    public Long resolveRecordId(String recordId, Long userId) {
        if (!StringUtils.hasText(recordId) || userId == null) {
            throw invalidParamException("练习记录不存在");
        }
        String normalized = recordId.trim();
        PracticeRuntimeSession session = runtimeSessions.get(normalized);
        if (session != null && userId.equals(session.userId) && session.recordId != null) {
            return session.recordId;
        }
        if (normalized.chars().allMatch(Character::isDigit)) {
            return Long.valueOf(normalized);
        }
        PracticeCatalogBatchDO batch = practiceCatalogBatchMapper.selectOne(new LambdaQueryWrapperX<PracticeCatalogBatchDO>()
                .eq(PracticeCatalogBatchDO::getSessionId, normalized)
                .eq(PracticeCatalogBatchDO::getCustomerAccountId, userId)
                .orderByDesc(PracticeCatalogBatchDO::getId)
                .last("LIMIT 1"));
        if (batch != null && batch.getRecordId() != null) {
            return batch.getRecordId();
        }
        throw invalidParamException("练习记录不存在");
    }

    void setPracticeRandom(Random random) {
        this.practiceRandom = random;
    }

    private AppPracticeStartRespVO startBatch(LoginUser loginUser, String practiceId, BatchStartPlan plan) {
        if (!isCareerAssessmentPlan(plan)) {
            AppPracticeStartRespVO resumed = resumeLatestIncompleteCategoryBatch(loginUser, practiceId, plan);
            if (resumed != null) {
                return resumed;
            }
        }
        List<PracticeExercisesDO> orderedExercises = resolveOrderedExercises(plan.exerciseIds, plan.mode);
        if (plan.shuffleQuestions) {
            FrontPracticeBatchUtils.shuffleInPlace(orderedExercises, practiceRandom);
        }
        String sessionId = practiceId + "-" + plan.mode + "-" + Instant.now().toEpochMilli();
        PracticeCatalogBatchDO catalogBatch = PracticeCatalogBatchDO.builder()
                .customerAccountId(loginUser.getId())
                .categoryId(plan.categoryReference == null ? null : plan.categoryReference.categoryId)
                .categoryName(plan.categoryReference == null ? null : plan.categoryReference.categoryName)
                .sessionId(sessionId)
                .practiceId(practiceId)
                .mode(plan.mode)
                .type(plan.type)
                .batchNo(sessionId)
                .total(orderedExercises.size())
                .nextPage(PRACTICE_ANSWER_PAGE)
                .completed(Boolean.FALSE)
                .status(0)
                .currentExercisesNo(1)
                .build();
        practiceCatalogBatchMapper.insert(catalogBatch);

        List<Long> orderedExerciseBatchIds = new ArrayList<>();
        Map<Long, List<OptionSnapshot>> optionSnapshotsByBatchId = new LinkedHashMap<>();
        int totalScore = orderedExercises.stream()
                .map(PracticeExercisesDO::getScore)
                .filter(score -> score != null && score > 0)
                .mapToInt(Integer::intValue)
                .sum();
        if (supportsSequentialBatchCopy(plan)) {
            BatchSnapshot batchSnapshot = createSequentialBatchSnapshot(loginUser.getId(), catalogBatch.getId(), orderedExercises);
            orderedExerciseBatchIds.addAll(batchSnapshot.exerciseBatchIds);
            optionSnapshotsByBatchId.putAll(batchSnapshot.optionSnapshotsByBatchId);
        } else {
            BatchSnapshot batchSnapshot = createShuffledBatchSnapshot(loginUser.getId(), catalogBatch.getId(), orderedExercises);
            orderedExerciseBatchIds.addAll(batchSnapshot.exerciseBatchIds);
            optionSnapshotsByBatchId.putAll(batchSnapshot.optionSnapshotsByBatchId);
        }

        UserPracticeExercisesRecordDO record = UserPracticeExercisesRecordDO.builder()
                .customerAccountId(loginUser.getId())
                .categoryId(catalogBatch.getId())
                .totalScore(totalScore)
                .correctCount(0)
                .wrongCount(0)
                .fieldType(plan.categoryReference == null ? null : plan.categoryReference.fieldType)
                .build();
        userPracticeExercisesRecordMapper.insert(record);
        catalogBatch.setRecordId(record.getId());
        practiceCatalogBatchMapper.updateById(catalogBatch);

        PracticeRuntimeSession session = new PracticeRuntimeSession(loginUser.getId(), practiceId, plan.mode, orderedExerciseBatchIds);
        session.recordId = record.getId();
        session.catalogBatchId = catalogBatch.getId();
        session.recordCategoryId = catalogBatch.getId();
        session.assessmentCategoryId = plan.categoryReference == null ? null : plan.categoryReference.categoryId;
        session.optionSnapshotsByBatchId.putAll(optionSnapshotsByBatchId);
        runtimeSessions.put(sessionId, session);

        return AppPracticeStartRespVO.builder()
                .practiceId(practiceId)
                .sessionId(sessionId)
                .batchId(String.valueOf(catalogBatch.getId()))
                .catalogBatchId(String.valueOf(catalogBatch.getId()))
                .recordId(String.valueOf(record.getId()))
                .resumeQuestionIndex(0)
                .mode(plan.mode)
                .nextPage(PRACTICE_ANSWER_PAGE)
                .build();
    }

    private boolean supportsSequentialBatchCopy(BatchStartPlan plan) {
        return plan != null && !plan.shuffleAnswers;
    }

    private BatchSnapshot createSequentialBatchSnapshot(Long customerAccountId, Long catalogBatchId,
                                                        List<PracticeExercisesDO> orderedExercises) {
        if (catalogBatchId == null || customerAccountId == null || orderedExercises == null || orderedExercises.isEmpty()) {
            return BatchSnapshot.empty();
        }
        List<Long> orderedExerciseIds = orderedExercises.stream()
                .map(PracticeExercisesDO::getId)
                .filter(Objects::nonNull)
                .collect(Collectors.toList());
        if (orderedExerciseIds.isEmpty()) {
            return BatchSnapshot.empty();
        }
        LocalDateTime now = LocalDateTime.now();
        String operator = String.valueOf(customerAccountId);
        int insertedExerciseBatches = practiceExercisesBatchMapper.insertBatchByExerciseIds(
                customerAccountId, catalogBatchId, orderedExerciseIds, operator, now);
        List<PracticeExercisesBatchDO> exerciseBatches = listExerciseBatches(catalogBatchId);
        if (insertedExerciseBatches != orderedExerciseIds.size() || exerciseBatches.size() != orderedExerciseIds.size()) {
            throw invalidParamException("练习批次生成失败，请稍后重试");
        }
        practiceExercisesAnswerBatchMapper.insertBatchByCatalogBatchId(catalogBatchId, operator, now);
        Map<Long, List<OptionSnapshot>> optionSnapshotsByBatchId = buildOptionSnapshotsByBatchId(exerciseBatches);
        return new BatchSnapshot(exerciseBatches.stream()
                .map(PracticeExercisesBatchDO::getId)
                .collect(Collectors.toList()), optionSnapshotsByBatchId);
    }

    private BatchSnapshot createShuffledBatchSnapshot(Long customerAccountId, Long catalogBatchId,
                                                      List<PracticeExercisesDO> orderedExercises) {
        if (catalogBatchId == null || customerAccountId == null || orderedExercises == null || orderedExercises.isEmpty()) {
            return BatchSnapshot.empty();
        }
        List<Long> orderedExerciseIds = orderedExercises.stream()
                .map(PracticeExercisesDO::getId)
                .filter(Objects::nonNull)
                .collect(Collectors.toList());
        if (orderedExerciseIds.isEmpty()) {
            return BatchSnapshot.empty();
        }
        LocalDateTime now = LocalDateTime.now();
        String operator = String.valueOf(customerAccountId);
        int insertedExerciseBatches = practiceExercisesBatchMapper.insertBatchByExerciseIds(
                customerAccountId, catalogBatchId, orderedExerciseIds, operator, now);
        List<PracticeExercisesBatchDO> exerciseBatches = listExerciseBatches(catalogBatchId);
        if (insertedExerciseBatches != orderedExerciseIds.size() || exerciseBatches.size() != orderedExerciseIds.size()) {
            throw invalidParamException("练习批次生成失败，请稍后重试");
        }

        Map<Long, List<PracticeExercisesAnswerDO>> answersByExerciseId = practiceExercisesAnswerMapper.selectList(
                        new LambdaQueryWrapperX<PracticeExercisesAnswerDO>()
                                .in(PracticeExercisesAnswerDO::getExercisesId, orderedExerciseIds)
                                .orderByAsc(PracticeExercisesAnswerDO::getExercisesId)
                                .orderByAsc(PracticeExercisesAnswerDO::getSortNo)
                                .orderByAsc(PracticeExercisesAnswerDO::getId))
                .stream()
                .collect(Collectors.groupingBy(PracticeExercisesAnswerDO::getExercisesId, LinkedHashMap::new, Collectors.toList()));
        List<PracticeExercisesAnswerBatchDO> answerBatches = new ArrayList<>();
        for (PracticeExercisesBatchDO exerciseBatch : exerciseBatches) {
            if (exerciseBatch == null || exerciseBatch.getId() == null || exerciseBatch.getExercisesId() == null) {
                continue;
            }
            List<PracticeExercisesAnswerDO> answers = new ArrayList<>(
                    answersByExerciseId.getOrDefault(exerciseBatch.getExercisesId(), Collections.emptyList()));
            if (answers.isEmpty()) {
                continue;
            }
            FrontPracticeBatchUtils.shuffleInPlace(answers, practiceRandom);
            for (int answerIndex = 0; answerIndex < answers.size(); answerIndex++) {
                PracticeExercisesAnswerDO answer = answers.get(answerIndex);
                answerBatches.add(PracticeExercisesAnswerBatchDO.builder()
                        .exercisesBatchId(exerciseBatch.getId())
                        .answerId(answer.getId())
                        .questionType(answer.getQuestionType())
                        .answerCode(FrontPracticeBatchUtils.buildAnswerCode(answerIndex))
                        .answerContent(answer.getAnswerContent())
                        .correct(answer.getCorrect())
                        .sortNo(answerIndex + 1)
                        .build());
            }
        }
        if (!answerBatches.isEmpty()) {
            practiceExercisesAnswerBatchMapper.insertBatch(answerBatches, operator, now);
        }
        Map<Long, List<OptionSnapshot>> optionSnapshotsByBatchId = buildOptionSnapshotsByBatchId(exerciseBatches);
        return new BatchSnapshot(exerciseBatches.stream()
                .map(PracticeExercisesBatchDO::getId)
                .collect(Collectors.toList()), optionSnapshotsByBatchId);
    }

    private Map<Long, List<OptionSnapshot>> buildOptionSnapshotsByBatchId(List<PracticeExercisesBatchDO> exerciseBatches) {
        if (exerciseBatches == null || exerciseBatches.isEmpty()) {
            return Collections.emptyMap();
        }
        Map<Long, List<OptionSnapshot>> optionSnapshotsByBatchId = new LinkedHashMap<>();
        List<Long> exerciseBatchIds = new ArrayList<>();
        for (PracticeExercisesBatchDO exerciseBatch : exerciseBatches) {
            if (exerciseBatch == null || exerciseBatch.getId() == null) {
                continue;
            }
            exerciseBatchIds.add(exerciseBatch.getId());
            optionSnapshotsByBatchId.put(exerciseBatch.getId(), new ArrayList<>());
        }
        if (exerciseBatchIds.isEmpty()) {
            return optionSnapshotsByBatchId;
        }
        List<PracticeExercisesAnswerBatchDO> answerBatches = practiceExercisesAnswerBatchMapper.selectList(
                new LambdaQueryWrapperX<PracticeExercisesAnswerBatchDO>()
                        .in(PracticeExercisesAnswerBatchDO::getExercisesBatchId, exerciseBatchIds)
                        .orderByAsc(PracticeExercisesAnswerBatchDO::getExercisesBatchId)
                        .orderByAsc(PracticeExercisesAnswerBatchDO::getSortNo)
                        .orderByAsc(PracticeExercisesAnswerBatchDO::getId));
        for (PracticeExercisesAnswerBatchDO answerBatch : answerBatches) {
            List<OptionSnapshot> optionSnapshots = optionSnapshotsByBatchId.get(answerBatch.getExercisesBatchId());
            if (optionSnapshots == null) {
                continue;
            }
            optionSnapshots.add(OptionSnapshot.builder()
                    .id(String.valueOf(answerBatch.getId()))
                    .label(answerBatch.getAnswerCode())
                    .content(answerBatch.getAnswerContent())
                    .correct(Boolean.TRUE.equals(answerBatch.getCorrect()))
                    .build());
        }
        return optionSnapshotsByBatchId;
    }

    private AppPracticeStartRespVO resumeLatestIncompleteCategoryBatch(LoginUser loginUser, String practiceId,
                                                                       BatchStartPlan plan) {
        if (!PRACTICE_MODE.equals(plan.mode) && !CHAPTER_TEST_MODE.equals(plan.mode)) {
            return null;
        }
        if (loginUser == null || loginUser.getId() == null || plan.categoryReference == null
                || plan.categoryReference.categoryId == null) {
            throw invalidParamException("练习分类不存在");
        }
        PracticeCatalogBatchDO latest = practiceCatalogBatchMapper.selectLatestByUserCategoryAndMode(
                loginUser.getId(), plan.categoryReference.categoryId, plan.mode);
        if (latest == null) {
            return null;
        }
        if (Boolean.TRUE.equals(latest.getCompleted())) {
            return null;
        }
        if (!StringUtils.hasText(latest.getSessionId()) || latest.getRecordId() == null) {
            throw invalidParamException("未完成练习批次关联记录不完整");
        }
        UserPracticeExercisesRecordDO record = userPracticeExercisesRecordMapper.selectById(latest.getRecordId());
        if (record == null || !loginUser.getId().equals(record.getCustomerAccountId())
                || !latest.getId().equals(record.getCategoryId())) {
            throw invalidParamException("未完成练习批次关联记录不正确");
        }
        boolean fullyAnswered = isCatalogBatchFullyAnswered(latest.getId(), record.getId());
        if (CHAPTER_TEST_MODE.equals(plan.mode) && fullyAnswered) {
            completeCatalogBatch(latest);
            return null;
        }
        int resumeQuestionIndex = resolveResumeQuestionIndex(latest.getId(), record.getId());
        requireSession(latest.getSessionId(), loginUser.getId());
        return AppPracticeStartRespVO.builder()
                .practiceId(StringUtils.hasText(latest.getPracticeId()) ? latest.getPracticeId() : practiceId)
                .sessionId(latest.getSessionId())
                .batchId(String.valueOf(latest.getId()))
                .catalogBatchId(String.valueOf(latest.getId()))
                .recordId(String.valueOf(record.getId()))
                .resumeQuestionIndex(resumeQuestionIndex)
                .pendingSubmit(PRACTICE_MODE.equals(plan.mode) && fullyAnswered)
                .mode(latest.getMode())
                .nextPage(StringUtils.hasText(latest.getNextPage()) ? latest.getNextPage() : PRACTICE_ANSWER_PAGE)
                .build();
    }

    private int resolveResumeQuestionIndex(Long catalogBatchId, Long recordId) {
        List<PracticeExercisesBatchDO> exerciseBatches = listExerciseBatches(catalogBatchId);
        if (exerciseBatches.isEmpty()) {
            throw invalidParamException("未完成练习批次没有题目");
        }
        if (isCatalogBatchFullyAnswered(catalogBatchId, recordId)) {
            return Math.max(exerciseBatches.size() - 1, 0);
        }
        return resolveNextUnansweredIndex(catalogBatchId, recordId);
    }

    private int resolveNextUnansweredIndex(Long catalogBatchId, Long recordId) {
        List<PracticeExercisesBatchDO> exerciseBatches = listExerciseBatches(catalogBatchId);
        if (exerciseBatches.isEmpty()) {
            throw invalidParamException("未完成练习批次没有题目");
        }
        Set<Long> answeredExerciseBatchIds = userPracticeExercisesRecordDetailMapper.selectList(
                        new LambdaQueryWrapperX<UserPracticeExercisesRecordDetailDO>()
                                .eq(UserPracticeExercisesRecordDetailDO::getRecordId, recordId))
                .stream()
                .map(UserPracticeExercisesRecordDetailDO::getExercisesId)
                .filter(java.util.Objects::nonNull)
                .collect(Collectors.toSet());
        for (int index = 0; index < exerciseBatches.size(); index++) {
            if (!answeredExerciseBatchIds.contains(exerciseBatches.get(index).getId())) {
                return index;
            }
        }
        throw invalidParamException("未完成练习批次没有待答题目");
    }

    private boolean isCatalogBatchFullyAnswered(Long catalogBatchId, Long recordId) {
        if (catalogBatchId == null || recordId == null) {
            return false;
        }
        List<PracticeExercisesBatchDO> exerciseBatches = listExerciseBatches(catalogBatchId);
        if (exerciseBatches.isEmpty()) {
            return false;
        }
        Set<Long> answeredExerciseBatchIds = userPracticeExercisesRecordDetailMapper.selectList(
                        new LambdaQueryWrapperX<UserPracticeExercisesRecordDetailDO>()
                                .eq(UserPracticeExercisesRecordDetailDO::getRecordId, recordId))
                .stream()
                .map(UserPracticeExercisesRecordDetailDO::getExercisesId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());
        if (answeredExerciseBatchIds.size() < exerciseBatches.size()) {
            return false;
        }
        Set<Long> exerciseBatchIds = exerciseBatches.stream()
                .map(PracticeExercisesBatchDO::getId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());
        return !exerciseBatchIds.isEmpty() && answeredExerciseBatchIds.containsAll(exerciseBatchIds);
    }

    private void completeCatalogBatch(PracticeCatalogBatchDO batch) {
        if (batch == null || batch.getId() == null) {
            return;
        }
        practiceCatalogBatchMapper.updateById(PracticeCatalogBatchDO.builder()
                .id(batch.getId())
                .completed(Boolean.TRUE)
                .build());
        if (isAssessmentBatch(batch)) {
            markAssessmentBatchFinished(batch.getId(), batch.getCustomerAccountId());
        }
        batch.setCompleted(Boolean.TRUE);
        runtimeSessions.entrySet().removeIf(entry -> Objects.equals(entry.getValue().catalogBatchId, batch.getId()));
    }

    private void markAssessmentBatchFinished(Long catalogBatchId, Long customerAccountId) {
        PracticeCatalogBatchDO batchUpdate = PracticeCatalogBatchDO.builder()
                .id(catalogBatchId)
                .build();
        batchUpdate.setStatus(2);
        practiceCatalogBatchMapper.updateById(batchUpdate);
    }

    private PracticeCatalogBatchDO requireCatalogBatch(Long catalogBatchId, Long userId) {
        if (catalogBatchId == null || userId == null) {
            throw invalidParamException("练习批次不存在");
        }
        PracticeCatalogBatchDO batch = practiceCatalogBatchMapper.selectById(catalogBatchId);
        if (batch == null || !userId.equals(batch.getCustomerAccountId())) {
            throw invalidParamException("练习批次不存在");
        }
        return batch;
    }

    private Long resolveRecordIdForBatch(PracticeCatalogBatchDO batch) {
        if (batch.getRecordId() != null) {
            return batch.getRecordId();
        }
        UserPracticeExercisesRecordDO record = userPracticeExercisesRecordMapper.selectOne(
                new LambdaQueryWrapperX<UserPracticeExercisesRecordDO>()
                        .eq(UserPracticeExercisesRecordDO::getCategoryId, batch.getId())
                        .eq(UserPracticeExercisesRecordDO::getCustomerAccountId, batch.getCustomerAccountId())
                        .orderByDesc(UserPracticeExercisesRecordDO::getId)
                        .last("LIMIT 1"));
        return record == null ? null : record.getId();
    }

    private String resolveSessionId(PracticeCatalogBatchDO batch) {
        return FrontPracticeBatchUtils.resolveSessionId(batch, DEFAULT_PRACTICE_ID);
    }

    private String resolveCategoryName(PracticeCatalogBatchDO batch) {
        if (StringUtils.hasText(batch.getCategoryName())) {
            return batch.getCategoryName();
        }
        if (batch.getCategoryId() == null) {
            return "题库练习";
        }
        PracticeCategoryDO category = practiceCategoryMapper.selectById(batch.getCategoryId());
        return category == null ? "题库练习" : category.getCategoryName();
    }

    private PracticeRuntimeSession requireSession(String sessionId, Long userId) {
        PracticeRuntimeSession session = runtimeSessions.get(sessionId);
        if (session != null) {
            if (!userId.equals(session.userId)) {
                throw invalidParamException("练习会话已失效，请重新开始练习");
            }
            return session;
        }
        PracticeCatalogBatchDO batch = practiceCatalogBatchMapper.selectOne(new LambdaQueryWrapperX<PracticeCatalogBatchDO>()
                .eq(PracticeCatalogBatchDO::getSessionId, sessionId)
                .eq(PracticeCatalogBatchDO::getCustomerAccountId, userId)
                .orderByDesc(PracticeCatalogBatchDO::getId)
                .last("LIMIT 1"));
        if (batch == null) {
            throw invalidParamException("练习会话已失效，请重新开始练习");
        }
        PracticeRuntimeSession rebuilt = new PracticeRuntimeSession(userId,
                StringUtils.hasText(batch.getPracticeId()) ? batch.getPracticeId() : DEFAULT_PRACTICE_ID,
                StringUtils.hasText(batch.getMode()) ? batch.getMode() : PRACTICE_MODE,
                listExerciseBatches(batch.getId()).stream()
                        .map(PracticeExercisesBatchDO::getId)
                        .collect(Collectors.toList()));
        rebuilt.recordId = resolveRecordIdForBatch(batch);
        rebuilt.catalogBatchId = batch.getId();
        rebuilt.recordCategoryId = batch.getId();
        rebuilt.assessmentCategoryId = ASSESSMENT_MODE.equalsIgnoreCase(batch.getMode()) ? batch.getCategoryId() : null;
        List<UserPracticeExercisesRecordDetailDO> details = rebuilt.recordId == null ? Collections.emptyList()
                : userPracticeExercisesRecordDetailMapper.selectList(new LambdaQueryWrapperX<UserPracticeExercisesRecordDetailDO>()
                        .eq(UserPracticeExercisesRecordDetailDO::getRecordId, rebuilt.recordId)
                        .orderByAsc(UserPracticeExercisesRecordDetailDO::getId));
        Map<Long, PracticeExercisesBatchDO> exerciseBatchMap = listExerciseBatches(batch.getId()).stream()
                .collect(Collectors.toMap(PracticeExercisesBatchDO::getId, item -> item));
        Map<Long, Integer> batchIndexMap = new LinkedHashMap<>();
        for (int i = 0; i < rebuilt.exerciseBatchIds.size(); i++) {
            batchIndexMap.put(rebuilt.exerciseBatchIds.get(i), i);
        }
        for (UserPracticeExercisesRecordDetailDO detail : details) {
            if (detail.getExercisesId() == null) {
                continue;
            }
            Integer answeredIndex = batchIndexMap.get(detail.getExercisesId());
            if (answeredIndex != null) {
                PracticeExercisesBatchDO exerciseBatch = exerciseBatchMap.get(detail.getExercisesId());
                if (exerciseBatch == null) {
                    throw invalidParamException("练习记录关联题目批次不存在");
                }
                rebuilt.answer(answeredIndex, exerciseBatch.getId(), exerciseBatch.getExercisesId(),
                        requireExercise(exerciseBatch.getExercisesId()),
                        FrontPracticeBatchUtils.splitOptionIds(detail.getAnswerCode()),
                        FrontPracticeBatchUtils.splitOptionIds(detail.getCorrectAnswerCode()),
                        Boolean.TRUE.equals(detail.getCorrect()));
            }
        }
        runtimeSessions.put(sessionId, rebuilt);
        return rebuilt;
    }

    private void persistProgress(PracticeRuntimeSession session, int currentIndex) {
        long totalStart = System.nanoTime();
        long countCalcStart = System.nanoTime();
        int answeredCount = session.answeredCount;
        int correctCount = session.correctCount;
        int wrongCount = Math.max(answeredCount - correctCount, 0);
        long countCalcCostMs = elapsedMillis(countCalcStart);
        long recordUpdateStart = System.nanoTime();
        userPracticeExercisesRecordMapper.updateById(UserPracticeExercisesRecordDO.builder()
                .id(session.recordId)
                .categoryId(session.recordCategoryId)
                .correctCount(correctCount)
                .wrongCount(wrongCount)
                .build());
        long recordUpdateCostMs = elapsedMillis(recordUpdateStart);

        long batchUpdateStart = System.nanoTime();
        boolean completed = answeredCount >= session.exerciseBatchIds.size() && !isCareerAssessmentSession(session);
        PracticeCatalogBatchDO batchUpdate = PracticeCatalogBatchDO.builder()
                .id(session.catalogBatchId)
                .recordId(session.recordId)
                .currentExercisesNo(currentIndex + 1)
                .completed(completed)
                .build();
        practiceCatalogBatchMapper.updateById(batchUpdate);
        long batchUpdateCostMs = elapsedMillis(batchUpdateStart);

        long detailUpsertCostNanos = 0L;
        long wrongSyncCostNanos = 0L;
        AnswerSnapshot answer = session.answerSnapshots.get(currentIndex);
        if (answer != null) {
            if (isAssessmentSession(session)) {
                markAssessmentBatchSaving(session);
            }
            long detailUpsertStart = System.nanoTime();
            Long recordDetailId = upsertRecordDetail(session.recordId, answer);
            detailUpsertCostNanos += System.nanoTime() - detailUpsertStart;
            long wrongSyncStart = System.nanoTime();
            syncWrongRecordDetail(session.userId, recordDetailId, answer);
            wrongSyncCostNanos += System.nanoTime() - wrongSyncStart;
        }
        if (completed && isAssessmentSession(session)) {
            markAssessmentBatchFinished(session.catalogBatchId, session.userId);
        }

        long detailUpsertCostMs = Duration.ofNanos(detailUpsertCostNanos).toMillis();
        long wrongSyncCostMs = Duration.ofNanos(wrongSyncCostNanos).toMillis();
        log.info("practice.persistProgress costMs total={} countCalc={} recordUpdate={} batchUpdate={} detailUpsert={} wrongSync={} answerCount={} userId={} sessionId={} recordId={} catalogBatchId={}",
                elapsedMillis(totalStart), countCalcCostMs, recordUpdateCostMs, batchUpdateCostMs,
                detailUpsertCostMs, wrongSyncCostMs, answeredCount, session.userId, session.practiceId, session.recordId, session.catalogBatchId);
    }

    private void markAssessmentBatchSaving(PracticeRuntimeSession session) {
        practiceCatalogBatchMapper.markAssessmentBatchSaving(session.catalogBatchId, session.userId,
                String.valueOf(session.userId), LocalDateTime.now());
    }

    private long elapsedMillis(long startNanos) {
        return Duration.ofNanos(System.nanoTime() - startNanos).toMillis();
    }

    private Long upsertRecordDetail(Long recordId, AnswerSnapshot answer) {
        UserPracticeExercisesRecordDetailDO existing = userPracticeExercisesRecordDetailMapper.selectOne(
                new LambdaQueryWrapperX<UserPracticeExercisesRecordDetailDO>()
                        .eq(UserPracticeExercisesRecordDetailDO::getRecordId, recordId)
                        .eq(UserPracticeExercisesRecordDetailDO::getExercisesId, answer.exercisesBatchId)
                        .last("LIMIT 1"));
        if (existing == null) {
            UserPracticeExercisesRecordDetailDO detail = UserPracticeExercisesRecordDetailDO.builder()
                    .recordId(recordId)
                    .exercisesId(answer.exercisesBatchId)
                    .answerCode(String.join(",", answer.selectedAnswerCodes))
                    .correctAnswerCode(String.join(",", answer.correctAnswerCodes))
                    .correct(answer.correct)
                    .build();
            userPracticeExercisesRecordDetailMapper.insert(detail);
            return detail.getId();
        }
        existing.setExercisesId(answer.exercisesBatchId);
        existing.setAnswerCode(String.join(",", answer.selectedAnswerCodes));
        existing.setCorrectAnswerCode(String.join(",", answer.correctAnswerCodes));
        existing.setCorrect(answer.correct);
        userPracticeExercisesRecordDetailMapper.updateById(existing);
        return existing.getId();
    }

    private void syncWrongRecordDetail(Long userId, Long recordDetailId, AnswerSnapshot answer) {
        Long sourceExerciseId = requireSourceExerciseId(answer);
        UserPracticeExercisesWrongRecordDetailDO wrong = findWrongRecordDetail(userId, answer);
        if (answer.correct) {
            userPracticeExercisesWrongRecordDetailMapper.deleteByCustomerAccountIdAndExercisesId(userId, sourceExerciseId);
            return;
        }
        LocalDateTime now = LocalDateTime.now();
        if (wrong == null) {
            UserPracticeExercisesWrongRecordDetailDO detail = UserPracticeExercisesWrongRecordDetailDO.builder()
                    .customerAccountId(userId)
                    .recordDetailId(recordDetailId)
                    .exercisesId(sourceExerciseId)
                    .answerCode(String.join(",", answer.selectedAnswerCodes))
                    .correctAnswerCode(String.join(",", answer.correctAnswerCodes))
                    .wrongCount(1)
                    .latestWrongTime(now)
                    .build();
            userPracticeExercisesWrongRecordDetailMapper.insert(detail);
            return;
        }
        wrong.setRecordDetailId(recordDetailId);
        wrong.setExercisesId(sourceExerciseId);
        wrong.setAnswerCode(String.join(",", answer.selectedAnswerCodes));
        wrong.setCorrectAnswerCode(String.join(",", answer.correctAnswerCodes));
        wrong.setWrongCount((wrong.getWrongCount() == null ? 0 : wrong.getWrongCount()) + 1);
        wrong.setLatestWrongTime(now);
        userPracticeExercisesWrongRecordDetailMapper.updateById(wrong);
    }

    private UserPracticeExercisesWrongRecordDetailDO findWrongRecordDetail(Long userId, AnswerSnapshot answer) {
        return userPracticeExercisesWrongRecordDetailMapper.selectOne(
                new LambdaQueryWrapperX<UserPracticeExercisesWrongRecordDetailDO>()
                        .eq(UserPracticeExercisesWrongRecordDetailDO::getCustomerAccountId, userId)
                        .eq(UserPracticeExercisesWrongRecordDetailDO::getExercisesId, requireSourceExerciseId(answer))
                        .last("LIMIT 1"));
    }

    private Long resolveWrongRecordCategoryId(UserPracticeExercisesWrongRecordDetailDO wrongRecord) {
        PracticeExercisesDO exercise = wrongRecord == null ? null : practiceExercisesMapper.selectById(wrongRecord.getExercisesId());
        return exercise == null ? null : exercise.getCategoryId();
    }

    private Long requireSourceExerciseId(AnswerSnapshot answer) {
        if (answer == null || answer.exercisesId == null) {
            throw invalidParamException("练习原题不存在");
        }
        return answer.exercisesId;
    }

    private PracticeExercisesBatchDO resolveRecordExerciseBatch(UserPracticeExercisesRecordDO record,
                                                                UserPracticeExercisesRecordDetailDO detail) {
        if (record == null || detail == null || detail.getExercisesId() == null) {
            return null;
        }
        PracticeExercisesBatchDO batch = practiceExercisesBatchMapper.selectById(detail.getExercisesId());
        Long catalogBatchId = resolveRecordCatalogBatchId(record);
        if (batch == null || catalogBatchId == null || !catalogBatchId.equals(batch.getCatalogBatchId())) {
            return null;
        }
        return batch;
    }

    private PracticeCategoryDO resolveSelectedPracticeCategory(String topicId) {
        List<PracticeCategoryDO> categories = StringUtils.hasText(topicId)
                ? listMatchedCategories(topicId, 0)
                : Collections.emptyList();
        if (!categories.isEmpty()) {
            return categories.get(0);
        }
        throw invalidParamException("练习分类不存在：{}", topicId);
    }

    private PracticeCategoryDO resolveSelectedAssessmentCategory() {
        List<PracticeCategoryDO> categories = practiceCategoryMapper.selectList(new LambdaQueryWrapperX<PracticeCategoryDO>()
                        .eq(PracticeCategoryDO::getCatalogType, ASSESSMENT_CATALOG_TYPE)
                        .eq(PracticeCategoryDO::getCategoryStatus, Boolean.TRUE)
                        .orderByAsc(PracticeCategoryDO::getSortNo, PracticeCategoryDO::getId))
                .stream()
                .filter(this::isEnabledAssessmentCategory)
                .collect(Collectors.toList());
        if (categories.isEmpty()) {
            throw invalidParamException("自测分类不存在：catalog_type={}", ASSESSMENT_CATALOG_TYPE);
        }
        if (categories.size() > 1) {
            throw invalidParamException("自测分类配置不唯一：catalog_type={}", ASSESSMENT_CATALOG_TYPE);
        }
        return categories.get(0);
    }

    private boolean isEnabledAssessmentCategory(PracticeCategoryDO category) {
        return category != null
                && Objects.equals(category.getCatalogType(), ASSESSMENT_CATALOG_TYPE)
                && Boolean.TRUE.equals(category.getCategoryStatus());
    }

    private PracticeCategoryDO requirePracticeCategory(Long categoryId) {
        PracticeCategoryDO category = practiceCategoryMapper.selectById(categoryId);
        if (category == null) {
            throw invalidParamException("练习分类不存在：{}", categoryId);
        }
        return category;
    }

    private CategoryReference resolveCategoryReference(PracticeCategoryDO category) {
        if (category == null) {
            return CategoryReference.builder().build();
        }
        return CategoryReference.builder()
                .categoryId(category.getId())
                .categoryName(category.getCategoryName())
                .fieldType(category.getFieldType())
                .build();
    }

    private List<PracticeExercisesBatchDO> listExerciseBatches(Long catalogBatchId) {
        return practiceExercisesBatchMapper.selectList(new LambdaQueryWrapperX<PracticeExercisesBatchDO>()
                .eq(PracticeExercisesBatchDO::getCatalogBatchId, catalogBatchId)
                .orderByAsc(PracticeExercisesBatchDO::getSortNo)
                .orderByAsc(PracticeExercisesBatchDO::getId));
    }

    private Map<Long, PracticeExercisesDO> listExerciseMap(List<Long> exerciseIds) {
        if (exerciseIds == null || exerciseIds.isEmpty()) {
            return Collections.emptyMap();
        }
        return practiceExercisesMapper.selectBatchIds(exerciseIds).stream()
                .filter(exercise -> exercise != null && exercise.getId() != null)
                .collect(Collectors.toMap(PracticeExercisesDO::getId, exercise -> exercise, (left, right) -> left, LinkedHashMap::new));
    }

    private List<PracticeExercisesDO> resolveOrderedExercises(List<Long> exerciseIds, String mode) {
        if (exerciseIds == null || exerciseIds.isEmpty()) {
            throw invalidParamException(WRONG_REVIEW_MODE.equals(mode) ? "暂无错题可练习" : "暂无练习题可开始");
        }
        Map<Long, PracticeExercisesDO> exerciseMap = listExerciseMap(exerciseIds);
        List<PracticeExercisesDO> ordered = exerciseIds.stream()
                .map(exerciseMap::get)
                .filter(exercise -> exercise != null && exercise.getId() != null)
                .collect(Collectors.toList());
        if (ordered.size() != exerciseIds.size()) {
            throw invalidParamException("部分练习题不存在，请重新生成");
        }
        return ordered;
    }

    private List<PracticeExercisesAnswerDO> listAnswers(Long exerciseId) {
        return practiceExercisesAnswerMapper.selectList(new LambdaQueryWrapperX<PracticeExercisesAnswerDO>()
                .eq(PracticeExercisesAnswerDO::getExercisesId, exerciseId)
                .orderByAsc(PracticeExercisesAnswerDO::getSortNo)
                .orderByAsc(PracticeExercisesAnswerDO::getId));
    }

    private List<OptionSnapshot> listBatchOptions(PracticeRuntimeSession session, Long exercisesBatchId) {
        if (session != null) {
            List<OptionSnapshot> cached = session.optionSnapshotsByBatchId.get(exercisesBatchId);
            if (cached != null) {
                return cached;
            }
        }
        return practiceExercisesAnswerBatchMapper.selectList(new LambdaQueryWrapperX<PracticeExercisesAnswerBatchDO>()
                        .eq(PracticeExercisesAnswerBatchDO::getExercisesBatchId, exercisesBatchId)
                        .orderByAsc(PracticeExercisesAnswerBatchDO::getSortNo)
                        .orderByAsc(PracticeExercisesAnswerBatchDO::getId))
                .stream()
                .map(answer -> OptionSnapshot.builder()
                        .id(String.valueOf(answer.getId()))
                        .label(answer.getAnswerCode())
                        .content(answer.getAnswerContent())
                        .correct(Boolean.TRUE.equals(answer.getCorrect()))
                        .build())
                .collect(Collectors.toList());
    }

    private List<Long> listCategoryExerciseIds(Long categoryId) {
        if (categoryId == null) {
            return Collections.emptyList();
        }
        return practiceExercisesMapper.selectObjs(new QueryWrapper<PracticeExercisesDO>()
                        .select("id")
                        .eq("question_status", Boolean.TRUE)
                        .eq("category_id", categoryId)
                        .orderByAsc("sort_no IS NULL", "sort_no", "id"))
                .stream()
                .map(value -> ((Number) value).longValue())
                .collect(Collectors.toList());
    }

    private List<Long> listWrongExerciseIds(Long userId, String topicId) {
        Set<Long> allowedCategoryIds = resolveCategoryIds(topicId);
        return listUserWrongRecords(userId).stream()
                .map(UserPracticeExercisesWrongRecordDetailDO::getExercisesId)
                .filter(Objects::nonNull)
                .filter(exerciseId -> isAllowedWrongReviewExercise(exerciseId, allowedCategoryIds))
                .collect(Collectors.toCollection(LinkedHashSet::new))
                .stream()
                .collect(Collectors.toList());
    }

    private boolean isAllowedWrongReviewExercise(Long exerciseId, Set<Long> allowedCategoryIds) {
        PracticeExercisesDO exercise = practiceExercisesMapper.selectById(exerciseId);
        if (exercise == null || exercise.getCategoryId() == null) {
            return false;
        }
        return allowedCategoryIds.isEmpty() || allowedCategoryIds.contains(exercise.getCategoryId());
    }

    private Set<Long> resolveCategoryIds(String topicId) {
        if (!StringUtils.hasText(topicId)) {
            return Collections.emptySet();
        }
        List<PracticeCategoryDO> categories = listMatchedCategories(topicId, 0);
        if (categories.isEmpty()) {
            return Collections.emptySet();
        }
        return categories.stream()
                .map(PracticeCategoryDO::getId)
                .filter(id -> id != null)
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    private List<PracticeCategoryDO> listMatchedCategories(String topicId, int catalogType) {
        if (!StringUtils.hasText(topicId)) {
            return Collections.emptyList();
        }
        String normalizedTopicId = FrontPracticeBatchUtils.toCategoryCode(topicId, TOPIC_CATEGORY_CODE_MAP);
        Long normalizedCategoryId = normalizedTopicId.chars().allMatch(Character::isDigit)
                ? Long.valueOf(normalizedTopicId)
                : null;
        return practiceCategoryMapper.selectList(new LambdaQueryWrapperX<PracticeCategoryDO>()
                        .eq(PracticeCategoryDO::getCatalogType, catalogType)
                        .orderByAsc(PracticeCategoryDO::getSortNo, PracticeCategoryDO::getId))
                .stream()
                .filter(category -> Objects.equals(category.getId(), normalizedCategoryId)
                        || topicId.equals(category.getCategoryName())
                        || normalizedTopicId.equals(category.getCategoryName())
                        || topicId.equals(category.getFieldType())
                        || normalizedTopicId.equals(category.getFieldType()))
                .collect(Collectors.toList());
    }

    private PracticeStepDO findPracticeStep(Long stepId, Long categoryId) {
        if (stepId == null || categoryId == null || practiceStepMapper == null) {
            return null;
        }
        return practiceStepMapper.selectByIdAndCategoryId(stepId, categoryId);
    }

    /**
     * Category 14 only. The final answer is persisted by submitAnswer, but the
     * batch remains resumable until its independent career rules pass.
     */
    @Transactional(rollbackFor = Exception.class)
    public void completeCareerAssessment(Long userId, String sessionId, Long recordId) {
        if (userId == null || !StringUtils.hasText(sessionId) || recordId == null) {
            throw invalidParamException("职业规划评测记录不存在");
        }
        PracticeCatalogBatchDO batch = practiceCatalogBatchMapper.selectOne(new LambdaQueryWrapperX<PracticeCatalogBatchDO>()
                .eq(PracticeCatalogBatchDO::getSessionId, sessionId.trim())
                .eq(PracticeCatalogBatchDO::getCustomerAccountId, userId)
                .eq(PracticeCatalogBatchDO::getCategoryId, CAREER_ASSESSMENT_CATEGORY_ID)
                .eq(PracticeCatalogBatchDO::getMode, ASSESSMENT_MODE)
                .last("LIMIT 1"));
        if (batch == null || !recordId.equals(batch.getRecordId())) {
            throw invalidParamException("职业规划评测记录不存在");
        }
        if (!isCatalogBatchFullyAnswered(batch.getId(), recordId)) {
            throw invalidParamException("职业规划评测尚未完成");
        }
        completeCatalogBatch(batch);
    }

    private boolean isCareerAssessmentPlan(BatchStartPlan plan) {
        return plan != null && ASSESSMENT_MODE.equals(plan.mode) && plan.categoryReference != null
                && CAREER_ASSESSMENT_CATEGORY_ID.equals(plan.categoryReference.categoryId);
    }

    private boolean isCareerAssessmentSession(PracticeRuntimeSession session) {
        return session != null && CAREER_ASSESSMENT_CATEGORY_ID.equals(session.assessmentCategoryId)
                && ASSESSMENT_MODE.equals(session.mode);
    }

    private boolean isAssessmentSession(PracticeRuntimeSession session) {
        return session != null && ASSESSMENT_MODE.equals(session.mode)
                && (SELF_ASSESSMENT_CATEGORY_ID.equals(session.assessmentCategoryId)
                || CAREER_ASSESSMENT_CATEGORY_ID.equals(session.assessmentCategoryId));
    }

    private boolean isAssessmentBatch(PracticeCatalogBatchDO batch) {
        return batch != null && ASSESSMENT_MODE.equalsIgnoreCase(batch.getMode())
                && (SELF_ASSESSMENT_CATEGORY_ID.equals(batch.getCategoryId())
                || CAREER_ASSESSMENT_CATEGORY_ID.equals(batch.getCategoryId()));
    }

    private PracticeCategoryDO requireCareerAssessmentCategory() {
        PracticeCategoryDO category = requirePracticeCategory(CAREER_ASSESSMENT_CATEGORY_ID);
        if (!Boolean.TRUE.equals(category.getCategoryStatus())) {
            throw invalidParamException("职业规划评测分类未启用：{}", CAREER_ASSESSMENT_CATEGORY_ID);
        }
        return category;
    }

    private void validateCareerAssessmentStepMappings(Long categoryId, List<Long> exerciseIds) {
        if (exerciseIds == null || exerciseIds.isEmpty()) {
            throw invalidParamException("职业规划评测题库未初始化");
        }
        for (PracticeExercisesDO exercise : resolveOrderedExercises(exerciseIds, ASSESSMENT_MODE)) {
            if (exercise == null || !categoryId.equals(exercise.getCategoryId())
                    || exercise.getStepId() == null
                    || findPracticeStep(exercise.getStepId(), categoryId) == null) {
                throw invalidParamException("职业规划评测题目步骤关联不完整");
            }
        }
    }

    private PracticeExercisesBatchDO requireExerciseBatch(Long exercisesBatchId) {
        PracticeExercisesBatchDO batch = practiceExercisesBatchMapper.selectById(exercisesBatchId);
        if (batch == null) {
            throw invalidParamException("练习题目不存在：{}", exercisesBatchId);
        }
        return batch;
    }

    private PracticeExercisesDO requireExercise(PracticeRuntimeSession session, Long exerciseId) {
        PracticeExercisesDO exercise = session.exerciseCache.get(exerciseId);
        if (exercise != null) {
            return exercise;
        }
        exercise = requireExercise(exerciseId);
        session.exerciseCache.put(exerciseId, exercise);
        return exercise;
    }

    private PracticeExercisesDO requireExercise(Long exerciseId) {
        PracticeExercisesDO exercise = practiceExercisesMapper.selectById(exerciseId);
        if (exercise == null) {
            throw invalidParamException("练习题目不存在：{}", exerciseId);
        }
        return exercise;
    }

    private List<UserPracticeExercisesWrongRecordDetailDO> listUserWrongRecords(Long userId) {
        if (userId == null) {
            return Collections.emptyList();
        }
        return userPracticeExercisesWrongRecordDetailMapper.selectList(new LambdaQueryWrapperX<UserPracticeExercisesWrongRecordDetailDO>()
                .eq(UserPracticeExercisesWrongRecordDetailDO::getCustomerAccountId, userId)
                .orderByDesc(UserPracticeExercisesWrongRecordDetailDO::getLatestWrongTime)
                .orderByDesc(UserPracticeExercisesWrongRecordDetailDO::getId));
    }

    private Long resolveRecordCatalogBatchId(UserPracticeExercisesRecordDO record) {
        return record == null ? null : record.getCategoryId();
    }

    private List<PracticeExercisesBatchDO> resolveCatalogExerciseBatches(PracticeCatalogBatchDO catalogBatch) {
        return listExerciseBatches(catalogBatch.getId()).stream()
                .filter(batch -> batch != null && Objects.equals(batch.getCatalogBatchId(), catalogBatch.getId()))
                .collect(Collectors.toList());
    }

    @lombok.AllArgsConstructor
    private static final class BatchSnapshot {

        private final List<Long> exerciseBatchIds;
        private final Map<Long, List<OptionSnapshot>> optionSnapshotsByBatchId;

        private static BatchSnapshot empty() {
            return new BatchSnapshot(Collections.emptyList(), Collections.emptyMap());
        }
    }
}
