package com.huiyitech.app.practice.controller.vo;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeQuestionRespVO {

    private String practiceId;

    private String sessionId;

    private String mode;

    private Integer currentIndex;

    private Integer totalQuestions;

    private Integer answeredCount;

    private Integer correctCount;

    private Integer progressPercent;

    private AppPracticeQuestionItemRespVO question;
}
