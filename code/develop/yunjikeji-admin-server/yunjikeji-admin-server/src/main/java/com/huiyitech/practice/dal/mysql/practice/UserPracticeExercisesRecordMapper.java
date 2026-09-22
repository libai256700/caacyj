package com.huiyitech.practice.dal.mysql.practice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDO;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface UserPracticeExercisesRecordMapper extends BaseMapperX<UserPracticeExercisesRecordDO> {

    @Select({
            "<script>",
            "SELECT id FROM yj_user_practice_exercises_record ",
            "WHERE customer_account_id = #{customerAccountId} ",
            "AND field_type = #{fieldType} ",
            "AND category_id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    List<Long> selectAssessmentRecordIdsForPhysicalDelete(@Param("customerAccountId") Long customerAccountId,
                                                          @Param("fieldType") String fieldType,
                                                          @Param("catalogBatchIds") List<Long> catalogBatchIds);

    @Delete({
            "<script>",
            "DELETE FROM yj_user_practice_exercises_record ",
            "WHERE customer_account_id = #{customerAccountId} ",
            "AND field_type = #{fieldType} ",
            "AND category_id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    int physicalDeleteAssessmentByCustomerAccountIdAndCatalogBatchIds(
            @Param("customerAccountId") Long customerAccountId,
            @Param("fieldType") String fieldType,
            @Param("catalogBatchIds") List<Long> catalogBatchIds);

    @Select({
            "<script>",
            "SELECT id FROM yj_user_practice_exercises_record ",
            "WHERE customer_account_id = #{customerAccountId} ",
            "AND category_id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    List<Long> selectRecordIdsForPhysicalDelete(@Param("customerAccountId") Long customerAccountId,
                                                @Param("catalogBatchIds") List<Long> catalogBatchIds);

    @Delete({
            "<script>",
            "DELETE FROM yj_user_practice_exercises_record ",
            "WHERE customer_account_id = #{customerAccountId} ",
            "AND category_id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    int physicalDeleteByCustomerAccountIdAndCatalogBatchIds(@Param("customerAccountId") Long customerAccountId,
                                                            @Param("catalogBatchIds") List<Long> catalogBatchIds);
}
