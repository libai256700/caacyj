package com.huiyitech.postcollect.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageParam;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostCollectionRunDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentItemDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.FeishuPostCollectionRunMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.FeishuPostDocumentItemMapper;
import com.huiyitech.postcollect.dal.mysql.postcollect.FeishuPostDocumentMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.List;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - Feishu Post Collection Audit")
@RestController
@RequestMapping("/admin-api/postcollect/feishu-audit")
public class FeishuPostCollectionAuditController {

    private static final String DOCUMENT_DATE_ORDER =
            "STR_TO_DATE(SUBSTRING_INDEX(SUBSTRING_INDEX(document_name, '(', -1), ')', 1), '%Y-%m-%d')";

    @Resource
    private FeishuPostCollectionRunMapper runMapper;
    @Resource
    private FeishuPostDocumentMapper documentMapper;
    @Resource
    private FeishuPostDocumentItemMapper itemMapper;

    @GetMapping("/runs")
    @Operation(summary = "List Feishu collection runs")
    public CommonResult<List<FeishuPostCollectionRunDO>> getRuns(
            @RequestParam(value = "folderToken", required = false) String folderToken) {
        LambdaQueryWrapper<FeishuPostCollectionRunDO> wrapper = new LambdaQueryWrapper<FeishuPostCollectionRunDO>()
                .eq(FeishuPostCollectionRunDO::getDeleted, Boolean.FALSE)
                .orderByDesc(FeishuPostCollectionRunDO::getId);
        if (org.springframework.util.StringUtils.hasText(folderToken)) {
            wrapper.eq(FeishuPostCollectionRunDO::getFolderToken, folderToken);
        }
        return success(runMapper.selectList(wrapper));
    }

    @GetMapping("/run")
    @Operation(summary = "Get Feishu collection run")
    public CommonResult<FeishuPostCollectionRunDO> getRun(@RequestParam("id") Long id) {
        return success(runMapper.selectById(id));
    }

    @GetMapping("/documents")
    @Operation(summary = "List Feishu collection documents")
    public CommonResult<List<FeishuPostDocumentDO>> getDocuments(@RequestParam("runId") Long runId) {
        return success(documentMapper.selectList(new LambdaQueryWrapper<FeishuPostDocumentDO>()
                .eq(FeishuPostDocumentDO::getLastRunId, runId)
                .eq(FeishuPostDocumentDO::getDeleted, Boolean.FALSE)
                .orderByAsc(FeishuPostDocumentDO::getId)));
    }

    @GetMapping("/documents/page")
    @Operation(summary = "Page Feishu collection document overview")
    public CommonResult<PageResult<FeishuPostDocumentDO>> getDocumentPage(
            @RequestParam(value = "folderToken", required = false) String folderToken,
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "keyword", required = false) String keyword,
            PageParam pageParam) {
        QueryWrapper<FeishuPostDocumentDO> wrapper = new QueryWrapper<FeishuPostDocumentDO>()
                .eq("deleted", Boolean.FALSE)
                .orderByDesc(DOCUMENT_DATE_ORDER)
                .orderByDesc("update_time")
                .orderByDesc("id");
        if (org.springframework.util.StringUtils.hasText(folderToken)) {
            wrapper.eq("folder_token", folderToken.trim());
        }
        if (org.springframework.util.StringUtils.hasText(status)) {
            wrapper.eq("status", status.trim());
        }
        if (org.springframework.util.StringUtils.hasText(keyword)) {
            String value = keyword.trim();
            wrapper.and(query -> query.like("document_name", value)
                    .or().like("document_url", value));
        }
        return success(documentMapper.selectPage(pageParam, wrapper));
    }

    @GetMapping("/document")
    @Operation(summary = "Get Feishu collection document overview")
    public CommonResult<FeishuPostDocumentDO> getDocument(@RequestParam("id") Long id) {
        return success(documentMapper.selectById(id));
    }

    @GetMapping("/items")
    @Operation(summary = "List Feishu parsed post items")
    public CommonResult<List<FeishuPostDocumentItemDO>> getItems(
            @RequestParam(value = "runId", required = false) Long runId,
            @RequestParam(value = "documentId", required = false) Long documentId) {
        LambdaQueryWrapper<FeishuPostDocumentItemDO> wrapper = new LambdaQueryWrapper<FeishuPostDocumentItemDO>()
                .eq(FeishuPostDocumentItemDO::getDeleted, Boolean.FALSE)
                .orderByAsc(FeishuPostDocumentItemDO::getId);
        if (runId != null) {
            wrapper.eq(FeishuPostDocumentItemDO::getRunId, runId);
        }
        if (documentId != null) {
            wrapper.eq(FeishuPostDocumentItemDO::getDocumentId, documentId);
        }
        return success(itemMapper.selectList(wrapper));
    }
}
