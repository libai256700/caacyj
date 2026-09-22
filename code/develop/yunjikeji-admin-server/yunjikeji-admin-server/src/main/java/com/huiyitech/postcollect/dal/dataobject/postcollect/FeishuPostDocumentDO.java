package com.huiyitech.postcollect.dal.dataobject.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

import java.time.LocalDateTime;

@TenantIgnore
@TableName("yj_feishu_post_document")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class FeishuPostDocumentDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String folderToken;
    private String documentId;
    private String documentName;
    private String documentUrl;
    private String documentRevisionId;
    private String contentHash;
    private Boolean collected;
    private String status;
    private Long lastRunId;
    private String lastError;
    private Integer extractedCount;
    private Integer createdCount;
    private Integer updatedCount;
    private Integer skippedCount;
    private Integer failedCount;
    private LocalDateTime collectedAt;
}
