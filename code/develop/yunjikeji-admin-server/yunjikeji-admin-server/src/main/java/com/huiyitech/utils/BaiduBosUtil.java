package com.huiyitech.utils;

import com.baidubce.auth.DefaultBceCredentials;
import com.baidubce.services.bos.BosClient;
import com.baidubce.services.bos.BosClientConfiguration;
import com.baidubce.services.bos.model.PutObjectResponse;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

import javax.annotation.Resource;
import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.UUID;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Component
public class BaiduBosUtil {

    private static final DateTimeFormatter DATE_PATH_FORMATTER = DateTimeFormatter.ofPattern("yyyy/MM/dd");

    @Resource
    private BaiduBosProperties properties;

    public BosUploadResult upload(MultipartFile file, String directory) {
        if (file == null || file.isEmpty()) {
            throw invalidParamException("Upload file cannot be empty");
        }
        validateConfigured();

        String objectKey = buildObjectKey(file.getOriginalFilename(), directory);
        try {
            BosClient client = createClient();
            PutObjectResponse response = client.putObject(properties.getBucketName(), objectKey, file.getInputStream());
            return BosUploadResult.builder()
                    .url(buildPublicUrl(objectKey))
                    .bosUri("bos://" + properties.getBucketName() + "/" + objectKey)
                    .bucketName(properties.getBucketName())
                    .endpoint(stripEndpointScheme(properties.getEndpoint()))
                    .objectKey(objectKey)
                    .eTag(response == null ? "" : response.getETag())
                    .build();
        } catch (IOException ex) {
            throw invalidParamException("BOS upload failed: {}", ex.getMessage());
        }
    }

    private BosClient createClient() {
        BosClientConfiguration config = new BosClientConfiguration();
        config.setCredentials(new DefaultBceCredentials(properties.getAccessKeyId(), properties.getSecretAccessKey()));
        config.setEndpoint(stripEndpointScheme(properties.getEndpoint()));
        return new BosClient(config);
    }

    private void validateConfigured() {
        if (!properties.isEnabled()) {
            throw invalidParamException("BOS upload is not enabled");
        }
        if (!StringUtils.hasText(properties.getAccessKeyId())
                || !StringUtils.hasText(properties.getSecretAccessKey())
                || !StringUtils.hasText(properties.getEndpoint())
                || !StringUtils.hasText(properties.getBucketName())) {
            throw invalidParamException("BOS upload configuration is incomplete");
        }
    }

    private String buildObjectKey(String originalFilename, String directory) {
        String ext = resolveExtension(originalFilename);
        String root = trimSlashes(properties.getPrefixRoot());
        String dir = trimSlashes(directory);
        String datePath = DATE_PATH_FORMATTER.format(LocalDate.now());
        String filename = UUID.randomUUID().toString().replace("-", "") + ext;
        StringBuilder key = new StringBuilder();
        appendPath(key, root);
        appendPath(key, dir);
        appendPath(key, datePath);
        appendPath(key, filename);
        return key.toString();
    }

    private String resolveExtension(String originalFilename) {
        if (!StringUtils.hasText(originalFilename)) {
            return "";
        }
        String name = originalFilename.trim();
        int index = name.lastIndexOf('.');
        if (index < 0 || index == name.length() - 1) {
            return "";
        }
        return name.substring(index).toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9.]", "");
    }

    private String buildPublicUrl(String objectKey) {
        String endpoint = stripEndpointScheme(properties.getEndpoint());
        return "https://" + properties.getBucketName() + "." + endpoint + "/" + objectKey;
    }

    private String stripEndpointScheme(String endpoint) {
        if (endpoint == null) {
            return "";
        }
        return endpoint.trim().replaceFirst("^https?://", "").replaceAll("/+$", "");
    }

    private String trimSlashes(String value) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        return value.trim().replaceAll("^/+", "").replaceAll("/+$", "");
    }

    private void appendPath(StringBuilder key, String part) {
        if (!StringUtils.hasText(part)) {
            return;
        }
        if (key.length() > 0) {
            key.append('/');
        }
        key.append(part);
    }

    @Data
    @Builder
    @AllArgsConstructor
    public static class BosUploadResult {
        private String url;
        private String bosUri;
        private String bucketName;
        private String endpoint;
        private String objectKey;
        private String eTag;
    }
}
