# VC-VAPP-TESTENV-001 测试环境部署门禁

## 验收类型

`闭环项`

## 业务场景

在 `TEST-3DAPP-MICRO-01` 上部署 `yunjikeji` 前端和 `yunjikeji-server` 后端前，必须先确认正式部署入口、Nginx 路由、端口和测试库连接记录。

## 验收标准说明

测试环境部署不得凭聊天印象或代码局部配置直接执行；所有应用级入口和连接信息必须落在正式记录中，且与当前主机已有服务不冲突。

## 核心对象

- `TEST-3DAPP-MICRO-01`
- `server-info.md`
- `AppList-01.md`
- `applications.md`
- `yunjikeji`
- `yunjikeji-server`
- Nginx 配置
- 测试库连接记录

## 前置条件

1. 已确认测试环境正式主机为 `TEST-3DAPP-MICRO-01`。
2. 已读取 `server-info.md`、`AppList-01.md` 和 `applications.md`。
3. 待补齐信息不允许用推测值替代。

## 触发动作

1. 核对 `AppList-01.md` 是否已有 `yunjikeji` 和 `yunjikeji-server` 应用登记。
2. 核对 Nginx 静态路由和 API 代理路由是否已有正式记录。
3. 核对后端服务端口是否与现有服务冲突。
4. 核对 `applications.md` 是否已有 `yunjikeji` 专属测试库连接记录。
5. 核对部署前备份、回滚和日志路径是否明确。

## 期望结果

1. `yunjikeji-server` 的应用名、部署目录、启动脚本、停止脚本、日志目录、运行 profile、外部配置路径和健康检查 URL 全部明确。
2. `yunjikeji` 的访问 URL、静态目录、构建产物目录、Nginx 路由、备份与回滚口径全部明确。
3. 后端端口和 Nginx 路由确认不与现有服务冲突。
4. `yunjikeji` 测试库正式连接记录已经补齐。
5. 未满足以上条件时，不得进入 `TASK-018-04` 部署实施。

## 执行结果

1. `2026-05-13`：`TASK-018-04/05` 已在唯一测试服务器 `TEST-3DAPP-MICRO-01` 完成预备部署。
2. 首次预备部署备份目录：`/home/soft/backup/yunjikeji-20260513083338`。
3. 后端健康检查结果：端口 `18080` 可用，`/api/health` 与 `/api/health/db` 已验证通过。
4. 首次前端与 Nginx 路由结果：`/yunjikeji/` 可访问，`/yunjikeji-api/api/health` 已验证通过。
5. `2026-05-14`：最新前端 H5 包已按“先备份后部署”重新发布到测试环境，远程备份目录为 `/home/soft/backup/20260514065123/yunjikeji-web`，静态部署目录为 `/home/soft/web/yunjikeji`。
6. 最新前端访问校验结果：`https://yunjikeji.lai-do.com/` 返回 `200`，抽样 JS 资源返回 `200`。
7. 当前边界：本执行结果只证明测试环境预备部署和最新前端包覆盖部署成立；六页面端到端、关键数据、完整接口契约和版本正式验收仍需后续独立验收。
