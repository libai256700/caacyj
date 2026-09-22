package com.huiyitech.postcollect.dal.dataobject.postcollect;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

import java.sql.Timestamp;

@TableName("yj_post_collection_task")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PostCollectTaskDO extends TenantBaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String name;

    private String collectionChannel;

    private Timestamp collectionTime;

    private Integer collectionCountRule;

    private String collectionKey;

    private Integer collectionNum;

    private Timestamp lastExecuteTime;

    private String lastExecuteResult;

    private Integer lastExecuteStatus;

    private Boolean status;
}
