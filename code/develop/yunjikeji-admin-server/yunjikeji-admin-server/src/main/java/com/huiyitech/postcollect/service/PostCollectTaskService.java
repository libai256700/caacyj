package com.huiyitech.postcollect.service;

import java.util.Map;

public interface PostCollectTaskService extends PostCollectResourceService {

    Map<String, Object> collectNow(Map<String, Object> body);
}
