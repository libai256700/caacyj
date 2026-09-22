package com.huiyitech.companyaudit.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotNull;

@Schema(description = "APP 企业端 - 学员审核操作 Request VO")
@Data
public class AppCompanyStudentAuditReqVO {

    @Schema(description = "审核记录编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "审核记录编号不能为空")
    private Long id;

    @Schema(description = "审核状态：2 已通过，3 已驳回", requiredMode = Schema.RequiredMode.REQUIRED, example = "2")
    @NotNull(message = "审核状态不能为空")
    private Integer auditStatus;

    @Schema(description = "审核原因", example = "资料不完整")
    private String auditReason;
}
