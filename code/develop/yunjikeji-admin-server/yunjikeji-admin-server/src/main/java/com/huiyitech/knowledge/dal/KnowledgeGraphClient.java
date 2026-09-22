package com.huiyitech.knowledge.dal;

import com.huiyitech.knowledge.config.KnowledgeProperties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Repository;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Map;

@Repository
public class KnowledgeGraphClient {

    private final RestTemplate restTemplate;
    private final KnowledgeProperties properties;

    public KnowledgeGraphClient(@Qualifier("knowledgeGraphRestTemplate") RestTemplate restTemplate,
                                KnowledgeProperties properties) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> query(String question) {
        URI uri = UriComponentsBuilder.fromHttpUrl(properties.getGraph().getBaseUrl())
                .path(properties.getGraph().getQueryPath())
                .queryParam("q", question)
                .build()
                .encode(StandardCharsets.UTF_8)
                .toUri();
        ResponseEntity<Map> response = restTemplate.getForEntity(uri, Map.class);
        Map<String, Object> body = response.getBody();
        return body == null ? Collections.emptyMap() : body;
    }
}
