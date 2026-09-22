package com.huiyitech.chart.service;

import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import com.huiyitech.chart.controller.vo.ChartDateRangeReqVO;
import com.huiyitech.chart.controller.vo.ChartOverviewRespVO;
import com.huiyitech.chart.controller.vo.ChartPracticeStatsRespVO;
import com.huiyitech.chart.controller.vo.ChartTrendPointRespVO;
import com.huiyitech.chart.dal.mysql.AccountLoginLogMapper;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
@RequiredArgsConstructor
public class ChartServiceImpl implements ChartService {

    private final AccountLoginLogMapper accountLoginLogMapper;

    @Override
    public ChartOverviewRespVO getOverview(ChartDateRangeReqVO reqVO) {
        return executeIgnoreTenant(() -> ChartOverviewRespVO.builder()
                .todayActiveUserCount(getTodayActiveUserCount())
                .todayLoginCount(getTodayLoginCount())
                .loginTrend(getLoginTrend(reqVO))
                .todayRegisterCount(getTodayRegisterCount())
                .totalRegisterCount(getTotalRegisterCount())
                .registerTrend(getRegisterTrend(reqVO))
                .totalKnowledgeCallCount(getTotalKnowledgeCallCount())
                .todayKnowledgeCallCount(getTodayKnowledgeCallCount())
                .knowledgeCallTrend(getKnowledgeCallTrend(reqVO))
                .practiceStats(getPracticeStats(reqVO))
                .practiceTrend(getPracticeTrend(reqVO))
                .build());
    }

    @Override
    public Long getTodayActiveUserCount() {
        return executeIgnoreTenant(() -> {
            DateRange range = todayRange();
            return zeroIfNull(accountLoginLogMapper.selectTodayActiveUserCount(range.getStartTimeText(),
                    range.getEndTimeText()));
        });
    }

    @Override
    public Long getTodayLoginCount() {
        return executeIgnoreTenant(() -> {
            DateRange range = todayRange();
            return zeroIfNull(accountLoginLogMapper.selectLoginCount(range.getStartTimeText(), range.getEndTimeText()));
        });
    }

    @Override
    public List<ChartTrendPointRespVO> getLoginTrend(ChartDateRangeReqVO reqVO) {
        return executeIgnoreTenant(() -> {
            DateRange range = resolveRange(reqVO);
            return fillTrend(range, accountLoginLogMapper.selectLoginTrend(range.getStartTimeText(), range.getEndTimeText()));
        });
    }

    @Override
    public Long getTodayRegisterCount() {
        return executeIgnoreTenant(() -> {
            DateRange range = todayRange();
            return zeroIfNull(accountLoginLogMapper.selectRegisterCount(range.getStartTime(), range.getEndTime()));
        });
    }

    @Override
    public Long getTotalRegisterCount() {
        return executeIgnoreTenant(() -> zeroIfNull(accountLoginLogMapper.selectTotalRegisterCount()));
    }

    @Override
    public List<ChartTrendPointRespVO> getRegisterTrend(ChartDateRangeReqVO reqVO) {
        return executeIgnoreTenant(() -> {
            DateRange range = resolveRange(reqVO);
            return fillTrend(range, accountLoginLogMapper.selectRegisterTrend(range.getStartTime(), range.getEndTime()));
        });
    }

    @Override
    public Long getTodayKnowledgeCallCount() {
        return executeIgnoreTenant(() -> {
            DateRange range = todayRange();
            return zeroIfNull(accountLoginLogMapper.selectKnowledgeCallCount(range.getStartTimeText(), range.getEndTimeText()));
        });
    }

    @Override
    public Long getTotalKnowledgeCallCount() {
        return executeIgnoreTenant(() -> zeroIfNull(accountLoginLogMapper.selectTotalKnowledgeCallCount()));
    }

    @Override
    public List<ChartTrendPointRespVO> getKnowledgeCallTrend(ChartDateRangeReqVO reqVO) {
        return executeIgnoreTenant(() -> {
            DateRange range = resolveRange(reqVO);
            return fillTrend(range, accountLoginLogMapper.selectKnowledgeCallTrend(range.getStartTimeText(),
                    range.getEndTimeText()));
        });
    }

