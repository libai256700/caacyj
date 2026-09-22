package com.huiyitech.agreement.service;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.agreement.dal.dataobject.agreement.AgreementDO;
import com.huiyitech.agreement.dal.mysql.agreement.AgreementMapper;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.Set;

@Service
public class AgreementServiceImpl extends AbstractAgreementResourceService<AgreementDO>
        implements AgreementService {

    private static final Set<String> WRITABLE_COLUMNS = columns("name", "type", "status", "tenant_id");
    private static final Set<String> LIKE_COLUMNS = columns("name", "type");

    @Resource
    private AgreementMapper agreementMapper;

    @Override
    protected BaseMapperX<AgreementDO> mapper() {
        return agreementMapper;
    }

    @Override
    protected Class<AgreementDO> entityClass() {
        return AgreementDO.class;
    }

    @Override
    protected Set<String> writableColumns() {
        return WRITABLE_COLUMNS;
    }

    @Override
    protected Set<String> likeColumns() {
        return LIKE_COLUMNS;
    }
}
