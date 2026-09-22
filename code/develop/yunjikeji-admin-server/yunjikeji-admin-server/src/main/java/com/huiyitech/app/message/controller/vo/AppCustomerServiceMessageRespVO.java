package com.huiyitech.app.message.controller.vo;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class AppCustomerServiceMessageRespVO {

    private Long id;

    private Long sessionId;

    private Long sessionFrom;

    private Long sessionTo;

    private String messageType;

    private String content;

    private LocalDateTime createTime;

    private Boolean mine;
}
