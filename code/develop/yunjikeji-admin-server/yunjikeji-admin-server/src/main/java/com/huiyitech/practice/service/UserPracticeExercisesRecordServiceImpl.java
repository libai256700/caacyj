package com.huiyitech.practice.service;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDO;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDetailDO;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordDetailMapper;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesRecordMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Service
public class UserPracticeExercisesRecordServiceImpl
        extends AbstractPracticeResourceService<UserPracticeExercisesRecordDO>
        implements UserPracticeExercisesRecordService {

    private static final Set<String> RECORD_WRITABLE_COLUMNS = columns("customer_account_id", "category_id",
            "catalog_batch_id", "total_score", "correct_count", "wrong_count", "field_type");
    private static final Set<String> RECORD_LIKE_COLUMNS = columns("field_type");
    private static final Set<String> DETAIL_WRITABLE_COLUMNS = columns("record_id", "exercises_id",
            "answer_code", "correct_answer_code", "is_correct");
    private static final Set<String> DETAIL_LIKE_COLUMNS = columns("answer_code", "correct_answer_code");

    @Resource
    private UserPracticeExercisesRecordMapper userPracticeExercisesRecordMapper;
    @Resource
    private UserPracticeExercisesRecordDetailMapper userPracticeExercisesRecordDetailMapper;
    @Resource
    private JdbcTemplate jdbcTemplate;

    private PracticeResourceService detailResourceService;

    @PostConstruct
    public void initDetailResourceService() {
        this.detailResourceService = new AbstractPracticeResourceService<UserPracticeExercisesRecordDetailDO>() {
            @Override
            public PageResult<Map<String, Object>> getPage(Map<String, String> params) {
                return getPracticeWrongDetailPage(params);
            }

            @Override
            protected BaseMapperX<UserPracticeExercisesRecordDetailDO> mapper() {
                return userPracticeExercisesRecordDetailMapper;
            }

            @Override
            protected Class<UserPracticeExercisesRecordDetailDO> entityClass() {
                return UserPracticeExercisesRecordDetailDO.class;
            }

            @Override
            protected Set<String> writableColumns() {
                return DETAIL_WRITABLE_COLUMNS;
            }

            @Override
            protected Set<String> likeColumns() {
                return DETAIL_LIKE_COLUMNS;
            }
        };
    }

    @Override
    protected BaseMapperX<UserPracticeExercisesRecordDO> mapper() {
        return userPracticeExercisesRecordMapper;
    }

    @Override
    protected Class<UserPracticeExercisesRecordDO> entityClass() {
        return UserPracticeExercisesRecordDO.class;
    }

    @Override
    protected Set<String> writableColumns() {
        return RECORD_WRITABLE_COLUMNS;
    }

    @Override
    protected Set<String> likeColumns() {
        return RECORD_LIKE_COLUMNS;
    }

    @Override
    public PageResult<Map<String, Object>> getPage(Map<String, String> params) {
        return getPracticeRecordPage(params);
    }

    @Override
    public PageResult<Map<String, Object>> getDetailPage(Map<String, String> params) {
        return detailResourceService.getPage(params);
    }

    @Override
    public Map<String, Object> getDetail(Long id) {
        return detailResourceService.get(id);
    }

    @Override
    public Long createDetail(Map<String, Object> body) {
        return detailResourceService.create(body);
    }

    @Override
    public void updateDetail(Map<String, Object> body) {
        detailResourceService.update(body);
    }

    @Override
    public void deleteDetail(Long id) {
        detailResourceService.delete(id);
    }

    private PageResult<Map<String, Object>> getPracticeRecordPage(Map<String, String> params) {
        PageParam pageParam = buildPageParam(params);
        SqlBuilder sql = buildPracticeRecordWhere(params);
        Long total = jdbcTemplate.queryForObject("SELECT COUNT(1) " + PRACTICE_RECORD_FROM_SQL + sql.whereSql,
                sql.args.toArray(), Long.class);
        if (total == null || total == 0L) {
            return PageResult.empty(0L);
        }

        List<Object> pageArgs = new ArrayList<>(sql.args);
        pageArgs.add((pageParam.getPageNo() - 1) * pageParam.getPageSize());
        pageArgs.add(pageParam.getPageSize());
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("SELECT r.*, "
                        + STUDENT_NAME_SQL + " AS student_name, "
                        + CATEGORY_NAME_SQL + " AS category_name "
                        + PRACTICE_RECORD_FROM_SQL + sql.whereSql
                        + " ORDER BY r.id DESC LIMIT ?, ?",
                pageArgs.toArray());
        normalizePracticeRecordRows(rows);
        return new PageResult<>(rows, total);
    }

    private PageResult<Map<String, Object>> getPracticeWrongDetailPage(Map<String, String> params) {
        PageParam pageParam = buildPageParam(params);
        SqlBuilder sql = buildPracticeWrongDetailWhere(params);
        Long total = jdbcTemplate.queryForObject("SELECT COUNT(1) " + PRACTICE_WRONG_DETAIL_FROM_SQL + sql.whereSql,
                sql.args.toArray(), Long.class);
        if (total == null || total == 0L) {
            return PageResult.empty(0L);
        }

        List<Object> pageArgs = new ArrayList<>(sql.args);
        pageArgs.add((pageParam.getPageNo() - 1) * pageParam.getPageSize());
        pageArgs.add(pageParam.getPageSize());
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("SELECT d.*, "
                        + STUDENT_NAME_SQL + " AS student_name, "
                        + PRACTICE_RECORD_DISPLAY_SQL + " AS practice_record_display, "
                        + CATEGORY_NAME_SQL + " AS category_name, "
                        + QUESTION_STEM_SQL + " AS question_stem, "
                        + "r.customer_account_id AS customer_account_id "
                        + PRACTICE_WRONG_DETAIL_FROM_SQL + sql.whereSql
                        + " ORDER BY d.id DESC LIMIT ?, ?",
                pageArgs.toArray());
        normalizePracticeWrongDetailRows(rows);
        return new PageResult<>(rows, total);
    }

    private SqlBuilder buildPracticeRecordWhere(Map<String, String> params) {
        SqlBuilder sql = new SqlBuilder();
        sql.whereSql.append(" WHERE r.deleted = b'0'");
        appendPracticeRecordFilters(sql, params, false);
        appendCreateTimeRange(sql, params, "r.create_time");
        return sql;
    }

    private SqlBuilder buildPracticeWrongDetailWhere(Map<String, String> params) {
        SqlBuilder sql = new SqlBuilder();
        sql.whereSql.append(" WHERE d.deleted = b'0' AND r.deleted = b'0'");
        appendPracticeRecordFilters(sql, params, true);
        appendCreateTimeRange(sql, params, "d.create_time");
        return sql;
    }

    private void appendPracticeRecordFilters(SqlBuilder sql, Map<String, String> params, boolean detailMode) {
        if (params == null) {
            return;
        }
        for (Map.Entry<String, String> entry : params.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();
            if (!StringUtils.hasText(value) || isPageKey(key) || isCreateTimeKey(key)) {
                continue;
            }
            String column = toSnakeCase(key);
            if ("keyword".equals(key)) {
                appendKeywordFilter(sql, value, detailMode);
                continue;
            }
            if ("student_name".equals(column)) {
                sql.whereSql.append(" AND ").append(STUDENT_NAME_SQL).append(" LIKE ?");
                sql.args.add("%" + value + "%");
                continue;
            }
            if ("category_name".equals(column)) {
                sql.whereSql.append(" AND ").append(CATEGORY_NAME_SQL).append(" LIKE ?");
                sql.args.add("%" + value + "%");
                continue;
            }
            if (detailMode && ("question_keyword".equals(column) || "question_stem".equals(column))) {
                sql.whereSql.append(" AND ").append(QUESTION_STEM_SQL).append(" LIKE ?");
                sql.args.add("%" + value + "%");
                continue;
            }
            if (!detailMode) {
                appendPracticeRecordOnlyFilter(sql, column, value);
                continue;
            }
            appendPracticeWrongDetailOnlyFilter(sql, column, value);
        }
    }

    private void appendKeywordFilter(SqlBuilder sql, String value, boolean detailMode) {
        String likeValue = "%" + value + "%";
        if (detailMode) {
            sql.whereSql.append(" AND (")
                    .append(STUDENT_NAME_SQL).append(" LIKE ?")
                    .append(" OR d.answer_code LIKE ? OR d.correct_answer_code LIKE ?)");
            sql.args.add(likeValue);
            sql.args.add(likeValue);
            sql.args.add(likeValue);
            return;
        }
        sql.whereSql.append(" AND (")
                .append(STUDENT_NAME_SQL).append(" LIKE ?")
                .append(" OR ").append(CATEGORY_NAME_SQL).append(" LIKE ?")
                .append(" OR r.field_type LIKE ?)");
        sql.args.add(likeValue);
        sql.args.add(likeValue);
        sql.args.add(likeValue);
    }

    private void appendPracticeRecordOnlyFilter(SqlBuilder sql, String column, String value) {
        if ("customer_account_id".equals(column)) {
            sql.whereSql.append(" AND r.customer_account_id = ?");
            sql.args.add(value);
        } else if ("category_id".equals(column)) {
            sql.whereSql.append(" AND r.category_id = ?");
            sql.args.add(value);
        } else if ("field_type".equals(column)) {
            sql.whereSql.append(" AND r.field_type LIKE ?");
            sql.args.add("%" + value + "%");
        } else if ("total_score".equals(column) || "correct_count".equals(column)
                || "wrong_count".equals(column) || "id".equals(column)) {
            sql.whereSql.append(" AND r.").append(column).append(" = ?");
            sql.args.add(value);
        }
    }

    private void appendPracticeWrongDetailOnlyFilter(SqlBuilder sql, String column, String value) {
        if ("record_id".equals(column) || "exercises_id".equals(column) || "id".equals(column)) {
            sql.whereSql.append(" AND d.").append(column).append(" = ?");
            sql.args.add(value);
        } else if ("answer_code".equals(column) || "correct_answer_code".equals(column)) {
            sql.whereSql.append(" AND d.").append(column).append(" LIKE ?");
            sql.args.add("%" + value + "%");
        } else if ("is_correct".equals(column)) {
            sql.whereSql.append(" AND d.is_correct = ?");
            sql.args.add(normalizeBooleanQueryValue(value));
        }
    }

    private void appendCreateTimeRange(SqlBuilder sql, Map<String, String> params, String qualifiedColumn) {
        if (params == null) {
            return;
        }
        String begin = params.get("beginCreateTime");
        if (StringUtils.hasText(begin)) {
            sql.whereSql.append(" AND ").append(qualifiedColumn).append(" >= ?");
            sql.args.add(begin);
        }
        String end = params.get("endCreateTime");
        if (StringUtils.hasText(end)) {
            sql.whereSql.append(" AND ").append(qualifiedColumn).append(" <= ?");
            sql.args.add(end);
        }
    }

    private void normalizePracticeRecordRows(List<Map<String, Object>> rows) {
        for (Map<String, Object> row : rows) {
            Object customerAccountId = row.remove("customer_account_id");
            row.put("user_id", customerAccountId);
        }
    }

    private void normalizePracticeWrongDetailRows(List<Map<String, Object>> rows) {
        // keep hook for future row normalization; current SQL already returns frontend field names.
    }

    private PageParam buildPageParam(Map<String, String> params) {
        PageParam pageParam = new PageParam();
        pageParam.setPageNo(parseInt(params == null ? null : params.get("pageNo"), 1));
        pageParam.setPageSize(parseInt(params == null ? null : params.get("pageSize"), 10));
        if (pageParam.getPageNo() < 1 || pageParam.getPageSize() < 1 || pageParam.getPageSize() > 200) {
            throw invalidParamException("Invalid page params");
        }
        return pageParam;
    }

    private boolean isPageKey(String key) {
        return "pageNo".equals(key) || "pageSize".equals(key);
    }

    private boolean isCreateTimeKey(String key) {
        return "beginCreateTime".equals(key) || "endCreateTime".equals(key);
    }

    private Object normalizeBooleanQueryValue(String value) {
        if ("true".equalsIgnoreCase(value)) {
            return Boolean.TRUE;
        }
        if ("false".equalsIgnoreCase(value)) {
            return Boolean.FALSE;
        }
        return value;
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

    private static final String STUDENT_NAME_SQL = "COALESCE(NULLIF(ci.real_name, ''), NULLIF(ci.nick_name, ''), "
            + "NULLIF(ci.mobile_phone, ''), NULLIF(ca.username, ''), NULLIF(ca.mobile, ''), '')";
    private static final String CATEGORY_NAME_SQL = "(COALESCE(NULLIF(pcb.category_name, ''), "
            + "NULLIF(pc.category_name, ''), '') COLLATE utf8mb4_unicode_ci)";
    private static final String PRACTICE_RECORD_DISPLAY_SQL = "CONCAT(DATE_FORMAT(r.create_time, "
            + "'%Y-%m-%d %H:%i:%s'), ' + ', " + CATEGORY_NAME_SQL + ")";
    private static final String QUESTION_STEM_SQL = "(COALESCE(NULLIF(pe.question_stem, ''), '') "
            + "COLLATE utf8mb4_unicode_ci)";
    private static final String PRACTICE_RECORD_FROM_SQL = "FROM yj_user_practice_exercises_record r "
            + "LEFT JOIN yj_customer_account ca ON ca.id = r.customer_account_id AND ca.deleted = b'0' "
            + "LEFT JOIN yj_customer_info ci ON ci.id = (SELECT MAX(ci_pick.id) FROM yj_customer_info ci_pick "
            + "WHERE ci_pick.customer_account_id = r.customer_account_id AND ci_pick.deleted = b'0') "
            + "LEFT JOIN yj_practice_catalog_batch pcb ON pcb.id = r.category_id AND pcb.deleted = b'0' "
            + "LEFT JOIN yj_practice_category pc ON pc.id = pcb.category_id AND pc.deleted = b'0'";
    private static final String PRACTICE_WRONG_DETAIL_FROM_SQL = "FROM yj_user_practice_exercises_record_detail d "
            + "INNER JOIN yj_user_practice_exercises_record r ON r.id = d.record_id "
            + "LEFT JOIN yj_customer_account ca ON ca.id = r.customer_account_id AND ca.deleted = b'0' "
            + "LEFT JOIN yj_customer_info ci ON ci.id = (SELECT MAX(ci_pick.id) FROM yj_customer_info ci_pick "
            + "WHERE ci_pick.customer_account_id = r.customer_account_id AND ci_pick.deleted = b'0') "
            + "LEFT JOIN yj_practice_catalog_batch pcb ON pcb.id = r.category_id AND pcb.deleted = b'0' "
            + "LEFT JOIN yj_practice_category pc ON pc.id = pcb.category_id AND pc.deleted = b'0' "
            + "LEFT JOIN yj_practice_exercises_batch peb ON peb.id = d.exercises_id AND peb.deleted = b'0' "
            + "LEFT JOIN yj_practice_exercises pe ON pe.id = peb.exercises_id AND pe.deleted = b'0'";

    private static final class SqlBuilder {
        private final StringBuilder whereSql = new StringBuilder();
        private final List<Object> args = new ArrayList<>();
    }
}
