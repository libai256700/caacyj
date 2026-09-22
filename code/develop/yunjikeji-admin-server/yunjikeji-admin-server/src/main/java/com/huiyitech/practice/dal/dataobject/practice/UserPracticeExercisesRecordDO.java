package com.huiyitech.practice.dal.dataobject.practice;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

@TableName("yj_user_practice_exercises_record")
@TenantIgnore
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserPracticeExercisesRecordDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long customerAccountId;

    private Long categoryId;

    private Integer totalScore;

    private Integer correctCount;

    private Integer wrongCount;

    private String fieldType;
}
