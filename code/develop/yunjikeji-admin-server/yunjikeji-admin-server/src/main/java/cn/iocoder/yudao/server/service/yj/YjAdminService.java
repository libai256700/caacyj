package cn.iocoder.yudao.server.service.yj;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.server.service.yj.YjAdminTableRegistry.TableMeta;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcInsert;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.util.UriUtils;

import javax.annotation.Resource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.sql.Timestamp;
import java.util.*;
import java.util.stream.Stream;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
public class YjAdminService {

    private static final String RESOURCE_STUDENT_AUDIT = "student-audit";
    private static final String RESOURCE_ENTERPRISE_AUDIT = "enterprise-audit";
    private static final String RESOURCE_ENTERPRISE_AUDIT_ATTACHMENT = "enterprise-audit-attachment";
    private static final String RESOURCE_COMPANY_ACCOUNT_FRONT = "company-account-front";
    private static final String RESOURCE_ASSESSMENT_QUESTION = "assessment-question";
    private static final String RESOURCE_ASSESSMENT_ANSWER = "assessment-answer";
    private static final String RESOURCE_AGENT = "agent";
    private static final String QWENPAW_AGENT_ID_PREFIX = "feixingxueyuan-";
    private static final String QWENPAW_API_BASE_URL = "http://127.0.0.1:8088";
    private static final String QWENPAW_SOURCE = "qwenpaw：同步自QwenPaw";
    private static final Path QWENPAW_CONFIG_PATH = Paths.get(System.getProperty("user.home"), ".qwenpaw", "config.json");
    private static final List<Path> QWENPAW_WORKSPACE_ROOTS = Arrays.asList(
            Paths.get(System.getProperty("user.home"), ".qwenpaw", "workspaces"),
            Paths.get("E:\\huiyitechworkspace\\QwenPaw\\workspaces"));
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final int CATALOG_TYPE_ASSESSMENT = 1;
    private static final long DEFAULT_ASSESSMENT_CATEGORY_ID = 13L;

    @Resource
    private JdbcTemplate jdbcTemplate;

    private final YjAdminTableRegistry tableRegistry = new YjAdminTableRegistry();

    public Collection<TableMeta> listResources() {
        return tableRegistry.list();
    }

    public PageResult<Map<String, Object>> getPage(String resource, Map<String, String> params) {
        TableMeta meta = tableRegistry.get(resource);
        int pageNo = parseInt(params.get("pageNo"), 1);
        int pageSize = parseInt(params.get("pageSize"), 10);
        if (pageNo < 1 || pageSize < 1 || pageSize > 200) {
            throw invalidParamException("分页参数不正确");
        }

        if (RESOURCE_STUDENT_AUDIT.equals(resource)) {
            return getStudentAuditPage(meta, params, pageNo, pageSize);
        }
        if (RESOURCE_ASSESSMENT_QUESTION.equals(resource)) {
            return getAssessmentQuestionPage(params, pageNo, pageSize);
        }
        if (RESOURCE_ASSESSMENT_ANSWER.equals(resource)) {
            return getAssessmentAnswerPage(params, pageNo, pageSize);
        }

        SqlWhere where = buildWhere(meta, params);
        Long total = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM `" + meta.getTableName() + "`" + where.sql,
                where.args.toArray(), Long.class);
        if (total == null || total == 0) {
            return PageResult.empty(0L);
        }

