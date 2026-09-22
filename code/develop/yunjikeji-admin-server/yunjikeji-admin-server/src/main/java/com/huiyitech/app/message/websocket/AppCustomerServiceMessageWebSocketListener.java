package com.huiyitech.app.message.websocket;

import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.websocket.core.listener.WebSocketMessageListener;
import cn.iocoder.yudao.framework.websocket.core.util.WebSocketFrameworkUtils;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceRealtimeSendReqVO;
import com.huiyitech.app.message.service.CustomerMessageService;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketSession;

import javax.annotation.Resource;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Component
public class AppCustomerServiceMessageWebSocketListener
        implements WebSocketMessageListener<AppCustomerServiceRealtimeSendReqVO> {

    public static final String MESSAGE_TYPE = "yj_customer_service_send";

    @Resource
    private CustomerMessageService customerMessageService;

    @Override
    public void onMessage(WebSocketSession session, AppCustomerServiceRealtimeSendReqVO message) {
        LoginUser loginUser = WebSocketFrameworkUtils.getLoginUser(session);
        if (loginUser == null || !UserTypeEnum.MEMBER.getValue().equals(loginUser.getUserType())) {
            throw invalidParamException("Only member websocket sessions can send customer-service messages");
        }
        customerMessageService.sendRealtimeMessage(loginUser, message.getStudentId(), message.getConversationId(),
                message.getMessageType(), message.getContent());
    }

    @Override
    public String getType() {
        return MESSAGE_TYPE;
    }
}
