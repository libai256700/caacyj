package com.huiyitech.app.practice.service;

import com.huiyitech.app.practice.controller.vo.AppPracticeRecordAnswerRespVO;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * V3 self-assessment rule engine. The scoring and direction rules mirror the
 * portable evaluation-report V3 core; this component has no persistence or AI
 * side effects and only produces deterministic facts and prompts.
 */
@Component
public class SelfAssessmentV3RuleEngine {

    private static final List<String> DIRECTIONS = Arrays.asList("航拍传媒", "工程测绘", "行业巡检", "农业植保", "无人机清洗",
            "无人机配送", "应急救援", "无人机培训", "装调维修", "无人机表演", "低空运营管理");
    private static final List<String> DIM_KEYS = Arrays.asList("industryCognition", "careerMotivation", "selfEfficacy",
            "learningReadiness", "practicalFeasibility");
    private static final Map<String, List<String>> DIM_QUESTIONS = new LinkedHashMap<>();
    private static final Map<String, String> DIM_LABELS = new LinkedHashMap<>();
    private static final Map<String, Integer> DRONE_SCORE = new HashMap<>();
    private static final Map<String, Integer> CAAC_SCORE = new HashMap<>();
    private static final Map<String, Integer> EQUIPMENT_SCORE = new HashMap<>();
    private static final Map<String, List<String>> BACKGROUND_MAP = new HashMap<>();
    private static final Map<String, List<String>> CAPABILITY_MAP = new HashMap<>();
    private static final Map<String, String> FEATURE_KEYS = new LinkedHashMap<>();
    private static final Map<String, Integer> ACCEPT_SCORE = new HashMap<>();
    private static final Map<String, List<String>> DIRECTION_FEATURES = new LinkedHashMap<>();
    private static final List<HardCap> HARD_CAPS = new ArrayList<>();
    private static final Map<String, ConcernRule> CONCERN_MAP = new LinkedHashMap<>();
    private static final Map<String, List<String>> LEARNING_RECOMMENDATIONS = new LinkedHashMap<>();
    private static final Map<String, String> SIDE_ADVICE = new LinkedHashMap<>();
    private static final Map<String, String> CAREER_MODE = new HashMap<>();
    private static final Map<String, String> GOAL_SECTIONS = new LinkedHashMap<>();
    private static final Map<String, String> LIKERT_QUESTION_BY_ID = new LinkedHashMap<>();
    private static final Map<String, String> LIKERT_QUESTION_BY_STEM = new LinkedHashMap<>();
    private static final Map<String, String> CATEGORY13_QUESTION_STEMS = new LinkedHashMap<>();
    private static final Set<String> CATEGORY13_REQUIRED_QUESTION_IDS = new LinkedHashSet<>();
    private static final Map<String, String> WORK_FEATURE_BY_QUESTION_ID = new LinkedHashMap<>();
    private static final Map<String, String> REPORT_GOAL_BY_ANSWER = new LinkedHashMap<>();
    private static final String CATEGORY13_QUESTION_ID_PREFIX = "13202608181";
    private static final String LOCAL_RESOURCE_FALLBACK = "当前未检索到可核验的本地资源，建议通过民航管理部门、招聘平台、当地低空经济产业园区或正规培训机构进一步核实。";
    private static final String V3_LEVEL_NATURAL_EXPLANATION_RULE = "【V3 等级自然解释规则（最高优先级，违反即不合格）】\n"
            + "1. 报告开头的程序评分仪表盘是系统确定性事实，已原样展示发展潜力、当前入行成熟度的分数与官方等级名称。\n"
            + "2. 报告正文必须以该仪表盘为准，不得重新计算、修改、质疑或另行判定分数与等级。\n"
            + "3. 正文允许对官方等级作不改变含义的自然语言解释，无需逐字重复官方等级名称；但不得出现与系统等级冲突的任何其他官方等级名称。";

