package com.huiyitech.app.practice.service;

import com.huiyitech.app.practice.controller.vo.AppPracticeRecordAnswerRespVO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SelfAssessmentV3RuleEngineTest {

    private final SelfAssessmentV3RuleEngine engine = new SelfAssessmentV3RuleEngine();

    @Test
    void computeScoresV3_shouldMatchPortableFixtureValues() {
        Map<String, Object> form = fixture();
        Map<String, Object> scores = engine.computeScoresV3(form);

        assertEquals(62.5, scores.get("dims") instanceof Map
                ? ((Map<?, ?>) scores.get("dims")).get("industryCognition") : null);
        assertEquals(87.5, ((Map<?, ?>) scores.get("dims")).get("careerMotivation"));
        assertEquals(83.8, scores.get("potentialScore"));
        assertEquals(63.3, scores.get("maturityScore"));
        assertEquals("高潜力准备型", scores.get("personaType"));
        assertEquals(false, ((Map<?, ?>) scores.get("flags")).get("straightLine"));
        assertEquals(0, ((Map<?, ?>) scores.get("flags")).get("missingLikert"));
    }

    @Test
    void directionMatch_shouldApplySafetyHardCap() {
        Map<String, Object> form = fixture();
        Map<String, Object> module = new LinkedHashMap<>();
        module.put("directions", Collections.singletonList("航拍传媒"));
        module.put("capabilities", Collections.emptyList());
        Map<String, String> features = new LinkedHashMap<>();
        features.put("需要承担较强的飞行与安全责任", "较难接受");
        module.put("workFeatures", features);
        form.put("moduleA", module);
        Map<String, Object> bundle = engine.buildBundle(form);
        Map<?, ?> direction = (Map<?, ?>) bundle.get("direction");
        Map<?, ?> primary = (Map<?, ?>) direction.get("primary");
        assertEquals("航拍传媒", primary.get("direction"));
        assertTrue(((Number) primary.get("score")).doubleValue() <= 50.0);
    }

    @Test
    void buildBundle_shouldOnlyAddSelectedGoalModules() {
        Map<String, Object> form = fixture();
        form.put("reportGoals", Collections.singletonList("A"));
        Map<String, Object> bundle = engine.buildBundle(form);
        assertTrue(bundle.get("direction") != null);
        assertEquals(null, bundle.get("learning"));
        assertEquals(null, bundle.get("career"));
        assertEquals(null, bundle.get("sideBiz"));
    }

    @Test
    void buildContext_shouldEmitOnlySelectedDynamicPromptSections() {
        List<AppPracticeRecordAnswerRespVO> answers = new java.util.ArrayList<>();
        answers.add(AppPracticeRecordAnswerRespVO.builder().no(1).question("希望得到评估报告").answer("方向 学习").build());
        String[] keys = {"a1", "a2", "b1", "b2", "c1", "c2", "d1", "d2", "e1", "e2"};
        for (int i = 0; i < keys.length; i++) {
            answers.add(AppPracticeRecordAnswerRespVO.builder().no(10 + i)
                    .question("V3量表 " + keys[i]).answer("4").build());
        }
        String prompt = String.valueOf(engine.buildContext(Collections.emptyMap(), answers, Collections.emptyMap()).get("userPrompt"));
        assertTrue(prompt.contains("<h1>九、细分方向匹配</h1>"));
        assertTrue(prompt.contains("<h1>十、学习、实操、考证与培训路径</h1>"));
        assertTrue(!prompt.contains("<h1>十一、就业与转行准备</h1>"));
        assertTrue(!prompt.contains("<h1>十二、副业、自由接单与创业可行性</h1>"));
        assertTrue(prompt.contains("报告开头的程序评分仪表盘是系统确定性事实"));
        assertTrue(prompt.contains("不得重新计算、修改、质疑或另行判定分数与等级"));
        assertTrue(prompt.contains("无需逐字重复官方等级名称"));
        assertTrue(prompt.contains("不得出现与系统等级冲突的任何其他官方等级名称"));
        assertFalse(prompt.contains("规则引擎已算定，原样引用"));
    }

    @Test
    void buildContext_shouldRejectLegacyAnswersWithoutExplicitLikertKeys() {
        List<AppPracticeRecordAnswerRespVO> answers = Collections.singletonList(
                answer(1, "您的岗位认知如何", "比较了解"));
        IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                () -> engine.buildContext(Collections.emptyMap(), answers, Collections.emptyMap()));
        assertTrue(error.getMessage().contains("a1"));
        assertTrue(error.getMessage().contains("e2"));
    }

    @Test
    void buildContext_shouldRejectBlankUnknownAndUncertainLikertValues() {
        for (String invalid : Arrays.asList("", "未知", "无法确定", "暂不确定")) {
            List<AppPracticeRecordAnswerRespVO> answers = v3LikertAnswers(invalid);
            IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                    () -> engine.buildContext(Collections.emptyMap(), answers, Collections.emptyMap()));
            assertTrue(error.getMessage().contains("a1"), invalid);
        }
    }

    @Test
    void adaptFormData_shouldKeepLowQualitativeLikertValuesLowAndHonorNumericBoundaries() {
        Map<String, Object> low = engine.adaptFormData(Collections.emptyMap(), v3LikertAnswers("完全不了解"));
        assertEquals(1, ((Map<?, ?>) low.get("likert")).get("a1"));

        Map<String, Object> noExposure = engine.adaptFormData(Collections.emptyMap(), v3LikertAnswers("完全没有接触"));
        assertEquals(1, ((Map<?, ?>) noExposure.get("likert")).get("a1"));

        Map<String, Object> one = engine.adaptFormData(Collections.emptyMap(), v3LikertAnswers("1"));
        assertEquals(1, ((Map<?, ?>) one.get("likert")).get("a1"));
        Map<String, Object> five = engine.adaptFormData(Collections.emptyMap(), v3LikertAnswers("5"));
        assertEquals(5, ((Map<?, ?>) five.get("likert")).get("a1"));
    }

    @Test
    void buildContext_shouldMapCategory13LikertQuestionsByStableIdAndExactStem() {
        Map<String, Object> profile = new LinkedHashMap<>();
        profile.put("droneExposure", "有过自学或少量实操，但未参加系统培训");
        profile.put("caacAwareness", "比较了解");
        profile.put("equipmentAccess", "可以借用或偶尔接触");
        Map<String, Object> context = engine.buildContext(profile, realCategory13LikertAnswers(), Collections.emptyMap());
        Map<?, ?> form = (Map<?, ?>) context.get("formData");
        Map<?, ?> likert = (Map<?, ?>) form.get("likert");
        assertEquals(4, likert.get("a1"));
        assertEquals(3, likert.get("a2"));
        assertEquals(5, likert.get("b1"));
        assertEquals(4, likert.get("b2"));
        assertEquals(4, likert.get("c1"));
        assertEquals(4, likert.get("c2"));
        assertEquals(5, likert.get("d1"));
        assertEquals(4, likert.get("d2"));
        assertEquals(3, likert.get("e1"));
        assertEquals(4, likert.get("e2"));
        assertEquals("有过自学或少量实操，但未参加系统培训", form.get("droneExposure"));
        assertEquals("比较了解", form.get("caacAwareness"));
        assertEquals("可以借用或偶尔接触", form.get("equipmentAccess"));
        Map<?, ?> scores = (Map<?, ?>) ((Map<?, ?>) context.get("bundle")).get("scores");
        assertEquals(83.8, scores.get("potentialScore"));
        assertEquals(63.3, scores.get("maturityScore"));
    }

    @Test
    void buildContext_shouldMapAllFortyEightCategory13QuestionsWithoutSilentDefaults() {
        Map<String, Object> context = engine.buildContext(Collections.emptyMap(), realCategory13Answers(),
                Collections.emptyMap());
        Map<?, ?> form = (Map<?, ?>) context.get("formData");
        Map<?, ?> bundle = (Map<?, ?>) context.get("bundle");
        Map<?, ?> scores = (Map<?, ?>) bundle.get("scores");

        assertEquals("学生", form.get("identity"));
        assertEquals(Collections.singletonList("摄影摄像/传媒/设计/自媒体"), form.get("backgroundFields"));
        assertEquals(Arrays.asList("A", "B", "C"), form.get("reportGoals"));
        assertEquals("林同学", form.get("nickname"));
        assertEquals("是", form.get("truthConfirm"));
        assertEquals("同意", form.get("consent"));
        assertEquals("为全职就业或转行做准备", ((Map<?, ?>) form.get("moduleB")).get("purpose"));
        assertEquals("全职进入相关岗位", ((Map<?, ?>) form.get("moduleC")).get("careerMode"));
        assertEquals("武汉市", ((Map<?, ?>) form.get("moduleE")).get("city"));
        Map<?, ?> features = (Map<?, ?>) ((Map<?, ?>) form.get("moduleA")).get("workFeatures");
        assertEquals(8, features.size());
        assertEquals("较难接受", features.get("长时间户外作业"));
        assertEquals("可以接受", features.get("项目制工作，地点和时间存在变化"));
        assertEquals("可以接受", features.get("需要较多客户沟通和团队协作"));
        assertEquals(83.8, scores.get("potentialScore"));
        assertEquals(63.3, scores.get("maturityScore"));
        assertEquals("高潜力准备型", scores.get("personaType"));
        assertEquals("航拍传媒", ((Map<?, ?>) ((Map<?, ?>) bundle.get("direction")).get("primary")).get("direction"));
        assertFalse(String.valueOf(context.get("userPrompt")).contains("13800000000"));
    }

    @Test
    void adaptFormData_shouldMapOtherIdentityBackgroundAndNicknameByStableId() {
        List<AppPracticeRecordAnswerRespVO> answers = realCategory13Answers();
        answers.set(0, category13Answer(1, "您当前的身份状态是？", "其他"));
        answers.set(1, category13Answer(2, "您的学习或工作背景更接近哪些领域？", "计算机/软件/数据/AI"));
        answers.set(44, category13Answer(45, "您希望报告如何称呼您？", "飞行同学"));

        Map<String, Object> form = engine.adaptFormData(Collections.emptyMap(), answers);

        assertEquals("其他", form.get("identity"));
        assertEquals(Collections.singletonList("计算机/软件/数据/AI"), form.get("backgroundFields"));
        assertEquals("飞行同学", form.get("nickname"));
    }

    @Test
    void buildContext_shouldRejectStableQuestionStemDriftAndMissingQ17() {
        IllegalArgumentException stemError = assertThrows(IllegalArgumentException.class,
                () -> engine.adaptFormData(Collections.emptyMap(), Collections.singletonList(
                        category13Answer(20, "错误题干", "可以接受"))));
        assertTrue(stemError.getMessage().contains("题干不一致"));

        List<AppPracticeRecordAnswerRespVO> likertOnly = new java.util.ArrayList<>(realCategory13LikertAnswers());
        likertOnly.removeIf(answer -> "132026081810017".equals(answer.getQuestionId()));
        IllegalArgumentException goalError = assertThrows(IllegalArgumentException.class,
                () -> engine.buildContext(Collections.emptyMap(), likertOnly, Collections.emptyMap()));
        assertTrue(goalError.getMessage().contains("Q17"));
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 47, 48})
    void buildContext_shouldRejectEachMissingCategory13RequiredQuestion(int missingQuestionNo) {
        List<AppPracticeRecordAnswerRespVO> answers = realCategory13Answers();
        answers.removeIf(answer -> answer.getNo() == missingQuestionNo);

        IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                () -> engine.buildContext(Collections.emptyMap(), answers, Collections.emptyMap()));

        assertTrue(error.getMessage().contains("Q" + missingQuestionNo), error.getMessage());
    }

    @Test
    void adaptFormData_shouldRequireExactCanonicalSingleAnswer() {
        List<AppPracticeRecordAnswerRespVO> deniedAnswers = realCategory13Answers();
        deniedAnswers.set(47, category13Answer(48,
                "我同意系统根据本次回答生成个性化评估建议。", "不同意"));
        assertEquals("不同意", engine.adaptFormData(Collections.emptyMap(), deniedAnswers).get("consent"));

        for (String invalid : Arrays.asList("我同意", "同意、不同意", "未知")) {
            List<AppPracticeRecordAnswerRespVO> invalidAnswers = realCategory13Answers();
            invalidAnswers.set(47, category13Answer(48,
                    "我同意系统根据本次回答生成个性化评估建议。", invalid));
            IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                    () -> engine.adaptFormData(Collections.emptyMap(), invalidAnswers));
            assertTrue(error.getMessage().contains("132026081810048"), invalid);
        }
    }

    @Test
    void adaptFormData_shouldMapExistingTwentyOneQuestionAnswers() {
        List<AppPracticeRecordAnswerRespVO> answers = Arrays.asList(
                answer(1, "姓名", "林同学"),
                answer(4, "您的学历及相关专业是", "本科，摄影摄像"),
                answer(5, "您当前的职业状态是", "职场人（想转行）"),
                answer(6, "您是否了解 CAAC 执照", "基本了解"),
                answer(7, "您目前是否有无人机设备", "是"),
                answer(10, "您学习无人机，最核心的诉求是？", "赚外快"),
                answer(11, "您的过往工作/学习经历中，最擅长的是？", "视频制作"),
                answer(12, "您拥有哪些可以和低空经济结合的资源？", "传媒资源、自媒体"),
                answer(15, "以下低空经济细分方向，您最感兴趣的是？", "无人机吊运、不清楚希望评估"),
                answer(16, "您能接受的工作场景和模式是？", "经常户外作业、自由职业"),
                answer(17, "您每周能投入的有效学习时间是？", "每日固定学习1-2小时"),
                answer(18, "您能接受的学习和待岗周期是？", "1-2个月"),
                answer(19, "您能接受的学习预算是？", "10000-20000元"),
                answer(20, "如果给您一份专属的评估报告，您最希望得到什么内容？", "具体的学习路径、行业合规飞行与安全须知"),
                answer(21, "您还有其他问题或想补充的内容吗？", "希望结合本地机会给建议")
        );

        Map<String, Object> form = engine.adaptFormData(Collections.emptyMap(), answers);
        assertEquals("林同学", form.get("nickname"));
        assertEquals("比较了解", form.get("caacAwareness"));
        assertEquals("有可稳定使用的设备", form.get("equipmentAccess"));
        assertEquals(Collections.singletonList("暂不清楚，希望系统评估"),
                ((Map<?, ?>) form.get("moduleA")).get("directions"));
        assertEquals("为副业、接单或项目合作做准备", ((Map<?, ?>) form.get("moduleB")).get("purpose"));
        assertEquals("4–7 小时", ((Map<?, ?>) form.get("moduleB")).get("weeklyTime"));
        assertEquals("1–2 个月", ((Map<?, ?>) form.get("moduleB")).get("period"));
        assertEquals("10000–20000 元", ((Map<?, ?>) form.get("moduleB")).get("budget"));
        assertEquals("全职进入相关岗位", ((Map<?, ?>) form.get("moduleC")).get("careerMode"));
        assertTrue(((List<?>) form.get("reportGoals")).containsAll(Arrays.asList("B", "F")));
        assertEquals("希望结合本地机会给建议", form.get("extraNote"));
    }

    private static AppPracticeRecordAnswerRespVO answer(int no, String question, String value) {
        return AppPracticeRecordAnswerRespVO.builder().no(no).question(question).answer(value).build();
    }

    private static List<AppPracticeRecordAnswerRespVO> v3LikertAnswers(String a1Value) {
        List<AppPracticeRecordAnswerRespVO> answers = new java.util.ArrayList<>();
        String[] keys = {"a1", "a2", "b1", "b2", "c1", "c2", "d1", "d2", "e1", "e2"};
        for (int i = 0; i < keys.length; i++) {
            answers.add(answer(i + 1, "V3量表 " + keys[i], i == 0 ? a1Value : "3"));
        }
        return answers;
    }

    private static List<AppPracticeRecordAnswerRespVO> realCategory13LikertAnswers() {
        String[] ids = {"132026081810006", "132026081810007", "132026081810008", "132026081810009",
                "132026081810010", "132026081810011", "132026081810012", "132026081810013",
                "132026081810014", "132026081810015"};
        String[] stems = {"我对无人机相关岗位类型有基本了解。", "我了解无人机相关岗位通常涉及的证照、合规安全飞行与实践要求。",
                "我关注这一方向，不只是短期好奇，而是与未来职业收入或能力提升有关。", "如果方向明确，我愿意在未来6–12个月持续推进学习。",
                "我的过往学习、工作等经验，可以迁移到至少一个无人机相关方向。", "我有信心掌握无人机操作或相关软件、设备和工作流程。",
                "我能够为相关学习、训练或实践安排相对稳定的时间。", "我能够接受证照、实操和项目经验积累需要一个阶段性周期。",
                "我的时间、预算和工作/家庭安排允许我在未来6个月开始学习无人机相关内容。", "即使存在不确定性，我也愿意先从低成本了解、体验或基础学习开始推进。"};
        String[] values = {"4 比较同意", "3 一般", "5 非常同意", "4 比较同意", "4 比较同意", "4 比较同意", "5 非常同意", "4 比较同意", "3 一般", "4 比较同意"};
        List<AppPracticeRecordAnswerRespVO> answers = new java.util.ArrayList<>();
        answers.add(category13Answer(1, "您当前的身份状态是？", "学生"));
        answers.add(category13Answer(2, "您的学习或工作背景更接近哪些领域？",
                "摄影摄像/传媒/设计/自媒体"));
        answers.add(category13Answer(3, "您目前接触无人机的程度是？",
                "有过自学或少量实操，但未参加系统培训"));
        answers.add(category13Answer(4, "您对CAAC无人机执照的了解程度是？", "比较了解"));
        answers.add(category13Answer(5, "您目前是否拥有或可稳定接触无人机设备？", "可以借用或偶尔接触"));
        for (int i = 0; i < ids.length; i++) {
            answers.add(AppPracticeRecordAnswerRespVO.builder().no(i + 6).questionId(ids[i]).question(stems[i])
                    .stepName("核心量表").answer(values[i]).build());
        }
        answers.add(category13Answer(16, "您当前推进无人机方向时，主要顾虑或限制有哪些？", "预算有限"));
        answers.add(category13Answer(17, "您本次最想解决的主要问题是？",
                "A. 我想知道自己更适合哪些无人机细分方向"));
        answers.add(category13Answer(47, "我确认以上回答基本符合本人真实情况。", "是"));
        answers.add(category13Answer(48, "我同意系统根据本次回答生成个性化评估建议。", "同意"));
        return answers;
    }

    private static List<AppPracticeRecordAnswerRespVO> realCategory13Answers() {
        String[][] rows = {
                {"您当前的身份状态是？", "学生"},
                {"您的学习或工作背景更接近哪些领域？", "摄影摄像/传媒/设计/自媒体"},
                {"您目前接触无人机的程度是？", "有过自学或少量实操，但未参加系统培训"},
                {"您对CAAC无人机执照的了解程度是？", "比较了解"},
                {"您目前是否拥有或可稳定接触无人机设备？", "可以借用或偶尔接触"},
                {"我对无人机相关岗位类型有基本了解。", "4 比较同意"},
                {"我了解无人机相关岗位通常涉及的证照、合规安全飞行与实践要求。", "3 一般"},
                {"我关注这一方向，不只是短期好奇，而是与未来职业收入或能力提升有关。", "5 非常同意"},
                {"如果方向明确，我愿意在未来6–12个月持续推进学习。", "4 比较同意"},
                {"我的过往学习、工作等经验，可以迁移到至少一个无人机相关方向。", "4 比较同意"},
                {"我有信心掌握无人机操作或相关软件、设备和工作流程。", "4 比较同意"},
                {"我能够为相关学习、训练或实践安排相对稳定的时间。", "5 非常同意"},
                {"我能够接受证照、实操和项目经验积累需要一个阶段性周期。", "4 比较同意"},
                {"我的时间、预算和工作/家庭安排允许我在未来6个月开始学习无人机相关内容。", "3 一般"},
                {"即使存在不确定性，我也愿意先从低成本了解、体验或基础学习开始推进。", "4 比较同意"},
                {"您当前推进无人机方向时，主要顾虑或限制有哪些？", "预算有限、没有设备或实操机会"},
                {"您本次最想解决的主要问题是？", "A. 我想知道自己更适合哪些无人机细分方向；B. 我想了解学习、实操、考证及培训选择；C. 我想了解就业或转行前需要做哪些准备"},
                {"您最想评估的细分方向是？", "航拍传媒"},
                {"您目前具备或可以争取的相关能力与资源有哪些？", "摄影、剪辑、内容创作或自媒体运营能力"},
                {"对以下工作特征，您的接受程度如何？【长时间户外作业】", "较难接受"},
                {"对以下工作特征，您的接受程度如何？【经常出差或跨区域项目】", "视具体情况决定"},
                {"对以下工作特征，您的接受程度如何？【项目制工作，地点和时间存在变化】", "可以接受"},
                {"对以下工作特征，您的接受程度如何？【前期收入可能不稳定】", "可以接受"},
                {"对以下工作特征，您的接受程度如何？【需要持续学习、训练或考证】", "可以接受"},
                {"对以下工作特征，您的接受程度如何？【需要承担较强的飞行与安全责任】", "视具体情况决定"},
                {"对以下工作特征，您的接受程度如何？【需要维护设备或处理简单故障】", "视具体情况决定"},
                {"对以下工作特征，您的接受程度如何？【需要较多客户沟通和团队协作】", "可以接受"},
                {"您现阶段学习无人机的主要目的是什么？", "为全职就业或转行做准备"},
                {"您更倾向于哪种学习与实操方式？", "线上理论 + 周末线下实操"},
                {"您目前每周可投入的有效学习时间大约是？", "4–7 小时"},
                {"您可接受的学习准备周期是？", "2–3 个月"},
                {"您当前可接受的学习或训练预算范围是？", "5000–10000 元"},
                {"您更倾向的职业发展方式是？", "全职进入相关岗位"},
                {"您选择相关岗位时最看重什么？", "技术成长、职业发展空间"},
                {"您目前最大的就业或转行障碍是？", "缺少证照、缺少项目经验"},
                {"您能否接受为相关岗位进行短期实习、项目体验或跨区域学习？", "视时间和成本决定"},
                {"您更希望尝试哪种发展形式？", "周末或业余时间接单、航拍/内容创作"},
                {"您目前是否已有可展示的作品、项目经历或潜在客户资源？", "有少量作品或经历"},
                {"您目前可接受哪种启动与投入方式？", "仅接受低成本学习和小范围尝试"},
                {"您认为自己当前最大的变现障碍是？", "技能不足、缺少客户与渠道"},
                {"您的常驻城市是？", "武汉市"},
                {"您目前最希望查找哪类本地资源？", "无人机体验或实操场地、实习或就业岗位"},
                {"您可接受的地域范围是？", "常驻城市及周边"},
                {"您还有哪些特殊情况、补充需求或其他疑问？", "希望先实地体验"},
                {"您希望报告如何称呼您？", "林同学"},
                {"如需进一步沟通，您愿意留下联系方式吗？手机/微信", "13800000000"},
                {"我确认以上回答基本符合本人真实情况。", "是"},
                {"我同意系统根据本次回答生成个性化评估建议。", "同意"}
        };
        List<AppPracticeRecordAnswerRespVO> answers = new java.util.ArrayList<>();
        for (int i = 0; i < rows.length; i++) answers.add(category13Answer(i + 1, rows[i][0], rows[i][1]));
        return answers;
    }

    private static AppPracticeRecordAnswerRespVO category13Answer(int no, String stem, String value) {
        return AppPracticeRecordAnswerRespVO.builder().no(no).questionId("13202608181" + String.format("%04d", no))
                .question(stem).answer(value).build();
    }

    private Map<String, Object> fixture() {
        Map<String, Object> form = new LinkedHashMap<>();
        form.put("droneExposure", "有过自学或少量实操，但未参加系统培训");
        form.put("caacAwareness", "比较了解");
        form.put("equipmentAccess", "可以借用或偶尔接触");
        Map<String, Integer> likert = new LinkedHashMap<>();
        likert.put("a1", 4); likert.put("a2", 3);
        likert.put("b1", 5); likert.put("b2", 4);
        likert.put("c1", 4); likert.put("c2", 4);
        likert.put("d1", 5); likert.put("d2", 4);
        likert.put("e1", 3); likert.put("e2", 4);
        form.put("likert", likert);
        form.put("backgroundFields", Collections.singletonList("摄影摄像/传媒/设计/自媒体"));
        form.put("reportGoals", Arrays.asList("A", "B", "C", "D"));
        Map<String, Object> module = new LinkedHashMap<>();
        module.put("directions", Collections.singletonList("航拍传媒"));
        module.put("capabilities", Collections.singletonList("摄影、剪辑、内容创作或自媒体运营能力"));
        Map<String, String> features = new LinkedHashMap<>();
        features.put("项目制工作，地点和时间存在变化", "可以接受");
        features.put("需要较多客户沟通和团队协作", "可以接受");
        features.put("前期收入可能不稳定", "视具体情况决定");
        features.put("需要持续学习、训练或考证", "可以接受");
        module.put("workFeatures", features);
        form.put("moduleA", module);
        form.put("concerns", Collections.emptyList());
        return form;
    }
}
