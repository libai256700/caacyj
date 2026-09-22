package com.huiyitech.aiconfig.service;

import com.huiyitech.aiconfig.dal.dataobject.AiModelConfigDO;

public interface AiModelConfigService {

    AiModelConfigDO getActiveBySceneCode(String sceneCode);

    AiModelConfigDO getRequiredActiveBySceneCode(String sceneCode);
}
