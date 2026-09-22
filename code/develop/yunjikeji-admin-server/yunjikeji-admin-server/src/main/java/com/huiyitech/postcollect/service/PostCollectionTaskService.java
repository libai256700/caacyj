package com.huiyitech.postcollect.service;

import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectionTaskInstanceDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostInstanceDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectTaskMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectionTaskInstanceMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostInstanceMapper;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.util.StringUtils;

import java.sql.Timestamp;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
public class PostCollectionTaskService implements DisposableBean {

    private static final Logger log = LoggerFactory.getLogger(PostCollectionTaskService.class);
    private static final int FREQUENCY_DAILY = 1;
    private static final int FREQUENCY_WEEKLY = 2;
    private static final int FREQUENCY_MONTHLY = 3;
    private static final int INSTANCE_STATUS_RUNNING = 1;
    private static final int INSTANCE_STATUS_SUCCESS_UNMERGED = 2;
    private static final int INSTANCE_STATUS_SUCCESS_MERGED = 3;
    private static final int INSTANCE_STATUS_FAILED = 4;
    private static final int COLLECTION_LOCK_MINUTES = 30;
    private static final int COLLECTION_LOCK_RENEWAL_MINUTES = 5;

    private final PostCollectMapper postCollectMapper;
    private final PostCollectTaskMapper postCollectTaskMapper;
    private final PostCollectionTaskInstanceMapper taskInstanceMapper;
    private final PostInstanceMapper postInstanceMapper;
    private final PostPlatformCollectServiceFactory platformCollectServiceFactory;
    private final FeishuPostCollectionAuditService feishuAuditService;
    @Value("${huiyitech.post-collection.scheduler-channel:feishu_folder}")
    private String schedulerChannel;
    private final String processInstanceId = UUID.randomUUID().toString();
    private final ScheduledExecutorService collectionLockRenewalExecutor = Executors.newSingleThreadScheduledExecutor(runnable -> {
        Thread thread = new Thread(runnable, "yj-post-collection-lock-renewal");
        thread.setDaemon(true);
        return thread;
    });

    public PostCollectionTaskService(PostCollectMapper postCollectMapper,
                                     PostCollectTaskMapper postCollectTaskMapper,
                                     PostCollectionTaskInstanceMapper taskInstanceMapper,
                                     PostInstanceMapper postInstanceMapper,
                                     PostPlatformCollectServiceFactory platformCollectServiceFactory,
                                     FeishuPostCollectionAuditService feishuAuditService) {
        this.postCollectMapper = postCollectMapper;
        this.postCollectTaskMapper = postCollectTaskMapper;
        this.taskInstanceMapper = taskInstanceMapper;
        this.postInstanceMapper = postInstanceMapper;
        this.platformCollectServiceFactory = platformCollectServiceFactory;
        this.feishuAuditService = feishuAuditService;
    }

    @Override
    public void destroy() {
        collectionLockRenewalExecutor.shutdownNow();
    }

    public Map<String, Object> collectNow(Long taskId, String operator) {
        PostCollectTaskDO task = getTask(taskId);
        return collectTask(task, operator);
    }

    public int collectDueTasks(String operator) {
        int count = 0;
        LocalDateTime now = LocalDateTime.now();
        List<PostCollectTaskDO> tasks = TenantUtils.executeIgnore(this::listEnabledTasks);
        for (PostCollectTaskDO task : tasks) {
            if (shouldExecute(task, now)) {
                count++;
                try {
                    TenantUtils.execute(normalizeTenantId(task.getTenantId()), () -> collectTask(task, operator));
                } catch (Throwable ex) {
                    // Keep later tasks runnable even when one collector encounters a JVM Error.
                    log.error("岗位采集定时任务执行异常: taskId={}", task.getId(), ex);
                }
            }
        }
        return count;
    }

    public int recoverStaleCollections(String operator) {
        return TenantUtils.executeIgnore(() -> {
            LocalDateTime now = LocalDateTime.now();
            LocalDateTime staleBefore = now.minusMinutes(COLLECTION_LOCK_MINUTES);
            int recoveredRuns = feishuAuditService.recoverStaleRuns(staleBefore, operator);
            int recoveredInstances = taskInstanceMapper.failStaleRunningInstances(staleBefore, operator, now);
            if (recoveredRuns > 0 || recoveredInstances > 0) {
                log.warn("岗位采集残留状态已回收: runs={}, instances={}", recoveredRuns, recoveredInstances);
            }
            return recoveredRuns + recoveredInstances;
        });
    }

