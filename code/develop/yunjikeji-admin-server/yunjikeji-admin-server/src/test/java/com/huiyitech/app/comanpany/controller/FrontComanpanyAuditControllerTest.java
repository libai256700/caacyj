package com.huiyitech.app.comanpany.controller;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.security.config.SecurityProperties;
import com.huiyitech.companyaudit.controller.vo.AppCompanyAuthMeRespVO;
import com.huiyitech.companyaudit.service.CompanyAuditService;
import com.huiyitech.utils.BaiduBosUtil;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class FrontComanpanyAuditControllerTest {

    private CompanyAuditService companyAuditService;
    private BaiduBosUtil baiduBosUtil;
    private FrontComanpanyAuditController controller;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        companyAuditService = mock(CompanyAuditService.class);
        baiduBosUtil = mock(BaiduBosUtil.class);

        controller = new FrontComanpanyAuditController();
        ReflectionTestUtils.setField(controller, "companyAuditService", companyAuditService);
        ReflectionTestUtils.setField(controller, "securityProperties", new SecurityProperties());
        ReflectionTestUtils.setField(controller, "baiduBosUtil", baiduBosUtil);

        mockMvc = MockMvcBuilders.standaloneSetup(controller).build();
    }

    @Test
    void uploadEnterpriseLicense_shouldReturnBosUrl() throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", "license.jpg", MediaType.IMAGE_JPEG_VALUE, new byte[]{1});
        when(baiduBosUtil.upload(org.mockito.ArgumentMatchers.any(), eq("enterprise/license")))
                .thenReturn(BaiduBosUtil.BosUploadResult.builder()
                        .url("https://yunjikeji.bj.bcebos.com/yunjikeji/enterprise/license/license.jpg")
                        .build());

        mockMvc.perform(multipart("/app-api/yj/enterprise-audit/license/upload").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data").value("https://yunjikeji.bj.bcebos.com/yunjikeji/enterprise/license/license.jpg"));

        verify(baiduBosUtil).upload(org.mockito.ArgumentMatchers.any(), eq("enterprise/license"));
    }

    @Test
    void uploadEnterpriseLicense_shouldMaskBosConfigurationErrors() throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", "license.jpg", MediaType.IMAGE_JPEG_VALUE, new byte[]{1});
        when(baiduBosUtil.upload(org.mockito.ArgumentMatchers.any(), eq("enterprise/license")))
                .thenThrow(ServiceExceptionUtil.invalidParamException("BOS upload configuration is incomplete"));

        ServiceException ex = assertThrows(ServiceException.class, () -> controller.uploadEnterpriseLicense(file));
        assertEquals("百度 BOS 未配置，暂时无法上传营业执照，请联系管理员配置 BAIDU_BOS_ENABLED、BAIDU_BOS_ACCESS_KEY_ID、BAIDU_BOS_SECRET_ACCESS_KEY、BAIDU_BOS_ENDPOINT、BAIDU_BOS_BUCKET_NAME", ex.getMessage());
    }

    @Test
    void me_shouldExposeNicknameAndDeptNameInJson() throws Exception {
        when(companyAuditService.getCurrentCompanyAccount()).thenReturn(AppCompanyAuthMeRespVO.builder()
                .companyAccountFrontId(9527L)
                .tenantId(2001L)
                .tenantName("飞行学院")
                .username("13986119652")
                .nickname("教员1")
                .deptName("教学部")
                .status(true)
                .auditStatus(2)
                .build());

        mockMvc.perform(get("/app-api/yj/company-auth/me"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.username").value("13986119652"))
                .andExpect(jsonPath("$.data.nickname").value("教员1"))
                .andExpect(jsonPath("$.data.deptName").value("教学部"));
    }
}
