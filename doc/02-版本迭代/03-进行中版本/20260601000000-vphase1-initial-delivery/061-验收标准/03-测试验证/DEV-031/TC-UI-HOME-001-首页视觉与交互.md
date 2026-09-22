# TC-UI-HOME-001 首页视觉与交互

## 2026-07-18 第二轮返工最终复验

- 结果：通过，`96/pass`。
- 自动化：`check-home-visual.mjs` 与 `check-home-page.mjs` 均退出码 `0`。
- 通过范围：三档截图、五卡多层插画、左大右二几何、三等分底栏、AI工作台标签、猫头鹰白环与上浮、真实导航、无溢出/裁切/console/page errors、顶部透明猫头鹰和质量命令。

## 2026-07-18 返工后独立复验

- 结果：未通过，`92/fail`。
- 自动化：`check-home-visual.mjs` 退出码 `0`；`check-home-page.mjs` 退出码 `1`。
- 已通过：三档新截图、完整五卡与多层插画、列比、等高、真实导航、无横向溢出/文字裁切/console/page errors、顶部透明猫头鹰和质量命令。
- 未通过：360 gap 与两张右卡插画面积、360/390 左右底栏字号、三档 AI工作台/猫头鹰重叠、430 猫头鹰白环尺寸。

## 2026-07-18 最新参考图返工复验

- 结果：未通过。
- 自动化：`check-home-visual.mjs` 退出码 `1`；`check-home-page.mjs` 退出码 `1`。
- 失败项：测评列宽比例、360 档 gap、左右卡高组合、常用功能插画可见面积、底栏“AI工作台”标签、猫头鹰裁切与顶部资产灰底。
- 视觉判定：`72/fail`，未达到 `95/pass`。
- 通过项：真实导航、无横向溢出、无 console/page errors、类型检查、H5 构建和 diff 检查。

- 执行时间：2026-07-18
- 环境：`http://127.0.0.1:5173/yunjikeji/`
- 自动化入口：`../05-自动化测试脚本/check-home-page.mjs`
- 结果：通过

## 覆盖范围

- `AC-HOME-001`：暖色登录页视觉基线、欢迎区、成对练习块和独立招聘块可见。
- `AC-HOME-002`：底部仅三个入口；首页、AI工作台和我的分别指向 `/pages/home`、`/pages/center`、`/pages/profile`。
- `AC-HOME-003`：`360x800`、`390x844`、`430x932` 下无横向溢出、无文字裁切，底栏固定。
- `AC-HOME-004`：客服块默认指向 `/pages/service/customer-service-chat?conversationId=default`；企业源码分支指向 `/pages/service/customer-service`。
- `AC-HOME-101`：新首页路由和全部导航 URL 已由 `uni.navigateTo` / `uni.reLaunch` 拦截验证。
- `AC-HOME-102`：页面无控制台错误或页面异常；`pnpm type-check` 退出码为 `0`。

## 证据

- `navigation-results.json`：三个视口均通过，结构为 3 个导航入口、2 个练习块、1 个招聘块、1 个客服块。
- `home-360x800.png`、`home-390x844.png`、`home-430x932.png`：最新三档截图。
- `visual-verdict.json`：`93/pass`。
