package com.huiyitech.practice.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;

import java.util.Map;

public interface UserPracticeExercisesRecordService extends PracticeResourceService {

    PageResult<Map<String, Object>> getDetailPage(Map<String, String> params);

    Map<String, Object> getDetail(Long id);

    Long createDetail(Map<String, Object> body);

    void updateDetail(Map<String, Object> body);

    void deleteDetail(Long id);
}
