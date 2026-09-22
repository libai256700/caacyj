package com.huiyitech.chart.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDate;

@Schema(description = "管理后台首页统计 - 日期范围 Request VO")
@Data
public class ChartDateRangeReqVO {

    @Schema(description = "开始日期", example = "2026-06-25")
    @DateTimeFormat(pattern = "yyyy-MM-dd")
    private LocalDate startDate;

    @Schema(description = "结束日期", example = "2026-07-01")
    @DateTimeFormat(pattern = "yyyy-MM-dd")
    private LocalDate endDate;
}
