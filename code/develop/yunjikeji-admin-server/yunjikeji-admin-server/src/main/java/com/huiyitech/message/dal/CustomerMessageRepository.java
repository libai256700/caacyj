package com.huiyitech.message.dal;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Repository
public class CustomerMessageRepository {

    private static final String CUSTOMER_SERVICE_POST_CODE = "WT";
    private static final int DEFAULT_PAGE_NO = 1;
    private static final int DEFAULT_PAGE_SIZE = 10;
    private static final int MAX_PAGE_SIZE = 200;

    @Resource
    private JdbcTemplate jdbcTemplate;

    public Long getStudentTenantId(Long studentId) {
        List<Long> tenantIds = jdbcTemplate.queryForList("SELECT tenant_id FROM yj_customer_account "
                        + "WHERE id = ? AND deleted = b'0' LIMIT 1",
                Long.class, studentId);
        return tenantIds.isEmpty() ? null : tenantIds.get(0);
    }

    public Long getCompanyFrontTenantId(Long companyAccountFrontId) {
        List<Long> tenantIds = jdbcTemplate.queryForList("SELECT tenant_id FROM yj_company_account_front "
                        + "WHERE id = ? AND status = b'1' AND deleted = b'0' LIMIT 1",
                Long.class, companyAccountFrontId);
        return tenantIds.isEmpty() ? null : tenantIds.get(0);
    }

