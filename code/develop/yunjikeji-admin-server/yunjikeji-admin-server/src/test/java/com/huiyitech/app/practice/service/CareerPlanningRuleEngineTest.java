package com.huiyitech.app.practice.service;

import com.huiyitech.app.practice.controller.vo.AppPracticeRecordAnswerRespVO;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CareerPlanningRuleEngineTest {

    private final CareerPlanningRuleEngine engine = new CareerPlanningRuleEngine();
    private static final String[] STYLE_SOURCE_ANSWERS = {
            "一个人安静做自己的事", "先自己研究明白", "把一块事情钻透的人",
            "数据、事实和利弊", "直接指出问题", "证据和逻辑",
            "节奏快、常有新挑战", "愿意快速调整", "边用边学",
            "尽快拿到结果", "围绕目标调整方法", "有冲劲、敢拍板"
    };

    @Test
    void build_shouldMapAll47AnswersAndCalculateSourceRiasecAndStyle() {
        CareerPlanningRuleEngine.Result result = engine.build(validAnswers());

        assertEquals(2, result.getInput().get("formVersion"));
        assertEquals("张三", result.getInput().get("name"));
        assertEquals("完成一次无人机项目", result.getInput().get("achievements"));
        Map<String, Object> assessment = map(result.getBundle().get("assessment"));
        Map<String, Object> riasec = map(assessment.get("riasec"));
        assertEquals(java.util.Arrays.asList("R", "I"), riasec.get("top2"));
        assertFalse((Boolean) riasec.get("exploration"));
        Map<String, Object> style = map(assessment.get("style"));
        assertEquals("quiz", style.get("source"));
        assertEquals(4, ((List<?>) style.get("dimensions")).size());
        assertEquals("动手实操、钻研分析", result.getPromptData().get("assessedInterest"));
    }

    @Test
    void build_shouldAllowAllOptionalFieldsEmptyAndWholeStyleSkip() {
        List<AppPracticeRecordAnswerRespVO> answers = validAnswers();
        answers.get(1).setAnswer("");
        answers.get(2).setAnswer("");
        for (int index = 26; index < 38; index++) answers.get(index).setAnswer("");
        answers.get(39).setAnswer("");
        for (int index = 40; index < 47; index++) answers.get(index).setAnswer("");

        CareerPlanningRuleEngine.Result result = engine.build(answers);

        Map<String, Object> style = map(map(result.getBundle().get("assessment")).get("style"));
        assertEquals("skip", style.get("source"));
        assertEquals("本次未测", result.getPromptData().get("assessedStyle"));
    }

    @Test
    void build_shouldAllowPartialWorkStyleAnswersAndOnlySummarizeAnsweredDimensions() {
        List<AppPracticeRecordAnswerRespVO> answers = validAnswers();
        for (int index = 26; index < 38; index++) answers.get(index).setAnswer("");
        answers.get(26).setAnswer("一个人安静做自己的事");
        answers.get(27).setAnswer("先找人讨论想法");
        answers.get(29).setAnswer("数据、事实和利弊");
        answers.get(37).setAnswer("可靠、细致、有条理");

        CareerPlanningRuleEngine.Result result = engine.build(answers);

        Map<String, Object> assessment = map(result.getBundle().get("assessment"));
        Map<String, Object> style = map(assessment.get("style"));
        assertEquals("quiz", style.get("source"));
        assertEquals(4, style.get("answeredCount"));
        List<Map<String, Object>> dimensions = castList(style.get("dimensions"));
        assertEquals(3, dimensions.size());
        assertEquals("均衡待确认", dimensions.get(0).get("tendency"));
        assertEquals("数据逻辑", dimensions.get(1).get("tendency"));
        assertEquals("流程规范", dimensions.get(2).get("tendency"));
        assertEquals("能量与互动：均衡待确认、决策依据：数据逻辑、任务取向：流程规范", result.getPromptData().get("assessedStyle"));
    }

    @Test
    void build_shouldUseSourceExplorationThresholdWhenEveryInterestScoreIsLow() {
        List<AppPracticeRecordAnswerRespVO> answers = validAnswers();
        for (int index = 13; index <= 24; index++) answers.get(index).setAnswer("不太想做");

        Map<String, Object> riasec = map(map(engine.build(answers).getBundle().get("assessment")).get("riasec"));

        assertTrue((Boolean) riasec.get("exploration"));
        assertEquals(java.util.Collections.emptyList(), riasec.get("top2"));
    }

    @Test
    void build_shouldRejectMissingMandatoryAndCrossQuestionViolations() {
        List<AppPracticeRecordAnswerRespVO> missingName = validAnswers();
        missingName.get(0).setAnswer(" ");
        assertThrows(IllegalArgumentException.class, () -> engine.build(missingName));

        List<AppPracticeRecordAnswerRespVO> missingAchievement = validAnswers();
        missingAchievement.get(10).setAnswer(" ");
        assertThrows(IllegalArgumentException.class, () -> engine.build(missingAchievement));

        List<AppPracticeRecordAnswerRespVO> missingInterest = validAnswers();
        missingInterest.get(13).setAnswer(" ");
        assertThrows(IllegalArgumentException.class, () -> engine.build(missingInterest));

        List<AppPracticeRecordAnswerRespVO> repeatedLeast = validAnswers();
        repeatedLeast.get(39).setAnswer("收入回报");
        assertThrows(IllegalArgumentException.class, () -> engine.build(repeatedLeast));

        List<AppPracticeRecordAnswerRespVO> wrongTopCount = validAnswers();
        wrongTopCount.get(38).setAnswer("收入回报、稳定保障");
        assertThrows(IllegalArgumentException.class, () -> engine.build(wrongTopCount));

        List<AppPracticeRecordAnswerRespVO> tooManyTopValues = validAnswers();
        tooManyTopValues.get(38).setAnswer("收入回报、稳定保障、成长空间、自主自由");
        assertThrows(IllegalArgumentException.class, () -> engine.build(tooManyTopValues));
    }

    @Test
    void validateAndNormalizeReport_shouldEnforceCareerOnlyStructureAndSafety() {
        String valid = "<h1>一、我的现状盘点</h1><p>" + repeated("基于本次作答梳理当前基础和已有经历，建议把真实体验作为后续选择依据。", 5)
                + "</p><h1>二、优势与待发展方向</h1><p>" + repeated("兴趣、价值取向和实际投入共同用于判断适合优先尝试的方向，结论需要在实践中继续确认。", 5)
                + "</p><h1>三、下一步发展计划</h1><p>" + repeated("未来九十天先完成一个可验证的小任务，记录过程和成果，再根据反馈调整方向。", 5) + "</p>";
        assertEquals(valid, engine.validateAndNormalizeReport(valid));

        assertThrows(IllegalArgumentException.class,
                () -> engine.validateAndNormalizeReport("<h1>一、我的现状盘点</h1><script>alert(1)</script>" + repeated("测试", 200)));
        assertThrows(IllegalArgumentException.class,
                () -> engine.validateAndNormalizeReport("<h1>错误标题</h1><p>" + repeated("测试内容。", 100) + "</p>"));
        String privacyAudited = "<h1>一、我的现状盘点</h1><p>" + repeated("隐私内容。", 100)
                + "</p><h1>二、优势与待发展方向</h1><p>" + repeated("测试内容。", 100)
                + "</p><h1>三、下一步发展计划</h1><p>" + repeated("测试内容。", 100) + "</p>";
        assertEquals(privacyAudited, engine.validateAndNormalizeReport(privacyAudited));
    }

    @Test
    void build_withPartialWorkStyleShouldStillPassCareerReportValidation() {
        List<AppPracticeRecordAnswerRespVO> answers = validAnswers();
        for (int index = 26; index < 38; index++) answers.get(index).setAnswer("");
        answers.get(26).setAnswer("一个人安静做自己的事");
        answers.get(29).setAnswer("数据、事实和利弊");

        CareerPlanningRuleEngine.Result result = engine.build(answers);
        String valid = "<h1>一、我的现状盘点</h1><p>" + repeated("基于已提交的姓名、成果、兴趣和工作风格作答，先整理当前阶段的真实起点。", 5)
                + "</p><h1>二、优势与待发展方向</h1><p>" + repeated("已答的工作风格题只作为当前倾向信号，需要继续通过实践观察来校准。", 5)
                + "</p><h1>三、下一步发展计划</h1><p>" + repeated("结合当前作答先安排小步验证任务，再根据结果持续修正职业方向。", 5) + "</p>";

        assertEquals("能量与互动：独立深耕、决策依据：数据逻辑", result.getPromptData().get("assessedStyle"));
        assertEquals(valid, engine.validateAndNormalizeReport(valid));
    }

    @Test
    void build_shouldRejectInvalidPartialWorkStyleOption() {
        List<AppPracticeRecordAnswerRespVO> answers = validAnswers();
        for (int index = 26; index < 38; index++) answers.get(index).setAnswer("");
        answers.get(26).setAnswer("独立深耕");

        assertThrows(IllegalArgumentException.class, () -> engine.build(answers));
    }

    @Test
    void validateAndNormalizeReport_shouldAllowNegatedOrScopedLicenseAdvice() {
        String[] allowedParagraphs = {
                "如果全职目标直接考虑超视距，这是职业规划建议，不是法规强制要求。",
                "全职考虑超视距只是职业建议，并非法律强制要求。",
                "如果涉及飞行或教学培训，搜索公开的无人机驾驶员培训要求和低空教学岗位要求。"
        };

        for (String paragraph : allowedParagraphs) {
            String report = careerReportWithPlanParagraph(paragraph);
            assertEquals(report, engine.validateAndNormalizeReport(report));
        }
    }

    @Test
    void validateAndNormalizeReport_shouldRejectInvalidLicenseMandates() {
        String[] auditedParagraphs = {
                "法律规定全职从业必须直接报考超视距。",
                "没有CAAC执照不能就业。",
                "所有岗位都要求CAAC执照。",
                "老师建议你遵守法规要求，必须直接报考超视距。"
        };

        for (String paragraph : auditedParagraphs) {
            String report = careerReportWithPlanParagraph(paragraph);
            assertEquals(report, engine.validateAndNormalizeReport(report));
        }
    }

    private static List<AppPracticeRecordAnswerRespVO> validAnswers() {
        List<AppPracticeRecordAnswerRespVO> result = new ArrayList<>();
        for (int number = 1; number <= 47; number++) {
            result.add(AppPracticeRecordAnswerRespVO.builder().no(number).answer("").build());
        }
        result.get(0).setAnswer("张三");
        result.get(10).setAnswer("完成一次无人机项目");
        for (int index = 13; index <= 24; index++) result.get(index).setAnswer("很想做");
        for (int index = 0; index < STYLE_SOURCE_ANSWERS.length; index++) result.get(26 + index).setAnswer(STYLE_SOURCE_ANSWERS[index]);
        result.get(38).setAnswer("收入回报、稳定保障、成长空间");
        result.get(39).setAnswer("自主自由");
        return result;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) {
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> castList(Object value) {
        return (List<Map<String, Object>>) value;
    }

    private static String repeated(String value, int count) {
        StringBuilder builder = new StringBuilder();
        for (int index = 0; index < count; index++) builder.append(value);
        return builder.toString();
    }

    private static String careerReportWithPlanParagraph(String planParagraph) {
        return "<h1>一、我的现状盘点</h1><p>" + repeated("基于本次作答梳理当前基础和已有经历，建议把真实体验作为后续选择依据。", 5)
                + "</p><h1>二、优势与待发展方向</h1><p>" + repeated("兴趣、价值取向和实际投入共同用于判断适合优先尝试的方向，结论需要在实践中继续确认。", 5)
                + "</p><h1>三、下一步发展计划</h1><p>" + repeated("未来九十天先完成一个可验证的小任务，记录过程和成果，再根据反馈调整方向。", 4)
                + planParagraph + "</p>";
    }
}
