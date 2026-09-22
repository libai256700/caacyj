package com.huiyitech.customer.dal.mysql.customer;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.huiyitech.customer.dal.dataobject.customer.CustomerAccountDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CustomerAccountMapper extends BaseMapperX<CustomerAccountDO> {

    int AUDIT_STATUS_APPROVED = 2;

    default CustomerAccountDO selectByMobile(String mobile, boolean activeOnly) {
        LambdaQueryWrapperX<CustomerAccountDO> query = new LambdaQueryWrapperX<CustomerAccountDO>()
                .eq(CustomerAccountDO::getMobile, mobile)
                .orderByDesc(CustomerAccountDO::getId)
                .last("LIMIT 1");
        if (activeOnly) {
            query.eq(CustomerAccountDO::getStatus, true)
                    .eq(CustomerAccountDO::getAuditStatus, AUDIT_STATUS_APPROVED);
        }
        return selectOne(query);
    }

    default CustomerAccountDO selectByUsername(String username) {
        return selectOne(new LambdaQueryWrapperX<CustomerAccountDO>()
                .eq(CustomerAccountDO::getUsername, username)
                .orderByDesc(CustomerAccountDO::getId)
                .last("LIMIT 1"));
    }
}
