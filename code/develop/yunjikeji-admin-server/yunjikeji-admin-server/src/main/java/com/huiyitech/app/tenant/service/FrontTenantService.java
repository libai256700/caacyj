package com.huiyitech.app.tenant.service;

import com.huiyitech.app.tenant.controller.vo.AppTenantListRespVO;

import java.util.List;

public interface FrontTenantService {

    List<AppTenantListRespVO> listTenants();

}
