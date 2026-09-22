# TC-API-WRONG-101 错题管理默认false与不限三态接口契约

## 1. 测试层级

`接口级`

## 2. 对应验收项

- 验收项 ID：`AC-ADMIN-WRONG-101`
- 正式验收入口：`../../01-验收执行详情/AC-ADMIN-WRONG-101.md`

## 3. 前置条件

- 环境前置：后端模块可执行 `UserPracticeExercisesRecordSqlContractTest`
- 账号前置：无
- 数据前置：使用现有后端契约测试输入 `is_correct=false` 与 `is_correct=''`

## 4. 测试数据

```json
{
  "paramsWhenDefaultWrongOnly": {
    "category_name": "概述",
    "question_keyword": "题干",
    "is_correct": "false"
  },
  "paramsWhenUserSelectUnlimited": {
    "is_correct": ""
  }
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 执行 `mvn '-Dtest=UserPracticeExercisesRecordSqlContractTest' test` | 后端聚焦测试启动成功 |
| 2 | 核对 `wrongDetailWhere_shouldFilterCategoryQuestionAndBooleanWhenProvided` | SQL 追加 `AND d.is_correct = ?`，参数承接 `false` |
| 3 | 核对 `wrongDetailWhere_shouldNotAppendBooleanFilterWhenIsCorrectIsBlank` | “不限”分支不追加 `d.is_correct = ?` |

## 6. 期望结果

- 默认错题筛选与用户主动“不限”在接口层有独立契约
- `COUNT` / list 共用的 where 逻辑保留 `false`，但不会把空串误当成 `false`

## 7. 脚本入口

- 自动化脚本：后端 `UserPracticeExercisesRecordSqlContractTest`
- 依赖命令：`mvn '-Dtest=UserPracticeExercisesRecordSqlContractTest' test`
- 结果输出位置：`command-results.md`

## 8. 失败判定

- 测试未达到 `6/6` 或 `BUILD SUCCESS`
- `false` 分支不再追加 `d.is_correct = ?`，或“不限”分支误追加该条件
