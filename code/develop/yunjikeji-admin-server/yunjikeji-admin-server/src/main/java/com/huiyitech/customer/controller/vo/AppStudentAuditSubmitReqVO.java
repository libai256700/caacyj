package com.huiyitech.customer.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotNull;

@Schema(description = "用户 App - 学员提交审核 Request VO")
@Data
public class AppStudentAuditSubmitReqVO {

    @Schema(description = "企业租户编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "企业租户编号不能为空")
    private Long tenantId;

    @Schema(description = "学员账号编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    @NotNull(message = "学员账号编号不能为空")
    private Long customerAccountId;
}
