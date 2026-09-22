package com.huiyitech.app.knowledge.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;

@Data
public class AppKnowledgeAskReqVO {

    @Schema(description = "用户问题", requiredMode = Schema.RequiredMode.REQUIRED, example = "无人机是什么？")
    @NotBlank(message = "用户问题不能为空")
    private String question;
}
