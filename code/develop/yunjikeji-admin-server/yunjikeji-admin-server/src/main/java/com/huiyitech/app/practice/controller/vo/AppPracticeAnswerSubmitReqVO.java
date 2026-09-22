package com.huiyitech.app.practice.controller.vo;

import lombok.Data;

import java.util.List;

@Data
public class AppPracticeAnswerSubmitReqVO {

    private String questionId;

    private String selectedOptionId;

    private List<String> selectedOptionIds;

    private Integer currentIndex;
}
