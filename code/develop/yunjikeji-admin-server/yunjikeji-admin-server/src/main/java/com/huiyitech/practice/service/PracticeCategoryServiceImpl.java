package com.huiyitech.practice.service;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCategoryDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeCategoryMapper;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.Set;

@Service
public class PracticeCategoryServiceImpl extends AbstractPracticeResourceService<PracticeCategoryDO>
        implements PracticeCategoryService {

    private static final Set<String> WRITABLE_COLUMNS = columns("category_name", "category_status", "field_type",
            "catalog_type", "sort_no");
    private static final Set<String> LIKE_COLUMNS = columns("category_name", "field_type");
    private static final int CATALOG_TYPE_PRACTICE = 0;

    @Resource
    private PracticeCategoryMapper practiceCategoryMapper;

    @Override
    protected BaseMapperX<PracticeCategoryDO> mapper() {
        return practiceCategoryMapper;
    }

    @Override
    protected Class<PracticeCategoryDO> entityClass() {
        return PracticeCategoryDO.class;
    }

    @Override
    protected Set<String> writableColumns() {
        return WRITABLE_COLUMNS;
    }

    @Override
    protected Set<String> likeColumns() {
        return LIKE_COLUMNS;
    }

    @Override
    protected QueryWrapper<PracticeCategoryDO> buildQuery(java.util.Map<String, String> params) {
        QueryWrapper<PracticeCategoryDO> wrapper = super.buildQuery(params);
        wrapper.eq("catalog_type", CATALOG_TYPE_PRACTICE);
        return wrapper;
    }
}
