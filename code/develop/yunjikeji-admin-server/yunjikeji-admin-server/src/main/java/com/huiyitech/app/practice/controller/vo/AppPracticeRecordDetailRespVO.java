package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Schema(description = "APP practice record detail")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeRecordDetailRespVO {

    @Schema(description = "Record id", example = "1")
    private String id;

    @Schema(description = "Record title", example = "入行专属评估")
    private String title;

    @Schema(description = "Category filter value", example = "13")
    private String category;

    @Schema(description = "Category name", example = "入行专属评估")
    private String categoryName;

    @Schema(description = "Total score", example = "100")
    private Integer totalScore;

    @Schema(description = "Score", example = "86")
    private Integer score;

    @Schema(description = "Correct count", example = "23")
    private Integer correctCount;

    @Schema(description = "Wrong count", example = "2")
    private Integer wrongCount;

    @Schema(description = "Practice time", example = "2026-06-11 16:40")
    private String practicedAt;

    @Schema(description = "Assessment completion time", example = "2026-06-11 16:40:32")
    private String assessmentTime;

    @Schema(description = "Assessment report status", example = "SUCCESS")
    private String assessmentReportStatus;

    @Schema(description = "Assessment report failure reason")
    private String assessmentReportFailureReason;

    @Schema(description = "AI self assessment report")
    private String selfReportContent;

    @Schema(description = "Related practice step name", example = "基础认知")
    private String stepName;

    @Schema(description = "Related practice step status", example = "true")
    private Boolean stepStatus;

    @Schema(description = "Answer details")
    private List<AppPracticeRecordAnswerRespVO> answers;
}
