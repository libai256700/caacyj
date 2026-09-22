package com.huiyitech.mcp;

import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.companyaudit.service.CompanyAuditService;
import com.huiyitech.customer.service.CustomerService;
import com.huiyitech.knowledge.service.KnowledgeService;
import com.huiyitech.postcollect.service.PostCollectService;
import com.huiyitech.postcollect.service.PostCollectionTaskService;
import com.huiyitech.practice.service.PracticeCategoryService;
import com.huiyitech.practice.service.PracticeExercisesAnswerService;
import com.huiyitech.practice.service.PracticeExercisesService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;

@RestController
@RequiredArgsConstructor
public class YjAdminMcpController {

    private static final String JSONRPC = "2.0";
    private static final String PROTOCOL_VERSION = "2024-11-05";
    private static final int CATALOG_TYPE_PRACTICE = 0;

    private final CompanyAuditService companyAuditService;
    private final CustomerService customerService;
    private final KnowledgeService knowledgeService;
    private final PostCollectionTaskService postCollectionTaskService;
    private final PostCollectService postCollectService;
    private final PracticeCategoryService practiceCategoryService;
    private final PracticeExercisesService practiceExercisesService;
    private final PracticeExercisesAnswerService practiceExercisesAnswerService;
    private final YjAdminMcpProperties properties;
    private final ObjectMapper objectMapper;

    @PostMapping("${huiyitech.yj-admin.mcp.endpoint:/mcp/yj-admin}")
    public ResponseEntity<Map<String, Object>> handle(@RequestHeader Map<String, String> headers,
                                                      @RequestBody Map<String, Object> request) {
        Object id = request.get("id");
        if (!properties.isEnabled()) {
            return error(id, -32000, "YJ admin MCP endpoint is disabled", HttpStatus.NOT_FOUND);
        }
        if (!isAuthorized(headers)) {
            return error(id, -32001, "Unauthorized YJ admin MCP request", HttpStatus.UNAUTHORIZED);
        }

        String method = asString(request.get("method"));
        try {
            if (id == null && method != null && method.startsWith("notifications/")) {
                return ResponseEntity.noContent().build();
            }
            if ("initialize".equals(method)) {
                return ok(id, initializeResult());
            }
            if ("ping".equals(method)) {
                return ok(id, map());
            }
            if ("tools/list".equals(method)) {
                return ok(id, toolsListResult());
            }
            if ("tools/call".equals(method)) {
                return ok(id, callTool(request.get("params")));
            }
            return error(id, -32601, "Unsupported MCP method: " + method, HttpStatus.OK);
        } catch (IllegalArgumentException ex) {
            return error(id, -32602, ex.getMessage(), HttpStatus.OK);
        } catch (Exception ex) {
            return error(id, -32603, "YJ admin MCP call failed: " + ex.getMessage(), HttpStatus.OK);
        }
    }

