package com.huiyitech.companyaudit.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import com.huiyitech.companyaudit.service.CompanyAuditService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "企业审核模块")
@RestController
@Validated
public class CompanyAuditController {

    @Resource
    private CompanyAuditService companyAuditService;


    @PutMapping("/admin-api/yj/enterprise-audit/audit")
    @Operation(summary = "企业注册审核")
    public CommonResult<Boolean> auditEnterprise(@RequestBody Map<String, Object> body) {
        companyAuditService.auditEnterprise(body);
        return success(true);
    }
}
