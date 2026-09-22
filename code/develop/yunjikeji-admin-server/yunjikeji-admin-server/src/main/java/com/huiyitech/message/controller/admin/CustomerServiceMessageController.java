package com.huiyitech.message.controller.admin;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.app.message.service.CustomerMessageService;
import com.huiyitech.utils.BaiduBosUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Customer Service Message")
@RestController
@RequestMapping("/yj/customer-message")
@Validated
public class CustomerServiceMessageController {

    @Resource
    private CustomerMessageService customerMessageService;
    @Resource
    private BaiduBosUtil baiduBosUtil;

    @GetMapping("/page")
    @Operation(summary = "Get customer-service message page")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@RequestParam Map<String, String> params) {
        return success(customerMessageService.getMessagePage(params));
    }

    @GetMapping("/get")
    @Operation(summary = "Get customer-service message detail")
    public CommonResult<Map<String, Object>> get(@RequestParam("id") Long id) {
        return success(customerMessageService.getMessage(id));
    }

    @PostMapping("/send")
    @Operation(summary = "Send customer-service message")
    public CommonResult<Long> send(@RequestBody Map<String, Object> body) {
        return success(customerMessageService.sendAdminMessage(body));
    }

    @PostMapping("/upload-media")
    @Operation(summary = "Upload customer-service media to BOS")
    public CommonResult<BaiduBosUtil.BosUploadResult> uploadMedia(@RequestParam("file") MultipartFile file,
                                                                  @RequestParam(value = "messageType", required = false) String messageType) {
        return success(baiduBosUtil.upload(file, "customer-service/" + normalizeMediaType(messageType)));
    }

    private String normalizeMediaType(String messageType) {
        if ("video".equals(messageType)) {
            return "video";
        }
        return "image";
    }
}
