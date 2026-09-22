# DEV-040 测试结论

## 验证码 login-or-register 契约与随机初始密码实施证据（2026-07-19）

- 远端事实源：`git fetch origin` exit `0`；远端最新为 `51e38828`，短信业务提交为 `1f50accd606d459a2008081e88604cc5107f866c`。实施前两套 DTO、两套 service 和 `customerAuth.ts` 与该短信提交逐字一致。
- 发送存储链：`AppAuthController.sendSmsCode -> MemberAuthServiceImpl.sendSmsCode -> SmsCodeApiImpl.sendSmsCode -> SmsCodeServiceImpl.sendSmsCode`；`SmsCodeServiceImpl` 先向 `system_sms_code` 插入记录，再调用短信供应商发送。记录保存 `mobile/code/scene/used`，`createTime` 由 `BaseDO` 审计字段承接，过期时间按 `createTime + expireTimes` 动态计算。
- 消费一致性：学员、企业均经 `SmsCodeApiImpl.useSmsCode -> SmsCodeServiceImpl.useSmsCode`，由 `SmsCodeMapper.selectLastByMobile` 按 `mobile + code + scene` 读取同一 `system_sms_code`；发送端和两消费端 scene 均为 `MEMBER_LOGIN(1)`。
- 请求契约：两套 Request VO 的凭证字段均为 `code`，Schema 与校验明确 6 位数字；`customerAuth.ts` 的学员/企业 `login-or-register` payload 均为 `mobile + code`，验证码路径不再发送 `password`。
- 认证流程：验证码消费后再按手机号查账号；已有账号不读取、恢复或匹配密码，直接复用原状态校验及共同的 Token、登录记录、refresh/me、审核、岗位、tenant 流程；无账号完成随机密码注册后进入同一共同尾部。
- 随机策略：学员、企业均使用 JDK `SecureRandom` 生成 32 字节（256-bit）随机值，经 URL-safe Base64 后直接交给现有 `passwordEncoder`；仅哈希落库，随机字节在局部 `finally` 清零，不进入响应或日志。
- 红态：`verify_code_login_contract.py` 生成 `code-login-contract-red.json`，结果 `FAIL`；DTO 字段、两套 service 的 code 使用/无密码读取/随机密码以及两套前端 payload 共 10 项失败，短信发送存储链 4 项通过。
- 绿态：同一脚本生成 `code-login-contract-green.json`，16/16 项 `PASS`。
- 质量命令：`pnpm type-check` exit `0`，耗时 `21.6s`；`mvn -pl yunjikeji-admin-server -am -DskipTests compile` exit `0`，39/39 模块 `SUCCESS`，总耗时 `01:56 min`；`git diff --check` exit `0`。
- 边界审计：本轮认证代码相对 `1f50accd` 仅变化两套 DTO、两套 service 和 `customerAuth.ts` 共 5 个白名单文件；`login.vue` 本轮未编辑，模板/style/布局变化为 `0`；冲突标记、index 冲突、`uni_modules/**` 工作区/暂存差异均为 `0`。
- 残余风险：当前保存先于供应商发送，供应商失败可能遗留调用方未知的未使用验证码记录；`useSmsCode` 的“查询未使用 -> 更新已使用”不是单条原子声明，并发重放风险不在本轮修改范围。
- 当前状态：实施、自检与编译通过，待独立验收；未运行真实短信或 Chrome 登录，未重启/停止后端、前端或 Redis，未暂存、提交或推送。

## 登录前短信发码租户拦截修复实施证据（2026-07-19）

