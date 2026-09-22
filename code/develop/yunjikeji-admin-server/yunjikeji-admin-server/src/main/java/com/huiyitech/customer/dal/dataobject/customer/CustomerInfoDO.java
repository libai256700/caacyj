package com.huiyitech.customer.dal.dataobject.customer;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

@TableName("yj_customer_info")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CustomerInfoDO extends TenantBaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long customerAccountId;

    private String nickName;

    private String realName;

    private String idCard;

    private String sex;

    private String mobilePhone;

    private String email;

    private String avatarUrl;

    private String studentNo;

    private String schoolName;

    private String majorName;

    private String roleLabel;

    private String trainingDirection;
}
