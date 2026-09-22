# TASK-027 pre-state 与备份证据

## 结论

- 状态：预部署备份已完成；不代表 Cloud v2 已部署或验收通过。
- 目标：生产节点 `106.13.71.85`。
- 本次未停止、重启或改写旧 API、Neo4j、Nginx、Java、5001 和生产数据库。

## 受控访问

- SSH 主机指纹：`ssh-ed25519 SHA256:9ca5CqWGQQzGeczpSuO82I9/+5XPba/qKRTsfJjrAP4`。
- 专用 key 已验证批处理登录；私钥仅位于 DevCenter 目标服务器 `keys/`，项目不保存私钥。
- `authorized_keys` 变更前备份：`/data/backup/apps/knowledge-qa/access/20260905T140440+0800/authorized_keys.before`。
- 备份 SHA-256：`4b9f59b0d417831172ee1373824c3f26650503a1114e9973a93fd872b5b1b492`。
- 既有密码入口保留；本文不记录密码或其他 secret 值。

## Exact Pre-State

- OS：CentOS Linux 8 x86_64，4 vCPU，7.8 GiB RAM，99 GiB root disk，盘使用约 30%。
- 旧 API：容器 `yunji-knowledge-api`，image id `sha256:d98ac2463b38d0c7f8aa222217cd64dc239922a057b6308d5bad84fadb1955df`，host network，`/home/soft/knowledge-graph:/app` rw，Python 3.11 执行 `pipeline/server.py`，监听 `0.0.0.0:5001`。
- Neo4j：容器 `yunji-knowledge-graph`，Neo4j 2026.05.0，数据挂载 `/home/soft/knowledge-graph/neo4j-docker/data`；只读计数 `3986 nodes / 143661 relationships`。
- Java 调用链：`yunjikeji-admin-server` 通过 `http://127.0.0.1:5001/api/ask` 调用旧 API，当前无 JWT。
- 既有风险：Neo4j 7474/7687 当前公开绑定；Cloud v2 要求 loopback/私网。本任务未越权修改。
- 配置仅采集变量名，不记录值；provider/identity/Neo4j secret 均未读取到本文。

## 备份

- 目录：`/data/backup/apps/knowledge-qa/pre-v2-20260905T141131+0800/`。
- 归档：`knowledge-graph-prestate.tar.gz`。
- 大小：`373703921` bytes。
- SHA-256：`a45a9e9f647f2213758081ad1a5e726d0f2942064b0a8ec0a860138cc52eb88e`。
- 校验：目录内 `SHA256SUMS` 全项通过；`tar -tzf knowledge-graph-prestate.tar.gz` 退出 0。
- 证据：`prestate.txt`、`config-variable-names.txt`、`http-summary.txt`、`neo4j-readonly-counts.txt`、`source-file-inventory.txt`、`archive-members.txt`、`RESTORE.txt`。
- 排除：活动 Neo4j store、Neo4j logs、应用 logs、venv、cache。

## 健康与恢复边界

- `/api/health`：HTTP 200。
- 首次受控 `/api/ask`：HTTP 200，答案非空。
- 旧 API 容器持续 Up；Neo4j 容器持续 healthy。
- 恢复命令记录在远端 `RESTORE.txt`；只有获得发布/回滚批准并停止旧服务后才能执行。
- 本次归档不是一致性 Neo4j dump；图谱切换前必须取得一致性 dump 或使用蓝绿独立 candidate。
