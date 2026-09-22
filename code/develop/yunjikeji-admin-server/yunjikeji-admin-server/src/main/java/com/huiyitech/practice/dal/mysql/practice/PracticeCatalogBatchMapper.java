package com.huiyitech.practice.dal.mysql.practice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCatalogBatchDO;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface PracticeCatalogBatchMapper extends BaseMapperX<PracticeCatalogBatchDO> {

    @Update("UPDATE yj_practice_catalog_batch SET status = 1, updater = #{operator}, update_time = #{updateTime} "
            + "WHERE id = #{catalogBatchId} AND custom_account_id = #{customerAccountId} "
            + "AND category_id IN (13, 14) AND mode = 'ASSESSMENT' "
            + "AND (status = 0 OR status = 1) AND is_completed = 0 AND deleted = b'0'")
    int markAssessmentBatchSaving(@Param("catalogBatchId") Long catalogBatchId,
                                  @Param("customerAccountId") Long customerAccountId,
                                  @Param("operator") String operator,
                                  @Param("updateTime") LocalDateTime updateTime);

    @Update("UPDATE yj_practice_catalog_batch SET status = 2, updater = #{operator}, update_time = #{updateTime} "
            + "WHERE id = #{catalogBatchId} AND custom_account_id = #{customerAccountId} "
            + "AND category_id IN (13, 14) AND mode = 'ASSESSMENT' "
            + "AND (status = 0 OR status = 1) AND is_completed = 0 AND deleted = b'0'")
    int finishAssessmentBatchAfterFailure(@Param("catalogBatchId") Long catalogBatchId,
                                          @Param("customerAccountId") Long customerAccountId,
                                          @Param("operator") String operator,
                                          @Param("updateTime") LocalDateTime updateTime);

    @Select("SELECT batch.* "
            + "FROM yj_practice_catalog_batch batch "
            + "INNER JOIN yj_user_practice_exercises_record record ON record.category_id = batch.id "
            + "WHERE record.customer_account_id = #{customerAccountId} "
            + "AND batch.category_id = #{categoryId} "
            + "AND batch.mode = #{mode} "
            + "ORDER BY batch.create_time DESC, batch.id DESC "
            + "LIMIT 1")
    PracticeCatalogBatchDO selectLatestByUserCategoryAndMode(@Param("customerAccountId") Long customerAccountId,
                                                               @Param("categoryId") Long categoryId,
                                                               @Param("mode") String mode);

    @Select("SELECT * "
            + "FROM yj_practice_catalog_batch "
            + "WHERE custom_account_id = #{customerAccountId} "
            + "AND type = #{type} "
            + "AND mode = #{mode} "
            + "ORDER BY create_time DESC, id DESC "
            + "LIMIT 1")
    PracticeCatalogBatchDO selectLatestByCustomerAccountIdAndTypeAndMode(@Param("customerAccountId") Long customerAccountId,
                                                                          @Param("type") Long type,
                                                                          @Param("mode") String mode);

    @Delete({
            "<script>",
            "DELETE FROM yj_practice_catalog_batch ",
            "WHERE custom_account_id = #{customerAccountId} ",
            "AND mode = #{mode} ",
            "AND id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    int physicalDeleteByCustomerAccountIdAndModeAndIds(@Param("customerAccountId") Long customerAccountId,
                                                       @Param("mode") String mode,
                                                       @Param("catalogBatchIds") List<Long> catalogBatchIds);
}
