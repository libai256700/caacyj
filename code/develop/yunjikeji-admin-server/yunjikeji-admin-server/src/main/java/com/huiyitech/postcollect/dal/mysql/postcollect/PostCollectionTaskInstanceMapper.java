package com.huiyitech.postcollect.dal.mysql.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectionTaskInstanceDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;

@Mapper
public interface PostCollectionTaskInstanceMapper extends BaseMapperX<PostCollectionTaskInstanceDO> {

    @Update("UPDATE yj_post_collection_task_instance i "
            + "LEFT JOIN yj_post_collection_task t ON t.id = i.task_id AND t.deleted = b'0' "
            + "SET i.stauts = 4, i.updater = #{operator}, i.update_time = #{now} "
            + "WHERE i.stauts = 1 AND i.create_time < #{staleBefore} "
            + "AND (t.collection_lock_until IS NULL OR t.collection_lock_until < #{now})")
    int failStaleRunningInstances(@Param("staleBefore") LocalDateTime staleBefore,
                                  @Param("operator") String operator, @Param("now") LocalDateTime now);
}
