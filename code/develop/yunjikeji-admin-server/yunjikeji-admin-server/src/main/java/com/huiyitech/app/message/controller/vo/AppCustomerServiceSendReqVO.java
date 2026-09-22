package com.huiyitech.app.message.controller.vo;

import lombok.Data;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Positive;
import javax.validation.constraints.Size;

@Data
public class AppCustomerServiceSendReqVO {

    private Long studentId;

    @Positive(message = "conversationId must be positive")
    private Long conversationId;

    private String messageType;

    @NotBlank(message = "Message content cannot be empty")
    @Size(max = 4000, message = "Message content cannot exceed 4000 characters")
    private String content;
}
