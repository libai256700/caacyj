package com.huiyitech.postcollect.dal.dataobject.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

@TenantIgnore
@TableName("yj_post_collection_task_instance")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PostCollectionTaskInstanceDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * Keep the current document/database spelling: stauts.
     */
    private Integer stauts;

    private Long taskId;

    private Integer collectionCount;
}
