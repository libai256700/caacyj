package com.huiyitech.companyaudit.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Pattern;
import javax.validation.constraints.Size;
import java.util.List;

@Schema(description = "用户 APP - 企业审核信息保存 Request VO")
@Data
public class AppCompanyAuditSaveReqVO {

    @Schema(description = "提交人编号", example = "1001")
    private Long userId;

    @Schema(description = "企业名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "云技航空科技有限公司")
    @NotBlank(message = "企业名称不能为空")
    @Size(max = 30, message = "企业名称长度不能超过 30 位")
    private String name;

    @Schema(description = "统一社会信用代码", example = "91440300MA5K9UAV8X")
    @Size(max = 30, message = "统一社会信用代码长度不能超过 30 位")
    private String creditCode;

    @Schema(description = "法人", example = "张三")
    @Size(max = 30, message = "法人长度不能超过 30 位")
    private String legalPerson;

    @Schema(description = "法人身份证号", example = "440101199001011234")
    @Size(max = 30, message = "法人身份证号长度不能超过 30 位")
    private String legalPersonId;

    @Schema(description = "联系人", requiredMode = Schema.RequiredMode.REQUIRED, example = "李四")
    @NotBlank(message = "联系人不能为空")
    @Size(max = 30, message = "联系人长度不能超过 30 位")
    private String contactName;

    @Schema(description = "联系电话", requiredMode = Schema.RequiredMode.REQUIRED, example = "13800138000")
    @NotBlank(message = "联系电话不能为空")
    @Pattern(regexp = "^1\\d{10}$", message = "联系电话格式不正确")
    private String contactMobile;

    @Schema(description = "附件列表")
    @Valid
    private List<AppCompanyAuditAttachmentReqVO> attachments;
}
