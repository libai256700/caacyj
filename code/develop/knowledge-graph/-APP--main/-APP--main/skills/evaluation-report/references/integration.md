# 宿主 App 接入

## JavaScript

Node.js 18+ 可直接导入核心；核心本身无第三方依赖，正式生成时由宿主提供成熟的 HTML 消毒器：

```javascript
import sanitizeHtml from "sanitize-html";
import {
  REPORT_HTML_POLICY,
  generateReportV3
} from "./scripts/evaluation-report-core.mjs";
import { createOpenAICompatibleLlm } from "./scripts/openai-compatible-llm.mjs";

const llm = createOpenAICompatibleLlm({
  endpoint: process.env.EVALUATION_LLM_ENDPOINT,
  apiKey: process.env.EVALUATION_LLM_API_KEY,
  model: process.env.EVALUATION_LLM_MODEL
});

const result = await generateReportV3(evaluationId, formData, {
  llm,
  sanitizeHtml: html => sanitizeHtml(html, {
    allowedTags: [...REPORT_HTML_POLICY.allowedTags],
    allowedAttributes: REPORT_HTML_POLICY.allowedAttributes
  }),
  brandContent: appBrandHtml
});

if (!result.corePublishable) {
  await queueForReview(result);
} else {
  await saveOnce(evaluationId, result.reportContent, result.privacy);
}
```

上例中的 `sanitize-html` 由宿主 App 安装，不是技能的运行时依赖。`generateReportV3()` 只生成内存结果，不保存、不通知、不发布。`llm` 回调收到 `(systemPrompt, userPrompt, context)`，可返回 HTML 字符串或 `{ content, channel }`。`context` 只含评测 ID、规则结果和隐私级别，不含原始表单或联系方式。

`sanitizeHtml` 回调是强制门禁：只消毒 LLM 片段，策略来自 `REPORT_HTML_POLICY`，且消毒后会再次执行业务校验。仪表盘由核心的可信模板在此后组装，包含 `div`、`span` 和内联样式；不要拿 LLM 的严格标签策略再次清洗整个组合结果。`brandContent` 和自定义 `methodologyHtml` 必须由宿主作为可信模板管理，不得直接接受用户或模型 HTML。

`assembleReportV3()` 是供已消毒片段使用的低层函数，不得把原始 LLM 输出直接传入。

## 非 JavaScript

先进入技能目录；以下命令都以该目录为当前工作目录。通过标准输入准备提示词：

```bash
node scripts/evaluation-report-cli.mjs prepare - < form-data.json
```

LLM 返回 HTML 后，将以下 JSON 交给校验模式：

```json
{
  "formData": {},
  "html": "<h1>一、评测摘要</h1><p>...</p>"
}
```

```bash
node scripts/evaluation-report-cli.mjs validate - < generated-report.json
```

`validate` 只完成输入与业务事实校验，输出 `corePublishable=false` 和 `candidateHtml`。宿主必须使用成熟库按输出中的 `sanitizationPolicy` 消毒 `candidateHtml`，再提交组装模式：

```json
{
  "formData": {},
  "sanitizedHtml": "<h1>一、评测摘要</h1><p>...</p>"
}
```

```bash
node scripts/evaluation-report-cli.mjs assemble - < sanitized-report.json
```

只有 `assemble` 返回 `corePublishable=true` 时才得到非空 `reportContent`。该状态只表示技能内部的输入、事实、HTML 结构和消毒流程门禁已通过，不替代宿主的鉴权、幂等、存储及发布审核。

CLI 的 `assemble` 输入明确拒绝 `brandContent`，防止用户或模型 HTML 伪装成可信模板。品牌内容只能由 JavaScript 宿主在代码配置中注入，或由非 JavaScript 宿主在技能返回后通过自身受控模板追加。

## 发布门禁

宿主必须依次完成：

1. Schema 校验通过。
2. 使用评测 ID 做幂等检查或队列去重。
3. `truthConfirm=是`，且 `processingConsent=同意` 允许相应数据进入第三方 LLM。
4. 使用成熟库消毒 LLM 片段，且消毒后的业务校验通过。
5. `corePublishable=true` 且 `reviewRequired=false`。
6. 根据发布授权 `consent` 产生的 `privacy` 决定公开或私有存储。
7. 保存 `schemaVersion`、`contractVersion`、`sourceRulesetVersion`、`rulesetVersion` 与 `knowledgeVersion`，保证历史报告可追踪。
8. 保存成功后再通知，通知目标由宿主配置。

OpenClaw Hook、serverless 函数和后台任务都必须等待 `generateReportV3()` 完成，或把任务明确交给持久队列。不要在短生命周期进程中使用未等待的异步调用。

## 配置边界

- 凭据只放宿主的 Secret Manager 或环境变量，禁止写入技能文件、示例、测试和日志。
- 模型、端点、超时、回退顺序、品牌内容和通知目标都由宿主注入。
- UI 展示文案可以本地化，但提交值必须映射到 `FORM_OPTIONS_V3` 的规范值。
- 结构化 `scores` 保留一位小数；提示词和仪表盘使用四舍五入后的整数展示。计算、历史比较和数据交换以结构化值为准。
- `generationSucceeded` 只表示 LLM 调用完成；是否进入宿主门禁看 `corePublishable`，输入与报告详情分别看 `inputValidation` 和 `reportValidation`。
- 私有报告使用会话鉴权或短期签名链接，不把管理密钥放入 URL。
- OpenAI 兼容适配器默认不把供应商错误正文带入异常；只有受控调试时才显式启用 `includeErrorBody`，且不得把错误正文写入普通日志。
- `validateReport()` 是严格业务门禁，不替代内容安全审核、法律合规复核或宿主模板的安全治理。
