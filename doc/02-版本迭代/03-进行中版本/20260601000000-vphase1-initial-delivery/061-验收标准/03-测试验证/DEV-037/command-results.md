# DEV-037 独立验收命令结果

## 运行态

- `node DEV-037/dev037-background-check.cjs`：退出码 `0`。
- Playwright：390x844 页面非空，`scrollWidth=390`，无横向溢出；5 个分类标签、确认卡和双按钮完整，console/page error 均为 `0`。
- 背景 computed style：外围 `rgb(245, 240, 234)`；渐变包含 `rgba(247, 161, 106, 0.94)`、`rgba(248, 220, 200, 0.92)` 和 `rgb(245, 240, 234)`，背景图片继续存在。
- 与 DEV-036 冷色基线对比：tab Y、两个按钮的 left/right/width/height、页面与 body scrollWidth 全部一致。

## 精确结构

- `COLOR_MAP_ONLY=1`。
- `STRUCTURE_PRESERVED=1`。
- 当前文件严格等于 `HEAD` 文件应用四项正式颜色映射后的结果。
- 新值计数：`#F5F0EA=2`，两个 rgba 新值各 `1`；四个旧值计数均为 `0`。
- `linear-gradient`、`180deg`、`.94 0%`、`.92 58%`、`100%` 和 `focus-atmosphere.png` 均保留。

## 质量命令

- `pnpm type-check`：退出码 `0`。
- `pnpm run build:h5`：退出码 `0`，输出 `DONE Build complete.`。
- `git diff --check`：退出码 `0`；仅有工作区既有 LF/CRLF 提示，无空白错误。
- `git diff --cached --name-only`：无输出，本轮未暂存。

## 边界

- DEV-037 应用 diff 仅 `src/pages/practice/exam-assessment.vue` 两行四个背景颜色字面量。
- 验收代理未修改应用、后端、services、center、锁文件或 `uni_modules/**`。
- `5173` 与 `6379` 保持运行。
