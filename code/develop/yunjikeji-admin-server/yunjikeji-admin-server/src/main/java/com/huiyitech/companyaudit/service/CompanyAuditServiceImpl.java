package com.huiyitech.companyaudit.service;

import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import cn.iocoder.yudao.module.system.api.sms.SmsCodeApi;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.DeptDO;
import cn.iocoder.yudao.module.system.api.sms.dto.code.SmsCodeUseReqDTO;
import cn.iocoder.yudao.module.system.dal.dataobject.oauth2.OAuth2AccessTokenDO;
import cn.iocoder.yudao.module.system.dal.dataobject.tenant.TenantDO;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.PostDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.dal.mysql.dept.DeptMapper;
import cn.iocoder.yudao.module.system.dal.mysql.dept.PostMapper;
import cn.iocoder.yudao.module.system.dal.mysql.user.AdminUserMapper;
import cn.iocoder.yudao.module.system.enums.oauth2.OAuth2ClientConstants;
import cn.iocoder.yudao.module.system.enums.sms.SmsSceneEnum;
import cn.iocoder.yudao.module.system.service.oauth2.OAuth2TokenService;
import cn.iocoder.yudao.module.system.service.tenant.TenantEnterpriseAuditCreateReqDTO;
import cn.iocoder.yudao.module.system.service.tenant.TenantService;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuditAttachmentReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuditSaveReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuditSubmitReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthLoginRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthMeRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthPostCodesRespVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthRegisterReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditPageReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditReqVO;
import com.huiyitech.companyaudit.controller.vo.AppCompanyStudentAuditRespVO;
import com.huiyitech.companyaudit.dal.dataobject.companyaudit.CompanyAccountFrontDO;
import com.huiyitech.companyaudit.dal.dataobject.companyaudit.CompanyAuditAttachmentDO;
import com.huiyitech.companyaudit.dal.dataobject.companyaudit.CompanyAuditInfoDO;
import com.huiyitech.companyaudit.dal.mysql.companyaudit.CompanyAccountFrontMapper;
import com.huiyitech.companyaudit.dal.mysql.companyaudit.CompanyAuditAttachmentMapper;
import com.huiyitech.companyaudit.dal.mysql.companyaudit.CompanyAuditInfoMapper;
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
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Collections;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;
import static cn.iocoder.yudao.framework.common.util.servlet.ServletUtils.getClientIP;

@Service
public class CompanyAuditServiceImpl implements CompanyAuditService {

    private static final int AUDIT_STATUS_DRAFT = 0;
    private static final int AUDIT_STATUS_APPROVED = 2;
    private static final int AUDIT_STATUS_REJECTED = 3;
    private static final int AUDIT_STATUS_PENDING = 1;
    private static final String COMPANY_FRONT_SCOPE = "company-front";
    private static final int RANDOM_PASSWORD_BYTES = 32;
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    @Resource
    private CompanyAccountFrontMapper companyAccountFrontMapper;
    @Resource
    private CompanyAuditInfoMapper companyAuditInfoMapper;
    @Resource
    private CompanyAuditAttachmentMapper companyAuditAttachmentMapper;
    @Resource
    private TenantService tenantService;
    @Resource
    private OAuth2TokenService oauth2TokenService;
    @Resource
    private PasswordEncoder passwordEncoder;
    @Resource
    private AdminUserMapper adminUserMapper;
    @Resource
    private DeptMapper deptMapper;
    @Resource
    private PostMapper postMapper;
    @Resource
    private StudentAuditInfoMapper studentAuditInfoMapper;
    @Resource
    private CustomerAccountMapper customerAccountMapper;
    @Resource
    private CustomerInfoMapper customerInfoMapper;
    @Resource
    private SmsCodeApi smsCodeApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCompanyAuthLoginRespVO loginOrRegister(AppCompanyAuthRegisterReqVO reqVO) {
        String mobile = normalizeMobile(reqVO.getMobile());
        String smsCode = reqVO.getEffectiveCode();
        useLoginSmsCode(mobile, smsCode);
        return loginOrRegisterVerifiedMobile(mobile, "app-sms");
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCompanyAuthLoginRespVO univerifyLogin(String mobile) {
        return loginOrRegisterVerifiedMobile(normalizeMobile(mobile), "app-univerify");
    }

    private AppCompanyAuthLoginRespVO loginOrRegisterVerifiedMobile(String mobile, String creator) {
        CompanyAccountFrontDO account = findCompanyAccountByUsername(mobile);
        if (account != null) {
            if (!Boolean.TRUE.equals(account.getStatus())) {
                throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), "组织账号不可用");
            }
        } else {
            account = CompanyAccountFrontDO.builder()
                    .username(mobile)
                    .password(encodeRandomInitialPassword())
                    .status(true)
                    .auditStatus(AUDIT_STATUS_DRAFT)
                    .build();
            fillCreateValues(account, creator);
            insertCompanyAccount(account);
        }
        return buildLoginResponse(account, createCompanyToken(account));
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

