package com.huiyitech.companyaudit.dal.mysql.companyaudit;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.huiyitech.companyaudit.dal.dataobject.companyaudit.CompanyAccountFrontDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CompanyAccountFrontMapper extends BaseMapperX<CompanyAccountFrontDO> {

    default CompanyAccountFrontDO selectByUsername(String username) {
        return selectOne(new LambdaQueryWrapperX<CompanyAccountFrontDO>()
                .eq(CompanyAccountFrontDO::getUsername, username)
                .orderByDesc(CompanyAccountFrontDO::getId)
                .last("LIMIT 1"));
    }
}
