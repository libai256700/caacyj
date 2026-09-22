package com.huiyitech.app.knowledge.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppKnowledgeAskRespVO {

    @Schema(description = "用户问题")
    private String question;

    @Schema(description = "最终回答")
    private String answer;

    @Schema(description = "知识库原始回答")
    private String knowledgeAnswer;

    @Schema(description = "知识库 traceId")
    private String traceId;

    @Schema(description = "大模型名称")
    private String model;
}
