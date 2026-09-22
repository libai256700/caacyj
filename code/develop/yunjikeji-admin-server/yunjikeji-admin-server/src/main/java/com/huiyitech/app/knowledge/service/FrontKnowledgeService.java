package com.huiyitech.app.knowledge.service;

import com.huiyitech.app.knowledge.controller.vo.AppKnowledgeAskReqVO;
import com.huiyitech.app.knowledge.controller.vo.AppKnowledgeAskRespVO;
import com.huiyitech.app.knowledge.controller.vo.AppAiCenterHistoryRespVO;

import java.util.List;

public interface FrontKnowledgeService {

    AppKnowledgeAskRespVO ask(AppKnowledgeAskReqVO reqVO);

    AppKnowledgeAskRespVO query(String question, String source);

    List<AppAiCenterHistoryRespVO> history(int limit);
}
