package com.huiyitech.companyaudit.dal.mysql.companyaudit;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.huiyitech.companyaudit.dal.dataobject.companyaudit.CompanyAuditAttachmentDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface CompanyAuditAttachmentMapper extends BaseMapperX<CompanyAuditAttachmentDO> {

    default List<CompanyAuditAttachmentDO> selectListByCompanyId(Long companyId) {
        return selectList(new LambdaQueryWrapperX<CompanyAuditAttachmentDO>()
                .eq(CompanyAuditAttachmentDO::getCompanyId, companyId));
    }

    default void deleteByCompanyId(Long companyId) {
        delete(new LambdaQueryWrapperX<CompanyAuditAttachmentDO>()
                .eq(CompanyAuditAttachmentDO::getCompanyId, companyId));
    }

    default void updateTenantIdByCompanyId(Long companyId, Long tenantId, String updater) {
        CompanyAuditAttachmentDO update = new CompanyAuditAttachmentDO();
        update.setTenantId(tenantId);
        update.setUpdater(updater);
        update(update, new LambdaQueryWrapperX<CompanyAuditAttachmentDO>()
                .eq(CompanyAuditAttachmentDO::getCompanyId, companyId));
    }
}
