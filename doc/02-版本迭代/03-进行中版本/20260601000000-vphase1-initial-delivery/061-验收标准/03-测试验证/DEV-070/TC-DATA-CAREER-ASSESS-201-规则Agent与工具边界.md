# TC-DATA-CAREER-ASSESS-201 规则 Agent 与工具边界

## 1. 测试层级

`数据级`

## 2. 对应验收项

- 验收项 ID：`AC-CAREER-ASSESS-201/202/301`
- 正式验收入口：`../../01-验收执行详情/AC-CAREER-ASSESS-201.md`

## 3. 前置条件

- 环境前置：本任务禁止数据库写入，仅检查程序结构和隔离边界。
- 账号前置：无。
- 数据前置：职业规划分类14、Agent固定主键3；自评分类13、Agent固定主键2。

## 4. 测试数据

题库固定 `category=14/questions=47/answers=111`。Agent固定 `id=3,name=职业规划评测,status=1,tenant_id=1`，`agent_id/knowledge_base_id/reply_strategy=NULL`，`prompt_config=career-core.mjs`提取的 `SELF_SYSTEM_PROMPT`；id=3冲突即中止。

## 5. 执行动作

| 步骤 | 动作 | 预期结果 |
| --- | --- | --- |
| 1 | 结构化扫描职业规划后端路由 | 经 record.category_id 批次ID反查 catalog batch 的真实 category |
| 2 | 检查固定常量和规则类 | 分类13仍为Agent 2/V3；分类14为Agent 3/独立规则 |
| 3 | 比较当前应用local配置 | 分别解析传入配置与仓库固定 `application-local.yaml` 的host/port/database，完全一致后才连接；禁止CLI切换host/port/database及异库JDBC |
| 4 | 检查apply AST主路径 | 同库连接 -> 前置校验 -> 备份 -> begin/禁autocommit -> 写入 -> 事务内回读 -> commit；全部异常分支rollback并重新抛出；dry-run零DML |
| 5 | 扫描两个Python入口与业务引用 | 题库和Agent工具独立、默认dry-run、业务/启动/build/migration零引用 |
| 6 | 执行Python mutation | 异库、错误连接数据流、错序、dry-run写入、缺rollback、id3后检、错误计数及Agent字段变体全部被拒绝 |

## 6. 期望结果

- 当前因职业规划规则、Agent 3 路由和两工具均不存在而红灯。
- 不执行数据库查询或写入，不冒充真实初始化回执。

## 7. 脚本入口

- 自动化脚本：`dev070-contract.mjs --suite=feature`
- 依赖命令：Node.js
- 结果输出位置：`command-results.md`

## 8. 失败判定

- 直接把 record.category_id 与13/14比较。
- 工具允许任意host/port/database、未复用当前应用local配置，或事务步骤顺序/异常回滚/dry-run边界不成立。
- Agent任一固定字段不精确、未使用精确 `AGENT_ROW` 写入/回读，或id=3检查晚于任何写入。
- 运行时按name/agent_id查询或创建Agent，或把手工工具接入业务链路。
