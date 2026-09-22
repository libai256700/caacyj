package com.huiyitech.app.message.controller.vo;

import lombok.Data;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Positive;

@Data
public class AppCustomerServiceRealtimeSendReqVO {

    @Positive(message = "studentId must be positive")
    private Long studentId;

    @Positive(message = "conversationId must be positive")
    private Long conversationId;

    private String messageType;

    @NotBlank(message = "content cannot be empty")
    private String content;
}
