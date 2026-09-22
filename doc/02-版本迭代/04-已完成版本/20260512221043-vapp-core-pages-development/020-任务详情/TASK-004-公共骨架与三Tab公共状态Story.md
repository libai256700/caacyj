# TASK-004 公共骨架与三 Tab 公共状态 Story

## 实施标准

1. 本 Story 只作为“公共骨架与三 Tab 公共状态”正式任务容器，实际执行以“Story 子任务清单”为准。
2. 每个子任务最多只绑定 1 个主技能，不得在单子任务内混绑多个主技能。
3. 未完成前置子任务前，不得推进后续实现、测试或回写动作。
4. 历史同类实现记录只作为参考，不直接视为当前 Story 已完成。

## 对应技能

- `30-0100-development-task-breakdown`

## 交付物

- 公共骨架 Story 子任务清单
- 三 Tab 公共状态交付边界
- Story 结果回写入口

## 分支安排详情

- 沿用当前版本真实代码现场；执行阶段按子任务需要创建或沿用版本分支，本 Story 汇总层不预设多分支。

## 关联验收项

- `AA-004 公共骨架与三 Tab 公共状态 Story 验收通过`

## Story 子任务清单

| 子任务 ID | 子任务名称 | 主技能 | 前置子任务 | 交付物 |
| --- | --- | --- | --- | --- |
| `TASK-004-01` | 复核公共骨架设计输入与页面边界 | `20-0100-requirements-documentation` | `-` | 公共骨架范围说明 |
| `TASK-004-02` | 输出公共路由、Tab 关系与共享状态程序设计 | `30-0200-story-technical-design` | `TASK-004-01` | 公共骨架程序设计 |
| `TASK-004-03` | 补充公共骨架正式验收项 | `20-0200-acceptance-standards-documentation` | `TASK-004-02` | 公共骨架验收项引用 |
| `TASK-004-04` | 实现 tabBar 与正式页面注册骨架 | `00-1600-frontend-ui-implementation` | `TASK-004-03` | 页面注册与 tabBar 配置 |
| `TASK-004-05` | 实现全局视觉变量与背景资源映射 | `00-1600-frontend-ui-implementation` | `TASK-004-04` | 全局样式变量与背景资源入口 |
| `TASK-004-06` | 实现公共导航容器与页面通用骨架 | `00-1600-frontend-ui-implementation` | `TASK-004-05` | 公共容器组件 |
| `TASK-004-07` | 实现三 Tab 共享状态模型 | `00-1600-frontend-ui-implementation` | `TASK-004-06` | 共享状态模型与读取入口 |
| `TASK-004-08` | 实现公共加载态、空态、异常态组件 | `00-1600-frontend-ui-implementation` | `TASK-004-07` | 公共状态组件 |
| `TASK-004-09` | 实现登录态与用户基础信息公共缓存 | `00-1600-frontend-ui-implementation` | `TASK-004-08` | 登录态缓存入口 |
| `TASK-004-10` | 完成 uni-app 骨架页面冒烟验证 | `40-0200-uniapp-cli-run-and-automation` | `TASK-004-09` | 骨架页面运行结果 |
| `TASK-004-11` | 回写公共骨架 Story 人工测试结论 | `40-0100-project-testing` | `TASK-004-10` | Story 人工测试记录 |

## 任务产出 / 结果记录

- `2026-05-13`：本文件已按“单页单 Story / 每个 Story 至少 10 个子任务 / 每个子任务仅 1 个主技能”重写。
- 历史“页面实现方案与公共骨架”记录降级为参考，不再直接作为当前 Story 完成依据。
- `2026-05-13`：实施代理已完成公共骨架、三 Tab 共享状态、页面注册、公共组件与六页面骨架落位，并提交推送 `66cc5186c2059cfc30667fe728c9155f0436887e`。
- `2026-05-13`：独立验收代理已验证 `npm run type-check`、`npm run build:h5` 通过，允许主代理回写完成。

## 进度总结

- `已完成`

## TASK-004 最小收口留痕

- `2026-05-13`：完成公共骨架与三 Tab 公共状态前端代码收口验证；`npm run type-check` 通过，`npm run build:h5` 通过。
- 已确认本次收口范围限制在前端骨架目标文件与本任务详情文件；不包含后端目录，不包含 `uni_modules/**`。
