package com.huiyitech.companyaudit.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuditSaveReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuditSubmitReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthLoginRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthMeRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthPostCodesRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthRegisterReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditPageReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditRespVO;

import java.util.Map;

public interface CompanyAuditService {

    AppCompanyAuthLoginRespVO loginOrRegister(AppCompanyAuthRegisterReqVO reqVO);

    AppCompanyAuthLoginRespVO univerifyLogin(String mobile);

    AppCompanyAuthLoginRespVO refreshToken(String refreshToken);

    void logout(String token);

    AppCompanyAuthMeRespVO getCurrentCompanyAccount();

    AppCompanyAuthPostCodesRespVO getCompanyAuthPostCodes(String mobile);

    Long saveAudit(AppCompanyAuditSaveReqVO reqVO);

    Long submitAudit(AppCompanyAuditSubmitReqVO reqVO);

    PageResult<AppCompanyStudentAuditRespVO> getCurrentCompanyStudentAuditPage(AppCompanyStudentAuditPageReqVO reqVO);

    void auditCurrentCompanyStudent(AppCompanyStudentAuditReqVO reqVO);

    void auditEnterprise(Map<String, Object> body);
}
