package com.huiyitech.app.practice.service;

import com.huiyitech.app.practice.controller.vo.AppPracticeRecordAnswerRespVO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Category 14 only. Keeps career assessment isolated from SelfAssessmentV3RuleEngine.
 */
final class CareerPlanningRuleEngine {

    static final int FORM_VERSION = 2;
    private static final Logger log = LoggerFactory.getLogger(CareerPlanningRuleEngine.class);
    private static final List<String> RIASEC_TYPES = Arrays.asList("R", "I", "A", "S", "E", "C");
    private static final Map<String, String> RIASEC_NAMES = riasecNames();
    private static final List<String> RIASEC_QUESTION_TYPES = Arrays.asList(
            "R", "I", "A", "S", "E", "C", "R", "I", "A", "S", "E", "C");
    private static final List<String> VALUE_OPTIONS = Arrays.asList(
            "收入回报", "稳定保障", "成长空间", "自主自由", "助人意义", "挑战新鲜", "被认可", "生活平衡");
    private static final List<String> STYLE_KEYS = Arrays.asList("interaction", "decision", "pace", "orientation");
    private static final List<String> STYLE_NAMES = Arrays.asList("能量与互动", "决策依据", "工作节奏", "任务取向");
    private static final List<String> STYLE_A = Arrays.asList("独立深耕", "数据逻辑", "求快求变", "结果推动");
    private static final List<String> STYLE_B = Arrays.asList("协作互动", "人际感受", "求稳求精", "流程规范");
    private static final List<List<String>> STYLE_SOURCE_OPTIONS_A = Arrays.asList(
            Arrays.asList("一个人安静做自己的事", "先自己研究明白", "把一块事情钻透的人"),
            Arrays.asList("数据、事实和利弊", "直接指出问题", "证据和逻辑"),
            Arrays.asList("节奏快、常有新挑战", "愿意快速调整", "边用边学"),
            Arrays.asList("尽快拿到结果", "围绕目标调整方法", "有冲劲、敢拍板")
    );
    private static final List<List<String>> STYLE_SOURCE_OPTIONS_B = Arrays.asList(
            Arrays.asList("和朋友同事聊聊天", "先找人讨论想法", "把大家串起来的人"),
            Arrays.asList("自己和相关人的感受", "先肯定再提醒", "诚意和共情"),
            Arrays.asList("节奏稳、把事做扎实", "希望尽量保持原计划", "系统学完再上手"),
            Arrays.asList("过程规范不留隐患", "优先守住规则", "可靠、细致、有条理")
    );
    private static final Set<String> ALLOWED_HTML_TAGS = new LinkedHashSet<>(Arrays.asList(
            "h1", "h2", "h3", "p", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td",
            "blockquote", "strong", "br", "hr"));
    private static final Set<String> VOID_HTML_TAGS = new LinkedHashSet<>(Arrays.asList("br", "hr"));
    private static final List<String> REQUIRED_H1 = Arrays.asList("一、我的现状盘点", "二、优势与待发展方向", "三、下一步发展计划");
    private static final Pattern HTML_TAG = Pattern.compile("<\\s*(/?)\\s*([A-Za-z][\\w-]*)([^<>]*?)>");
    private static final Pattern FENCED_HTML = Pattern.compile("(?is)^```(?:html)?\\s*|\\s*```$");
    private static final Pattern UNSAFE_HTML = Pattern.compile("(?is)<(?:script|iframe)\\b|\\son\\w+\\s*=|javascript\\s*:");
    private static final Pattern PRIVACY_COPY = Pattern.compile(
            "(?is)本报告仅供本人|仅你本人可见|内容保密|隐私|个人信息|数据访问范围|可见范围|授权(?:状态|同意)?|用户同意|"
                    + "第三方.{0,16}(?:披露|共享|提供|转交|泄露)|(?:填写|提交).{0,16}(?:信息|数据).{0,20}(?:仅|只)用于|"
                    + "privacy|personal\\s+(?:data|information)|consent|confidential|third\\s+part(?:y|ies)");
    private static final Pattern LICENSE_PROGRESSION_CLAIM = Pattern.compile(
            ".*(?:升级|加考|补考|补证|前置|前提|基础上|为基础|先.{0,10}(?:考|学|训练|考试|取得|获得|完成)|"
                    + "(?:考|学|训练|考试|取得|获得|完成).{0,10}(?:后|之后).{0,10}(?:再|才)|才能).*");
    private static final Pattern INVALID_LICENSE_MANDATE = Pattern.compile(
            "(?:(?:法律|法规|法定|监管|合规).{0,12}(?:规定|要求|必须|强制|应当|一律|只能|务必|需要).{0,12}(?:超视距|CAAC执照|执照))"
                    + "|(?:(?:全职|从业|就业).{0,12}(?:必须|强制|应当|一律|只能|务必|要求|需要).{0,12}(?:超视距|CAAC执照|执照))"
                    + "|(?:没有.{0,8}(?:CAAC执照|执照).{0,8}(?:不能|无法|不得).{0,8}(?:就业|从业|入职|工作))"
                    + "|(?:(?:所有|全部|任何).{0,6}(?:岗位|工作|职业|企业).{0,8}(?:都|均|一律)?(?:要求|需要|必须).{0,8}(?:CAAC执照|执照|超视距))",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    private static final Pattern NEGATED_LICENSE_MANDATE = Pattern.compile(
            "(?:(?:不是|并非|不属于|并不属于|不构成|不等于).{0,6}(?:法律|法规|法定|监管|合规).{0,6}(?:强制|要求|规定))"
                    + "|(?:(?:法律|法规|法定|监管|合规).{0,6}(?:不是|并非|不属于|不构成|不等于).{0,6}(?:强制|要求|规定))");

    private static Map<String, String> riasecNames() {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("R", "动手实操");
        result.put("I", "钻研分析");
        result.put("A", "创意表达");
        result.put("S", "助人教学");
        result.put("E", "开拓经营");
        result.put("C", "严谨规范");
        return result;
    }

    Result build(List<AppPracticeRecordAnswerRespVO> answers) {
        Map<Integer, String> values = answersByQuestionNo(answers);
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("mode", "self");
        input.put("formVersion", FORM_VERSION);
        input.put("name", clean(values.get(1), 40));
        input.put("age", clean(values.get(2), 30));
        input.put("education", clean(values.get(3), 40));
        input.put("major", clean(values.get(4), 80));
        input.put("currentRole", clean(values.get(5), 100));
        input.put("years", clean(values.get(6), 40));
        input.put("duties", clean(values.get(7), 600));
        input.put("certsList", cleanArray(values.get(8), 12, 80));
        input.put("certsOther", clean(values.get(9), 160));
        input.put("experience", clean(values.get(10), 1200));
        input.put("achievements", clean(values.get(11), 1200));
        input.put("interests", clean(values.get(12), 500));
        input.put("dislikes", clean(values.get(13), 500));
        List<Integer> riasecAnswers = riasecAnswers(values);
        input.put("riasecAnswers", riasecAnswers);
        input.put("interestDirections", cleanArray(values.get(26), 12, 80));
        Map<String, Object> style = style(values);
        input.put("style", style);
        Map<String, Object> workValues = new LinkedHashMap<>();
        // Preserve every submitted value here so the server can reject a fourth selection.
        workValues.put("top3", cleanArray(values.get(39), VALUE_OPTIONS.size(), 40));
        workValues.put("least", clean(values.get(40), 40));
        input.put("values", workValues);
        input.put("goal3y", clean(values.get(41), 800));
        input.put("trackPreference", clean(values.get(42), 100));
        input.put("targetJob", clean(values.get(43), 160));
        input.put("targetJD", clean(values.get(44), 4000));
        input.put("obstacle", clean(values.get(45), 800));
        input.put("firstStep", clean(values.get(46), 500));
        input.put("weeklyHours", clean(values.get(47), 40));
        validate(input);

        Map<String, Object> assessment = new LinkedHashMap<>();
        assessment.put("riasec", scoreRiasec(riasecAnswers));
        assessment.put("style", scoreStyle(style));
        assessment.put("values", workValues);
        Map<String, Object> bundle = new LinkedHashMap<>();
        bundle.put("mode", "self");
        bundle.put("coreVersion", "career-planning-core/1.0.0");
        bundle.put("formVersion", FORM_VERSION);
        bundle.put("input", input);
        bundle.put("assessment", assessment);
        return new Result(input, bundle, formatPromptData(input, assessment));
    }

    String validateAndNormalizeReport(String raw) {
        if (!StringUtils.hasText(raw)) throw invalid("职业规划报告为空");
        String html = FENCED_HTML.matcher(raw.trim()).replaceAll("").trim();
        if (!html.startsWith("<") || html.length() > 200000 || UNSAFE_HTML.matcher(html).find()) {
            throw invalid("职业规划报告HTML不符合安全要求");
        }
        HtmlInspection inspection = inspectHtml(html);
        if (!inspection.unsupportedTags.isEmpty() || !inspection.tagsWithAttributes.isEmpty()
                || !inspection.structuralErrors.isEmpty() || html.contains("<!--")) {
            throw invalid("职业规划报告HTML结构不符合要求");
        }
        int visibleLength = inspection.visibleText.codePointCount(0, inspection.visibleText.length());
        if (!REQUIRED_H1.equals(extractH1Titles(html))) {
            throw invalid("职业规划报告章节不符合要求");
        }
        auditContentIssues(inspection.visibleText, visibleLength);
        return html;
    }

    private Map<Integer, String> answersByQuestionNo(List<AppPracticeRecordAnswerRespVO> answers) {
        if (answers == null || answers.size() != 47) throw invalid("职业规划评测题目不完整");
        Map<Integer, String> result = new LinkedHashMap<>();
        for (AppPracticeRecordAnswerRespVO answer : answers) {
            Integer no = answer == null ? null : answer.getNo();
            if (no == null || no < 1 || no > 47 || result.put(no, answer.getAnswer()) != null) {
                throw invalid("职业规划评测题目顺序异常");
            }
        }
        if (result.size() != 47) throw invalid("职业规划评测题目不完整");
        return result;
    }

    private List<Integer> riasecAnswers(Map<Integer, String> values) {
        List<Integer> result = new ArrayList<>();
        for (int index = 14; index <= 25; index++) {
            String answer = clean(values.get(index), 32);
            if ("不太想做".equals(answer)) result.add(0);
            else if ("可以尝试".equals(answer)) result.add(1);
            else if ("很想做".equals(answer)) result.add(2);
            else throw invalid("兴趣倾向题必须全部作答");
        }
        return result;
    }

    private Map<String, Object> style(Map<Integer, String> values) {
        List<Map<String, Object>> answers = new ArrayList<>();
        for (int questionNo = 27; questionNo <= 38; questionNo++) {
            String answer = clean(values.get(questionNo), 64);
            if (!StringUtils.hasText(answer)) continue;
            int dimension = (questionNo - 27) / 3;
            int indexWithinDimension = (questionNo - 27) % 3;
            String side;
            if (STYLE_SOURCE_OPTIONS_A.get(dimension).get(indexWithinDimension).equals(answer)) side = "a";
            else if (STYLE_SOURCE_OPTIONS_B.get(dimension).get(indexWithinDimension).equals(answer)) side = "b";
            else throw invalid("工作风格答案无效");
            answers.add(orderedMap(
                    "questionNo", questionNo,
                    "dimensionIndex", dimension,
                    "answer", side
            ));
        }
        if (answers.isEmpty()) return orderedMap("source", "skip", "answeredCount", 0, "answers", Collections.emptyList());
        return orderedMap("source", "quiz", "answeredCount", answers.size(), "answers", answers);
    }

    @SuppressWarnings("unchecked")
    private void validate(Map<String, Object> input) {
        if (!StringUtils.hasText((String) input.get("name"))) throw invalid("姓名不能为空");
        if (!StringUtils.hasText((String) input.get("achievements"))) throw invalid("成果经历不能为空");
        List<String> top3 = (List<String>) ((Map<String, Object>) input.get("values")).get("top3");
        String least = (String) ((Map<String, Object>) input.get("values")).get("least");
        if (top3.size() != 3 || new LinkedHashSet<>(top3).size() != 3 || !VALUE_OPTIONS.containsAll(top3)) {
            throw invalid("最看重的工作价值必须刚好包含3项");
        }
        if (StringUtils.hasText(least) && (!VALUE_OPTIONS.contains(least) || top3.contains(least))) {
            throw invalid("最不看重项不能与最看重项重复");
        }
    }

    private Map<String, Object> scoreRiasec(List<Integer> answers) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        for (String type : RIASEC_TYPES) scores.put(type, 0);
        for (int index = 0; index < answers.size(); index++) {
            scores.put(RIASEC_QUESTION_TYPES.get(index), scores.get(RIASEC_QUESTION_TYPES.get(index)) + answers.get(index));
        }
        List<String> ranked = new ArrayList<>(RIASEC_TYPES);
        ranked.sort(Comparator.comparingInt((String type) -> scores.get(type)).reversed()
                .thenComparingInt(RIASEC_TYPES::indexOf));
        boolean exploration = scores.get(ranked.get(0)) <= 2;
        List<String> top2 = exploration ? Collections.emptyList() : new ArrayList<>(ranked.subList(0, 2));
        List<String> labels = new ArrayList<>();
        for (String type : top2) labels.add(RIASEC_NAMES.get(type));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scores", scores);
        result.put("top2", top2);
        result.put("exploration", exploration);
        result.put("labels", labels);
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> scoreStyle(Map<String, Object> style) {
        if ("skip".equals(style.get("source"))) return orderedMap("source", "skip", "answeredCount", 0, "dimensions", Collections.emptyList());
        List<Map<String, Object>> answers = (List<Map<String, Object>>) style.get("answers");
        List<Map<String, Object>> dimensions = new ArrayList<>();
        for (int dimension = 0; dimension < 4; dimension++) {
            int a = 0;
            int b = 0;
            int answered = 0;
            for (Map<String, Object> answer : answers) {
                if (!Integer.valueOf(dimension).equals(answer.get("dimensionIndex"))) continue;
                if ("a".equals(answer.get("answer"))) a++;
                else if ("b".equals(answer.get("answer"))) b++;
                answered++;
            }
            if (answered == 0) continue;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("key", STYLE_KEYS.get(dimension));
            item.put("name", STYLE_NAMES.get(dimension));
            if (a == b) {
                item.put("tendency", "均衡待确认");
                item.put("strength", "balanced");
            } else {
                String side = a > b ? "a" : "b";
                item.put("tendency", "a".equals(side) ? STYLE_A.get(dimension) : STYLE_B.get(dimension));
                item.put("strength", answered == 1 ? "initial" : (Math.max(a, b) == answered ? "clear" : "slight"));
            }
            item.put("counts", orderedMap("a", a, "b", b, "answered", answered));
            dimensions.add(item);
        }
        return orderedMap("source", style.get("source"), "answeredCount", style.get("answeredCount"), "dimensions", dimensions);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> formatPromptData(Map<String, Object> input, Map<String, Object> assessment) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (String key : Arrays.asList("name", "age", "education", "major", "currentRole", "years", "duties", "experience",
                "achievements", "interests", "dislikes", "interestDirections", "goal3y", "trackPreference", "targetJob", "targetJD",
                "obstacle", "firstStep", "weeklyHours")) result.put(key, input.get(key));
        List<String> certificates = new ArrayList<>((List<String>) input.get("certsList"));
        String certOther = (String) input.get("certsOther");
        if (StringUtils.hasText(certOther)) certificates.add(certOther);
        result.put("certificates", certificates);
        Map<String, Object> riasec = (Map<String, Object>) assessment.get("riasec");
        result.put("assessedInterest", Boolean.TRUE.equals(riasec.get("exploration"))
                ? "各方向兴趣较均衡，仍在探索期" : join((List<String>) riasec.get("labels")));
        result.put("values", input.get("values"));
        Map<String, Object> style = (Map<String, Object>) assessment.get("style");
        if ("skip".equals(style.get("source"))) result.put("assessedStyle", "本次未测");
        else {
            List<String> formatted = new ArrayList<>();
            for (Map<String, Object> item : (List<Map<String, Object>>) style.get("dimensions")) {
                formatted.add(item.get("name") + "：" + item.get("tendency"));
            }
            result.put("assessedStyle", join(formatted));
        }
        return result;
    }

    private HtmlInspection inspectHtml(String html) {
        Matcher matcher = HTML_TAG.matcher(html);
        List<String> stack = new ArrayList<>();
        Set<String> unsupported = new LinkedHashSet<>();
        Set<String> attributes = new LinkedHashSet<>();
        Set<String> structural = new LinkedHashSet<>();
        StringBuilder visible = new StringBuilder();
        int cursor = 0;
        while (matcher.find()) {
            String between = html.substring(cursor, matcher.start());
            if (between.contains("<")) structural.add("unparseable_tag");
            visible.append(between);
            String tag = matcher.group(2).toLowerCase(Locale.ROOT);
            String tail = matcher.group(3) == null ? "" : matcher.group(3).trim();
            boolean closing = "/".equals(matcher.group(1));
            boolean selfClosing = tail.endsWith("/");
            String attributeText = selfClosing ? tail.substring(0, tail.length() - 1).trim() : tail;
            if (!ALLOWED_HTML_TAGS.contains(tag)) unsupported.add(tag);
            if (!attributeText.isEmpty()) attributes.add(tag);
            if (closing) {
                if (selfClosing || VOID_HTML_TAGS.contains(tag) || stack.isEmpty() || !tag.equals(stack.remove(stack.size() - 1))) structural.add("tag_order");
            } else if (!VOID_HTML_TAGS.contains(tag)) {
                if (selfClosing) structural.add("nonvoid_self_closing"); else stack.add(tag);
            }
            cursor = matcher.end();
        }
        String tail = html.substring(cursor);
        if (tail.contains("<")) structural.add("unparseable_tail");
        visible.append(tail);
        if (!stack.isEmpty()) structural.add("unclosed_tag");
        return new HtmlInspection(normalizeText(visible.toString()), unsupported, attributes, structural);
    }

    private List<String> extractH1Titles(String html) {
        List<String> titles = new ArrayList<>();
        Matcher matcher = Pattern.compile("<h1>(.*?)</h1>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL).matcher(html);
        while (matcher.find()) titles.add(normalizeText(matcher.group(1).replaceAll("<[^>]+>", "")));
        return titles;
    }

    private void auditContentIssues(String text, int visibleLength) {
        LinkedHashSet<String> auditIssues = new LinkedHashSet<>();
        if (visibleLength < 300 || visibleLength > 3500) {
            auditIssues.add("career_visible_length_out_of_range visibleCodePoints=" + visibleLength + " min=300 max=3500");
        }
        if (PRIVACY_COPY.matcher(text).find()) {
            auditIssues.add("career_privacy_copy_detected");
        }
        collectInvalidLicenseClaims(text, auditIssues);
        for (String auditIssue : auditIssues) {
            log.warn("Career assessment AI audit issue={}", auditIssue);
        }
    }

    private void collectInvalidLicenseClaims(String text, Set<String> auditIssues) {
        for (String sentence : text.split("[。！？!?；;\\n]")) {
            String normalized = normalizeText(sentence);
            if (!StringUtils.hasText(normalized)) continue;
            if (normalized.contains("视距内") && normalized.contains("超视距")
                    && LICENSE_PROGRESSION_CLAIM.matcher(normalized).matches()) {
                auditIssues.add("career_license_progression " + normalized);
            }
            for (String clause : normalized.split("[，,：:]")) {
                String clauseText = normalizeText(clause);
                if (isInvalidLicenseMandate(clauseText)) {
                    auditIssues.add("career_license_mandate " + clauseText);
                }
            }
            if (mentionsLicenseTopic(normalized)
                    && !NEGATED_LICENSE_MANDATE.matcher(normalized).find()
                    && INVALID_LICENSE_MANDATE.matcher(normalized).find()) {
                auditIssues.add("career_license_mandate " + normalized);
            }
        }
    }

    private boolean isInvalidLicenseMandate(String clause) {
        if (!StringUtils.hasText(clause) || !mentionsLicenseTopic(clause)) return false;
        if (NEGATED_LICENSE_MANDATE.matcher(clause).find()) return false;
        return INVALID_LICENSE_MANDATE.matcher(clause).find();
    }

    private boolean mentionsLicenseTopic(String clause) {
        return clause.contains("超视距") || clause.contains("CAAC执照") || clause.contains("执照");
    }

    private static String clean(String value, int max) {
        if (value == null) return "";
        String normalized = value.replace("\u0000", "").trim();
        return normalized.length() <= max ? normalized : normalized.substring(0, max);
    }

    private static List<String> cleanArray(String value, int maxItems, int maxLength) {
        if (!StringUtils.hasText(value)) return new ArrayList<>();
        LinkedHashSet<String> result = new LinkedHashSet<>();
        for (String item : value.split("、")) {
            String cleaned = clean(item, maxLength);
            if (StringUtils.hasText(cleaned)) result.add(cleaned);
            if (result.size() == maxItems) break;
        }
        return new ArrayList<>(result);
    }

    private static String normalizeText(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").trim();
    }

    private static String join(List<String> values) {
        return values == null || values.isEmpty() ? "" : String.join("、", values);
    }

    private static IllegalArgumentException invalid(String message) {
        return new IllegalArgumentException(message);
    }

    private static Map<String, Object> orderedMap(Object... values) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int index = 0; index < values.length; index += 2) result.put((String) values[index], values[index + 1]);
        return result;
    }

    static final class Result {
        private final Map<String, Object> input;
        private final Map<String, Object> bundle;
        private final Map<String, Object> promptData;

        Result(Map<String, Object> input, Map<String, Object> bundle, Map<String, Object> promptData) {
            this.input = input;
            this.bundle = bundle;
            this.promptData = promptData;
        }

        Map<String, Object> getInput() { return input; }
        Map<String, Object> getBundle() { return bundle; }
        Map<String, Object> getPromptData() { return promptData; }
    }

    private static final class HtmlInspection {
        private final String visibleText;
        private final Set<String> unsupportedTags;
        private final Set<String> tagsWithAttributes;
        private final Set<String> structuralErrors;

        private HtmlInspection(String visibleText, Set<String> unsupportedTags, Set<String> tagsWithAttributes,
                               Set<String> structuralErrors) {
            this.visibleText = visibleText;
            this.unsupportedTags = unsupportedTags;
            this.tagsWithAttributes = tagsWithAttributes;
            this.structuralErrors = structuralErrors;
        }
    }
}
