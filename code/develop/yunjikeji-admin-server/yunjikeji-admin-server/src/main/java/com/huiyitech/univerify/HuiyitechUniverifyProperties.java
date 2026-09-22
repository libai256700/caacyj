package com.huiyitech.univerify;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Data
@Component
@ConfigurationProperties(prefix = "huiyitech.univerify")
public class HuiyitechUniverifyProperties {

    /** Shared only with the uniCloud function, never with the App client. */
    private String hmacSecret;

    private Integer maxRequestAgeSeconds = 300;
}
