package com.huiyitech.postcollect.dal.dataobject.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

@TenantIgnore
@TableName("yj_feishu_post_document_item")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class FeishuPostDocumentItemDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long runId;
    private Long documentId;
    private Integer itemIndex;
    private String sourceText;
    private String aiRawJson;
    private String name;
    private String companyName;
    private String sourceCode;
    private String externalPostId;
    private String salaryRange;
    private String workArea;
    private String publishDate;
    private String detailUrl;
    private Long targetPostId;
    private String status;
    private String errorMessage;
}
