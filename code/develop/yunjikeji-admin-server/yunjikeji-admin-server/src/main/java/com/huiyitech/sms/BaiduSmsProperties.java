package com.huiyitech.sms;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "huiyitech.sms.baidu")
public class BaiduSmsProperties {

    private Boolean enabled = false;

    private String accessKeyId;

    private String secretAccessKey;

    private String endpoint = "smsv3.bj.baidubce.com";

    private String signatureId;

    private String templateId;

    private String codeVariableName = "code";

    private Integer connectTimeoutMillis = 5000;

    private Integer socketTimeoutMillis = 10000;
}
