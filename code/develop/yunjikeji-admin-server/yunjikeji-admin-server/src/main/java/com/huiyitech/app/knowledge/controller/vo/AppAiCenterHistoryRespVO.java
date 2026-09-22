package com.huiyitech.app.knowledge.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Schema(description = "APP AI 中心历史对话")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppAiCenterHistoryRespVO {

    @Schema(description = "历史记录 ID", example = "1001")
    private String id;

    @Schema(description = "用户问题")
    private String question;

    @Schema(description = "AI 回答")
    private String answer;

    @Schema(description = "创建时间")
    private LocalDateTime createTime;
}
