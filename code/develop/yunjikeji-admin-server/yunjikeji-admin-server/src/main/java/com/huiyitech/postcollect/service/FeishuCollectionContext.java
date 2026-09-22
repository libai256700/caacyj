package com.huiyitech.postcollect.service;

import org.springframework.stereotype.Component;

/** Keeps the current Feishu run ID while a synchronous collection is merged. */
@Component
public class FeishuCollectionContext {

    private final ThreadLocal<Long> runId = new ThreadLocal<>();

    public void bind(Long value) {
        runId.set(value);
    }

    public Long currentRunId() {
        return runId.get();
    }

    public void clear() {
        runId.remove();
    }
}
