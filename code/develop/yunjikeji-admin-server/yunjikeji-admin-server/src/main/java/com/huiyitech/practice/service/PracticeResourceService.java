package com.huiyitech.practice.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;

import java.util.Map;

public interface PracticeResourceService {

    PageResult<Map<String, Object>> getPage(Map<String, String> params);

    Map<String, Object> get(Long id);

    Long create(Map<String, Object> body);

    void update(Map<String, Object> body);

    void delete(Long id);
}
