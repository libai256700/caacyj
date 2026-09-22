# AC-EXAMBG-101 四色值最小代码边界

- 类型：技术-代码级
- 正式入口：`code/develop/yunjikeji/src/pages/practice/exam-assessment.vue`。
- 支撑的业务结果：考题测评页背景与登录页/首页暖色基值一致，同时不引入布局或业务回归。
- 技术边界：只允许两行中的四个颜色字面量按正式映射变化；渐变函数、方向、三个色标、透明度、背景图片、选择器及其余源码不变。
- 通过条件：源码 diff 只出现四个目标色值替换；`pnpm type-check`、`pnpm run build:h5` 和 `git diff --check` 均退出码 `0`。
- 证据承接：`061-验收标准/03-测试验证/DEV-037/`。

- 当前状态：已通过。
- 独立验收结果：`COLOR_MAP_ONLY=1`、`STRUCTURE_PRESERVED=1`；`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均退出码 `0`。
- 证据：`../03-测试验证/DEV-037/command-results.md`、`../03-测试验证/DEV-037/playwright-results.json`。
