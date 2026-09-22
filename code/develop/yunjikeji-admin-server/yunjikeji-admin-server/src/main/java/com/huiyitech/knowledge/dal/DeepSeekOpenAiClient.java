package com.huiyitech.knowledge.dal;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.aiconfig.AiSceneCodes;
import com.huiyitech.aiconfig.dal.dataobject.AiModelConfigDO;
import com.huiyitech.aiconfig.service.AiModelConfigService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Repository;
import org.springframework.util.StringUtils;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestTemplate;

import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Repository
public class DeepSeekOpenAiClient {

    private static final Logger log = LoggerFactory.getLogger(DeepSeekOpenAiClient.class);
    private static final String REQUEST_ID_MDC_KEY = "deepSeekRequestId";
    private static final String ANTHROPIC_VERSION = "2023-06-01";
    private static final String CHANNEL_ANTHROPIC = "ANTHROPIC";
    private static final String CHANNEL_OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE";
    private static final int DEFAULT_ANTHROPIC_MAX_TOKENS = 4096;
    private static final int DEFAULT_TIMEOUT_MILLIS = 300000;

    private final AiModelConfigService aiModelConfigService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DeepSeekOpenAiClient(AiModelConfigService aiModelConfigService) {
        this.aiModelConfigService = aiModelConfigService;
    }

    public String complete(String question, String knowledgeAnswer, Map<String, Object> rawKnowledge) {
        AiModelConfigDO config = aiModelConfigService.getActiveBySceneCode(AiSceneCodes.KNOWLEDGE_CHAT);
        if (!isUsable(config)) {
            return knowledgeAnswer;
        }
        String userPrompt = "用户问题：\n" + question + "\n\n知识库回答：\n" + knowledgeAnswer
                + "\n\n知识库原始结果摘要：\n" + String.valueOf(rawKnowledge);
        return complete(AiSceneCodes.KNOWLEDGE_CHAT, config.getSystemPrompt(), userPrompt, knowledgeAnswer);
    }

    public String complete(String systemPrompt, String userPrompt, String model, Double temperature,
                           Integer maxTokens, String fallback) {
        return complete(AiSceneCodes.KNOWLEDGE_CHAT, systemPrompt, userPrompt, fallback);
    }

    public String complete(String sceneCode, String systemPrompt, String userPrompt, String fallback) {
        String requestId = UUID.randomUUID().toString();
        String previousRequestId = MDC.get(REQUEST_ID_MDC_KEY);
        MDC.put(REQUEST_ID_MDC_KEY, requestId);
        try {
            long lookupStartNanos = System.nanoTime();
            log.info("DeepSeek complete stage=CONFIG_LOOKUP_START sceneCode={} requestId={}",
                    sceneCode, requestId);
            AiModelConfigDO config;
            try {
                config = aiModelConfigService.getActiveBySceneCode(sceneCode);
            } catch (RuntimeException ex) {
                log.error("DeepSeek complete stage=CONFIG_LOOKUP_FAILED sceneCode={} requestId={} "
                                + "elapsedMs={} exceptionType={} exceptionMessage={}",
                        sceneCode, requestId, elapsedMillis(lookupStartNanos), ex.getClass().getName(),
                        exceptionMessageForLog(ex, null));
                throw ex;
            }
            log.info("DeepSeek complete stage=CONFIG_LOOKUP_RETURNED sceneCode={} requestId={} "
                            + "elapsedMs={} usable={}",
                    sceneCode, requestId, elapsedMillis(lookupStartNanos), isUsable(config));
            if (!isUsable(config)) {
                log.warn("DeepSeek complete stage=CONFIG_UNUSABLE_RETURN sceneCode={} requestId={} outcome=FALLBACK",
                        sceneCode, requestId);
                return fallback;
            }
            return complete(config, systemPrompt, userPrompt, fallback);
        } finally {
            if (previousRequestId == null) {
                MDC.remove(REQUEST_ID_MDC_KEY);
            } else {
                MDC.put(REQUEST_ID_MDC_KEY, previousRequestId);
            }
        }
    }

