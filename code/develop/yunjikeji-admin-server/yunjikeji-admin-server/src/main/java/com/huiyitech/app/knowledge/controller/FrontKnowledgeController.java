package com.huiyitech.app.knowledge.controller;

import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.app.knowledge.controller.vo.AppKnowledgeAskReqVO;
import com.huiyitech.app.knowledge.controller.vo.AppKnowledgeAskRespVO;
import com.huiyitech.app.knowledge.service.FrontKnowledgeService;
import com.huiyitech.chart.service.AccountLoginLogService;
import com.huiyitech.framework.security.AppMobileAuthUtils;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import javax.validation.Valid;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "APP 知识库问答")
@RestController
@Validated
@TenantIgnore
public class FrontKnowledgeController {

    @Resource
    private FrontKnowledgeService frontKnowledgeService;
    @Resource
    private AccountLoginLogService accountLoginLogService;

    @PostMapping("/app-api/yj/knowledge/ask")
    @Operation(summary = "APP 知识库问答")
    public CommonResult<AppKnowledgeAskRespVO> ask(@Valid @RequestBody AppKnowledgeAskReqVO reqVO) {
        AppKnowledgeAskRespVO result = frontKnowledgeService.ask(reqVO);
        accountLoginLogService.recordKnowledgeCallIfPresent(getOptionalStudentCustomerAccountId());
        return success(result);
    }

    @GetMapping("/app-api/yj/knowledge/query")
    @Operation(summary = "APP 查询知识库")
    public CommonResult<AppKnowledgeAskRespVO> query(
            @RequestParam("q") String question,
            @RequestParam(value = "source", required = false) String source
    ) {
        AppKnowledgeAskRespVO result = frontKnowledgeService.query(question, source);
        accountLoginLogService.recordKnowledgeCallIfPresent(getOptionalStudentCustomerAccountId());
        return success(result);
    }

    private Long getOptionalStudentCustomerAccountId() {
        LoginUser loginUser = SecurityFrameworkUtils.getLoginUser();
        if (loginUser == null || !UserTypeEnum.MEMBER.getValue().equals(loginUser.getUserType())) {
            return null;
        }
        if (loginUser.getScopes() == null || !loginUser.getScopes().contains(AppMobileAuthUtils.CUSTOMER_STUDENT_SCOPE)) {
            return null;
        }
        return loginUser.getId();
    }
}
