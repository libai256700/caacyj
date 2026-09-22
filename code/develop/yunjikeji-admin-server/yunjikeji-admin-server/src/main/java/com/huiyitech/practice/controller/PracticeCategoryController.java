package com.huiyitech.practice.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.practice.service.PracticeCategoryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Practice Category")
@RestController
@RequestMapping("/admin-api/practice/practice-category")
@Validated
public class PracticeCategoryController {

    @Resource
    private PracticeCategoryService practiceCategoryService;

    @GetMapping("/page")
    @Operation(summary = "Get practice category page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(practiceCategoryService.getPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get practice category detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(practiceCategoryService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "Create practice category")
    public CommonResult<Long> create(@RequestBody Map<String, Object> body) {
        return success(practiceCategoryService.create(body));
    }

    @PutMapping("/update")
    @Operation(summary = "Update practice category")
    public CommonResult<Boolean> update(@RequestBody Map<String, Object> body) {
        practiceCategoryService.update(body);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "Delete practice category")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        practiceCategoryService.delete(id);
        return success(true);
    }
}
