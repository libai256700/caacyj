package com.huiyitech.postcollect.service;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectTaskMapper;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.Map;
import java.util.Set;

@Service
public class PostCollectTaskServiceImpl extends AbstractPostCollectResourceService<PostCollectTaskDO>
        implements PostCollectTaskService {

    private static final Set<String> WRITABLE_COLUMNS = columns("name", "collection_channel", "collection_time",
            "collection_count_rule", "collection_key", "collection_num", "last_execute_time",
            "last_execute_result", "last_execute_status", "status", "tenant_id");
    private static final Set<String> LIKE_COLUMNS = columns("name", "collection_channel", "collection_key",
            "last_execute_result");

    @Resource
    private PostCollectTaskMapper postCollectTaskMapper;
    @Resource
    private PostCollectionTaskService postCollectionTaskService;

    @Override
    protected BaseMapperX<PostCollectTaskDO> mapper() {
        return postCollectTaskMapper;
    }

    @Override
    protected Class<PostCollectTaskDO> entityClass() {
        return PostCollectTaskDO.class;
    }

    @Override
    protected Set<String> writableColumns() {
        return WRITABLE_COLUMNS;
    }

    @Override
    protected Set<String> likeColumns() {
        return LIKE_COLUMNS;
    }

    @Override
    public Map<String, Object> collectNow(Map<String, Object> body) {
        Long id = requireId(body);
        return postCollectionTaskService.collectNow(id, "admin");
    }

    private Long requireId(Map<String, Object> body) {
        Object id = body == null ? null : body.get("id");
        if (id == null) {
            throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException(
                    "id cannot be empty");
        }
        if (id instanceof Number) {
            return ((Number) id).longValue();
        }
        try {
            return Long.parseLong(String.valueOf(id));
        } catch (NumberFormatException ex) {
            throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException(
                    "id must be a number");
        }
    }
}
