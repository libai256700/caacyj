package com.huiyitech.chart.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.util.List;

@Schema(description = "管理后台首页统计 - 首页总览 Response VO")
@Data
@Builder
public class ChartOverviewRespVO {

    @Schema(description = "当天活跃人数")
    private Long todayActiveUserCount;

    @Schema(description = "当天学员登录总次数")
    private Long todayLoginCount;

    @Schema(description = "7天登录趋势")
    private List<ChartTrendPointRespVO> loginTrend;

    @Schema(description = "当天注册数")
    private Long todayRegisterCount;

    @Schema(description = "注册总数")
    private Long totalRegisterCount;

    @Schema(description = "7天注册趋势")
    private List<ChartTrendPointRespVO> registerTrend;

    @Schema(description = "知识图谱总调用次数")
    private Long totalKnowledgeCallCount;

    @Schema(description = "当天知识图谱调用次数")
    private Long todayKnowledgeCallCount;

    @Schema(description = "7天知识图谱调用趋势")
    private List<ChartTrendPointRespVO> knowledgeCallTrend;

    @Schema(description = "学员做题情况")
    private ChartPracticeStatsRespVO practiceStats;

    @Schema(description = "学员做题趋势")
    private List<ChartTrendPointRespVO> practiceTrend;
}
