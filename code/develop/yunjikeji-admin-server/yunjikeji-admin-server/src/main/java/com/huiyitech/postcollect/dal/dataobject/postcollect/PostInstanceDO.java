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
@TableName("yj_post_instance")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PostInstanceDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long taskInstanceId;

    private String name;

    private String companyName;

    private String sourceCode;

    /** The configured channel that produced this collection instance. */
    private String collectionChannel;

    private String externalPostId;

    private String salaryRange;

    private String workArea;

    private String publishDate;

    private String detailUrl;

    private Boolean status;
}
