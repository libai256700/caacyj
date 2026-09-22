# TASK-025 新测试服务器环境安装与应用迁移

## 实施标准

- 上游事实：`E:\huiyitechworkspace\feixingxueyuan\服务器信息.txt`、`E:\huiyitechworkspace\feixingxueyuan\数据库信息.txt`、`TASK-003` 服务器采购与部署架构图，以及当前版本正式计划与正式验收标准。
- 以新测试服务器 `106.13.71.85` 作为并行测试环境先完成基础环境安装，再迁移五个工程的运行态；旧测试服务器保持可用，不停机，不改 DNS，不把新机当成旧机的覆盖式替换。
- 新服务器初始口令仅用于临时接入，部署后改用受控 SSH 私钥；正式计划和验收回写中不得记录明文口令。
- 基础环境必须完成 SSH key 化、Docker、Nginx、Java 及项目运行依赖安装与校验。
- Redis 在新机本地持久化部署，默认新空实例，端口 `6379`，按实施事实选择容器或 systemd，不迁旧缓存 / 会话，旧 Redis 不停；`knowledge-graph` 按旧机现状迁移 Neo4j 当前数据和 config；`QwenPaw` 按旧机现状迁移容器、必要运行卷和 config；`yunjikeji` 仅部署 H5，不部署 App / uniCloud，也不迁未点名的 `yunjikeji-server`；`yunjikeji-admin-server` 与 `yunjikeji-admin-ui` 按当前代码构建部署。
- MySQL 使用用户提供的内网库 `172.16.32.2:3306`，schema 为 `yunjikeji_test`，由应用直接连接；不保留本地 `13306` 或 `127.0.0.1:3306` 代理。验收使用 IP + Host / `curl --resolve`，DNS 切换另行放行。

## 对应技能

- `00-0600-deployment-architecture-management`
- `00-1000-server-deployment-standards`
- `20-0200-acceptance-standards-documentation`
- `30-0100-development-task-breakdown`

## 交付物

- `061-验收标准/00-验收标准索引.md`
- `061-验收标准/01-验收执行详情/AC-NEWSERVER-001.md`
- `061-验收标准/01-验收执行详情/AC-NEWSERVER-101.md`
- `061-验收标准/01-验收执行详情/AC-NEWSERVER-201.md`
- `061-验收标准/01-验收执行详情/AC-NEWSERVER-301.md`
- `061-验收标准/01-验收执行详情/AC-NEWSERVER-401.md`
- 新测试服务器基础环境安装、五应用迁移、IP + Host 复核与健康检查记录

## 分支安排详情

- 当前版本代码现场模式：`复杂模式`
- 当前实际代码目录：`code/develop/`
- 当前实际工作分支：`feature/20260601000000-vphase1-initial-delivery`
- 新服务器仅作并行测试环境，旧测试服务器保持可用，不改 DNS
- `knowledge-graph` 与 `QwenPaw` 按旧机现状迁移，`yunjikeji` 仅 H5，`yunjikeji-admin-server` 与 `yunjikeji-admin-ui` 按当前代码构建部署

## 关联验收项

- `AC-NEWSERVER-001`
- `AC-NEWSERVER-101`
- `AC-NEWSERVER-201`
- `AC-NEWSERVER-301`
- `AC-NEWSERVER-401`

## 任务产出 / 结果记录

- 2026-09-04 已依据 `服务器信息.txt` 收口新服务器事实，并建立新测试服务器环境安装与应用迁移任务的正式计划与验收入口；验收状态为 `待验证`。
- 2026-09-04 已在新机 `106.13.71.85` 完成 Java、Docker、Docker Compose、Nginx 与必要运行依赖安装，受控 SSH 接入及服务启动入口验证通过。
- 新机 Redis 已按新空实例持久化部署；后台应用直连内网数据库 `172.16.32.2:3306/yunjikeji_test`，未部署本地 MySQL，也未保留本地数据库端口代理。
- `knowledge-graph` 的 Neo4j 运行态与数据、`QwenPaw` 的容器与必要运行卷已迁移并健康运行；`yunjikeji` H5、`yunjikeji-admin-server`、`yunjikeji-admin-ui` 已由当前代码产物部署并可访问。
- 迁移前已完成必要备份；Neo4j 与 QwenPaw 一致性迁移使用短暂停机窗口，复制完成后旧机对应服务立即恢复。旧测试服务器继续保活，DNS 未切换。
- 新机外部 `curl` 正式入口验证返回 `HTTP 200`，服务健康、数据承接、代码边界与部署闭环由不同代理独立复核，结论为 `PASS`。

## 进度总结

- 当前状态：已完成。
- 当前阶段：基础环境、服务迁移、入口验证与独立验收均已完成。
- 当前结论：`TASK-025` 独立验收 `PASS`；新测试服务器采用并行部署，旧机保活且未切 DNS。该结论仅关闭本任务，不代表当前版本整体完成。
