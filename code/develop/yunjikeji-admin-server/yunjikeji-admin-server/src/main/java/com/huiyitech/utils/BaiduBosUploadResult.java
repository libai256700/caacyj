package com.huiyitech.utils;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BaiduBosUploadResult {

    private String bucketName;

    private String objectKey;

    private String bosUri;

    private String publicUrl;

    private String etag;
}
