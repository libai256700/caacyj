# TC-ANSWERBG-001 答题页暖色背景与 DEV-038 几何基线

- 对应验收项：`AC-ANSWERBG-001`、`AC-ANSWERBG-101`
- 脚本入口：`dev039-answer-background.spec.cjs`
- 数据入口：脚本内确定性视觉夹具；只在 Playwright 上下文设置登录存储并拦截练习拉题接口，不写入产品源码。
- 几何基线：只读 `../DEV-038/playwright-results.json` 的三档单选布局数据。
- 视口：`360x800`、`390x844`、`430x932`
- 验证：computed `page/.answer-page` 背景为 `rgb(245, 240, 234)`；渐变依次为 `#F7A16A 0% / #EF7D3B 27% / #F8DCC8 61% / #F5F0EA 100%`；色标数量为 4；不含 `#F3AD7B 36%`；题卡、叠层、插画、操作区、主按钮和全部选项矩形与 DEV-038 基线偏差不超过 `0.05px`；无横向溢出和页面错误。
- 实际：2026-07-18 独立复跑脚本 exit `0`；三档 computed 四色、四个色标、非空、横向溢出和 DEV-038 几何基线全部通过，最大几何差 `0px`，console/page errors 均为 `0`，并重新生成 `answer-warm-*.png` 与 `playwright-results.json`。
- 当前结论：独立验收通过，等待提交闭环。
