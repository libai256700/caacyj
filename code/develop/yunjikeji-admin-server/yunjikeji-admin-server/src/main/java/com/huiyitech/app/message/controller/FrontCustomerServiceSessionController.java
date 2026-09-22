package com.huiyitech.app.message.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.app.message.controller.vo.AppCompanyStudentConversationRespVO;
import com.huiyitech.app.message.controller.vo.AppCompanyStudentConversationStartReqVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceMessageRespVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceSendReqVO;
import com.huiyitech.app.message.controller.vo.AppCustomerServiceSessionRespVO;
import com.huiyitech.app.message.service.CustomerMessageService;
import com.huiyitech.utils.BaiduBosUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.util.List;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "APP - Customer Service Message")
@RestController
@Validated
@TenantIgnore
@RequestMapping("/app-api")
public class FrontCustomerServiceSessionController {

    @Resource
    private CustomerMessageService customerMessageService;
    @Resource
    private BaiduBosUtil baiduBosUtil;

    @GetMapping("/yj/customer-service/session")
    @Operation(summary = "Get or create current student customer-service session")
    public CommonResult<AppCustomerServiceSessionRespVO> getOrCreateSession() {
        return success(customerMessageService.getOrCreateCurrentSession());
    }

    @GetMapping("/yj/customer-service/messages")
    @Operation(summary = "Get current student customer-service messages")
    public CommonResult<List<AppCustomerServiceMessageRespVO>> getMessages(
            @RequestParam(value = "pageNo", defaultValue = "1") Integer pageNo,
            @RequestParam(value = "pageSize", defaultValue = "100") Integer pageSize) {
        return success(customerMessageService.getCurrentMessages(pageNo, pageSize));
    }

    @PostMapping("/yj/customer-service/messages")
    @Operation(summary = "Send current student customer-service message")
    public CommonResult<AppCustomerServiceMessageRespVO> sendText(@RequestBody @Valid AppCustomerServiceSendReqVO reqVO) {
        return success(customerMessageService.sendCurrentStudentMessage(reqVO.getMessageType(), reqVO.getContent()));
    }

    @PostMapping("/yj/customer-service/media")
    @Operation(summary = "Upload current student customer-service media to BOS")
    public CommonResult<BaiduBosUtil.BosUploadResult> uploadMedia(@RequestParam("file") MultipartFile file,
                                                                  @RequestParam(value = "messageType", required = false) String messageType) {
        return success(baiduBosUtil.upload(file, "customer-service/" + normalizeMediaType(messageType)));
    }

    @PostMapping("/yj/customer-service/messages/media")
    @Operation(summary = "Send current student customer-service media message")
    public CommonResult<AppCustomerServiceMessageRespVO> sendMedia(
            @RequestParam("messageType") String messageType,
            @RequestPart("file") MultipartFile file) {
        return success(customerMessageService.sendCurrentStudentMedia(messageType, file));
    }

    @GetMapping("/yj/company-students")
    @Operation(summary = "Get approved students available to enterprise customer service")
    public CommonResult<List<AppCompanyStudentConversationRespVO>> getCompanyStudents(
            @RequestParam(value = "pageNo", defaultValue = "1") Integer pageNo,
            @RequestParam(value = "pageSize", defaultValue = "100") Integer pageSize) {
        return success(customerMessageService.getCurrentCompanyStudentConversations(pageNo, pageSize));
    }

    @PostMapping("/yj/company-students/conversations/start")
    @Operation(summary = "Start or reuse a customer-service conversation for an approved student")
    public CommonResult<AppCompanyStudentConversationRespVO> startCompanyStudentConversation(
            @RequestBody @Valid AppCompanyStudentConversationStartReqVO reqVO) {
        return success(customerMessageService.startCurrentCompanyStudentConversation(reqVO.getStudentId()));
    }

    @GetMapping("/yj/company-students/messages")
    @Operation(summary = "Get selected student customer-service messages")
    public CommonResult<List<AppCustomerServiceMessageRespVO>> getCompanyStudentMessages(
            @RequestParam("studentId") Long studentId,
            @RequestParam("conversationId") Long conversationId,
            @RequestParam(value = "pageNo", defaultValue = "1") Integer pageNo,
            @RequestParam(value = "pageSize", defaultValue = "100") Integer pageSize) {
        return success(customerMessageService.getCurrentCompanyStudentMessages(studentId, conversationId,
                pageNo, pageSize));
    }

    @PostMapping("/yj/company-students/messages/send")
    @Operation(summary = "Send selected student customer-service message")
    public CommonResult<AppCustomerServiceMessageRespVO> sendCompanyStudentText(
            @RequestBody @Valid AppCustomerServiceSendReqVO reqVO) {
        return success(customerMessageService.sendCurrentCompanyStudentMessage(reqVO.getStudentId(),
                reqVO.getConversationId(), reqVO.getMessageType(), reqVO.getContent()));
    }

    private String normalizeMediaType(String messageType) {
        if ("video".equals(messageType)) {
            return "video";
        }
        return "image";
    }

    @PostMapping("/yj/company-students/messages/media")
    @Operation(summary = "Send selected student customer-service media message")
    public CommonResult<AppCustomerServiceMessageRespVO> sendCompanyStudentMedia(
            @RequestParam("studentId") Long studentId,
            @RequestParam("conversationId") Long conversationId,
            @RequestParam("messageType") String messageType,
            @RequestPart("file") MultipartFile file) {
        return success(customerMessageService.sendCurrentCompanyStudentMedia(studentId, conversationId,
                messageType, file));
    }
}
