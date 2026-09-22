package com.huiyitech.practice.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.practice.service.PracticeExercisesService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Practice Exercises")
@RestController
@RequestMapping("/admin-api/practice/practice-exercises")
@Validated
public class PracticeExercisesController {

    @Resource
    private PracticeExercisesService practiceExercisesService;

    @GetMapping("/page")
    @Operation(summary = "Get practice exercises page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(practiceExercisesService.getPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get practice exercises detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(practiceExercisesService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "Create practice exercises")
    public CommonResult<Long> create(@RequestBody Map<String, Object> body) {
        return success(practiceExercisesService.create(body));
    }

    @PutMapping("/update")
    @Operation(summary = "Update practice exercises")
    public CommonResult<Boolean> update(@RequestBody Map<String, Object> body) {
        practiceExercisesService.update(body);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "Delete practice exercises")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        practiceExercisesService.delete(id);
        return success(true);
    }
}
