package com.huiyitech.chart.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "管理后台首页统计 - 趋势点 Response VO")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ChartTrendPointRespVO {

    @Schema(description = "日期", example = "2026-07-01")
    private String date;

    @Schema(description = "数量", example = "12")
    private Long count;
}
