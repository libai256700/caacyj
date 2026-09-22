# DEV-040 APP新首页正式业务接入

## 实施标准

- 冷启动兼容入口：无会话进入启动首屏或受保护页时跳转登录；学员有效会话进入 `/pages/home`，企业有效会话进入改版前企业端入口 `/pages/service/customer-service`。
- 登录成功分流：企业已具备岗位或审核通过时默认进入 `/pages/service/customer-service`，企业待审/未注册继续进入 review/register；学员未绑定/驳回继续进入 organization-bind，学员审核通过进入 `/pages/home`；合法 `redirectUrl` 保持优先。
- 新首页接入：`home.vue` 保留既有 `requireLogin()` 门禁并在 `onLoad`、`onShow` 检查会话；企业身份误入时立即转回企业端入口，任何时候不得渲染学员自测、题库训练或错题练习模块；学员首页视觉和真实入口保持不变。
- 练习链路：`home -> exam-assessment -> answer` 参数保持不变；测评返回首页；答题有栈正常返回测评，无栈回退测评；完成练习后 `reLaunch('/pages/home')`；退出登录仍回登录页。
- 控件条件：测评与答题的 loading/empty/error、题型、题序、提交中、结果、AI、完成条件不变；远端短信发码、60 秒倒计时与 `loginLoading/codeCountdown` 互斥在后续干净集成时必须保留。
- 验证码登录契约：学员、企业 `login-or-register` 的 JSON 请求统一为 `mobile + code`；`code` 必须是 6 位数字，并由后台按 `MEMBER_LOGIN` 场景消费，不接受或发送以 `password` 字段承载的验证码。
- 已有账号登录：验证码消费通过后，不查询、恢复或重放账号密码，不执行 `passwordEncoder.matches`；学员、企业均直接复用原密码校验成功后的状态校验、Token、登录记录、refresh/me、审核、岗位及 tenant 流程。
- 无账号注册：服务器生成至少 128-bit 等价熵的不可预测随机初始密码，经 `passwordEncoder` 哈希后落库；不得使用验证码、手机号或固定值，不得在响应或日志中输出随机密码；注册后进入与已有账号相同的登录后流程。
- 页面边界：前端只提交手机号和验证码；登录页模板、CSS 和布局保持零变化，接口 URL、响应契约、审核/tenant/redirect/首页路由不变。
- 短信存储门禁：以远端提交 `1f50accd606d459a2008081e88604cc5107f866c` 为事实源，发送端必须经 `AppAuthController -> MemberAuthServiceImpl -> SmsCodeApiImpl -> SmsCodeServiceImpl` 写入 `system_sms_code`，消费端必须经同一 `SmsCodeServiceImpl` 按 `mobile + code + MEMBER_LOGIN` 读取同表；保存先于发送，保存字段及过期计算、发送异常一致性均纳入证据。

## 对应技能

- `10-0400-version-detailed-plan-creation`
- `20-0200-acceptance-standards-documentation`
- `00-1600-frontend-ui-implementation`
- `40-0100-project-testing`

## 交付物

- 四个应用白名单文件中的最小路由与登录门禁改动。
- `AC-PAGEROUTE-001` 至 `AC-PAGEROUTE-201` 正式验收入口。
- `061-验收标准/03-测试验证/DEV-040/` 下的 Playwright 路由/条件验证、源码边界审计与质量命令结果。
- `061-验收标准/03-测试验证/DEV-040/` 下的验证码登录契约红绿源码检查，覆盖两套 DTO、两套 service 和前端 payload。

## 分支安排详情

- 沿用当前版本实际分支 `feature/20260601000000-vphase1-initial-delivery`。
- 当前主工作区保留既有用户脏改，不执行 pull、rebase、merge、stash、reset 或 checkout。
- 本轮只推进到待独立验收，不暂存、不提交、不推送；后续在干净远端集成现场保留 `1f50accd` 的短信登录实现。

## 关联验收项

- 业务验收：`AC-PAGEROUTE-001`、`AC-PAGEROUTE-002`、`AC-PAGEROUTE-003`、`AC-PAGEROUTE-004`、`AC-PAGEROUTE-005`
- 技术验收：`AC-PAGEROUTE-101`、`AC-PAGEROUTE-102`
- 闭环项：`AC-PAGEROUTE-201`
- 验证码契约与登录后业务保持由 `AC-PAGEROUTE-005` 承接；随机初始密码、后端认证边界和登录页视觉零变化由 `AC-PAGEROUTE-101` 承接。

## 任务产出 / 结果记录

- 2026-07-19 已将学员/企业 `login-or-register` 契约正式收口为 `mobile + code`；两套 DTO、service 和 `customerAuth.ts` 不再以 `password` 承载验证码，已有账号直接进入各自既有登录后流程。
- 学员/企业无账号分支均使用 JDK `SecureRandom` 生成 32 字节（256-bit）随机初始密码，经 URL-safe Base64 后交给现有 `passwordEncoder`；随机字节仅存于局部作用域并在 `finally` 清零，响应和日志均不承载随机值。
- `verify_code_login_contract.py` 红态记录契约/随机密码 10 项失败、短信存储链 4 项通过；实施后 16/16 项通过。`pnpm type-check` exit `0`；Maven 39/39 模块编译成功；`git diff --check`、冲突、`uni_modules/**` 与白名单审计通过。
- 远端事实源：`git fetch origin` 后短信提交为 `1f50accd606d459a2008081e88604cc5107f866c`，远端最新为 `51e38828`；当前工作树在本轮实施前的五个认证文件与短信提交一致。
- 2026-07-18 已建立 DEV-040 主计划、任务详情、任务索引与八条正式验收入口。
- 已完成四个应用白名单文件的最小门禁/路由实现，模板、样式、业务参数与条件表达式未变化。
- 实施前红态断言已记录；修复后 Playwright 路由链路、`pnpm type-check`、`pnpm run build:h5`、`git diff --check` 均 exit `0`。
- 应用差异仅包含登录页 3 个默认路由、首页 2 个生命周期门禁、兼容页 1 个有会话路由和答题页 2 个返回/完成路由；指定禁改目标差异为 `0`。
- 远端 `51e38828` 登录页的 `sendLoginSmsCode`、60 秒倒计时、倒计时/登录加载互斥和禁用绑定均存在；真实账号联调保留用户复验。

## 2026-08-15 企业端默认入口回归修正

- 用户复验确认企业账号登录后错误显示学员首页；该结果不符合企业端既有业务入口。
- 根因是 `daf685d0` 将企业 `hasWtPost=true` 与 `auditStatus=2` 的默认落点从 `/pages/service/customer-service` 改为 `/pages/home`，并被原 `DEV-040` 错误验收口径承接。
- 本轮以用户最新要求修正正式口径：学员正常登录进入学员首页，企业正常登录恢复改版前企业端页面；企业审核和注册分流保持不变。

## 进度总结

- 当前状态：待测试环境验收。
- 当前结论：企业正常登录默认入口已恢复 `/pages/service/customer-service`，企业误入 `/pages/home` 时在学员内容和接口请求前完成身份拦截；聚焦 Playwright、类型检查、H5 构建和边界审计通过。测试服务器尚未部署，真实企业/学员账号端到端验证未完成，`AC-PAGEROUTE-201` 保持未完成。
