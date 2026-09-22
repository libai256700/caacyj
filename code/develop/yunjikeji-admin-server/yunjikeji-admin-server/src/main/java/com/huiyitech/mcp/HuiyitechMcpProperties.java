package com.huiyitech.mcp;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "huiyitech.mcp")
public class HuiyitechMcpProperties {

    /**
     * Unified MCP endpoint is closed by default. Enable it only for trusted model-framework deployments.
     */
    private boolean enabled = false;

    /**
     * Shared secret required in the X-Huiyitech-Mcp-Token request header.
     */
    private String accessToken;

    private String tokenHeader = "X-Huiyitech-Mcp-Token";

    private String endpoint = "/mcp";

}
