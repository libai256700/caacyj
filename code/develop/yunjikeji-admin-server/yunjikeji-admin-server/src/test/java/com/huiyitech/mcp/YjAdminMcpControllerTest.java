package com.huiyitech.mcp;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.companyaudit.service.CompanyAuditService;
import com.huiyitech.customer.service.CustomerService;
import com.huiyitech.knowledge.controller.vo.KnowledgeQueryRespVO;
import com.huiyitech.knowledge.service.KnowledgeService;
import com.huiyitech.postcollect.service.PostCollectService;
import com.huiyitech.postcollect.service.PostCollectionTaskService;
import com.huiyitech.practice.service.PracticeCategoryService;
import com.huiyitech.practice.service.PracticeExercisesAnswerService;
import com.huiyitech.practice.service.PracticeExercisesService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class YjAdminMcpControllerTest {

    private CompanyAuditService companyAuditService;
    private CustomerService customerService;
    private KnowledgeService knowledgeService;
    private PostCollectionTaskService postCollectionTaskService;
    private PostCollectService postCollectService;
    private PracticeCategoryService practiceCategoryService;
    private PracticeExercisesService practiceExercisesService;
    private PracticeExercisesAnswerService practiceExercisesAnswerService;
    private YjAdminMcpProperties properties;
    private YjAdminMcpController controller;

    @BeforeEach
    void setUp() {
        companyAuditService = mock(CompanyAuditService.class);
        customerService = mock(CustomerService.class);
        knowledgeService = mock(KnowledgeService.class);
        postCollectionTaskService = mock(PostCollectionTaskService.class);
        postCollectService = mock(PostCollectService.class);
        practiceCategoryService = mock(PracticeCategoryService.class);
        practiceExercisesService = mock(PracticeExercisesService.class);
        practiceExercisesAnswerService = mock(PracticeExercisesAnswerService.class);
        properties = new YjAdminMcpProperties();
        properties.setEnabled(true);
        properties.setAccessToken("test-token");
        controller = new YjAdminMcpController(companyAuditService, customerService, knowledgeService,
                postCollectionTaskService, postCollectService, practiceCategoryService, practiceExercisesService,
                practiceExercisesAnswerService, properties, new ObjectMapper());
    }

    @Test
    void handle_shouldRejectWhenDisabled() {
        properties.setEnabled(false);

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), request("tools/list"));

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals(-32000, errorCode(response));
    }

    @Test
    void handle_shouldRejectMissingOrWrongToken() {
        ResponseEntity<Map<String, Object>> missing = controller.handle(Collections.emptyMap(), request("tools/list"));
        ResponseEntity<Map<String, Object>> wrong = controller.handle(headers("wrong-token"), request("tools/list"));

        assertEquals(HttpStatus.UNAUTHORIZED, missing.getStatusCode());
        assertEquals(HttpStatus.UNAUTHORIZED, wrong.getStatusCode());
        assertEquals(-32001, errorCode(missing));
        assertEquals(-32001, errorCode(wrong));
    }

    @Test
    @SuppressWarnings("unchecked")
    void handle_shouldListToolsWithValidToken() {
        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), request("tools/list"));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<String, Object> result = (Map<String, Object>) response.getBody().get("result");
        assertNotNull(result.get("tools"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void handle_shouldCallKnowledgeQuery() {
        when(knowledgeService.query("怎么报名")).thenReturn(KnowledgeQueryRespVO.builder()
                .question("怎么报名")
                .knowledgeAnswer("报名说明")
                .finalAnswer("报名说明")
                .build());
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "knowledge_query", "arguments", map("question", "怎么报名")));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<String, Object> result = (Map<String, Object>) response.getBody().get("result");
        assertNotNull(result.get("structuredContent"));
        verify(knowledgeService).query("怎么报名");
    }

    @Test
    void handle_shouldCallCompanyAuditWithOperatorContext() {
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "company_audit_review",
                "arguments", map("id", 10L, "auditStatus", 2, "operatorUserId", 99L)));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        verify(companyAuditService).auditEnterprise(any());
    }

    @Test
    void handle_shouldCallPostCollectQuery() {
        when(postCollectService.getPage(any())).thenReturn(new PageResult<>(Collections.emptyList(), 0L));
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "post_collect_query_positions",
                "arguments", map("pageNo", 1, "pageSize", 5, "keyword", "飞手")));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        verify(postCollectService).getPage(any());
    }

    @Test
    void handle_shouldCreatePracticeQuestion() {
        when(practiceExercisesService.create(any())).thenReturn(123L);
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "practice_create_question",
                "arguments", map("categoryId", 1L, "questionStem", "题干", "questionType", "single")));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        verify(practiceExercisesService).create(any());
    }

    @Test
    void handle_shouldConfigurePracticeAnswers() {
        when(practiceExercisesAnswerService.create(any())).thenReturn(1L, 2L);
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "practice_configure_answers",
                "arguments", map("questionId", 123L, "answers", java.util.Arrays.asList(
                        map("answerCode", "A", "answerContent", "对", "isCorrect", true),
                        map("answerCode", "B", "answerContent", "错", "isCorrect", false)))));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        verify(practiceExercisesAnswerService, times(2)).create(any());
    }

    @Test
    void handle_shouldExecuteCollectNow() {
        when(postCollectionTaskService.collectNow(eq(7L), eq("mcp"))).thenReturn(map("success", true));
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "post_collect_execute_now", "arguments", map("taskId", 7L)));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        verify(postCollectionTaskService).collectNow(eq(7L), eq("mcp"));
    }

    @SuppressWarnings("unchecked")
    private Integer errorCode(ResponseEntity<Map<String, Object>> response) {
        return (Integer) ((Map<String, Object>) response.getBody().get("error")).get("code");
    }

    private Map<String, String> headers(String token) {
        Map<String, String> headers = new HashMap<>();
        headers.put("X-Huiyitech-Mcp-Token", token);
        return headers;
    }

    private Map<String, Object> request(String method) {
        return map("jsonrpc", "2.0", "id", 1, "method", method);
    }

    private Map<String, Object> map(Object... keyValues) {
        Map<String, Object> map = new HashMap<>();
        for (int i = 0; i + 1 < keyValues.length; i += 2) {
            map.put(String.valueOf(keyValues[i]), keyValues[i + 1]);
        }
        return map;
    }

}
