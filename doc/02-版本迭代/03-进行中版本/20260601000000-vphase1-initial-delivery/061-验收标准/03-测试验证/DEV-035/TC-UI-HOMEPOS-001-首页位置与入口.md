# TC-UI-HOMEPOS-001 首页位置与入口

- 对应验收项：`AC-HOMEPOS-001`、`AC-HOMEPOS-002`、`AC-HOMEPOS-003`、`AC-HOMEPOS-101`
- 页面入口：`http://127.0.0.1:5173/yunjikeji/#/pages/home`
- 位置基线：`../DEV-033/playwright-results.json`
- 暖色基线：`../DEV-034/playwright-results.json`
- 自动化脚本：`dev035-home-position.spec.cjs`

## 首轮失败与关闭

- 首轮：三档assistant/suggestions/ask均提前`62px`，脚本退出码`1`，视觉`88/revise`。
- 最小返工：create-panel常规`32→94px`、小屏`29→91px`，只增加原快捷栏`62px`布局高度。
- 最终：三档五个DEV-033基线delta全部为`0`，脚本退出码`0`，首轮失败关闭。

## 最终重测结果

- Chrome DevTools：reward/status/quick相关DOM、目标精确文本和幽灵内容均为`0`；390坐标`166/465/663/708`完全匹配。
- Playwright：360的assistant/suggestions/ask为`443/641/686`；390与430为`465/663/708`；create和Tony基线继续匹配。
- 暖色、欢迎/Tony重叠`0`、无横向溢出、console/page/request错误`0`。
- 默认四项与enterprise客服路由全部通过，客服均进入实时聊天页。
- 视觉：`97/pass`。
- 质量：`pnpm type-check`、`pnpm run build:h5`、`git diff --check`均退出码`0`。

## 重跑入口

在APP目录执行`pnpm exec node <DEV-035>/dev035-home-position.spec.cjs`；当前最终退出码为`0`。

## 测试边界

- 最终重测已补齐质量命令和边界检查。
- 本验收代理只创建DEV-035失败证据，未修改应用实现、计划或验收标准定义。