    @Override
    public ChartPracticeStatsRespVO getPracticeStats(ChartDateRangeReqVO reqVO) {
        return executeIgnoreTenant(() -> {
            DateRange range = resolveRange(reqVO);
            DateRange todayRange = todayRange();
            Long recordCount = zeroIfNull(accountLoginLogMapper.selectPracticeRecordCount(range.getStartTime(),
                    range.getEndTime()));
            Long todayAnsweredCount = zeroIfNull(accountLoginLogMapper.selectAnsweredQuestionCount(
                    todayRange.getStartTime(), todayRange.getEndTime()));
            Long totalAnsweredCount = zeroIfNull(accountLoginLogMapper.selectTotalAnsweredQuestionCount());
            Long answeredCount = zeroIfNull(accountLoginLogMapper.selectAnsweredQuestionCount(range.getStartTime(),
                    range.getEndTime()));
            Long correctCount = zeroIfNull(accountLoginLogMapper.selectCorrectQuestionCount(range.getStartTime(),
                    range.getEndTime()));
            Long wrongCount = zeroIfNull(accountLoginLogMapper.selectWrongQuestionCount(range.getStartTime(),
                    range.getEndTime()));
            return ChartPracticeStatsRespVO.builder()
                    .practiceRecordCount(recordCount)
                    .todayAnsweredQuestionCount(todayAnsweredCount)
                    .answeredQuestionCount(answeredCount)
                    .totalAnsweredQuestionCount(totalAnsweredCount)
                    .correctQuestionCount(correctCount)
                    .wrongQuestionCount(wrongCount)
                    .accuracyRate(calculateAccuracyRate(correctCount, answeredCount))
                    .build();
        });
    }

    @Override
    public List<ChartTrendPointRespVO> getPracticeTrend(ChartDateRangeReqVO reqVO) {
        return executeIgnoreTenant(() -> {
            DateRange range = resolveRange(reqVO);
            return fillTrend(range, accountLoginLogMapper.selectPracticeTrend(range.getStartTime(), range.getEndTime()));
        });
    }

    private <T> T executeIgnoreTenant(Supplier<T> supplier) {
        return TenantUtils.executeIgnore(supplier::get);
    }

    private DateRange resolveRange(ChartDateRangeReqVO reqVO) {
        LocalDate endDate = reqVO == null || reqVO.getEndDate() == null ? LocalDate.now() : reqVO.getEndDate();
        LocalDate startDate = reqVO == null || reqVO.getStartDate() == null ? endDate.minusDays(6) : reqVO.getStartDate();
        if (startDate.isAfter(endDate)) {
            throw invalidParamException("startDate 不能晚于 endDate");
        }
        long days = ChronoUnit.DAYS.between(startDate, endDate);
        if (days > 6) {
            throw invalidParamException("startDate 和 endDate 时间窗口不能超过 7 天");
        }
        return new DateRange(startDate, endDate.plusDays(1));
    }

    private DateRange todayRange() {
        LocalDate today = LocalDate.now();
        return new DateRange(today, today.plusDays(1));
    }

    private List<ChartTrendPointRespVO> fillTrend(DateRange range, List<ChartTrendPointRespVO> rows) {
        Map<String, Long> rowMap = new LinkedHashMap<>();
        for (ChartTrendPointRespVO row : rows) {
            rowMap.put(row.getDate(), zeroIfNull(row.getCount()));
        }
        List<ChartTrendPointRespVO> result = new ArrayList<>();
        LocalDate cursor = range.getStartDate();
        while (cursor.isBefore(range.getEndExclusiveDate())) {
            String date = cursor.toString();
            result.add(ChartTrendPointRespVO.builder()
                    .date(date)
                    .count(rowMap.getOrDefault(date, 0L))
                    .build());
            cursor = cursor.plusDays(1);
        }
        return result;
    }

    private String calculateAccuracyRate(Long correctCount, Long answeredCount) {
        if (answeredCount == null || answeredCount == 0) {
            return "0.00";
        }
        return BigDecimal.valueOf(correctCount == null ? 0L : correctCount)
                .multiply(BigDecimal.valueOf(100))
                .divide(BigDecimal.valueOf(answeredCount), 2, RoundingMode.HALF_UP)
                .toPlainString();
    }

    private Long zeroIfNull(Long value) {
        return value == null ? 0L : value;
    }

    @Data
    @AllArgsConstructor
    private static class DateRange {

        private LocalDate startDate;

        private LocalDate endExclusiveDate;

        LocalDateTime getStartTime() {
            return startDate.atStartOfDay();
        }

        LocalDateTime getEndTime() {
            return endExclusiveDate.atStartOfDay();
        }

        String getStartTimeText() {
            return getStartTime().format(AccountLoginLogTimeFormatter.FORMATTER);
        }

        String getEndTimeText() {
            return getEndTime().format(AccountLoginLogTimeFormatter.FORMATTER);
        }
    }

    private static final class AccountLoginLogTimeFormatter {
        private static final java.time.format.DateTimeFormatter FORMATTER =
                java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    }
}
