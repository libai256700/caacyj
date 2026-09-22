package com.huiyitech.knowledge.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import com.huiyitech.knowledge.controller.vo.KnowledgeQueryReqVO;
import com.huiyitech.knowledge.controller.vo.KnowledgeQueryRespVO;
import com.huiyitech.knowledge.service.KnowledgeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import javax.validation.Valid;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "Admin - 知识库问答")
@RestController
@RequestMapping("/admin-api/yj/knowledge")
@Validated
public class KnowledgeController {

    @Resource
    private KnowledgeService knowledgeService;

    @GetMapping("/query")
    @Operation(summary = "查询知识库并返回大模型整理后的结果")
    public CommonResult<KnowledgeQueryRespVO> query(@RequestParam("question") String question) {
        return success(knowledgeService.query(question));
    }

    @PostMapping("/query")
    @Operation(summary = "查询知识库并返回大模型整理后的结果")
    public CommonResult<KnowledgeQueryRespVO> query(@Valid @RequestBody KnowledgeQueryReqVO reqVO) {
        return success(knowledgeService.query(reqVO.getQuestion()));
    }
}
