package cn.iocoder.yudao.server.service.yj;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class YjAdminAssessmentQuestionRequiredContractTest {

    private CapturingJdbcTemplate jdbcTemplate;
    private YjAdminService service;

    @BeforeEach
    void setUp() {
        jdbcTemplate = new CapturingJdbcTemplate();
        service = new YjAdminService();
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplate);
    }

    @Test
    void registry_shouldExposeIsRequiredAsReadableAndWritable() {
        YjAdminTableRegistry.TableMeta meta = new YjAdminTableRegistry().get("assessment-question");

        assertTrue(meta.isColumn("is_required"));
        assertTrue(meta.isWritableColumn("is_required"));
    }

    @Test
    void pageAndGet_shouldSelectIsRequired() {
        service.getPage("assessment-question", Collections.emptyMap());
        String pageSql = jdbcTemplate.lastQueryForListSql;

        service.get("assessment-question", 1L);
        String detailSql = jdbcTemplate.lastQueryForListSql;

        assertTrue(pageSql.contains("e.is_required"), pageSql);
        assertTrue(detailSql.contains("e.is_required"), detailSql);
    }

    @Test
    @SuppressWarnings("unchecked")
    void createMapping_shouldAcceptCamelCaseFalseAndDefaultToTrue() {
        Map<String, Object> optionalBody = requiredQuestionBody();
        optionalBody.put("isRequired", false);

        Map<String, Object> optionalValues = ReflectionTestUtils.invokeMethod(
                service, "mapAssessmentQuestionValues", optionalBody, false);
        Map<String, Object> requiredValues = ReflectionTestUtils.invokeMethod(
                service, "mapAssessmentQuestionValues", requiredQuestionBody(), false);

        assertFalse((Boolean) optionalValues.get("is_required"));
        assertEquals(Boolean.TRUE, requiredValues.get("is_required"));
    }

    @Test
    void update_shouldAcceptSnakeCaseFalseWithoutDroppingIt() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", 1L);
        body.put("is_required", false);

        service.update("assessment-question", body);

        assertTrue(jdbcTemplate.lastUpdateSql.contains("is_required"), jdbcTemplate.lastUpdateSql);
        assertTrue(Arrays.asList(jdbcTemplate.lastUpdateArgs).contains(Boolean.FALSE));
    }

    private Map<String, Object> requiredQuestionBody() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("title", "是否必填契约测试题");
        body.put("question_type", "1");
        return body;
    }

    private static class CapturingJdbcTemplate extends JdbcTemplate {

        private String lastQueryForListSql;
        private String lastUpdateSql;
        private Object[] lastUpdateArgs;

        @Override
        public <T> T queryForObject(String sql, Object[] args, Class<T> requiredType) {
            return requiredType.cast(1L);
        }

        @Override
        public List<Map<String, Object>> queryForList(String sql, Object... args) {
            lastQueryForListSql = sql;
            return Collections.singletonList(Collections.singletonMap("id", 1L));
        }

        @Override
        public int update(String sql, Object... args) {
            lastUpdateSql = sql;
            lastUpdateArgs = args;
            return 1;
        }
    }
}
