package com.huiyitech.utils;

import com.baidubce.services.bos.BosClient;
import com.baidubce.services.bos.model.PutObjectResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.MockedConstruction;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.InputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mockConstruction;

class BaiduBosUtilTest {

    private BaiduBosUtil util;
    private BaiduBosProperties properties;

    @BeforeEach
    void setUp() {
        util = new BaiduBosUtil();
        properties = new BaiduBosProperties();
        ReflectionTestUtils.setField(util, "properties", properties);
    }

    @Test
    void upload_shouldRejectWhenBosDisabled() {
        MockMultipartFile file = new MockMultipartFile("file", "license.jpg", "image/jpeg", new byte[]{1, 2, 3});

        try {
            util.upload(file, "enterprise/license");
            fail("expected upload to reject disabled BOS");
        } catch (Exception ex) {
            assertTrue(ex.getMessage().contains("BOS upload is not enabled"));
        }
    }

    @Test
    void upload_shouldRejectWhenBosConfigurationIncomplete() {
        properties.setEnabled(true);
        properties.setAccessKeyId("ak");
        MockMultipartFile file = new MockMultipartFile("file", "license.jpg", "image/jpeg", new byte[]{1, 2, 3});

        try {
            util.upload(file, "enterprise/license");
            fail("expected upload to reject incomplete BOS config");
        } catch (Exception ex) {
            assertTrue(ex.getMessage().contains("BOS upload configuration is incomplete"));
        }
    }

    @Test
    void upload_shouldUseBosClientWhenConfigured() {
        properties.setEnabled(true);
        properties.setAccessKeyId("ak");
        properties.setSecretAccessKey("sk");
        properties.setEndpoint("bj.bcebos.com");
        properties.setBucketName("yunjikeji");
        properties.setPrefixRoot("yunjikeji");
        MockMultipartFile file = new MockMultipartFile("file", "license.jpg", "image/jpeg", new byte[]{1, 2, 3});

        try (MockedConstruction<BosClient> mocked = mockConstruction(BosClient.class, (mock, context) -> {
            PutObjectResponse response = new PutObjectResponse();
            response.setETag("etag-001");
            org.mockito.Mockito.when(mock.putObject(anyString(), anyString(), org.mockito.ArgumentMatchers.any(InputStream.class)))
                    .thenReturn(response);
        })) {
            BaiduBosUtil.BosUploadResult result = util.upload(file, "enterprise/license");

            assertEquals("yunjikeji", result.getBucketName());
            assertEquals("bj.bcebos.com", result.getEndpoint());
            assertEquals("etag-001", result.getETag());
            assertTrue(result.getBosUri().startsWith("bos://yunjikeji/yunjikeji/enterprise/license/"));
            assertTrue(result.getUrl().startsWith("https://yunjikeji.bj.bcebos.com/yunjikeji/enterprise/license/"));
            assertEquals(1, mocked.constructed().size());
        }
    }
}
