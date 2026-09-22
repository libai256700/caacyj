package com.huiyitech.app.practice.service;

import com.huiyitech.practice.dal.dataobject.practice.PracticeCategoryDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesDO;
import lombok.Builder;
import lombok.Data;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Builder
final class BatchStartPlan {
    final String mode;
    final Integer type;
    final PracticeCategoryDO category;
    final CategoryReference categoryReference;
    final List<Long> exerciseIds;
    final boolean shuffleQuestions;
    final boolean shuffleAnswers;
}

@Builder
final class CategoryReference {
    final Long categoryId;
    final String categoryName;
    final String fieldType;
}

final class PracticeRuntimeSession {
    final Long userId;
    final String practiceId;
    final String mode;
    final List<Long> exerciseBatchIds;
    final Map<Long, PracticeExercisesDO> exerciseCache = new ConcurrentHashMap<>();
    final Map<Long, List<OptionSnapshot>> optionSnapshotsByBatchId = new ConcurrentHashMap<>();
    final Set<Integer> answeredIndexes = new LinkedHashSet<>();
    final Map<Integer, AnswerSnapshot> answerSnapshots = new LinkedHashMap<>();
    Long recordId;
    Long catalogBatchId;
    Long recordCategoryId;
    Long assessmentCategoryId;
    int answeredCount;
    int correctCount;

    PracticeRuntimeSession(Long userId, String practiceId, String mode, List<Long> exerciseBatchIds) {
        this.userId = userId;
        this.practiceId = practiceId;
        this.mode = mode;
        this.exerciseBatchIds = exerciseBatchIds;
    }

    void answer(int index, Long exercisesBatchId, Long exercisesId, PracticeExercisesDO exercise,
                List<String> selectedAnswerCodes, List<String> correctAnswerCodes, boolean correct) {
        AnswerSnapshot previous = answerSnapshots.put(index, new AnswerSnapshot(index, exercisesBatchId, exercisesId,
                exercise, selectedAnswerCodes, correctAnswerCodes, correct));
        answeredIndexes.add(index);
        if (previous != null && previous.correct) {
            correctCount--;
        }
        if (correct) {
            correctCount++;
        }
        answeredCount = answeredIndexes.size();
    }
}

final class AnswerSnapshot {
    final int questionIndex;
    final Long exercisesBatchId;
    final Long exercisesId;
    final PracticeExercisesDO exercise;
    final List<String> selectedAnswerCodes;
    final List<String> correctAnswerCodes;
    final boolean correct;

    AnswerSnapshot(int questionIndex, Long exercisesBatchId, Long exercisesId, PracticeExercisesDO exercise,
                   List<String> selectedAnswerCodes, List<String> correctAnswerCodes, boolean correct) {
        this.questionIndex = questionIndex;
        this.exercisesBatchId = exercisesBatchId;
        this.exercisesId = exercisesId;
        this.exercise = exercise;
        this.selectedAnswerCodes = selectedAnswerCodes;
        this.correctAnswerCodes = correctAnswerCodes;
        this.correct = correct;
    }

    int getQuestionIndex() {
        return questionIndex;
    }

    boolean isCorrect() {
        return correct;
    }

    PracticeExercisesDO getExercise() {
        return exercise;
    }
}

@Data
@Builder
final class OptionSnapshot {
    private String id;
    private String label;
    private String content;
    private boolean correct;
}
