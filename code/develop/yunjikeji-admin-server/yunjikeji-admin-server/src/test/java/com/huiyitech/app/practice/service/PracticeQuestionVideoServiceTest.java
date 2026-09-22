package com.huiyitech.app.practice.service;

import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionItemRespVO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesMapper;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Arrays;
import java.util.Collections;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class PracticeQuestionVideoServiceTest {
    @Test
    void signsPrivateObjectAndPreservesCloudBatchId() {
        PracticeExercisesMapper mapper = mock(PracticeExercisesMapper.class);
        PracticeExercisesDO exercise = PracticeExercisesDO.builder().id(5592L).questionStatus(true)
                .videoBucket("video").videoObjectKey("1/example with spaces.mp4").build();
        when(mapper.selectById(5592L)).thenReturn(exercise);
        PracticeQuestionVideoService service = service(mapper);
        ReflectionTestUtils.setField(service, "endpoint", "http://127.0.0.1:9000");
        ReflectionTestUtils.setField(service, "accessKey", "test-access");
        ReflectionTestUtils.setField(service, "secretKey", "test-secret");
        AppPracticeQuestionItemRespVO question = AppPracticeQuestionItemRespVO.builder()
                .id("999999").exerciseId(5592L).build();
        try {
            service.enrich(question);
            assertEquals("999999", question.getId());
            assertTrue(question.getVideoAvailable());
            assertTrue(question.getVideoUrl().contains("/video/1/example%20with%20spaces.mp4"));
            assertTrue(question.getVideoUrl().contains("X-Amz-Expires=900"));
            assertTrue(question.getVideoUrl().contains("X-Amz-Signature="));
            assertFalse(question.getVideoUrl().contains("test-secret"));
            assertTrue(question.getVideoExpiresAt() > System.currentTimeMillis());
        } finally {
            service.close();
        }
    }

    @Test
    void doesNotGuessSourceIdForAmbiguousCloudQuestion() {
        PracticeExercisesMapper mapper = mock(PracticeExercisesMapper.class);
        when(mapper.selectList(any())).thenReturn(Arrays.asList(
                PracticeExercisesDO.builder().id(1L).questionStem("same").build(),
                PracticeExercisesDO.builder().id(2L).questionStem("same").build()));
        AppPracticeQuestionItemRespVO question = AppPracticeQuestionItemRespVO.builder().id("5592").stem("same").build();
        service(mapper).enrich(question);
        assertNull(question.getExerciseId());
        assertFalse(question.getVideoAvailable());
        assertNull(question.getVideoUrl());
        verify(mapper, never()).selectById(any());
    }

    @Test
    void questionWithoutVideoStillLoadsAndClearsStaleUrl() {
        PracticeExercisesMapper mapper = mock(PracticeExercisesMapper.class);
        when(mapper.selectList(any())).thenReturn(Collections.singletonList(
                PracticeExercisesDO.builder().id(5592L).questionStem("unique").build()));
        AppPracticeQuestionItemRespVO question = AppPracticeQuestionItemRespVO.builder()
                .id("999").stem("unique").videoUrl("stale").build();
        service(mapper).enrich(question);
        assertEquals(5592L, question.getExerciseId());
        assertFalse(question.getVideoAvailable());
        assertNull(question.getVideoUrl());
    }

    private PracticeQuestionVideoService service(PracticeExercisesMapper mapper) {
        PracticeQuestionVideoService service = new PracticeQuestionVideoService();
        ReflectionTestUtils.setField(service, "exercisesMapper", mapper);
        ReflectionTestUtils.setField(service, "expirationSeconds", 900);
        return service;
    }
}
