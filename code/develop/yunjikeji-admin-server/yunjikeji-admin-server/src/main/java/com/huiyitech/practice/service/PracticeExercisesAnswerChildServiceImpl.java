package com.huiyitech.practice.service;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerChildDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesAnswerChildMapper;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.Set;

@Service
public class PracticeExercisesAnswerChildServiceImpl
        extends AbstractPracticeResourceService<PracticeExercisesAnswerChildDO>
        implements PracticeExercisesAnswerChildService {

    private static final Set<String> WRITABLE_COLUMNS = columns("answer_id", "question_type", "answer_content",
            "is_correct");
    private static final Set<String> LIKE_COLUMNS = columns("answer_content");

    @Resource
    private PracticeExercisesAnswerChildMapper practiceExercisesAnswerChildMapper;

    @Override
    protected BaseMapperX<PracticeExercisesAnswerChildDO> mapper() {
        return practiceExercisesAnswerChildMapper;
    }

    @Override
    protected Class<PracticeExercisesAnswerChildDO> entityClass() {
        return PracticeExercisesAnswerChildDO.class;
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
