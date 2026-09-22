package com.huiyitech.app.post.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Schema(description = "APP post response")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppPostRespVO {

    @Schema(description = "Post id", example = "1")
    private Long id;

    @Schema(description = "Post name", example = "Java Engineer")
    private String name;

    @Schema(description = "Company name", example = "Huiyi Tech")
    private String companyName;

    @Schema(description = "Post source code", example = "51job")
    private String sourceCode;

    @Schema(description = "External post id", example = "123456")
    private String externalPostId;

    @Schema(description = "Salary range", example = "10k-15k")
    private String salaryRange;

    @Schema(description = "Work area", example = "Shanghai")
    private String workArea;

    @Schema(description = "Publish date", example = "2026-06-12")
    private String publishDate;

    @Schema(description = "Detail URL")
    private String detailUrl;

    @Schema(description = "Post status", example = "true")
    private Boolean status;

    @Schema(description = "Create time")
    private LocalDateTime createTime;
}
