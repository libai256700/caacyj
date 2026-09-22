package com.huiyitech.postcollect.dal.mysql.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostCollectionRunDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface FeishuPostCollectionRunMapper extends BaseMapperX<FeishuPostCollectionRunDO> {

    @Select("SELECT r.* FROM yj_feishu_post_collection_run r "
            + "LEFT JOIN yj_post_collection_task t ON t.id = r.task_id AND t.deleted = b'0' "
            + "WHERE r.status = 'RUNNING' AND r.update_time < #{staleBefore} AND r.deleted = b'0' "
            + "AND (t.collection_lock_until IS NULL OR t.collection_lock_until < #{now})")
    List<FeishuPostCollectionRunDO> selectStaleRunsWithoutActiveLock(
            @Param("staleBefore") LocalDateTime staleBefore, @Param("now") LocalDateTime now);
}
