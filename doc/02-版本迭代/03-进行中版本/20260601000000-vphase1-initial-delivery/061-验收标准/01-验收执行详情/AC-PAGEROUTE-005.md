# AC-PAGEROUTE-005 页面控件条件与短信登录互斥保持

- 类型：业务-交互级
- 业务起点：用户处于登录、考题测评或答题页面的不同加载与结果状态。
- 触发动作：切换 loading、empty、error、题型、题序、提交中、结果、AI、完成、短信发码和倒计时状态。
- 关键交互：只改变目标导航，不改变任何控件条件表达式；短信发码期间保持 `loginLoading/codeCountdown` 互斥。
- 业务终点：各状态显示/隐藏与 DEV-040 实施前一致，远端短信按钮、60 秒倒计时和登录加载态全部保留。
- 结果承接：状态仍由现有响应式变量、接口结果和远端短信实现承接。
- 核对方式：Playwright 状态夹具、源码条件归一化对比及远端提交静态审计。

## 验证码 login-or-register 契约补充

- 学员、企业请求 JSON 均且仅以 `mobile + code` 承载登录凭证；`code` 为 6 位数字，前后端不得以 `password` 字段发送或接收验证码。
- 两条后台链路均先按 `MEMBER_LOGIN` 场景消费短信验证码，再按手机号查找账号。
- 已有账号不得读取或恢复密码，不得执行 `passwordEncoder.matches`；验证码通过后直接复用密码检查成功后的状态校验、Token、登录记录、refresh/me、审核、岗位与 tenant 流程。
- 无账号完成后台随机密码注册后，进入与已有账号相同的登录后流程；接口 URL、响应结构、审核/tenant/redirect/首页路由保持不变。
- 核对方式：DEV-040 可执行源码契约检查、前后端编译和重启后的 Chrome 真实联调；本轮源码实施不以真实短信或本地集成测试替代测试环境验收。
- 发送/消费一致性：以远端 `1f50accd606d459a2008081e88604cc5107f866c` 为事实源，发送端经 `AppAuthController -> MemberAuthServiceImpl -> SmsCodeApiImpl -> SmsCodeServiceImpl`，消费端经同一 API/Service；二者必须使用 `system_sms_code` 与 `MEMBER_LOGIN`，否则本项阻断。

## 2026-07-18 独立验收结果

- 状态：通过（代码与静态编译口径）。
- 2026-07-19 证据：当前工作树已合入 `sendLoginSmsCode`、60 秒倒计时、`codeCountdown/loginLoading` 双互斥、发送点击/禁用态/动态文案及 6 位验证码校验；登录加载态与倒计时不会并发触发发码。
- 回归：测评/答题模板和控件条件相对基线未变化；`pnpm type-check` exit `0`，后端 Maven 39/39 模块编译通过。
- 运行态边界：H5/Playwright 仍由 `AC-PAGEROUTE-102` 承接环境复验，不影响本项代码口径结论。