- 缺陷现象：学员/企业共用的 `POST /app-api/member/auth/send-sms-code` 在登录前不会携带 `tenant-id`；原接口只有 `@PermitAll`，仍会在进入 Controller 前被 `TenantSecurityWebFilter` 以业务 `400` 拦截。
- 最小修复：仅在 `AppAuthController.sendSmsCode` 方法添加 `@TenantIgnore`；该 Controller 类级注解计数为 `0`，文件内方法级注解计数为 `1`，`smsLogin`、其他接口、前端请求和租户 ignore 配置均未扩大修改。
- 登录前链路：`sendLoginSmsCode` 继续无 `auth`、无 `headers` 地请求 `/app-api/member/auth/send-sms-code`；方法级 `@TenantIgnore` 只让该发码 URL 跳过租户过滤，不要求前端伪造 tenant。
- 登录链路：学员 `/app-api/yj/customer-auth/login-or-register` 与企业 `/app-api/yj/company-auth/login-or-register` 继续复用原密码登录业务链路，仅把原 `password` 入参承载的凭证改为短信验证码；两端 Controller 原有类级 `@TenantIgnore` 保持不变。企业登录返回租户信息后，既有 `refreshCompanyToken` 才按实际 `tenantId` 条件写入 `tenant-id` 请求头。
- 质量证据：`mvn -pl yunjikeji-admin-server -am -DskipTests compile` exit `0`，39/39 模块 `SUCCESS`，总耗时 `02:24 min`；最终 `git diff --check` exit `0`。
- 当前状态：实施与编译通过；未重启或停止后端、前端、Redis。编译产物可能被当前 devtools 自动重载，是否已进入运行进程须由独立验收通过 Chrome 真实无 tenant 请求确认，不据此提前宣称运行态通过。

## 历史独立验收（2026-07-18）

- 当时结论：未通过；无会话直达 `/pages/home` 时，首页内容先进入 DOM 后才跳登录。
- 历史证据：`independent-playwright-results.json` 保留该失败现场，不作为本轮修复后的通过证据。

## 短信合并冲突解决独立验收（2026-07-19）

- 当前结论：冲突解决通过，H5/Playwright 待环境复验。
- 登录业务：短信发送、6 位验证码、60 秒倒计时、`codeCountdown/loginLoading` 互斥、发送点击/禁用态/倒计时文案和验证码错误语义完整；企业与学员审核、注册、绑定分流顺序不变，`redirectUrl` 优先，三处正常无 redirect 均进入 `/pages/home`。
- 登录视觉：相对 `HEAD 2687d5da` 的模板骨架、核心 class、背景、配图、尺寸、边距和响应式 CSS 等价；`.login-hero` 保留；仅增加短信业务绑定及验证码发送禁用态样式。
- 后端与配置：四个后端文件及 `customerAuth.ts` 与同事提交 `1f50accd` 一致；两角色 6 位验证码校验、会员登录场景消费及短信发送 API 完整。`application.yaml` 仅合入短信验证码范围键，并保留任务前 DeepSeek/assessment 本地配置。
- DEV-040：`home.vue` 根节点已有 `v-if="homeReady"` 防闪现门禁；`home.vue`、`index.vue`、`answer.vue` 路由补丁保留；首页三入口和测评/答题控件条件未变。
- 质量命令：`pnpm type-check` exit `0`；`mvn -pl yunjikeji-admin-server -am -DskipTests compile` exit `0`，39/39 模块成功；`git diff --check` exit `0`。
- Git 与白名单：无活动 merge/rebase/cherry-pick；U 文件、stage 冲突、冲突标记和暂存文件均为 0；未覆盖 `uni_modules/**`、锁文件或范围外并发改动。
- 环境门禁：H5 构建未重复执行。既有证据已定位为操作系统级 esbuild 执行故障，原 binary 与 Temp 副本执行 `--version` 均超时；当前产物不能证明包含最新合并，因此 Playwright 未执行。
- 验收状态：`AC-PAGEROUTE-005`、`AC-PAGEROUTE-101` 按代码审计与后端编译通过；`AC-PAGEROUTE-102` 保持待验收；`AC-PAGEROUTE-201` 未完成。真实短信账号联调仍待用户复验。

## 企业端身份分流独立验收（2026-08-15）

