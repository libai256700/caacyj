package com.huiyitech.aiconfig.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Access settings for the private configuration endpoint used by trusted services. */
@Data
@Component
@ConfigurationProperties(prefix = "huiyitech.ai-config.internal")
public class AiModelConfigInternalProperties {

    private boolean enabled = false;

    private String endpoint = "/internal/ai/model-config";

    private String tokenHeader = "X-Huiyitech-Ai-Config-Token";

    private String accessToken;
}