    public Map<String, Object> collectTask(PostCollectTaskDO task, String operator) {
        validateTask(task);
        LocalDateTime lockStartedAt = LocalDateTime.now();
        String lockOwner = processInstanceId + ":" + UUID.randomUUID();
        int acquired = postCollectTaskMapper.tryAcquireCollectionLock(task.getId(), lockOwner,
                lockStartedAt.plusMinutes(COLLECTION_LOCK_MINUTES), operator, lockStartedAt);
        if (acquired != 1) {
            throw invalidParamException("post collection task is already running: {}", task.getId());
        }
        AtomicBoolean lockLost = new AtomicBoolean(false);
        ScheduledFuture<?> lockRenewal = null;
        PostCollectionTaskInstanceDO instance = null;
        try {
            lockRenewal = scheduleLockRenewal(task.getId(), lockOwner, operator, lockLost);
            IPostPlatformCollectService platformService = platformCollectServiceFactory.getRequired(task.getCollectionChannel());
            log.info("岗位采集任务开始: taskId={}, channel={}, keyword={}, collectionNum={}, operator={}",
                    task.getId(), task.getCollectionChannel(), task.getCollectionKey(), task.getCollectionNum(), operator);
            instance = createTaskInstance(task.getId(), operator);
            log.info("岗位采集任务实例已创建: taskId={}, instanceId={}, operator={}",
                    task.getId(), instance.getId(), operator);
            List<PostCollectDO> posts = platformService.collect(task);
            ensureCollectionLockHeld(task.getId(), lockLost);
            applyCollectionChannel(posts, task.getCollectionChannel());
            log.info("岗位采集平台返回: taskId={}, instanceId={}, channel={}, returnCount={}",
                    task.getId(), instance.getId(), task.getCollectionChannel(), posts == null ? 0 : posts.size());
            int collectedCount = saveInstancePosts(instance.getId(), posts, operator);
            log.info("岗位采集实例入库完成: taskId={}, instanceId={}, savedCount={}",
                    task.getId(), instance.getId(), collectedCount);
            updateInstanceStatus(instance.getId(), INSTANCE_STATUS_SUCCESS_UNMERGED, collectedCount, operator);
            boolean directInsert = isFeishuFolderChannel(task.getCollectionChannel());
            MergeResult mergeResult = mergeInstancePosts(instance.getId(), operator, directInsert);
            int mergedCount = mergeResult.mergedCount;
            if (directInsert) {
                feishuAuditService.completeAfterMerge(collectedCount, mergeResult.insertedPostIds, operator);
            }
            log.info("岗位采集合入完成: taskId={}, instanceId={}, savedCount={}, mergedCount={}",
                    task.getId(), instance.getId(), collectedCount, mergedCount);
            updateInstanceStatus(instance.getId(), INSTANCE_STATUS_SUCCESS_MERGED, collectedCount, operator);
            updateTaskSuccess(task.getId(), instance.getId(), collectedCount, mergedCount, operator);

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("taskId", task.getId());
            result.put("taskInstanceId", instance.getId());
            result.put("collectionChannel", task.getCollectionChannel());
            result.put("collectCount", collectedCount);
            result.put("mergedCount", mergedCount);
            result.put("success", true);
            return result;
        } catch (Throwable ex) {
            String errorMessage = failureMessage(ex);
            log.error("岗位采集任务失败: taskId={}, instanceId={}, channel={}, operator={}",
                    task.getId(), instance == null ? null : instance.getId(), task.getCollectionChannel(), operator, ex);
            try {
                if (instance != null) {
                    updateInstanceStatus(instance.getId(), INSTANCE_STATUS_FAILED, 0, operator);
                }
                updateTaskFailure(task.getId(), instance == null ? null : instance.getId(), errorMessage, operator);
                if (isFeishuFolderChannel(task.getCollectionChannel())) {
                    feishuAuditService.fail(errorMessage, operator);
                }
            } catch (Throwable auditEx) {
                log.error("岗位采集失败状态写回异常: taskId={}, instanceId={}",
                        task.getId(), instance == null ? null : instance.getId(), auditEx);
            }
            rethrow(ex);
            return null; // unreachable; keeps the compiler aware that rethrow always exits.
        } finally {
            if (lockRenewal != null) {
                lockRenewal.cancel(true);
            }
            postCollectTaskMapper.releaseCollectionLock(task.getId(), lockOwner, operator, LocalDateTime.now());
        }
    }

