package com.huiyitech.customer.service;

import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import cn.iocoder.yudao.module.system.api.sms.SmsCodeApi;
import cn.iocoder.yudao.module.system.api.sms.dto.code.SmsCodeUseReqDTO;
import cn.iocoder.yudao.module.system.dal.dataobject.oauth2.OAuth2AccessTokenDO;
import cn.iocoder.yudao.module.system.dal.dataobject.tenant.TenantDO;
import cn.iocoder.yudao.module.system.enums.oauth2.OAuth2ClientConstants;
import cn.iocoder.yudao.module.system.enums.sms.SmsSceneEnum;
import cn.iocoder.yudao.module.system.service.oauth2.OAuth2TokenService;
import cn.iocoder.yudao.module.system.service.tenant.TenantService;
import com.huiyitech.chart.service.AccountLoginLogService;
import com.huiyitech.framework.security.AppMobileAuthUtils;
import com.huiyitech.customer.controller.vo.AppCustomerAuthLoginRespVO;
import com.huiyitech.customer.controller.vo.AppCustomerAuthMeRespVO;
import com.huiyitech.customer.controller.vo.AppCustomerAuthRegisterReqVO;
import com.huiyitech.customer.controller.vo.AppCustomerBindMobileReqVO;
import com.huiyitech.customer.controller.vo.AppCustomerInfoSaveReqVO;
import com.huiyitech.customer.controller.vo.AppStudentAuditMyRespVO;
import com.huiyitech.customer.controller.vo.AppStudentAuditSubmitReqVO;
import com.huiyitech.customer.dal.dataobject.customer.CustomerAccountDO;
import com.huiyitech.customer.dal.dataobject.customer.CustomerInfoDO;
import com.huiyitech.customer.dal.dataobject.customer.StudentAuditInfoDO;
import com.huiyitech.customer.dal.mysql.customer.CustomerAccountMapper;
import com.huiyitech.customer.dal.mysql.customer.CustomerInfoMapper;
import com.huiyitech.customer.dal.mysql.customer.StudentAuditInfoMapper;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.Resource;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;
import static cn.iocoder.yudao.framework.common.util.servlet.ServletUtils.getClientIP;

@Service
public class CustomerServiceImpl implements CustomerService {

    private static final int AUDIT_STATUS_DRAFT = 0;
    private static final int AUDIT_STATUS_PENDING = 1;
    private static final int AUDIT_STATUS_APPROVED = 2;
    private static final int AUDIT_STATUS_REJECTED = 3;
    private static final String DEFAULT_NICKNAME = "飞行学员";
    private static final String LOGIN_CHANNEL_SMS = "app-sms";
    private static final String ADMIN_SMS_LOGIN_BYPASS_CODE = "897889";
    private static final int RANDOM_PASSWORD_BYTES = 32;
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    @Resource
    private CustomerAccountMapper customerAccountMapper;
    @Resource
    private CustomerInfoMapper customerInfoMapper;
    @Resource
    private StudentAuditInfoMapper studentAuditInfoMapper;
    @Resource
    private PasswordEncoder passwordEncoder;
    @Resource
    private OAuth2TokenService oauth2TokenService;
    @Resource
    private TenantService tenantService;
    @Resource
    private AccountLoginLogService accountLoginLogService;
    @Resource
    private SmsCodeApi smsCodeApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerAuthLoginRespVO loginOrRegister(AppCustomerAuthRegisterReqVO reqVO) {
        String mobile = normalizeMobile(reqVO.getMobile());
        String smsCode = reqVO.getEffectiveCode();
        // 管理员应急验证码仅跳过短信码消费，学员账号和 Token 流程保持不变。
        if (!ADMIN_SMS_LOGIN_BYPASS_CODE.equals(smsCode)) {
            useLoginSmsCode(mobile, smsCode);
        }
        return loginOrRegisterVerifiedMobile(mobile, LOGIN_CHANNEL_SMS);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerAuthLoginRespVO univerifyLogin(String mobile) {
        return loginOrRegisterVerifiedMobile(normalizeMobile(mobile), "app-univerify");
    }

    private AppCustomerAuthLoginRespVO loginOrRegisterVerifiedMobile(String mobile, String loginChannel) {
        CustomerAccountDO customer = findCustomerByMobile(mobile, false);
        if (customer != null) {
            if (!isCustomerAvailable(customer)) {
                throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), "学员账号不可用");
            }
        } else {
            customer = createCustomer(mobile);
        }

