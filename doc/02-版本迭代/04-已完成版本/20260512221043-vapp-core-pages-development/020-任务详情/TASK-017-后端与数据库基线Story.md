# TASK-017 后端与数据库基线 Story

## 实施标准

1. 本 Story 只作为“后端与数据库基线”正式任务容器，实际执行以“Story 子任务清单”为准。
2. 每个子任务最多只绑定 1 个主技能，不得在单子任务内混绑多个主技能。
3. 后端与数据库基线 Story 必须覆盖后端工程基线、配置分层、数据库规范、脚本资产、测试库验证与结果回写。
4. 历史后端初始化记录只作为参考，不直接视为当前 Story 已完成。

## 对应技能

- `30-0100-development-task-breakdown`

## 交付物

- 后端与数据库基线 Story 子任务清单
- 工程与库表基线交付边界
- Story 结果回写入口

## 分支安排详情

- 沿用当前版本真实代码现场；执行阶段按子任务需要创建或沿用版本分支，本 Story 汇总层不预设多分支。

## 关联验收项

- `AA-017 后端与数据库基线 Story 验收通过`

## Story 子任务清单

| 子任务 ID | 子任务名称 | 主技能 | 前置子任务 | 交付物 |
| --- | --- | --- | --- | --- |
| `TASK-017-01` | 复核后端基线范围与服务边界 | `20-0100-requirements-documentation` | `-` | 后端基线范围说明 |
| `TASK-017-02` | 输出后端目录、模块与分层程序设计 | `30-0200-story-technical-design` | `TASK-017-01` | 后端程序设计 |
| `TASK-017-03` | 输出通用接口约定与错误码设计 | `30-0200-story-technical-design` | `TASK-017-02` | 通用接口契约 |
| `TASK-017-04` | 定义核心库表命名、约束与索引基线 | `00-0300-database-standards-definition` | `TASK-017-03` | 数据库基线规范 |
| `TASK-017-05` | 规划版本数据库资产目录与表清单 | `30-0500-database-management` | `TASK-017-04` | 数据库资产清单 |
| `TASK-017-06` | 编写首批 DDL 脚本并固化执行口径 | `00-0350-sql-script-standards-definition` | `TASK-017-05` | DDL 脚本与执行说明 |
| `TASK-017-07` | 核对测试库连接正式入口 | `00-0400-application-connection-management` | `TASK-017-06` | 测试库连接入口记录 |
| `TASK-017-08` | 完成后端工程基础骨架与 profile 分层 | `00-0900-project-template-management` | `TASK-017-07` | 后端基础工程 |
| `TASK-017-09` | 完成健康检查、统一响应与鉴权骨架 | `00-0900-project-template-management` | `TASK-017-08` | 后端公共能力骨架 |
| `TASK-017-10` | 完成测试库执行与启动验证 | `40-0100-project-testing` | `TASK-017-09` | 启动与测试库验证结果 |
| `TASK-017-11` | 回写后端与数据库基线 Story 人工测试结论 | `40-0100-project-testing` | `TASK-017-10` | Story 人工测试结论 |

## 任务产出 / 结果记录

- `2026-05-13`：本文件已重写为“后端与数据库基线 Story”。
- 历史后端初始化与配置注入记录降级为参考，不再直接作为当前 Story 完成依据。
- `2026-05-13`：轮次三补齐首批数据库脚本资产入口：`050-执行脚本/TASK-017/README.md`、`001-baseline-ddl.sql`、`database-assets.md`。
- `2026-05-13`：轮次三复跑 `mvn test` 通过，4 tests / 0 failures / 0 errors / BUILD SUCCESS。
- `2026-05-13`：实施代理已提交推送 `ee785828a915877a06551a5a0f7e1799abf3c5bf`，独立验收代理确认脚本资产、后端文件与测试结果通过，允许主代理回写完成。

## 进度总结

- `已完成`
