# TC-API-ASSESSMENT-AI-001 DeepSeek 非流式协议与失败边界

## 1. 测试层级

`接口级 / 代码级`

## 2. 对应验收项

- 验收项 ID：`AC-ASSESSMENT-AI-101`、`AC-ASSESSMENT-AI-301`
- 正式验收入口：`../../01-验收执行详情/AC-ASSESSMENT-AI-101.md`、`../../01-验收执行详情/AC-ASSESSMENT-AI-301.md`

## 3. 前置条件

- 环境前置：本地代码现场使用 JDK 8 执行非流式合同测试和编译；DeepSeek 正式 Anthropic/OpenAI 兼容入口只作为运行时配置能力，不以本地伪造响应冒充测试服务器端到端验收。
- 账号前置：API Key 从应用配置的单一来源安全读取，命令与证据不输出完整值。
- 数据前置：使用不含个人信息的最小提示词，测试数据见 `test-data.json`。

## 4. 测试数据

- 测试库当前 Anthropic 模型：`deepseek-v4-pro`。
- 请求内容：固定最小文本，不包含真实学员或答题数据。
- 密钥：`<REDACTED>`。

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 检查配置和客户端调用链 | OpenAI 兼容链路调用 `/v1/chat/completions`、发送 Bearer Key 与 `stream=false`，解析 `choices[0].message.content`；Anthropic 链路调用 `/v1/messages`、发送 `x-api-key`、`anthropic-version`、`system`、`messages`、`max_tokens`、`temperature` 与 `stream=false`，解析非流式 `content[].text` |
| 2 | 复跑非流式目标测试 | 覆盖协议选择、两类请求路径/请求头/请求体、成功完整响应、HTTP 错误原样传播、全阶段日志 requestId 一致和 API Key 脱敏 |
| 3 | 编译后端 | 正式 JDK 8 下 234 个源文件按 target 1.8 编译成功 |
| 4 | 审计日志与边界 | 失败日志可区分网络、鉴权、模型、参数、超时、空响应和 HTML 安全失败；正文业务偏差只记录审计，日志不泄露 API Key |
| 5 | 审计 diff 和 `uni_modules/**` | `git diff --check` 通过；`uni_modules/**` 无变更 |

## 6. 期望结果

- OpenAI/Anthropic 非流式请求契约、目标测试、编译与边界审计全部通过。
- 失败日志可以区分上游 HTTP 异常、超时、空响应和 HTML 安全失败；字数、章节和正文事实偏差不得成为失败条件。
- 测试服务器部署后另行执行新报告端到端验证，本用例不冒充该结果。

## 7. 脚本入口

- 自动化脚本：`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/test/java/com/huiyitech/knowledge/dal/DeepSeekOpenAiClientTest.java`、`code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/test/java/com/huiyitech/app/practice/service/FrontPracticeServiceImplAssessmentHtmlTest.java`、`FrontPracticeV3ContentAuditNoMockTest.java`、`SelfAssessmentV3RuleEngineTest.java`
- 依赖命令：相关四类目标测试命令；`mvn -nsu -DskipTests compile`
- 结果输出位置：同目录 `execution-results.json` 及 `../04-测试执行结论.md`。

## 8. 失败判定

- 任一协议未固定 `stream=false`、请求路径/鉴权头错误，或未正确解析 OpenAI `message.content` / Anthropic `content[].text`。
- 空响应、超时或 HTML 安全失败被静默回退，或字数、章节、分数等正文业务偏差错误地使记录进入 `FAILED`。
- 测试、编译、差异格式或 `uni_modules/**` 边界任一未通过。

## 9. 本次结论

- 本地实施自检：正式 JDK 8 下 `DeepSeekOpenAiClientTest` `7/7`，相关四类测试合计 `105/105` 通过；`mvn -nsu -DskipTests compile` 为 `BUILD SUCCESS`，234 个源文件按 target 1.8 编译。
- 环境门禁：未执行真实 DeepSeek 或测试环境端到端；仍需测试环境真实完整报告、最终状态、持久化与详情接口证据，不存在 30 秒阶段正文协议。
