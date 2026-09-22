package com.huiyitech.practice.dal.mysql.practice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.huiyitech.practice.dal.dataobject.practice.PracticeStepDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface PracticeStepMapper extends BaseMapperX<PracticeStepDO> {

    default PracticeStepDO selectByIdAndCategoryId(Long id, Long categoryId) {
        return selectOne(new LambdaQueryWrapperX<PracticeStepDO>()
                .eq(PracticeStepDO::getId, id)
                .eq(PracticeStepDO::getCategoryId, categoryId)
                .eq(PracticeStepDO::getDeleted, Boolean.FALSE));
    }
}
