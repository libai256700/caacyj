package com.huiyitech.app.practice.service;

import cn.iocoder.yudao.framework.security.core.LoginUser;
import com.baomidou.mybatisplus.core.conditions.AbstractWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitReqVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerCardRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordDetailRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeStartRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeTopicRespVO;
import com.huiyitech.customer.dal.dataobject.customer.CustomerAccountDO;
import com.huiyitech.customer.dal.mysql.customer.CustomerAccountMapper;
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
import org.mockito.MockedStatic;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FrontPracticeServiceImplBatchStartContractTest {

    @Test
    void startPractice_shouldCreateOrderedBatchSnapshotForPracticeMode() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubPracticeModeSource();

        AppPracticeStartRespVO response = fixture.start("standard");

        assertEquals("PRACTICE", response.getMode());
        assertEquals(String.valueOf(fixture.catalogBatch.getId()), response.getBatchId());
        assertEquals(String.valueOf(fixture.record.getId()), response.getRecordId());
        assertEquals(fixture.catalogBatch.getBatchNo(), response.getSessionId());
        assertEquals(Arrays.asList(101L, 102L, 103L), fixture.exerciseBatches.stream()
                .map(PracticeExercisesBatchDO::getExercisesId)
                .collect(Collectors.toList()));
        assertEquals(Arrays.asList(1, 2, 3), fixture.exerciseBatches.stream()
                .map(PracticeExercisesBatchDO::getSortNo)
                .collect(Collectors.toList()));
        assertEquals(Arrays.asList("A", "B"), fixture.answerBatches.stream()
                .filter(answer -> answer.getExercisesBatchId().equals(fixture.exerciseBatches.get(0).getId()))
                .sorted(java.util.Comparator.comparing(PracticeExercisesAnswerBatchDO::getSortNo))
                .map(PracticeExercisesAnswerBatchDO::getAnswerCode)
                .collect(Collectors.toList()));
        assertEquals(fixture.catalogBatch.getId(), fixture.record.getCategoryId());
        assertEquals(Long.valueOf(9001L), fixture.record.getCustomerAccountId());
        verify(fixture.exercisesBatchMapper).insertBatchByExerciseIds(anyLong(), anyLong(), anyList(), anyString(), any(LocalDateTime.class));
        verify(fixture.answerBatchMapper).insertBatchByCatalogBatchId(anyLong(), anyString(), any(LocalDateTime.class));
        verify(fixture.exercisesBatchMapper, never()).insert(any(PracticeExercisesBatchDO.class));
        verify(fixture.answerBatchMapper, never()).insert(any(PracticeExercisesAnswerBatchDO.class));
    }

    @Test
    void startPractice_shouldShuffleExercisesAndAnswersForRandomExamMode() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubPracticeModeSource();
        fixture.setPracticeRandom(new Random(7L));

        AppPracticeStartRespVO response = fixture.start("RANDOM_EXAM");

        assertEquals("CHAPTER_TEST", response.getMode());
        List<Long> expectedExerciseOrder = shuffledCopy(Arrays.asList(101L, 102L, 103L), new Random(7L));
        assertEquals(expectedExerciseOrder, fixture.exerciseBatches.stream()
                .sorted(java.util.Comparator.comparing(PracticeExercisesBatchDO::getSortNo))
                .map(PracticeExercisesBatchDO::getExercisesId)
                .collect(Collectors.toList()));
        List<String> expectedFirstAnswerOrder = shuffledCopy(Arrays.asList("A", "B"), new RandomAdvance(7L, 1).random);
        assertEquals(Arrays.asList("A", "B"), fixture.answerBatches.stream()
                .filter(answer -> answer.getExercisesBatchId().equals(fixture.exerciseBatches.stream()
                        .filter(batch -> batch.getExercisesId().equals(expectedExerciseOrder.get(0)))
                        .findFirst()
                        .orElseThrow(AssertionError::new)
                        .getId()))
                .sorted(java.util.Comparator.comparing(PracticeExercisesAnswerBatchDO::getSortNo))
                .map(PracticeExercisesAnswerBatchDO::getAnswerCode)
                .collect(Collectors.toList()));
        assertEquals(expectedFirstAnswerOrder, fixture.answerBatches.stream()
                .filter(answer -> answer.getExercisesBatchId().equals(fixture.exerciseBatches.stream()
                        .filter(batch -> batch.getExercisesId().equals(expectedExerciseOrder.get(0)))
                        .findFirst()
                        .orElseThrow(AssertionError::new)
                        .getId()))
                .sorted(java.util.Comparator.comparing(PracticeExercisesAnswerBatchDO::getSortNo))
                .map(PracticeExercisesAnswerBatchDO::getAnswerContent)
                .map(content -> content.substring(content.length() - 1))
                .collect(Collectors.toList()));
        assertNotNull(response.getBatchId());
        assertNotNull(response.getRecordId());
        verify(fixture.exercisesBatchMapper).insertBatchByExerciseIds(anyLong(), anyLong(), anyList(), anyString(), any(LocalDateTime.class));
        verify(fixture.answerBatchMapper).insertBatch(anyList(), anyString(), any(LocalDateTime.class));
        verify(fixture.answerBatchMapper, never()).insertBatchByCatalogBatchId(anyLong(), anyString(), any(LocalDateTime.class));
    }

    @Test
    void startTheoryExam_shouldSelectTenRandomQuestionsFromCategory10() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubFixedExamSource(10L, 15, "理论分类");
        fixture.setPracticeRandom(new Random(3L));

        AppPracticeStartRespVO response = fixture.startTheoryExam();

        assertEquals("THEORY_EXAM", response.getMode());
        assertEquals(10, fixture.exerciseBatches.size());
        assertEquals(Long.valueOf(10L), fixture.catalogBatch.getCategoryId());
        assertEquals(Integer.valueOf(3), fixture.catalogBatch.getType());
    }

    @Test
    void startComprehensiveExam_shouldSelectConfiguredQuotaAcrossCategories1To9() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubComprehensiveExamSource();
        fixture.setPracticeRandom(new Random(5L));

        AppPracticeStartRespVO response = fixture.startComprehensiveExam();

        assertEquals("COMPREHENSIVE_EXAM", response.getMode());
        assertEquals(100, fixture.exerciseBatches.size());
        Map<Long, Long> categoryCounts = fixture.exerciseBatches.stream()
                .collect(Collectors.groupingBy(batch -> fixture.exerciseStore.get(batch.getExercisesId()).getCategoryId(),
                        LinkedHashMap::new, Collectors.counting()));
        assertEquals(Long.valueOf(5L), categoryCounts.get(1L));
        assertEquals(Long.valueOf(13L), categoryCounts.get(2L));
        assertEquals(Long.valueOf(3L), categoryCounts.get(3L));
        assertEquals(Long.valueOf(11L), categoryCounts.get(4L));
        assertEquals(Long.valueOf(7L), categoryCounts.get(5L));
        assertEquals(Long.valueOf(22L), categoryCounts.get(6L));
        assertEquals(Long.valueOf(7L), categoryCounts.get(7L));
        assertEquals(Long.valueOf(6L), categoryCounts.get(8L));
        assertEquals(Long.valueOf(26L), categoryCounts.get(9L));
        assertEquals(Integer.valueOf(4), fixture.catalogBatch.getType());
    }

    @Test
    void startInstructorExam_shouldSelectHundredRandomQuestionsFromCategory11() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubFixedExamSource(11L, 120, "教员分类");
        fixture.setPracticeRandom(new Random(9L));

        AppPracticeStartRespVO response = fixture.startInstructorExam();

        assertEquals("INSTRUCTOR_EXAM", response.getMode());
        assertEquals(100, fixture.exerciseBatches.size());
        assertEquals(Long.valueOf(11L), fixture.catalogBatch.getCategoryId());
        assertEquals(Integer.valueOf(5), fixture.catalogBatch.getType());
    }

    @Test
    void startPractice_shouldRouteAssessmentModeByCatalogTypeOnly() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubAssessmentSource();

        AppPracticeStartRespVO response = fixture.startAssessment();

        assertEquals("ASSESSMENT", response.getMode());
        assertEquals(2, fixture.exerciseBatches.size());
        assertEquals(Long.valueOf(13L), fixture.catalogBatch.getCategoryId());
        assertEquals("入行专属评估", fixture.catalogBatch.getCategoryName());
        assertEquals(Integer.valueOf(1), fixture.catalogBatch.getType());
        assertEquals("assessment", fixture.record.getFieldType());
        verify(fixture.exercisesBatchMapper).insertBatchByExerciseIds(anyLong(), anyLong(), anyList(), anyString(), any(LocalDateTime.class));
        verify(fixture.answerBatchMapper).insertBatchByCatalogBatchId(anyLong(), anyString(), any(LocalDateTime.class));
    }

    @Test
    void submitAnswer_andGetRecordDetail_shouldPersistBatchAnswersWithSourceExerciseMetadata() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubPracticeModeSource();

        AppPracticeStartRespVO startResponse = fixture.start("standard");
        PracticeExercisesAnswerBatchDO selectedAnswer = fixture.answerBatchesForExercise(0).get(1);
        PracticeExercisesAnswerBatchDO correctAnswer = fixture.answerBatchesForExercise(0).get(0);

        fixture.resetSourceMapperInteractions();
        AppPracticeAnswerSubmitReqVO reqVO = new AppPracticeAnswerSubmitReqVO();
        reqVO.setCurrentIndex(0);
        reqVO.setSelectedOptionIds(Collections.singletonList(String.valueOf(selectedAnswer.getId())));
        fixture.submit(startResponse.getSessionId(), reqVO);

        assertEquals(1, fixture.recordDetails.size());
        UserPracticeExercisesRecordDetailDO detail = fixture.recordDetails.get(0);
        assertEquals(fixture.exerciseBatches.get(0).getId(), detail.getExercisesId());
        assertEquals(selectedAnswer.getAnswerCode(), detail.getAnswerCode());
        assertEquals(correctAnswer.getAnswerCode(), detail.getCorrectAnswerCode());
        assertEquals(Boolean.FALSE, detail.getCorrect());
        assertEquals(1, fixture.wrongRecordDetails.size());

        verify(fixture.answerMapper, never()).selectList(any());

        fixture.resetSourceMapperInteractions();
        AppPracticeRecordDetailRespVO recordDetail = fixture.getRecordDetail(startResponse.getRecordId());

        assertEquals(1, recordDetail.getAnswers().size());
        assertEquals(String.valueOf(fixture.exerciseBatches.get(0).getId()), recordDetail.getAnswers().get(0).getQuestionId());
        assertEquals(Collections.singletonList(selectedAnswer.getAnswerCode()), recordDetail.getAnswers().get(0).getSelectedOptionIds());
        assertEquals(Collections.singletonList(correctAnswer.getAnswerCode()), recordDetail.getAnswers().get(0).getCorrectOptionIds());
        assertEquals(selectedAnswer.getAnswerContent(), recordDetail.getAnswers().get(0).getAnswer());
        assertEquals(correctAnswer.getAnswerContent(), recordDetail.getAnswers().get(0).getCorrect());
        assertEquals(Boolean.FALSE, recordDetail.getAnswers().get(0).getCorrectFlag());

        verify(fixture.answerMapper, never()).selectList(any());
    }

    @Test
    void listWrongCountStats_shouldCountWrongQuestionsByBatchCategoryWithoutLegacyExerciseLookup() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubPracticeModeSource();

        AppPracticeStartRespVO startResponse = fixture.start("standard");
        AppPracticeAnswerSubmitReqVO reqVO = new AppPracticeAnswerSubmitReqVO();
        reqVO.setCurrentIndex(0);
        reqVO.setSelectedOptionIds(Collections.singletonList(String.valueOf(fixture.answerBatchesForExercise(0).get(1).getId())));
        fixture.submit(startResponse.getSessionId(), reqVO);

        fixture.resetSourceMapperInteractions();
        @SuppressWarnings("unchecked")
        Map<Long, Integer> wrongCountMap = (Map<Long, Integer>) ReflectionTestUtils.invokeMethod(
                fixture.service, "listWrongCountStats", 9001L);

        assertEquals(Integer.valueOf(1), wrongCountMap.get(2001L));
        verify(fixture.exercisesMapper, never()).selectList(any());
    }

    @Test
    void getAnswerCard_shouldMarkCompletedQuestionsByBatchId() {
        BatchStartFixture fixture = new BatchStartFixture();
        fixture.stubPracticeModeSource();

        AppPracticeStartRespVO startResponse = fixture.start("standard");
        AppPracticeAnswerSubmitReqVO reqVO = new AppPracticeAnswerSubmitReqVO();
        reqVO.setCurrentIndex(0);
        reqVO.setSelectedOptionIds(Collections.singletonList(String.valueOf(fixture.answerBatchesForExercise(0).get(0).getId())));
        fixture.submit(startResponse.getSessionId(), reqVO);
        AppPracticeAnswerCardRespVO answerCard = fixture.getAnswerCard(startResponse.getRecordId());

        assertEquals(Integer.valueOf(3), answerCard.getTotal());
        assertEquals(fixture.catalogBatch.getId(), answerCard.getCatalogBatchId());
        assertEquals(Long.valueOf(fixture.exerciseBatches.get(0).getId()), answerCard.getDetail().get(0).getExercisesBatchId());
        assertEquals(Boolean.TRUE, answerCard.getDetail().get(0).getIsCompleted());
        assertEquals(Boolean.FALSE, answerCard.getDetail().get(1).getIsCompleted());
        assertEquals(Boolean.FALSE, answerCard.getDetail().get(2).getIsCompleted());
    }

    @Test
    void versionSql_shouldDropObsoleteCatalogIdWithoutRestoringRemovedDetailColumns() throws Exception {
        String sql = readVersionFile("20260818170000-ddl-drop_practice_catalog_batch_catalog_id.sql");
        String scriptIndex = readVersionFile("00-脚本索引.md");

        assertTrue(sql.contains("UPDATE yj_practice_catalog_batch"));
        assertTrue(sql.contains("AND type IN (1, 2)"));
        assertTrue(sql.contains("DROP COLUMN catalog_id"));
        assertFalse(sql.contains("exercises_batch_id"));
        assertFalse(sql.contains("answer_batch_id"));
        assertTrue(scriptIndex.contains("20260818170000-ddl-drop_practice_catalog_batch_catalog_id.sql"));
    }

    private static <T> List<T> shuffledCopy(List<T> source, Random random) {
        List<T> copy = new ArrayList<>(source);
        for (int i = copy.size() - 1; i > 0; i--) {
            int index = random.nextInt(i + 1);
            Collections.swap(copy, i, index);
        }
        return copy;
    }

    private static String readVersionFile(String name) throws Exception {
        Path current = Paths.get(System.getProperty("user.dir")).toAbsolutePath();
        while (current != null && !Files.exists(current.resolve(".git"))) {
            current = current.getParent();
        }
        assertNotNull(current);
        Path file = current.resolve(Paths.get(
                "doc", "02-版本迭代", "03-进行中版本", "20260601000000-vphase1-initial-delivery",
                "050-执行脚本", name));
        return new String(Files.readAllBytes(file), StandardCharsets.UTF_8);
    }

    private static final class RandomAdvance {
        private final Random random;

        private RandomAdvance(long seed, int exerciseShuffleCount) {
            this.random = new Random(seed);
            List<Long> consume = Arrays.asList(101L, 102L, 103L);
            for (int iteration = 0; iteration < exerciseShuffleCount; iteration++) {
                for (int i = consume.size() - 1; i > 0; i--) {
                    random.nextInt(i + 1);
                }
            }
        }
    }

    private static final class BatchStartFixture {
        private final FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
        private final FrontPracticeBatchService frontPracticeBatchService = new FrontPracticeBatchService();
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
        private final CustomerAccountMapper customerAccountMapper = mock(CustomerAccountMapper.class);
        private final List<PracticeExercisesBatchDO> exerciseBatches = new ArrayList<>();
        private final List<PracticeExercisesAnswerBatchDO> answerBatches = new ArrayList<>();
        private final List<UserPracticeExercisesRecordDetailDO> recordDetails = new ArrayList<>();
        private final List<UserPracticeExercisesWrongRecordDetailDO> wrongRecordDetails = new ArrayList<>();
        private final Map<Long, PracticeExercisesDO> exerciseStore = new LinkedHashMap<>();
        private final Map<Long, List<PracticeExercisesAnswerDO>> answersByExerciseId = new LinkedHashMap<>();
        private PracticeCatalogBatchDO catalogBatch;
        private UserPracticeExercisesRecordDO record;

        private BatchStartFixture() {
            injectPracticeDependencies(service);
            injectPracticeDependencies(frontPracticeBatchService);
            ReflectionTestUtils.setField(service, "frontPracticeBatchService", frontPracticeBatchService);
            ReflectionTestUtils.setField(frontPracticeBatchService, "theoryExamCategoryId", 10L);
            ReflectionTestUtils.setField(frontPracticeBatchService, "instructorExamCategoryId", 11L);
            ReflectionTestUtils.setField(frontPracticeBatchService, "practiceRandom", new Random(0L));
            stubIds();
        }

        private void setPracticeRandom(Random random) {
            ReflectionTestUtils.setField(frontPracticeBatchService, "practiceRandom", random);
        }

        private void injectPracticeDependencies(Object target) {
            ReflectionTestUtils.setField(target, "practiceCategoryMapper", categoryMapper);
            ReflectionTestUtils.setField(target, "practiceExercisesMapper", exercisesMapper);
            ReflectionTestUtils.setField(target, "practiceExercisesAnswerMapper", answerMapper);
            ReflectionTestUtils.setField(target, "practiceExercisesAnswerChildMapper", answerChildMapper);
            ReflectionTestUtils.setField(target, "practiceCatalogBatchMapper", catalogBatchMapper);
            ReflectionTestUtils.setField(target, "practiceExercisesBatchMapper", exercisesBatchMapper);
            ReflectionTestUtils.setField(target, "practiceExercisesAnswerBatchMapper", answerBatchMapper);
            ReflectionTestUtils.setField(target, "userPracticeExercisesRecordMapper", recordMapper);
            ReflectionTestUtils.setField(target, "userPracticeExercisesRecordDetailMapper", recordDetailMapper);
            ReflectionTestUtils.setField(target, "userPracticeExercisesWrongRecordDetailMapper", wrongRecordDetailMapper);
            if (target instanceof FrontPracticeServiceImpl) {
                ReflectionTestUtils.setField(target, "customerAccountMapper", customerAccountMapper);
            }
        }

        private void stubPracticeModeSource() {
            PracticeCategoryDO category = PracticeCategoryDO.builder()
                    .id(2001L)
                    .categoryName("法规")
                    .fieldType("law")
                    .catalogType(0)
                    .categoryStatus(Boolean.TRUE)
                    .sortNo(1)
                    .build();
            when(categoryMapper.selectList(any())).thenReturn(Collections.singletonList(category));
            when(categoryMapper.selectById(2001L)).thenReturn(category);
            when(exercisesMapper.selectObjs(any())).thenReturn(Arrays.asList(101L, 102L, 103L));
            registerExercises(Arrays.asList(
                    practiceExercise(101L, 2001L, 2, "题目2"),
                    practiceExercise(102L, 2001L, 1, "题目1"),
                    practiceExercise(103L, 2001L, 3, "题目3")));
            when(exercisesMapper.selectMaps(any())).thenReturn(Collections.singletonList(exerciseStatsRow()));
            answersByExerciseId.put(101L, Arrays.asList(answer(11L, 101L, "A", 1, true), answer(12L, 101L, "B", 2, false)));
            answersByExerciseId.put(102L, Arrays.asList(answer(21L, 102L, "A", 1, false), answer(22L, 102L, "B", 2, true)));
            answersByExerciseId.put(103L, Arrays.asList(answer(31L, 103L, "A", 1, true), answer(32L, 103L, "B", 2, false)));
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
                Object wrapper = invocation.getArgument(0);
                String text = String.valueOf(wrapper);
                if (text.contains("101")) {
                    return answersByExerciseId.get(101L);
                }
                if (text.contains("102")) {
                    return answersByExerciseId.get(102L);
                }
                return answersByExerciseId.values().stream()
                        .flatMap(List::stream)
                        .collect(Collectors.toList());
            });
            when(answerChildMapper.selectList(any())).thenReturn(Collections.emptyList());
            CustomerAccountDO account = CustomerAccountDO.builder().id(9001L).build();
            account.setTenantId(8L);
            when(customerAccountMapper.selectById(anyLong())).thenReturn(account);
            when(catalogBatchMapper.selectOne(any())).thenAnswer(invocation -> catalogBatch);
            when(catalogBatchMapper.selectById(anyLong())).thenAnswer(invocation -> catalogBatch);
            when(catalogBatchMapper.selectBatchIds(any())).thenAnswer(invocation -> catalogBatch == null
                    ? Collections.emptyList()
                    : Collections.singletonList(catalogBatch));
            when(catalogBatchMapper.selectLatestByUserCategoryAndMode(anyLong(), anyLong(), anyString()))
                    .thenReturn(null);
            when(exercisesMapper.selectById(anyLong())).thenAnswer(invocation -> exerciseStore.get(invocation.getArgument(0)));
            when(exercisesMapper.selectBatchIds(any())).thenAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                List<Long> ids = new ArrayList<>((java.util.Collection<Long>) invocation.getArgument(0, java.util.Collection.class));
                return ids.stream().map(exerciseStore::get).filter(item -> item != null).collect(Collectors.toList());
            });
            when(exercisesBatchMapper.selectById(anyLong())).thenAnswer(invocation ->
                    exerciseBatches.stream()
                            .filter(batch -> batch.getId().equals(invocation.getArgument(0)))
                            .findFirst()
                            .orElse(null));
            when(exercisesBatchMapper.selectList(any())).thenAnswer(invocation -> exerciseBatches.stream()
                    .sorted(java.util.Comparator.comparing(PracticeExercisesBatchDO::getSortNo))
                    .collect(Collectors.toList()));
            when(exercisesBatchMapper.selectOne(any())).thenAnswer(invocation -> {
                String text = String.valueOf(invocation.getArgument(0, Object.class));
                return exerciseBatches.stream()
                        .filter(batch -> text.contains(String.valueOf(batch.getExercisesId())))
                        .findFirst()
                        .orElse(exerciseBatches.isEmpty() ? null : exerciseBatches.get(0));
            });
            when(exercisesBatchMapper.selectBatchIds(any())).thenAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                List<Long> ids = new ArrayList<>((java.util.Collection<Long>) invocation.getArgument(0, java.util.Collection.class));
                return exerciseBatches.stream()
                        .filter(batch -> ids.contains(batch.getId()))
                        .collect(Collectors.toList());
            });
            when(answerBatchMapper.selectList(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                return answerBatches.stream()
                        .filter(answer -> values.isEmpty() || values.contains(answer.getExercisesBatchId()))
                        .sorted(java.util.Comparator.comparing(PracticeExercisesAnswerBatchDO::getSortNo))
                        .collect(Collectors.toList());
            });
            when(recordMapper.selectById(anyLong())).thenAnswer(invocation -> record != null
                    && record.getId().equals(invocation.getArgument(0)) ? record : null);
            when(recordMapper.selectOne(any())).thenAnswer(invocation -> record);
            when(recordMapper.selectList(any())).thenAnswer(invocation -> record == null
                    ? Collections.emptyList()
                    : Collections.singletonList(record));
            when(recordDetailMapper.selectOne(any())).thenReturn(null);
            when(recordDetailMapper.selectList(any())).thenAnswer(invocation -> new ArrayList<>(recordDetails));
            when(wrongRecordDetailMapper.selectOne(any())).thenReturn(null);
            when(wrongRecordDetailMapper.selectList(any())).thenAnswer(invocation -> new ArrayList<>(wrongRecordDetails));
        }

        private void stubFixedExamSource(Long categoryId, int questionCount, String categoryName) {
            PracticeCategoryDO category = PracticeCategoryDO.builder()
                    .id(categoryId)
                    .categoryName(categoryName)
                    .fieldType("cat-" + categoryId)
                    .catalogType(0)
                    .categoryStatus(Boolean.TRUE)
                    .sortNo(categoryId.intValue())
                    .build();
            when(categoryMapper.selectById(categoryId)).thenReturn(category);
            List<Long> exerciseIds = new ArrayList<>();
            List<PracticeExercisesDO> exercises = new ArrayList<>();
            for (int i = 1; i <= questionCount; i++) {
                long exerciseId = categoryId * 1000 + i;
                exerciseIds.add(exerciseId);
                exercises.add(practiceExercise(exerciseId, categoryId, i, "题目" + exerciseId));
            }
            registerExercises(exercises);
            when(exercisesMapper.selectObjs(any())).thenAnswer(invocation -> exerciseIds);
            stubExerciseLookupByBatchIds();
            when(exercisesMapper.selectMaps(any())).thenReturn(Collections.emptyList());
            for (Long exerciseId : exerciseIds) {
                answersByExerciseId.put(exerciseId, Arrays.asList(
                        answer(exerciseId * 10 + 1, exerciseId, "A", 1, true),
                        answer(exerciseId * 10 + 2, exerciseId, "B", 2, false)));
            }
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
                return answersByExerciseId.values().stream()
                        .flatMap(List::stream)
                        .collect(Collectors.toList());
            });
            when(answerChildMapper.selectList(any())).thenReturn(Collections.emptyList());
            CustomerAccountDO account = CustomerAccountDO.builder().id(9001L).build();
            account.setTenantId(8L);
            when(customerAccountMapper.selectById(anyLong())).thenReturn(account);
            stubGeneratedBatchLookup();
        }

        private void stubAssessmentSource() {
            PracticeCategoryDO category = PracticeCategoryDO.builder()
                    .id(13L)
                    .categoryName("入行专属评估")
                    .fieldType("entry")
                    .catalogType(1)
                    .categoryStatus(Boolean.TRUE)
                    .sortNo(13)
                    .build();
            when(categoryMapper.selectList(any())).thenReturn(Collections.singletonList(category));
            when(categoryMapper.selectById(13L)).thenReturn(category);
            List<Long> exerciseIds = Arrays.asList(13001L, 13002L);
            registerExercises(Arrays.asList(
                    practiceExercise(13001L, 13L, 1, "自测题1"),
                    practiceExercise(13002L, 13L, 2, "自测题2")));
            when(exercisesMapper.selectObjs(any())).thenAnswer(invocation -> exerciseIds);
            stubExerciseLookupByBatchIds();
            when(exercisesMapper.selectMaps(any())).thenReturn(Collections.emptyList());
            answersByExerciseId.put(13001L, Arrays.asList(answer(130011L, 13001L, "A", 1, true), answer(130012L, 13001L, "B", 2, false)));
            answersByExerciseId.put(13002L, Arrays.asList(answer(130021L, 13002L, "A", 1, true), answer(130022L, 13002L, "B", 2, false)));
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
                String text = String.valueOf(invocation.getArgument(0));
                if (text.contains("13002")) {
                    return answersByExerciseId.get(13002L);
                }
                if (text.contains("13001")) {
                    return answersByExerciseId.get(13001L);
                }
                return answersByExerciseId.values().stream()
                        .flatMap(List::stream)
                        .collect(Collectors.toList());
            });
            when(answerChildMapper.selectList(any())).thenReturn(Collections.emptyList());
            CustomerAccountDO account = CustomerAccountDO.builder().id(9001L).build();
            account.setTenantId(8L);
            when(customerAccountMapper.selectById(anyLong())).thenReturn(account);
            stubGeneratedBatchLookup();
        }

        private void stubGeneratedBatchLookup() {
            when(catalogBatchMapper.selectOne(any())).thenAnswer(invocation -> catalogBatch);
            when(catalogBatchMapper.selectById(anyLong())).thenAnswer(invocation -> catalogBatch);
            when(catalogBatchMapper.selectBatchIds(any())).thenAnswer(invocation -> catalogBatch == null
                    ? Collections.emptyList()
                    : Collections.singletonList(catalogBatch));
            when(catalogBatchMapper.selectLatestByUserCategoryAndMode(anyLong(), anyLong(), anyString()))
                    .thenReturn(null);
            when(exercisesBatchMapper.selectById(anyLong())).thenAnswer(invocation ->
                    exerciseBatches.stream()
                            .filter(batch -> batch.getId().equals(invocation.getArgument(0)))
                            .findFirst()
                            .orElse(null));
            when(exercisesBatchMapper.selectList(any())).thenAnswer(invocation -> exerciseBatches.stream()
                    .sorted(java.util.Comparator.comparing(PracticeExercisesBatchDO::getSortNo))
                    .collect(Collectors.toList()));
            when(answerBatchMapper.selectList(any())).thenAnswer(invocation -> {
                List<Long> values = wrapperLongValues(invocation.getArgument(0));
                return answerBatches.stream()
                        .filter(answer -> values.isEmpty() || values.contains(answer.getExercisesBatchId()))
                        .sorted(java.util.Comparator.comparing(PracticeExercisesAnswerBatchDO::getSortNo))
                        .collect(Collectors.toList());
            });
        }

        private void stubComprehensiveExamSource() {
            Map<Long, Integer> quotas = new LinkedHashMap<>();
            quotas.put(1L, 5);
            quotas.put(2L, 13);
            quotas.put(3L, 3);
            quotas.put(4L, 11);
            quotas.put(5L, 7);
            quotas.put(6L, 22);
            quotas.put(7L, 7);
            quotas.put(8L, 6);
            quotas.put(9L, 26);
            List<List<Long>> resultQueue = new ArrayList<>();
            for (Map.Entry<Long, Integer> entry : quotas.entrySet()) {
                long categoryId = entry.getKey();
                int count = entry.getValue() + 2;
                PracticeCategoryDO category = PracticeCategoryDO.builder()
                        .id(categoryId)
                        .categoryName("分类" + categoryId)
                        .fieldType("cat-" + categoryId)
                        .catalogType(0)
                        .categoryStatus(Boolean.TRUE)
                        .sortNo((int) categoryId)
                        .build();
                when(categoryMapper.selectById(categoryId)).thenReturn(category);
                List<Long> ids = new ArrayList<>();
                List<PracticeExercisesDO> exercises = new ArrayList<>();
                for (int i = 1; i <= count; i++) {
                    long exerciseId = categoryId * 1000 + i;
                    ids.add(exerciseId);
                    exercises.add(practiceExercise(exerciseId, categoryId, i, "题目" + exerciseId));
                }
            registerExercises(exercises);
                resultQueue.add(ids);
            }
            java.util.concurrent.atomic.AtomicInteger queueIndex = new java.util.concurrent.atomic.AtomicInteger(0);
            when(exercisesMapper.selectObjs(any())).thenAnswer(invocation ->
                    resultQueue.get(queueIndex.getAndIncrement()));
            stubExerciseLookupByBatchIds();
            when(exercisesMapper.selectMaps(any())).thenReturn(Collections.emptyList());
            for (PracticeExercisesDO exercise : exerciseStore.values()) {
                answersByExerciseId.put(exercise.getId(), Arrays.asList(
                        answer(exercise.getId() * 10 + 1, exercise.getId(), "A", 1, true),
                        answer(exercise.getId() * 10 + 2, exercise.getId(), "B", 2, false)));
            }
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
                return answersByExerciseId.values().stream()
                        .flatMap(List::stream)
                        .collect(Collectors.toList());
            });
            when(answerChildMapper.selectList(any())).thenReturn(Collections.emptyList());
            CustomerAccountDO account = CustomerAccountDO.builder().id(9001L).build();
            account.setTenantId(8L);
            when(customerAccountMapper.selectById(anyLong())).thenReturn(account);
            stubGeneratedBatchLookup();
        }

        private void stubExerciseLookupByBatchIds() {
            when(exercisesMapper.selectBatchIds(any())).thenAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                java.util.Collection<Long> ids = invocation.getArgument(0, java.util.Collection.class);
                if (ids == null) {
                    return Collections.emptyList();
                }
                return ids.stream().map(exerciseStore::get)
                        .filter(java.util.Objects::nonNull)
                        .collect(Collectors.toList());
            });
        }

        private AppPracticeStartRespVO start(String mode) {
            return withLogin(() -> service.startPractice("uav-basic-001", "law", mode));
        }

        private AppPracticeStartRespVO startTheoryExam() {
            return withLogin(() -> service.startTheoryExam("uav-basic-001"));
        }

        private AppPracticeStartRespVO startComprehensiveExam() {
            return withLogin(() -> service.startComprehensiveExam("uav-basic-001"));
        }

        private AppPracticeStartRespVO startInstructorExam() {
            return withLogin(() -> service.startInstructorExam("uav-basic-001"));
        }

        private AppPracticeStartRespVO startAssessment() {
            return withLogin(() -> service.startPractice("uav-basic-001", "assessment", "assessment"));
        }

        private void submit(String sessionId, AppPracticeAnswerSubmitReqVO reqVO) {
            withLogin(() -> service.submitAnswer("uav-basic-001", sessionId, reqVO));
        }

        private AppPracticeRecordDetailRespVO getRecordDetail(String recordId) {
            return withLogin(() -> service.getRecordDetail(recordId));
        }

        private List<AppPracticeTopicRespVO> getCurrentPractice(String topicId) {
            return withLogin(() -> service.getCurrentPractice(topicId, "standard"));
        }

        private AppPracticeAnswerCardRespVO getAnswerCard(String recordId) {
            return withLogin(() -> service.getAnswerCard(recordId));
        }

        private void resetSourceMapperInteractions() {
            clearInvocations(exercisesMapper, answerMapper);
        }

        private List<PracticeExercisesAnswerBatchDO> answerBatchesForExercise(int exerciseIndex) {
            Long exercisesBatchId = exerciseBatches.get(exerciseIndex).getId();
            return answerBatches.stream()
                    .filter(answer -> exercisesBatchId.equals(answer.getExercisesBatchId()))
                    .sorted(java.util.Comparator.comparing(PracticeExercisesAnswerBatchDO::getSortNo))
                    .collect(Collectors.toList());
        }

        private Map<String, Object> exerciseStatsRow() {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("category_id", 2001L);
            row.put("question_count", 3);
            row.put("total_score", 6);
            return row;
        }

        private void registerExercises(List<PracticeExercisesDO> exercises) {
            for (PracticeExercisesDO exercise : exercises) {
                exerciseStore.put(exercise.getId(), exercise);
            }
        }

        private <T> T withLogin(Supplier<T> supplier) {
            LoginUser loginUser = new LoginUser();
            loginUser.setId(9001L);
            loginUser.setTenantId(8L);
            try (MockedStatic<com.huiyitech.framework.security.AppMobileAuthUtils> authMock =
                         mockStatic(com.huiyitech.framework.security.AppMobileAuthUtils.class)) {
                authMock.when(com.huiyitech.framework.security.AppMobileAuthUtils::requireStudentLoginUser)
                        .thenReturn(loginUser);
                return supplier.get();
            }
        }

        private void stubIds() {
            AtomicLong catalogId = new AtomicLong(5000L);
            AtomicLong exerciseId = new AtomicLong(6000L);
            AtomicLong answerId = new AtomicLong(7000L);
            AtomicLong recordId = new AtomicLong(8000L);
            AtomicLong recordDetailId = new AtomicLong(9000L);
            AtomicLong wrongRecordId = new AtomicLong(9500L);
            doAnswer(invocation -> {
                catalogBatch = invocation.getArgument(0);
                catalogBatch.setId(catalogId.incrementAndGet());
                return 1;
            }).when(catalogBatchMapper).insert(any(PracticeCatalogBatchDO.class));
            doAnswer(invocation -> {
                PracticeExercisesBatchDO batch = invocation.getArgument(0);
                batch.setId(exerciseId.incrementAndGet());
                exerciseBatches.add(batch);
                return 1;
            }).when(exercisesBatchMapper).insert(any(PracticeExercisesBatchDO.class));
            doAnswer(invocation -> {
                Long customerAccountId = invocation.getArgument(0);
                Long catalogBatchId = invocation.getArgument(1);
                @SuppressWarnings("unchecked")
                List<Long> exerciseIds = invocation.getArgument(2, List.class);
                for (int index = 0; index < exerciseIds.size(); index++) {
                    PracticeExercisesBatchDO batch = PracticeExercisesBatchDO.builder()
                            .id(exerciseId.incrementAndGet())
                            .customerAccountId(customerAccountId)
                            .catalogBatchId(catalogBatchId)
                            .exercisesId(exerciseIds.get(index))
                            .sortNo(index + 1)
                            .build();
                    exerciseBatches.add(batch);
                }
                return exerciseIds.size();
            }).when(exercisesBatchMapper).insertBatchByExerciseIds(anyLong(), anyLong(), anyList(), anyString(), any(LocalDateTime.class));
            doAnswer(invocation -> {
                PracticeExercisesAnswerBatchDO batch = invocation.getArgument(0);
                batch.setId(answerId.incrementAndGet());
                answerBatches.add(batch);
                return 1;
            }).when(answerBatchMapper).insert(any(PracticeExercisesAnswerBatchDO.class));
            doAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                List<PracticeExercisesAnswerBatchDO> batches = invocation.getArgument(0, List.class);
                for (PracticeExercisesAnswerBatchDO batch : batches) {
                    batch.setId(answerId.incrementAndGet());
                    answerBatches.add(batch);
                }
                return batches == null ? 0 : batches.size();
            }).when(answerBatchMapper).insertBatch(anyList(), anyString(), any(LocalDateTime.class));
            doAnswer(invocation -> {
                Long catalogBatchId = invocation.getArgument(0);
                int inserted = 0;
                List<PracticeExercisesBatchDO> matchedBatches = exerciseBatches.stream()
                        .filter(batch -> batch.getCatalogBatchId().equals(catalogBatchId))
                        .sorted(java.util.Comparator.comparing(PracticeExercisesBatchDO::getSortNo))
                        .collect(Collectors.toList());
                for (PracticeExercisesBatchDO batch : matchedBatches) {
                    List<PracticeExercisesAnswerDO> answers = answersByExerciseId.getOrDefault(
                            batch.getExercisesId(), Collections.emptyList());
                    for (int answerIndex = 0; answerIndex < answers.size(); answerIndex++) {
                        PracticeExercisesAnswerDO answer = answers.get(answerIndex);
                        PracticeExercisesAnswerBatchDO answerBatch = PracticeExercisesAnswerBatchDO.builder()
                                .id(answerId.incrementAndGet())
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
            }).when(answerBatchMapper).insertBatchByCatalogBatchId(anyLong(), anyString(), any(LocalDateTime.class));
            doAnswer(invocation -> {
                record = invocation.getArgument(0);
                record.setId(recordId.incrementAndGet());
                return 1;
            }).when(recordMapper).insert(any(UserPracticeExercisesRecordDO.class));
            doAnswer(invocation -> {
                UserPracticeExercisesRecordDO update = invocation.getArgument(0);
                record = update;
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
                recordDetails.removeIf(detail -> detail.getId().equals(update.getId()));
                recordDetails.add(update);
                return 1;
            }).when(recordDetailMapper).updateById(any(UserPracticeExercisesRecordDetailDO.class));
            doAnswer(invocation -> {
                UserPracticeExercisesWrongRecordDetailDO wrong = invocation.getArgument(0);
                wrong.setId(wrongRecordId.incrementAndGet());
                wrongRecordDetails.add(wrong);
                return 1;
            }).when(wrongRecordDetailMapper).insert(any(UserPracticeExercisesWrongRecordDetailDO.class));
            doAnswer(invocation -> {
                UserPracticeExercisesWrongRecordDetailDO update = invocation.getArgument(0);
                wrongRecordDetails.removeIf(detail -> detail.getId().equals(update.getId()));
                wrongRecordDetails.add(update);
                return 1;
            }).when(wrongRecordDetailMapper).updateById(any(UserPracticeExercisesWrongRecordDetailDO.class));
            doAnswer(invocation -> {
                Long customerAccountId = invocation.getArgument(0);
                Long exercisesId = invocation.getArgument(1);
                wrongRecordDetails.removeIf(detail -> customerAccountId != null
                        && customerAccountId.equals(detail.getCustomerAccountId())
                        && exercisesId != null
                        && exercisesId.equals(detail.getExercisesId()));
                return 1;
            }).when(wrongRecordDetailMapper).deleteByCustomerAccountIdAndExercisesId(anyLong(), anyLong());
        }

        private PracticeExercisesDO practiceExercise(Long id, Long categoryId, Integer sortNo, String stem) {
            return PracticeExercisesDO.builder()
                    .id(id)
                    .categoryId(categoryId)
                    .stepId(categoryId)
                    .questionStem(stem)
                    .questionType("single_choice")
                    .questionStatus(Boolean.TRUE)
                    .score(2)
                    .sortNo(sortNo)
                    .correctMemo("解析")
                    .build();
        }

        private PracticeExercisesAnswerDO answer(Long id, Long exerciseId, String code, Integer sortNo, boolean correct) {
            return PracticeExercisesAnswerDO.builder()
                    .id(id)
                    .exercisesId(exerciseId)
                    .questionType("single_choice")
                    .answerCode(code)
                    .answerContent("选项" + code)
                    .correct(correct)
                    .sortNo(sortNo)
                    .build();
        }

        private List<Long> wrapperLongValues(Object wrapper) {
            List<Long> values = new ArrayList<>();
            if (wrapper instanceof AbstractWrapper) {
                ((AbstractWrapper<?, ?, ?>) wrapper).getParamNameValuePairs().values()
                        .forEach(value -> {
                            if (value instanceof Number) {
                                values.add(((Number) value).longValue());
                                return;
                            }
                            if (value instanceof java.util.Collection) {
                                ((java.util.Collection<?>) value).forEach(item -> {
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
