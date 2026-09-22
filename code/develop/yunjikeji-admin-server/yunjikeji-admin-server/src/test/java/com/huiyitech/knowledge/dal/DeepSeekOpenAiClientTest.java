package com.huiyitech.knowledge.dal;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.aiconfig.AiSceneCodes;
import com.huiyitech.aiconfig.dal.dataobject.AiModelConfigDO;
import com.huiyitech.aiconfig.service.AiModelConfigService;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.util.StreamUtils;
import org.springframework.web.client.HttpServerErrorException;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DeepSeekOpenAiClientTest {

    private static final String TEST_API_KEY = "test-api-key";

    private final ObjectMapper objectMapper = new ObjectMapper();
    private Logger logger;
    private ListAppender<ILoggingEvent> appender;
    private HttpServer server;

    @BeforeEach
    void setUp() {
        logger = (Logger) LoggerFactory.getLogger(DeepSeekOpenAiClient.class);
        appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
        logger.detachAppender(appender);
        appender.stop();
    }

    @Test
    void resolveProtocol_shouldPreferAnthropicChannelOverOrdinaryBaseUrl() {
        assertEquals(DeepSeekOpenAiClient.Protocol.ANTHROPIC,
                DeepSeekOpenAiClient.resolveProtocol("ANTHROPIC", "https://gateway.example/api"));
        assertEquals(DeepSeekOpenAiClient.Protocol.ANTHROPIC,
                DeepSeekOpenAiClient.resolveProtocol("anthropic", "https://gateway.example/api"));
    }

    @Test
    void resolveProtocol_shouldPreferOpenAiChannelOverAnthropicUrlShape() {
        assertEquals(DeepSeekOpenAiClient.Protocol.OPENAI_COMPATIBLE,
                DeepSeekOpenAiClient.resolveProtocol("OPENAI_COMPATIBLE", "https://gateway.example/anthropic"));
        assertEquals(DeepSeekOpenAiClient.Protocol.OPENAI_COMPATIBLE,
                DeepSeekOpenAiClient.resolveProtocol("openai-compatible", "https://gateway.example/anthropic"));
    }

    @Test
    void resolveProtocol_shouldUseUrlOnlyWhenChannelIsMissing() {
        assertEquals(DeepSeekOpenAiClient.Protocol.ANTHROPIC,
                DeepSeekOpenAiClient.resolveProtocol("  ", "https://gateway.example/anthropic"));
        assertEquals(DeepSeekOpenAiClient.Protocol.OPENAI_COMPATIBLE,
                DeepSeekOpenAiClient.resolveProtocol(null, "https://gateway.example/v1"));
    }

    @Test
    void anthropicContract_shouldBuildPathHeadersAndBody() throws Exception {
        AiModelConfigDO config = config(AiSceneCodes.KNOWLEDGE_CHAT);

        assertEquals("https://gateway.example/api/v1/messages",
                DeepSeekOpenAiClient.messagesUrl("https://gateway.example/api"));
        HttpHeaders headers = DeepSeekOpenAiClient.requestHeaders(config, true);
        assertEquals(TEST_API_KEY, headers.getFirst("x-api-key"));
        assertEquals("2023-06-01", headers.getFirst("anthropic-version"));
        assertNull(headers.getFirst(HttpHeaders.AUTHORIZATION));

        Map<String, Object> request = DeepSeekOpenAiClient.buildAnthropicRequest(config, "system", "user");
        assertEquals("test-model", request.get("model"));
        assertEquals(2048, request.get("max_tokens"));
        assertEquals("system", request.get("system"));
        assertFalse((Boolean) request.get("stream"));
        assertEquals("user", objectMapper.valueToTree(request).path("messages").get(0).path("role").asText());
    }

    @Test
    void openAiContract_shouldBuildPathHeadersAndBody() {
        AiModelConfigDO config = config(AiSceneCodes.JOB_EXTRACTION);

        assertEquals("https://gateway.example/anthropic/v1/chat/completions",
                DeepSeekOpenAiClient.chatCompletionsUrl("https://gateway.example/anthropic"));
        HttpHeaders headers = DeepSeekOpenAiClient.requestHeaders(config, false);
        assertEquals("Bearer " + TEST_API_KEY, headers.getFirst(HttpHeaders.AUTHORIZATION));
        assertNull(headers.getFirst("x-api-key"));
        assertNull(headers.getFirst("anthropic-version"));

        Map<String, Object> request = DeepSeekOpenAiClient.buildOpenAiRequest(config, "system", "user");
        assertEquals("low", request.get("reasoning_effort"));
        assertFalse((Boolean) request.get("stream"));
        assertFalse(request.containsKey("system"));
        List<?> messages = (List<?>) request.get("messages");
        assertEquals(2, messages.size());
        assertTrue(messages.get(0) instanceof Map);
        assertEquals("system", ((Map<?, ?>) messages.get(0)).get("role"));
        assertEquals("user", ((Map<?, ?>) messages.get(1)).get("role"));
    }

    @Test
    void complete_shouldLogEveryInternalStageWithOneRequestIdAndNoApiKey() throws Exception {
        int port = startServer(200,
                "{\"choices\":[{\"message\":{\"content\":\"generated report\"}}]}");
        String baseUrl = "http://127.0.0.1:" + port;
        DeepSeekOpenAiClient client = client(config(AiSceneCodes.PRACTICE_ASSESSMENT, baseUrl));

        String result = client.complete(AiSceneCodes.PRACTICE_ASSESSMENT,
                "complete system prompt", "complete user prompt", null);

        assertEquals("generated report", result);
        String logs = logs();
        assertTrue(logs.contains("stage=CONFIG_LOOKUP_START"), logs);
        assertTrue(logs.contains("stage=CONFIG_LOOKUP_RETURNED"), logs);
        assertTrue(logs.contains("stage=METHOD_ENTER"), logs);
        assertTrue(logs.contains("stage=CONFIG_VALIDATED"), logs);
        assertTrue(logs.contains("stage=REQUEST_BODY_BUILT"), logs);
        assertTrue(logs.contains("stage=HTTP_REQUEST_BUILT"), logs);
        assertTrue(logs.contains("url=" + baseUrl + "/v1/chat/completions"), logs);
        assertTrue(logs.contains("stage=HTTP_CALL_START"), logs);
        assertTrue(logs.contains("stage=HTTP_CALL_RETURNED"), logs);
        assertTrue(logs.contains("status=200"), logs);
        assertTrue(logs.contains("stage=RESPONSE_BODY_READ"), logs);
        assertTrue(logs.contains("bodyBytes="), logs);
        assertTrue(logs.contains("stage=RESPONSE_DECODED"), logs);
        assertTrue(logs.contains("responseChars="), logs);
        assertTrue(logs.contains("stage=JSON_PARSE_COMPLETED"), logs);
        assertTrue(logs.contains("stage=RETURN"), logs);
        assertTrue(logs.contains("outcome=NON_FALLBACK"), logs);
        assertTrue(logs.contains("stage=FINALLY"), logs);
        assertFalse(logs.contains(TEST_API_KEY), logs);

        Matcher requestIdMatcher = Pattern.compile("requestId=([0-9a-f-]+)").matcher(logs);
        assertTrue(requestIdMatcher.find(), logs);
        String requestId = requestIdMatcher.group(1);
        assertTrue(logs.contains("stage=FINALLY sceneCode=" + AiSceneCodes.PRACTICE_ASSESSMENT
                + " requestId=" + requestId), logs);
    }

    @Test
    void complete_shouldLogExceptionAndFinallyWithoutChangingPropagation() throws Exception {
        int port = startServer(500, "{\"error\":\"upstream unavailable\"}");
        DeepSeekOpenAiClient client = client(config(AiSceneCodes.PRACTICE_ASSESSMENT,
                "http://127.0.0.1:" + port));

        RuntimeException thrown = assertThrows(RuntimeException.class,
                () -> client.complete(AiSceneCodes.PRACTICE_ASSESSMENT,
                        "complete system prompt", "complete user prompt", null));

        assertTrue(thrown instanceof HttpServerErrorException, thrown.getClass().getName());
        String logs = logs();
        assertTrue(logs.contains("stage=EXCEPTION_EXIT"), logs);
        assertTrue(logs.contains("failedStage=HTTP_CALL_START"), logs);
        assertTrue(logs.contains("status=500"), logs);
        assertTrue(logs.contains("stage=FINALLY"), logs);
        assertTrue(logs.contains("outcome=EXCEPTION"), logs);
        assertFalse(logs.contains(TEST_API_KEY), logs);
    }

    private AiModelConfigDO config(String sceneCode) {
        return config(sceneCode, "https://gateway.example/v1");
    }

    private AiModelConfigDO config(String sceneCode, String baseUrl) {
        return AiModelConfigDO.builder()
                .sceneCode(sceneCode)
                .channel("OPENAI_COMPATIBLE")
                .baseUrl(baseUrl)
                .apiKey(TEST_API_KEY)
                .model("test-model")
                .temperature(0.2D)
                .maxTokens(2048)
                .build();
    }

    private DeepSeekOpenAiClient client(AiModelConfigDO config) {
        AiModelConfigService configService = mock(AiModelConfigService.class);
        when(configService.getActiveBySceneCode(config.getSceneCode())).thenReturn(config);
        return new DeepSeekOpenAiClient(configService);
    }

    private int startServer(int status, String responseBody) throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/chat/completions", exchange -> {
            StreamUtils.copyToByteArray(exchange.getRequestBody());
            byte[] bytes = responseBody.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        return server.getAddress().getPort();
    }

    private String logs() {
        StringBuilder logs = new StringBuilder();
        for (ILoggingEvent event : appender.list) {
            logs.append(event.getFormattedMessage()).append('\n');
        }
        return logs.toString();
    }
}
