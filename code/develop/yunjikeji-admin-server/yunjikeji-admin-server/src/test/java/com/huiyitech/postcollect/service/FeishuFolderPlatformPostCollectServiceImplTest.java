package com.huiyitech.postcollect.service;

import com.huiyitech.aiconfig.AiSceneCodes;
import com.huiyitech.knowledge.dal.DeepSeekOpenAiClient;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentItemDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FeishuFolderPlatformPostCollectServiceImplTest {

    private final DeepSeekOpenAiClient aiClient = mock(DeepSeekOpenAiClient.class);
    private final FeishuPostCollectionAuditService auditService = mock(FeishuPostCollectionAuditService.class);
    private FeishuFolderPlatformPostCollectServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new FeishuFolderPlatformPostCollectServiceImpl();
        ReflectionTestUtils.setField(service, "aiClient", aiClient);
        ReflectionTestUtils.setField(service, "auditService", auditService);
    }

    @Test
    void extractJobsWithAiShouldSendCompleteDocumentToSemanticExtraction() {
        String response = "{\"jobs\":["
                + "{\"name\":\"无人机教员\",\"company_name\":\"甲公司\","
                + "\"source_code\":\"智联招聘\",\"external_post_id\":\"job-1\","
                + "\"salary_range\":\"8-12K\",\"work_area\":\"武汉\","
                + "\"publish_date\":\"2026-08-20\",\"detail_url\":\"https://www.zhaopin.com/job-1\","
                + "\"status\":true,\"source_text\":\"无人机教员原文\"},"
                + "{\"name\":\"无人机飞手\",\"company_name\":\"乙公司\","
                + "\"source_code\":null,\"external_post_id\":null,\"salary_range\":null,"
                + "\"work_area\":\"成都\",\"publish_date\":null,\"detail_url\":null,"
                + "\"status\":true,\"source_text\":\"无人机飞手原文\"}],"
                + "\"ignored\":[],\"warnings\":[]}";
        when(aiClient.completeRequired(eq(AiSceneCodes.JOB_EXTRACTION), anyString(), anyString()))
                .thenReturn(response);

        List<PostCollectDO> posts = service.extractJobsWithAi("doc-1", "招聘岗位日报｜无人机/CAAC @ 全国 (2026-08-18)",
                Arrays.asList("新增岗位（今日首次出现）", "岗位正文一", "岗位正文二",
                        "更新岗位", "不应进入结构化步骤的正文"),
                10L, 20L);

        assertEquals(2, posts.size());
        assertEquals("zhilian", posts.get(0).getSourceCode());
        assertEquals("feishu:doc-1:2", posts.get(1).getExternalPostId());
        assertEquals("2026-08-18", posts.get(0).getPublishDate());
        assertEquals("2026-08-18", posts.get(1).getPublishDate());

        ArgumentCaptor<String> promptCaptor = ArgumentCaptor.forClass(String.class);
        ArgumentCaptor<String> systemPromptCaptor = ArgumentCaptor.forClass(String.class);
        verify(aiClient, times(1)).completeRequired(eq(AiSceneCodes.JOB_EXTRACTION), systemPromptCaptor.capture(),
                promptCaptor.capture());
        assertTrue(systemPromptCaptor.getValue().contains("完整的飞书招聘日报正文"));
        assertTrue(systemPromptCaptor.getValue().contains("依靠文档语义和上下文识别"));
        assertTrue(promptCaptor.getValue().contains("岗位正文一"));
        assertTrue(promptCaptor.getValue().contains("岗位正文二"));
        assertTrue(promptCaptor.getValue().contains("更新岗位"));
        assertTrue(promptCaptor.getValue().contains("不应进入结构化步骤的正文"));

        ArgumentCaptor<FeishuPostDocumentItemDO> itemCaptor =
                ArgumentCaptor.forClass(FeishuPostDocumentItemDO.class);
        verify(auditService, times(2)).saveItem(itemCaptor.capture(), eq("system"));
        assertEquals("EXTRACTED", itemCaptor.getAllValues().get(0).getStatus());
        assertEquals("无人机教员原文", itemCaptor.getAllValues().get(0).getSourceText());
        assertEquals("2026-08-18", itemCaptor.getAllValues().get(0).getPublishDate());
    }

    @Test
    void extractJobsWithAiShouldRetryInvalidJsonWithoutRuleFallback() {
        when(aiClient.completeRequired(eq(AiSceneCodes.JOB_EXTRACTION), anyString(), anyString()))
                .thenReturn("not-json")
                .thenReturn("{\"jobs\":[],\"ignored\":[],\"warnings\":[]}");

        List<PostCollectDO> posts = service.extractJobsWithAi("doc-2", "每日岗位信息报告_2026-05-20",
                Arrays.asList("任意版式正文"), 11L, 21L);

        assertTrue(posts.isEmpty());
        verify(aiClient, times(2)).completeRequired(eq(AiSceneCodes.JOB_EXTRACTION), anyString(), anyString());
    }

    @Test
    void extractJobsWithAiShouldNotRepeatAiCallWhenAuditPersistenceFails() {
        String response = "{\"jobs\":[{\"name\":\"无人机教员\",\"company_name\":null,"
                + "\"source_code\":\"feishu\",\"external_post_id\":null,\"salary_range\":null,"
                + "\"work_area\":null,\"publish_date\":null,\"detail_url\":null,"
                + "\"status\":true,\"source_text\":\"岗位原文\"}],\"ignored\":[],\"warnings\":[]}";
        when(aiClient.completeRequired(eq(AiSceneCodes.JOB_EXTRACTION), anyString(), anyString()))
                .thenReturn(response);
        doThrow(new IllegalStateException("database unavailable"))
                .when(auditService).saveItem(org.mockito.ArgumentMatchers.any(FeishuPostDocumentItemDO.class),
                        eq("system"));

        assertThrows(IllegalStateException.class, () -> service.extractJobsWithAi("doc-3", "招聘日报_2026-08-17",
                Arrays.asList("新增岗位（今日首次出现）", "岗位原文", "更新岗位"), 12L, 22L));

        verify(aiClient, times(1)).completeRequired(eq(AiSceneCodes.JOB_EXTRACTION), anyString(), anyString());
    }

    @Test
    void extractJobsWithAiShouldAcceptEmptyJobsForAnyDocumentLayout() {
        when(aiClient.completeRequired(eq(AiSceneCodes.JOB_EXTRACTION), anyString(), anyString()))
                .thenReturn("{\"jobs\":[],\"ignored\":[],\"warnings\":[]}");

        List<PostCollectDO> posts = service.extractJobsWithAi("doc-4", "招聘日报_2026-08-16",
                Arrays.asList("任意标题", "任意岗位正文", "其他历史内容"), 13L, 23L);

        assertTrue(posts.isEmpty());
        verify(aiClient, times(1)).completeRequired(eq(AiSceneCodes.JOB_EXTRACTION), anyString(), anyString());
    }

    @Test
    void extractDocumentLinesShouldKeepLongBlocksLinksAndOnlyRemoveExactSsrDuplicates() {
        StringBuilder longTextBuilder = new StringBuilder("新增岗位正文");
        for (int index = 0; index < 31_000; index++) {
            longTextBuilder.append('x');
        }
        String longText = longTextBuilder.toString();
        String firstBlock = "\"initialAttributedTexts\":{\"attribs\":{},\"text\":{\"0\":\""
                + longText + "\"}},\"link\",\"https://www.liepin.com/job/1.shtml\"";
        String secondBlock = "\"initialAttributedTexts\":{\"attribs\":{},\"text\":{\"0\":\"另一条岗位\"}}";

        List<String> lines = service.extractDocumentLines(firstBlock + firstBlock + secondBlock);

        assertEquals(2, lines.size());
        assertTrue(lines.get(0).contains(longText));
        assertTrue(lines.get(0).contains("[查看详情](https://www.liepin.com/job/1.shtml)"));
        assertEquals("另一条岗位", lines.get(1));
    }

    @Test
    void extractDocumentLinesShouldReadSsrPayloadEscapedAsAJsonString() {
        String html = "{\"payload\":\"{\\\"initialAttributedTexts\\\":{\\\"attribs\\\":{},"
                + "\\\"text\\\":{\\\"0\\\":\\\"转义后的岗位正文\\\"}}}\"}";

        List<String> lines = service.extractDocumentLines(html);

        assertEquals(Arrays.asList("转义后的岗位正文"), lines);
    }

    @Test
    void extractDocumentLinesShouldFallBackToRenderedSsrDomWhenJsonPayloadIsIncomplete() {
        String html = "<div class=\"ace-line\"><span data-string=\"true\">无人机教员</span>"
                + "<a href=\"https://www.example.com/job/1\">查看详情</a></div>";

        List<String> lines = service.extractDocumentLines(html);

        assertEquals(Arrays.asList("无人机教员查看详情\n[查看详情](https://www.example.com/job/1)"), lines);
    }

    @Test
    void resolveDocumentPublishDateShouldSupportReportTitleFormats() {
        assertEquals("2026-08-18", service.resolveDocumentPublishDate(
                "招聘岗位日报｜无人机/CAAC @ 全国 (2026-08-18)"));
        assertEquals("2026-05-20", service.resolveDocumentPublishDate("每日岗位信息报告_2026-05-20"));
        assertEquals("2026-06-03", service.resolveDocumentPublishDate("招聘日报_2026年6月3日"));
    }

    @Test
    void resolveDocumentPublishDateShouldRejectMissingOrInvalidDate() {
        assertThrows(IllegalStateException.class,
                () -> service.resolveDocumentPublishDate("招聘岗位日报｜无人机/CAAC @ 全国"));
        assertThrows(IllegalStateException.class,
                () -> service.resolveDocumentPublishDate("招聘岗位日报 (2026-02-30)"));
    }

    @Test
    void hasSuccessfulReadRecordShouldOnlySkipCompletedDocuments() {
        FeishuPostDocumentDO collected = new FeishuPostDocumentDO();
        collected.setCollected(Boolean.TRUE);
        collected.setDeleted(Boolean.FALSE);
        assertTrue(service.hasSuccessfulReadRecord(collected));

        FeishuPostDocumentDO failed = new FeishuPostDocumentDO();
        failed.setCollected(Boolean.FALSE);
        failed.setStatus("FAILED");
        failed.setDeleted(Boolean.FALSE);
        assertTrue(!service.hasSuccessfulReadRecord(failed));

        collected.setDeleted(Boolean.TRUE);
        assertTrue(!service.hasSuccessfulReadRecord(collected));
    }
}
