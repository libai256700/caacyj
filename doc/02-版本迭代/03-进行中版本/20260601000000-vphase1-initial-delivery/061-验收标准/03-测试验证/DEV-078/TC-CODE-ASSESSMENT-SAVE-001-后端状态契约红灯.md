# TC-CODE-ASSESSMENT-SAVE-001 后端状态契约红灯

## 1. 测试层级

`接口级 / 数据级 / 代码级`

## 2. 对应验收项

- 验收项 ID：`AC-ASSESSMENT-SAVE-101/201/301`
- 正式验收入口：`061-验收标准/01-验收执行详情/`

## 3. 前置条件

- 本地仅执行静态契约和既有单元保护测试，不连接数据库。
- 生产代码尚未实施 DEV-078。
- 分类13/14既有完成点和职业规划 report-entry 必须保留。

## 4. 测试数据

见 `test-data.json` 的 `backend_state_matrix` 与 `failure_matrix`。

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 运行 `AssessmentBatchSaveStatusContractTest` | 因缺少 status 字段、条件跃迁、latest-status 投影和失败收口而红灯 |
| 2 | 同时运行既有 batch-start 与分类隔离保护测试 | 既有保护测试保持通过，证明红灯由 DEV-078 缺失导致 |
| 3 | 检查失败保存边界 | 原答案异常继续抛出，失败事务回滚后以独立可靠边界写 status=2 |

## 6. 期望结果

- 新批次为0，startBatch 不置1。
- 分类13/14第一条答案明细写入前以 `status=0 AND is_completed=0` 条件置1，状态2不回退。
- 分类13原完成点、分类14原 report-entry 完成点成功时均写 `is_completed=1,status=2`。
- 任一答案持久化失败时保留原异常，并在回滚后独立提交 `status=2`；此时允许 `is_completed=0,status=2`。
- 分类13/14 latest-status 仅返回本人、对应分类最新批次的真实状态；report-entry 语义不变。

## 7. 脚本入口

- 自动化脚本：`yunjikeji-admin-server/src/test/java/com/huiyitech/app/practice/service/AssessmentBatchSaveStatusContractTest.java`
- 依赖命令：见 `command-results.md`
- 结果输出位置：Maven Surefire 控制台与 `test-conclusion.md`

## 8. 失败判定

- 因编译、路径、依赖或测试语法错误失败，视为假红灯。
- DEV-078目标断言未满足且既有保护用例通过，视为正确红灯。
