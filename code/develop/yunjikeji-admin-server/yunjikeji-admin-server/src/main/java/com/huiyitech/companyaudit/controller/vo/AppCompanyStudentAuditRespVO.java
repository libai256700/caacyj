package com.huiyitech.companyaudit.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Schema(description = "APP 企业端 - 学员审核记录 Response VO")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppCompanyStudentAuditRespVO {

    @Schema(description = "审核记录编号", example = "1")
    private Long id;

    @Schema(description = "企业租户编号", example = "1")
    private Long tenantId;

    @Schema(description = "企业编号", example = "1")
    private Long companyId;

    @Schema(description = "学员账号编号", example = "1024")
    private Long customerAccountId;

    @Schema(description = "学员名称")
    private String studentName;

    @Schema(description = "学员手机号", example = "13800138000")
    private String studentPhone;

    @Schema(description = "审核状态：1 待审核，2 已通过，3 已驳回", example = "1")
    private Integer auditStatus;

    @Schema(description = "审核状态文案", example = "待审核")
    private String auditStatusText;

    @Schema(description = "审核原因")
    private String auditReason;

    @Schema(description = "申请时间")
    private LocalDateTime applyTime;

    @Schema(description = "审核时间")
    private LocalDateTime auditTime;
}
