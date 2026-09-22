package com.huiyitech.app.practice.service;

import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitReqVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeCatalogBatchDetailRespVO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCatalogBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesDO;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.function.Function;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

final class FrontPracticeBatchUtils {

    private FrontPracticeBatchUtils() {
    }

    static Map<Long, Integer> buildComprehensiveExamCategoryQuotas() {
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
        return Collections.unmodifiableMap(quotas);
    }

    static Map<String, String> buildTopicCategoryCodeMap() {
        Map<String, String> map = new LinkedHashMap<>();
        map.put("overview", "overview");
        map.put("system", "system_components");
        map.put("traffic", "air_traffic_control");
        map.put("manual", "flight_manual_and_regulations");
        map.put("law", "flight_manual_and_regulations");
        map.put("attention", "operation_precautions");
        map.put("weather", "meteorology");
        map.put("rotor", "rotary_uav");
        map.put("planning", "mission_planning");
        map.put("performance", "flight_principles_and_performance");
        map.put("qa", "comprehensive_qa");
        return map;
    }

    static <T> void shuffleInPlace(List<T> values, Random random) {
        for (int i = values.size() - 1; i > 0; i--) {
            int index = random.nextInt(i + 1);
            Collections.swap(values, i, index);
        }
    }

    static List<Long> pickRandomExerciseIds(Long categoryId, int expectedCount, String displayName,
                                            Function<Long, List<Long>> exerciseIdLoader, Random random) {
        List<Long> exerciseIds = new ArrayList<>(exerciseIdLoader.apply(categoryId));
        if (exerciseIds.size() < expectedCount) {
            throw invalidParamException("{}题量不足，至少需要{}道题，当前仅{}道", displayName, expectedCount, exerciseIds.size());
        }
        shuffleInPlace(exerciseIds, random);
        return new ArrayList<>(exerciseIds.subList(0, expectedCount));
    }

    static List<Long> pickComprehensiveExamExerciseIds(Map<Long, Integer> quotas,
                                                       Function<Long, List<Long>> exerciseIdLoader,
                                                       Random random) {
        List<Long> selectedExerciseIds = new ArrayList<>();
        for (Map.Entry<Long, Integer> entry : quotas.entrySet()) {
            List<Long> categoryExerciseIds = new ArrayList<>(exerciseIdLoader.apply(entry.getKey()));
            if (categoryExerciseIds.size() < entry.getValue()) {
                throw invalidParamException("综合考试题量不足，分类{}需要{}道题，当前仅{}道",
                        entry.getKey(), entry.getValue(), categoryExerciseIds.size());
            }
            shuffleInPlace(categoryExerciseIds, random);
            selectedExerciseIds.addAll(categoryExerciseIds.subList(0, entry.getValue()));
        }
        shuffleInPlace(selectedExerciseIds, random);
        return selectedExerciseIds;
    }

    static int normalizeIndex(Integer index, int totalQuestions) {
        if (totalQuestions <= 0) {
            return 0;
        }
        if (index == null || index < 0) {
            return 0;
        }
        return Math.min(index, totalQuestions - 1);
    }

    static int progressPercent(int answeredCount, int totalQuestions) {
        if (totalQuestions <= 0) {
            return 0;
        }
        return Math.min(100, answeredCount * 100 / totalQuestions);
    }

    static int nextIndex(PracticeRuntimeSession session, int currentIndex) {
        for (int i = currentIndex + 1; i < session.exerciseBatchIds.size(); i++) {
            if (!session.answeredIndexes.contains(i)) {
                return i;
            }
        }
        for (int i = 0; i < session.exerciseBatchIds.size(); i++) {
            if (!session.answeredIndexes.contains(i)) {
                return i;
            }
        }
        return currentIndex;
    }

    static boolean sameOptions(List<String> selectedOptionIds, List<String> correctOptionIds) {
        return new LinkedHashSet<>(selectedOptionIds).equals(new LinkedHashSet<>(correctOptionIds));
    }

    static List<String> normalizeSelectedOptionIds(AppPracticeAnswerSubmitReqVO reqVO) {
        if (reqVO == null) {
            return Collections.emptyList();
        }
        List<String> selectedOptionIds = reqVO.getSelectedOptionIds();
        if (selectedOptionIds != null && !selectedOptionIds.isEmpty()) {
            return selectedOptionIds.stream()
                    .filter(StringUtils::hasText)
                    .map(String::trim)
                    .distinct()
                    .collect(Collectors.toList());
        }
        return splitOptionIds(reqVO.getSelectedOptionId());
    }

