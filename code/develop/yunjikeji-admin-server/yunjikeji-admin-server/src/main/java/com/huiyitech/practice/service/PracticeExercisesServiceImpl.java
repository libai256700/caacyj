package com.huiyitech.practice.service;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCategoryDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeCategoryMapper;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesMapper;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class PracticeExercisesServiceImpl extends AbstractPracticeResourceService<PracticeExercisesDO>
        implements PracticeExercisesService {

    private static final Set<String> WRITABLE_COLUMNS = columns("step_id", "category_id", "question_stem", "question_type",
            "question_status", "score", "sort_no", "correct_memo");
    private static final Set<String> LIKE_COLUMNS = columns("question_stem", "question_type");
    private static final int CATALOG_TYPE_PRACTICE = 0;

    @Resource
    private PracticeExercisesMapper practiceExercisesMapper;

    @Resource
    private PracticeCategoryMapper practiceCategoryMapper;

    @Override
    public PageResult<Map<String, Object>> getPage(Map<String, String> params) {
        PageResult<Map<String, Object>> page = super.getPage(params);
        enrichCategoryName(page.getList());
        return page;
    }

    @Override
    public Map<String, Object> get(Long id) {
        Map<String, Object> row = super.get(id);
        enrichCategoryName(Collections.singletonList(row));
        return row;
    }

    @Override
    protected BaseMapperX<PracticeExercisesDO> mapper() {
        return practiceExercisesMapper;
    }

    @Override
    protected Class<PracticeExercisesDO> entityClass() {
        return PracticeExercisesDO.class;
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
    protected QueryWrapper<PracticeExercisesDO> buildQuery(Map<String, String> params) {
        QueryWrapper<PracticeExercisesDO> wrapper = super.buildQuery(params);
        wrapper.inSql("category_id", "SELECT id FROM yj_practice_category WHERE deleted = b'0' AND catalog_type = "
                + CATALOG_TYPE_PRACTICE);
        return wrapper;
    }

    private void enrichCategoryName(java.util.List<Map<String, Object>> rows) {
        Set<Long> categoryIds = rows.stream()
                .map(row -> row.get("category_id"))
                .filter(Objects::nonNull)
                .map(value -> ((Number) value).longValue())
                .collect(Collectors.toSet());
        if (categoryIds.isEmpty()) {
            return;
        }

        Map<Long, PracticeCategoryDO> categoryMap = practiceCategoryMapper.selectBatchIds(categoryIds).stream()
                .collect(Collectors.toMap(PracticeCategoryDO::getId, Function.identity()));
        for (Map<String, Object> row : rows) {
            Object categoryId = row.get("category_id");
            if (categoryId == null) {
                continue;
            }
            PracticeCategoryDO category = categoryMap.get(((Number) categoryId).longValue());
            row.put("category_name", category == null ? null : category.getCategoryName());
        }
    }
}
