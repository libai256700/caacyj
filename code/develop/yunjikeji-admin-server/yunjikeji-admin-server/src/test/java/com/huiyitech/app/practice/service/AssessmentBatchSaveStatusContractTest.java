package com.huiyitech.app.practice.service;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AssessmentBatchSaveStatusContractTest {

    private static final String JAVA_ROOT = "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/"
            + "src/main/java/";

    @Test
    void batchModelAndLatestStatusDto_shouldExposeSaveStatus() throws Exception {
        String batch = readJava("com/huiyitech/practice/dal/dataobject/practice/PracticeCatalogBatchDO.java");
        String status = readJava("com/huiyitech/app/practice/controller/vo/AppAssessmentResultStatusRespVO.java");

        assertTrue(batch.contains("private Integer status;"),
                "DEV-078 RED: PracticeCatalogBatchDO must map yj_practice_catalog_batch.status");
        assertTrue(status.contains("private Integer batchSaveStatus;"),
                "DEV-078 RED: latest-status DTO must add batchSaveStatus without replacing existing fields");
    }

    @Test
    void startBatch_shouldCreateStatusZeroAndNeverEnterSaving() throws Exception {
        String batchService = readJava("com/huiyitech/app/practice/service/FrontPracticeBatchService.java");
        String startBatch = methodBody(batchService, "private AppPracticeStartRespVO startBatch");

        assertTrue(compact(startBatch).contains(".status(0)"),
                "DEV-078 RED: a new batch must explicitly start at status 0");
        assertFalse(compact(startBatch).contains(".status(1)"),
                "startBatch and record creation must never mark answer persistence as started");
    }

    @Test
    void firstAssessmentDetailWrite_shouldConditionallyMoveZeroToOneBeforeInsert() throws Exception {
        String batchService = readJava("com/huiyitech/app/practice/service/FrontPracticeBatchService.java");
        String mapper = readJava("com/huiyitech/practice/dal/mysql/practice/PracticeCatalogBatchMapper.java");
        String persistProgress = methodBody(batchService, "private void persistProgress");
        String compactMapper = compact(mapper);
        String lowerCaseMapper = compactMapper.toLowerCase();

        assertTrue(compactMapper.contains("status=1") && compactMapper.contains("status=0")
                        && compactMapper.contains("is_completed=0"),
                "DEV-078 RED: mapper needs a conditional 0 -> 1 update guarded by is_completed=0");
        int markSaving = firstIndexOfAny(persistProgress,
                "markAssessmentBatchSaving", "markAssessmentSaving", "updateAssessmentBatchStatusToSaving");
        int writeDetail = persistProgress.indexOf("upsertRecordDetail");
        assertTrue(markSaving >= 0,
                "DEV-078 RED: assessment persistence must mark status 1 at the first detail-write boundary");
        assertTrue(writeDetail >= 0 && markSaving < writeDetail,
                "DEV-078 RED: conditional status 1 must be applied before the first answer detail is persisted");
        assertTrue(persistProgress.contains("isAssessmentSession"),
                "DEV-078 RED: the saving transition must be limited to assessment categories 13 and 14");
    }

    @Test
    void categoryCompletionPoints_shouldMoveToTwoWithoutChangingCareerReportEntry() throws Exception {
        String batchService = readJava("com/huiyitech/app/practice/service/FrontPracticeBatchService.java");
        String controller = readJava("com/huiyitech/app/practice/controller/FrontPracticeController.java");
        String service = readJava("com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        String persistProgress = methodBody(batchService, "private void persistProgress");
        String completeCareer = methodBody(batchService, "private void completeCatalogBatch");
        String markFinished = methodBody(batchService, "private void markAssessmentBatchFinished");
        String reportEntry = methodBody(service,
                "public AppAssessmentResultStatusRespVO getLatestCareerAssessmentReportEntry");

        assertTrue(hasStatusFinishTransition(persistProgress),
                "DEV-078 RED: category 13 must write status=2 at its existing final save point");
        assertTrue(hasStatusFinishTransition(completeCareer),
                "DEV-078 RED: category 14 must write status=2 at completeCareerAssessment");
        assertTrue(compact(completeCareer).contains(".completed(Boolean.TRUE)"),
                "DEV-078 RED: category 14 original is_completed flow must stay on completeCatalogBatch");
        assertTrue(compact(markFinished).contains("batchUpdate.setStatus(2);"),
                "DEV-078 RED: success status finish helper must update status only");
        assertFalse(compact(markFinished).contains("completed(")
                        || compact(markFinished).contains("setcompleted("),
                "success status finish helper must not add or replace is_completed logic");
        assertTrue(controller.contains("/app-api/yj/practices/assessment-result/career/report-entry"),
                "career report-entry endpoint semantics must remain available");
        assertTrue(compact(reportEntry).contains(
                        ".eq(PracticeCatalogBatchDO::getCompleted,Boolean.TRUE)"),
                "career report-entry must keep selecting completed batches only");
    }

    @Test
    void failedAnswerPersistence_shouldFinishInRequiresNewBoundaryAndRethrow() throws Exception {
        String allPracticeServices = readJavaTree("com/huiyitech/app/practice/service");
        String batchService = readJava("com/huiyitech/app/practice/service/FrontPracticeBatchService.java");
        String transactionService = readJava(
                "com/huiyitech/app/practice/service/AssessmentBatchSaveStatusTransactionService.java");
        String mapper = readJava("com/huiyitech/practice/dal/mysql/practice/PracticeCatalogBatchMapper.java");
        String submitAnswer = methodBody(batchService, "public AppPracticeAnswerSubmitRespVO submitAnswer");
        String finishAfterFailure = methodBody(transactionService, "public void finishAssessmentBatchAfterFailure");
        String compactMapper = compact(mapper);
        String lowerCaseMapper = compactMapper.toLowerCase();

        assertTrue(allPracticeServices.contains("REQUIRES_NEW")
                        || allPracticeServices.contains("PROPAGATION_REQUIRES_NEW"),
                "DEV-078 RED: failure status 2 must commit outside the rolled-back answer transaction");
        assertTrue(submitAnswer.contains("catch"),
                "DEV-078 RED: answer persistence failure must be intercepted only to finish the save state");
        assertTrue(firstIndexOfAny(submitAnswer,
                "finishAssessmentBatchAfterFailure", "markAssessmentBatchFinishedAfterFailure") >= 0,
                "DEV-078 RED: failed answer persistence must mark status 2 at the reliable failure boundary");
        assertTrue(submitAnswer.contains("throw"),
                "DEV-078 RED: the original persistence exception must still propagate after status 2 is recorded");
        assertFalse(compact(finishAfterFailure).contains("completed(")
                        || compact(finishAfterFailure).contains("setcompleted("),
                "failure compensation must not update is_completed");
        assertTrue(lowerCaseMapper.contains("setstatus=2"),
                "DEV-078 RED: failure compensation must finish the save state with status=2");
        assertFalse(lowerCaseMapper.contains("setis_completed"),
                "failure compensation SQL must not overwrite is_completed");
    }

    @Test
    void latestStatus_shouldProjectZeroOneTwoWithCategoryIsolation() throws Exception {
        String controller = readJava("com/huiyitech/app/practice/controller/FrontPracticeController.java");
        String service = readJava("com/huiyitech/app/practice/service/FrontPracticeServiceImpl.java");
        String statusDto = readJava("com/huiyitech/app/practice/controller/vo/AppAssessmentResultStatusRespVO.java");

        assertTrue(statusDto.contains("batchSaveStatus"),
                "DEV-078 RED: API response must expose batchSaveStatus");
        assertTrue(service.contains("getLatestAssessmentResultStatus(loginUser.getId(), SELF_ASSESSMENT_CATEGORY_ID)"),
                "DEV-078 RED: category 13 latest-status must use the category-scoped latest query");
        assertTrue(service.contains("getLatestAssessmentResultStatus(loginUser.getId(), CAREER_ASSESSMENT_CATEGORY_ID)"),
                "DEV-078 RED: category 14 latest-status must use its own category-scoped latest query");
        assertTrue(service.contains(".batchSaveStatus(0)"),
                "DEV-078 RED: no-batch latest-status must return batchSaveStatus 0");
        assertTrue(service.contains("latest.getStatus()"),
                "DEV-078 RED: latest-status must project the stored batch status, not infer it from report state");
        assertTrue(controller.contains("/app-api/yj/practices/assessment-result/career/latest-status"),
                "DEV-078 RED: category 14 needs a dedicated latest-status endpoint separate from report-entry");
    }

    @Test
    void everySavingUpdate_shouldExcludeAlreadyFinishedStatus() throws Exception {
        String mapper = compact(readJava(
                "com/huiyitech/practice/dal/mysql/practice/PracticeCatalogBatchMapper.java"));
        int update = mapper.indexOf("status=1");

        assertTrue(update >= 0, "DEV-078 RED: status 1 conditional update is missing");
        int boundary = mapper.indexOf(";", update);
        String statement = boundary < 0 ? mapper.substring(update) : mapper.substring(update, boundary);
        assertTrue(statement.contains("status=0") || statement.contains("status=1"),
                "DEV-078 RED: a status 1 update must only operate within unfinished save states");
        assertFalse(statement.contains("status=2"),
                "DEV-078 RED: a status 1 update must exclude finished status 2 so it can never regress");
    }

    private static boolean hasStatusFinishTransition(String method) {
        String compactMethod = compact(method);
        return compactMethod.contains(".status(2)")
                || firstIndexOfAny(method, "markAssessmentBatchFinished", "finishAssessmentBatch") >= 0;
    }

    private static int firstIndexOfAny(String source, String... candidates) {
        int first = -1;
        for (String candidate : candidates) {
            int index = source.indexOf(candidate);
            if (index >= 0 && (first < 0 || index < first)) {
                first = index;
            }
        }
        return first;
    }

    private static String compact(String source) {
        return source.replaceAll("\\s+", "");
    }

    private static String methodBody(String source, String signature) {
        int signatureStart = source.indexOf(signature);
        assertTrue(signatureStart >= 0, "method missing: " + signature);
        int bodyStart = source.indexOf('{', signatureStart);
        assertTrue(bodyStart >= 0, "method body missing: " + signature);
        int depth = 0;
        for (int index = bodyStart; index < source.length(); index++) {
            char current = source.charAt(index);
            if (current == '{') {
                depth++;
            } else if (current == '}') {
                depth--;
                if (depth == 0) {
                    return source.substring(bodyStart, index + 1);
                }
            }
        }
        throw new AssertionError("unterminated method: " + signature);
    }

    private static String readJava(String relativePath) throws IOException {
        return readRepoFile(JAVA_ROOT + relativePath);
    }

    private static String readJavaTree(String relativeDirectory) throws IOException {
        Path root = repoRoot().resolve(JAVA_ROOT).resolve(relativeDirectory);
        try (Stream<Path> stream = Files.walk(root)) {
            return stream.filter(path -> Files.isRegularFile(path) && path.toString().endsWith(".java"))
                    .map(path -> {
                        try {
                            return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
                        } catch (IOException exception) {
                            throw new IllegalStateException(exception);
                        }
                    })
                    .collect(Collectors.joining("\n"));
        }
    }

    private static String readRepoFile(String relativePath) throws IOException {
        return new String(Files.readAllBytes(repoRoot().resolve(relativePath)), StandardCharsets.UTF_8);
    }

    private static Path repoRoot() {
        Path current = Paths.get(System.getProperty("user.dir")).toAbsolutePath();
        while (current != null && !Files.exists(current.resolve(".git"))) {
            current = current.getParent();
        }
        if (current == null) {
            throw new AssertionError("repository root not found");
        }
        return current;
    }
}
