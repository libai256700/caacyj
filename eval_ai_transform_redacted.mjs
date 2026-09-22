// Hook transform for caacyj.com evaluation report generation
// This runs inside the Gateway webhook handler when /hooks/new-evaluation is called
//
// It generates the AI report directly via DeepSeek Flash, then saves it to caacyj.com
// and notifies the user via Feishu. Returns null to skip agent dispatch (we handle
// everything here).

// ── Configuration ────────────────────────────────────────────────────────
const DEEPSEEK_API_KEY = "YOUR_API_KEY";
const DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1";

const CAACY_API_BASE = "https://caacyj.com/api";
const INTERNAL_KEY = "YOUR_INTERNAL_KEY";

const FEISHU_APP_ID = "cli_a9671c9b1b78dbd9";
const FEISHU_APP_SECRET = "YOUR_APP_SECRET";
// 运营咨询组群聊
const FEISHU_CHAT_ID = "oc_58f9fea49207fafe5690ce11dc4ff984";

const BRAND_CONTENT = `
<hr>

<h2 data-brand="true">飞手岗位薪资参考</h2>
<p>当前国内入门级持证飞手兼职月收入普遍在4000-10000元，全职飞手月收入区间为8000-18000元，具备专项技能（如航拍剪辑、植保作业调度、培训授课）的飞手收入较平均水平高30%-60%。</p>

<hr>

<h2 data-brand="true">云技科技专属补充</h2>

<h3>为什么选择云技科技</h3>
<p>湖北云技科技是华中地区领先的CAAC无人机执照培训与低空经济人才服务机构，具备以下核心优势：</p>

<p><strong>权威资质，行业认可</strong></p>
<ul>
<li>民航局认证考点，自有考试场地，考证无需异地奔波</li>
<li>甲级培训资质，教学品质受行业主管部门认可，政企单位培训通过率100%</li>
<li>CAAC民用无人驾驶航空器运营合格证以及中国航空运输协会民用无人机驾驶员训练机构合格证</li>
</ul>

<p><strong>专业教学，效果保障</strong></p>
<ul>
<li>武大华师教研合作基地，课程体系由高校专家联合开发</li>
<li>理论+实操双轨教学，全天制/半天制高效训练（理论1h+实飞2h）</li>
<li>小班制教学、一对一指导</li>
<li>教学设备齐全，覆盖多旋翼、垂起等主流机型</li>
</ul>

<p><strong>就业赋能，收入可期</strong></p>
<ul>
<li>合作企业覆盖航拍、巡检、测绘、植保等多个赛道</li>
<li>CAAC持证飞手全国缺口超百万，持证即具备行业准入资格</li>
<li>毕业学员优先推荐就业，优秀学员可获内部岗位机会</li>
<li>已有学员成功入职无人机企业，月薪8k-15k+</li>
</ul>

<p><strong>位置便利，随到随学</strong></p>
<ul>
<li>位于武汉市硚口区长丰大道17号微+空间数智文创产业园</li>
<li>地铁直达，交通便利，提供食宿</li>
<li>滚动开班，灵活安排学习时间</li>
</ul>

<hr>

<h2 data-brand="true">下一步行动</h2>
<ol>
<li>拨打 <strong>13027193573</strong> 预约到校参观，实地考察教学环境</li>
<li>到校后与课程顾问一对一沟通，确定最适合的课程方案</li>
<li>确认报名，踏上低空经济领域职业的美好新征途</li>
</ol>

<blockquote>
湖北云技科技 · 专注低空经济人才培养<br>
地址：武汉市硚口区长丰大道17号微+空间数智文创产业园1号楼2层2-9室
</blockquote>
`;

