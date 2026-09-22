package com.huiyitech.postcollect.dal.mysql.postcollect;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;

@Mapper
public interface FeishuPostDocumentMapper extends BaseMapperX<FeishuPostDocumentDO> {

    @Select("SELECT * FROM yj_feishu_post_document "
            + "WHERE folder_token = #{folderToken} AND document_id = #{documentId} LIMIT 1")
    FeishuPostDocumentDO selectIncludingDeleted(@Param("folderToken") String folderToken,
                                                @Param("documentId") String documentId);

    @Update("UPDATE yj_feishu_post_document SET deleted = b'0', updater = #{operator}, update_time = #{updateTime} "
            + "WHERE id = #{id} AND deleted = b'1'")
    int restoreDeletedById(@Param("id") Long id, @Param("operator") String operator,
                           @Param("updateTime") LocalDateTime updateTime);
}
