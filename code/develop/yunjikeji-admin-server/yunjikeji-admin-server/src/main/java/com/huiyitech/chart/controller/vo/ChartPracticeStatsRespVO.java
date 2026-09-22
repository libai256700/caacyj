package com.huiyitech.chart.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

@Schema(description = "管理后台首页统计 - 学员做题情况 Response VO")
@Data
@Builder
public class ChartPracticeStatsRespVO {

    @Schema(description = "练习记录数", example = "128")
    private Long practiceRecordCount;

    @Schema(description = "当天答题数", example = "36")
    private Long todayAnsweredQuestionCount;

    @Schema(description = "答题总数", example = "1024")
    private Long answeredQuestionCount;

    @Schema(description = "答题总数", example = "1024")
    private Long totalAnsweredQuestionCount;

    @Schema(description = "答对题数", example = "880")
    private Long correctQuestionCount;

    @Schema(description = "答错题数", example = "144")
    private Long wrongQuestionCount;

    @Schema(description = "正确率百分比", example = "86.00")
    private String accuracyRate;
}
