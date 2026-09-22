package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PostPlatformCollectServiceTest {

    @Test
    void splitKeywordsShouldSupportCommonSeparators() {
        TestPostPlatformCollectService service = new TestPostPlatformCollectService();
        PostCollectTaskDO task = PostCollectTaskDO.builder()
                .collectionKey("飞手,无人机；教员 飞控，运维")
                .build();

        assertEquals(Arrays.asList("飞手", "无人机", "教员", "飞控", "运维"),
                Arrays.asList(service.exposeSplitKeywords(task)));
    }

    @Test
    void zhilianSearchUrlTemplateShouldUseExpectedKeywordParameter() {
        TestZhilianPlatformPostCollectService service = new TestZhilianPlatformPostCollectService();

        assertEquals("https://www.zhaopin.com/sou/?key=%s&city=", service.exposeSearchUrlTemplate());
    }

    private static class TestPostPlatformCollectService extends AbstractPostPlatformCollectService {

        @Override
        public String getPlatformSource() {
            return "test";
        }

        @Override
        public List<PostCollectDO> collect(PostCollectTaskDO task) {
            return java.util.Collections.emptyList();
        }

        private String[] exposeSplitKeywords(PostCollectTaskDO task) {
            return splitKeywords(task);
        }
    }

    private static class TestZhilianPlatformPostCollectService extends ZhilianPlatformPostCollectServiceImpl {

        private String exposeSearchUrlTemplate() {
            return searchUrlTemplate();
        }
    }
}
