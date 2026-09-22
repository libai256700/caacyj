package com.huiyitech.app.tenant.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.app.tenant.controller.vo.AppTenantListRespVO;
import com.huiyitech.app.tenant.service.FrontTenantService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.List;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "APP 公共 - 租户")
@RestController
@Validated
public class FrontTenantController {

    @Resource
    private FrontTenantService appTenantService;

    @GetMapping("/app-api/yj/tenants")
    @TenantIgnore
    @Operation(summary = "APP 端查询所有可用租户")
    public CommonResult<List<AppTenantListRespVO>> listTenants() {
        return success(appTenantService.listTenants());
    }

}
