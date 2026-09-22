package com.huiyitech.univerify;

import cn.hutool.core.util.StrUtil;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import javax.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import static cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0;

@Component
public class UniverifyRequestVerifier {

    private static final String TIMESTAMP_HEADER = "X-Yj-Univerify-Timestamp";
    private static final String SIGNATURE_HEADER = "X-Yj-Univerify-Signature";

    @Resource
    private HuiyitechUniverifyProperties properties;

    public void verify(HttpServletRequest request, String mobile, String role) {
        String secret = StrUtil.trim(properties.getHmacSecret());
        if (StrUtil.isBlank(secret)) {
            throw forbidden();
        }

        String timestamp = StrUtil.trim(request.getHeader(TIMESTAMP_HEADER));
        String signature = StrUtil.trim(request.getHeader(SIGNATURE_HEADER));
        if (StrUtil.isBlank(timestamp) || StrUtil.isBlank(signature) || !timestamp.matches("^\\d{13}$")) {
            throw forbidden();
        }

        long requestTime;
        try {
            requestTime = Long.parseLong(timestamp);
        } catch (NumberFormatException ex) {
            throw forbidden();
        }

        long allowedAgeMillis = Math.max(30, properties.getMaxRequestAgeSeconds()) * 1000L;
        if (Math.abs(System.currentTimeMillis() - requestTime) > allowedAgeMillis) {
            throw forbidden();
        }

        String payload = timestamp + "\n" + mobile + "\n" + role;
        String expected = hmacSha256Base64Url(secret, payload);
        if (!MessageDigest.isEqual(expected.getBytes(StandardCharsets.US_ASCII), signature.getBytes(StandardCharsets.US_ASCII))) {
            throw forbidden();
        }
    }

    private String hmacSha256Base64Url(String secret, String payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return java.util.Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(mac.doFinal(payload.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("Failed to verify univerify request", ex);
        }
    }

    private RuntimeException forbidden() {
        return exception0(FORBIDDEN.getCode(), "一键登录请求校验失败");
    }
}
