package com.huiyitech.app.message.controller.vo;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class AppCompanyStudentConversationRespVO {

    private Long studentId;

    private String studentName;

    private String studentPhone;

    private Long tenantId;

    private String conversationId;

    private String lastMessageContent;

    private LocalDateTime lastMessageTime;

    private Integer unreadCount;
}
