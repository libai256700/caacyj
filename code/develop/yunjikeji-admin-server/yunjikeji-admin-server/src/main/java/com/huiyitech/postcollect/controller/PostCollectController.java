package com.huiyitech.postcollect.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.postcollect.service.PostCollectService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Post Collect")
@RestController
@RequestMapping("/admin-api/postcollect/post")
@Validated
public class PostCollectController {

    @Resource
    private PostCollectService postCollectService;

    @GetMapping("/page")
    @Operation(summary = "Get post collect page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(postCollectService.getPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get post collect detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(postCollectService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "Create post collect")
    public CommonResult<Long> create(@RequestBody Map<String, Object> body) {
        return success(postCollectService.create(body));
    }

    @PutMapping("/update")
    @Operation(summary = "Update post collect")
    public CommonResult<Boolean> update(@RequestBody Map<String, Object> body) {
        postCollectService.update(body);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "Delete post collect")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        postCollectService.delete(id);
        return success(true);
    }
}