    private boolean isAuthorized(Map<String, String> headers) {
        if (StrUtil.isBlank(properties.getAccessToken())) {
            return false;
        }
        String expectedHeader = properties.getTokenHeader();
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            if (entry.getKey() != null && entry.getKey().equalsIgnoreCase(expectedHeader)) {
                return MessageDigest.isEqual(properties.getAccessToken().getBytes(StandardCharsets.UTF_8),
                        String.valueOf(entry.getValue()).getBytes(StandardCharsets.UTF_8));
            }
        }
        return false;
    }

    private Map<String, Object> initializeResult() {
        Map<String, Object> result = map();
        result.put("protocolVersion", PROTOCOL_VERSION);
        result.put("capabilities", map("tools", map()));
        result.put("serverInfo", map("name", "huiyitech-yj-admin-mcp", "version", "1.0.0"));
        return result;
    }

    Map<String, Object> toolsListResult() {
        List<Map<String, Object>> tools = new ArrayList<>();
        tools.add(tool("company_audit_review", "审核企业注册申请，对应 /admin-api/yj/enterprise-audit/audit。", auditSchema()));
        tools.add(tool("student_audit_review", "审核学员加入申请，对应 /admin-api/yj/student-audit/audit。", auditSchema()));
        tools.add(tool("knowledge_query", "查询知识库问答，对应 /admin-api/yj/knowledge/query。", knowledgeSchema()));
        tools.add(tool("post_collect_execute_now", "根据采集任务配置立即执行岗位采集任务。", collectNowSchema()));
        tools.add(tool("post_collect_query_positions", "分页查询已采集到的岗位信息。", pageQuerySchema()));
        tools.add(tool("practice_create_category", "新建练习题分类。", practiceCategorySchema()));
        tools.add(tool("practice_create_question", "在指定练习分类下新建题目。", practiceQuestionSchema()));
        tools.add(tool("practice_configure_answers", "为指定题目批量配置答案选项。", practiceAnswersSchema()));
        return map("tools", tools);
    }

    Map<String, Object> callTool(Object paramsObject) throws Exception {
        JsonNode params = objectMapper.valueToTree(paramsObject == null ? map() : paramsObject);
        String name = text(params, "name", null);
        JsonNode arguments = params.path("arguments");
        Object value;
        if ("company_audit_review".equals(name)) {
            value = executeWithContext(arguments, () -> {
                companyAuditService.auditEnterprise(body(arguments));
                return map("success", true);
            });
        } else if ("student_audit_review".equals(name)) {
            value = executeWithContext(arguments, () -> {
                customerService.auditStudent(body(arguments));
                return map("success", true);
            });
        } else if ("knowledge_query".equals(name)) {
            String question = requiredText(arguments, "question");
            value = executeWithContext(arguments, () -> knowledgeService.query(question));
        } else if ("post_collect_execute_now".equals(name)) {
            Long taskId = requiredLong(arguments, "taskId");
            String operator = StrUtil.blankToDefault(text(arguments, "operator", null), "mcp");
            value = executeWithContext(arguments, () -> postCollectionTaskService.collectNow(taskId, operator));
        } else if ("post_collect_query_positions".equals(name)) {
            value = executeWithContext(arguments, () -> postCollectService.getPage(params(arguments)));
        } else if ("practice_create_category".equals(name)) {
            value = executeWithContext(arguments, () -> map("id", practiceCategoryService.create(categoryBody(arguments))));
        } else if ("practice_create_question".equals(name)) {
            value = executeWithContext(arguments, () -> map("id", practiceExercisesService.create(questionBody(arguments))));
        } else if ("practice_configure_answers".equals(name)) {
            value = executeWithContext(arguments, () -> configureAnswers(arguments));
        } else {
            throw new IllegalArgumentException("Unknown YJ admin MCP tool: " + name);
        }
        return toolResult(value);
    }

    private Object executeWithContext(JsonNode arguments, Callable<Object> action) throws Exception {
        Long operatorUserId = optionalLong(arguments, "operatorUserId");
        Long tenantId = optionalLong(arguments, "tenantId");
        Authentication oldAuthentication = SecurityContextHolder.getContext().getAuthentication();
        Long oldTenantId = TenantContextHolder.getTenantId();
        Boolean oldIgnore = TenantContextHolder.isIgnore();
        try {
            if (operatorUserId != null) {
                LoginUser loginUser = new LoginUser();
                loginUser.setId(operatorUserId);
                loginUser.setUserType(UserTypeEnum.ADMIN.getValue());
                loginUser.setTenantId(tenantId);
                loginUser.setVisitTenantId(tenantId);
                SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(
                        loginUser, null, Collections.emptyList()));
            }
            if (tenantId != null) {
                TenantContextHolder.setTenantId(tenantId);
                TenantContextHolder.setIgnore(false);
            }
            return action.call();
        } finally {
            if (oldAuthentication == null) {
                SecurityContextHolder.clearContext();
            } else {
                SecurityContextHolder.getContext().setAuthentication(oldAuthentication);
            }
            TenantContextHolder.setTenantId(oldTenantId);
            TenantContextHolder.setIgnore(oldIgnore);
        }
    }

    private Map<String, Object> configureAnswers(JsonNode arguments) {
        Long questionId = requiredLong(arguments, "questionId");
        JsonNode answers = arguments.path("answers");
        if (!answers.isArray() || answers.isEmpty()) {
            throw new IllegalArgumentException("answers must be a non-empty array");
        }
        List<Long> ids = new ArrayList<>();
        for (JsonNode answer : answers) {
            Map<String, Object> body = body(answer);
            body.put("exercises_id", questionId);
            body.putIfAbsent("sort_no", ids.size());
            ids.add(practiceExercisesAnswerService.create(body));
        }
        return map("questionId", questionId, "answerIds", ids);
    }

    private Map<String, Object> categoryBody(JsonNode arguments) {
        Map<String, Object> body = body(arguments);
        putAlias(body, "categoryName", "category_name");
        putAlias(body, "categoryStatus", "category_status");
        putAlias(body, "fieldType", "field_type");
        putAlias(body, "catalogType", "catalog_type");
        putAlias(body, "sortNo", "sort_no");
        body.putIfAbsent("catalog_type", CATALOG_TYPE_PRACTICE);
        body.putIfAbsent("category_status", Boolean.TRUE);
        body.putIfAbsent("sort_no", 0);
        if (!body.containsKey("category_name")) {
            throw new IllegalArgumentException("categoryName cannot be empty");
        }
        return body;
    }

    private Map<String, Object> questionBody(JsonNode arguments) {
        Map<String, Object> body = body(arguments);
        putAlias(body, "categoryId", "category_id");
        putAlias(body, "questionStem", "question_stem");
        putAlias(body, "questionContent", "question_stem");
        putAlias(body, "questionType", "question_type");
        putAlias(body, "questionStatus", "question_status");
        putAlias(body, "stepId", "step_id");
        putAlias(body, "sortNo", "sort_no");
        putAlias(body, "correctMemo", "correct_memo");
        body.putIfAbsent("question_status", Boolean.TRUE);
        body.putIfAbsent("score", 0);
        body.putIfAbsent("sort_no", 0);
        if (!body.containsKey("category_id")) {
            throw new IllegalArgumentException("categoryId cannot be empty");
        }
        if (!body.containsKey("question_stem")) {
            throw new IllegalArgumentException("questionStem cannot be empty");
        }
        if (!body.containsKey("question_type")) {
            throw new IllegalArgumentException("questionType cannot be empty");
        }
        return body;
    }

    private Map<String, String> params(JsonNode arguments) {
        Map<String, String> result = new LinkedHashMap<>();
        if (arguments == null || arguments.isMissingNode() || arguments.isNull()) {
            return result;
        }
        arguments.fields().forEachRemaining(entry -> {
            if (isContextKey(entry.getKey()) || entry.getValue().isNull() || entry.getValue().isContainerNode()) {
                return;
            }
            result.put(entry.getKey(), entry.getValue().asText());
        });
        result.putIfAbsent("pageNo", "1");
        result.putIfAbsent("pageSize", "10");
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> body(JsonNode arguments) {
        Map<String, Object> result = objectMapper.convertValue(arguments == null || arguments.isMissingNode()
                ? map() : arguments, LinkedHashMap.class);
        result.remove("operatorUserId");
        result.remove("tenantId");
        result.remove("operator");
        return result;
    }

    private void putAlias(Map<String, Object> body, String source, String target) {
        if (body.containsKey(source) && !body.containsKey(target)) {
            body.put(target, body.get(source));
        }
    }

    private boolean isContextKey(String key) {
        return "operatorUserId".equals(key) || "tenantId".equals(key) || "operator".equals(key);
    }

    private Map<String, Object> toolResult(Object value) {
        Object jsonValue = objectMapper.convertValue(value, Object.class);
        return map("structuredContent", jsonValue,
                "content", list(map("type", "text", "text", toJson(jsonValue))));
    }

    private Map<String, Object> tool(String name, String description, Map<String, Object> inputSchema) {
        return map("name", name, "description", description, "inputSchema", inputSchema);
    }

    private Map<String, Object> auditSchema() {
        Map<String, Object> properties = commonContextProperties();
        properties.put("id", map("type", "integer", "description", "审核记录 ID"));
        properties.put("auditStatus", map("type", "integer", "description", "审核状态：2 通过，3 驳回"));
        properties.put("auditReason", map("type", "string", "description", "驳回原因"));
        return schema(properties, list("id", "auditStatus"));
    }

    private Map<String, Object> knowledgeSchema() {
        Map<String, Object> properties = commonContextProperties();
        properties.put("question", map("type", "string", "description", "知识库问题"));
        return schema(properties, list("question"));
    }

    private Map<String, Object> collectNowSchema() {
        Map<String, Object> properties = commonContextProperties();
        properties.put("taskId", map("type", "integer", "description", "采集任务 ID"));
        properties.put("operator", map("type", "string", "description", "执行人标识，默认 mcp"));
        return schema(properties, list("taskId"));
    }

    private Map<String, Object> pageQuerySchema() {
        Map<String, Object> properties = commonContextProperties();
        properties.put("pageNo", map("type", "integer", "description", "页码，默认 1"));
        properties.put("pageSize", map("type", "integer", "description", "每页数量，默认 10，最大 200"));
        properties.put("keyword", map("type", "string", "description", "岗位关键词"));
        properties.put("name", map("type", "string", "description", "岗位名称"));
        properties.put("companyName", map("type", "string", "description", "公司名称"));
        properties.put("sourceCode", map("type", "string", "description", "来源渠道"));
        return schema(properties, Collections.emptyList());
    }

    private Map<String, Object> practiceCategorySchema() {
        Map<String, Object> properties = commonContextProperties();
        properties.put("categoryName", map("type", "string", "description", "分类名称"));
        properties.put("categoryStatus", map("type", "boolean", "description", "是否启用，默认 true"));
        properties.put("fieldType", map("type", "string", "description", "领域类型"));
        properties.put("sortNo", map("type", "integer", "description", "排序号，默认 0"));
        return schema(properties, list("categoryName"));
    }

    private Map<String, Object> practiceQuestionSchema() {
        Map<String, Object> properties = commonContextProperties();
        properties.put("categoryId", map("type", "integer", "description", "练习题分类 ID"));
        properties.put("questionStem", map("type", "string", "description", "题干"));
        properties.put("questionType", map("type", "string", "description", "题型"));
        properties.put("questionStatus", map("type", "boolean", "description", "是否启用，默认 true"));
        properties.put("score", map("type", "number", "description", "分值，默认 0"));
        properties.put("sortNo", map("type", "integer", "description", "排序号，默认 0"));
        properties.put("correctMemo", map("type", "string", "description", "解析说明"));
        return schema(properties, list("categoryId", "questionStem", "questionType"));
    }

    private Map<String, Object> practiceAnswersSchema() {
        Map<String, Object> answerProperties = map();
        answerProperties.put("answerCode", map("type", "string", "description", "答案编码，例如 A/B/C"));
        answerProperties.put("answerContent", map("type", "string", "description", "答案内容"));
        answerProperties.put("isCorrect", map("type", "boolean", "description", "是否正确答案"));
        answerProperties.put("questionType", map("type", "string", "description", "题型"));
        answerProperties.put("sortNo", map("type", "integer", "description", "排序号"));

        Map<String, Object> properties = commonContextProperties();
        properties.put("questionId", map("type", "integer", "description", "题目 ID"));
        properties.put("answers", map("type", "array", "items",
                map("type", "object", "properties", answerProperties, "required", list("answerContent"),
                        "additionalProperties", true)));
        return schema(properties, list("questionId", "answers"));
    }

    private Map<String, Object> commonContextProperties() {
        Map<String, Object> properties = new LinkedHashMap<>();
        properties.put("operatorUserId", map("type", "integer", "description", "可选，后台操作人用户 ID，用于审计字段"));
        properties.put("tenantId", map("type", "integer", "description", "可选，租户 ID，用于多租户数据范围"));
        return properties;
    }

    private Map<String, Object> schema(Map<String, Object> properties, List<Object> required) {
        return map("type", "object", "properties", properties, "required", required, "additionalProperties", true);
    }

    private ResponseEntity<Map<String, Object>> ok(Object id, Object result) {
        return ResponseEntity.ok(map("jsonrpc", JSONRPC, "id", id, "result", result));
    }

    private ResponseEntity<Map<String, Object>> error(Object id, int code, String message, HttpStatus status) {
        return ResponseEntity.status(status).body(map("jsonrpc", JSONRPC, "id", id,
                "error", map("code", code, "message", message)));
    }

    private String requiredText(JsonNode node, String field) {
        String value = text(node, field, null);
        if (StrUtil.isBlank(value)) {
            throw new IllegalArgumentException(field + " cannot be empty");
        }
        return value;
    }

    private Long requiredLong(JsonNode node, String field) {
        Long value = optionalLong(node, field);
        if (value == null) {
            throw new IllegalArgumentException(field + " cannot be empty");
        }
        return value;
    }

    private Long optionalLong(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        if (value == null || value.isNull() || !StrUtil.isNotBlank(value.asText())) {
            return null;
        }
        if (value.isNumber()) {
            return value.longValue();
        }
        try {
            return Long.parseLong(value.asText());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(field + " must be a number");
        }
    }

    private String text(JsonNode node, String field, String defaultValue) {
        JsonNode value = node == null ? null : node.get(field);
        return value == null || value.isNull() ? defaultValue : value.asText();
    }

    private String asString(Object value) {
        return value == null ? null : value.toString();
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception ex) {
            throw new IllegalStateException("Serialize MCP tool result failed", ex);
        }
    }

    private List<Object> list(Object... values) {
        List<Object> list = new ArrayList<>();
        Collections.addAll(list, values);
        return list;
    }

    private Map<String, Object> map(Object... keyValues) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < keyValues.length; i += 2) {
            map.put(String.valueOf(keyValues[i]), keyValues[i + 1]);
        }
        return map;
    }

}
