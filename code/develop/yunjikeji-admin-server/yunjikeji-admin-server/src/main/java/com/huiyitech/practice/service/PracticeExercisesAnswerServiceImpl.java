package com.huiyitech.practice.service;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesAnswerMapper;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.Set;

@Service
public class PracticeExercisesAnswerServiceImpl extends AbstractPracticeResourceService<PracticeExercisesAnswerDO>
        implements PracticeExercisesAnswerService {

    private static final Set<String> WRITABLE_COLUMNS = columns("exercises_id", "question_type", "answer_code",
            "answer_content", "is_correct", "sort_no");
    private static final Set<String> LIKE_COLUMNS = columns("answer_code", "answer_content");

    @Resource
    private PracticeExercisesAnswerMapper practiceExercisesAnswerMapper;

    @Override
    protected BaseMapperX<PracticeExercisesAnswerDO> mapper() {
        return practiceExercisesAnswerMapper;
    }

    @Override
    protected Class<PracticeExercisesAnswerDO> entityClass() {
        return PracticeExercisesAnswerDO.class;
    }

    @Override
    protected Set<String> writableColumns() {
        return WRITABLE_COLUMNS;
    }

    @Override
    protected Set<String> likeColumns() {
        return LIKE_COLUMNS;
    }
}
