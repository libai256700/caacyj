package com.huiyitech.chart.dal.mysql;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.chart.dal.dataobject.AccountLoginLogDO;
import com.huiyitech.chart.controller.vo.ChartTrendPointRespVO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface AccountLoginLogMapper extends BaseMapperX<AccountLoginLogDO> {

    @Select("SELECT COUNT(DISTINCT customer_account_id) FROM yj_account_login_log "
            + "WHERE deleted = b'0' AND type = 0 AND customer_account_id IS NOT NULL "
            + "AND operator_time >= #{startTimeText} AND operator_time < #{endTimeText}")
    Long selectTodayActiveUserCount(@Param("startTimeText") String startTimeText,
                                    @Param("endTimeText") String endTimeText);

    @Select("SELECT COUNT(1) FROM yj_account_login_log "
            + "WHERE deleted = b'0' AND type = 0 AND operator_time >= #{startTimeText} AND operator_time < #{endTimeText}")
    Long selectLoginCount(@Param("startTimeText") String startTimeText,
                          @Param("endTimeText") String endTimeText);

    @Select("SELECT DATE_FORMAT(STR_TO_DATE(operator_time, '%Y-%m-%d %H:%i:%s'), '%Y-%m-%d') AS date, COUNT(1) AS count "
            + "FROM yj_account_login_log "
            + "WHERE deleted = b'0' AND type = 0 AND operator_time >= #{startTimeText} AND operator_time < #{endTimeText} "
            + "GROUP BY DATE_FORMAT(STR_TO_DATE(operator_time, '%Y-%m-%d %H:%i:%s'), '%Y-%m-%d') "
            + "ORDER BY date")
    List<ChartTrendPointRespVO> selectLoginTrend(@Param("startTimeText") String startTimeText,
                                                 @Param("endTimeText") String endTimeText);

    @Select("SELECT COUNT(1) FROM yj_account_login_log "
            + "WHERE deleted = b'0' AND type = 10 AND operator_time >= #{startTimeText} AND operator_time < #{endTimeText}")
    Long selectKnowledgeCallCount(@Param("startTimeText") String startTimeText,
                                  @Param("endTimeText") String endTimeText);

    @Select("SELECT COUNT(1) FROM yj_account_login_log WHERE deleted = b'0' AND type = 10")
    Long selectTotalKnowledgeCallCount();

    @Select("SELECT DATE_FORMAT(STR_TO_DATE(operator_time, '%Y-%m-%d %H:%i:%s'), '%Y-%m-%d') AS date, COUNT(1) AS count "
            + "FROM yj_account_login_log "
            + "WHERE deleted = b'0' AND type = 10 AND operator_time >= #{startTimeText} AND operator_time < #{endTimeText} "
            + "GROUP BY DATE_FORMAT(STR_TO_DATE(operator_time, '%Y-%m-%d %H:%i:%s'), '%Y-%m-%d') "
            + "ORDER BY date")
    List<ChartTrendPointRespVO> selectKnowledgeCallTrend(@Param("startTimeText") String startTimeText,
                                                         @Param("endTimeText") String endTimeText);

    @Select("SELECT COUNT(1) FROM yj_customer_account "
            + "WHERE deleted = b'0' AND create_time >= #{startTime} AND create_time < #{endTime}")
    Long selectRegisterCount(@Param("startTime") LocalDateTime startTime,
                             @Param("endTime") LocalDateTime endTime);

    @Select("SELECT COUNT(1) FROM yj_customer_account WHERE deleted = b'0'")
    Long selectTotalRegisterCount();

    @Select("SELECT DATE_FORMAT(create_time, '%Y-%m-%d') AS date, COUNT(1) AS count "
            + "FROM yj_customer_account "
            + "WHERE deleted = b'0' AND create_time >= #{startTime} AND create_time < #{endTime} "
            + "GROUP BY DATE_FORMAT(create_time, '%Y-%m-%d') "
            + "ORDER BY date")
    List<ChartTrendPointRespVO> selectRegisterTrend(@Param("startTime") LocalDateTime startTime,
                                                    @Param("endTime") LocalDateTime endTime);

    @Select("SELECT COUNT(DISTINCT record_id) FROM yj_user_practice_exercises_record_detail "
            + "WHERE deleted = b'0' AND create_time >= #{startTime} AND create_time < #{endTime}")
    Long selectPracticeRecordCount(@Param("startTime") LocalDateTime startTime,
                                   @Param("endTime") LocalDateTime endTime);

    @Select("SELECT COUNT(1) FROM yj_user_practice_exercises_record_detail "
            + "WHERE deleted = b'0' AND create_time >= #{startTime} AND create_time < #{endTime}")
    Long selectAnsweredQuestionCount(@Param("startTime") LocalDateTime startTime,
                                     @Param("endTime") LocalDateTime endTime);

    @Select("SELECT COUNT(1) FROM yj_user_practice_exercises_record_detail WHERE deleted = b'0'")
    Long selectTotalAnsweredQuestionCount();

    @Select("SELECT COUNT(1) FROM yj_user_practice_exercises_record_detail "
            + "WHERE deleted = b'0' AND is_correct = b'1' "
            + "AND create_time >= #{startTime} AND create_time < #{endTime}")
    Long selectCorrectQuestionCount(@Param("startTime") LocalDateTime startTime,
                                    @Param("endTime") LocalDateTime endTime);

    @Select("SELECT COUNT(1) FROM yj_user_practice_exercises_record_detail "
            + "WHERE deleted = b'0' AND is_correct = b'0' "
            + "AND create_time >= #{startTime} AND create_time < #{endTime}")
    Long selectWrongQuestionCount(@Param("startTime") LocalDateTime startTime,
                                  @Param("endTime") LocalDateTime endTime);

    @Select("SELECT DATE_FORMAT(create_time, '%Y-%m-%d') AS date, COUNT(1) AS count "
            + "FROM yj_user_practice_exercises_record_detail "
            + "WHERE deleted = b'0' AND create_time >= #{startTime} AND create_time < #{endTime} "
            + "GROUP BY DATE_FORMAT(create_time, '%Y-%m-%d') "
            + "ORDER BY date")
    List<ChartTrendPointRespVO> selectPracticeTrend(@Param("startTime") LocalDateTime startTime,
                                                    @Param("endTime") LocalDateTime endTime);
}
