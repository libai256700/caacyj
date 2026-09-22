package com.huiyitech.practice.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.practice.service.PracticeExercisesAnswerService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Practice Exercises Answer")
@RestController
@RequestMapping("/admin-api/practice/practice-exercises-answer")
@Validated
public class PracticeExercisesAnswerController {

    @Resource
    private PracticeExercisesAnswerService practiceExercisesAnswerService;

    @GetMapping("/page")
    @Operation(summary = "Get practice exercises answer page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(practiceExercisesAnswerService.getPage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get practice exercises answer detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(practiceExercisesAnswerService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "Create practice exercises answer")
    public CommonResult<Long> create(@RequestBody Map<String, Object> body) {
        return success(practiceExercisesAnswerService.create(body));
    }

    @PutMapping("/update")
    @Operation(summary = "Update practice exercises answer")
    public CommonResult<Boolean> update(@RequestBody Map<String, Object> body) {
        practiceExercisesAnswerService.update(body);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "Delete practice exercises answer")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        practiceExercisesAnswerService.delete(id);
        return success(true);
    }
}
