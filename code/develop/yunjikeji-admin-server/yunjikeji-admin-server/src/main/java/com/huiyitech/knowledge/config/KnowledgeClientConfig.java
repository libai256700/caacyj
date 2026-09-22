package com.huiyitech.knowledge.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
public class KnowledgeClientConfig {

    @Bean
    @Qualifier("knowledgeGraphRestTemplate")
    public RestTemplate knowledgeGraphRestTemplate(KnowledgeProperties properties) {
        return createRestTemplate(properties.getGraph().getTimeoutMillis());
    }

    private RestTemplate createRestTemplate(Integer timeoutMillis) {
        int timeout = timeoutMillis == null || timeoutMillis <= 0 ? 120000 : timeoutMillis;
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(timeout);
        requestFactory.setReadTimeout(timeout);
        return new RestTemplate(requestFactory);
    }
}
