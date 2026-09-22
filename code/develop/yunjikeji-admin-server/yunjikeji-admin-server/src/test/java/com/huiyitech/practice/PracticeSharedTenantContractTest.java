package com.huiyitech.practice;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import cn.iocoder.yudao.server.service.yj.YjAdminTableRegistry;
import com.huiyitech.customer.dal.dataobject.customer.CustomerAccountDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCategoryDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeCatalogBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerChildDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesAnswerDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesBatchDO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesDO;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDetailDO;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesRecordDO;
import com.huiyitech.practice.dal.dataobject.practice.UserPracticeExercisesWrongRecordDetailDO;
import com.huiyitech.practice.dal.mysql.practice.UserPracticeExercisesWrongRecordDetailMapper;
import com.huiyitech.practice.service.PracticeCategoryServiceImpl;
import com.huiyitech.practice.service.PracticeExercisesAnswerChildServiceImpl;
import com.huiyitech.practice.service.PracticeExercisesAnswerServiceImpl;
import com.huiyitech.practice.service.PracticeExercisesServiceImpl;
import com.huiyitech.practice.service.UserPracticeExercisesRecordServiceImpl;
import org.apache.ibatis.annotations.Delete;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PracticeSharedTenantContractTest {

    private static final Class<?>[] SHARED_ENTITY_TYPES = {
            PracticeCategoryDO.class,
            PracticeCatalogBatchDO.class,
            PracticeExercisesDO.class,
            PracticeExercisesBatchDO.class,
            PracticeExercisesAnswerDO.class,
            PracticeExercisesAnswerBatchDO.class,
            PracticeExercisesAnswerChildDO.class,
            UserPracticeExercisesRecordDO.class,
            UserPracticeExercisesRecordDetailDO.class,
            UserPracticeExercisesWrongRecordDetailDO.class
    };

    @Test
    void sharedEntities_shouldUseGlobalTableContract() {
        for (Class<?> entityType : SHARED_ENTITY_TYPES) {
            assertEquals(BaseDO.class, entityType.getSuperclass(), entityType.getSimpleName());
            assertFalse(TenantBaseDO.class.isAssignableFrom(entityType), entityType.getSimpleName());
            assertNotNull(entityType.getAnnotation(TenantIgnore.class), entityType.getSimpleName());
        }
    }

    @Test
    void nonTargetCustomerAccount_shouldRemainTenantScoped() {
        assertTrue(TenantBaseDO.class.isAssignableFrom(CustomerAccountDO.class));
        assertFalse(CustomerAccountDO.class.isAnnotationPresent(TenantIgnore.class));
    }

    @Test
    void sharedResourceWritableColumns_shouldNotExposeTenantId() {
        assertNoTenantColumn(PracticeCategoryServiceImpl.class, "WRITABLE_COLUMNS");
        assertNoTenantColumn(PracticeExercisesServiceImpl.class, "WRITABLE_COLUMNS");
        assertNoTenantColumn(PracticeExercisesAnswerServiceImpl.class, "WRITABLE_COLUMNS");
        assertNoTenantColumn(PracticeExercisesAnswerChildServiceImpl.class, "WRITABLE_COLUMNS");
        assertNoTenantColumn(UserPracticeExercisesRecordServiceImpl.class, "RECORD_WRITABLE_COLUMNS");
        assertNoTenantColumn(UserPracticeExercisesRecordServiceImpl.class, "DETAIL_WRITABLE_COLUMNS");
    }

    @Test
    void wrongRecordDelete_shouldUseCustomerAndExerciseBusinessKey() {
        Method deleteMethod = Arrays.stream(UserPracticeExercisesWrongRecordDetailMapper.class.getDeclaredMethods())
                .filter(method -> method.getAnnotation(Delete.class) != null)
                .findFirst()
                .orElseThrow(() -> new AssertionError("Wrong-record delete mapping is missing"));

        assertEquals("deleteByCustomerAccountIdAndExercisesId", deleteMethod.getName());
        assertEquals(2, deleteMethod.getParameterCount());
        String sql = String.join(" ", deleteMethod.getAnnotation(Delete.class).value()).toLowerCase();
        assertFalse(sql.contains("tenant_id"));
        assertTrue(sql.contains("customer_account_id"));
        assertTrue(sql.contains("exercises"));
    }

    @Test
    void yjAdminSharedResources_shouldNotExposeTenantId() {
        YjAdminTableRegistry registry = new YjAdminTableRegistry();
        for (String resource : Arrays.asList("assessment-question", "assessment-answer", "assessment-result")) {
            YjAdminTableRegistry.TableMeta meta = registry.get(resource);
            assertFalse(meta.isColumn("tenant_id"), resource);
            assertFalse(meta.isWritableColumn("tenant_id"), resource);
        }
    }

    @Test
    void practiceMigration_shouldProvideExecutableSnapshotRollback() throws IOException {
        String migration = readVersionSql("20260610-yj-practice-data-migration.sql");
        String normalizedMigration = migration.replaceAll("\\s+", " ");
        String rollback = readVersionSql("20260817113200-dml-rollback_yj_practice_data_migration.sql");
        String scriptIndex = readVersionSql("00-脚本索引.md");

        String[][] rollbackPairs = {
                {"yj_practice_category", "bak_20260610_practice_category_ids"},
                {"yj_practice_exercises", "bak_20260610_practice_exercises_ids"},
                {"yj_practice_exercises_answer", "bak_20260610_practice_answer_ids"},
                {"yj_user_practice_exercises_record", "bak_20260610_practice_record_ids"},
                {"yj_user_practice_exercises_record_detail", "bak_20260610_practice_detail_ids"}
        };
        for (String[] rollbackPair : rollbackPairs) {
            String table = rollbackPair[0];
            String backupTable = rollbackPair[1];
            assertTrue(migration.contains(backupTable), backupTable);
            assertTrue(migration.contains("CREATE TABLE `" + backupTable + "` AS SELECT"), backupTable);
            assertTrue(rollback.contains("DELETE target FROM `" + table + "` target"), table);
            assertTrue(rollback.contains("JOIN `" + backupTable + "` backup ON backup.id = target.id"), table);
        }
        assertTrue(normalizedMigration.contains("FROM yk_question_category qc INNER JOIN bak_20260610_practice_category_ids migration_scope ON migration_scope.id = qc.id"));
        assertTrue(normalizedMigration.contains("FROM yk_question q INNER JOIN bak_20260610_practice_exercises_ids migration_scope ON migration_scope.id = q.id"));
        assertTrue(normalizedMigration.contains("FROM yk_question_option qo INNER JOIN bak_20260610_practice_answer_ids migration_scope ON migration_scope.id = qo.id"));
        assertTrue(normalizedMigration.contains("FROM yk_practice_session ps INNER JOIN bak_20260610_practice_record_ids migration_scope ON migration_scope.id = ps.id"));
        assertTrue(normalizedMigration.contains("FROM yk_practice_record pr INNER JOIN bak_20260610_practice_detail_ids migration_scope ON migration_scope.id = pr.id"));
        assertTrue(scriptIndex.contains("20260817113200-dml-rollback_yj_practice_data_migration.sql"));
    }

    @Test
    void compatibilityDdl_shouldVerifyTenantColumnState() throws IOException {
        String ddl = readVersionSql("20260817113000-ddl-normalize_practice_shared_indexes.sql");

        assertTrue(ddl.contains("information_schema.COLUMNS"));
        assertTrue(ddl.contains("TENANT_ID_REMOVED"));
        assertTrue(ddl.contains("TENANT_ID_RETAINED_REQUIRES_INDEX_REVIEW"));
        assertTrue(ddl.contains("TENANT_ID_PRESENT_UNEXPECTED"));
        assertTrue(ddl.contains("'yj_assessment_question'"));
        assertTrue(ddl.contains("'yj_assessment_answer'"));
    }

    @SuppressWarnings("unchecked")
    private void assertNoTenantColumn(Class<?> serviceType, String fieldName) {
        Set<String> columns = (Set<String>) ReflectionTestUtils.getField(serviceType, fieldName);
        assertNotNull(columns, serviceType.getSimpleName() + "." + fieldName);
        assertFalse(columns.contains("tenant_id"), serviceType.getSimpleName() + "." + fieldName);
    }

    private String readVersionSql(String fileName) throws IOException {
        Path current = Paths.get(System.getProperty("user.dir")).toAbsolutePath();
        while (current != null && !Files.exists(current.resolve(".git"))) {
            current = current.getParent();
        }
        assertNotNull(current, "Repository root is missing");
        Path sql = current.resolve(Paths.get(
                "doc", "02-版本迭代", "03-进行中版本", "20260601000000-vphase1-initial-delivery",
                "050-执行脚本", fileName));
        assertTrue(Files.exists(sql), sql.toString());
        return new String(Files.readAllBytes(sql), StandardCharsets.UTF_8);
    }
}
