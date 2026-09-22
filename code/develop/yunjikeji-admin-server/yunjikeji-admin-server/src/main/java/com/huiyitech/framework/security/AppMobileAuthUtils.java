package com.huiyitech.framework.security;

import cn.hutool.core.collection.CollUtil;
import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.module.system.dal.dataobject.oauth2.OAuth2AccessTokenDO;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0;

/**
 * APP 端移动账号 Token 校验工具。
 *
 * <p>学员账号和组织前端账号都属于 MEMBER 用户类型，但通过 OAuth2 scope 隔离业务身份。</p>
 */
public final class AppMobileAuthUtils {

    public static final String CUSTOMER_STUDENT_SCOPE = "customer-student";
    public static final String COMPANY_FRONT_SCOPE = "company-front";

    private AppMobileAuthUtils() {
    }

    public static LoginUser requireStudentLoginUser() {
        return requireScopedMemberLoginUser(CUSTOMER_STUDENT_SCOPE, "学员令牌不能为空", "学员令牌类型不正确");
    }

    public static LoginUser requireCompanyFrontLoginUser() {
        return requireScopedMemberLoginUser(COMPANY_FRONT_SCOPE, "组织账号令牌不能为空", "组织账号令牌类型不正确");
    }

    public static void assertStudentAccessToken(OAuth2AccessTokenDO accessToken) {
        assertScopedMemberAccessToken(accessToken, CUSTOMER_STUDENT_SCOPE, "学员令牌类型不正确");
    }

    public static void assertCompanyFrontAccessToken(OAuth2AccessTokenDO accessToken) {
        assertScopedMemberAccessToken(accessToken, COMPANY_FRONT_SCOPE, "组织账号令牌类型不正确");
    }

    private static LoginUser requireScopedMemberLoginUser(String scope, String emptyMessage, String wrongTypeMessage) {
        LoginUser loginUser = SecurityFrameworkUtils.getLoginUser();
        if (loginUser == null) {
            throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), emptyMessage);
        }
        if (!UserTypeEnum.MEMBER.getValue().equals(loginUser.getUserType())
                || CollUtil.isEmpty(loginUser.getScopes())
                || !loginUser.getScopes().contains(scope)) {
            throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), wrongTypeMessage);
        }
        return loginUser;
    }

    private static void assertScopedMemberAccessToken(OAuth2AccessTokenDO accessToken, String scope, String wrongTypeMessage) {
        if (accessToken == null
                || !UserTypeEnum.MEMBER.getValue().equals(accessToken.getUserType())
                || CollUtil.isEmpty(accessToken.getScopes())
                || !accessToken.getScopes().contains(scope)) {
            throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), wrongTypeMessage);
        }
    }
}
