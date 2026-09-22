package com.huiyitech.app.practice.service;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.huiyitech.aiconfig.AiSceneCodes;
import com.huiyitech.aiconfig.dal.dataobject.AiModelConfigDO;
import com.huiyitech.aiconfig.service.AiModelConfigService;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCatalogBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeCatalogBatchMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class FrontPracticeServiceImplCareerReportReadTest {

    private FrontPracticeServiceImpl service;
    private final CareerPlanningRuleEngine careerPlanningRuleEngine = new CareerPlanningRuleEngine();
    private Logger logger;
    private Logger careerLogger;
    private ListAppender<ILoggingEvent> appender;

    @BeforeEach
    void setUp() {
        service = new FrontPracticeServiceImpl();
        AiModelConfigService aiModelConfigService = mock(AiModelConfigService.class);
        when(aiModelConfigService.getRequiredActiveBySceneCode(AiSceneCodes.PRACTICE_ASSESSMENT))
                .thenReturn(AiModelConfigDO.builder()
                        .channel("openai-compatible")
                        .baseUrl("https://api.deepseek.com")
                        .apiKey("test-key")
                        .model("deepseek-chat")
                        .minReportLength(200)
                        .build());
        ReflectionTestUtils.setField(service, "aiModelConfigService", aiModelConfigService);
        logger = (Logger) LoggerFactory.getLogger(FrontPracticeServiceImpl.class);
        careerLogger = (Logger) LoggerFactory.getLogger(CareerPlanningRuleEngine.class);
        appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        careerLogger.addAppender(appender);
    }

    @AfterEach
    void tearDown() {
        logger.detachAppender(appender);
        careerLogger.detachAppender(appender);
        appender.stop();
    }

    @Test
    void resolveAssessmentReportCategoryId_shouldUseCatalogBatchBusinessCategoryForAssessmentRecord() {
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        when(catalogBatchMapper.selectById(215L)).thenReturn(PracticeCatalogBatchDO.builder()
                .id(215L)
                .categoryId(14L)
                .build());
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);

        Long result = ReflectionTestUtils.invokeMethod(service, "resolveAssessmentReportCategoryId",
                assessmentRecord(215L));

        assertEquals(14L, result);
    }

    @Test
    void findSelfReportContent_shouldKeepCareerReportWhenCatalogBatchMapsToCategory14() {
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplateReturning("SUCCESS", validCareerReport()));
        UserPracticeExercisesRecordMapper recordMapper = mock(UserPracticeExercisesRecordMapper.class);
        when(recordMapper.selectById(104L)).thenReturn(assessmentRecord(104L, 215L));
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordMapper", recordMapper);
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        when(catalogBatchMapper.selectById(215L)).thenReturn(PracticeCatalogBatchDO.builder()
                .id(215L)
                .categoryId(14L)
                .build());
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);

        String result = ReflectionTestUtils.invokeMethod(service, "findSelfReportContent", 1L, 104L);

        assertEquals(validCareerReport(), result);
        assertTrue(infos().contains("Career assessment AI stage=report_poll status=RESULT userId=1 recordId=104 assessmentResultId=1 categoryId=14 reportStatus=SUCCESS hasReportContent=true failureReason=null"));
    }

    @Test
    void findSelfReportContent_shouldRejectCareerHtmlWhenCatalogBatchMapsToCategory13() {
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplateReturning("SUCCESS", validCareerReport()));
        UserPracticeExercisesRecordMapper recordMapper = mock(UserPracticeExercisesRecordMapper.class);
        when(recordMapper.selectById(105L)).thenReturn(assessmentRecord(105L, 216L));
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordMapper", recordMapper);
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        when(catalogBatchMapper.selectById(216L)).thenReturn(PracticeCatalogBatchDO.builder()
                .id(216L)
                .categoryId(13L)
                .build());
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);

        String result = ReflectionTestUtils.invokeMethod(service, "findSelfReportContent", 1L, 105L);

        assertEquals("", result);
    }

    @Test
    void findSelfReportContent_shouldRejectCareerHtmlWhenCatalogBatchMissing() {
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplateReturning("SUCCESS", validCareerReport()));
        UserPracticeExercisesRecordMapper recordMapper = mock(UserPracticeExercisesRecordMapper.class);
        when(recordMapper.selectById(106L)).thenReturn(assessmentRecord(106L, 217L));
        ReflectionTestUtils.setField(service, "userPracticeExercisesRecordMapper", recordMapper);
        PracticeCatalogBatchMapper catalogBatchMapper = mock(PracticeCatalogBatchMapper.class);
        when(catalogBatchMapper.selectById(217L)).thenReturn(null);
        ReflectionTestUtils.setField(service, "practiceCatalogBatchMapper", catalogBatchMapper);

        String result = ReflectionTestUtils.invokeMethod(service, "findSelfReportContent", 1L, 106L);

        assertEquals("", result);
    }

    @Test
    void resolveAssessmentReportContent_shouldRejectInvalidCareerReportForCategory14() {
        Object snapshot = snapshot("SUCCESS", invalidCareerReport());

        String result = ReflectionTestUtils.invokeMethod(service, "resolveAssessmentReportContent", snapshot, 1L, 103L, 14L);

        assertEquals("", result);
        assertTrue(infos().contains("Career assessment AI stage=report_poll status=RESULT userId=1 recordId=103 assessmentResultId=1 categoryId=14 reportStatus=SUCCESS hasReportContent=false failureReason=null"));
    }

    @Test
    void resolveAssessmentReportContent_shouldKeepAuditedCareerReportForCategory14() {
        String auditedReport = careerReportWithPlanParagraph("所有岗位都要求CAAC执照。");
        Object snapshot = snapshot("SUCCESS", auditedReport);

        String result = ReflectionTestUtils.invokeMethod(service, "resolveAssessmentReportContent", snapshot, 1L, 107L, 14L);

        assertEquals(auditedReport, result);
    }

    private UserPracticeExercisesRecordDO assessmentRecord(Long catalogBatchId) {
        return assessmentRecord(null, catalogBatchId);
    }

    private UserPracticeExercisesRecordDO assessmentRecord(Long recordId, Long catalogBatchId) {
        return UserPracticeExercisesRecordDO.builder()
                .id(recordId)
                .categoryId(catalogBatchId)
                .fieldType("assessment")
                .build();
    }

    private Object snapshot(String reportStatus, String reportContent) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", 1L);
        row.put("report_status", reportStatus);
        row.put("result_summary", "summary");
        row.put("recommend_direction", "career");
        row.put("report_content", reportContent);
        row.put("failure_reason", null);
        row.put("assessment_time", null);
        return ReflectionTestUtils.invokeMethod(service, "toAssessmentResultSnapshot", row);
    }

    private JdbcTemplate jdbcTemplateReturning(String reportStatus, String reportContent) {
        return mock(JdbcTemplate.class, invocation -> {
            if ("queryForList".equals(invocation.getMethod().getName())) {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("id", 1L);
                row.put("report_status", reportStatus);
                row.put("result_summary", "summary");
                row.put("recommend_direction", "career");
                row.put("report_content", reportContent);
                row.put("failure_reason", null);
                row.put("assessment_time", null);
                return Collections.singletonList(row);
            }
            return null;
        });
    }

    private String validCareerReport() {
        String report = "<h1>一、我的现状盘点</h1><p>" + repeated("基于本次作答梳理当前基础和已有经历，建议把真实体验作为后续选择依据。", 5)
                + "</p><h1>二、优势与待发展方向</h1><p>" + repeated("兴趣、价值取向和实际投入共同用于判断适合优先尝试的方向，结论需要在实践中继续确认。", 5)
                + "</p><h1>三、下一步发展计划</h1><p>" + repeated("未来九十天先完成一个可验证的小任务，记录过程和成果，再根据反馈调整方向。", 5) + "</p>";
        return careerPlanningRuleEngine.validateAndNormalizeReport(report);
    }

    private String invalidCareerReport() {
        return validCareerReport().replace("三、下一步发展计划", "错误标题");
    }

    private String careerReportWithPlanParagraph(String planParagraph) {
        return "<h1>一、我的现状盘点</h1><p>" + repeated("基于本次作答梳理当前基础和已有经历，建议把真实体验作为后续选择依据。", 5)
                + "</p><h1>二、优势与待发展方向</h1><p>" + repeated("兴趣、价值取向和实际投入共同用于判断适合优先尝试的方向，结论需要在实践中继续确认。", 5)
                + "</p><h1>三、下一步发展计划</h1><p>" + repeated("未来九十天先完成一个可验证的小任务，记录过程和成果，再根据反馈调整方向。", 4)
                + planParagraph + "</p>";
    }

    private String repeated(String value, int count) {
        StringBuilder builder = new StringBuilder();
        for (int index = 0; index < count; index++) {
            builder.append(value);
        }
        return builder.toString();
    }

    private String infos() {
        StringBuilder result = new StringBuilder();
        appender.list.stream()
                .filter(event -> Level.INFO.equals(event.getLevel()))
                .map(ILoggingEvent::getFormattedMessage)
                .forEach(message -> result.append(message).append('\n'));
        return result.toString();
    }
}