    public String completeRequired(String sceneCode, String systemPrompt, String userPrompt) {
        AiModelConfigDO config = aiModelConfigService.getRequiredActiveBySceneCode(sceneCode);
        return complete(config, systemPrompt, userPrompt, "");
    }

    private String complete(AiModelConfigDO config, String systemPrompt, String userPrompt, String fallback) {
        long totalStartNanos = System.nanoTime();
        String requestId = MDC.get(REQUEST_ID_MDC_KEY);
        if (!StringUtils.hasText(requestId)) {
            requestId = UUID.randomUUID().toString();
        }
        String sceneCode = config != null && StringUtils.hasText(config.getSceneCode())
                ? config.getSceneCode() : "unknown";
        String apiKey = config == null ? null : config.getApiKey();
        String currentStage = "METHOD_ENTER";
        String outcome = "IN_PROGRESS";
        log.info("DeepSeek complete stage={} sceneCode={} requestId={} systemPromptChars={} "
                        + "userPromptChars={} fallbackChars={}",
                currentStage, sceneCode, requestId, textLength(systemPrompt), textLength(userPrompt),
                textLength(fallback));
        try {
            boolean usableConfig = isUsable(config);
            Protocol protocol = config == null ? null : resolveProtocol(config.getChannel(), config.getBaseUrl());
            boolean anthropic = protocol == Protocol.ANTHROPIC;
            int timeoutMillis = config == null || config.getTimeoutMillis() == null
                    || config.getTimeoutMillis() <= 0 ? DEFAULT_TIMEOUT_MILLIS : config.getTimeoutMillis();
            currentStage = "CONFIG_VALIDATED";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} usable={} protocol={} "
                            + "model={} timeoutMillis={} apiKeyPresent={}",
                    currentStage, sceneCode, requestId, usableConfig, protocol,
                    config == null ? null : config.getModel(), timeoutMillis, StringUtils.hasText(apiKey));

