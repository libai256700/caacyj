# DEV-068 测试环境关闭异常 IoT Quartz

## 实施标准

- 先按 [PD-068](../040-程序设计/[程序设计]PD-068-20260828-DEV-068-测试环境关闭异常IoT-Quartz.md) 落实唯一正式设计，再按正式验收项执行测试环境部署与复核。
- 当前异常只允许关闭 IoT 独立 scheduler `iotScheduler`，其职责仅覆盖 IoT TIMER 场景；不得关闭全局 Quartz 或其他调度。
- 测试 profile 必须通过明确配置开关关闭 IoT Scheduler 自动装配；`IotSceneRuleTimerHandler` 在关闭时必须安全 no-op，不得因为 bean 缺失导致启动失败。
- DEVICE / 设备属性 / 设备状态触发链路不得删除或改写；仅禁用定时触发器注册、更新、注销与暂停的实际执行入口。
- 部署前必须先备份测试服务器当前部署目录与启动脚本，再执行重建、重启与健康检查；不直接操作生产数据库。
- 应用源码白名单仅限 IoT Scheduler 相关配置、处理器与必要测试，不修改 `uni_modules/**`。

## 对应技能

- `00-0600-deployment-architecture-management`
- `00-1000-server-deployment-standards`
- `30-0200-story-technical-design`
- `20-0200-acceptance-standards-documentation`

## 交付物

- `040-程序设计/[程序设计]PD-068-20260828-DEV-068-测试环境关闭异常IoT-Quartz.md`
- `061-验收标准/00-验收标准索引.md`
- `061-验收标准/01-验收执行详情/AC-IOT-QUARTZ-001.md`
- `061-验收标准/01-验收执行详情/AC-IOT-QUARTZ-101.md`
- `061-验收标准/01-验收执行详情/AC-IOT-QUARTZ-201.md`
- `061-验收标准/01-验收执行详情/AC-IOT-QUARTZ-301.md`
- 测试环境部署、重启、健康检查与线程检查记录

## 分支安排详情

- 当前版本代码现场模式：`复杂模式`
- 当前实际代码目录：`code/develop/`
- 当前实际工作分支：`feature/20260601000000-vphase1-initial-delivery`
- 不回退并行改动，不触碰 `uni_modules/**`
- 仅围绕 `yunjikeji-admin-server` 的 IoT Scheduler 开关和测试环境部署链路推进

## 关联验收项

- 业务验收：`AC-IOT-QUARTZ-001`
- 技术验收：`AC-IOT-QUARTZ-101`、`AC-IOT-QUARTZ-201`、`AC-IOT-QUARTZ-301`

## 任务产出 / 结果记录

- 2026-08-28 已确认测试服正式入口为 `TEST-3DAPP-MICRO-01`，正式连接为 `ssh test-3dapp`，管理端后端端口为 `18081`。
- 2026-08-28 已确认异常仅为 IoT 独立 scheduler `iotScheduler`，当前设计要求通过测试 profile 配置开关关闭，并在关闭时对场景规则定时入口安全 no-op。
- 2026-08-28 已建立 DEV-068 的正式计划、程序设计与验收标准入口，后续实施必须先按正式入口重建部署，再做健康与线程验证。

## 进度总结

- 当前状态：进行中。
- 当前阶段：计划、程序设计与验收标准已建立，等待实施、部署和测试环境复核。
- 当前结论：只关闭 IoT TIMER 的独立 scheduler，不扩大到全局 Quartz 或其他调度。
