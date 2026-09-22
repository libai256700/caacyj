package com.huiyitech.customer.dal.mysql.customer;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.huiyitech.customer.dal.dataobject.customer.StudentAuditInfoDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface StudentAuditInfoMapper extends BaseMapperX<StudentAuditInfoDO> {

    default StudentAuditInfoDO selectLatestByCustomerAccountId(Long customerAccountId) {
        return selectOne(new LambdaQueryWrapperX<StudentAuditInfoDO>()
                .eq(StudentAuditInfoDO::getCustomerAccountId, customerAccountId)
                .orderByDesc(StudentAuditInfoDO::getId)
                .last("LIMIT 1"));
    }

    default StudentAuditInfoDO selectLatestApprovedByCustomerAccountId(Long customerAccountId) {
        return selectOne(new LambdaQueryWrapperX<StudentAuditInfoDO>()
                .eq(StudentAuditInfoDO::getCustomerAccountId, customerAccountId)
                .eq(StudentAuditInfoDO::getAuditStatus, 2)
                .orderByDesc(StudentAuditInfoDO::getId)
                .last("LIMIT 1"));
    }

    @Select({
            "<script>",
            "SELECT id, tenant_id, company_id, user_id, customer_account_id, audit_status, audit_reason, audit_time,",
            "       create_time, update_time, creator, updater, deleted",
            "FROM yj_student_audit_info",
            "WHERE deleted = 0",
            "  AND (company_id = #{companyId}",
            "       OR (tenant_id = #{companyId} AND (company_id IS NULL OR company_id &lt;= 0)))",
            "<if test='auditStatus != null'>",
            "  AND audit_status = #{auditStatus}",
            "</if>",
            "<if test='startTime != null'>",
            "  AND create_time &gt;= #{startTime}",
            "</if>",
            "<if test='endTime != null'>",
            "  AND create_time &lt;= #{endTime}",
            "</if>",
            "ORDER BY create_time DESC, id DESC",
            "</script>"
    })
    List<StudentAuditInfoDO> selectCompanyStudentAuditList(@Param("companyId") Long companyId,
                                                           @Param("auditStatus") Integer auditStatus,
                                                           @Param("startTime") LocalDateTime startTime,
                                                           @Param("endTime") LocalDateTime endTime);
}
