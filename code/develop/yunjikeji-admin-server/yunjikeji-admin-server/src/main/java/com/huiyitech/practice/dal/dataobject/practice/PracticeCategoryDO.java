package com.huiyitech.practice.dal.dataobject.practice;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

@TableName("yj_practice_category")
@TenantIgnore
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PracticeCategoryDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String categoryName;

    private Boolean categoryStatus;

    private String fieldType;

    private Integer catalogType;

    private Integer sortNo;
}
