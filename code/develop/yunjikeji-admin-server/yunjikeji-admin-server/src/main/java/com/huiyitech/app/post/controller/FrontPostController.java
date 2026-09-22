package com.huiyitech.app.post.controller;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.app.post.controller.vo.AppPostPageReqVO;
import com.huiyitech.app.post.controller.vo.AppPostRespVO;
import com.huiyitech.app.post.service.FrontPostService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import javax.validation.Valid;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "APP posts")
@RestController
@Validated
@TenantIgnore
public class FrontPostController {

    @Resource
    private FrontPostService frontPostService;

    @GetMapping("/app-api/yj/posts")
    @Operation(summary = "APP get post page")
    public CommonResult<PageResult<AppPostRespVO>> getPostPage(@Valid AppPostPageReqVO reqVO) {
        return success(frontPostService.getPostPage(reqVO));
    }

    @GetMapping("/app-api/yj/posts/{id}")
    @Operation(summary = "APP get post detail")
    @Parameter(name = "id", description = "Post id", required = true)
    public CommonResult<AppPostRespVO> getPost(@PathVariable("id") Long id) {
        return success(frontPostService.getPost(id));
    }
}
