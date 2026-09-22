package com.huiyitech.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.chart.controller.vo.ChartDateRangeReqVO;
import com.huiyitech.chart.controller.vo.ChartOverviewRespVO;
import com.huiyitech.chart.controller.vo.ChartTrendPointRespVO;
import com.huiyitech.chart.service.ChartService;
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

class ChartMcpControllerTest {

    private ChartService chartService;
    private ChartMcpProperties properties;
    private ChartMcpController controller;

    @BeforeEach
    void setUp() {
        chartService = mock(ChartService.class);
        properties = new ChartMcpProperties();
        properties.setEnabled(true);
        properties.setAccessToken("test-token");
        controller = new ChartMcpController(chartService, properties, new ObjectMapper());
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
    void handle_shouldOnlyAllowConfiguredToken() {
        properties.setAccessToken("configured-token");

        ResponseEntity<Map<String, Object>> allowed = controller.handle(headers("configured-token"), request("ping"));
        ResponseEntity<Map<String, Object>> rejected = controller.handle(headers("test-token"), request("ping"));

        assertEquals(HttpStatus.OK, allowed.getStatusCode());
        assertEquals(HttpStatus.UNAUTHORIZED, rejected.getStatusCode());
        assertEquals(-32001, errorCode(rejected));
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
    void handle_shouldSupportPing() {
        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), request("ping"));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<String, Object> result = (Map<String, Object>) response.getBody().get("result");
        assertNotNull(result);
    }

    @Test
    void handle_shouldIgnoreInitializedNotification() {
        Map<String, Object> body = map("jsonrpc", "2.0", "method", "notifications/initialized");

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.NO_CONTENT, response.getStatusCode());
    }

    @Test
    @SuppressWarnings("unchecked")
    void handle_shouldCallOverviewWithDateRange() {
        when(chartService.getOverview(any(ChartDateRangeReqVO.class))).thenReturn(ChartOverviewRespVO.builder()
                .todayActiveUserCount(1L)
                .todayLoginCount(2L)
                .loginTrend(Collections.singletonList(ChartTrendPointRespVO.builder()
                        .date("2026-07-01")
                        .count(2L)
                        .build()))
                .build());
        Map<String, Object> body = request("tools/call");
        body.put("params", map("name", "chart_get_overview",
                "arguments", map("startDate", "2026-06-25", "endDate", "2026-07-01")));

        ResponseEntity<Map<String, Object>> response = controller.handle(headers("test-token"), body);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<String, Object> result = (Map<String, Object>) response.getBody().get("result");
        assertNotNull(result.get("structuredContent"));
        verify(chartService).getOverview(any(ChartDateRangeReqVO.class));
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
