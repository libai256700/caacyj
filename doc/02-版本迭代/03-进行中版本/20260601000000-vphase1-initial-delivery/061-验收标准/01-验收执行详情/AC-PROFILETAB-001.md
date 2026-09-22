# AC-PROFILETAB-001 我的页三入口底栏

- 类型：业务-交互级
- 业务起点：已登录用户进入 `/pages/profile`。
- 触发动作：查看并点击底栏三个入口。
- 业务终点：只显示首页、猫头鹰 AI助手、我的；我的 active 且点击不重复跳转，其他两项进入对应页面。
- 通过条件：DOM、`67px` 高度、三等分、active 红色、`62px` 猫头鹰环、白边和资产 `/static/brand/jixiangwu-logo.png` 与首页基线一致。
- 核对方式：源码契约与 Chrome DevTools 移动端运行验收。
