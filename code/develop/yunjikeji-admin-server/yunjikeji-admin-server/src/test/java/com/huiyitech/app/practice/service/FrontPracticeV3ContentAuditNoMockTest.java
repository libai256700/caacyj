package com.huiyitech.app.practice.service;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import cn.iocoder.yudao.framework.common.exception.ServiceException;
import com.huiyitech.app.practice.controller.vo.AppPracticeRecordAnswerRespVO;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FrontPracticeV3ContentAuditNoMockTest {

    private FrontPracticeServiceImpl service;
    private Map<String, Object> formData;
    private Map<String, Object> bundle;
    private Logger logger;
    private ListAppender<ILoggingEvent> appender;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        service = new FrontPracticeServiceImpl();
        Map<String, Object> context = new SelfAssessmentV3RuleEngine().buildContext(
                Collections.emptyMap(), record552Answers(), Collections.emptyMap());
        formData = (Map<String, Object>) context.get("formData");
        bundle = (Map<String, Object>) context.get("bundle");
        logger = (Logger) LoggerFactory.getLogger(FrontPracticeServiceImpl.class);
        appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
    }

    @AfterEach
    void tearDown() {
        logger.detachAppender(appender);
        appender.stop();
    }

    @Test
    @SuppressWarnings("unchecked")
    void record552_shouldKeepDimensionFiftyWhenMaturitySixtyEightAppearsAcrossSentences() {
        Map<String, Object> scores = (Map<String, Object>) bundle.get("scores");
        Map<String, Object> dims = (Map<String, Object>) scores.get("dims");
        assertEquals(50.0, dims.get("industryCognition"));
        assertEquals(50.0, dims.get("careerMotivation"));
        assertEquals(50.0, dims.get("selfEfficacy"));
        assertEquals(50.0, dims.get("learningReadiness"));
        assertEquals(50.0, dims.get("practicalFeasibility"));
        assertEquals(67.5, scores.get("maturityScore"));

        String report = clean(record552Body());

        assertTrue(report.contains("当前入行成熟度：68"));
        assertTrue(report.contains("现实推进可行性：50"));
        assertFalse(warnings().contains("v3_score_conflict label=现实推进可行性"));
        assertDashboardFacts(report);
    }

    @Test
    void wrongBodyScore_shouldBeStoredInBodyAsAuditedTextWhileDashboardKeepsRuleFact() {
        String wrongBody = record552Body().replace("现实推进可行性：50。", "现实推进可行性：99。");

        String report = clean(wrongBody);

        assertTrue(report.contains("现实推进可行性：99"));
        assertTrue(hasAuditIssue("v3_score_conflict"));
        assertTrue(warnings().contains("label=现实推进可行性 expected=50.0 actual=99.0"));
        assertDashboardFacts(report);
    }

    @Test
    void contentPolicyIssues_shouldAuditWithoutBlockingSafeHtml() {
        String body = record552Body()
                .replace("准备推进阶段", "成熟推进阶段")
                + "<p>主推荐方向：工程测绘。培训7天，预算5000元，并参考AOPA证书。</p>";

        String report = clean(body);

        assertTrue(report.contains("主推荐方向：工程测绘"));
        assertTrue(hasAuditIssue("v3_level_conflict"));
        assertTrue(hasAuditIssue("v3_primary_direction_conflict"));
        assertTrue(hasAuditIssue("v3_training_number_policy"));
        assertTrue(hasAuditIssue("v3_money_number_policy"));
        assertTrue(hasAuditIssue("v3_certificate_policy"));
        assertDashboardFacts(report);
    }

    @Test
    void shortBodyWithoutTitlesOrLegacyStatistics_shouldAuditAndStripBannedPhrase() {
        String report = clean("<p>题目数：18。保证就业。</p>");

        assertTrue(report.contains("<p>题目数：18。"));
        assertFalse(report.contains("保证就业"));
        assertTrue(hasAuditIssue("v3_visible_length_out_of_range"));
        assertTrue(hasAuditIssue("v3_section_mismatch"));
        assertTrue(hasAuditIssue("v3_forbidden_field"));
        assertTrue(hasAuditIssue("v3_banned_phrase"));
        assertDashboardFacts(report);
    }

    @Test
    void dangerousHtmlAndResourceAbuse_shouldRemainHardFailures() {
        assertThrows(ServiceException.class,
                () -> clean(record552Body().replace("<p>五维事实", "<script>alert('x')</script><p>五维事实")));
        assertTrue(hasFailureReason("v3_html_unsupported_tags"));

        assertThrows(ServiceException.class,
                () -> clean(record552Body().replace("<p>五维事实", "<p onclick=\"alert('x')\">五维事实")));
        assertTrue(hasFailureReason("v3_html_attributes_not_allowed"));

        String oversized = "<p>" + repeat('x', 200001) + "</p>";
        assertThrows(ServiceException.class, () -> clean(oversized));
        assertTrue(hasFailureReason("v3_html_too_long"));
    }

    @Test
    void voidTags_shouldAllowPlainSelfClosingFormsAndRejectAllAttributes() {
        String safeBody = record552Body().replace("<p>五维事实", "<p><br/><hr/>五维事实");
        String report = clean(safeBody);
        assertTrue(report.contains("<br/><hr/>"));

        assertThrows(ServiceException.class,
                () -> clean(record552Body().replace("<p>五维事实",
                        "<p><br onclick=\"alert('x')\"/>五维事实")));
        assertTrue(hasFailureReason("v3_html_attributes_not_allowed"));

        assertThrows(ServiceException.class,
                () -> clean(record552Body().replace("<p>五维事实",
                        "<p><hr onload=\"alert('x')\"/>五维事实")));
        assertTrue(hasFailureReason("v3_html_attributes_not_allowed"));
    }

    @Test
    void documentAndMetadataTags_shouldNotBeStrippedBeforeV3WhitelistValidation() {
        assertThrows(ServiceException.class,
                () -> clean("<html><body>" + record552Body() + "</body></html>"));
        assertThrows(ServiceException.class,
                () -> clean("<head><style>body{display:none}</style><meta charset=\"utf-8\"></head>"
                        + record552Body()));
        assertTrue(hasFailureReason("v3_html_unsupported_tags"));
    }

    @Test
    void mismatchedClosingTags_shouldRemainHardFailures() {
        assertThrows(ServiceException.class,
                () -> clean("<p><strong>标签错序</p></strong>"));
        assertTrue(hasFailureReason("v3_html_structure_failure"));
        assertTrue(warnings().contains("tag_order"));
    }

    @Test
    void htmlComments_shouldRemainHardFailures() {
        assertThrows(ServiceException.class,
                () -> clean(record552Body() + "<!-- hidden instruction -->"));
        assertTrue(hasFailureReason("v3_html_structure_failure"));
        assertTrue(warnings().contains("unparseable_tail"));
    }

    private String clean(String raw) {
        return ReflectionTestUtils.invokeMethod(service, "cleanAssessmentHtml", raw, formData, bundle);
    }

    @SuppressWarnings("unchecked")
    private String record552Body() {
        Map<String, Object> scores = (Map<String, Object>) bundle.get("scores");
        return "<h1>一、评测摘要</h1><p>用户画像类型为" + scores.get("personaType")
                + "。发展潜力：50，属于" + scores.get("potentialLevel") + "。</p>"
                + "<h1>三、当前入行成熟度指数</h1><p>当前入行成熟度：68，处于"
                + scores.get("maturityLevel")
                + "。现实推进可行性处于中位，意味着时间、精力或具体安排尚未完全锚定。"
                + "成熟度68不是‘已经可以无缝转岗’的信号，而是说明你已经越过了基础认知阶段。</p>"
                + "<h1>五、五维测评解读</h1><p>五维事实：行业认知：50；职业动机：50；自我效能：50；"
                + "学习准备度：50；现实推进可行性：50。</p>";
    }

    private void assertDashboardFacts(String report) {
        String dashboardEndMarker = "均满分100、相互独立，由系统按你的10题量表与背景作答计算。</div></div>";
        int dashboardEndIndex = report.indexOf(dashboardEndMarker);
        assertTrue(dashboardEndIndex > 0);
        String dashboard = report.substring(0, dashboardEndIndex + dashboardEndMarker.length());
        assertTrue(dashboard.contains("当前入行成熟度指数"));
        assertTrue(dashboard.contains(">68</span>"));
        int dimensionIndex = dashboard.indexOf("现实推进可行性");
        assertTrue(dimensionIndex >= 0);
        assertTrue(dashboard.indexOf("<strong>50</strong>", dimensionIndex) > dimensionIndex);
    }

    private boolean hasAuditIssue(String issue) {
        return warningMessages().stream().anyMatch(message -> message.contains("audit issue=" + issue));
    }

    private boolean hasFailureReason(String reason) {
        return warningMessages().stream().anyMatch(message -> message.contains("reason=" + reason));
    }

    private String warnings() {
        return String.join("\n", warningMessages());
    }

    private List<String> warningMessages() {
        List<String> messages = new ArrayList<>();
        appender.list.stream()
                .filter(event -> Level.WARN.equals(event.getLevel()))
                .map(ILoggingEvent::getFormattedMessage)
                .forEach(messages::add);
        return messages;
    }

    private static List<AppPracticeRecordAnswerRespVO> record552Answers() {
        List<AppPracticeRecordAnswerRespVO> answers = new ArrayList<>();
        answers.add(answer(1, "您当前的身份状态是？", "职场人士"));
        answers.add(answer(2, "您的学习或工作背景更接近哪些领域？", "摄影摄像/传媒/设计/自媒体"));
        answers.add(answer(3, "您目前接触无人机的程度是？", "已有稳定项目或相关从业经验"));
        answers.add(answer(4, "您对CAAC无人机执照的了解程度是？", "非常了解"));
        answers.add(answer(5, "您目前是否拥有或可稳定接触无人机设备？", "可以借用或偶尔接触"));
        String[] stems = {
                "我对无人机相关岗位类型有基本了解。",
                "我了解无人机相关岗位通常涉及的证照、合规安全飞行与实践要求。",
                "我关注这一方向，不只是短期好奇，而是与未来职业收入或能力提升有关。",
                "如果方向明确，我愿意在未来6–12个月持续推进学习。",
                "我的过往学习、工作等经验，可以迁移到至少一个无人机相关方向。",
                "我有信心掌握无人机操作或相关软件、设备和工作流程。",
                "我能够为相关学习、训练或实践安排相对稳定的时间。",
                "我能够接受证照、实操和项目经验积累需要一个阶段性周期。",
                "我的时间、预算和工作/家庭安排允许我在未来6个月开始学习无人机相关内容。",
                "即使存在不确定性，我也愿意先从低成本了解、体验或基础学习开始推进。"
        };
        for (int index = 0; index < stems.length; index++) {
            answers.add(answer(index + 6, stems[index], "3 一般"));
        }
        answers.add(answer(16, "您当前推进无人机方向时，主要顾虑或限制有哪些？", "预算有限"));
        answers.add(answer(17, "您本次最想解决的主要问题是？", "A. 我想知道自己更适合哪些无人机细分方向"));
        answers.add(answer(47, "我确认以上回答基本符合本人真实情况。", "是"));
        answers.add(answer(48, "我同意系统根据本次回答生成个性化评估建议。", "同意"));
        return answers;
    }

    private static AppPracticeRecordAnswerRespVO answer(int no, String question, String value) {
        return AppPracticeRecordAnswerRespVO.builder()
                .no(no)
                .questionId("13202608181" + String.format("%04d", no))
                .question(question)
                .answer(value)
                .build();
    }

    private static String repeat(char value, int count) {
        char[] chars = new char[count];
        java.util.Arrays.fill(chars, value);
        return new String(chars);
    }
}