- 当前结论：`DONE_WITH_CONCERNS`，未形成全量独立验收 PASS，不允许据此进入提交阶段。
- 已通过源码审计：相对 Gitee 基线 `4b97b39b391efe2dc5c099bba8a80388d05e026f`，应用代码仅修改 `login.vue` 与 `home.vue`；企业 H5 预览、`hasWtPost=true`、`auditStatus=2` 三个正常默认分支均指向 `/pages/service/customer-service`，合法 `redirectUrl` 仍优先；企业 review/register、学员审核/绑定/default 分支顺序未越界；`home.vue` 企业门禁位于 `homeReady=true` 和学员服务动态导入之前。
- 已通过独立 Playwright 运行态：企业有效会话访问历史 `/pages/home` 后进入 `#/pages/service/customer-service`；全过程未观察到“自我测评 / 题库训练 / 错题练习”学员 DOM，学员专属请求为 `[]`。无会话首页与兼容入口均进入登录页且未闪现学员内容。
- 未完成独立运行态：独立脚本在学员三入口旧断言处停止。当前激活态“首页”点击不会重复 `reLaunch`，实际仅 AI 助手和“我的”分别产生 `/pages/center`、`/pages/profile` 跳转；因此企业登录 `hasWtPost/auditStatus/H5 preview/redirect/review/register` 与学员登录审核/绑定分支尚未在本次独立浏览器进程中全部执行到。
- 质量命令：`pnpm type-check` exit `0`；`pnpm run build:h5` exit `0`，输出 `DONE Build complete`；`git diff --check` exit `0`；真实冲突标记为 `0`；`uni_modules/**` 工作区和暂存差异均为 `0`。
- 证据入口：`independent-source-audit.json` 为 `passed`；`independent-playwright-results.json` 保留本次部分通过场景和脚本停止原因；`dev040-independent-verification.spec.cjs` 为独立复跑入口。
- 环境边界：本次只验证本地 H5 构建与确定性 Playwright 夹具；测试服务器尚未部署，未访问真实账号、真实后端或测试服务器页面，不得将本地结果表述为测试环境端到端通过。

## 企业端身份分流失败重测（2026-08-15）

- 最终结论：`FAIL`，不允许进入提交阶段。
- 唯一断言修正：依据 `AC-PROFILETAB-001` 的“点击 active 项不重复跳转”，移除首页 active 点击产生 `/pages/home` `reLaunch` 的错误预期；AI 助手和“我的”仍分别严格预期 `/pages/center`、`/pages/profile`。该场景本次通过。
- 完整运行结果：修正后的 `dev040-independent-verification.spec.cjs` 仅完整启动一次，exit `1`，耗时 `41.4s`。已通过无会话首页无闪现、企业历史首页转企业页且学员 DOM/请求为零、无会话兼容入口进登录、学员首页三入口 active no-op 共 4 个场景。
- 新失败：`home-to-assessment` 在第 297 行等待并点击“考题测评”时 30 秒超时。该失败属于旧断言之后的新实现行为失败，故按重测门禁立即停止，未扩大脚本修改。
- 未执行场景：测评/答题链路、企业 `hasWtPost`、`auditStatus=2`、H5 preview、`redirectUrl`、review/register，以及学员 approved/redirect/organization-bind 等后续身份矩阵未在本次进程中执行到，不能判定 `AC-PAGEROUTE-001/002/003` 全量通过。
- 源码审计：`independent-source-audit.json` 为 `passed`，企业首页门禁、应用代码白名单、禁止目标与 Gitee 基线一致性通过。
- 停止边界：按“脚本失败立即记录并停止”要求，本次未继续执行 `pnpm type-check`、`pnpm run build:h5`、`git diff --check`、冲突标记或 `uni_modules/**` 审计；不得复用首轮结果冒充本次重测结果。
- 环境边界：仅使用本地 H5 与确定性 Playwright 夹具；未访问测试服务器、真实账号或真实后端。

## 企业端身份分流聚焦独立验收（2026-08-15）

- 最终结论：本轮 `AC-PAGEROUTE-001/002/003` 聚焦独立验收 `PASS`，允许提交；测试环境端到端验收保持待执行。
- 执行入口：在 `code/develop/yunjikeji` 工作目录原样运行 `DEV-040/dev040-page-routing.spec.cjs`，exit `0`；`playwright-results.json` 为 `passed`，`errors=[]`。
- 身份结果：无会话首页进入登录页且学员内容计数为 `0`；企业历史 `/pages/home` 进入 `/pages/service/customer-service`，学员请求为 `0`、学员自测内容为 `0`；企业正常状态、H5 preview、redirect、review/register 与学员审核/绑定/default 分支均通过源码和运行断言。
- 学员回归：学员首页、AI 助手、我的和“开始训练”正常；训练进入当前 Gitee 基线 `/pages/practice/exam-topics`；答题返回/完成、页面栈返回与退出登录关联场景通过。
- 质量结果：`pnpm type-check` exit `0`；`pnpm run build:h5` exit `0`；`git diff --check` exit `0`；未合并文件、冲突标记、`uni_modules/**` 工作区和暂存差异均为 `0`。
- 环境边界：使用本机 `5173` H5 服务、本机 Chrome 和确定性会话/接口夹具；尚未部署测试服务器，未使用真实企业或学员账号，不得表述为测试环境端到端已通过。
