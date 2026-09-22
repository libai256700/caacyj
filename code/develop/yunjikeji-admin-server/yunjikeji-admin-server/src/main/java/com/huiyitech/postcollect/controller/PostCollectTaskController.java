package com.huiyitech.postcollect.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.postcollect.service.PostCollectTaskService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Post Collect Task")
@RestController
@RequestMapping("/admin-api/postcollect/post-collection-task")
@Validated
public class PostCollectTaskController {

    @Resource
    private PostCollectTaskService postCollectTaskService;

    @GetMapping("/page")
    @Operation(summary = "Get post collect task page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(postCollectTaskService.getPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get post collect task detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(postCollectTaskService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "Create post collect task")
    public CommonResult<Long> create(@RequestBody Map<String, Object> body) {
        return success(postCollectTaskService.create(body));
    }

    @PutMapping("/update")
    @Operation(summary = "Update post collect task")
    public CommonResult<Boolean> update(@RequestBody Map<String, Object> body) {
        postCollectTaskService.update(body);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "Delete post collect task")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        postCollectTaskService.delete(id);
        return success(true);
    }

    @PostMapping("/collect-now")
    @Operation(summary = "Collect post task now")
    public CommonResult<Map<String, Object>> collectNow(@RequestBody Map<String, Object> body) {
        return success(postCollectTaskService.collectNow(body));
    }
}
