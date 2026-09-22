package com.huiyitech.practice.dal.dataobject.practice;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

@TableName("yj_practice_exercises")
@TenantIgnore
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PracticeExercisesDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long stepId;

    private Long categoryId;

    private String questionStem;

    private String questionType;

    private Boolean questionStatus;

    private Boolean isRequired;

    private Integer score;

    private Integer sortNo;

    private String correctMemo;

    private String videoBucket;

    private String videoObjectKey;

    private String videoUrl;
}
