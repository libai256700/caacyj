package com.huiyitech.message.controller.admin;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.app.message.service.CustomerMessageService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Customer Service Session")
@RestController
@RequestMapping("/yj/customer-session")
@Validated
public class CustomerServiceSessionController {

    @Resource
    private CustomerMessageService customerMessageService;

    @GetMapping("/page")
    @Operation(summary = "Get customer-service session page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(customerMessageService.getSessionPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get customer-service session detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(customerMessageService.getSession(id));
    }
}
