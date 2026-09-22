package com.huiyitech.knowledge.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "huiyitech.knowledge")
public class KnowledgeProperties {

    private Graph graph = new Graph();

    @Data
    public static class Graph {

        private String baseUrl = "http://127.0.0.1:5001";

        private String queryPath = "/api/ask";

        private Integer timeoutMillis = 120000;
    }
}
