package com.huiyitech.practice.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.practice.service.UserPracticeExercisesRecordService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - User Practice Exercises Record")
@RestController
@RequestMapping("/admin-api/practice/user-practice-exercises-record")
@Validated
public class UserPracticeExercisesRecordController {

    @Resource
    private UserPracticeExercisesRecordService userPracticeExercisesRecordService;

    @GetMapping("/page")
    @Operation(summary = "Get user practice record page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(userPracticeExercisesRecordService.getPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get user practice record detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(userPracticeExercisesRecordService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "Create user practice record")
    public CommonResult<Long> create(@RequestBody Map<String, Object> body) {
        return success(userPracticeExercisesRecordService.create(body));
    }

    @PutMapping("/update")
    @Operation(summary = "Update user practice record")
    public CommonResult<Boolean> update(@RequestBody Map<String, Object> body) {
        userPracticeExercisesRecordService.update(body);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "Delete user practice record")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        userPracticeExercisesRecordService.delete(id);
        return success(true);
    }

    @GetMapping("/detail/page")
    @Operation(summary = "Get user practice record detail page")
    public CommonResult<PageResult<Map<String, Object>>> getDetailPage(@RequestParam Map<String, String> params) {
        return success(userPracticeExercisesRecordService.getDetailPage(params));
    }

    @GetMapping("/detail/get")
    @Operation(summary = "Get user practice record detail item")
    public CommonResult<Map<String, Object>> getDetail(@RequestParam("id") Long id) {
        return success(userPracticeExercisesRecordService.getDetail(id));
    }

    @PostMapping("/detail/create")
    @Operation(summary = "Create user practice record detail")
    public CommonResult<Long> createDetail(@RequestBody Map<String, Object> body) {
        return success(userPracticeExercisesRecordService.createDetail(body));
    }

    @PutMapping("/detail/update")
    @Operation(summary = "Update user practice record detail")
    public CommonResult<Boolean> updateDetail(@RequestBody Map<String, Object> body) {
        userPracticeExercisesRecordService.updateDetail(body);
        return success(true);
    }

    @DeleteMapping("/detail/delete")
    @Operation(summary = "Delete user practice record detail")
    public CommonResult<Boolean> deleteDetail(@RequestParam("id") Long id) {
        userPracticeExercisesRecordService.deleteDetail(id);
        return success(true);
    }
}
