package com.huiyitech.customer.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "用户 App - 当前学员信息 Response VO")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppCustomerAuthMeRespVO {

    @Schema(description = "学员账号编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long customerId;

    @Schema(description = "租户编号", example = "1")
    private Long tenantId;

    @Schema(description = "手机号", requiredMode = Schema.RequiredMode.REQUIRED, example = "13800138000")
    private String mobile;

    @Schema(description = "昵称", example = "飞行学员")
    private String nickname;

    @Schema(description = "姓名", example = "张三")
    private String realName;

    @Schema(description = "身份证号", example = "110101199001011234")
    private String idCard;

    @Schema(description = "头像地址")
    private String avatarUrl;

    @Schema(description = "学员编号", example = "FY20260001")
    private String studentNo;

    @Schema(description = "学校名称", example = "云技飞行学院")
    private String schoolName;

    @Schema(description = "专业名称", example = "无人机应用")
    private String majorName;

    @Schema(description = "角色标签", example = "student")
    private String roleLabel;

    @Schema(description = "训练方向", example = "多旋翼")
    private String trainingDirection;
}