        List<Object> pageArgs = new ArrayList<>(where.args);
        pageArgs.add((pageNo - 1) * pageSize);
        pageArgs.add(pageSize);
        List<Map<String, Object>> list = jdbcTemplate.queryForList("SELECT * FROM `" + meta.getTableName() + "`"
                + where.sql + " ORDER BY id DESC LIMIT ?, ?", pageArgs.toArray());
        return new PageResult<>(list, total);
    }

    public Map<String, Object> get(String resource, Long id) {
        TableMeta meta = tableRegistry.get(resource);
        if (RESOURCE_STUDENT_AUDIT.equals(resource)) {
            return getStudentAudit(id, meta);
        }
        if (RESOURCE_ASSESSMENT_QUESTION.equals(resource)) {
            return getAssessmentQuestion(id);
        }
        if (RESOURCE_ASSESSMENT_ANSWER.equals(resource)) {
            return getAssessmentAnswer(id);
        }
        List<Map<String, Object>> list = jdbcTemplate.queryForList("SELECT * FROM `" + meta.getTableName()
                + "` WHERE id = ? AND deleted = b'0'", id);
        if (list.isEmpty()) {
            throw invalidParamException("记录不存在：{}", id);
        }
        return list.get(0);
    }

    public Long create(String resource, Map<String, Object> body) {
        TableMeta meta = tableRegistry.get(resource);
        if (RESOURCE_ASSESSMENT_QUESTION.equals(resource)) {
            return createAssessmentQuestion(body);
        }
        if (RESOURCE_ASSESSMENT_ANSWER.equals(resource)) {
            return createAssessmentAnswer(body);
        }
        Map<String, Object> values = toWritableColumns(meta, body, false);
        if (values.isEmpty()) {
            throw invalidParamException("创建内容不能为空");
        }
        fillCreateAuditValues(values, meta);
        Number key = new SimpleJdbcInsert(jdbcTemplate)
                .withTableName(meta.getTableName())
                .usingGeneratedKeyColumns("id")
                .executeAndReturnKey(new MapSqlParameterSource(values));
        return key.longValue();
    }

    public void update(String resource, Map<String, Object> body) {
        TableMeta meta = tableRegistry.get(resource);
        if (RESOURCE_ASSESSMENT_QUESTION.equals(resource)) {
            updateAssessmentQuestion(body);
            return;
        }
        if (RESOURCE_ASSESSMENT_ANSWER.equals(resource)) {
            updateAssessmentAnswer(body);
            return;
        }
        Long id = requireId(body);
        Map<String, Object> values = toWritableColumns(meta, body, true);
        if (values.isEmpty()) {
            throw invalidParamException("更新内容不能为空");
        }
        fillUpdateAuditValues(values);

        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE `").append(meta.getTableName()).append("` SET ");
        int index = 0;
        for (Map.Entry<String, Object> entry : values.entrySet()) {
            if (index++ > 0) {
                sql.append(", ");
            }
            sql.append('`').append(entry.getKey()).append("` = ?");
            args.add(entry.getValue());
        }
        sql.append(" WHERE id = ? AND deleted = b'0'");
        args.add(id);
        int updated = jdbcTemplate.update(sql.toString(), args.toArray());
        if (updated == 0) {
            throw invalidParamException("记录不存在：{}", id);
        }
    }

    public void delete(String resource, Long id) {
        TableMeta meta = tableRegistry.get(resource);
        if (RESOURCE_ASSESSMENT_QUESTION.equals(resource)) {
            deleteAssessmentQuestion(id);
            return;
        }
        if (RESOURCE_ASSESSMENT_ANSWER.equals(resource)) {
            deleteAssessmentAnswer(id);
            return;
        }
        int updated = jdbcTemplate.update("UPDATE `" + meta.getTableName()
                + "` SET deleted = b'1', updater = ?, update_time = ? WHERE id = ? AND deleted = b'0'",
                currentUser(), now(), id);
        if (updated == 0) {
            throw invalidParamException("记录不存在：{}", id);
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> syncQwenPawAgents() {
        int total = 0;
        int created = 0;
        int updated = 0;
        int skipped = 0;
        Set<Path> agentPaths = discoverQwenPawAgentPaths();
        Map<String, Long> existingAgentIds = findQwenPawAgentIds();
        Set<String> syncedAgentIds = new LinkedHashSet<>();

        for (Path agentPath : agentPaths) {
            if (!Files.isRegularFile(agentPath)) {
                skipped++;
                continue;
            }
            Map<String, Object> agent;
            try {
                agent = readQwenPawAgent(agentPath);
            } catch (IOException ex) {
                skipped++;
                continue;
            }
            if (agent == null) {
                skipped++;
                continue;
            }
            String qwenpawAgentId = stringValue(agent.get("id"));
            if (!StringUtils.hasText(qwenpawAgentId)) {
                skipped++;
                continue;
            }
            if (!qwenpawAgentId.startsWith(QWENPAW_AGENT_ID_PREFIX)) {
                skipped++;
                continue;
            }
            if (!syncedAgentIds.add(qwenpawAgentId)) {
                skipped++;
                continue;
            }
            total++;

            Map<String, Object> values = mapQwenPawAgentValues(agent, qwenpawAgentId);
            Long existingId = existingAgentIds.get(qwenpawAgentId);
            if (existingId == null) {
                insertQwenPawAgent(values);
                created++;
            } else {
                updateQwenPawAgent(existingId, values);
                updated++;
            }
        }
        int deleted = deleteMissingQwenPawAgents(syncedAgentIds);
        return mapOf("total", total, "created", created, "updated", updated, "deleted", deleted, "skipped", skipped,
                "sourcePaths", qwenPawSourcePaths());
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> callQwenPawAgent(Map<String, Object> body) {
        String agentId = stringValue(firstPresent(body, "agentId", "agent_id"));
        String question = stringValue(firstPresent(body, "question", "input", "content"));
        if (!StringUtils.hasText(agentId)) {
            throw invalidParamException("agentId 不能为空");
        }
        if (!agentId.startsWith(QWENPAW_AGENT_ID_PREFIX)) {
            throw invalidParamException("仅支持调用 {} 开头的智能体", QWENPAW_AGENT_ID_PREFIX);
        }
        if (!StringUtils.hasText(question)) {
            throw invalidParamException("调用内容不能为空");
        }

        String sessionId = defaultString(firstPresent(body, "sessionId", "session_id"),
                "yj-agent-call-" + System.currentTimeMillis());
        RestTemplate restTemplate = createQwenPawRestTemplate();
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Agent-Id", agentId);

        Map<String, Object> requestBody = mapOf(
                "input", Collections.singletonList(mapOf(
                        "role", "user",
                        "content", Collections.singletonList(mapOf(
                                "type", "text",
                                "text", question)))),
                "session_id", sessionId,
                "user_id", "yj-admin-agent-test",
                "channel", "console",
                "timeout", 120);
        String encodedAgentId = UriUtils.encodePathSegment(agentId, StandardCharsets.UTF_8);
        String taskUrl = QWENPAW_API_BASE_URL + "/api/agents/" + encodedAgentId + "/console/chat/task";
        try {
            ResponseEntity<Map> submitResponse = restTemplate.postForEntity(taskUrl, new HttpEntity<>(requestBody, headers), Map.class);
            Map<String, Object> submitBody = submitResponse.getBody();
            String taskId = stringValue(submitBody == null ? null : submitBody.get("task_id"));
            if (!StringUtils.hasText(taskId)) {
                throw invalidParamException("QwenPaw 未返回任务编号");
            }
            Map<String, Object> taskResult = pollQwenPawTask(restTemplate, headers, encodedAgentId, taskId);
            Map<String, Object> result = (Map<String, Object>) taskResult.get("result");
            if (result == null) {
                throw invalidParamException("QwenPaw 未返回调用结果");
            }
            if ("failed".equals(stringValue(result.get("status")))) {
                Object error = result.get("error");
                throw invalidParamException("QwenPaw 调用失败：{}", extractQwenPawErrorMessage(error));
            }
            return mapOf(
                    "agentId", agentId,
                    "sessionId", result.getOrDefault("session_id", sessionId),
                    "content", extractQwenPawText(result),
                    "raw", result);
        } catch (RestClientException ex) {
            throw invalidParamException("QwenPaw 服务访问失败：{}", ex.getMessage());
        }
    }

    private RestTemplate createQwenPawRestTemplate() {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(5000);
        requestFactory.setReadTimeout(15000);
        return new RestTemplate(requestFactory);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> pollQwenPawTask(RestTemplate restTemplate, HttpHeaders headers,
                                                String encodedAgentId, String taskId) {
        String taskResultUrl = QWENPAW_API_BASE_URL + "/api/agents/" + encodedAgentId
                + "/console/chat/task/" + UriUtils.encodePathSegment(taskId, StandardCharsets.UTF_8);
        for (int i = 0; i < 80; i++) {
            ResponseEntity<Map> response = restTemplate.exchange(taskResultUrl, org.springframework.http.HttpMethod.GET,
                    new HttpEntity<>(headers), Map.class);
            Map<String, Object> body = response.getBody();
            if (body != null && "finished".equals(stringValue(body.get("status")))) {
                return body;
            }
            sleepQuietly(1500);
        }
        throw invalidParamException("QwenPaw 调用超时");
    }

    private void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw invalidParamException("QwenPaw 调用被中断");
        }
    }

    @SuppressWarnings("unchecked")
    private String extractQwenPawText(Map<String, Object> result) {
        Object output = result.get("output");
        if (output instanceof Collection) {
            StringBuilder builder = new StringBuilder();
            for (Object item : (Collection<?>) output) {
                if (item instanceof Map) {
                    Object content = ((Map<String, Object>) item).get("content");
                    appendQwenPawContent(builder, content);
                }
            }
            String text = builder.toString().trim();
            if (StringUtils.hasText(text)) {
                return text;
            }
        }
        Object content = result.get("content");
        if (content != null) {
            return String.valueOf(content);
        }
        return toJson(result);
    }

    @SuppressWarnings("unchecked")
    private void appendQwenPawContent(StringBuilder builder, Object content) {
        if (content instanceof String) {
            appendLine(builder, (String) content);
            return;
        }
        if (content instanceof Collection) {
            for (Object part : (Collection<?>) content) {
                if (part instanceof Map) {
                    Object text = ((Map<String, Object>) part).get("text");
                    if (text != null) {
                        appendLine(builder, String.valueOf(text));
                    }
                } else if (part != null) {
                    appendLine(builder, String.valueOf(part));
                }
            }
        }
    }

    private void appendLine(StringBuilder builder, String text) {
        if (!StringUtils.hasText(text)) {
            return;
        }
        if (builder.length() > 0) {
            builder.append('\n');
        }
        builder.append(text);
    }

    @SuppressWarnings("unchecked")
    private String extractQwenPawErrorMessage(Object error) {
        if (error instanceof Map) {
            Object message = ((Map<String, Object>) error).get("message");
            if (message != null) {
                return String.valueOf(message);
            }
        }
        return error == null ? "未知错误" : String.valueOf(error);
    }

    private String toJson(Object value) {
        try {
            return OBJECT_MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(value);
        } catch (IOException ex) {
            return String.valueOf(value);
        }
    }

    private Set<Path> discoverQwenPawAgentPaths() {
        Set<Path> agentPaths = new LinkedHashSet<>();
        addQwenPawConfigAgentPaths(agentPaths);
        for (Path workspaceRoot : QWENPAW_WORKSPACE_ROOTS) {
            addQwenPawWorkspaceRootAgentPaths(agentPaths, workspaceRoot);
        }
        return agentPaths;
    }

    private void addQwenPawConfigAgentPaths(Set<Path> agentPaths) {
        if (!Files.isRegularFile(QWENPAW_CONFIG_PATH)) {
            return;
        }
        try {
            Map<String, Object> config = OBJECT_MAPPER.readValue(QWENPAW_CONFIG_PATH.toFile(),
                    new TypeReference<Map<String, Object>>() {
                    });
            Object agentsValue = config.get("agents");
            if (!(agentsValue instanceof Map)) {
                return;
            }
            Map<?, ?> agents = (Map<?, ?>) agentsValue;
            Object profilesValue = agents.get("profiles");
            if (!(profilesValue instanceof Map)) {
                return;
            }
            Map<?, ?> profiles = (Map<?, ?>) profilesValue;
            Object orderValue = agents.get("agent_order");
            if (orderValue instanceof Collection) {
                for (Object profileId : (Collection<?>) orderValue) {
                    addQwenPawProfileAgentPath(agentPaths, profiles.get(String.valueOf(profileId)));
                }
            }
            for (Object profile : profiles.values()) {
                addQwenPawProfileAgentPath(agentPaths, profile);
            }
        } catch (IOException ex) {
            // Fall back to workspace root scanning when QwenPaw config cannot be read.
        }
    }

    private void addQwenPawProfileAgentPath(Set<Path> agentPaths, Object profileValue) {
        if (!(profileValue instanceof Map)) {
            return;
        }
        String workspaceDir = stringValue(((Map<?, ?>) profileValue).get("workspace_dir"));
        if (!StringUtils.hasText(workspaceDir)) {
            return;
        }
        agentPaths.add(Paths.get(workspaceDir).resolve("agent.json").normalize());
    }

    private void addQwenPawWorkspaceRootAgentPaths(Set<Path> agentPaths, Path workspaceRoot) {
        if (!Files.isDirectory(workspaceRoot)) {
            return;
        }
        try (Stream<Path> workspaceStream = Files.list(workspaceRoot)) {
            Iterator<Path> iterator = workspaceStream.iterator();
            while (iterator.hasNext()) {
                Path agentPath = iterator.next().resolve("agent.json");
                if (Files.isRegularFile(agentPath)) {
                    agentPaths.add(agentPath.normalize());
                }
            }
        } catch (IOException ex) {
            // Ignore a single unreadable root; other configured roots can still be synced.
        }
    }

    private List<String> qwenPawSourcePaths() {
        List<String> sourcePaths = new ArrayList<>();
        if (Files.isRegularFile(QWENPAW_CONFIG_PATH)) {
            sourcePaths.add(QWENPAW_CONFIG_PATH.toString());
        }
        for (Path workspaceRoot : QWENPAW_WORKSPACE_ROOTS) {
            if (Files.isDirectory(workspaceRoot)) {
                sourcePaths.add(workspaceRoot.toString());
            }
        }
        return sourcePaths;
    }

    private Map<String, Object> readQwenPawAgent(Path agentPath) throws IOException {
        return OBJECT_MAPPER.readValue(agentPath.toFile(), new TypeReference<Map<String, Object>>() {
        });
    }

    private Map<String, Object> mapQwenPawAgentValues(Map<String, Object> agent, String qwenpawAgentId) {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("agent_id", qwenpawAgentId);
        values.put("name", defaultString(agent.get("name"), qwenpawAgentId));
        values.put("knowledge_base_id", null);
        values.put("prompt_config", defaultString(agent.get("description"), ""));
        values.put("reply_strategy", QWENPAW_SOURCE);
        values.put("status", Boolean.TRUE);
        values.put("remark", defaultString(agent.get("description"), ""));
        values.put("tenant_id", 1L);
        values.put("deleted", Boolean.FALSE);
        return values;
    }

    private Map<String, Long> findQwenPawAgentIds() {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("SELECT id, agent_id FROM yj_agent_info "
                        + "WHERE agent_id LIKE ? ORDER BY deleted ASC, id ASC",
                QWENPAW_AGENT_ID_PREFIX + "%");
        Map<String, Long> ids = new LinkedHashMap<>();
        for (Map<String, Object> row : rows) {
            String agentId = stringValue(row.get("agent_id"));
            Long id = optionalLong(row.get("id"));
            if (StringUtils.hasText(agentId) && id != null) {
                ids.putIfAbsent(agentId, id);
            }
        }
        return ids;
    }

    private void insertQwenPawAgent(Map<String, Object> values) {
        fillCreateAuditValues(values, tableRegistry.get(RESOURCE_AGENT));
        new SimpleJdbcInsert(jdbcTemplate)
                .withTableName("yj_agent_info")
                .usingGeneratedKeyColumns("id")
                .execute(new MapSqlParameterSource(values));
    }

    private void updateQwenPawAgent(Long id, Map<String, Object> values) {
        fillUpdateAuditValues(values);
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE yj_agent_info SET ");
        appendSetSql(sql, args, values);
        sql.append(" WHERE id = ?");
        args.add(id);
        jdbcTemplate.update(sql.toString(), args.toArray());
    }

    private int deleteMissingQwenPawAgents(Set<String> currentAgentIds) {
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE yj_agent_info SET deleted = b'1', updater = ?, update_time = ? "
                + "WHERE deleted = b'0' AND reply_strategy = ? AND agent_id LIKE ?");
        args.add(currentUser());
        args.add(now());
        args.add(QWENPAW_SOURCE);
        args.add(QWENPAW_AGENT_ID_PREFIX + "%");
        if (!currentAgentIds.isEmpty()) {
            sql.append(" AND agent_id NOT IN (");
            appendPlaceholders(sql, args, currentAgentIds);
            sql.append(")");
        }
        return jdbcTemplate.update(sql.toString(), args.toArray());
    }

    @Transactional(rollbackFor = Exception.class)
    public void publishAgreementDetail(Map<String, Object> body) {
        Long id = requireId(body);
        Map<String, Object> detail = get("agreement-detail", id);
        Object agreementInfoId = detail.get("agreement_info_id");
        if (agreementInfoId == null) {
            throw invalidParamException("协议详情缺少协议编号：{}", id);
        }
        Timestamp now = now();
        jdbcTemplate.update("UPDATE yj_agreement_detail_info SET publish_status = 2, updater = ?, update_time = ? "
                        + "WHERE agreement_info_id = ? AND deleted = b'0'",
                currentUser(), now, agreementInfoId);
        jdbcTemplate.update("UPDATE yj_agreement_detail_info SET publish_status = 1, publish_time = ?, updater = ?, "
                        + "update_time = ? WHERE id = ? AND deleted = b'0'",
                now, currentUser(), now, id);
    }


    private PageResult<Map<String, Object>> getStudentAuditPage(TableMeta meta, Map<String, String> params,
                                                               int pageNo, int pageSize) {
        SqlWhere where = buildStudentAuditWhere(params);
        Long total = jdbcTemplate.queryForObject("SELECT COUNT(1) " + getStudentAuditFromSql(meta) + where.sql,
                where.args.toArray(), Long.class);
        if (total == null || total == 0) {
            return PageResult.empty(0L);
        }

        List<Object> pageArgs = new ArrayList<>(where.args);
        pageArgs.add((pageNo - 1) * pageSize);
        pageArgs.add(pageSize);
        List<Map<String, Object>> list = jdbcTemplate.queryForList("SELECT a.*, ci.id AS customer_info_id, "
                        + "COALESCE(NULLIF(t.name, ''), NULLIF(ai.name, ''), '') AS company_name, "
                        + "COALESCE(NULLIF(ci.mobile_phone, ''), NULLIF(ca.mobile, ''), '') AS mobile_phone, "
                        + "COALESCE(NULLIF(ci.real_name, ''), NULLIF(ci.nick_name, ''), ca.username, ca.mobile, '') AS student_name "
                        + getStudentAuditFromSql(meta)
                        + where.sql + " ORDER BY a.id DESC LIMIT ?, ?",
                pageArgs.toArray());
        return new PageResult<>(list, total);
    }

    private Map<String, Object> getStudentAudit(Long id, TableMeta meta) {
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("SELECT a.*, ci.id AS customer_info_id, ")
                .append("COALESCE(NULLIF(t.name, ''), NULLIF(ai.name, ''), '') AS company_name, ")
                .append("COALESCE(NULLIF(ci.mobile_phone, ''), NULLIF(ca.mobile, ''), '') AS mobile_phone, ")
                .append("COALESCE(NULLIF(ci.real_name, ''), NULLIF(ci.nick_name, ''), ca.username, ca.mobile, '') AS student_name ")
                .append(getStudentAuditFromSql(meta))
                .append(" WHERE a.id = ? AND a.deleted = b'0'");
        args.add(id);
        Long tenantId = TenantContextHolder.getTenantId();
        if (tenantId != null) {
            sql.append(" AND a.company_id = ?");
            args.add(tenantId);
        }
        List<Map<String, Object>> list = jdbcTemplate.queryForList(sql.toString(), args.toArray());
        if (list.isEmpty()) {
            throw invalidParamException("记录不存在：{}", id);
        }
        return list.get(0);
    }

    private String getStudentAuditFromSql(TableMeta meta) {
        return "FROM `" + meta.getTableName() + "` a "
                + "LEFT JOIN system_tenant t ON t.id = a.company_id AND t.deleted = b'0' "
                + "LEFT JOIN (SELECT tenant_id, MAX(name) AS name FROM yj_audit_info "
                + "WHERE deleted = b'0' GROUP BY tenant_id) ai ON ai.tenant_id = a.company_id "
                + "LEFT JOIN yj_customer_account ca ON ca.id = a.customer_account_id AND ca.deleted = b'0' "
                + "LEFT JOIN yj_customer_info ci ON ci.customer_account_id = a.customer_account_id AND ci.deleted = b'0'";
    }

    private PageResult<Map<String, Object>> getAssessmentQuestionPage(Map<String, String> params,
                                                                      int pageNo, int pageSize) {
        SqlWhere where = buildAssessmentQuestionWhere(params);
        Long total = jdbcTemplate.queryForObject("SELECT COUNT(1) " + getAssessmentQuestionFromSql() + where.sql,
                where.args.toArray(), Long.class);
        if (total == null || total == 0) {
            return PageResult.empty(0L);
        }

        List<Object> pageArgs = new ArrayList<>(where.args);
        pageArgs.add((pageNo - 1) * pageSize);
        pageArgs.add(pageSize);
        List<Map<String, Object>> list = jdbcTemplate.queryForList("SELECT e.id, e.question_stem AS title, "
                        + "e.question_type, e.question_stem AS question_content, e.question_status AS status, "
                        + "e.is_required, e.step_id, e.sort_no, e.creator, e.create_time, e.updater, e.update_time, "
                        + "e.category_id, e.score, e.correct_memo, s.step_name AS step_name "
                        + getAssessmentQuestionFromSql()
                        + where.sql + " ORDER BY e.sort_no ASC, e.id ASC LIMIT ?, ?",
                pageArgs.toArray());
        return new PageResult<>(list, total);
    }

    private Map<String, Object> getAssessmentQuestion(Long id) {
        SqlWhere where = new SqlWhere();
        where.sql.append(" WHERE e.id = ? AND e.deleted = b'0' AND c.deleted = b'0' AND c.catalog_type = ?");
        where.args.add(id);
        where.args.add(CATALOG_TYPE_ASSESSMENT);
        List<Map<String, Object>> list = jdbcTemplate.queryForList("SELECT e.id, e.question_stem AS title, "
                        + "e.question_type, e.question_stem AS question_content, e.question_status AS status, "
                        + "e.is_required, e.step_id, e.sort_no, e.creator, e.create_time, e.updater, e.update_time, "
                        + "e.category_id, e.score, e.correct_memo, s.step_name AS step_name "
                        + getAssessmentQuestionFromSql() + where.sql,
                where.args.toArray());
        if (list.isEmpty()) {
            throw invalidParamException("璁板綍涓嶅瓨鍦細{}", id);
        }
        return list.get(0);
    }

    private Long createAssessmentQuestion(Map<String, Object> body) {
        Map<String, Object> values = mapAssessmentQuestionValues(body, false);
        fillCreateAuditValues(values, null);
        putIfAbsent(values, "category_id", DEFAULT_ASSESSMENT_CATEGORY_ID);
        validateAssessmentCategory(values);
        Number key = new SimpleJdbcInsert(jdbcTemplate)
                .withTableName("yj_practice_exercises")
                .usingGeneratedKeyColumns("id")
                .executeAndReturnKey(new MapSqlParameterSource(values));
        return key.longValue();
    }

    private void updateAssessmentQuestion(Map<String, Object> body) {
        Long id = requireId(body);
        Map<String, Object> values = mapAssessmentQuestionValues(body, true);
        if (values.isEmpty()) {
            throw invalidParamException("鏇存柊鍐呭涓嶈兘涓虹┖");
        }
        validateAssessmentCategory(values);
        fillUpdateAuditValues(values);
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE yj_practice_exercises SET ");
        appendSetSql(sql, args, values);
        sql.append(" WHERE id = ? AND deleted = b'0' AND category_id IN (")
                .append(assessmentCategorySubquery()).append(")");
        args.add(id);
        if (jdbcTemplate.update(sql.toString(), args.toArray()) == 0) {
            throw invalidParamException("璁板綍涓嶅瓨鍦細{}", id);
        }
    }

    private void deleteAssessmentQuestion(Long id) {
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE yj_practice_exercises SET deleted = b'1', updater = ?, update_time = ? "
                + "WHERE id = ? AND deleted = b'0' AND category_id IN (" + assessmentCategorySubquery() + ")");
        args.add(currentUser());
        args.add(now());
        args.add(id);
        if (jdbcTemplate.update(sql.toString(), args.toArray()) == 0) {
            throw invalidParamException("璁板綍涓嶅瓨鍦細{}", id);
        }
    }

    private PageResult<Map<String, Object>> getAssessmentAnswerPage(Map<String, String> params,
                                                                    int pageNo, int pageSize) {
        SqlWhere where = buildAssessmentAnswerWhere(params);
        Long total = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM yj_practice_exercises_answer a "
                        + "JOIN yj_practice_exercises e ON e.id = a.exercises_id "
                        + "JOIN yj_practice_category c ON c.id = e.category_id" + where.sql,
                where.args.toArray(), Long.class);
        if (total == null || total == 0) {
            return PageResult.empty(0L);
        }

        List<Object> pageArgs = new ArrayList<>(where.args);
        pageArgs.add((pageNo - 1) * pageSize);
        pageArgs.add(pageSize);
        List<Map<String, Object>> list = jdbcTemplate.queryForList("SELECT a.id, a.exercises_id AS question_id, "
                        + "a.question_type, a.answer_code, a.answer_content, a.is_correct, a.sort_no, "
                        + "a.creator, a.create_time, a.updater, a.update_time "
                        + "FROM yj_practice_exercises_answer a "
                        + "JOIN yj_practice_exercises e ON e.id = a.exercises_id "
                        + "JOIN yj_practice_category c ON c.id = e.category_id"
                        + where.sql + " ORDER BY a.id DESC LIMIT ?, ?",
                pageArgs.toArray());
        return new PageResult<>(list, total);
    }

    private Map<String, Object> getAssessmentAnswer(Long id) {
        SqlWhere where = new SqlWhere();
        where.sql.append(" WHERE a.id = ? AND a.deleted = b'0' AND e.deleted = b'0' "
                + "AND c.deleted = b'0' AND c.catalog_type = ?");
        where.args.add(id);
        where.args.add(CATALOG_TYPE_ASSESSMENT);
        List<Map<String, Object>> list = jdbcTemplate.queryForList("SELECT a.id, a.exercises_id AS question_id, "
                        + "a.question_type, a.answer_code, a.answer_content, a.is_correct, a.sort_no, "
                        + "a.creator, a.create_time, a.updater, a.update_time "
                        + "FROM yj_practice_exercises_answer a "
                        + "JOIN yj_practice_exercises e ON e.id = a.exercises_id "
                        + "JOIN yj_practice_category c ON c.id = e.category_id" + where.sql,
                where.args.toArray());
        if (list.isEmpty()) {
            throw invalidParamException("璁板綍涓嶅瓨鍦細{}", id);
        }
        return list.get(0);
    }

    private Long createAssessmentAnswer(Map<String, Object> body) {
        Long exercisesId = requireLong(body, "question_id");
        String questionType = getEntryAssessmentQuestionType(exercisesId);
        Map<String, Object> values = mapAssessmentAnswerValues(body, false);
        values.put("exercises_id", exercisesId);
        if (!StringUtils.hasText(String.valueOf(values.get("question_type")))) {
            values.put("question_type", questionType);
        }
        fillCreateAuditValues(values, null);
        Number key = new SimpleJdbcInsert(jdbcTemplate)
                .withTableName("yj_practice_exercises_answer")
                .usingGeneratedKeyColumns("id")
                .executeAndReturnKey(new MapSqlParameterSource(values));
        return key.longValue();
    }

    private void updateAssessmentAnswer(Map<String, Object> body) {
        Long id = requireId(body);
        Map<String, Object> values = mapAssessmentAnswerValues(body, true);
        Object questionId = firstPresent(body, "question_id", "questionId");
        if (questionId != null) {
            Long exercisesId;
            try {
                exercisesId = questionId instanceof Number
                        ? ((Number) questionId).longValue() : Long.parseLong(String.valueOf(questionId));
            } catch (NumberFormatException ex) {
                throw invalidParamException("question_id must be a number");
            }
            String questionType = getEntryAssessmentQuestionType(exercisesId);
            values.put("exercises_id", exercisesId);
            if (!values.containsKey("question_type")) {
                values.put("question_type", questionType);
            }
        }
        if (values.isEmpty()) {
            throw invalidParamException("鏇存柊鍐呭涓嶈兘涓虹┖");
        }
        fillUpdateAuditValues(values);
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE yj_practice_exercises_answer a "
                + "JOIN yj_practice_exercises e ON e.id = a.exercises_id SET ");
        appendSetSql(sql, args, values, "a");
        sql.append(" WHERE a.id = ? AND a.deleted = b'0' AND e.deleted = b'0' AND e.category_id IN (")
                .append(assessmentCategorySubquery()).append(")");
        args.add(id);
        if (jdbcTemplate.update(sql.toString(), args.toArray()) == 0) {
            throw invalidParamException("璁板綍涓嶅瓨鍦細{}", id);
        }
    }

    private void deleteAssessmentAnswer(Long id) {
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE yj_practice_exercises_answer a "
                + "JOIN yj_practice_exercises e ON e.id = a.exercises_id "
                + "SET a.deleted = b'1', a.updater = ?, a.update_time = ? "
                + "WHERE a.id = ? AND a.deleted = b'0' AND e.deleted = b'0' AND e.category_id IN ("
                + assessmentCategorySubquery() + ")");
        args.add(currentUser());
        args.add(now());
        args.add(id);
        if (jdbcTemplate.update(sql.toString(), args.toArray()) == 0) {
            throw invalidParamException("璁板綍涓嶅瓨鍦細{}", id);
        }
    }

    private SqlWhere buildStudentAuditWhere(Map<String, String> params) {
        SqlWhere where = new SqlWhere();
        where.sql.append(" WHERE a.deleted = b'0'");
        Long tenantId = TenantContextHolder.getTenantId();
        if (tenantId != null) {
            where.sql.append(" AND a.company_id = ?");
            where.args.add(tenantId);
        }

        for (Map.Entry<String, String> entry : params.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();
            if (!StringUtils.hasText(value) || "pageNo".equals(key) || "pageSize".equals(key)) {
                continue;
            }
            if ("keyword".equals(key)) {
                where.sql.append(" AND (t.name LIKE ? OR ci.real_name LIKE ? OR ci.nick_name LIKE ? "
                        + "OR ci.mobile_phone LIKE ? OR ca.username LIKE ? OR ca.mobile LIKE ?)");
                appendLikeArgs(where, value, 6);
                continue;
            }
            if ("beginCreateTime".equals(key) || "endCreateTime".equals(key)) {
                continue;
            }
            String column = toSnakeCase(key);
            if ("company_name".equals(column)) {
                where.sql.append(" AND t.name LIKE ?");
                where.args.add("%" + value + "%");
            } else if ("student_name".equals(column)) {
                where.sql.append(" AND (ci.real_name LIKE ? OR ci.nick_name LIKE ? OR ci.mobile_phone LIKE ? "
                        + "OR ca.username LIKE ? OR ca.mobile LIKE ?)");
                appendLikeArgs(where, value, 5);
            } else if ("mobile_phone".equals(column)) {
                where.sql.append(" AND (ci.mobile_phone LIKE ? OR ca.mobile LIKE ?)");
                appendLikeArgs(where, value, 2);
            } else if ("id".equals(column) || "create_time".equals(column) || "update_time".equals(column)
                    || "company_id".equals(column) || "user_id".equals(column) || "customer_account_id".equals(column)
                    || "audit_status".equals(column) || "audit_reason".equals(column) || "audit_time".equals(column)
                    || "tenant_id".equals(column)) {
                where.sql.append(" AND a.`").append(column).append("` = ?");
                where.args.add(value);
            }
        }
        appendAliasedCreateTimeRange(where, params, "a");
        return where;
    }

    private SqlWhere buildAssessmentQuestionWhere(Map<String, String> params) {
        SqlWhere where = new SqlWhere();
        where.sql.append(" WHERE e.deleted = b'0' AND c.deleted = b'0' AND c.catalog_type = ?");
        where.args.add(CATALOG_TYPE_ASSESSMENT);
        for (Map.Entry<String, String> entry : params.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();
            if (!StringUtils.hasText(value) || "pageNo".equals(key) || "pageSize".equals(key)) {
                continue;
            }
            if ("keyword".equals(key)) {
                where.sql.append(" AND (e.question_stem LIKE ? OR e.question_type LIKE ?)");
                appendLikeArgs(where, value, 2);
                continue;
            }
            if ("beginCreateTime".equals(key) || "endCreateTime".equals(key)) {
                continue;
            }
            String column = toAssessmentQuestionColumn(key);
            if (column == null) {
                continue;
            }
            if ("question_stem".equals(column) || "question_type".equals(column) || "correct_memo".equals(column)) {
                where.sql.append(" AND e.").append(column).append(" LIKE ?");
                where.args.add("%" + value + "%");
            } else {
                where.sql.append(" AND e.").append(column).append(" = ?");
                where.args.add(value);
            }
        }
        appendAliasedCreateTimeRange(where, params, "e");
        return where;
    }

    private SqlWhere buildAssessmentAnswerWhere(Map<String, String> params) {
        SqlWhere where = new SqlWhere();
        where.sql.append(" WHERE a.deleted = b'0' AND e.deleted = b'0' AND c.deleted = b'0' AND c.catalog_type = ?");
        where.args.add(CATALOG_TYPE_ASSESSMENT);
        for (Map.Entry<String, String> entry : params.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();
            if (!StringUtils.hasText(value) || "pageNo".equals(key) || "pageSize".equals(key)) {
                continue;
            }
            if ("keyword".equals(key)) {
                where.sql.append(" AND (a.answer_code LIKE ? OR a.answer_content LIKE ?)");
                appendLikeArgs(where, value, 2);
                continue;
            }
            if ("beginCreateTime".equals(key) || "endCreateTime".equals(key)) {
                continue;
            }
            String column = toAssessmentAnswerColumn(key);
            if (column == null) {
                continue;
            }
            if ("answer_code".equals(column) || "answer_content".equals(column)) {
                where.sql.append(" AND a.").append(column).append(" LIKE ?");
                where.args.add("%" + value + "%");
            } else {
                where.sql.append(" AND a.").append(column).append(" = ?");
                where.args.add(value);
            }
        }
        appendAliasedCreateTimeRange(where, params, "a");
        return where;
    }

    private SqlWhere buildWhere(TableMeta meta, Map<String, String> params) {
        SqlWhere where = new SqlWhere();
        where.sql.append(" WHERE deleted = b'0'");
        Long tenantId = shouldIgnoreTenantFilter(meta) ? null : TenantContextHolder.getTenantId();
        if (tenantId != null && meta.isColumn("tenant_id")) {
            where.sql.append(" AND tenant_id = ?");
            where.args.add(tenantId);
        }

        for (Map.Entry<String, String> entry : params.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();
            if (!StringUtils.hasText(value) || "pageNo".equals(key) || "pageSize".equals(key)) {
                continue;
            }
            if ("keyword".equals(key)) {
                appendKeywordWhere(meta, where, value);
                continue;
            }
            if ("beginCreateTime".equals(key) || "endCreateTime".equals(key)) {
                continue;
            }
            String column = toSnakeCase(key);
            if (!meta.isColumn(column)) {
                continue;
            }
            if (meta.isLikeColumn(column)) {
                where.sql.append(" AND `").append(column).append("` LIKE ?");
                where.args.add("%" + value + "%");
            } else {
                where.sql.append(" AND `").append(column).append("` = ?");
                where.args.add(value);
            }
        }
        appendCreateTimeRange(where, params);
        return where;
    }

    private void appendKeywordWhere(TableMeta meta, SqlWhere where, String keyword) {
        List<String> likeColumns = new ArrayList<>();
        for (String column : meta.getColumns()) {
            if (meta.isLikeColumn(column)) {
                likeColumns.add(column);
            }
        }
        if (likeColumns.isEmpty()) {
            return;
        }
        where.sql.append(" AND (");
        for (int i = 0; i < likeColumns.size(); i++) {
            if (i > 0) {
                where.sql.append(" OR ");
            }
            where.sql.append('`').append(likeColumns.get(i)).append("` LIKE ?");
            where.args.add("%" + keyword + "%");
        }
        where.sql.append(')');
    }

    private void appendCreateTimeRange(SqlWhere where, Map<String, String> params) {
        appendAliasedCreateTimeRange(where, params, null);
    }

    private void appendAliasedCreateTimeRange(SqlWhere where, Map<String, String> params, String alias) {
        String prefix = StringUtils.hasText(alias) ? alias + "." : "";
        String begin = params.get("beginCreateTime");
        if (StringUtils.hasText(begin)) {
            where.sql.append(" AND ").append(prefix).append("create_time >= ?");
            where.args.add(begin);
        }
        String end = params.get("endCreateTime");
        if (StringUtils.hasText(end)) {
            where.sql.append(" AND ").append(prefix).append("create_time <= ?");
            where.args.add(end);
        }
    }

    private void appendLikeArgs(SqlWhere where, String value, int count) {
        for (int i = 0; i < count; i++) {
            where.args.add("%" + value + "%");
        }
    }

    private Map<String, Object> toWritableColumns(TableMeta meta, Map<String, Object> body, boolean update) {
        Map<String, Object> values = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : body.entrySet()) {
            String column = toSnakeCase(entry.getKey());
            if ("id".equals(column)) {
                continue;
            }
            if (!meta.isWritableColumn(column)) {
                if (update || entry.getValue() != null) {
                    continue;
                }
            }
            if (meta.isWritableColumn(column)) {
                values.put(column, entry.getValue());
            }
        }
        return values;
    }

    private Map<String, Object> mapAssessmentQuestionValues(Map<String, Object> body, boolean update) {
        Map<String, Object> values = new LinkedHashMap<>();
        putMappedValue(values, body, "question_stem", "title", "questionContent", "question_content", "questionStem", "question_stem");
        putMappedValue(values, body, "question_type", "questionType", "question_type");
        putMappedValue(values, body, "question_status", "status", "questionStatus", "question_status");
        putMappedValue(values, body, "is_required", "isRequired", "is_required");
        putMappedValue(values, body, "step_id", "stepId", "step_id");
        putMappedValue(values, body, "category_id", "categoryId", "category_id");
        putMappedValue(values, body, "sort_no", "sortNo", "sort_no");
        putMappedValue(values, body, "score", "score");
        putMappedValue(values, body, "correct_memo", "correctMemo", "correct_memo");
        if (!update) {
            putIfAbsent(values, "question_status", Boolean.TRUE);
            putIfAbsent(values, "is_required", Boolean.TRUE);
            putIfAbsent(values, "score", 0);
            putIfAbsent(values, "sort_no", 0);
        }
        if (!update && !values.containsKey("question_stem")) {
            throw invalidParamException("棰樼洰鍐呭涓嶈兘涓虹┖");
        }
        if (!update && !values.containsKey("question_type")) {
            throw invalidParamException("棰樺瀷涓嶈兘涓虹┖");
        }
        return values;
    }

    private Map<String, Object> mapAssessmentAnswerValues(Map<String, Object> body, boolean update) {
        Map<String, Object> values = new LinkedHashMap<>();
        putMappedValue(values, body, "question_type", "questionType", "question_type");
        putMappedValue(values, body, "answer_code", "answerCode", "answer_code");
        putMappedValue(values, body, "answer_content", "answerContent", "answer_content");
        putMappedValue(values, body, "is_correct", "isCorrect", "is_correct");
        putMappedValue(values, body, "sort_no", "sortNo", "sort_no");
        if (!update) {
            putIfAbsent(values, "question_type", "");
            putIfAbsent(values, "is_correct", Boolean.FALSE);
            putIfAbsent(values, "sort_no", 0);
        }
        if (!update && !values.containsKey("answer_content")) {
            throw invalidParamException("绛旀鍐呭涓嶈兘涓虹┖");
        }
        return values;
    }

    private void putMappedValue(Map<String, Object> values, Map<String, Object> body, String column, String... keys) {
        Object value = firstPresent(body, keys);
        if (value != null) {
            values.put(column, value);
        }
    }

    private String toAssessmentQuestionColumn(String key) {
        String column = toSnakeCase(key);
        if ("title".equals(column) || "question_content".equals(column)) {
            return "question_stem";
        }
        if ("status".equals(column)) {
            return "question_status";
        }
        if ("id".equals(column) || "step_id".equals(column) || "question_stem".equals(column) || "question_type".equals(column)
                || "question_status".equals(column) || "is_required".equals(column) || "score".equals(column) || "sort_no".equals(column)
                || "correct_memo".equals(column) || "create_time".equals(column)
                || "update_time".equals(column)) {
            return column;
        }
        return null;
    }

    private String toAssessmentAnswerColumn(String key) {
        String column = toSnakeCase(key);
        if ("question_id".equals(column)) {
            return "exercises_id";
        }
        if ("id".equals(column) || "exercises_id".equals(column) || "question_type".equals(column)
                || "answer_code".equals(column) || "answer_content".equals(column) || "is_correct".equals(column)
                || "sort_no".equals(column) || "create_time".equals(column)
                || "update_time".equals(column)) {
            return column;
        }
        return null;
    }

    private void assertEntryAssessmentQuestion(Long exercisesId) {
        getEntryAssessmentQuestionType(exercisesId);
    }

    private String getEntryAssessmentQuestionType(Long exercisesId) {
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("SELECT question_type FROM yj_practice_exercises "
                + "WHERE id = ? AND category_id IN (" + assessmentCategorySubquery() + ") AND deleted = b'0'");
        args.add(exercisesId);
        List<String> list = jdbcTemplate.queryForList(sql.toString(), args.toArray(), String.class);
        if (list.isEmpty()) {
            throw invalidParamException("鑷祴棰樼洰涓嶅瓨鍦細{}", exercisesId);
        }
        return list.get(0);
    }

    private String getAssessmentQuestionFromSql() {
        return "FROM yj_practice_exercises e "
                + "JOIN yj_practice_category c ON c.id = e.category_id "
                + "LEFT JOIN yj_practice_step s ON s.id = e.step_id AND s.category_id = e.category_id "
                + "AND s.deleted = b'0' ";
    }

    private String assessmentCategorySubquery() {
        return "SELECT id FROM yj_practice_category WHERE deleted = b'0' AND catalog_type = " + CATALOG_TYPE_ASSESSMENT;
    }

    private void validateAssessmentCategory(Map<String, Object> values) {
        Object categoryId = values.get("category_id");
        if (categoryId == null) {
            return;
        }
        Long id;
        try {
            id = categoryId instanceof Number ? ((Number) categoryId).longValue() : Long.parseLong(String.valueOf(categoryId));
        } catch (NumberFormatException ex) {
            throw invalidParamException("category_id must be a number");
        }
        Integer count = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM yj_practice_category "
                + "WHERE id = ? AND deleted = b'0' AND catalog_type = ?", Integer.class, id, CATALOG_TYPE_ASSESSMENT);
        if (count == null || count == 0) {
            throw invalidParamException("自测题分类不合法：{}", id);
        }
    }

    private void appendSetSql(StringBuilder sql, List<Object> args, Map<String, Object> values) {
        appendSetSql(sql, args, values, null);
    }

    private void appendSetSql(StringBuilder sql, List<Object> args, Map<String, Object> values, String alias) {
        int index = 0;
        for (Map.Entry<String, Object> entry : values.entrySet()) {
            if (index++ > 0) {
                sql.append(", ");
            }
            if (StringUtils.hasText(alias)) {
                sql.append(alias).append(".");
            }
            sql.append('`').append(entry.getKey()).append("` = ?");
            args.add(entry.getValue());
        }
    }

    private void appendPlaceholders(StringBuilder sql, List<Object> args, Collection<?> values) {
        int index = 0;
        for (Object value : values) {
            if (index++ > 0) {
                sql.append(", ");
            }
            sql.append("?");
            args.add(value);
        }
    }

    private void fillCreateAuditValues(Map<String, Object> values, TableMeta meta) {
        Timestamp now = now();
        String user = currentUser();
        putIfAbsent(values, "creator", user);
        putIfAbsent(values, "updater", user);
        putIfAbsent(values, "create_time", now);
        putIfAbsent(values, "update_time", now);
        putIfAbsent(values, "deleted", Boolean.FALSE);
        Long tenantId = shouldIgnoreTenantFill(meta) || meta == null || !meta.isWritableColumn("tenant_id")
                ? null : TenantContextHolder.getTenantId();
        if (tenantId != null) {
            putIfAbsent(values, "tenant_id", tenantId);
        }
    }

    private boolean shouldIgnoreTenantFilter(TableMeta meta) {
        return RESOURCE_ENTERPRISE_AUDIT.equals(meta.getResource())
                || RESOURCE_ENTERPRISE_AUDIT_ATTACHMENT.equals(meta.getResource())
                || RESOURCE_COMPANY_ACCOUNT_FRONT.equals(meta.getResource());
    }

    private boolean shouldIgnoreTenantFill(TableMeta meta) {
        return meta != null
                && (RESOURCE_ENTERPRISE_AUDIT.equals(meta.getResource())
                || RESOURCE_ENTERPRISE_AUDIT_ATTACHMENT.equals(meta.getResource())
                || RESOURCE_COMPANY_ACCOUNT_FRONT.equals(meta.getResource()));
    }

    private void fillUpdateAuditValues(Map<String, Object> values) {
        values.put("updater", currentUser());
        values.put("update_time", now());
    }

    private void putIfAbsent(Map<String, Object> values, String key, Object value) {
        if (!values.containsKey(key) && value != null) {
            values.put(key, value);
        }
    }

    private String defaultString(Object value, String defaultValue) {
        String text = stringValue(value);
        return StringUtils.hasText(text) ? text : defaultValue;
    }

    private String stringValue(Object value) {
        return value == null ? null : String.valueOf(value).trim();
    }

    private Long optionalLong(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        try {
            return Long.parseLong(String.valueOf(value));
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private String limitLength(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

    private Long requireId(Map<String, Object> body) {
        return requireLong(body, "id");
    }

    private Long requireLong(Map<String, Object> body, String key) {
        Object value = firstPresent(body, key, toSnakeCase(key));
        if (value == null) {
            throw invalidParamException("{} 不能为空", key);
        }
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        try {
            return Long.parseLong(String.valueOf(value));
        } catch (NumberFormatException ex) {
            throw invalidParamException("{} 必须是数字", key);
        }
    }

    private Object firstPresent(Map<String, Object> body, String... keys) {
        for (String key : keys) {
            if (body.containsKey(key)) {
                return body.get(key);
            }
        }
        return null;
    }

    private int parseInt(String value, int defaultValue) {
        if (!StringUtils.hasText(value)) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException ex) {
            return defaultValue;
        }
    }

    private String currentUser() {
        Long userId = SecurityFrameworkUtils.getLoginUserId();
        return userId == null ? "" : String.valueOf(userId);
    }

    private Timestamp now() {
        return new Timestamp(System.currentTimeMillis());
    }

    private String toSnakeCase(String key) {
        if (key == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < key.length(); i++) {
            char ch = key.charAt(i);
            if (ch == '-') {
                builder.append('_');
            } else if (Character.isUpperCase(ch)) {
                if (i > 0) {
                    builder.append('_');
                }
                builder.append(Character.toLowerCase(ch));
            } else {
                builder.append(ch);
            }
        }
        return builder.toString();
    }

    private Map<String, Object> mapOf(Object... values) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < values.length; i += 2) {
            map.put(String.valueOf(values[i]), values[i + 1]);
        }
        return map;
    }

    private static class SqlWhere {
        private final StringBuilder sql = new StringBuilder();
        private final List<Object> args = new ArrayList<>();
    }
}