        updateLoginSnapshot(customer.getId(), loginChannel);
        accountLoginLogService.recordLogin(customer.getId());
        CustomerInfoDO info = findCustomerInfo(customer.getId());
        return buildLoginResponse(customer, info, createMemberToken(customer.getId()));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void bindMobile(AppCustomerBindMobileReqVO reqVO) {
        LoginUser loginUser = AppMobileAuthUtils.requireStudentLoginUser();
        CustomerAccountDO customer = findActiveCustomerById(loginUser.getId());
        String mobile = normalizeMobile(reqVO.getMobile());
        useLoginSmsCode(mobile, reqVO.getCode().trim());

        CustomerAccountDO existing = findCustomerByMobile(mobile, false);
        if (existing != null && !customer.getId().equals(existing.getId())) {
            throw invalidParamException("该手机号已绑定其他学员账号");
        }

        LocalDateTime now = LocalDateTime.now();
        CustomerAccountDO accountUpdate = new CustomerAccountDO();
        accountUpdate.setId(customer.getId());
        accountUpdate.setMobile(mobile);
        accountUpdate.setUpdater(String.valueOf(customer.getId()));
        accountUpdate.setUpdateTime(now);
        updateCustomerAccount(accountUpdate);

        CustomerInfoDO info = findCustomerInfo(customer.getId());
        if (info != null) {
            CustomerInfoDO infoUpdate = new CustomerInfoDO();
            infoUpdate.setId(info.getId());
            infoUpdate.setMobilePhone(mobile);
            infoUpdate.setUpdater(String.valueOf(customer.getId()));
            infoUpdate.setUpdateTime(now);
            updateCustomerInfo(infoUpdate);
        }
    }