// ── System Prompt (from SKILL.md) ────────────────────────────────────────
const SYSTEM_PROMPT = `你是一名低空经济和无人机职业规划专家，就职于湖北云技科技（华中地区领先的CAAC无人机执照培训机构）。你的任务是根据用户填写的评测表单数据，生成一份个性化、有温度、有说服力的低空经济入行评估报告。

⚠️ 重要约束：
1. 输出纯 HTML 片段（不含 <html>/<body>/<head>/<style>/<meta> 标签）
2. 使用标准的 HTML 标签：<h1> <h2> <h3> <h4> <p> <ul> <ol> <li> <table> <blockquote> <strong> <br> <hr>
3. 表格必须包含完整的 <table><thead><tr><th><tbody><tr><td> 结构
4. 不要使用 <div> 或包裹容器，只输出内容标签
5. 标题层级：h1=章节标题（"1. 基础信息概览"等），h2=小节标题，h3=子标题
6. 报告内容必须基于用户实际填写的表单数据，不要套用模板或生成泛泛的内容
7. 分析要具体、有力度，不要泛泛而谈
8. 每个章节之间用 <hr> 分隔
9. 年龄段分析要有细节：16-25强调学习能力/反应速度，26-35强调经验积累/职业稳定，36+强调资源整合
10. CAAC知识储备分档：完全不了解→入门级建议，了解一些→适中难度，基本了解→系统提升，比较熟悉→进阶方案
11. 报告中不得出现具体预算金额、预算分配或预算分档分析
12. 所有与日期相关的信息（如行业资讯、政策、数据）使用当前时间上下文确定，不要写死年份
13. ⚠️ 行业数据和政策信息：优先使用你训练数据中的知识。如不确定具体数字，使用模糊表述（如「数万人」「普遍在」「主流区间」），**严禁凭空编造具体数字、百分比、政策文件名称**。宁可模糊，不可虚假——报告是面向潜在客户的，假数据会直接损害公司信誉
14. 第5章「行业资讯」的数据必须与用户的意向方向（directions）强相关，不要写和用户无关的赛道信息
15. 视觉美化要求：在关键位置使用 emoji 图标增强可读性
    - 章节标题前加 emoji，如 📋 1. 基础信息概览、🎯 2. 核心适配度评估、📚 3. 课程推荐、🗓 4. 入行规划、📡 5. 行业资讯、✅ 6. 评估结论
    - 优势得分点用 ✅ 列表、成长提升方向用 💪
    - 评分用 ⭐ 图标
    - 关键数据（数字、百分比、薪资）旁可加 📊 图标
    - 课程推荐板块：根据学员的意向方向推荐方向性内容（如「你的方向是测绘，建议从CAAC考证入手，同步对接测绘实训模块」），**不得写具体费用、价格、周期数字**，**不得因学员预算而限制或调整推荐方向**，最后补充可到线下体验后由专业老师详细沟通
    - 入行规划默认采用3个月紧凑版节奏，阶段图标用 🚀 💎 🏆
    - 差异化建议开头加 💡
    - 评估结论用 📌 总结
    - 注意：所有提及不足的板块统一命名为「成长提升方向」，采用正向鼓励式表述，不得出现负面扣分、缺陷类引导
    - 评估结论全程采用正向鼓励语气，突出用户优势与发展潜力
    - 不得在报告中提及具体预算金额、预算分配相关内容
    - 不得建议学员自行购买无人机、模拟器、设备或配件，机构提供全套教学设备，学员只管来学
    - emoji 放在标签文本内，不包裹在额外的 HTML 标签里
16. **交叉分析指令（务必执行）：**
    - 对「专业 + 意向方向」进行交叉评估：用户的学术背景与所选赛道是否存在协同效应？专业跨度是否需要额外补课？
    - 对「现有技能 + 意向赛道」进行匹配分析：哪些技能可以直接迁移，哪些需要从零学习？给出具体匹配度判断。
    - 对「学习周期 + 用户时间条件」进行可行性验证：用户的时间安排是否适配该周期的学习规划？给出合理的调整建议。
    - 将以上交叉分析结论融入第2章（核心适配度评估）和第4章（入行规划），让报告体现"人和赛道之间的化学关系"，而非简单罗列。`;

