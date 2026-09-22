package com.huiyitech.companyaudit.dal.dataobject.companyaudit;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.*;

import java.time.LocalDateTime;

@TableName("yj_audit_info")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CompanyAuditInfoDO extends TenantBaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private Long companyAccountFrontId;

    private String name;

    private String creditCode;

    private String legalPerson;

    private String legalPersonId;

    private String contactName;

    private String contactMobile;

    private Integer auditStatus;

    private String auditReason;

    private LocalDateTime auditTime;

    private Long auditUserId;
}
