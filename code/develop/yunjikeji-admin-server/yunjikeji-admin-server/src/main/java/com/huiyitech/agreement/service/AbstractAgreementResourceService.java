package com.huiyitech.agreement.service;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.util.StringUtils;

import java.beans.PropertyDescriptor;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

public abstract class AbstractAgreementResourceService<T extends TenantBaseDO>
        implements AgreementResourceService {

    protected abstract BaseMapperX<T> mapper();

    protected abstract Class<T> entityClass();

    protected abstract Set<String> writableColumns();

    protected abstract Set<String> likeColumns();

    @Override
    public PageResult<Map<String, Object>> getPage(Map<String, String> params) {
        PageParam pageParam = buildPageParam(params);
        QueryWrapper<T> wrapper = buildQuery(params);
        wrapper.orderByDesc("id");
        PageResult<T> page = mapper().selectPage(pageParam, wrapper);
        List<Map<String, Object>> rows = new ArrayList<>();
        for (T item : page.getList()) {
            rows.add(toSnakeCaseMap(item));
        }
        return new PageResult<>(rows, page.getTotal());
    }

    @Override
    public Map<String, Object> get(Long id) {
        T item = mapper().selectById(id);
        if (item == null) {
            throw invalidParamException("Record does not exist: {}", id);
        }
        return toSnakeCaseMap(item);
    }

    @Override
    public Long create(Map<String, Object> body) {
        T item = newEntity();
        bindWritableValues(item, body, false);
        applyTenant(item);
        mapper().insert(item);
        return getId(item);
    }

    @Override
    public void update(Map<String, Object> body) {
        Long id = requireId(body);
        T item = newEntity();
        setProperty(item, "id", id);
        bindWritableValues(item, body, true);
        if (mapper().updateById(item) == 0) {
            throw invalidParamException("Record does not exist: {}", id);
        }
    }

    @Override
    public void delete(Long id) {
        if (mapper().deleteById(id) == 0) {
            throw invalidParamException("Record does not exist: {}", id);
        }
    }

    protected QueryWrapper<T> buildQuery(Map<String, String> params) {
        QueryWrapper<T> wrapper = new QueryWrapper<>();
        if (params == null) {
            return wrapper;
        }
        for (Map.Entry<String, String> entry : params.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();
            if (!StringUtils.hasText(value) || isPageKey(key) || isCreateTimeKey(key)) {
                continue;
            }
            if ("keyword".equals(key)) {
                appendKeyword(wrapper, value);
                continue;
            }
            String column = toSnakeCase(key);
            if (!isKnownColumn(column)) {
                continue;
            }
            if (likeColumns().contains(column)) {
                wrapper.like(column, value);
            } else {
                wrapper.eq(column, normalizeQueryValue(value));
            }
        }
        appendCreateTimeRange(wrapper, params);
        return wrapper;
    }

    protected Long requireId(Map<String, Object> body) {
        Object id = firstPresent(body, "id");
        if (id == null) {
            throw invalidParamException("id cannot be empty");
        }
        if (id instanceof Number) {
            return ((Number) id).longValue();
        }
        try {
            return Long.parseLong(String.valueOf(id));
        } catch (NumberFormatException ex) {
            throw invalidParamException("id must be a number");
        }
    }

    protected Map<String, Object> toSnakeCaseMap(T item) {
        Map<String, Object> result = new LinkedHashMap<>();
        BeanWrapper wrapper = new BeanWrapperImpl(item);
        for (PropertyDescriptor descriptor : wrapper.getPropertyDescriptors()) {
            String name = descriptor.getName();
            if ("class".equals(name) || "transMap".equals(name)) {
                continue;
            }
            result.put(toSnakeCase(name), wrapper.getPropertyValue(name));
        }
        return result;
    }

    protected static Set<String> columns(String... columns) {
        return new LinkedHashSet<>(Arrays.asList(columns));
    }

    protected static String toSnakeCase(String key) {
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

    protected static String toCamelCase(String key) {
        StringBuilder builder = new StringBuilder();
        boolean upperNext = false;
        for (int i = 0; i < key.length(); i++) {
            char ch = key.charAt(i);
            if (ch == '_') {
                upperNext = true;
            } else if (upperNext) {
                builder.append(Character.toUpperCase(ch));
                upperNext = false;
            } else {
                builder.append(ch);
            }
        }
        return builder.toString();
    }

    private void appendKeyword(QueryWrapper<T> wrapper, String keyword) {
        if (likeColumns().isEmpty()) {
            return;
        }
        wrapper.and(query -> {
            boolean first = true;
            for (String column : likeColumns()) {
                if (first) {
                    query.like(column, keyword);
                    first = false;
                } else {
                    query.or().like(column, keyword);
                }
            }
        });
    }

    private void appendCreateTimeRange(QueryWrapper<T> wrapper, Map<String, String> params) {
        String begin = params.get("beginCreateTime");
        if (StringUtils.hasText(begin)) {
            wrapper.ge("create_time", begin);
        }
        String end = params.get("endCreateTime");
        if (StringUtils.hasText(end)) {
            wrapper.le("create_time", end);
        }
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

    private void bindWritableValues(T item, Map<String, Object> body, boolean update) {
        if (body == null || body.isEmpty()) {
            throw invalidParamException(update ? "Update content cannot be empty" : "Create content cannot be empty");
        }
        int count = 0;
        for (Map.Entry<String, Object> entry : body.entrySet()) {
            String column = toSnakeCase(entry.getKey());
            if ("id".equals(column) || !writableColumns().contains(column)) {
                continue;
            }
            setProperty(item, toCamelCase(column), entry.getValue());
            count++;
        }
        if (count == 0) {
            throw invalidParamException(update ? "Update content cannot be empty" : "Create content cannot be empty");
        }
    }

    private T newEntity() {
        try {
            return entityClass().newInstance();
        } catch (InstantiationException | IllegalAccessException ex) {
            throw new IllegalStateException("Cannot create entity: " + entityClass().getName(), ex);
        }
    }

    private void applyTenant(T item) {
        if (item.getTenantId() != null) {
            return;
        }
        Long tenantId = TenantContextHolder.getTenantId();
        item.setTenantId(tenantId == null ? 0L : tenantId);
    }

    private Long getId(T item) {
        Object id = new BeanWrapperImpl(item).getPropertyValue("id");
        return id == null ? null : ((Number) id).longValue();
    }

    private Object firstPresent(Map<String, Object> body, String key) {
        if (body == null) {
            return null;
        }
        if (body.containsKey(key)) {
            return body.get(key);
        }
        return body.get(toSnakeCase(key));
    }

    private void setProperty(T item, String property, Object value) {
        BeanWrapper wrapper = new BeanWrapperImpl(item);
        if (!wrapper.isWritableProperty(property)) {
            return;
        }
        Class<?> targetType = wrapper.getPropertyType(property);
        wrapper.setPropertyValue(property, convertValue(value, targetType));
    }

    private Object convertValue(Object value, Class<?> targetType) {
        if (value == null || targetType == null || targetType.isInstance(value)) {
            return value;
        }
        if (LocalDateTime.class.equals(targetType)) {
            Timestamp timestamp = toTimestamp(value);
            return timestamp == null ? null : timestamp.toLocalDateTime();
        }
        if (Long.class.equals(targetType)) {
            return toLong(value);
        }
        if (Integer.class.equals(targetType)) {
            return toInteger(value);
        }
        if (Boolean.class.equals(targetType)) {
            return toBoolean(value);
        }
        return value;
    }

    private Timestamp toTimestamp(Object value) {
        if (value instanceof Timestamp) {
            return (Timestamp) value;
        }
        if (value instanceof Date) {
            return new Timestamp(((Date) value).getTime());
        }
        if (!StringUtils.hasText(String.valueOf(value))) {
            return null;
        }
        String text = String.valueOf(value).trim();
        try {
            return Timestamp.valueOf(text);
        } catch (IllegalArgumentException ignored) {
            return Timestamp.valueOf(LocalDateTime.parse(text, DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        }
    }

    private Long toLong(Object value) {
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        return Long.valueOf(String.valueOf(value));
    }

    private Integer toInteger(Object value) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        return Integer.valueOf(String.valueOf(value));
    }

    private Boolean toBoolean(Object value) {
        if (value instanceof Boolean) {
            return (Boolean) value;
        }
        if (value instanceof Number) {
            return ((Number) value).intValue() != 0;
        }
        return Boolean.valueOf(String.valueOf(value));
    }

    private boolean isKnownColumn(String column) {
        return writableColumns().contains(column) || "id".equals(column)
                || "create_time".equals(column) || "update_time".equals(column);
    }

    private boolean isPageKey(String key) {
        return "pageNo".equals(key) || "pageSize".equals(key);
    }

    private boolean isCreateTimeKey(String key) {
        return "beginCreateTime".equals(key) || "endCreateTime".equals(key);
    }

    private Object normalizeQueryValue(String value) {
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
}
