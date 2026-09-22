package com.huiyitech.sms;

import com.baidubce.BceClientException;
import com.baidubce.BceServiceException;
import com.baidubce.auth.DefaultBceCredentials;
import com.baidubce.services.sms.SmsClient;
import com.baidubce.services.sms.SmsClientConfiguration;
import com.baidubce.services.sms.model.SendMessageItem;
import com.baidubce.services.sms.model.SendMessageV3Request;
import com.baidubce.services.sms.model.SendMessageV3Response;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

@Component
public class BaiduSmsUtil {

    private final BaiduSmsProperties properties;

    public BaiduSmsUtil(BaiduSmsProperties properties) {
        this.properties = properties;
    }

    public BaiduSmsSendResult sendVerificationCode(String mobile, String code) {
        return sendVerificationCode(mobile, code, Collections.emptyMap());
    }

    public BaiduSmsSendResult sendVerificationCode(String mobile, String code, Map<String, String> extraContentVar) {
        if (!Boolean.TRUE.equals(properties.getEnabled())) {
            throw new IllegalStateException("Baidu SMS is disabled");
        }
        validateConfig();
        if (!StringUtils.hasText(mobile)) {
            throw new IllegalArgumentException("mobile must not be blank");
        }
        if (!StringUtils.hasText(code)) {
            throw new IllegalArgumentException("code must not be blank");
        }

        Map<String, String> contentVar = new HashMap<>();
        if (extraContentVar != null) {
            contentVar.putAll(extraContentVar);
        }
        contentVar.put(properties.getCodeVariableName(), code);

        SendMessageV3Request request = new SendMessageV3Request();
        request.setMobile(mobile);
        request.setSignatureId(properties.getSignatureId());
        request.setTemplate(properties.getTemplateId());
        request.setContentVar(contentVar);

        try {
            SendMessageV3Response response = createClient().sendMessage(request);
            return toResult(response);
        } catch (BceServiceException ex) {
            return BaiduSmsSendResult.builder()
                    .success(false)
                    .requestId(ex.getRequestId())
                    .code(ex.getErrorCode())
                    .message(ex.getErrorMessage())
                    .mobile(mobile)
                    .build();
        } catch (BceClientException ex) {
            return BaiduSmsSendResult.builder()
                    .success(false)
                    .message(ex.getMessage())
                    .mobile(mobile)
                    .build();
        }
    }

    public BaiduSmsSendResult send(String mobile, String templateId, String signatureId,
                                   Map<String, String> contentVar) {
        if (!Boolean.TRUE.equals(properties.getEnabled())) {
            throw new IllegalStateException("Baidu SMS is disabled");
        }
        validateCredentialConfig();
        if (!StringUtils.hasText(mobile)) {
            throw new IllegalArgumentException("mobile must not be blank");
        }
        if (!StringUtils.hasText(templateId)) {
            throw new IllegalArgumentException("templateId must not be blank");
        }
        if (!StringUtils.hasText(signatureId)) {
            throw new IllegalArgumentException("signatureId must not be blank");
        }

        SendMessageV3Request request = new SendMessageV3Request();
        request.setMobile(mobile);
        request.setSignatureId(signatureId);
        request.setTemplate(templateId);
        request.setContentVar(contentVar == null ? Collections.emptyMap() : contentVar);

        try {
            SendMessageV3Response response = createClient().sendMessage(request);
            return toResult(response);
        } catch (BceServiceException ex) {
            return BaiduSmsSendResult.builder()
                    .success(false)
                    .requestId(ex.getRequestId())
                    .code(ex.getErrorCode())
                    .message(ex.getErrorMessage())
                    .mobile(mobile)
                    .build();
        } catch (BceClientException ex) {
            return BaiduSmsSendResult.builder()
                    .success(false)
                    .message(ex.getMessage())
                    .mobile(mobile)
                    .build();
        }
    }

    private SmsClient createClient() {
        SmsClientConfiguration config = new SmsClientConfiguration()
                .withCredentials(new DefaultBceCredentials(properties.getAccessKeyId(),
                        properties.getSecretAccessKey()))
                .withEndpoint(properties.getEndpoint())
                .withConnectionTimeoutInMillis(properties.getConnectTimeoutMillis())
                .withSocketTimeoutInMillis(properties.getSocketTimeoutMillis());
        return new SmsClient(config);
    }

    private BaiduSmsSendResult toResult(SendMessageV3Response response) {
        SendMessageItem item = response.getData() == null || response.getData().isEmpty()
                ? null : response.getData().get(0);
        return BaiduSmsSendResult.builder()
                .success(response.isSuccess() && (item == null || "1000".equals(item.getCode())))
                .requestId(response.getRequestId())
                .code(item == null ? response.getCode() : item.getCode())
                .message(item == null ? response.getMessage() : item.getMessage())
                .messageId(item == null ? null : item.getMessageId())
                .mobile(item == null ? null : item.getMobile())
                .build();
    }

    private void validateConfig() {
        validateCredentialConfig();
        if (!StringUtils.hasText(properties.getSignatureId())) {
            throw new IllegalStateException("huiyitech.sms.baidu.signature-id must not be blank");
        }
        if (!StringUtils.hasText(properties.getTemplateId())) {
            throw new IllegalStateException("huiyitech.sms.baidu.template-id must not be blank");
        }
        if (!StringUtils.hasText(properties.getCodeVariableName())) {
            throw new IllegalStateException("huiyitech.sms.baidu.code-variable-name must not be blank");
        }
    }

    private void validateCredentialConfig() {
        if (!StringUtils.hasText(properties.getAccessKeyId())) {
            throw new IllegalStateException("huiyitech.sms.baidu.access-key-id must not be blank");
        }
        if (!StringUtils.hasText(properties.getSecretAccessKey())) {
            throw new IllegalStateException("huiyitech.sms.baidu.secret-access-key must not be blank");
        }
        if (!StringUtils.hasText(properties.getEndpoint())) {
            throw new IllegalStateException("huiyitech.sms.baidu.endpoint must not be blank");
        }
    }
}
