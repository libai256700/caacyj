package com.huiyitech.app.post.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.app.post.controller.vo.AppPostPageReqVO;
import com.huiyitech.app.post.controller.vo.AppPostRespVO;

public interface FrontPostService {

    PageResult<AppPostRespVO> getPostPage(AppPostPageReqVO reqVO);

    AppPostRespVO getPost(Long id);
}
