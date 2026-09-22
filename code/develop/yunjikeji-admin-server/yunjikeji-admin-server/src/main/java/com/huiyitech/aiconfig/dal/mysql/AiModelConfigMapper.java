package com.huiyitech.aiconfig.dal.mysql;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.huiyitech.aiconfig.dal.dataobject.AiModelConfigDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface AiModelConfigMapper extends BaseMapper<AiModelConfigDO> {

    default AiModelConfigDO selectActiveBySceneCode(String sceneCode) {
        return selectOne(new LambdaQueryWrapper<AiModelConfigDO>()
                .eq(AiModelConfigDO::getSceneCode, sceneCode)
                .eq(AiModelConfigDO::getStatus, 0)
                .orderByAsc(AiModelConfigDO::getSort)
                .orderByAsc(AiModelConfigDO::getId)
                .last("LIMIT 1"));
    }
}
