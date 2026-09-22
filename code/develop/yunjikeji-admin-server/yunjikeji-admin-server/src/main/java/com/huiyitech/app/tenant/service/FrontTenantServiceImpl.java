package com.huiyitech.app.tenant.service;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.module.system.dal.dataobject.tenant.TenantDO;
import cn.iocoder.yudao.module.system.service.tenant.TenantService;
import com.huiyitech.app.tenant.controller.vo.AppTenantListRespVO;
import com.huiyitech.framework.security.AppMobileAuthUtils;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class FrontTenantServiceImpl implements FrontTenantService {

    @Resource
    private TenantService tenantService;

    @Override
    public List<AppTenantListRespVO> listTenants() {
        AppMobileAuthUtils.requireStudentLoginUser();
        return tenantService.getTenantListByStatus(CommonStatusEnum.ENABLE.getStatus()).stream()
                .sorted(Comparator.comparing(TenantDO::getId))
                .map(tenant -> AppTenantListRespVO.builder()
                        .id(tenant.getId())
                        .name(tenant.getName())
                        .build())
                .collect(Collectors.toList());
    }

}
