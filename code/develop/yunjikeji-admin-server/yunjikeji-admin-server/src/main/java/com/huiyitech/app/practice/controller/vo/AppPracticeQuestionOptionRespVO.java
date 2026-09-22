package com.huiyitech.app.practice.controller.vo;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeQuestionOptionRespVO {

    private String id;

    private String label;

    private String content;
}
