package cn.iocoder.yudao.server.job.yj;

import com.huiyitech.postcollect.service.PostCollectionTaskService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
public class PostCollectionTaskScheduleJob implements ApplicationListener<ApplicationReadyEvent>, DisposableBean {

    private static final Logger LOGGER = LoggerFactory.getLogger(PostCollectionTaskScheduleJob.class);

    @Resource
    private PostCollectionTaskService postCollectionTaskService;

    private final AtomicBoolean running = new AtomicBoolean(false);
    private ScheduledExecutorService executorService;

    @Override
    public synchronized void onApplicationEvent(ApplicationReadyEvent event) {
        if (executorService != null) {
            return;
        }
        executorService = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "yj-post-collection-task-scheduler");
            thread.setDaemon(true);
            return thread;
        });
        executorService.scheduleWithFixedDelay(this::executeDueTasks, 30, 60, TimeUnit.SECONDS);
        LOGGER.info("[onApplicationEvent][招聘岗位采集调度器已在应用就绪后启动]");
    }

    @Override
    public void destroy() {
        if (executorService != null) {
            executorService.shutdownNow();
        }
    }

    private void executeDueTasks() {
        if (!running.compareAndSet(false, true)) {
            return;
        }
        try {
            postCollectionTaskService.recoverStaleCollections("system");
            int count = postCollectionTaskService.collectDueTasks("system");
            if (count > 0) {
                LOGGER.info("[executeDueTasks][招聘岗位采集任务执行完成，数量({})]", count);
            }
        } catch (Throwable ex) {
            // A ScheduledExecutorService silently cancels a periodic task when an Error escapes it.
            LOGGER.error("[executeDueTasks][招聘岗位采集任务执行异常]", ex);
        } finally {
            running.set(false);
        }
    }
}
