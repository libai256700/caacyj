package com.huiyitech.agreement.service;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.huiyitech.agreement.dal.dataobject.agreement.AgreementDetailDO;
import com.huiyitech.agreement.dal.mysql.agreement.AgreementDetailMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.Set;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
public class AgreementDetailServiceImpl extends AbstractAgreementResourceService<AgreementDetailDO>
        implements AgreementDetailService {

    private static final int PUBLISH_STATUS_PUBLISHED = 1;
    private static final int PUBLISH_STATUS_WITHDRAWN = 2;

    private static final Set<String> WRITABLE_COLUMNS = columns("agreement_info_id", "version", "content",
            "publish_status", "publish_time", "tenant_id");
    private static final Set<String> LIKE_COLUMNS = columns("version");

    @Resource
    private AgreementDetailMapper agreementDetailMapper;

    @Override
    protected BaseMapperX<AgreementDetailDO> mapper() {
        return agreementDetailMapper;
    }

    @Override
    protected Class<AgreementDetailDO> entityClass() {
        return AgreementDetailDO.class;
    }

    @Override
    protected Set<String> writableColumns() {
        return WRITABLE_COLUMNS;
    }

    @Override
    protected Set<String> likeColumns() {
        return LIKE_COLUMNS;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void publish(Map<String, Object> body) {
        Long id = requireId(body);
        AgreementDetailDO detail = agreementDetailMapper.selectById(id);
        if (detail == null) {
            throw invalidParamException("Record does not exist: {}", id);
        }
        if (detail.getAgreementInfoId() == null) {
            throw invalidParamException("agreement_info_id cannot be empty");
        }

        AgreementDetailDO withdraw = new AgreementDetailDO();
        withdraw.setPublishStatus(PUBLISH_STATUS_WITHDRAWN);
        agreementDetailMapper.update(withdraw, new UpdateWrapper<AgreementDetailDO>()
                .eq("agreement_info_id", detail.getAgreementInfoId())
                .ne("id", id));

        AgreementDetailDO update = new AgreementDetailDO();
        update.setId(id);
        update.setPublishStatus(PUBLISH_STATUS_PUBLISHED);
        update.setPublishTime(LocalDateTime.now());
        agreementDetailMapper.updateById(update);
    }

    @Override
    public void withdraw(Map<String, Object> body) {
        Long id = requireId(body);
        AgreementDetailDO update = new AgreementDetailDO();
        update.setId(id);
        update.setPublishStatus(PUBLISH_STATUS_WITHDRAWN);
        if (agreementDetailMapper.updateById(update) == 0) {
            throw invalidParamException("Record does not exist: {}", id);
        }
    }
}
