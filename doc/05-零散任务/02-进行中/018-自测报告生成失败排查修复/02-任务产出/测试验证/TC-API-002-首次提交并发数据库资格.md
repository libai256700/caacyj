# TC-API-002 首次提交并发数据库资格

## 1. 测试层级

`接口级 / 数据级`

## 2. 对应验收项

- 验收项 ID：`TA-T0018-API-004`、`TA-T0018-DATA-001`
- 正式验收入口：`../../01-验收标准.md`

## 3. 前置条件

- 环境前置：当前代码可完成 Maven 测试与编译；不连接或写入运行数据库。
- 账号前置：无。
- 数据前置：使用生产源码契约，不创建伪数据库或伪业务记录。

## 4. 测试数据

```json
{
  "recordOwnershipSql": "id + customer_account_id + deleted + FOR UPDATE",
  "resultStates": ["PENDING", "SUCCESS", "FAILED"]
}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 检查首次提交取得资格的事务代码 | 通过真实练习记录行锁串行同一 `recordId` |
| 2 | 检查锁内 latest 二次判定 | 无结果才新增；FAILED 原地认领；PENDING/SUCCESS 不重复调度 |
| 3 | 检查异步入队位置 | 短事务提交完成后才入队 |
| 4 | 执行契约测试与编译 | 契约测试和编译通过 |

## 6. 期望结果

- 多实例重复提交不会各自创建无任务承接的最新 `PENDING`。
- 重生成取得数据库资格后不会再被 JVM 本地门禁短路。

## 7. 脚本入口

- 自动化脚本：`FrontPracticeAssessmentPendingInsertContractTest`
- 依赖命令：`mvn -pl yunjikeji-admin-server "-Dtest=FrontPracticeAssessmentPendingInsertContractTest" test`
- 结果输出位置：`04-测试执行结论.md`

## 8. 失败判定

- 仍以 JVM 集合作为唯一正确性门禁。
- 行锁缺少当前用户归属条件，或在事务提交前启动异步任务。
- 重复请求可留下无任务承接的最新 `PENDING`。

## 9. 执行记录

- 当前状态：`已通过`
- 执行时间：`2026-08-27 12:45`
- 已执行证据：无本地替身契约测试 4/4 通过，Maven compile 通过。
