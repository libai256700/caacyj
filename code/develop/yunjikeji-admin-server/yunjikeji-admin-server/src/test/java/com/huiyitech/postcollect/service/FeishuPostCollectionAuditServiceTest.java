package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostCollectionRunDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.FeishuPostCollectionRunMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.FeishuPostDocumentMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.LocalDateTime;
import java.util.Collections;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FeishuPostCollectionAuditServiceTest {

    private final FeishuPostDocumentMapper documentMapper = mock(FeishuPostDocumentMapper.class);
    private final FeishuPostCollectionRunMapper runMapper = mock(FeishuPostCollectionRunMapper.class);
    private final FeishuCollectionContext context = new FeishuCollectionContext();
    private FeishuPostCollectionAuditService service;

    @BeforeEach
    void setUp() {
        service = new FeishuPostCollectionAuditService();
        ReflectionTestUtils.setField(service, "documentMapper", documentMapper);
        ReflectionTestUtils.setField(service, "runMapper", runMapper);
        ReflectionTestUtils.setField(service, "context", context);
    }

    @Test
    void upsertDocumentShouldRestoreSoftDeletedDocumentBeforeUpdatingIt() {
        FeishuPostDocumentDO existing = new FeishuPostDocumentDO();
        existing.setId(88L);
        existing.setFolderToken("folder-1");
        existing.setDocumentId("doc-1");
        existing.setDeleted(Boolean.TRUE);
        when(documentMapper.selectIncludingDeleted("folder-1", "doc-1")).thenReturn(existing);
        when(documentMapper.restoreDeletedById(eq(88L), eq("system"), any())).thenReturn(1);

        Long documentId = service.upsertDocument(9L, "folder-1", "doc-1", "招聘日报_2026-08-21",
                "https://example.com/doc-1", "revision-1", "hash-1", "system", 0);

        assertEquals(88L, documentId);
        verify(documentMapper).restoreDeletedById(eq(88L), eq("system"), any());
        ArgumentCaptor<FeishuPostDocumentDO> captor = ArgumentCaptor.forClass(FeishuPostDocumentDO.class);
        verify(documentMapper).updateById(captor.capture());
        assertEquals(Boolean.FALSE, captor.getValue().getDeleted());
        assertEquals("PROCESSING", captor.getValue().getStatus());
        assertEquals(9L, captor.getValue().getLastRunId());
        verify(documentMapper, never()).insert(any(FeishuPostDocumentDO.class));
    }

    @Test
    void findDocumentIncludingDeletedShouldUseTheUniqueDocumentKey() {
        FeishuPostDocumentDO existing = new FeishuPostDocumentDO();
        existing.setId(99L);
        when(documentMapper.selectIncludingDeleted("folder-1", "doc-1")).thenReturn(existing);

        assertEquals(existing, service.findDocumentIncludingDeleted("folder-1", "doc-1"));

        verify(documentMapper).selectIncludingDeleted("folder-1", "doc-1");
    }

    @Test
    void failShouldFinalizeDocumentsStillProcessingInTheCurrentRun() {
        FeishuPostDocumentDO document = new FeishuPostDocumentDO();
        document.setId(101L);
        document.setLastRunId(11L);
        document.setStatus("PROCESSING");
        document.setFailedCount(0);
        when(documentMapper.selectList(any())).thenReturn(Collections.singletonList(document));
        context.bind(11L);

        service.fail("model request timed out", "system");

        ArgumentCaptor<FeishuPostDocumentDO> documentCaptor = ArgumentCaptor.forClass(FeishuPostDocumentDO.class);
        verify(documentMapper).updateById(documentCaptor.capture());
        assertEquals("FAILED", documentCaptor.getValue().getStatus());
        assertEquals("model request timed out", documentCaptor.getValue().getLastError());
        ArgumentCaptor<FeishuPostCollectionRunDO> runCaptor =
                ArgumentCaptor.forClass(FeishuPostCollectionRunDO.class);
        verify(runMapper).updateById(runCaptor.capture());
        assertEquals("FAILED", runCaptor.getValue().getStatus());
        assertEquals(1, runCaptor.getValue().getDocumentsFailed());
        assertEquals(null, context.currentRunId());
    }

    @Test
    void recoverStaleRunsShouldFinalizeTheRunAndItsProcessingDocuments() {
        FeishuPostCollectionRunDO run = FeishuPostCollectionRunDO.builder()
                .id(12L)
                .status("RUNNING")
                .documentsFailed(0)
                .build();
        FeishuPostDocumentDO document = new FeishuPostDocumentDO();
        document.setId(102L);
        document.setLastRunId(12L);
        document.setStatus("PROCESSING");
        document.setFailedCount(0);
        when(runMapper.selectStaleRunsWithoutActiveLock(any(), any())).thenReturn(Collections.singletonList(run));
        when(documentMapper.selectList(any())).thenReturn(Collections.singletonList(document));

        assertEquals(1, service.recoverStaleRuns(LocalDateTime.now(), "system"));

        ArgumentCaptor<FeishuPostDocumentDO> documentCaptor = ArgumentCaptor.forClass(FeishuPostDocumentDO.class);
        verify(documentMapper).updateById(documentCaptor.capture());
        assertEquals("FAILED", documentCaptor.getValue().getStatus());
        assertEquals("采集进程在完成前退出，已自动回收为失败状态", documentCaptor.getValue().getLastError());
        ArgumentCaptor<FeishuPostCollectionRunDO> runCaptor =
                ArgumentCaptor.forClass(FeishuPostCollectionRunDO.class);
        verify(runMapper).updateById(runCaptor.capture());
        assertEquals("FAILED", runCaptor.getValue().getStatus());
        assertEquals(1, runCaptor.getValue().getDocumentsFailed());
    }
}