    static {
        DIM_QUESTIONS.put("industryCognition", Arrays.asList("a1", "a2"));
        DIM_QUESTIONS.put("careerMotivation", Arrays.asList("b1", "b2"));
        DIM_QUESTIONS.put("selfEfficacy", Arrays.asList("c1", "c2"));
        DIM_QUESTIONS.put("learningReadiness", Arrays.asList("d1", "d2"));
        DIM_QUESTIONS.put("practicalFeasibility", Arrays.asList("e1", "e2"));
        DIM_LABELS.put("industryCognition", "行业认知");
        DIM_LABELS.put("careerMotivation", "职业动机");
        DIM_LABELS.put("selfEfficacy", "自我效能");
        DIM_LABELS.put("learningReadiness", "学习准备度");
        DIM_LABELS.put("practicalFeasibility", "现实推进可行性");
        DRONE_SCORE.put("完全没有接触，只想先了解", 0);
        DRONE_SCORE.put("操作过消费级无人机或参加过体验活动", 25);
        DRONE_SCORE.put("有过自学或少量实操，但未参加系统培训", 50);
        DRONE_SCORE.put("参加过系统培训或已持有相关证照，但尚未正式从业", 75);
        DRONE_SCORE.put("已有稳定项目或相关从业经验", 100);
        CAAC_SCORE.put("完全不了解", 0);
        CAAC_SCORE.put("听说过但不清楚", 35);
        CAAC_SCORE.put("比较了解", 70);
        CAAC_SCORE.put("非常了解", 100);
        EQUIPMENT_SCORE.put("没有", 0);
        EQUIPMENT_SCORE.put("可以借用或偶尔接触", 50);
        EQUIPMENT_SCORE.put("有可稳定使用的设备", 100);
        put(BACKGROUND_MAP, "理工/工程/测绘/建筑", "工程测绘", "行业巡检", "低空运营管理");
        put(BACKGROUND_MAP, "电子/机械/维修/自动化", "装调维修", "行业巡检", "无人机清洗");
        put(BACKGROUND_MAP, "农业/植保/农村相关", "农业植保");
        put(BACKGROUND_MAP, "摄影摄像/传媒/设计/自媒体", "航拍传媒", "无人机表演");
        put(BACKGROUND_MAP, "教育/培训/语言表达", "无人机培训");
        put(BACKGROUND_MAP, "计算机/软件/数据/AI", "工程测绘", "无人机配送", "低空运营管理");
        put(BACKGROUND_MAP, "销售/商务/运营/管理", "航拍传媒", "无人机培训", "低空运营管理");
        put(CAPABILITY_MAP, "摄影、剪辑、内容创作或自媒体运营能力", "航拍传媒", "无人机表演");
        put(CAPABILITY_MAP, "工程、测绘、施工、CAD或GIS相关基础", "工程测绘", "行业巡检");
        put(CAPABILITY_MAP, "农业、植保、农村场景或相关资源", "农业植保");
        put(CAPABILITY_MAP, "电子、机械、维修或自动化基础", "装调维修", "行业巡检", "无人机清洗");
        put(CAPABILITY_MAP, "教学培训、课程设计或表达能力", "无人机培训");
        put(CAPABILITY_MAP, "软件、数据、人工智能或建模工具能力", "工程测绘", "无人机配送", "低空运营管理");
        put(CAPABILITY_MAP, "销售、商务、运营或客户沟通能力", "航拍传媒", "无人机培训", "低空运营管理");
        FEATURE_KEYS.put("长时间户外作业", "outdoor");
        FEATURE_KEYS.put("经常出差或跨区域项目", "travel");
        FEATURE_KEYS.put("项目制工作，地点和时间存在变化", "projectBased");
        FEATURE_KEYS.put("前期收入可能不稳定", "incomeUnstable");
        FEATURE_KEYS.put("需要持续学习、训练或考证", "continuousLearning");
        FEATURE_KEYS.put("需要承担较强的飞行与安全责任", "safetyResponsibility");
        FEATURE_KEYS.put("需要维护设备或处理简单故障", "equipMaintenance");
        FEATURE_KEYS.put("需要较多客户沟通和团队协作", "clientTeamwork");
        ACCEPT_SCORE.put("可以接受", 100);
        ACCEPT_SCORE.put("视具体情况决定", 60);
        ACCEPT_SCORE.put("较难接受", 0);
        put(DIRECTION_FEATURES, "航拍传媒", "projectBased", "clientTeamwork", "incomeUnstable", "continuousLearning");
        put(DIRECTION_FEATURES, "工程测绘", "outdoor", "travel", "projectBased", "safetyResponsibility", "continuousLearning");
        put(DIRECTION_FEATURES, "行业巡检", "outdoor", "travel", "safetyResponsibility", "equipMaintenance");
        put(DIRECTION_FEATURES, "农业植保", "outdoor", "safetyResponsibility", "equipMaintenance", "projectBased");
        put(DIRECTION_FEATURES, "无人机清洗", "outdoor", "safetyResponsibility", "equipMaintenance");
        put(DIRECTION_FEATURES, "无人机配送", "safetyResponsibility", "clientTeamwork");
        put(DIRECTION_FEATURES, "应急救援", "outdoor", "travel", "safetyResponsibility", "clientTeamwork");
        put(DIRECTION_FEATURES, "无人机培训", "continuousLearning", "clientTeamwork");
        put(DIRECTION_FEATURES, "装调维修", "equipMaintenance", "continuousLearning");
        put(DIRECTION_FEATURES, "无人机表演", "projectBased", "clientTeamwork", "incomeUnstable");
        put(DIRECTION_FEATURES, "低空运营管理", "clientTeamwork", "projectBased", "safetyResponsibility");
        HARD_CAPS.add(new HardCap("outdoor", 55, Arrays.asList("农业植保", "工程测绘", "行业巡检", "无人机清洗", "应急救援"), "长时间户外作业"));
        HARD_CAPS.add(new HardCap("safetyResponsibility", 50, Arrays.asList("航拍传媒", "工程测绘", "行业巡检", "农业植保", "无人机清洗", "无人机配送", "应急救援", "无人机表演"), "较强的飞行与安全责任"));
        HARD_CAPS.add(new HardCap("equipMaintenance", 40, Collections.singletonList("装调维修"), "设备维护"));
        HARD_CAPS.add(new HardCap("clientTeamwork", 55, Arrays.asList("无人机培训", "航拍传媒", "无人机表演", "低空运营管理"), "客户沟通和团队协作"));
        addConcern("不了解行业真实情况", "industryInformationGap", "先了解岗位类型、实际工作内容和行业进入要求。");
        addConcern("不知道自己适合哪个方向", "directionUnclear", "优先生成细分方向匹配和方向验证任务。");
        addConcern("时间不足", "timeConstraint", "推荐碎片化学习、周末实践或延长准备周期。");
        addConcern("预算有限", "budgetConstraint", "优先推荐低成本了解、体验和分阶段投入，不直接推荐高投入方案。");
        addConcern("没有设备或实操机会", "practiceAccessGap", "推荐体验课、模拟训练、设备租借或正规机构实操。");
        addConcern("不了解证照与合规要求", "complianceKnowledgeGap", "增加证照、实名登记、合规飞行和安全责任说明。");
        addConcern("缺少行业资源", "resourceGap", "优先加入成熟团队、行业社群或通过项目实践积累资源。");
        addConcern("所在城市机会不清晰", "locationOpportunityUnclear", "只有用户选择本地资源模块时才检索具体资源。");
        addConcern("家庭或工作安排受限", "externalSupportConstraint", "采用低风险、分阶段推进方案。");
        addConcern("担心收入或就业不稳定", "incomeUncertaintyConcern", "不得承诺薪资或就业，优先进行岗位验证、实习和项目体验。");
        LEARNING_RECOMMENDATIONS.put("认知体验阶段", Arrays.asList("先了解岗位、证照和安全要求", "完成一次模拟或线下实操体验", "暂不建议立即进入高成本培训", "暂不建议直接规划高级证照"));
        LEARNING_RECOMMENDATIONS.put("系统入门阶段", Arrays.asList("理论学习与线下实操结合", "根据目标岗位确定是否需要考证", "先建立基础飞行和安全能力，再进入岗位技能训练"));
        LEARNING_RECOMMENDATIONS.put("准备推进阶段", Arrays.asList("系统培训、证照准备和岗位技能训练", "结合目标方向安排项目实践", "不承诺通过率、就业或收入"));
        SIDE_ADVICE.put("低风险试水型", "从低成本学习和小范围尝试起步，先积累第一批作品；暂不建议投入设备或高额费用。");
        SIDE_ADVICE.put("团队积累型", "优先加入成熟团队参与项目，用协作降低个人投入与试错风险，逐步积累客户与经验。");
        SIDE_ADVICE.put("作品变现准备型", "已有少量作品，重点是打磨案例、明确交付与定价，稳步扩大接单。");
        SIDE_ADVICE.put("资源驱动型", "已有较完整作品或客户资源，可围绕现有资源规划稳定变现与项目升级。");
        SIDE_ADVICE.put("创业条件尚不成熟", "创业意愿明确但技能/作品/客户/设备尚有缺口，建议先补齐核心能力与案例；暂不建议立即成立公司或大额投入。");
        CAREER_MODE.put("全职进入相关岗位", "全职进入");
        CAREER_MODE.put("在现有岗位中增加无人机能力", "现岗位赋能");
        CAREER_MODE.put("先实习/兼职积累经验", "实习兼职积累");
        CAREER_MODE.put("先实习兼职积累经验", "实习兼职积累");
        CAREER_MODE.put("先考证再决定", "考证观望");
        CAREER_MODE.put("暂不确定", "尚未确定");
        GOAL_SECTIONS.put("A", "细分方向匹配");
        GOAL_SECTIONS.put("B", "学习、实操、考证与培训路径");
        GOAL_SECTIONS.put("C", "就业与转行准备");
        GOAL_SECTIONS.put("D", "副业、自由接单与创业可行性");
        GOAL_SECTIONS.put("E", "本地学习与项目资源");
        GOAL_SECTIONS.put("F", "合规飞行与安全注意事项");
        GOAL_SECTIONS.put("G", "未来30—90天行动计划");
        putCategory13Question("132026081810001", "您当前的身份状态是？");
        putCategory13Question("132026081810002", "您的学习或工作背景更接近哪些领域？");
        putCategory13Question("132026081810003", "您目前接触无人机的程度是？");
        putCategory13Question("132026081810004", "您对CAAC无人机执照的了解程度是？");
        putCategory13Question("132026081810005", "您目前是否拥有或可稳定接触无人机设备？");
        putLikertQuestion("132026081810006", "a1", "我对无人机相关岗位类型有基本了解。");
        putLikertQuestion("132026081810007", "a2", "我了解无人机相关岗位通常涉及的证照、合规安全飞行与实践要求。");
        putLikertQuestion("132026081810008", "b1", "我关注这一方向，不只是短期好奇，而是与未来职业收入或能力提升有关。");
        putLikertQuestion("132026081810009", "b2", "如果方向明确，我愿意在未来6–12个月持续推进学习。");
        putLikertQuestion("132026081810010", "c1", "我的过往学习、工作等经验，可以迁移到至少一个无人机相关方向。");
        putLikertQuestion("132026081810011", "c2", "我有信心掌握无人机操作或相关软件、设备和工作流程。");
        putLikertQuestion("132026081810012", "d1", "我能够为相关学习、训练或实践安排相对稳定的时间。");
        putLikertQuestion("132026081810013", "d2", "我能够接受证照、实操和项目经验积累需要一个阶段性周期。");
        putLikertQuestion("132026081810014", "e1", "我的时间、预算和工作/家庭安排允许我在未来6个月开始学习无人机相关内容。");
        putLikertQuestion("132026081810015", "e2", "即使存在不确定性，我也愿意先从低成本了解、体验或基础学习开始推进。");
        putCategory13Question("132026081810016", "您当前推进无人机方向时，主要顾虑或限制有哪些？");
        putCategory13Question("132026081810017", "您本次最想解决的主要问题是？");
        putCategory13Question("132026081810018", "您最想评估的细分方向是？");
        putCategory13Question("132026081810019", "您目前具备或可以争取的相关能力与资源有哪些？");
        putCategory13Question("132026081810020", "对以下工作特征，您的接受程度如何？【长时间户外作业】");
        putCategory13Question("132026081810021", "对以下工作特征，您的接受程度如何？【经常出差或跨区域项目】");
        putCategory13Question("132026081810022", "对以下工作特征，您的接受程度如何？【项目制工作，地点和时间存在变化】");
        putCategory13Question("132026081810023", "对以下工作特征，您的接受程度如何？【前期收入可能不稳定】");
        putCategory13Question("132026081810024", "对以下工作特征，您的接受程度如何？【需要持续学习、训练或考证】");
        putCategory13Question("132026081810025", "对以下工作特征，您的接受程度如何？【需要承担较强的飞行与安全责任】");
        putCategory13Question("132026081810026", "对以下工作特征，您的接受程度如何？【需要维护设备或处理简单故障】");
        putCategory13Question("132026081810027", "对以下工作特征，您的接受程度如何？【需要较多客户沟通和团队协作】");
        putCategory13Question("132026081810028", "您现阶段学习无人机的主要目的是什么？");
        putCategory13Question("132026081810029", "您更倾向于哪种学习与实操方式？");
        putCategory13Question("132026081810030", "您目前每周可投入的有效学习时间大约是？");
        putCategory13Question("132026081810031", "您可接受的学习准备周期是？");
        putCategory13Question("132026081810032", "您当前可接受的学习或训练预算范围是？");
        putCategory13Question("132026081810033", "您更倾向的职业发展方式是？");
        putCategory13Question("132026081810034", "您选择相关岗位时最看重什么？");
        putCategory13Question("132026081810035", "您目前最大的就业或转行障碍是？");
        putCategory13Question("132026081810036", "您能否接受为相关岗位进行短期实习、项目体验或跨区域学习？");
        putCategory13Question("132026081810037", "您更希望尝试哪种发展形式？");
        putCategory13Question("132026081810038", "您目前是否已有可展示的作品、项目经历或潜在客户资源？");
        putCategory13Question("132026081810039", "您目前可接受哪种启动与投入方式？");
        putCategory13Question("132026081810040", "您认为自己当前最大的变现障碍是？");
        putCategory13Question("132026081810041", "您的常驻城市是？");
        putCategory13Question("132026081810042", "您目前最希望查找哪类本地资源？");
        putCategory13Question("132026081810043", "您可接受的地域范围是？");
        putCategory13Question("132026081810044", "您还有哪些特殊情况、补充需求或其他疑问？");
        putCategory13Question("132026081810045", "您希望报告如何称呼您？");
        putCategory13Question("132026081810046", "如需进一步沟通，您愿意留下联系方式吗？手机/微信");
        putCategory13Question("132026081810047", "我确认以上回答基本符合本人真实情况。");
        putCategory13Question("132026081810048", "我同意系统根据本次回答生成个性化评估建议。");
        for (int questionNo = 1; questionNo <= 17; questionNo++) {
            CATEGORY13_REQUIRED_QUESTION_IDS.add(category13QuestionId(questionNo));
        }
        CATEGORY13_REQUIRED_QUESTION_IDS.add(category13QuestionId(47));
        CATEGORY13_REQUIRED_QUESTION_IDS.add(category13QuestionId(48));
        WORK_FEATURE_BY_QUESTION_ID.put("132026081810020", "长时间户外作业");
        WORK_FEATURE_BY_QUESTION_ID.put("132026081810021", "经常出差或跨区域项目");
        WORK_FEATURE_BY_QUESTION_ID.put("132026081810022", "项目制工作，地点和时间存在变化");
        WORK_FEATURE_BY_QUESTION_ID.put("132026081810023", "前期收入可能不稳定");
        WORK_FEATURE_BY_QUESTION_ID.put("132026081810024", "需要持续学习、训练或考证");
        WORK_FEATURE_BY_QUESTION_ID.put("132026081810025", "需要承担较强的飞行与安全责任");
        WORK_FEATURE_BY_QUESTION_ID.put("132026081810026", "需要维护设备或处理简单故障");
        WORK_FEATURE_BY_QUESTION_ID.put("132026081810027", "需要较多客户沟通和团队协作");
        REPORT_GOAL_BY_ANSWER.put("A. 我想知道自己更适合哪些无人机细分方向", "A");
        REPORT_GOAL_BY_ANSWER.put("B. 我想了解学习、实操、考证及培训选择", "B");
        REPORT_GOAL_BY_ANSWER.put("C. 我想了解就业或转行前需要做哪些准备", "C");
        REPORT_GOAL_BY_ANSWER.put("D. 我想评估副业、自由接单或创业的可行性", "D");
        REPORT_GOAL_BY_ANSWER.put("E. 我想了解本地学习、实操、就业或项目资源", "E");
        REPORT_GOAL_BY_ANSWER.put("F. 我想了解合规飞行与安全注意事项", "F");
        REPORT_GOAL_BY_ANSWER.put("G. 我想获得未来30—90天行动计划", "G");
    }

