package com.huiyitech.app.practice.controller;

import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionItemRespVO;
import com.huiyitech.app.practice.service.PracticeQuestionVideoService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.*;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

import javax.annotation.Resource;
import javax.annotation.security.PermitAll;
import javax.servlet.http.HttpServletResponse;
import java.net.URI;

@RestController
@TenantIgnore
@ConditionalOnProperty(name = "practice.question-bridge.enabled", havingValue = "true")
public class LocalPracticeQuestionController {
    private static final String CLOUD_BASE = "https://xiaojiapp.caacyj.com/yunjikeji-admin-api";
    private final RestTemplate cloud;
    @Resource
    private ObjectMapper objectMapper;
    @Resource
    private PracticeQuestionVideoService videoService;

    public LocalPracticeQuestionController() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);
        factory.setReadTimeout(15000);
        factory.setOutputStreaming(false);
        cloud = new RestTemplate(factory);
    }

    // The cloud validates the bearer token AND session ownership before any private video is signed.
    @PermitAll
    @GetMapping("/app-api/yj/local-practice/{practiceId}/sessions/{sessionId}/question")
    public JsonNode getQuestion(@PathVariable String practiceId, @PathVariable String sessionId,
            @RequestParam(defaultValue = "practice") String mode,
            @RequestParam(defaultValue = "0") int index,
            @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization,
            @RequestHeader(value = "tenant-id", required = false) String tenantId,
            HttpServletResponse response) {
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        if (authorization == null || !authorization.startsWith("Bearer ") || authorization.length() <= 7) {
            return error(401, "请先登录");
        }
        if (index < 0 || !practiceId.matches("[A-Za-z0-9_-]{1,100}")
                || !sessionId.matches("[A-Za-z0-9_-]{1,200}")) {
            return error(400, "题目参数不正确");
        }
        URI uri = UriComponentsBuilder.fromHttpUrl(CLOUD_BASE)
                .pathSegment("app-api", "yj", "practices", practiceId, "sessions", sessionId, "question")
                .queryParam("mode", mode).queryParam("index", index).build().encode().toUri();
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.AUTHORIZATION, authorization);
        if (tenantId != null) {
            headers.set("tenant-id", tenantId);
        }
        JsonNode body;
        try {
            body = cloud.exchange(uri, HttpMethod.GET, new HttpEntity<Void>(headers), JsonNode.class).getBody();
        } catch (RestClientException exception) {
            return error(502, "云端题目服务暂不可用，请重试");
        }
        if (body == null || !body.has("code")) {
            return error(502, "云端题目响应异常");
        }
        if (body.path("code").asInt(-1) != 0) {
            return body;
        }
        JsonNode question = body.path("data").path("question");
        if (question.isObject()) {
            AppPracticeQuestionItemRespVO item = new AppPracticeQuestionItemRespVO();
            item.setStem(question.path("stem").asText(null));
            if (question.path("exerciseId").canConvertToLong()) {
                item.setExerciseId(question.path("exerciseId").asLong());
            }
            videoService.enrich(item);
            ObjectNode target = (ObjectNode) question;
            target.set("exerciseId", objectMapper.valueToTree(item.getExerciseId()));
            target.set("videoAvailable", objectMapper.valueToTree(item.getVideoAvailable()));
            target.set("videoUrl", objectMapper.valueToTree(item.getVideoUrl()));
            target.set("videoExpiresAt", objectMapper.valueToTree(item.getVideoExpiresAt()));
        }
        return body;
    }

    private ObjectNode error(int code, String message) {
        ObjectNode result = objectMapper.createObjectNode();
        result.put("code", code);
        result.put("msg", message);
        result.putNull("data");
        return result;
    }
}
