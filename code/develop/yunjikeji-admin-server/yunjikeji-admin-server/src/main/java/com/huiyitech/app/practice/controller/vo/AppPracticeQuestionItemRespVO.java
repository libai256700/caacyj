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
public class AppPracticeQuestionItemRespVO {

    private String id;

    private Long exerciseId;

    private Boolean videoAvailable;

    private String videoUrl;

    private Long videoExpiresAt;

    private String type;

    private String title;

    private String stem;

    private Integer score;

    private Boolean isRequired;

    private String stepName;

    private Boolean stepStatus;

    private List<AppPracticeQuestionOptionRespVO> options;
}
