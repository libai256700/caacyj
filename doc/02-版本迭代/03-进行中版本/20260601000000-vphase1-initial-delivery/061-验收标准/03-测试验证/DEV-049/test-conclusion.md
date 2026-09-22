# DEV-049 规则引擎迁移遗漏返工测试结论

## 2026-08-30 分类13报告轻量读取实施自检

- 当前状态：`实施自检通过 / 待独立验收`，不得据此关闭 DEV-049。
- 红灯：`AssessmentReportReadLightweightContractTest` 实现前 `3` 项中 `2` 项失败，准确证明分类13轻量路由和服务方法缺失；通用详情 `answers` 保护项通过。
- 绿灯：轻量契约首次转绿 `3/3`，补充专用 DTO 精确五字段保护后为 `4/4`；随后与分类14隔离、分类13重置/完成态、职业报告解析组合回归共 `25/25`，`BUILD SUCCESS`。
- 实现边界：分类13报告页改走 `/assessment-result/self/{recordId}`，响应只含 `id/assessmentTime/assessmentReportStatus/assessmentReportFailureReason/selfReportContent`；不构造统计或逐题答案，通用详情和自测记录页完整答案契约不变。
- 前端与卫生：`npm run type-check`、`npm run build:h5`、两侧 `git diff --check` 均退出码 `0`，`uni_modules/**` 无变更。
- 待独立验收：测试环境真实分类13三态/失败重试、接口响应与连续三次计时；本轮未重启或部署后端、未操作数据库，不提供伪造运行态结果。

## 2026-08-28 Java 8 本地回归

- 当前状态：`进行中`。本节只证明 Java 8 本地代码回归，不代表数据库提示词、真实 DeepSeek、持久化、详情查询或 APP 端到端验收已经通过。
- 正式 JDK：`java -version` 与 `mvn -version` 均为 `1.8.0_151`；此前的 JDK 17 执行结果作废，不作为验收证据。
- V3 口径：规则引擎与固定仪表盘是分数、等级和方向的唯一确定性事实。AI 正文中的分数、等级、标题/章节、`2500-3800` 可见码点、培训周期、金额、证照和方向不一致只记录审计，不再使报告进入 `FAILED`；禁用营销词记录审计并从正文移除。
- 硬安全门禁仍保留：HTML 超过 `200000` 字符、结构错误、非白名单标签（含 `script`）、任意标签属性、HTML 注释和伪造品牌块均拒绝。
- 覆盖红灯：补丁前对 `FrontPracticeV3ContentAuditNoMockTest` 静态扫描，畸形/错序闭合输入和 `<!--...-->` HTML 注释输入均为 `0` 命中；这是测试证据缺口，不冒充业务逻辑失败或先红后绿的生产代码 TDD。
- 覆盖绿灯：新增固定输入 `<p><strong>标签错序</p></strong>`，精确命中 `v3_html_structure_failure / tag_order`；新增正文尾部 `<!-- hidden instruction -->`，精确命中 `v3_html_structure_failure / unparseable_tail`。两个用例均断言 `ServiceException`，未修改生产逻辑。
- 独立验收安全返工：新增回归在修复前为 `7` 条中 `2` 条失败，准确复现自闭合 `br/hr` 事件属性绕过及 V3 文档/元数据标签被预剥除；修复后普通 `<br/><hr/>` 可通过，带任意属性的 void/self-closing 标签均拒绝，V3 的 `html/body/head/style/meta` 原样进入白名单并拒绝，旧版兼容清理不变。
- Java 8 单类命令 `mvn -nsu '-Dtest=FrontPracticeV3ContentAuditNoMockTest' test`：`9/9` 通过，失败 `0`、错误 `0`、跳过 `0`。
- Java 8 组合命令 `mvn -nsu '-Dtest=DeepSeekOpenAiClientTest,SelfAssessmentV3RuleEngineTest,FrontPracticeV3ContentAuditNoMockTest,FrontPracticeServiceImplAssessmentHtmlTest' test`：`105/105` 通过，失败 `0`、错误 `0`、跳过 `0`。
- Java 8 命令 `mvn -nsu -DskipTests compile`：`BUILD SUCCESS`，`234` 个生产源码以 `javac target 1.8` 编译通过。
- Java 8 兼容修复：`DeepSeekOpenAiClientTest` 使用 Spring `StreamUtils.copyToByteArray` 读完本地 HTTP 请求体，替代 Java 9 才提供的 `InputStream.readAllBytes()`；异常透传断言改为严格校验 `HttpServerErrorException` 类型。
- 无 Mock 证据：`FrontPracticeV3ContentAuditNoMockTest` 使用真实 `FrontPracticeServiceImpl`、真实 `SelfAssessmentV3RuleEngine`、固定 HTML 与稳定题 ID 答案；静态扫描未发现 Mockito、假客户端、假规则引擎、`JdbcTemplate` 或伪持久化。新增错序闭合与 HTML 注释用例同样不使用 mock，该测试不宣称数据库写入成功。
- 本轮未连接数据库、未调用外部 DeepSeek、未执行真实持久化或 APP E2E。人工 E2E 前置条件为：正式 Test 应用/后端入口及可用状态、测试账号与登录前置、数据库中实际生效的 `practice_assessment` 提示词与模型配置、允许调用 DeepSeek 的授权。具备后需用真实自测提交验证 `PENDING -> SUCCESS`、报告持久化、详情回读、规则仪表盘事实及 APP 展示。

