package com.huiyitech.app.practice.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.app.practice.controller.vo.AppPracticeStartRespVO;
import com.huiyitech.app.practice.service.FrontPracticeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "APP Practice Legacy API")
@RestController
@Validated
@TenantIgnore
public class FrontPracticeLegacyController {

    @Resource
    private FrontPracticeService frontPracticeService;

    @PostMapping("/api/practices/{practiceId}/start")
    @Operation(summary = "Legacy start practice")
    public CommonResult<AppPracticeStartRespVO> startPractice(
            @PathVariable("practiceId") String practiceId,
            @RequestParam(value = "mode", defaultValue = "standard") String mode,
            @RequestParam(value = "topicId", defaultValue = "") String topicId) {
        return success(frontPracticeService.startPractice(practiceId, topicId, mode));
    }
}
