package com.huiyitech.customer.dal.dataobject.customer;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

import java.time.LocalDateTime;

@TableName("yj_customer_account")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CustomerAccountDO extends TenantBaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String username;

    private String mobile;

    private String passwordSalt;

    private String password;

    private Boolean status;

    private Integer auditStatus;

    private LocalDateTime passwordInitializedAt;

    private LocalDateTime lastLoginAt;

    private String lastLoginChannel;
}
