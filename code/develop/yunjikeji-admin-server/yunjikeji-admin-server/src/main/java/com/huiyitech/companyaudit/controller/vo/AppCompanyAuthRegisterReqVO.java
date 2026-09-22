package com.huiyitech.companyaudit.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;

import javax.validation.constraints.AssertTrue;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Pattern;

@Schema(description = "User App - company SMS login/register request")
public class AppCompanyAuthRegisterReqVO {

    @Schema(description = "Mobile phone", example = "13800138000")
    @NotBlank(message = "手机号不能为空")
    @Pattern(regexp = "^1\\d{10}$", message = "手机号格式不正确")
    private String mobile;

    @Schema(description = "SMS verification code", example = "123456")
    private String code;

    @Schema(description = "Legacy SMS verification code field for old app packages", hidden = true)
    private String password;

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

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getEffectiveCode() {
        String normalizedCode = trimToNull(code);
        return normalizedCode != null ? normalizedCode : trimToNull(password);
    }

    @AssertTrue(message = "短信验证码不能为空")
    public boolean isEffectiveCodePresent() {
        return getEffectiveCode() != null;
    }

    @AssertTrue(message = "短信验证码必须为 6 位数字")
    public boolean isEffectiveCodeFormatValid() {
        String effectiveCode = getEffectiveCode();
        return effectiveCode == null || effectiveCode.matches("^\\d{6}$");
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
