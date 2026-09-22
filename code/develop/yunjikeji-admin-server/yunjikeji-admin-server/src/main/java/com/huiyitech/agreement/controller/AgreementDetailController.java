package com.huiyitech.agreement.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.agreement.service.AgreementDetailService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Agreement Detail")
@RestController
@RequestMapping("/admin-api/agreement/agreement-detail")
@Validated
public class AgreementDetailController {

    @Resource
    private AgreementDetailService agreementDetailService;

    @GetMapping("/page")
    @Operation(summary = "Get agreement detail page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(agreementDetailService.getPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get agreement detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(agreementDetailService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "Create agreement detail")
    public CommonResult<Long> create(@RequestBody Map<String, Object> body) {
        return success(agreementDetailService.create(body));
    }

    @PutMapping("/update")
    @Operation(summary = "Update agreement detail")
    public CommonResult<Boolean> update(@RequestBody Map<String, Object> body) {
        agreementDetailService.update(body);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "Delete agreement detail")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        agreementDetailService.delete(id);
        return success(true);
    }

    @PutMapping("/publish")
    @Operation(summary = "Publish agreement detail")
    public CommonResult<Boolean> publish(@RequestBody Map<String, Object> body) {
        agreementDetailService.publish(body);
        return success(true);
    }

    @PutMapping("/withdraw")
    @Operation(summary = "Withdraw agreement detail")
    public CommonResult<Boolean> withdraw(@RequestBody Map<String, Object> body) {
        agreementDetailService.withdraw(body);
        return success(true);
    }
}
