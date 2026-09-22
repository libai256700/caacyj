package com.huiyitech.chart.service;

public interface AccountLoginLogService {

    void recordLogin(Long customerAccountId);

    void recordKnowledgeCallIfPresent(Long customerAccountId);
}
