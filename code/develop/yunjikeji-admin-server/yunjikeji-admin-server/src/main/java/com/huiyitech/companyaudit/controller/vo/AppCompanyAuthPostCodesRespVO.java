package com.huiyitech.companyaudit.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.util.List;

@Schema(description = "用户 APP - 企业账号岗位编码 Response VO")
@Data
@Builder
public class AppCompanyAuthPostCodesRespVO {

    @Schema(description = "手机号是否匹配到后台用户")
    private Boolean userMatched;

    @Schema(description = "岗位编码列表")
    private List<String> postCodes;

    @Schema(description = "是否包含 WT 岗位")
    private Boolean hasWtPost;

    @Schema(description = "匹配到的后台用户租户编号")
    private Long tenantId;

}
