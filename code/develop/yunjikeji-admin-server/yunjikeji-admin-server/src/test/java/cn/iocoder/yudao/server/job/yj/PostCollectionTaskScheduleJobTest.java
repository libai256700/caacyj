package cn.iocoder.yudao.server.job.yj;

import com.huiyitech.postcollect.service.PostCollectionTaskService;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

class PostCollectionTaskScheduleJobTest {

    @Test
    void executeDueTasksShouldKeepThePeriodicTaskAliveWhenServiceThrowsAnError() {
        PostCollectionTaskService collectionTaskService = mock(PostCollectionTaskService.class);
        doThrow(new AssertionError("simulated fatal scheduler error"))
                .when(collectionTaskService).recoverStaleCollections(eq("system"));
        PostCollectionTaskScheduleJob job = new PostCollectionTaskScheduleJob();
        ReflectionTestUtils.setField(job, "postCollectionTaskService", collectionTaskService);

        assertDoesNotThrow(() -> ReflectionTestUtils.invokeMethod(job, "executeDueTasks"));
    }
}
