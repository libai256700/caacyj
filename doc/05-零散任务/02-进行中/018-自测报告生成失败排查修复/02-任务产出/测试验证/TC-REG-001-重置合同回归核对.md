# TC-REG-001 重置合同回归核对

## 1. 测试层级

`数据级`

## 2. 对应验收项

- 验收项 ID：`TA-T0018-CODE-001`
- 正式验收入口：`../../01-验收标准.md`

## 3. 前置条件

- 环境前置：原 Maven 测试验证环境可运行 `FrontPracticeAssessmentResetContractTest`。
- 账号前置：本用例不需要人工登录态，不记录账号、Token、Cookie 或密码。
- 数据前置：沿用 `FrontPracticeAssessmentResetContractTest` 内既有重置合同测试数据。

## 4. 测试数据

```json
{
  "testClass": "FrontPracticeAssessmentResetContractTest",
  "expectedPassed": 9,
  "expectedFailed": 0
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 运行既有 ResetContractTest 全部用例 | 全部重置合同测试被执行 |
| 2 | 核对测试数量和失败数 | `9/9` 通过且无失败 |
| 3 | 核对重生成修复对邻接重置合同的影响 | 未发现 reset 合同失真或邻接回归 |

## 6. 期望结果

- `FrontPracticeAssessmentResetContractTest` 全部 `9/9` 通过。
- 重生成修复不破坏既有重置合同。

## 7. 脚本入口

- 自动化脚本：`FrontPracticeAssessmentResetContractTest`
- 依赖命令：`mvn -pl yunjikeji-admin-server "-Dtest=FrontPracticeAssessmentResetContractTest" test`
- 结果输出位置：`04-测试执行结论.md`

## 8. 失败判定

- ResetContractTest 任一用例失败或未执行。
- 出现与本次修复相关的 reset 合同失真。

## 9. 执行记录

- 当前状态：`已通过`
- 执行时间：`2026-08-27 11:33`
- 已执行证据：`04-测试执行结论.md` 明确记录 `FrontPracticeAssessmentResetContractTest` 已复跑为 `9/9` 通过，且未再看到 reset 合同失真。
