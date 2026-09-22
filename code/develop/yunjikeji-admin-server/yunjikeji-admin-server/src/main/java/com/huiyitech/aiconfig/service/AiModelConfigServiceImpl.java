package com.huiyitech.aiconfig.service;

import com.huiyitech.aiconfig.dal.dataobject.AiModelConfigDO;
import com.huiyitech.aiconfig.dal.mysql.AiModelConfigMapper;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
@TenantIgnore
public class AiModelConfigServiceImpl implements AiModelConfigService {

    @Resource
    private AiModelConfigMapper aiModelConfigMapper;

    @Override
    public AiModelConfigDO getActiveBySceneCode(String sceneCode) {
        if (!StringUtils.hasText(sceneCode)) {
            return null;
        }
        return aiModelConfigMapper.selectActiveBySceneCode(sceneCode.trim());
    }

    @Override
    public AiModelConfigDO getRequiredActiveBySceneCode(String sceneCode) {
        AiModelConfigDO config = getActiveBySceneCode(sceneCode);
        if (config == null) {
            throw invalidParamException("AI 模型场景未配置或未启用：" + sceneCode);
        }
        if (!StringUtils.hasText(config.getChannel())
                || !StringUtils.hasText(config.getBaseUrl())
                || !StringUtils.hasText(config.getApiKey())
                || !StringUtils.hasText(config.getModel())) {
            throw invalidParamException("AI 模型场景配置不完整：" + sceneCode);
        }
        return config;
    }
}
