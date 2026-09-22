package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Schema(description = "APP 练习 - 当前练习 Response VO")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeCurrentRespVO {

    @Schema(description = "练习编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "uav-basic-001")
    private String id;

    @Schema(description = "科目", requiredMode = Schema.RequiredMode.REQUIRED, example = "无人机驾驶员理论")
    private String subject;

    @Schema(description = "题库分类", requiredMode = Schema.RequiredMode.REQUIRED, example = "全部题库")
    private String category;

    @Schema(description = "试卷编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "UAV-THEORY-LIVE")
    private String paperNo;

    @Schema(description = "标题", requiredMode = Schema.RequiredMode.REQUIRED, example = "无人机题库练习")
    private String title;

    @Schema(description = "题目数量", requiredMode = Schema.RequiredMode.REQUIRED, example = "100")
    private Integer questionCount;

    @Schema(description = "总分", requiredMode = Schema.RequiredMode.REQUIRED, example = "100")
    private Integer totalScore;

    @Schema(description = "限时分钟数", requiredMode = Schema.RequiredMode.REQUIRED, example = "45")
    private Integer timeLimitMinutes;

    @Schema(description = "阅卷模式", requiredMode = Schema.RequiredMode.REQUIRED, example = "系统阅卷")
    private String gradingMode;

    @Schema(description = "错题数量", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    private Integer wrongQuestionCount;

    @Schema(description = "Practice topic list")
    private List<AppPracticeTopicRespVO> topics;
}
