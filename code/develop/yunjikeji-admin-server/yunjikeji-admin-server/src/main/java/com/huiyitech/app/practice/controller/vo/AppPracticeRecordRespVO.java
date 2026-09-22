package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "APP practice record")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeRecordRespVO {

    @Schema(description = "Record id", example = "1")
    private String id;

    @Schema(description = "Record title", example = "无人机理论练习")
    private String title;

    @Schema(description = "Category filter value", example = "overview")
    private String category;

    @Schema(description = "Category name", example = "概述")
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

    @Schema(description = "Time filter range", example = "today")
    private String timeRange;
}
