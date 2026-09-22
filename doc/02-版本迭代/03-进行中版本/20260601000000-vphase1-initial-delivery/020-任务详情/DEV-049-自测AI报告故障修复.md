# DEV-049 自测 AI 报告故障修复

## 实施标准

- 先按 [PD-049](../040-程序设计/[程序设计]PD-049-20260825-DEV-049-自测报告生成逻辑精确迁移.md) 实现源工程 V3 实际导出的最小兼容链路：V3 formData 映射、五维、双指数、画像、方向匹配、顾虑/学习/就业/副业标签和事实包。
- 规则引擎先于 AI；LLM 只能按确定性事实叙述，不能重算分数、改判画像/方向、补写用户未填信息。固定 fixture 结果为 83.8、63.3、“高潜力准备型”、主方向“航拍传媒”。
- 提示词正式运行时来源仍为 yj_agent_info.id=2.prompt_config，由 050-执行脚本/20260815120000-dml-update_yj_agent_info_self_test_prompt_from_mjs.sql 承接完整 VERIFIED_KNOWLEDGE；不得只替换零散数据库文案。
- 默认输出 8 章；仅对已选择 A-G 目标追加动态章节。方法论与评分仪表盘在正文前，固定品牌区仅在末尾追加一次。
- 保留当前异步 PENDING/SUCCESS/FAILED、OpenAI 兼容 AI 客户端、无 fallback、报告持久化与 APP 轮询；AI 调用或超时、响应映射、不安全 HTML 标签/属性/结构、固定区块组装或持久化失败必须进入 FAILED。正文分数、等级、标题/章节、字数、训练、金额、证书和方向等内容偏差仅审计，不得据此阻断持久化或回退简版 HTML。
- 精确范围排除源工程 *Current 候选实现、可选 sanitizer、CLI/知识库/部署/保存/通知/密钥和 uni_modules/**。

## 对应技能

- 30-0200-story-technical-design
- 20-0200-acceptance-standards-documentation
- 40-0100-project-testing
- 00-1000-server-deployment-standards

## 交付物

- PD-049 唯一程序设计及 V3 映射/组装/红灯入口。
- 当前服务最小 V3 事实层和数据库提示词更新（代码实施阶段交付）。
- 源 fixture、阈值、字段映射、动态章节、禁止 LLM 重算、状态异常和持久化测试。
- 测试环境真实完整报告、日志与记录 ID 证据。

## 分支安排详情

- 当前版本代码现场模式：复杂模式
- 当前代码现场：code/develop/
- 当前分支：feature/20260601000000-vphase1-initial-delivery
- 不回退并行改动，不修改 uni_modules/**

## 关联验收项

- AC-ASSESSMENT-AI-001
- AC-ASSESSMENT-AI-101
- AC-ASSESSMENT-AI-201
- AC-ASSESSMENT-AI-301

## 任务产出 / 结果记录

- 2026-08-30 新增报告读取性能返工：自测报告页当前复用通用 `/records/{recordId}`，虽只展示报告字段，却触发完整统计与逐题答案重建。实施链固定为“正式验收补充 -> 轻量入口红灯 -> 分类13轻量报告接口 -> 页面 service 切换 -> 目标测试/type-check/build -> 独立验收”；轻量响应仅承接 `id/assessmentTime/assessmentReportStatus/assessmentReportFailureReason/selfReportContent`，不返回 `answers`，不得改变通用详情契约、三态和重试语义。
- 2026-08-25 已按脚本创建唯一 PD-049，退出码 0；设计文档已写明 V3 白名单、*Current 排除、确定性事实层、默认 8 章+A-G 动态章节、组装顺序、DML 入口和红灯测试。
- 当前只读事实：FrontPracticeServiceImpl 现有 AI 输入仅为 studentProfile/statistics/answers，提示词运行时来自数据库；必须先补 V3 formData 与事实包，不能仅修改提示词文本。
- 当前任务重新进入进行中；此前“待测试环境验收”的旧状态仅对应旧故障修复，不代表新增迁移范围已实施或验收通过。
- 2026-08-25 实施前门禁：当时不执行代码、SQL、部署或浏览器验收；实施前必须先建立红灯测试并完成测试库备份与正式入口核对。
- 2026-08-27 按用户明确要求撤回自测报告流式传输改造：五个既有文件已恢复到 `2aa987f4`，九个流式新增类/测试已删除，规则引擎、MJS 提示词入口、无简版 fallback、APP 轮询与详情契约继续保留；后续批次小修改和其他并行内容未触碰。
- 验证结果：有效主要回归 `75/75` 通过，包括规则引擎 `9/9`、报告 HTML `40/40`、批次契约 `16/16 + 10/10`；Reset 单列 `9` 项中 `3` 项通过、`1 failure`、`5 errors`，原因为 `2aa987f4` 测试要求注入同基线实现不存在的 `knowledgeProperties` 字段及一条普通批次判断差异，按用户决策作为基线既有缺陷记录，不在本任务修正。全 reactor 编译 `41/41` 通过。
- 2026-08-28 已修复 V3 内容审计误阻断和自闭合 `br/hr` 尾部属性绕过：正文业务偏差仅记录审计，危险标签、任意属性、文档/元数据标签和非法闭合结构继续硬拒绝；数据库 `yj_agent_info.id=2.prompt_config` 当前回执为 `2627 / 6770 / 3f2a53619b12ea47e94978d47aff1028781ea52903fe2e845362027f8160dbc1`，直接前驱为 `2440 / 6243 / 974ef05f4cda6fe0e07d6076c06e0c87b33986461dcaf2d39feda7c1e2d8d414`。
- Java 8 本地自检：`FrontPracticeServiceImplAssessmentHtmlTest` 57 项、`FrontPracticeV3ContentAuditNoMockTest` 9 项、`SelfAssessmentV3RuleEngineTest` 32 项、`DeepSeekOpenAiClientTest` 7 项，合计 `105/105` 通过；`mvn -nsu -DskipTests compile` 为 `BUILD SUCCESS`，234 个源文件按 target 1.8 编译。

## 进度总结

- 当前状态：进行中；新增分类13轻量报告查询返工，完成实施后仍待独立验收与测试环境真实报告链路验收。
- 当前结论：流式改造已撤回，当前保持非流式调用；规则引擎、内容审计、安全硬拒绝与数据库提示词指纹已完成本地验证。JDK 8 相关回归 `105/105` 和编译通过，但未执行真实 DeepSeek、测试环境完整生成、持久化、详情查询与 APP 展示，不得宣称 DEV-049 整体完成。

## 2026-08-15 既有保留事实

- 既有 DeepSeek Anthropic 兼容入口、模型配置、脱敏错误日志和 9/9 自动化测试结果继续保留；本次不扩大为客户端重构。
- 报告页统一“返回首页”并 reLaunch /pages/home 的既有前端事实继续保留；本次不修改报告页或 uni_modules/**。
