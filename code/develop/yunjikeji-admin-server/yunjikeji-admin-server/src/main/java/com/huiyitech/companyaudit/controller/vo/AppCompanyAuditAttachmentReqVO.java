package com.huiyitech.companyaudit.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Size;

@Schema(description = "用户 APP - 企业审核附件 Request VO")
@Data
public class AppCompanyAuditAttachmentReqVO {

    @Schema(description = "文件路径", requiredMode = Schema.RequiredMode.REQUIRED, example = "bos://xxx")
    @NotBlank(message = "文件路径不能为空")
    @Size(max = 500, message = "文件路径长度不能超过 500 位")
    private String filePath;

    @Schema(description = "文件名", example = "营业执照.png")
    @Size(max = 255, message = "文件名长度不能超过 255 位")
    private String fileName;

    @Schema(description = "文件类型", example = "business_license")
    @Size(max = 64, message = "文件类型长度不能超过 64 位")
    private String fileType;
}
