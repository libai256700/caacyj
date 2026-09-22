package com.huiyitech.mcp;

import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.chart.controller.vo.ChartDateRangeReqVO;
import com.huiyitech.chart.service.ChartService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class ChartMcpController {

    private static final String JSONRPC = "2.0";
    private static final String PROTOCOL_VERSION = "2024-11-05";

    private final ChartService chartService;
    private final ChartMcpProperties properties;
    private final ObjectMapper objectMapper;

    @PostMapping("${huiyitech.chart.mcp.endpoint:/mcp/chart}")
    public ResponseEntity<Map<String, Object>> handle(@RequestHeader Map<String, String> headers,
                                                      @RequestBody Map<String, Object> request) {
        Object id = request.get("id");
        if (!properties.isEnabled()) {
            return error(id, -32000, "Chart MCP endpoint is disabled", HttpStatus.NOT_FOUND);
        }
        if (!isAuthorized(headers)) {
            return error(id, -32001, "Unauthorized chart MCP request", HttpStatus.UNAUTHORIZED);
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
            return error(id, -32603, "Chart MCP call failed: " + ex.getMessage(), HttpStatus.OK);
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
        result.put("serverInfo", map("name", "huiyitech-chart-mcp", "version", "1.0.0"));
        return result;
    }

    Map<String, Object> toolsListResult() {
        Map<String, Object> result = map();
        List<Map<String, Object>> tools = new ArrayList<>();
        tools.add(tool("chart_get_overview", "获取管理首页完整数据看板：活跃、登录、注册、知识图谱、做题统计和趋势。", true));
        tools.add(tool("chart_get_today_active_user_count", "获取当天有登录行为的活跃学员人数。", false));
        tools.add(tool("chart_get_today_login_count", "获取当天学员登录总次数。", false));
        tools.add(tool("chart_get_login_trend", "按天获取登录趋势，日期窗口最多 7 天。", true));
        tools.add(tool("chart_get_today_register_count", "获取当天注册学员数量。", false));
        tools.add(tool("chart_get_total_register_count", "获取注册学员总数。", false));
        tools.add(tool("chart_get_register_trend", "按天获取注册趋势，日期窗口最多 7 天。", true));
        tools.add(tool("chart_get_today_knowledge_call_count", "获取当天知识图谱接口调用次数。", false));
        tools.add(tool("chart_get_total_knowledge_call_count", "获取知识图谱接口累计调用次数。", false));
        tools.add(tool("chart_get_knowledge_call_trend", "按天获取知识图谱调用趋势，日期窗口最多 7 天。", true));
        tools.add(tool("chart_get_practice_stats", "获取学员做题统计，包含当天答题数、答题总数、正确数、错误数和正确率。", true));
        tools.add(tool("chart_get_practice_trend", "按天获取学员答题趋势，日期窗口最多 7 天。", true));
        result.put("tools", tools);
        return result;
    }

    Map<String, Object> callTool(Object paramsObject) {
        JsonNode params = objectMapper.valueToTree(paramsObject == null ? map() : paramsObject);
        String name = text(params, "name", null);
        JsonNode arguments = params.path("arguments");
        Object value = TenantUtils.executeIgnore(() -> callChartTool(name, arguments));
        return toolResult(value);
    }

    private Object callChartTool(String name, JsonNode arguments) {
        Object value;
        if ("chart_get_overview".equals(name)) {
            value = chartService.getOverview(range(arguments));
        } else if ("chart_get_today_active_user_count".equals(name)) {
            value = chartService.getTodayActiveUserCount();
        } else if ("chart_get_today_login_count".equals(name)) {
            value = chartService.getTodayLoginCount();
        } else if ("chart_get_login_trend".equals(name)) {
            value = chartService.getLoginTrend(range(arguments));
        } else if ("chart_get_today_register_count".equals(name)) {
            value = chartService.getTodayRegisterCount();
        } else if ("chart_get_total_register_count".equals(name)) {
            value = chartService.getTotalRegisterCount();
        } else if ("chart_get_register_trend".equals(name)) {
            value = chartService.getRegisterTrend(range(arguments));
        } else if ("chart_get_today_knowledge_call_count".equals(name)) {
            value = chartService.getTodayKnowledgeCallCount();
        } else if ("chart_get_total_knowledge_call_count".equals(name)) {
            value = chartService.getTotalKnowledgeCallCount();
        } else if ("chart_get_knowledge_call_trend".equals(name)) {
            value = chartService.getKnowledgeCallTrend(range(arguments));
        } else if ("chart_get_practice_stats".equals(name)) {
            value = chartService.getPracticeStats(range(arguments));
        } else if ("chart_get_practice_trend".equals(name)) {
            value = chartService.getPracticeTrend(range(arguments));
        } else {
            throw new IllegalArgumentException("Unknown chart MCP tool: " + name);
        }
        return value;
    }

    private ChartDateRangeReqVO range(JsonNode arguments) {
        ChartDateRangeReqVO reqVO = new ChartDateRangeReqVO();
        if (arguments == null || arguments.isMissingNode() || arguments.isNull()) {
            return reqVO;
        }
        String startDate = text(arguments, "startDate", null);
        String endDate = text(arguments, "endDate", null);
        if (StrUtil.isNotBlank(startDate)) {
            reqVO.setStartDate(LocalDate.parse(startDate));
        }
        if (StrUtil.isNotBlank(endDate)) {
            reqVO.setEndDate(LocalDate.parse(endDate));
        }
        return reqVO;
    }

    private Map<String, Object> toolResult(Object value) {
        Map<String, Object> result = map();
        Object jsonValue = objectMapper.convertValue(value, Object.class);
        result.put("structuredContent", jsonValue);
        result.put("content", list(map("type", "text", "text", toJson(jsonValue))));
        return result;
    }

    private Map<String, Object> tool(String name, String description, boolean withDateRange) {
        Map<String, Object> tool = map();
        tool.put("name", name);
        tool.put("description", description);
        tool.put("inputSchema", withDateRange ? dateRangeSchema() : emptySchema());
        return tool;
    }

    private Map<String, Object> dateRangeSchema() {
        Map<String, Object> properties = map();
        properties.put("startDate", map("type", "string", "description", "开始日期，格式 yyyy-MM-dd"));
        properties.put("endDate", map("type", "string", "description", "结束日期，格式 yyyy-MM-dd；和 startDate 的窗口最多 7 天"));
        return map("type", "object", "properties", properties, "additionalProperties", false);
    }

    private Map<String, Object> emptySchema() {
        return map("type", "object", "properties", map(), "additionalProperties", false);
    }

    private ResponseEntity<Map<String, Object>> ok(Object id, Object result) {
        return ResponseEntity.ok(map("jsonrpc", JSONRPC, "id", id, "result", result));
    }

    private ResponseEntity<Map<String, Object>> error(Object id, int code, String message, HttpStatus status) {
        return ResponseEntity.status(status).body(map("jsonrpc", JSONRPC, "id", id,
                "error", map("code", code, "message", message)));
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
        for (Object value : values) {
            list.add(value);
        }
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
