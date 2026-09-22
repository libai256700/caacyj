package com.huiyitech.customer.service;

import com.huiyitech.customer.controller.vo.AppCustomerAuthLoginRespVO;
import com.huiyitech.customer.controller.vo.AppCustomerAuthMeRespVO;
import com.huiyitech.customer.controller.vo.AppCustomerAuthRegisterReqVO;
import com.huiyitech.customer.controller.vo.AppCustomerBindMobileReqVO;
import com.huiyitech.customer.controller.vo.AppCustomerInfoSaveReqVO;
import com.huiyitech.customer.controller.vo.AppStudentAuditMyRespVO;
import com.huiyitech.customer.controller.vo.AppStudentAuditSubmitReqVO;

import java.util.Map;

public interface CustomerService {

    AppCustomerAuthLoginRespVO loginOrRegister(AppCustomerAuthRegisterReqVO reqVO);

    AppCustomerAuthLoginRespVO univerifyLogin(String mobile);

    void bindMobile(AppCustomerBindMobileReqVO reqVO);

    AppCustomerAuthLoginRespVO refreshToken(String refreshToken);

    void logout(String token);

    AppCustomerAuthMeRespVO getCurrentCustomer();

    void saveCustomerInfo(AppCustomerInfoSaveReqVO reqVO);

    Long submitStudentAudit(AppStudentAuditSubmitReqVO reqVO);

    AppStudentAuditMyRespVO getCurrentStudentAudit();

    void auditStudent(Map<String, Object> body);
}
