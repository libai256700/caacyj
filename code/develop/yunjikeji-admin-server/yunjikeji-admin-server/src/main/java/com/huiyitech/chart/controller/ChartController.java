package com.huiyitech.chart.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import com.huiyitech.chart.controller.vo.ChartDateRangeReqVO;
import com.huiyitech.chart.controller.vo.ChartOverviewRespVO;
import com.huiyitech.chart.controller.vo.ChartPracticeStatsRespVO;
import com.huiyitech.chart.controller.vo.ChartTrendPointRespVO;
import com.huiyitech.chart.service.ChartService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 首页数据看板")
@RestController
@RequestMapping("/admin-api/chart")
@Validated
@RequiredArgsConstructor
public class ChartController {

    private final ChartService chartService;

    @GetMapping("/overview")
    @Operation(summary = "首页统计总览")
    public CommonResult<ChartOverviewRespVO> getOverview(@ModelAttribute ChartDateRangeReqVO reqVO) {
        return success(chartService.getOverview(reqVO));
    }

    @GetMapping("/active-users/today")
    @Operation(summary = "当天活跃人数")
    public CommonResult<Long> getTodayActiveUserCount() {
        return success(chartService.getTodayActiveUserCount());
    }

    @GetMapping("/logins/today")
    @Operation(summary = "当天学员登录总次数")
    public CommonResult<Long> getTodayLoginCount() {
        return success(chartService.getTodayLoginCount());
    }

    @GetMapping("/logins/trend")
    @Operation(summary = "登录趋势")
    public CommonResult<List<ChartTrendPointRespVO>> getLoginTrend(@ModelAttribute ChartDateRangeReqVO reqVO) {
        return success(chartService.getLoginTrend(reqVO));
    }

    @GetMapping("/registers/today")
    @Operation(summary = "当天注册数")
    public CommonResult<Long> getTodayRegisterCount() {
        return success(chartService.getTodayRegisterCount());
    }

    @GetMapping("/registers/total")
    @Operation(summary = "注册总数")
    public CommonResult<Long> getTotalRegisterCount() {
        return success(chartService.getTotalRegisterCount());
    }

    @GetMapping("/registers/trend")
    @Operation(summary = "注册趋势")
    public CommonResult<List<ChartTrendPointRespVO>> getRegisterTrend(@ModelAttribute ChartDateRangeReqVO reqVO) {
        return success(chartService.getRegisterTrend(reqVO));
    }

    @GetMapping("/knowledge-calls/today")
    @Operation(summary = "当天知识图谱调用次数")
    public CommonResult<Long> getTodayKnowledgeCallCount() {
        return success(chartService.getTodayKnowledgeCallCount());
    }

    @GetMapping("/knowledge-calls/total")
    @Operation(summary = "知识图谱总调用次数")
    public CommonResult<Long> getTotalKnowledgeCallCount() {
        return success(chartService.getTotalKnowledgeCallCount());
    }

    @GetMapping("/knowledge-calls/trend")
    @Operation(summary = "知识图谱调用趋势")
    public CommonResult<List<ChartTrendPointRespVO>> getKnowledgeCallTrend(@ModelAttribute ChartDateRangeReqVO reqVO) {
        return success(chartService.getKnowledgeCallTrend(reqVO));
    }

    @GetMapping("/practice/stats")
    @Operation(summary = "学员做题情况")
    public CommonResult<ChartPracticeStatsRespVO> getPracticeStats(@ModelAttribute ChartDateRangeReqVO reqVO) {
        return success(chartService.getPracticeStats(reqVO));
    }

    @GetMapping("/practice/trend")
    @Operation(summary = "学员做题趋势")
    public CommonResult<List<ChartTrendPointRespVO>> getPracticeTrend(@ModelAttribute ChartDateRangeReqVO reqVO) {
        return success(chartService.getPracticeTrend(reqVO));
    }
}
