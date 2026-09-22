# TC-API-001 自测报告重生成真实入口

## 1. 测试层级

`接口级`

## 2. 对应验收项

- 验收项 ID：`TA-T0018-API-001`、`TA-T0018-API-002`、`TA-T0018-API-003`
- 正式验收入口：`../../01-验收标准.md`

## 3. 前置条件

- 环境前置：正式测试环境后端已运行，并使用该环境正式数据库和 AI 配置。
- 账号前置：提供真实已登录学员 `accessToken`，但不得把 Token、Cookie 或密码写入仓库。
- 数据前置：提供该学员本人在正式测试环境中已有的 `report_status=FAILED` 自测 `recordId`；测试不得自行构造或写入数据库记录。

## 4. 测试数据

- Test 构造 `response`、`session` 和 10 条代表性量表 `answers` 方法入参；answers 不从数据库读取，也不作为持久化作答恢复证据。
- 必填系统参数：`assessment.integration.enabled=true`、`springProfile`、`recordId`、`assessmentResultId`、`userId`、`tenantId`、`practiceId`。
- 参数缺失时 JUnit assumption 明确标记 `SKIPPED`，不会使用默认环境或默认关联标识。

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 准备失败状态报告及其已持久化作答、租户、练习和模式数据 | 重生成入口能够读取原报告及其关联数据 |
| 2 | 调用自测报告重生成接口 | 接口按原记录恢复生成所需入参，不使用占位或伪造数据 |
| 3 | 核对真实报告生成入口的调用 | 真实生成入口收到恢复后的会话、作答和记录标识 |

## 6. 期望结果

- 重生成接口从持久化记录恢复完整生成入参。
- 接口调用真实报告生成入口，报告状态按生成结果更新。
- 关联记录标识保持一致，不产生无关的新报告记录。

## 7. 脚本入口

- 真实依赖方法：`FrontPracticeAssessmentRegenerateTest#applyAssessmentEvaluation_shouldUseRealSpringDependenciesAndPersistConfiguredRecord`
- 依赖命令：`mvn -pl yunjikeji-admin-server "-Dtest=FrontPracticeAssessmentRegenerateTest#applyAssessmentEvaluation_shouldUseRealSpringDependenciesAndPersistConfiguredRecord" "-Dassessment.integration.enabled=true" "-Dassessment.integration.springProfile=<profile>" "-Dassessment.integration.recordId=<record-id>" "-Dassessment.integration.assessmentResultId=<pending-result-id>" "-Dassessment.integration.userId=<user-id>" "-Dassessment.integration.tenantId=<tenant-id>" "-Dassessment.integration.practiceId=<practice-id>" test`
- 结果输出位置：`04-测试执行结论.md`

## 8. 失败判定

- 无法从持久化记录恢复作答、会话或记录标识。
- 未调用真实报告生成入口，或调用入参与持久化数据不一致。
- 重生成产生无关新记录或未按结果更新报告状态。

## 9. 执行记录

- 当前状态：`未执行`
- 执行时间：`2026-08-27 13:29`
- 已执行证据：真实依赖方法在缺少显式 enable 与真实标识参数时 `Skipped: 1`；跳过发生在 Spring 上下文启动前，未连接数据库、未调用 AI、未写库。
- 待执行证据：正式测试环境提供真实参数后运行该方法，并以同一 `recordId` 核对生成日志和数据库最终字段；Controller 鉴权及持久化作答恢复仍由正式接口联调单独验证。
