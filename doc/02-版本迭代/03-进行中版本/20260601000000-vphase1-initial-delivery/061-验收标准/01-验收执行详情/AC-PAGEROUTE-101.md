# AC-PAGEROUTE-101 代码边界与并发集成

- 类型：技术-代码级
- 正式入口：`src/pages/auth/login.vue`、`src/pages/home.vue`、`src/pages/index.vue`、`src/pages/practice/answer.vue`。
- 支撑结果：以最小路由和登录门禁改动完成新首页正式接入。
- 技术边界：不修改 `pages.json`、`exam-assessment.vue`、`AppDynamicTabBar.vue`、`appState.ts`、`services/**`、后端、锁文件、素材或 `uni_modules/**`。
- 通过条件：主工作区四文件差异仅包含指定路由/门禁；后续干净集成同时保留 `1f50accd` 短信登录与本地用户改动语义。
- 证据承接：应用白名单、结构化差异审计和后续远端集成检查。

## 验证码注册安全与代码边界补充

- 两套请求 VO 的登录凭证字段必须为 `code`，校验和 Schema 均明确 6 位短信验证码；`customerAuth.ts` 的两套登录函数参数及 payload 必须发送 `code`，验证码路径不得出现 `password` payload。
- 学员、企业无账号分支必须由服务器生成至少 128-bit 等价熵的不可预测随机初始密码，使用现有 `passwordEncoder` 哈希后落库；不得以验证码、手机号或固定值作为密码，不得返回或记录随机密码。
- 学员、企业已有账号分支不得执行密码查询、恢复、重放或 `passwordEncoder.matches`；两条链路复用各自既有的密码认证成功后流程，避免复制 Token、登录记录、审核、岗位及 tenant 步骤。
- 代码白名单扩展为两套请求 VO、`CustomerServiceImpl`、`CompanyAuditServiceImpl`、`src/services/customerAuth.ts`、必要的登录页局部变量/调用参数及 DEV-040 最小测试证据；不得修改登录页 template/style、接口 URL、响应契约、`uni_modules/**` 或范围外业务。
- 通过条件：DEV-040 源码契约脚本先红后绿；`pnpm type-check`、后端 Maven compile、`git diff --check`、冲突标记和白名单审计通过；真实短信与 Chrome 联调保留到用户重启后独立验收。
- 安全关注项：当前 `SmsCodeServiceImpl` 的并发消费原子性不在本轮修改范围；并发重放残余风险必须保留到独立验收和后续安全治理。
- 短信持久化证据：`system_sms_code` 保存 `mobile/code/scene/used`，`createTime` 由基础审计字段承接，过期时间按 `createTime + expireTimes` 动态计算；当前实现先插入后调用短信供应商，供应商发送失败可能遗留未使用记录，须作为异常一致性残余风险保留。

## 2026-07-18 独立验收结果

- 状态：通过（代码边界与并发集成口径）。
- 2026-07-19 证据：DEV-040 路由/门禁仍限于 `login.vue`、`home.vue`、`index.vue`、`answer.vue`；并发短信业务 7 文件与 `1f50accd` 的差异归属清楚，其中四个后端文件及 `customerAuth.ts` 与同事提交逐字一致。
- 视觉与配置：`login.vue` 相对 `HEAD 2687d5da` 保留模板、核心 class、背景、配图、尺寸、边距、响应式 CSS 和 `.login-hero`；`application.yaml` 仅合入短信范围键并保留任务前 DeepSeek/assessment 本地键。
- 白名单：未覆盖 `uni_modules/**`、锁文件、范围外页面或范围外后端；暂存区为空，`git diff --check` exit `0`。
