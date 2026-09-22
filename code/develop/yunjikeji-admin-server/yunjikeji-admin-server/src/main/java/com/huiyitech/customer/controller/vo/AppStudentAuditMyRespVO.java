package com.huiyitech.customer.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Schema(description = "用户 App - 当前学员最新组织申请 Response VO")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppStudentAuditMyRespVO {

    @Schema(description = "审核记录编号", example = "1")
    private Long id;

    @Schema(description = "企业租户编号", example = "1")
    private Long tenantId;

    @Schema(description = "企业组织编号", example = "1")
    private Long companyId;

    @Schema(description = "学员账号编号", example = "1024")
    private Long customerAccountId;

    @Schema(description = "审核状态：1 待审核，2 通过，3 驳回", example = "1")
    private Integer auditStatus;

    @Schema(description = "审核状态文案", example = "待审核")
    private String auditStatusText;

    @Schema(description = "审核原因")
    private String auditReason;

    @Schema(description = "审核时间")
    private LocalDateTime auditTime;
}
