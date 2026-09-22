package com.huiyitech.app.post.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.huiyitech.app.post.controller.vo.AppPostPageReqVO;
import com.huiyitech.app.post.controller.vo.AppPostRespVO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectMapper;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Collections;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FrontPostServiceImplTest {

    private final PostCollectMapper postCollectMapper = mock(PostCollectMapper.class);
    private final FrontPostServiceImpl service = createService();

    @Test
    void getPostPageShouldReuseDatabasePagingWhenNoExtendedFiltersSelected() {
        AppPostPageReqVO reqVO = new AppPostPageReqVO();
        reqVO.setPageNo(1);
        reqVO.setPageSize(10);
        reqVO.setStatus(true);

        when(postCollectMapper.selectPage(any(AppPostPageReqVO.class), any()))
                .thenReturn(new PageResult<>(Collections.singletonList(buildPost(1L, "飞手教练", "武汉", "8-12K")), 1L));

        PageResult<AppPostRespVO> page = service.getPostPage(reqVO);

        assertEquals(1L, page.getTotal());
        assertEquals(1, page.getList().size());
        assertEquals("飞手教练", page.getList().get(0).getName());
        verify(postCollectMapper).selectPage(any(AppPostPageReqVO.class), any());
        verify(postCollectMapper, never()).selectList(any());
    }

    @Test
    void getPostPageShouldApplyNameProvinceSalaryFiltersAndPaginateAfterFiltering() {
        AppPostPageReqVO reqVO = new AppPostPageReqVO();
        reqVO.setPageNo(2);
        reqVO.setPageSize(1);
        reqVO.setStatus(true);
        reqVO.setName("飞手");
        reqVO.setWorkArea("湖北省");
        reqVO.setSalaryRange("5000-10000");

        when(postCollectMapper.selectList(any())).thenReturn(Arrays.asList(
                buildPost(10L, "飞手学员", "武汉市洪山区", "8-12K"),
                buildPost(9L, "飞手讲师", "武汉", "7000-14000"),
                buildPost(8L, "飞手讲师", "西安", "7000-14000"),
                buildPost(7L, "教练", "武汉", "5000-7000"),
                buildPost(6L, "飞手讲师", "武汉", "面议")
        ));

        PageResult<AppPostRespVO> page = service.getPostPage(reqVO);

        assertEquals(2L, page.getTotal());
        assertEquals(1, page.getList().size());
        assertEquals(9L, page.getList().get(0).getId());
        assertEquals("飞手讲师", page.getList().get(0).getName());
        verify(postCollectMapper).selectList(any());
        verify(postCollectMapper, never()).selectPage(any(AppPostPageReqVO.class), any());
    }

    @Test
    void getPostPageShouldApplyOtherKeywordExclusionAndTreatNullNamesAsOther() {
        AppPostPageReqVO reqVO = new AppPostPageReqVO();
        reqVO.setPageNo(1);
        reqVO.setPageSize(10);
        reqVO.setStatus(true);
        reqVO.setName("__other__");

        when(postCollectMapper.selectList(any())).thenReturn(Arrays.asList(
                buildPost(10L, null, "武汉", "8-12K"),
                buildPost(9L, "飞手讲师", "武汉", "7000-14000"),
                buildPost(8L, "工程师", "武汉", "5000-7000"),
                buildPost(7L, "教培老师", "武汉", "面议"),
                buildPost(6L, "综合岗位", "武汉", "5000-7000")
        ));

        PageResult<AppPostRespVO> page = service.getPostPage(reqVO);

        assertEquals(2L, page.getTotal());
        assertEquals(2, page.getList().size());
        assertNull(page.getList().get(0).getName());
        assertEquals("综合岗位", page.getList().get(1).getName());
        verify(postCollectMapper).selectList(any());
        verify(postCollectMapper, never()).selectPage(any(AppPostPageReqVO.class), any());
    }

    @Test
    void workAreaShouldSupportProvinceAliasesForCurrentSamples() {
        assertTrue(PostFilterSupport.matchesWorkArea("武汉市洪山区", "湖北省"));
        assertTrue(PostFilterSupport.matchesWorkArea("西安", "陕西省"));
    }

    @Test
    void salaryRangeShouldSupportCommonFormatsAndBoundaries() {
        assertTrue(PostFilterSupport.matchesSalaryRange("8-12K", "10000-30000"));
        assertTrue(PostFilterSupport.matchesSalaryRange("7000-14000", "5000-10000"));
        assertTrue(PostFilterSupport.matchesSalaryRange("5000-10000", "3000-5000"));
        assertTrue(PostFilterSupport.matchesSalaryRange("9000-9500元/月", "5000-10000"));
        assertTrue(PostFilterSupport.matchesSalaryRange("5-20K", "10000-30000"));
        assertTrue(PostFilterSupport.matchesSalaryRange("0.8-1.2万/月", "10000-30000"));
    }

    @Test
    void salaryRangeShouldExcludeUnparseableValuesWhenFilterSelected() {
        assertFalse(PostFilterSupport.matchesSalaryRange("面议", "0-3000"));
        assertFalse(PostFilterSupport.matchesSalaryRange("", "5000-10000"));
    }

    @Test
    void keywordFilterShouldSupportOtherSentinelAndWhitespaceNormalization() {
        assertTrue(PostFilterSupport.matchesName("  飞手讲师  ", "飞手"));
        assertTrue(PostFilterSupport.matchesName("工程师", "工程师"));
        assertTrue(PostFilterSupport.matchesName(null, "__other__"));
        assertTrue(PostFilterSupport.matchesName("   ", "__other__"));
        assertTrue(PostFilterSupport.matchesName("综合岗位", "__other__"));
        assertFalse(PostFilterSupport.matchesName("飞手讲师", "__other__"));
        assertFalse(PostFilterSupport.matchesName("工程师", "__other__"));
        assertFalse(PostFilterSupport.matchesName("教培老师", "__other__"));
    }

    private FrontPostServiceImpl createService() {
        FrontPostServiceImpl target = new FrontPostServiceImpl();
        injectField(target, "postCollectMapper", postCollectMapper);
        return target;
    }

    private void injectField(Object target, String fieldName, Object value) {
        try {
            Field field = target.getClass().getDeclaredField(fieldName);
            field.setAccessible(true);
            field.set(target, value);
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private PostCollectDO buildPost(Long id, String name, String workArea, String salaryRange) {
        return PostCollectDO.builder()
                .id(id)
                .name(name)
                .companyName("测试公司")
                .workArea(workArea)
                .salaryRange(salaryRange)
                .status(true)
                .build();
    }
}
