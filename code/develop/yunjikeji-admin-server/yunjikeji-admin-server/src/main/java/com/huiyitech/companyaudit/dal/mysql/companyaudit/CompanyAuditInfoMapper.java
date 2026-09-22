package com.huiyitech.companyaudit.dal.mysql.companyaudit;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.huiyitech.companyaudit.dal.dataobject.companyaudit.CompanyAuditInfoDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CompanyAuditInfoMapper extends BaseMapperX<CompanyAuditInfoDO> {

    default CompanyAuditInfoDO selectLatestByUserId(Long userId) {
        return selectOne(new LambdaQueryWrapperX<CompanyAuditInfoDO>()
                .eq(CompanyAuditInfoDO::getUserId, userId)
                .orderByDesc(CompanyAuditInfoDO::getId)
                .last("LIMIT 1"));
    }

    default CompanyAuditInfoDO selectLatestByCompanyAccountFrontId(Long companyAccountFrontId) {
        return selectOne(new LambdaQueryWrapperX<CompanyAuditInfoDO>()
                .eq(CompanyAuditInfoDO::getCompanyAccountFrontId, companyAccountFrontId)
                .orderByDesc(CompanyAuditInfoDO::getId)
                .last("LIMIT 1"));
    }

    default CompanyAuditInfoDO selectPendingByContactMobileAndName(String contactMobile, String name, Long excludeId) {
        return selectOne(new LambdaQueryWrapperX<CompanyAuditInfoDO>()
                .eq(CompanyAuditInfoDO::getContactMobile, contactMobile)
                .eq(CompanyAuditInfoDO::getName, name)
                .eq(CompanyAuditInfoDO::getAuditStatus, 1)
                .neIfPresent(CompanyAuditInfoDO::getId, excludeId)
                .orderByDesc(CompanyAuditInfoDO::getId)
                .last("LIMIT 1"));
    }
}
