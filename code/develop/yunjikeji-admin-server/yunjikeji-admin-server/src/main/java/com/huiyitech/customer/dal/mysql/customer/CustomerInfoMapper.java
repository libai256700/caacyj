package com.huiyitech.customer.dal.mysql.customer;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.huiyitech.customer.dal.dataobject.customer.CustomerInfoDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CustomerInfoMapper extends BaseMapperX<CustomerInfoDO> {

    default CustomerInfoDO selectByCustomerAccountId(Long customerAccountId) {
        return selectOne(new LambdaQueryWrapperX<CustomerInfoDO>()
                .eq(CustomerInfoDO::getCustomerAccountId, customerAccountId)
                .last("LIMIT 1"));
    }
}
