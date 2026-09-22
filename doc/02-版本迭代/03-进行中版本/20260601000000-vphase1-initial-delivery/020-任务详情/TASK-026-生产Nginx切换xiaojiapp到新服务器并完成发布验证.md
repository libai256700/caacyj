# TASK-026 生产Nginx切换 xiaojiapp 到新服务器并完成发布验证

## 实施标准

- 上游事实固定来源于生产机 `106.13.128.217` 的正式 Nginx 生效配置，必须先只读执行 `nginx -T` 盘点 `xiaojiapp.caacyj.com` 对应的 `server/location/upstream`、证书引用和现有 header/path 语义，禁止凭现网页面猜配置。
- 只允许修改与 `xiaojiapp.caacyj.com` 直接相关的 Nginx 反代上游，把实际旧上游切到 `106.13.71.85`；不得先验假设所有 `location` 使用同一协议或端口，不得把 HTTPS 入口改成外跳。
- 生产 SSH 私钥正式依赖已满足：`E:\huiyitechworkspace\feixingxueyuan\prod-106.13.128.217-root` 的 `ssh-keygen` 指纹已确认与正式记录 `SHA256:nQa6F4y8l+3A+A2ojX0u16VF7Rhe1iIxuN34mXWqZoA` 一致。
- 变更前必须完整备份生产 Nginx 生效配置、相关 include 文件和证书引用信息，并明确回滚命令或回滚步骤；生产验证失败时必须按备份自动回滚并恢复。
- 变更后必须先 `nginx -t`，通过后优先平滑 `reload`；只有在 `reload` 明确不适用时才允许 `restart`，并记录原因以避免不必要的生产中断。
- 验收必须同时覆盖生产机到新机的 Host/SNI 连通性、外部 `https://xiaojiapp.caacyj.com/`、关键静态资源、相关 API 路径与其他生产站点回归，确认请求不会误落默认站点或旧上游。

## 对应技能

- `00-0600-deployment-architecture-management`
- `00-1000-server-deployment-standards`

## 交付物

- `061-验收标准/00-验收标准索引.md`
- `061-验收标准/01-验收执行详情/AC-PROD-NGINX-001.md`
- `061-验收标准/01-验收执行详情/AC-PROD-NGINX-101.md`
- `061-验收标准/01-验收执行详情/AC-PROD-NGINX-201.md`
- `061-验收标准/01-验收执行详情/AC-PROD-NGINX-301.md`
- `061-验收标准/01-验收执行详情/AC-PROD-NGINX-401.md`
- 生产 Nginx 变更记录、备份路径、回滚步骤与发布验证记录

## 分支安排详情

- 当前版本代码现场模式：`复杂模式`
- 当前实际代码目录：`code/develop/`
- 当前实际工作分支：`feature/20260601000000-vphase1-initial-delivery`
- 本任务只涉及生产机 Nginx 配置变更与验证，不改项目源码、不改数据库、不改 DNS
- 目标新机：`106.13.71.85`
- 生产入口：`https://xiaojiapp.caacyj.com/`

## 关联验收项

- `AC-PROD-NGINX-001`
- `AC-PROD-NGINX-101`
- `AC-PROD-NGINX-201`
- `AC-PROD-NGINX-301`
- `AC-PROD-NGINX-401`

## 任务产出 / 结果记录

- 2026-09-04 已在当前版本正式计划、任务索引与验收索引中建立 `TASK-026` 和配套验收入口。
- 已确认生产 SSH 私钥路径 `E:\huiyitechworkspace\feixingxueyuan\prod-106.13.128.217-root`，其 `ssh-keygen` 指纹与正式记录一致。
- 生产机 `106.13.128.217` 已按 `nginx -T` 盘点旧映射：旧根路径使用本地静态内容，旧 admin 反代到 `114.111.30.111:18081`，旧 api 反代到 `114.111.30.111:18080`。
- 本次仅将根、admin、api 三处反代统一切到 `https://106.13.71.85`，SNI 固定 `yunjikeji.lai-do.com`；两个隐私相关路径保持本地不变，DNS 继续指向 `106.13.128.217`。
- 变更前完整备份位于 `/data/backup/nginx/conf/TASK-026-20260904175724`；`nginx -t` 已通过，并于 `2026-09-04 17:58:54` 对生产 Nginx 执行平滑 `reload`，未触发 `restart` 或回滚。
- 外部 `https://xiaojiapp.caacyj.com/`、关键静态资源、相关 API、新机日志与其他生产站点回归均已通过；生产 Java 应用未重启，独立验收结论为 `PASS`。

## 进度总结

- 当前状态：已完成。
- 当前结论：`TASK-026` 已按最小影响面完成生产 Nginx 上游切换与发布验证；外部验证、日志核对、其他生产站点回归和独立验收均通过，当前版本整体仍保持 `进行中`。
