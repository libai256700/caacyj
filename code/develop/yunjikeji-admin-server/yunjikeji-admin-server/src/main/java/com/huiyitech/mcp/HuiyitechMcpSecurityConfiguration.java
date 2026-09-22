package com.huiyitech.mcp;

import cn.iocoder.yudao.framework.security.config.AuthorizeRequestsCustomizer;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AuthorizeHttpRequestsConfigurer;

@Configuration(proxyBeanMethods = false)
@RequiredArgsConstructor
public class HuiyitechMcpSecurityConfiguration {

    private final HuiyitechMcpProperties properties;

    @Bean("huiyitechMcpAuthorizeRequestsCustomizer")
    public AuthorizeRequestsCustomizer authorizeRequestsCustomizer() {
        return new AuthorizeRequestsCustomizer() {

            @Override
            public void customize(AuthorizeHttpRequestsConfigurer<HttpSecurity>.AuthorizationManagerRequestMatcherRegistry registry) {
                registry.requestMatchers(properties.getEndpoint()).permitAll();
            }

        };
    }

}
