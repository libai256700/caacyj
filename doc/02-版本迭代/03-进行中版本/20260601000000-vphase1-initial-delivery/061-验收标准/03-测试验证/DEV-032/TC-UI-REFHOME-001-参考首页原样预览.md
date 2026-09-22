# TC-UI-REFHOME-001 参考首页原样预览

- 对应验收项：`AC-REFHOME-001`、`AC-REFHOME-101`、`AC-REFHOME-201`
- 页面入口：`http://127.0.0.1:5173/yunjikeji/#/pages/home-reference-preview`
- 自动化脚本：`dev032-reference-home.spec.cjs`
- 执行命令：在 `code/develop/yunjikeji` 执行 `pnpm exec node <DEV-032绝对路径>/dev032-reference-home.spec.cjs`
- 正式视口：`360x800`、`390x844`、`430x932`

## 验证范围

1. 状态栏、打卡、273、关闭按钮、欢迎标题、副标题和 Tony 机器人完整可见。
2. AI 创作白面板包含左大右二三卡和五个快捷入口，原蓝色与原文案保持不变。
3. 智能助理包含三卡、两个建议按钮和底部输入框。
4. 五入口底栏等分，中间蓝色 AI 助手上浮且无遮挡。
5. 五张专用素材加载成功，页面使用真实 DOM 文本和卡片结构，不以整张截图作为背景。
6. 三档无横向溢出、资源失败、控制台错误、文字缺失或元素裁切。
7. 当前首页、旧首页、共享底栏、登录页和 `uni_modules/**` 无 DEV-032 差异。

## 返工复验结果

- Playwright：退出码 `0`，三档 `allPassed=true`。
- `390x844`、`430x932`：创作面板高度 `289px`；智能助理到建议按钮间距 `10px`。
- `360x800`：创作面板高度 `278px`；连续流间距 `10px`。
- 三档底栏五等分宽差均为 `0.015625px`；悬浮助手外径 `62px`，相对底栏上浮 `26px`。
- 三档图片数均为 `5` 且全部加载；页面文本长度 `277`，缺失文案为 `0`。
- 三档 `scrollWidth === clientWidth`；console error 与 failed request 均为 `0`。
- 目视结论：机器人软边无矩形硬边；三类创作素材已融合，朋友圈素材不再侵入标题；底栏助手比例接近参考图。
- 视觉判定：`95/pass`。

## 质量与边界

- `pnpm type-check`：退出码 `0`。
- `pnpm run build:h5`：退出码 `0`，输出 `DONE Build complete.`。
- `git diff --check`：退出码 `0`。
- `home.vue`、`index.vue`、`AppDynamicTabBar.vue`、`auth/login.vue`、`uni_modules/**`：无工作区或暂存区差异。
- 工作区既有 `services/**` 差异不属于 DEV-032，本轮未修改、未暂存。
- Chrome DevTools MCP 因同一 `chrome-profile` 被其他调试会话占用而无法接管；已两次重试并记录原始错误，浏览器 DOM、console 和资源检查由正式 Playwright 脚本完成。
