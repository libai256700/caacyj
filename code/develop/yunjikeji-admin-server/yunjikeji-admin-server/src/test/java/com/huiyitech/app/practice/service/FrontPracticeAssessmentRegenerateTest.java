package com.huiyitech.app.practice.service;

import cn.iocoder.yudao.server.YunjikejiAdminServerApplication;
import com.huiyitech.app.practice.controller.vo.AppPracticeAnswerSubmitRespVO;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordAnswerRespVO;
import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.util.AopTestUtils;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class FrontPracticeAssessmentRegenerateTest {

    /**
     * This method uses the configured Spring beans, database, and AI channel.
     *
     * mvn -pl yunjikeji-admin-server
     * "-Dtest=FrontPracticeAssessmentRegenerateTest#applyAssessmentEvaluation_shouldUseRealSpringDependenciesAndPersistConfiguredRecord"
     * "-Dassessment.integration.enabled=true" "-Dassessment.integration.springProfile=<profile>"
     * "-Dassessment.integration.recordId=<record-id>"
     * "-Dassessment.integration.assessmentResultId=<pending-result-id>"
     * "-Dassessment.integration.userId=<user-id>" "-Dassessment.integration.tenantId=<tenant-id>"
     * "-Dassessment.integration.practiceId=<practice-id>" test
     */
    @Test
    void applyAssessmentEvaluation_shouldUseRealSpringDependenciesAndPersistConfiguredRecord() throws Exception {
        assumeTrue("true".equalsIgnoreCase(System.getProperty("assessment.integration.enabled")),
                "SKIPPED: assessment.integration.enabled=true is required");
        String springProfile = requiredProperty("assessment.integration.springProfile");
        Long recordId = positiveLongProperty("assessment.integration.recordId");
        Long assessmentResultId = positiveLongProperty("assessment.integration.assessmentResultId");
        Long userId = positiveLongProperty("assessment.integration.userId");
        Long tenantId = positiveLongProperty("assessment.integration.tenantId");
        String practiceId = requiredProperty("assessment.integration.practiceId");

        try (ConfigurableApplicationContext context = new SpringApplicationBuilder(
                YunjikejiAdminServerApplication.class)
                .profiles(springProfile)
                .web(WebApplicationType.NONE)
                .properties("spring.main.lazy-initialization=true")
                .run()) {
            FrontPracticeService serviceBean = context.getBean(FrontPracticeService.class);
            FrontPracticeServiceImpl service = AopTestUtils.getUltimateTargetObject(serviceBean);
            List<AppPracticeRecordAnswerRespVO> answers = assessmentAnswers();

            Object currentResult = invoke(service, "findLatestAssessmentResult",
                    new Class<?>[]{Long.class, Long.class}, userId, recordId);
            assertNotNull(currentResult, "The configured assessment result must exist");
            assertEquals(assessmentResultId, field(currentResult, "id"));
            assertEquals("PENDING", String.valueOf(field(currentResult, "reportStatus")).toUpperCase(),
                    "The configured assessment result must already be PENDING");

            AppPracticeAnswerSubmitRespVO response = AppPracticeAnswerSubmitRespVO.builder()
                    .totalQuestions(answers.size())
                    .correctCount(8)
                    .build();
            Object session = newRuntimeSession(tenantId, userId, practiceId, recordId);
            Method generationMethod = FrontPracticeServiceImpl.class.getDeclaredMethod(
                    "applyAssessmentEvaluation",
                    AppPracticeAnswerSubmitRespVO.class,
                    session.getClass(),
                    Long.class,
                    Long.class,
                    List.class);
            generationMethod.setAccessible(true);
            generationMethod.invoke(service, response, session, recordId, assessmentResultId, answers);

            Object persistedResult = invoke(service, "findLatestAssessmentResult",
                    new Class<?>[]{Long.class, Long.class}, userId, recordId);
            assertNotNull(persistedResult);
            assertEquals(assessmentResultId, field(persistedResult, "id"));
            assertEquals("SUCCESS", String.valueOf(field(persistedResult, "reportStatus")).toUpperCase());
            assertTrue(hasText(String.valueOf(field(persistedResult, "reportContent"))),
                    "The configured assessment result must contain the generated report");
        }
    }

    private List<AppPracticeRecordAnswerRespVO> assessmentAnswers() {
        List<String> questionIds = Arrays.asList(
                "132026081810006", "132026081810007", "132026081810008", "132026081810009",
                "132026081810010", "132026081810011", "132026081810012", "132026081810013",
                "132026081810014", "132026081810015");
        List<AppPracticeRecordAnswerRespVO> answers = new ArrayList<>();
        for (int index = 0; index < questionIds.size(); index++) {
            answers.add(AppPracticeRecordAnswerRespVO.builder()
                    .no(index + 1)
                    .questionId(questionIds.get(index))
                    .question("量表测试题目 " + (index + 1))
                    .answer("5")
                    .correctFlag(index < 8)
                    .stepName("核心量表")
                    .build());
        }
        return answers;
    }

    private String requiredProperty(String name) {
        String value = System.getProperty(name);
        assumeTrue(hasText(value), "SKIPPED: " + name + " is required");
        return value.trim();
    }

    private Long positiveLongProperty(String name) {
        String value = requiredProperty(name);
        Long parsed = Long.valueOf(value);
        assertTrue(parsed > 0L, name + " must be positive");
        return parsed;
    }

    private Object newRuntimeSession(Long tenantId, Long userId, String practiceId, Long recordId)
            throws Exception {
        Class<?> sessionClass = null;
        for (Class<?> nestedClass : FrontPracticeServiceImpl.class.getDeclaredClasses()) {
            if ("PracticeRuntimeSession".equals(nestedClass.getSimpleName())) {
                sessionClass = nestedClass;
                break;
            }
        }
        assertNotNull(sessionClass, "PracticeRuntimeSession must exist");
        Constructor<?> constructor = sessionClass.getDeclaredConstructor(
                Long.class, Long.class, String.class, String.class, List.class, boolean.class);
        constructor.setAccessible(true);
        Object session = constructor.newInstance(
                tenantId, userId, practiceId, "ASSESSMENT", Collections.emptyList(), true);
        Field recordIdField = sessionClass.getDeclaredField("recordId");
        recordIdField.setAccessible(true);
        recordIdField.set(session, recordId);
        return session;
    }

    private Object invoke(Object target, String name, Class<?>[] parameterTypes, Object... arguments)
            throws Exception {
        Method method = FrontPracticeServiceImpl.class.getDeclaredMethod(name, parameterTypes);
        method.setAccessible(true);
        return method.invoke(target, arguments);
    }

    private Object field(Object target, String name) throws Exception {
        Field field = target.getClass().getDeclaredField(name);
        field.setAccessible(true);
        return field.get(target);
    }

    private boolean hasText(String value) {
        return value != null && !value.trim().isEmpty() && !"null".equalsIgnoreCase(value.trim());
    }
}
