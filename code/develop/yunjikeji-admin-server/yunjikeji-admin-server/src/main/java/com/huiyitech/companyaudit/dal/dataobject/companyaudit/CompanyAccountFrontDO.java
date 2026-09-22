package com.huiyitech.companyaudit.dal.dataobject.companyaudit;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

@TableName("yj_company_account_front")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CompanyAccountFrontDO extends TenantBaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String username;

    private String password;

    private Boolean status;

    private Integer auditStatus;
}
