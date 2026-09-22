package com.huiyitech.app.message.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import com.huiyitech.app.message.controller.vo.AppCompanyStudentConversationRespVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceMessageRespVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceSessionRespVO;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

public interface CustomerMessageService {

    AppCustomerServiceSessionRespVO getOrCreateCurrentSession();

    List<AppCustomerServiceMessageRespVO> getCurrentMessages(Integer pageNo, Integer pageSize);

    AppCustomerServiceMessageRespVO sendCurrentStudentText(String content);

    AppCustomerServiceMessageRespVO sendCurrentStudentMessage(String messageType, String content);

    AppCustomerServiceMessageRespVO sendCurrentStudentMedia(String messageType, MultipartFile file);

    List<AppCompanyStudentConversationRespVO> getCurrentCompanyStudentConversations(Integer pageNo, Integer pageSize);

    AppCompanyStudentConversationRespVO startCurrentCompanyStudentConversation(Long studentId);

    List<AppCustomerServiceMessageRespVO> getCurrentCompanyStudentMessages(Long studentId, Long conversationId,
                                                                           Integer pageNo, Integer pageSize);

    AppCustomerServiceMessageRespVO sendCurrentCompanyStudentText(Long studentId, Long conversationId, String content);

    AppCustomerServiceMessageRespVO sendCurrentCompanyStudentMessage(Long studentId, Long conversationId,
                                                                      String messageType, String content);

    AppCustomerServiceMessageRespVO sendCurrentCompanyStudentMedia(Long studentId, Long conversationId,
                                                                    String messageType, MultipartFile file);

    AppCustomerServiceMessageRespVO sendRealtimeMessage(LoginUser loginUser, Long studentId, Long conversationId,
                                                        String messageType, String content);

    PageResult<Map<String, Object>> getSessionPage(Map<String, String> params);

    Map<String, Object> getSession(Long id);

    PageResult<Map<String, Object>> getMessagePage(Map<String, String> params);

    Map<String, Object> getMessage(Long id);

    Long sendAdminMessage(Map<String, Object> body);
}
