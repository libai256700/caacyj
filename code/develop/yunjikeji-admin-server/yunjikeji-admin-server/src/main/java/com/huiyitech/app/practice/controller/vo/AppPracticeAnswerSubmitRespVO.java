package com.huiyitech.app.practice.controller.vo;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeAnswerSubmitRespVO {

    private String questionId;

    private String selectedOptionId;

    private List<String> selectedOptionIds;

    private String correctOptionId;

    private List<String> correctOptionIds;

    private Boolean correct;

    private String explanation;

    private Integer currentIndex;

    private Integer nextQuestionIndex;

    private Integer totalQuestions;

    private Integer answeredCount;

    private Integer correctCount;

    private Integer progressPercent;

    private Boolean completed;

    private String recordId;

    private String assessmentLevel;

    private String assessmentSummary;

    private String assessmentSuggestion;

    private String recommendDirection;

    private List<String> weakPoints;

    private String assessmentReportContent;

    private String assessmentReportStatus;

    private String assessmentReportFailureReason;

    /**
     * Identifies which assessment flow produced this report. Existing self-assessment
     * clients may ignore this additive field.
     */
    private String reportType;
}