    private ScheduledFuture<?> scheduleLockRenewal(Long taskId, String lockOwner, String operator,
                                                    AtomicBoolean lockLost) {
        return collectionLockRenewalExecutor.scheduleWithFixedDelay(() -> {
            LocalDateTime now = LocalDateTime.now();
            int renewed = postCollectTaskMapper.renewCollectionLock(taskId, lockOwner,
                    now.plusMinutes(COLLECTION_LOCK_MINUTES), operator, now);
            if (renewed != 1) {
                lockLost.set(true);
                log.error("岗位采集锁续租失败: taskId={}, owner={}", taskId, lockOwner);
            }
        }, COLLECTION_LOCK_RENEWAL_MINUTES, COLLECTION_LOCK_RENEWAL_MINUTES, TimeUnit.MINUTES);
    }

    private void ensureCollectionLockHeld(Long taskId, AtomicBoolean lockLost) {
        if (lockLost.get()) {
            throw new IllegalStateException("岗位采集执行锁已丢失: taskId=" + taskId);
        }
    }

    public boolean shouldExecute(PostCollectTaskDO task, LocalDateTime now) {
        if (task == null || !Boolean.TRUE.equals(task.getStatus()) || task.getCollectionTime() == null) {
            return false;
        }
        LocalDateTime plan = task.getCollectionTime().toLocalDateTime();
        if (now.toLocalTime().isBefore(plan.toLocalTime())) {
            return false;
        }
        Integer rule = task.getCollectionCountRule();
        if (FREQUENCY_DAILY == safeRule(rule)) {
            return task.getLastExecuteTime() == null
                    || task.getLastExecuteTime().toLocalDateTime().toLocalDate().isBefore(now.toLocalDate());
        }
        if (FREQUENCY_WEEKLY == safeRule(rule)) {
            LocalDate weekStart = now.toLocalDate().with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
            return now.getDayOfWeek().equals(plan.getDayOfWeek())
                    && (task.getLastExecuteTime() == null
                    || task.getLastExecuteTime().toLocalDateTime().toLocalDate().isBefore(weekStart));
        }
        if (FREQUENCY_MONTHLY == safeRule(rule)) {
            return now.getDayOfMonth() == plan.getDayOfMonth()
                    && (task.getLastExecuteTime() == null
                    || YearMonth.from(task.getLastExecuteTime().toLocalDateTime()).isBefore(YearMonth.from(now)));
        }
        return false;
    }

    private void validateTask(PostCollectTaskDO task) {
        if (task == null || task.getId() == null) {
            throw invalidParamException("post collection task cannot be empty");
        }
        if (!Boolean.TRUE.equals(task.getStatus())) {
            throw invalidParamException("post collection task is disabled: {}", task.getId());
        }
        if (!StringUtils.hasText(task.getCollectionChannel())) {
            throw invalidParamException("post collection channel cannot be empty");
        }
        if (!isFeishuFolderChannel(task.getCollectionChannel().trim())) {
            throw invalidParamException("post collection channel is disabled: {}", task.getCollectionChannel());
        }
    }

    private int safeRule(Integer rule) {
        return rule == null ? 0 : rule;
    }

    private Long normalizeTenantId(Long tenantId) {
        return tenantId == null ? 0L : tenantId;
    }

    private PostCollectTaskDO getTask(Long id) {
        PostCollectTaskDO task = postCollectTaskMapper.selectById(id);
        if (task == null) {
            throw invalidParamException("post collection task does not exist: {}", id);
        }
        return task;
    }

    private List<PostCollectTaskDO> listEnabledTasks() {
        return postCollectTaskMapper.selectList(new LambdaQueryWrapper<PostCollectTaskDO>()
                .eq(PostCollectTaskDO::getStatus, Boolean.TRUE)
                .eq(PostCollectTaskDO::getCollectionChannel, getSchedulerChannel())
                .orderByAsc(PostCollectTaskDO::getId));
    }

    String getSchedulerChannel() {
        String channel = StringUtils.hasText(schedulerChannel)
                ? schedulerChannel.trim() : PostPlatformCollectServiceFactory.FEISHU_FOLDER_CHANNEL;
        if (!isFeishuFolderChannel(channel)) {
            throw new IllegalStateException("unsupported post collection scheduler channel: " + channel);
        }
        return channel;
    }