    static List<String> resolveOptionCodes(List<OptionSnapshot> options, List<String> optionIds) {
        if (optionIds == null || optionIds.isEmpty()) {
            return Collections.emptyList();
        }
        Map<String, String> optionCodeMap = options.stream()
                .collect(Collectors.toMap(OptionSnapshot::getId, OptionSnapshot::getLabel, (left, right) -> left, LinkedHashMap::new));
        return optionIds.stream()
                .map(optionId -> optionCodeMap.getOrDefault(optionId, optionId))
                .filter(StringUtils::hasText)
                .collect(Collectors.toList());
    }

    static List<String> singletonTextAnswer(String value) {
        return StringUtils.hasText(value) ? Collections.singletonList(value.trim()) : Collections.emptyList();
    }

    static String textAnswerContent(String value) {
        return StringUtils.hasText(value) ? value.trim() : "";
    }

    static String textCorrectContent(String explanation) {
        return "暂无标准答案。".equals(explanation) || "暂无标准解析。".equals(explanation)
                ? "暂无标准答案"
                : explanation;
    }

    static List<String> splitOptionIds(String value) {
        if (!StringUtils.hasText(value)) {
            return Collections.emptyList();
        }
        return java.util.Arrays.stream(value.split(","))
                .map(String::trim)
                .filter(StringUtils::hasText)
                .distinct()
                .collect(Collectors.toList());
    }

    static String optionContents(List<OptionSnapshot> options, List<String> optionIds) {
        if (optionIds == null || optionIds.isEmpty()) {
            return "";
        }
        Map<String, String> optionContentMap = new LinkedHashMap<>();
        for (OptionSnapshot option : options) {
            optionContentMap.put(option.getId(), option.getContent());
            optionContentMap.put(option.getLabel(), option.getContent());
        }
        return optionIds.stream()
                .map(optionId -> optionContentMap.getOrDefault(optionId, optionId))
                .filter(StringUtils::hasText)
                .collect(Collectors.joining("、"));
    }

    static boolean isTextQuestion(String questionType) {
        return "text".equals(questionType)
                || "text_question".equals(questionType)
                || "input".equals(questionType)
                || "文本题".equals(questionType);
    }

    static String toDisplayQuestionType(String questionType) {
        if (isTextQuestion(questionType)) {
            return "文本题";
        }
        if ("multiple_choice".equals(questionType)) {
            return "多选题";
        }
        if ("judge".equals(questionType)) {
            return "判断题";
        }
        return "单选题";
    }

    static Long normalizeCategoryId(Long categoryId) {
        return categoryId;
    }

    static String toCategoryCode(String topicId, Map<String, String> topicCategoryCodeMap) {
        String key = topicId == null ? "" : topicId.trim();
        return topicCategoryCodeMap.getOrDefault(key, key);
    }

    static String normalizePracticeId(String practiceId, String defaultPracticeId) {
        return StringUtils.hasText(practiceId) ? practiceId.trim() : defaultPracticeId;
    }

    static String requireTopicId(String topicId) {
        if (!StringUtils.hasText(topicId)) {
            throw invalidParamException("topicId不能为空");
        }
        return topicId.trim();
    }

    static String buildAnswerCode(int index) {
        int normalizedIndex = index + 1;
        StringBuilder builder = new StringBuilder();
        while (normalizedIndex > 0) {
            int remainder = (normalizedIndex - 1) % 26;
            builder.insert(0, (char) ('A' + remainder));
            normalizedIndex = (normalizedIndex - 1) / 26;
        }
        return builder.toString();
    }

    static String resolveSessionId(PracticeCatalogBatchDO batch, String defaultPracticeId) {
        if (StringUtils.hasText(batch.getSessionId())) {
            return batch.getSessionId();
        }
        if (StringUtils.hasText(batch.getBatchNo())) {
            return batch.getBatchNo();
        }
        return defaultPracticeId + "-" + batch.getId();
    }

    static List<AppPracticeCatalogBatchDetailRespVO.QuestionTypeStatItem> buildQuestionTypeStats(
            List<PracticeExercisesBatchDO> exerciseBatches, Map<Long, PracticeExercisesDO> exerciseMap) {
        Map<String, Integer> stats = new LinkedHashMap<>();
        for (PracticeExercisesBatchDO batch : exerciseBatches) {
            PracticeExercisesDO exercise = exerciseMap.get(batch.getExercisesId());
            String questionType = exercise == null ? "single_choice" : exercise.getQuestionType();
            stats.merge(questionType, 1, Integer::sum);
        }
        return stats.entrySet().stream()
                .map(entry -> AppPracticeCatalogBatchDetailRespVO.QuestionTypeStatItem.builder()
                        .questionType(entry.getKey())
                        .label(toDisplayQuestionType(entry.getKey()))
                        .count(entry.getValue())
                        .build())
                .collect(Collectors.toList());
    }
}
