package com.huiyitech.postcollect.dal.mysql.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;

@Mapper
public interface PostCollectTaskMapper extends BaseMapperX<PostCollectTaskDO> {

    @Update("UPDATE yj_post_collection_task "
            + "SET collection_lock_owner = #{owner}, collection_lock_until = #{lockUntil}, "
            + "updater = #{operator}, update_time = #{now} "
            + "WHERE id = #{taskId} AND deleted = b'0' "
            + "AND (collection_lock_until IS NULL OR collection_lock_until < #{now})")
    int tryAcquireCollectionLock(@Param("taskId") Long taskId, @Param("owner") String owner,
                                 @Param("lockUntil") LocalDateTime lockUntil, @Param("operator") String operator,
                                 @Param("now") LocalDateTime now);

    @Update("UPDATE yj_post_collection_task "
            + "SET collection_lock_until = #{lockUntil}, updater = #{operator}, update_time = #{now} "
            + "WHERE id = #{taskId} AND collection_lock_owner = #{owner}")
    int renewCollectionLock(@Param("taskId") Long taskId, @Param("owner") String owner,
                             @Param("lockUntil") LocalDateTime lockUntil, @Param("operator") String operator,
                             @Param("now") LocalDateTime now);

    @Update("UPDATE yj_post_collection_task "
            + "SET collection_lock_owner = NULL, collection_lock_until = NULL, "
            + "updater = #{operator}, update_time = #{now} "
            + "WHERE id = #{taskId} AND collection_lock_owner = #{owner}")
    int releaseCollectionLock(@Param("taskId") Long taskId, @Param("owner") String owner,
                              @Param("operator") String operator, @Param("now") LocalDateTime now);
}
