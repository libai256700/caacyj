package com.huiyitech.companyaudit.service;

import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.DeptDO;
import cn.iocoder.yudao.module.system.dal.dataobject.tenant.TenantDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import com.baomidou.mybatisplus.core.toolkit.support.SFunction;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthMeRespVO;
import com.huiyitech.companyaudit.dal.dataobject.companyaudit.CompanyAccountFrontDO;
import com.huiyitech.companyaudit.dal.mysql.companyaudit.CompanyAccountFrontMapper;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;

import java.lang.reflect.Field;
import java.util.concurrent.Callable;
import java.util.Arrays;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicLong;

import static cn.iocoder.yudao.framework.common.enums.UserTypeEnum.MEMBER;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CompanyAuditServiceImplTest {

    private final CompanyAccountFrontMapper companyAccountFrontMapper = mock(CompanyAccountFrontMapper.class);
    private final cn.iocoder.yudao.module.system.service.tenant.TenantService tenantService = mock(cn.iocoder.yudao.module.system.service.tenant.TenantService.class);
    private final cn.iocoder.yudao.module.system.dal.mysql.user.AdminUserMapper adminUserMapper = mock(cn.iocoder.yudao.module.system.dal.mysql.user.AdminUserMapper.class);
    private final cn.iocoder.yudao.module.system.dal.mysql.dept.DeptMapper deptMapper = mock(cn.iocoder.yudao.module.system.dal.mysql.dept.DeptMapper.class);
    private final CompanyAuditServiceImpl service = createService();
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void getCurrentCompanyAccount_shouldReturnNicknameAndDeptNameFromCurrentTenantAndMobile() {
        CompanyAccountFrontDO account = buildAccount(9527L, 2001L, "13986119652");
        TenantDO tenant = new TenantDO();
        tenant.setId(2001L);
        tenant.setName("飞行学院");
        tenant.setContactName("王老师");
        tenant.setContactMobile("13986110000");

        AdminUserDO user = new AdminUserDO();
        user.setId(7001L);
        user.setMobile("13986119652");
        user.setNickname("教员1");
        user.setDeptId(8001L);

        DeptDO dept = new DeptDO();
        dept.setId(8001L);
        dept.setName("教学部");

        when(companyAccountFrontMapper.selectById(9527L)).thenReturn(account);
        when(tenantService.getTenant(2001L)).thenReturn(tenant);
        when(adminUserMapper.selectList(anyMobileColumn(), eq("13986119652"))).thenReturn(Collections.singletonList(user));
        when(deptMapper.selectById(8001L)).thenReturn(dept);

        AtomicLong executedTenantId = new AtomicLong(-1L);
        try (MockedStatic<cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils> securityMock =
                     mockStatic(cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.class);
             MockedStatic<TenantUtils> tenantMock = mockStatic(TenantUtils.class)) {
            securityMock.when(cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils::getLoginUser)
                    .thenReturn(buildCompanyFrontLoginUser(9527L));
            tenantMock.when(() -> TenantUtils.executeIgnore(any(Callable.class)))
                    .thenAnswer(invocation -> ((Callable<?>) invocation.getArgument(0)).call());
            tenantMock.when(() -> TenantUtils.execute(eq(2001L), any(Callable.class)))
                    .thenAnswer(invocation -> {
                        executedTenantId.set(invocation.getArgument(0, Long.class));
                        return ((Callable<?>) invocation.getArgument(1)).call();
                    });

            AppCompanyAuthMeRespVO response = service.getCurrentCompanyAccount();
            JsonNode json = objectMapper.valueToTree(response);

            assertEquals("教员1", json.path("nickname").asText());
            assertEquals("教学部", json.path("deptName").asText());
            assertEquals("13986119652", json.path("username").asText());
            assertEquals(2001L, executedTenantId.get());
        }

        verify(adminUserMapper).selectList(anyMobileColumn(), eq("13986119652"));
        verify(deptMapper).selectById(8001L);
    }

    @Test
    void getCurrentCompanyAccount_shouldReturnControlledNullsWhenTenantUserIsNotUnique() {
        CompanyAccountFrontDO account = buildAccount(9527L, 2001L, "13986119652");
        AdminUserDO userA = new AdminUserDO();
        userA.setId(7001L);
        userA.setMobile("13986119652");
        userA.setNickname("教员A");
        AdminUserDO userB = new AdminUserDO();
        userB.setId(7002L);
        userB.setMobile("13986119652");
        userB.setNickname("教员B");

        when(companyAccountFrontMapper.selectById(9527L)).thenReturn(account);
        when(adminUserMapper.selectList(anyMobileColumn(), eq("13986119652")))
                .thenReturn(Arrays.asList(userA, userB));

        try (MockedStatic<cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils> securityMock =
                     mockStatic(cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.class);
             MockedStatic<TenantUtils> tenantMock = mockStatic(TenantUtils.class)) {
            securityMock.when(cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils::getLoginUser)
                    .thenReturn(buildCompanyFrontLoginUser(9527L));
            tenantMock.when(() -> TenantUtils.executeIgnore(any(Callable.class)))
                    .thenAnswer(invocation -> ((Callable<?>) invocation.getArgument(0)).call());
            tenantMock.when(() -> TenantUtils.execute(eq(2001L), any(Callable.class)))
                    .thenAnswer(invocation -> ((Callable<?>) invocation.getArgument(1)).call());

            AppCompanyAuthMeRespVO response = service.getCurrentCompanyAccount();
            JsonNode json = objectMapper.valueToTree(response);

            assertTrue(json.path("nickname").isNull());
            assertTrue(json.path("deptName").isNull());
        }

        verify(adminUserMapper).selectList(anyMobileColumn(), eq("13986119652"));
        verify(deptMapper, never()).selectById(any(Long.class));
    }

    @SuppressWarnings("unchecked")
    private SFunction<AdminUserDO, ?> anyMobileColumn() {
        return (SFunction<AdminUserDO, ?>) any(SFunction.class);
    }

    private CompanyAuditServiceImpl createService() {
        CompanyAuditServiceImpl target = new CompanyAuditServiceImpl();
        injectField(target, "companyAccountFrontMapper", companyAccountFrontMapper);
        injectField(target, "tenantService", tenantService);
        injectField(target, "adminUserMapper", adminUserMapper);
        injectFieldIfPresent(target, "deptMapper", deptMapper);
        return target;
    }

    private cn.iocoder.yudao.framework.security.core.LoginUser buildCompanyFrontLoginUser(Long userId) {
        cn.iocoder.yudao.framework.security.core.LoginUser loginUser =
                new cn.iocoder.yudao.framework.security.core.LoginUser();
        loginUser.setId(userId);
        loginUser.setUserType(MEMBER.getValue());
        loginUser.setScopes(Collections.singletonList("company-front"));
        return loginUser;
    }

    private CompanyAccountFrontDO buildAccount(Long id, Long tenantId, String username) {
        CompanyAccountFrontDO account = new CompanyAccountFrontDO();
        account.setId(id);
        account.setTenantId(tenantId);
        account.setUsername(username);
        account.setStatus(true);
        account.setAuditStatus(2);
        return account;
    }

    private void injectField(Object target, String fieldName, Object value) {
        try {
            Field field = target.getClass().getDeclaredField(fieldName);
            field.setAccessible(true);
            field.set(target, value);
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private void injectFieldIfPresent(Object target, String fieldName, Object value) {
        try {
            Field field = target.getClass().getDeclaredField(fieldName);
            field.setAccessible(true);
            field.set(target, value);
        } catch (NoSuchFieldException ignored) {
            // Current red phase allows the field to be absent before implementation lands.
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
