# TC-DATA-002 自测报告生成日志与 HTML 回归

## 1. 测试层级

`数据级`

## 2. 对应验收项

- 验收项 ID：`TA-T0018-API-002`、`TA-T0018-CODE-001`
- 正式验收入口：`../../01-验收标准.md`

## 3. 前置条件

- 环境前置：原 Maven 测试验证环境可运行自测报告 HTML 测试。
- 账号前置：本用例不需要人工登录态，不记录账号、Token、Cookie 或密码。
- 数据前置：使用 `03-测试数据模板.json` 中 `regenerateAssessmentReport.logFields` 定义的日志字段集合。

## 4. 测试数据

```json
{
  "dataEntry": "03-测试数据模板.json#regenerateAssessmentReport.logFields",
  "requiredFieldCount": 11,
  "htmlTarget": "assessment report"
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 执行真实报告生成入口相关测试 | 生成入口处理恢复后的会话、作答和记录数据 |
| 2 | 核对关键日志字段 | 方法名、题目数、正确数、租户、用户、练习、模式、记录和作答数量字段均可追踪 |
| 3 | 执行报告 HTML 回归断言 | 既有 HTML 输出合同保持兼容，无本次修复引入的结构回归 |

## 6. 期望结果

- 真实生成入口的关键上下文可通过日志字段追踪。
- 日志不记录账号凭证、Token、Cookie 或密码。
- 自测报告 HTML 输出保持既有兼容性。

## 7. 脚本入口

- 自动化脚本：`FrontPracticeServiceImplAssessmentHtmlTest`
- 依赖命令：`mvn -o -pl yunjikeji-admin-server "-Dtest=FrontPracticeServiceImplAssessmentHtmlTest" test`
- 结果输出位置：`04-测试执行结论.md`

## 8. 失败判定

- 真实生成入口缺少测试数据模板列出的关键可追踪字段。
- 日志包含账号凭证、Token、Cookie 或密码。
- 报告 HTML 合同出现与本次修复相关的兼容性回归。

## 9. 执行记录

- 当前状态：`已通过`
- 执行时间：`2026-08-27 11:33`
- 已执行证据：本条只保留 `FrontPracticeServiceImplAssessmentHtmlTest` 的既有 HTML 合同回归结论；原合并统计中的重生成替身测试已撤回，不作为真实入口、真实日志或真实落库证据。
