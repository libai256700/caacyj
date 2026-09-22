# AC-PROFILETAB-101 代码白名单

- 类型：技术-代码级
- 正式入口：新增共享组件及 `home.vue`、`profile.vue`。
- 支撑结果：以最小应用边界完成共享底栏和暖色背景。
- 技术边界：禁止修改 `AppDynamicTabBar.vue`、`appState.ts`、登录页、`pages.json`、其他五个动态底栏页面和 `uni_modules/**`。
- 通过条件：排除实施前 DEV-040 差异后，范围外应用差异摘要与实施前一致；暂存区保持为空。
- 证据承接：源码契约、Git 白名单与 `uni_modules` 审计。
