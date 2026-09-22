package com.huiyitech.app.message.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import cn.iocoder.yudao.framework.websocket.core.session.WebSocketSessionManager;
import cn.iocoder.yudao.framework.websocket.core.util.WebSocketFrameworkUtils;
import cn.iocoder.yudao.module.infra.api.websocket.WebSocketSenderApi;
import com.huiyitech.app.message.controller.vo.AppCompanyStudentConversationRespVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceMessageRespVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceRealtimeMessageRespVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceSessionRespVO;
import com.huiyitech.framework.security.AppMobileAuthUtils;
import com.huiyitech.message.dal.CustomerMessageRepository;
import com.huiyitech.utils.BaiduBosUtil;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.socket.WebSocketSession;

import javax.annotation.Resource;
import java.io.IOException;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.UNAUTHORIZED;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
public class CustomerMessageServiceImpl implements CustomerMessageService {

    private static final long PLATFORM_SERVICE_USER_ID = 0L;
    private static final String MESSAGE_TYPE_TEXT = "text";
    private static final String MESSAGE_TYPE_IMAGE = "image";
    private static final String MESSAGE_TYPE_VIDEO = "video";
    private static final Set<String> SUPPORTED_MESSAGE_TYPES = new HashSet<>(Arrays.asList(
            MESSAGE_TYPE_TEXT, MESSAGE_TYPE_IMAGE, MESSAGE_TYPE_VIDEO));
    private static final String YJ_CUSTOMER_SERVICE_MESSAGE_TYPE = "yj_customer_service_message";
    private static final long CUSTOMER_SERVICE_TENANT_ID = 1L;
    private static final int DEFAULT_PAGE_NO = 1;
    private static final int DEFAULT_PAGE_SIZE = 100;
    private static final int MAX_PAGE_SIZE = 200;
    private static final String COMPANY_FRONT_SCOPE = "company-front";

    @Resource
    private CustomerMessageRepository customerMessageRepository;
    @Resource
    private WebSocketSenderApi webSocketSenderApi;
    @Resource
    private WebSocketSessionManager webSocketSessionManager;
    @Resource
    private BaiduBosUtil baiduBosUtil;

    @Override
    @Transactional(rollbackFor = Exception.class)
    @TenantIgnore
    public AppCustomerServiceSessionRespVO getOrCreateCurrentSession() {
        LoginUser loginUser = currentStudent();
        Long studentId = loginUser.getId();
        Map<String, Object> session = customerMessageRepository.getOrCreateSession(studentId, PLATFORM_SERVICE_USER_ID,
                CUSTOMER_SERVICE_TENANT_ID, now());
        return toSessionResp(session, getMessagesBySessionId(toLong(session.get("id")), DEFAULT_PAGE_NO,
                DEFAULT_PAGE_SIZE, studentId, CUSTOMER_SERVICE_TENANT_ID));
    }

