package cn.iocoder.yudao.server.service.yj;

import java.util.*;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

/**
 * 云技业务后台资源白名单。
 */
public class YjAdminTableRegistry {

    private static final Map<String, TableMeta> TABLES = new LinkedHashMap<>();

    static {
        register("enterprise-audit", "yj_audit_info",
                columns("user_id", "name", "legal_person", "contact_name", "contact_mobile", "audit_status",
                        "audit_reason", "audit_time", "audit_user_id", "tenant_id"),
                columns("name", "contact_name", "contact_mobile"));
        register("enterprise-audit-attachment", "yj_audit_info_attachment",
                columns("company_id", "user_id", "company_account_front_id", "file_path", "file_name", "file_type", "tenant_id"),
                columns("file_name", "file_type"));
        register("company-account-front", "yj_company_account_front",
                columns("username", "status", "audit_status", "tenant_id"),
                columns("username"));
        register("student-audit", "yj_student_audit_info",
                columns("company_id", "user_id", "customer_account_id", "audit_status", "audit_reason", "audit_time", "tenant_id"),
                Collections.<String>emptySet());
        register("customer-account", "yj_customer_account",
                columns("username", "mobile", "status", "audit_status", "last_login_channel", "tenant_id"),
                columns("username", "mobile"));
        register("customer-info", "yj_customer_info",
                columns("customer_account_id", "nick_name", "real_name", "sex", "mobile_phone", "email", "avatar_url",
                        "id_card", "student_no", "school_name", "major_name", "role_label", "training_direction", "tenant_id"),
                columns("nick_name", "real_name", "id_card", "mobile_phone", "student_no", "school_name", "major_name"));
        register("assessment-question", "yj_practice_exercises",
                columns("step_id", "category_id", "question_stem", "question_type", "question_status", "score", "sort_no",
                        "correct_memo", "is_required"),
                columns("question_stem", "question_type"));
        register("assessment-answer", "yj_practice_exercises_answer",
                columns("exercises_id", "question_type", "answer_code", "answer_content", "is_correct", "sort_no"),
                columns("answer_code", "answer_content"));
        register("assessment-result", "yj_assessment_result",
                columns("user_id", "customer_account_id", "assessment_time", "result_summary", "recommend_direction",
                        "report_content"),
                columns("result_summary", "recommend_direction"));
        register("post", "yj_post",
                columns("name", "company_name", "source_code", "collection_channel", "external_post_id", "salary_range",
                        "work_area", "publish_date", "detail_url", "status"),
                columns("name", "company_name", "source_code", "collection_channel", "salary_range", "work_area"));
        register("collection-task", "yj_post_collection_task",
                columns("name", "collection_channel", "collection_time", "collection_count_rule", "collection_key",
                        "collection_num", "last_execute_time", "last_execute_result", "last_execute_status", "status",
                        "tenant_id"),
                columns("name", "collection_channel", "collection_key", "last_execute_result"));
        register("collection-task-instance", "yj_post_collection_task_instance",
                columns("stauts", "task_id", "collection_count"),
                Collections.<String>emptySet());
        register("post-instance", "yj_post_instance",
                columns("task_instance_id", "name", "company_name", "source_code", "collection_channel", "external_post_id",
                        "salary_range", "work_area", "publish_date", "detail_url", "status"),
                columns("name", "company_name", "source_code", "collection_channel", "salary_range", "work_area"));
        register("collection-task-log", "yj_collection_task_log",
                columns("task_id", "execute_time", "execute_result", "success_count", "fail_reason", "tenant_id"),
                columns("execute_result", "fail_reason"));
        register("knowledge-base", "yj_knowledge_base",
                columns("name", "item_count", "status", "interface_url", "tenant_id"),
                columns("name"));
        register("knowledge-item", "yj_knowledge_item",
                columns("knowledge_base_id", "title", "content_type", "content_url", "content_text", "status",
                        "tenant_id"),
                columns("title", "content_type", "content_text"));
        register("agent", "yj_agent_info",
                columns("name", "knowledge_base_id", "prompt_config", "reply_strategy", "status", "remark",
                        "agent_id", "tenant_id"),
                columns("name", "reply_strategy", "remark", "agent_id"));
    }

    private static void register(String resource, String table, Set<String> columns, Set<String> likeColumns) {
        TABLES.put(resource, new TableMeta(resource, table, columns, likeColumns));
    }

    private static Set<String> columns(String... columns) {
        return new LinkedHashSet<>(Arrays.asList(columns));
    }

    public TableMeta get(String resource) {
        TableMeta meta = TABLES.get(resource);
        if (meta == null) {
            throw invalidParamException("不支持的云技后台资源：{}", resource);
        }
        return meta;
    }

    public Collection<TableMeta> list() {
        return TABLES.values();
    }

    public static class TableMeta {

        private final String resource;
        private final String tableName;
        private final Set<String> columns;
        private final Set<String> likeColumns;

        TableMeta(String resource, String tableName, Set<String> columns, Set<String> likeColumns) {
            this.resource = resource;
            this.tableName = tableName;
            this.columns = columns;
            this.likeColumns = likeColumns;
        }

        public String getResource() {
            return resource;
        }

        public String getTableName() {
            return tableName;
        }

        public Set<String> getColumns() {
            return columns;
        }

        public boolean isColumn(String column) {
            return columns.contains(column) || "id".equals(column) || "create_time".equals(column)
                    || "update_time".equals(column);
        }

        public boolean isWritableColumn(String column) {
            return columns.contains(column);
        }

        public boolean isLikeColumn(String column) {
            return likeColumns.contains(column);
        }
    }
}
