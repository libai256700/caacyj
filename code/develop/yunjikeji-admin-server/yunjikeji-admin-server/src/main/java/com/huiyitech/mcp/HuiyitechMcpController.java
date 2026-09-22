package com.huiyitech.mcp;

import cn.hutool.core.util.StrUtil;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class HuiyitechMcpController {

    private static final String JSONRPC = "2.0";
    private static final String PROTOCOL_VERSION = "2024-11-05";

    private final ChartMcpController chartMcpController;
    private final YjAdminMcpController yjAdminMcpController;
    private final HuiyitechMcpProperties properties;
    private final ObjectMapper objectMapper;

    @PostMapping("${huiyitech.mcp.endpoint:/mcp}")
    public ResponseEntity<Map<String, Object>> handle(@RequestHeader Map<String, String> headers,
                                                      @RequestBody Map<String, Object> request) {
        Object id = request.get("id");
        if (!properties.isEnabled()) {
            return error(id, -32000, "Huiyitech MCP endpoint is disabled", HttpStatus.NOT_FOUND);
        }
        if (!isAuthorized(headers)) {
            return error(id, -32001, "Unauthorized Huiyitech MCP request", HttpStatus.UNAUTHORIZED);
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
            return error(id, -32603, "Huiyitech MCP call failed: " + ex.getMessage(), HttpStatus.OK);
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
        result.put("serverInfo", map("name", "huiyitech-mcp", "version", "1.0.0"));
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> toolsListResult() {
        List<Map<String, Object>> tools = new ArrayList<>();
        tools.addAll((List<Map<String, Object>>) chartMcpController.toolsListResult().get("tools"));
        tools.addAll((List<Map<String, Object>>) yjAdminMcpController.toolsListResult().get("tools"));
        return map("tools", tools);
    }

    private Map<String, Object> callTool(Object paramsObject) throws Exception {
        JsonNode params = objectMapper.valueToTree(paramsObject == null ? map() : paramsObject);
        String name = text(params, "name", null);
        if (StrUtil.isBlank(name)) {
            throw new IllegalArgumentException("MCP tool name cannot be empty");
        }
        if (name.startsWith("chart_")) {
            return chartMcpController.callTool(paramsObject);
        }
        return yjAdminMcpController.callTool(paramsObject);
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

    private Map<String, Object> map(Object... keyValues) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < keyValues.length; i += 2) {
            map.put(String.valueOf(keyValues[i]), keyValues[i + 1]);
        }
        return map;
    }

}
