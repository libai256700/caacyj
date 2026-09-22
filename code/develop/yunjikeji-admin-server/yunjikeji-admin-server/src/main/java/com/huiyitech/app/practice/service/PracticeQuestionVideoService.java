package com.huiyitech.app.practice.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.huiyitech.app.practice.controller.vo.AppPracticeQuestionItemRespVO;
import com.huiyitech.practice.dal.dataobject.practice.PracticeExercisesDO;
import com.huiyitech.practice.dal.mysql.practice.PracticeExercisesMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

import javax.annotation.PreDestroy;
import javax.annotation.Resource;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class PracticeQuestionVideoService {
    @Resource
    private PracticeExercisesMapper exercisesMapper;

    @Value("${practice.video.endpoint:}")
    private String endpoint;
    @Value("${practice.video.access-key:}")
    private String accessKey;
    @Value("${practice.video.secret-key:}")
    private String secretKey;
    @Value("${practice.video.expiration-seconds:900}")
    private int expirationSeconds;
    private S3Presigner presigner;

    public void enrich(AppPracticeQuestionItemRespVO question) {
        if (question == null) {
            return;
        }
        PracticeExercisesDO exercise = resolveExercise(question);
        question.setVideoAvailable(false);
        question.setVideoUrl(null);
        question.setVideoExpiresAt(null);
        if (exercise == null) {
            return;
        }
        question.setExerciseId(exercise.getId());
        if (!StringUtils.hasText(exercise.getVideoBucket()) || !StringUtils.hasText(exercise.getVideoObjectKey())) {
            return;
        }
        question.setVideoAvailable(true);
        S3Presigner signer = getPresigner();
        if (signer == null) {
            return;
        }
        int lifetime = Math.max(60, Math.min(expirationSeconds, 3600));
        String url = signer.presignGetObject(GetObjectPresignRequest.builder()
                .signatureDuration(Duration.ofSeconds(lifetime))
                .getObjectRequest(b -> b.bucket(exercise.getVideoBucket()).key(exercise.getVideoObjectKey()))
                .build()).url().toString();
        question.setVideoUrl(url);
        question.setVideoExpiresAt(Instant.now().plusSeconds(lifetime).toEpochMilli());
    }

    private PracticeExercisesDO resolveExercise(AppPracticeQuestionItemRespVO question) {
        if (question.getExerciseId() != null) {
            PracticeExercisesDO exercise = exercisesMapper.selectById(question.getExerciseId());
            return exercise != null && Boolean.TRUE.equals(exercise.getQuestionStatus()) ? exercise : null;
        }
        if (!StringUtils.hasText(question.getStem())) {
            return null;
        }
        // Older cloud releases expose a batch id only. Never interpret it as a source exercise id.
        List<PracticeExercisesDO> matches = exercisesMapper.selectList(new LambdaQueryWrapper<PracticeExercisesDO>()
                        .eq(PracticeExercisesDO::getQuestionStem, question.getStem())
                        .eq(PracticeExercisesDO::getQuestionStatus, true)).stream()
                .filter(exercise -> question.getStem().equals(exercise.getQuestionStem()))
                .collect(Collectors.toList());
        return matches.size() == 1 ? matches.get(0) : null;
    }

    private synchronized S3Presigner getPresigner() {
        if (presigner == null && StringUtils.hasText(endpoint)
                && StringUtils.hasText(accessKey) && StringUtils.hasText(secretKey)) {
            presigner = S3Presigner.builder()
                    .endpointOverride(URI.create(endpoint))
                    .region(Region.US_EAST_1)
                    .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(accessKey, secretKey)))
                    .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
                    .build();
        }
        return presigner;
    }

    @PreDestroy
    public synchronized void close() {
        if (presigner != null) {
            presigner.close();
        }
    }
}
