package com.huiyitech.knowledge.dal;

import cn.iocoder.yudao.server.YunjikejiAdminServerApplication;
import com.huiyitech.aiconfig.AiSceneCodes;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.junit.jupiter.api.function.Executable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertFalse;

/**
 * Opt-in smoke test for the active practice_assessment model configuration.
 * It is disabled during normal test runs so no external model call is made accidentally.
 */
@EnabledIfSystemProperty(named = "practice.assessment.api.smoke", matches = "true")
@SpringBootTest(classes = YunjikejiAdminServerApplication.class)
class DeepSeekPracticeAssessmentApiSmokeTest {

    @Autowired
    private DeepSeekOpenAiClient client;

    @Test
    void activePracticeAssessmentApiShouldRespond() {
        Executable call = () -> {
            String response = client.complete(
                    AiSceneCodes.PRACTICE_ASSESSMENT,
                    "你是连通性测试助手，只回复一句简短问候。",
                    "你好",
                    null);

            assertNotNull(response, "practice_assessment API returned no content");
            assertFalse(response.trim().isEmpty(), "practice_assessment API returned blank content");
        };

        assertTimeoutPreemptively(Duration.ofSeconds(10), call, "practice_assessment API did not respond within 10 seconds");
    }
}
