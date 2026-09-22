package com.huiyitech.customer.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import com.huiyitech.customer.service.CustomerService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "客户模块 - 学员账号")
@RestController
@Validated
public class CustomerController {

    @Resource
    private CustomerService customerService;

    @PutMapping("/admin-api/yj/student-audit/audit")
    @Operation(summary = "学员加入审核")
    public CommonResult<Boolean> auditStudent(@RequestBody Map<String, Object> body) {
        customerService.auditStudent(body);
        return success(true);
    }
}
