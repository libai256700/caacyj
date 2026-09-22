package com.huiyitech.app.message.controller.vo;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Data
@Builder
public class AppCustomerServiceSessionRespVO {

    private Long id;

    private Long sessionFrom;

    private Long sessionTo;

    private String lastMessageContent;

    private LocalDateTime lastMessageTime;

    private Integer unreadCount;

    private List<AppCustomerServiceMessageRespVO> messages;
}
