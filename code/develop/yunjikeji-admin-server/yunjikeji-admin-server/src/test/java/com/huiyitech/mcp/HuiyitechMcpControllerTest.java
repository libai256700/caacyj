package com.huiyitech.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
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
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class HuiyitechMcpControllerTest {

    private ChartMcpController chartMcpController;
    private YjAdminMcpController yjAdminMcpController;
    private HuiyitechMcpProperties properties;
    private HuiyitechMcpController controller;

    @BeforeEach
    void setUp() throws Exception {
        chartMcpController = mock(ChartMcpController.class);
        yjAdminMcpController = mock(YjAdminMcpController.class);
        properties = new HuiyitechMcpProperties();
        properties.setEnabled(true);
        properties.setAccessToken("test-token");
        controller = new HuiyitechMcpController(chartMcpController, yjAdminMcpController, properties, new ObjectMapper());

        when(chartMcpController.toolsListResult()).thenReturn(map("tools", Collections.singletonList(
                map("name", "chart_get_overview", "inputSchema", map()))));
        when(yjAdminMcpController.toolsListResult()).thenReturn(map("tools", Collections.singletonList(
                map("name", "knowledge_query", "inputSchema", map()))));
        when(chartMcpController.callTool(any())).thenReturn(map("structuredContent", map("chart", true)));
        when(yjAdminMcpController.callTool(any())).thenReturn(map("structuredContent", map("admin", true)));
    }

    @Test
    void handle_shouldRejectWrongToken() {
        ResponseEntity<Map<String, Object>> response = controller.handle(headers("wrong-token"), request("tools/list"));

        assertEquals(HttpStatus.UNAUTHORIZED, response.getStatusCode());
        assertEquals(-32001, errorCode(response));
    }

    @Test
    @SuppressWarnings("unchecked")
    void handle_shouldListChartAndAdminToolsFromOneEndpoint() {
        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), request("tools/list"));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<String, Object> result = (Map<String, Object>) response.getBody().get("result");
        assertNotNull(result.get("tools"));
    }

    @Test
    void handle_shouldRouteChartToolCall() throws Exception {
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "chart_get_overview", "arguments", map()));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        verify(chartMcpController).callTool(any());
    }

    @Test
    void handle_shouldRouteAdminToolCall() throws Exception {
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "knowledge_query", "arguments", map("question", "hello")));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        verify(yjAdminMcpController).callTool(any());
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
