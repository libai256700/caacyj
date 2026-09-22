# TASK-027 Neo4j 一致性备份与隔离门禁证据

## 备份与恢复

| 项目 | 事实 |
| --- | --- |
| Neo4j edition/version | Community `2026.05.0` |
| 数据库 | `neo4j`（另有 `system`） |
| 备份命令 | 同版本 `neo4j-admin database dump neo4j --to-path=<backup-dir> --overwrite-destination=true` |
| dump 路径 | `/data/backup/apps/knowledge-qa/neo4j-consistency-20260905T1810+0800/neo4j.dump` |
| dump 大小 | `78390872` bytes |
| dump SHA-256 | `7738a27a7c7bd18ae7db4eb5476e4f55d06d9a34557d70ca29f9a4f1feea9dc1` |
| 原容器 | 停止后使用同一容器恢复，容器 ID 未变化 |

维护窗口内先确认 5001 无已建立连接并记录旧 API 恢复路径；Neo4j 停止后完成 dump，随后立即启动原容器。恢复确认结果：Neo4j `running/healthy`，旧 API `/api/health` HTTP 200，5001 正常监听，Neo4j 只读计数恢复为 `3986 nodes / 143661 relationships`。

## Candidate 隔离核对

- 交付 importer 使用 Neo4j driver `6.2.0`，连接 URI、用户名、密码和数据库均由环境变量提供，写事务使用 `WRITE_ACCESS`。
- importer 只执行交付内固定参数化 Cypher，并以 `graph_release_id` 为 candidate namespace；runtime reader 使用相同数据库和 release 过滤，以 `READ_ACCESS` 只读查询。
- 当前生产实例为 Community 单实例，仅有 `neo4j` 与 `system` 数据库，当前仅有现有 `neo4j` 用户；未配置可验证的独立 import/runtime 账号。
- 因而 scoped graph 尚未导入。继续导入前必须满足以下任一条件：
  1. 用户批准同库 `graph_release_id` namespace + 独立最小权限 import/runtime 账户方案，并完成权限验证；或
  2. 提供独立 Neo4j 实例/数据库用于 candidate。
- 在隔离方案获批前，不降低权限、不覆盖现有图、不执行生产 Cypher、不启动新 runtime。

## Provider 与 Embedding 门禁

- 旧 provider 配置路径：`/home/soft/knowledge-graph/pipeline/config.json`。
- 旧配置 SHA-256：`19cc96b1d92d0a5a4df835284130225654fea62882b16b34a2d86d8d694df9a3`。
- 旧配置包含外部 provider endpoint 和 secret；本证据不记录 secret 值。未发现可验证的 Stop B production approval、egress mapping 或 external hash anchor，不能直接映射到 Cloud v2 provider contract。
- 旧 Embedding 为本机 Ollama `bge-m3:latest`，digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`，与交付 Embedding identity 一致。

## 当前状态

```text
neo4j_consistency_backup: true
neo4j_recovery_verified: true
neo4j_candidate_import: pending_isolation_approval
production_provider: pending_stop_b_approval
runtime_active: false
product_accepted: false
```

本文件是服务器实施证据，不是完整生产验收结论。未执行 provider/identity、public/ops WSGI、Java/Nginx、5001 切流、回滚演练或产品 QA。
