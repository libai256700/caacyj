package com.huiyitech.app.message.service;

import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.test.core.ut.BaseMockitoUnitTest;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.websocket.core.session.WebSocketSessionManager;
import cn.iocoder.yudao.module.infra.api.websocket.WebSocketSenderApi;
import com.huiyitech.app.message.controller.vo.AppCompanyStudentConversationRespVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceMessageRespVO;
import com.huiyitech.framework.security.AppMobileAuthUtils;
import com.huiyitech.message.dal.CustomerMessageRepository;
import com.huiyitech.utils.BaiduBosUtil;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.RETURNS_DEFAULTS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.when;

class CustomerMessageServiceImplTest extends BaseMockitoUnitTest {

    @InjectMocks
    private CustomerMessageServiceImpl customerMessageService;

    @Mock
    private CustomerMessageRepository customerMessageRepository;
    @Mock
    private WebSocketSenderApi webSocketSenderApi;
    @Mock
    private BaiduBosUtil baiduBosUtil;

    @Test
    void getSessionPage_shouldUseFixedTenantForAdminWithoutWtPost() {
        LoginUser loginUser = new LoginUser()
                .setId(1L)
                .setUserType(UserTypeEnum.ADMIN.getValue())
                .setTenantId(0L);

        PageResult<Map<String, Object>> pageResult = new PageResult<>(Collections.emptyList(), 0L);
        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class);
             MockedStatic<TenantContextHolder> tenantMock = mockStatic(TenantContextHolder.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(loginUser);
            tenantMock.when(TenantContextHolder::getTenantId).thenReturn(null);
            when(customerMessageRepository.getSessionPage(anyMap(), eq(1L))).thenReturn(pageResult);

            PageResult<Map<String, Object>> result = customerMessageService.getSessionPage(new HashMap<>());

            assertSame(pageResult, result);
        }
    }

    @Test
    void getSessionPage_shouldRejectNonAdminUser() {
        LoginUser loginUser = new LoginUser()
                .setId(1L)
                .setUserType(UserTypeEnum.MEMBER.getValue())
                .setTenantId(1L);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(loginUser);

            ServiceException error = assertThrows(ServiceException.class,
                    () -> customerMessageService.getSessionPage(new HashMap<>()));

            assertEquals("Admin token is required", error.getMessage());
        }
    }

    @Test
    void getCompanyStudentConversations_shouldRejectCompanyUserWithoutWtPost() {
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            if ("getApprovedStudentConversations".equals(invocation.getMethod().getName())) {
                fail("a company user without a WT post must not read customer-service conversations");
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWith(repository);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(companyUser());

            ServiceException error = assertThrows(ServiceException.class,
                    () -> service.getCurrentCompanyStudentConversations(1, 100));

            assertEquals("当前账号不具备无人机教员客服权限", error.getMessage());
        }
    }

    @Test
    void getCompanyStudentConversations_shouldKeepUnstartedStudentWithoutSyntheticIdAndEveryRealConversation() {
        LoginUser companyUser = companyUser();
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            String method = invocation.getMethod().getName();
            if ("getCompanyFrontTenantId".equals(method)) {
                fail("global customer-service visibility must not read the current teacher tenant");
            }
            if ("getApprovedStudentConversations".equals(method)) {
                assertEquals(2, invocation.getArguments().length);
                return Arrays.asList(
                        row("student_id", 101L, "student_name", "Student A", "tenant_id", null,
                                "session_id", null),
                        row("student_id", 101L, "student_name", "Student A", "tenant_id", 11L,
                                "session_id", 901L),
                        row("student_id", 202L, "student_name", "Student B", "tenant_id", 22L,
                                "session_id", 902L));
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWithWtCompanyUser(repository);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(companyUser);

            List<AppCompanyStudentConversationRespVO> conversations =
                    service.getCurrentCompanyStudentConversations(1, 100);

            assertEquals(3, conversations.size(), "approved students must remain visible before their first conversation");
            assertEquals(null, conversations.get(0).getConversationId(),
                    "students without a session must not get a synthetic conversation id");
            assertEquals("901", conversations.get(1).getConversationId());
            assertEquals("902", conversations.get(2).getConversationId());
            assertEquals(null, conversations.get(0).getTenantId(),
                    "an approved student without an organization tenant must remain visible");
            assertEquals(22L, conversations.get(2).getTenantId(),
                    "approved students from another tenant must remain visible");
        }
    }

    @Test
    void startCurrentCompanyStudentConversation_shouldReuseUnboundStudentSessionTenantRule() throws Throwable {
        Method method = assertDoesNotThrow(() -> CustomerMessageServiceImpl.class.getMethod(
                        "startCurrentCompanyStudentConversation", Long.class),
                "an unstarted student must use an explicit start operation");
        LoginUser companyUser = companyUser();
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            String name = invocation.getMethod().getName();
            Object[] arguments = invocation.getArguments();
            if ("getCompanyFrontTenantId".equals(name)) {
                fail("explicit start must not use the current teacher tenant");
            }
            if ("lockApprovedStudentTenantId".equals(name)) {
                assertEquals(1, arguments.length);
                assertEquals(202L, arguments[0]);
                return null;
            }
            if ("findLatestSessionByStudent".equals(name)) {
                assertEquals(202L, arguments[0]);
                return null;
            }
            if ("createSession".equals(name)) {
                assertEquals(202L, arguments[0]);
                assertEquals(0L, arguments[1]);
                assertEquals(1L, arguments[2],
                        "enterprise start must reuse the student-side unbound session tenant rule");
                return row("id", 903L, "session_from", 202L, "session_to", 0L,
                        "tenant_id", 1L, "last_message_content", "", "unread_count", 0);
            }
            if ("getStudentName".equals(name)) {
                assertEquals(1, arguments.length,
                        "student display lookup must not require a tenant for an unbound student");
                return "Student A";
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWithWtCompanyUser(repository);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(companyUser);

            AppCompanyStudentConversationRespVO conversation = (AppCompanyStudentConversationRespVO)
                    invoke(method, service, 202L);

            assertEquals("903", conversation.getConversationId());
            assertEquals(202L, conversation.getStudentId());
            assertEquals(1L, conversation.getTenantId());
        }
    }

    @Test
    void startCurrentCompanyStudentConversation_shouldReuseSessionCreatedBeforeLockAcquisition() throws Throwable {
        Method method = assertDoesNotThrow(() -> CustomerMessageServiceImpl.class.getMethod(
                        "startCurrentCompanyStudentConversation", Long.class),
                "an unstarted student must use an explicit start operation");
        LoginUser companyUser = companyUser();
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            String name = invocation.getMethod().getName();
            if ("getCompanyFrontTenantId".equals(name)) {
                fail("explicit start must not use the current teacher tenant");
            }
            if ("lockApprovedStudentTenantId".equals(name)) {
                assertEquals(1, invocation.getArguments().length);
                return 11L;
            }
            if ("findLatestSessionByStudent".equals(name)) {
                return row("id", 901L, "session_from", 101L, "session_to", 400L,
                        "tenant_id", 77L, "last_message_content", "existing", "unread_count", 0);
            }
            if ("createSession".equals(name)) {
                fail("explicit start must reuse a session found after the student relation lock");
            }
            if ("getStudentName".equals(name)) {
                return "Student A";
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWithWtCompanyUser(repository);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(companyUser);

            AppCompanyStudentConversationRespVO conversation = (AppCompanyStudentConversationRespVO)
                    invoke(method, service, 101L);

            assertEquals("901", conversation.getConversationId());
            assertEquals(77L, conversation.getTenantId(), "an existing session keeps its persisted audit tenant");
        }
    }

    @Test
    void unboundApprovedStudent_shouldStartAndSendFirstMessageWithRealConversationId() {
        LoginUser companyUser = companyUser();
        AtomicReference<Map<String, Object>> persistedSession = new AtomicReference<>();
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            String name = invocation.getMethod().getName();
            Object[] arguments = invocation.getArguments();
            if ("getCompanyFrontTenantId".equals(name)) {
                fail("unbound first contact must not use the current teacher tenant");
            }
            if ("lockApprovedStudentTenantId".equals(name)) {
                return null;
            }
            if ("findLatestSessionByStudent".equals(name)) {
                return persistedSession.get();
            }
            if ("createSession".equals(name)) {
                assertEquals(1L, arguments[2]);
                Map<String, Object> session = row("id", 903L, "session_from", 202L,
                        "session_to", 0L, "tenant_id", 1L, "last_message_content", "", "unread_count", 0);
                persistedSession.set(session);
                return session;
            }
            if ("getStudentName".equals(name)) {
                return "Student A";
            }
            if ("existsApprovedStudent".equals(name)) {
                return true;
            }
            if ("getSessionByConversationAndStudent".equals(name)) {
                assertEquals(903L, arguments[0]);
                assertEquals(202L, arguments[1]);
                return persistedSession.get();
            }
            if ("insertMessage".equals(name)) {
                assertEquals(903L, arguments[0]);
                assertEquals(1L, arguments[5]);
                return 999L;
            }
            if ("getMessage".equals(name)) {
                return messageRow(999L, 903L, 0L, 202L, 1L, "first message");
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWithWtCompanyUser(repository);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(companyUser);

            AppCompanyStudentConversationRespVO conversation =
                    service.startCurrentCompanyStudentConversation(202L);
            AppCustomerServiceMessageRespVO message =
                    service.sendCurrentCompanyStudentMessage(202L, 903L, "text", "first message");

            assertEquals("903", conversation.getConversationId());
            assertEquals(999L, message.getId());
            assertEquals(903L, message.getSessionId());
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void getCurrentCompanyStudentMessages_shouldUseSelectedConversationAndSharedHistory() throws Throwable {
        Method method = assertDoesNotThrow(() -> CustomerMessageServiceImpl.class.getMethod(
                        "getCurrentCompanyStudentMessages", Long.class, Long.class, Integer.class, Integer.class),
                "enterprise history must require both studentId and conversationId");
        LoginUser companyUser = companyUser();
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            String name = invocation.getMethod().getName();
            Object[] arguments = invocation.getArguments();
            if ("getCompanyFrontTenantId".equals(name)) {
                fail("enterprise history must not use the current teacher tenant");
            }
            if ("existsApprovedStudent".equals(name)) {
                assertEquals(101L, arguments[0]);
                return true;
            }
            if ("getSessionByConversationAndStudent".equals(name)) {
                assertEquals(901L, arguments[0]);
                assertEquals(101L, arguments[1]);
                return row("id", 901L, "session_from", 101L, "session_to", 0L, "tenant_id", 1L);
            }
            if ("getMessagesByStudentId".equals(name)) {
                assertEquals(101L, arguments[0]);
                assertEquals(1, arguments[1]);
                assertEquals(200, arguments[2]);
                return Collections.singletonList(messageRow(501L, 901L, 101L, 0L, 1L, "history"));
            }
            if ("getOrCreateSession".equals(name)) {
                fail("enterprise history must never create or guess a session");
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWithWtCompanyUser(repository);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(companyUser);

            List<AppCustomerServiceMessageRespVO> messages = (List<AppCustomerServiceMessageRespVO>)
                    invoke(method, service, 101L, 901L, 1, 200);

            assertEquals(1, messages.size());
            assertEquals(901L, messages.get(0).getSessionId());
        }
    }

    @Test
    void sendCurrentCompanyStudentMessage_shouldStayInSelectedConversationAndReturnInsertedMessage() throws Throwable {
        Method method = assertDoesNotThrow(() -> CustomerMessageServiceImpl.class.getMethod(
                        "sendCurrentCompanyStudentMessage", Long.class, Long.class, String.class, String.class),
                "enterprise send must require both studentId and conversationId");
        LoginUser companyUser = companyUser();
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            String name = invocation.getMethod().getName();
            Object[] arguments = invocation.getArguments();
            if ("getCompanyFrontTenantId".equals(name)) {
                fail("enterprise send must not use the current teacher tenant");
            }
            if ("existsApprovedStudent".equals(name)) {
                return true;
            }
            if ("getSessionByConversationAndStudent".equals(name)) {
                assertEquals(901L, arguments[0]);
                assertEquals(101L, arguments[1]);
                return row("id", 901L, "session_from", 101L, "session_to", 0L, "tenant_id", 1L);
            }
            if ("insertMessage".equals(name)) {
                assertEquals(901L, arguments[0]);
                assertEquals(0L, arguments[1]);
                assertEquals(101L, arguments[2]);
                assertEquals(1L, arguments[5]);
                return 999L;
            }
            if ("getMessage".equals(name)) {
                assertEquals(999L, arguments[0]);
                assertEquals(1L, arguments[1]);
                return messageRow(999L, 901L, 0L, 101L, 1L, "new message");
            }
            if ("getMessagesBySessionId".equals(name)) {
                fail("send must locate the inserted message by id instead of rereading the first history page");
            }
            if ("getOrCreateSession".equals(name)) {
                fail("enterprise send must never create or guess a session");
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWithWtCompanyUser(repository);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(companyUser);

            AppCustomerServiceMessageRespVO message = (AppCustomerServiceMessageRespVO)
                    invoke(method, service, 101L, 901L, "text", "new message");

            assertEquals(999L, message.getId());
            assertEquals(901L, message.getSessionId());
            assertEquals(Boolean.TRUE, message.getMine());
        }
    }

    @Test
    void sendRealtimeMessage_shouldRequireConversationForCompanyIdentity() {
        assertDoesNotThrow(() -> CustomerMessageServiceImpl.class.getMethod(
                        "sendRealtimeMessage", LoginUser.class, Long.class, Long.class, String.class, String.class),
                "enterprise websocket send must carry conversationId with studentId");
    }

    @Test
    void getCurrentCompanyStudentMessages_shouldRejectConversationStudentMismatch() throws Throwable {
        Method method = CustomerMessageServiceImpl.class.getMethod(
                "getCurrentCompanyStudentMessages", Long.class, Long.class, Integer.class, Integer.class);
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            String name = invocation.getMethod().getName();
            if ("getCompanyFrontTenantId".equals(name)) {
                fail("enterprise history must not use the current teacher tenant");
            }
            if ("existsApprovedStudent".equals(name)) {
                return true;
            }
            if ("getSessionByConversationAndStudent".equals(name)) {
                assertEquals(901L, invocation.getArguments()[0]);
                assertEquals(202L, invocation.getArguments()[1]);
                throw new IllegalArgumentException("conversation/student mismatch");
            }
            if ("getMessagesBySessionId".equals(name) || "getOrCreateSession".equals(name)) {
                fail("a mismatched conversation must not read or create messages");
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWithWtCompanyUser(repository);

        try (MockedStatic<SecurityFrameworkUtils> securityMock = mockStatic(SecurityFrameworkUtils.class)) {
            securityMock.when(SecurityFrameworkUtils::getLoginUser).thenReturn(companyUser());

            IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                    () -> invoke(method, service, 202L, 901L, 1, 200));

            assertTrue(error.getMessage().contains("mismatch"));
        }
    }

    @Test
    void sendCurrentStudentMessage_shouldUseSharedServiceTenantAndReturnInsertedMessage() {
        LoginUser studentUser = new LoginUser()
                .setId(101L)
                .setUserType(UserTypeEnum.MEMBER.getValue())
                .setTenantId(11L);
        CustomerMessageRepository repository = mock(CustomerMessageRepository.class, invocation -> {
            String name = invocation.getMethod().getName();
            Object[] arguments = invocation.getArguments();
            if ("getOrCreateSession".equals(name)) {
                assertEquals(101L, arguments[0]);
                assertEquals(1L, arguments[2]);
                return row("id", 901L, "session_from", 101L, "session_to", 0L, "tenant_id", 1L);
            }
            if ("insertMessage".equals(name)) {
                return 999L;
            }
            if ("getMessage".equals(name)) {
                assertEquals(999L, arguments[0]);
                assertEquals(1L, arguments[1]);
                return messageRow(999L, 901L, 101L, 0L, 1L, "student message");
            }
            if ("getMessagesBySessionId".equals(name)) {
                return Collections.singletonList(messageRow(100L, 901L, 101L, 0L, 1L, "old page tail"));
            }
            return RETURNS_DEFAULTS.answer(invocation);
        });
        CustomerMessageServiceImpl service = serviceWith(repository);

        try (MockedStatic<AppMobileAuthUtils> authMock = mockStatic(AppMobileAuthUtils.class)) {
            authMock.when(AppMobileAuthUtils::requireStudentLoginUser).thenReturn(studentUser);

            AppCustomerServiceMessageRespVO message = service.sendCurrentStudentMessage("text", "student message");

            assertEquals(999L, message.getId(),
                    "student send must return the inserted message even when history exceeds the first page");
            assertEquals(901L, message.getSessionId());
        }
    }

    private static LoginUser companyUser() {
        return new LoginUser()
                .setId(500L)
                .setUserType(UserTypeEnum.MEMBER.getValue())
                .setTenantId(11L)
                .setScopes(Collections.singletonList("company-front"));
    }

    private static CustomerMessageServiceImpl serviceWith(CustomerMessageRepository repository) {
        CustomerMessageServiceImpl service = new CustomerMessageServiceImpl();
        setField(service, "customerMessageRepository", repository);
        setField(service, "webSocketSenderApi", mock(WebSocketSenderApi.class));
        setField(service, "webSocketSessionManager", mock(WebSocketSessionManager.class));
        setField(service, "baiduBosUtil", mock(BaiduBosUtil.class));
        return service;
    }

    private static CustomerMessageServiceImpl serviceWithWtCompanyUser(CustomerMessageRepository repository) {
        when(repository.isWtCompanyFrontUser(500L)).thenReturn(true);
        return serviceWith(repository);
    }

    private static void setField(Object target, String name, Object value) {
        try {
            Field field = CustomerMessageServiceImpl.class.getDeclaredField(name);
            field.setAccessible(true);
            field.set(target, value);
        } catch (ReflectiveOperationException ex) {
            throw new AssertionError(ex);
        }
    }

    private static Object invoke(Method method, Object target, Object... arguments) throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException ex) {
            throw ex.getTargetException();
        }
    }

    private static Map<String, Object> messageRow(Long id, Long sessionId, Long sessionFrom, Long sessionTo,
                                                   Long tenantId, String content) {
        return row("id", id, "session_id", sessionId, "session_from", sessionFrom, "session_to", sessionTo,
                "tenant_id", tenantId, "message_type", "text", "content", content);
    }

    private static Map<String, Object> row(Object... entries) {
        Map<String, Object> row = new HashMap<>();
        for (int index = 0; index < entries.length; index += 2) {
            row.put(String.valueOf(entries[index]), entries[index + 1]);
        }
        return row;
    }
}
