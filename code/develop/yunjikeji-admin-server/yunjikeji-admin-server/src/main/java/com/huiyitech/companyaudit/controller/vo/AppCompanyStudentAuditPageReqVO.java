package com.huiyitech.companyaudit.controller.vo;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@Schema(description = "APP 企业端 - 学员审核分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class AppCompanyStudentAuditPageReqVO extends PageParam {

    @Schema(description = "学员姓名或手机号关键字", example = "13800138000")
    private String keyword;

    @Schema(description = "审核状态：1 待审核，2 已通过，3 已驳回", example = "1")
    private Integer auditStatus;

    @Schema(description = "申请开始时间", example = "2026-06-15T00:00:00")
    private LocalDateTime startTime;

    @Schema(description = "申请结束时间", example = "2026-06-15T23:59:59")
    private LocalDateTime endTime;
}
