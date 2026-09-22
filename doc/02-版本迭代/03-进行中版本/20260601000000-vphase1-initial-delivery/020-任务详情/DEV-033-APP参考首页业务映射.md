# DEV-033 APP参考首页业务映射

## 实施标准

- 真实首页 `src/pages/home.vue` 严格复用已确认 `home-reference-preview.vue` 的蓝色体系、页面几何、边缘、边距、卡片配图、状态栏、欢迎区、快捷入口、建议区和底部输入区，不重新设计布局。
- 只做以下文案映射：`AI创作` 改为 `考题测试`；`小红书创作` 改为 `考题自测`；`抖音创作` 改为 `考题测评`；`朋友圈创作` 改为 `错题测评`；`智能助理` 改为 `常用功能`；`开单收银` 改为 `岗位查询`；`预约查询` 改为 `联系客服`；`添加顾客` 改为 `个人资料`。
- 三个常用功能必须接入真实入口：岗位查询进入招聘页；联系客服按当前用户身份进入企业客服页或学员客服会话页；个人资料进入“我的”页。
- 底栏删除“学习”和“练口语”，只保留等宽的“首页 / AI助手 / 我的”；中间 AI 助手使用 `src/static/brand/jixiangwu-logo.png` 并保持参考页悬浮结构。
- 独立参考页 `src/pages/home-reference-preview.vue` 及其专用素材保持不变，继续作为可直接访问的回退对照页。
- 正式视口为 `360x800`、`390x844`、`430x932`，视觉门禁为 `95/pass`。

## 对应技能

- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`
- `visual-verdict`

## 交付物

- 完成业务映射的真实首页。
- 三档截图、导航验证、质量命令和视觉判定证据。

## 分支安排详情

- 沿用 `feature/20260601000000-vphase1-initial-delivery`。
- 实施白名单：`code/develop/yunjikeji/src/pages/home.vue`、`DEV-033` 正式计划与测试证据。
- 禁止修改 `home-reference-preview.vue`、旧 `pages/index.vue`、登录页、业务服务和 `uni_modules/**`。

## 关联验收项

- 业务验收：`AC-HOMEMAP-001`、`AC-HOMEMAP-002`、`AC-HOMEMAP-003`
- 技术验收：`AC-HOMEMAP-101`、`AC-HOMEMAP-102`
- 闭环项：`AC-HOMEMAP-201`

## 任务产出 / 结果记录

- 2026-07-18 用户明确确认参考预览页布局，要求保持布局不变并按指定文案与真实入口映射到首页。
- 实施仅修改 `code/develop/yunjikeji/src/pages/home.vue`；独立参考页、旧首页、登录页、业务服务和 `uni_modules/**` 无本任务差异。
- 独立验收在 Chrome DevTools `390x844` 与 Playwright `360x800`、`390x844`、`430x932` 完成；视觉判定 `98/pass`，三档关键盒模型 `geometryDiffs=[]`，默认八条路由与企业客服分流全部通过。
- `pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均退出码 `0`；证据位于 `061-验收标准/03-测试验证/DEV-033/`。

## 进度总结

- 当前状态：已完成。
- 当前结论：`AC-HOMEMAP-001` 至 `AC-HOMEMAP-201` 全部通过，无未关闭缺陷；功能与正式证据提交 `b1d65089` 已推送到 `origin/feature/20260601000000-vphase1-initial-delivery`。
