package com.huiyitech.practice.dal.mysql.practice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesBatchDO;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface PracticeExercisesBatchMapper extends BaseMapperX<PracticeExercisesBatchDO> {

    @Insert({
            "<script>",
            "INSERT INTO yj_practice_exercises_batch ",
            "(custom_account_id, catalog_batch_id, exercises_id, sort_no, creator, create_time, updater, update_time, deleted) ",
            "SELECT #{customerAccountId}, #{catalogBatchId}, ordered.exercise_id, ordered.sort_no, ",
            "#{operator}, #{now}, #{operator}, #{now}, b'0' ",
            "FROM (",
            "<foreach collection='exerciseIds' item='exerciseId' index='index' separator=' UNION ALL '>",
            "SELECT #{exerciseId} AS exercise_id, (#{index} + 1) AS sort_no",
            "</foreach>",
            ") ordered",
            "</script>"
    })
    int insertBatchByExerciseIds(@Param("customerAccountId") Long customerAccountId,
                                 @Param("catalogBatchId") Long catalogBatchId,
                                 @Param("exerciseIds") List<Long> exerciseIds,
                                 @Param("operator") String operator,
                                 @Param("now") LocalDateTime now);

    @Delete({
            "<script>",
            "DELETE FROM yj_practice_exercises_batch ",
            "WHERE custom_account_id = #{customerAccountId} ",
            "AND catalog_batch_id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    int physicalDeleteByCustomerAccountIdAndCatalogBatchIds(@Param("customerAccountId") Long customerAccountId,
                                                            @Param("catalogBatchIds") List<Long> catalogBatchIds);
}
