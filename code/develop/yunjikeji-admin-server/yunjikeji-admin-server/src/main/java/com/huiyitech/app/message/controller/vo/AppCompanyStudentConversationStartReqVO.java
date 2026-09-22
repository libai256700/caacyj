package com.huiyitech.app.message.controller.vo;

import lombok.Data;

import javax.validation.constraints.NotNull;
import javax.validation.constraints.Positive;

@Data
public class AppCompanyStudentConversationStartReqVO {

    @NotNull(message = "studentId cannot be empty")
    @Positive(message = "studentId must be positive")
    private Long studentId;
}
