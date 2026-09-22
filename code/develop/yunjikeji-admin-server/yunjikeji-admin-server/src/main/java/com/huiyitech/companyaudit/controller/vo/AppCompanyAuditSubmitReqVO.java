package com.huiyitech.companyaudit.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotNull;

@Schema(description = "用户 APP - 企业审核提交 Request VO")
@Data
public class AppCompanyAuditSubmitReqVO {

    @Schema(description = "企业前端登录账号 ID", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    @NotNull(message = "企业前端登录账号 ID 不能为空")
    private Long companyAccountFrontId;
}