    private boolean isFeishuFolderChannel(String channel) {
        return PostPlatformCollectServiceFactory.isFeishuFolderChannel(channel == null ? null : channel.trim());
    }

    private PostCollectionTaskInstanceDO createTaskInstance(Long taskId, String operator) {
        LocalDateTime now = LocalDateTime.now();
        PostCollectionTaskInstanceDO instance = PostCollectionTaskInstanceDO.builder()
                .taskId(taskId)
                .stauts(INSTANCE_STATUS_RUNNING)
                .collectionCount(0)
                .build();
        instance.setCreator(operator);
        instance.setUpdater(operator);
        instance.setCreateTime(now);
        instance.setUpdateTime(now);
        instance.setDeleted(Boolean.FALSE);
        taskInstanceMapper.insert(instance);
        return instance;
    }

    private int saveInstancePosts(Long taskInstanceId, List<PostCollectDO> posts, String operator) {
        int count = 0;
        if (posts == null || posts.isEmpty()) {
            log.warn("岗位采集实例无待入库数据: instanceId={}", taskInstanceId);
            return count;
        }
        for (PostCollectDO post : posts) {
            if (post == null || !StringUtils.hasText(post.getName())) {
                log.debug("岗位采集实例跳过空岗位名: instanceId={}, sourceCode={}, externalPostId={}",
                        taskInstanceId, post == null ? null : post.getSourceCode(),
                        post == null ? null : post.getExternalPostId());
                continue;
            }
            postInstanceMapper.insert(toPostInstance(taskInstanceId, post, operator));
            count++;
        }
        return count;
    }

    private PostInstanceDO toPostInstance(Long taskInstanceId, PostCollectDO post, String operator) {
        LocalDateTime now = LocalDateTime.now();
        PostInstanceDO instancePost = PostInstanceDO.builder()
                .taskInstanceId(taskInstanceId)
                .name(post.getName())
                .companyName(post.getCompanyName())
                .sourceCode(post.getSourceCode())
                .collectionChannel(post.getCollectionChannel())
                .externalPostId(post.getExternalPostId())
                .salaryRange(post.getSalaryRange())
                .workArea(post.getWorkArea())
                .publishDate(post.getPublishDate())
                .detailUrl(post.getDetailUrl())
                .status(Boolean.TRUE.equals(post.getStatus()))
                .build();
        instancePost.setCreator(operator);
        instancePost.setUpdater(operator);
        instancePost.setCreateTime(now);
        instancePost.setUpdateTime(now);
        instancePost.setDeleted(Boolean.FALSE);
        return instancePost;
    }

    private MergeResult mergeInstancePosts(Long taskInstanceId, String operator, boolean directInsert) {
        List<PostInstanceDO> instancePosts = postInstanceMapper.selectList(new LambdaQueryWrapper<PostInstanceDO>()
                .eq(PostInstanceDO::getTaskInstanceId, taskInstanceId)
                .orderByAsc(PostInstanceDO::getId));
        int mergedCount = 0;
        List<Long> insertedPostIds = new ArrayList<>();
        for (PostInstanceDO instancePost : instancePosts) {
            if (instancePost == null || !StringUtils.hasText(instancePost.getName())) {
                log.debug("岗位采集合入跳过空岗位名: instanceId={}, postInstanceId={}",
                        taskInstanceId, instancePost == null ? null : instancePost.getId());
                continue;
            }
            PostCollectDO existing = directInsert ? null : findExistingPost(instancePost);
            if (existing != null) {
                updateCollectionChannel(existing, instancePost.getCollectionChannel(), operator);
                log.debug("岗位采集合入跳过重复数据: instanceId={}, postInstanceId={}, name={}, companyName={}, salaryRange={}, workArea={}",
                        taskInstanceId, instancePost.getId(), instancePost.getName(), instancePost.getCompanyName(),
                        instancePost.getSalaryRange(), instancePost.getWorkArea());
                continue;
            }
            insertedPostIds.add(insertPost(instancePost, operator));
            mergedCount++;
        }
        return new MergeResult(mergedCount, insertedPostIds);
    }

