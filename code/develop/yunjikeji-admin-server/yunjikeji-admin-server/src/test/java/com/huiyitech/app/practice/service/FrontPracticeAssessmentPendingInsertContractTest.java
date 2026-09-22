package com.huiyitech.app.practice.service;

import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FrontPracticeAssessmentPendingInsertContractTest {

    @Test
    void createPendingAssessmentResult_shouldInsertAllSharedColumnsWhenSchemaIsComplete() {
        JdbcTemplate jdbcTemplate = jdbcTemplate("complete_schema");
        createAssessmentResultTable(jdbcTemplate, true, true);
        FrontPracticeServiceImpl service = service(jdbcTemplate);

        Long assessmentResultId = ReflectionTestUtils.invokeMethod(service,
                "createPendingAssessmentResult", 9001L, 201L);

        assertNotNull(assessmentResultId);
        Map<String, Object> row = jdbcTemplate.queryForMap(
                "SELECT user_id, customer_account_id, record_id, report_status, failure_reason, deleted "
                        + "FROM yj_assessment_result WHERE id = ?",
                assessmentResultId);
        assertEquals(9001L, ((Number) row.get("user_id")).longValue());
        assertEquals(9001L, ((Number) row.get("customer_account_id")).longValue());
        assertEquals(201L, ((Number) row.get("record_id")).longValue());
        assertEquals("PENDING", row.get("report_status"));
        assertEquals(null, row.get("failure_reason"));
        assertEquals(Boolean.FALSE, row.get("deleted"));
    }

    @Test
    void createPendingAssessmentResult_shouldFallbackWhenCustomerAccountColumnIsMissing() {
        JdbcTemplate jdbcTemplate = jdbcTemplate("missing_customer_account");
        createAssessmentResultTable(jdbcTemplate, false, true);
        FrontPracticeServiceImpl service = service(jdbcTemplate);

        Long assessmentResultId = ReflectionTestUtils.invokeMethod(service,
                "createPendingAssessmentResult", 9001L, 201L);

        assertNotNull(assessmentResultId);
        Map<String, Object> row = jdbcTemplate.queryForMap(
                "SELECT user_id, record_id, report_status, failure_reason, deleted "
                        + "FROM yj_assessment_result WHERE id = ?",
                assessmentResultId);
        assertEquals(9001L, ((Number) row.get("user_id")).longValue());
        assertEquals(201L, ((Number) row.get("record_id")).longValue());
        assertEquals("PENDING", row.get("report_status"));
        assertEquals(null, row.get("failure_reason"));
        assertEquals(Boolean.FALSE, row.get("deleted"));
    }

    @Test
    void submitAnswer_sourceContract_shouldLockOwnedRecordAndClaimInsideTransactionBeforeEnqueue() throws Exception {
        Path sourcePath = Paths.get("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        String source = new String(Files.readAllBytes(sourcePath), StandardCharsets.UTF_8);
        int submitStart = source.indexOf("public AppPracticeAnswerSubmitRespVO submitAnswer(");
        String submitMethod = source.substring(submitStart,
                source.indexOf("private InitialAssessmentReportClaim claimInitialAssessmentReport(", submitStart));
        int claimCallIndex = submitMethod.indexOf("claimInitialAssessmentReport(loginUser.getId(), recordId)");
        int enqueueIndex = submitMethod.indexOf("enqueueAssessmentEvaluation(response, assessmentSession, recordId");
        assertTrue(claimCallIndex >= 0 && enqueueIndex > claimCallIndex,
                "the database claim transaction must commit before asynchronous enqueue");
        assertTrue(submitMethod.contains(
                "answers, true)"));
        assertTrue(submitMethod.contains("new PracticeRuntimeSession(null, loginUser.getId()"),
                "assessment submission must use the shared agent configuration without tenant binding");
        assertTrue(!submitMethod.contains("currentTenantId(loginUser)"),
                "assessment submission must not require a student tenant binding");

        int agentConfigStart = source.indexOf("private Map<String, Object> findAssessmentAgentConfig(Long tenantId,");
        String agentConfigMethod = source.substring(agentConfigStart,
                source.indexOf("private String cleanAssessmentHtml(", agentConfigStart));
        assertTrue(agentConfigMethod.contains("WHERE id = ? AND deleted = b'0' LIMIT 1"));
        assertTrue(agentConfigMethod.contains("agentInfoId);"));
        assertTrue(!agentConfigMethod.contains("tenant_id"),
                "shared assessment agent lookup must ignore tenant_id completely");

        int claimStart = source.indexOf("private InitialAssessmentReportClaim claimInitialAssessmentReport(");
        String claimMethod = source.substring(claimStart,
                source.indexOf("private void lockOwnedAssessmentRecord(", claimStart));
        int transactionIndex = claimMethod.indexOf("transactionTemplate.execute");
        int lockIndex = claimMethod.indexOf("lockOwnedAssessmentRecord(recordId, customerAccountId)");
        int latestIndex = claimMethod.indexOf("findLatestAssessmentResult(customerAccountId, recordId)");
        int failedClaimIndex = claimMethod.indexOf("claimFailedAssessmentResult(current.id, recordId, customerAccountId)");
        int pendingInsertIndex = claimMethod.indexOf("createPendingAssessmentResult(customerAccountId, recordId)");
        assertTrue(transactionIndex >= 0 && lockIndex > transactionIndex && latestIndex > lockIndex);
        assertTrue(failedClaimIndex > latestIndex && pendingInsertIndex > latestIndex);
        assertTrue(claimMethod.contains("ASSESSMENT_REPORT_STATUS_SUCCESS"));
        assertTrue(claimMethod.contains("ASSESSMENT_REPORT_STATUS_PENDING"));
        assertTrue(claimMethod.contains("ASSESSMENT_REPORT_STATUS_FAILED"));

        int lockMethodStart = source.indexOf("private void lockOwnedAssessmentRecord(");
        String lockMethod = source.substring(lockMethodStart,
                source.indexOf("private void applyAssessmentResultToSubmitResponse(", lockMethodStart));
        assertTrue(lockMethod.contains("SELECT id FROM yj_user_practice_exercises_record"));
        assertTrue(lockMethod.contains("WHERE id = ? AND customer_account_id = ? AND deleted = b'0' FOR UPDATE"));
        assertTrue(lockMethod.contains("Long.class, recordId, customerAccountId"));
    }

    @Test
    void regenerateAssessmentReport_sourceContract_shouldEnqueueDatabaseClaimWithoutJvmGate() throws Exception {
        Path sourcePath = Paths.get("src/main/java/com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        String source = new String(Files.readAllBytes(sourcePath), StandardCharsets.UTF_8);
        int regenerateStart = source.indexOf("public AppPracticeAnswerSubmitRespVO regenerateAssessmentReport(");
        String regenerateMethod = source.substring(regenerateStart,
                source.indexOf("private PracticeCatalogBatchDO requireCompletedAssessmentBatch(", regenerateStart));
        int failedClaimIndex = regenerateMethod.indexOf(
                "claimFailedAssessmentResult(assessmentResult.id, recordId, customerAccountId)");
        int enqueueIndex = regenerateMethod.indexOf(
                "enqueueAssessmentEvaluation(response, assessmentSession, recordId, assessmentResult.id, answers, true)");
        assertTrue(failedClaimIndex >= 0 && enqueueIndex > failedClaimIndex);
        assertTrue(regenerateMethod.contains("new PracticeRuntimeSession(null, customerAccountId"),
                "self-assessment report retry must use the shared agent configuration without tenant binding");
        assertTrue(!regenerateMethod.contains("currentTenantId(loginUser)"),
                "self-assessment report retry must not require a student tenant binding");

        int enqueueStart = source.indexOf("private void enqueueAssessmentEvaluation(");
        String enqueueMethod = source.substring(enqueueStart,
                source.indexOf("private String normalizePracticeId(", enqueueStart));
        assertTrue(enqueueMethod.contains("if (!reportAlreadyClaimed)"));
        assertTrue(enqueueMethod.contains("markAssessmentResultFailed(assessmentResultId, recordId"));
        assertTrue(!source.contains("assessmentReportsInProgress"));
    }

    private FrontPracticeServiceImpl service(JdbcTemplate jdbcTemplate) {
        FrontPracticeServiceImpl service = new FrontPracticeServiceImpl();
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplate);
        return service;
    }

    private JdbcTemplate jdbcTemplate(String suffix) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:" + suffix + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");
        return new JdbcTemplate(dataSource);
    }

    private void createAssessmentResultTable(JdbcTemplate jdbcTemplate,
                                             boolean includeCustomerAccountId,
                                             boolean includeStatusColumns) {
        String customerAccountColumn = includeCustomerAccountId
                ? "customer_account_id bigint DEFAULT NULL COMMENT '学员账号编号',"
                : "";
        String statusColumns = includeStatusColumns
                ? "report_status varchar(32) NOT NULL DEFAULT 'SUCCESS' COMMENT '报告状态：PENDING/SUCCESS/FAILED',"
                + "failure_reason varchar(255) DEFAULT NULL COMMENT '报告失败原因',"
                : "";
        jdbcTemplate.execute("DROP TABLE IF EXISTS yj_assessment_result");
        jdbcTemplate.execute("CREATE TABLE yj_assessment_result ("
                + "id bigint auto_increment primary key,"
                + "user_id bigint NOT NULL,"
                + customerAccountColumn
                + "record_id bigint NOT NULL,"
                + "assessment_time datetime NOT NULL,"
                + "result_summary varchar(500) DEFAULT NULL,"
                + "recommend_direction varchar(255) DEFAULT NULL,"
                + "report_content clob,"
                + statusColumns
                + "tenant_id bigint DEFAULT NULL,"
                + "creator varchar(64) DEFAULT '',"
                + "create_time datetime NOT NULL,"
                + "updater varchar(64) DEFAULT '',"
                + "update_time datetime NOT NULL,"
                + "deleted boolean NOT NULL DEFAULT false"
                + ")");
    }
}