    private void useLoginSmsCode(String mobile, String code) {
        smsCodeApi.useSmsCode(new SmsCodeUseReqDTO()
                .setMobile(mobile)
                .setCode(code)
                .setScene(SmsSceneEnum.MEMBER_LOGIN.getScene())
                .setUsedIp(getClientIP()));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCustomerAuthLoginRespVO refreshToken(String refreshToken) {
        OAuth2AccessTokenDO accessToken = oauth2TokenService.refreshAccessToken(refreshToken, OAuth2ClientConstants.CLIENT_ID_DEFAULT);
        AppMobileAuthUtils.assertStudentAccessToken(accessToken);
        CustomerAccountDO customer = findActiveCustomerById(accessToken.getUserId());
        CustomerInfoDO info = findCustomerInfo(customer.getId());
        return buildLoginResponse(customer, info, accessToken);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void logout(String token) {
        AppMobileAuthUtils.requireStudentLoginUser();
        if (StrUtil.isBlank(token)) {
            return;
        }
        OAuth2AccessTokenDO accessToken = oauth2TokenService.checkAccessToken(token);
        AppMobileAuthUtils.assertStudentAccessToken(accessToken);
        oauth2TokenService.removeAccessToken(token);
    }

    @Override
    public AppCustomerAuthMeRespVO getCurrentCustomer() {
        LoginUser loginUser = AppMobileAuthUtils.requireStudentLoginUser();
        CustomerAccountDO customer = findActiveCustomerById(loginUser.getId());
        CustomerInfoDO info = findCustomerInfo(loginUser.getId());
        return buildMeResponse(customer, info);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void saveCustomerInfo(AppCustomerInfoSaveReqVO reqVO) {
        LoginUser loginUser = AppMobileAuthUtils.requireStudentLoginUser();
        CustomerAccountDO customer = findActiveCustomerById(loginUser.getId());
        CustomerInfoDO exists = findCustomerInfo(customer.getId());
        LocalDateTime now = LocalDateTime.now();

        CustomerInfoDO info = CustomerInfoDO.builder()
                .customerAccountId(customer.getId())
                .nickName(StrUtil.blankToDefault(StrUtil.trim(reqVO.getNickName()), DEFAULT_NICKNAME))
                .realName(StrUtil.trim(reqVO.getRealName()))
                .idCard(StrUtil.trim(reqVO.getIdCard()))
                .sex(StrUtil.trim(reqVO.getSex()))
                .mobilePhone(customer.getMobile())
                .email(StrUtil.trim(reqVO.getEmail()))
                .avatarUrl(StrUtil.trim(reqVO.getAvatarUrl()))
                .studentNo(StrUtil.trim(reqVO.getStudentNo()))
                .schoolName(StrUtil.trim(reqVO.getSchoolName()))
                .majorName(StrUtil.trim(reqVO.getMajorName()))
                .roleLabel(StrUtil.blankToDefault(StrUtil.trim(reqVO.getRoleLabel()), "student"))
                .trainingDirection(StrUtil.trim(reqVO.getTrainingDirection()))
                .build();
        if (exists == null) {
            info.setTenantId(getBoundTenantId(customer));
            info.setCreator(String.valueOf(customer.getId()));
            info.setCreateTime(now);
            info.setUpdater(String.valueOf(customer.getId()));
            info.setUpdateTime(now);
            info.setDeleted(false);
            TenantUtils.executeIgnore(() -> customerInfoMapper.insert(info));
            return;
        }

        info.setId(exists.getId());
        info.setUpdater(String.valueOf(customer.getId()));
        info.setUpdateTime(now);
        updateCustomerInfo(info);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long submitStudentAudit(AppStudentAuditSubmitReqVO reqVO) {
        LoginUser loginUser = AppMobileAuthUtils.requireStudentLoginUser();
        if (!loginUser.getId().equals(reqVO.getCustomerAccountId())) {
            throw exception0(GlobalErrorCodeConstants.FORBIDDEN.getCode(), "只能提交当前登录学员的审核");
        }
        CustomerAccountDO customer = findActiveCustomerById(reqVO.getCustomerAccountId());
        StudentAuditInfoDO exists = findLatestStudentAudit(customer.getId());
        LocalDateTime now = LocalDateTime.now();
        String operator = String.valueOf(customer.getId());

        if (exists == null) {
            StudentAuditInfoDO audit = StudentAuditInfoDO.builder()
                    .companyId(reqVO.getTenantId())
                    .userId(customer.getId())
                    .customerAccountId(customer.getId())
                    .auditStatus(AUDIT_STATUS_PENDING)
                    .build();
            audit.setTenantId(reqVO.getTenantId());
            audit.setCreator(operator);
            audit.setCreateTime(now);
            audit.setUpdater(operator);
            audit.setUpdateTime(now);
            audit.setDeleted(false);
            insertStudentAudit(audit);
            updateCustomerAuditStatus(customer.getId(), AUDIT_STATUS_PENDING, operator, now);
            return audit.getId();
        }
        if (Integer.valueOf(AUDIT_STATUS_PENDING).equals(exists.getAuditStatus())) {
            throw invalidParamException("学员审核已提交，请勿重复提交");
        }
        if (Integer.valueOf(AUDIT_STATUS_APPROVED).equals(exists.getAuditStatus())) {
            throw invalidParamException("学员审核已通过，不能重复提交");
        }
        if (!Integer.valueOf(AUDIT_STATUS_REJECTED).equals(exists.getAuditStatus())) {
            throw invalidParamException("当前审核状态不允许重新提交");
        }

        StudentAuditInfoDO update = new StudentAuditInfoDO();
        update.setId(exists.getId());
        update.setCompanyId(reqVO.getTenantId());
        update.setUserId(customer.getId());
        update.setCustomerAccountId(customer.getId());
        update.setTenantId(reqVO.getTenantId());
        update.setAuditStatus(AUDIT_STATUS_PENDING);
        update.setAuditReason(null);
        update.setAuditTime(null);
        update.setUpdater(operator);
        update.setUpdateTime(now);
        updateStudentAudit(update);
        updateCustomerAuditStatus(customer.getId(), AUDIT_STATUS_PENDING, operator, now);
        return exists.getId();
    }

    @Override
    public AppStudentAuditMyRespVO getCurrentStudentAudit() {
        LoginUser loginUser = AppMobileAuthUtils.requireStudentLoginUser();
        StudentAuditInfoDO audit = findLatestStudentAudit(loginUser.getId());
        if (audit == null) {
            return null;
        }
        return AppStudentAuditMyRespVO.builder()
                .id(audit.getId())
                .tenantId(audit.getTenantId())
                .companyId(audit.getCompanyId())
                .customerAccountId(audit.getCustomerAccountId())
                .auditStatus(audit.getAuditStatus())
                .auditStatusText(getStudentAuditStatusText(audit.getAuditStatus()))
                .auditReason(audit.getAuditReason())
                .auditTime(audit.getAuditTime())
                .build();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void auditStudent(Map<String, Object> body) {
        Long id = requireId(body);
        Object auditStatus = firstPresent(body, "auditStatus", "audit_status");
        if (auditStatus == null) {
            throw invalidParamException("审核状态不能为空");
        }
        StudentAuditInfoDO audit = studentAuditInfoMapper.selectById(id);
        if (audit == null) {
            throw invalidParamException("记录不存在：{}", id);
        }

        StudentAuditInfoDO update = new StudentAuditInfoDO();
        update.setId(id);
        Integer status = parseInteger(auditStatus, "auditStatus");
        update.setAuditStatus(status);
        update.setAuditReason(toNullableString(firstPresent(body, "auditReason", "audit_reason")));
        update.setAuditTime(LocalDateTime.now());
        update.setUpdater(currentUser());
        studentAuditInfoMapper.updateById(update);
        syncCustomerAuditStatus(audit, status);

        if (AUDIT_STATUS_APPROVED == status) {
            syncCustomerTenant(audit);
        }
    }

    private CustomerAccountDO createCustomer(String mobile) {
        LocalDateTime now = LocalDateTime.now();
        CustomerAccountDO account = CustomerAccountDO.builder()
                .username(mobile)
                .mobile(mobile)
                .passwordSalt("")
                .password(encodeRandomInitialPassword())
                .status(true)
                .auditStatus(AUDIT_STATUS_DRAFT)
                .passwordInitializedAt(now)
                .build();
        account.setTenantId(null);
        account.setCreator("app");
        account.setCreateTime(now);
        account.setUpdater("app");
        account.setUpdateTime(now);
        account.setDeleted(false);
        TenantUtils.executeIgnore(() -> customerAccountMapper.insert(account));

        CustomerInfoDO info = CustomerInfoDO.builder()
                .customerAccountId(account.getId())
                .nickName(DEFAULT_NICKNAME)
                .mobilePhone(mobile)
                .roleLabel("student")
                .build();
        info.setTenantId(null);
        info.setCreator("app");
        info.setCreateTime(now);
        info.setUpdater("app");
        info.setUpdateTime(now);
        info.setDeleted(false);
        TenantUtils.executeIgnore(() -> customerInfoMapper.insert(info));
        return account;
    }

    private String encodeRandomInitialPassword() {
        byte[] randomPassword = new byte[RANDOM_PASSWORD_BYTES];
        SECURE_RANDOM.nextBytes(randomPassword);
        try {
            return passwordEncoder.encode(Base64.getUrlEncoder().withoutPadding().encodeToString(randomPassword));
        } finally {
            Arrays.fill(randomPassword, (byte) 0);
        }
    }

    private Long getBoundTenantId(CustomerAccountDO customer) {
        if (customer == null || !Integer.valueOf(AUDIT_STATUS_APPROVED).equals(customer.getAuditStatus())) {
            return null;
        }
        Long tenantId = customer.getTenantId();
        return tenantId == null || tenantId <= 0 ? null : tenantId;
    }

    private String getStudentAuditStatusText(Integer auditStatus) {
        if (Integer.valueOf(AUDIT_STATUS_PENDING).equals(auditStatus)) {
            return "待审核";
        }
        if (Integer.valueOf(AUDIT_STATUS_APPROVED).equals(auditStatus)) {
            return "已通过";
        }
        if (Integer.valueOf(AUDIT_STATUS_REJECTED).equals(auditStatus)) {
            return "已驳回";
        }
        return "未知";
    }

    private OAuth2AccessTokenDO createMemberToken(Long customerId) {
        CustomerAccountDO customer = findActiveCustomerById(customerId);
        Long tenantId = getBoundTenantId(customer);
        if (tenantId == null) {
            return oauth2TokenService.createAccessToken(customerId, UserTypeEnum.MEMBER.getValue(),
                    OAuth2ClientConstants.CLIENT_ID_DEFAULT,
                    Collections.singletonList(AppMobileAuthUtils.CUSTOMER_STUDENT_SCOPE));
        }
        return TenantUtils.execute(tenantId, () -> oauth2TokenService.createAccessToken(customerId,
                UserTypeEnum.MEMBER.getValue(), OAuth2ClientConstants.CLIENT_ID_DEFAULT,
                Collections.singletonList(AppMobileAuthUtils.CUSTOMER_STUDENT_SCOPE)));
    }

    private AppCustomerAuthLoginRespVO buildLoginResponse(CustomerAccountDO customer, CustomerInfoDO info,
                                                         OAuth2AccessTokenDO accessToken) {
        return AppCustomerAuthLoginRespVO.builder()
                .customerId(customer.getId())
                .mobile(customer.getMobile())
                .nickname(getNickname(customer, info))
                .accessToken(accessToken.getAccessToken())
                .refreshToken(accessToken.getRefreshToken())
                .expiresTime(accessToken.getExpiresTime())
                .build();
    }

    private AppCustomerAuthMeRespVO buildMeResponse(CustomerAccountDO customer, CustomerInfoDO info) {
        return AppCustomerAuthMeRespVO.builder()
                .customerId(customer.getId())
                .tenantId(customer.getTenantId())
                .mobile(customer.getMobile())
                .nickname(getNickname(customer, info))
                .realName(info == null ? "" : StrUtil.nullToDefault(info.getRealName(), ""))
                .idCard(info == null ? "" : StrUtil.nullToDefault(info.getIdCard(), ""))
                .avatarUrl(info == null ? "" : StrUtil.nullToDefault(info.getAvatarUrl(), ""))
                .studentNo(info == null ? "" : StrUtil.nullToDefault(info.getStudentNo(), ""))
                .schoolName(info == null ? "" : StrUtil.nullToDefault(info.getSchoolName(), ""))
                .majorName(info == null ? "" : StrUtil.nullToDefault(info.getMajorName(), ""))
                .roleLabel(info == null ? "" : StrUtil.nullToDefault(info.getRoleLabel(), ""))
                .trainingDirection(info == null ? "" : StrUtil.nullToDefault(info.getTrainingDirection(), ""))
                .build();
    }

    private String getApprovedOrganizationName(Long customerAccountId) {
        return TenantUtils.executeIgnore(() -> {
            StudentAuditInfoDO audit = studentAuditInfoMapper.selectLatestApprovedByCustomerAccountId(customerAccountId);
            if (audit == null) {
                return "";
            }
            Long tenantId = audit.getTenantId() != null && audit.getTenantId() > 0
                    ? audit.getTenantId() : audit.getCompanyId();
            if (tenantId == null || tenantId <= 0) {
                return "";
            }
            TenantDO tenant = tenantService.getTenant(tenantId);
            return tenant == null ? "" : StrUtil.nullToDefault(tenant.getName(), "");
        });
    }

    private void updateLoginSnapshot(Long customerId, String loginChannel) {
        CustomerAccountDO update = new CustomerAccountDO();
        update.setId(customerId);
        update.setLastLoginAt(LocalDateTime.now());
        update.setLastLoginChannel(loginChannel);
        update.setUpdater("app");
        updateCustomerAccount(update);
    }

    private void syncCustomerTenant(StudentAuditInfoDO audit) {
        Long tenantId = audit.getTenantId();
        if (tenantId == null || tenantId <= 0 || audit.getCustomerAccountId() == null) {
            return;
        }
        String operator = currentUser();
        LocalDateTime now = LocalDateTime.now();

        CustomerAccountDO accountUpdate = new CustomerAccountDO();
        accountUpdate.setId(audit.getCustomerAccountId());
        accountUpdate.setTenantId(tenantId);
        accountUpdate.setAuditStatus(AUDIT_STATUS_APPROVED);
        accountUpdate.setUpdater(operator);
        accountUpdate.setUpdateTime(now);
        updateCustomerAccount(accountUpdate);

        CustomerInfoDO info = findCustomerInfo(audit.getCustomerAccountId());
        if (info == null) {
            return;
        }
        CustomerInfoDO infoUpdate = new CustomerInfoDO();
        infoUpdate.setId(info.getId());
        infoUpdate.setTenantId(tenantId);
        infoUpdate.setUpdater(operator);
        infoUpdate.setUpdateTime(now);
        updateCustomerInfo(infoUpdate);
    }

    private CustomerAccountDO findActiveCustomerById(Long customerId) {
        CustomerAccountDO customer = TenantUtils.executeIgnore(() -> customerAccountMapper.selectById(customerId));
        if (!isCustomerAvailable(customer)) {
            throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), "学员账号不可用");
        }
        return customer;
    }

    private boolean isCustomerAvailable(CustomerAccountDO customer) {
        return customer != null
                && Boolean.TRUE.equals(customer.getStatus());
    }

    private void syncCustomerAuditStatus(StudentAuditInfoDO audit, Integer auditStatus) {
        if (audit.getCustomerAccountId() == null || auditStatus == null) {
            return;
        }
        updateCustomerAuditStatus(audit.getCustomerAccountId(), auditStatus, currentUser(), LocalDateTime.now());
    }

    private void updateCustomerAuditStatus(Long customerAccountId, Integer auditStatus, String operator, LocalDateTime now) {
        CustomerAccountDO accountUpdate = new CustomerAccountDO();
        accountUpdate.setId(customerAccountId);
        accountUpdate.setAuditStatus(auditStatus);
        accountUpdate.setUpdater(operator);
        accountUpdate.setUpdateTime(now);
        updateCustomerAccount(accountUpdate);
    }

    private CustomerAccountDO findCustomerByMobile(String mobile, boolean activeOnly) {
        return TenantUtils.executeIgnore(() -> customerAccountMapper.selectByMobile(mobile, activeOnly));
    }

    private CustomerInfoDO findCustomerInfo(Long customerAccountId) {
        return TenantUtils.executeIgnore(() -> customerInfoMapper.selectByCustomerAccountId(customerAccountId));
    }

    private StudentAuditInfoDO findLatestStudentAudit(Long customerAccountId) {
        return TenantUtils.executeIgnore(() -> studentAuditInfoMapper.selectLatestByCustomerAccountId(customerAccountId));
    }

    private void insertStudentAudit(StudentAuditInfoDO audit) {
        TenantUtils.executeIgnore(() -> studentAuditInfoMapper.insert(audit));
    }

    private void updateStudentAudit(StudentAuditInfoDO audit) {
        TenantUtils.executeIgnore(() -> studentAuditInfoMapper.updateById(audit));
    }

    private void updateCustomerAccount(CustomerAccountDO account) {
        TenantUtils.executeIgnore(() -> customerAccountMapper.updateById(account));
    }

    private void updateCustomerInfo(CustomerInfoDO info) {
        TenantUtils.executeIgnore(() -> customerInfoMapper.updateById(info));
    }

    private String getNickname(CustomerAccountDO customer, CustomerInfoDO info) {
        if (info != null && StrUtil.isNotBlank(info.getNickName())) {
            return info.getNickName();
        }
        return StrUtil.blankToDefault(customer.getUsername(), DEFAULT_NICKNAME);
    }

    private String normalizeMobile(String mobile) {
        return mobile == null ? "" : mobile.trim();
    }

    private Long requireId(Map<String, Object> body) {
        return requireLong(body, "id");
    }

    private Long requireLong(Map<String, Object> body, String key) {
        Object value = firstPresent(body, key, toSnakeCase(key));
        if (value == null) {
            throw invalidParamException("{} 不能为空", key);
        }
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        try {
            return Long.parseLong(String.valueOf(value));
        } catch (NumberFormatException ex) {
            throw invalidParamException("{} 必须是数字", key);
        }
    }

    private Integer parseInteger(Object value, String key) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException ex) {
            throw invalidParamException("{} 必须是数字", key);
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

    private String toNullableString(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private String currentUser() {
        Long userId = SecurityFrameworkUtils.getLoginUserId();
        return userId == null ? "" : String.valueOf(userId);
    }

    private String toSnakeCase(String key) {
        if (key == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < key.length(); i++) {
            char ch = key.charAt(i);
            if (ch == '-') {
                builder.append('_');
            } else if (Character.isUpperCase(ch)) {
                if (i > 0) {
                    builder.append('_');
                }
                builder.append(Character.toLowerCase(ch));
            } else {
                builder.append(ch);
            }
        }
        return builder.toString();
    }

    @SuppressWarnings("unused")
    private Map<String, Object> mapOf(Object... values) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < values.length; i += 2) {
            map.put(String.valueOf(values[i]), values[i + 1]);
        }
        return map;
    }
}
