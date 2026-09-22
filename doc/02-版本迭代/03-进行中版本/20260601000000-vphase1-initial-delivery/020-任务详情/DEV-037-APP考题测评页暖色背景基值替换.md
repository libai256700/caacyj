# DEV-037 APP考题测评页暖色背景基值替换

## 实施标准

- 仅修改 `code/develop/yunjikeji/src/pages/practice/exam-assessment.vue` 的背景基色字面量。
- 精确映射：`#edf7ff` 替换为 `#F5F0EA`；`rgba(226,244,255,.94)` 替换为 `rgba(247,161,106,.94)`；`rgba(244,250,255,.92)` 替换为 `rgba(248,220,200,.92)`；`#f3f8fc` 替换为 `#F5F0EA`。
- `linear-gradient`、`180deg`、三个色标、`0%/58%/100%`、`.94/.92` 透明度、背景图片、选择器、尺寸、间距、布局、标签和按钮颜色全部保持不变。
- 不修改后端、services、center、锁文件、`uni_modules/**`、首页或登录页。
- 执行 `pnpm type-check`、`pnpm run build:h5` 与 `git diff --check`，并用只读 diff/rg 证明应用源码只发生四个目标颜色变化。

## 对应技能

- `10-0400-version-detailed-plan-creation`
- `20-0200-acceptance-standards-documentation`
- `00-1600-frontend-ui-implementation`

## 交付物

- 暖色背景基值替换后的考题测评页。
- `AC-EXAMBG-001`、`AC-EXAMBG-101`、`AC-EXAMBG-201` 正式验收入口。
- `061-验收标准/03-测试验证/DEV-037/` 自检证据。

## 分支安排详情

- 沿用 `feature/20260601000000-vphase1-initial-delivery`。
- 应用源码白名单仅限 `code/develop/yunjikeji/src/pages/practice/exam-assessment.vue`。
- 功能与证据提交 `1fc972ba` 已推送到 `origin/feature/20260601000000-vphase1-initial-delivery`。

## 关联验收项

- 业务验收：`AC-EXAMBG-001`
- 技术验收：`AC-EXAMBG-101`
- 闭环项：`AC-EXAMBG-201`

## 任务产出 / 结果记录

- 2026-07-18 已确认登录页与首页使用 `#F7A16A`、`#F8DCC8`、`#F5F0EA` 暖色基值，本任务只做四个目标颜色字面量的精确替换。
- 2026-07-18 已完成精确映射；应用源码 diff 仅两行四个颜色字面量，Node 归一化断言返回 `COLOR_MAP_ONLY=1`、`STRUCTURE_PRESERVED=1`。
- `pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均退出码 `0`。
- 首次 PowerShell 归一化只读断言因同一新色 `#F5F0EA` 对应两个不同旧值而错误使用全局反向替换，退出码 `1`；未修改源码，随后改为上下文精确映射并以 Node 断言通过。
- 自检证据位于 `061-验收标准/03-测试验证/DEV-037/`。
- 独立验收通过；白名单与禁改范围检查通过，功能与证据提交 `1fc972ba` 已推送。

## 进度总结

- 当前状态：已完成。
- 当前结论：`AC-EXAMBG-001`、`AC-EXAMBG-101`、`AC-EXAMBG-201` 全部通过；功能与证据提交 `1fc972ba` 已推送，DEV-037 已完成闭环。