    private PostCollectDO findExistingPost(PostInstanceDO post) {
        QueryWrapper<PostCollectDO> wrapper = new QueryWrapper<PostCollectDO>()
                .eq("name", safeText(post.getName()))
                .apply("COALESCE(company_name, '') = {0}", safeText(post.getCompanyName()))
                .apply("COALESCE(salary_range, '') = {0}", safeText(post.getSalaryRange()))
                .apply("COALESCE(work_area, '') = {0}", safeText(post.getWorkArea()))
                .last("LIMIT 1");
        return postCollectMapper.selectOne(wrapper);
    }

    private Long insertPost(PostInstanceDO source, String operator) {
        LocalDateTime now = LocalDateTime.now();
        PostCollectDO post = PostCollectDO.builder()
                .name(source.getName())
                .companyName(source.getCompanyName())
                .sourceCode(source.getSourceCode())
                .collectionChannel(source.getCollectionChannel())
                .externalPostId(source.getExternalPostId())
                .salaryRange(source.getSalaryRange())
                .workArea(source.getWorkArea())
                .publishDate(source.getPublishDate())
                .detailUrl(source.getDetailUrl())
                .status(Boolean.TRUE.equals(source.getStatus()))
                .build();
        post.setCreator(operator);
        post.setUpdater(operator);
        post.setCreateTime(now);
        post.setUpdateTime(now);
        post.setDeleted(Boolean.FALSE);
        postCollectMapper.insert(post);
        return post.getId();
    }

    private void updateInstanceStatus(Long taskInstanceId, Integer status, int collectionCount, String operator) {
        PostCollectionTaskInstanceDO update = PostCollectionTaskInstanceDO.builder()
                .id(taskInstanceId)
                .stauts(status)
                .collectionCount(collectionCount)
                .build();
        update.setUpdater(operator);
        update.setUpdateTime(LocalDateTime.now());
        taskInstanceMapper.updateById(update);
    }

    private void updateTaskSuccess(Long taskId, Long instanceId, int collectCount, int mergedCount, String operator) {
        String result = "collect done: instance " + instanceId + ", collected " + collectCount
                + ", merged " + mergedCount;
        updateTaskResult(taskId, 1, result, operator);
    }

    private void updateTaskFailure(Long taskId, Long instanceId, String errorMessage, String operator) {
        updateTaskResult(taskId, 2, "instance " + instanceId + " collect failed: "
                + abbreviate(errorMessage, 450), operator);
    }

    private void updateTaskResult(Long taskId, Integer status, String result, String operator) {
        PostCollectTaskDO update = PostCollectTaskDO.builder()
                .id(taskId)
                .lastExecuteTime(new Timestamp(System.currentTimeMillis()))
                .lastExecuteStatus(status)
                .lastExecuteResult(result)
                .build();
        update.setUpdater(operator);
        update.setUpdateTime(LocalDateTime.now());
        postCollectTaskMapper.updateById(update);
    }

    private void applyCollectionChannel(List<PostCollectDO> posts, String collectionChannel) {
        if (!StringUtils.hasText(collectionChannel) || posts == null) {
            return;
        }
        for (PostCollectDO post : posts) {
            if (post != null) {
                post.setCollectionChannel(collectionChannel);
            }
        }
    }

    private void updateCollectionChannel(PostCollectDO post, String collectionChannel, String operator) {
        if (post == null || !StringUtils.hasText(collectionChannel)
                || collectionChannel.equals(post.getCollectionChannel())) {
            return;
        }
        PostCollectDO update = PostCollectDO.builder()
                .id(post.getId())
                .collectionChannel(collectionChannel)
                .build();
        update.setUpdater(operator);
        update.setUpdateTime(LocalDateTime.now());
        postCollectMapper.updateById(update);
    }

    private String safeText(String value) {
        return value == null ? "" : value.trim();
    }

    private String abbreviate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

    private String failureMessage(Throwable throwable) {
        if (throwable == null) {
            return "unknown error";
        }
        String message = throwable.getMessage();
        return StringUtils.hasText(message) ? message : throwable.getClass().getName();
    }

    private void rethrow(Throwable throwable) {
        if (throwable instanceof Error) {
            throw (Error) throwable;
        }
        if (throwable instanceof RuntimeException) {
            throw (RuntimeException) throwable;
        }
        throw new IllegalStateException(throwable);
    }

    private static final class MergeResult {
        private final int mergedCount;
        private final List<Long> insertedPostIds;

        private MergeResult(int mergedCount, List<Long> insertedPostIds) {
            this.mergedCount = mergedCount;
            this.insertedPostIds = insertedPostIds;
        }
    }
}
