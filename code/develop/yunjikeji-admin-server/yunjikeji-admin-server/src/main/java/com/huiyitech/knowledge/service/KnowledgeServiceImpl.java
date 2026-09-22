package com.huiyitech.knowledge.service;

import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import com.huiyitech.knowledge.controller.vo.KnowledgeQueryRespVO;
import com.huiyitech.knowledge.dal.KnowledgeGraphClient;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.Collections;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
@RequiredArgsConstructor
public class KnowledgeServiceImpl implements KnowledgeService {

    private final KnowledgeGraphClient knowledgeGraphClient;
    @Override
    public KnowledgeQueryRespVO query(String question) {
        if (!StringUtils.hasText(question)) {
            throw invalidParamException("用户问题不能为空");
        }
        String normalizedQuestion = question.trim();
        Map<String, Object> rawKnowledge = knowledgeGraphClient.query(normalizedQuestion);
        String knowledgeAnswer = stringValue(rawKnowledge.get("answer"));
        if (!StringUtils.hasText(knowledgeAnswer)) {
            knowledgeAnswer = "知识库暂未返回可用答案。";
        }
        String finalAnswer = knowledgeAnswer;

        return KnowledgeQueryRespVO.builder()
                .question(normalizedQuestion)
                .knowledgeAnswer(knowledgeAnswer)
                .finalAnswer(finalAnswer)
                .route(stringValue(rawKnowledge.get("route")))
                .traceId(resolveTraceId(rawKnowledge))
                .llmUsed(Boolean.FALSE)
                .model("")
                .sources(resolveSources(rawKnowledge))
                .rawKnowledge(rawKnowledge)
                .build();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> resolveSources(Map<String, Object> rawKnowledge) {
        Object sources = rawKnowledge.get("sources");
        if (sources instanceof List) {
            return (List<Map<String, Object>>) sources;
        }
        return Collections.emptyList();
    }

    @SuppressWarnings("unchecked")
    private String resolveTraceId(Map<String, Object> rawKnowledge) {
        Object stats = rawKnowledge.get("stats");
        if (stats instanceof Map) {
            Object traceId = ((Map<String, Object>) stats).get("trace_id");
            if (traceId != null) {
                return String.valueOf(traceId);
            }
        }
        return "";
    }

    private String stringValue(Object value) {
        if (value == null) {
            return "";
        }
        if (value instanceof String) {
            return (String) value;
        }
        return JsonUtils.toJsonString(value);
    }
}
