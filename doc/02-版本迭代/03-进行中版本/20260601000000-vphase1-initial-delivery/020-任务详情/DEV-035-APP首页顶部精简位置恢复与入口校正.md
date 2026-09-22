# DEV-035 APP首页顶部精简位置恢复与入口校正

## 实施标准

- 删除真实首页顶部的打卡胶囊、金币/积分胶囊和关闭 `X`，并清理仅服务它们的 DOM 与样式。
- 已删除的模拟系统状态栏、五项快捷入口继续保持不存在；暖色背景和渐变结构继续保持 `DEV-034` 结果。
- 纵向位置必须恢复到 `DEV-033` 删除前正式基线：常规视口 `.top-area=166px`、`.content-scroll=calc(100vh - 233px)`、机器人 `140x146px`；`<=370px` 视口 `.top-area=155px`、`.content-scroll=calc(100vh - 222px)`、机器人 `128x136px`。删除的顶部内容只隐藏显示，欢迎区、考题面板和后续内容不得上移。
- 考题自测进入 `/pages/center`；岗位查询进入 `/pages/jobs`；联系客服统一进入 `/pages/service/customer-service-chat?conversationId=default`，不再按企业身份分流到其他客服页；个人资料进入 `/pages/profile`。
- 除目标元素删除、纵向位置恢复、死代码清理和客服入口校正外，不得改变暖色背景、渐变、考题卡、常用功能、建议区、输入框、配图、其他文案、其他路由或三项底栏。
- 在 `360x800`、`390x844`、`430x932` 三档验证位置、显示和导航。

## 对应技能

- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`
- `visual-verdict`

## 交付物

- 最小范围首页结构、位置和路由补丁。
- 三档位置对比、点击导航、截图和质量命令证据。

## 分支安排详情

- 沿用 `feature/20260601000000-vphase1-initial-delivery`。
- 实施白名单：`code/develop/yunjikeji/src/pages/home.vue` 与 `DEV-035` 正式计划、验收、测试证据。
- 禁止修改 `home-reference-preview.vue`、登录页、旧首页、业务服务和 `uni_modules/**`。

## 关联验收项

- 业务验收：`AC-HOMEPOS-001`、`AC-HOMEPOS-002`、`AC-HOMEPOS-003`
- 技术验收：`AC-HOMEPOS-101`
- 闭环项：`AC-HOMEPOS-201`

## 任务产出 / 结果记录

- 2026-07-18 用户要求删除打卡、金币和 `X`，同时明确指出上轮删除状态栏后内容不应整体上移，须恢复原位置；并指定四项真实页面入口。
- 首轮独立验收：`AC-HOMEPOS-001`、`AC-HOMEPOS-003` 通过，`AC-HOMEPOS-002` 未通过；三档考题面板和机器人已恢复基线，但常用功能、建议和输入框统一比 `DEV-033` 提前 `62px`，原因是删除五项快捷栏时未保留其原占用高度。正式失败证据位于 `061-验收标准/03-测试验证/DEV-035/`。
- 最小返工仅将考题面板常规/小屏底部内边距分别调整为 `94px / 91px`，保留原快捷栏 `62px` 不可见布局高度；未恢复任何快捷 DOM、图标或文字。
- 独立重测 `97/pass`：三档考题面板、常用功能、建议和输入框相对 `DEV-033` 的五项位置差全部为 `0`；打卡、金币、X、状态栏和快捷栏计数均为 `0`，无可见幽灵内容。
- 考题自测、岗位查询、联系客服、个人资料分别命中 `/pages/center`、`/pages/jobs`、`/pages/service/customer-service-chat?conversationId=default`、`/pages/profile`；默认与企业身份客服目标一致。
- `pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均退出码 `0`；最终证据位于 `061-验收标准/03-测试验证/DEV-035/`。

## 进度总结

- 当前状态：已完成。
- 当前结论：`AC-HOMEPOS-001` 至 `AC-HOMEPOS-201` 全部通过，无未关闭缺陷；功能与正式证据提交 `2509fc66` 已推送到 `origin/feature/20260601000000-vphase1-initial-delivery`。
