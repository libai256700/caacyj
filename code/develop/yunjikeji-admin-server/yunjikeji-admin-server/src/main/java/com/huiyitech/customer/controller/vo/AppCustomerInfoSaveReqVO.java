package com.huiyitech.customer.controller.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.Email;
import javax.validation.constraints.Size;

@Schema(description = "用户 App - 学员基础信息保存 Request VO")
@Data
public class AppCustomerInfoSaveReqVO {

    @Schema(description = "昵称", example = "飞行学员")
    @Size(max = 100, message = "昵称长度不能超过 100 位")
    private String nickName;

    @Schema(description = "真实姓名", example = "张三")
    @Size(max = 100, message = "真实姓名长度不能超过 100 位")
    private String realName;

    @Schema(description = "身份证号", example = "110101199001011234")
    @Size(max = 18, message = "身份证号长度不能超过 18 位")
    private String idCard;

    @Schema(description = "性别", example = "男")
    @Size(max = 10, message = "性别长度不能超过 10 位")
    private String sex;

    @Schema(description = "邮箱", example = "student@example.com")
    @Email(message = "邮箱格式不正确")
    @Size(max = 100, message = "邮箱长度不能超过 100 位")
    private String email;

    @Schema(description = "头像地址", example = "https://example.com/avatar.png")
    @Size(max = 500, message = "头像地址长度不能超过 500 位")
    private String avatarUrl;

    @Schema(description = "学号", example = "STU202606001")
    @Size(max = 100, message = "学号长度不能超过 100 位")
    private String studentNo;

    @Schema(description = "学校名称", example = "云技飞行学院")
    @Size(max = 100, message = "学校名称长度不能超过 100 位")
    private String schoolName;

    @Schema(description = "专业名称", example = "无人机应用技术")
    @Size(max = 100, message = "专业名称长度不能超过 100 位")
    private String majorName;

    @Schema(description = "角色标签", example = "student")
    @Size(max = 100, message = "角色标签长度不能超过 100 位")
    private String roleLabel;

    @Schema(description = "培训方向", example = "无人机巡检")
    @Size(max = 100, message = "培训方向长度不能超过 100 位")
    private String trainingDirection;
}