    @Override
    public List<AppCustomerServiceMessageRespVO> getCurrentMessages(Integer pageNo, Integer pageSize) {
        LoginUser loginUser = currentStudent();
        Long studentId = loginUser.getId();
        Map<String, Object> session = customerMessageRepository.getOrCreateSession(studentId, PLATFORM_SERVICE_USER_ID,
                CUSTOMER_SERVICE_TENANT_ID, now());
        return getMessagesBySessionId(toLong(session.get("id")), pageNo, pageSize, studentId,
                CUSTOMER_SERVICE_TENANT_ID);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerServiceMessageRespVO sendCurrentStudentText(String content) {
        return sendCurrentStudentMessage(MESSAGE_TYPE_TEXT, content);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerServiceMessageRespVO sendCurrentStudentMessage(String messageType, String content) {
        String normalizedMessageType = normalizeMessageType(messageType);
        String normalizedContent = normalizeContent(content);
        LoginUser loginUser = currentStudent();
        return sendStudentMessage(loginUser, normalizedMessageType, normalizedContent);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerServiceMessageRespVO sendCurrentStudentMedia(String messageType, MultipartFile file) {
        String normalizedMessageType = normalizeMediaMessageType(messageType);
        String mediaUrl = uploadCustomerServiceMedia(normalizedMessageType, file);
        LoginUser loginUser = currentStudent();
        return sendStudentMessage(loginUser, normalizedMessageType, mediaUrl);
    }

    private AppCustomerServiceMessageRespVO sendStudentMessage(LoginUser loginUser, String messageType,
                                                               String normalizedContent) {
        Long studentId = loginUser.getId();
        Timestamp now = now();
        Map<String, Object> session = customerMessageRepository.getOrCreateSession(studentId, PLATFORM_SERVICE_USER_ID,
                CUSTOMER_SERVICE_TENANT_ID, now);
        Long sessionId = toLong(session.get("id"));

        Long messageId = customerMessageRepository.insertMessage(sessionId, studentId, PLATFORM_SERVICE_USER_ID,
                messageType, normalizedContent, CUSTOMER_SERVICE_TENANT_ID, String.valueOf(studentId), now);
        customerMessageRepository.updateSessionSnapshot(sessionId, CUSTOMER_SERVICE_TENANT_ID,
                toSessionSnapshotContent(messageType, normalizedContent), now, String.valueOf(studentId), false);
        broadcastCustomerServiceMessage(sessionId, messageId, studentId, PLATFORM_SERVICE_USER_ID,
                normalizedContent, messageType, now, CUSTOMER_SERVICE_TENANT_ID, studentId);

        return toMessageResp(customerMessageRepository.getMessage(messageId, CUSTOMER_SERVICE_TENANT_ID), studentId);
    }

    @Override
    public List<AppCompanyStudentConversationRespVO> getCurrentCompanyStudentConversations(Integer pageNo,
                                                                                           Integer pageSize) {
        requireCompanyFrontLoginUser();
        int normalizedPageNo = pageNo == null || pageNo < 1 ? DEFAULT_PAGE_NO : pageNo;
        int normalizedPageSize = pageSize == null || pageSize < 1 ? DEFAULT_PAGE_SIZE : Math.min(pageSize, MAX_PAGE_SIZE);
        return customerMessageRepository.getApprovedStudentConversations(normalizedPageNo, normalizedPageSize)
                .stream()
                .map(this::toCompanyStudentConversationResp)
                .collect(Collectors.toList());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCompanyStudentConversationRespVO startCurrentCompanyStudentConversation(Long studentId) {
        LoginUser loginUser = requireCompanyFrontLoginUser();
        assertStudentId(studentId);
        customerMessageRepository.lockApprovedStudentTenantId(studentId);
        Map<String, Object> session = customerMessageRepository.findLatestSessionByStudent(studentId,
                PLATFORM_SERVICE_USER_ID, CUSTOMER_SERVICE_TENANT_ID);
        if (session == null) {
            session = customerMessageRepository.createSession(studentId, PLATFORM_SERVICE_USER_ID,
                    CUSTOMER_SERVICE_TENANT_ID, now());
        }
        return toStartedCompanyStudentConversationResp(session, studentId);
    }

    @Override
    public List<AppCustomerServiceMessageRespVO> getCurrentCompanyStudentMessages(Long studentId, Long conversationId,
                                                                                  Integer pageNo, Integer pageSize) {
        requireCompanyFrontLoginUser();
        assertCompanyStudentAccess(studentId);
        requireCompanyStudentSession(studentId, conversationId);
        return getCompanyMessagesByStudentId(studentId, pageNo, pageSize);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerServiceMessageRespVO sendCurrentCompanyStudentText(Long studentId, Long conversationId,
                                                                         String content) {
        return sendCurrentCompanyStudentMessage(studentId, conversationId, MESSAGE_TYPE_TEXT, content);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerServiceMessageRespVO sendCurrentCompanyStudentMessage(Long studentId, Long conversationId,
                                                                            String messageType, String content) {
        String normalizedMessageType = normalizeMessageType(messageType);
        String normalizedContent = normalizeContent(content);
        LoginUser loginUser = requireCompanyFrontLoginUser();
        return sendCompanyStudentMessage(loginUser, studentId, conversationId, normalizedMessageType,
                normalizedContent);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerServiceMessageRespVO sendCurrentCompanyStudentMedia(Long studentId, Long conversationId,
                                                                          String messageType, MultipartFile file) {
        String normalizedMessageType = normalizeMediaMessageType(messageType);
        String mediaUrl = uploadCustomerServiceMedia(normalizedMessageType, file);
        LoginUser loginUser = requireCompanyFrontLoginUser();
        return sendCompanyStudentMessage(loginUser, studentId, conversationId, normalizedMessageType, mediaUrl);
    }

    private AppCustomerServiceMessageRespVO sendCompanyStudentMessage(LoginUser loginUser, Long studentId,
                                                                      Long conversationId, String messageType,
                                                                      String normalizedContent) {
        assertWtCompanyFrontLoginUser(loginUser);
        assertCompanyStudentAccess(studentId);
        Map<String, Object> session = requireSharedCompanyStudentSession(studentId, conversationId);
        Long sessionId = toLong(session.get("id"));

        Timestamp now = now();
        String operator = String.valueOf(loginUser.getId());
        Long messageId = customerMessageRepository.insertMessage(sessionId, PLATFORM_SERVICE_USER_ID, studentId,
                messageType, normalizedContent, CUSTOMER_SERVICE_TENANT_ID, operator, now);
        customerMessageRepository.updateSessionSnapshot(sessionId, CUSTOMER_SERVICE_TENANT_ID,
                toSessionSnapshotContent(messageType, normalizedContent), now, operator, true);
        broadcastCustomerServiceMessage(sessionId, messageId, PLATFORM_SERVICE_USER_ID, studentId,
                normalizedContent, messageType, now, CUSTOMER_SERVICE_TENANT_ID, studentId);

        return toCompanyMessageResp(customerMessageRepository.getMessage(messageId, CUSTOMER_SERVICE_TENANT_ID),
                studentId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerServiceMessageRespVO sendRealtimeMessage(LoginUser loginUser, Long studentId,
                                                               Long conversationId, String messageType, String content) {
        if (loginUser == null || !UserTypeEnum.MEMBER.getValue().equals(loginUser.getUserType())) {
            throw invalidParamException("Member token is required");
        }
        String normalizedMessageType = normalizeMessageType(messageType);
        String normalizedContent = normalizeContent(content);
        if (loginUser.getScopes() != null && loginUser.getScopes().contains(COMPANY_FRONT_SCOPE)) {
            return sendCompanyStudentMessage(loginUser, studentId, conversationId, normalizedMessageType,
                    normalizedContent);
        }
        return sendStudentMessage(loginUser, normalizedMessageType, normalizedContent);
    }

    @Override
    public PageResult<Map<String, Object>> getSessionPage(Map<String, String> params) {
        return customerMessageRepository.getSessionPage(params, requireAdminTenantId());
    }

    @Override
    public Map<String, Object> getSession(Long id) {
        return customerMessageRepository.getSession(id, requireAdminTenantId());
    }

    @Override
    public PageResult<Map<String, Object>> getMessagePage(Map<String, String> params) {
        return customerMessageRepository.getMessagePage(params, requireAdminTenantId());
    }

    @Override
    public Map<String, Object> getMessage(Long id) {
        return customerMessageRepository.getMessage(id, requireAdminTenantId());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long sendAdminMessage(Map<String, Object> body) {
        Long sessionId = requireLong(body, "session_id");
        String content = normalizeContent(body == null ? null : toString(firstPresent(body, "content")));
        String messageType = normalizeMessageType(body == null ? null : toString(firstPresent(body, "message_type", "messageType")));
        Long tenantId = requireAdminTenantId();
        Map<String, Object> session = customerMessageRepository.getSession(sessionId, tenantId);
        Long operatorUserId = SecurityFrameworkUtils.getLoginUserId();
        Long sessionTo = toLong(session.get("session_from"));
        if (operatorUserId == null || operatorUserId <= 0) {
            throw invalidParamException("Admin token is required");
        }

        Timestamp now = now();
        String operator = currentUser();
        Long id = customerMessageRepository.insertMessage(sessionId, PLATFORM_SERVICE_USER_ID, sessionTo,
                messageType, content, tenantId, operator, now);
        customerMessageRepository.updateSessionSnapshot(sessionId, tenantId, toSessionSnapshotContent(messageType, content),
                now, operator, true);
        broadcastCustomerServiceMessage(sessionId, id, PLATFORM_SERVICE_USER_ID, sessionTo, content, messageType, now,
                tenantId, toLong(session.get("session_from")));
        return id;
    }

    private void broadcastCustomerServiceMessage(Long sessionId, Long messageId, Long sessionFrom, Long sessionTo,
                                                 String content, String messageType, Timestamp createTime,
                                                 Long tenantId, Long studentId) {
        AppCustomerServiceRealtimeMessageRespVO payload = AppCustomerServiceRealtimeMessageRespVO.builder()
                .id(messageId)
                .conversationId(String.valueOf(sessionId))
                .sessionId(sessionId)
                .sessionFrom(sessionFrom)
                .sessionTo(sessionTo)
                .studentId(studentId)
                .tenantId(tenantId)
                .content(content)
                .messageType(messageType)
                .createTime(toDateTimeString(createTime))
                .build();
        sendRealtimeMessageToEligibleSessions(studentId, payload);
    }

    private void sendRealtimeMessageToEligibleSessions(Long studentId, Object payload) {
        Map<Long, Boolean> wtCompanyUsers = new HashMap<>();
        for (WebSocketSession session : webSocketSessionManager.getSessionList(UserTypeEnum.MEMBER.getValue())) {
            LoginUser loginUser = WebSocketFrameworkUtils.getLoginUser(session);
            if (isTargetStudent(loginUser, studentId)
                    || isWtCompanyFrontUser(loginUser, wtCompanyUsers)) {
                webSocketSenderApi.sendObject(session.getId(), YJ_CUSTOMER_SERVICE_MESSAGE_TYPE, payload);
            }
        }

        for (WebSocketSession session : webSocketSessionManager.getSessionList(UserTypeEnum.ADMIN.getValue())) {
            LoginUser loginUser = WebSocketFrameworkUtils.getLoginUser(session);
            if (isAdminUser(loginUser)) {
                webSocketSenderApi.sendObject(session.getId(), YJ_CUSTOMER_SERVICE_MESSAGE_TYPE, payload);
            }
        }
    }

    private boolean isTargetStudent(LoginUser loginUser, Long studentId) {
        return loginUser != null && studentId != null && studentId.equals(loginUser.getId())
                && loginUser.getScopes() != null
                && loginUser.getScopes().contains(AppMobileAuthUtils.CUSTOMER_STUDENT_SCOPE);
    }

    private boolean isWtCompanyFrontUser(LoginUser loginUser, Map<Long, Boolean> accessCache) {
        if (loginUser == null || loginUser.getScopes() == null
                || !loginUser.getScopes().contains(COMPANY_FRONT_SCOPE)) {
            return false;
        }
        return accessCache.computeIfAbsent(loginUser.getId(), customerMessageRepository::isWtCompanyFrontUser);
    }

    private boolean isAdminUser(LoginUser loginUser) {
        return loginUser != null && UserTypeEnum.ADMIN.getValue().equals(loginUser.getUserType());
    }

    private LoginUser currentStudent() {
        return AppMobileAuthUtils.requireStudentLoginUser();
    }

    private LoginUser requireCompanyFrontLoginUser() {
        LoginUser loginUser = SecurityFrameworkUtils.getLoginUser();
        assertWtCompanyFrontLoginUser(loginUser);
        return loginUser;
    }

    private void assertWtCompanyFrontLoginUser(LoginUser loginUser) {
        if (loginUser == null) {
            throw exception0(UNAUTHORIZED.getCode(), "组织账号令牌不能为空");
        }
        if (!UserTypeEnum.MEMBER.getValue().equals(loginUser.getUserType())
                || loginUser.getScopes() == null
                || !loginUser.getScopes().contains(COMPANY_FRONT_SCOPE)) {
            throw exception0(UNAUTHORIZED.getCode(), "组织账号令牌类型不正确");
        }
        if (!customerMessageRepository.isWtCompanyFrontUser(loginUser.getId())) {
            throw exception0(UNAUTHORIZED.getCode(), "当前账号不具备无人机教员客服权限");
        }
    }

    private void assertCompanyStudentAccess(Long studentId) {
        assertStudentId(studentId);
        if (!customerMessageRepository.existsApprovedStudent(studentId)) {
            throw invalidParamException("Approved student does not exist");
        }
    }

    private void assertStudentId(Long studentId) {
        if (studentId == null || studentId <= 0) {
            throw invalidParamException("studentId cannot be empty");
        }
    }

    private Map<String, Object> requireCompanyStudentSession(Long studentId, Long conversationId) {
        if (conversationId == null || conversationId <= 0) {
            throw invalidParamException("conversationId cannot be empty");
        }
        return customerMessageRepository.getSessionByConversationAndStudent(conversationId, studentId);
    }

    private Map<String, Object> requireSharedCompanyStudentSession(Long studentId, Long conversationId) {
        Map<String, Object> session = requireCompanyStudentSession(studentId, conversationId);
        if (toLong(session.get("tenant_id")) == null
                || CUSTOMER_SERVICE_TENANT_ID != toLong(session.get("tenant_id"))
                || toLong(session.get("session_to")) == null
                || PLATFORM_SERVICE_USER_ID != toLong(session.get("session_to"))) {
            throw invalidParamException("Customer service conversation is not bound to the shared service identity");
        }
        return session;
    }

    private Long requireSessionTenantId(Map<String, Object> session) {
        Long tenantId = toLong(session.get("tenant_id"));
        if (tenantId == null || tenantId <= 0) {
            throw invalidParamException("Customer service session tenant is invalid");
        }
        return tenantId;
    }

    private Long requireAdminTenantId() {
        LoginUser loginUser = SecurityFrameworkUtils.getLoginUser();
        if (loginUser == null || !UserTypeEnum.ADMIN.getValue().equals(loginUser.getUserType())) {
            throw invalidParamException("Admin token is required");
        }
        return CUSTOMER_SERVICE_TENANT_ID;
    }

    private List<AppCustomerServiceMessageRespVO> getMessagesBySessionId(Long sessionId, Integer pageNo, Integer pageSize,
                                                                         Long currentStudentId, Long tenantId) {
        int normalizedPageNo = pageNo == null || pageNo < 1 ? DEFAULT_PAGE_NO : pageNo;
        int normalizedPageSize = pageSize == null || pageSize < 1 ? DEFAULT_PAGE_SIZE : Math.min(pageSize, MAX_PAGE_SIZE);
        return customerMessageRepository.getMessagesBySessionId(sessionId, tenantId, normalizedPageNo, normalizedPageSize)
                .stream()
                .map(row -> toMessageResp(row, currentStudentId))
                .collect(Collectors.toList());
    }

    private List<AppCustomerServiceMessageRespVO> getCompanyMessagesByStudentId(Long studentId, Integer pageNo,
                                                                                 Integer pageSize) {
        int normalizedPageNo = pageNo == null || pageNo < 1 ? DEFAULT_PAGE_NO : pageNo;
        int normalizedPageSize = pageSize == null || pageSize < 1 ? DEFAULT_PAGE_SIZE : Math.min(pageSize, MAX_PAGE_SIZE);
        return customerMessageRepository.getMessagesByStudentId(studentId, normalizedPageNo, normalizedPageSize)
                .stream()
                .map(row -> toCompanyMessageResp(row, studentId))
                .collect(Collectors.toList());
    }

    private AppCustomerServiceSessionRespVO toSessionResp(Map<String, Object> row,
                                                          List<AppCustomerServiceMessageRespVO> messages) {
        return AppCustomerServiceSessionRespVO.builder()
                .id(toLong(row.get("id")))
                .sessionFrom(toLong(row.get("session_from")))
                .sessionTo(toLong(row.get("session_to")))
                .lastMessageContent(toString(row.get("last_message_content")))
                .lastMessageTime(toLocalDateTime(row.get("last_message_time")))
                .unreadCount(toInteger(row.get("unread_count")))
                .messages(messages)
                .build();
    }

    private AppCompanyStudentConversationRespVO toCompanyStudentConversationResp(Map<String, Object> row) {
        Long studentId = toLong(row.get("student_id"));
        Long sessionId = toLong(row.get("session_id"));
        return AppCompanyStudentConversationRespVO.builder()
                .studentId(studentId)
                .studentName(toString(row.get("student_name")))
                .studentPhone(toString(row.get("student_phone")))
                .tenantId(toLong(row.get("tenant_id")))
                .conversationId(sessionId == null ? null : String.valueOf(sessionId))
                .lastMessageContent(toString(row.get("last_message_content")))
                .lastMessageTime(toLocalDateTime(row.get("last_message_time")))
                .unreadCount(toInteger(row.get("unread_count")))
                .build();
    }

    private AppCompanyStudentConversationRespVO toStartedCompanyStudentConversationResp(Map<String, Object> session,
                                                                                         Long studentId) {
        Long sessionTenantId = requireSessionTenantId(session);
        return AppCompanyStudentConversationRespVO.builder()
                .studentId(studentId)
                .studentName(customerMessageRepository.getStudentName(studentId))
                .studentPhone("")
                .tenantId(sessionTenantId)
                .conversationId(String.valueOf(toLong(session.get("id"))))
                .lastMessageContent(toString(session.get("last_message_content")))
                .lastMessageTime(toLocalDateTime(session.get("last_message_time")))
                .unreadCount(toInteger(session.get("unread_count")))
                .build();
    }

    private AppCustomerServiceMessageRespVO toMessageResp(Map<String, Object> row, Long currentStudentId) {
        Long senderId = toLong(row.get("session_from"));
        return buildMessageResp(row, senderId != null && senderId.equals(currentStudentId));
    }

    private AppCustomerServiceMessageRespVO toCompanyMessageResp(Map<String, Object> row, Long studentId) {
        Long senderId = toLong(row.get("session_from"));
        return buildMessageResp(row, senderId != null && !senderId.equals(studentId));
    }

    private AppCustomerServiceMessageRespVO buildMessageResp(Map<String, Object> row, boolean mine) {
        return AppCustomerServiceMessageRespVO.builder()
                .id(toLong(row.get("id")))
                .sessionId(toLong(row.get("session_id")))
                .sessionFrom(toLong(row.get("session_from")))
                .sessionTo(toLong(row.get("session_to")))
                .messageType(toString(row.get("message_type")))
                .content(toString(row.get("content")))
                .createTime(toLocalDateTime(row.get("create_time")))
                .mine(mine)
                .build();
    }

    private String normalizeContent(String content) {
        String normalizedContent = content == null ? "" : content.trim();
        if (!StringUtils.hasText(normalizedContent)) {
            throw invalidParamException("Message content cannot be empty");
        }
        return normalizedContent;
    }

    private String normalizeMessageType(String messageType) {
        String normalizedMessageType = StringUtils.hasText(messageType) ? messageType.trim() : MESSAGE_TYPE_TEXT;
        if (!SUPPORTED_MESSAGE_TYPES.contains(normalizedMessageType)) {
            throw invalidParamException("Unsupported message type: {}", normalizedMessageType);
        }
        return normalizedMessageType;
    }

    private String normalizeMediaMessageType(String messageType) {
        String normalizedMessageType = normalizeMessageType(messageType);
        if (!MESSAGE_TYPE_IMAGE.equals(normalizedMessageType) && !MESSAGE_TYPE_VIDEO.equals(normalizedMessageType)) {
            throw invalidParamException("Unsupported media message type: {}", normalizedMessageType);
        }
        return normalizedMessageType;
    }

    private String uploadCustomerServiceMedia(String messageType, MultipartFile file) {
        BaiduBosUtil.BosUploadResult uploadResult = baiduBosUtil.upload(file, "customer-service/" + messageType);
        return normalizeContent(uploadResult == null ? null : uploadResult.getUrl());
    }

    private String toSessionSnapshotContent(String messageType, String content) {
        if (MESSAGE_TYPE_IMAGE.equals(messageType)) {
            return "[图片]";
        }
        if (MESSAGE_TYPE_VIDEO.equals(messageType)) {
            return "[视频]";
        }
        return content;
    }

    private Long requireLong(Map<String, Object> body, String key) {
        Object value = body == null ? null : firstPresent(body, key, toCamelCase(key));
        if (value == null) {
            throw invalidParamException("{} cannot be empty", key);
        }
        try {
            return value instanceof Number ? ((Number) value).longValue() : Long.parseLong(String.valueOf(value));
        } catch (NumberFormatException ex) {
            throw invalidParamException("{} must be a number", key);
        }
    }

    private Object firstPresent(Map<String, Object> body, String... keys) {
        for (String key : keys) {
            if (body.containsKey(key)) {
                return body.get(key);
            }
        }
        return null;
    }

    private String toCamelCase(String value) {
        StringBuilder result = new StringBuilder();
        boolean upperNext = false;
        for (char ch : value.toCharArray()) {
            if (ch == '_') {
                upperNext = true;
                continue;
            }
            result.append(upperNext ? Character.toUpperCase(ch) : ch);
            upperNext = false;
        }
        return result.toString();
    }

    private Timestamp now() {
        return Timestamp.valueOf(LocalDateTime.now());
    }

    private Long toLong(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        return Long.parseLong(String.valueOf(value));
    }

    private Integer toInteger(Object value) {
        if (value == null) {
            return 0;
        }
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        return Integer.parseInt(String.valueOf(value));
    }

    private String toString(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private LocalDateTime toLocalDateTime(Object value) {
        if (value instanceof Timestamp) {
            return ((Timestamp) value).toLocalDateTime();
        }
        if (value instanceof LocalDateTime) {
            return (LocalDateTime) value;
        }
        return null;
    }

    private String toDateTimeString(Timestamp value) {
        return value == null ? null : value.toLocalDateTime().toString();
    }

    private String currentUser() {
        Long userId = SecurityFrameworkUtils.getLoginUserId();
        return userId == null ? "system" : String.valueOf(userId);
    }
}
