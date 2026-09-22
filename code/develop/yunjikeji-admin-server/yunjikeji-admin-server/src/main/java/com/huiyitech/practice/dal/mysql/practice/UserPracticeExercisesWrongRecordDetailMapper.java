package com.huiyitech.practice.dal.mysql.practice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesWrongRecordDetailDO;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface UserPracticeExercisesWrongRecordDetailMapper extends BaseMapperX<UserPracticeExercisesWrongRecordDetailDO> {

    @Delete("DELETE FROM yj_user_practice_exercises_wrong_record_detail "
            + "WHERE customer_account_id = #{customerAccountId} AND exercises = #{exercisesId}")
    int deleteByCustomerAccountIdAndExercisesId(@Param("customerAccountId") Long customerAccountId,
                                                @Param("exercisesId") Long exercisesId);
}
