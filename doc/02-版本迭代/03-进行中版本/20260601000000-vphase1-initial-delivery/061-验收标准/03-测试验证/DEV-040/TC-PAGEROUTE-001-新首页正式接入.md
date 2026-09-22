# TC-PAGEROUTE-001 新首页正式接入

- 对应验收项：`AC-PAGEROUTE-001`、`AC-PAGEROUTE-002`、`AC-PAGEROUTE-003`
- 测试层级：交互级 / 代码边界
- 前置条件：H5 服务监听 `5173`；Playwright 上下文使用确定性会话与练习接口夹具，不写入应用。
- 执行入口：`node dev040-page-routing.spec.cjs`
- 场景：无会话冷启动；企业正常登录默认入口；企业通过冷启动、缓存或历史链接误入学员首页；学员首页训练与三入口；答题有栈/无栈返回与完成；退出登录；待审、未注册、redirectUrl 优先级及 H5 预览身份分流源码边界。
- 预期：企业正常登录或误入 `/pages/home` 均进入 `/pages/service/customer-service`，且学员首页内容和练习请求均不出现；学员继续进入 `/pages/home` 并正常使用训练与导航；待审、未注册和合法 redirectUrl 分支不变。
- 真实账号边界：短信发送与真实账号登录仅做远端实现静态保留审计，真实联调保留用户复验。
