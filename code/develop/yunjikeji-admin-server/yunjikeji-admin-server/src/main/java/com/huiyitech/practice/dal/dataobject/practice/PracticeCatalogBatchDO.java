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

@TableName("yj_practice_catalog_batch")
@TenantIgnore
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PracticeCatalogBatchDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("custom_account_id")
    private Long customerAccountId;

    private Long categoryId;

    private String categoryName;

    private Long recordId;

    private String sessionId;

    private String practiceId;

    private String mode;

    private Integer type;

    private String batchNo;

    private Integer total;

    private String nextPage;

    @TableField("is_completed")
    private Boolean completed;

    private Integer status;

    private Integer currentExercisesNo;
}
