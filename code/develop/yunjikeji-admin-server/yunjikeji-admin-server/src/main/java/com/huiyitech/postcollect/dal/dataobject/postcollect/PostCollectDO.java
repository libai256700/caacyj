package com.huiyitech.postcollect.dal.dataobject.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

@TenantIgnore
@TableName("yj_post")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PostCollectDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String name;

    private String companyName;

    private String sourceCode;

    /** The configured channel that collected this post, for example feishu_folder. */
    private String collectionChannel;

    private String externalPostId;

    private String salaryRange;

    private String workArea;

    private String publishDate;

    private String detailUrl;

    private Boolean status;
}
