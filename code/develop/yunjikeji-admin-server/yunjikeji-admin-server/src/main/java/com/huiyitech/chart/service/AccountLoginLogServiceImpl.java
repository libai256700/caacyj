package com.huiyitech.chart.service;

import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import com.huiyitech.chart.dal.dataobject.AccountLoginLogDO;
import com.huiyitech.chart.dal.mysql.AccountLoginLogMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

@Service
@RequiredArgsConstructor
public class AccountLoginLogServiceImpl implements AccountLoginLogService {

    private static final DateTimeFormatter OPERATOR_TIME_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final AccountLoginLogMapper accountLoginLogMapper;

    @Override
    public void recordLogin(Long customerAccountId) {
        insertLog(customerAccountId, AccountLoginLogDO.TYPE_LOGIN);
    }

    @Override
    public void recordKnowledgeCallIfPresent(Long customerAccountId) {
        if (customerAccountId == null || customerAccountId <= 0) {
            return;
        }
        insertLog(customerAccountId, AccountLoginLogDO.TYPE_KNOWLEDGE_CALL);
    }

    private void insertLog(Long customerAccountId, Integer type) {
        if (customerAccountId == null || customerAccountId <= 0) {
            return;
        }
        LocalDateTime now = LocalDateTime.now();
        AccountLoginLogDO log = AccountLoginLogDO.builder()
                .customerAccountId(customerAccountId)
                .type(type)
                .operatorTime(now.format(OPERATOR_TIME_FORMATTER))
                .build();
        log.setCreator(String.valueOf(customerAccountId));
        log.setCreateTime(now);
        log.setUpdater(String.valueOf(customerAccountId));
        log.setUpdateTime(now);
        log.setDeleted(false);
        TenantUtils.executeIgnore(() -> accountLoginLogMapper.insert(log));
    }
}
