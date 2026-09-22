package com.huiyitech.app.post.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.huiyitech.app.post.controller.vo.AppPostPageReqVO;
import com.huiyitech.app.post.controller.vo.AppPostRespVO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
@TenantIgnore
public class FrontPostServiceImpl implements FrontPostService {

    @Resource
    private PostCollectMapper postCollectMapper;

    @Override
    public PageResult<AppPostRespVO> getPostPage(AppPostPageReqVO reqVO) {
        LambdaQueryWrapperX<PostCollectDO> wrapper = new LambdaQueryWrapperX<PostCollectDO>()
                .eq(PostCollectDO::getStatus, reqVO.getStatus() == null ? Boolean.TRUE : reqVO.getStatus())
                .eqIfPresent(PostCollectDO::getSourceCode, reqVO.getSourceCode())
                .orderByDesc(PostCollectDO::getId);
        appendKeyword(wrapper, reqVO.getKeyword());
        if (shouldUseInMemoryFiltering(reqVO)) {
            List<PostCollectDO> filteredPosts = PostFilterSupport.filterPosts(postCollectMapper.selectList(wrapper),
                    reqVO.getName(), reqVO.getWorkArea(), reqVO.getSalaryRange());
            List<AppPostRespVO> pageList = paginate(filteredPosts, reqVO).stream()
                    .map(this::toRespVO)
                    .collect(Collectors.toList());
            return new PageResult<>(pageList, (long) filteredPosts.size());
        }

        wrapper.likeIfPresent(PostCollectDO::getName, reqVO.getName())
                .likeIfPresent(PostCollectDO::getWorkArea, reqVO.getWorkArea());

        PageResult<PostCollectDO> page = postCollectMapper.selectPage(reqVO, wrapper);
        List<AppPostRespVO> list = page.getList().stream()
                .map(this::toRespVO)
                .collect(Collectors.toList());
        return new PageResult<>(list, page.getTotal());
    }

    @Override
    public AppPostRespVO getPost(Long id) {
        PostCollectDO post = postCollectMapper.selectById(id);
        if (post == null || !Boolean.TRUE.equals(post.getStatus())) {
            throw invalidParamException("Post does not exist: {}", id);
        }
        return toRespVO(post);
    }

    private void appendKeyword(LambdaQueryWrapperX<PostCollectDO> wrapper, String keyword) {
        if (!StringUtils.hasText(keyword)) {
            return;
        }
        wrapper.and(query -> query.like(PostCollectDO::getName, keyword)
                .or().like(PostCollectDO::getCompanyName, keyword)
                .or().like(PostCollectDO::getSalaryRange, keyword)
                .or().like(PostCollectDO::getWorkArea, keyword));
    }

    private boolean shouldUseInMemoryFiltering(AppPostPageReqVO reqVO) {
        return StringUtils.hasText(reqVO.getName())
                || StringUtils.hasText(reqVO.getWorkArea())
                || StringUtils.hasText(reqVO.getSalaryRange());
    }

    private List<PostCollectDO> paginate(List<PostCollectDO> posts, AppPostPageReqVO reqVO) {
        if (posts.isEmpty()) {
            return Collections.emptyList();
        }
        int pageSize = reqVO.getPageSize();
        int fromIndex = Math.max((reqVO.getPageNo() - 1) * pageSize, 0);
        if (fromIndex >= posts.size()) {
            return Collections.emptyList();
        }
        int toIndex = Math.min(fromIndex + pageSize, posts.size());
        return posts.subList(fromIndex, toIndex);
    }

    private AppPostRespVO toRespVO(PostCollectDO post) {
        return AppPostRespVO.builder()
                .id(post.getId())
                .name(post.getName())
                .companyName(post.getCompanyName())
                .sourceCode(post.getSourceCode())
                .externalPostId(post.getExternalPostId())
                .salaryRange(post.getSalaryRange())
                .workArea(post.getWorkArea())
                .publishDate(post.getPublishDate())
                .detailUrl(post.getDetailUrl())
                .status(post.getStatus())
                .createTime(post.getCreateTime())
                .build();
    }
}
