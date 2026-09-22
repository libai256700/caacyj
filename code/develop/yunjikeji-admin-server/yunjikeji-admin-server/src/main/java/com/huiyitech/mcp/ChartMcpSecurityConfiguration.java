package com.huiyitech.mcp;

import cn.iocoder.yudao.framework.security.config.AuthorizeRequestsCustomizer;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AuthorizeHttpRequestsConfigurer;

@Configuration(proxyBeanMethods = false)
@RequiredArgsConstructor
public class ChartMcpSecurityConfiguration {

    private final ChartMcpProperties properties;

    @Bean("chartMcpAuthorizeRequestsCustomizer")
    public AuthorizeRequestsCustomizer authorizeRequestsCustomizer() {
        return new AuthorizeRequestsCustomizer() {

            @Override
            public void customize(AuthorizeHttpRequestsConfigurer<HttpSecurity>.AuthorizationManagerRequestMatcherRegistry registry) {
                registry.requestMatchers(properties.getEndpoint()).permitAll();
            }

        };
    }

}
