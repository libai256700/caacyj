package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectionTaskInstanceDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectTaskMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectionTaskInstanceMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostInstanceMapper;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PostCollectionTaskServiceTest {

    private final PostCollectMapper postCollectMapper = mock(PostCollectMapper.class);
    private final PostCollectTaskMapper taskMapper = mock(PostCollectTaskMapper.class);
    private final PostCollectionTaskInstanceMapper taskInstanceMapper = mock(PostCollectionTaskInstanceMapper.class);
    private final PostInstanceMapper postInstanceMapper = mock(PostInstanceMapper.class);
    private final PostPlatformCollectServiceFactory platformFactory = mock(PostPlatformCollectServiceFactory.class);
    private final FeishuPostCollectionAuditService auditService = mock(FeishuPostCollectionAuditService.class);
    private final PostCollectionTaskService service = new PostCollectionTaskService(postCollectMapper, taskMapper,
            taskInstanceMapper, postInstanceMapper, platformFactory, auditService);

    @Test
    void collectTaskShouldRejectAConcurrentExecutionBeforeCreatingAnInstance() {
        PostCollectTaskDO task = activeTask();
        when(taskMapper.tryAcquireCollectionLock(eq(6L), any(), any(), eq("system"), any())).thenReturn(0);

        assertThrows(RuntimeException.class, () -> service.collectTask(task, "system"));

        verify(taskInstanceMapper, never()).insert(org.mockito.ArgumentMatchers.<PostCollectionTaskInstanceDO>any());
        verify(platformFactory, never()).getRequired(any());
    }

    @Test
    void collectTaskShouldReleaseTheLockWhenTheCollectorCannotStart() {
        PostCollectTaskDO task = activeTask();
        when(taskMapper.tryAcquireCollectionLock(eq(6L), any(), any(), eq("system"), any())).thenReturn(1);
        when(platformFactory.getRequired("feishu_folder")).thenThrow(new IllegalStateException("collector unavailable"));

        assertThrows(IllegalStateException.class, () -> service.collectTask(task, "system"));

        verify(taskMapper).releaseCollectionLock(eq(6L), any(), eq("system"), any());
        verify(taskInstanceMapper, never()).insert(org.mockito.ArgumentMatchers.<PostCollectionTaskInstanceDO>any());
    }

    @Test
    void collectTaskShouldWriteFailureAndReleaseTheLockWhenCollectorThrowsAnError() {
        PostCollectTaskDO task = activeTask();
        IPostPlatformCollectService collector = mock(IPostPlatformCollectService.class);
        when(taskMapper.tryAcquireCollectionLock(eq(6L), any(), any(), eq("system"), any())).thenReturn(1);
        when(platformFactory.getRequired("feishu_folder")).thenReturn(collector);
        doThrow(new AssertionError("simulated fatal collector error")).when(collector).collect(task);

        assertThrows(AssertionError.class, () -> service.collectTask(task, "system"));

        verify(taskInstanceMapper).insert(org.mockito.ArgumentMatchers.<PostCollectionTaskInstanceDO>any());
        verify(auditService).fail("simulated fatal collector error", "system");
        verify(taskMapper).releaseCollectionLock(eq(6L), any(), eq("system"), any());
    }

    @Test
    void collectTaskShouldAcceptTheIsolatedFeishuChannel() {
        PostCollectTaskDO task = activeTask();
        task.setCollectionChannel(PostPlatformCollectServiceFactory.FEISHU_FOLDER_V2_CHANNEL);
        when(taskMapper.tryAcquireCollectionLock(eq(6L), any(), any(), eq("system"), any())).thenReturn(1);
        when(platformFactory.getRequired(PostPlatformCollectServiceFactory.FEISHU_FOLDER_V2_CHANNEL))
                .thenThrow(new IllegalStateException("collector unavailable"));

        assertThrows(IllegalStateException.class, () -> service.collectTask(task, "system"));

        verify(platformFactory).getRequired(PostPlatformCollectServiceFactory.FEISHU_FOLDER_V2_CHANNEL);
        verify(taskMapper).releaseCollectionLock(eq(6L), any(), eq("system"), any());
    }

    @Test
    void schedulerChannelShouldUseTheConfiguredIsolatedChannel() {
        ReflectionTestUtils.setField(service, "schedulerChannel", PostPlatformCollectServiceFactory.FEISHU_FOLDER_V2_CHANNEL);

        assertEquals(PostPlatformCollectServiceFactory.FEISHU_FOLDER_V2_CHANNEL, service.getSchedulerChannel());
    }

    private PostCollectTaskDO activeTask() {
        return PostCollectTaskDO.builder()
                .id(6L)
                .status(Boolean.TRUE)
                .collectionChannel("feishu_folder")
                .collectionKey("folder-token")
                .build();
    }
}
