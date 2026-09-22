package com.huiyitech.chart.service;

import com.huiyitech.chart.controller.vo.ChartDateRangeReqVO;
import com.huiyitech.chart.controller.vo.ChartOverviewRespVO;
import com.huiyitech.chart.controller.vo.ChartPracticeStatsRespVO;
import com.huiyitech.chart.controller.vo.ChartTrendPointRespVO;

import java.util.List;

public interface ChartService {

    ChartOverviewRespVO getOverview(ChartDateRangeReqVO reqVO);

    Long getTodayActiveUserCount();

    Long getTodayLoginCount();

    List<ChartTrendPointRespVO> getLoginTrend(ChartDateRangeReqVO reqVO);

    Long getTodayRegisterCount();

    Long getTotalRegisterCount();

    List<ChartTrendPointRespVO> getRegisterTrend(ChartDateRangeReqVO reqVO);

    Long getTodayKnowledgeCallCount();

    Long getTotalKnowledgeCallCount();

    List<ChartTrendPointRespVO> getKnowledgeCallTrend(ChartDateRangeReqVO reqVO);

    ChartPracticeStatsRespVO getPracticeStats(ChartDateRangeReqVO reqVO);

    List<ChartTrendPointRespVO> getPracticeTrend(ChartDateRangeReqVO reqVO);
}