// ── Helper: Format user data for prompt ──────────────────────────────────
function formatPromptData(formData) {
  const f = (v) => {
    if (v === null || v === undefined) return "未填写";
    if (Array.isArray(v)) return v.length > 0 ? v.join("、") : "未填写";
    if (typeof v === "boolean") return v ? "有" : "无";
    return String(v);
  };
  return `=== 用户表单数据 ===
姓名：${f(formData.name)}
性别：${f(formData.gender)}
年龄：${f(formData.age)}
学历：${f(formData.education)}
专业：${f(formData.educationMajor)}
职业：${f(formData.occupation)}
行业经历：${f(formData.industryExp)}
CAAC了解度：${f(formData.caacKnowledge)}
是否有设备：${f(formData.hasEquipment)}
了解渠道：${f(formData.discoverySource)}
岗位认知：${f(formData.jobKnowledge)}
岗位详情：${f(formData.jobKnowledgeDetail)}
核心诉求：${f(formData.coreMotivation)}
诉求补充：${f(formData.coreMotivationOther)}
擅长技能：${f(formData.skills)}
技能补充：${f(formData.skillsOther)}
可用资源：${f(formData.resources)}
资源补充：${f(formData.resourcesOther)}
性格特征：${f(formData.personality)}
性格补充：${f(formData.personalityOther)}
兴趣方向：${f(formData.interests)}
兴趣补充：${f(formData.interestsOther)}
意向方向：${f(formData.directions)}
方向补充：${f(formData.directionsOther)}
工作场景：${f(formData.workScene)}
每周可投入时间：${f(formData.weeklyHours)}
预期学习周期：${f(formData.studyPeriod)}
期望：${f(formData.expectations)}
期望补充：${f(formData.expectationsOther)}\n\n`;
}

function buildUserPrompt(formData) {
  const data = formatPromptData(formData);
  return `${data}=== 报告结构 ===

<h1>1. 基础信息概览</h1>
按以下格式生成数据表格：
<table>
<thead><tr><th>维度</th><th>详情</th></tr></thead>
<tbody>
<tr><td>姓名</td><td>{name}</td></tr>
<tr><td>年龄</td><td>{age}（此处添加年龄段的优势分析点评）</td></tr>
<tr><td>学历</td><td>{education}</td></tr>
<tr><td>CAAC知识储备</td><td>{caacKnowledge}</td></tr>
<tr><td>意向赛道</td><td>{directions}</td></tr>
<tr><td>核心诉求</td><td>{coreMotivation}</td></tr>
<tr><td>职业背景</td><td>{occupation}</td></tr>
<tr><td>行业经历</td><td>{industryExp}</td></tr>
<tr><td>现有技能</td><td>{skills}</td></tr>
<tr><td>可投入学习时间</td><td>{weeklyHours}</td></tr>
<tr><td>预期学习周期</td><td>{studyPeriod}</td></tr>
</tbody>
</table>

<hr>

<h1>2. 核心适配度评估</h1>

<h2>综合评分：XX分</h2>
（根据用户画像，给出60-95之间的分数。评分逻辑：学历权重（本科及以上+5，大专+3，其他+1）；年龄权重（16-25岁+5，26-35岁+4，其他+3）；CAAC了解度（比较熟悉+5，基本了解+4，了解一些+3，完全不了解+1）；技能匹配度（和意向赛道强相关每项+3）；时间投入（脱产/全职+5，每天2-4小时+3，少于2小时+1）。以上为基础分，根据具体情况进行调整）

<h2>详细分析</h2>

<h3>优势得分点</h3>
（列出2-4个具体的优势，每点一段分析）

<h3>💪 成长提升方向</h3>
（列出1-3个可以优化的方向，采用正向鼓励式表述，说明优化后可获得的收益）

<hr>

<h1>3. 课程推荐</h1>

<h2>根据你的意向方向定制推荐</h2>
（根据用户的意向方向描述1-2个推荐方向，如「你选择的测绘方向，建议从CAAC超视距驾驶员考证入门，同步对接测绘专项实训，让你持证即具备接单能力」）

（⚠️ 绝对禁止：不得写具体费用、价格、周期天数！不得因用户填写的预算而限制推荐方向！预算高低不影响课程推荐，均按学员意向岗位来推荐！）

<p>如需了解具体课程方案和试听体验，欢迎联系云技科技预约到校，由专业老师一对一沟通哦~</p>

<hr>

<h1>4. 入行规划（分阶段）</h1>

<h2>🚀 第一阶段：考证拿证期（第1-4周）</h2>
- 学习内容：CAAC执照培训（理论+实操），培训过程同步建立行业认知和岗位理解
- 阶段目标：一个月内完成培训和考试，顺利拿证

<h2>💎 第二阶段：实战积累期（第5-8周）</h2>
- 学习内容：拿证后对接跟飞/实习项目，积累商业飞行经验
- 阶段目标：完成首单商业项目，建立作品集

<h2>🏆 第三阶段：起步变现期（第9-12周）</h2>
- 学习内容：接单平台认证+持续接单+个人IP打磨
- 阶段目标：达到独立接单能力，稳定获取收入

（⚠️ 绝对禁止：不得提及任何课程费用、学费金额、价格区间、预算！不得单独提及行业认知扫盲相关安排，行业认知在培训过程中自然积累！）

<hr>

<h1>5. 行业资讯（当前日期更新）</h1>

<h2>最新政策&行业趋势</h2>
<h2>意向赛道岗位机会&市场前景</h2>
<h2>差异化建议</h2>

<hr>

<h1>6. 评估结论</h1>
（全程采用正向鼓励语气，开头突出对用户适配度的高度肯定，重点说明用户的独家优势和发展潜力，最后给出清晰的下一步行动建议，传递陪跑支持的服务感）

（注：不得提及预算金额、设备购买、价格等内容）`;
}

