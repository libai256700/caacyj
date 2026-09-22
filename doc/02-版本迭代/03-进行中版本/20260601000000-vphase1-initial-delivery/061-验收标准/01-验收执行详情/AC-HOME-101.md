# AC-HOME-101 新旧首页切换与导航入口契约

- 当前状态：待验收。
- 类型：技术-接口级
- 关联任务：`DEV-031`
- 正式入口：新首页 `code/develop/yunjikeji/src/pages/home.vue`；页面注册 `code/develop/yunjikeji/src/pages.json`；三入口目标为 `pages/home`、`pages/center`、`pages/profile`；客服目标为企业身份 `pages/service/customer-service`、其他身份 `pages/service/customer-service-chat?conversationId=default`。
- 支撑的业务结果：新首页可以独立访问和作为当前首页使用，底部三入口与客服联系入口均接入真实页面，出现问题时能够快速恢复旧首页。
- 技术边界：新首页使用新页面文件；旧首页文件不改；只通过最小页面注册或入口配置切换当前首页；导航只连接项目已有真实页面，不新增后端接口或伪造成功状态。
- 通过条件：新首页直接访问成功；首页、AI工作台、我的三个导航目标和客服联系目标均可用；恢复旧首页只需把 `pages/index` 恢复为 `src/pages.json` 首项，旧首页源码无本任务差异。
- 证据承接：页面配置差异、目标路径清单与浏览器导航结果回写 `../03-测试验证/DEV-031/`。
