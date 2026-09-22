package com.huiyitech.practice.dal.dataobject.practice;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("yj_user_practice_exercises_wrong_record_detail")
@TenantIgnore
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserPracticeExercisesWrongRecordDetailDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long customerAccountId;

    private Long recordDetailId;

    @TableField("exercises")
    private Long exercisesId;

    private String answerCode;

    private String correctAnswerCode;

    private Integer wrongCount;

    private LocalDateTime latestWrongTime;
}
