package com.huiyitech.utils;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "huiyitech.bos.baidu")
public class BaiduBosProperties {

    private boolean enabled = false;

    private String accessKeyId;

    private String secretAccessKey;

    private String endpoint = "bj.bcebos.com";

    private String bucketName = "yunjikeji";

    private String prefixRoot = "yunjikeji";
}
