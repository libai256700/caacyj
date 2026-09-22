package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "APP assessment result entry status")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppAssessmentResultStatusRespVO {

    @Schema(description = "Latest assessment catalog batch id", example = "107")
    private String catalogBatchId;

    @Schema(description = "Related record id", example = "455")
    private String recordId;

    @Schema(description = "Latest assessment completed", example = "false")
    private Boolean completed;

    @Schema(description = "Assessment answer save status: 0 not started, 1 saving, 2 finished", example = "1")
    private Integer batchSaveStatus;
}
