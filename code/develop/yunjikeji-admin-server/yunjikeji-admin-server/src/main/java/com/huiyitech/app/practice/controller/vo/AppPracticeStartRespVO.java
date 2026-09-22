package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "APP Practice - Start Response VO")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeStartRespVO {

    @Schema(description = "Practice id", requiredMode = Schema.RequiredMode.REQUIRED, example = "uav-basic-001")
    private String practiceId;

    @Schema(description = "Session id", requiredMode = Schema.RequiredMode.REQUIRED)
    private String sessionId;

    @Schema(description = "Batch id", requiredMode = Schema.RequiredMode.REQUIRED)
    private String batchId;

    @Schema(description = "Catalog batch id", requiredMode = Schema.RequiredMode.REQUIRED)
    private String catalogBatchId;

    @Schema(description = "Record id", requiredMode = Schema.RequiredMode.REQUIRED)
    private String recordId;

    @Schema(description = "首个待答题目的零基序号", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    private Integer resumeQuestionIndex;

    @Schema(description = "是否处于待提交状态", requiredMode = Schema.RequiredMode.REQUIRED, example = "false")
    private Boolean pendingSubmit;

    @Schema(description = "Practice mode", requiredMode = Schema.RequiredMode.REQUIRED, example = "standard")
    private String mode;

    @Schema(description = "Next page", requiredMode = Schema.RequiredMode.REQUIRED, example = "/pages/practice/answer")
    private String nextPage;
}
