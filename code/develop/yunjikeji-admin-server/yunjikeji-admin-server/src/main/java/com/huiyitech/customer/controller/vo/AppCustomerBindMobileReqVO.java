package com.huiyitech.customer.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;

import javax.validation.constraints.AssertTrue;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Pattern;

@Schema(description = "学员 APP - 微信账号绑定手机号 Request VO")
public class AppCustomerBindMobileReqVO {

    @Schema(description = "手机号", requiredMode = Schema.RequiredMode.REQUIRED, example = "13800138000")
    @NotBlank(message = "手机号不能为空")
    @Pattern(regexp = "^1\\d{10}$", message = "手机号格式不正确")
    private String mobile;

    @Schema(description = "短信验证码", requiredMode = Schema.RequiredMode.REQUIRED, example = "123456")
    private String code;

    public String getMobile() {
        return mobile;
    }

    public void setMobile(String mobile) {
        this.mobile = mobile;
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    @AssertTrue(message = "短信验证码必须为 6 位数字")
    public boolean isCodeValid() {
        return code != null && code.trim().matches("^\\d{6}$");
    }
}
