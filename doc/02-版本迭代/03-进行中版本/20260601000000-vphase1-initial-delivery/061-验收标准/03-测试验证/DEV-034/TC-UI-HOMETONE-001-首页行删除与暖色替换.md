# TC-UI-HOMETONE-001 首页行删除与暖色替换

- 对应验收项：`AC-HOMETONE-001`、`AC-HOMETONE-002`、`AC-HOMETONE-101`
- 页面入口：`http://127.0.0.1:5173/yunjikeji/#/pages/home`
- 源码基线：`232fcf3a`
- 视觉基线：`../DEV-033/home-360x800.png`、`home-390x844.png`、`home-430x932.png`
- 自动化脚本：`dev034-home-tone.spec.cjs`
- 正式视口：`360x800`、`390x844`、`430x932`

## 验证范围

1. `.status-bar / .signal / .wifi / .battery` 和精确文本“5:30”全部不存在。
2. `.quick-row / .quick-item` 和五项快捷入口精确文本全部不存在。
3. 页面与外围背景均为 `#F5F0EA`，主背景精确为 `linear-gradient(180deg, #F7A16A 0, #F8DCC8 33%, #F5F0EA 76%)`。
4. 相对基线只删除目标DOM/死代码和CSS、收紧对应空间并替换颜色字面量。
5. 三张考题卡、三张常用功能卡、建议、输入框、三项底栏、五张图片和八项路由保持。
6. 三档无异常内部空白、重叠、机器人变形、卡片裁切、横向滚动或底栏遮挡。
7. 冻结预览页、参考素材、登录页、旧首页、服务和 `uni_modules/**` 不产生本任务差异。

## 执行结果

- Chrome DevTools：目标DOM和精确文本计数均为 `0`；背景计算值精确；三段连续间距为 `0/10/10px`；五图加载；首页资源与console error均无异常。
- Playwright：退出码 `0`，三档 `allPassed=true`。
- 基线几何：顶部缩短 `34px`；创作面板减少快捷栏原占用 `62px`；常用功能、建议和输入整体上移 `96px`；卡片与底栏尺寸不变。
- 机器人：360档缩放 `0.891/0.890`，390/430档缩放 `0.900/0.904`；比例差小于 `0.01`，底部裁切保持 `7px`。
- 三档：目标节点和文本均为 `0`，背景精确，横向溢出、console error、page error、failed request均为 `0`。
- 导航：八项调用与 `DEV-033` 基线一致。
- 视觉：`96/pass`。
- 质量：`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均退出码 `0`。

## 测试边界

- 接口级：不涉及后端接口变更；只回归前端导航调用。
- 数据级：不涉及数据库或业务数据变更。
- 交互级：Chrome DevTools 与 Playwright 均已执行。
- 服务文件存在任务前既有未提交差异，本验收代理未修改、未暂存，也未归入DEV-034。
- 本验收代理只创建DEV-034测试证据，未修改应用实现、计划或验收标准定义。