    private void useLoginSmsCode(String mobile, String code) {
        smsCodeApi.useSmsCode(new SmsCodeUseReqDTO()
                .setMobile(mobile)
                .setCode(code)
                .setScene(SmsSceneEnum.MEMBER_LOGIN.getScene())
                .setUsedIp(getClientIP()));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AppCompanyAuthLoginRespVO refreshToken(String refreshToken) {
        OAuth2AccessTokenDO accessToken = oauth2TokenService.refreshAccessToken(refreshToken, OAuth2ClientConstants.CLIENT_ID_DEFAULT);
        assertCompanyFrontAccessToken(accessToken);
        CompanyAccountFrontDO account = findActiveCompanyAccountById(accessToken.getUserId());
        if (isTenantMismatch(account, accessToken)) {
            oauth2TokenService.removeAccessToken(accessToken.getAccessToken());
            accessToken = createCompanyToken(account);
        }
        return buildLoginResponse(account, accessToken);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void logout(String token) {
        requireCompanyFrontLoginUser();
        if (StrUtil.isBlank(token)) {
            return;
        }
        OAuth2AccessTokenDO accessToken = oauth2TokenService.checkAccessToken(token);
        assertCompanyFrontAccessToken(accessToken);
        oauth2TokenService.removeAccessToken(token);
    }

    @Override
    public AppCompanyAuthMeRespVO getCurrentCompanyAccount() {
        CompanyAccountFrontDO account = getCurrentCompanyAccountRequired();
        TenantDO tenant = getAccountTenant(account);
        CurrentCompanyProfile profile = resolveCurrentCompanyProfile(getBoundTenantId(account), account.getUsername());
        return AppCompanyAuthMeRespVO.builder()
                .companyAccountFrontId(account.getId())
                .tenantId(account.getTenantId())
                .tenantName(tenant != null ? tenant.getName() : null)
                .tenantContactName(tenant != null ? tenant.getContactName() : null)
                .tenantContactMobile(tenant != null ? tenant.getContactMobile() : null)
                .username(account.getUsername())
                .nickname(profile.getNickname())
                .deptName(profile.getDeptName())
                .status(account.getStatus())
                .auditStatus(account.getAuditStatus())
                .build();
    }

    @Override
    public AppCompanyAuthPostCodesRespVO getCompanyAuthPostCodes(String mobile) {
        LoginUser loginUser = requireCompanyFrontLoginUser();
        String normalizedMobile = normalizeMobile(mobile);
        if (StrUtil.isBlank(normalizedMobile)) {
            return buildPostCodesResponse(false, Collections.emptyList(), null);
        }

        List<AdminUserDO> users = TenantUtils.executeIgnore(() ->
                adminUserMapper.selectList(AdminUserDO::getMobile, normalizedMobile));
        if (users == null || users.isEmpty()) {
            return buildPostCodesResponse(false, Collections.emptyList(), null);
        }

        Long tenantId = users.stream()
                .map(AdminUserDO::getTenantId)
                .filter(id -> id != null && id > 0)
                .findFirst()
                .orElse(null);
        bindCurrentCompanyAccountTenantIfAbsent(loginUser.getId(), normalizedMobile, tenantId);

        Set<Long> postIds = users.stream()
                .filter(user -> user.getPostIds() != null)
                .flatMap(user -> user.getPostIds().stream())
                .filter(postId -> postId != null && postId > 0)
                .collect(Collectors.toCollection(LinkedHashSet::new));
        if (postIds.isEmpty()) {
            return buildPostCodesResponse(true, Collections.emptyList(), tenantId);
        }

        List<PostDO> posts = TenantUtils.executeIgnore(() -> postMapper.selectList(postIds, null));
        List<String> postCodes = posts == null ? Collections.emptyList() : posts.stream()
                .map(PostDO::getCode)
                .filter(StrUtil::isNotBlank)
                .distinct()
                .collect(Collectors.toCollection(ArrayList::new));
        return buildPostCodesResponse(true, postCodes, tenantId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long saveAudit(AppCompanyAuditSaveReqVO reqVO) {
        CompanyAccountFrontDO account = getCurrentCompanyAccountRequired();
        CompanyAuditInfoDO exists = findLatestCompanyAudit(account.getId());
        if (exists != null) {
            assertAuditCanEditOrSubmit(exists);
        }

        String companyName = StrUtil.trim(reqVO.getName());
        String contactMobile = StrUtil.trim(reqVO.getContactMobile());
        assertNoDuplicatePendingAudit(contactMobile, companyName, exists == null ? null : exists.getId());

        CompanyAuditInfoDO audit = CompanyAuditInfoDO.builder()
                .userId(reqVO.getUserId())
                .companyAccountFrontId(account.getId())
                .name(companyName)
                .creditCode(StrUtil.trim(reqVO.getCreditCode()))
                .legalPerson(StrUtil.trim(reqVO.getLegalPerson()))
                .legalPersonId(StrUtil.trim(reqVO.getLegalPersonId()))
                .contactName(StrUtil.trim(reqVO.getContactName()))
                .contactMobile(contactMobile)
                .build();
        if (exists != null) {
            audit.setId(exists.getId());
            audit.setAuditStatus(AUDIT_STATUS_DRAFT);
            audit.setAuditReason(null);
            audit.setAuditTime(null);
            audit.setAuditUserId(null);
            audit.setTenantId(null);
            audit.setUpdater(String.valueOf(account.getId()));
            audit.setUpdateTime(LocalDateTime.now());
            updateCompanyAudit(audit);
            updateCompanyAccountAuditStatus(account.getId(), AUDIT_STATUS_DRAFT, String.valueOf(account.getId()));
            deleteCompanyAuditAttachments(exists.getId());
            saveAttachments(exists.getId(), account.getId(), reqVO.getUserId(), reqVO.getAttachments());
            return exists.getId();
        }

        audit.setAuditStatus(AUDIT_STATUS_DRAFT);
        fillCreateValues(audit, String.valueOf(account.getId()));
        insertCompanyAudit(audit);
        updateCompanyAccountAuditStatus(account.getId(), AUDIT_STATUS_DRAFT, String.valueOf(account.getId()));
        saveAttachments(audit.getId(), account.getId(), reqVO.getUserId(), reqVO.getAttachments());
        return audit.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long submitAudit(AppCompanyAuditSubmitReqVO reqVO) {
        CompanyAccountFrontDO account = getCurrentCompanyAccountRequired();
        if (!account.getId().equals(reqVO.getCompanyAccountFrontId())) {
            throw exception0(GlobalErrorCodeConstants.FORBIDDEN.getCode(), "只能提交当前登录企业账号的审核");
        }

        CompanyAuditInfoDO audit = findLatestCompanyAudit(account.getId());
        if (audit == null) {
            throw invalidParamException("请先保存企业审核信息");
        }
        assertAuditCanEditOrSubmit(audit);
        assertNoDuplicatePendingAudit(audit.getContactMobile(), audit.getName(), audit.getId());

        CompanyAuditInfoDO update = new CompanyAuditInfoDO();
        update.setId(audit.getId());
        update.setAuditStatus(AUDIT_STATUS_PENDING);
        update.setAuditReason(null);
        update.setAuditTime(null);
        update.setAuditUserId(null);
        update.setUpdater(String.valueOf(account.getId()));
        updateCompanyAudit(update);
        updateCompanyAccountAuditStatus(account.getId(), AUDIT_STATUS_PENDING, String.valueOf(account.getId()));
        return audit.getId();
    }

    @Override
    public PageResult<AppCompanyStudentAuditRespVO> getCurrentCompanyStudentAuditPage(AppCompanyStudentAuditPageReqVO reqVO) {
        CompanyAccountFrontDO account = getCurrentCompanyAccountRequired();
        Long tenantId = requireCompanyTenantId(account);
        List<StudentAuditInfoDO> audits = TenantUtils.executeIgnore(() ->
                studentAuditInfoMapper.selectCompanyStudentAuditList(tenantId,
                        reqVO.getAuditStatus(), reqVO.getStartTime(), reqVO.getEndTime()));
        List<AppCompanyStudentAuditRespVO> matchedList = audits.stream()
                .map(this::toStudentAuditRespVO)
                .filter(item -> matchesStudentKeyword(item, reqVO.getKeyword()))
                .collect(Collectors.toList());
        int fromIndex = Math.max((reqVO.getPageNo() - 1) * reqVO.getPageSize(), 0);
        if (fromIndex >= matchedList.size()) {
            return new PageResult<>(Collections.emptyList(), (long) matchedList.size());
        }
        int toIndex = Math.min(fromIndex + reqVO.getPageSize(), matchedList.size());
        return new PageResult<>(matchedList.subList(fromIndex, toIndex), (long) matchedList.size());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void auditCurrentCompanyStudent(AppCompanyStudentAuditReqVO reqVO) {
        CompanyAccountFrontDO account = getCurrentCompanyAccountRequired();
        Long tenantId = requireCompanyTenantId(account);
        Integer auditStatus = reqVO.getAuditStatus();
        if (!Integer.valueOf(AUDIT_STATUS_APPROVED).equals(auditStatus)
                && !Integer.valueOf(AUDIT_STATUS_REJECTED).equals(auditStatus)) {
            throw invalidParamException("审核状态只允许通过或驳回");
        }

        StudentAuditInfoDO audit = TenantUtils.executeIgnore(() -> studentAuditInfoMapper.selectById(reqVO.getId()));
        if (!isCurrentCompanyStudentAudit(audit, tenantId)) {
            throw invalidParamException("审核记录不存在");
        }
        if (!Integer.valueOf(AUDIT_STATUS_PENDING).equals(audit.getAuditStatus())) {
            throw invalidParamException("当前审核记录不允许重复处理");
        }

        StudentAuditInfoDO update = new StudentAuditInfoDO();
        update.setId(audit.getId());
        update.setAuditStatus(auditStatus);
        update.setAuditReason(normalizeStudentAuditReason(auditStatus, reqVO.getAuditReason()));
        update.setAuditTime(LocalDateTime.now());
        update.setUpdater(String.valueOf(account.getId()));
        TenantUtils.executeIgnore(() -> studentAuditInfoMapper.updateById(update));
        syncStudentCustomerAuditStatus(audit, auditStatus, String.valueOf(account.getId()));

        if (Integer.valueOf(AUDIT_STATUS_APPROVED).equals(auditStatus)) {
            syncStudentCustomerTenant(audit, String.valueOf(account.getId()));
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void auditEnterprise(Map<String, Object> body) {
        Long id = requireLong(body, "id");
        Integer auditStatus = parseInteger(firstPresent(body, "auditStatus", "audit_status"), "auditStatus");
        String auditReason = toNullableString(firstPresent(body, "auditReason", "audit_reason"));
        if (AUDIT_STATUS_REJECTED == auditStatus && StrUtil.isBlank(auditReason)) {
            throw invalidParamException("驳回原因不能为空");
        }

        CompanyAuditInfoDO audit = findCompanyAuditById(id);
        if (audit == null) {
            throw invalidParamException("记录不存在：{}", id);
        }

        Long tenantId = audit.getTenantId();
        if (AUDIT_STATUS_APPROVED == auditStatus && (tenantId == null || tenantId <= 0)) {
            tenantId = createTenantForAudit(audit);
        }

        CompanyAuditInfoDO update = new CompanyAuditInfoDO();
        update.setId(id);
        update.setAuditStatus(auditStatus);
        update.setAuditReason(auditReason);
        update.setAuditTime(LocalDateTime.now());
        update.setAuditUserId(SecurityFrameworkUtils.getLoginUserId());
        update.setUpdater(currentUser());
        if (AUDIT_STATUS_APPROVED == auditStatus) {
            update.setTenantId(tenantId);
        }
        updateCompanyAudit(update);
        if (audit.getCompanyAccountFrontId() != null) {
            updateCompanyAccountAuditStatus(audit.getCompanyAccountFrontId(), auditStatus, currentUser());
        }

        if (AUDIT_STATUS_APPROVED == auditStatus && tenantId != null) {
            updateCompanyAuditAttachmentTenant(id, tenantId, currentUser());
            updateCompanyAccountByAudit(audit, tenantId);
        }
    }

    private void assertAuditCanEditOrSubmit(CompanyAuditInfoDO audit) {
        if (Integer.valueOf(AUDIT_STATUS_PENDING).equals(audit.getAuditStatus())) {
            throw invalidParamException("企业审核已提交，请勿重复提交");
        }
        if (Integer.valueOf(AUDIT_STATUS_APPROVED).equals(audit.getAuditStatus())) {
            throw invalidParamException("企业审核已通过，不能重复提交");
        }
        if (!Integer.valueOf(AUDIT_STATUS_DRAFT).equals(audit.getAuditStatus())
                && !Integer.valueOf(AUDIT_STATUS_REJECTED).equals(audit.getAuditStatus())) {
            throw invalidParamException("当前审核状态不允许重新提交");
        }
    }

    private void assertNoDuplicatePendingAudit(String contactMobile, String name, Long excludeId) {
        if (StrUtil.isBlank(contactMobile) || StrUtil.isBlank(name)) {
            return;
        }
        CompanyAuditInfoDO duplicate = findPendingCompanyAudit(contactMobile, name, excludeId);
        if (duplicate != null) {
            throw invalidParamException("相同手机号和企业名称的企业审核已提交，请勿重复提交");
        }
    }

    private void saveAttachments(Long auditId, Long companyAccountFrontId, Long userId,
                                 Iterable<AppCompanyAuditAttachmentReqVO> attachments) {
        if (attachments == null) {
            return;
        }
        for (AppCompanyAuditAttachmentReqVO attachmentReqVO : attachments) {
            CompanyAuditAttachmentDO attachment = CompanyAuditAttachmentDO.builder()
                    .companyId(auditId)
                    .userId(userId)
                    .companyAccountFrontId(companyAccountFrontId)
                    .filePath(StrUtil.trim(attachmentReqVO.getFilePath()))
                    .fileName(StrUtil.trim(attachmentReqVO.getFileName()))
                    .fileType(StrUtil.trim(attachmentReqVO.getFileType()))
                    .build();
            fillCreateValues(attachment, String.valueOf(companyAccountFrontId));
            insertCompanyAuditAttachment(attachment);
        }
    }

    private Long createTenantForAudit(CompanyAuditInfoDO audit) {
        TenantDO exists = tenantService.getTenantByName(audit.getName());
        if (exists != null) {
            return exists.getId();
        }

        TenantEnterpriseAuditCreateReqDTO reqDTO = new TenantEnterpriseAuditCreateReqDTO();
        reqDTO.setName(audit.getName());
        reqDTO.setContactName(StrUtil.blankToDefault(audit.getContactName(), audit.getName()));
        reqDTO.setContactMobile(audit.getContactMobile());
        reqDTO.setStatus(0);
        reqDTO.setWebsites(Collections.emptyList());
        return tenantService.createTenantByEnterpriseAudit(reqDTO);
    }

    private void updateCompanyAccountByAudit(CompanyAuditInfoDO audit, Long tenantId) {
        if (audit.getCompanyAccountFrontId() == null) {
            return;
        }
        CompanyAccountFrontDO update = new CompanyAccountFrontDO();
        update.setId(audit.getCompanyAccountFrontId());
        update.setTenantId(tenantId);
        update.setAuditStatus(AUDIT_STATUS_APPROVED);
        update.setUpdater(currentUser());
        updateCompanyAccount(update);
    }

    private AppCompanyStudentAuditRespVO toStudentAuditRespVO(StudentAuditInfoDO audit) {
        CustomerAccountDO account = audit.getCustomerAccountId() == null ? null
                : TenantUtils.executeIgnore(() -> customerAccountMapper.selectById(audit.getCustomerAccountId()));
        CustomerInfoDO info = audit.getCustomerAccountId() == null ? null
                : TenantUtils.executeIgnore(() -> customerInfoMapper.selectByCustomerAccountId(audit.getCustomerAccountId()));
        return AppCompanyStudentAuditRespVO.builder()
                .id(audit.getId())
                .tenantId(audit.getTenantId())
                .companyId(audit.getCompanyId())
                .customerAccountId(audit.getCustomerAccountId())
                .studentName(resolveStudentName(account, info))
                .studentPhone(resolveStudentPhone(account, info))
                .auditStatus(audit.getAuditStatus())
                .auditStatusText(getStudentAuditStatusText(audit.getAuditStatus()))
                .auditReason(audit.getAuditReason())
                .applyTime(audit.getCreateTime())
                .auditTime(audit.getAuditTime())
                .build();
    }

    private boolean matchesStudentKeyword(AppCompanyStudentAuditRespVO item, String keyword) {
        String value = StrUtil.trim(keyword);
        if (StrUtil.isBlank(value)) {
            return true;
        }
        return StrUtil.containsIgnoreCase(item.getStudentName(), value)
                || StrUtil.containsIgnoreCase(item.getStudentPhone(), value);
    }

    private String resolveStudentName(CustomerAccountDO account, CustomerInfoDO info) {
        if (info != null && StrUtil.isNotBlank(info.getRealName())) {
            return info.getRealName().trim();
        }
        if (info != null && StrUtil.isNotBlank(info.getNickName())) {
            return info.getNickName().trim();
        }
        if (account != null && StrUtil.isNotBlank(account.getUsername())) {
            return account.getUsername().trim();
        }
        if (account != null && StrUtil.isNotBlank(account.getMobile())) {
            return account.getMobile().trim();
        }
        return "飞行学员";
    }

    private String resolveStudentPhone(CustomerAccountDO account, CustomerInfoDO info) {
        String phone = info == null ? "" : StrUtil.blankToDefault(StrUtil.trim(info.getMobilePhone()), "");
        if (StrUtil.isBlank(phone) && account != null) {
            phone = StrUtil.blankToDefault(StrUtil.trim(account.getMobile()), StrUtil.trim(account.getUsername()));
        }
        return phone;
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

    private String normalizeStudentAuditReason(Integer auditStatus, String auditReason) {
        String normalized = StrUtil.trimToNull(auditReason);
        if (Integer.valueOf(AUDIT_STATUS_REJECTED).equals(auditStatus) && normalized == null) {
            return "企业端已拒绝";
        }
        return normalized;
    }

    private void syncStudentCustomerAuditStatus(StudentAuditInfoDO audit, Integer auditStatus, String operator) {
        if (audit.getCustomerAccountId() == null || auditStatus == null) {
            return;
        }
        CustomerAccountDO update = new CustomerAccountDO();
        update.setId(audit.getCustomerAccountId());
        update.setAuditStatus(auditStatus);
        update.setUpdater(operator);
        update.setUpdateTime(LocalDateTime.now());
        TenantUtils.executeIgnore(() -> customerAccountMapper.updateById(update));
    }

    private void syncStudentCustomerTenant(StudentAuditInfoDO audit, String operator) {
        Long tenantId = resolveStudentAuditCompanyTenantId(audit);
        if (tenantId == null || tenantId <= 0 || audit.getCustomerAccountId() == null) {
            return;
        }
        LocalDateTime now = LocalDateTime.now();

        CustomerAccountDO accountUpdate = new CustomerAccountDO();
        accountUpdate.setId(audit.getCustomerAccountId());
        accountUpdate.setTenantId(tenantId);
        accountUpdate.setAuditStatus(AUDIT_STATUS_APPROVED);
        accountUpdate.setUpdater(operator);
        accountUpdate.setUpdateTime(now);
        TenantUtils.executeIgnore(() -> customerAccountMapper.updateById(accountUpdate));

        CustomerInfoDO info = TenantUtils.executeIgnore(() ->
                customerInfoMapper.selectByCustomerAccountId(audit.getCustomerAccountId()));
        if (info == null) {
            return;
        }
        CustomerInfoDO infoUpdate = new CustomerInfoDO();
        infoUpdate.setId(info.getId());
        infoUpdate.setTenantId(tenantId);
        infoUpdate.setUpdater(operator);
        infoUpdate.setUpdateTime(now);
        TenantUtils.executeIgnore(() -> customerInfoMapper.updateById(infoUpdate));
    }

    private boolean isCurrentCompanyStudentAudit(StudentAuditInfoDO audit, Long tenantId) {
        if (audit == null || tenantId == null) {
            return false;
        }
        Long companyId = audit.getCompanyId();
        if (companyId != null && companyId > 0) {
            return tenantId.equals(companyId);
        }
        return tenantId.equals(audit.getTenantId());
    }

    private Long resolveStudentAuditCompanyTenantId(StudentAuditInfoDO audit) {
        if (audit == null) {
            return null;
        }
        Long companyId = audit.getCompanyId();
        return companyId != null && companyId > 0 ? companyId : audit.getTenantId();
    }

    private Long requireCompanyTenantId(CompanyAccountFrontDO account) {
        Long tenantId = getBoundTenantId(account);
        if (tenantId == null || tenantId <= 0) {
            throw invalidParamException("组织账号未绑定租户");
        }
        return tenantId;
    }

    private CurrentCompanyProfile resolveCurrentCompanyProfile(Long tenantId, String mobile) {
        if (tenantId == null || tenantId <= 0) {
            return CurrentCompanyProfile.empty();
        }
        String normalizedMobile = normalizeMobile(mobile);
        if (StrUtil.isBlank(normalizedMobile)) {
            return CurrentCompanyProfile.empty();
        }
        return TenantUtils.execute(tenantId, () -> {
            List<AdminUserDO> users = adminUserMapper.selectList(AdminUserDO::getMobile, normalizedMobile);
            if (users == null || users.size() != 1) {
                return CurrentCompanyProfile.empty();
            }
            AdminUserDO user = users.get(0);
            String nickname = StrUtil.trimToNull(user.getNickname());
            String deptName = null;
            if (user.getDeptId() != null && user.getDeptId() > 0) {
                DeptDO dept = deptMapper.selectById(user.getDeptId());
                deptName = dept == null ? null : StrUtil.trimToNull(dept.getName());
            }
            return new CurrentCompanyProfile(nickname, deptName);
        });
    }

    private CompanyAccountFrontDO getCurrentCompanyAccountRequired() {
        LoginUser loginUser = requireCompanyFrontLoginUser();
        return findActiveCompanyAccountById(loginUser.getId());
    }

    private CompanyAccountFrontDO findActiveCompanyAccountById(Long id) {
        CompanyAccountFrontDO account = TenantUtils.executeIgnore(() -> companyAccountFrontMapper.selectById(id));
        if (account == null || !Boolean.TRUE.equals(account.getStatus())) {
            throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), "组织账号不可用");
        }
        return account;
    }

    private OAuth2AccessTokenDO createCompanyToken(CompanyAccountFrontDO account) {
        Long tenantId = getBoundTenantId(account);
        if (tenantId == null) {
            return createCompanyAccessToken(account.getId());
        }
        return TenantUtils.execute(tenantId, () -> createCompanyAccessToken(account.getId()));
    }

    private OAuth2AccessTokenDO createCompanyAccessToken(Long accountId) {
        return oauth2TokenService.createAccessToken(accountId, UserTypeEnum.MEMBER.getValue(),
                OAuth2ClientConstants.CLIENT_ID_DEFAULT, Collections.singletonList(COMPANY_FRONT_SCOPE));
    }

    private LoginUser requireCompanyFrontLoginUser() {
        LoginUser loginUser = SecurityFrameworkUtils.getLoginUser();
        if (loginUser == null) {
            throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), "组织账号令牌不能为空");
        }
        if (!UserTypeEnum.MEMBER.getValue().equals(loginUser.getUserType())
                || loginUser.getScopes() == null
                || !loginUser.getScopes().contains(COMPANY_FRONT_SCOPE)) {
            throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), "组织账号令牌类型不正确");
        }
        return loginUser;
    }

    private void assertCompanyFrontAccessToken(OAuth2AccessTokenDO accessToken) {
        if (accessToken == null
                || !UserTypeEnum.MEMBER.getValue().equals(accessToken.getUserType())
                || accessToken.getScopes() == null
                || !accessToken.getScopes().contains(COMPANY_FRONT_SCOPE)) {
            throw exception0(GlobalErrorCodeConstants.UNAUTHORIZED.getCode(), "组织账号令牌类型不正确");
        }
    }

    private boolean isTenantMismatch(CompanyAccountFrontDO account, OAuth2AccessTokenDO accessToken) {
        Long tenantId = getBoundTenantId(account);
        return tenantId != null && !tenantId.equals(accessToken.getTenantId());
    }

    private AppCompanyAuthLoginRespVO buildLoginResponse(CompanyAccountFrontDO account, OAuth2AccessTokenDO accessToken) {
        TenantDO tenant = getAccountTenant(account);
        return AppCompanyAuthLoginRespVO.builder()
                .companyAccountFrontId(account.getId())
                .tenantId(account.getTenantId())
                .tenantName(tenant != null ? tenant.getName() : null)
                .tenantContactName(tenant != null ? tenant.getContactName() : null)
                .tenantContactMobile(tenant != null ? tenant.getContactMobile() : null)
                .username(account.getUsername())
                .status(account.getStatus())
                .auditStatus(account.getAuditStatus())
                .accessToken(accessToken.getAccessToken())
                .refreshToken(accessToken.getRefreshToken())
                .expiresTime(accessToken.getExpiresTime())
                .build();
    }

    private TenantDO getAccountTenant(CompanyAccountFrontDO account) {
        Long tenantId = getBoundTenantId(account);
        if (tenantId == null || tenantId <= 0) {
            return null;
        }
        return tenantService.getTenant(tenantId);
    }

    private AppCompanyAuthPostCodesRespVO buildPostCodesResponse(boolean userMatched, List<String> postCodes, Long tenantId) {
        boolean hasWtPost = postCodes.stream()
                .anyMatch(code -> StrUtil.containsIgnoreCase(code, "WT"));
        return AppCompanyAuthPostCodesRespVO.builder()
                .userMatched(userMatched)
                .postCodes(postCodes)
                .hasWtPost(hasWtPost)
                .tenantId(tenantId)
                .build();
    }

    private Long getBoundTenantId(CompanyAccountFrontDO account) {
        if (account == null) {
            return null;
        }
        Long tenantId = account.getTenantId();
        return tenantId == null || tenantId <= 0 ? null : tenantId;
    }

    private void bindCurrentCompanyAccountTenantIfAbsent(Long companyAccountFrontId, String mobile, Long tenantId) {
        if (companyAccountFrontId == null || companyAccountFrontId <= 0 || tenantId == null || tenantId <= 0) {
            return;
        }
        CompanyAccountFrontDO account = findActiveCompanyAccountById(companyAccountFrontId);
        if (getBoundTenantId(account) != null) {
            if (!Integer.valueOf(AUDIT_STATUS_APPROVED).equals(account.getAuditStatus())) {
                updateCompanyAccountAuditStatus(account.getId(), AUDIT_STATUS_APPROVED, String.valueOf(account.getId()));
            }
            return;
        }
        if (!StrUtil.equals(normalizeMobile(account.getUsername()), mobile)) {
            return;
        }
        CompanyAccountFrontDO update = new CompanyAccountFrontDO();
        update.setId(account.getId());
        update.setTenantId(tenantId);
        update.setAuditStatus(AUDIT_STATUS_APPROVED);
        update.setUpdater(String.valueOf(account.getId()));
        update.setUpdateTime(LocalDateTime.now());
        updateCompanyAccount(update);
    }

    private void fillCreateValues(CompanyAccountFrontDO account, String user) {
        LocalDateTime now = LocalDateTime.now();
        account.setCreator(user);
        account.setCreateTime(now);
        account.setUpdater(user);
        account.setUpdateTime(now);
        account.setDeleted(false);
        account.setTenantId(null);
    }

    private void fillCreateValues(CompanyAuditInfoDO audit, String user) {
        LocalDateTime now = LocalDateTime.now();
        audit.setCreator(user);
        audit.setCreateTime(now);
        audit.setUpdater(user);
        audit.setUpdateTime(now);
        audit.setDeleted(false);
        audit.setTenantId(null);
    }

    private void fillCreateValues(CompanyAuditAttachmentDO attachment, String user) {
        LocalDateTime now = LocalDateTime.now();
        attachment.setCreator(user);
        attachment.setCreateTime(now);
        attachment.setUpdater(user);
        attachment.setUpdateTime(now);
        attachment.setDeleted(false);
        attachment.setTenantId(null);
    }

    private CompanyAccountFrontDO findCompanyAccountByUsername(String username) {
        return TenantUtils.executeIgnore(() -> companyAccountFrontMapper.selectByUsername(username));
    }

    private void insertCompanyAccount(CompanyAccountFrontDO account) {
        TenantUtils.executeIgnore(() -> companyAccountFrontMapper.insert(account));
    }

    private void updateCompanyAccount(CompanyAccountFrontDO account) {
        TenantUtils.executeIgnore(() -> companyAccountFrontMapper.updateById(account));
    }

    private void updateCompanyAccountAuditStatus(Long companyAccountFrontId, Integer auditStatus, String updater) {
        CompanyAccountFrontDO update = new CompanyAccountFrontDO();
        update.setId(companyAccountFrontId);
        update.setAuditStatus(auditStatus);
        update.setUpdater(updater);
        update.setUpdateTime(LocalDateTime.now());
        updateCompanyAccount(update);
    }

    private CompanyAuditInfoDO findCompanyAuditById(Long id) {
        return TenantUtils.executeIgnore(() -> companyAuditInfoMapper.selectById(id));
    }

    private CompanyAuditInfoDO findLatestCompanyAudit(Long companyAccountFrontId) {
        return TenantUtils.executeIgnore(() ->
                companyAuditInfoMapper.selectLatestByCompanyAccountFrontId(companyAccountFrontId));
    }

    private CompanyAuditInfoDO findPendingCompanyAudit(String contactMobile, String name, Long excludeId) {
        return TenantUtils.executeIgnore(() ->
                companyAuditInfoMapper.selectPendingByContactMobileAndName(contactMobile, name, excludeId));
    }

    private void insertCompanyAudit(CompanyAuditInfoDO audit) {
        TenantUtils.executeIgnore(() -> companyAuditInfoMapper.insert(audit));
    }

    private void updateCompanyAudit(CompanyAuditInfoDO audit) {
        TenantUtils.executeIgnore(() -> companyAuditInfoMapper.updateById(audit));
    }

    private void insertCompanyAuditAttachment(CompanyAuditAttachmentDO attachment) {
        TenantUtils.executeIgnore(() -> companyAuditAttachmentMapper.insert(attachment));
    }

    private void deleteCompanyAuditAttachments(Long auditId) {
        TenantUtils.executeIgnore(() -> companyAuditAttachmentMapper.deleteByCompanyId(auditId));
    }

    private void updateCompanyAuditAttachmentTenant(Long auditId, Long tenantId, String updater) {
        TenantUtils.executeIgnore(() -> companyAuditAttachmentMapper.updateTenantIdByCompanyId(auditId, tenantId, updater));
    }

    private String normalizeMobile(String mobile) {
        return mobile == null ? "" : mobile.trim();
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
        if (value == null) {
            throw invalidParamException("{} 不能为空", key);
        }
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

    private static final class CurrentCompanyProfile {

        private final String nickname;
        private final String deptName;

        private CurrentCompanyProfile(String nickname, String deptName) {
            this.nickname = nickname;
            this.deptName = deptName;
        }

        private static CurrentCompanyProfile empty() {
            return new CurrentCompanyProfile(null, null);
        }

        private String getNickname() {
            return nickname;
        }

        private String getDeptName() {
            return deptName;
        }
    }
}
