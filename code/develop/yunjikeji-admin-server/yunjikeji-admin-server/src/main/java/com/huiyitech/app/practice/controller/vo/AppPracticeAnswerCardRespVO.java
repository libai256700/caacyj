package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Schema(description = "APP practice answer card response")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeAnswerCardRespVO {

    @Schema(description = "Total question count", requiredMode = Schema.RequiredMode.REQUIRED, example = "100")
    private Integer total;

    @Schema(description = "Catalog batch id", requiredMode = Schema.RequiredMode.REQUIRED, example = "5001")
    private Long catalogBatchId;

    @Schema(description = "Answer card detail list", requiredMode = Schema.RequiredMode.REQUIRED)
    private List<AnswerCardDetailItem> detail;

    @Schema(description = "APP practice answer card detail item")
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class AnswerCardDetailItem {

        @Schema(description = "Exercise batch id", requiredMode = Schema.RequiredMode.REQUIRED, example = "6001")
        private Long exercisesBatchId;

        @Schema(description = "Whether the question has been completed", requiredMode = Schema.RequiredMode.REQUIRED)
        private Boolean isCompleted;

        @Schema(description = "Question sort number", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
        private Integer sortNo;
    }
}