    public Map<String, Object> buildContext(Map<String, Object> studentProfile,
                                             List<AppPracticeRecordAnswerRespVO> answers,
                                             Map<String, Object> statistics) {
        Map<String, Object> formData = adaptFormData(studentProfile, answers);
        requireCompleteLikert(formData);
        Map<String, Object> bundle = buildBundle(formData);
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("formData", formData);
        context.put("bundle", bundle);
        context.put("userPrompt", buildUserPrompt(formData, bundle));
        context.put("statistics", statistics == null ? Collections.emptyMap() : statistics);
        return context;
    }

    public Map<String, Object> adaptFormData(Map<String, Object> profile,
                                             List<AppPracticeRecordAnswerRespVO> answers) {
        Map<String, Object> form = new LinkedHashMap<>();
        form.put("evalVersion", 3);
        form.put("identity", firstNonBlank(profile, "identity", "roleLabel", "职场人士"));
        form.put("nickname", firstNonBlank(profile, "nickname", "name", ""));
        form.put("backgroundFields", new ArrayList<>(Collections.singletonList(mapBackground(firstNonBlank(profile, "major", "majorName", "")))));
        form.put("droneExposure", firstNonBlank(profile, "droneExposure", "完全没有接触，只想先了解"));
        form.put("caacAwareness", firstNonBlank(profile, "caacAwareness", "完全不了解"));
        form.put("equipmentAccess", firstNonBlank(profile, "equipmentAccess", "没有"));
        form.put("concerns", new ArrayList<String>());
        form.put("reportGoals", new ArrayList<String>());
        Map<String, Integer> likert = new LinkedHashMap<>();
        Map<String, Object> moduleA = new LinkedHashMap<>();
        moduleA.put("directions", new ArrayList<String>());
        moduleA.put("capabilities", new ArrayList<String>());
        Map<String, String> workFeatures = new LinkedHashMap<>();
        moduleA.put("workFeatures", workFeatures);
        form.put("moduleA", moduleA);
        form.put("moduleB", new LinkedHashMap<String, Object>());
        form.put("moduleC", new LinkedHashMap<String, Object>());
        form.put("moduleD", new LinkedHashMap<String, Object>());
        form.put("moduleE", new LinkedHashMap<String, Object>());
        Set<String> mappedCategory13QuestionIds = new LinkedHashSet<>();
        for (AppPracticeRecordAnswerRespVO answer : answers == null ? Collections.<AppPracticeRecordAnswerRespVO>emptyList() : answers) {
            String questionId = answer == null ? "" : safe(answer.getQuestionId()).trim();
            if (isCategory13QuestionId(questionId)) {
                if (mappedCategory13QuestionIds.contains(questionId)) {
                    throw new IllegalArgumentException("分类13 V3题目重复：Q" + category13QuestionNo(questionId));
                }
                mapCategory13Question(form, likert, answer);
                mappedCategory13QuestionIds.add(questionId);
                continue;
            }
            String question = answer == null ? "" : safe(answer.getQuestion());
            String value = answer == null ? "" : safe(answer.getAnswer());
            String all = question + " " + value;
            String lower = all.toLowerCase();
            mapIdentityAndBackground(form, all);
            mapOptionFields(form, question, value);
            mapLikert(likert, answer);
            mapGoals(form, question, value);
            mapModules(form, question, value);
            mapConsentFlags(form, question, value);
            if (lower.contains("顾虑") || lower.contains("担心")) addConcern(form, value);
        }
        form.put("likert", likert);
        if (!mappedCategory13QuestionIds.isEmpty()) {
            List<String> missingRequiredQuestions = CATEGORY13_REQUIRED_QUESTION_IDS.stream()
                    .filter(questionId -> !mappedCategory13QuestionIds.contains(questionId))
                    .map(questionId -> "Q" + category13QuestionNo(questionId))
                    .collect(Collectors.toList());
            if (!missingRequiredQuestions.isEmpty()) {
                throw new IllegalArgumentException("分类13 V3必答题缺失：" + String.join(",", missingRequiredQuestions));
            }
        }
        if (((List<?>) form.get("reportGoals")).isEmpty()) {
            if (!mappedCategory13QuestionIds.isEmpty()) {
                throw new IllegalArgumentException("分类13 V3报告目标无法映射，禁止静默默认A");
            }
            form.put("reportGoals", new ArrayList<>(Collections.singletonList("A")));
        }
        return form;
    }

    public Map<String, Object> buildBundle(Map<String, Object> formData) {
        Map<String, Object> scores = computeScoresV3(formData);
        List<String> goals = stringList(formData.get("reportGoals"));
        Map<String, Object> bundle = new LinkedHashMap<>();
        bundle.put("scores", scores);
        bundle.put("direction", goals.contains("A") ? directionMatch(formData) : null);
        bundle.put("concerns", concernTags(formData));
        bundle.put("learning", goals.contains("B") ? learningStage(formData, number(scores.get("maturityScore"))) : null);
        bundle.put("career", goals.contains("C") ? careerStructure(formData) : null);
        bundle.put("sideBiz", goals.contains("D") ? sideBusinessTag(formData) : null);
        return bundle;
    }

    public Map<String, Object> computeScoresV3(Map<String, Object> formData) {
        Map<String, Object> likert = map(formData.get("likert"));
        Map<String, Object> dims = new LinkedHashMap<>();
        for (String dim : DIM_KEYS) {
            List<String> keys = DIM_QUESTIONS.get(dim);
            double sum = 0;
            for (String key : keys) sum += standard(likert.get(key));
            dims.put(dim, round1(sum / keys.size()));
        }
        int drone = DRONE_SCORE.getOrDefault(safe(formData.get("droneExposure")), 0);
        int caac = CAAC_SCORE.getOrDefault(safe(formData.get("caacAwareness")), 0);
        int equipment = EQUIPMENT_SCORE.getOrDefault(safe(formData.get("equipmentAccess")), 0);
        double potential = round1(number(dims.get("careerMotivation")) * .40 + number(dims.get("selfEfficacy")) * .30 + number(dims.get("learningReadiness")) * .30);
        double maturity = round1(number(dims.get("industryCognition")) * .25 + drone * .25 + caac * .10 + equipment * .05 + number(dims.get("learningReadiness")) * .15 + number(dims.get("practicalFeasibility")) * .20);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("dims", dims);
        result.put("dimLabels", new LinkedHashMap<>(DIM_LABELS));
        result.put("droneExposureScore", drone);
        result.put("caacAwarenessScore", caac);
        result.put("equipmentAccessScore", equipment);
        result.put("potentialScore", potential);
        result.put("potentialLevel", potentialLevel(potential));
        result.put("maturityScore", maturity);
        result.put("maturityLevel", maturityLevel(maturity));
        result.put("personaType", personaType(potential, maturity));
        result.put("isExperienced", "已有稳定项目或相关从业经验".equals(formData.get("droneExposure")));
        List<Double> answered = new ArrayList<>();
        for (String key : Arrays.asList("a1", "a2", "b1", "b2", "c1", "c2", "d1", "d2", "e1", "e2")) {
            double value = number(likert.get(key));
            if (value >= 1 && value <= 5) answered.add(value);
        }
        Map<String, Object> flags = new LinkedHashMap<>();
        flags.put("straightLine", answered.size() == 10 && answered.stream().allMatch(value -> value.equals(answered.get(0))));
        flags.put("truthDenied", "否".equals(formData.get("truthConfirm")));
        flags.put("missingLikert", 10 - answered.size());
        result.put("flags", flags);
        return result;
    }

    private Map<String, Object> directionMatch(Map<String, Object> form) {
        Map<String, Object> module = map(form.get("moduleA"));
        List<String> directions = stringList(module.get("directions"));
        List<String> backgrounds = stringList(form.get("backgroundFields"));
        List<String> capabilities = stringList(module.get("capabilities"));
        boolean systemEval = directions.stream().anyMatch(item -> item.contains("暂不清楚"));
        Map<String, Integer> features = new HashMap<>();
        for (Map.Entry<String, Object> item : map(module.get("workFeatures")).entrySet()) {
            String key = FEATURE_KEYS.get(item.getKey());
            if (key != null) features.put(key, ACCEPT_SCORE.getOrDefault(safe(item.getValue()), 60));
        }
        List<Map<String, Object>> scored = new ArrayList<>();
        for (String direction : DIRECTIONS) {
            int interest = systemEval ? 60 : (directions.contains(direction) ? 100 : 20);
            List<String> bgHits = backgrounds.stream().filter(item -> BACKGROUND_MAP.getOrDefault(item, Collections.emptyList()).contains(direction)).collect(Collectors.toList());
            int background = bgHits.isEmpty() ? 40 : 100;
            List<String> capHits = capabilities.stream().filter(item -> CAPABILITY_MAP.getOrDefault(item, Collections.emptyList()).contains(direction)).collect(Collectors.toList());
            int capability = capHits.isEmpty() ? 40 : capHits.size() == 1 ? 70 : 100;
            List<String> feats = DIRECTION_FEATURES.get(direction);
            double work = feats.stream().mapToInt(key -> features.getOrDefault(key, 60)).average().orElse(60);
            double base = interest * .20 + background * .20 + capability * .35 + work * .25;
            int cap = 100;
            String capReason = null;
            for (HardCap rule : HARD_CAPS) if (features.getOrDefault(rule.key, 60) == 0 && rule.directions.contains(direction) && rule.cap < cap) {
                cap = rule.cap;
                capReason = "你对「" + rule.reason + "」接受度较低，该方向匹配上限已下调至 " + rule.cap;
            }
            double score = Math.min(base, cap);
            List<String> evidence = new ArrayList<>();
            if (interest == 100) evidence.add("你主动选择了这个方向");
            if (!bgHits.isEmpty()) evidence.add("你的背景「" + String.join("、", bgHits) + "」与该方向对口");
            if (!capHits.isEmpty()) evidence.add("你具备「" + String.join("、", capHits) + "」，可迁移到该方向");
            if (work >= 80) evidence.add("你能接受该方向的主要工作特征");
            if (evidence.isEmpty()) evidence.add("暂无直接的背景或能力衔接，主要来自系统综合评估");
            List<String> limitation = new ArrayList<>();
            if (capReason != null && cap < base) limitation.add(capReason);
            if (bgHits.isEmpty() && capHits.isEmpty()) limitation.add("目前缺少直接对口的背景或能力，需要从基础积累");
            if (work < 60) limitation.add("该方向的部分工作特征你接受度不高，正式投入前需再确认");
            if (limitation.isEmpty()) limitation.add("匹配度较高，仍建议先通过一次实操体验确认真实感受");
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("direction", direction); item.put("score", round1(score)); item.put("rawScore", round1(base));
            item.put("capped", cap < base); item.put("evidence", evidence); item.put("limitation", limitation);
            item.put("verification", "建议通过一次「" + direction + "」相关的线下实操体验或岗位实况了解来验证匹配度");
            scored.add(item);
        }
        scored.sort(Comparator.comparingDouble(item -> -number(item.get("score"))));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scored", scored);
        result.put("primary", scored.get(0));
        result.put("alternatives", new ArrayList<>(scored.subList(1, Math.min(3, scored.size()))));
        result.put("deprioritized", new ArrayList<>(scored.subList(Math.max(0, scored.size() - 2), scored.size())));
        result.put("systemEvaluated", systemEval);
        return result;
    }