    public boolean isWtCompanyFrontUser(Long companyAccountFrontId) {
        Long count = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM yj_company_account_front caf "
                        + "INNER JOIN system_users su ON su.mobile = caf.username "
                        + "AND su.tenant_id IN (0, 1) AND su.status = 0 AND su.deleted = b'0' "
                        + "WHERE caf.id = ? AND caf.status = b'1' AND caf.deleted = b'0' "
                        + "AND EXISTS (SELECT 1 FROM system_post sp "
                        + "WHERE sp.code = ? AND sp.tenant_id IN (0, 1) "
                        + "AND sp.status = 0 AND sp.deleted = b'0' "
                        + "AND JSON_CONTAINS(COALESCE(su.post_ids, JSON_ARRAY()), CAST(sp.id AS CHAR), '$'))",
                Long.class, companyAccountFrontId, CUSTOMER_SERVICE_POST_CODE);
        return count != null && count > 0;
    }

    public List<Map<String, Object>> getApprovedStudentConversations(int pageNo, int pageSize) {
        int offset = (pageNo - 1) * pageSize;
        return jdbcTemplate.queryForList("SELECT ca.id AS student_id, "
                        + "COALESCE(NULLIF(ci.real_name, ''), NULLIF(ci.nick_name, ''), "
                        + "NULLIF(ci.mobile_phone, ''), NULLIF(ca.mobile, ''), NULLIF(ca.username, ''), "
                        + "CONCAT('学员', ca.id)) AS student_name, "
                        + "COALESCE(NULLIF(ci.mobile_phone, ''), NULLIF(ca.mobile, ''), NULLIF(ca.username, '')) AS student_phone, "
                        + "ca.tenant_id, sm.id AS session_id, sm.last_message_content, sm.last_message_time, "
                        + "COALESCE(sm.unread_count, 0) AS unread_count "
                        + "FROM yj_customer_account ca "
                        + "LEFT JOIN yj_customer_info ci ON ci.id = ("
                        + "SELECT MAX(latest_ci.id) FROM yj_customer_info latest_ci "
                        + "WHERE latest_ci.customer_account_id = ca.id "
                        + "AND (latest_ci.tenant_id = ca.tenant_id "
                        + "OR (latest_ci.tenant_id IS NULL AND ca.tenant_id IS NULL)) "
                        + "AND latest_ci.deleted = b'0') "
                        + "LEFT JOIN yj_session_message sm ON sm.id = ("
                        + "SELECT MAX(latest_sm.id) FROM yj_session_message latest_sm "
                        + "WHERE latest_sm.session_from = ca.id AND latest_sm.session_to = 0 "
                        + "AND latest_sm.tenant_id = 1 AND latest_sm.deleted = b'0') "
                        + "WHERE ca.deleted = b'0' "
                        + "ORDER BY COALESCE(sm.last_message_time, ci.update_time, ci.create_time, "
                        + "ca.update_time, ca.create_time) DESC, ca.id DESC "
                        + "LIMIT ? OFFSET ?",
                pageSize, offset);
    }

    public boolean existsApprovedStudent(Long studentId) {
        Long count = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM yj_customer_account ca "
                        + "WHERE ca.id = ? AND ca.deleted = b'0'",
                Long.class, studentId);
        return count != null && count > 0;
    }

    public Long lockApprovedStudentTenantId(Long studentId) {
        List<Long> tenantIds = jdbcTemplate.queryForList("SELECT ca.tenant_id FROM yj_customer_account ca "
                        + "WHERE ca.id = ? AND ca.deleted = b'0' LIMIT 1 FOR UPDATE",
                Long.class, studentId);
        if (tenantIds.isEmpty()) {
            throw invalidParamException("Approved student does not exist");
        }
        return tenantIds.get(0);
    }

    public String getStudentName(Long studentId) {
        if (studentId == null) {
            return "";
        }
        List<String> names = jdbcTemplate.queryForList("SELECT COALESCE(NULLIF(ci.real_name, ''), "
                        + "NULLIF(ci.nick_name, ''), NULLIF(ci.mobile_phone, ''), NULLIF(ca.username, ''), "
                        + "CONCAT('学员', ca.id)) FROM yj_customer_account ca "
                        + "LEFT JOIN yj_customer_info ci ON ci.customer_account_id = ca.id "
                        + "AND (ci.tenant_id = ca.tenant_id OR (ci.tenant_id IS NULL AND ca.tenant_id IS NULL)) "
                        + "AND ci.deleted = b'0' "
                        + "WHERE ca.id = ? AND ca.deleted = b'0' LIMIT 1",
                String.class, studentId);
        return names.isEmpty() ? "学员" + studentId : names.get(0);
    }

    public String getStaffName(Long staffId, Long tenantId) {
        if (staffId == null || staffId <= 0) {
            return "";
        }
        List<String> names = jdbcTemplate.queryForList("SELECT COALESCE(NULLIF(nickname, ''), "
                        + "NULLIF(username, ''), CONCAT('员工', id)) FROM system_users "
                        + "WHERE id = ? AND tenant_id = ? AND deleted = b'0' LIMIT 1",
                String.class, staffId, tenantId);
        return names.isEmpty() ? "员工" + staffId : names.get(0);
    }

    public Map<String, Object> getOrCreateSession(Long sessionFrom, Long sessionTo, Long tenantId, Timestamp now) {
        List<Map<String, Object>> existing = jdbcTemplate.queryForList("SELECT * FROM yj_session_message "
                + "WHERE session_from = ? AND session_to = ? AND tenant_id = ? AND deleted = b'0' "
                + "ORDER BY id DESC LIMIT 1", sessionFrom, sessionTo, tenantId);
        if (!existing.isEmpty()) {
            return existing.get(0);
        }

        jdbcTemplate.update("INSERT INTO yj_session_message "
                        + "(session_from, session_to, last_message_content, last_message_time, unread_count, tenant_id, creator, create_time, updater, update_time, deleted) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, b'0')",
                sessionFrom, sessionTo, "", now, 0, tenantId, String.valueOf(sessionFrom), now,
                String.valueOf(sessionFrom), now);
        return jdbcTemplate.queryForMap("SELECT * FROM yj_session_message "
                        + "WHERE session_from = ? AND session_to = ? AND tenant_id = ? AND deleted = b'0' "
                        + "ORDER BY id DESC LIMIT 1",
                sessionFrom, sessionTo, tenantId);
    }

    public Map<String, Object> findLatestSessionByStudent(Long studentId, Long sessionTo, Long tenantId) {
        List<Map<String, Object>> sessions = jdbcTemplate.queryForList("SELECT * FROM yj_session_message "
                        + "WHERE session_from = ? AND session_to = ? AND tenant_id = ? AND deleted = b'0' "
                        + "ORDER BY id DESC LIMIT 1",
                studentId, sessionTo, tenantId);
        return sessions.isEmpty() ? null : sessions.get(0);
    }

    public Map<String, Object> createSession(Long sessionFrom, Long sessionTo, Long tenantId, Timestamp now) {
        jdbcTemplate.update("INSERT INTO yj_session_message "
                        + "(session_from, session_to, last_message_content, last_message_time, unread_count, tenant_id, creator, create_time, updater, update_time, deleted) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, b'0')",
                sessionFrom, sessionTo, "", now, 0, tenantId, String.valueOf(sessionFrom), now,
                String.valueOf(sessionFrom), now);
        Long conversationId = jdbcTemplate.queryForObject("SELECT LAST_INSERT_ID()", Long.class);
        if (conversationId == null || conversationId <= 0) {
            throw invalidParamException("Customer service session creation failed");
        }
        return getSessionByConversationAndStudent(conversationId, sessionFrom);
    }

    public Map<String, Object> getSessionByConversationAndStudent(Long conversationId, Long studentId) {
        List<Map<String, Object>> sessions = jdbcTemplate.queryForList("SELECT * FROM yj_session_message "
                + "WHERE id = ? AND session_from = ? AND deleted = b'0'", conversationId, studentId);
        if (sessions.isEmpty()) {
            throw invalidParamException("Customer service conversation does not match the selected student");
        }
        return sessions.get(0);
    }

    public PageResult<Map<String, Object>> getSessionPage(Map<String, String> params, Long tenantId) {
        int pageNo = parsePageNo(params);
        int pageSize = parsePageSize(params);
        int offset = (pageNo - 1) * pageSize;
        StringBuilder where = new StringBuilder(" WHERE deleted = b'0' AND tenant_id = ?");
        List<Object> args = new ArrayList<>();
        args.add(tenantId);
        appendLongCondition(where, args, params, "session_from");
        appendLongCondition(where, args, params, "session_to");
        appendCreateTimeRange(where, args, params);

        Long total = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM yj_session_message" + where, Long.class, args.toArray());
        args.add(pageSize);
        args.add(offset);
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("SELECT s.id, s.session_from, s.session_to, "
                + "s.last_message_content, s.last_message_time, s.unread_count, s.tenant_id, s.creator, "
                + "s.create_time, s.updater, s.update_time, " + sessionNameColumns()
                + " FROM yj_session_message s "
                + "LEFT JOIN yj_customer_account ca ON ca.id = s.session_from AND ca.tenant_id = s.tenant_id AND ca.deleted = b'0' "
                + "LEFT JOIN yj_customer_info ci ON ci.customer_account_id = ca.id AND ci.tenant_id = s.tenant_id AND ci.deleted = b'0' "
                + "LEFT JOIN system_users su ON su.id = s.session_to AND su.tenant_id = s.tenant_id AND su.deleted = b'0'"
                + where.toString().replace(" WHERE ", " WHERE s.")
                        .replace(" AND ", " AND s.")
                + " ORDER BY s.id DESC LIMIT ? OFFSET ?", args.toArray());
        return new PageResult<>(rows, total == null ? 0L : total);
    }

    public Map<String, Object> getSession(Long id, Long tenantId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("SELECT s.id, s.session_from, s.session_to, "
                + "s.last_message_content, s.last_message_time, s.unread_count, s.tenant_id, s.creator, "
                + "s.create_time, s.updater, s.update_time, " + sessionNameColumns()
                + " FROM yj_session_message s "
                + "LEFT JOIN yj_customer_account ca ON ca.id = s.session_from AND ca.tenant_id = s.tenant_id AND ca.deleted = b'0' "
                + "LEFT JOIN yj_customer_info ci ON ci.customer_account_id = ca.id AND ci.tenant_id = s.tenant_id AND ci.deleted = b'0' "
                + "LEFT JOIN system_users su ON su.id = s.session_to AND su.tenant_id = s.tenant_id AND su.deleted = b'0' "
                + "WHERE s.id = ? AND s.tenant_id = ? AND s.deleted = b'0'", id, tenantId);
        if (rows.isEmpty()) {
            throw invalidParamException("Customer service session does not exist: {}", id);
        }
        return rows.get(0);
    }

    public PageResult<Map<String, Object>> getMessagePage(Map<String, String> params, Long tenantId) {
        int pageNo = parsePageNo(params);
        int pageSize = parsePageSize(params);
        int offset = (pageNo - 1) * pageSize;
        StringBuilder where = new StringBuilder(" WHERE deleted = b'0' AND tenant_id = ?");
        List<Object> args = new ArrayList<>();
        args.add(tenantId);
        appendLongCondition(where, args, params, "session_id");
        appendLongCondition(where, args, params, "session_from");
        appendLongCondition(where, args, params, "session_to");
        appendContentCondition(where, args, params);
        appendCreateTimeRange(where, args, params);

        Long total = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM yj_message_info" + where, Long.class, args.toArray());
        args.add(pageSize);
        args.add(offset);
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("SELECT m.id, m.session_id, m.session_from, m.session_to, "
                + "m.message_type, m.content, m.tenant_id, m.creator, m.create_time, m.updater, m.update_time, "
                + messageNameColumns()
                + " FROM yj_message_info m "
                + "LEFT JOIN yj_session_message s ON s.id = m.session_id AND s.tenant_id = m.tenant_id AND s.deleted = b'0' "
                + "LEFT JOIN yj_customer_account ca ON ca.id = s.session_from AND ca.tenant_id = m.tenant_id AND ca.deleted = b'0' "
                + "LEFT JOIN yj_customer_info ci ON ci.customer_account_id = ca.id AND ci.tenant_id = m.tenant_id AND ci.deleted = b'0' "
                + "LEFT JOIN system_users su ON su.id = s.session_to AND su.tenant_id = m.tenant_id AND su.deleted = b'0'"
                + where.toString().replace(" WHERE ", " WHERE m.")
                        .replace(" AND ", " AND m.")
                + " ORDER BY m.id DESC LIMIT ? OFFSET ?", args.toArray());
        return new PageResult<>(rows, total == null ? 0L : total);
    }

    public Map<String, Object> getMessage(Long id, Long tenantId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("SELECT m.id, m.session_id, m.session_from, m.session_to, "
                + "m.message_type, m.content, m.tenant_id, m.creator, m.create_time, m.updater, m.update_time, "
                + messageNameColumns()
                + " FROM yj_message_info m "
                + "LEFT JOIN yj_session_message s ON s.id = m.session_id AND s.tenant_id = m.tenant_id AND s.deleted = b'0' "
                + "LEFT JOIN yj_customer_account ca ON ca.id = s.session_from AND ca.tenant_id = m.tenant_id AND ca.deleted = b'0' "
                + "LEFT JOIN yj_customer_info ci ON ci.customer_account_id = ca.id AND ci.tenant_id = m.tenant_id AND ci.deleted = b'0' "
                + "LEFT JOIN system_users su ON su.id = s.session_to AND su.tenant_id = m.tenant_id AND su.deleted = b'0' "
                + "WHERE m.id = ? AND m.tenant_id = ? AND m.deleted = b'0'", id, tenantId);
        if (rows.isEmpty()) {
            throw invalidParamException("Customer service message does not exist: {}", id);
        }
        return rows.get(0);
    }

    public List<Map<String, Object>> getMessagesBySessionId(Long sessionId, Long tenantId, int pageNo, int pageSize) {
        int offset = (pageNo - 1) * pageSize;
        return jdbcTemplate.queryForList("SELECT m.*, " + messageNameColumns()
                        + " FROM yj_message_info m "
                        + "LEFT JOIN yj_session_message s ON s.id = m.session_id AND s.tenant_id = m.tenant_id AND s.deleted = b'0' "
                        + "LEFT JOIN yj_customer_account ca ON ca.id = s.session_from AND ca.tenant_id = m.tenant_id AND ca.deleted = b'0' "
                        + "LEFT JOIN yj_customer_info ci ON ci.customer_account_id = ca.id AND ci.tenant_id = m.tenant_id AND ci.deleted = b'0' "
                        + "LEFT JOIN system_users su ON su.id = s.session_to AND su.tenant_id = m.tenant_id AND su.deleted = b'0' "
                        + "WHERE m.session_id = ? AND m.tenant_id = ? AND m.deleted = b'0' ORDER BY m.id ASC LIMIT ? OFFSET ?",
                sessionId, tenantId, pageSize, offset);
    }

    public List<Map<String, Object>> getMessagesByStudentId(Long studentId, int pageNo, int pageSize) {
        int offset = (pageNo - 1) * pageSize;
        return jdbcTemplate.queryForList("SELECT m.* FROM yj_message_info m "
                        + "INNER JOIN yj_session_message s ON s.id = m.session_id AND s.deleted = b'0' "
                        + "WHERE s.session_from = ? AND m.deleted = b'0' "
                        + "ORDER BY m.create_time ASC, m.id ASC LIMIT ? OFFSET ?",
                studentId, pageSize, offset);
    }

    public Long insertMessage(Long sessionId, Long sessionFrom, Long sessionTo, String messageType, String content,
                              Long tenantId, String operator, Timestamp now) {
        jdbcTemplate.update("INSERT INTO yj_message_info "
                        + "(session_id, session_from, session_to, message_type, content, tenant_id, creator, create_time, updater, update_time, deleted) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, b'0')",
                sessionId, sessionFrom, sessionTo, messageType, content, tenantId, operator, now, operator, now);
        Long id = jdbcTemplate.queryForObject("SELECT LAST_INSERT_ID()", Long.class);
        return id == null ? 0L : id;
    }

    public void bindSessionReceiver(Long sessionId, Long tenantId, Long sessionTo, String operator, Timestamp now) {
        jdbcTemplate.update("UPDATE yj_session_message SET session_to = ?, updater = ?, update_time = ? "
                        + "WHERE id = ? AND tenant_id = ? AND deleted = b'0'",
                sessionTo, operator, now, sessionId, tenantId);
    }

    public void updateSessionSnapshot(Long sessionId, Long tenantId, String content, Timestamp now, String operator,
                                      boolean increaseUnread) {
        if (increaseUnread) {
            jdbcTemplate.update("UPDATE yj_session_message SET last_message_content = ?, last_message_time = ?, "
                            + "unread_count = unread_count + 1, updater = ?, update_time = ? "
                            + "WHERE id = ? AND tenant_id = ? AND deleted = b'0'",
                    content, now, operator, now, sessionId, tenantId);
            return;
        }
        jdbcTemplate.update("UPDATE yj_session_message SET last_message_content = ?, last_message_time = ?, "
                        + "updater = ?, update_time = ? WHERE id = ? AND tenant_id = ? AND deleted = b'0'",
                content, now, operator, now, sessionId, tenantId);
    }

    private String sessionNameColumns() {
        return "COALESCE(NULLIF(ci.real_name, ''), NULLIF(ci.nick_name, ''), NULLIF(ci.mobile_phone, ''), "
                + "NULLIF(ca.username, ''), CONCAT('学员', s.session_from)) AS student_name, "
                + "CASE WHEN s.session_to > 0 THEN COALESCE(NULLIF(su.nickname, ''), NULLIF(su.username, ''), "
                + "CONCAT('员工', s.session_to)) ELSE '客服' END AS staff_name";
    }

    private String messageNameColumns() {
        return "COALESCE(NULLIF(ci.real_name, ''), NULLIF(ci.nick_name, ''), NULLIF(ci.mobile_phone, ''), "
                + "NULLIF(ca.username, ''), CONCAT('学员', s.session_from)) AS student_name, "
                + "CASE WHEN s.session_to > 0 THEN COALESCE(NULLIF(su.nickname, ''), NULLIF(su.username, ''), "
                + "CONCAT('员工', s.session_to)) ELSE '客服' END AS staff_name";
    }

    private void appendLongCondition(StringBuilder where, List<Object> args, Map<String, String> params, String key) {
        String value = params == null ? null : params.get(key);
        if (!StringUtils.hasText(value)) {
            return;
        }
        where.append(" AND ").append(key).append(" = ?");
        args.add(parseLong(value, key));
    }

    private void appendContentCondition(StringBuilder where, List<Object> args, Map<String, String> params) {
        String keyword = params == null ? null : params.get("keyword");
        if (!StringUtils.hasText(keyword)) {
            return;
        }
        where.append(" AND content LIKE ?");
        args.add("%" + keyword.trim() + "%");
    }

    private void appendCreateTimeRange(StringBuilder where, List<Object> args, Map<String, String> params) {
        String begin = params == null ? null : params.get("beginCreateTime");
        if (StringUtils.hasText(begin)) {
            where.append(" AND create_time >= ?");
            args.add(begin);
        }
        String end = params == null ? null : params.get("endCreateTime");
        if (StringUtils.hasText(end)) {
            where.append(" AND create_time <= ?");
            args.add(end);
        }
    }

    private Long parseLong(String value, String key) {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException ex) {
            throw invalidParamException("{} must be a number", key);
        }
    }

    private int parsePageNo(Map<String, String> params) {
        return parsePageInt(params == null ? null : params.get("pageNo"), DEFAULT_PAGE_NO);
    }

    private int parsePageSize(Map<String, String> params) {
        int pageSize = parsePageInt(params == null ? null : params.get("pageSize"), DEFAULT_PAGE_SIZE);
        return Math.min(pageSize, MAX_PAGE_SIZE);
    }

    private int parsePageInt(String value, int defaultValue) {
        if (!StringUtils.hasText(value)) {
            return defaultValue;
        }
        try {
            int result = Integer.parseInt(value);
            return result < 1 ? defaultValue : result;
        } catch (NumberFormatException ex) {
            return defaultValue;
        }
    }
}
