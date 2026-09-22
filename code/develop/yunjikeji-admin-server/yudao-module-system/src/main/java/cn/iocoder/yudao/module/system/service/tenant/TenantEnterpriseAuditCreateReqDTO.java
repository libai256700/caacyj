package cn.iocoder.yudao.module.system.service.tenant;

import lombok.Data;

import java.util.List;

@Data
public class TenantEnterpriseAuditCreateReqDTO {

    private String name;

    private String contactName;

    private String contactMobile;

    private Integer status;

    private List<String> websites;
}
