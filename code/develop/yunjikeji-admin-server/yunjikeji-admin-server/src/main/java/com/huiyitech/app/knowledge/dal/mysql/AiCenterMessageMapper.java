package com.huiyitech.app.knowledge.dal.mysql;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.huiyitech.app.knowledge.dal.dataobject.AiCenterMessageDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface AiCenterMessageMapper extends BaseMapper<AiCenterMessageDO> {

    default List<AiCenterMessageDO> selectRecentHistory(Long customAccountId, String name, int limit) {
        LambdaQueryWrapper<AiCenterMessageDO> queryWrapper = new LambdaQueryWrapper<AiCenterMessageDO>()
                .eq(AiCenterMessageDO::getCustomAccountId, customAccountId)
                .eq(AiCenterMessageDO::getName, name)
                .orderByDesc(AiCenterMessageDO::getId)
                .last("LIMIT " + limit);
        return selectList(queryWrapper);
    }
}
