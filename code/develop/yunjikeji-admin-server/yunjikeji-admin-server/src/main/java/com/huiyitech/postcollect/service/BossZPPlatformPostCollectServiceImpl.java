package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import lombok.extern.slf4j.Slf4j;

import java.util.Collections;
import java.util.List;

@Slf4j
public class BossZPPlatformPostCollectServiceImpl extends AbstractPostPlatformCollectService {

    @Override
    public String getPlatformSource() {
        return "boss_zhipin";
    }

    @Override
    public List<PostCollectDO> collect(PostCollectTaskDO task) {
        log.info("BOSS直聘岗位采集当前不予实现，返回空结果: taskId={}", task == null ? null : task.getId());
        return Collections.emptyList();
    }
}
