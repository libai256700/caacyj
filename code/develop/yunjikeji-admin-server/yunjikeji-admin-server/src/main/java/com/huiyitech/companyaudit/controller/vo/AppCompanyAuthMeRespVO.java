package com.huiyitech.companyaudit.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "用户 APP - 当前组织前端账号 Response VO")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppCompanyAuthMeRespVO {

    @Schema(description = "组织前端账号编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long companyAccountFrontId;

    @Schema(description = "租户编号", example = "1")
    private Long tenantId;

    @Schema(description = "租户名称", example = "云技航空科技有限公司")
    private String tenantName;

    @Schema(description = "租户联系人", example = "李四")
    private String tenantContactName;

    @Schema(description = "租户联系电话", example = "13800138000")
    private String tenantContactMobile;

    @Schema(description = "用户名", requiredMode = Schema.RequiredMode.REQUIRED, example = "company001")
    private String username;

    @Schema(description = "后台用户名", example = "教员1")
    private String nickname;

    @Schema(description = "所属组织名称", example = "教学部")
    private String deptName;

    @Schema(description = "是否启用", requiredMode = Schema.RequiredMode.REQUIRED)
    private Boolean status;

    @Schema(description = "是否通过审核", requiredMode = Schema.RequiredMode.REQUIRED)
    private Integer auditStatus;
}
