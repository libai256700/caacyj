package com.huiyitech.postcollect.dal.dataobject.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

import java.time.LocalDateTime;

@TenantIgnore
@TableName("yj_feishu_post_collection_run")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class FeishuPostCollectionRunDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long taskId;
    private String folderToken;
    private String status;
    private Integer documentsSeen;
    private Integer documentsProcessed;
    private Integer documentsFailed;
    private Integer jobsExtracted;
    private Integer jobsCreated;
    private Integer jobsUpdated;
    private Integer jobsSkipped;
    private Integer jobsFailed;
    private String errorMessage;
    private LocalDateTime startedAt;
    private LocalDateTime finishedAt;
}
