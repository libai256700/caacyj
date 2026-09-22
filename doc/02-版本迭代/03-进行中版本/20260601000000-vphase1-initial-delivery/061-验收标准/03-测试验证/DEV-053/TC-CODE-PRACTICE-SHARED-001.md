# TC-CODE-PRACTICE-SHARED-001 练习共享代码契约

## 对应验收项

- `AC-PRACTICE-SHARED-001`
- `AC-PRACTICE-SHARED-101`
- `AC-PRACTICE-SHARED-201`
- `AC-PRACTICE-SHARED-301`

## 执行入口

在仓库根目录执行：

```powershell
python "doc/02-版本迭代/03-进行中版本/20260601000000-vphase1-initial-delivery/061-验收标准/03-测试验证/DEV-051/run_practice_shared_contract.py" --output "doc/02-版本迭代/03-进行中版本/20260601000000-vphase1-initial-delivery/061-验收标准/03-测试验证/DEV-053/execution-results.json"
```

## 覆盖范围

- 七个目标 DO 使用 `BaseDO` 并显式忽略租户拦截。
- 题目、分类、答案、子答案、练习记录、记录明细、错题记录、测评结果的查询和插入不再使用 `tenant_id`。
- `yj_practice_setp` 保持原有无租户条件的读取路径。
- 错题按 `customer_account_id + exercises` 唯一处理。
- 迁移 SQL 不再为目标表写入 `tenant_id`；兼容 DDL 具备重复门禁和未知复合索引保护。
- 迁移 SQL 在插入前固化五张唯一候选 ID 快照；配对回滚脚本只删除本次候选行并登记脚本索引。
- 五段 `INSERT ... SELECT` 均 `INNER JOIN` 各自首次候选 ID 快照，重跑不会导入快照创建后新增的源数据；回滚也只删除同一组快照 ID。
- 兼容 DDL 后置校验直接读取两个可选表的 `tenant_id` 列，区分已移除、因索引风险保留和非预期残留。
- `agent_info`、认证门禁及其他非目标资源继续保留租户语义。
- 后端模块编译、差异格式和 `uni_modules/**` 工作区/暂存区保护检查。

## 结果判定

- 全部脚本步骤退出码为 `0` 时，本地代码和静态数据契约通过。
- 本用例不执行数据库，不替代测试环境双租户集成验证，也不构成 `DEV-054` 独立验收结论。
- 正式 Python 入口同时执行 SQL 资产静态契约、Java 契约、编译和受保护路径检查。
