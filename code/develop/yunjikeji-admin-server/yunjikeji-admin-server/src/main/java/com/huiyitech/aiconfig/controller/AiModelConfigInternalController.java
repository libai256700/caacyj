package com.huiyitech.aiconfig.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import com.huiyitech.aiconfig.config.AiModelConfigInternalProperties;
import com.huiyitech.aiconfig.dal.dataobject.AiModelConfigDO;
import com.huiyitech.aiconfig.service.AiModelConfigService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import javax.annotation.security.PermitAll;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

/**
 * Private service-to-service endpoint. It returns only active configuration and
 * is protected by a separate shared token; it is not an admin UI endpoint.
 */
@Tag(name = "内部服务 - AI 模型配置")
@RestController
@RequestMapping("${huiyitech.ai-config.internal.endpoint:/internal/ai/model-config}")
public class AiModelConfigInternalController {

    @Resource
    private AiModelConfigService aiModelConfigService;

    @Resource
    private AiModelConfigInternalProperties properties;

    @GetMapping("/{sceneCode}")
    @PermitAll
    @Operation(summary = "按场景读取启用的 AI 模型配置")
    public ResponseEntity<CommonResult<AiModelConfigInternalRespVO>> get(
            @PathVariable String sceneCode, @RequestHeader Map<String, String> headers) {
        if (!properties.isEnabled() || !isAuthorized(headers)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        AiModelConfigDO config = aiModelConfigService.getActiveBySceneCode(sceneCode);
        if (config == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        return ResponseEntity.ok(success(AiModelConfigInternalRespVO.from(config)));
    }

    private boolean isAuthorized(Map<String, String> headers) {
        if (!StringUtils.hasText(properties.getAccessToken())
                || !StringUtils.hasText(properties.getTokenHeader())) {
            return false;
        }
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            if (entry.getKey() != null && entry.getKey().equalsIgnoreCase(properties.getTokenHeader())) {
                byte[] expected = properties.getAccessToken().getBytes(StandardCharsets.UTF_8);
                byte[] actual = String.valueOf(entry.getValue()).getBytes(StandardCharsets.UTF_8);
                return MessageDigest.isEqual(expected, actual);
            }
        }
        return false;
    }

    public static class AiModelConfigInternalRespVO {

        public String sceneCode;
        public String sceneName;
        public String channel;
        public String baseUrl;
        public String apiKey;
        public String extraConfig;
        public String model;
        public String systemPrompt;
        public Double temperature;
        public Integer maxTokens;
        public Integer timeoutMillis;
        public Integer minReportLength;

        static AiModelConfigInternalRespVO from(AiModelConfigDO config) {
            AiModelConfigInternalRespVO result = new AiModelConfigInternalRespVO();
            result.sceneCode = config.getSceneCode();
            result.sceneName = config.getSceneName();
            result.channel = config.getChannel();
            result.baseUrl = config.getBaseUrl();
            result.apiKey = config.getApiKey();
            result.extraConfig = config.getExtraConfig();
            result.model = config.getModel();
            result.systemPrompt = config.getSystemPrompt();
            result.temperature = config.getTemperature();
            result.maxTokens = config.getMaxTokens();
            result.timeoutMillis = config.getTimeoutMillis();
            result.minReportLength = config.getMinReportLength();
            return result;
        }
    }
}
