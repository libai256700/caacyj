package com.huiyitech.app.knowledge.service;

import cn.iocoder.yudao.framework.security.core.LoginUser;
import com.huiyitech.app.knowledge.controller.vo.AppKnowledgeAskRespVO;
import com.huiyitech.app.knowledge.dal.dataobject.AiCenterMessageDO;
import com.huiyitech.app.knowledge.dal.mysql.AiCenterMessageMapper;
import com.huiyitech.knowledge.controller.vo.KnowledgeQueryRespVO;
import com.huiyitech.knowledge.service.KnowledgeService;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.MockedStatic;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FrontKnowledgeServiceImplHistoryIsolationContractTest {

    @Test
    void query_shouldSkipHistoryForPracticeAiAnswerSource() {
        Fixture fixture = new Fixture();

        AppKnowledgeAskRespVO response = fixture.query("为什么选 B", "practice_ai_answer");

        assertEquals("为什么选 B", response.getQuestion());
        assertEquals("因为题目考察的是飞行前检查顺序。", response.getAnswer());
        verify(fixture.aiCenterMessageMapper, never()).insert(any(AiCenterMessageDO.class));
    }

    @Test
    void query_shouldPersistHistoryForAiAssistantSource() {
        Fixture fixture = new Fixture();

        AppKnowledgeAskRespVO response = fixture.query("无人机起飞前要检查什么", "ai_assistant");

        assertEquals("无人机起飞前要检查什么", response.getQuestion());
        assertEquals("因为题目考察的是飞行前检查顺序。", response.getAnswer());
        ArgumentCaptor<AiCenterMessageDO> captor = ArgumentCaptor.forClass(AiCenterMessageDO.class);
        verify(fixture.aiCenterMessageMapper, org.mockito.Mockito.times(2)).insert(captor.capture());
        List<AiCenterMessageDO> records = captor.getAllValues();
        assertEquals(Integer.valueOf(1), records.get(0).getFromType());
        assertEquals("无人机起飞前要检查什么", records.get(0).getContent());
        assertEquals(Integer.valueOf(2), records.get(1).getFromType());
        assertEquals("因为题目考察的是飞行前检查顺序。", records.get(1).getContent());
    }

    @Test
    void query_shouldPersistHistoryWhenSourceMissingForCompatibility() {
        Fixture fixture = new Fixture();

        fixture.query("兼容旧版请求", null);

        verify(fixture.aiCenterMessageMapper, org.mockito.Mockito.times(2)).insert(any(AiCenterMessageDO.class));
    }

    @Test
    void query_shouldPersistHistoryWhenSourceUnknownForSafety() {
        Fixture fixture = new Fixture();

        fixture.query("未知来源仍按 AI 助手处理", "legacy-caller");

        verify(fixture.aiCenterMessageMapper, org.mockito.Mockito.times(2)).insert(any(AiCenterMessageDO.class));
    }

    private static final class Fixture {
        private final KnowledgeService knowledgeService = mock(KnowledgeService.class);
        private final AiCenterMessageMapper aiCenterMessageMapper = mock(AiCenterMessageMapper.class);
        private final FrontKnowledgeServiceImpl service = new FrontKnowledgeServiceImpl(knowledgeService, aiCenterMessageMapper);

        private Fixture() {
            when(knowledgeService.query(any())).thenAnswer(invocation -> KnowledgeQueryRespVO.builder()
                    .question(invocation.getArgument(0, String.class))
                    .finalAnswer("因为题目考察的是飞行前检查顺序。")
                    .knowledgeAnswer("知识库命中了飞行前检查章节。")
                    .traceId("trace-dev-079")
                    .model("deepseek")
                    .build());
        }

        private AppKnowledgeAskRespVO query(String question, String source) {
            LoginUser loginUser = new LoginUser();
            loginUser.setId(9527L);
            try (MockedStatic<com.huiyitech.framework.security.AppMobileAuthUtils> authMock =
                         mockStatic(com.huiyitech.framework.security.AppMobileAuthUtils.class)) {
                authMock.when(com.huiyitech.framework.security.AppMobileAuthUtils::requireStudentLoginUser)
                        .thenReturn(loginUser);
                return service.query(question, source);
            }
        }
    }
}
