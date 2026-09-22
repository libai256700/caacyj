package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Schema(description = "APP practice catalog batch detail response")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeCatalogBatchDetailRespVO {

    @Schema(description = "Practice id", example = "uav-basic-001")
    private String practiceId;

    @Schema(description = "Catalog batch id", example = "5001")
    private Long catalogBatchId;

    @Schema(description = "Record id", example = "6001")
    private Long recordId;

    @Schema(description = "Session id", example = "uav-basic-001-PRACTICE-1755495000")
    private String sessionId;

    @Schema(description = "Batch type", example = "1")
    private Integer type;

    @Schema(description = "Category id", example = "10")
    private Long categoryId;

    @Schema(description = "Category name", example = "法规")
    private String categoryName;

    @Schema(description = "Total question count", example = "100")
    private Integer total;

    @Schema(description = "Exam time limit in minutes", example = "45")
    private Integer timeLimitMinutes;

    @Schema(description = "Remaining exam time in seconds", example = "1800")
    private Long remainingSeconds;

    @Schema(description = "Whether the batch is completed", example = "false")
    private Boolean completed;

    @Schema(description = "Whether the batch is pending submit", example = "false")
    private Boolean pendingSubmit;

    @Schema(description = "Resume question index", example = "4")
    private Integer resumeQuestionIndex;

    @Schema(description = "Next page", example = "/pages/practice/answer")
    private String nextPage;

    @Schema(description = "Question type statistics")
    private List<QuestionTypeStatItem> questionTypeStats;

    @Schema(description = "Question type statistic item")
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class QuestionTypeStatItem {

        @Schema(description = "Question type code", example = "single_choice")
        private String questionType;

        @Schema(description = "Question type display name", example = "单选题")
        private String label;

        @Schema(description = "Question count", example = "10")
        private Integer count;
    }
}
