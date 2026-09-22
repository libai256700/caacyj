# TC-DATA-001 自测报告重生成落库校验

## 1. 测试层级

`数据级`

## 2. 对应验收项

- 验收项 ID：`TA-T0018-DATA-001`
- 正式验收入口：`../../01-验收标准.md`

## 3. 前置条件

- 环境前置：正式测试环境后端使用该环境正式数据库和 AI 配置。
- 账号前置：真实已登录学员身份；不在测试资产中记录 Token、Cookie 或密码。
- 数据前置：该学员本人已有的 `report_status=FAILED` 自测 `recordId`，不得由测试构造或写入。

## 4. 测试数据

- Test 在代码中构造 10 条 answers 与 response/session 入参，不从数据库恢复 answers。
- `recordId`、`assessmentResultId`、`userId`、`tenantId`、`practiceId` 必须由正式测试环境显式提供；目标报告记录必须已为 `PENDING`，并归属给定用户。
- opt-in 执行会通过生产 Service 真实写入给定 `assessmentResultId`；默认缺参跳过，不连接或写数据库。

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 准备已有失败报告及其持久化作答数据 | 原报告记录和作答数据可被重生成流程读取 |
| 2 | 执行重生成并核对落库对象 | 原地更新同一条 `yj_assessment_result`，不新增替代记录 |
| 3 | 核对首次生成 PENDING 插入合同 | 初始状态为 `PENDING`，失败原因为空，并兼容既有字段变体 |

## 6. 期望结果

- 重生成使用持久化作答数据，不依赖临时或伪造入参。
- 重生成原地更新同一条 `yj_assessment_result`。
- 首次生成的 PENDING 插入合同保持有效。

## 7. 脚本入口

- 真实依赖脚本：`FrontPracticeAssessmentRegenerateTest#applyAssessmentEvaluation_shouldUseRealSpringDependenciesAndPersistConfiguredRecord`
- 依赖命令：参见 `TC-API-001-自测报告重生成真实入口.md`；只有显式启用并提供真实标识后才执行真实 AI 与同一行落库。
- 结果输出位置：`04-测试执行结论.md`

## 8. 失败判定

- 重生成新建报告记录而非更新原记录。
- 重生成未恢复持久化作答数据，或更新了错误记录。
- 首次生成的 PENDING 状态、失败原因或字段兼容合同失效。

## 9. 执行记录

- 当前状态：`未执行`
- 执行时间：`2026-08-27 13:29`
- 已执行证据：真实依赖方法因缺少显式 enable 与真实标识参数 `Skipped: 1`，未连接数据库、未调用 AI、未写库。
- 待执行证据：授权 opt-in Test 后，以同一 `recordId/assessmentResultId` 核对 `report_status`、`report_content`、`result_summary`、`recommend_direction`、`failure_reason`、`updater`、`update_time`；持久化作答恢复仍由正式重生成接口联调验证。
