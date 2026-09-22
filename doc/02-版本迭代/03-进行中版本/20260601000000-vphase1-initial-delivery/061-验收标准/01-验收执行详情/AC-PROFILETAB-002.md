# AC-PROFILETAB-002 首页与我的页共享组件

- 类型：业务-交互级
- 业务起点：首页或我的页已渲染。
- 触发动作：点击非 active 底栏入口。
- 业务终点：首页、AI助手、我的分别 `reLaunch` 到 `/pages/home`、`/pages/center`、`/pages/profile`。
- 通过条件：两页各引用同一正式组件一次；首页 active 且视觉不变；`AppDynamicTabBar` 和其他五个页面不变。
- 核对方式：源码契约、差异审计与 Chrome DevTools 移动端运行验收。
