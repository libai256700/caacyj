package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;

import java.util.List;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

public class UnsupportedPostPlatformCollectServiceImpl extends AbstractPostPlatformCollectService {

    private final String platformSource;

    public UnsupportedPostPlatformCollectServiceImpl(String platformSource) {
        this.platformSource = platformSource;
    }

    @Override
    public String getPlatformSource() {
        return platformSource;
    }

    @Override
    public List<PostCollectDO> collect(PostCollectTaskDO task) {
        throw invalidParamException("采集渠道暂未实现：{}", platformSource);
    }
}
