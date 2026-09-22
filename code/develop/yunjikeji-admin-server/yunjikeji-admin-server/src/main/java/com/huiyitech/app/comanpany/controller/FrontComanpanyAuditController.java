package com.huiyitech.app.comanpany.controller;

import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.security.config.SecurityProperties;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuditSaveReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuditSubmitReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthLoginRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthMeRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthPostCodesRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthRegisterReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyUniverifyLoginReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditPageReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditRespVO;
import com.huiyitech.companyaudit.service.CompanyAuditService;
import com.huiyitech.univerify.UniverifyRequestVerifier;
import com.huiyitech.utils.BaiduBosUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import javax.annotation.Resource;
import javax.annotation.security.PermitAll;
import javax.servlet.http.HttpServletRequest;
import javax.validation.Valid;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;
import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "企业审核模块")
@RestController
@Validated
@TenantIgnore
public class FrontComanpanyAuditController {

    @Resource
    private CompanyAuditService companyAuditService;
    @Resource
    private SecurityProperties securityProperties;
    @Resource
    private BaiduBosUtil baiduBosUtil;
    @Resource
    private UniverifyRequestVerifier univerifyRequestVerifier;

    @PostMapping("/app-api/yj/company-auth/login-or-register")
    @PermitAll
    @Operation(summary = "APP 组织前端账号登录或注册")
    public CommonResult<AppCompanyAuthLoginRespVO> loginOrRegister(@RequestBody @Valid AppCompanyAuthRegisterReqVO reqVO) {
        return success(companyAuditService.loginOrRegister(reqVO));
    }

    @PostMapping("/app-api/yj/company-auth/univerify-login")
    @PermitAll
    @Operation(summary = "企业 UniVerify 一键登录或注册")
    public CommonResult<AppCompanyAuthLoginRespVO> univerifyLogin(@RequestBody @Valid AppCompanyUniverifyLoginReqVO reqVO,
                                                                   HttpServletRequest request) {
        univerifyRequestVerifier.verify(request, reqVO.getMobile(), "enterprise");
        return success(companyAuditService.univerifyLogin(reqVO.getMobile()));
    }

    @PostMapping("/app-api/yj/company-auth/refresh-token")
    @PermitAll
    @Operation(summary = "刷新组织前端账号访问令牌")
    @Parameter(name = "refreshToken", description = "刷新令牌", required = true)
    public CommonResult<AppCompanyAuthLoginRespVO> refreshToken(@RequestParam("refreshToken") String refreshToken) {
        return success(companyAuditService.refreshToken(refreshToken));
    }

    @PostMapping("/app-api/yj/company-auth/logout")
    @Operation(summary = "APP 组织前端账号登出")
    public CommonResult<Boolean> logout(HttpServletRequest request) {
        String token = SecurityFrameworkUtils.obtainAuthorization(request,
                securityProperties.getTokenHeader(), securityProperties.getTokenParameter());
        companyAuditService.logout(token);
        return success(true);
    }

    @GetMapping("/app-api/yj/company-auth/me")
    @Operation(summary = "校验 Token 并获得当前组织前端账号")
    public CommonResult<AppCompanyAuthMeRespVO> me() {
        return success(companyAuditService.getCurrentCompanyAccount());
    }

    @GetMapping("/app-api/yj/company-auth/post-codes")
    @Operation(summary = "APP 企业账号按手机号获取后台用户岗位编码")
    @Parameter(name = "mobile", description = "手机号", required = true)
    public CommonResult<AppCompanyAuthPostCodesRespVO> postCodes(@RequestParam("mobile") String mobile) {
        return success(companyAuditService.getCompanyAuthPostCodes(mobile));
    }

    @PostMapping("/app-api/yj/enterprise-audit/save")
    @Operation(summary = "APP 端保存企业审核信息")
    public CommonResult<Long> saveAudit(@RequestBody @Valid AppCompanyAuditSaveReqVO reqVO) {
        return success(companyAuditService.saveAudit(reqVO));
    }

    @PostMapping(value = "/app-api/yj/enterprise-audit/save", consumes = "application/x-www-form-urlencoded")
    @Operation(summary = "APP 端保存企业审核信息（表单）")
    public CommonResult<Long> saveAuditForm(@ModelAttribute @Valid AppCompanyAuditSaveReqVO reqVO) {
        return success(companyAuditService.saveAudit(reqVO));
    }

    @PostMapping("/app-api/yj/enterprise-audit/submit")
    @Operation(summary = "APP 端提交企业审核")
    public CommonResult<Long> submitAudit(@RequestBody @Valid AppCompanyAuditSubmitReqVO reqVO) {
        return success(companyAuditService.submitAudit(reqVO));
    }

    @PostMapping(value = "/app-api/yj/enterprise-audit/submit", consumes = "application/x-www-form-urlencoded")
    @Operation(summary = "APP 端提交企业审核（表单）")
    public CommonResult<Long> submitAuditForm(@ModelAttribute @Valid AppCompanyAuditSubmitReqVO reqVO) {
        return success(companyAuditService.submitAudit(reqVO));
    }

    @PostMapping("/app-api/yj/enterprise-audit/license/upload")
    @Operation(summary = "APP 端上传企业营业执照到百度 BOS")
    public CommonResult<String> uploadEnterpriseLicense(@RequestParam("file") MultipartFile file) {
        try {
            return success(baiduBosUtil.upload(file, "enterprise/license").getUrl());
        } catch (ServiceException ex) {
            throw invalidParamException(normalizeEnterpriseLicenseUploadMessage(ex.getMessage()));
        } catch (Exception ex) {
            throw invalidParamException("营业执照上传失败，请稍后重试或联系管理员检查百度 BOS 配置");
        }
    }

    @GetMapping("/app-api/yj/company/student-audit/page")
    @Operation(summary = "APP 企业端分页查询当前组织的学员审核列表")
    public CommonResult<PageResult<AppCompanyStudentAuditRespVO>> getStudentAuditPage(@Valid AppCompanyStudentAuditPageReqVO reqVO) {
        return success(companyAuditService.getCurrentCompanyStudentAuditPage(reqVO));
    }

    @PutMapping("/app-api/yj/company/student-audit/audit")
    @Operation(summary = "APP 企业端审核当前组织的学员申请")
    public CommonResult<Boolean> auditStudent(@RequestBody @Valid AppCompanyStudentAuditReqVO reqVO) {
        companyAuditService.auditCurrentCompanyStudent(reqVO);
        return success(true);
    }

    private String normalizeEnterpriseLicenseUploadMessage(String message) {
        String normalized = message == null ? "" : message.trim();
        if (normalized.contains("BOS upload is not enabled") || normalized.contains("BOS upload configuration is incomplete")) {
            return "百度 BOS 未配置，暂时无法上传营业执照，请联系管理员配置 BAIDU_BOS_ENABLED、BAIDU_BOS_ACCESS_KEY_ID、BAIDU_BOS_SECRET_ACCESS_KEY、BAIDU_BOS_ENDPOINT、BAIDU_BOS_BUCKET_NAME";
        }
        return "营业执照上传失败，请稍后重试或联系管理员检查百度 BOS 配置";
    }
}
