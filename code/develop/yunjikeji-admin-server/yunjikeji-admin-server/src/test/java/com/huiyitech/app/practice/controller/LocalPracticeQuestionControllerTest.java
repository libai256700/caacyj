package com.huiyitech.app.practice.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.app.practice.service.PracticeQuestionVideoService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class LocalPracticeQuestionControllerTest {
    @Test
    void rejectsMissingTokenWithoutSigning() {
        LocalPracticeQuestionController controller = new LocalPracticeQuestionController();
        PracticeQuestionVideoService video = mock(PracticeQuestionVideoService.class);
        ReflectionTestUtils.setField(controller, "objectMapper", new ObjectMapper());
        ReflectionTestUtils.setField(controller, "videoService", video);
        JsonNode result = controller.getQuestion("p", "s", "practice", 0, null, null, new MockHttpServletResponse());
        assertEquals(401, result.path("code").asInt());
        verifyNoInteractions(video);
    }

    @Test
    void cloudSessionRejectionNeverSignsVideo() {
        LocalPracticeQuestionController controller = new LocalPracticeQuestionController();
        PracticeQuestionVideoService video = mock(PracticeQuestionVideoService.class);
        ReflectionTestUtils.setField(controller, "objectMapper", new ObjectMapper());
        ReflectionTestUtils.setField(controller, "videoService", video);
        MockRestServiceServer server = MockRestServiceServer.bindTo(
                (RestTemplate) ReflectionTestUtils.getField(controller, "cloud")).build();
        server.expect(requestTo("https://xiaojiapp.caacyj.com/yunjikeji-admin-api/app-api/yj/practices/p/sessions/s/question?mode=practice&index=0"))
                .andExpect(header("Authorization", "Bearer test-token"))
                .andRespond(withSuccess("{\"code\":401,\"msg\":\"expired\",\"data\":null}", MediaType.APPLICATION_JSON));
        JsonNode result = controller.getQuestion("p", "s", "practice", 0, "Bearer test-token", null, new MockHttpServletResponse());
        assertEquals(401, result.path("code").asInt());
        verifyNoInteractions(video);
        server.verify();
    }
}
