package com.huiyitech.app.customer.controller;

import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.security.config.SecurityProperties;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.customer.controller.vo.AppCustomerAuthLoginRespVO;
import com.huiyitech.customer.controller.vo.AppCustomerAuthMeRespVO;
import com.huiyitech.customer.controller.vo.AppCustomerAuthRegisterReqVO;
import com.huiyitech.customer.controller.vo.AppCustomerBindMobileReqVO;
import com.huiyitech.customer.controller.vo.AppCustomerUniverifyLoginReqVO;
import com.huiyitech.customer.controller.vo.AppCustomerInfoSaveReqVO;
import com.huiyitech.customer.controller.vo.AppStudentAuditMyRespVO;
import com.huiyitech.customer.controller.vo.AppStudentAuditSubmitReqVO;
import com.huiyitech.customer.service.CustomerService;
import com.huiyitech.univerify.UniverifyRequestVerifier;
import com.huiyitech.utils.BaiduBosUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import javax.annotation.Resource;
import javax.annotation.security.PermitAll;
import javax.servlet.http.HttpServletRequest;
import javax.validation.Valid;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Tag(name = "客户模块 - 学员账号")
@RestController
@Validated
@TenantIgnore
public class FrontCustomerController {

    @Resource
    private CustomerService customerService;
    @Resource
    private SecurityProperties securityProperties;
    @Resource
    private UniverifyRequestVerifier univerifyRequestVerifier;
    @Resource
    private BaiduBosUtil baiduBosUtil;

    @PostMapping("/app-api/yj/customer-auth/login-or-register")
    @PermitAll
    @Operation(summary = "学员手机号密码登录或注册")
    public CommonResult<AppCustomerAuthLoginRespVO> loginOrRegister(@RequestBody @Valid AppCustomerAuthRegisterReqVO reqVO) {
        return success(customerService.loginOrRegister(reqVO));
    }

    @PostMapping("/app-api/yj/customer-auth/univerify-login")
    @PermitAll
    @Operation(summary = "学员 UniVerify 一键登录或注册")
    public CommonResult<AppCustomerAuthLoginRespVO> univerifyLogin(@RequestBody @Valid AppCustomerUniverifyLoginReqVO reqVO,
                                                                    HttpServletRequest request) {
        univerifyRequestVerifier.verify(request, reqVO.getMobile(), "student");
        return success(customerService.univerifyLogin(reqVO.getMobile()));
    }

    @PostMapping("/app-api/yj/customer-auth/bind-mobile")
    @Operation(summary = "学员账号绑定手机号")
    public CommonResult<Boolean> bindMobile(@RequestBody @Valid AppCustomerBindMobileReqVO reqVO) {
        customerService.bindMobile(reqVO);
        return success(true);
    }

    @PostMapping("/app-api/yj/customer-auth/refresh-token")
    @PermitAll
    @Operation(summary = "刷新学员访问令牌")
    @Parameter(name = "refreshToken", description = "刷新令牌", required = true)
    public CommonResult<AppCustomerAuthLoginRespVO> refreshToken(@RequestParam("refreshToken") String refreshToken) {
        return success(customerService.refreshToken(refreshToken));
    }

    @PostMapping("/app-api/yj/customer-auth/logout")
    @Operation(summary = "学员 APP 登出")
    public CommonResult<Boolean> logout(HttpServletRequest request) {
        String token = SecurityFrameworkUtils.obtainAuthorization(request,
                securityProperties.getTokenHeader(), securityProperties.getTokenParameter());
        customerService.logout(token);
        return success(true);
    }

    @GetMapping("/app-api/yj/customer-auth/me")
    @Operation(summary = "校验 Token 并获得当前学员信息")
    public CommonResult<AppCustomerAuthMeRespVO> me() {
        return success(customerService.getCurrentCustomer());
    }

    @PostMapping("/app-api/yj/customer-info/save")
    @Operation(summary = "APP 端保存学员基础信息")
    public CommonResult<Boolean> saveCustomerInfo(@RequestBody @Valid AppCustomerInfoSaveReqVO reqVO) {
        customerService.saveCustomerInfo(reqVO);
        return success(true);
    }

    @PostMapping("/app-api/yj/customer-info/avatar/upload")
    @Operation(summary = "APP 端上传学员头像到百度 BOS")
    public CommonResult<String> uploadAvatar(@RequestParam("file") MultipartFile file) {
        try {
            return success(baiduBosUtil.upload(file, "avatar").getUrl());
        } catch (ServiceException ex) {
            throw invalidParamException(normalizeAvatarUploadMessage(ex.getMessage()));
        } catch (Exception ex) {
            throw invalidParamException("头像上传失败，请稍后重试或联系管理员检查百度 BOS 配置");
        }
    }

    @PostMapping("/app-api/yj/student-audit/submit")
    @Operation(summary = "APP 端提交学员审核")
    public CommonResult<Long> submitStudentAudit(@RequestBody @Valid AppStudentAuditSubmitReqVO reqVO) {
        return success(customerService.submitStudentAudit(reqVO));
    }

    @GetMapping("/app-api/yj/student-audit/my")
    @Operation(summary = "APP 端获取当前学员最新审核状态")
    public CommonResult<AppStudentAuditMyRespVO> getCurrentStudentAudit() {
        return success(customerService.getCurrentStudentAudit());
    }

    private String normalizeAvatarUploadMessage(String message) {
        String normalized = message == null ? "" : message.trim();
        if (normalized.contains("BOS upload is not enabled") || normalized.contains("BOS upload configuration is incomplete")) {
            return "百度 BOS 未配置，暂时无法上传头像，请联系管理员配置 BAIDU_BOS_ENABLED、BAIDU_BOS_ACCESS_KEY_ID、BAIDU_BOS_SECRET_ACCESS_KEY、BAIDU_BOS_ENDPOINT、BAIDU_BOS_BUCKET_NAME";
        }
        return "头像上传失败，请稍后重试或联系管理员检查百度 BOS 配置";
    }
}
