# TC-T0014-CODE-001 SQL资产边界

## 1. 测试层级

`接口级`

## 2. 对应验收项

- 验收项 ID：`TA-T0014-CODE-001`
- 正式验收入口：`../../../../01-验收标准.md`

## 3. 前置条件

- 实施目录中的 mapping、backup、更新、回滚、校验和 execution-log 均存在。
- 不执行更新或回滚 SQL。

## 4. 测试数据

```json
{"category_id": 13, "tenant_id": 1, "write_execution": false}
```

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 静态拆分全部 SQL 语句并检查 DML 边界 | 仅允许目标表、tenant/category 和精确 ID 集合 |
| 2 | 核对步骤反向引用断言、幂等、备份与回滚对应 | 全部成立 |
| 3 | 检查 verify SQL 的语句类型 | 仅只读事务控制和查询语句 |

## 6. 期望结果

- 自动化静态审查整体通过。

## 7. 脚本入口

- 自动化脚本：`../05-自动化测试脚本/verify_t0014_readonly.py`
- 结果输出位置：`../t0014-readonly-result.json`

## 8. 失败判定

- 首次实际失败：分类器允许集遗漏安全的 `ROLLBACK`，导致 `verifyIsReadOnly=false` 和整体退出码 1；证据为 `../t0014-readonly-result.json`。
- 修复后重测：内置 9 正例/14 反例自测通过，完整只读脚本退出码 0 且 `overallPass=true`；证据为 `../t0014-readonly-result-rerun.json`。
- 第二次独立验收失败：分类器对所有 `SELECT` 直接返回允许，错误放行 `SELECT ... FOR UPDATE`、`SELECT ... INTO OUTFILE` 和 `SELECT ... INTO DUMPFILE`，不满足 fail-closed；验收代理不修复。
