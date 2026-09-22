# DEV-039 APP答题页背景暖色基值替换

## 实施标准

- 应用文件仅修改 `code/develop/yunjikeji/src/pages/practice/answer.vue`。
- 精确映射：`#d5f8e4 -> #F5F0EA` 两处；`#fbffe1 -> #F7A16A`；`#eafbdc -> #EF7D3B`；渐变中的 `#d5f8e4 -> #F8DCC8`；`#bdf3f7 -> #F5F0EA`。
- 只允许末尾覆盖规则三行中的六个颜色字面量变化；`linear-gradient`、`180deg`、`0%/27%/61%/100%` 四个色标、选择器和所有其他源码完全不变。
- 不增加登录页第五色标 `#F3AD7B 36%`，不修改前部被覆盖的旧蓝色规则，不清理 CSS。
- 不修改进度蓝、题型标签、选中/正确/错误状态色、主次按钮、插画、页面结构或业务逻辑。
- 完成全文件结构归一化比较，证明 `COLOR_MAP_ONLY=1`、`STRUCTURE_PRESERVED=1`；执行 Playwright `360x800`、`390x844`、`430x932` 几何基线与 computed 背景验证，以及 `pnpm type-check`、`pnpm run build:h5`、`git diff --check`。

## 对应技能

- `10-0400-version-detailed-plan-creation`
- `20-0200-acceptance-standards-documentation`
- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`

## 交付物

- 完成精确暖色基值替换的真实答题页。
- `AC-ANSWERBG-001`、`AC-ANSWERBG-101`、`AC-ANSWERBG-201` 正式验收入口。
- `061-验收标准/03-测试验证/DEV-039/` 下的结构对比、Playwright 三档截图、结构化结果和命令结果。

## 分支安排详情

- 沿用当前版本实际分支。
- 应用源码白名单仅 `code/develop/yunjikeji/src/pages/practice/answer.vue`。
- 实施和独立验收通过后，仅提交 DEV-039 白名单文件并推送当前版本远程分支。

## 关联验收项

- 业务验收：`AC-ANSWERBG-001`
- 技术验收：`AC-ANSWERBG-101`
- 闭环项：`AC-ANSWERBG-201`

## 任务产出 / 结果记录

- 2026-07-18 已建立 DEV-039 主计划、任务详情、索引与正式验收入口。
- 2026-07-18 已完成 `answer.vue` 末尾覆盖规则三行六色精确映射，未增加第五色标，未修改旧蓝色规则或其他源码。
- 全文件归一化对比返回 `COLOR_MAP_ONLY=1`、`STRUCTURE_PRESERVED=1`，禁止第五色标计数为 `0`。
- Playwright 三档 computed 暖色和 DEV-038 关键矩形基线全部通过；`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均 exit `0`。
- 证据位于 `061-验收标准/03-测试验证/DEV-039/`。
- 功能与证据提交：`2687d5da87dfe8c096857379997ca5b5be793486`。
- 远端并发提交通过无冲突集成提交 `4215c171599bace9da3345b448c24ec02ddd0bf0` 合入，两个父提交均完整保留并已推送到 `origin/feature/20260601000000-vphase1-initial-delivery`。

## 进度总结

- 当前状态：已完成。
- 当前结论：独立验收已通过且无未关闭缺陷；`AC-ANSWERBG-001`、`AC-ANSWERBG-101`、`AC-ANSWERBG-201` 全部通过，功能与证据提交及远端集成推送均已闭环。
