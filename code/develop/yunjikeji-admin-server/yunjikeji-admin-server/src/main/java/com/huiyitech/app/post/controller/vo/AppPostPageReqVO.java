package com.huiyitech.app.post.controller.vo;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Schema(description = "APP post page request")
@Data
@EqualsAndHashCode(callSuper = true)
public class AppPostPageReqVO extends PageParam {

    @Schema(description = "Keyword", example = "Java")
    private String keyword;

    @Schema(description = "Post name filter, __other__ means excluding 飞手/工程师/教培", example = "飞手")
    private String name;

    @Schema(description = "Post source code", example = "51job")
    private String sourceCode;

    @Schema(description = "Work area", example = "Shanghai")
    private String workArea;

    @Schema(description = "Salary range filter", example = "5000-10000")
    private String salaryRange;

    @Schema(description = "Post status", example = "true")
    private Boolean status;
}
