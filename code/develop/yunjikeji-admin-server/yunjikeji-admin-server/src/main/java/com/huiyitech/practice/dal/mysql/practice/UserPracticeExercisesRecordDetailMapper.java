package com.huiyitech.practice.dal.mysql.practice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDetailDO;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface UserPracticeExercisesRecordDetailMapper extends BaseMapperX<UserPracticeExercisesRecordDetailDO> {

    @Delete({
            "<script>",
            "DELETE detail FROM yj_user_practice_exercises_record_detail detail ",
            "INNER JOIN yj_user_practice_exercises_record record ",
            "ON record.id = detail.record_id ",
            "WHERE record.customer_account_id = #{customerAccountId} ",
            "AND record.field_type = #{fieldType} ",
            "AND record.category_id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    int physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(
            @Param("customerAccountId") Long customerAccountId,
            @Param("fieldType") String fieldType,
            @Param("catalogBatchIds") List<Long> catalogBatchIds);

    @Delete({
            "<script>",
            "DELETE detail FROM yj_user_practice_exercises_record_detail detail ",
            "INNER JOIN yj_user_practice_exercises_record record ON record.id = detail.record_id ",
            "WHERE record.customer_account_id = #{customerAccountId} ",
            "AND record.category_id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    int physicalDeleteByCustomerAccountIdAndCatalogBatchIds(@Param("customerAccountId") Long customerAccountId,
                                                            @Param("catalogBatchIds") List<Long> catalogBatchIds);
}
