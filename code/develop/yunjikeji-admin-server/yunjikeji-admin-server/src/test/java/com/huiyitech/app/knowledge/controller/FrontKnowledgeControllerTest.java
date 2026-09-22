package com.huiyitech.app.knowledge.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import com.huiyitech.app.knowledge.controller.vo.AppKnowledgeAskRespVO;
import com.huiyitech.app.knowledge.service.FrontKnowledgeService;
import com.huiyitech.chart.service.AccountLoginLogService;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FrontKnowledgeControllerTest {

    @Test
    void query_shouldPassExplicitSourceToService() {
        FrontKnowledgeService frontKnowledgeService = mock(FrontKnowledgeService.class);
        AccountLoginLogService accountLoginLogService = mock(AccountLoginLogService.class);
        FrontKnowledgeController controller = new FrontKnowledgeController();
        ReflectionTestUtils.setField(controller, "frontKnowledgeService", frontKnowledgeService);
        ReflectionTestUtils.setField(controller, "accountLoginLogService", accountLoginLogService);

        AppKnowledgeAskRespVO response = AppKnowledgeAskRespVO.builder()
                .question("为什么选 B")
                .answer("因为题目考察的是飞行前检查顺序。")
                .knowledgeAnswer("知识库命中了飞行前检查章节。")
                .traceId("trace-dev-079")
                .model("deepseek")
                .build();
        when(frontKnowledgeService.query(eq("为什么选 B"), eq("practice_ai_answer"))).thenReturn(response);

        CommonResult<AppKnowledgeAskRespVO> result = controller.query("为什么选 B", "practice_ai_answer");

        assertEquals("为什么选 B", result.getData().getQuestion());
        assertEquals("因为题目考察的是飞行前检查顺序。", result.getData().getAnswer());
        verify(frontKnowledgeService).query("为什么选 B", "practice_ai_answer");
    }

    @Test
    void query_shouldPassNullSourceWhenMissing() {
        FrontKnowledgeService frontKnowledgeService = mock(FrontKnowledgeService.class);
        AccountLoginLogService accountLoginLogService = mock(AccountLoginLogService.class);
        FrontKnowledgeController controller = new FrontKnowledgeController();
        ReflectionTestUtils.setField(controller, "frontKnowledgeService", frontKnowledgeService);
        ReflectionTestUtils.setField(controller, "accountLoginLogService", accountLoginLogService);

        AppKnowledgeAskRespVO response = AppKnowledgeAskRespVO.builder()
                .question("兼容旧版请求")
                .answer("因为题目考察的是飞行前检查顺序。")
                .knowledgeAnswer("知识库命中了飞行前检查章节。")
                .traceId("trace-dev-079")
                .model("deepseek")
                .build();
        when(frontKnowledgeService.query(eq("兼容旧版请求"), eq(null))).thenReturn(response);

        CommonResult<AppKnowledgeAskRespVO> result = controller.query("兼容旧版请求", null);

        assertEquals("兼容旧版请求", result.getData().getQuestion());
        assertEquals("因为题目考察的是飞行前检查顺序。", result.getData().getAnswer());
        verify(frontKnowledgeService).query("兼容旧版请求", null);
    }
}