            long requestBodyStartNanos = System.nanoTime();
            String resolvedSystemPrompt = StringUtils.hasText(systemPrompt) ? systemPrompt : config.getSystemPrompt();
            Map<String, Object> request = anthropic
                    ? buildAnthropicRequest(config, resolvedSystemPrompt, userPrompt)
                    : buildOpenAiRequest(config, resolvedSystemPrompt, userPrompt);
            currentStage = "REQUEST_BODY_BUILT";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} requestFields={} "
                            + "systemPromptChars={} userPromptChars={} elapsedMs={}",
                    currentStage, sceneCode, requestId, request.keySet(), textLength(resolvedSystemPrompt),
                    textLength(userPrompt), elapsedMillis(requestBodyStartNanos));

            long httpRequestStartNanos = System.nanoTime();
            HttpHeaders headers = requestHeaders(config, anthropic);
            String url = anthropic ? messagesUrl(config.getBaseUrl()) : chatCompletionsUrl(config.getBaseUrl());
            HttpEntity<Map<String, Object>> httpRequest = new HttpEntity<>(request, headers);
            RestTemplate restTemplate = createRestTemplate(config.getTimeoutMillis());
            currentStage = "HTTP_REQUEST_BUILT";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} url={} timeoutMillis={} elapsedMs={}",
                    currentStage, sceneCode, requestId, urlForLog(url), timeoutMillis,
                    elapsedMillis(httpRequestStartNanos));

            long httpStartNanos = System.nanoTime();
            currentStage = "HTTP_CALL_START";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} url={} totalElapsedMs={}",
                    currentStage, sceneCode, requestId, urlForLog(url), elapsedMillis(totalStartNanos));

            ResponseEntity<byte[]> response = restTemplate.postForEntity(url, httpRequest, byte[].class);
            long httpReturnedAtNanos = System.nanoTime();
            int responseStatus = response.getStatusCode().value();
            currentStage = "HTTP_CALL_RETURNED";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} status={} httpElapsedMs={} "
                            + "totalElapsedMs={}",
                    currentStage, sceneCode, requestId, responseStatus,
                    elapsedMillis(httpStartNanos, httpReturnedAtNanos),
                    elapsedMillis(totalStartNanos, httpReturnedAtNanos));

            long bodyReadStartNanos = System.nanoTime();
            byte[] responseBody = response.getBody();
            long bodyReadEndNanos = System.nanoTime();
            currentStage = "RESPONSE_BODY_READ";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} status={} bodyBytes={} "
                            + "sinceHttpStartMs={} sinceHttpReturnMs={} bodyReadElapsedMs={}",
                    currentStage, sceneCode, requestId, responseStatus,
                    responseBody == null ? 0 : responseBody.length,
                    elapsedMillis(httpStartNanos, bodyReadEndNanos),
                    elapsedMillis(httpReturnedAtNanos, bodyReadEndNanos),
                    elapsedMillis(bodyReadStartNanos, bodyReadEndNanos));


            long decodeStartNanos = System.nanoTime();
            String decodedBody = decodeUtf8(responseBody);
            long decodeEndNanos = System.nanoTime();
            currentStage = "RESPONSE_DECODED";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} responseChars={} decodeElapsedMs={}",
                    currentStage, sceneCode, requestId, textLength(decodedBody),
                    elapsedMillis(decodeStartNanos, decodeEndNanos));

            long parseStartNanos = System.nanoTime();
            String result = parseContent(decodedBody, fallback);
            long parseEndNanos = System.nanoTime();
            currentStage = "JSON_PARSE_COMPLETED";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} resultChars={} parseElapsedMs={}",
                    currentStage, sceneCode, requestId, textLength(result),
                    elapsedMillis(parseStartNanos, parseEndNanos));

            outcome = Objects.equals(result, fallback) ? "FALLBACK" : "NON_FALLBACK";
            currentStage = "RETURN";
            log.info("DeepSeek complete stage={} sceneCode={} requestId={} outcome={} totalElapsedMs={}",
                    currentStage, sceneCode, requestId, outcome, elapsedMillis(totalStartNanos));
            return result;
        } catch (RuntimeException ex) {
            boolean timeout = isTimeout(ex);
            outcome = timeout ? "TIMEOUT" : "EXCEPTION";
            Integer httpStatus = ex instanceof HttpStatusCodeException
                    ? ((HttpStatusCodeException) ex).getStatusCode().value() : null;
            log.error("DeepSeek complete stage={} sceneCode={} requestId={} failedStage={} status={} "
                            + "totalElapsedMs={} exceptionType={} exceptionMessage={}",
                    timeout ? "TIMEOUT_EXIT" : "EXCEPTION_EXIT", sceneCode, requestId, currentStage, httpStatus,
                    elapsedMillis(totalStartNanos), ex.getClass().getName(), exceptionMessageForLog(ex, apiKey));
            throw ex;
        } finally {
            log.info("DeepSeek complete stage=FINALLY sceneCode={} requestId={} outcome={} totalElapsedMs={}",
                    sceneCode, requestId, outcome, elapsedMillis(totalStartNanos));
        }
    }

    private static int textLength(String value) {
        return value == null ? 0 : value.length();
    }

    private static long elapsedMillis(long startNanos) {
        return elapsedMillis(startNanos, System.nanoTime());
    }

    private static long elapsedMillis(long startNanos, long endNanos) {
        return TimeUnit.NANOSECONDS.toMillis(Math.max(0L, endNanos - startNanos));
    }

    private static boolean isTimeout(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof SocketTimeoutException
                    || current.getClass().getSimpleName().toLowerCase(Locale.ROOT).contains("timeout")) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static String urlForLog(String url) {
        if (url == null) {
            return null;
        }
        int queryIndex = url.indexOf('?');
        return queryIndex < 0 ? url : url.substring(0, queryIndex) + "?<redacted>";
    }

    private static String exceptionMessageForLog(Throwable error, String apiKey) {
        String message = error == null ? null : error.getMessage();
        if (!StringUtils.hasText(message)) {
            return message;
        }
        if (StringUtils.hasText(apiKey)) {
            message = message.replace(apiKey, "<redacted>");
        }
        message = message.replaceAll("(?i)(https?://[^\\s?]+)\\?[^\\s]+", "$1?<redacted>");
        return message.replaceAll(
                "(?i)((?:api[-_]?key|access[-_]?token|token|secret)=)[^\\s&,]+", "$1<redacted>");
    }

    private RestTemplate createRestTemplate(Integer timeoutMillis) {
        int timeout = timeoutMillis == null || timeoutMillis <= 0 ? DEFAULT_TIMEOUT_MILLIS : timeoutMillis;
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(timeout);
        requestFactory.setReadTimeout(timeout);
        return new RestTemplate(requestFactory);
    }

    static Map<String, Object> buildAnthropicRequest(AiModelConfigDO config, String systemPrompt, String userPrompt) {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("model", config.getModel());
        request.put("max_tokens", positiveMaxTokens(config.getMaxTokens()));
        request.put("temperature", config.getTemperature());
        request.put("stream", false);
        request.put("system", systemPrompt == null ? "" : systemPrompt);
        request.put("messages", Collections.singletonList(message("user", userPrompt)));
        return request;
    }

    static Map<String, Object> buildOpenAiRequest(AiModelConfigDO config, String systemPrompt, String userPrompt) {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("model", config.getModel());
        if (config.getTemperature() != null) {
            request.put("temperature", config.getTemperature());
        }
        if (config.getMaxTokens() != null && config.getMaxTokens() > 0) {
            request.put("max_tokens", config.getMaxTokens());
        }
        if (AiSceneCodes.JOB_EXTRACTION.equals(config.getSceneCode())) {
            request.put("reasoning_effort", "low");
        }
        request.put("stream", false);
        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(message("system", systemPrompt));
        messages.add(message("user", userPrompt));
        request.put("messages", messages);
        return request;
    }

    static HttpHeaders requestHeaders(AiModelConfigDO config, boolean anthropic) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(Collections.singletonList(MediaType.APPLICATION_JSON));
        headers.set(HttpHeaders.USER_AGENT, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
        if (anthropic) {
            headers.set("x-api-key", config.getApiKey());
            headers.set("anthropic-version", ANTHROPIC_VERSION);
        } else {
            headers.setBearerAuth(config.getApiKey());
        }
        return headers;
    }

    private static int positiveMaxTokens(Integer configured) {
        return configured != null && configured > 0 ? configured : DEFAULT_ANTHROPIC_MAX_TOKENS;
    }

    private boolean isUsable(AiModelConfigDO config) {
        return config != null && StringUtils.hasText(config.getBaseUrl())
                && StringUtils.hasText(config.getApiKey())
                && StringUtils.hasText(config.getModel());
    }

    private static Map<String, String> message(String role, String content) {
        Map<String, String> message = new LinkedHashMap<>();
        message.put("role", role);
        message.put("content", content == null ? "" : content);
        return message;
    }

    @SuppressWarnings("unchecked")
    private String parseContent(Map<String, Object> body, String fallback) {
        if (body == null) {
            return fallback;
        }
        Object choicesObj = body.get("choices");
        if (!(choicesObj instanceof List) || ((List<?>) choicesObj).isEmpty()) {
            return fallback;
        }
        Object firstChoice = ((List<?>) choicesObj).get(0);
        if (!(firstChoice instanceof Map)) {
            return fallback;
        }
        Object messageObj = ((Map<String, Object>) firstChoice).get("message");
        if (!(messageObj instanceof Map)) {
            return fallback;
        }
        Object content = ((Map<String, Object>) messageObj).get("content");
        return content == null || !StringUtils.hasText(String.valueOf(content)) ? fallback : String.valueOf(content);
    }

    private String parseContent(String body, String fallback) {
        if (!StringUtils.hasText(body)) {
            return fallback;
        }
        String text = body.trim();
        try {
            if (!text.startsWith("data:")) {
                return parseJsonContent(text, fallback);
            }
            StringBuilder content = new StringBuilder();
            String[] lines = text.split("\\r?\\n");
            for (String line : lines) {
                String value = line.trim();
                if (!value.startsWith("data:")) {
                    continue;
                }
                value = value.substring("data:".length()).trim();
                if (!StringUtils.hasText(value) || "[DONE]".equals(value)) {
                    continue;
                }
                String part = parseJsonContent(value, "");
                if (StringUtils.hasText(part)) {
                    content.append(part);
                }
            }
            return StringUtils.hasText(content.toString()) ? content.toString() : fallback;
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private String decodeUtf8(byte[] body) {
        return body == null || body.length == 0 ? "" : new String(body, StandardCharsets.UTF_8);
    }

    private String parseJsonContent(String json, String fallback) throws Exception {
        JsonNode root = objectMapper.readTree(json);
        JsonNode anthropicContent = root.path("content");
        if (anthropicContent.isArray()) {
            StringBuilder text = new StringBuilder();
            for (JsonNode block : anthropicContent) {
                if ("text".equals(block.path("type").asText()) && StringUtils.hasText(block.path("text").asText())) {
                    text.append(block.path("text").asText());
                }
            }
            return StringUtils.hasText(text.toString()) ? text.toString() : fallback;
        }
        JsonNode choices = root.path("choices");
        if (!choices.isArray() || choices.isEmpty()) {
            return fallback;
        }
        JsonNode first = choices.get(0);
        JsonNode content = first.path("message").path("content");
        if (content.isMissingNode() || content.isNull()) {
            content = first.path("delta").path("content");
        }
        return content.isMissingNode() || content.isNull() || !StringUtils.hasText(content.asText())
                ? fallback
                : content.asText();
    }

    private static String trimRight(String value) {
        if (!StringUtils.hasText(value)) {
            return "https://api.deepseek.com/anthropic";
        }
        String result = value.trim();
        while (result.endsWith("/")) {
            result = result.substring(0, result.length() - 1);
        }
        return result;
    }

    static String chatCompletionsUrl(String baseUrl) {
        String base = trimRight(baseUrl);
        return base.endsWith("/v1") ? base + "/chat/completions" : base + "/v1/chat/completions";
    }

    static String messagesUrl(String baseUrl) {
        String base = trimRight(baseUrl);
        return base.endsWith("/v1") ? base + "/messages" : base + "/v1/messages";
    }

    private static boolean isAnthropicBaseUrl(String baseUrl) {
        String base = trimRight(baseUrl).toLowerCase(Locale.ROOT);
        return base.endsWith("/anthropic") || base.contains("/anthropic/");
    }

    static Protocol resolveProtocol(String configuredChannel, String baseUrl) {
        if (StringUtils.hasText(configuredChannel)) {
            String channel = configuredChannel.trim().replace('-', '_').toUpperCase(Locale.ROOT);
            if (CHANNEL_ANTHROPIC.equals(channel)) {
                return Protocol.ANTHROPIC;
            }
            if (CHANNEL_OPENAI_COMPATIBLE.equals(channel)) {
                return Protocol.OPENAI_COMPATIBLE;
            }
            return Protocol.OPENAI_COMPATIBLE;
        }
        return isAnthropicBaseUrl(baseUrl) ? Protocol.ANTHROPIC : Protocol.OPENAI_COMPATIBLE;
    }

    enum Protocol {
        ANTHROPIC,
        OPENAI_COMPATIBLE
    }
}