    private List<Map<String, Object>> concernTags(Map<String, Object> form) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (String concern : stringList(form.get("concerns"))) {
            ConcernRule rule = CONCERN_MAP.get(concern);
            if (rule != null) {
                Map<String, Object> item = new LinkedHashMap<>(); item.put("concern", concern); item.put("tag", rule.tag); item.put("advice", rule.advice); result.add(item);
            }
        }
        return result;
    }

    private Map<String, Object> learningStage(Map<String, Object> form, double maturity) {
        Map<String, Object> module = map(form.get("moduleB"));
        String purpose = safe(module.get("purpose")), mode = safe(module.get("mode")), weekly = safe(module.get("weeklyTime")), period = safe(module.get("period")), budget = safe(module.get("budget"));
        String drone = safe(form.get("droneExposure"));
        boolean zero = normalize(drone).contains("完全没有接触");
        boolean cognitive = maturity < 45 || normalize(purpose).contains("先了解") || normalize(purpose).contains("体验飞行") || normalize(mode).contains("先体验一次") || normalize(weekly).contains("暂时无法") || (normalize(budget).contains("5000元以下") && zero);
        boolean weeklyOk = Arrays.asList("47小时", "8小时以上", "可阶段性集中投入").contains(normalize(weekly));
        boolean periodOk = StringUtils.hasText(period) && !normalize(period).contains("暂不确定");
        boolean budgetOk = StringUtils.hasText(budget) && !normalize(budget).contains("暂不确定");
        boolean goalClear = StringUtils.hasText(purpose) && !normalize(purpose).contains("暂不确定");
        boolean hasBase = Arrays.asList("有过自学", "参加过系统培训", "已有稳定项目").stream().anyMatch(k -> normalize(drone).contains(k));
        boolean ready = maturity >= 65 && goalClear && weeklyOk && periodOk && budgetOk && hasBase;
        String stage = cognitive ? "认知体验阶段" : ready ? "准备推进阶段" : "系统入门阶段";
        boolean teaching = normalize(purpose).contains("教学培训") || normalize(purpose).contains("科普");
        Map<String, Object> result = new LinkedHashMap<>(); result.put("learningStage", stage); result.put("learningRecommendation", LEARNING_RECOMMENDATIONS.get(stage));
        if (teaching && (zero || maturity < 65)) result.put("teachingNote", "教学方向起步只推荐课程助教、课程运营、科普内容与教学辅助；不直接推荐CAAC教员，待证照、飞行经验与实践积累具备后再作为中长期目标。");
        return result;
    }

    private Map<String, Object> sideBusinessTag(Map<String, Object> form) {
        Map<String, Object> module = map(form.get("moduleD")); List<String> forms = stringList(module.get("forms")); String portfolio = safe(module.get("portfolio")); String investment = safe(module.get("investment")); List<String> barriers = stringList(module.get("barriers"));
        boolean startup = forms.stream().anyMatch(item -> normalize(item).contains("成立团队或创业")); boolean noPortfolio = normalize(portfolio).contains("完全没有");
        List<String> gaps = Arrays.asList("技能不足", "缺少作品或案例", "缺少客户与渠道", "缺少设备").stream().filter(item -> barriers.stream().anyMatch(value -> normalize(value).contains(normalize(item)))).collect(Collectors.toList());
        String stage;
        if (startup && (noPortfolio || !gaps.isEmpty())) stage = "创业条件尚不成熟";
        else if (normalize(portfolio).contains("已有客户") || normalize(portfolio).contains("较完整")) stage = "资源驱动型";
        else if (normalize(portfolio).contains("少量")) stage = "作品变现准备型";
        else if (normalize(investment).contains("加入成熟团队") || forms.stream().anyMatch(item -> normalize(item).contains("与团队合作"))) stage = "团队积累型";
        else stage = "低风险试水型";
        Map<String, Object> result = new LinkedHashMap<>(); result.put("sideBusinessStage", stage); result.put("startingAdvice", SIDE_ADVICE.get(stage)); result.put("portfolioLevel", StringUtils.hasText(portfolio) ? portfolio : "未填"); result.put("barriers", barriers); return result;
    }

    private Map<String, Object> careerStructure(Map<String, Object> form) {
        Map<String, Object> module = map(form.get("moduleC")); Map<String, Object> result = new LinkedHashMap<>();
        String mode = safe(module.get("careerMode")); result.put("careerMode", CAREER_MODE.getOrDefault(mode, StringUtils.hasText(mode) ? mode : "尚未确定"));
        result.put("careerPriorities", stringList(module.get("priorities"))); result.put("careerGaps", stringList(module.get("gaps"))); result.put("mobilityLevel", StringUtils.hasText(safe(module.get("mobility"))) ? module.get("mobility") : "不确定"); return result;
    }

    private String buildUserPrompt(Map<String, Object> form, Map<String, Object> bundle) {
        Map<String, Object> scores = map(bundle.get("scores"));
        Map<String, Object> dims = map(scores.get("dims"));
        StringBuilder facts = new StringBuilder("=== 系统事实（规则引擎已算定；分数与官方等级由程序仪表盘原样展示，正文按等级自然解释规则处理，禁止改动/重算/另判）===\n");
        facts.append("报告称呼：").append(StringUtils.hasText(safe(form.get("nickname"))) ? form.get("nickname") : "你").append("\n");
        facts.append("【基础画像】身份：").append(join(form.get("identity"))).append("｜背景领域：").append(join(form.get("backgroundFields"))).append("｜无人机接触程度：").append(join(form.get("droneExposure"))).append("｜CAAC了解：").append(join(form.get("caacAwareness"))).append("｜设备：").append(join(form.get("equipmentAccess"))).append("\n");
        if (Boolean.TRUE.equals(scores.get("isExperienced"))) {
            facts.append("★该用户接触程度为「已有稳定项目或相关从业经验」，已超出入行评测主要适用范围：报告不得判断其是否适合入行，改为在结论中提示其更适合使用「职业发展梳理工具」做进阶规划。\n");
        }
        facts.append("【两大指数】发展潜力：").append(Math.round(number(scores.get("potentialScore")))).append("（").append(scores.get("potentialLevel")).append("）｜当前入行成熟度：").append(Math.round(number(scores.get("maturityScore")))).append("（").append(scores.get("maturityLevel")).append("）\n");
        facts.append(V3_LEVEL_NATURAL_EXPLANATION_RULE).append("\n");
        facts.append("【用户画像类型（程序判定，不得修改）】").append(scores.get("personaType")).append("\n");
        facts.append("【五维标准分 0-100】");
        for (String key : DIM_KEYS) {
            facts.append(DIM_LABELS.get(key)).append(" ").append(Math.round(number(dims.get(key))))
                    .append("practicalFeasibility".equals(key) ? "（正向，越高越易开始行动）" : "｜");
        }
        List<Map<String, Object>> concerns = (List<Map<String, Object>>) bundle.get("concerns");
        facts.append("\n【主要顾虑标签与应对（不扣分）】");
        facts.append(concerns.isEmpty() ? "用户未勾选明显顾虑" : concerns.stream().map(item -> safe(item.get("concern")) + "→" + safe(item.get("advice"))).collect(Collectors.joining("；")));
        List<String> goals = stringList(form.get("reportGoals"));
        if (goals.contains("A") && bundle.get("direction") instanceof Map) {
            Map<String, Object> direction = map(bundle.get("direction"));
            appendDirection(facts, direction);
            if (Boolean.TRUE.equals(direction.get("systemEvaluated"))) facts.append("\n（用户选「希望系统评估」，需说明推导依据）");
        }
        if (goals.contains("B") && bundle.get("learning") != null) {
            Map<String, Object> learning = map(bundle.get("learning"));
            facts.append("\n【学习阶段】").append(learning.get("learningStage")).append("｜推荐：").append(join(learning.get("learningRecommendation")));
            if (learning.get("teachingNote") != null) facts.append("｜教学限制：").append(learning.get("teachingNote"));
        }
        if (goals.contains("C") && bundle.get("career") != null) {
            Map<String, Object> career = map(bundle.get("career"));
            facts.append("\n【就业与转行】方式：").append(career.get("careerMode")).append("｜看重：").append(join(career.get("careerPriorities"))).append("｜缺口：").append(join(career.get("careerGaps"))).append("｜异地接受度：").append(career.get("mobilityLevel"));
        }
        if (goals.contains("D") && bundle.get("sideBiz") != null) {
            Map<String, Object> side = map(bundle.get("sideBiz"));
            facts.append("\n【副业/创业】阶段：").append(side.get("sideBusinessStage")).append("｜作品客户基础：").append(side.get("portfolioLevel")).append("｜障碍：").append(join(side.get("barriers"))).append("｜启动建议：").append(side.get("startingAdvice"));
        }
        if (goals.contains("E")) {
            Map<String, Object> local = map(form.get("moduleE"));
            facts.append("\n【本地资源】城市：").append(join(local.get("city"))).append("｜需求：").append(join(local.get("resourceTypes"))).append("｜系统无可核验资源库，本章只能输出兜底提示，禁止虚构机构/岗位/地址/项目：「").append(LOCAL_RESOURCE_FALLBACK).append("」");
        }
        if (StringUtils.hasText(safe(form.get("extraNote")))) facts.append("\n【用户补充】").append(form.get("extraNote"));

        boolean experienced = Boolean.TRUE.equals(scores.get("isExperienced"));
        facts.append("\n\n=== 报告正文结构（默认8章，h1按序号；").append(experienced ? "已从业用户：不做入行适配判断，结论章引导使用职业发展梳理工具" : "按当前成熟度给建议").append("）===\n")
                .append("<h1>一、评测摘要</h1>一段话概述用户当前起点（结合接触程度、两指数与画像类型），客观不夸大。\n")
                .append("<h1>二、发展潜力指数</h1>解释潜力").append(Math.round(number(scores.get("potentialScore")))).append("（").append(scores.get("potentialLevel")).append("），挂到动机/效能/准备。\n")
                .append("<h1>三、当前入行成熟度指数</h1>解释成熟度").append(Math.round(number(scores.get("maturityScore")))).append("（").append(scores.get("maturityLevel")).append("），挂到认知/接触/证照/设备/学习准备/可行性。\n")
                .append("<h1>四、用户画像类型</h1>解读「").append(scores.get("personaType")).append("」，同时说明优势与限制。\n")
                .append("<h1>五、五维测评解读</h1>每维一小节结合分数给针对性说明；偏低维度用「💡 成长提升方向：」给一条具体建议。\n")
                .append("<h1>六、核心优势</h1>从高分维度与作答提炼2-3条真实优势，不拔高。\n")
                .append("<h1>七、主要顾虑与限制</h1>对照顾虑标签逐条给务实应对，同时如实点出限制。\n")
                .append("<h1>八、当前阶段下一步建议</h1>给与成熟度匹配的下一步动作，结尾自然邀约到校免费体验飞行与一对一沟通。\n");
        String[] cnNumbers = {"九", "十", "十一", "十二", "十三", "十四", "十五"};
        int index = 0;
        for (String goal : GOAL_SECTIONS.keySet()) {
            if (!goals.contains(goal)) continue;
            facts.append("<h1>").append(index < cnNumbers.length ? cnNumbers[index] : String.valueOf(9 + index)).append("、").append(GOAL_SECTIONS.get(goal)).append("</h1>");
            switch (goal) {
                case "A": facts.append("严格按系统给的主推荐/备选/暂不优先展开，每方向引用其匹配证据与当前限制；即使主推也说明限制，不因兴趣或专业相关就判定高度适合。"); break;
                case "B": facts.append("按系统给的学习阶段与推荐要点展开，成熟度不足者不推高级证照/教员；不写费用与量化训练数字。"); break;
                case "C": facts.append("按 careerMode 与缺口生成准备清单；不得因选全职就建议离职或立即转行。"); break;
                case "D": facts.append("按副业阶段说明已有基础、当前缺口、适合启动方式与暂不建议的行动；不得只因选创业就推荐买设备/成立公司/高额投入。"); break;
                case "E": facts.append("只输出系统给的本地资源兜底提示，不得虚构任何机构/岗位/地址/项目。"); break;
                case "F": facts.append("结合 verifiedKnowledge 给合规飞行与安全注意事项（实名登记、空域与合规意识、安全责任），不虚构法规编号。"); break;
                default: facts.append("给未来30—90天分阶段行动计划，节奏与用户填写的时间/周期/成熟度自洽，动作具体但不超出问卷信息。"); break;
            }
            facts.append("\n");
            index++;
        }
        facts.append("\n=== 生成要求 ===\n- 信息密度优先，2500-3800字，删掉凑字数套话\n- 从 <h1>一、评测摘要</h1> 直接开始，无前置说明\n- 未选择的报告目标章节不得出现\n- 不得输出品牌区、答题统计或用户未填写信息\n- 不得生成具体薪资、金额、训练周期、通过率或非 verifiedKnowledge 证照名称。");
        return facts.toString();
    }

    private void appendDirection(StringBuilder facts, Map<String, Object> direction) {
        facts.append("\n【方向匹配（程序算分，只引用证据与限制，不得改分）】\n");
        appendDirectionItem(facts, "主推荐：", map(direction.get("primary")));
        List<Map<String, Object>> alternatives = (List<Map<String, Object>>) direction.get("alternatives"); for (Map<String, Object> item : alternatives) appendDirectionItem(facts, "备选：", item);
        facts.append("暂不优先："); List<Map<String, Object>> deprioritized = (List<Map<String, Object>>) direction.get("deprioritized"); facts.append(deprioritized.stream().map(item -> safe(item.get("direction")) + "（" + safe(item.get("score")) + "）").collect(Collectors.joining("、")));
    }

    private void appendDirectionItem(StringBuilder facts, String prefix, Map<String, Object> item) { facts.append(prefix).append(item.get("direction")).append("（匹配分").append(Math.round(number(item.get("score")))).append("）｜证据：").append(join(item.get("evidence"))).append("｜限制：").append(join(item.get("limitation"))).append("｜验证：").append(item.get("verification")).append("\n"); }

    private boolean isCategory13QuestionId(String questionId) {
        if (!StringUtils.hasText(questionId)) return false;
        if (CATEGORY13_QUESTION_STEMS.containsKey(questionId)) return true;
        if (questionId.startsWith(CATEGORY13_QUESTION_ID_PREFIX)) {
            throw new IllegalArgumentException("分类13 V3题目ID不在Q1-Q48映射中：" + questionId);
        }
        return false;
    }

    private void mapCategory13Question(Map<String, Object> form, Map<String, Integer> likert,
                                       AppPracticeRecordAnswerRespVO answer) {
        String questionId = safe(answer.getQuestionId()).trim();
        String expectedStem = CATEGORY13_QUESTION_STEMS.get(questionId);
        String actualStem = normalizeQuestionStem(answer.getQuestion());
        if (!normalizeQuestionStem(expectedStem).equals(actualStem)) {
            throw new IllegalArgumentException("分类13 V3题目ID与题干不一致：" + questionId);
        }
        if (LIKERT_QUESTION_BY_ID.containsKey(questionId)) {
            mapLikert(likert, answer);
            return;
        }
        String value = safe(answer.getAnswer()).trim();
        int questionNo = Integer.parseInt(questionId.substring(questionId.length() - 3));
        if (!StringUtils.hasText(value)) {
            if (questionNo >= 18 && questionNo <= 46) return;
            throw new IllegalArgumentException("分类13 V3必答题答案为空：Q" + questionNo);
        }
        switch (questionId) {
            case "132026081810001":
                form.put("identity", requireCanonicalSingle(questionId, value,
                        Arrays.asList("学生", "职场人士", "自由职业者", "待业/求职中", "创业者", "其他")));
                return;
            case "132026081810002":
                form.put("backgroundFields", requireCanonicalList(questionId, value,
                        Arrays.asList("理工/工程/测绘/建筑", "电子/机械/维修/自动化", "农业/植保/农村相关",
                                "摄影摄像/传媒/设计/自媒体", "教育/培训/语言表达", "计算机/软件/数据/AI",
                                "销售/商务/运营/管理", "其他专业或行业", "暂无明确相关背景"),
                        2, "暂无明确相关背景"));
                return;
            case "132026081810003":
                form.put("droneExposure", requireCanonicalSingle(questionId, value, new ArrayList<>(DRONE_SCORE.keySet())));
                return;
            case "132026081810004":
                form.put("caacAwareness", requireCanonicalSingle(questionId, value, new ArrayList<>(CAAC_SCORE.keySet())));
                return;
            case "132026081810005":
                form.put("equipmentAccess", requireCanonicalSingle(questionId, value, new ArrayList<>(EQUIPMENT_SCORE.keySet())));
                return;
            case "132026081810016":
                form.put("concerns", requireCanonicalList(questionId, value, new ArrayList<>(CONCERN_MAP.keySet()),
                        3, "暂无明显顾虑"));
                return;
            case "132026081810017":
                mapCategory13ReportGoals(form, value);
                return;
            case "132026081810018":
                putModuleValue(form, "moduleA", "directions", requireCanonicalList(questionId, value,
                        Arrays.asList("航拍传媒", "工程测绘", "行业巡检", "农业植保", "无人机清洗", "无人机配送",
                                "应急救援", "无人机培训", "装调维修", "无人机表演", "低空运营管理",
                                "暂不清楚，希望系统评估", "其他"), 3, "暂不清楚，希望系统评估"));
                return;
            case "132026081810019":
                putModuleValue(form, "moduleA", "capabilities", requireCanonicalList(questionId, value,
                        Arrays.asList("摄影、剪辑、内容创作或自媒体运营能力", "工程、测绘、施工、CAD或GIS相关基础",
                                "农业、植保、农村场景或相关资源", "电子、机械、维修或自动化基础",
                                "教学培训、课程设计或表达能力", "软件、数据、人工智能或建模工具能力",
                                "销售、商务、运营或客户沟通能力", "行业人脉或项目引荐机会",
                                "无人机设备接触或借用机会", "资金、场地、学校、公司或项目资源",
                                "已有作品、案例或实践经历", "暂无明显资源"), 5, "暂无明显资源"));
                return;
            case "132026081810020": case "132026081810021": case "132026081810022":
            case "132026081810023": case "132026081810024": case "132026081810025":
            case "132026081810026": case "132026081810027":
                Map<String, Object> moduleA = map(form.get("moduleA"));
                Map<String, String> features = stringMap(moduleA.get("workFeatures"));
                features.put(WORK_FEATURE_BY_QUESTION_ID.get(questionId), requireCanonicalSingle(questionId, value,
                        Arrays.asList("可以接受", "视具体情况决定", "较难接受")));
                moduleA.put("workFeatures", features);
                return;
            case "132026081810028":
                putModuleValue(form, "moduleB", "purpose", requireCanonicalSingle(questionId, value,
                        Arrays.asList("先了解行业，判断自己是否适合", "体验飞行，培养兴趣", "学习一项实用技能",
                                "为全职就业或转行做准备", "为副业、接单或项目合作做准备", "为教学培训或科普活动做准备",
                                "满足现有单位或岗位的工作需求", "暂不确定")));
                return;
            case "132026081810029":
                putModuleValue(form, "moduleB", "mode", requireCanonicalSingle(questionId, value,
                        Arrays.asList("线上了解和自学", "线上理论 + 周末线下实操", "短期集中线下培训",
                                "系统考证 + 岗位技能训练", "先体验一次再决定", "暂不确定")));
                return;
            case "132026081810030":
                putModuleValue(form, "moduleB", "weeklyTime", requireCanonicalSingle(questionId, value,
                        Arrays.asList("暂时无法稳定安排", "1–3 小时", "4–7 小时", "8 小时以上", "可阶段性集中投入")));
                return;
            case "132026081810031":
                putModuleValue(form, "moduleB", "period", requireCanonicalSingle(questionId, value,
                        Arrays.asList("1 个月以内", "1–2 个月", "2–3 个月", "3–6 个月", "可灵活安排", "暂不确定")));
                return;
            case "132026081810032":
                putModuleValue(form, "moduleB", "budget", requireCanonicalSingle(questionId, value,
                        Arrays.asList("5000 元以下", "5000–10000 元", "10000–20000 元", "20000 元以上",
                                "可根据目标决定", "暂不确定")));
                return;
            case "132026081810033":
                putModuleValue(form, "moduleC", "careerMode", requireCanonicalSingle(questionId, value,
                        Arrays.asList("全职进入相关岗位", "在现有岗位中增加无人机能力", "先实习/兼职积累经验",
                                "先考证再决定", "暂不确定")));
                return;
            case "132026081810034":
                putModuleValue(form, "moduleC", "priorities", requireCanonicalList(questionId, value,
                        Arrays.asList("收入稳定", "收入增长空间", "技术成长", "岗位数量和就业机会",
                                "工作地点与出差频率", "职业发展空间", "兴趣与成就感"), 2, null));
                return;
            case "132026081810035":
                putModuleValue(form, "moduleC", "gaps", requireCanonicalList(questionId, value,
                        Arrays.asList("缺少证照", "缺少实操技能", "缺少项目经验", "缺少作品或案例", "不了解岗位要求",
                                "所在城市机会不清晰", "当前工作或学业难以兼顾", "暂不确定"), 3, "暂不确定"));
                return;
            case "132026081810036":
                putModuleValue(form, "moduleC", "mobility", requireCanonicalSingle(questionId, value,
                        Arrays.asList("可以接受", "视时间和成本决定", "暂时不能接受", "不确定")));
                return;
            case "132026081810037":
                putModuleValue(form, "moduleD", "forms", requireCanonicalList(questionId, value,
                        Arrays.asList("周末或业余时间接单", "航拍/内容创作", "与团队合作参与项目", "无人机培训或科普服务",
                                "基于现有行业资源开展应用项目", "成立团队或创业", "暂不确定"), 2, "暂不确定"));
                return;
            case "132026081810038":
                putModuleValue(form, "moduleD", "portfolio", requireCanonicalSingle(questionId, value,
                        Arrays.asList("完全没有", "有少量作品或经历", "已有较完整作品/项目经历", "已有客户或合作资源")));
                return;
            case "132026081810039":
                putModuleValue(form, "moduleD", "investment", requireCanonicalSingle(questionId, value,
                        Arrays.asList("仅接受低成本学习和小范围尝试", "可以投入必要的培训费用，但暂不购买设备",
                                "可以在不影响基本生活的情况下投入培训和基础设备", "可以接受前3—6个月以学习、积累作品和项目经验为主",
                                "希望先加入成熟团队，降低个人投入和试错风险", "暂不确定")));
                return;
            case "132026081810040":
                putModuleValue(form, "moduleD", "barriers", requireCanonicalList(questionId, value,
                        Arrays.asList("技能不足", "缺少证照与合规能力", "缺少设备", "缺少作品或案例", "缺少客户与渠道",
                                "不了解定价与交付流程", "时间不足", "暂不确定"), 3, "暂不确定"));
                return;
            case "132026081810041":
                putModuleValue(form, "moduleE", "city", value);
                return;
            case "132026081810042":
                putModuleValue(form, "moduleE", "resourceTypes", requireCanonicalList(questionId, value,
                        Arrays.asList("培训或考证机构", "无人机体验或实操场地", "设备租借或接触机会", "实习或就业岗位",
                                "项目合作或接单机会", "行业交流社群", "政策与产业园区信息", "其他"), 3, null));
                return;
            case "132026081810043":
                putModuleValue(form, "moduleE", "geoScope", requireCanonicalSingle(questionId, value,
                        Arrays.asList("仅常驻城市", "常驻城市及周边", "省内均可", "可跨省学习或就业", "线上资源也可以")));
                return;
            case "132026081810044": form.put("extraNote", value); return;
            case "132026081810045": form.put("nickname", value); return;
            case "132026081810046": form.put("contact", value); return;
            case "132026081810047":
                form.put("truthConfirm", requireCanonicalSingle(questionId, value, Arrays.asList("是", "否")));
                return;
            case "132026081810048":
                form.put("consent", requireCanonicalSingle(questionId, value, Arrays.asList("同意", "不同意")));
                return;
            default:
                throw new IllegalArgumentException("分类13 V3题目缺少映射：" + questionId);
        }
    }

    private void mapCategory13ReportGoals(Map<String, Object> form, String answer) {
        List<String> goals = new ArrayList<>();
        for (Map.Entry<String, String> entry : REPORT_GOAL_BY_ANSWER.entrySet()) {
            if (containsCanonicalAnswer(answer, entry.getKey())) addUnique(goals, entry.getValue());
        }
        if (goals.isEmpty() || goals.size() > 3) {
            throw new IllegalArgumentException("分类13 V3报告目标题Q17无法精确映射A-G或超过3项");
        }
        form.put("reportGoals", goals);
    }

    private String requireCanonicalSingle(String questionId, String answer, List<String> options) {
        String normalizedAnswer = normalizeQuestionStem(answer);
        List<String> matches = options.stream()
                .filter(option -> normalizedAnswer.equals(normalizeQuestionStem(option)))
                .collect(Collectors.toList());
        if (matches.size() != 1) {
            throw new IllegalArgumentException("分类13 V3题目答案无法唯一映射：" + questionId);
        }
        return matches.get(0);
    }

    private List<String> requireCanonicalList(String questionId, String answer, List<String> options,
                                              int maxItems, String exclusive) {
        List<String> matches = options.stream().filter(option -> containsCanonicalAnswer(answer, option))
                .collect(Collectors.toCollection(ArrayList::new));
        if (matches.isEmpty() || matches.size() > maxItems
                || (exclusive != null && matches.contains(exclusive) && matches.size() > 1)) {
            throw new IllegalArgumentException("分类13 V3题目答案列表不符合契约：" + questionId);
        }
        return matches;
    }

    private boolean containsCanonicalAnswer(String answer, String option) {
        return normalizeQuestionStem(answer).contains(normalizeQuestionStem(option));
    }

    private void putModuleValue(Map<String, Object> form, String moduleName, String field, Object value) {
        map(form.get(moduleName)).put(field, value);
    }

    private void mapLikert(Map<String, Integer> likert, AppPracticeRecordAnswerRespVO answer) {
        if (answer == null) return;
        String question = safe(answer.getQuestion());
        String questionId = safe(answer.getQuestionId()).trim();
        String stepName = safe(answer.getStepName());
        String stemKey = LIKERT_QUESTION_BY_STEM.get(normalizeQuestionStem(question));
        String idKey = LIKERT_QUESTION_BY_ID.get(questionId);
        String key = idKey;
        if (idKey != null) {
            if (stemKey != null && !idKey.equals(stemKey)) {
                throw new IllegalArgumentException("V3量表题目ID与题干不一致：" + questionId);
            }
        } else if (stemKey != null) {
            key = stemKey;
        } else {
            key = explicitLikertKey(question);
            if (key == null && "核心量表".equals(stepName)) {
                throw new IllegalArgumentException("V3量表题目缺少稳定映射：" + questionId);
            }
        }
        if (key == null) return;
        int score = qualitativeScore(answer.getAnswer());
        if (score < 1 || score > 5) return;
        if (likert.containsKey(key)) {
            throw new IllegalArgumentException("V3量表题目重复映射：" + key);
        }
        likert.put(key, score);
    }

    private String explicitLikertKey(String question) {
        String q = safe(question).toLowerCase(Locale.ROOT);
        for (String key : Arrays.asList("a1", "a2", "b1", "b2", "c1", "c2", "d1", "d2", "e1", "e2")) {
            if (q.matches(".*(?<![a-z0-9])" + key + "(?![a-z0-9]).*")) return key;
        }
        return null;
    }

    private static void putLikertQuestion(String questionId, String key, String stem) {
        LIKERT_QUESTION_BY_ID.put(questionId, key);
        LIKERT_QUESTION_BY_STEM.put(normalizeQuestionStem(stem), key);
        putCategory13Question(questionId, stem);
    }

    private static void putCategory13Question(String questionId, String stem) {
        CATEGORY13_QUESTION_STEMS.put(questionId, stem);
    }

    private static String category13QuestionId(int questionNo) {
        return CATEGORY13_QUESTION_ID_PREFIX + String.format(Locale.ROOT, "%04d", questionNo);
    }

    private static int category13QuestionNo(String questionId) {
        return Integer.parseInt(questionId.substring(CATEGORY13_QUESTION_ID_PREFIX.length()));
    }

    private static String normalizeQuestionStem(String stem) {
        return safe(stem).replaceAll("\\s+", "").trim();
    }

    private void requireCompleteLikert(Map<String, Object> formData) {
        Map<String, Object> likert = map(formData.get("likert"));
        List<String> missing = Arrays.asList("a1", "a2", "b1", "b2", "c1", "c2", "d1", "d2", "e1", "e2").stream()
                .filter(key -> !likert.containsKey(key) || number(likert.get(key)) < 1 || number(likert.get(key)) > 5)
                .collect(Collectors.toList());
        if (!missing.isEmpty()) throw new IllegalArgumentException("V3量表答案缺失，无法从当前answers确定映射：" + String.join(",", missing));
    }

    private void mapOptionFields(Map<String, Object> form, String question, String answer) {
        String all = safe(question) + " " + safe(answer);
        String caac = match(all, CAAC_SCORE.keySet());
        if (caac == null && question.contains("CAAC")) {
            if (all.contains("非常了解")) caac = "非常了解";
            else if (all.contains("基本了解")) caac = "比较了解";
            else if (all.contains("不太了解")) caac = "听说过但不清楚";
            else if (all.contains("没听过")) caac = "完全不了解";
        }
        if (caac != null) form.put("caacAwareness", caac);
        String exposure = match(all, DRONE_SCORE.keySet());
        if (exposure == null && question.contains("职业状态") && all.contains("有飞行基础")) exposure = "有过自学或少量实操，但未参加系统培训";
        if (exposure != null) form.put("droneExposure", exposure);
        String equipment = match(all, EQUIPMENT_SCORE.keySet());
        if (equipment == null && (question.contains("目前是否拥有") || question.contains("目前是否有无人机设备")
                || question.contains("可稳定接触无人机设备"))) {
            equipment = all.contains("是") ? "有可稳定使用的设备" : "没有";
        }
        if (equipment != null) form.put("equipmentAccess", equipment);
    }

    private void mapModules(Map<String, Object> form, String question, String answer) {
        String all = safe(question) + " " + safe(answer);
        if (question.contains("姓名") && StringUtils.hasText(answer)) form.put("nickname", answer.trim());
        Map<String, Object> module = map(form.get("moduleA")); List<String> directions = stringList(module.get("directions"));
        for (String direction : DIRECTIONS) if (all.contains(direction) && !directions.contains(direction)) directions.add(direction);
        if ((all.contains("无人机吊运") || all.contains("物流配送")) && !directions.contains("无人机配送")) directions.add("无人机配送");
        if (all.contains("不清楚") || all.contains("希望评估")) {
            directions.clear();
            directions.add("暂不清楚，希望系统评估");
        }
        if (all.contains("其他") && question.contains("细分方向") && !directions.contains("其他")) directions.add("其他");
        List<String> caps = stringList(module.get("capabilities"));
        for (String cap : CAPABILITY_MAP.keySet()) if (all.contains(cap) && !caps.contains(cap)) caps.add(cap);
        if (question.contains("擅长") || question.contains("资源") || question.contains("兴趣")) mapLegacyCapabilities(caps, all);
        module.put("directions", directions); module.put("capabilities", caps);
        if (question.contains("工作场景") || question.contains("工作模式")) mapWorkFeatures(module, answer);
        if (FEATURE_KEYS.containsKey(question)) {
            Map<String, String> features = stringMap(module.get("workFeatures"));
            setFeature(features, question, answer);
            module.put("workFeatures", features);
        }
        if (question.contains("最核心的诉求")) mapLearningPurpose(form, map(form.get("moduleB")), answer);
        if (question.contains("学习模式") || question.contains("学习方式")) mapCanonicalValue(form, "moduleB", "mode", answer,
                Arrays.asList("线上了解和自学", "线上理论 + 周末线下实操", "短期集中线下培训", "系统考证 + 岗位技能训练", "先体验一次再决定", "暂不确定"));
        if (question.contains("每周") && question.contains("学习时间")) mapLearningValue(form, "weeklyTime", answer);
        if (question.contains("学习和待岗周期")) mapLearningValue(form, "period", answer);
        if (question.contains("学习预算")) mapLearningValue(form, "budget", answer);
        if (question.contains("职业状态")) mapCareerMode(form, answer);
        if (question.contains("就业") && question.contains("障碍")) mapCanonicalList(form, "moduleC", "gaps", answer,
                Arrays.asList("缺少证照", "缺少实操技能", "缺少项目经验", "缺少作品或案例", "不了解岗位要求", "所在城市机会不清晰", "当前工作或学业难以兼顾", "暂不确定"));
        if (question.contains("异地") || question.contains("跨区域") || question.contains("地域范围")) mapCanonicalValue(form,
                question.contains("地域") ? "moduleE" : "moduleC", question.contains("地域") ? "geoScope" : "mobility", answer,
                question.contains("地域") ? Arrays.asList("仅常驻城市", "常驻城市及周边", "省内均可", "可跨省学习或就业", "线上资源也可以")
                        : Arrays.asList("可以接受", "视时间和成本决定", "暂时不能接受", "不确定"));
        if (question.contains("看重") || question.contains("职业优先")) mapCanonicalList(form, "moduleC", "priorities", answer,
                Arrays.asList("收入稳定", "收入增长空间", "技术成长", "岗位数量和就业机会", "工作地点与出差频率", "职业发展空间", "兴趣与成就感"));
        if (question.contains("发展形式")) mapCanonicalList(form, "moduleD", "forms", answer,
                Arrays.asList("周末或业余时间接单", "航拍/内容创作", "与团队合作参与项目", "无人机培训或科普服务", "基于现有行业资源开展应用项目", "成立团队或创业", "暂不确定"));
        if (question.contains("作品、项目经历") || question.contains("潜在客户资源")) mapCanonicalValue(form, "moduleD", "portfolio", answer,
                Arrays.asList("完全没有", "有少量作品或经历", "已有较完整作品/项目经历", "已有客户或合作资源"));
        if (question.contains("启动与投入方式")) mapCanonicalValue(form, "moduleD", "investment", answer,
                Arrays.asList("仅接受低成本学习和小范围尝试", "可以投入必要的培训费用，但暂不购买设备", "可以在不影响基本生活的情况下投入培训和基础设备", "可以接受前3—6个月以学习、积累作品和项目经验为主", "希望先加入成熟团队，降低个人投入和试错风险", "暂不确定"));
        if (question.contains("变现障碍")) mapCanonicalList(form, "moduleD", "barriers", answer,
                Arrays.asList("技能不足", "缺少证照与合规能力", "缺少设备", "缺少作品或案例", "缺少客户与渠道", "不了解定价与交付流程", "时间不足", "暂不确定"));
        if (question.contains("资源") && !question.contains("擅长")) mapResourceTypes(form, answer);
        if (question.contains("常驻城市")) map(form.get("moduleE")).put("city", answer.trim());
        if (question.contains("核心的诉求")) mapSideBusinessForms(form, answer);
        if (question.contains("补充") || question.contains("其他问题")) {
            if (StringUtils.hasText(answer)) form.put("extraNote", answer.trim());
        }
    }

    private void mapLegacyCapabilities(List<String> capabilities, String all) {
        if (all.contains("视频制作") || all.contains("摄影摄像") || all.contains("传媒") || all.contains("自媒体")) {
            addUnique(capabilities, "摄影、剪辑、内容创作或自媒体运营能力");
        }
        if (all.contains("电脑技术") || all.contains("软件") || all.contains("数据") || all.contains("计算机")) {
            addUnique(capabilities, "软件、数据、人工智能或建模工具能力");
        }
        if (all.contains("沟通谈判") || all.contains("销售") || all.contains("商务") || all.contains("客户")) {
            addUnique(capabilities, "销售、商务、运营或客户沟通能力");
        }
        if (all.contains("工程施工") || all.contains("测绘") || all.contains("建筑")) {
            addUnique(capabilities, "工程、测绘、施工、CAD或GIS相关基础");
        }
        if (all.contains("教学培训") || all.contains("教育") || all.contains("表达")) {
            addUnique(capabilities, "教学培训、课程设计或表达能力");
        }
        if (all.contains("行业人脉") || all.contains("人脉")) addUnique(capabilities, "行业人脉或项目引荐机会");
        if (all.contains("创业资金") || all.contains("商家资源") || all.contains("传媒资源") || all.contains("公司资源")) {
            addUnique(capabilities, "资金、场地、学校、公司或项目资源");
        }
        if (all.contains("无直接可利用资源") || all.contains("无突出技能")) addUnique(capabilities, "暂无明显资源");
    }

    private void mapWorkFeatures(Map<String, Object> module, String answer) {
        Map<String, String> features = new LinkedHashMap<>();
        Object existing = module.get("workFeatures");
        if (existing instanceof Map) {
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) existing).entrySet()) features.put(safe(entry.getKey()), safe(entry.getValue()));
        }
        if (answer.contains("经常户外作业") || answer.contains("室内+户外结合")) setFeature(features, "长时间户外作业", "可以接受");
        if (answer.contains("办公室办公") && !answer.contains("经常户外作业") && !answer.contains("室内+户外结合")) setFeature(features, "长时间户外作业", "较难接受");
        if (answer.contains("自由职业")) {
            setFeature(features, "项目制工作，地点和时间存在变化", "可以接受");
            setFeature(features, "前期收入可能不稳定", "可以接受");
        }
        if (answer.contains("兼职")) setFeature(features, "项目制工作，地点和时间存在变化", "可以接受");
        if (answer.contains("全职")) setFeature(features, "前期收入可能不稳定", "视具体情况决定");
        module.put("workFeatures", features);
    }

    private void mapLearningPurpose(Map<String, Object> form, Map<String, Object> module, String answer) {
        String purpose = null;
        if (answer.contains("全职转行")) purpose = "为全职就业或转行做准备";
        else if (answer.contains("赚外快")) purpose = "为副业、接单或项目合作做准备";
        else if (answer.contains("公司要求")) purpose = "满足现有单位或岗位的工作需求";
        else if (answer.contains("纯兴趣")) purpose = "体验飞行，培养兴趣";
        else if (answer.contains("怕错过风口")) purpose = "先了解行业，判断自己是否适合";
        else if (answer.contains("先拿证")) purpose = "学习一项实用技能";
        if (purpose != null) module.put("purpose", purpose);
        if (answer.contains("全职转行")) module.put("mode", "系统考证 + 岗位技能训练");
        else if (answer.contains("纯兴趣")) module.put("mode", "先体验一次再决定");
        else if (purpose != null) module.put("mode", "线上理论 + 周末线下实操");
        Map<String, Object> career = map(form.get("moduleC"));
        List<String> priorities = stringList(career.get("priorities"));
        if (answer.contains("全职转行")) { addUnique(priorities, "岗位数量和就业机会"); addUnique(priorities, "职业发展空间"); }
        if (answer.contains("赚外快")) addUnique(priorities, "收入增长空间");
        if (answer.contains("纯兴趣")) addUnique(priorities, "兴趣与成就感");
        career.put("priorities", priorities);
    }

    private void mapLearningValue(Map<String, Object> form, String field, String answer) {
        Map<String, Object> module = map(form.get("moduleB"));
        String value = answer;
        if ("weeklyTime".equals(field)) {
            if (answer.contains("周末")) value = "1–3 小时";
            else if (answer.contains("每日")) value = "4–7 小时";
            else if (answer.contains("脱产")) value = "可阶段性集中投入";
            else if (answer.contains("不确定")) value = "暂时无法稳定安排";
        } else if ("period".equals(field)) {
            if (answer.contains("1个月以内")) value = "1 个月以内";
            else if (answer.contains("1-2个月")) value = "1–2 个月";
            else if (answer.contains("2-3个月")) value = "2–3 个月";
            else if (answer.contains("6个月以内")) value = "3–6 个月";
        } else if ("budget".equals(field)) {
            if (answer.contains("10000元以内")) value = "5000–10000 元";
            else if (answer.contains("10000-20000元")) value = "10000–20000 元";
            else if (answer.contains("20000元以上")) value = "20000 元以上";
            else if (answer.contains("根据岗位") || answer.contains("根据目标")) value = "可根据目标决定";
        }
        if (StringUtils.hasText(value)) module.put(field, value);
    }

    private void mapCareerMode(Map<String, Object> form, String answer) {
        Map<String, Object> module = map(form.get("moduleC"));
        if (answer.contains("职场人") || answer.contains("转行")) module.put("careerMode", "全职进入相关岗位");
        else if (answer.contains("学生")) module.put("careerMode", "全职进入相关岗位");
        else if (answer.contains("有飞行基础")) module.put("careerMode", "在现有岗位中增加无人机能力");
    }

    private void mapResourceTypes(Map<String, Object> form, String answer) {
        Map<String, Object> module = map(form.get("moduleE"));
        List<String> types = stringList(module.get("resourceTypes"));
        if (answer.contains("培训") || answer.contains("考证")) addUnique(types, "培训或考证机构");
        if (answer.contains("体验") || answer.contains("实操")) addUnique(types, "无人机体验或实操场地");
        if (answer.contains("设备")) addUnique(types, "设备租借或接触机会");
        if (answer.contains("岗位") || answer.contains("就业")) addUnique(types, "实习或就业岗位");
        if (answer.contains("项目") || answer.contains("接单")) addUnique(types, "项目合作或接单机会");
        if (answer.contains("社群") || answer.contains("人脉")) addUnique(types, "行业交流社群");
        if (answer.contains("政策") || answer.contains("产业园")) addUnique(types, "政策与产业园区信息");
        module.put("resourceTypes", types);
    }

    private void mapSideBusinessForms(Map<String, Object> form, String answer) {
        Map<String, Object> module = map(form.get("moduleD"));
        List<String> forms = stringList(module.get("forms"));
        if (answer.contains("赚外快")) addUnique(forms, "周末或业余时间接单");
        if (answer.contains("视频") || answer.contains("传媒")) addUnique(forms, "航拍/内容创作");
        if (answer.contains("公司要求")) addUnique(forms, "基于现有行业资源开展应用项目");
        module.put("forms", forms);
    }

    private void setFeature(Map<String, String> features, String key, String value) { features.put(key, value); }

    private Map<String, String> stringMap(Object value) {
        Map<String, String> result = new LinkedHashMap<>();
        if (value instanceof Map) {
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) result.put(safe(entry.getKey()), safe(entry.getValue()));
        }
        return result;
    }

    private void mapCanonicalValue(Map<String, Object> form, String moduleName, String field, String answer, List<String> options) {
        Map<String, Object> module = map(form.get(moduleName));
        for (String option : options) if (answer.contains(option)) { module.put(field, option); break; }
    }

    private void mapCanonicalList(Map<String, Object> form, String moduleName, String field, String answer, List<String> options) {
        Map<String, Object> module = map(form.get(moduleName));
        List<String> values = stringList(module.get(field));
        for (String option : options) if (answer.contains(option)) addUnique(values, option);
        module.put(field, values);
    }

    private void mapGoals(Map<String, Object> form, String question, String answer) {
        if (!question.contains("希望得到") && !question.contains("评估报告")) return;
        List<String> goals = stringList(form.get("reportGoals"));
        if (answer.contains("适合") || answer.contains("方向")) addUnique(goals, "A");
        if (answer.contains("学习") || answer.contains("路径")) addUnique(goals, "B");
        if (answer.contains("就业") || answer.contains("转行")) addUnique(goals, "C");
        if (answer.contains("副业") || answer.contains("创业") || answer.contains("接单")) addUnique(goals, "D");
        if (answer.contains("本地") || answer.contains("资源") || answer.contains("城市") || answer.contains("机构")) addUnique(goals, "E");
        if (answer.contains("合规") || answer.contains("安全")) addUnique(goals, "F");
        if (answer.contains("行动") || answer.contains("计划")) addUnique(goals, "G");
        form.put("reportGoals", goals);
    }
    private void mapConsentFlags(Map<String, Object> form, String question, String answer) {
        if (question.contains("真实") || question.contains("准确")) {
            if (answer.contains("否") || answer.contains("不")) form.put("truthConfirm", "否");
            else if (answer.contains("是") || answer.contains("同意")) form.put("truthConfirm", "是");
        }
        if (question.contains("同意") || question.contains("授权")) {
            if (answer.contains("不同意") || answer.contains("否")) form.put("consent", "不同意");
            else if (answer.contains("同意") || answer.contains("是")) form.put("consent", "同意");
        }
    }
    private void mapIdentityAndBackground(Map<String, Object> form, String all) {
        if (all.contains("学生") && all.contains("待入行")) form.put("identity", "学生");
        else if (all.contains("职场人") && all.contains("转行")) form.put("identity", "职场人士");
        else if (all.contains("自由职业")) form.put("identity", "自由职业者");
        else if (all.contains("待业") || all.contains("求职")) form.put("identity", "待业/求职中");
        else if (all.contains("创业者")) form.put("identity", "创业者");
        Map<String, Object> profile = form;
        String bg = mapBackground(all);
        if (!"暂无明确相关背景".equals(bg) && !"其他专业或行业".equals(bg)
                && !stringList(profile.get("backgroundFields")).contains(bg)) {
            List<String> values = stringList(profile.get("backgroundFields"));
            values.clear();
            values.add(bg);
            profile.put("backgroundFields", values);
        }
    }
    private String mapBackground(String value) { if (value == null) return "暂无明确相关背景"; if (value.contains("摄影") || value.contains("传媒") || value.contains("设计") || value.contains("自媒体") || value.contains("视频")) return "摄影摄像/传媒/设计/自媒体"; if (value.contains("工程") || value.contains("测绘") || value.contains("建筑") || value.contains("施工")) return "理工/工程/测绘/建筑"; if (value.contains("电子") || value.contains("机械") || value.contains("维修") || value.contains("自动化")) return "电子/机械/维修/自动化"; if (value.contains("农业") || value.contains("植保")) return "农业/植保/农村相关"; if (value.contains("教育") || value.contains("培训")) return "教育/培训/语言表达"; if (value.contains("计算机") || value.contains("软件") || value.contains("数据") || value.contains("AI")) return "计算机/软件/数据/AI"; if (value.contains("销售") || value.contains("运营") || value.contains("管理")) return "销售/商务/运营/管理"; return "暂无明确相关背景"; }
    private void addConcern(Map<String, Object> form, String value) { List<String> concerns = stringList(form.get("concerns")); for (String concern : CONCERN_MAP.keySet()) if (value.contains(concern)) addUnique(concerns, concern); form.put("concerns", concerns); }
    private static void addConcern(String concern, String tag, String advice) { CONCERN_MAP.put(concern, new ConcernRule(tag, advice)); }
    private static void put(Map<String, List<String>> target, String key, String... values) { target.put(key, Arrays.asList(values)); }
    private static String safe(Object value) { return value == null ? "" : String.valueOf(value); }
    private static String firstNonBlank(Map<String, Object> profile, String first, String second, String fallback) { String value = profile == null ? "" : safe(profile.get(first)); if (!StringUtils.hasText(value) && profile != null) value = safe(profile.get(second)); return StringUtils.hasText(value) ? value : fallback; }
    private static String firstNonBlank(Map<String, Object> profile, String first, String fallback) { String value = profile == null ? "" : safe(profile.get(first)); return StringUtils.hasText(value) ? value : fallback; }
    private static String match(String text, Set<String> values) { for (String value : values) if (text.contains(value)) return value; return null; }
    private static String normalize(String value) { return safe(value).replaceAll("[\\s–—\\-]", ""); }
    private static int qualitativeScore(String value) {
        if (!StringUtils.hasText(value)) return 0;
        try {
            String trimmed = value.trim();
            if (trimmed.matches("^[1-5](?:\\s|[、.．:：]).*")) return trimmed.charAt(0) - '0';
            int parsed = Integer.parseInt(trimmed);
            return parsed >= 1 && parsed <= 5 ? parsed : 0;
        } catch (NumberFormatException ignored) {
            // Continue with the known qualitative labels below.
        }
        String n = normalize(value);
        // Check explicit low/unknown phrases before the broad "完全" label.
        if (n.contains("非常不同意") || n.contains("完全不了解") || n.contains("完全没有接触") || n.contains("完全无")
                || n.contains("没听过") || n.contains("无直接")) return 1;
        if (n.contains("比较不同意")) return 2;
        if (n.equals("一般")) return 3;
        if (n.contains("无法确定") || n.contains("暂不确定") || n.contains("不确定")
                || n.contains("未知") || n.contains("不清楚")) return 0;
        if (n.contains("非常同意") || n.contains("5个以上") || n.contains("可以接受")) return 5;
        if (n.contains("比较同意") || n.contains("基本") || n.contains("4")) return 4;
        if (n.contains("不太") || n.contains("1-2") || n.contains("较难") || n.contains("没有")) return 2;
        return 0;
    }
    private static double standard(Object value) { double parsed = number(value); return parsed >= 1 && parsed <= 5 ? (parsed - 1) / 4 * 100 : 50; }
    private static double round1(double value) { return BigDecimal.valueOf(value).setScale(1, RoundingMode.HALF_UP).doubleValue(); }
    private static double number(Object value) { if (value instanceof Number) return ((Number) value).doubleValue(); try { return Double.parseDouble(safe(value)); } catch (NumberFormatException ignored) { return 0; } }
    private static Map<String, Object> map(Object value) { if (!(value instanceof Map)) return new LinkedHashMap<>(); return (Map<String, Object>) value; }
    private static List<String> stringList(Object value) { if (!(value instanceof List)) return new ArrayList<>(); return ((List<?>) value).stream().map(SelfAssessmentV3RuleEngine::safe).collect(Collectors.toCollection(ArrayList::new)); }
    private static String join(Object value) { if (value instanceof List) return ((List<?>) value).isEmpty() ? "未选" : ((List<?>) value).stream().map(SelfAssessmentV3RuleEngine::safe).collect(Collectors.joining("、")); return StringUtils.hasText(safe(value)) ? safe(value) : "未填"; }
    private static void addUnique(List<String> list, String value) { if (!list.contains(value)) list.add(value); }
    private static String potentialLevel(double score) { return score >= 80 ? "高发展潜力" : score >= 65 ? "中高发展潜力" : score >= 50 ? "发展意愿一般" : "当前发展意愿较弱"; }
    private static String maturityLevel(double score) { return score >= 80 ? "成熟推进阶段" : score >= 65 ? "准备推进阶段" : score >= 45 ? "起步探索阶段" : "初步认知阶段"; }
    private static String personaType(double potential, double maturity) { if (potential >= 65 && maturity < 45) return "高潜力零基础探索型"; if (potential >= 65 && maturity < 65) return "高潜力准备型"; if (potential >= 65) return "积极推进型"; if (maturity >= 65) return "基础较好但目标动力待明确型"; if (potential >= 50) return "谨慎探索型"; return "兴趣观察型"; }

    private static final class HardCap { private final String key; private final int cap; private final List<String> directions; private final String reason; private HardCap(String key, int cap, List<String> directions, String reason) { this.key = key; this.cap = cap; this.directions = directions; this.reason = reason; } }
    private static final class ConcernRule { private final String tag; private final String advice; private ConcernRule(String tag, String advice) { this.tag = tag; this.advice = advice; } }
}
