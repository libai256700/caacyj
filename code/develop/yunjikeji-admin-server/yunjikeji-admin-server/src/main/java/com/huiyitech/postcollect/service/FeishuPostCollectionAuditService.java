package com.huiyitech.postcollect.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostCollectionRunDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentItemDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.FeishuPostCollectionRunMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.FeishuPostDocumentItemMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.FeishuPostDocumentMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class FeishuPostCollectionAuditService {

    @Resource
    private FeishuPostCollectionRunMapper runMapper;
    @Resource
    private FeishuPostDocumentMapper documentMapper;
    @Resource
    private FeishuPostDocumentItemMapper itemMapper;
    @Resource
    private FeishuCollectionContext context;

    public Long startRun(Long taskId, String folderToken, String operator, int documentsSeen) {
        LocalDateTime now = LocalDateTime.now();
        FeishuPostCollectionRunDO run = FeishuPostCollectionRunDO.builder()
                .taskId(taskId)
                .folderToken(folderToken)
                .status("RUNNING")
                .documentsSeen(documentsSeen)
                .documentsProcessed(0)
                .documentsFailed(0)
                .jobsExtracted(0)
                .jobsCreated(0)
                .jobsUpdated(0)
                .jobsSkipped(0)
                .jobsFailed(0)
                .startedAt(now)
                .build();
        run.setCreator(operator);
        run.setUpdater(operator);
        run.setCreateTime(now);
        run.setUpdateTime(now);
        run.setDeleted(Boolean.FALSE);
        runMapper.insert(run);
        context.bind(run.getId());
        return run.getId();
    }

    public Long upsertDocument(Long runId, String folderToken, String documentId, String documentName,
                               String documentUrl, String revisionId, String contentHash, String operator,
                               int extractedCount) {
        FeishuPostDocumentDO existing = documentMapper.selectIncludingDeleted(folderToken, documentId);
        LocalDateTime now = LocalDateTime.now();
        boolean restoreDeleted = existing != null && Boolean.TRUE.equals(existing.getDeleted());
        FeishuPostDocumentDO document = existing == null ? new FeishuPostDocumentDO() : existing;
        document.setFolderToken(folderToken);
        document.setDocumentId(documentId);
        document.setDocumentName(documentName);
        document.setDocumentUrl(documentUrl);
        document.setDocumentRevisionId(revisionId);
        document.setContentHash(contentHash);
        document.setCollected(Boolean.FALSE);
        document.setStatus("PROCESSING");
        document.setLastRunId(runId);
        document.setLastError(null);
        document.setExtractedCount(extractedCount);
        document.setCreatedCount(0);
        document.setUpdatedCount(0);
        document.setSkippedCount(0);
        document.setFailedCount(0);
        document.setCollectedAt(null);
        document.setUpdater(operator);
        document.setUpdateTime(now);
        document.setDeleted(Boolean.FALSE);
        if (existing == null) {
            document.setCreator(operator);
            document.setCreateTime(now);
            documentMapper.insert(document);
        } else {
            if (restoreDeleted) {
                documentMapper.restoreDeletedById(existing.getId(), operator, now);
            }
            documentMapper.updateById(document);
        }
        return document.getId();
    }

    public FeishuPostDocumentDO findDocument(String folderToken, String documentId) {
        return documentMapper.selectOne(new LambdaQueryWrapper<FeishuPostDocumentDO>()
                .eq(FeishuPostDocumentDO::getFolderToken, folderToken)
                .eq(FeishuPostDocumentDO::getDocumentId, documentId)
                .eq(FeishuPostDocumentDO::getDeleted, Boolean.FALSE)
                .last("LIMIT 1"));
    }

    /** Returns the read record including a soft-deleted record, without applying MyBatis-Plus logical deletion. */
    public FeishuPostDocumentDO findDocumentIncludingDeleted(String folderToken, String documentId) {
        return documentMapper.selectIncludingDeleted(folderToken, documentId);
    }

    public void updateDocumentExtractedCount(Long documentId, int extractedCount, String operator) {
        FeishuPostDocumentDO document = documentMapper.selectById(documentId);
        if (document == null) {
            return;
        }
        document.setExtractedCount(extractedCount);
        document.setUpdater(operator);
        document.setUpdateTime(LocalDateTime.now());
        documentMapper.updateById(document);
    }

    public void markDocumentSkipped(Long runId, Long documentId, String operator) {
        FeishuPostDocumentDO document = documentMapper.selectById(documentId);
        if (document == null) {
            return;
        }
        document.setLastRunId(runId);
        document.setStatus("SKIPPED");
        document.setLastError(null);
        document.setUpdater(operator);
        document.setUpdateTime(LocalDateTime.now());
        documentMapper.updateById(document);
    }

    public void markDocumentCollectedEmpty(Long runId, Long documentId, String operator) {
        FeishuPostDocumentDO document = documentMapper.selectById(documentId);
        if (document == null) {
            return;
        }
        document.setLastRunId(runId);
        document.setCollected(Boolean.TRUE);
        document.setStatus("NO_JOBS");
        document.setLastError(null);
        document.setCollectedAt(LocalDateTime.now());
        document.setUpdater(operator);
        document.setUpdateTime(LocalDateTime.now());
        documentMapper.updateById(document);
    }

    public void updateDocumentsSeen(Long runId, int documentsSeen, String operator) {
        FeishuPostCollectionRunDO update = FeishuPostCollectionRunDO.builder()
                .id(runId)
                .documentsSeen(documentsSeen)
                .build();
        update.setUpdater(operator);
        update.setUpdateTime(LocalDateTime.now());
        runMapper.updateById(update);
    }

    public void markDocumentFailed(Long runId, Long documentId, String message, String operator) {
        if (documentId == null) {
            return;
        }
        FeishuPostDocumentDO document = documentMapper.selectById(documentId);
        if (document == null) {
            return;
        }
        document.setCollected(Boolean.FALSE);
        document.setStatus("FAILED");
        document.setLastRunId(runId);
        document.setLastError(abbreviate(message));
        document.setFailedCount(Math.max(1, document.getFailedCount() == null ? 0 : document.getFailedCount()));
        document.setUpdater(operator);
        document.setUpdateTime(LocalDateTime.now());
        documentMapper.updateById(document);
    }

    public void saveItem(FeishuPostDocumentItemDO item, String operator) {
        LocalDateTime now = LocalDateTime.now();
        item.setCreator(operator);
        item.setUpdater(operator);
        item.setCreateTime(now);
        item.setUpdateTime(now);
        item.setDeleted(Boolean.FALSE);
        itemMapper.insert(item);
    }

    public void fail(String message, String operator) {
        Long runId = context.currentRunId();
        if (runId == null) {
            return;
        }
        LocalDateTime now = LocalDateTime.now();
        int failedDocuments = failProcessingDocuments(runId, message, operator, now);
        FeishuPostCollectionRunDO update = FeishuPostCollectionRunDO.builder()
                .id(runId)
                .status("FAILED")
                .documentsFailed(failedDocuments)
                .errorMessage(abbreviate(message))
                .finishedAt(now)
                .build();
        update.setUpdater(operator);
        update.setUpdateTime(now);
        runMapper.updateById(update);
        context.clear();
    }

    /** Finalizes runs abandoned by a terminated process before a task can be run again. */
    public int recoverStaleRuns(LocalDateTime staleBefore, String operator) {
        LocalDateTime now = LocalDateTime.now();
        List<FeishuPostCollectionRunDO> staleRuns = runMapper.selectStaleRunsWithoutActiveLock(staleBefore, now);
        if (staleRuns.isEmpty()) {
            return 0;
        }
        String message = "采集进程在完成前退出，已自动回收为失败状态";
        for (FeishuPostCollectionRunDO run : staleRuns) {
            int failedDocuments = failProcessingDocuments(run.getId(), message, operator, now);
            FeishuPostCollectionRunDO update = FeishuPostCollectionRunDO.builder()
                    .id(run.getId())
                    .status("FAILED")
                    .documentsFailed(Math.max(failedDocuments,
                            run.getDocumentsFailed() == null ? 0 : run.getDocumentsFailed()))
                    .errorMessage(message)
                    .finishedAt(now)
                    .build();
            update.setUpdater(operator);
            update.setUpdateTime(now);
            runMapper.updateById(update);
        }
        return staleRuns.size();
    }

    /** Completes the audit only after the normal yj_post merge has finished. */
    public void completeAfterMerge(int collectedCount, List<Long> insertedPostIds, String operator) {
        Long runId = context.currentRunId();
        if (runId == null) {
            return;
        }
        List<FeishuPostDocumentItemDO> items = itemMapper.selectList(new LambdaQueryWrapper<FeishuPostDocumentItemDO>()
                .eq(FeishuPostDocumentItemDO::getRunId, runId)
                .eq(FeishuPostDocumentItemDO::getDeleted, Boolean.FALSE)
                .orderByAsc(FeishuPostDocumentItemDO::getId));
        List<FeishuPostDocumentDO> documents = documentMapper.selectList(new LambdaQueryWrapper<FeishuPostDocumentDO>()
                .eq(FeishuPostDocumentDO::getLastRunId, runId)
                .eq(FeishuPostDocumentDO::getDeleted, Boolean.FALSE)
                .orderByAsc(FeishuPostDocumentDO::getId));
        int created = 0;
        int failed = 0;
        Map<Long, DocumentStats> documentStats = new LinkedHashMap<>();
        for (int index = 0; index < items.size(); index++) {
            FeishuPostDocumentItemDO item = items.get(index);
            DocumentStats stats = documentStats.computeIfAbsent(item.getDocumentId(), ignored -> new DocumentStats());
            Long targetPostId = index < insertedPostIds.size() ? insertedPostIds.get(index) : null;
            if (targetPostId == null) {
                item.setStatus("FAILED");
                item.setErrorMessage("岗位新增后未取得正式岗位编号");
                failed++;
                stats.failed++;
            } else {
                item.setTargetPostId(targetPostId);
                item.setStatus("CREATED");
                item.setErrorMessage(null);
                created++;
                stats.created++;
            }
            item.setUpdater(operator);
            item.setUpdateTime(LocalDateTime.now());
            itemMapper.updateById(item);
        }
        int failedDocuments = (int) documents.stream()
                .filter(document -> "FAILED".equals(document.getStatus())
                        || "PARTIAL_FAILED".equals(document.getStatus()))
                .count();
        boolean mappingComplete = insertedPostIds.size() == items.size();
        String status = failed == 0 && failedDocuments == 0 && mappingComplete ? "SUCCESS" : "PARTIAL_FAILED";
        FeishuPostCollectionRunDO run = FeishuPostCollectionRunDO.builder()
                .id(runId)
                .status(status)
                .documentsProcessed(documents.size())
                .documentsFailed((int) documents.stream()
                        .filter(document -> "FAILED".equals(document.getStatus())
                                || "PARTIAL_FAILED".equals(document.getStatus()))
                        .count())
                .jobsExtracted(collectedCount)
                .jobsCreated(created)
                .jobsUpdated(0)
                .jobsSkipped(0)
                .jobsFailed(failed)
                .errorMessage(mappingComplete ? null : "岗位新增结果与飞书采集明细未完整对应")
                .finishedAt(LocalDateTime.now())
                .build();
        run.setUpdater(operator);
        run.setUpdateTime(LocalDateTime.now());
        runMapper.updateById(run);
        for (Map.Entry<Long, DocumentStats> entry : documentStats.entrySet()) {
            FeishuPostDocumentDO document = documentMapper.selectById(entry.getKey());
            if (document == null) {
                continue;
            }
            DocumentStats stats = entry.getValue();
            document.setCollected(stats.failed == 0);
            document.setStatus(stats.failed == 0 ? "COLLECTED" : "PARTIAL_FAILED");
            document.setCreatedCount(stats.created);
            document.setSkippedCount(0);
            document.setFailedCount(stats.failed);
            document.setCollectedAt(stats.failed == 0 ? LocalDateTime.now() : null);
            document.setUpdater(operator);
            document.setUpdateTime(LocalDateTime.now());
            documentMapper.updateById(document);
        }
        context.clear();
    }

    private static final class DocumentStats {
        private int created;
        private int failed;
    }

    private int failProcessingDocuments(Long runId, String message, String operator, LocalDateTime now) {
        List<FeishuPostDocumentDO> documents = documentMapper.selectList(
                new LambdaQueryWrapper<FeishuPostDocumentDO>()
                        .eq(FeishuPostDocumentDO::getLastRunId, runId)
                        .eq(FeishuPostDocumentDO::getStatus, "PROCESSING")
                        .eq(FeishuPostDocumentDO::getDeleted, Boolean.FALSE));
        for (FeishuPostDocumentDO document : documents) {
            document.setCollected(Boolean.FALSE);
            document.setStatus("FAILED");
            document.setLastError(abbreviate(message));
            document.setFailedCount(Math.max(1,
                    document.getFailedCount() == null ? 0 : document.getFailedCount()));
            document.setUpdater(operator);
            document.setUpdateTime(now);
            documentMapper.updateById(document);
        }
        return documents.size();
    }

    private String abbreviate(String value) {
        if (!StringUtils.hasText(value) || value.length() <= 900) {
            return value;
        }
        return value.substring(0, 900);
    }
}
