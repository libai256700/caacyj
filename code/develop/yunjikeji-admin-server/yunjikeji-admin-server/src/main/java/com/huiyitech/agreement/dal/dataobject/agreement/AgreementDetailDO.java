package com.huiyitech.agreement.dal.dataobject.agreement;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("yj_agreement_detail_info")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AgreementDetailDO extends TenantBaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long agreementInfoId;

    private String version;

    private String content;

    private Integer publishStatus;

    private LocalDateTime publishTime;
}
