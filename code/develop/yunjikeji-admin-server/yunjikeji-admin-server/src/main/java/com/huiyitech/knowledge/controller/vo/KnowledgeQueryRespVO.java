package com.huiyitech.knowledge.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class KnowledgeQueryRespVO {

    @Schema(description = "用户问题")
    private String question;

    @Schema(description = "知识库原始回答")
    private String knowledgeAnswer;

    @Schema(description = "DeepSeek 整理后的最终回答")
    private String finalAnswer;

    @Schema(description = "知识库路由")
    private String route;

    @Schema(description = "知识库 traceId")
    private String traceId;

    @Schema(description = "是否已调用大模型")
    private Boolean llmUsed;

    @Schema(description = "大模型名称")
    private String model;

    @Schema(description = "知识库来源")
    private List<Map<String, Object>> sources;

    @Schema(description = "知识库原始返回")
    private Map<String, Object> rawKnowledge;
}
