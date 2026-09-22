# AC-ANSWERBG-101 六色精确映射与结构保持

- 类型：技术-代码级
- 正式入口：`code/develop/yunjikeji/src/pages/practice/answer.vue`。
- 支撑的业务结果：答题页主背景切换为登录页暖色，同时 DEV-038 页面和业务能力零结构回归。
- 技术边界：只允许末尾覆盖规则三行六个颜色字面量变化；禁止增加色标，禁止修改前部旧蓝色规则、其他颜色、选择器、结构、逻辑、素材或其他应用文件。
- 通过条件：精确映射计数与全文件归一化比较返回 `COLOR_MAP_ONLY=1`、`STRUCTURE_PRESERVED=1`；`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 和 Playwright 三档均 exit `0`。
- 证据承接：`061-验收标准/03-测试验证/DEV-039/`。

- 当前状态：已通过（独立验收）。
- 独立验收结果：`COLOR_MAP_ONLY=1`、`STRUCTURE_PRESERVED=1`、`exactExpectedMatch=true`，仅三行六色变化且无第五色标；类型检查、H5 构建、差异检查与 Playwright 三档均 exit `0`。
