package com.huiyitech.knowledge.service;

import com.huiyitech.knowledge.controller.vo.KnowledgeQueryRespVO;

public interface KnowledgeService {

    KnowledgeQueryRespVO query(String question);
}
