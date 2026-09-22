package com.huiyitech.app.knowledge.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.app.knowledge.controller.vo.AppAiCenterHistoryRespVO;
import com.huiyitech.app.knowledge.service.FrontKnowledgeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.List;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "APP AI 中心")
@RestController
@Validated
@TenantIgnore
public class FrontAiCenterController {

    private static final int DEFAULT_HISTORY_LIMIT = 20;
    private static final int MAX_HISTORY_LIMIT = 50;

    @Resource
    private FrontKnowledgeService frontKnowledgeService;

    @GetMapping("/app-api/yj/ai-center/history")
    @Operation(summary = "APP 查询 AI 中心历史对话")
    public CommonResult<List<AppAiCenterHistoryRespVO>> history(@RequestParam(value = "limit", required = false) Integer limit) {
        int resolvedLimit = limit == null || limit <= 0 ? DEFAULT_HISTORY_LIMIT : Math.min(limit, MAX_HISTORY_LIMIT);
        return success(frontKnowledgeService.history(resolvedLimit));
    }
}