// ── Helper: Call DeepSeek Flash API ──────────────────────────────────────
async function callDeepSeekFlash(formData) {
  const userPrompt = buildUserPrompt(formData);
  const body = {
    model: "deepseek-chat",
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: userPrompt }
    ],
    temperature: 0.7,
    max_tokens: 12000,
    stream: false
  };

  const response = await fetch(`${DEEPSEEK_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${DEEPSEEK_API_KEY}`
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120000) // 120s timeout
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "no response body");
    throw new Error(`DeepSeek API error ${response.status}: ${text}`);
  }

  const data = await response.json();
  const raw = data.choices?.[0]?.message?.content ?? "";
  if (!raw) throw new Error("DeepSeek returned empty content");

  // ── Post-processing: clean up the LLM output ──
  let cleaned = raw;

  // 1. Remove markdown code fences
  cleaned = cleaned.replace(/^```(?:html)?\s*\n?/i, "").replace(/\n?```\s*$/i, "");

  // 2. Remove leading descriptive text
  const knownPrefixes = [
    "以下是根据您的数据生成的报告",
    "好的，以下是为您生成的",
    "根据您提供的表单数据",
    "好的，根据您的表单数据",
    "以下是为您生成的"
  ];
  for (const prefix of knownPrefixes) {
    if (cleaned.startsWith(prefix)) {
      cleaned = cleaned.slice(prefix.length).trim();
    }
  }

  // 3. Remove trailing descriptive text (first match from end)
  const trailingPatterns = [
    /希望这份报告对您有帮助[\s\S]*$/,
    /如果您需要调整[\s\S]*$/,
    /如有任何问题[\s\S]*$/
  ];
  for (const pattern of trailingPatterns) {
    cleaned = cleaned.replace(pattern, "").trim();
  }

  // 4. Strip html/body/head tags
  cleaned = cleaned.replace(/<\/?(?:html|body|head|style|meta)[^>]*>/gi, "");

  // 5. Ensure starts with <h1>
  cleaned = cleaned.trim();
  if (!cleaned.startsWith("<")) throw new Error("Generated content doesn't start with HTML tag");

  // 6. Validate content quality
  if (cleaned.length < 200) throw new Error(`Generated report too short: ${cleaned.length} chars`);

  // 7. Append brand content
  return cleaned + BRAND_CONTENT;
}

// ── Helper: Get Feishu tenant access token ───────────────────────────────
let cachedToken = null;
let tokenExpiresAt = 0;

async function getFeishuToken() {
  if (cachedToken && Date.now() < tokenExpiresAt - 60000) {
    return cachedToken;
  }
  const resp = await fetch("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      app_id: FEISHU_APP_ID,
      app_secret: FEISHU_APP_SECRET
    })
  });
  if (!resp.ok) throw new Error(`Feishu token error: ${resp.status}`);
  const data = await resp.json();
  cachedToken = data.tenant_access_token;
  tokenExpiresAt = Date.now() + (data.expire || 7200) * 1000;
  return cachedToken;
}

