# AC-HOMEPOS-003 指定真实页面导航

- 类型：业务-交互级
- 前置条件：真实首页已加载并可拦截/记录 uni-app 导航调用。
- 触发动作：依次点击考题自测、岗位查询、联系客服、个人资料。
- 期望结果：目标依次为 `/pages/center`、`/pages/jobs`、`/pages/service/customer-service-chat?conversationId=default`、`/pages/profile`；联系客服不再根据企业身份改走其他页面。
- 核对方式：Chrome DevTools 与 Playwright 实际点击/导航调用记录。
