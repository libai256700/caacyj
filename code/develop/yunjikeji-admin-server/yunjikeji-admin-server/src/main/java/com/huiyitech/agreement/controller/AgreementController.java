package com.huiyitech.agreement.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.agreement.service.AgreementService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Agreement")
@RestController
@RequestMapping("/admin-api/agreement/agreement")
@Validated
public class AgreementController {

    @Resource
    private AgreementService agreementService;

    @GetMapping("/page")
    @Operation(summary = "Get agreement page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(agreementService.getPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get agreement detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(agreementService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "Create agreement")
    public CommonResult<Long> create(@RequestBody Map<String, Object> body) {
        return success(agreementService.create(body));
    }

    @PutMapping("/update")
    @Operation(summary = "Update agreement")
    public CommonResult<Boolean> update(@RequestBody Map<String, Object> body) {
        agreementService.update(body);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "Delete agreement")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        agreementService.delete(id);
        return success(true);
    }
}
