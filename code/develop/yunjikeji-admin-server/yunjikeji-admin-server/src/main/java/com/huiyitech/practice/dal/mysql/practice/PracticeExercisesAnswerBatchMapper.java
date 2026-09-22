package com.huiyitech.practice.dal.mysql.practice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerBatchDO;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface PracticeExercisesAnswerBatchMapper extends BaseMapperX<PracticeExercisesAnswerBatchDO> {

    @Insert({
            "<script>",
            "INSERT INTO yj_practice_exercises_answer_batch ",
            "(exercises_batch_id, answer_id, question_type, answer_code, answer_content, is_correct, sort_no, ",
            "creator, create_time, updater, update_time, deleted) ",
            "VALUES ",
            "<foreach collection='answerBatches' item='item' separator=','>",
            "(#{item.exercisesBatchId}, #{item.answerId}, #{item.questionType}, #{item.answerCode}, ",
            "#{item.answerContent}, #{item.correct}, #{item.sortNo}, ",
            "#{operator}, #{now}, #{operator}, #{now}, b'0')",
            "</foreach>",
            "</script>"
    })
    int insertBatch(@Param("answerBatches") List<PracticeExercisesAnswerBatchDO> answerBatches,
                    @Param("operator") String operator,
                    @Param("now") LocalDateTime now);

    @Insert({
            "INSERT INTO yj_practice_exercises_answer_batch ",
            "(exercises_batch_id, answer_id, question_type, answer_code, answer_content, is_correct, sort_no, ",
            "creator, create_time, updater, update_time, deleted) ",
            "SELECT batch.id, answer.id, answer.question_type, answer.answer_code, answer.answer_content, answer.is_correct, answer.sort_no, ",
            "#{operator}, #{now}, #{operator}, #{now}, b'0' ",
            "FROM yj_practice_exercises_batch batch ",
            "INNER JOIN yj_practice_exercises_answer answer ON answer.exercises_id = batch.exercises_id ",
            "WHERE batch.catalog_batch_id = #{catalogBatchId} ",
            "AND batch.deleted = b'0' ",
            "AND answer.deleted = b'0' ",
            "ORDER BY batch.sort_no ASC, answer.sort_no ASC, answer.id ASC"
    })
    int insertBatchByCatalogBatchId(@Param("catalogBatchId") Long catalogBatchId,
                                    @Param("operator") String operator,
                                    @Param("now") LocalDateTime now);

    @Delete({
            "<script>",
            "DELETE answer_batch FROM yj_practice_exercises_answer_batch answer_batch ",
            "INNER JOIN yj_practice_exercises_batch exercise_batch ",
            "ON exercise_batch.id = answer_batch.exercises_batch_id ",
            "WHERE exercise_batch.custom_account_id = #{customerAccountId} ",
            "AND exercise_batch.catalog_batch_id IN ",
            "<foreach collection='catalogBatchIds' item='catalogBatchId' open='(' separator=',' close=')'>",
            "#{catalogBatchId}",
            "</foreach>",
            "</script>"
    })
    int physicalDeleteByCustomerAccountIdAndCatalogBatchIds(@Param("customerAccountId") Long customerAccountId,
                                                            @Param("catalogBatchIds") List<Long> catalogBatchIds);
}
