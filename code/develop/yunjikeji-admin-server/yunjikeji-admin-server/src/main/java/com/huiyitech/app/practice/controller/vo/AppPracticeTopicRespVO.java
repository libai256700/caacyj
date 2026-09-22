package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "APP Practice - Topic Response VO")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeTopicRespVO {

    @Schema(description = "Topic id", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private String id;

    @Schema(description = "Display index", requiredMode = Schema.RequiredMode.REQUIRED, example = "01")
    private String index;

    @Schema(description = "Topic title", requiredMode = Schema.RequiredMode.REQUIRED, example = "Overview")
    private String title;

    @Schema(description = "Category name", requiredMode = Schema.RequiredMode.REQUIRED, example = "Overview")
    private String categoryName;

    @Schema(description = "Field type", example = "overview")
    private String fieldType;

    @Schema(description = "Sort number", example = "1")
    private Integer sortNo;

    @Schema(description = "Category status", requiredMode = Schema.RequiredMode.REQUIRED, example = "true")
    private Boolean categoryStatus;

    @Schema(description = "Question count", requiredMode = Schema.RequiredMode.REQUIRED, example = "100")
    private Integer questionCount;

    @Schema(description = "Total score", requiredMode = Schema.RequiredMode.REQUIRED, example = "100")
    private Integer totalScore;

    @Schema(description = "Wrong question count", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    private Integer wrongQuestionCount;
}
