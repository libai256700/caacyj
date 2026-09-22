package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Schema(description = "APP practice record answer detail")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeRecordAnswerRespVO {

    @Schema(description = "Question order", example = "1")
    private Integer no;

    @Schema(description = "Question id", example = "1001")
    private String questionId;

    @Schema(description = "Question type", example = "单选题")
    private String type;

    @Schema(description = "Question stem", example = "飞行前检查电源系统时，最应优先确认哪一项？")
    private String question;

    @Schema(description = "Selected option ids")
    private List<String> selectedOptionIds;

    @Schema(description = "Selected answer content", example = "电池电量")
    private String answer;

    @Schema(description = "Correct option ids")
    private List<String> correctOptionIds;

    @Schema(description = "Correct answer content", example = "电池电量")
    private String correct;

    @Schema(description = "Whether the answer is correct", example = "true")
    private Boolean correctFlag;

    @Schema(description = "Question explanation", example = "暂无标准解析。")
    private String explanation;

    @Schema(description = "Practice step name", example = "基础认知")
    private String stepName;

    @Schema(description = "Practice step status", example = "true")
    private Boolean stepStatus;
}
