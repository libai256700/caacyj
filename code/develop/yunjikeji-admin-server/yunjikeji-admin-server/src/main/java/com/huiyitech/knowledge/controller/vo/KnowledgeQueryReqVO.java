package com.huiyitech.knowledge.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;

@Data
public class KnowledgeQueryReqVO {

    @Schema(description = "用户问题", requiredMode = Schema.RequiredMode.REQUIRED, example = "无人机有哪些分类？")
    @NotBlank(message = "用户问题不能为空")
    private String question;
}
