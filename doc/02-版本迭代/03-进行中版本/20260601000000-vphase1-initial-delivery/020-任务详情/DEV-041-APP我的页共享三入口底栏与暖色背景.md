# DEV-041：APP我的页共享三入口底栏与暖色背景

## 实施标准

- 从 `home.vue` 既有三入口底栏原样抽取 `HomeProfileTabBar.vue`，只增加 `active: 'home' | 'profile'` 与 `placement: 'absolute' | 'fixed'` 两个 props。
- 三个固定入口分别为 `/pages/home`、`/pages/center`、`/pages/profile`；active 项不跳，其他入口统一 `uni.reLaunch`。
- 首页仅以共享组件替换旧底栏 DOM 与专用样式；保留 DEV-040 的 `homeReady`、`requireLogin`、现有页面内容、事件和视觉。
- 我的页仅替换底栏组件与七个背景颜色字面量；业务数据、菜单、审核、角色、编辑、上传、退出、登录门禁和显示条件冻结。
- 禁止修改 `AppDynamicTabBar.vue`、`appState.ts`、登录页、`pages.json`、其他五个动态底栏页面和 `uni_modules/**`。

## 对应技能

- `10-0400-version-detailed-plan-creation`
- `20-0200-acceptance-standards-documentation`
- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`

## 交付物

- `src/components/HomeProfileTabBar.vue`
- `src/pages/home.vue`
- `src/pages/profile.vue`
- `061-验收标准/03-测试验证/DEV-041/verify_profile_tab_contract.py`
- DEV-041 正式计划、验收详情与测试记录。

## 分支安排详情

- 复用当前 `code/develop/yunjikeji` 现场，不建立新分支或 worktree。
- 当前工作树包含 DEV-040 未提交改动，DEV-041 必须行级保留并在差异审计中单独识别。

## 关联验收项

- `AC-PROFILETAB-001`、`AC-PROFILETAB-002`、`AC-PROFILETAB-003`
- `AC-PROFILEBG-001`
- `AC-PROFILETAB-101`、`AC-PROFILETAB-102`、`AC-PROFILETAB-201`

## 任务产出 / 结果记录

- 2026-07-19：正式计划、任务详情、索引、七项验收口径和源码契约入口已建立。
- 实施前基线：`home.vue` SHA-256 `a5a9caf2bdcf496693ba2d40e44164c830b7e9a7db397d86fb6ab4666794f990`；`profile.vue` SHA-256 `38daa8dda8e6f42feda73e4cf38f2d4d8f2ecdc5fdf2753e7474c034a5de11df`（统一 LF 后计算）。
- 红态：`python .../DEV-041/verify_profile_tab_contract.py` exit `1`；共享组件、两页引用、暖色映射检查失败，`home_frozen`、`profile_business_frozen`、`forbidden_app_diff_frozen` 均通过，证明失败原因只来自目标实现尚不存在。
- 绿态：同一契约 exit `0`，15 项检查全部通过；共享组件三项/三路由/active 防重复、视觉常量、两页单一引用、profile 动态底栏清除、七色映射、渐变结构、home/profile 冻结和范围外应用差异全部成立。
- `pnpm type-check` exit `0`；`pnpm run build:h5` exit `0`，32.5 秒完成，未复现 esbuild OS 故障。
- `git diff --check` exit `0`（仅工作树既有 LF/CRLF 提示）；冲突标记 `0`、暂存区 `0`、`uni_modules/**` 差异 `0`；`AppDynamicTabBar` 仍只由原五个页面引用。

## 进度总结

- 当前状态：待独立验收。
- 完成边界：实现、源码契约、静态检查、type-check 与 H5 构建已完成；Chrome DevTools 移动端运行验收由独立验收代理执行。不暂存、不提交、不推送。
