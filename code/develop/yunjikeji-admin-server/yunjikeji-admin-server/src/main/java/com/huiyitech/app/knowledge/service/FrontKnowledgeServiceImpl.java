package com.huiyitech.app.knowledge.service;

import cn.iocoder.yudao.framework.security.core.LoginUser;
import com.huiyitech.aiconfig.AiSceneCodes;
import com.huiyitech.app.knowledge.controller.vo.AppKnowledgeAskReqVO;
import com.huiyitech.app.knowledge.controller.vo.AppKnowledgeAskRespVO;
import com.huiyitech.app.knowledge.controller.vo.AppAiCenterHistoryRespVO;
import com.huiyitech.app.knowledge.dal.dataobject.AiCenterMessageDO;
import com.huiyitech.app.knowledge.dal.mysql.AiCenterMessageMapper;
import com.huiyitech.knowledge.controller.vo.KnowledgeQueryRespVO;
import com.huiyitech.knowledge.service.KnowledgeService;
import com.huiyitech.framework.security.AppMobileAuthUtils;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
@RequiredArgsConstructor
@Slf4j
public class FrontKnowledgeServiceImpl implements FrontKnowledgeService {

    private static final int FROM_TYPE_USER = 1;
    private static final int FROM_TYPE_AI = 2;
    private static final int MAX_CONTENT_LENGTH = 5000;
    private static final String SOURCE_AI_ASSISTANT = "ai_assistant";
    private static final String SOURCE_PRACTICE_AI_ANSWER = "practice_ai_answer";

    private final KnowledgeService knowledgeService;
    private final AiCenterMessageMapper aiCenterMessageMapper;

    @Override
    public AppKnowledgeAskRespVO ask(AppKnowledgeAskReqVO reqVO) {
        if (reqVO == null || !StringUtils.hasText(reqVO.getQuestion())) {
            throw invalidParamException("用户问题不能为空");
        }
        return query(reqVO.getQuestion(), null);
    }

    @Override
    public AppKnowledgeAskRespVO query(String question, String source) {
        if (!StringUtils.hasText(question)) {
            throw invalidParamException("用户问题不能为空");
        }
        LoginUser loginUser = AppMobileAuthUtils.requireStudentLoginUser();
        KnowledgeQueryRespVO result = knowledgeService.query(question);
        if (shouldRecordHistory(source)) {
            recordHistory(loginUser, question, result);
        }
        return AppKnowledgeAskRespVO.builder()
                .question(result.getQuestion())
                .answer(result.getFinalAnswer())
                .knowledgeAnswer(result.getKnowledgeAnswer())
                .traceId(result.getTraceId())
                .model(result.getModel())
                .build();
    }

    @Override
    public List<AppAiCenterHistoryRespVO> history(int limit) {
        LoginUser loginUser = AppMobileAuthUtils.requireStudentLoginUser();
        List<AiCenterMessageDO> records = aiCenterMessageMapper.selectRecentHistory(
                loginUser.getId(),
                AiSceneCodes.KNOWLEDGE_CHAT,
                limit * 2
        );
        if (records.isEmpty()) {
            return Collections.emptyList();
        }
        List<AppAiCenterHistoryRespVO> history = new ArrayList<>();
        AiCenterMessageDO pendingQuestion = null;
        for (int i = records.size() - 1; i >= 0; i--) {
            AiCenterMessageDO record = records.get(i);
            if (Integer.valueOf(FROM_TYPE_USER).equals(record.getFromType())) {
                pendingQuestion = record;
                continue;
            }
            if (Integer.valueOf(FROM_TYPE_AI).equals(record.getFromType()) && pendingQuestion != null) {
                history.add(AppAiCenterHistoryRespVO.builder()
                        .id(pendingQuestion.getId() == null ? "" : String.valueOf(pendingQuestion.getId()))
                        .question(pendingQuestion.getContent())
                        .answer(record.getContent())
                        .createTime(pendingQuestion.getCreateTime())
                        .build());
                pendingQuestion = null;
            }
        }
        return history;
    }

    private void recordHistory(LoginUser loginUser, String question, KnowledgeQueryRespVO result) {
        try {
            aiCenterMessageMapper.insert(buildHistoryMessage(loginUser.getId(), FROM_TYPE_USER, question));
            aiCenterMessageMapper.insert(buildHistoryMessage(loginUser.getId(), FROM_TYPE_AI, result.getFinalAnswer()));
        } catch (Exception ex) {
            // 历史记录只做增强展示，不影响主问答逻辑
            log.warn("AI center history record failed customerAccountId={}", loginUser.getId(), ex);
        }
    }

    private AiCenterMessageDO buildHistoryMessage(Long customAccountId, Integer fromType, String content) {
        return AiCenterMessageDO.builder()
                .name(AiSceneCodes.KNOWLEDGE_CHAT)
                .customAccountId(customAccountId)
                .fromType(fromType)
                .content(limitContent(content))
                .build();
    }

    private String limitContent(String content) {
        String value = content == null ? "" : content;
        return value.length() > MAX_CONTENT_LENGTH ? value.substring(0, MAX_CONTENT_LENGTH) : value;
    }

    private boolean shouldRecordHistory(String source) {
        if (!StringUtils.hasText(source)) {
            return true;
        }
        String normalizedSource = source.trim().toLowerCase();
        if (SOURCE_PRACTICE_AI_ANSWER.equals(normalizedSource)) {
            return false;
        }
        return true;
    }
}
