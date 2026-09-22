package com.huiyitech.app.message.controller.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class AppCustomerServiceRealtimeMessageRespVO {

    private Long id;

    private String conversationId;

    private Long sessionId;

    private Long sessionFrom;

    private Long sessionTo;

    private Long studentId;

    private Long tenantId;

    private String messageType;

    private String content;

    private String createTime;
}
