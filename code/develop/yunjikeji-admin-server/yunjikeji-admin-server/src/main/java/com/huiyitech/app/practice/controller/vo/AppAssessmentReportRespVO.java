package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "APP assessment report")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppAssessmentReportRespVO {

    @Schema(description = "Record id", example = "1")
    private String id;

    @Schema(description = "Assessment completion time", example = "2026-06-11 16:40:32")
    private String assessmentTime;

    @Schema(description = "Assessment report status", example = "SUCCESS")
    private String assessmentReportStatus;

    @Schema(description = "Assessment report failure reason")
    private String assessmentReportFailureReason;

    @Schema(description = "Assessment report HTML")
    private String selfReportContent;
}
