# AC-KGCLOUD-401 生产知识问答发布闭环

- 类型：闭环项
- 正式入口：`AC-KGCLOUD-001/101/201/301`、部署记录、回滚演练、独立验收、版本计划与部署现状回写。
- 支撑的业务结果：Cloud v2 在生产真实生效并有可靠回退能力，交付、运行和产品验收状态不会混淆。
- 技术边界：部署成功或进程存活不等于产品验收；实施与独立验收必须由不同代理完成。
- 通过条件：Release、Authority、Retrieval、Graph、Provider、Runtime、产品和代表性问答均通过；回滚演练、状态回写和无未关闭阻断缺陷齐备；分别记录 `github_delivery_complete`、`deployment_handoff_ready`、`runtime_active`、`product_accepted`。
- 证据承接方式：四个前置验收项、部署/回滚/QA 报告和正式状态回写共同承接。

## 验收结果

- 状态：受阻，前置验收项未完成。
- 当前状态拆分：`github_delivery_complete=true`（沿用已核验的交付事实）；`deployment_handoff_ready=false`；`runtime_active=false`；`product_accepted=false`。
- 已有证据：生产预部署备份、Neo4j 一致性 dump 与恢复验证、final delivery staging、Python/wheelhouse/venv/USEarch 阶段均完成，旧服务保持可用。
- 未满足：Community import/runtime 账户隔离方案、scoped Neo4j candidate、provider Stop B/identity、public/ops WSGI、切流、真实回滚演练、代表性产品 QA、独立验收及最终状态回写。
- 证据入口：`../03-测试验证/TASK-027/01-prestate-and-backup.md`、`../03-测试验证/TASK-027/02-release-staging-and-runtime.md`、`../03-测试验证/TASK-027/04-wheelhouse-venv-usearch.md`、`../03-测试验证/TASK-027/05-neo4j-consistency-backup.md`。
