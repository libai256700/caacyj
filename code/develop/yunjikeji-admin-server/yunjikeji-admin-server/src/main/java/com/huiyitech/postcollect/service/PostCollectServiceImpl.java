package com.huiyitech.postcollect.service;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.mysql.postcollect.PostCollectMapper;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.Set;

@Service
public class PostCollectServiceImpl extends AbstractPostCollectResourceService<PostCollectDO>
        implements PostCollectService {

    private static final Set<String> WRITABLE_COLUMNS = columns("name", "company_name", "source_code",
            "collection_channel",
            "external_post_id", "salary_range", "work_area", "publish_date", "detail_url", "status");
    private static final Set<String> LIKE_COLUMNS = columns("name", "company_name", "source_code",
            "collection_channel",
            "external_post_id", "salary_range", "work_area", "publish_date", "detail_url");

    @Resource
    private PostCollectMapper postCollectMapper;

    @Override
    protected BaseMapperX<PostCollectDO> mapper() {
        return postCollectMapper;
    }

    @Override
    protected Class<PostCollectDO> entityClass() {
        return PostCollectDO.class;
    }

    @Override
    protected Set<String> writableColumns() {
        return WRITABLE_COLUMNS;
    }

    @Override
    protected Set<String> likeColumns() {
        return LIKE_COLUMNS;
    }
}
