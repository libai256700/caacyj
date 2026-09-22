package com.huiyitech.app.practice.service;

import com.huiyitech.practice.dal.mysql.practice.PracticeCatalogBatchMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.Resource;
import java.time.LocalDateTime;

@Service
public class AssessmentBatchSaveStatusTransactionService {

    @Resource
    private PracticeCatalogBatchMapper practiceCatalogBatchMapper;

    @Transactional(propagation = Propagation.REQUIRES_NEW, rollbackFor = Exception.class)
    public void finishAssessmentBatchAfterFailure(Long catalogBatchId, Long customerAccountId) {
        if (catalogBatchId == null || customerAccountId == null) {
            return;
        }
        practiceCatalogBatchMapper.finishAssessmentBatchAfterFailure(catalogBatchId, customerAccountId,
                String.valueOf(customerAccountId), LocalDateTime.now());
    }
}
