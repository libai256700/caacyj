package com.huiyitech.agreement.service;

import java.util.Map;

public interface AgreementDetailService extends AgreementResourceService {

    void publish(Map<String, Object> body);

    void withdraw(Map<String, Object> body);
}
