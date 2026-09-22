package com.huiyitech.chart.dal.dataobject;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

@TableName("yj_account_login_log")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AccountLoginLogDO extends TenantBaseDO {

    public static final int TYPE_LOGIN = 0;
    public static final int TYPE_KNOWLEDGE_CALL = 10;

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long customerAccountId;

    private Integer type;

    private String operatorTime;
}
