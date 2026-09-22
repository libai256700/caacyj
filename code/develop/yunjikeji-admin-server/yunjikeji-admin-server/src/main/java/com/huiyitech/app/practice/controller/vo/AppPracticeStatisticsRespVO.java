package com.huiyitech.app.practice.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "APP practice statistics")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPracticeStatisticsRespVO {

    @Schema(description = "Total practice count", example = "128")
    private Integer practiceTotal;

    @Schema(description = "Total answered question count", example = "1248")
    private Integer answerTotal;

    @Schema(description = "Accuracy percent", example = "86")
    private Integer accuracy;

    @Schema(description = "Continuous practice days", example = "12")
    private Integer streakDays;

    @Schema(description = "Total wrong question count", example = "36")
    private Integer wrongTotal;
}