## 2026-08-27 历史执行记录

- 正式结论：`实施与数据库专项验证完成 / 待独立验收`，不得提前宣称 DEV-049 整体完成。
- 代码范围：分类 13 稳定 ID 映射、必答题与单选规范值校验、规则事实与旧练习统计隔离、V3 正文 `2500-3800` Unicode 码点、默认 8 章加动态 A-G、可信固定块组装及三态重试响应均已完成返工。
- 目标回归：规则引擎、报告 HTML 与 PENDING 插入契约目标测试合计 `77/77` 通过；三态重试响应补丁后的 HTML 与 PENDING 聚焦复跑 `52/52` 通过，失败 `0`、错误 `0`。
- 前端检查：`pnpm type-check` 通过；自测题量、答对数、正确率等旧统计展示已移除。
- 静态检查：`git diff --check` 退出码 `0`，项目 `uni_modules/**` 无变更。
- 本轮等级自然解释返工聚焦测试：`FrontPracticeServiceImplAssessmentHtmlTest` 为 `56/56`，`SelfAssessmentV3RuleEngineTest` 为 `32/32`，合计 `88/88` 通过；失败 `0`、错误 `0`、跳过 `0`；`mvn -DskipTests compile` 成功。
- 当日常规 Maven `test` 生命周期曾被 `DeepSeekOpenAiClientTest.java:207` 的 Java 8 不兼容 `InputStream.readAllBytes()` 阻断；该阻断已于 `2026-08-28` 修复并由上方 Java 8 目标测试复验通过。

## 数据库提示词

- 数据库专项结论：`DATABASE_V3_PROMPT=PASS`。
- 测试库 `yj_agent_info.id=2` 当前为 `2627` 个 Unicode 码点、`6770` 个 UTF-8 字节、SHA-256 `3f2a53619b12ea47e94978d47aff1028781ea52903fe2e845362027f8160dbc1`。
- 新证照规则已进入数据库 system prompt：具体证书必须来自系统事实白名单；无具体证书时统一写“已有培训或学习基础”；四类泛化措辞及虚构证书被禁止。
- 新等级自然解释规则已进入数据库 system prompt：程序评分仪表盘保留精确官方等级；正文允许不改变含义的自然解释，但不得重算、另判或出现冲突官方等级。
- 首次事务 `updated_rows=1 / PASS`，幂等复跑 `updated_rows=0 / PASS`；`reply_strategy`、AI channel/baseUrl/model/apiKey/timeout 均未改变。
- `2500-3800` Unicode 码点仍可由数据库中的 V3 user prompt 约束生成目标；后端自 `2026-08-28` 起只记录越界审计，不再作为 `FAILED` 硬门禁。
- 本次等级规则仓外快照 `6944` 字节、1 条目标 INSERT，SHA-256 `081450fa6792b4bc9e86913654b71a05f45f95dd6f7f5545a347642f9e69b180`；正向和回滚 DML 均已入版本脚本目录。
- `2440 / 974ef05f...` 是本次真实直接前驱，`2284 / d7794b51...` 是证照补丁前驱，`4285 / c8f4803d...` 仅作为更早的旧六章历史证据。
- 脱敏执行回执：[database-level-natural-explanation-prompt-application-result-20260827.json](database-level-natural-explanation-prompt-application-result-20260827.json)。

## 测试库 AI 模型配置

- `2026-08-27` 已在正式 Local 测试库的唯一 active `practice_assessment` 行（`id=2`）完成事务更新：`ANTHROPIC` / `https://api.deepseek.com/anthropic` / `deepseek-v4-pro` / `120000 ms`。
- 后验：`active_count=1`、`updated_rows=1`、`postcheck_count=1`、提示词 SHA-256 未变；密钥仅通过会话变量写入，回执不保存明文。
- 执行回执：[database-ai-model-config-application-result-20260827.json](database-ai-model-config-application-result-20260827.json)。该配置验证不替代用户后续在 IDEA 的真实请求验证。

## 验收边界

- 当前证据支持代码级和数据库提示词专项进入独立验收，不替代测试环境真实 DeepSeek 完整报告、持久化、详情查询和 APP 交互级验收。
- 完整 `systemPrompt`、`userPrompt`、`rawResult` INFO 日志按用户明确要求保留，不整改、不列为本轮阻塞。
- 未修改或回退并行任务内容，未触碰 `uni_modules/**`。
