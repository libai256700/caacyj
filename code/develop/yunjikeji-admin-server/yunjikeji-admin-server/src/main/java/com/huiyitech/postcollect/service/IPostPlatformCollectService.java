package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;

import java.util.List;

public interface IPostPlatformCollectService {

    String getPlatformSource();

    List<PostCollectDO> collect(PostCollectTaskDO task);

}
