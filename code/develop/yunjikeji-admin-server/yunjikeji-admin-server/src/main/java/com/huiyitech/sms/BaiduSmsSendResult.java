package com.huiyitech.sms;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BaiduSmsSendResult {

    private boolean success;

    private String requestId;

    private String code;

    private String message;

    private String messageId;

    private String mobile;
}