// ── Helper: Send Feishu message ──────────────────────────────────────────
async function sendFeishuMessage(title, content) {
  try {
    const token = await getFeishuToken();
    const msgContent = JSON.stringify({
      zh_cn: {
        title,
        content: [[{ tag: "text", text: content }]]
      }
    });
    await fetch("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({
        receive_id: FEISHU_CHAT_ID,
        msg_type: "post",
        content: msgContent
      })
    });
  } catch (err) {
    console.error(`[eval-report-transform] Failed to send Feishu message: ${err.message}`);
  }
}

// ── Helper: Post completed report to caacyj.com API ──────────────────────
async function saveReport(id, reportContent) {
  const resp = await fetch(`${CAACY_API_BASE}/complete`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-internal-key": INTERNAL_KEY
    },
    body: JSON.stringify({
      id,
      reportContent
    }),
    signal: AbortSignal.timeout(30000)
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "no response");
    throw new Error(`saveReport error ${resp.status}: ${text}`);
  }
  return await resp.json();
}

// ── Main: Generate report workflow (async, fire-and-forget) ──────────────
async function generateReport(id, formData) {
  const name = formData?.name || "未知用户";
  try {
    console.log(`[eval-report-transform] Generating report for ${name} (ID: ${id})...`);

    // Step: Check idempotency first
    try {
      const checkResp = await fetch(`${CAACY_API_BASE}/check/${id}`, { signal: AbortSignal.timeout(5000) });
      if (checkResp.ok) {
        const checkData = await checkResp.json();
        if (checkData.status === "completed") {
          console.log(`[eval-report-transform] Report ${id} already completed, skipping.`);
          await sendFeishuMessage("✅ 评测报告生成(跳过)", `评测 (ID: ${id}, 姓名: ${name}) 的报告已存在，跳过生成。`);
          return;
        }
      }
    } catch (e) {
      // Check failed, proceed with generation anyway
      console.log(`[eval-report-transform] Idempotency check failed, proceeding anyway: ${e.message}`);
    }

    // Step: Call DeepSeek Flash
    const reportContent = await callDeepSeekFlash(formData);
    console.log(`[eval-report-transform] DeepSeek response received: ${reportContent.length} chars`);

    // Step: Save to API
    const saveResult = await saveReport(id, reportContent);
    console.log(`[eval-report-transform] Report saved successfully: ${saveResult.reportUrl || "OK"}`);

    // Step: Notify via Feishu
    const reportUrl = saveResult.reportUrl || `https://caacyj.com/reports/${id}.html`;
    await sendFeishuMessage(
      "✅ 评估报告生成成功",
      `评测报告已完成\n\n姓名：${name}\n报告编号：${id}\n查看链接：${reportUrl}\n\n由 DeepSeek Flash 自动生成。`
    );
    console.log(`[eval-report-transform] Report ${id} for ${name}: COMPLETE`);
  } catch (err) {
    console.error(`[eval-report-transform] FAILED for ${name} (ID: ${id}): ${err.message}`);
    await sendFeishuMessage(
      "❌ 评估报告生成失败",
      `评测报告生成失败\n\n姓名：${name}\n报告编号：${id}\n错误：${err.message}\n\n请手动处理。`
    );
  }
}

// ── Transform entry point ────────────────────────────────────────────────
// Receives ctx = { payload, headers, url, path }
// Returns: override action object (partial), or null to skip mapping entirely
export default async function transform(ctx) {
  const { payload } = ctx;

  // Extract evaluation data from the webhook payload
  const evaluation = payload?.evaluation;
  if (!evaluation || !evaluation.id || !evaluation.formData?.name) {
    // No evaluation data - let the normal agent dispatch handle it
    console.log("[eval-report-transform] No evaluation data in payload, falling through to agent");
    return null;
  }

  const id = evaluation.id;
  const formData = evaluation.formData;

  // Fire-and-forget: start report generation (this is the long-running part)
  generateReport(id, formData).catch(err => {
    console.error(`[eval-report-transform] Unhandled error: ${err.message}`);
  });

  // Return { action: null } to tell the Gateway "transform handled this, reply with 204".
  return { action: null };
}
